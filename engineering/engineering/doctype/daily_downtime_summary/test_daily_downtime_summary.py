# Copyright (c) 2026, Isambane Mining (Pty) Ltd
# See license.txt

from datetime import date, datetime
from unittest import TestCase
from unittest.mock import patch

from engineering import hooks
from engineering.engineering.report.down_time import down_time


class TestDailyDowntimeSummary(TestCase):
	def test_day_shift_uses_shift_date_from_six_am_to_six_pm(self):
		windows = down_time.get_report_windows(
			date(2026, 9, 1),
			"Day Shift",
		)

		self.assertEqual(
			windows,
			[
				(
					"Day",
					datetime(2026, 9, 1, 6, 0),
					datetime(2026, 9, 1, 18, 0),
				)
			],
		)

	def test_night_shift_uses_shift_date_until_next_day_six_am(self):
		windows = down_time.get_report_windows(
			date(2026, 9, 1),
			"Night Shift",
		)

		self.assertEqual(
			windows,
			[
				(
					"Night",
					datetime(2026, 9, 1, 18, 0),
					datetime(2026, 9, 2, 6, 0),
				)
			],
		)

	def test_full_daily_uses_shift_date_from_six_am_to_next_six_am(self):
		windows = down_time.get_report_windows(
			date(2026, 9, 1),
			"Full Daily",
		)

		self.assertEqual(windows[0][1], datetime(2026, 9, 1, 6, 0))
		self.assertEqual(windows[-1][2], datetime(2026, 9, 2, 6, 0))

	@patch.object(down_time, "create_daily_downtime_summary")
	@patch.object(down_time, "now_datetime")
	def test_full_daily_generation_uses_previous_shift_date_at_six_am(
		self,
		mock_now,
		mock_create,
	):
		mock_now.return_value = datetime(2026, 9, 2, 6, 0)
		mock_create.side_effect = lambda site, report_date, shift: site

		down_time.create_daily_downtime_summaries("Full Daily")

		self.assertEqual(
			mock_create.call_count,
			len(down_time.DAILY_DOWNTIME_SITE_CHANNELS),
		)
		for call in mock_create.call_args_list:
			self.assertEqual(call.args[1], date(2026, 9, 1))
			self.assertEqual(call.args[2], "Full Daily")

	def test_saved_summary_scheduler_times(self):
		hourly_job = (
			"engineering.engineering.doctype.hourly_downtime_summary."
			"hourly_downtime_summary.create_all_hourly_downtime_summaries"
		)
		day_job = (
			"engineering.engineering.report.down_time.down_time."
			"send_daily_downtime_day_shift"
		)
		night_job = (
			"engineering.engineering.report.down_time.down_time."
			"send_daily_downtime_night_shift"
		)
		full_daily_job = (
			"engineering.engineering.report.down_time.down_time."
			"send_full_daily_downtime_summary"
		)

		self.assertNotIn(
			hourly_job,
			hooks.scheduler_events.get("hourly", []),
		)
		self.assertIn(
			hourly_job,
			hooks.scheduler_events["cron"]["15 * * * *"],
		)
		self.assertIn(
			day_job,
			hooks.scheduler_events["cron"]["0 18 * * *"],
		)
		self.assertIn(
			night_job,
			hooks.scheduler_events["cron"]["0 6 * * *"],
		)
		self.assertIn(
			full_daily_job,
			hooks.scheduler_events["cron"]["0 6 * * *"],
		)
