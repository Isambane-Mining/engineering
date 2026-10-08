# Copyright (c) 2026, buff0k and contributors
# For license information, please see license.txt

"""Shared fleet-compliance derivation logic, reused by Vehicle Allocation's
virtual fields (computed live, never stored — see that doctype's controller),
the Fleet Compliance Overview report, the Fleet Management dashboard Number
Cards, and the notifications controller — so there is exactly one place that
decides what "Valid" / "Expiring" / "Outstanding" mean.

Nothing here re-enters licence/undertaking data, and nothing here is cached:
every call reads straight from the existing sources of truth (ir's Employee
Induction Record, the driver's own Employee Records table, and this app's
Vehicle Licence) at read time."""

import frappe
from frappe.utils import add_days, cint, escape_html, getdate, nowdate

COMPANY_VEHICLE_UNDERTAKING = "Company Vehicle Undertaking"

# ---------------------------------------------------------------------
# SA driving-licence code hierarchy: a holder of a higher/combination code
# is legally entitled to drive anything a lower code covers (K53 code
# hierarchy). Keyed by short code; value is the set of codes (including
# itself) that a holder of that code is authorised to drive.
# ---------------------------------------------------------------------
LICENCE_CODE_AUTHORISES = {
	"B": {"B"},
	"C1": {"C1", "B"},
	"C": {"C", "C1", "B"},
	"EB": {"EB", "B"},
	"EC1": {"EC1", "C1", "EB", "B"},
	"EC": {"EC", "C", "EC1", "C1", "EB", "B"},
}

LICENCE_CODE_TO_INDUCTION_NAME = {
	"B": "Drivers Licence - Code B",
	"EB": "Drivers Licence - Code EB",
	"C": "Drivers Licence - Code C",
	"EC": "Drivers Licence - Code EC",
	"C1": "Drivers Licence - Code C1",
	"EC1": "Drivers Licence - Code EC1",
}
INDUCTION_NAME_TO_LICENCE_CODE = {v: k for k, v in LICENCE_CODE_TO_INDUCTION_NAME.items()}


def qualifying_licence_names(required_licence_type):
	"""Every Employee Induction (licence code) that legally entitles someone
	to drive whatever `required_licence_type` requires — i.e. the required
	code itself plus every higher code in the SA hierarchy. Falls back to an
	exact-match-only list for any licence type outside the standard 6 codes."""
	code = INDUCTION_NAME_TO_LICENCE_CODE.get(required_licence_type)

	if not code:
		return [required_licence_type]

	holder_codes = [c for c, authorises in LICENCE_CODE_AUTHORISES.items() if code in authorises]

	return [LICENCE_CODE_TO_INDUCTION_NAME[c] for c in holder_codes]


def get_expiring_threshold_days() -> int:
	try:
		days = frappe.db.get_single_value("Fleet Management Settings", "expiring_threshold_days")
	except Exception:
		days = None

	return cint(days) or 90


def effective_asset_owner(asset_owner, company, supplier=None, customer=None):
	"""An Asset's "Company" field is just the books it's accounted under —
	who actually *owns* it is the Ownership section (Asset Owner: Company /
	Supplier / Customer, each with its own party field). Company only means
	"the owner" when Asset Owner is actually set to Company; a hired/leased
	LDV has Asset Owner = Supplier, and Company on its own says nothing
	about that. Mirrors the same Company-vs-Supplier reasoning already used
	for plant/equipment grouping in machine_file.py and the Daily
	Availability dashboard's ownership_sections.py, so fleet reporting
	agrees with the rest of the app on what "owner" means."""
	owner = (asset_owner or "").strip().lower()

	if owner == "supplier":
		# Explicitly Supplier-owned — Company never applies here, even if
		# Supplier itself wasn't captured (that's a data-entry gap to flag as
		# "Unassigned", not a reason to silently count it as a Company asset).
		return (supplier or "").strip()
	if owner == "customer":
		return (customer or "").strip()
	if owner == "company":
		return (company or "").strip()

	# Asset Owner was never captured — fall back to whatever's actually filled in.
	return (company or supplier or customer or "").strip()


def _status_from_valid_to(valid_to, threshold_days, today):
	if not valid_to:
		return "Outstanding"

	if valid_to < today:
		return "Expired"

	if valid_to <= add_days(today, threshold_days):
		return "Expiring"

	return "Valid"


