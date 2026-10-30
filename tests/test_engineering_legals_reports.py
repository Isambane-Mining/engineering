"""Exercise report and SharePoint selection without a configured Frappe site."""

import json
from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe

from engineering.controllers import engineering_legals_rules as rules
from engineering.engineering.doctype.engineering_legals import (
    engineering_legals as legals,
)
from engineering.engineering.doctype.engineering_legals import (
    sharepoint_monthly_frequency as sync,
)
from engineering.engineering.report.engineering_legals_monthly_summary import (
    engineering_legals_monthly_summary as monthly,
)
from engineering.engineering.report.engineering_legals_report import (
    engineering_legals_report as expiry_report,
)
from engineering.engineering.report.engineering_legals_report import (
    fetch_second_table as drilldown,
)
from engineering.templates.pages import (
    engineering_legals_supplier_report as supplier_report,
)


def record(name="historic", **changes):
    result = frappe._dict(
        name=name,
        site="Gwab",
        sections="NDT",
        start_date="2026-01-01",
        expiry_date="2026-12-31",
        creation="2026-01-01",
        vehicle_type=None,
        fleet_number="EX001",
        asset_category="Excavator",
    )
    result.update(changes)
    return result


def snapshot(**changes):
    result = {
        "version": 1,
        "source": "Site Configuration",
        "report_category": "02. Condition Monitoring",
        "counting_mode": "Active Until Expiry",
        "no_expiry": 0,
        "sharepoint_site_code": "gwab",
        "sharepoint_subfolder": "",
    }
    result.update(changes)
    return json.dumps(result)


