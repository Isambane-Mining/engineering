"""Offline MPI regressions. Run explicitly on LAB; no real credentials or API calls."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import requests
import json

from engineering.controllers.mpi import MPIClient, MPIError, _discover, _upsert, activity_values, match_vehicle


class TestMPIMatching(TestCase):
    def setUp(self):
        self.assets = [
            {"name": "AST-001", "asset_name": "AU 24"},
            {"name": "AST-002", "asset_name": "AU-25"},
            {"name": "AST-003", "asset_name": "AU25"},
        ]

    def test_unique_raw_match_links_asset(self):
        self.assertEqual(match_vehicle("AU 24", "", self.assets)["asset"], "AST-001")
        self.assertEqual(match_vehicle("AST-001", "", self.assets)["asset"], "AST-001")

    def test_normalized_match_is_only_a_suggestion(self):
        result = match_vehicle("au-24", "", self.assets)
        self.assertIsNone(result["asset"])
        self.assertEqual(result["mapping_status"], "Suggested")
        self.assertEqual(result["suggested_assets"], "AST-001")

    def test_ambiguous_normalized_matches_remain_unlinked(self):
        result = match_vehicle("AU 25", "", self.assets)
        self.assertEqual(result["mapping_status"], "Ambiguous")
        self.assertIsNone(result["asset"])
        self.assertEqual(result["suggested_assets"], "AST-002\nAST-003")

    def test_conflicting_raw_plate_and_name_are_ambiguous(self):
        result = match_vehicle("AU 24", "AU-25", self.assets)
        self.assertEqual(result["mapping_status"], "Ambiguous")
        self.assertIsNone(result["asset"])

    def test_duplicate_raw_names_and_blank_identifiers_do_not_link(self):
        self.assets.append({"name": "AST-004", "asset_name": "AU 24"})
        self.assertEqual(match_vehicle("AU 24", "", self.assets)["mapping_status"], "Ambiguous")
        self.assertEqual(match_vehicle("", "", self.assets)["mapping_status"], "Unmatched")

    def test_item_code_is_never_a_matching_identifier(self):
        result = match_vehicle("AU26", "", [{"name": "AST-005", "asset_name": "Other", "item_code": "AU26"}])
        self.assertEqual(result["mapping_status"], "Unmatched")


class TestMPIActivity(TestCase):
    def test_allowlist_preserves_zeroes_and_durations(self):
        row = {"imei": "123456789012345", "driver_name": "discard", "vin": "discard",
               "status": {"active": 0, "lat": "0", "lon": "28.5", "speed": 0,
                          "direction": 0, "moving": 345, "parking": 0, "zone": "Depot"},
               "sensors_status": [{"value": "discard"}]}
        values = activity_values(row)
        self.assertEqual(values["active"], 0)
        self.assertEqual(values["latitude"], 0)
        self.assertEqual(values["moving"], 345)
        self.assertEqual(values["parking_duration"], 0)
        self.assertEqual(values["zone"], "Depot")
        self.assertEqual(set(values), {"active", "latitude", "longitude", "speed", "direction",
                                       "moving", "parking_duration", "zone", "position_timestamp"})

    def test_missing_data_is_null_and_invalid_coordinates_are_rejected(self):
        self.assertIsNone(activity_values({"status": {}})["speed"])
        with self.assertRaises(MPIError):
            activity_values({"status": {"lat": "nan"}})
        with self.assertRaises(MPIError):
            activity_values({"status": {"lon": 181}})


class TestMPIRequests(TestCase):
    def setUp(self):
        self.client = MPIClient("https://web.mpitracking.co.za", 3, "test-user", "test-secret")

    @patch("engineering.controllers.mpi.requests.sessions.Session.request")
    def test_verified_object_list_request_and_deduplication(self, request):
        request.return_value = Mock(status_code=200)
        request.return_value.json.return_value = [
            {"IMEI": "123456789012345", "PLATE": "AU24", "NAME": "Excavator", "VIN": "discard"},
            {"IMEI": "123456789012345", "PLATE": "AU24", "NAME": "Excavator"},
        ]
        rows = self.client.object_list()
        self.assertEqual(rows, [{"imei": "123456789012345", "plate": "AU24", "vehicle_name": "Excavator", "list_latitude": None, "list_longitude": None}])
        args, kwargs = request.call_args
        self.assertEqual(args, ("POST", "https://web.mpitracking.co.za/api/CRIT/api.php"))
        self.assertEqual(kwargs["params"], {"node": 3})
        self.assertIn(b"functionName=api_objectlist", kwargs["data"])
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (5, 20))

    @patch("engineering.controllers.mpi.requests.sessions.Session.request")
    def test_status_uses_basic_auth_and_selects_requested_imei(self, request):
        request.return_value = Mock(status_code=200)
        request.return_value.json.return_value = {"code": 0, "data": [
            {"imei": "123456789012345", "status": {"active": 1, "speed": 12}}]}
        self.assertEqual(self.client.status("123456789012345")["status"]["speed"], 12)
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Basic dGVzdC11c2VyOnRlc3Qtc2VjcmV0")
        self.assertEqual(kwargs["params"], {"cmd": "status", "imei": "123456789012345", "node": 3})

    @patch("engineering.controllers.mpi.requests.sessions.Session.request")
    def test_http_timeout_and_api_errors_are_safe(self, request):
        request.side_effect = requests.Timeout("test-secret must never be copied")
        with self.assertRaises(MPIError) as error:
            self.client.status("123456789012345")
        self.assertNotIn("test-secret", str(error.exception))
        request.side_effect = None
        for status, payload in [(401, {}), (302, {}), (200, {"code": 5, "msg": "test-secret"}),
                                (200, {"code": 0, "data": []})]:
            request.return_value = Mock(status_code=status)
            request.return_value.json.return_value = payload
            with self.assertRaises(MPIError) as error:
                self.client.status("123456789012345")
            self.assertNotIn("test-secret", str(error.exception))

    @patch("engineering.controllers.mpi.requests.sessions.Session.request")
    def test_conflicting_duplicate_imei_is_rejected(self, request):
        request.return_value = Mock(status_code=200)
        request.return_value.json.return_value = [
            {"IMEI": "123456789012345", "PLATE": "AU24"},
            {"IMEI": "123456789012345", "PLATE": "AU25"},
        ]
        with self.assertRaises(MPIError):
            self.client.object_list()

    @patch("engineering.controllers.mpi.requests.sessions.Session.request")
    def test_other_imei_and_invalid_json_are_rejected(self, request):
        request.return_value = Mock(status_code=200)
        request.return_value.json.return_value = {"code": 0, "data": [
            {"imei": "999999999999999", "status": {"speed": 10}}]}
        with self.assertRaises(MPIError):
            self.client.status("123456789012345")
        request.return_value.json.side_effect = ValueError("untrusted remote content")
        with self.assertRaises(MPIError) as error:
            self.client.status("123456789012345")
        self.assertNotIn("untrusted remote content", str(error.exception))


class TestMPIPersistence(TestCase):
    @staticmethod
    def complete_activity():
        return dict(active=1, latitude=-25, longitude=28, speed=4, direction=90,
                    moving=120, parking_duration=0, zone=None,
                    position_timestamp=datetime(2026, 11, 19, 12, 0))

    @patch("engineering.controllers.mpi.frappe")
    def test_discovery_preserves_manual_asset_selection(self, frappe):
        row = Mock(imei="123456789012345", asset="MANUALLY-SELECTED", plate="Old", vehicle_name="Old")
        row.is_new.return_value = False
        row.get.side_effect = lambda field: getattr(row, field)
        settings = Mock(vehicles=[row])
        settings.flags = SimpleNamespace()
        frappe.get_doc.return_value = settings
        frappe.get_all.return_value = [{"name": "DIFFERENT-EXACT-MATCH", "asset_name": "AU24"}]
        _discover([{"imei": row.imei, "plate": "AU24", "vehicle_name": "New Name"}])
        self.assertEqual(row.asset, "MANUALLY-SELECTED")
        self.assertEqual(row.plate, "AU24")
        self.assertEqual(row.vehicle_name, "New Name")
        settings.save.assert_not_called()
        self.assertFalse(frappe.db.set_value.call_args.kwargs["update_modified"])

    @patch("engineering.controllers.mpi.result_values")
    @patch("engineering.controllers.mpi.frappe")
    def test_repeated_upsert_updates_existing_imei_and_reloads_manual_mapping(self, frappe, parse):
        vehicle = {"imei": "123456789012345", "plate": "AU24", "vehicle_name": ""}
        mapping = SimpleNamespace(name="mapping-1", asset="REVIEWED-ASSET")
        result = Mock(position_timestamp=None)
        result.get.return_value = None
        frappe.db.sql.return_value = [(mapping.name,)]
        frappe.db.exists.return_value = True
        frappe.get_doc.side_effect = lambda doctype, name: mapping if doctype == "MPI Vehicle Mapping" else result
        parse.return_value = self.complete_activity()
        _upsert(vehicle, {})
        _upsert(vehicle, {})
        frappe.new_doc.assert_not_called()
        self.assertEqual(result.save.call_count, 2)
        self.assertEqual(result.update.call_args_list[0].args[0]["asset"], "REVIEWED-ASSET")

    @patch("engineering.controllers.mpi.result_values")
    @patch("engineering.controllers.mpi.frappe")
    def test_stale_position_does_not_replace_newer_activity(self, frappe, parse):
        vehicle = {"imei": "123456789012345", "plate": "AU24", "vehicle_name": ""}
        mapping = SimpleNamespace(name="mapping-1", asset="REVIEWED-ASSET")
        current = datetime(2026, 11, 19, 12, 0)
        result = Mock(position_timestamp=current)
        result.get.return_value = None
        frappe.db.sql.return_value = [(mapping.name,)]
        frappe.db.exists.return_value = True
        frappe.get_doc.side_effect = lambda doctype, name: mapping if doctype == "MPI Vehicle Mapping" else result
        parse.return_value = self.complete_activity() | {"position_timestamp": current - timedelta(minutes=1), "speed": 99}
        _upsert(vehicle, {})
        self.assertEqual(result.update.call_count, 1)
        self.assertNotIn("speed", result.update.call_args.args[0])

    @patch("engineering.controllers.mpi.result_values")
    @patch("engineering.controllers.mpi.frappe")
    def test_incomplete_status_cannot_create_false_zero_activity(self, frappe, parse):
        vehicle = {"imei": "123456789012345", "plate": "AU24", "vehicle_name": ""}
        mapping = SimpleNamespace(name="mapping-1", asset="REVIEWED-ASSET")
        frappe.db.sql.return_value = [(mapping.name,)]
        frappe.get_doc.return_value = mapping
        for missing in ("active", "latitude", "longitude", "speed", "direction", "moving",
                        "parking_duration", "position_timestamp"):
            parse.return_value = self.complete_activity() | {missing: None}
            with self.assertRaises(MPIError):
                _upsert(vehicle, {})
        frappe.new_doc.assert_not_called()
        frappe.db.exists.assert_not_called()