def _incomplete_or_outstanding(draft_valid_to, draft_name, today):
	"""A Draft (unsubmitted) record is real progress, not nothing — someone
	has captured it, they just haven't finished (an upload still pending,
	etc). If its own dates would currently be valid, surface that as
	"Incomplete" rather than conflating it with "Outstanding" (no record at
	all). A draft whose dates are already lapsed doesn't represent current
	progress either way, so it still falls back to Outstanding."""
	valid_to = getdate(draft_valid_to) if draft_valid_to else None

	if valid_to and valid_to >= today:
		return valid_to, "Incomplete", draft_name

	return None, "Outstanding", None


def compute_driver_licence_status(driver, required_licence_type, threshold_days=None):
	"""A driver is compliant if they hold ANY currently-submitted Employee
	Induction Record for the required code, or for a higher code in the SA
	licence hierarchy that legally covers it (e.g. a Code C holder may
	legally drive a Code C1 vehicle). Among all qualifying records, the one
	with the furthest valid_to is used.

	If no submitted record exists but a currently-valid Draft one does
	(captured but not yet finalised — e.g. certificate upload outstanding),
	that is reported as "Incomplete" rather than "Outstanding"."""
	if threshold_days is None:
		threshold_days = get_expiring_threshold_days()

	if not driver:
		return None, "Not Applicable", None

	if not required_licence_type:
		# A driver is assigned but nobody has said which licence code this
		# Asset requires — that is itself a compliance gap, not "N/A".
		return None, "Outstanding", None

	if not frappe.db.exists("DocType", "Employee Induction Record"):
		return None, "Outstanding", None

	qualifying_names = qualifying_licence_names(required_licence_type)
	today = getdate(nowdate())

	records = frappe.get_all(
		"Employee Induction Record",
		filters={"employee": driver, "training": ["in", qualifying_names], "docstatus": 1},
		fields=["name", "valid_to"],
		order_by="valid_to desc",
		limit_page_length=1,
	)

	if records:
		row = records[0]
		valid_to = getdate(row.valid_to) if row.valid_to else None
		return valid_to, _status_from_valid_to(valid_to, threshold_days, today), row.name

	draft = frappe.get_all(
		"Employee Induction Record",
		filters={"employee": driver, "training": ["in", qualifying_names], "docstatus": 0},
		fields=["name", "valid_to"],
		order_by="valid_to desc",
		limit_page_length=1,
	)

	if draft:
		return _incomplete_or_outstanding(draft[0].valid_to, draft[0].name, today)

	return None, "Outstanding", None


def get_effective_allocations(assets, fields=None):
	"""One allocation per Asset — the one that should drive that Asset's
	Location/Drivers/compliance columns wherever this is displayed (Excel
	export, Fleet Compliance Overview report/dashboard). A Submitted
	"Current" allocation wins; if there isn't one yet, falls back to the
	most recent Draft "Current" allocation — a captured-but-not-yet-
	submitted allocation still carries real Location/Drivers, it
	shouldn't make the Asset look unregistered.

	Never returns more than one row per Asset even if more than one Draft
	exists for it (nothing stops a user creating several): highest
	docstatus wins, then newest valid_from/creation."""
	if not assets:
		return {}

	fields = list(fields or ["location", "required_licence_type"])

	for standard_field in ("name", "asset", "docstatus"):
		if standard_field not in fields:
			fields.append(standard_field)

	rows = frappe.get_all(
		"Vehicle Allocation",
		filters={"asset": ["in", assets], "status": "Current", "docstatus": ["<", 2]},
		fields=fields,
		order_by="docstatus desc, valid_from desc, creation desc",
	)

	effective = {}

	for row in rows:
		effective.setdefault(row.asset, row)  # first hit per asset wins — already ordered best-first

	return effective


def apply_draft_allocation_penalty(overall_status, allocation_docstatus):
	"""A Draft allocation isn't legally in effect yet — even when every
	underlying detail (licences, undertaking) individually looks fine, the
	allocation itself hasn't been finalised, so it can never read as truly
	Compliant. Only applies where get_effective_allocations() resolved to
	a Draft; a Submitted allocation (or an unregistered Asset with no
	allocation at all) is untouched."""
	if allocation_docstatus == 0:
		return "Non-Compliant"

	return overall_status


