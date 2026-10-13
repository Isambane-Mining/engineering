from datetime import datetime, time
from unittest import TestCase

from engineering.engineering.page.adt_hourly_productivity import adt_hourly_productivity as report


class TestADTHourlyProductivity(TestCase):
    def setUp(self):
        self.assets = [{"name": "ADT04", "asset_name": "ADT04"}, {"name": "ADT05", "asset_name": "ADT05"}]

    def build(self, shift="Day", breakdowns=(), production=(), excavators=(), planned_adts=(), tub_factors=()):
        return report.build_report("2026-09-28", shift, "Koppie", self.assets, breakdowns, production,
                                   excavators, planned_adts, tub_factors)

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

    def test_earliest_start_and_latest_end_win_across_operational_shift(self):
        production = [
            self.excavator_row("10:00-11:00", first="10:25", last="16:55"),
            self.excavator_row("06:00-07:00", first="06:18", last="09:40"),
            self.excavator_row("11:00-12:00"),  # Blank copy must not erase a recorded event.
        ]
        data = self.build(production=production)
        self.assertEqual(len(data["excavators"]), 1)
        self.assertEqual(data["excavators"][0]["first_load_time"], "06:18")
        self.assertEqual(data["excavators"][0]["last_load_time"], "16:55")
        self.assertEqual(data["hours"][0]["first_load_events"], [{"excavator": "EX019", "time": "06:18"}])
        self.assertEqual(data["hours"][10]["last_load_events"], [{"excavator": "EX019", "time": "16:55"}])
        self.assertEqual(sum(len(h["first_load_events"]) for h in data["hours"]), 1)
        self.assertEqual(sum(len(h["last_load_events"]) for h in data["hours"]), 1)

    def test_same_hour_times_ignore_record_modified_order(self):
        production = [
            self.excavator_row("06:00-07:00", first="06:35", hp_name="second",
                               last="06:45", hp_modified="2026-09-28 09:00:00"),
            self.excavator_row("06:00-07:00", first="06:23", hp_name="first",
                               last="06:50", hp_modified="2026-09-28 08:00:00"),
        ]
        event = self.build(production=production)["excavators"][0]
        self.assertEqual(event["first_load_time"], "06:23")
        self.assertEqual(event["last_load_time"], "06:50")

    def test_breakdown_restart_keeps_original_start_and_final_end(self):
        production = [
            self.excavator_row("06:00-07:00", first="06:18", last="09:40"),
            self.excavator_row("10:00-11:00", first="10:25", last="16:55"),
        ]
        breakdowns = [{"asset_name": "EX019", "breakdown_start_datetime": "2026-09-28 09:45:00",
                       "resolved_datetime": "2026-09-28 10:20:00"}]
        data = self.build(production=production, breakdowns=breakdowns,
                          excavators=[{"name": "EX019", "asset_name": "EX019"}])
        event = data["excavators"][0]
        self.assertEqual((event["first_load_time"], event["last_load_time"]), ("06:18", "16:55"))
        self.assertAlmostEqual(data["hours"][3]["excavator_available"], 45 / 60)
        self.assertAlmostEqual(data["hours"][4]["excavator_available"], 40 / 60)

    def test_night_events_order_across_midnight_and_ignore_out_of_shift_times(self):
        production = [
            self.excavator_row("18:00-19:00", first="18:42", last="23:41"),
            self.excavator_row("00:00-01:00", first="00:15", last="02:15"),
            self.excavator_row("02:00-03:00", first="00:15", last="23:41"),
            self.excavator_row("03:00-04:00", first="17:30", last="06:30"),
        ]
        data = self.build("Night", production=production)
        self.assertEqual(data["excavators"][0]["first_load_time"], "18:42")
        self.assertEqual(data["excavators"][0]["last_load_time"], "02:15")
        self.assertEqual(data["hours"][0]["first_load_events"], [{"excavator": "EX019", "time": "18:42"}])
        self.assertEqual(data["hours"][8]["last_load_events"], [{"excavator": "EX019", "time": "02:15"}])
        self.assertEqual(sum(len(h["first_load_events"]) for h in data["hours"]), 1)
        self.assertEqual(sum(len(h["last_load_events"]) for h in data["hours"]), 1)

    def test_multiple_excavators_keep_independent_shift_extrema(self):
        production = [
            self.excavator_row("06:00-07:00", "EX019", first="06:18", last="09:40"),
            self.excavator_row("07:00-08:00", "EX021", first="07:12", last="15:20"),
            self.excavator_row("10:00-11:00", "EX019", first="10:25", last="16:55"),
            self.excavator_row("11:00-12:00", "EX021", first="11:10", last="14:05"),
        ]
        events = {row["excavator"]: row for row in self.build(production=production)["excavators"]}
        self.assertEqual((events["EX019"]["first_load_time"], events["EX019"]["last_load_time"]),
                         ("06:18", "16:55"))
        self.assertEqual((events["EX021"]["first_load_time"], events["EX021"]["last_load_time"]),
                         ("07:12", "15:20"))

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

    def test_excavator_full_and_twenty_minute_availability_across_buckets(self):
        excavators = [{"name": "EX019", "asset_name": "EX019", "location": "Koppie"}]
        breakdowns = [{"asset_name": "EX019", "breakdown_start_datetime": "2026-09-28 06:40:00",
                       "resolved_datetime": "2026-09-28 07:40:00"}]
        hours = self.build(breakdowns=breakdowns, excavators=excavators)["hours"]
        self.assertAlmostEqual(hours[0]["excavator_available"], 40 / 60)
        self.assertAlmostEqual(hours[1]["excavator_available"], 20 / 60)
        self.assertEqual(hours[2]["excavator_available"], 1)

    def test_excavator_utilisation_is_unique_and_requires_positive_loads(self):
        excavators = [{"name": "EX019", "location": "Koppie"}, {"name": "EX021", "location": "Koppie"}]
        production = [self.excavator_row("06:00-07:00", "EX019", loads=1),
                      self.excavator_row("06:00-07:00", "EX019", loads=3),
                      self.excavator_row("06:00-07:00", "EX021", loads=1),
                      self.excavator_row("07:00-08:00", "EX021", loads=0)]
        hours = self.build(production=production, excavators=excavators)["hours"]
        self.assertEqual(hours[0]["excavator_utilised"], 2)
        self.assertEqual(hours[1]["excavator_utilised"], 0)

    def test_other_site_excavators_are_not_counted(self):
        excavators = [{"name": "EX019", "location": "Koppie"}, {"name": "EX099", "location": "Gwab"}]
        production = [self.excavator_row("06:00-07:00", "EX099", loads=2)]
        hour = self.build(production=production, excavators=excavators)["hours"][0]
        self.assertEqual(hour["excavator_available"], 1)
        self.assertEqual(hour["excavator_utilised"], 0)

    def test_night_excavator_utilisation_after_midnight(self):
        production = [self.excavator_row("02:00-03:00", "EX019", loads=1)]
        hour = self.build("Night", production=production, excavators=[{"name": "EX019"}])["hours"][8]
        self.assertEqual(hour["excavator_utilised"], 1)
        self.assertEqual(hour["start"], "2026-09-29 02:00:00")

    def test_target_bcm_windows_average_model_factors_and_exclude_spares(self):
        planned = [{"name": "ADT04", "item_name": "Model A"}, {"name": "ADT05", "item_name": "Model B"}]
        factors = [{"item_name": "Model A", "mat_type": "Softs", "tub_factor": 14},
                   {"item_name": "Model A", "mat_type": "Hards", "tub_factor": 16},
                   {"item_name": "Model B", "mat_type": "Coal", "tub_factor": 20}]
        hours = self.build(planned_adts=planned, tub_factors=factors)["hours"]
        self.assertEqual([hours[i]["target_bcm"] for i in (0, 1, 11)], [55, 220, 165])
        self.assertEqual(hours[0]["target_loads"], round(55 / 15 + 55 / 20, 1))
        self.assertEqual(hours[1]["target_loads"], round(220 / 15 + 220 / 20, 1))
        self.assertEqual(hours[11]["target_loads"], round(165 / 15 + 165 / 20, 1))
        self.assertNotEqual(hours[1]["target_loads"], round(220 / 15 + 220 / 20 + 220 / 14, 1))

    def test_target_ignores_breakdown_and_missing_factors_are_reported(self):
        planned = [{"name": "ADT04", "item_name": "Model A"}, {"name": "ADT05", "item_name": "Model Missing"}]
        factors = [{"item_name": "Model A", "mat_type": "Softs", "tub_factor": 14},
                   {"item_name": "Model Missing", "mat_type": "Coal", "tub_factor": 0}]
        breakdowns = [{"asset_name": "ADT04", "breakdown_start_datetime": "2026-09-28 06:00:00",
                       "resolved_datetime": "2026-09-28 07:00:00"}]
        data = self.build(breakdowns=breakdowns, planned_adts=planned, tub_factors=factors)
        self.assertEqual(data["hours"][0]["available"], 1)
        self.assertEqual(data["hours"][0]["target_loads"], round(55 / 14, 1))
        self.assertEqual(data["missing_tub_factors"], ["ADT05"])

    def test_target_averages_only_valid_material_factors_and_handles_no_valid_factor(self):
        planned = [{"name": "ADT04", "item_name": "Model A"}]
        factors = [{"item_name": "Model A", "mat_type": "Softs", "tub_factor": 14},
                   {"item_name": "Model A", "mat_type": "Hards", "tub_factor": ""},
                   {"item_name": "Model A", "mat_type": "Coal", "tub_factor": 0}]
        self.assertEqual(self.build(planned_adts=planned, tub_factors=factors)["hours"][1]["target_loads"],
                         round(220 / 14, 1))
        missing = self.build(planned_adts=planned, tub_factors=[])
        self.assertIsNone(missing["hours"][1]["target_loads"])
        self.assertEqual(missing["missing_tub_factors"], ["ADT04"])

    def test_night_target_uses_same_first_middle_and_last_windows(self):
        data = self.build("Night", planned_adts=[{"name": "ADT04", "item_name": "Model A"}],
                          tub_factors=[{"item_name": "Model A", "mat_type": "Softs", "tub_factor": 10}])
        self.assertEqual([data["hours"][i]["target_loads"] for i in (0, 6, 11)], [5.5, 22.0, 16.5])

    def test_pdf_hourly_section_contains_all_six_metrics(self):
        data = self.build(excavators=[{"name": "EX019"}],
                          planned_adts=[{"name": "ADT04", "item_name": "Model A"}],
                          tub_factors=[{"item_name": "Model A", "mat_type": "Softs", "tub_factor": 14}])
        html = report.build_pdf_html(data)
        for label in ("ADT Available", "ADT Utilised", "Actual Loads", "Target Loads",
                      "Excavator Available", "Excavator Utilised"):
            self.assertIn(label, html)
