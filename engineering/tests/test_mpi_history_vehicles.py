"""Multi-vehicle imports use fictional mappings and offline API/database doubles."""
import json
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from engineering.controllers import mpi_history as history
from engineering.controllers.mpi import MPIError
from engineering.tests.test_mpi_history import IMEI, WINDOW, trip

OTHER = "222222222222222"


def row(imei=IMEI, **extra):
    return frappe._dict(name=f"row-{imei}", imei=imei, plate="TEST", asset="ASSET-A", status="Draft", **extra)


def request(vehicles=None, **extra):
    return frappe._dict(name="parent", imei=None, vehicles=vehicles or [], start_date="2026-11-19",
                        end_date="2026-11-19", include_report=0, status="Draft", **extra)


def settings():
    return frappe._dict(enabled=1, vehicles=[row(), row(OTHER)])


class TestVehicleSelection(TestCase):
    def test_accepts_known_selections_and_legacy_single_vehicle(self):
        self.assertEqual([v.imei for v in history.import_vehicles(request([row(), row(OTHER)]), settings())], [IMEI, OTHER])
        legacy = request(); legacy.imei = IMEI
        self.assertEqual(history.import_vehicles(legacy, settings())[0].imei, IMEI)

    def test_rejects_duplicates_invalid_unknown_and_ambiguous_mappings(self):
        for vehicles in ([row(), row()], [row("bad")], [row("999")], []):
            with self.subTest(vehicles=vehicles), self.assertRaises(MPIError):
                history.import_vehicles(request(vehicles), settings())
        duplicate_settings = settings(); duplicate_settings.vehicles.append(row())
        with self.assertRaises(MPIError):
            history.import_vehicles(request([row()]), duplicate_settings)
        with patch.object(history, "MAX_VEHICLES", 1), self.assertRaises(MPIError):
            history.import_vehicles(request([row(), row(OTHER)]), settings())

    @patch.object(history, "frappe")
    def test_mapping_picker_checks_permissions_and_returns_display_fields_only(self, framework):
        saved = Mock(vehicles=[frappe._dict(imei=IMEI, plate="TEST", asset="ASSET-A", driver_name="private"),
                               frappe._dict(imei=OTHER, plate="OTHER", asset=None)])
        framework.get_single.return_value = saved
        self.assertEqual(history.get_history_vehicle_options(), [
            {"imei": IMEI, "plate": "TEST", "asset": "ASSET-A"},
            {"imei": OTHER, "plate": "OTHER", "asset": None}])
        saved.check_permission.assert_called_with("write")
        saved.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): history.get_history_vehicle_options()

    @patch.object(history, "utc_windows", return_value=[WINDOW])
    @patch.object(history, "frappe")
    def test_parent_enqueues_once_and_resets_each_child_for_rerun(self, framework, windows):
        doc = request([row(), row(OTHER)])
        doc.check_permission = Mock()
        saved = settings(); saved.check_permission = Mock()
        framework.get_doc.return_value = doc
        framework.get_single.return_value = saved
        result = history.enqueue_import(doc.name)
        self.assertTrue(result["queued"])
        self.assertEqual(framework.enqueue.call_count, 1)
        queued = [c for c in framework.db.set_value.call_args_list if c.args[0] == "MPI History Vehicle"]
        self.assertEqual(len(queued), 2)
        self.assertTrue(all(c.args[2]["status"] == "Queued" for c in queued))
        doc.status = "Queued"
        history.enqueue_import(doc.name)
        self.assertEqual(framework.enqueue.call_count, 1)


class TestMultipleVehicleWorker(TestCase):
    @patch.object(history, "frappe")
    def test_failure_continues_and_rerun_upserts_without_cross_vehicle_collisions(self, framework):
        doc = request([row(), row(OTHER)])
        saved = settings()
        persisted = {}
        class HistoryDoc(frappe._dict):
            def save(self, **kwargs): persisted[self.source_key] = self
        framework.db.exists.side_effect = lambda doctype, name: name in persisted
        framework.get_doc.side_effect = lambda doctype, name: persisted[name]
        framework.new_doc.side_effect = lambda doctype: HistoryDoc()
        framework.cache.lock.return_value.acquire.return_value = True
        client = Mock()
        fail = [True]
        def fetch(command, imei, *args, **kwargs):
            if imei == IMEI and fail[0]: raise RuntimeError("private credentials and response")
            return {"run": {"code": 0, "tracks": [trip()]},
                "runstops": {"code": 0, "stops": [], "parkings": []},
                "get_idle": {"code": 0, "data": {imei: []}},
                "ag_geozones": {"code": 0, "data": []},
                "distance": {"code": 0, "distance": {"length": 0}}}[command]
        client.fetch.side_effect = fetch
        history._run_vehicles(doc, saved, client, [WINDOW])
        self.assertEqual([v.status for v in doc.vehicles], ["Failed", "Completed"])
        self.assertEqual([v.records_processed for v in doc.vehicles], [0, 2])
        parent = [c.args[2] for c in framework.db.set_value.call_args_list if c.args[0] == history.IMPORT][-1]
        self.assertEqual(parent["status"], "Partial")
        self.assertNotIn("private", json.dumps(parent, default=str))
        self.assertEqual(len(json.loads(doc.vehicles[1].endpoint_outcomes)), 5)
        fail[0] = False
        history._run_vehicles(doc, saved, client, [WINDOW])
        history._run_vehicles(doc, saved, client, [WINDOW])
        self.assertEqual(len(persisted), 4)
        self.assertEqual([v.status for v in doc.vehicles], ["Completed", "Completed"])
        parent = [c.args[2] for c in framework.db.set_value.call_args_list if c.args[0] == history.IMPORT][-1]
        self.assertEqual((parent["status"], parent["records_processed"]), ("Completed", 4))

    @patch.object(history, "frappe")
    def test_lock_contention_for_one_vehicle_does_not_stop_the_next(self, framework):
        doc = request([row(), row(OTHER)])
        framework.cache.lock.return_value.acquire.side_effect = [False, True]
        client = Mock()
        client.fetch.side_effect = lambda command, *a, **k: {"code": 0, "tracks": []} if command == "run" else {"code": 0}
        with patch.object(history, "_execute", return_value={"status": "Completed", "records_processed": 0,
                "endpoint_outcomes": "{}", "last_error": ""}) as execute:
            history._run_vehicles(doc, settings(), client, [WINDOW])
        self.assertEqual([v.status for v in doc.vehicles], ["Failed", "Completed"])
        self.assertEqual(execute.call_count, 1)
        framework.cache.lock.return_value.release.assert_called_once()


