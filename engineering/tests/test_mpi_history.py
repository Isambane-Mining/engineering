"""MPI history: fictional endpoint fixtures, mocked HTTP/DB, no live credentials."""
import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from engineering.controllers import mpi_history as history
from engineering.controllers.mpi import MPIError

IMEI = "123456789012345"
START = 1795046400  # 2026-11-19T00:00:00Z
END = START + 86400
WINDOW = (START, END)
NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
TEMPLATE = {"id": 7, "name": "Mileage report"}


def trip(**extra):
    return {"ts": START + 10, "te": START + 70, "length": 1.5, "maxspeed": 20,
            "avgspeed": 15, "lats": "-25", "lons": "28", "late": "-24", "lone": "29", **extra}


def report_row(**extra):
    return {"agentid": 42, "ts": START + 10, "te": START + 70, "length": 1.5,
            "data": ["discard presentation values"], "fn": 1, **extra}


def report(**extra):
    return {"success": True, "report_type": 7, "name": "Mileage report",
            "headers": ["discard"], "fuel": True, "aggr": ["discard"],
            "data": {"group-key": {"vehicle-key": [report_row()]}}, **extra}


class TestUTCBoundaries(TestCase):
    def test_closed_utc_days_and_inclusive_date_selection(self):
        self.assertEqual(history.utc_windows("2026-11-19", "2026-11-19", now=NOW), [WINDOW])
        self.assertEqual(history.utc_windows("2026-11-18", "2026-11-19", now=NOW),
                         [(START - 86400, START), WINDOW])

    def test_invalid_reversed_future_and_unbounded_dates_are_rejected(self):
        for start, end in [("bad", "2026-11-19"), ("2026-11-20", "2026-11-19"),
                           ("2026-11-20", "2026-11-20"), ("2026-11-21", "2026-11-21"),
                           ("2026-11-01", "2026-11-19"), ("2026-11-19T00:00:00+02:00", "2026-11-19")]:
            with self.subTest(start=start, end=end), self.assertRaises(MPIError):
                history.utc_windows(start, end, now=NOW)
        self.assertEqual(len(history.utc_windows("2026-11-13", "2026-11-19", now=NOW)), 7)

    def test_half_open_window_overlap_and_correction_keys(self):
        rows = {"before": trip(ts=START - 20, te=START), "crossing": trip(ts=START - 10, te=START + 10),
                "after": trip(ts=END, te=END + 5), "inside": trip()}
        values = history.parse_endpoint("run", {"code": 0, "tracks": rows}, IMEI, WINDOW)
        self.assertEqual(len(values), 2)
        corrected = dict(values[1], end_epoch=values[1]["end_epoch"] + 5)
        self.assertEqual(history.history_key(IMEI, values[1]), history.history_key(IMEI, corrected))
        self.assertEqual(values[0]["start_utc"], "2026-11-18T23:59:50Z")