def bulk_drivers(parent_names):
	"""Drivers is a Table MultiSelect child table (Vehicle Allocation
	Driver), so it never comes through a plain frappe.get_all() on the
	Vehicle Allocation parent. One extra query, grouped by parent, for any
	caller that loops many allocations at once (list view, xlsx export,
	dashboard Number Cards, notifications, reports). Returns
	{parent_name: [<Vehicle Allocation Driver row>, ...]}, each row having
	.driver and .driver_name."""
	if not parent_names:
		return {}

	by_parent = {}

	for row in frappe.get_all(
		"Vehicle Allocation Driver",
		filters={"parent": ["in", parent_names], "parenttype": "Vehicle Allocation", "parentfield": "drivers"},
		fields=["parent", "driver", "driver_name"],
	):
		by_parent.setdefault(row.parent, []).append(row)

	return by_parent


def collect_drivers(drivers):
	"""Dedupe/clean the Drivers table into an ordered list of Employee ids.
	Empty means a vehicle allocated to a Location as a shared resource
	(compliance is then Not Applicable for the driver-related sections);
	one or more drivers means every one of them must be individually
	compliant."""
	result = []

	for candidate in drivers or []:
		if candidate and candidate not in result:
			result.append(candidate)

	return result


# Severity ranking used to reduce a group of drivers down to a single
# worst-case status: "the group is only as compliant as its least compliant
# member". Expired/Outstanding (no usable licence at all) outrank
# Expiring/Incomplete (licence exists, just lapsing or not yet finalised),
# which outrank Valid.
_DRIVER_STATUS_SEVERITY = {"Outstanding": 3, "Expired": 3, "Incomplete": 2, "Expiring": 2, "Valid": 1}


def compute_driver_licence_status_for_group(drivers, required_licence_type, threshold_days=None):
	"""Like compute_driver_licence_status, but for a list of drivers (a
	shared vehicle) rather than a single one. The whole group must be
	Valid for the aggregate to read Valid — the worst individual result
	is surfaced, since that is the one that actually needs attention."""
	if not drivers:
		return None, "Not Applicable", None

	if threshold_days is None:
		threshold_days = get_expiring_threshold_days()

	worst = None
	very_old = getdate("1900-01-01")

	for candidate in drivers:
		valid_to, status, source = compute_driver_licence_status(candidate, required_licence_type, threshold_days)
		severity = _DRIVER_STATUS_SEVERITY.get(status, 0)

		if worst is None or severity > worst[0]:
			worst = (severity, valid_to, status, source)
		elif severity == worst[0] and (valid_to or very_old) < (worst[1] or very_old):
			# Tie-break on the soonest valid_to (the more urgent of the two
			# equally severe results — a missing licence, with no date at
			# all, is the most urgent of all) so the surfaced source record
			# is actionable.
			worst = (severity, valid_to, status, source)

	return worst[1], worst[2], worst[3]


def compute_addendum_status_for_group(drivers):
	"""Like compute_addendum_status, but for a list of drivers. Every driver
	in the group needs their own signed Undertaking on file — if any one is
	missing, the group reads Outstanding."""
	if not drivers:
		return "Not Applicable", None, None

	results = [compute_addendum_status(candidate) for candidate in drivers]
	missing = [r for r in results if r[0] != "On File"]

	if missing:
		return "Outstanding", None, None

	# All On File: surface the most recently captured one as representative.
	results.sort(key=lambda r: r[1] or getdate("1900-01-01"), reverse=True)
	return "On File", results[0][1], results[0][2]


def compute_addendum_status(driver):
	"""Look up the 'Company Vehicle Undertaking' entry in the driver's own
	Employee Records table (Employee.ir_employee_records) rather than storing
	a duplicate upload anywhere — the returned value is the actual file URL
	already on that record, read fresh every time."""
	if not driver:
		return "Not Applicable", None, None

	if not frappe.db.exists("DocType", "Employee") or not frappe.get_meta("Employee").has_field(
		"ir_employee_records"
	):
		return "Outstanding", None, None

	rows = frappe.get_all(
		"Employee File Records",
		filters={"parent": driver, "parenttype": "Employee", "record_type": COMPANY_VEHICLE_UNDERTAKING},
		fields=["attach", "date_captured"],
		order_by="date_captured desc, idx desc",
		limit_page_length=1,
	)

	if not rows or not rows[0].attach:
		return "Outstanding", None, None

	return "On File", rows[0].date_captured, rows[0].attach


