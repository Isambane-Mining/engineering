"""LAB transaction tests. Run with tests/run_kobelco_tests.py or bench run-tests.

Only HTTP is mocked. Frappe passwords, mappings, uniqueness, results, permissions
and transaction rollback use the real database. All test changes are rolled back.
"""
import unittest
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import frappe
from engineering.controllers.test_kobelco import equipment as fixture_equipment


def equipment(serial="TEST-KOBELCO-13", **overrides):
    return fixture_equipment(serial, **overrides)


class TestKobelcoIntegration(unittest.TestCase):
    def setUp(self):
        from engineering.controllers import kobelco
        self.api = kobelco
        self.user = frappe.session.user
        frappe.set_user("Administrator")
        frappe.db.savepoint("kobelco_test")
        self.settings = frappe.get_single("API Kobelco Settings")
        self.settings.update({"enabled": 1, "base_url": "https://example.test/api/aemp",
                              "username": "test-operator", "password": "test-secret"})
        self.settings.save()
        mapped_assets = [r.asset for r in self.settings.machine_mappings if r.asset]
        self.assets = frappe.get_all("Asset", filters={"name": ["not in", mapped_assets]} if mapped_assets else {}, pluck="name", limit_page_length=2)
        if len(self.assets) < 2:
            self.skipTest("Two existing Assets are required for LAB mapping checks")
        self.http = patch("requests.get", return_value=Mock(status_code=200, json=lambda: {
            "Equipment": [equipment(), equipment("TEST-KOBELCO-58")]}))
        self.get = self.http.start()
        self.addCleanup(self.http.stop)

    def tearDown(self):
        frappe.db.rollback(save_point="kobelco_test")
        frappe.clear_document_cache("API Kobelco Settings", "API Kobelco Settings")
        frappe.set_user(self.user)

    def test_password_is_encrypted_and_connection_test_does_not_import(self):
        self.assertEqual(frappe.get_single("API Kobelco Settings").get_password("password"), "test-secret")
        stored = frappe.db.sql("select password from __Auth where doctype=%s and name=%s and fieldname=%s",
                               ("API Kobelco Settings", "API Kobelco Settings", "password"))
        self.assertTrue(stored)
        self.assertNotEqual(stored[0][0], "test-secret")
        self.assertTrue(self.api.test_connection()["ok"])
        self.assertEqual(frappe.db.count("Kobelco Machine Mapping", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 0)
        self.assertEqual(frappe.db.count("Kobelco Results", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 0)

    def test_fetch_discovers_distinct_serials_sharing_model_without_assets(self):
        before = frappe.db.count("Asset")
        self.assertEqual(self.api.fetch_fleet()["unmapped"], 2)
        self.api.fetch_fleet()
        self.assertEqual(frappe.db.count("Kobelco Machine Mapping", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 2)
        self.assertEqual(frappe.db.count("Kobelco Results", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 0)
        self.assertEqual(frappe.db.count("Asset"), before)
        rows = frappe.get_all("Kobelco Machine Mapping", filters={"serial_number": ["like", "TEST-KOBELCO-%"]}, fields=["serial_number", "asset", "mapping_status"])
        self.assertEqual({r.serial_number for r in rows}, {"TEST-KOBELCO-13", "TEST-KOBELCO-58"})
        self.assertTrue(all(not r.asset and r.mapping_status == "Unmapped" for r in rows))

    def test_sync_snapshot_deduplication_and_mapping_relink(self):
        result = self.api.sync_now()
        self.assertEqual((result["created"], result["unmapped"]), (2, 2))
        settings = frappe.get_single("API Kobelco Settings")
        mapping = next(row for row in settings.machine_mappings if row.serial_number == "TEST-KOBELCO-13")
        mapping.asset = self.assets[0]
        settings.save()
        linked = frappe.get_all("Kobelco Results", filters={"serial_number": "TEST-KOBELCO-13"}, fields=["asset", "mapping_status", "operating_hours", "fuel_remaining", "engine_status"])
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0].asset, self.assets[0])
        self.assertEqual(linked[0].mapping_status, "Mapped")
        self.assertEqual(linked[0].operating_hours, 100.5)
        self.assertEqual(linked[0].fuel_remaining, 0)
        self.assertEqual(linked[0].engine_status, "Stopped")
        result = self.api.sync_now()
        self.assertEqual((result["created"], result["skipped"], result["unmapped"]), (0, 2, 1))
        changed = equipment(CumulativeOperatingHours={"Hour": 101, "datetime": "2026-11-19T07:00:00Z"})
        self.get.return_value = Mock(status_code=200, json=lambda: {"Equipment": [changed]})
        self.assertEqual(self.api.sync_now()["created"], 1)
        self.assertEqual(frappe.db.count("Kobelco Results", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 3)
        settings = frappe.get_single("API Kobelco Settings")
        mapping = next(row for row in settings.machine_mappings if row.serial_number == "TEST-KOBELCO-13")
        mapping.asset = None
        settings.save()
        self.assertFalse(any(frappe.get_all("Kobelco Results", filters={"serial_number": "TEST-KOBELCO-13"}, pluck="asset")))
        settings = frappe.get_single("API Kobelco Settings")
        self.assertEqual(settings.last_sync_status, "Success")
        self.assertTrue(settings.last_sync_timestamp)

    def test_duplicate_serial_pin_and_asset_are_rejected(self):
        self.api.fetch_fleet()
        for values in (
            {"serial_number": " test-kobelco-13 "},
            {"serial_number": "DIFFERENT", "pin": "pin-test-kobelco-13"},
        ):
            settings = frappe.get_single("API Kobelco Settings")
            settings.append("machine_mappings", values)
            with self.assertRaises(frappe.ValidationError):
                settings.save()
        settings = frappe.get_single("API Kobelco Settings")
        for row in settings.machine_mappings:
            row.asset = self.assets[0]
        with self.assertRaises(frappe.ValidationError):
            settings.save()

    def test_fetch_preserves_asset_choices_and_updates_only_discovery_fields(self):
        self.api.fetch_fleet()
        settings = frappe.get_single("API Kobelco Settings")
        first = next(row for row in settings.machine_mappings if row.serial_number == "TEST-KOBELCO-13")
        first.asset = self.assets[0]
        settings.save()
        row_name = first.name
        self.get.return_value = Mock(status_code=200, json=lambda: {"Equipment": [equipment()]})
        self.assertTrue(self.api.fetch_fleet()["ok"])
        settings.reload()
        self.assertEqual(len([r for r in settings.machine_mappings if r.serial_number.startswith("TEST-KOBELCO-")]), 2)  # missing machines retained
        first = next(row for row in settings.machine_mappings if row.serial_number == "TEST-KOBELCO-13")
        self.assertEqual(first.name, row_name)
        self.assertEqual(first.asset, self.assets[0])
        self.assertEqual(first.mapping_status, "Mapped")
        self.assertEqual(first.parent, "API Kobelco Settings")
        self.assertEqual(first.parenttype, "API Kobelco Settings")
        self.assertEqual(first.parentfield, "machine_mappings")

    def test_asset_selection_saved_during_http_request_is_preserved(self):
        self.api.fetch_fleet()
        def http_response(*args, **kwargs):
            # Simulate a user saving a choice while the fleet response is pending.
            latest = frappe.get_single("API Kobelco Settings")
            next(r for r in latest.machine_mappings if r.serial_number == "TEST-KOBELCO-13").asset = self.assets[0]
            latest.save()
            return Mock(status_code=200, json=lambda: {"Equipment": [equipment(), equipment("TEST-KOBELCO-58")]})
        self.get.side_effect = http_response
        self.assertTrue(self.api.fetch_fleet()["ok"])
        settings = frappe.get_single("API Kobelco Settings")
        self.assertEqual(next(r for r in settings.machine_mappings if r.serial_number == "TEST-KOBELCO-13").asset, self.assets[0])
        self.assertEqual(next(r for r in settings.machine_mappings if r.serial_number == "TEST-KOBELCO-13").mapping_status, "Mapped")

    def test_conflicting_pin_rolls_back_batch_and_records_failure(self):
        self.api.fetch_fleet()
        conflicting = equipment("TEST-KOBELCO-58")
        conflicting["EquipmentHeader"]["PIN"] = "PIN-TEST-KOBELCO-13"
        self.get.return_value = Mock(status_code=200, json=lambda: {"Equipment": [equipment(), conflicting]})
        result = self.api.sync_now()
        self.assertFalse(result["ok"])
        self.assertEqual(frappe.db.count("Kobelco Results", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 0)
        self.assertEqual(frappe.get_single("API Kobelco Settings").last_sync_status, "Failed")

    def test_disabled_and_unauthorized_calls_do_not_contact_api(self):
        self.settings.enabled = 0
        self.settings.save()
        for method in (self.api.fetch_fleet, self.api.sync_now):
            with self.assertRaises(frappe.ValidationError):
                method()
        self.assertEqual(self.get.call_count, 0)
        frappe.set_user("Guest")
        for method in (self.api.test_connection, self.api.fetch_fleet, self.api.sync_now):
            with self.assertRaises(frappe.PermissionError):
                method()
        self.assertEqual(self.get.call_count, 0)

    def test_failed_http_does_not_expose_secrets_or_overwrite_success(self):
        self.api.sync_now()
        success = frappe.get_single("API Kobelco Settings").last_successful_sync
        self.get.return_value = Mock(status_code=401, text="test-secret")
        result = self.api.sync_now()
        self.assertFalse(result["ok"])
        self.assertNotIn("test-secret", str(result))
        settings = frappe.get_single("API Kobelco Settings")
        self.assertEqual(settings.last_sync_status, "Failed")
        self.assertEqual(settings.last_successful_sync, success)
        self.assertEqual(frappe.db.count("Kobelco Results", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 2)

    def test_invalid_second_machine_leaves_no_partial_records(self):
        invalid = equipment("TEST-KOBELCO-58", FuelUsed={"FuelConsumed": "bad"})
        self.get.return_value = Mock(status_code=200, json=lambda: {"Equipment": [equipment(), invalid]})
        self.assertFalse(self.api.sync_now()["ok"])
        self.assertEqual(frappe.db.count("Kobelco Machine Mapping", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 0)
        self.assertEqual(frappe.db.count("Kobelco Results", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 0)

    def test_missing_optional_measurements_do_not_appear_as_zero_readings(self):
        self.get.return_value = Mock(status_code=200, json=lambda: {
            "Equipment": [equipment(FuelUsed=None, FuelRemaining=None, DEFRemaining=None)]})
        self.assertTrue(self.api.sync_now()["ok"])
        name = frappe.get_all("Kobelco Results", filters={"serial_number": "TEST-KOBELCO-13"}, pluck="name")[0]
        result = frappe.get_doc("Kobelco Results", name)
        self.assertFalse(result.fuel_consumption_available)
        self.assertFalse(result.fuel_remaining_available)
        self.assertFalse(result.def_remaining_available)
        self.assertTrue(result.operating_hours_available)

    def test_absent_measurements_are_database_null_not_zero(self):
        self.get.return_value = Mock(status_code=200, json=lambda: {"Equipment": [equipment(
            FuelUsed=None, FuelRemaining=None, DEFRemaining={"Percent": 0},
            CumulativePowerTakeOffHours={"Hour": 0})]})
        self.assertTrue(self.api.sync_now()["ok"])
        row = frappe.get_all("Kobelco Results", filters={"serial_number": "TEST-KOBELCO-13"},
                             fields=["name", "fuel_consumption", "fuel_remaining", "altitude", "def_remaining", "pto_hours"])[0]
        self.assertIsNone(row.fuel_consumption)
        self.assertIsNone(row.fuel_remaining)
        self.assertIsNone(row.altitude)
        self.assertEqual(row.def_remaining, 0)
        self.assertEqual(row.pto_hours, 0)
        self.assertIsNone(frappe.get_doc("Kobelco Results", row.name).as_dict()["fuel_consumption"])

    def test_actual_response_is_fully_preserved_and_all_fields_imported_in_utc(self):
        from engineering.controllers import test_kobelco
        payload = json.loads((Path(test_kobelco.__file__).parent / "fixtures" / "kobelco_fleet.json").read_text())
        for index, item in enumerate(payload["Fleet"]["Equipment"]):
            item["EquipmentHeader"].update(SerialNumber=f"TEST-KOBELCO-{13 if index == 0 else 58}", PIN=f"TEST-RAW-PIN-{index}")
        body = json.dumps(payload, indent=2)
        self.get.return_value = Mock(status_code=200, text=body, json=lambda: json.loads(body))
        result = self.api.sync_now()
        self.assertTrue(result["ok"], result)
        row = frappe.get_all("Kobelco Results", filters={"serial_number": "TEST-KOBELCO-13"}, fields=["*"])[0]
        self.assertEqual(row.raw_response, body)
        self.assertEqual(json.loads(row.raw_json), payload["Fleet"]["Equipment"][0])
        self.assertEqual(row.engine_number, "00638737")
        self.assertEqual(row.fuel_used_last24, 165)
        self.assertEqual(row.fuel_tank_capacity, 960)
        self.assertEqual(row.altitude, 1627)
        self.assertEqual(str(row.fleet_snapshot_timestamp), "2026-11-19 12:06:25")
        self.assertEqual(str(row.operating_hours_timestamp), "2026-11-18 22:00:00")
        self.assertLess(abs((datetime.now(timezone.utc).replace(tzinfo=None) - row.fetched_at).total_seconds()), 60)
        self.assertEqual(row.telemetry_version, 2)
        self.assertIn("engine_status_timestamp", row.source_time_warning)

    def test_legacy_repair_previews_first_and_preserves_identity_raw_and_zero(self):
        from engineering.controllers.kobelco_audit import repair_legacy_results
        self.api.sync_now()
        row = frappe.get_all("Kobelco Results", filters={"serial_number": "TEST-KOBELCO-13"}, fields=["*"])[0]
        frappe.db.set_value("Kobelco Results", row.name, {"telemetry_version": 0, "fetched_at": "2026-11-19 17:30:00", "operating_hours_timestamp": None}, update_modified=False)
        preview = repair_legacy_results(legacy_timezone="Asia/Kolkata", names=[row.name])
        self.assertFalse(preview["applied"])
        self.assertEqual(str(frappe.db.get_value("Kobelco Results", row.name, "fetched_at")), "2026-11-19 17:30:00")
        self.assertEqual(str(preview["results"][0]["changes"]["fetched_at"]["after"]), "2026-11-19 12:00:00")
        repaired = repair_legacy_results(apply=True, legacy_timezone="Asia/Kolkata", names=[row.name])
        self.assertEqual(repaired["count"], 1)
        after = frappe.get_doc("Kobelco Results", row.name)
        self.assertEqual(after.name, row.name)
        self.assertEqual(after.raw_json, row.raw_json)
        self.assertEqual(after.snapshot_key, row.snapshot_key)
        self.assertEqual(after.modified, row.modified)
        self.assertEqual(after.fuel_remaining, 0)
        self.assertIsNone(after.altitude)
        self.assertEqual(str(after.operating_hours_timestamp), "2026-11-19 06:00:00")
        self.assertEqual(repair_legacy_results(apply=True, legacy_timezone="Asia/Kolkata", names=[row.name])["count"], 0)

    def test_connection_can_be_tested_before_enabling(self):
        self.settings.enabled = 0
        self.settings.save()
        self.assertTrue(self.api.test_connection()["ok"])
        self.assertEqual(frappe.db.count("Kobelco Results", {"serial_number": ["like", "TEST-KOBELCO-%"]}), 0)

    def test_database_unique_indexes_prevent_duplicates_without_validation(self):
        self.api.fetch_fleet()
        rows = {r.serial_number: r for r in frappe.get_single("API Kobelco Settings").machine_mappings}
        first, second = rows["TEST-KOBELCO-13"], rows["TEST-KOBELCO-58"]
        for field, value in (("serial_number", first.serial_number), ("pin", first.pin)):
            with self.subTest(field=field), self.assertRaises(Exception) as raised:
                frappe.db.set_value("Kobelco Machine Mapping", second.name, field, value)
            self.assertTrue(frappe.db.is_unique_key_violation(raised.exception))
        frappe.db.set_value("Kobelco Machine Mapping", first.name, "asset", self.assets[0])
        with self.assertRaises(Exception) as raised:
            frappe.db.set_value("Kobelco Machine Mapping", second.name, "asset", self.assets[0])
        self.assertTrue(frappe.db.is_unique_key_violation(raised.exception))

    def test_results_cannot_be_edited_manually(self):
        self.api.sync_now()
        result = frappe.get_doc("Kobelco Results", frappe.get_all("Kobelco Results", filters={"serial_number": ["like", "TEST-KOBELCO-%"]}, pluck="name")[0])
        result.operating_hours = 999
        with self.assertRaises(frappe.ValidationError):
            result.save()

    def test_identifiers_cannot_be_changed_after_discovery(self):
        self.api.fetch_fleet()
        settings = frappe.get_single("API Kobelco Settings")
        next(r for r in settings.machine_mappings if r.serial_number == "TEST-KOBELCO-13").serial_number = "CHANGED"
        with self.assertRaises(frappe.ValidationError):
            settings.save()

    def test_removed_rows_cannot_silently_destroy_mapping_data(self):
        self.api.fetch_fleet()
        settings = frappe.get_single("API Kobelco Settings")
        settings.set("machine_mappings", [])
        with self.assertRaises(frappe.ValidationError):
            settings.save()

    def test_engineering_roles_can_read_results_and_child_inherits_settings_permissions(self):
        from frappe.permissions import get_role_permissions
        for role in ("Engineering User", "Engineering Manager", "Engineering Area Manager"):
            with patch("frappe.get_roles", return_value=[role]):
                results = get_role_permissions(frappe.get_meta("Kobelco Results"), user="test-" + role)
            self.assertTrue(results.get("read"))
            self.assertFalse(results.get("write"))
            self.assertFalse(results.get("create"))
        child = frappe.get_meta("Kobelco Machine Mapping")
        self.assertTrue(child.istable)
        self.assertFalse(child.permissions)
        with patch("frappe.get_roles", return_value=["Engineering User"]):
            settings = get_role_permissions(frappe.get_meta("API Kobelco Settings"), user="test-Engineering User")
        self.assertFalse(settings.get("write"))

    def test_settings_has_two_native_tabs_one_grid_and_no_username_default(self):
        meta = frappe.get_meta("API Kobelco Settings")
        self.assertEqual([f.label for f in meta.fields if f.fieldtype == "Tab Break"],
                         ["API Configuration", "Machine Mapping"])
        self.assertEqual([(f.fieldname, f.options) for f in meta.fields if f.fieldtype == "Table"],
                         [("machine_mappings", "Kobelco Machine Mapping")])
        self.assertFalse(meta.get_field("username").default)
        self.assertEqual(meta.get_field("password").fieldtype, "Password")