class TestHistoryEndpoints(TestCase):
    def test_trip_dictionary_and_duplicate_rows(self):
        row = trip(driver_name="discard", fuel=99, configuration="discard")
        values = history.parse_endpoint("run", {"code": 0, "tracks": {"1": row, "2": row}}, IMEI, WINDOW)
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["activity_type"], "Trip")
        self.assertEqual(values[0]["distance"], 1.5)
        self.assertEqual(values[0]["max_speed"], 20)
        self.assertEqual(values[0]["start_latitude"], -25)
        self.assertEqual(values[0]["end_longitude"], 29)
        self.assertNotIn("discard", json.dumps(values))
        self.assertNotIn("fuel", json.dumps(values))

    def test_stops_and_parkings_do_not_collide(self):
        row = {"ts": START + 10, "te": START + 70, "dur": 60, "lat": -25, "lon": 28, "address": ["discard"]}
        values = history.parse_endpoint("runstops", {"code": 0, "stops": [row], "parkings": [row]}, IMEI, WINDOW)
        self.assertEqual([v["activity_type"] for v in values], ["Stop", "Parking"])
        self.assertEqual(values[0]["duration_seconds"], 60)
        self.assertNotEqual(history.history_key(IMEI, values[0]), history.history_key(IMEI, values[1]))
        self.assertNotIn("address", json.dumps(values))

    def test_idle_vehicle_keyed_response(self):
        payload = {"code": 0, "data": {IMEI: [{"idle_start": START + 10, "idle_end": START + 40}]}}
        values = history.parse_endpoint("get_idle", payload, IMEI, WINDOW)
        self.assertEqual(values[0]["activity_type"], "Idle")
        self.assertEqual(values[0]["duration_seconds"], 30)
        with self.assertRaises(MPIError):
            history.parse_endpoint("get_idle", {"code": 0, "data": {"999": []}}, IMEI, WINDOW)

    def test_zone_visits_allow_open_end_and_distinguish_zones(self):
        payload = {"code": 0, "data": [{"ts": START, "te": None, "zonename": "Fictional A", "group": "Test"},
                                       {"ts": START, "te": START + 30, "zonename": "Fictional B", "group": "Test"}]}
        values = history.parse_endpoint("ag_geozones", payload, IMEI, WINDOW)
        self.assertEqual(len(values), 2)
        self.assertIsNone(values[0]["end_epoch"])
        self.assertIn("end_epoch", values[0]["missing_fields"])
        self.assertNotEqual(history.history_key(IMEI, values[0]), history.history_key(IMEI, values[1]))

    def test_daily_distance_summary_is_allowlisted_and_window_keyed(self):
        payload = {"code": 0, "distance": {"length": 20.5, "duration": 120, "max_speed": 35, "avg_speed": 20,
                    "trips_cnt": 3, "trips_time": 100, "trips_driving": 80, "parking_count": 2,
                    "parking_time": 20, "can": 99, "fuel": 100, "tracks": {"raw": "discard"}}}
        value = history.parse_endpoint("distance", payload, IMEI, WINDOW)[0]
        self.assertEqual(value["activity_type"], "Distance Summary")
        self.assertEqual(value["trips_count"], 3)
        self.assertEqual(value["driving_seconds"], 80)
        self.assertEqual(value["distance"], 20.5)
        self.assertEqual((value["start_epoch"], value["end_epoch"]), WINDOW)
        self.assertNotIn("discard", json.dumps(value))
        different_day = dict(value, start_epoch=START - 86400, end_epoch=START)
        self.assertNotEqual(history.history_key(IMEI, value), history.history_key(IMEI, different_day))

    def test_empty_results_are_successful_and_incomplete_shapes_fail_closed(self):
        for cmd, payload in [("run", {"code": 0, "tracks": {}}),
                ("runstops", {"code": 0, "stops": [], "parkings": []}),
                ("get_idle", {"code": 0, "data": {IMEI: []}}),
                ("ag_geozones", {"code": 0, "data": []})]:
            self.assertEqual(history.parse_endpoint(cmd, payload, IMEI, WINDOW), [])
        for cmd, payload in [("run", {"code": 1, "msg": "secret"}), ("run", {"code": 0}),
                ("runstops", {"code": 0, "stops": []}), ("distance", {"code": 0}),
                ("run", {"code": 0, "tracks": {"1": {"ts": START}}}),
                ("ag_geozones", {"code": 0, "data": [{"ts": START, "zonename": "Test"}]})]:
            with self.subTest(cmd=cmd), self.assertRaises(MPIError):
                history.parse_endpoint(cmd, payload, IMEI, WINDOW)

    def test_rows_are_bounded(self):
        with patch.object(history, "MAX_ENDPOINT_ROWS", 1), self.assertRaises(MPIError):
            history.parse_endpoint("run", {"code": 0, "tracks": [trip(), trip(ts=START + 100, te=START + 150)]}, IMEI, WINDOW)