def compute_vehicle_licence_status(asset, threshold_days=None):
	"""The current Vehicle Licence for an Asset is simply the most recently
	*issued* submitted one — by construction that is never the superseded
	one, so there is no need to depend on Vehicle Licence's own (also
	virtual) status field here.

	If no submitted record exists but a currently-valid Draft one does
	(captured but not yet finalised — e.g. the disc scan hasn't been
	attached/submitted yet), that is reported as "Incomplete" rather than
	"Outstanding"."""
	if threshold_days is None:
		threshold_days = get_expiring_threshold_days()

	if not asset or not frappe.db.exists("DocType", "Vehicle Licence"):
		return None, "Outstanding", None

	today = getdate(nowdate())

	records = frappe.get_all(
		"Vehicle Licence",
		filters={"fleet_number": asset, "docstatus": 1},
		fields=["name", "expiry_date"],
		order_by="issue_date desc",
		limit_page_length=1,
	)

	if records:
		row = records[0]
		valid_to = getdate(row.expiry_date) if row.expiry_date else None
		return valid_to, _status_from_valid_to(valid_to, threshold_days, today), row.name

	draft = frappe.get_all(
		"Vehicle Licence",
		filters={"fleet_number": asset, "docstatus": 0},
		fields=["name", "expiry_date"],
		order_by="issue_date desc",
		limit_page_length=1,
	)

	if draft:
		return _incomplete_or_outstanding(draft[0].expiry_date, draft[0].name, today)

	return None, "Outstanding", None


def compute_fleet_card_status(asset, threshold_days=None):
	"""Mirrors compute_vehicle_licence_status, but against Fleet Card
	(fleet_number = asset) instead of Vehicle Licence — the current card for
	an Asset is simply the most recently *issued* submitted one.

	Unlike a Vehicle Licence, a Fleet Card isn't a legal requirement every
	vehicle must carry — plenty of real Assets legitimately have none at
	all (private-use vehicles, assets not on a fuel/toll card scheme). So
	"no card at all" reads "None Issued" (compliant, not a gap), unlike
	Vehicle Licence's own "no record" case which correctly reads
	Outstanding. "Outstanding" here is reserved for a real but currently-
	unusable record (a Draft whose own dates have already lapsed) — a card
	someone actually started capturing, not nothing.

	If no submitted record exists but a currently-valid Draft one does, that
	is reported as "Incomplete" rather than "Outstanding"."""
	if threshold_days is None:
		threshold_days = get_expiring_threshold_days()

	if not asset or not frappe.db.exists("DocType", "Fleet Card"):
		return None, "None Issued", None

	today = getdate(nowdate())

	# allocation_type="Asset" is explicit, not just implied by the value
	# matching - fleet_number is a Dynamic Link (a card can instead be
	# allocated to an Employee, for a private vehicle with no Asset record
	# at all), so an Asset name and an Employee id are different ID spaces
	# that could in principle collide.
	records = frappe.get_all(
		"Fleet Card",
		filters={"allocation_type": "Asset", "fleet_number": asset, "docstatus": 1},
		fields=["name", "expiry_date"],
		order_by="issue_date desc",
		limit_page_length=1,
	)

	if records:
		row = records[0]
		valid_to = getdate(row.expiry_date) if row.expiry_date else None
		return valid_to, _status_from_valid_to(valid_to, threshold_days, today), row.name

	draft = frappe.get_all(
		"Fleet Card",
		filters={"allocation_type": "Asset", "fleet_number": asset, "docstatus": 0},
		fields=["name", "expiry_date"],
		order_by="issue_date desc",
		limit_page_length=1,
	)

	if draft:
		return _incomplete_or_outstanding(draft[0].expiry_date, draft[0].name, today)

	return None, "None Issued", None


