import hashlib
import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate


FIXES_FIELD = "fixes"


def get_allowed_sites():
    user = frappe.session.user

    if user == "Guest":
        frappe.throw(_("Login required."), frappe.PermissionError)

    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return []

    sites = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Location"},
        pluck="for_value",
    )

    if not sites:
        frappe.throw(
            _("No permitted Locations are assigned to your user."),
            frappe.PermissionError,
        )

    return sites


def check_dashboard_access():
    user = frappe.session.user

    if user == "Administrator":
        return

    if user == "Guest":
        frappe.throw(_("Login required."), frappe.PermissionError)

    page = frappe.get_doc("Page", "downtime-correction-dashboard")
    allowed_roles = {row.role for row in page.get("roles") or []}

    if not allowed_roles or not allowed_roles.intersection(
        frappe.get_roles(user)
    ):
        frappe.throw(
            _("You do not have access to the Downtime Correction Dashboard."),
            frappe.PermissionError,
        )


def check_site_access(site):
    allowed_sites = get_allowed_sites()

    if allowed_sites and site not in allowed_sites:
        frappe.throw(
            _("You do not have permission to access site {0}.").format(site)
        )


@frappe.whitelist()
def get_page_html(from_date=None, to_date=None, site=None, fixed_status=None):
    check_dashboard_access()

    from_date = getdate(from_date or add_days(nowdate(), -7))
    to_date = getdate(to_date or nowdate())

    if from_date > to_date:
        frappe.throw(_("From Date must not exceed To Date."))

    if site and not frappe.db.exists("Location", site):
        frappe.throw(_("Invalid Site."))

    if fixed_status not in (None, "", "All", "Fixed", "Not Fixed"):
        frappe.throw(_("Invalid fixed status filter."))

    return get_dashboard_html(
        get_items(from_date, to_date, site, fixed_status)
    )


def get_items(from_date, to_date, site=None, fixed_status=None):
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
            v.name AS verification_entry,
            v.correction_fixed,
            v.downtime_record,
            v.department,
            v.verification_status,
            v.verified_by,
            v.verified_on,
            v.comments,
            p.site,
            p.report_date,
            p.report_shift,
            b.asset_name AS fleet,
            b.breakdown_start_datetime AS breakdown_start_datetime
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

    verification_cards = {}

    for row in verification_rows:
        if not row.fleet:
            continue

        source = (
            "Production Manager"
            if row.department == "Production"
            else "Engineering Manager"
        )

        key = (
            row.downtime_record,
            str(row.report_date),
            row.site or "",
            row.report_shift or "",
        )

        if key not in verification_cards:
            verification_cards[key] = {
                "date": row.report_date,
                "site": row.site,
                "shift": row.report_shift,
                "fleet": row.fleet,
                "child_row": None,
                "fixed_key": "",
                "comments": [],
                "is_fixed": True,
                "verification_entry": row.verification_entry,
                "verification_only": True,
                "breakdown_name": row.downtime_record,
                "breakdown_start_datetime": row.breakdown_start_datetime,
            }

        verifier = row.verified_by or ""
        verifier_name = (
            frappe.db.get_value("User", verifier, "full_name")
            or verifier
        ) if verifier else ""

        display_source = (
            f"{source} ({verifier_name})"
            if verifier_name
            else source
        )

        verification_cards[key]["is_fixed"] = (
            verification_cards[key]["is_fixed"]
            and bool(row.correction_fixed)
        )

        verification_cards[key]["comments"].append({
            "source": display_source,
            "comment": row.comments,
        })

    items.extend(verification_cards.values())

    if fixed_status == "Fixed":
        items = [
            item for item in items
            if item.get("is_fixed")
        ]
    elif fixed_status == "Not Fixed":
        items = [
            item for item in items
            if not item.get("is_fixed")
        ]

    return items



