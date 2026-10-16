import hashlib
import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate


FIXES_FIELD = "fixes"


def get_allowed_sites():
	if frappe.session.user == "Administrator":
		return []

	if "System Manager" in frappe.get_roles(frappe.session.user):
		return []

	return frappe.get_all(
		"User Permission",
		filters={
			"user": frappe.session.user,
			"allow": "Location",
		},
		pluck="for_value",
	)


def check_site_access(site):
	allowed_sites = get_allowed_sites()

	if allowed_sites and site not in allowed_sites:
		frappe.throw(
			_("You do not have permission to access site {0}.").format(site)
		)


def execute(filters=None):
	filters = filters or {}

	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -7))

	items = get_items(from_date, to_date, filters.get("site"))

	return get_columns(), [{"dashboard_html": get_dashboard_html(items)}]


def get_columns():
	return [
		{"label": _("Dashboard"), "fieldname": "dashboard_html", "fieldtype": "HTML", "width": 1200},
	]


def get_items(from_date, to_date, site=None):
	conditions = ["c.parenttype = 'Mechanical Downtime sign-off'"]
	values = {}

	allowed_sites = get_allowed_sites()

	if site:
		check_site_access(site)
		conditions.append("p.site = %(site)s")
		values["site"] = site
	elif allowed_sites:
		conditions.append("p.site IN %(allowed_sites)s")
		values["allowed_sites"] = tuple(allowed_sites)

	rows = frappe.db.sql(
		f"""
		SELECT
			c.name,
			c.parent,
			p.site,
			c.fixes,
			c.date_time_io,
			c.date_time_p,
			c.date_time_e,
			c.comments1,
			c.comments2,
			c.comments3
		FROM `tabMechanical Downtime sign-off child` c
		LEFT JOIN `tabMechanical Downtime sign-off` p ON p.name = c.parent
		WHERE {" AND ".join(conditions)}
		ORDER BY COALESCE(c.date_time_io, c.date_time_p, c.date_time_e) DESC
		""",
		values,
		as_dict=True,
	)

	grouped = {}

	for row in rows:
		comment_groups = [
			("Information Officer", row.date_time_io, row.comments1),
			("Production Manager", row.date_time_p, row.comments2),
			("Engineering Manager", row.date_time_e, row.comments3),
		]

		for source, dt, comments in comment_groups:
			if not dt or not comments:
				continue

			comment_date = getdate(dt)

			if comment_date < from_date or comment_date > to_date:
				continue

			for item in split_fleet_comments(comments):
				group_key = (row.name, str(comment_date), row.site or "", item["fleet"])

				if group_key not in grouped:
					grouped[group_key] = {
						"date": comment_date,
						"site": row.site,
						"shift": get_shift_from_parent(row.parent),
						"fleet": item["fleet"],
						"child_row": row.name,
						"fixes": row.fixes,
						"comments": [],
					}

				grouped[group_key]["comments"].append({
					"source": source,
					"comment": item["comment"],
				})

	items = []

	for item in grouped.values():
		fixed_key = make_fixed_key(
			item["child_row"],
			"Combined",
			item["date"],
			item["fleet"],
			frappe.as_json(item["comments"]),
		)
		is_fixed = get_fixed_status(item["fixes"], fixed_key)

		items.append({
			"date": item["date"],
			"site": item["site"],
			"shift": item["shift"],
			"fleet": item["fleet"],
			"child_row": item["child_row"],
			"fixed_key": fixed_key,
			"comments": item["comments"],
			"is_fixed": is_fixed,
		})


	# downtime_verification_dashboard_comments_v3
	verification_filters = [
		"v.parenttype = 'Mechanical Downtime sign-off'",
		"v.parentfield = 'downtime_verifications'",
		"p.verification_workflow_version = 1",
		"p.report_date BETWEEN %(from_date)s AND %(to_date)s",
		"TRIM(COALESCE(v.comments, '')) != ''",
	]

	verification_values = {
		"from_date": from_date,
		"to_date": to_date,
	}

	if site:
		verification_filters.append("p.site = %(site)s")
		verification_values["site"] = site
	elif allowed_sites:
		verification_filters.append("p.site IN %(allowed_sites)s")
		verification_values["allowed_sites"] = tuple(allowed_sites)

	verification_rows = frappe.db.sql(
		"""
		SELECT
			v.downtime_record,
			v.department,
			v.verification_status,
			v.verified_by,
			v.verified_on,
			v.comments,
			p.site,
			p.report_date,
			p.report_shift,
			b.asset_name AS fleet
		FROM `tabDowntime Verification Entry` v
		INNER JOIN `tabMechanical Downtime sign-off` p
			ON p.name = v.parent
		INNER JOIN `tabPlant Breakdown or Maintenance` b
			ON b.name = v.downtime_record
		WHERE """ + " AND ".join(verification_filters) + """
		ORDER BY p.report_date DESC, v.verified_on DESC
		""",
		verification_values,
		as_dict=True,
	)

	for row in verification_rows:
		if not row.fleet:
			continue

		source = (
			"Production Manager"
			if row.department == "Production"
			else "Engineering Manager"
		)

		detail = row.comments

		items.append({
			"date": row.report_date,
			"site": row.site,
			"shift": row.report_shift,
			"fleet": row.fleet,
			"child_row": None,
			"fixed_key": "",
			"comments": [{
				"source": source,
				"comment": detail,
			}],
			"is_fixed": False,
			"verification_only": True,
		})

	return items