def compute_overall_status(
	vehicle_licence_status, has_driver, driver_licence_status, addendum_status, fleet_card_status=None
):
	# "Incomplete" (a currently-valid Draft record exists, just not yet
	# submitted) is partial compliance — the paperwork is in motion, only a
	# finalisation step is outstanding — so it belongs with "Attention
	# Required", not "Non-Compliant".
	#
	# has_driver is True whenever at least one driver (the primary Driver
	# and/or one-or-more Additional Drivers) is assigned. A vehicle with no
	# driver at all — allocated to a Location as a shared resource — has
	# nobody's licence/undertaking to check, so those sections don't count
	# against it either way.
	#
	# fleet_card_status gets the same treatment as vehicle_licence_status
	# (not gated on has_driver — a card is issued against the vehicle, not a
	# driver). Optional/None for callers that don't track Fleet Card at all.
	non_compliant_flags = [vehicle_licence_status in ("Expired", "Outstanding")]

	if fleet_card_status is not None:
		non_compliant_flags.append(fleet_card_status in ("Expired", "Outstanding"))

	if has_driver:
		non_compliant_flags.append(driver_licence_status in ("Expired", "Outstanding"))
		non_compliant_flags.append(addendum_status == "Outstanding")

	if any(non_compliant_flags):
		return "Non-Compliant"

	attention_flags = [vehicle_licence_status in ("Expiring", "Incomplete")]

	if fleet_card_status is not None:
		attention_flags.append(fleet_card_status in ("Expiring", "Incomplete"))

	if has_driver:
		attention_flags.append(driver_licence_status in ("Expiring", "Incomplete"))

	if any(attention_flags):
		return "Attention Required"

	return "Compliant"


# Pill colours shared by every compliance HTML block below, so "Valid" /
# "Expiring" / "Expired" etc always mean the same colour everywhere on the
# form (and roughly track the list-view indicator colours).
_STATUS_COLOURS = {
	"Valid": "#2e7d32",
	"On File": "#2e7d32",
	"Closed": "#2e7d32",
	"None Issued": "#2e7d32",
	"Expiring": "#e65100",
	"Incomplete": "#e65100",
	"Open": "#e65100",
	"Expired": "#c62828",
	"Outstanding": "#c62828",
	"Not Applicable": "#757575",
}


def _status_pill(status):
	colour = _STATUS_COLOURS.get(status, "#757575")
	return (
		f"<span style='display:inline-block;padding:2px 10px;border-radius:10px;"
		f"background:{colour};color:#fff;font-size:12px;font-weight:600;white-space:nowrap;'>"
		f"{escape_html(status)}</span>"
	)


def _driver_label(driver):
	name = frappe.db.get_value("Employee", driver, "employee_name")
	return f"{escape_html(driver)} - {escape_html(name)}" if name else escape_html(driver)


# Shared look for every compliance block on the Vehicle Allocation form — a
# single rounded, bordered panel per block, consistent header/cell styling,
# so the driver cards and the plain tables read as one visual system
# instead of the driver cards looking hand-styled and everything else
# looking like default Bootstrap.
_PANEL_STYLE = "border:1px solid var(--border-color); border-radius:8px; overflow:hidden;"
_CARD_STYLE = "border:1px solid var(--border-color); border-radius:8px; padding:8px 10px; min-width:180px; flex:1 1 200px; position:relative;"
_TABLE_STYLE = "width:100%; border-collapse:collapse; font-size:12px;"
_TH_STYLE = (
	"text-align:left; padding:8px 10px; font-size:10.5px; font-weight:700; text-transform:uppercase; "
	"letter-spacing:0.3px; color:var(--text-muted); background:var(--control-bg); border-bottom:1px solid var(--border-color);"
)
_TD_STYLE = "padding:8px 10px; border-top:1px solid var(--border-color);"


def _empty_panel(message):
	return f"<p class='text-muted' style='margin:4px 0 0;'>{escape_html(message)}</p>"


def _render_table(headers, rows_of_cells):
	"""headers: [str, ...]; rows_of_cells: [[cell_html, ...], ...] — cells
	are raw HTML (pills/links), not escaped again here."""
	thead = "".join(f"<th style='{_TH_STYLE}'>{escape_html(h)}</th>" for h in headers)
	body = "".join(
		"<tr>" + "".join(f"<td style='{_TD_STYLE}'>{cell}</td>" for cell in row) + "</tr>" for row in rows_of_cells
	)

	return f"<div style='{_PANEL_STYLE} margin-top:4px;'><table style='{_TABLE_STYLE}'><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table></div>"


