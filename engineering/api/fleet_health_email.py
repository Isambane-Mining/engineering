"""Private LAB Fleet Health delivery boundary. Never register this as an MCP tool."""
import base64
import binascii
import re
from datetime import date
from email.utils import parseaddr
from html.parser import HTMLParser

import frappe
from frappe.email.doctype.email_account.email_account import EmailAccount
from engineering.api.fleet_health_privacy import private_delivery

LAB_SITE = "juan.isambane.co.za"
RECIPIENT = "juan@isambane.co.za"
METHOD = "engineering.api.fleet_health_email.send_fleet_health_email"
MAX_BYTES = 10 * 1024 * 1024
MAX_ENCODED = 4 * ((MAX_BYTES + 2) // 3)
NAME = re.compile(r"(daily|weekly)-fleet-health-koppie-(\d{4}-\d{2}-\d{2})(?:-to-(\d{4}-\d{2}-\d{2}))?\.(pdf|html)")


def _reject(message="Invalid Fleet Health payload."):
    frappe.throw(message, frappe.ValidationError)


class _ReportHTML(HTMLParser):
    """Only passive, self-contained markup used by the Fleet Health renderer."""
    tags = {"html", "head", "meta", "title", "style", "body", "main", "section", "article",
            "header", "footer", "div", "span", "h1", "h2", "p", "b", "strong", "em", "small", "br"}
    attrs = {"class", "lang", "charset", "name", "content"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.in_style = False

    def handle_data(self, data):
        if self.in_style and ("\\" in data or "/*" in data):
            _reject()

    def handle_starttag(self, tag, attrs):
        self.in_style = tag == "style"
        if tag not in self.tags or any(name not in self.attrs for name, _ in attrs):
            _reject()
        if tag == "meta" and any(name == "name" and value != "viewport" for name, value in attrs):
            _reject()

    def handle_endtag(self, tag):
        self.in_style = False
        if tag not in self.tags:
            _reject()

    def handle_decl(self, decl):
        if decl.lower() != "doctype html":
            _reject()


def _validate_html(value, document=False):
    if not isinstance(value, str) or not value or "\x00" in value:
        _reject()
    if re.search(r"url\s*\(|image-set\s*\(|@import|expression\s*\(|javascript\s*:", value, re.I):
        _reject()
    if document and (not value.lower().startswith("<!doctype html>")
                     or "fleet health" not in value.lower() or not value.rstrip().lower().endswith("</html>")):
        _reject()
    parser = _ReportHTML(convert_charrefs=True)
    parser.feed(value)
    parser.close()


def _attachments(items):
    if not isinstance(items, list) or len(items) != 2:
        _reject()
    decoded, names, extensions, total, encoded_total = [], set(), set(), 0, 0
    for item in items:
        if not isinstance(item, dict) or set(item) != {"filename", "content_type", "content_base64"}:
            _reject()
        name = item["filename"]
        match = NAME.fullmatch(name) if isinstance(name, str) else None
        if not match:
            _reject()
        mode, start, end, ext = match.groups()
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end) if end else start_date
        except ValueError:
            _reject()
        if (mode == "daily" and end is not None) or (mode == "weekly" and (not end or (end_date - start_date).days != 6)):
            _reject()
        if ext in extensions or item["content_type"] != {"pdf": "application/pdf", "html": "text/html"}[ext]:
            _reject()
        names.add(name.rsplit(".", 1)[0])
        extensions.add(ext)
        encoded = item["content_base64"]
        if not isinstance(encoded, str) or not encoded:
            _reject()
        encoded_total += len(encoded)
        if encoded_total > MAX_ENCODED + 4:  # Two separately padded attachments.
            _reject()
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            _reject()
        if not content or base64.b64encode(content).decode("ascii") != encoded:
            _reject()
        total += len(content)
        if total > MAX_BYTES:
            _reject()
        if ext == "pdf":
            if not content.startswith(b"%PDF-") or not content.rstrip().endswith(b"%%EOF"):
                _reject()
        else:
            try:
                html = content.decode("utf-8")
            except UnicodeDecodeError:
                _reject()
            _validate_html(html, document=True)
        decoded.append({"fname": name, "fcontent": content})
    if len(names) != 1 or extensions != {"pdf", "html"}:
        _reject()
    return decoded


@frappe.whitelist(methods=["POST"])
def send_fleet_health_email(subject=None, text=None, html=None, attachments=None, **kwargs):
    """Send exactly two generated reports; return only confirmed queue delivery evidence."""
    if frappe.local.site != LAB_SITE or frappe.session.user not in {"erp.intelligence@isambane.co.za", "Administrator"}:
        frappe.throw("Fleet Health delivery is restricted to the LAB service account.", frappe.PermissionError)
    if getattr(frappe, "request", None) and frappe.request.method != "POST":
        frappe.throw("POST required.", frappe.PermissionError)
    # Frappe's v1 dispatcher supplies cmd. No other extra inputs are accepted.
    if kwargs.pop("cmd", METHOD) != METHOD or kwargs:
        _reject("Fleet Health envelope overrides are forbidden.")
    if (not isinstance(subject, str) or len(subject) > 200 or any(ord(c) < 32 for c in subject)
            or not re.fullmatch(r"(?:\[PARTIAL\] )?(?:Daily|Weekly) Fleet Health — Koppie — .+", subject)):
        _reject()
    if not isinstance(text, str) or not text or len(text.encode("utf-8")) > 65536:
        _reject()
    if not isinstance(html, str) or len(html.encode("utf-8")) > 65536:
        _reject()
    _validate_html(html)
    files = _attachments(attachments)
    with private_delivery():
        account = EmailAccount.find_default_outgoing()
        if (not account or account.email_id != RECIPIENT or not account.enable_outgoing
                or not account.default_outgoing or account.auth_method != "OAuth"
                or account.smtp_server not in {"smtp.office365.com", "smtp-mail.outlook.com"}
                or getattr(account, "service", None) == "Frappe Mail"
                or getattr(account, "no_smtp_authentication", False)
                or not account.connected_app or account.always_bcc
                or frappe.are_emails_muted() or frappe.get_hooks("override_email_send")):
            _reject("Approved LAB default outgoing Microsoft OAuth account required.")
        queue = None
        delivery_started = False
        try:
            queue = frappe.sendmail(recipients=[RECIPIENT], subject=subject, message=html,
                attachments=files, cc=[], bcc=[], delayed=True, add_unsubscribe_link=0)
            # Check the actual queue too, before any SMTP side effect, including hook/account drift.
            if (not queue or queue.email_account != account.name or parseaddr(queue.sender)[1] != RECIPIENT
                    or [row.recipient for row in queue.recipients] != [RECIPIENT]):
                _reject()
            delivery_started = True
            queue.send()
            queue.reload()
            if queue.status != "Sent" or any(row.status != "Sent" for row in queue.recipients):
                _reject()
        except Exception:
            # Frappe commits failed queues as retryable. Stop background retries so a
            # failed agent run cannot leave another deliverable copy behind.
            if delivery_started and queue.status != "Sent":
                queue.db_set({"status": "Error", "error": "Fleet Health delivery failed."}, commit=True)
            # Never propagate upstream OAuth/server diagnostics into API responses or Node logs.
            raise frappe.ValidationError("Fleet Health delivery failed.") from None
        return {"status": "sent", "queue_id": queue.name}
