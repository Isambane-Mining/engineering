"""Synthetic secrets only; native Frappe queue context/OAuth, no DB or SMTP."""

import base64
import smtplib
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.email.doctype.email_queue import email_queue

with patch.object(frappe, "conf", frappe._dict()):
    from frappe.integrations.doctype.connected_app import connected_app


class TestPrivateDeliveryBoundaries(TestCase):
    def privacy(self):
        from engineering.controllers import fleet_health_privacy

        self.assertTrue(
            callable(getattr(fleet_health_privacy, "send_private_queue", None))
        )
        return fleet_health_privacy

    def test_native_oauth_refresh_cannot_create_raw_error_log(self):
        privacy = self.privacy()
        token = SimpleNamespace(
            name="synthetic-token", is_expired=lambda: True, reload=lambda: None
        )
        raw_log = Mock()
        oauth = Mock(
            return_value=SimpleNamespace(
                refresh_token=Mock(side_effect=RuntimeError("synthetic-refresh-secret"))
            )
        )
        app = SimpleNamespace(
            get_token_cache=lambda user: token,
            get_oauth2_session=oauth,
            redirect_uri="https://example.invalid/callback",
            token_uri="https://example.invalid/token",
            log_error=raw_log,
        )
        app.get_active_token = lambda user: connected_app.ConnectedApp.get_active_token(
            app, user
        )
        account = SimpleNamespace(
            name="LAB",
            connected_app="Microsoft",
            backend_app_flow=0,
            connected_user="service",
        )

        def get_doc(doctype, name):
            return account if doctype == "Email Account" else app

        with (
            patch.object(privacy.frappe, "get_doc", side_effect=get_doc),
            patch.object(connected_app, "filelock", return_value=nullcontext()),
            self.assertRaisesRegex(
                frappe.ValidationError, "^Fleet Health delivery failed\\.$"
            ),
        ):
            privacy._private_account(SimpleNamespace(**vars(account))).get_smtp_server()
        oauth.assert_called_once_with("service")
        raw_log.assert_not_called()

    def test_account_drift_is_rejected_before_loading_private_token(self):
        privacy = self.privacy()
        approved = SimpleNamespace(
            name="LAB", email_id="juan@isambane.co.za", smtp_server="smtp.office365.com"
        )
        changed = SimpleNamespace(
            name="LAB",
            email_id="juan@isambane.co.za",
            smtp_server="example.invalid",
            connected_app="Microsoft",
        )
        with (
            patch.object(privacy.frappe, "get_doc", return_value=changed) as get_doc,
            self.assertRaises(frappe.ValidationError),
        ):
            privacy._private_account(approved)
        self.assertEqual(get_doc.call_count, 1)

    def test_native_queue_context_persists_only_generic_error_before_commit(self):
        privacy = self.privacy()
        writes = []

        class Queue:
            retry = 0
            recipients = ()
            redact_message_after_send = False

            def update_status(self, **kwargs):
                writes.append(kwargs)

            def send(self, smtp_server_instance=None):
                with email_queue.SendMailContext(self, smtp_server_instance):
                    raise RuntimeError("synthetic-smtp-secret")

        queue = Queue()
        original_update = queue.update_status
        with (
            patch.object(email_queue, "get_email_retry_limit", return_value=3),
            self.assertRaisesRegex(
                frappe.ValidationError, "^Fleet Health delivery failed\\.$"
            ) as error,
        ):
            privacy.send_private_queue(queue, SimpleNamespace(name="LAB"))
        self.assertTrue(error.exception.skip_error_log)
        self.assertNotIn("synthetic-smtp-secret", str(writes))
        self.assertEqual(writes[-1]["error"], "Fleet Health delivery failed.")
        self.assertEqual(writes[-1]["status"], "Error")
        self.assertEqual(queue.update_status, original_update)

    def test_private_messages_removed_without_changing_other_requests(self):
        privacy = self.privacy()
        messages = ["ordinary existing message"]
        with patch.object(privacy.frappe.local, "message_log", messages, create=True):
            with privacy.private_delivery():
                privacy.frappe.local.message_log.append("synthetic-password")
            self.assertEqual(messages, ["ordinary existing message"])

    def test_failure_is_excluded_from_framework_error_snapshots(self):
        privacy = self.privacy()
        from frappe.utils import error

        with patch.object(error, "log_error") as logger:
            error.log_error_snapshot(privacy.delivery_error())
        logger.assert_not_called()

    def test_smtp_auth_failure_never_calls_native_global_error_logger(self):
        privacy = self.privacy()
        connection = smtplib.SMTP()
        replies = iter([(334, b""), (535, b"synthetic-smtp-secret")])
        connection.docmd = lambda *args: next(replies)
        connection.close = Mock()
        server = privacy._PrivateSMTPServer(
            server="smtp.office365.com",
            login="service",
            access_token="synthetic-token",
            use_oauth=1,
        )
        with (
            patch.object(privacy, "SMTP", return_value=connection),
            patch.object(frappe, "log_error") as logger,
            self.assertRaisesRegex(
                frappe.ValidationError, "^Fleet Health delivery failed\\.$"
            ),
        ):
            _ = server.session
        logger.assert_not_called()
        connection.close.assert_called_once()

    def test_smtp_preserves_xoauth2_tls_ssl_and_session_reuse(self):
        privacy = self.privacy()
        for use_ssl, use_tls in [(False, True), (True, False)]:
            connection = smtplib.SMTP()
            calls = []
            replies = iter([(334, b""), (235, b"accepted")])

            def command(*args, calls=calls, replies=replies):
                calls.append(args)
                return next(replies)

            connection.docmd = command
            connection.ehlo = Mock()
            connection.starttls = Mock()
            connection.noop = lambda: (250, b"ok")
            server = privacy._PrivateSMTPServer(
                server="smtp.office365.com",
                login="service",
                access_token="synthetic-token",
                use_oauth=1,
                use_ssl=use_ssl,
                use_tls=use_tls,
            )
            with (
                patch.object(privacy, "SMTP", return_value=connection) as plain,
                patch.object(privacy, "SMTP_SSL", return_value=connection) as secure,
                patch.object(server, "_enqueue_connection_closure"),
                patch.object(frappe, "conf", frappe._dict()),
            ):
                self.assertIs(server.session, connection)
                self.assertIs(server.session, connection)
            wire = base64.b64decode(calls[1][0]).decode()
            self.assertEqual(
                wire, "user=service\x01auth=Bearer synthetic-token\x01\x01"
            )
            self.assertEqual(connection.starttls.call_count, int(use_tls))
            self.assertEqual((secure if use_ssl else plain).call_count, 1)

    def test_queue_is_claimed_before_token_refresh_can_commit(self):
        privacy = self.privacy()
        states = []

        class Queue:
            retry = 0
            recipients = ()
            redact_message_after_send = False

            def update_status(self, **kwargs):
                states.append(kwargs["status"])

            def send(self):
                with email_queue.SendMailContext(self) as context:
                    context.fetch_outgoing_server()

        class Account:
            service = "Outlook.com"

            def get_smtp_server(self):
                self_test.assertEqual(states[-1], "Sending")
                raise RuntimeError("synthetic-refresh-secret")

        self_test = self
        with (
            patch.object(privacy, "_private_account", return_value=Account()),
            patch.object(email_queue, "get_email_retry_limit", return_value=3),
            self.assertRaises(frappe.ValidationError),
        ):
            privacy.send_private_queue(Queue(), SimpleNamespace(name="LAB"))
        self.assertEqual(states, ["Sending", "Error"])

    def test_sent_copy_preserves_folder_and_never_logs_failed_imap_auth(self):
        privacy = self.privacy()
        token = SimpleNamespace(get_password=lambda field: "synthetic-imap-token")
        account = SimpleNamespace(
            enable_incoming=True,
            use_imap=True,
            use_ssl=True,
            email_server="outlook.office365.com",
            incoming_port=993,
            use_starttls=False,
            sent_folder_name="CustomSent",
            name="LAB",
            email_id="service",
            get_oauth_token=lambda: token,
        )
        connection = Mock()
        for fails in (False, True):
            connection.reset_mock()
            connection.authenticate.side_effect = (
                RuntimeError("synthetic-imap-secret") if fails else None
            )
            with (
                patch.object(privacy, "IMAP4_SSL", return_value=connection),
                patch.object(frappe, "conf", frappe._dict()),
                patch.object(frappe, "log_error") as logger,
            ):
                privacy._append_sent(account, b"private report")
            logger.assert_not_called()
            self.assertEqual(connection.append.call_count, 0 if fails else 1)
            if not fails:
                self.assertEqual(connection.append.call_args.args[0], "CustomSent")
                self.assertEqual(
                    connection.append.call_args.args[-1], b"private report"
                )
            connection.logout.assert_called_once()

    def test_failed_quit_closes_socket_and_later_response_callback_is_safe(self):
        privacy = self.privacy()
        connection = Mock()
        connection.quit.side_effect = RuntimeError("synthetic-quit-secret")
        connection.noop.return_value = (250, b"ok")
        server = privacy._PrivateSMTPServer(
            server="smtp.office365.com", access_token="synthetic-token"
        )
        server._session = connection
        callback = server.quit
        with privacy.private_delivery():
            server.quit()
        callback()
        connection.close.assert_called_once()
        self.assertIsNone(server._session)