def render_driver_licence_html(drivers, required_licence_type, threshold_days=None):
	"""One row per Driver — replaces the old single driver_licence_status/
	valid_to/source virtual fields, which couldn't represent more than one
	person's compliance at a time."""
	drivers = collect_drivers(drivers)

	if not drivers:
		return _empty_panel("No driver assigned — shared resource, no licence to check.")

	if threshold_days is None:
		threshold_days = get_expiring_threshold_days()

	rows = []

	for driver in drivers:
		valid_to, status, source = compute_driver_licence_status(driver, required_licence_type, threshold_days)
		source_html = (
			f"<a href='/app/employee-induction-record/{escape_html(source)}'>{escape_html(source)}</a>"
			if source
			else "—"
		)
		rows.append([_driver_label(driver), _status_pill(status), escape_html(str(valid_to or "—")), source_html])

	return _render_table(["Driver", "Status", "Valid To", "Source Record"], rows)


def render_addendum_html(drivers):
	"""One row per Driver — replaces the old single addendum_status/date/url
	virtual fields."""
	drivers = collect_drivers(drivers)

	if not drivers:
		return _empty_panel("No driver assigned — shared resource, no undertaking to check.")

	rows = []

	for driver in drivers:
		status, date_captured, url = compute_addendum_status(driver)
		link_html = f"<a href='{escape_html(url)}' target='_blank'>View</a>" if url else "—"
		rows.append([_driver_label(driver), _status_pill(status), escape_html(str(date_captured or "—")), link_html])

	return _render_table(["Driver", "Status", "Date Captured", "Undertaking"], rows)


def render_drivers_overview_html(drivers, required_licence_type):
	"""The Drivers field's entire interactive surface: a search box (add),
	a card per already-added Driver with Name / Designation / Licence &
	Undertaking status and a remove button, all rendered here — the
	underlying Drivers Table MultiSelect field itself is hidden (see
	vehicle_allocation.json), driven entirely from this HTML block's JS
	(vehicle_allocation.js) instead of its own native widget."""
	drivers = collect_drivers(drivers)

	search_box = (
		"<div class='fleet-driver-search' style='position:relative; margin-bottom:8px;'>"
		"<input type='text' class='form-control' autocomplete='off' "
		"placeholder='Search driver by name or employee ID…' data-fleet-driver-search>"
		f"<div data-fleet-driver-results style='display:none; position:absolute; z-index:50; top:100%; left:0; right:0; "
		f"background:var(--card-bg); {_PANEL_STYLE} margin-top:2px; max-height:220px; overflow:auto;'></div>"
		"</div>"
	)

	if not drivers:
		return search_box + _empty_panel("No Drivers added yet.")

	employees = {
		e.name: e
		for e in frappe.get_all(
			"Employee", filters={"name": ["in", drivers]}, fields=["name", "employee_name", "designation"]
		)
	}

	cards = []

	for driver in drivers:
		emp = employees.get(driver)
		name_label = f"{driver} - {emp.employee_name}" if emp and emp.employee_name else driver
		designation = emp.designation if emp else ""
		_, licence_status, _ = compute_driver_licence_status(driver, required_licence_type)
		addendum_status, _, _ = compute_addendum_status(driver)

		cards.append(
			f"<div style='{_CARD_STYLE}' data-fleet-driver-card='{escape_html(driver)}'>"
			f"<button type='button' data-fleet-driver-remove='{escape_html(driver)}' title='Remove' "
			"style='position:absolute; top:4px; right:6px; border:none; background:none; cursor:pointer; "
			"font-size:14px; line-height:1; color:var(--text-muted);'>&times;</button>"
			f"<div style='font-weight:600; font-size:12px; padding-right:16px;'>{escape_html(name_label)}</div>"
			f"<div style='color:var(--text-muted); font-size:11px; margin-bottom:6px;'>{escape_html(designation or '—')}</div>"
			f"<div style='display:flex; gap:4px; flex-wrap:wrap;'>{_status_pill(licence_status)}{_status_pill(addendum_status)}</div>"
			"</div>"
		)

	return search_box + f"<div style='display:flex; flex-wrap:wrap; gap:8px;'>{''.join(cards)}</div>"


