"""Bell database integration tests. HTTP is always mocked."""

import unittest
from datetime import datetime
from unittest.mock import patch

import frappe

from engineering.controllers import bell
from engineering.controllers.bell_client import FleetSnapshot, BellError
from engineering.tests.kobelco_test_support import require_isolated_site


def sample_machine(pin, serial, equipment_id):
    return {
        "equipment_id": equipment_id,
        "pin": pin,
        "serial_number": serial,
        "oem": "BELL",
        "model": "B40D",
        "unit_install_timestamp": datetime(2013, 9, 10),
        "fleet_snapshot_timestamp": datetime(2026, 11, 20, 11, 28),
        "operating_hours": 29144.8,
        "operating_hours_timestamp": datetime(2026, 11, 19, 22),
        "idle_hours": 4745.47,
        "idle_hours_timestamp": datetime(2026, 11, 19, 22),
        "load_count": 50868,
        "load_count_timestamp": datetime(2026, 11, 19, 22),
        "payload": 1351903375.0,
        "payload_units": "kilogram",
        "payload_timestamp": datetime(2026, 11, 19, 22),
        "fuel_consumed": 194258.0,
        "fuel_units": "litre",
        "fuel_consumed_timestamp": datetime(2026, 11, 19, 22),
        "fuel_remaining": 50.0,
        "fuel_remaining_timestamp": datetime(2026, 11, 19, 22),
        "def_remaining": 0.0,
        "def_tank_capacity_units": "litre",
        "def_remaining_timestamp": datetime(2026, 11, 19, 22),
        "odometer": 219361.0,
        "odometer_units": "kilometre",
        "odometer_timestamp": datetime(2026, 11, 19, 22),
        "latitude": -25.9777,
        "longitude": 29.5014,
        "location_timestamp": datetime(2026, 11, 20, 10),
        "engine_number": "1",
        "engine_running": 1,
        "engine_status_timestamp": datetime(2026, 11, 19, 22),
    }


def sample_snapshot():
    return FleetSnapshot(
        machines=[
            sample_machine("PIN-BELL-001", "SERIAL-BELL-001", "IS 532"),
            sample_machine("PIN-BELL-002", "SERIAL-BELL-002", "IS 538"),
        ],
        snapshot_timestamp=datetime(2026, 11, 20, 11, 28),
        raw_xml="<Fleet snapshotTime='2026-11-20T11:28:00Z'/>",
    )


class FakeBellClient:
    def __init__(self, settings):
        pass

    def fetch_fleet(self):
        return sample_snapshot()


class TestBellIntegration(unittest.TestCase):

    def setUp(self):
        require_isolated_site()

        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")

        frappe.db.savepoint("bell_test_case")
        self.addCleanup(self.cleanup_test)

        self.settings = frappe.get_single("API Bell Settings")
        self.settings.update({
            "enabled": 1,
            "token_url": "https://sso.bellequipment.com/connect/token",
            "fleet_url": "https://b-fleet03.bellequipment.com:8080/Fleet",
            "client_id": "ISO_Export_Service",
            "username": "bell-test@example.invalid",
            "password": "test-account-password",
            "client_secret": "test-oauth-secret",
            "scope": "ISO_Exports",
            "timeout": 30,
        })
        self.settings.save(ignore_permissions=True)

    def cleanup_test(self):
        frappe.db.rollback(save_point="bell_test_case")
        frappe.clear_document_cache("API Bell Settings", "API Bell Settings")
        frappe.set_user(self.previous_user)

    def client(self):
        return patch.object(
            bell,
            "BellClient",
            return_value=FakeBellClient(None),
        )

    def test_passwords_are_encrypted(self):
        settings = frappe.get_single("API Bell Settings")

        self.assertEqual(
            settings.get_password("password"),
            "test-account-password",
        )
        self.assertEqual(
            settings.get_password("client_secret"),
            "test-oauth-secret",
        )

    def test_fetch_discovers_embedded_mappings_without_results(self):
        with self.client():
            result = bell.fetch_fleet()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["unmapped"], 2)

        settings = frappe.get_single("API Bell Settings")
        self.assertEqual(len(settings.machine_mappings), 2)

        self.assertEqual(
            {row.equipment_id for row in settings.machine_mappings},
            {"IS 532", "IS 538"},
        )

        self.assertEqual(frappe.db.count("Bell Results"), 0)

    def test_sync_creates_then_updates_latest_results(self):
        with self.client():
            first = bell.sync_now()
            second = bell.sync_now()

        self.assertTrue(first["ok"], first)
        self.assertEqual(first["created"], 2)

        self.assertTrue(second["ok"], second)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 2)

        self.assertEqual(frappe.db.count("Bell Results"), 2)

        result = frappe.get_doc("Bell Results", "PIN-PIN-BELL-001")
        self.assertEqual(result.operating_hours, 29144.8)
        self.assertEqual(result.def_remaining, 0)
        self.assertEqual(result.mapping_status, "Unmapped")
        self.assertIn("<Fleet", result.raw_xml)

    def test_manual_asset_mapping_updates_existing_result(self):
        with self.client():
            result = bell.sync_now()

        self.assertTrue(result["ok"], result)

        asset = frappe.get_doc({
            "doctype": "Asset",
            "name": "TEST-BELL-ASSET-001",
            "asset_name": "Bell integration test asset",
        })
        asset.db_insert()

        settings = frappe.get_single("API Bell Settings")
        row = next(
            r for r in settings.machine_mappings
            if r.pin == "PIN-BELL-001"
        )

        row.asset = asset.name
        settings.save(ignore_permissions=True)

        result = frappe.get_doc("Bell Results", "PIN-PIN-BELL-001")

        self.assertEqual(result.asset, asset.name)
        self.assertEqual(result.mapping_status, "Mapped")

    def test_connection_works_before_enabling_without_import(self):
        settings = frappe.get_single("API Bell Settings")
        settings.enabled = 0
        settings.save(ignore_permissions=True)

        with self.client():
            result = bell.test_connection()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["count"], 2)
        self.assertEqual(frappe.db.count("Bell Results"), 0)

    def test_disabled_sync_is_rejected(self):
        settings = frappe.get_single("API Bell Settings")
        settings.enabled = 0
        settings.save(ignore_permissions=True)

        with patch.object(bell, "BellClient") as client:
            with self.assertRaises(frappe.ValidationError):
                bell.sync_now()

        client.assert_not_called()

    def test_failed_sync_preserves_last_success(self):
        with self.client():
            first = bell.sync_now()

        self.assertTrue(first["ok"])

        previous = frappe.db.get_single_value(
            "API Bell Settings",
            "last_successful_sync",
        )

        with patch.object(
            bell,
            "BellClient",
            side_effect=BellError("Bell authentication failed."),
        ):
            failed = bell.sync_now()

        self.assertFalse(failed["ok"])
        self.assertEqual(
            frappe.db.get_single_value(
                "API Bell Settings",
                "last_successful_sync",
            ),
            previous,
        )


if __name__ == "__main__":
    unittest.main()