@frappe.whitelist()
def get_commented_breakdown_name(fleet, site, correction_date):
    check_dashboard_access()

    if site:
        check_site_access(site)
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
        fixed_control = """
        <label class="dcd-check">
            <input type="checkbox" class="dcd-verification-fixed-checkbox"
                data-entry="{entry}" {checked} {disabled}>
            Fixed
        </label>
        """.format(
            entry=frappe.utils.escape_html(item["verification_entry"]),
            checked=checked,
            disabled="" if can_mark_correction_fixed() else "disabled",
        )
    else:
        fixed_control = """
        <label class="dcd-check">
            <input type="checkbox" class="dcd-fixed-checkbox"
                data-row="{child_row}"
                data-key="{fixed_key}" {checked} {disabled}>
            Fixed
        </label>
        """.format(
            child_row=frappe.utils.escape_html(item["child_row"]),
            fixed_key=frappe.utils.escape_html(item["fixed_key"]),
            checked=checked,
            disabled="" if can_mark_correction_fixed() else "disabled",
        )

    comments_json = frappe.utils.escape_html(frappe.as_json(item["comments"]))

    return f"""
        <div class="dcd-card {card_class}">
            <div class="dcd-top">
                <button type="button"
                                        class="dcd-fleet dcd-fleet-link"
                                        data-fleet="{frappe.utils.escape_html(item["fleet"])}"
                        data-breakdown="{frappe.utils.escape_html(item.get("breakdown_name") or "")}"
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
                    data-start="{frappe.utils.escape_html(str(item.get("breakdown_start_datetime") or ""))}"
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


FIXED_EDITOR_ROLES = frozenset({
    "System Manager",
    "Engineering Manager",
    "Engineering Foreman",
    "Production Manager",
    "Production Foreman",
    "Production User",
})


def can_mark_correction_fixed():
    """Separate dashboard viewing from permission to edit Fixed status."""
    return (
        frappe.session.user == "Administrator"
        or bool(FIXED_EDITOR_ROLES.intersection(frappe.get_roles()))
    )


def valid_fixed_keys_for_child(row):
    """Rebuild keys from the saved comments, not client-supplied content."""
    grouped = {}

    comment_groups = [
        ("Information Officer", row.date_time_io, row.comments1),
        ("Production Manager", row.date_time_p, row.comments2),
        ("Engineering Manager", row.date_time_e, row.comments3),
    ]

    for source, dt, comments in comment_groups:
        if not dt or not comments:
            continue

        comment_date = getdate(dt)

        for item in split_fleet_comments(comments):
            key = (comment_date, item["fleet"])
            grouped.setdefault(key, []).append({
                "source": source,
                "comment": item["comment"],
            })

    return {
        make_fixed_key(
            row.name,
            "Combined",
            date,
            fleet,
            frappe.as_json(comments),
        )
        for (date, fleet), comments in grouped.items()
    }


@frappe.whitelist(methods=["POST"])
def set_fixed_status(child_row, fixed_key, fixed):
    check_dashboard_access()

    if not can_mark_correction_fixed():
        frappe.throw(
            _("You are not authorised to change downtime correction status."),
            frappe.PermissionError,
        )

    if str(fixed) not in ("0", "1"):
        frappe.throw(_("Invalid Fixed status."), frappe.ValidationError)

    fixed = int(fixed)

    row = frappe.get_doc("Mechanical Downtime sign-off child", child_row)

    if row.parenttype != "Mechanical Downtime sign-off":
        frappe.throw(
            _("Invalid downtime correction record."),
            frappe.PermissionError,
        )

    parent_site = frappe.db.get_value(
        "Mechanical Downtime sign-off",
        row.parent,
        "site",
    )

    if not parent_site:
        frappe.throw(
            _("Downtime correction site could not be verified."),
            frappe.PermissionError,
        )

    check_site_access(parent_site)

    if fixed_key not in valid_fixed_keys_for_child(row):
        frappe.throw(
            _("This correction is no longer valid. Refresh the dashboard."),
            frappe.ValidationError,
        )

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


@frappe.whitelist(methods=["POST"])
def set_verification_correction_fixed(verification_entry, fixed):
    check_dashboard_access()

    if not can_mark_correction_fixed():
        frappe.throw(
            _("You are not authorised to change downtime correction status."),
            frappe.PermissionError,
        )

    if str(fixed) not in ("0", "1"):
        frappe.throw(_("Invalid Fixed status."), frappe.ValidationError)

    target = frappe.db.sql(
        """
        SELECT
            v.name,
            v.parent,
            v.downtime_record,
            p.site,
            p.report_date,
            p.report_shift,
            p.verification_workflow_version
        FROM `tabDowntime Verification Entry` v
        INNER JOIN `tabMechanical Downtime sign-off` p
            ON p.name = v.parent
        WHERE v.name = %(entry)s
          AND v.parenttype = 'Mechanical Downtime sign-off'
          AND v.parentfield = 'downtime_verifications'
          AND TRIM(COALESCE(v.comments, '')) != ''
        """,
        {"entry": verification_entry},
        as_dict=True,
    )

    if len(target) != 1:
        frappe.throw(_("Invalid verification correction."), frappe.ValidationError)

    target = target[0]
    check_site_access(target.site)

    if int(target.verification_workflow_version or 0) != 1:
        frappe.throw(_("Verification workflow is not enabled."))

    rows = frappe.db.sql(
        """
        SELECT v.name
        FROM `tabDowntime Verification Entry` v
        INNER JOIN `tabMechanical Downtime sign-off` p
            ON p.name = v.parent
        WHERE v.parenttype = 'Mechanical Downtime sign-off'
          AND v.parentfield = 'downtime_verifications'
          AND p.verification_workflow_version = 1
          AND v.downtime_record = %(breakdown)s
          AND p.site = %(site)s
          AND p.report_date = %(date)s
          AND COALESCE(p.report_shift, '') = %(shift)s
          AND TRIM(COALESCE(v.comments, '')) != ''
        """,
        {
            "breakdown": target.downtime_record,
            "site": target.site,
            "date": target.report_date,
            "shift": target.report_shift or "",
        },
        as_dict=True,
    )

    if not rows or target.name not in {row.name for row in rows}:
        frappe.throw(_("Correction records are no longer valid."))

    from frappe.utils import now

    fixed_value = int(fixed)
    update = {
        "correction_fixed": fixed_value,
    }

    if fixed_value:
        update["correction_fixed_by"] = frappe.session.user
        update["correction_fixed_on"] = now()

    for row in rows:
        frappe.db.set_value(
            "Downtime Verification Entry",
            row.name,
            update,
        )

    return {"ok": 1}
