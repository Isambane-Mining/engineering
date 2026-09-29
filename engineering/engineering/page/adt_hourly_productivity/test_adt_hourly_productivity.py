from datetime import datetime
from unittest import TestCase

from engineering.engineering.page.adt_hourly_productivity import adt_hourly_productivity as report


class TestADTHourlyProductivity(TestCase):
    def setUp(self):
        self.assets = [{"name": "ADT04", "asset_name": "ADT04"}, {"name": "ADT05", "asset_name": "ADT05"}]

    def build(self, shift="Day", breakdowns=(), production=()):
        return report.build_report("2026-09-28", shift, "Koppie", self.assets, breakdowns, production)

    def test_day_shift_has_twelve_hourly_buckets(self):
        rows = self.build()["hours"]
        self.assertEqual(len(rows), 12)
        self.assertEqual((rows[0]["label"], rows[-1]["label"]), ("06:00–07:00", "17:00–18:00"))

    def test_night_shift_crosses_midnight(self):
        rows = self.build("Night")["hours"]
        self.assertEqual((rows[0]["label"], rows[6]["label"], rows[-1]["label"]),
                         ("18:00–19:00", "00:00–01:00", "05:00–06:00"))
        self.assertEqual(rows[6]["start"], "2026-09-29 00:00:00")

    def test_current_shift_defaults_before_six_to_previous_date(self):
        self.assertEqual(report.current_shift(datetime(2026, 9, 29, 2)),
                         {"date": "2026-09-28", "shift": "Night"})
        self.assertEqual(report.current_shift(datetime(2026, 9, 29, 6)),
                         {"date": "2026-09-29", "shift": "Day"})
        self.assertEqual(report.current_shift(datetime(2026, 9, 29, 18)),
                         {"date": "2026-09-29", "shift": "Night"})

    def test_full_availability_and_no_production(self):
        data = self.build()
        self.assertEqual(data["hours"][0]["available"], 2)
        self.assertEqual(data["hours"][0]["utilised"], 0)
        self.assertEqual(data["summary"]["average_available"], 2)

    def test_twenty_available_minutes_and_partial_status(self):
        breakdowns = [{"asset_name": "ADT04", "breakdown_start_datetime": "2026-09-28 06:00:00",
                       "resolved_datetime": "2026-09-28 06:40:00"}]
        data = self.build(breakdowns=breakdowns)
        self.assertAlmostEqual(data["hours"][0]["available"], 1.3333333)
        detail = data["details"][0]
        self.assertAlmostEqual(detail["available_minutes"], 20)
        self.assertEqual(detail["availability_status"], "partial")

    def test_breakdown_spans_buckets_and_starts_ends_within_hour(self):
        breakdowns = [{"asset_name": "ADT04", "breakdown_start_datetime": "2026-09-28 06:20:00",
                       "resolved_datetime": "2026-09-28 08:40:00"}]
        rows = self.build(breakdowns=breakdowns)["hours"]
        self.assertAlmostEqual(rows[0]["available"], 1 + 20 / 60)
        self.assertEqual(rows[1]["available"], 1)
        self.assertAlmostEqual(rows[2]["available"], 1 + 20 / 60)

    def test_overlapping_breakdowns_do_not_double_count(self):
        breakdowns = [
            {"asset_name": "ADT04", "breakdown_start_datetime": "2026-09-28 06:00:00",
             "resolved_datetime": "2026-09-28 06:40:00"},
            {"asset_name": "ADT04", "breakdown_start_datetime": "2026-09-28 06:20:00",
             "resolved_datetime": "2026-09-28 07:00:00"},
        ]
        self.assertEqual(self.build(breakdowns=breakdowns)["hours"][0]["available"], 1)

    def test_loads_are_summed_but_utilisation_is_unique_per_adt(self):
        production = [
            {"hour_slot": "6:00-7:00", "asset_name_truck": "ADT04", "loads": 15},
            {"hour_slot": "06:00-07:00", "asset_name_truck": "ADT04", "loads": 2},
            {"hour_slot": "06:00-07:00", "asset_name_truck": "ADT05", "loads": 1},
        ]
        data = self.build(production=production)
        self.assertEqual(data["hours"][0]["loads"], 18)
        self.assertEqual(data["hours"][0]["utilised"], 2)
        self.assertEqual(data["summary"]["adts_utilised"], 2)

    def test_other_site_assets_and_loads_are_excluded(self):
        assets = self.assets + [{"name": "ADT99", "asset_name": "ADT99", "location": "Gwab"}]
        production = [{"hour_slot": "06:00-07:00", "asset_name_truck": "ADT99", "loads": 9}]
        data = report.build_report("2026-09-28", "Day", "Koppie", assets, [], production)
        self.assertEqual(data["summary"]["adts_at_site"], 2)
        self.assertEqual(data["hours"][0]["loads"], 0)

    def test_night_production_after_midnight_uses_shift_date(self):
        production = [{"hour_slot": "0:00-1:00", "asset_name_truck": "ADT04", "loads": 1}]
        self.assertEqual(self.build("Night", production=production)["hours"][6]["utilised"], 1)


    def test_pdf_contains_detail_and_summary_definition(self):
        html = report.build_pdf_html(self.build())
        self.assertIn("ADT hourly productivity", html)
        self.assertIn("ADT04", html)
        self.assertIn("Average available = sum of twelve", html)
