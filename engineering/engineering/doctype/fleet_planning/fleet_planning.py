# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from engineering.controllers.fleet_compliance import (
	bulk_drivers,
	compute_addendum_status,
	compute_all,
	compute_driver_licence_status,
	get_expiring_threshold_days,
)
from engineering.engineering.doctype.fleet_management_settings.fleet_management_settings import (
	get_reportable_asset_names,
)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_planning_assets(doctype, txt, searchfield, start, page_len, filters):
	"""Link-style search for the Planning Board's "Add an Asset" control —
	restricted to get_reportable_asset_names(), the same Reporting-Scope-
	filtered universe Import Current Fleet Allocations uses, so a manually
	added Asset can never bypass Reporting Scope. Returned as
	value/description (matching frappe.desk.search.search_link's shape)
	plus item_name, so the client can paint a new card immediately without
	a save+reload round trip."""
	asset_names = get_reportable_asset_names()

	if not asset_names:
		return []

	return frappe.db.sql(
		"""
		select name as value, asset_name as description, item_name
		from `tabAsset`
		where name in %(asset_names)s and (name like %(txt)s or asset_name like %(txt)s)
		order by name
		limit %(start)s, %(page_len)s
		""",
		{"asset_names": list(asset_names), "txt": f"%{txt}%", "start": start, "page_len": page_len},
		as_dict=True,
	)


def _driver_tri_state(driver_licence_status, addendum_status):
	"""Red/orange/green for one Driver's OWN compliance — their licence
	against whatever Required Licence Type is asked of them, plus their
	Company Vehicle Undertaking — independent of any other driver sharing
	the same card. Same two-tier rule as
	fleet_compliance.compute_overall_status, just for a single person
	instead of a whole allocation."""
	if driver_licence_status in ("Expired", "Outstanding") or addendum_status == "Outstanding":
		return "Non-Compliant"

	if driver_licence_status in ("Expiring", "Incomplete"):
		return "Attention Required"

	return "Compliant"


@frappe.whitelist()
def get_board_compliance(rows):
	"""Bulk compliance lookup for the Planning Board: for each given row —
	{"asset": ..., "required_licence_type": ..., "drivers": [employee, ...]}
	— reflecting the board's CURRENT client-side state (including edits not
	yet saved, which is exactly why this takes that state as an explicit
	argument instead of reading the saved document) — computes the same
	compute_all() used everywhere else in Fleet for that card's overall
	(vehicle) status, plus each individual driver's own tri-state (see
	_driver_tri_state) for the driver chips. Returns
	{"asset_status": {asset: overall_status}, "driver_status": {"driver|required_licence_type": tri_state}}."""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else (rows or [])
	threshold_days = get_expiring_threshold_days()

	asset_status = {}
	driver_status = {}

	for row in rows:
		asset = row.get("asset")

		if not asset:
			continue

		drivers = [d for d in (row.get("drivers") or []) if d]
		required_licence_type = row.get("required_licence_type")

		compliance = compute_all(asset, drivers, required_licence_type, threshold_days)
		asset_status[asset] = compliance["overall_status"]

		for driver in drivers:
			key = f"{driver}|{required_licence_type or ''}"

			if key in driver_status:
				continue

			_, dl_status, _ = compute_driver_licence_status(driver, required_licence_type, threshold_days)
			addendum_status, _, _ = compute_addendum_status(driver)
			driver_status[key] = _driver_tri_state(dl_status, addendum_status)

	return {"asset_status": asset_status, "driver_status": driver_status}


