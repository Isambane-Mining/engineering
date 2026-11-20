"""Offline Phase 2 fixtures. All HTTP and database boundaries are mocked."""
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
import requests

from engineering.controllers import mpi


def vehicle():
    return {"imei": "123456789012345", "plate": "AU24", "vehicle_name": "Excavator",
            "list_latitude": -24.1, "list_longitude": 28.2}


def record():
    return {"agentid": 42, "configuration": "Tracker", "created_time": 1600000000,
            "current_mileage": 1234.5, "driver_name": "Fictional Driver", "driver_phone": "0000000000",
            "folder": "Test", "imei": "123456789012345", "info": "Fixture", "initial_mileage": 100,
            "model": "Test Model", "sensors_status": [{"id": "5", "name": "Test sensor", "raw_value": "4",
                "hum_value": "4 L", "dig_value": 4, "group": "Fuel", "change_ts": 1700000000}],
            "status": {"active": 1, "alt": 100.5, "direction": 90, "firing": 0, "lat": -25.3,
                "lon": 29.4, "moving": 120, "parking": 60, "satsinview": 8, "speed": 5.5,
                "unixtimestamp": 1700000000, "zone": "Test Depot"},
            "type": "Car", "typeid": 27, "uniqid": "device-42", "vehiclenumber": "Test Plate", "vin": "FICTIONAL-VIN"}


class TestPhase2Mapping(TestCase):
    @patch.object(mpi, "convert_utc_to_system_timezone", side_effect=lambda dt: dt)
    def test_every_record_and_nested_field_is_mapped(self, timezone):
        values = mpi.result_values(record())
        expected = {"agentid": "42", "configuration": "Tracker", "created_time": 1600000000,
            "current_mileage": 1234.5, "driver_name": "Fictional Driver", "driver_phone": "0000000000",
            "folder": "Test", "info": "Fixture", "initial_mileage": 100, "model": "Test Model",
            "type": "Car", "typeid": "27", "uniqid": "device-42", "vehiclenumber": "Test Plate",
            "vin": "FICTIONAL-VIN", "active": 1, "alt": 100.5, "direction": 90, "firing": 0,
            "latitude": -25.3, "longitude": 29.4, "moving": 120, "parking_duration": 60,
            "satsinview": 8, "speed": 5.5, "unixtimestamp": 1700000000,
            "position_timestamp": datetime(2023, 11, 14, 22, 13, 20)}
        for name, value in expected.items():
            with self.subTest(field=name): self.assertEqual(values[name], value)
        self.assertEqual(json.loads(values["sensors_status"]), record()["sensors_status"])
        self.assertEqual(values["zone"], "Test Depot")
        self.assertEqual(json.loads(values["zone_data"]), "Test Depot")
        self.assertNotIn("status", values)
        self.assertNotIn("imei", values)  # Upsert identity is the requested/matched IMEI, not API reassignment.
        schema = json.loads((Path(mpi.__file__).parents[1] / "engineering/doctype/mpi_results/mpi_results.json").read_text())
        self.assertTrue(set(values) <= {f["fieldname"] for f in schema["fields"]})

    @patch.object(mpi, "convert_utc_to_system_timezone", side_effect=lambda dt: dt)
    def test_json_nested_values_and_missing_optional_metadata(self, timezone):
        row = record(); row["status"]["zone"] = ["Depot", {"name": "Area"}]
        row["sensors_status"] = []; del row["model"]; row["driver_phone"] = None
        values = mpi.result_values(row)
        self.assertEqual(json.loads(values["zone_data"]), row["status"]["zone"])
        self.assertEqual(json.loads(values["sensors_status"]), [])
        self.assertNotIn("model", values)
        self.assertIsNone(values["driver_phone"])
        for field in ("Password", "Username", "other_data"):
            row[field] = "never persist"
        self.assertNotIn("never persist", json.dumps(mpi.result_values(row), default=str))