class TestAuditedActivityReport(TestCase):
    def test_names_are_inspected_and_only_audited_activity_template_is_selected(self):
        templates = {"code": 0, "data": [{"id": 1, "name": "Fuel mileage", "group": "Fuel"},
            {"id": 2, "name": "Driver trips", "group": "Driver"}, {"id": 7, "name": "Mileage report", "group": "Movement"}]}
        self.assertEqual(history.select_activity_template(templates), TEMPLATE)
        with self.assertRaises(MPIError):
            history.select_activity_template({"code": 0, "data": [{"id": 2, "name": "Driver trips"}]})

    def test_nonstandard_success_envelope_and_grouped_rows(self):
        values = history.parse_endpoint("get_report", report(), IMEI, WINDOW, template=TEMPLATE, vehicle_id=42)
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["activity_type"], "Activity Report")
        self.assertEqual(values[0]["distance"], 1.5)
        self.assertEqual(values[0]["template_id"], "7")
        self.assertNotIn("discard", json.dumps(values))
        self.assertNotIn("fuel", json.dumps(values))
        self.assertNotIn("agentid", json.dumps(values))

    def test_wrong_vehicle_schema_template_or_failure_is_rejected(self):
        for payload in [report(success=False), report(data={"x": [report_row(agentid=99)]}),
                report(data={"x": [{"agentid": 42, "ts": START, "te": END, "fuel": 5}]}),
                report(report_type=99), {"code": 0, "data": []}]:
            with self.assertRaises(MPIError):
                history.parse_endpoint("get_report", payload, IMEI, WINDOW, template=TEMPLATE, vehicle_id=42)


class TestHistoryClient(TestCase):
    def test_only_proven_endpoints_and_exact_utc_parameters(self):
        client = history.HistoryClient("https://web.mpitracking.co.za", 3, "fake", "fake-password")
        with patch.object(client, "_request", return_value={}) as request:
            for cmd in ("run", "runstops", "distance", "ag_geozones"):
                client.fetch(cmd, IMEI, WINDOW)
                params = request.call_args.kwargs["params"]
                self.assertEqual((params["start"], params["stop"]), (START, END - 1))
                self.assertEqual(params["node"], 3)
            client.fetch("get_idle", IMEI, WINDOW)
            self.assertEqual(request.call_args.kwargs["params"], {"cmd": "get_idle", "node": 3,
                "imei": IMEI, "time_start": START, "time_end": END - 1})
            client.fetch("get_report", IMEI, WINDOW, template=TEMPLATE, vehicle_id=42)
            params = request.call_args.kwargs["params"]
            self.assertEqual((params["veh_id"], params["report_type"], params["group"], params["explode"]), (42, 7, 2, 3))
            self.assertEqual(params["format"], "json")
            self.assertEqual(params["tz"], "Africa/Johannesburg")
            for cmd in ("zones_mileage", "get_status_and_distance", "geofencelist", "fuel", "drivers_add"):
                with self.assertRaises(MPIError): client.fetch(cmd, IMEI, WINDOW)


