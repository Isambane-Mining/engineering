"""Isolated tests: no site initialization, database, queue, mail or Graph access."""

import importlib
import json
from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

MODULE = "engineering.controllers.engineering_legals_rules"


def values(**changes):
    result = {
        "site": "Gwab",
        "sections": "NDT",
        "fleet_number": "EX001",
        "start_date": "2026-01-31",
        "vehicle_type": None,
        "lifting_type": None,
        "brake_wear_type": None,
        "expiry_date": None,
    }
    result.update(changes)
    return result


def row(**changes):
    result = {
        "section": "NDT",
        "active": 1,
        "vehicle_type": "",
        "lifting_type": "",
        "no_expiry": 0,
        "expiry_value": 2,
        "expiry_unit": "Months",
        "fleet_required": 1,
        "start_date_policy": "Required",
        "brake_wear_required": 0,
        "report_category": "02. Condition Monitoring",
        "counting_mode": "Active Until Expiry",
        "sharepoint_subfolder": "",
    }
    result.update(changes)
    return result


def configuration(**changes):
    result = {
        "name": "Gwab",
        "site": "Gwab",
        "enabled": 1,
        "effective_from": "2026-01-01",
        "section_rules": [row()],
        "sharepoint_site_code": "gwab",
    }
    result.update(changes)
    return result