@frappe.whitelist()
def get_commented_breakdown_name(fleet, site, correction_date):
        fleet = str(fleet or "").strip()
        site = str(site or "").strip()

        if not fleet or not site or not correction_date:
                return ""

        correction_date = getdate(correction_date)

        day_start = f"{correction_date} 00:00:00"
        day_end = f"{add_days(correction_date, 1)} 00:00:00"

        rows = frappe.db.sql(
                """
                SELECT name
                FROM `tabPlant Breakdown or Maintenance`
                WHERE UPPER(TRIM(asset_name)) = UPPER(TRIM(%(fleet)s))
                  AND location = %(site)s
                  AND COALESCE(
                        NULLIF(breakdown_start_datetime, ''),
                        creation
                  ) < %(day_end)s
                  AND (
                        resolved_datetime IS NULL
                        OR resolved_datetime = ''
                        OR resolved_datetime >= %(day_start)s
                  )
                ORDER BY
                        CASE
                                WHEN breakdown_start_datetime IS NOT NULL
                                        THEN breakdown_start_datetime
                                WHEN resolved_datetime IS NOT NULL
                                        THEN resolved_datetime
                                ELSE creation
                        END DESC,
                        modified DESC
                LIMIT 1
                """,
                {
                        "fleet": fleet,
                        "site": site,
                        "day_start": day_start,
                        "day_end": day_end,
                },
                as_dict=True,
        )

        return rows[0].name if rows else ""


def get_dashboard_html(items):
	if not items:
		return """
			<div class="dcd-dashboard">
				<div class="dcd-empty">No downtime corrections found for this filter.</div>
			</div>
		"""

	cards = [get_card_html(item) for item in items]

	return f"""
		<div class="dcd-dashboard">
			<div class="dcd-grid">
				{''.join(cards)}
			</div>
		</div>
	"""