class TestPhase2Transport(TestCase):
    def send(self, payload, status=200):
        response = requests.Response(); response.status_code = status
        response._content = json.dumps(payload).encode(); response.encoding = "utf-8"
        response._content_consumed = True
        return response

    @patch("requests.sessions.Session.send")
    def test_form_encoding_matches_urllib_reference(self, send):
        send.return_value = self.send([{"IMEI": "123456789012345", "LATITUDE": -24.1,
                                       "LONGITUDE": 28.2, "NAME": "Excavator", "PLATE": "AU24"}])
        client = mpi.MPIClient(mpi.ENDPOINT, 3, "fake user+", "fake&pass=+")
        self.assertEqual(client.object_list(), [vehicle()])
        prepared = send.call_args.args[0]
        self.assertEqual(prepared.body, b"functionName=api_objectlist&Username=fake+user%2B&Password=fake%26pass%3D%2B")
        self.assertEqual(prepared.headers["Content-Type"], "application/x-www-form-urlencoded")
        self.assertEqual(prepared.headers["Accept-Encoding"], "identity")
        self.assertNotIn("Authorization", prepared.headers)
        self.assertEqual(send.call_args.kwargs["timeout"], (5, 20))
        self.assertFalse(send.call_args.kwargs["allow_redirects"])

    @patch("requests.sessions.Session.send")
    def test_status_basic_auth_utf8_and_full_allowlist(self, send):
        row = record(); row["unrequested"] = "do not keep"
        send.return_value = self.send({"code": 0, "data": [row]})
        client = mpi.MPIClient(mpi.ENDPOINT, 3, "fake", "pāss")
        result = client.status("123456789012345")
        self.assertEqual(result["sensors_status"], row["sensors_status"])
        self.assertEqual(result["status"], row["status"])
        self.assertNotIn("unrequested", result)
        self.assertEqual(send.call_args.args[0].headers["Authorization"], "Basic ZmFrZTpwxIFzcw==")

    @patch("requests.sessions.Session.send")
    def test_endpoint_outcomes_are_independent_and_sanitized(self, send):
        client = mpi.MPIClient(mpi.ENDPOINT, 3, "fake", "fake-password")
        send.side_effect = [self.send([], 200), self.send({"msg": "secret body"}, 403)]
        client.object_list()
        with self.assertRaises(mpi.MPIError): client.status("123456789012345")
        self.assertEqual(client.outcomes["vehicle_list"]["http_status"], 200)
        self.assertTrue(client.outcomes["vehicle_list"]["ok"])
        self.assertEqual(client.outcomes["status"]["http_status"], 403)
        self.assertFalse(client.outcomes["status"]["ok"])
        self.assertNotIn("secret body", json.dumps(client.outcomes))
        self.assertNotIn("fake-password", json.dumps(client.outcomes))


class TestPhase2Settings(TestCase):
    def test_save_merges_background_discovery_and_status_with_user_edits(self):
        from engineering.engineering.doctype.api_mpi_settings.api_mpi_settings import APIMPISettings
        class Row(frappe._dict):
            def set(self, field, value): self[field] = value
            def as_dict(self): return dict(self)
        submitted = Row(name="row1", imei="123", asset="USER-ASSET", plate="Old", mapping_status="Unmatched")
        latest = frappe._dict(name="row1", imei="123", asset="AUTO-ASSET", plate="Fresh", vehicle_name="Fresh Name", mapping_status="Exact Match")
        discovered = Row(name="row2", imei="456", asset=None, plate="Discovered",
                         creation="original-creation", owner="original-owner", modified="discovery-time")
        previous = frappe._dict(vehicles=[latest, discovered], last_error="New status", last_success="Latest time")
        settings = Mock(vehicles=[submitted], username="edited-user", api_password="edited-fake-password",
                        endpoint=mpi.ENDPOINT, node=3, modified="user-save-time", modified_by="editing-user")
        settings.get_doc_before_save.return_value = previous
        settings.set.side_effect = lambda key, value: setattr(settings, key, value)
        settings.append.side_effect = lambda field, value: settings.vehicles.append(Row(value))
        APIMPISettings.before_validate(settings)
        APIMPISettings.validate(settings)
        self.assertEqual(settings.username, "edited-user")
        self.assertEqual(settings.api_password, "edited-fake-password")
        self.assertEqual(settings.last_error, "New status")
        self.assertEqual(settings.last_success, "Latest time")
        self.assertEqual(submitted.asset, "USER-ASSET")
        self.assertEqual(submitted.mapping_status, "Manual")
        self.assertEqual(submitted.plate, "Fresh")
        self.assertEqual([r.imei for r in settings.vehicles], ["123", "456"])
        self.assertEqual(settings.vehicles[1].creation, "original-creation")
        self.assertEqual(settings.vehicles[1].owner, "original-owner")
        self.assertEqual(settings.vehicles[1].modified, "user-save-time")
        self.assertEqual(settings.vehicles[1].modified_by, "editing-user")

    @patch.object(mpi, "frappe")
    def test_sync_state_does_not_change_form_revision(self, framework):
        mpi._sync_state(last_error="safe")
        self.assertFalse(framework.db.set_single_value.call_args.kwargs["update_modified"])

    @patch.object(mpi, "frappe")
    def test_refresh_endpoint_checks_read_permission_and_returns_only_status(self, framework):
        settings = Mock(last_attempt="time", last_success="time", last_error="safe",
                        vehicle_list_outcome="ok", status_outcome="ok")
        framework.get_single.return_value = settings
        value = mpi.get_sync_status()
        settings.check_permission.assert_called_once_with("read")
        self.assertNotIn("username", value); self.assertNotIn("api_password", value)
        settings.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): mpi.get_sync_status()

    @patch.object(mpi, "frappe")
    def test_sync_requires_write_permission(self, framework):
        framework.get_single.return_value.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): mpi.sync_now()
        framework.enqueue.assert_not_called()

    def test_sensitive_fields_have_restricted_read_permissions(self):
        schema = json.loads((Path(mpi.__file__).parents[1] / "engineering/doctype/mpi_results/mpi_results.json").read_text())
        levels = {f["fieldname"]: f.get("permlevel", 0) for f in schema["fields"]}
        for field in ("driver_name", "driver_phone", "vin", "info", "sensors_status"):
            self.assertEqual(levels[field], 1)
        readers = {p["role"] for p in schema["permissions"] if p.get("permlevel") == 1 and p.get("read")}
        self.assertEqual(readers, {"System Manager", "Engineering Manager", "Fleet Manager"})


