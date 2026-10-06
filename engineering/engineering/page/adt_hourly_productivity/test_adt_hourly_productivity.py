from datetime import datetime, time
from unittest import TestCase

from engineering.engineering.page.adt_hourly_productivity import adt_hourly_productivity as report


class TestADTHourlyProductivity(TestCase):
    def setUp(self):
        self.assets = [{"name": "ADT04", "asset_name": "ADT04"}, {"name": "ADT05", "asset_name": "ADT05"}]

    def build(self, shift="Day", breakdowns=(), production=()):
        return report.build_report("2026-09-28", shift, "Koppie", self.assets, breakdowns, production)

    def excavator_row(self, hour, excavator="EX019", first=None, last=None, **values):
        return {
            "hour_slot": hour,
            "asset_name_shoval": excavator,
            "excavator_plant_no": excavator,
            "asset_name_truck": "ADT04",
            "loads": 0,
            "exc_start_load_time": first,
            "exc_end_load_time": last,
            **values,
        }

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

    def test_first_and_last_events_appear_once_in_actual_hour(self):
        production = [
            self.excavator_row("06:00-07:00", first="06:23:00", last="17:14:00"),
            self.excavator_row("07:00-08:00", first="06:23:00", last="17:14:00"),
        ]
        data = self.build(production=production)
        self.assertEqual(data["excavators"], [{
            "excavator": "EX019", "first_load_time": "06:23",
            "first_load_hour": "06:00–07:00", "last_load_time": "17:14",
            "last_load_hour": "17:00–18:00",
        }])
        self.assertEqual(data["hours"][0]["first_load_events"], [{"excavator": "EX019", "time": "06:23"}])
        self.assertEqual(data["hours"][11]["last_load_events"], [{"excavator": "EX019", "time": "17:14"}])
        self.assertEqual(sum(len(h["first_load_events"]) for h in data["hours"]), 1)
        self.assertEqual(sum(len(h["last_load_events"]) for h in data["hours"]), 1)

    def test_multiple_excavators_can_share_first_and_last_buckets(self):
        production = [
            self.excavator_row("06:00-07:00", "EX021", "06:41", "17:32"),
            self.excavator_row("06:00-07:00", "EX019", "06:23", "17:14"),
        ]
        data = self.build(production=production)
        self.assertEqual([e["excavator"] for e in data["hours"][0]["first_load_events"]], ["EX019", "EX021"])
        self.assertEqual([e["excavator"] for e in data["hours"][11]["last_load_events"]], ["EX019", "EX021"])

    def test_night_event_after_midnight_uses_following_calendar_day(self):
        data = self.build("Night", production=[self.excavator_row(
            "18:00-19:00", first=time(19, 10), last=time(2, 15)
        )])
        self.assertEqual(data["excavators"][0]["first_load_hour"], "19:00–20:00")
        self.assertEqual(data["excavators"][0]["last_load_hour"], "02:00–03:00")
        self.assertEqual(data["hours"][8]["start"], "2026-09-29 02:00:00")
        self.assertEqual(data["hours"][8]["last_load_events"], [{"excavator": "EX019", "time": "02:15"}])

    def test_missing_first_or_last_load_remains_blank(self):
        production = [
            self.excavator_row("06:00-07:00", "EX019", last="17:14"),
            self.excavator_row("06:00-07:00", "EX021", first="06:41"),
        ]
        data = self.build(production=production)
        by_excavator = {row["excavator"]: row for row in data["excavators"]}
        self.assertIsNone(by_excavator["EX019"]["first_load_time"])
        self.assertIsNone(by_excavator["EX021"]["last_load_time"])
        self.assertEqual(sum(len(h["first_load_events"]) for h in data["hours"]), 1)
        self.assertEqual(sum(len(h["last_load_events"]) for h in data["hours"]), 1)

    def test_latest_hourly_record_wins_conflicting_nonblank_values(self):
        production = [
            self.excavator_row("10:00-11:00", first="06:44", last="16:58"),
            self.excavator_row("06:00-07:00", first="06:23", last="17:14"),
            self.excavator_row("11:00-12:00"),  # Blank copy must not erase a recorded event.
        ]
        data = self.build(production=production)
        self.assertEqual(len(data["excavators"]), 1)
        self.assertEqual(data["excavators"][0]["first_load_time"], "06:44")
        self.assertEqual(data["excavators"][0]["last_load_time"], "16:58")
        self.assertEqual(data["hours"][0]["first_load_events"], [{"excavator": "EX019", "time": "06:44"}])
        self.assertEqual(data["hours"][10]["last_load_events"], [{"excavator": "EX019", "time": "16:58"}])

    def test_same_hour_conflict_uses_latest_modified_record_deterministically(self):
        production = [
            self.excavator_row("06:00-07:00", first="06:35", hp_name="second",
                               hp_modified="2026-09-28 09:00:00"),
            self.excavator_row("06:00-07:00", first="06:23", hp_name="first",
                               hp_modified="2026-09-28 08:00:00"),
        ]
        self.assertEqual(self.build(production=production)["excavators"][0]["first_load_time"], "06:35")

    def test_excavator_events_do_not_change_adt_metrics(self):
        production = [self.excavator_row("06:00-07:00", first="06:23", last="17:14", loads=15)]
        data = self.build(production=production)
        self.assertEqual(data["hours"][0]["available"], 2)
        self.assertEqual(data["hours"][0]["utilised"], 1)
        self.assertEqual(data["hours"][0]["loads"], 15)
        self.assertEqual(data["summary"]["total_loads"], 15)

    def test_pdf_contains_excavator_first_last_section(self):
        data = self.build(production=[self.excavator_row("06:00-07:00", first="06:23", last="17:14")])
        html = report.build_pdf_html(data)
        self.assertIn("Excavator First / Last Load Performance", html)
        self.assertIn("EX019", html)
        self.assertIn("06:23", html)
        self.assertIn("17:14", html)
