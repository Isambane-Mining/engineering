"""Request-scoped protection for contextual OAuth diagnostics in LAB Frappe."""

# Errors at this privacy boundary must not be logged, including cleanup failures.
# ruff: noqa: BLE001, S110

import ssl
import time
from contextlib import contextmanager
from contextvars import ContextVar
from imaplib import IMAP4, IMAP4_SSL, Time2Internaldate
from smtplib import SMTP, SMTP_SSL

import frappe
from frappe.email.oauth import Oauth
from frappe.email.smtp import SMTPServer
from frappe.utils import _get_traceback_sanitizer
from sentry_sdk import Hub

_private = ContextVar("fleet_health_private_delivery", default=False)


def _hide_variables(*_args):
    return _private.get()


def _install_formatter():
    # Lazy, idempotent registration; importing a compatibility module has no effect.
    printers = _get_traceback_sanitizer().custom_var_printers
    if not any(predicate is _hide_variables for predicate, _printer in printers):
        printers.insert(0, (_hide_variables, lambda _value: "[REDACTED]"))


@contextmanager
def private_delivery():
    _install_formatter()
    marker = _private.set(True)
    messages = getattr(frappe.local, "message_log", None)
    message_count = len(messages) if isinstance(messages, list) else 0
    try:
        # Frappe's telemetry captures raw exceptions independently of its formatter.
        # A cloned hub keeps event suppression local to this delivery request.
        with Hub(Hub.current) as hub, hub.push_scope() as scope:
            scope.add_event_processor(lambda _event, _hint: None)
            yield
    finally:
        # SMTP's frappe.throw can add the raw server response to the HTTP message log.
        current = getattr(frappe.local, "message_log", None)
        if isinstance(current, list):
            del current[message_count:]
        _private.reset(marker)


def delivery_error(error_type=None):
    error = (error_type or frappe.ValidationError)("Fleet Health delivery failed.")
    # Frappe's native snapshot path otherwise records request payload/metadata later.
    error.skip_error_log = True
    return error


def _private_account(approved_account):
    # Fresh documents only: never mutate cached accounts or framework classes.
    account = frappe.get_doc("Email Account", approved_account.name)
    fields = (
        "email_id",
        "smtp_server",
        "smtp_port",
        "auth_method",
        "enable_outgoing",
        "default_outgoing",
        "connected_app",
        "connected_user",
        "backend_app_flow",
        "always_bcc",
        "service",
        "no_smtp_authentication",
        "use_tls",
        "use_ssl_for_outgoing",
        "append_emails_to_sent_folder",
        "enable_incoming",
        "use_imap",
        "email_server",
        "incoming_port",
        "use_ssl",
        "use_starttls",
        "sent_folder_name",
        "login_id",
    )
    if any(
        getattr(account, field, None) != getattr(approved_account, field, None)
        for field in fields
    ):
        raise delivery_error()
    token = None

    def get_token():
        nonlocal token
        if token is None:
            app = frappe.get_doc("Connected App", account.connected_app)
            # Native refresh catches/logs before returning. Only this fresh instance
            # suppresses its private diagnostic; other Connected Apps are unchanged.
            app.log_error = lambda *args, **kwargs: None
            token = (
                app.get_backend_app_token()
                if account.backend_app_flow
                else app.get_active_token(account.connected_user)
            )
            if token is None:
                raise delivery_error()
        return token

    account.get_oauth_token = get_token
    account.get_smtp_server = lambda: _server_for_account(account)
    account.append_email_to_sent_folder = lambda message: _append_sent(account, message)
    return account


def _server_for_account(account):
    account.get_oauth_token()
    if not getattr(account, "_private_smtp", None):
        account._private_smtp = _PrivateSMTPServer(**account.sendmail_config())
    return account._private_smtp


class _PrivateSMTPServer(SMTPServer):
    """Native SMTP/TLS/protocol, without Oauth.connect's global error logger."""

    @property
    def session(self):
        if self.is_session_active():
            return self._session
        connection = None
        try:
            connection = (SMTP_SSL if self.use_ssl else SMTP)(
                self.server, self.port, timeout=self.timeout
            )
            self.secure_session(connection)
            # The installed native primitive sends the identical XOAUTH2 challenge.
            # Oauth.connect adds a raw log_error before raising; do not use it here.
            Oauth(
                connection, self.email_account, self.login, self.access_token
            )._connect_smtp()
            if not frappe.conf.smtp_no_ehlo_after_auth:
                connection.ehlo()
            self._session = connection
            self._enqueue_connection_closure()
            return connection
        except Exception:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            raise delivery_error() from None

    def quit(self):
        # Frappe may call this again after_response, outside the private scope.
        connection, self._session = self._session, None
        self.access_token = self.password = None
        if connection is not None:
            try:
                connection.quit()
            except Exception:
                pass
            finally:
                try:
                    connection.close()
                except Exception:
                    pass


def _append_sent(account, message):
    """Preserve best-effort sent copies without native IMAP/OAuth diagnostic logs."""
    if not (account.enable_incoming and account.use_imap):
        return
    connection = None
    try:
        from frappe.email.utils import get_port

        token = account.get_oauth_token().get_password("access_token")
        if account.use_ssl:
            connection = IMAP4_SSL(
                account.email_server,
                get_port(account),
                timeout=frappe.conf.imap_timeout,
                ssl_context=ssl.create_default_context(),
            )
        else:
            connection = IMAP4(
                account.email_server,
                get_port(account),
                timeout=frappe.conf.imap_timeout,
            )
            if account.use_starttls:
                connection.starttls()
        Oauth(
            connection,
            account.name,
            getattr(account, "login_id", None) or account.email_id,
            token,
        )._connect_imap()
        connection.append(
            account.sent_folder_name or "Sent",
            "\\Seen",
            Time2Internaldate(time.time()),
            frappe.safe_encode(message),
        )
    except Exception:
        # Native sent-copy is best effort too. Never expose its server response,
        # request metadata, credentials, or turn an accepted SMTP send into a retry.
        pass
    finally:
        if connection is not None:
            try:
                connection.logout()
            except Exception:
                pass


def send_private_queue(queue, approved_account):
    """Keep native Sending-before-OAuth ordering and sanitize before each commit."""
    update_status = queue.update_status
    original_get = getattr(queue, "get_email_account", None)
    account = None

    def safe_account(*args, **kwargs):
        nonlocal account
        if account is None:
            account = _private_account(approved_account)
        return account

    def safe_status(*args, **kwargs):
        if kwargs.get("error"):
            kwargs.update(error="Fleet Health delivery failed.", status="Error")
        return update_status(*args, **kwargs)

    with private_delivery():
        queue.update_status = safe_status
        queue.get_email_account = safe_account
        try:
            # Native context commits Sending, then asks for this request's account.
            # Token refresh must not commit a newly built queue as Not Sent.
            queue.send()
        except Exception:
            raise delivery_error() from None
        finally:
            queue.update_status = update_status
            if original_get is None:
                del queue.get_email_account
            else:
                queue.get_email_account = original_get
            if account is not None:
                server = getattr(account, "_private_smtp", None)
                if server is not None:
                    try:
                        server.quit()
                    except Exception:
                        pass


def redact_error_log(doc, method=None):
    """Legacy explicit-call compatibility; no DocType hook is registered."""
    if _private.get() and frappe.local.site == "juan.isambane.co.za":
        doc.error = "Fleet Health delivery failed. Diagnostics redacted."
        doc.method = "Fleet Health delivery"
        doc.metadata = None
