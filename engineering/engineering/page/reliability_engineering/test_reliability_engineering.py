"""Focused calculation tests for the reusable reliability report."""

import unittest

from engineering.engineering.page.reliability_engineering.reliability_engineering import build_report


class ReliabilityCalculationsTest(unittest.TestCase):
    def test_breakdowns_include_au_exclusions_and_invalid_repairs(self):
        breakdowns = [
            dict(name="B1", asset_name="A1", location="Site", breakdown_start_datetime="2026-08-02 08:00:00", resolved_datetime="2026-08-02 10:00:00", failure_classification="Hydraulic", exclude_from_au=1),
            dict(name="B2", asset_name="A1", location="Site", breakdown_start_datetime="2026-08-03 08:00:00", resolved_datetime="2026-08-03 07:00:00", failure_classification="Hydraulic", exclude_from_au=0),
            dict(name="B3", asset_name="A1", location="Site", breakdown_start_datetime="2026-08-04 08:00:00", resolved_datetime=None, failure_classification="Hydraulic", exclude_from_au=0),
        ]
        hours = [dict(name="H1", asset_name="A1", location="Site", shift_date="2026-08-02", shift="Day", shift_system="2x12Hour", eng_hrs_start=100, eng_hrs_end=110)]
        report = build_report(breakdowns, hours, "2026-08-01", "2026-08-31")
        self.assertEqual(report["kpis"]["breakdowns"], 3)
        self.assertEqual(report["kpis"]["mttr"], 2)
        self.assertAlmostEqual(report["kpis"]["bdfr"], 300)
        self.assertEqual(report["quality"]["invalid_repairs"], 2)
        self.assertEqual(next(row for row in report["breakdowns"] if row["name"] == "B1")["exclude_from_au"], 1)

    def test_coverage_gates_repeat_rate_and_uses_lookback(self):
        base = dict(asset_name="A1", location="Site", resolved_datetime=None, exclude_from_au=0)
        breakdowns = [
            dict(base, name="prior", breakdown_start_datetime="2026-07-30 08:00:00", failure_classification="Electrical"),
            dict(base, name="in1", breakdown_start_datetime="2026-08-02 08:00:00", failure_classification="Electrical"),
            dict(base, name="in2", breakdown_start_datetime="2026-08-04 08:00:00", failure_classification=None),
        ]
        report = build_report(breakdowns, [], "2026-08-01", "2026-08-31")
        self.assertEqual(report["kpis"]["classification_coverage"], 50)
        self.assertIsNone(report["kpis"]["repeat_rate"])
        self.assertEqual(next(row for row in report["breakdowns"] if row["name"] == "in1")["repeat"], True)
        breakdowns[2]["failure_classification"] = "Mechanical"
        report = build_report(breakdowns, [], "2026-08-01", "2026-08-31")
        self.assertEqual(report["kpis"]["repeat_rate"], 50)

    def test_invalid_meter_and_conflicting_duplicate_shift_are_excluded(self):
        def row(name, start, end, shift="Day", system="2x12Hour"):
            return dict(name=name, asset_name="A1", location="Site", shift_date="2026-08-02", shift=shift, shift_system=system, eng_hrs_start=start, eng_hrs_end=end)
        hours = [row("valid", 10, 18), row("duplicate", 10, 18), row("bad_negative", 20, 19, "Night"), row("too_long", 10, 19, "Morning", "3x8Hour")]
        report = build_report([], hours, "2026-08-01", "2026-08-31")
        self.assertEqual(report["kpis"]["operating_hours"], 8)
        self.assertEqual(report["quality"]["invalid_meter_rows"], 2)
        hours[1]["eng_hrs_end"] = 17
        report = build_report([], hours, "2026-08-01", "2026-08-31")
        self.assertEqual(report["kpis"]["operating_hours"], 0)
        self.assertEqual(report["quality"]["conflicting_hour_groups"], 1)

    def test_repeat_requires_same_machine_class_and_seven_day_window(self):
        def event(name, asset, classification, day):
            return dict(name=name, asset_name=asset, location="Site", breakdown_start_datetime=f"2026-08-{day:02d} 08:00:00", failure_classification=classification)
        rows = [event("first", "A1", "Hydraulic", 1), event("different_class", "A1", "Electrical", 2),
                event("different_machine", "A2", "Hydraulic", 2), event("repeat", "A1", "Hydraulic", 8),
                event("too_late", "A1", "Hydraulic", 16)]
        report = build_report(rows, [], "2026-08-01", "2026-08-31")
        by_name = {row["name"]: row for row in report["breakdowns"]}
        self.assertEqual({name for name, row in by_name.items() if row["repeat"]}, {"repeat"})
        self.assertEqual(by_name["repeat"]["days_since_previous"], 7)
        self.assertEqual(report["kpis"]["repeat_rate"], 20)
        self.assertIsNone(report["kpis"]["bdfr"])

    def test_date_location_asset_filters_and_empty_period(self):
        rows = [dict(name="a", asset_name="A1", location="North", breakdown_start_datetime="2026-08-02 08:00:00", failure_classification="Hydraulic"),
                dict(name="b", asset_name="A2", location="North", breakdown_start_datetime="2026-08-03 08:00:00", failure_classification="Hydraulic"),
                dict(name="c", asset_name="A1", location="South", breakdown_start_datetime="2026-08-04 08:00:00", failure_classification="Hydraulic")]
        report = build_report(rows, [], "2026-08-02", "2026-08-03", location="North", asset="A1")
        self.assertEqual(report["kpis"]["breakdowns"], 1)
        self.assertEqual([row["name"] for row in report["breakdowns"]], ["a"])
        empty = build_report(rows, [], "2026-10-01", "2026-10-31")
        self.assertEqual(empty["kpis"]["breakdowns"], 0)
        self.assertIsNone(empty["kpis"]["mtbf"])
        self.assertIsNone(empty["kpis"]["repeat_rate"])

    def test_missing_start_uses_creation_for_failure_date_but_not_mttr(self):
        row = dict(name="missing-start", creation="2026-08-02 12:00:00", asset_name="A1",
                   location="Site", breakdown_start_datetime=None, resolved_datetime="2026-08-03 12:00:00",
                   failure_classification="Hydraulic")
        report = build_report([row], [], "2026-08-01", "2026-08-31")
        self.assertEqual(report["kpis"]["breakdowns"], 1)
        self.assertIsNone(report["kpis"]["mttr"])
        self.assertEqual(report["quality"]["invalid_start_times"], 1)


if __name__ == "__main__":
    unittest.main()
