"""Offline API contract tests: HTTP responses are mocked; no credentials or live API."""
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import requests


STAMP = "2026-11-19T06:00:00Z"


def equipment(serial="LY02510013", **overrides):
    row = {
        "EquipmentHeader": {"OEMName": "KOBELCO", "Model": "SK850LC",
                            "SerialNumber": serial, "PIN": "PIN-" + serial},
        "Location": {"Latitude": -25.1, "Longitude": 29.2, "datetime": STAMP},
        "CumulativeOperatingHours": {"Hour": 100.5, "datetime": STAMP},
        "CumulativeIdleHours": {"Hour": 12.5, "datetime": STAMP},
        "FuelUsed": {"FuelConsumed": 400, "FuelUnits": "litre", "datetime": STAMP},
        "FuelRemaining": {"Percent": 0, "datetime": STAMP},
        "EngineStatus": {"Running": False, "datetime": STAMP},
        "DEFRemaining": {"Percent": 45, "datetime": STAMP},
    }
    row.update(overrides)
    return row


class TestKobelcoClient(unittest.TestCase):
    def setUp(self):
        from engineering.controllers import kobelco_client as kobelco
        self.api = kobelco
        self.settings = SimpleNamespace(base_url="https://example.test/api/aemp", username="operator",
                                        get_password=Mock(return_value="secret"))

    @patch("requests.get")
    def test_basic_auth_and_relative_next_preserve_base_path(self, get):
        get.side_effect = [Mock(status_code=200, json=lambda: {
            "Equipment": [equipment()], "Links": [{"rel": "next", "href": "/Fleet/2"}]}),
            Mock(status_code=200, json=lambda: {"Equipment": [equipment("LY02510058")]})]
        rows = self.api.KobelcoClient(self.settings).fetch_fleet()
        self.assertEqual([r["EquipmentHeader"]["SerialNumber"] for r in rows],
                         ["LY02510013", "LY02510058"])
        self.assertEqual([c.args[0] for c in get.call_args_list],
                         ["https://example.test/api/aemp/Fleet/1", "https://example.test/api/aemp/Fleet/2"])
        auth = get.call_args.kwargs["auth"]
        self.assertEqual((auth.username, auth.password), ("operator", "secret"))
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertEqual(get.call_args.kwargs["headers"]["Accept"], "application/json")

    def test_link_resolution_handles_prefixed_paths_and_page_queries(self):
        client = self.api.KobelcoClient(self.settings)
        for link in ("/api/aemp/Fleet/2", "Fleet/2", "/Fleet/2"):
            self.assertEqual(client.resolve_url(link), "https://example.test/api/aemp/Fleet/2")
        self.assertEqual(client.resolve_url("?page=2", "https://example.test/api/aemp/Fleet/1"),
                         "https://example.test/api/aemp/Fleet/1?page=2")

    def test_page_relative_links_resolve_against_current_fleet_page(self):
        client = self.api.KobelcoClient(self.settings)
        for href in ("2", "./2"):
            self.assertEqual(client.resolve_url(href, "https://example.test/api/aemp/Fleet/1"),
                             "https://example.test/api/aemp/Fleet/2")

    def test_encoded_backslash_cannot_escape_base_path(self):
        client = self.api.KobelcoClient(self.settings)
        with self.assertRaises(self.api.KobelcoError):
            client.resolve_url("%2e%2e%5cprivate")

    def test_foreign_or_traversal_links_rejected_before_auth_sent(self):
        client = self.api.KobelcoClient(self.settings)
        for url in ("https://evil.test/Fleet/2", "//evil.test/Fleet/2", "../private", "/%2e%2e/private",
                    "https://example.test/outside/Fleet/2", "https://user:pass@example.test/api/aemp/Fleet/2"):
            with self.subTest(url=url), self.assertRaises(self.api.KobelcoError):
                client.resolve_url(url)

    @patch("requests.get")
    def test_auth_transport_redirect_and_json_errors_are_sanitized(self, get):
        errors = [(Mock(status_code=401), "Authentication"), (Mock(status_code=302), "redirect"),
                  (Mock(status_code=503), "503"),
                  (Mock(status_code=200, json=Mock(side_effect=ValueError("secret body"))), "JSON")]
        for response, message in errors:
            get.return_value = response
            with self.subTest(message=message), self.assertRaisesRegex(self.api.KobelcoError, message):
                self.api.KobelcoClient(self.settings).fetch_fleet()
        get.side_effect = requests.Timeout("secret URL")
        with self.assertRaises(self.api.KobelcoError) as raised:
            self.api.KobelcoClient(self.settings).fetch_fleet()
        self.assertNotIn("secret", str(raised.exception))

    @patch("requests.get")
    def test_invalid_payloads_and_pagination_loop_fail(self, get):
        for payload in ({"unexpected": []}, {"Equipment": "invalid"}, {"Equipment": [None]}, []):
            get.return_value = Mock(status_code=200, json=lambda: payload)
            with self.subTest(payload=payload), self.assertRaises(self.api.KobelcoError):
                self.api.KobelcoClient(self.settings).fetch_fleet()
        get.return_value = Mock(status_code=200, json=lambda: {
            "Equipment": [], "Links": [{"rel": "next", "href": "/Fleet/1"}]})
        with self.assertRaisesRegex(self.api.KobelcoError, "loop"):
            self.api.KobelcoClient(self.settings).fetch_fleet()

    def test_normalization_preserves_zero_false_and_independent_timestamps(self):
        row = self.api.normalize_equipment(equipment())
        self.assertEqual(row["serial_number"], "LY02510013")
        self.assertEqual(row["operating_hours"], 100.5)
        self.assertEqual(row["idle_hours"], 12.5)
        self.assertEqual(row["fuel_consumption"], 400)
        self.assertEqual(row["fuel_units"], "litre")
        self.assertEqual(row["fuel_remaining"], 0)
        self.assertEqual(row["engine_status"], "Stopped")
        self.assertEqual(row["def_remaining"], 45)
        self.assertEqual((row["latitude"], row["longitude"]), (-25.1, 29.2))
        self.assertEqual(str(row["location_timestamp"]), "2026-11-19 06:00:00")
        self.assertEqual(str(row["snapshot_timestamp"]), "2026-11-19 06:00:00")
        sparse = self.api.normalize_equipment(equipment(FuelUsed=None, DEFRemaining=None, EngineStatus=None))
        self.assertIsNone(sparse["fuel_consumption"])
        self.assertIsNone(sparse["engine_status"])

    def test_missing_identity_never_falls_back_to_model(self):
        for header in ({"Model": "SK850LC"}, {"SerialNumber": " ", "PIN": "PIN-only"}):
            with self.assertRaises(self.api.KobelcoError):
                self.api.normalize_equipment({"EquipmentHeader": header})

    def test_invalid_numbers_and_timestamps_fail_instead_of_silent_zero(self):
        for overrides in ({"FuelRemaining": {"Percent": "NaN"}},
                          {"Location": {"Latitude": 100, "Longitude": 0}},
                          {"CumulativeOperatingHours": {"Hour": "broken"}},
                          {"DEFRemaining": {"Percent": 101}},
                          {"FuelUsed": {"FuelConsumed": 4, "datetime": "broken"}}):
            with self.subTest(overrides=overrides), self.assertRaises(self.api.KobelcoError):
                self.api.normalize_equipment(equipment(**overrides))