def get_card_html(item):
	status_class = "dcd-fixed" if item["is_fixed"] else "dcd-open"
	status_text = "Fixed" if item["is_fixed"] else "Not Fixed"
	card_class = "dcd-card-fixed" if item["is_fixed"] else "dcd-card-not-fixed"
	checked = "checked" if item["is_fixed"] else ""

	if item.get("verification_only"):
		status_class = ""
		status_text = "Verification Comment"
		card_class = "dcd-card-not-fixed"
		fixed_control = ""
	else:
		fixed_control = """
		<label class="dcd-check">
			<input type="checkbox" class="dcd-fixed-checkbox"
				data-row="{child_row}"
				data-key="{fixed_key}" {checked}>
			Fixed
		</label>
		""".format(
			child_row=frappe.utils.escape_html(item["child_row"]),
			fixed_key=frappe.utils.escape_html(item["fixed_key"]),
			checked=checked,
		)

	comments_json = frappe.utils.escape_html(frappe.as_json(item["comments"]))

	return f"""
		<div class="dcd-card {card_class}">
			<div class="dcd-top">
				<button type="button"
                                        class="dcd-fleet dcd-fleet-link"
                                        data-fleet="{frappe.utils.escape_html(item["fleet"])}"
                                        data-site="{frappe.utils.escape_html(item["site"] or "")}"
                                        data-date="{item["date"]}"
                                        title="Open Plant Breakdown or Maintenance"
                                        style="cursor:pointer;font-family:inherit;">
                                        {frappe.utils.escape_html(item["fleet"])}
                                </button>
				<div class="dcd-status {status_class}">{status_text}</div>
			</div>

			<div class="dcd-meta">
				<div><b>Date:</b> {item["date"]} <b style="margin-left: 10px;">Shift:</b> {frappe.utils.escape_html(item["shift"] or "")}</div>
				<div><b>Site:</b> {frappe.utils.escape_html(item["site"] or "")}</div>
			</div>

			<div class="dcd-actions">
				<button class="btn btn-xs btn-default dcd-view"
					data-fleet="{frappe.utils.escape_html(item["fleet"])}"
					data-date="{item["date"]}"
					data-comments="{comments_json}">
					View Comment
				</button>

				{fixed_control}
			</div>
		</div>
	"""

def get_shift_from_parent(parent_name):
	value = str(parent_name or "")

	if "Night Shift" in value:
		return "Night Shift"

	if "Day Shift" in value:
		return "Day Shift"

	return ""


def split_fleet_comments(text):
	blocks = []
	current_fleet = None
	current_comment = []

	for raw_line in text.splitlines():
		line = raw_line.strip()

		if not line:
			continue

		if looks_like_fleet(line):
			if current_fleet:
				blocks.append({
					"fleet": current_fleet,
					"comment": "\n".join(current_comment).strip() or "No comment",
				})

			current_fleet = line
			current_comment = []
			continue

		if current_fleet:
			current_comment.append(line)

	if current_fleet:
		blocks.append({
			"fleet": current_fleet,
			"comment": "\n".join(current_comment).strip() or "No comment",
		})

	if not blocks and text.strip():
		blocks.append({"fleet": "Unknown Fleet", "comment": text.strip()})

	return blocks


def looks_like_fleet(line):
	value = str(line or "").strip().upper()

	if len(value) > 20:
		return False

	if " " in value:
		return False

	return bool(re.match(r"^[A-Z]{2,8}\d{2,6}[A-Z]?$", value))


def make_fixed_key(child_row, source, date, fleet, comment):
	raw = f"{child_row}|{source}|{date}|{fleet}|{comment}"
	return hashlib.sha256(raw.encode()).hexdigest()


def get_fixed_status(fixes_json, fixed_key):
	fixes = frappe.parse_json(fixes_json or "{}") or {}
	return 1 if fixes.get(fixed_key) else 0


@frappe.whitelist()
def set_fixed_status(child_row, fixed_key, fixed):
	fixed = int(fixed)

	row = frappe.get_doc("Mechanical Downtime sign-off child", child_row)

	parent_site = frappe.db.get_value(
		"Mechanical Downtime sign-off",
		row.parent,
		"site",
	)

	check_site_access(parent_site)

	fixes = frappe.parse_json(row.fixes or "{}") or {}

	if fixed:
		fixes[fixed_key] = {
			"fixed": 1,
			"fixed_by": frappe.session.user,
			"fixed_on": frappe.utils.now(),
		}
	else:
		fixes.pop(fixed_key, None)

	row.db_set(FIXES_FIELD, frappe.as_json(fixes), update_modified=False)

	return {"ok": 1}