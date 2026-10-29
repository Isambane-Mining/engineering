import base64
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from test_engineering_legals_site_rules import configuration, row, values

from engineering.controllers import engineering_legals_rules as rules
from engineering.controllers import hsec
from engineering.controllers import legals_history_imports as imports
from engineering.engineering.doctype.engineering_legals.engineering_legals import (
    EngineeringLegals,
)
from engineering.engineering.doctype.engineering_legals_supplier_portal_draft.engineering_legals_supplier_portal_draft import (
    EngineeringLegalssupplierPortalDraft,
)
from engineering.templates.pages import engineering_legals_list as supplier_list


class TestCaptureIntegrations(TestCase):
    def test_direct_supplier_legal_write_checks_incoming_and_persisted_asset_scope(
        self,
    ):
        for incoming, previous in [("other", None), ("owned", "other")]:
            before = (
                SimpleNamespace(**values(fleet_number=previous)) if previous else None
            )
            doc = SimpleNamespace(
                **values(fleet_number=incoming), get_doc_before_save=lambda before=before: before
            )
            with (
                patch.object(
                    frappe.local,
                    "session",
                    SimpleNamespace(user="supplier@example.invalid"),
                    create=True,
                ),
                patch.object(frappe, "get_roles", return_value=["Supplier"]),
                patch(
                    "engineering.templates.pages.engineering_legals_sup._get_user_suppliers",
                    return_value=["OWNER"],
                ),
                patch.object(rules, "supplier_sites", return_value=["Gwab"]),
                patch.object(
                    frappe,
                    "db",
                    SimpleNamespace(
                        exists=lambda doctype, filters: filters["name"] == "owned"
                    ),
                ),
                patch.object(rules, "load_configuration", return_value=None),
                self.assertRaises(frappe.PermissionError),
            ):
                EngineeringLegals.validate(doc)

    def test_direct_supplier_own_historical_legal_keeps_stored_expiry(self):
        before = SimpleNamespace(**values(expiry_date="2026-07-31"))
        doc = SimpleNamespace(
            **values(expiry_date="2099-01-01"), get_doc_before_save=lambda: before
        )
        with (
            patch.object(
                frappe.local,
                "session",
                SimpleNamespace(user="supplier@example.invalid"),
                create=True,
            ),
            patch.object(frappe, "get_roles", return_value=["Supplier"]),
            patch(
                "engineering.templates.pages.engineering_legals_sup._get_user_suppliers",
                return_value=["OWNER"],
            ),
            patch.object(rules, "supplier_sites", return_value=["Gwab"]),
            patch.object(
                frappe,
                "db",
                SimpleNamespace(
                    exists=lambda doctype, filters: filters["name"] == "EX001"
                ),
            ),
        ):
            EngineeringLegals.validate(doc)
        self.assertEqual(doc.expiry_date, "2026-07-31")

    def setUp(self):
        loader = patch.object(rules, "load_configuration", return_value=None)
        loader.start()
        self.addCleanup(loader.stop)

    def test_import_insert_attachment_save_keeps_server_expiry_and_duplicate_contract(
        self,
    ):
        data = {
            "site": "Gwab",
            "sections": "PDS",
            "fleet_number": "EX001",
            "vehicle_type": "TMM",
            "start_date": "2026-01-31",
            "file_name": "test.pdf",
            "file_content_base64": base64.b64encode(b"isolated attachment").decode(),
        }

        class ImportedLegal(SimpleNamespace):
            def get_doc_before_save(self):
                return getattr(self, "before", None)

            def insert(self, **kwargs):
                self.expiry_date = self.lifting_type = self.brake_wear_type = (
                    self.hsec_inserted_at
                ) = None
                EngineeringLegals.validate(self)
                self.name = "imported"
                self.before = SimpleNamespace(
                    **{
                        key: value
                        for key, value in vars(self).items()
                        if key != "before"
                    }
                )

            def save(self, **kwargs):
                EngineeringLegals.validate(self)

        with (
            patch.object(frappe.local, "form_dict", data, create=True),
            patch.object(frappe, "db", new=MagicMock()) as db,
            patch.object(
                frappe, "get_doc", side_effect=lambda fields: ImportedLegal(**fields)
            ),
            patch.object(
                imports,
                "save_file",
                return_value=frappe._dict(file_url="/files/import.pdf"),
            ),
        ):
            db.get_value.return_value = None
            db.exists.side_effect = lambda doctype, *args: (
                doctype != "Engineering Legals"
            )
            result = imports.import_legacy_legal()
            self.assertEqual(str(result["expiry_date"]), "2026-04-30")
            self.assertEqual(result["file_url"], "/files/import.pdf")
            db.exists.side_effect = lambda doctype, *args: (
                "existing" if doctype == "Engineering Legals" else True
            )
            self.assertEqual(
                imports.import_legacy_legal(),
                {"ok": 1, "skipped": 1, "reason": "duplicate", "name": "existing"},
            )

    def test_draft_rejects_posted_expiry_and_uses_configured_rules(self):
        doc = SimpleNamespace(
            **values(expiry_date="2099-01-01"),
            portal_user="supplier@example.invalid",
            get_doc_before_save=lambda: None,
        )
        with (
            patch.object(
                frappe.local,
                "session",
                SimpleNamespace(user="supplier@example.invalid"),
                create=True,
            ),
            patch.object(frappe, "get_roles", return_value=["Supplier"]),
            patch(
                "engineering.engineering.doctype.engineering_legals_supplier_portal_draft.engineering_legals_supplier_portal_draft.authorize_capture"
            ),
            patch.object(
                rules,
                "load_configuration",
                return_value=configuration(
                    section_rules=[row(expiry_unit="Days", expiry_value=10)]
                ),
            ),
        ):
            EngineeringLegalssupplierPortalDraft.validate(doc)
        self.assertEqual(str(doc.expiry_date), "2026-02-10")

    def test_draft_ownership_and_sent_state_are_enforced(self):
        for owner, before in [
            ("other@example.invalid", None),
            ("supplier@example.invalid", SimpleNamespace(sent_to_erp=1)),
        ]:
            doc = SimpleNamespace(
                portal_user=owner, get_doc_before_save=lambda before=before: before
            )
            with (
                patch.object(
                    frappe.local,
                    "session",
                    SimpleNamespace(user="supplier@example.invalid"),
                    create=True,
                ),
                patch.object(frappe, "get_roles", return_value=["Supplier"]),
                self.assertRaises(frappe.PermissionError),
            ):
                EngineeringLegalssupplierPortalDraft.validate(doc)

    def test_draft_owner_cannot_be_reassigned_to_bypass_stored_ownership(self):
        before = SimpleNamespace(portal_user="other@example.invalid", sent_to_erp=0)
        doc = SimpleNamespace(
            **values(),
            portal_user="supplier@example.invalid",
            get_doc_before_save=lambda: before,
        )
        with (
            patch.object(
                frappe.local,
                "session",
                SimpleNamespace(user="supplier@example.invalid"),
                create=True,
            ),
            patch.object(frappe, "get_roles", return_value=["Supplier"]),
            patch(
                "engineering.engineering.doctype.engineering_legals_supplier_portal_draft.engineering_legals_supplier_portal_draft.authorize_capture"
            ),
            self.assertRaises(frappe.PermissionError),
        ):
            EngineeringLegalssupplierPortalDraft.validate(doc)

    def test_hsec_exports_existing_expiry_without_recalculation(self):
        source = frappe._dict(
            name="old",
            fleet_number="EX001",
            start_date="2026-01-31",
            expiry_date="2026-07-31",
            hsec_qual_category_id="EQP",
            hsec_qualification_id_external="Brake Test",
            attach_paper="/files/old.pdf",
            modified="2026-01-31 12:00:00",
        )
        with (
            patch.object(frappe, "get_all", return_value=[source]),
            patch.object(hsec, "now_datetime", return_value="2026-10-28 12:00:00"),
            patch.object(
                hsec,
                "_file_to_base64_and_mime",
                return_value=("cGRm", "application/pdf", "old.pdf"),
            ),
        ):
            result = hsec.get_hsec_equipment_docs()
        self.assertEqual(result["data"][0]["Qualification_Date_End"], "2026-07-31")
        self.assertEqual(result["data"][0]["source_docname"], "old")

    def test_supplier_send_rejects_other_users_draft(self):
        with (
            patch.object(
                frappe.local,
                "session",
                SimpleNamespace(user="supplier@example.invalid"),
                create=True,
            ),
            patch.object(
                frappe.local, "form_dict", {"names": '["other-draft"]'}, create=True
            ),
            patch.object(frappe, "get_roles", return_value=["Supplier"]),
            patch.object(
                frappe,
                "get_doc",
                return_value=frappe._dict(portal_user="other@example.invalid"),
            ),
            patch.object(frappe, "throw", side_effect=frappe.PermissionError),
            patch.object(supplier_list, "_", side_effect=lambda message: message),
            self.assertRaises(frappe.PermissionError),
        ):
            supplier_list.send_engineering_legals()

    def test_unrelated_save_has_no_queue_or_notification_side_effect(self):
        old = SimpleNamespace(**values(expiry_date="2026-07-31"))
        doc = SimpleNamespace(
            **values(expiry_date="2026-07-31"),
            get_doc_before_save=lambda: old,
            hsec_inserted_at=None,
        )
        EngineeringLegals.validate(doc)
        self.assertEqual(doc.expiry_date, "2026-07-31")

    def test_machine_file_reads_stored_dates_and_no_expiry_without_recalculation(self):
        from engineering.engineering.doctype.machine_file import machine_file as machine

        rows = [
            frappe._dict(
                name="historic",
                sections="FRCS",
                fleet_number="EX001",
                site="Gwab",
                start_date="2026-01-31",
                expiry_date="2026-07-31",
                creation="2026-01-31",
                attach_paper="/files/old.pdf",
            ),
            frappe._dict(
                name="no-expiry",
                sections="FRCS",
                fleet_number="EX001",
                site="Gwab",
                start_date="2026-02-01",
                expiry_date=None,
                creation="2026-02-01",
                attach_paper="/files/new.pdf",
            ),
        ]
        meta = SimpleNamespace(
            is_submittable=0, fields=[SimpleNamespace(fieldname=key) for key in rows[0]]
        )
        config = {
            "section_field": "sections",
            "fleet_field": "fleet_number",
            "site_field": "site",
            "attachment_field": "attach_paper",
            "start_date_field": "start_date",
            "expiry_date_field": "expiry_date",
        }
        with (
            patch.object(machine, "_mf_engineering_legals_config", return_value=config),
            patch.object(machine.frappe, "get_meta", return_value=meta),
            patch.object(machine.frappe, "get_all", return_value=rows),
            patch.object(machine, "_mf_engineering_legals_files", return_value={}),
            patch.object(
                machine, "_mf_engineering_legal_status", return_value="ERP Records"
            ),
        ):
            result = machine._mf_get_engineering_legals("EX001", "Klipfontein", "3")
        self.assertEqual(result[0]["expiry_date"], "2026-07-31")
        self.assertEqual(result[1]["expiry_date"], "")
        self.assertEqual(result[0]["attachments"][0]["file_url"], "/files/old.pdf")