class TestKobelcoActualResponse(unittest.TestCase):
    def setUp(self):
        from engineering.controllers import kobelco_client
        self.api = kobelco_client
        self.text = (Path(__file__).parent / "fixtures" / "kobelco_fleet.json").read_text()
        self.fleet = json.loads(self.text)["Fleet"]

    def test_all_actual_measurements_identifiers_and_attribute_timestamps(self):
        row = self.api.normalize_equipment(self.fleet["Equipment"][0], self.fleet["@snapshotTime"])
        expected = {"operating_hours": 9157, "idle_hours": 2718.2, "fuel_consumption": 367176,
                    "fuel_used_last24": 165, "fuel_used_last24_units": "litre", "pto_hours": 9157,
                    "load_count": 292, "fuel_tank_capacity": 960, "fuel_tank_capacity_units": "litre",
                    "altitude": 1627, "altitude_units": "metre", "engine_number": "00638737",
                    "def_remaining": 0, "latitude": -25.98006, "longitude": 29.50418}
        for key, value in expected.items():
            self.assertEqual(row[key], value, key)
        for field in ("operating_hours", "idle_hours", "fuel_consumption", "fuel_used_last24", "pto_hours", "load_count", "fuel_tank_capacity", "fuel_remaining", "def_remaining"):
            self.assertEqual(str(row[field + "_timestamp"]), "2026-11-18 22:00:00", field)
        self.assertEqual(str(row["unit_install_timestamp"]), "2023-08-31 00:00:00")
        self.assertEqual(str(row["location_timestamp"]), "2026-11-17 22:00:00")
        self.assertEqual(str(row["engine_status_timestamp"]), "2026-11-19 21:45:00")
        self.assertEqual(str(row["snapshot_timestamp"]), "2026-11-19 12:06:25")
        self.assertIn("engine_status_timestamp", row["source_time_warning"])

    @patch("requests.get")
    def test_complete_original_response_and_equipment_are_preserved(self, get):
        settings = SimpleNamespace(base_url="https://example.test/api/aemp", username="operator", get_password=Mock(return_value="secret"))
        get.return_value = Mock(status_code=200, text=self.text, json=lambda: json.loads(self.text))
        rows = self.api.KobelcoClient(settings).fetch_fleet()
        self.assertEqual(rows, self.fleet["Equipment"])
        self.assertEqual(rows.raw_response_for(0), self.text)
        self.assertEqual(rows.raw_response_for(1), self.text)
        self.assertEqual(rows.snapshot_time_for(0), "2026-11-19T12:06:25Z")
        self.assertEqual(len(rows.pages), 1)
        self.assertEqual(get.call_count, 1)  # advertised last is page 1; no invented page 2

    def test_machine_only_history_keeps_fleet_time_unknown_and_source_future_time_exact(self):
        original = json.loads(self.text)["Fleet"]["Equipment"]
        for raw in original:
            before = json.dumps(raw, sort_keys=True)
            row = self.api.normalize_equipment(raw)
            self.assertIsNone(row["fleet_snapshot_timestamp"])
            self.assertEqual(str(row["engine_status_timestamp"]), "2026-11-19 21:45:00")
            self.assertEqual(row["snapshot_timestamp"], row["engine_status_timestamp"])
            self.assertEqual(row["snapshot_time_basis"], "Latest source measurement")
            self.assertEqual(json.dumps(raw, sort_keys=True), before)

    def test_pto_is_independent_of_operating_hours_and_its_timestamp(self):
        raw = json.loads(self.text)["Fleet"]["Equipment"][0]
        raw["CumulativePowerTakeOffHours"] = {"Hour": "123.25", "@datetime": "2026-11-17T20:00:00Z"}
        row = self.api.normalize_equipment(raw, self.fleet["@snapshotTime"])
        self.assertEqual(row["operating_hours"], 9157)
        self.assertEqual(row["pto_hours"], 123.25)
        self.assertEqual(str(row["operating_hours_timestamp"]), "2026-11-18 22:00:00")
        self.assertEqual(str(row["pto_hours_timestamp"]), "2026-11-17 20:00:00")
        raw.pop("CumulativePowerTakeOffHours")
        missing = self.api.normalize_equipment(raw)
        self.assertIsNone(missing["pto_hours"])
        self.assertIsNone(missing["pto_hours_timestamp"])
        self.assertEqual(missing["operating_hours"], 9157)

    @patch("requests.get")
    def test_fleet_metadata_is_taken_only_from_each_equipment_originating_page(self, get):
        settings = SimpleNamespace(base_url="https://example.test/api/aemp", username="operator", get_password=Mock(return_value="secret"))
        first = json.loads(self.text)
        first["Fleet"]["Equipment"] = first["Fleet"]["Equipment"][:1]
        first["Fleet"]["Links"] = [{"rel": "next", "href": "/Fleet/2"}]
        second = {"Fleet": {"Equipment": [self.fleet["Equipment"][1]]}}
        bodies = [json.dumps(first), json.dumps(second)]
        get.side_effect = [Mock(status_code=200, text=body, json=lambda body=body: json.loads(body)) for body in bodies]
        rows = self.api.KobelcoClient(settings).fetch_fleet()
        self.assertEqual(rows.version_for(0), "1")
        self.assertEqual(rows.snapshot_time_for(0), "2026-11-19T12:06:25Z")
        self.assertIsNone(rows.version_for(1))
        self.assertIsNone(rows.snapshot_time_for(1))
        for index in range(2):
            self.assertEqual(rows.raw_response_for(index), bodies[index])
        row = self.api.normalize_equipment(rows[0], rows.snapshot_time_for(0))
        self.assertEqual(str(row["snapshot_timestamp"]), "2026-11-19 12:06:25")
        self.assertEqual(str(row["engine_status_timestamp"]), "2026-11-19 21:45:00")
        self.assertEqual(row["snapshot_time_basis"], "Fleet snapshot")
        self.assertIn("engine_status_timestamp", row["source_time_warning"])

    def test_installation_time_is_not_a_measurement_snapshot(self):
        row = self.api.normalize_equipment({"EquipmentHeader": {
            "SerialNumber": "TEST-INSTALL", "UnitInstallDateTime": "2023-08-31T00:00:00Z"}})
        self.assertEqual(str(row["unit_install_timestamp"]), "2023-08-31 00:00:00")
        self.assertIsNone(row["snapshot_timestamp"])
        self.assertIsNone(row["snapshot_time_basis"])

    def test_missing_extended_values_stay_none_and_offsets_normalize_to_utc(self):
        row = self.api.normalize_equipment(equipment(Location={"Latitude": 0, "Longitude": 0,
            "@datetime": "2026-11-19T08:00:00+02:00"}, FuelUsedLast24={"FuelConsumed": 0}))
        self.assertEqual(row["fuel_used_last24"], 0)
        for field in ("altitude", "pto_hours", "load_count", "fuel_tank_capacity"):
            self.assertIsNone(row[field])
        self.assertEqual(str(row["location_timestamp"]), "2026-11-19 06:00:00")


