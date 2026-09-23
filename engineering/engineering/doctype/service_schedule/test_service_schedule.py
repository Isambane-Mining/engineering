# Copyright (c) 2025, BuFf0k and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from engineering.engineering.doctype.service_schedule.service_schedule import (
    interval_due_at_hours,
    next_service_target_from_service_hours,
    planning_status_for_hours,
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