class FleetPlanning(Document):
	def autoname(self):
		"""FP-{effective_date}, collision-safe: a second plan for the same
		date gets "FP-{effective_date} - 1", a third " - 2", and so on —
		same pattern as Vehicle Allocation.autoname(). naming_rule is "By
		script" (not the JSON's old "format:" string) deliberately: Frappe
		v16 flags "format:" as discouraged (frappe/core/doctype/doctype/
		doctype.py's patch_old_naming_expressions — it exists only to
		auto-migrate pre-v16 doctypes, and warns on every save of a
		DocType still using it), and there's no reason to carry that
		warning on a brand-new doctype when a real autoname() already has
		to exist here anyway."""
		base_name = f"FP-{self.effective_date}"

		if not frappe.db.exists("Fleet Planning", base_name):
			self.name = base_name
			return

		counter = 1

		while frappe.db.exists("Fleet Planning", f"{base_name} - {counter}"):
			counter += 1

		self.name = f"{base_name} - {counter}"

	def after_insert(self):
		"""The whole point of this doctype is to manipulate the fleet's
		actual current state — it's useless empty, there is no scenario
		where a user would want a blank board, so the import runs
		automatically the moment the document is first created rather than
		needing an extra manual button click for something that always has
		to happen anyway. Fires exactly once (after_insert, not on every
		later save), so re-saving an in-progress plan never re-imports over
		edits already made."""
		self.import_current_allocations()

	@frappe.whitelist()
	def import_current_allocations(self):
		"""Replaces plan_assets/plan_drivers entirely with a fresh snapshot of
		the real fleet: every in-scope Asset (Reporting Scope + Public Road
		Asset Categories, via get_reportable_asset_names — the same universe
		every other Fleet dashboard/report/export/notification uses) gets one
		plan_assets row — Location + Drivers copied from its Current,
		submitted Vehicle Allocation when one exists, or a blank Location
		(the board's "Unallocated" row) when it doesn't, exactly as agreed
		with the user rather than falling back to the Asset's own Location
		field."""
		if self.docstatus != 0:
			frappe.throw(frappe._("Can only import into a Draft Fleet Planning document."))

		asset_names = get_reportable_asset_names() or set()

		current_allocations = frappe.get_all(
			"Vehicle Allocation",
			filters={"docstatus": 1, "status": "Current", "asset": ["in", list(asset_names)]},
			fields=["name", "asset", "location", "is_temp", "required_licence_type"],
		)
		allocation_by_asset = {row.asset: row for row in current_allocations}
		drivers_by_parent = bulk_drivers([row.name for row in current_allocations])

		self.set("plan_assets", [])
		self.set("plan_drivers", [])

		for asset in sorted(asset_names):
			allocation = allocation_by_asset.get(asset)

			self.append(
				"plan_assets",
				{
					"asset": asset,
					"location": allocation.location if allocation else None,
					"is_temp": allocation.is_temp if allocation else 0,
					"required_licence_type": allocation.required_licence_type if allocation else None,
				},
			)

			if allocation:
				for driver_row in drivers_by_parent.get(allocation.name, []):
					self.append("plan_drivers", {"asset": asset, "driver": driver_row.driver})

		self.save()

		return {"asset_count": len(self.plan_assets), "driver_count": len(self.plan_drivers)}

	def on_submit(self):
		"""Diffs every plan_assets row against the Asset's actual current
		state and creates a Draft Vehicle Allocation for each one that
		genuinely changed — Location, Drivers, or Is Temporary Loan. Left as
		Draft, never auto-submitted: Vehicle Allocation's own before_submit
		already refuses to submit without signed handover paperwork whenever
		Drivers are listed, and on_submit already closes out the previous
		allocation and raises the Asset Movement — this only ever needs to
		create the new Draft, not duplicate any of that.

		Dragging a card to the "Unallocated" row (a blank planned Location)
		never closes out a real current allocation on its own — that stays a
		deliberate, separate action (the existing "Return Vehicle" button on
		Vehicle Allocation) rather than something a plan submit does
		implicitly."""
		failures = []
		generated = 0

		for plan_row in self.plan_assets:
			try:
				if self._generate_allocation_for_row(plan_row):
					generated += 1
			except Exception:
				frappe.log_error(
					f"Fleet Planning {self.name}: failed to generate Vehicle Allocation for {plan_row.asset}",
					"Fleet Planning",
				)
				failures.append(plan_row.asset)

		if failures:
			frappe.msgprint(
				frappe._(
					"Generated {0} Vehicle Allocation(s). Failed for: {1} — see the Error Log for details."
				).format(generated, ", ".join(failures)),
				title=frappe._("Fleet Planning Processed With Errors"),
				indicator="orange",
			)
		else:
			frappe.msgprint(
				frappe._("Generated {0} Vehicle Allocation(s) as Draft — each still needs signed handover paperwork and its own submit.").format(
					generated
				),
				title=frappe._("Fleet Planning Processed"),
				indicator="green",
			)

	def _generate_allocation_for_row(self, plan_row):
		"""Returns True if a new Draft Vehicle Allocation was created for
		this row, False if nothing changed (or there was nothing to
		generate)."""
		asset = plan_row.asset
		planned_location = (plan_row.location or "").strip()
		planned_is_temp = bool(plan_row.is_temp)
		planned_licence_type = plan_row.required_licence_type or ""
		planned_drivers = sorted({row.driver for row in self.plan_drivers if row.asset == asset})

		current = frappe.get_all(
			"Vehicle Allocation",
			filters={"asset": asset, "docstatus": 1, "status": "Current"},
			fields=["name", "location", "is_temp", "required_licence_type"],
			limit_page_length=1,
		)
		current = current[0] if current else None
		current_location = (current.location or "").strip() if current else ""
		current_is_temp = bool(current.is_temp) if current else False
		current_licence_type = (current.required_licence_type or "").strip() if current else ""
		current_drivers = (
			sorted(frappe.get_all("Vehicle Allocation Driver", filters={"parent": current.name}, pluck="driver"))
			if current
			else []
		)

		unchanged = (
			current is not None
			and planned_location == current_location
			and planned_is_temp == current_is_temp
			and planned_licence_type == current_licence_type
			and planned_drivers == current_drivers
		)

		if unchanged or not planned_location:
			return False

		new_alloc = frappe.new_doc("Vehicle Allocation")
		new_alloc.asset = asset
		new_alloc.location = planned_location
		new_alloc.valid_from = self.effective_date
		new_alloc.is_temp = planned_is_temp
		new_alloc.required_licence_type = plan_row.required_licence_type

		for driver in planned_drivers:
			new_alloc.append("drivers", {"driver": driver})

		new_alloc.insert()

		plan_row.db_set("generated_vehicle_allocation", new_alloc.name, update_modified=False)

		return True
