# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import frappe

from engineering.controllers.fleet_compliance import (
	apply_draft_allocation_penalty,
	bulk_drivers,
	compute_all,
	get_effective_allocations,
	get_expiring_threshold_days,
)
from engineering.engineering.doctype.fleet_management_settings.fleet_management_settings import (
	get_reportable_asset_names,
)


def execute(filters=None):
	filters = filters or {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns():
	return [
		{"fieldname": "asset", "label": "Asset", "fieldtype": "Link", "options": "Asset", "width": 120},
		{"fieldname": "asset_name", "label": "Asset Name", "fieldtype": "Data", "width": 140},
		{"fieldname": "asset_category", "label": "Category", "fieldtype": "Link", "options": "Asset Category", "width": 100},
		{"fieldname": "registered", "label": "Registered", "fieldtype": "Data", "width": 90},
		{"fieldname": "allocation", "label": "Allocation", "fieldtype": "Link", "options": "Vehicle Allocation", "width": 160},
		{"fieldname": "location", "label": "Location", "fieldtype": "Link", "options": "Location", "width": 120},
		{"fieldname": "drivers", "label": "Drivers", "fieldtype": "Data", "width": 220},
		{"fieldname": "driver_licence_status", "label": "Driver Licence", "fieldtype": "Data", "width": 110},
		{"fieldname": "driver_licence_valid_to", "label": "Driver Licence Valid To", "fieldtype": "Date", "width": 140},
		{"fieldname": "addendum_status", "label": "Addendum", "fieldtype": "Data", "width": 100},
		{"fieldname": "vehicle_licence_status", "label": "Vehicle Licence", "fieldtype": "Data", "width": 110},
		{"fieldname": "vehicle_licence_valid_to", "label": "Vehicle Licence Valid To", "fieldtype": "Date", "width": 140},
		{"fieldname": "fleet_card_status", "label": "Fleet Card", "fieldtype": "Data", "width": 110},
		{"fieldname": "fleet_card_valid_to", "label": "Fleet Card Valid To", "fieldtype": "Date", "width": 140},
		{"fieldname": "overall_status", "label": "Overall Status", "fieldtype": "Data", "width": 130},
	]


def get_data(filters):
	asset_names = get_reportable_asset_names()

	if not asset_names:
		return []

	conditions, params = _build_conditions(filters, asset_names)
	threshold_days = get_expiring_threshold_days()

	rows = frappe.db.sql(
		f"""
		select
			a.name as asset,
			a.asset_name as asset_name,
			a.item_name as item_name,
			a.asset_category as asset_category
		from `tabAsset` a
		where {conditions}
		order by a.name asc
		""",
		params,
		as_dict=True,
	)

	# A Draft Vehicle Allocation still counts as "this Asset's current
	# allocation" for Location/Drivers purposes — it shouldn't read as
	# unregistered just because nobody has submitted it yet. Its Overall
	# Status is forced Non-Compliant regardless though, since the
	# allocation itself isn't legally in effect (see
	# apply_draft_allocation_penalty). Compliance is always computed live
	# per row, never read from a stored/cached column.
	allocation_by_asset = get_effective_allocations(
		[row["asset"] for row in rows], fields=["location", "required_licence_type", "comments"]
	)
	drivers_by_allocation = bulk_drivers([a.name for a in allocation_by_asset.values()])

	for row in rows:
		effective = allocation_by_asset.get(row["asset"])
		row["allocation"] = effective.name if effective else None
		row["location"] = effective.location if effective else None
		row["comments"] = effective.comments if effective else None
		row["registered"] = "Yes" if effective else "No"

		driver_rows = drivers_by_allocation.get(row["allocation"], [])
		compliance = compute_all(
			row["asset"],
			[d.driver for d in driver_rows],
			effective.required_licence_type if effective else None,
			threshold_days,
		)
		row.update(compliance)
		row["drivers"] = ", ".join(d.driver_name or d.driver for d in driver_rows)
		row["_driver_ids"] = [d.driver for d in driver_rows]

		if not effective:
			row["overall_status"] = "Not Registered"
		else:
			row["overall_status"] = apply_draft_allocation_penalty(row["overall_status"], effective.docstatus)

	# Location and Driver can no longer be filtered in SQL — both now come
	# from the Python-resolved effective allocation (Draft or Submitted),
	# not a joined column.
	location_filter = (filters.get("location") or "").strip()
	driver_filter = (filters.get("driver") or "").strip()

	if location_filter:
		rows = [r for r in rows if r.get("location") == location_filter]

	if driver_filter:
		rows = [r for r in rows if driver_filter in r["_driver_ids"]]

	for row in rows:
		row.pop("_driver_ids", None)

	status_filter = (filters.get("overall_status") or "").strip()

	if status_filter:
		rows = [r for r in rows if r["overall_status"] == status_filter]

	# Worst-first, for at-a-glance triage.
	severity = {"Non-Compliant": 0, "Not Registered": 1, "Attention Required": 2, "Compliant": 3}
	rows.sort(key=lambda r: (severity.get(r["overall_status"], 4), r["asset"]))

	return rows


def _build_conditions(filters, asset_names):
	where = ["a.name in %(asset_names)s"]
	params = {"asset_names": list(asset_names)}

	if filters.get("asset_category"):
		where.append("a.asset_category = %(asset_category)s")
		params["asset_category"] = filters["asset_category"]

	return " and ".join(where), params
