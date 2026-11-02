# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import frappe

from engineering.engineering.doctype.hourly_downtime_summary.hourly_downtime_summary import (
	on_doctype_update,
)

# Runs pre-model-sync because the doctype sync itself calls
# on_doctype_update, which adds the (site, report_date, hour_slot) unique key.
#
# 1. Until 2026-09-22 06:00 the 00:00-06:00 hours were saved under their
#    calendar date; since 2026-09-23 they are saved under the shift date (the
#    previous day). That made the night of 22 Sep and the night of 23 Sep both
#    land on report_date 2026-09-22. Re-label the old calendar-date rows to
#    the shift date so history is consistent; this moves every old night back
#    by one day together, so it creates no new collisions.
# 2. The few remaining true duplicates are the same hour re-run minutes later;
#    keep the newest copy (it includes late-captured breakdowns).

SHIFT_DATE_SWITCH = "2026-09-22 12:00:00"
EARLY_HOUR_SLOTS = (
	"00:00-01:00",
	"01:00-02:00",
	"02:00-03:00",
	"03:00-04:00",
	"04:00-05:00",
	"05:00-06:00",
)


def execute():
	if not frappe.db.table_exists("Hourly Downtime Summary"):
		return

	relabel_calendar_date_night_hours()
	remove_rerun_duplicates()

	frappe.db.commit()
	on_doctype_update()


def relabel_calendar_date_night_hours():
	# report_date = DATE(creation) only holds for the old calendar-date rows
	# (a shift-date row is always created after its report_date), which also
	# keeps this idempotent.
	frappe.db.sql(
		"""
		UPDATE `tabHourly Downtime Summary`
		SET report_date = DATE_SUB(report_date, INTERVAL 1 DAY)
		WHERE hour_slot IN %(slots)s
		  AND creation < %(switch)s
		  AND report_date = DATE(creation)
		""",
		{"slots": EARLY_HOUR_SLOTS, "switch": SHIFT_DATE_SWITCH},
	)


def remove_rerun_duplicates():
	groups = frappe.db.sql(
		"""
		SELECT site, report_date, hour_slot
		FROM `tabHourly Downtime Summary`
		GROUP BY site, report_date, hour_slot
		HAVING COUNT(*) > 1
		""",
		as_dict=True,
	)

	for group in groups:
		names = frappe.get_all(
			"Hourly Downtime Summary",
			filters=group,
			order_by="sent_to_raven desc, creation desc",
			pluck="name",
		)
		for name in names[1:]:
			frappe.delete_doc(
				"Hourly Downtime Summary",
				name,
				ignore_permissions=True,
				force=True,
			)