class TestPhase2Upsert(TestCase):
    @patch.object(mpi, "convert_utc_to_system_timezone", side_effect=lambda dt: dt)
    @patch.object(mpi, "frappe")
    def test_all_fields_reach_one_imei_record_across_repeated_syncs(self, framework, timezone):
        saved = {}
        class Result(frappe._dict):
            def save(self, **kwargs): saved[self.imei] = self
        mapping = frappe._dict(name="mapping-1", asset="MANUALLY-SELECTED")
        framework.db.sql.return_value = [("mapping-1",)]
        framework.db.exists.side_effect = lambda doctype, name: name in saved
        framework.get_doc.side_effect = lambda doctype, name: mapping if doctype == "MPI Vehicle Mapping" else saved[name]
        framework.new_doc.side_effect = lambda doctype: Result()
        mpi._upsert(vehicle(), record())
        changed = record(); changed["current_mileage"] = 9999; changed["sensors_status"] = []
        del changed["model"]; changed["driver_phone"] = None; changed["status"]["alt"] = None
        mpi._upsert(vehicle(), changed)
        self.assertEqual(len(saved), 1)
        result = saved["123456789012345"]
        self.assertEqual(result.asset, "MANUALLY-SELECTED")
        self.assertEqual(result.list_latitude, -24.1)
        self.assertEqual(result.list_longitude, 28.2)
        self.assertEqual(result.plate, "AU24")
        self.assertEqual(result.vehicle_name, "Excavator")
        self.assertEqual(result.current_mileage, 9999)
        self.assertEqual(json.loads(result.sensors_status), [])
        self.assertEqual(result.vin, "FICTIONAL-VIN")
        self.assertEqual(result.unixtimestamp, 1700000000)
        self.assertEqual(result.model, "Test Model")
        self.assertIsNone(result.driver_phone)
        self.assertIn("alt", json.loads(result.null_fields))

    @patch.object(mpi, "convert_utc_to_system_timezone", side_effect=lambda dt: dt)
    @patch.object(mpi, "frappe")
    def test_missing_required_status_fields_never_write_a_result(self, framework, timezone):
        framework.db.sql.return_value = [("mapping-1",)]
        framework.get_doc.return_value = frappe._dict(name="mapping-1", asset=None)
        for missing in ("active", "lat", "lon", "speed", "direction", "moving", "parking", "unixtimestamp"):
            row = record(); del row["status"][missing]
            with self.subTest(field=missing), self.assertRaises(mpi.MPIError): mpi._upsert(vehicle(), row)
        framework.new_doc.assert_not_called()

    @patch.object(mpi, "convert_utc_to_system_timezone", side_effect=lambda dt: dt)
    def test_optional_null_is_distinguished_from_numeric_zero(self, timezone):
        row = record(); row["status"]["alt"] = None; row["current_mileage"] = None
        values = mpi.result_values(row)
        self.assertIsNone(values["alt"])
        self.assertIsNone(values["current_mileage"])