class TestSiteRules(TestCase):
    def setUp(self):
        self.rules = importlib.import_module(MODULE)
        self.actual_loader = self.rules.load_configuration
        self.loader = patch.object(self.rules, "load_configuration", return_value=None)
        self.loader.start()
        self.addCleanup(self.loader.stop)

    def test_shared_resolver_exists(self):
        self.assertTrue(callable(getattr(self.rules, "resolve_rule", None)))

    def test_validation_errors_include_a_message_for_desk_and_portal(self):
        with patch.object(self.rules.frappe, "message_log", []):
            with self.assertRaises(self.rules.frappe.ValidationError):
                self.rules.calculate(values(sections="Unknown Section"))
            messages = self.rules.frappe.message_log
            self.assertTrue(
                any(
                    "Unknown Section" in message.get("message", "")
                    for message in messages
                )
            )

    def test_controller_preserves_historical_expiry_and_hsec_contract(self):
        from engineering.engineering.doctype.engineering_legals.engineering_legals import (
            EngineeringLegals,
        )

        old = SimpleNamespace(
            **values(sections="PDS", vehicle_type="TMM", expiry_date="2026-02-28")
        )
        doc = SimpleNamespace(
            **values(sections="PDS", vehicle_type="TMM", expiry_date="2099-01-01"),
            get_doc_before_save=lambda: old,
            hsec_inserted_at=None,
        )
        EngineeringLegals.validate(doc)
        self.assertEqual(doc.expiry_date, "2026-02-28")
        self.assertEqual(doc.hsec_send, 0)

    def test_preview_rejects_guest_and_other_supplier_assets(self):
        with (
            patch.object(
                self.rules.frappe.local,
                "session",
                SimpleNamespace(user="Guest"),
                create=True,
            ),
            self.assertRaises(self.rules.frappe.PermissionError),
        ):
            self.rules.get_capture_preview(values())
        with (
            patch.object(
                self.rules.frappe.local,
                "session",
                SimpleNamespace(user="supplier@example.invalid"),
                create=True,
            ),
            patch.object(self.rules.frappe, "get_roles", return_value=["Supplier"]),
            patch(
                "engineering.templates.pages.engineering_legals_sup._get_user_suppliers",
                return_value=["OWNER"],
            ),
            patch.object(self.rules.frappe, "db", new=MagicMock()) as db,
        ):
            db.exists.return_value = False
            with self.assertRaises(self.rules.frappe.PermissionError):
                self.rules.get_capture_preview(values())

    def test_preview_uses_server_pds_calculation_and_ignores_posted_expiry(self):
        with (
            patch.object(self.rules, "authorize_capture"),
            patch.object(self.rules, "section_options", return_value=["PDS"]),
        ):
            preview = self.rules.get_capture_preview(
                values(sections="PDS", vehicle_type="TMM", expiry_date="2099-01-01")
            )
        self.assertEqual(str(preview["expiry_date"]), "2026-04-30")

    def test_partial_preview_requires_vehicle_without_guessing_expiry(self):
        with (
            patch.object(self.rules, "authorize_capture"),
            patch.object(self.rules, "section_options", return_value=["PDS"]),
        ):
            preview = self.rules.get_capture_preview(values(sections="PDS"))
        self.assertTrue(preview["rule"]["incomplete"])
        self.assertIsNone(preview["expiry_date"])
        self.assertEqual(preview["rule"]["vehicle_options"], ["LDV", "TMM"])

    def test_read_only_user_can_preview_a_permitted_historical_document(self):
        old = SimpleNamespace(
            **values(expiry_date="2026-07-31"), check_permission=lambda permission: None
        )
        with (
            patch.object(
                self.rules.frappe.local,
                "session",
                SimpleNamespace(user="reader@example.invalid"),
                create=True,
            ),
            patch.object(
                self.rules.frappe,
                "get_roles",
                return_value=["Engineering Area Manager"],
            ),
            patch.object(self.rules.frappe, "has_permission", return_value=False),
            patch.object(self.rules.frappe, "get_doc", return_value=old),
            patch.object(self.rules, "section_options", return_value=["NDT", "FRCS"]),
        ):
            preview = self.rules.get_capture_preview(values(), docname="old")
        self.assertEqual(preview["expiry_date"], "2026-07-31")
        self.assertIn("FRCS", preview["sections"])

    def test_clearing_required_fleet_is_rejected_without_recalculating_history(self):
        old = SimpleNamespace(**values(expiry_date="2026-07-31"))
        doc = SimpleNamespace(
            **values(fleet_number=None, expiry_date="2026-07-31"),
            get_doc_before_save=lambda: old,
        )
        with self.assertRaises(self.rules.frappe.ValidationError):
            self.rules.apply_document_rules(doc)
        self.assertEqual(doc.expiry_date, "2026-07-31")

    def test_preview_uses_persisted_creation_for_undated_existing_drafts(self):
        draft = SimpleNamespace(
            **values(sections="Wearcheck", start_date=None), creation="2026-01-01"
        )
        config = configuration(
            effective_from="2026-10-01",
            section_rules=[
                row(
                    section="Service Schedule",
                    no_expiry=1,
                    expiry_value=0,
                    expiry_unit="",
                    start_date_policy="Optional",
                    counting_mode="Saved In Month",
                )
            ],
        )
        with (
            patch.object(self.rules, "authorize_capture", return_value=draft),
            patch.object(
                self.rules, "section_options", return_value=["Service Schedule"]
            ),
            patch.object(self.rules, "load_configuration", return_value=config),
            patch.object(self.rules, "nowdate", return_value="2026-10-28"),
        ):
            result = self.rules.get_capture_preview(
                values(sections="Service Schedule", start_date=None),
                draft_name="old-draft",
            )
        self.assertEqual(result["rule"]["source"], "Legacy")
        self.assertFalse(result["preserved"])

    def test_rollout_off_and_missing_table_never_load_configuration_records(self):
        with patch.object(self.rules.frappe, "conf", {}):
            self.assertIsNone(self.actual_loader("Gwab"))
        with (
            patch.object(self.rules.frappe, "conf", {self.rules.ROLLOUT_SWITCH: 1}),
            patch.object(
                self.rules.frappe,
                "db",
                new=SimpleNamespace(table_exists=lambda name: False),
            ),
        ):
            self.assertIsNone(self.actual_loader("Gwab"))

    def test_legacy_variants_and_calendar_boundaries(self):
        cases = [
            ("Brake Test", "TMM", None, "2026-02-28"),
            ("Brake Test", "LDV", None, "2026-04-30"),
            ("PDS", "TMM", None, "2026-04-30"),
            ("PDS", "LDV", None, "2026-05-31"),
            ("Lifting Equipment", None, "Inspection", "2026-04-30"),
            ("Lifting Equipment", None, "Certificate", "2027-01-31"),
            ("NDT", None, None, "2027-01-31"),
            ("Machine NDT", None, None, "2027-01-31"),
            ("Fire Suppression", None, None, "2026-04-30"),
            ("FRCS", None, None, "2026-04-30"),
            ("Illumination Baseline", None, None, "2028-01-31"),
            ("Noise Level Baseline & Measurement", None, None, "2028-01-31"),
            ("CoC for Containers, Offices, Workshops", None, None, "2026-02-28"),
            ("C-Track Inspection", None, None, "2026-02-28"),
            ("Tyre Inspection Report", None, None, "2026-02-28"),
            ("Earth Leakage Testing", None, None, "2026-04-30"),
            ("Brake Tester Calibration Certificate", None, None, "2027-01-31"),
            ("Brake Test Authorisations", None, None, "2027-01-31"),
            ("Multi-meter Calibration Certificate", None, None, "2027-01-31"),
            ("Authorised LV Person", None, None, "2027-01-31"),
            ("Pressure Vessels", None, None, "2027-01-31"),
        ]
        for section, vehicle, lifting, expected in cases:
            with self.subTest(section=section, vehicle=vehicle, lifting=lifting):
                result = self.rules.calculate(
                    values(sections=section, vehicle_type=vehicle, lifting_type=lifting)
                )
                self.assertEqual(str(result["expiry_date"]), expected)

    def test_different_site_intervals_and_units(self):
        for unit, interval, expected in [
            ("Days", 10, "2026-02-10"),
            ("Months", 2, "2026-03-31"),
            ("Years", 1, "2027-01-31"),
        ]:
            config = configuration(
                section_rules=[row(expiry_unit=unit, expiry_value=interval)]
            )
            result = self.rules.calculate(values(), configuration=config)
            self.assertEqual(str(result["expiry_date"]), expected)
        other = configuration(
            site="Klipfontein", name="Klipfontein", section_rules=[row(expiry_value=6)]
        )
        self.assertEqual(
            str(
                self.rules.calculate(values(site="Klipfontein"), configuration=other)[
                    "expiry_date"
                ]
            ),
            "2026-07-31",
        )
        leap = configuration(
            section_rules=[row(expiry_unit="Years", expiry_value=1)],
            effective_from="2020-01-01",
        )
        self.assertEqual(
            str(
                self.rules.calculate(
                    values(start_date="2024-02-29"), configuration=leap
                )["expiry_date"]
            ),
            "2025-02-28",
        )

    def test_no_expiry_and_legacy_required_fields(self):
        for section in [
            "Machine Service Records",
            "Service Schedule",
            "Wearcheck",
            "Equipment Technical Information",
            "Maintenance Inspections",
            "PDS Installation",
        ]:
            self.assertIsNone(
                self.rules.calculate(values(sections=section))["expiry_date"]
            )
        result = self.rules.calculate(
            values(sections="Brake Wear Measurements", brake_wear_type="ADT")
        )
        self.assertIsNone(result["start_date"])
        self.assertIsNone(result["expiry_date"])
        for invalid in [
            values(sections="Unknown"),
            values(sections="Brake Test"),
            values(fleet_number=None),
            values(start_date=None),
        ]:
            with self.assertRaises(self.rules.frappe.ValidationError):
                self.rules.calculate(invalid)
        self.assertEqual(
            str(
                self.rules.calculate(
                    values(sections="Pressure Vessels", fleet_number=None)
                )["expiry_date"]
            ),
            "2027-01-31",
        )

    def test_missing_inactive_duplicate_and_ambiguous_rules_rejected(self):
        configs = [
            configuration(section_rules=[row(section="FRCS")]),
            configuration(section_rules=[row(active=0), row(section="FRCS")]),
            configuration(section_rules=[row(), row()]),
            configuration(
                section_rules=[row(vehicle_type="TMM"), row(lifting_type="Inspection")]
            ),
        ]
        for config in configs:
            with (
                self.subTest(config=config),
                self.assertRaises(self.rules.frappe.ValidationError),
            ):
                self.rules.calculate(
                    values(vehicle_type="TMM", lifting_type="Inspection"),
                    configuration=config,
                )

    def test_inactive_specific_rule_does_not_fall_through(self):
        config = configuration(section_rules=[row(), row(vehicle_type="TMM", active=0)])
        with self.assertRaises(self.rules.frappe.ValidationError):
            self.rules.calculate(values(vehicle_type="TMM"), configuration=config)

    def test_disabled_and_backdated_configuration_use_legacy(self):
        for config in [
            configuration(enabled=0),
            configuration(effective_from="2026-02-01"),
        ]:
            self.assertEqual(
                str(
                    self.rules.calculate(values(), configuration=config)["expiry_date"]
                ),
                "2027-01-31",
            )

    def test_history_and_forged_provenance_preserved_on_unrelated_edit(self):
        old = SimpleNamespace(
            **values(expiry_date=date(2026, 7, 31)),
            site_configuration=None,
            expiry_rule_source=None,
            expiry_rule_snapshot=None,
        )
        doc = SimpleNamespace(
            **values(expiry_date="2099-01-01"),
            site_configuration="forged",
            expiry_rule_source="Site Configuration",
            expiry_rule_snapshot='{"no_expiry":true}',
            get_doc_before_save=lambda: old,
        )
        self.rules.apply_document_rules(doc)
        self.assertEqual(doc.expiry_date, date(2026, 7, 31))
        self.assertIsNone(doc.expiry_rule_snapshot)
        self.assertIsNone(doc.site_configuration)

    def test_changed_inputs_recalculate_and_new_snapshot_is_server_managed(self):
        old = SimpleNamespace(**values(expiry_date="2026-07-31"))
        doc = SimpleNamespace(
            **values(start_date="2026-02-01"),
            get_doc_before_save=lambda: old,
            expiry_rule_snapshot='{"no_expiry":true}',
        )
        self.rules.apply_document_rules(doc)
        self.assertEqual(str(doc.expiry_date), "2027-02-01")
        self.assertFalse(json.loads(doc.expiry_rule_snapshot)["no_expiry"])
        self.assertEqual(doc.expiry_rule_source, "Legacy")

    def test_configuration_validation_rejects_invalid_periods_and_paths(self):
        invalid_rows = [
            row(expiry_value=0),
            row(expiry_value=-1),
            row(expiry_value=1.5),
            row(expiry_unit="Hours"),
            row(sharepoint_subfolder="../escape"),
            row(no_expiry=1),
            row(start_date_policy="Optional"),
        ]
        for invalid in invalid_rows:
            with (
                self.subTest(invalid=invalid),
                self.assertRaises(self.rules.frappe.ValidationError),
            ):
                self.rules.validate_configuration(
                    configuration(section_rules=[invalid])
                )
