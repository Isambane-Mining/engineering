import copy
import unittest

from engineering.engineering.page.reliability_engineering import problem_machines
from engineering.engineering.page.reliability_engineering.reliability_engineering import build_report


class ProblemMachinesTest(unittest.TestCase):
    def report(self):
        events, meters = [], []
        for i in range(1, 13):
            for day in range(1, i + 1):
                events.append(dict(name=f"B{i}-{day}", asset_name=f"A{i:02d}", location="North",
                                   breakdown_start_datetime=f"2026-08-{day:02d} 08:00:00",
                                   resolved_datetime=f"2026-08-{day:02d} 10:00:00",
                                   failure_classification="Hydraulic"))
            meters.append(dict(asset_name=f"A{i:02d}", location="North", shift_date="2026-08-01",
                               shift="Day", eng_hrs_start=100, eng_hrs_end=110))
        return build_report(events, meters, "2026-08-01", "2026-08-31")

    def test_top_limits_apply_after_fleet_scoring_and_preserve_original(self):
        report = self.report()
        before = copy.deepcopy(report)
        reference = problem_machines.build_problem_report(report, 10)["ranking"]
        for top in range(1, 11):
            result = problem_machines.build_problem_report(report, top)
            self.assertEqual(len(result["ranking"]), top)
            self.assertEqual(result["ranking"], reference[:top])
            self.assertEqual(result["ranking"][0]["asset"], "A12")
            self.assertEqual(result["ranking"][0]["problem_score"], 100)
            self.assertEqual(result["total_machines"], 12)
            self.assertEqual(result["ranking"][0]["main_problem"], "Hydraulic")
            self.assertEqual(result["ranking"][0]["main_problem_repeats"], 11)
        self.assertEqual(report, before)

    def test_zero_hours_partial_classification_and_no_data(self):
        events = [dict(name="one", asset_name="A1", location="North",
                       breakdown_start_datetime="2026-08-02 08:00:00")]
        report = build_report(events, [], "2026-08-01", "2026-08-31")
        row = problem_machines.build_problem_report(report)["ranking"][0]
        self.assertIsNone(row["score_mtbf"])
        self.assertIsNone(row["bdfr"])
        self.assertIsNone(row["repeat_rate"])
        self.assertEqual(row["score_metrics"], 2)
        self.assertEqual(row["main_problem"], "Unclassified")
        self.assertTrue(0 <= row["problem_score"] <= 100)
        empty = build_report([], [], "2026-08-01", "2026-08-31")
        self.assertEqual(problem_machines.build_problem_report(empty)["ranking"], [])

    def test_main_problem_uses_repeat_flags_not_text_matching(self):
        report = self.report()
        report["breakdowns"].append(dict(asset="A12", classification="Electrical", repeat=False))
        row = problem_machines.build_problem_report(report, 1)["ranking"][0]
        self.assertEqual(row["main_problem"], "Hydraulic")
        self.assertEqual(row["main_problem_repeats"], 11)

    def test_operating_only_machines_are_not_problem_machines(self):
        report = self.report()
        report["ranking"].append(dict(asset="healthy", breakdowns=0))
        self.assertEqual(problem_machines.build_problem_report(report)["total_machines"], 12)

    def test_unclassified_reason_fallback_does_not_create_repeats(self):
        rows = [dict(name=str(i), asset_name="A1", breakdown_start_datetime=f"2026-08-0{i} 08:00:00",
                     breakdown_reason=reason) for i, reason in enumerate(["Hose leak", " hose LEAK ", "Flat tyre"], 1)]
        report = build_report(rows, [], "2026-08-01", "2026-08-31")
        row = problem_machines.build_problem_report(report)["ranking"][0]
        self.assertEqual(row["main_problem"], "Hose leak")
        self.assertEqual(row["main_problem_events"], 2)
        self.assertEqual(row["main_problem_repeats"], 0)
        self.assertTrue(row["main_problem_unverified"])
        self.assertIsNone(row["repeat_rate"])

    def test_small_valid_meter_delta_is_not_lost_to_display_rounding(self):
        event = dict(name="one", asset_name="A1", breakdown_start_datetime="2026-08-01 08:00:00")
        meter = dict(asset_name="A1", shift_date="2026-08-01", shift="Day", eng_hrs_start=100, eng_hrs_end=100.001)
        report = build_report([event], [meter], "2026-08-01", "2026-08-31")
        row = problem_machines.build_problem_report(report)["ranking"][0]
        self.assertAlmostEqual(row["score_mtbf"], 0.001)
        self.assertGreater(row["bdfr"], 0)
        self.assertTrue(0 <= row["problem_score"] <= 100)


    def test_classified_repeat_example_uses_class_not_free_text(self):
        rows = [dict(name="B1", asset_name="A1", location="Site", failure_classification="Hydraulic",
                     breakdown_start_datetime="2026-08-01 08:00:00", resolved_datetime="2026-08-01 10:00:00",
                     breakdown_reason="Hose leak"),
                dict(name="B2", asset_name="A1", location="Site", failure_classification="Hydraulic",
                     breakdown_start_datetime="2026-08-03 08:00:00", resolved_datetime="2026-08-03 10:00:00",
                     breakdown_reason="Hydraulic line damaged")]
        meters = [dict(asset_name="A1", location="Site", shift_date="2026-08-01", shift="Day",
                       eng_hrs_start=100, eng_hrs_end=110)]
        report = build_report(rows, meters, "2026-08-01", "2026-08-31")
        row = problem_machines.build_problem_report(report)["ranking"][0]
        self.assertEqual(row["bdfr"], 200)
        self.assertEqual(row["repeat_rate"], 50)
        self.assertEqual(row["repeat_breakdowns"], 1)
        self.assertFalse(row["main_problem_unverified"])

    def test_identical_free_text_without_classification_is_not_a_repeat(self):
        rows = [dict(name=str(day), asset_name="A1", breakdown_reason="Hose leak",
                     breakdown_start_datetime=f"2026-08-{day:02d} 08:00:00") for day in (1, 3)]
        report = build_report(rows, [], "2026-08-01", "2026-08-31")
        row = problem_machines.build_problem_report(report)["ranking"][0]
        self.assertIsNone(row["repeat_rate"])
        self.assertEqual(row["repeat_breakdowns"], 0)
        self.assertTrue(row["main_problem_unverified"])


if __name__ == "__main__":
    unittest.main()
