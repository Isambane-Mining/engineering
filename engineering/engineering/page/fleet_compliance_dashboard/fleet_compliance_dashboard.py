# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

"""Whitelisted data sources for the Fleet Compliance Dashboard page. This
page is a visual front end over the exact same data as the "Fleet
Compliance Overview" Script Report — nothing here recomputes compliance
independently, it all goes through that report's own get_data(), so the
numbers on this page and in the report can never disagree."""

import frappe

from engineering.controllers.fleet_compliance import bulk_drivers
from engineering.engineering.report.fleet_compliance_overview.fleet_compliance_overview import get_data

DOCSTATUS_LABEL = {0: "Draft", 1: "Submitted", 2: "Cancelled"}

# Fixed display order — worst first, matching the report's own triage sort.
OVERALL_STATUSES = ["Non-Compliant", "Attention Required", "Not Registered", "Compliant"]


def _get_rows(filters):
	if not frappe.has_permission("Vehicle Allocation", "read"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	return get_data(
		{
			"location": filters.get("location"),
			"asset_category": filters.get("asset_category"),
			"driver": filters.get("driver"),
			"overall_status": filters.get("overall_status"),
		}
	)


@frappe.whitelist()
def get_summary(location=None, asset_category=None, driver=None):
	"""Bubble counts, unfiltered by overall_status (that's the thing being
	counted) but respecting the other filters — so the bubbles reflect
	whatever Location/Category/Driver the user has narrowed to."""
	rows = _get_rows({"location": location, "asset_category": asset_category, "driver": driver})

	counts = dict.fromkeys(OVERALL_STATUSES, 0)

	for row in rows:
		status = row.get("overall_status")
		counts[status] = counts.get(status, 0) + 1

	return {
		"total": len(rows),
		"by_status": [{"status": status, "count": counts[status]} for status in OVERALL_STATUSES],
	}


@frappe.whitelist()
def get_rows(location=None, asset_category=None, driver=None, overall_status=None):
	"""Full drill-down row set — same shape as the Fleet Compliance Overview
	report, grouped client-side by Asset Category for the tree view."""
	return _get_rows(
		{
			"location": location,
			"asset_category": asset_category,
			"driver": driver,
			"overall_status": overall_status,
		}
	)


@frappe.whitelist()
def get_asset_history(asset):
	"""Every Vehicle Allocation and Vehicle Licence record ever captured
	against this Asset (any docstatus) — the third drill-down level, opened
	when a user expands an individual Asset row. Lazy-loaded from the
	client rather than bundled into get_rows(), since most Assets on screen
	at once are never actually expanded."""
	if not frappe.has_permission("Vehicle Allocation", "read"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	allocations = frappe.get_all(
		"Vehicle Allocation",
		filters={"asset": asset},
		fields=["name", "location", "valid_from", "valid_to", "status", "docstatus", "required_licence_type"],
		order_by="valid_from desc, creation desc",
	)

	drivers_by_parent = bulk_drivers([a.name for a in allocations])

	for a in allocations:
		a["drivers"] = ", ".join(d.driver_name or d.driver for d in drivers_by_parent.get(a.name, []))
		a["docstatus_label"] = DOCSTATUS_LABEL.get(a.docstatus, "")

	licences = frappe.get_all(
		"Vehicle Licence",
		filters={"fleet_number": asset},
		fields=["name", "site", "registration_number", "issue_date", "expiry_date", "docstatus", "attach"],
		order_by="issue_date desc, creation desc",
	)

	for lic in licences:
		lic["docstatus_label"] = DOCSTATUS_LABEL.get(lic.docstatus, "")

	fleet_cards = frappe.get_all(
		"Fleet Card",
		filters={"allocation_type": "Asset", "fleet_number": asset},
		fields=["name", "bank", "card_number", "issue_date", "expiry_date", "docstatus", "attach"],
		order_by="issue_date desc, creation desc",
	)

	for card in fleet_cards:
		card["docstatus_label"] = DOCSTATUS_LABEL.get(card.docstatus, "")

	return {"allocations": allocations, "licences": licences, "fleet_cards": fleet_cards}
