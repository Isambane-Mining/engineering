"""Synthetic credential markers only. No real credentials, DB, mail, or telemetry."""
import base64
import importlib.util
import smtplib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from frappe.utils import _get_traceback_sanitizer
from sentry_sdk import Client, Hub
from traceback_with_variables import iter_exc_lines


class TestFleetHealthPrivacy(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("engineering.api.fleet_health_privacy"),
                             "Scoped Fleet Health privacy protection is missing")
        from engineering.api import fleet_health_privacy
        self.privacy = fleet_health_privacy

    def auth_failure_trace(self):
        # Exercise the actual stdlib response local that upstream OAuth logs expose.
        client = smtplib.SMTP()
        replies = iter([(334, b""), (535, b"synthetic authentication rejection")])
        client.docmd = lambda *args: next(replies)
        try:
            client.auth("XOAUTH2", lambda challenge: "synthetic-auth-marker", initial_response_ok=False)
        except smtplib.SMTPAuthenticationError:
            return "\n".join(iter_exc_lines(fmt=_get_traceback_sanitizer()))

    def test_oauth_response_locals_are_redacted_only_during_private_delivery(self):
        encoded = base64.b64encode(b"synthetic-auth-marker").decode()
        self.assertIn(encoded, self.auth_failure_trace())
        with self.privacy.private_delivery():
            trace = self.auth_failure_trace()
        self.assertNotIn(encoded, trace)
        self.assertIn("[REDACTED]", trace)
        self.assertIn(encoded, self.auth_failure_trace())

    def test_error_log_hook_replaces_diagnostics_only_in_lab_delivery(self):
        doc = SimpleNamespace(error="synthetic diagnostic", method="upstream error", metadata="context")
        with patch.object(self.privacy, "frappe", SimpleNamespace(local=SimpleNamespace(site="juan.isambane.co.za"))):
            self.privacy.redact_error_log(doc)
            self.assertEqual(doc.error, "synthetic diagnostic")
            with self.privacy.private_delivery():
                self.privacy.redact_error_log(doc)
            self.assertEqual(doc.error, "Fleet Health delivery failed. Diagnostics redacted.")
            self.assertIsNone(doc.metadata)

    def test_private_delivery_suppresses_only_its_own_sentry_events(self):
        events = []
        client = Client(dsn="https://public@example.test/1", default_integrations=False,
                        transport=lambda event: events.append(event))
        with Hub(client):
            with self.privacy.private_delivery():
                Hub.current.capture_message("private synthetic diagnostic")
            self.assertEqual(events, [])
            Hub.current.capture_message("ordinary event")
            self.assertEqual(len(events), 1)
        client.close()
