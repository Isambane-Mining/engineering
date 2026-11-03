import importlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe


class TestLabValidation(TestCase):
    def setUp(self):
        self.audit = importlib.import_module(
            "engineering.controllers.engineering_legals_lab_validation"
        )

    def test_missing_file_reference_is_recorded_without_masking_access_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.pdf"
            file = frappe._dict(
                name="missing-file", file_url="/private/files/missing.pdf"
            )
            document = SimpleNamespace(
                validate_file_path=lambda: None, get_full_path=lambda: str(missing)
            )
            with (
                patch.object(frappe.local, "site", "juan.isambane.co.za", create=True),
                patch.object(frappe, "get_all", side_effect=[[], [file]]),
                patch.object(frappe, "get_doc", return_value=document),
            ):
                self.assertEqual(
                    self.audit.read_state()["content_hashes"],
                    {"missing-file": "missing:ENOENT"},
                )
            with (
                patch.object(frappe.local, "site", "juan.isambane.co.za", create=True),
                patch.object(frappe, "get_all", side_effect=[[], [file]]),
                patch.object(frappe, "get_doc", return_value=document),
                patch("builtins.open", side_effect=PermissionError("unreadable")),
                self.assertRaises(PermissionError),
            ):
                self.audit.read_state()

    def test_missing_baseline_requires_explicit_acceptance_and_detects_recovery(self):
        state = {
            "records": [],
            "files": [{"name": "missing", "file_url": "/files/old.pdf"}],
            "content_hashes": {"missing": "missing:ENOENT"},
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(frappe.local, "site", "juan.isambane.co.za", create=True),
            patch.object(self.audit, "read_state", return_value=state),
        ):
            path = str(Path(directory) / "accepted.json")
            with self.assertRaises(frappe.ValidationError):
                self.audit.capture_snapshot(path, expected_count=0)
            self.assertFalse(Path(path).exists())
            self.assertEqual(
                self.audit.capture_snapshot(
                    path, expected_count=0, allow_missing_files=True
                )["missing_files"],
                1,
            )
            self.assertTrue(self.audit.verify_snapshot(path)["ok"])
            with (
                patch.object(
                    self.audit,
                    "read_state",
                    return_value=dict(state, content_hashes={"missing": "new-sha256"}),
                ),
                self.assertRaises(frappe.ValidationError),
            ):
                self.audit.verify_snapshot(path)

    def test_production_or_unspecified_site_is_rejected_before_reading_data(self):
        with (
            patch.object(
                frappe.local, "site", "production.example.invalid", create=True
            ),
            self.assertRaises(frappe.PermissionError),
        ):
            self.audit.capture_snapshot("/tmp/should-not-exist.json")

    def test_installation_check_requires_database_uniqueness_and_disabled_empty_configuration(
        self,
    ):
        site = SimpleNamespace(fieldtype="Link", options="Location", unique=1)
        parent = SimpleNamespace(
            istable=0, autoname="field:site", get_field=lambda name: site
        )
        child = SimpleNamespace(istable=1)
        legal = SimpleNamespace(has_field=lambda name: True)
        metadata = {
            "Engineering Legals Site Configuration": parent,
            "Engineering Legals Site Section Rule": child,
            "Engineering Legals": legal,
        }
        database = SimpleNamespace(
            table_exists=lambda name: True,
            count=lambda *args, **kwargs: 0,
            sql=lambda *args, **kwargs: [],
        )
        with (
            patch.object(frappe.local, "site", "juan.isambane.co.za", create=True),
            patch.object(frappe, "db", database),
            patch.object(frappe, "conf", {}),
            patch.object(frappe, "get_meta", side_effect=lambda name: metadata[name]),
        ):
            with self.assertRaises(frappe.ValidationError):
                self.audit.verify_installation()
            database.sql = lambda *args, **kwargs: [
                {"Column_name": "site", "Non_unique": 0}
            ]
            self.assertTrue(self.audit.verify_installation()["ok"])
            with (
                patch.object(
                    frappe, "conf", {"engineering_legals_site_rules_enabled": 1}
                ),
                self.assertRaises(frappe.ValidationError),
            ):
                self.audit.verify_installation()

    def test_added_columns_allowed_but_changed_dates_or_attachments_fail_verification(
        self,
    ):
        baseline = {
            "records": [
                {
                    "name": "old",
                    "expiry_date": "2026-07-31",
                    "attach_paper": "/files/old.pdf",
                }
            ],
            "files": [{"name": "file", "file_url": "/files/old.pdf"}],
            "content_hashes": {"file": "abc"},
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(frappe.local, "site", "juan.isambane.co.za", create=True),
            patch.object(self.audit, "read_state", return_value=baseline),
        ):
            path = str(Path(directory) / "baseline.json")
            self.audit.capture_snapshot(path, expected_count=1)
            with self.assertRaises(FileExistsError):
                self.audit.capture_snapshot(path, expected_count=1)
            expanded = dict(
                baseline,
                records=[dict(baseline["records"][0], expiry_rule_snapshot=None)],
            )
            with patch.object(self.audit, "read_state", return_value=expanded):
                self.assertTrue(self.audit.verify_snapshot(path)["ok"])
            for changed in [
                dict(
                    baseline,
                    records=[dict(baseline["records"][0], expiry_date="2027-01-31")],
                ),
                dict(baseline, content_hashes={"file": "changed"}),
            ]:
                with (
                    patch.object(self.audit, "read_state", return_value=changed),
                    self.assertRaises(frappe.ValidationError),
                ):
                    self.audit.verify_snapshot(path)