class TestVehicleRequestModel(TestCase):
    @patch("engineering.engineering.doctype.mpi_history_import.mpi_history_import.frappe")
    def test_draft_save_resolves_plate_asset_and_rejects_spoofed_status(self, framework):
        from engineering.engineering.doctype.mpi_history_import.mpi_history_import import MPIHistoryImport
        class Value(frappe._dict):
            def set(self, key, value): self[key] = value
            def get_doc_before_save(self): return None
        child = Value(imei=IMEI, plate="SPOOFED", asset="SPOOFED", status="Completed", records_processed=999)
        doc = Value(request([child]))
        saved = Mock(vehicles=settings().vehicles)
        framework.get_single.return_value = saved
        MPIHistoryImport.before_validate(doc)
        MPIHistoryImport.validate(doc)
        self.assertEqual((child.plate, child.asset), ("TEST", "ASSET-A"))
        self.assertEqual((child.status, child.records_processed), ("Draft", 0))
        saved.check_permission.assert_called_with("write")

    @patch("engineering.engineering.doctype.mpi_history_import.mpi_history_import.frappe")
    def test_stale_save_preserves_child_progress_and_freezes_selected_identity(self, framework):
        from engineering.engineering.doctype.mpi_history_import.mpi_history_import import MPIHistoryImport
        class Value(frappe._dict):
            def set(self, key, value): self[key] = value
            def get_doc_before_save(self): return self.previous
        old = row(); old.update(status="Completed", records_processed=7, endpoint_outcomes='{"run": {"records": 7}}')
        previous = request([old]); previous.status = "Running"
        child = Value(row()); child.update(status="Queued", records_processed=0)
        doc = Value(request([child])); doc.previous = previous
        MPIHistoryImport.before_validate(doc)
        self.assertEqual((child.status, child.records_processed), ("Completed", 7))
        self.assertEqual(child.endpoint_outcomes, old.endpoint_outcomes)
        MPIHistoryImport.validate(doc)
        child.imei = OTHER
        framework.throw.side_effect = ValueError()
        with self.assertRaises(ValueError): MPIHistoryImport.validate(doc)
        framework.get_single.assert_not_called()


class TestWorkerLimitsAndSetup(TestCase):
    @patch.object(history, "frappe")
    def test_expired_vehicle_deadline_prevents_api_calls_and_records_each_endpoint(self, framework):
        client = Mock()
        result = history._execute(frappe._dict(name="parent", imei=IMEI, include_report=0), client,
                                  "ASSET-A", [WINDOW], deadline=0)
        client.fetch.assert_not_called()
        self.assertEqual(result["status"], "Failed")
        self.assertEqual(len(json.loads(result["endpoint_outcomes"])), 5)

    @patch.object(history, "frappe")
    def test_lock_release_failure_does_not_abort_remaining_vehicles(self, framework):
        doc = request([row(), row(OTHER)])
        framework.cache.lock.return_value.acquire.return_value = True
        framework.cache.lock.return_value.release.side_effect = [RuntimeError("private Redis details"), None]
        with patch.object(history, "_execute", return_value={"status": "Completed", "records_processed": 0,
                "endpoint_outcomes": "{}", "last_error": ""}):
            history._run_vehicles(doc, settings(), Mock(), [WINDOW])
        self.assertEqual(doc.vehicles[1].status, "Completed")
        self.assertNotIn("private", doc.vehicles[0].last_error)

    @patch.object(history, "frappe")
    def test_global_setup_failure_marks_all_unprocessed_children_failed(self, framework):
        doc = request([row(), row(OTHER)])
        doc.check_permission = Mock()
        saved = Mock(enabled=True, username="fake-user")
        saved.get_password.return_value = None
        framework.get_doc.return_value = doc
        framework.get_single.return_value = saved
        history.run_import(doc.name)
        self.assertEqual([r.status for r in doc.vehicles], ["Failed", "Failed"])
        changes = [c.args[2] for c in framework.db.set_value.call_args_list if c.args[0] == history.IMPORT]
        self.assertEqual(changes[-1]["status"], "Failed")