class TestHistoryPersistence(TestCase):
    @patch.object(history, "frappe")
    def test_repeated_and_corrected_events_upsert_one_record(self, framework):
        saved = {}
        class Doc(frappe._dict):
            def save(self, **kwargs): saved[self.source_key] = self
        framework.db.exists.side_effect = lambda doctype, name: name in saved
        framework.get_doc.side_effect = lambda doctype, name: saved[name]
        framework.new_doc.side_effect = lambda doctype: Doc()
        row = history.parse_endpoint("run", {"code": 0, "tracks": [trip()]}, IMEI, WINDOW)[0]
        history.upsert_history(IMEI, "SELECTED-ASSET", row)
        history.upsert_history(IMEI, "REASSIGNED-ASSET", dict(row, end_epoch=row["end_epoch"] + 10))
        self.assertEqual(len(saved), 1)
        result = next(iter(saved.values()))
        self.assertEqual(result.asset, "SELECTED-ASSET")
        self.assertEqual(result.end_epoch, START + 80)
        self.assertEqual(result.imei, IMEI)
        self.assertTrue(all(call.args[0] == "MPI Activity History" for call in framework.get_doc.call_args_list))

    @patch.object(history, "frappe")
    def test_queue_requires_permissions_and_no_network_call(self, framework):
        framework.get_doc.return_value.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): history.enqueue_import("request-1")
        framework.enqueue.assert_not_called()

    @patch.object(history, "utc_windows", return_value=[WINDOW])
    @patch.object(history, "frappe")
    def test_queue_is_manual_deduplicated_and_does_not_save_settings(self, framework, windows):
        doc = Mock(name="request-1", imei=IMEI, start_date="2026-11-19", end_date="2026-11-19", status="Completed")
        doc.name = "request-1"
        settings = Mock(enabled=True, vehicles=[frappe._dict(imei=IMEI, asset="SELECTED-ASSET")])
        framework.get_doc.return_value = doc; framework.get_single.return_value = settings
        self.assertTrue(history.enqueue_import(doc.name)["queued"])
        self.assertTrue(framework.enqueue.call_args.kwargs["deduplicate"])
        self.assertTrue(framework.enqueue.call_args.kwargs["enqueue_after_commit"])
        self.assertFalse(framework.db.set_value.call_args.kwargs["update_modified"])
        settings.save.assert_not_called()
        doc.check_permission.assert_called_once_with("write")
        settings.check_permission.assert_called_once_with("write")

    @patch.object(history, "frappe")
    def test_status_refresh_is_permission_checked_and_has_no_parameters_or_secrets(self, framework):
        doc = Mock(); doc.get.side_effect = lambda field: "safe"
        framework.get_doc.return_value = doc
        result = history.get_import_status("request-1")
        self.assertEqual(set(result), set(history.STATUS_FIELDS))
        doc.check_permission.assert_called_once_with("read")
        self.assertNotIn("imei", result)
        doc.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): history.get_import_status("request-1")


