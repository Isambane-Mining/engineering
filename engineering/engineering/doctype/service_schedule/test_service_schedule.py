# Copyright (c) 2025, BuFf0k and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase
from frappe import _dict
from datetime import date, timedelta
from unittest.mock import patch, Mock

from engineering.engineering.doctype.service_schedule.service_schedule import (
    interval_due_at_hours,
    next_service_target_from_service_hours,
    planning_status_for_hours,
    recompute_planning_rows,
    select_schedule_snapshot_date,
    batch_get_day_shift_start_hours,
    queue_service_schedule_update,
    get_latest_prev_start_hours,
)


class TestServiceSchedule(FrappeTestCase):
    def test_next_service_target_is_strictly_after_completed_service(self):
        self.assertEqual(next_service_target_from_service_hours(9750), 10000)
        self.assertEqual(next_service_target_from_service_hours(9765), 10000)
        self.assertEqual(next_service_target_from_service_hours(10000), 10250)

        # Real-world examples around a service threshold
        self.assertEqual(next_service_target_from_service_hours(22747), 23000)
        self.assertEqual(next_service_target_from_service_hours(28920), 29250)
        self.assertEqual(next_service_target_from_service_hours(30591), 30750)

    def test_65_hour_warning(self):
        status, remaining = planning_status_for_hours(9940, 10000)
        self.assertEqual(status, "Due within 65 hours")
        self.assertEqual(remaining, 60)

    def test_260_hour_warning_does_not_overlap_65_hour_warning(self):
        status, remaining = planning_status_for_hours(9800, 10000)
        self.assertEqual(status, "Due within 260 hours")
        self.assertEqual(remaining, 200)

    def test_due_now(self):
        status, remaining = planning_status_for_hours(10000, 10000)
        self.assertEqual(status, "Due")
        self.assertEqual(remaining, 0)

    def test_overdue_remains_flagged(self):
        status, remaining = planning_status_for_hours(10030, 10000)
        self.assertEqual(status, "Overdue")
        self.assertEqual(remaining, -30)

    def test_completed_service_advances_target(self):
        target = next_service_target_from_service_hours(10030)
        self.assertEqual(target, 10250)

        status, remaining = planning_status_for_hours(10030, target)
        self.assertEqual(status, "Due within 260 hours")
        self.assertEqual(remaining, 220)

    def test_service_interval_matches_target(self):
        self.assertEqual(interval_due_at_hours(10000), 2000)
        self.assertEqual(interval_due_at_hours(10250), 250)

    def test_recompute_uses_baseline_on_each_day(self):
        start = date(2026, 7, 14)
        rows = []
        for i, estimate in enumerate((14800, 14820, 14980, 15010)):
            newer = i >= 2
            rows.append(_dict(date=start + timedelta(days=i), estimate_hours=estimate,
                hours_previous_service=14982 if newer else 14750,
                msr_record_name="new" if newer else "old"))
        recompute_planning_rows(rows, start)
        self.assertEqual([r.planning_planned_hours for r in rows], [15000, 15000, 15250, 15250])
        self.assertEqual([r.planned_hours_next_service_1 for r in rows], [15000, 15000, 15250, 15250])
        self.assertEqual(rows[0].next_service_interval_1, "1000 Hours")
        self.assertEqual(rows[2].next_service_interval_1, "250 Hours")
        self.assertEqual(rows[3].planning_hours_remaining, 240)

    def test_no_service_history_has_no_target(self):
        row = _dict(date=date(2026, 7, 1), estimate_hours=1000,
            hours_previous_service=0, msr_record_name="")
        recompute_planning_rows([row], date(2026, 7, 1))
        self.assertEqual(row.planning_status, "No Service History")
        self.assertEqual(row.planning_planned_hours, 0)
        self.assertFalse(row.planned_hours_next_service_1)

    def test_interval_cycle(self):
        for hours, interval in ((250, 250), (500, 500), (750, 750),
                                (1000, 1000), (1500, 500), (2000, 2000), (2250, 250)):
            self.assertEqual(interval_due_at_hours(hours), interval)

    def test_snapshot_selection_for_historical_current_and_future(self):
        dates = [date(2026, 7, 1), date(2026, 7, 31)]
        self.assertEqual(select_schedule_snapshot_date(dates, "July 2026", date(2026, 9, 23)), dates[-1])
        self.assertEqual(select_schedule_snapshot_date(dates, "July 2026", date(2026, 6, 23)), dates[0])
        self.assertEqual(select_schedule_snapshot_date(dates, "July 2026", date(2026, 7, 31)), dates[-1])

    def test_day_shift_duplicate_uses_highest_positive_reading(self):
        parents = [_dict(name="day", shift_date=date(2026, 7, 1))]
        children = [_dict(parent="day", asset_name="IS001", eng_hrs_start=100),
                    _dict(parent="day", asset_name="IS001", eng_hrs_start=110)]
        with patch("engineering.engineering.doctype.service_schedule.service_schedule.frappe.get_all",
                   side_effect=[parents, children]) as get_all:
            result = batch_get_day_shift_start_hours(["IS001"], date(2026, 7, 1), date(2026, 7, 31))
        self.assertEqual(result[("2026-07-01", "IS001")], 110)
        self.assertEqual(get_all.call_args_list[0].kwargs["filters"]["shift"], "Day")

    def test_scheduler_queues_existing_current_month_only(self):
        module = "engineering.engineering.doctype.service_schedule.service_schedule"
        with patch(f"{module}.nowdate", return_value="2026-07-20"), \
             patch(f"{module}.frappe.get_all", return_value=["Klipfontein-July 2026", "Koppie-July 2026"]) as get_all, \
             patch(f"{module}.frappe.enqueue") as enqueue:
            result = queue_service_schedule_update()
        self.assertEqual(result["schedule_names"], ["Klipfontein-July 2026", "Koppie-July 2026"])
        self.assertEqual(get_all.call_args.kwargs["filters"], {"month": "July 2026"})
        self.assertEqual(enqueue.call_count, 2)

    def test_first_day_carry_forward_uses_day_reading(self):
        module = "engineering.engineering.doctype.service_schedule.service_schedule"
        fake_db = _dict(sql=Mock(return_value=[_dict(eng_hrs_start=1234)]))
        with patch(f"{module}.frappe.db", fake_db):
            self.assertEqual(get_latest_prev_start_hours("IS001", date(2026, 7, 1)), 1234)
        self.assertIn("pu.shift = 'Day'", fake_db.sql.call_args.args[0])
        self.assertIn("pu.shift_date DESC, pa.eng_hrs_start DESC", fake_db.sql.call_args.args[0])
