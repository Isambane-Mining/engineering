# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, getdate, nowdate

from engineering.controllers.fleet_compliance import get_expiring_threshold_days


def _current_fleet_card(asset):
	"""The most recently issued non-cancelled Fleet Card for this Asset —
	mirrors _current_vehicle_licence() in vehicle_licence.py exactly."""
	rows = frappe.get_all(
		"Fleet Card",
		filters={"fleet_number": asset, "docstatus": ["<", 2]},
		fields=["name"],
		order_by="issue_date desc, docstatus desc",
		limit_page_length=1,
	)
	return rows[0].name if rows else None


class FleetCard(Document):
	def autoname(self):
		""""{fleet_number} - {issue_date}", collision-safe — same pattern as
		Vehicle Allocation's autoname(), used here instead of copying Vehicle
		Licence's own legacy "format:" string (flagged elsewhere this session
		as discouraged in v16)."""
		base_name = f"{self.fleet_number} - {self.issue_date}"

		if not frappe.db.exists("Fleet Card", base_name):
			self.name = base_name
			return

		counter = 1

		while frappe.db.exists("Fleet Card", f"{base_name} - {counter}"):
			counter += 1

		self.name = f"{base_name} - {counter}"

	@property
	def days_left(self):
		if not self.expiry_date:
			return None
		return date_diff(self.expiry_date, nowdate())

	@property
	def status(self):
		if self.docstatus == 2:
			return "Cancelled"

		if self.docstatus == 1 and self.fleet_number and self.issue_date:
			newer_exists = frappe.db.exists(
				"Fleet Card",
				{
					"fleet_number": self.fleet_number,
					"docstatus": 1,
					"issue_date": [">", self.issue_date],
					"name": ["!=", self.name],
				},
			)
			if newer_exists:
				return "Superseded"

		if not self.expiry_date:
			return "Active"

		today = getdate(nowdate())
		expiry_date = getdate(self.expiry_date)
		threshold_days = get_expiring_threshold_days()

		if expiry_date < today:
			return "Expired"

		if expiry_date <= add_days(today, threshold_days):
			return "Expiring"

		return "Active"
