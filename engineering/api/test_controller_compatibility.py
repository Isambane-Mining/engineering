"""Public import/HTTP contracts; no site, database or transport."""

import importlib
import importlib.util
import unittest
from unittest.mock import patch

import frappe


class TestControllerBoundaries(unittest.TestCase):
    def test_email_api_delegates_to_non_whitelisted_controller(self):
        name = "engineering.controllers.fleet_health_email"
        self.assertIsNotNone(importlib.util.find_spec(name))
        controller = importlib.import_module(name)
        api = importlib.import_module("engineering.api.fleet_health_email")
        with patch.object(
            controller,
            "send_fleet_health_email",
            return_value={"status": "sent", "queue_id": "synthetic"},
        ) as send:
            result = api.send_fleet_health_email(
                subject="example", cmd=controller.METHOD
            )
        self.assertEqual(result["queue_id"], "synthetic")
        self.assertEqual(
            send.call_args.kwargs,
            {
                "subject": "example",
                "text": None,
                "html": None,
                "attachments": None,
                "cmd": controller.METHOD,
            },
        )
        self.assertIn(api.send_fleet_health_email, frappe.whitelisted)
        self.assertNotIn(controller.send_fleet_health_email, frappe.whitelisted)

    def test_privacy_and_tyre_imports_remain_compatible(self):
        for name in ("fleet_health_privacy", "tyre_damage"):
            self.assertIsNotNone(
                importlib.util.find_spec("engineering.controllers." + name)
            )
        privacy = importlib.import_module(
            "engineering.controllers.fleet_health_privacy"
        )
        api = importlib.import_module("engineering.api.fleet_health_privacy")
        self.assertIs(api.private_delivery, privacy.private_delivery)
        tyre = importlib.import_module("engineering.controllers.tyre_damage")
        page = importlib.import_module(
            "engineering.engineering.page.daily_availability_and_utilization_dashboard.tyre_damage"
        )
        self.assertIs(page.fetch_tyre_damage_records, tyre.fetch_tyre_damage_records)
        self.assertEqual(page.damage_counts([]), {"ADT": 0, "Dozer": 0})
        self.assertIn("daily-tyre-kpi", page.tyre_damage_card("ADT", 2))

    def test_obsolete_global_hooks_are_absent(self):
        from engineering import hooks

        self.assertNotIn("Error Log", hooks.doc_events)
        self.assertNotIn("WhatsApp Message", hooks.doc_events)
        self.assertIn("Asset Movement", hooks.doc_events)

    def test_validation_failure_cannot_snapshot_private_request_payload(self):
        from engineering.api import fleet_health_email as api
        from engineering.controllers import fleet_health_email as controller

        error = frappe.ValidationError("Invalid Fleet Health payload.")
        with (
            patch.object(controller, "send_fleet_health_email", side_effect=error),
            self.assertRaises(frappe.ValidationError) as caught,
        ):
            api.send_fleet_health_email(attachments="private invalid attachment")
        self.assertTrue(getattr(caught.exception, "skip_error_log", False))
