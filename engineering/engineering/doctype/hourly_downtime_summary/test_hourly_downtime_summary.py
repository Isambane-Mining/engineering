# Copyright (c) 2026, Isambane Mining (Pty) Ltd
# See license.txt

from datetime import date, datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from engineering.engineering.doctype.hourly_downtime_summary import (
	hourly_downtime_summary as hourly_summary,
)


class _InsertedSummary:
	name = "HDS-TEST"

	def insert(self, ignore_permissions=False):
		self.ignore_permissions = ignore_permissions


class TestHourlyDowntimeSummary(TestCase):
	@patch.object(hourly_summary, "now_datetime")
	def test_midnight_to_six_am_slots_use_previous_shift_date(self, mock_now):
		cases = (
			(datetime(2026, 9, 2, 1, 15), "00:00-01:00"),
			(datetime(2026, 9, 2, 2, 15), "01:00-02:00"),
			(datetime(2026, 9, 2, 3, 15), "02:00-03:00"),
			(datetime(2026, 9, 2, 4, 15), "03:00-04:00"),
			(datetime(2026, 9, 2, 5, 15), "04:00-05:00"),
			(datetime(2026, 9, 2, 6, 15), "05:00-06:00"),
		)

		for run_time, expected_slot in cases:
			with self.subTest(hour_slot=expected_slot):
				mock_now.return_value = run_time

				report_date, hour_slot, period_date = (
					hourly_summary.get_completed_hour_slot()
				)

				self.assertEqual(report_date, date(2026, 9, 1))
				self.assertEqual(hour_slot, expected_slot)
				self.assertEqual(period_date, date(2026, 9, 2))

	@patch.object(hourly_summary, "now_datetime")
	def test_six_am_onwards_uses_calendar_date(self, mock_now):
		mock_now.return_value = datetime(2026, 9, 2, 7, 15)

		report_date, hour_slot, period_date = (
			hourly_summary.get_completed_hour_slot()
		)

		self.assertEqual(report_date, date(2026, 9, 2))
		self.assertEqual(hour_slot, "06:00-07:00")
		self.assertEqual(period_date, date(2026, 9, 2))

	@patch.object(hourly_summary, "now_datetime")
	def test_midnight_run_uses_previous_calendar_days_23_to_24_slot(self, mock_now):
		mock_now.return_value = datetime(2026, 9, 2, 0, 15)

		report_date, hour_slot, period_date = (
			hourly_summary.get_completed_hour_slot()
		)

		self.assertEqual(report_date, date(2026, 9, 1))
		self.assertEqual(hour_slot, "23:00-24:00")
		self.assertEqual(period_date, date(2026, 9, 1))

	@patch(
		"engineering.engineering.report.hourly_downtime_report."
		"hourly_downtime_report.execute"
	)
	@patch.object(hourly_summary, "get_completed_hour_slot")
	def test_saved_shift_date_does_not_change_actual_query_date(
		self,
		mock_completed_slot,
		mock_execute,
	):
		mock_completed_slot.return_value = (
			date(2026, 9, 1),
			"00:00-01:00",
			date(2026, 9, 2),
		)
		mock_execute.return_value = ([], [])
		inserted = _InsertedSummary()
		captured_doc = {}

		def capture_doc(values):
			captured_doc.update(values)
			return inserted

		fake_frappe = SimpleNamespace(
			get_doc=capture_doc,
			db=SimpleNamespace(commit=MagicMock()),
		)

		with patch.object(hourly_summary, "frappe", fake_frappe):
			result = hourly_summary.create_hourly_downtime_summary("Koppie")

		self.assertEqual(result, "HDS-TEST")
		self.assertEqual(
			mock_execute.call_args.args[0],
			{
				"report_date": "2026-09-02",
				"hour_slot": "00:00-01:00",
				"site": "Koppie",
			},
		)
		self.assertEqual(captured_doc["report_date"], date(2026, 9, 1))
		self.assertEqual(captured_doc["hour_slot"], "00:00-01:00")