class TestKobelcoTransactionFailures(unittest.TestCase):
    def test_deadlock_uses_full_rollback_and_returns_sanitized_failure(self):
        import frappe
        from engineering.controllers import kobelco
        frappe.local.debug_log = []
        with patch.object(frappe, "db", Mock()) as db, patch.object(frappe, "cache", MagicMock()), \
                patch.object(kobelco, "KobelcoClient") as client, \
                patch.object(kobelco, "_settings", return_value=Mock()), \
                patch.object(kobelco, "_discover", side_effect=frappe.QueryDeadlockError("sensitive details")), \
                patch.object(kobelco, "_status") as status:
            client.return_value.fetch_fleet.return_value = [equipment()]
            frappe.local.db = db
            result = kobelco._run(Mock(), store_results=True)
            self.assertFalse(result["ok"])
            self.assertNotIn("sensitive", result["message"])
            db.rollback.assert_any_call()
            self.assertNotIn("kobelco_sync", [call.kwargs.get("save_point") for call in db.rollback.call_args_list])
            self.assertEqual(result["diagnostic"]["exception_class"], "QueryDeadlockError")
            status.assert_called_once_with(False, result["message"])


class TestKobelcoSnapshotNaming(unittest.TestCase):
    def setUp(self):
        from engineering.controllers import kobelco
        self.api = kobelco

    def test_mapped_asset_uses_fleet_number_and_utc_timestamp(self):
        from datetime import datetime
        import hashlib

        raw_json = '{"serial":"LY02510013","hours":100}'
        machine = {"snapshot_timestamp": datetime(2026, 11, 23, 5, 34, 55)}
        mapping = SimpleNamespace(asset="IS0330")

        digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()[:8].upper()

        self.assertEqual(
            self.api._snapshot_record_name(machine, mapping, raw_json,
                                           datetime(2026, 11, 23, 6, 0)),
            f"KOB-IS0330-20261123T053455Z-{digest}",
        )

    def test_second_machine_uses_its_own_fleet_number(self):
        from datetime import datetime

        name = self.api._snapshot_record_name(
            {"snapshot_timestamp": datetime(2026, 11, 23, 5, 34, 55)},
            SimpleNamespace(asset="EX01"),
            '{"serial":"LY02510058"}',
            datetime(2026, 11, 23, 6, 0),
        )

        self.assertTrue(name.startswith("KOB-EX01-20261123T053455Z-"))

    def test_unmapped_machine_uses_unmapped_prefix(self):
        from datetime import datetime

        name = self.api._snapshot_record_name(
            {"snapshot_timestamp": datetime(2026, 11, 23, 5, 34, 55)},
            SimpleNamespace(asset=None),
            '{"serial":"LY02510013"}',
            datetime(2026, 11, 23, 6, 0),
        )

        self.assertTrue(name.startswith("KOB-UNMAPPED-20261123T053455Z-"))

    def test_missing_source_timestamp_uses_fetch_time(self):
        from datetime import datetime

        fetched = datetime(2026, 11, 23, 5, 40, 17)

        name = self.api._snapshot_record_name(
            {"snapshot_timestamp": None},
            SimpleNamespace(asset="IS0330"),
            '{"serial":"LY02510013"}',
            fetched,
        )

        self.assertTrue(name.startswith("KOB-IS0330-20261123T054017Z-"))

    def test_timezone_aware_timestamp_is_converted_to_utc(self):
        from datetime import datetime, timezone, timedelta

        timestamp = datetime(
            2026, 11, 23, 7, 34, 55,
            tzinfo=timezone(timedelta(hours=2)),
        )

        name = self.api._snapshot_record_name(
            {"snapshot_timestamp": timestamp},
            SimpleNamespace(asset="IS0330"),
            '{"serial":"LY02510013"}',
            datetime(2026, 11, 23, 8, 0),
        )

        self.assertIn("20261123T053455Z", name)

    def test_same_payload_is_deterministic_and_changed_payload_differs(self):
        from datetime import datetime

        machine = {"snapshot_timestamp": datetime(2026, 11, 23, 5, 34, 55)}
        mapping = SimpleNamespace(asset="IS0330")
        fetched = datetime(2026, 11, 23, 6, 0)

        first = self.api._snapshot_record_name(
            machine, mapping, '{"hours":100}', fetched
        )
        repeated = self.api._snapshot_record_name(
            machine, mapping, '{"hours":100}', fetched
        )
        changed = self.api._snapshot_record_name(
            machine, mapping, '{"hours":101}', fetched
        )

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, changed)

    def test_legacy_snapshot_identity_remains_deduplicated(self):
        import hashlib

        raw = {"serial": "LY02510013", "hours": 100}
        machine = {"serial_number": "LY02510013", "snapshot_timestamp": None}
        mapping = SimpleNamespace(asset="IS0330", name="mapping", mapping_status="Mapped")
        raw_json = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        legacy_key = hashlib.sha256((machine["serial_number"] + "\n" + raw_json).encode()).hexdigest()

        with patch.object(self.api.frappe, "db", Mock()) as db:
            db.exists.return_value = True
            with patch.object(self.api.frappe, "new_doc") as new_doc:
                result = self.api._store_snapshot(raw, machine, mapping)

        self.assertFalse(result)
        db.exists.assert_called_once_with(self.api.RESULTS, legacy_key)
        new_doc.assert_not_called()

    def test_new_record_with_missing_timestamp_is_still_deduplicated(self):
        raw = {"serial": "LY02510013", "hours": 100}
        machine = {"serial_number": "LY02510013", "snapshot_timestamp": None}
        mapping = SimpleNamespace(asset="IS0330", name="mapping", mapping_status="Mapped")
        raw_json = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

        with patch.object(self.api.frappe, "db", Mock()) as db:
            db.exists.side_effect = [False, True]
            with patch.object(self.api.frappe, "new_doc") as new_doc:
                result = self.api._store_snapshot(raw, machine, mapping)

        self.assertFalse(result)
        self.assertEqual(db.exists.call_count, 2)
        self.assertEqual(
            db.exists.call_args_list[1].args,
            (self.api.RESULTS, {
                "serial_number": machine["serial_number"],
                "raw_json": raw_json,
            }),
        )
        new_doc.assert_not_called()

    def test_new_fleet_timestamp_is_not_suppressed_by_identical_machine_json(self):
        from datetime import datetime

        raw = {"serial": "LY02510013", "hours": 100}
        machine = {
            "serial_number": "LY02510013",
            "snapshot_timestamp": datetime(2026, 11, 23, 5, 34, 55),
        }
        mapping = SimpleNamespace(
            asset="IS0330", name="mapping", mapping_status="Mapped"
        )
        doc = Mock()

        with patch.object(self.api.frappe, "db", Mock()) as db:
            db.exists.side_effect = [False, False]
            with patch.object(self.api.frappe, "new_doc", return_value=doc) as new_doc:
                result = self.api._store_snapshot(raw, machine, mapping)

        self.assertTrue(result)
        self.assertEqual(db.exists.call_count, 2)
        self.assertTrue(db.exists.call_args_list[1].args[1].startswith(
            "KOB-IS0330-20261123T053455Z-"
        ))
        new_doc.assert_called_once_with(self.api.RESULTS)
        doc.insert.assert_called_once_with(ignore_permissions=True)

    def test_invalid_timestamp_fails_safely(self):
        with self.assertRaises(self.api.KobelcoError):
            self.api._snapshot_record_name(
                {"snapshot_timestamp": "not-a-date"},
                SimpleNamespace(asset="IS0330"),
                '{"serial":"LY02510013"}',
                None,
            )


class TestKobelcoMappingMigration(unittest.TestCase):
    def test_existing_mapping_records_stop_migration_before_any_changes(self):
        import frappe
        from engineering.patches import embed_kobelco_machine_mapping as migration
        with patch.object(frappe, "db", Mock()) as db, \
                patch.object(frappe, "reload_doc") as reload_doc, \
                patch.object(frappe, "delete_doc") as delete_doc:
            db.table_exists.return_value = True
            db.count.return_value = 1
            with self.assertRaisesRegex(frappe.ValidationError, "existing data"):
                migration.execute()
            reload_doc.assert_not_called()
            delete_doc.assert_not_called()
            db.sql_ddl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
