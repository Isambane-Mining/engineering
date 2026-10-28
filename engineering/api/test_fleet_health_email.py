"""Offline contract tests: real endpoint, isolated mail/DB boundaries; never sends mail."""
import base64
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


class TestFleetHealthEmail(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec("engineering.api.fleet_health_email")
        self.assertIsNotNone(spec, "The restricted Fleet Health endpoint is missing")
        from engineering.api import fleet_health_email
        self.api = fleet_health_email
        self.account = SimpleNamespace(name="LAB OAuth", email_id="juan@isambane.co.za",
            enable_outgoing=1, default_outgoing=1, auth_method="OAuth",
            smtp_server="smtp.office365.com", always_bcc="", connected_app="Microsoft")
        self.queue = SimpleNamespace(name="test-queue", status="Not Sent", email_account="LAB OAuth",
            sender="LAB <juan@isambane.co.za>", recipients=[SimpleNamespace(recipient="juan@isambane.co.za", status="Sent")],
            send=Mock(), reload=Mock(), db_set=Mock())
        self.queue.send.side_effect = lambda: setattr(self.queue, "status", "Sent")
        self.frappe = SimpleNamespace(local=SimpleNamespace(site="juan.isambane.co.za"),
            session=SimpleNamespace(user="erp.intelligence@isambane.co.za"),
            request=SimpleNamespace(method="POST"), PermissionError=PermissionError,
            ValidationError=ValueError, throw=lambda message, exc=ValueError: self.fail_with(message, exc),
            sendmail=Mock(return_value=self.queue), are_emails_muted=lambda: False,
            get_hooks=Mock(return_value=[]))
        self.fp = patch.object(self.api, "frappe", self.frappe)
        self.ap = patch.object(self.api.EmailAccount, "find_default_outgoing", return_value=self.account)
        self.fp.start(); self.ap.start()
        self.addCleanup(self.fp.stop); self.addCleanup(self.ap.stop)
        self.payload = dict(subject="Daily Fleet Health — Koppie — 1 July 2026",
            text="24 machines checked", html="<h2>Daily Fleet Health — Koppie</h2>", attachments=[
                self.attachment("daily-fleet-health-koppie-2026-07-01.pdf", "application/pdf", b"%PDF-1.7\nfixture\n%%EOF\n"),
                self.attachment("daily-fleet-health-koppie-2026-07-01.html", "text/html", b"<!doctype html><html><head><title>Daily Fleet Health</title></head><body>Report</body></html>")])

    @staticmethod
    def fail_with(message, exc):
        raise exc(message)

    @staticmethod
    def attachment(name, mime, content):
        return dict(filename=name, content_type=mime, content_base64=base64.b64encode(content).decode())

    def send(self):
        return self.api.send_fleet_health_email(**self.payload)

    def rejected(self):
        with self.assertRaises((ValueError, PermissionError)):
            self.send()
        self.frappe.sendmail.assert_not_called()

    def test_sends_only_to_juan_through_default_account_and_confirms_queue(self):
        result = self.send()
        self.assertEqual(result, {"status": "sent", "queue_id": "test-queue"})
        kwargs = self.frappe.sendmail.call_args.kwargs
        self.assertEqual(kwargs["recipients"], ["juan@isambane.co.za"])
        self.assertNotIn("sender", kwargs)  # Let Frappe resolve global default outgoing.
        self.assertEqual(kwargs["cc"], [])
        self.assertEqual(kwargs["bcc"], [])
        self.assertTrue(kwargs["delayed"])
        self.assertEqual(len(kwargs["attachments"]), 2)
        self.assertTrue(kwargs["attachments"][0]["fcontent"].startswith(b"%PDF-"))

    def test_rejects_every_other_site_even_for_administrator(self):
        self.frappe.local.site = "production.invalid"
        self.frappe.session.user = "Administrator"
        self.rejected()

    def test_only_service_user_and_administrator_allowed(self):
        for user in ["Guest", "juan@isambane.co.za", "other@example.test", "", None]:
            self.frappe.session.user = user
            self.rejected()
        self.frappe.session.user = "Administrator"
        self.assertEqual(self.send()["status"], "sent")

    def test_post_only(self):
        self.frappe.request.method = "GET"
        self.rejected()

    def test_rejects_all_envelope_overrides_including_empty(self):
        for key in ["to", "recipients", "cc", "bcc", "sender", "from", "reply_to", "email_account", "headers", "unexpected"]:
            for value in [None, "", "juan@isambane.co.za", ["other@example.test"]]:
                self.payload[key] = value
                self.rejected()
                del self.payload[key]

    def test_exactly_one_matching_pdf_and_html(self):
        original = self.payload["attachments"]
        for attachments in [None, {}, "[]", [], original[:1], original * 2, [original[0], original[0]]]:
            self.payload["attachments"] = attachments
            self.rejected()
        self.payload["attachments"] = original
        original[1]["filename"] = "daily-fleet-health-koppie-2026-07-02.html"
        self.rejected()

    def test_rejects_names_mime_and_attachment_extra_fields(self):
        first = self.payload["attachments"][0]
        for name in ["../report.pdf", "/tmp/report.pdf", "report.pdf", "daily-fleet-health-koppie-2026-02-30.pdf", "daily-fleet-health-other-2026-07-01.pdf", "daily-fleet-health-koppie-2026-07-01.pdf\r\nBcc:x"]:
            old = first["filename"]; first["filename"] = name
            self.rejected(); first["filename"] = old
        first["content_type"] = "text/html"
        self.rejected(); first["content_type"] = "application/pdf"
        first["file_url"] = "https://example.test/file"
        self.rejected()

    def test_rejects_malformed_empty_and_noncanonical_base64_and_fake_pdf(self):
        first = self.payload["attachments"][0]
        for value in [None, 1, "", "!!!!", "YQ===", "Y Q==", "YR==", "aGVsbG8="]:
            first["content_base64"] = value
            self.rejected()

    def test_limits_total_decoded_and_encoded_size(self):
        self.payload["attachments"][0]["content_base64"] = "A" * (14 * 1024 * 1024)
        self.rejected()
        pdf = b"%PDF-1.7\n" + b"a" * (6 * 1024 * 1024) + b"\n%%EOF"
        html = b"<!doctype html><html><title>Daily Fleet Health</title>" + b"a" * (5 * 1024 * 1024) + b"</html>"
        self.payload["attachments"][0]["content_base64"] = base64.b64encode(pdf).decode()
        self.payload["attachments"][1]["content_base64"] = base64.b64encode(html).decode()
        self.rejected()

    def test_rejects_non_report_or_active_html(self):
        for content in [b"hello", b"\xff", b"<!doctype html><html><title>Fleet Health</title><script>alert(1)</script></html>"]:
            self.payload["attachments"][1]["content_base64"] = base64.b64encode(content).decode()
            self.rejected()

    def test_rejects_header_injection_and_unbounded_body(self):
        for key, value in [("subject", "Fleet Health\r\nBcc: x"), ("subject", "Other report"), ("html", "x" * 65537), ("text", None)]:
            old = self.payload[key]; self.payload[key] = value
            self.rejected(); self.payload[key] = old

    def test_requires_approved_default_microsoft_oauth_without_bcc(self):
        for key, value in [("email_id", "other@example.test"), ("auth_method", "Basic"), ("smtp_server", "smtp.example.test"), ("always_bcc", "juan@isambane.co.za"), ("enable_outgoing", 0), ("default_outgoing", 0), ("connected_app", "")]:
            old = getattr(self.account, key); setattr(self.account, key, value)
            self.rejected(); setattr(self.account, key, old)

    def test_never_reports_queued_or_failed_as_sent(self):
        self.queue.send.side_effect = None
        with self.assertRaises(ValueError): self.send()

    def test_rechecks_queue_envelope_before_sending(self):
        self.queue.recipients.append(SimpleNamespace(recipient="other@example.test"))
        with self.assertRaises(ValueError): self.send()
        self.queue.send.assert_not_called()

    def test_send_error_is_generic(self):
        self.queue.send.side_effect = RuntimeError("upstream private diagnostic")
        with self.assertRaisesRegex(ValueError, "^Fleet Health delivery failed\\.$"):
            self.send()

    def test_framework_cmd_must_match_the_endpoint(self):
        self.payload["cmd"] = "engineering.api.fleet_health_email.send_fleet_health_email"
        self.assertEqual(self.send()["status"], "sent")
        self.frappe.sendmail.reset_mock()
        self.payload["cmd"] = "other.method"
        self.rejected()

    def test_accepts_the_lab_outlook_oauth_host(self):
        self.account.smtp_server = "smtp-mail.outlook.com"
        self.account.service = "Outlook.com"
        self.assertEqual(self.send()["status"], "sent")

    def test_rejects_alternative_frappe_mail_transport(self):
        self.account.service = "Frappe Mail"
        self.rejected()

    def test_failed_delivery_cannot_retry_in_background(self):
        self.queue.send.side_effect = RuntimeError("failed")
        self.queue.db_set = Mock()
        with self.assertRaises(ValueError): self.send()
        self.queue.db_set.assert_called_once_with({"status": "Error", "error": "Fleet Health delivery failed."}, commit=True)

    def test_rejects_css_escapes_and_comments(self):
        for css in [r"body{background:u\72l(https://example.test/pixel)}", "@im/**/port 'https://example.test/a.css'"]:
            self.payload["html"] = "<style>" + css + "</style><h2>Fleet Health</h2>"
            self.rejected()