class TestReportCompatibility(TestCase):
    def test_configured_service_history_merges_legal_and_mechanical_records_before_paging(
        self,
    ):
        legal = record(
            "configured", sections="Machine Service Records", start_date="2026-02-03"
        )
        msr = frappe._dict(
            name="mechanical",
            service_date="2026-02-01",
            modified="2026-02-01",
            attach="/files/service.pdf",
        )

        def read(doctype, **kwargs):
            return [legal] if doctype == "Engineering Legals" else [msr]

        with (
            patch.object(drilldown.frappe, "get_all", side_effect=read),
            patch.object(
                drilldown,
                "optional_snapshot_fields",
                return_value=["expiry_rule_snapshot"],
            ),
            patch.object(
                drilldown, "_get_asset_site_map", return_value={"EX001": "Gwab"}
            ),
        ):
            first = drilldown.get_doc_history_docs(
                "Gwab", "Machine Service Records", "EX001", limit=1
            )
            second = drilldown.get_doc_history_docs(
                "Gwab", "Machine Service Records", "EX001", limit=1, offset=1
            )
        self.assertEqual([r["name"] for r in first["rows"]], ["configured"])
        self.assertEqual(
            first["rows"][0]["record_url"], "/app/engineering-legals/configured"
        )
        self.assertEqual([r["name"] for r in second["rows"]], ["mechanical"])
        self.assertEqual(
            second["rows"][0]["record_url"], "/app/mechanical-service-report/mechanical"
        )

    def test_service_history_tree_excludes_unrelated_legal_sections(self):
        legal = record("configured", sections="Machine Service Records")
        unrelated = record("ndt")

        def read(doctype, filters, **kwargs):
            if doctype != "Engineering Legals":
                return []
            rows = [legal, unrelated]
            for field, operator, operand in filters:
                if field == "sections" and operator == "=":
                    rows = [r for r in rows if r.sections == operand]
            return rows

        with (
            patch.object(drilldown.frappe, "get_all", side_effect=read),
            patch.object(
                drilldown, "_get_asset_site_map", return_value={"EX001": "Gwab"}
            ),
        ):
            tree = drilldown.get_doc_history_tree_meta(
                "Gwab", "Machine Service Records"
            )["tree"]
        self.assertEqual(
            [r["label"] for r in tree[0]["children"]], ["Machine Service Records"]
        )

    def report(self, rows):
        with (
            patch.object(monthly, "get_legal_records", return_value=rows),
            patch.object(monthly, "get_submitted_plant_counts", return_value={}),
            patch.object(monthly, "build_machine_plant_list_html", return_value=""),
            patch.object(monthly, "_", side_effect=lambda s: s),
        ):
            return monthly.execute({"site": "Gwab", "month": "Feb", "year": 2026})

    def test_legacy_report_contract_and_saved_month(self):
        result = self.report(
            [record(), record("pds", sections="PDS", vehicle_type="TMM")]
        )
        self.assertEqual(len(result), 5)
        rows = result[1]
        self.assertEqual(len(rows), 11)
        self.assertEqual(json.loads(rows[1]["record_names_json"]), ["historic"])
        self.assertEqual(rows[8]["completed"], 0)
        self.assertEqual(rows[-1]["completed"], 1)

    def test_recorded_category_and_counting_mode_override_section_defaults(self):
        rows = self.report(
            [
                record(
                    "custom", sections="Custom Legal", expiry_rule_snapshot=snapshot()
                ),
                record(
                    "pds",
                    sections="PDS",
                    expiry_rule_snapshot=snapshot(
                        report_category="09. PDS-MPI Maintenance"
                    ),
                ),
            ]
        )[1]
        self.assertEqual(json.loads(rows[1]["record_names_json"]), ["custom"])
        self.assertEqual(json.loads(rows[8]["record_names_json"]), ["pds"])

    def test_no_expiry_saved_month_and_other_category(self):
        rows = self.report(
            [
                record(
                    "other",
                    sections="Custom Legal",
                    start_date="2026-02-01",
                    expiry_date=None,
                    expiry_rule_snapshot=snapshot(
                        report_category="Other",
                        counting_mode="Saved In Month",
                        no_expiry=1,
                    ),
                )
            ]
        )[1]
        other = next(row for row in rows if row["category"] == "Other")
        self.assertEqual(json.loads(other["record_names_json"]), ["other"])
        self.assertEqual(rows[-1]["completed"], 1)

    def test_legacy_sharepoint_routes_remain_unchanged(self):
        self.assertEqual(
            legals._get_new_sharepoint_folder_parts(record()),
            ["Isambane Mining", "01.Jan-26", "gwab", "02. Condition Monitoring"],
        )
        self.assertEqual(
            legals._get_new_sharepoint_folder_parts(record(sections="PDS")),
            ["Isambane Mining", "01.Jan-26", "gwab", "09. PDS-MPI Maintenance"],
        )

    def test_recorded_routing_survives_disabled_rollout(self):
        doc = record(
            site="Koppie",
            sections="Custom Legal",
            expiry_rule_snapshot=snapshot(
                sharepoint_site_code="koppie",
                report_category="Other",
                sharepoint_subfolder="Certificates",
            ),
        )
        self.assertEqual(
            legals._get_new_sharepoint_folder_parts(doc),
            ["Isambane Mining", "01.Jan-26", "koppie", "Other", "Certificates"],
        )

    def test_monthly_sharepoint_plan_matches_selected_record_names_without_credentials(
        self,
    ):
        doc = record("custom", expiry_rule_snapshot=snapshot())
        report_result = self.report([doc])
        with (
            patch.object(
                sync, "get_sharepoint_site_mapping", return_value={"Gwab": "gwab"}
            ),
            patch.object(sync, "execute_monthly_summary", return_value=report_result),
            patch.object(sync.frappe, "get_doc", return_value=doc),
            patch.object(
                sync,
                "_get_attachment_file",
                return_value=frappe._dict(file_name="ndt.pdf"),
            ),
        ):
            result = sync.sync_active_legals_for_month(2026, 2, dry_run=True)
        self.assertEqual(result["selected"], 1)
        self.assertEqual(result["planned"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["details"][0]["name"], "custom")

    def test_snapshot_supports_expiring_legacy_no_expiry_section(self):
        doc = record(sections="Service Schedule", expiry_rule_snapshot=snapshot())
        self.assertFalse(rules.skip_no_expiry_section(doc, ("Service Schedule",)))
        self.assertTrue(
            rules.skip_no_expiry_section(
                record(sections="Service Schedule"), ("Service Schedule",)
            )
        )

    def test_new_no_expiry_policy_supersedes_older_expiring_status_only(self):
        old = record(expiry_date="2026-12-31")
        newer = record(
            "no-expiry",
            start_date="2026-02-01",
            expiry_date=None,
            expiry_rule_snapshot=snapshot(no_expiry=1, counting_mode="Saved In Month"),
        )
        result = rules.apply_no_expiry_overrides([old, newer])
        self.assertEqual([r.name for r in result], ["no-expiry"])
        self.assertEqual(old.expiry_date, "2026-12-31")

    def test_blank_configured_subfolder_preserves_existing_tyre_route(self):
        from test_engineering_legals_site_rules import configuration, row, values

        config = configuration(
            section_rules=[
                row(
                    section="Tyre Inspection Report",
                    report_category="08. Maintenance Schedules",
                )
            ]
        )
        result = rules.calculate(
            values(sections="Tyre Inspection Report"), configuration=config
        )
        self.assertEqual(result["rule"]["sharepoint_subfolder"], "Tyre Surveys")

    def test_expiring_service_records_appear_in_summary_and_category_drilldown(self):
        doc = record(
            sections="Machine Service Records",
            expiry_date="2026-02-05",
            expiry_rule_snapshot=snapshot(),
        )
        with (
            patch.object(expiry_report.frappe, "get_all", return_value=[doc]),
            patch.object(
                expiry_report,
                "optional_snapshot_fields",
                return_value=["expiry_rule_snapshot"],
            ),
            patch.object(
                expiry_report, "_get_asset_site_map", return_value={"EX001": "Gwab"}
            ),
        ):
            result = expiry_report._summary_view(date(2026, 2, 1), "Gwab", None, None)
        self.assertEqual(result[1][0]["d0_7"], 1)

        def read(doctype, **kwargs):
            return ["EX001"] if doctype == "Asset" else [doc]

        with (
            patch.object(drilldown.frappe, "get_all", side_effect=read),
            patch.object(
                drilldown,
                "optional_snapshot_fields",
                return_value=["expiry_rule_snapshot"],
            ),
            patch.object(drilldown, "_get_asset_site_field", return_value="location"),
            patch.object(
                drilldown, "_get_asset_site_map", return_value={"EX001": "Gwab"}
            ),
            patch.object(drilldown, "_get_service_msr_rows", return_value=[]),
            patch.object(drilldown, "today", return_value="2026-02-01"),
        ):
            result = drilldown.get_category_summary(
                "Gwab", "Excavator", "Machine Service Records"
            )
        self.assertEqual(result["rows"][0]["name"], "historic")

    def test_supplier_summary_retains_asset_scope(self):
        owned = record("owned-doc", fleet_number="owned", expiry_date="2026-02-05")
        other = record("other-doc", fleet_number="other", expiry_date="2026-02-05")

        def read(doctype, filters, **kwargs):
            permitted = next(
                (f[2] for f in filters if f[:2] == ["fleet_number", "in"]),
                ["owned", "other"],
            )
            return [doc for doc in (owned, other) if doc.fleet_number in permitted]

        with (
            patch.object(supplier_report.frappe, "get_all", side_effect=read),
            patch.object(supplier_report, "optional_snapshot_fields", return_value=[]),
            patch.object(supplier_report, "today", return_value="2026-02-01"),
        ):
            rows = supplier_report._get_summary_rows(["owned"], {})
        self.assertEqual(
            [asset["name"] for row in rows for asset in row["assets"]], ["owned-doc"]
        )

    def test_expiry_filters_cannot_revive_an_alert_superseded_by_no_expiry(self):
        docs = [
            record(expiry_date="2026-02-05"),
            record(
                "no-expiry",
                start_date="2026-02-01",
                expiry_date=None,
                expiry_rule_snapshot=snapshot(
                    no_expiry=1, counting_mode="Saved In Month"
                ),
            ),
        ]

        def read(doctype, filters, **kwargs):
            rows = list(docs)
            for field, operator, operand in filters:
                if field != "expiry_date":
                    continue
                rows = [
                    doc
                    for doc in rows
                    if doc.expiry_date
                    and (
                        str(doc.expiry_date) >= str(operand)
                        if operator == ">="
                        else str(doc.expiry_date) <= str(operand)
                    )
                ]
            return rows

        with (
            patch.object(expiry_report.frappe, "get_all", side_effect=read),
            patch.object(
                expiry_report,
                "optional_snapshot_fields",
                return_value=["expiry_rule_snapshot"],
            ),
            patch.object(
                expiry_report, "_get_asset_site_map", return_value={"EX001": "Gwab"}
            ),
        ):
            result = expiry_report._summary_view(
                date(2026, 2, 1),
                "Gwab",
                None,
                None,
                date(2026, 2, 1),
                date(2026, 2, 28),
            )
        self.assertEqual(result[1], [])
        with (
            patch.object(supplier_report.frappe, "get_all", side_effect=read),
            patch.object(
                supplier_report,
                "optional_snapshot_fields",
                return_value=["expiry_rule_snapshot"],
            ),
            patch.object(supplier_report, "today", return_value="2026-02-01"),
        ):
            rows = supplier_report._get_summary_rows(
                ["EX001"],
                {"from_expiry_date": "2026-02-01", "to_expiry_date": "2026-02-28"},
            )
        self.assertEqual(rows, [])