class TestHistoryWorker(TestCase):
    def fixture(self, command):
        return {"run": {"code": 0, "tracks": {"t": trip()}},
            "runstops": {"code": 0, "stops": [], "parkings": []},
            "get_idle": {"code": 0, "data": {IMEI: []}},
            "ag_geozones": {"code": 0, "data": []},
            "distance": {"code": 0, "distance": {"length": 0}}}[command]

    @patch.object(history, "_state")
    @patch.object(history, "upsert_history")
    @patch.object(history, "frappe")
    def test_worker_continues_after_failed_endpoint_with_safe_partial_outcome(self, framework, upsert, state):
        doc = frappe._dict(name="request-1", imei=IMEI, include_report=0)
        client = Mock()
        def fetch(command, *args, **kwargs):
            if command == "get_idle": raise ValueError("fake-password / untrusted response body")
            return self.fixture(command)
        client.fetch.side_effect = fetch
        history._execute(doc, client, "SELECTED-ASSET", [WINDOW])
        self.assertEqual([c.args[0] for c in client.fetch.call_args_list], list(history.COMMANDS))
        client.templates.assert_not_called()
        self.assertEqual(state.call_args.kwargs["status"], "Partial")

        self.assertEqual(state.call_args.kwargs["records_processed"], 2)
        self.assertNotIn("fake-password", state.call_args.kwargs["last_error"])
        self.assertNotIn("untrusted", state.call_args.kwargs["endpoint_outcomes"])
        framework.db.rollback.assert_called()

    @patch.object(history, "_state")
    @patch.object(history, "upsert_history")
    @patch.object(history, "frappe")
    def test_endpoint_save_failure_rolls_back_batch_and_other_endpoints_continue(self, framework, upsert, state):
        doc = frappe._dict(name="request-1", imei=IMEI, include_report=0)
        client = Mock(); client.fetch.side_effect = lambda command, *a, **k: self.fixture(command)
        upsert.side_effect = [RuntimeError("private backend detail"), "key"]
        history._execute(doc, client, "SELECTED-ASSET", [WINDOW])
        self.assertEqual(state.call_args.kwargs["status"], "Partial")
        self.assertEqual(state.call_args.kwargs["records_processed"], 1)
        framework.db.rollback.assert_called_once()
        self.assertNotIn("private backend detail", state.call_args.kwargs["last_error"])

    @patch.object(history, "_state")
    @patch.object(history, "upsert_history")
    @patch.object(history, "frappe")
    def test_optional_report_uses_saved_identity_without_status_or_other_api_calls(self, framework, upsert, state):
        doc = frappe._dict(name="request-1", imei=IMEI, include_report=1)
        framework.db.get_value.return_value = "42"
        client = Mock(); client.templates.return_value = {"code": 0, "data": [dict(TEMPLATE, group="Movement")]}
        client.fetch.side_effect = lambda command, *a, **k: report() if command == "get_report" else self.fixture(command)
        history._execute(doc, client, "SELECTED-ASSET", [WINDOW])
        self.assertEqual(state.call_args.kwargs["status"], "Completed")
        self.assertEqual(state.call_args.kwargs["records_processed"], 3)
        self.assertEqual(client.fetch.call_args_list[-1].kwargs["vehicle_id"], "42")
        self.assertEqual([c.args[0] for c in client.fetch.call_args_list], [*history.COMMANDS, "get_report"])
        client.status.assert_not_called()

    @patch.object(history, "_state")
    @patch.object(history, "upsert_history")
    @patch.object(history, "frappe")
    def test_non_activity_template_never_runs_report(self, framework, upsert, state):
        doc = frappe._dict(name="request-1", imei=IMEI, include_report=1)
        client = Mock(); client.templates.return_value = {"code": 0, "data": [{"id": 1, "name": "Driver trips"}]}
        client.fetch.side_effect = lambda command, *a, **k: self.fixture(command)
        history._execute(doc, client, "SELECTED-ASSET", [WINDOW])
        self.assertEqual([c.args[0] for c in client.fetch.call_args_list], list(history.COMMANDS))
        self.assertEqual(state.call_args.kwargs["status"], "Partial")

    @patch.object(history, "_state")
    @patch.object(history, "upsert_history")
    @patch.object(history, "frappe")
    def test_total_import_records_are_bounded(self, framework, upsert, state):
        doc = frappe._dict(name="request-1", imei=IMEI, include_report=0)
        client = Mock(); client.fetch.side_effect = lambda command, *a, **k: self.fixture(command)
        with patch.object(history, "MAX_IMPORT_ROWS", 1):
            history._execute(doc, client, "SELECTED-ASSET", [WINDOW])
        self.assertEqual(state.call_args.kwargs["records_processed"], 1)
        self.assertEqual(state.call_args.kwargs["status"], "Partial")


class TestHistoryRequestModel(TestCase):
    def test_background_status_is_retained_and_completed_parameters_are_immutable(self):
        from engineering.engineering.doctype.mpi_history_import.mpi_history_import import MPIHistoryImport
        class Request(frappe._dict):
            def set(self, field, value): self[field] = value
            def get_doc_before_save(self): return self.previous
        previous = frappe._dict(status="Completed", records_processed=5, imei=IMEI,
            start_date="2026-11-19", end_date="2026-11-19", include_report=0)
        doc = Request(previous=previous, status="Draft", records_processed=0, imei=IMEI,
            start_date="2026-11-19", end_date="2026-11-19", include_report=0)
        MPIHistoryImport.before_validate(doc)
        self.assertEqual(doc.status, "Completed")
        self.assertEqual(doc.records_processed, 5)
        with patch("engineering.engineering.doctype.mpi_history_import.mpi_history_import.utc_windows", return_value=[WINDOW]):
            MPIHistoryImport.validate(doc)
            doc.start_date = "2026-11-18"
            with patch("engineering.engineering.doctype.mpi_history_import.mpi_history_import.frappe.throw", side_effect=ValueError()):
                with self.assertRaises(ValueError): MPIHistoryImport.validate(doc)
