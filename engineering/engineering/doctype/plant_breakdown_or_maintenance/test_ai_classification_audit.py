"""Isolated tests for PBM AI classification audit validation."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from engineering.controllers import (
    ai_classification_audit as service,
    auto_failure_classification as classifier,
)


class DummyDocument:
    def __init__(self, previous=None, **fields):
        self.__dict__.update(fields)
        self._previous = previous
        self.flags = SimpleNamespace()

    def get(self, key, default=None):
        return getattr(self, key, default)

    def is_new(self):
        return self._previous is None

    def get_doc_before_save(self):
        return self._previous


class TestAIClassificationAudit(unittest.TestCase):

    def setUp(self):
        self.throw_patcher = patch.object(
            service.frappe,
            "throw",
            side_effect=frappe.ValidationError,
        )
        self.throw_patcher.start()
        self.addCleanup(self.throw_patcher.stop)

        self.time_patcher = patch.object(
            service,
            "now_datetime",
            return_value="2026-11-11 12:00:00",
        )
        self.time_patcher.start()
        self.addCleanup(self.time_patcher.stop)

    def make_documents(self, reason="New correction reason"):
        previous = DummyDocument(
            name="PBM-TEST-001",
            ai_classification_audit="AUDIT-001",
            downtime_type="Breakdown",
            breakdown_reason="Park brake not working",
            failure_classification="Braking System",
            ai_classification_correction_reason="",
        )

        current = DummyDocument(
            previous=previous,
            name="PBM-TEST-001",
            ai_classification_audit="AUDIT-001",
            downtime_type="Breakdown",
            breakdown_reason="Park brake not working",
            failure_classification="Mechanical",
            ai_classification_correction_reason=reason,
        )

        audit = DummyDocument(
            name="AUDIT-001",
            audit_status="Finalised",
            breakdown_reference="PBM-TEST-001",
            ai_suggested_classification="Braking System",
            ai_model="qwen3:8b",
            suggested_by="operator@example.test",
            suggested_at="2026-11-11 10:00:00",
        )

        return current, previous, audit

    def test_correction_requires_reason(self):
        current, previous, audit = self.make_documents(reason="")

        with patch.object(service.frappe, "get_doc", return_value=audit):
            with self.assertRaises(frappe.ValidationError):
                service.validate_audit_reference(current)

    def test_correction_requires_changed_reason(self):
        current, previous, audit = self.make_documents(
            reason="Original explanation"
        )
        previous.ai_classification_correction_reason = (
            "Original explanation"
        )

        with patch.object(service.frappe, "get_doc", return_value=audit):
            with self.assertRaises(frappe.ValidationError):
                service.validate_audit_reference(current)

    def test_valid_correction_passes_validation(self):
        current, previous, audit = self.make_documents()

        with patch.object(service.frappe, "get_doc", return_value=audit):
            service.validate_audit_reference(current)

    def test_existing_audit_reference_cannot_be_removed(self):
        current, previous, audit = self.make_documents()
        current.ai_classification_audit = ""

        with self.assertRaises(frappe.ValidationError):
            service.validate_audit_reference(current)

    def test_unrelated_update_does_not_create_correction(self):
        current, previous, audit = self.make_documents()
        current.failure_classification = previous.failure_classification

        with (
            patch.object(service, "_lock_audit", return_value=audit),
            patch.object(service, "validate_audit_reference"),
            patch.object(service.frappe, "get_doc") as get_doc,
        ):
            service.finalise_audit(current)
            get_doc.assert_not_called()


    def test_initial_ai_decision_accepted(self):
        current, previous, audit = self.make_documents()
        current._previous = None
        current.failure_classification = "Braking System"
        audit.audit_status = "Suggested"

        db = MagicMock()
        db.get_value.return_value = None

        with (
            patch.object(service, "_lock_audit", return_value=audit),
            patch.object(service, "validate_audit_reference"),
            patch.object(service.frappe, "db", db),
            patch.object(
                service.frappe, "session",
                SimpleNamespace(user="operator@example.test"),
            ),
        ):
            service.finalise_audit(current)

        db.set_value.assert_called_once()
        values = db.set_value.call_args.args[2]

        self.assertEqual(values["decision"], "Accepted")
        self.assertEqual(values["event_type"], "AI Decision")
        self.assertEqual(values["audit_status"], "Finalised")
        self.assertEqual(
            values["final_classification"], "Braking System"
        )

    def test_initial_ai_decision_overridden(self):
        current, previous, audit = self.make_documents()
        current._previous = None
        audit.audit_status = "Suggested"

        db = MagicMock()
        db.get_value.return_value = None

        with (
            patch.object(service, "_lock_audit", return_value=audit),
            patch.object(service, "validate_audit_reference"),
            patch.object(service.frappe, "db", db),
            patch.object(
                service.frappe, "session",
                SimpleNamespace(user="operator@example.test"),
            ),
        ):
            service.finalise_audit(current)

        values = db.set_value.call_args.args[2]

        self.assertEqual(values["decision"], "Overridden")
        self.assertEqual(
            values["final_classification"], "Mechanical"
        )

    def test_correction_creates_separate_audit_event(self):
        current, previous, audit = self.make_documents()

        db = MagicMock()
        correction = MagicMock()

        with (
            patch.object(service, "_lock_audit", return_value=audit),
            patch.object(service, "validate_audit_reference"),
            patch.object(service.frappe, "db", db),
            patch.object(
                service.frappe, "session",
                SimpleNamespace(user="reviewer@example.test"),
            ),
            patch.object(
                service.frappe, "get_doc",
                return_value=correction,
            ) as get_doc,
        ):
            service.finalise_audit(current)

        correction.insert.assert_called_once_with(
            ignore_permissions=True
        )

        event = get_doc.call_args.args[0]

        self.assertEqual(event["event_type"], "Correction")
        self.assertEqual(event["decision"], "Corrected")
        self.assertEqual(
            event["previous_classification"], "Braking System"
        )
        self.assertEqual(
            event["final_classification"], "Mechanical"
        )
        self.assertEqual(
            event["correction_reason"], "New correction reason"
        )
        self.assertEqual(
            event["verified_by"], "reviewer@example.test"
        )

        db.set_value.assert_not_called()


    def test_pending_audit_rejects_other_user(self):
        current, previous, audit = self.make_documents()

        current._previous = None
        current.failure_classification = "Braking System"

        audit.audit_status = "Suggested"
        audit.breakdown_reference = None
        audit.breakdown_description = current.breakdown_reason
        audit.suggested_by = "original@example.test"

        with (
            patch.object(service.frappe, "get_doc", return_value=audit),
            patch.object(
                service.frappe,
                "session",
                SimpleNamespace(user="different@example.test"),
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                service.validate_audit_reference(current)


    def test_mcp_classification_uses_background_queue(self):
        """MCP entry point must delegate without creating an audit."""
        reason = "PARK BRAKE IS NOT WORKING"
        expected = {
            "status": "Queued",
            "request_id": "TEST-REQUEST-001",
        }

        with (
            patch.object(
                classifier,
                "queue_classification",
                return_value=expected,
            ) as queue,
            patch.object(
                classifier.frappe,
                "get_doc",
            ) as get_doc,
        ):
            result = classifier.classify_breakdown(reason)

        self.assertEqual(result, expected)
        queue.assert_called_once_with(reason)
        get_doc.assert_not_called()



    def test_save_creates_initial_audit(self):
        doc = DummyDocument(
            breakdown_reason="PARK BRAKE IS NOT WORKING",
            failure_classification="Mechanical",
            ai_classification_request_id="REQUEST-001",
        )

        result = {
            "classification": "Braking System",
            "model": "qwen3:8b",
        }

        audit = MagicMock()
        audit.name = "AUDIT-NEW-001"

        with (
            patch.object(
                service.frappe,
                "session",
                SimpleNamespace(user="operator@example.test"),
            ),
            patch(
                "engineering.controllers."
                "ai_classification_requests.verify_request_for_save",
                return_value=result,
            ) as verify,
            patch.object(
                service.frappe,
                "get_doc",
                return_value=audit,
            ) as get_doc,
        ):
            service.create_initial_audit_for_save(doc)

        verify.assert_called_once_with(
            "REQUEST-001",
            "operator@example.test",
            "PARK BRAKE IS NOT WORKING",
        )

        audit.insert.assert_called_once_with(
            ignore_permissions=True
        )

        data = get_doc.call_args.args[0]

        self.assertEqual(
            data["ai_request_id"], "REQUEST-001"
        )
        self.assertEqual(
            data["ai_suggested_classification"],
            "Braking System",
        )
        self.assertEqual(data["audit_status"], "Suggested")

        self.assertEqual(
            doc.ai_classification_audit,
            "AUDIT-NEW-001",
        )
        self.assertIsNone(
            doc.ai_classification_request_id
        )

    def test_no_request_creates_no_audit(self):
        doc = DummyDocument(
            ai_classification_request_id=None,
        )

        with patch.object(
            service.frappe,
            "get_doc",
        ) as get_doc:
            service.create_initial_audit_for_save(doc)

        get_doc.assert_not_called()

    def test_failed_initial_audit_insert_raises(self):
        doc = DummyDocument(
            breakdown_reason="PARK BRAKE IS NOT WORKING",
            failure_classification="Braking System",
            ai_classification_request_id="REQUEST-002",
        )

        audit = MagicMock()
        audit.insert.side_effect = RuntimeError(
            "Simulated database insert failure"
        )

        with (
            patch.object(
                service.frappe,
                "session",
                SimpleNamespace(user="operator@example.test"),
            ),
            patch(
                "engineering.controllers."
                "ai_classification_requests.verify_request_for_save",
                return_value={
                    "classification": "Braking System",
                    "model": "qwen3:8b",
                },
            ),
            patch.object(
                service.frappe,
                "get_doc",
                return_value=audit,
            ),
        ):
            with self.assertRaises(RuntimeError):
                service.create_initial_audit_for_save(doc)

        self.assertEqual(
            doc.ai_classification_request_id,
            "REQUEST-002",
        )
        self.assertIsNone(
            doc.get("ai_classification_audit")
        )



    def test_temporary_request_rejects_other_user(self):
        from engineering.controllers import (
            ai_classification_requests as requests,
        )

        cache = MagicMock()
        cache.get_value.return_value = {
            "user": "operator-a@example.test",
            "status": "Completed",
        }

        with (
            patch.object(requests.frappe, "cache", return_value=cache),
            patch.object(
                requests.frappe,
                "throw",
                side_effect=frappe.PermissionError,
            ),
        ):
            with self.assertRaises(frappe.PermissionError):
                requests.get_request(
                    "REQUEST-001",
                    "operator-b@example.test",
                )

    def test_temporary_request_rejects_expiry(self):
        from engineering.controllers import (
            ai_classification_requests as requests,
        )

        with (
            patch.object(requests, "get_request", return_value=None),
            patch.object(
                requests.frappe,
                "throw",
                side_effect=frappe.ValidationError,
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                requests.verify_request_for_save(
                    "EXPIRED-001",
                    "operator@example.test",
                    "PARK BRAKE IS NOT WORKING",
                )

    def test_temporary_request_rejects_changed_reason(self):
        from engineering.controllers import (
            ai_classification_requests as requests,
        )

        result = {
            "status": "Completed",
            "reason": "PARK BRAKE IS NOT WORKING",
            "classification": "Braking System",
            "model": "qwen3:8b",
        }

        with (
            patch.object(requests, "get_request", return_value=result),
            patch.object(
                requests.frappe,
                "throw",
                side_effect=frappe.ValidationError,
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                requests.verify_request_for_save(
                    "REQUEST-001",
                    "operator@example.test",
                    "HYDRAULIC LEAK",
                )

    def test_temporary_request_rejects_incomplete_result(self):
        from engineering.controllers import (
            ai_classification_requests as requests,
        )

        result = {
            "status": "Processing",
            "reason": "PARK BRAKE IS NOT WORKING",
            "classification": None,
            "model": None,
        }

        with (
            patch.object(requests, "get_request", return_value=result),
            patch.object(
                requests.frappe,
                "throw",
                side_effect=frappe.ValidationError,
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                requests.verify_request_for_save(
                    "REQUEST-001",
                    "operator@example.test",
                    "PARK BRAKE IS NOT WORKING",
                )



    def test_new_pbm_rejects_unverified_pending_audit(self):
        doc = DummyDocument(
            name="PBM-NEW-001",
            ai_classification_audit="AUDIT-UNVERIFIED",
            ai_classification_request_id=None,
            downtime_type="Breakdown",
            breakdown_reason="PARK BRAKE IS NOT WORKING",
            failure_classification="Braking System",
        )

        audit = DummyDocument(
            name="AUDIT-UNVERIFIED",
            audit_status="Suggested",
            ai_request_id="REQUEST-UNVERIFIED",
            suggested_by="operator@example.test",
            breakdown_description="PARK BRAKE IS NOT WORKING",
            breakdown_reference=None,
        )

        with (
            patch.object(
                service.frappe,
                "session",
                SimpleNamespace(user="operator@example.test"),
            ),
            patch.object(
                service.frappe,
                "get_doc",
                return_value=audit,
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                service.validate_audit_reference(doc)


if __name__ == "__main__":
    unittest.main()