def render_vehicle_licence_html(asset, threshold_days=None):
	"""Replaces the old single vehicle_licence_status/valid_to/source
	virtual fields — kept as HTML too, for the same reason as the driver
	sections: one place, consistent pill styling, no virtual fields left to
	carry in the doctype's own schema."""
	valid_to, status, source = compute_vehicle_licence_status(asset, threshold_days)
	source_html = (
		f"<a href='/app/vehicle-licence/{escape_html(source)}'>{escape_html(source)}</a>" if source else "—"
	)

	rows = [
		["Status", _status_pill(status)],
		["Valid To", escape_html(str(valid_to or "—"))],
		["Source Record", source_html],
	]
	body = "".join(
		f"<tr><td style='{_TD_STYLE} width:160px; color:var(--text-muted); font-size:11px; text-transform:uppercase;'>{label}</td>"
		f"<td style='{_TD_STYLE}'>{value}</td></tr>"
		for label, value in rows
	)

	return f"<div style='{_PANEL_STYLE} margin-top:4px;'><table style='{_TABLE_STYLE}'><tbody>{body}</tbody></table></div>"


def render_service_history_html(asset, limit=10):
	if not asset or not frappe.db.exists("DocType", "Plant Breakdown or Maintenance"):
		return _empty_panel("No service history available.")

	rows = frappe.get_all(
		"Plant Breakdown or Maintenance",
		filters={"asset_name": asset},
		fields=["name", "breakdown_start_datetime", "resolved_datetime", "open_closed"],
		order_by="breakdown_start_datetime desc",
		limit_page_length=limit,
	)

	if not rows:
		return _empty_panel("No breakdown/maintenance history recorded for this Asset.")

	table_rows = []

	for r in rows:
		table_rows.append(
			[
				f"<a href='/app/plant-breakdown-or-maintenance/{escape_html(r.name)}'>{escape_html(r.name)}</a>",
				escape_html(str(r.breakdown_start_datetime or "—")),
				escape_html(str(r.resolved_datetime or "—")),
				_status_pill(r.open_closed or ""),
			]
		)

	return _render_table(["Record", "Start", "Resolved", "Status"], table_rows)


def compute_all(asset, drivers, required_licence_type, threshold_days=None):
	"""Bulk-friendly single entry point: returns every compliance field as a
	dict, for callers (the report, dashboard number cards, notifications)
	that loop many allocations and don't want to load a full Document (and
	therefore its virtual-field properties) per row.

	`drivers` is a list of Employees (0, 1, or many — a vehicle allocated to
	a Location as a shared resource with nobody named has an empty list)."""
	if threshold_days is None:
		threshold_days = get_expiring_threshold_days()

	vehicle_licence_valid_to, vehicle_licence_status, vehicle_licence_source = compute_vehicle_licence_status(
		asset, threshold_days
	)
	fleet_card_valid_to, fleet_card_status, fleet_card_source = compute_fleet_card_status(asset, threshold_days)

	drivers = collect_drivers(drivers)

	if drivers:
		driver_licence_valid_to, driver_licence_status, driver_licence_source = (
			compute_driver_licence_status_for_group(drivers, required_licence_type, threshold_days)
		)
		addendum_status, addendum_date, addendum_url = compute_addendum_status_for_group(drivers)
	else:
		driver_licence_valid_to, driver_licence_status, driver_licence_source = None, "Not Applicable", None
		addendum_status, addendum_date, addendum_url = "Not Applicable", None, None

	overall_status = compute_overall_status(
		vehicle_licence_status, bool(drivers), driver_licence_status, addendum_status, fleet_card_status
	)

	return {
		"vehicle_licence_valid_to": vehicle_licence_valid_to,
		"vehicle_licence_status": vehicle_licence_status,
		"vehicle_licence_source": vehicle_licence_source,
		"fleet_card_valid_to": fleet_card_valid_to,
		"fleet_card_status": fleet_card_status,
		"fleet_card_source": fleet_card_source,
		"driver_licence_valid_to": driver_licence_valid_to,
		"driver_licence_status": driver_licence_status,
		"driver_licence_source": driver_licence_source,
		"addendum_status": addendum_status,
		"addendum_date": addendum_date,
		"addendum_url": addendum_url,
		"overall_status": overall_status,
	}
