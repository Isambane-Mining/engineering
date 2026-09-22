import json
# Copyright (c) 2026, Isambane Mining (Pty) Ltd
# For license information, please see license.txt

import base64
import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, now_datetime, time_diff_in_hours, format_datetime
from frappe.utils.pdf import get_pdf
from frappe.utils.file_manager import save_file
from datetime import timedelta
from engineering.engineering.page.daily_availability_and_utilization_dashboard import (
    daily_availability_and_utilization_dashboard as daily_au_dashboard,
)


from engineering.engineering.doctype.availability_and_utilisation.availability_and_utilisation import (
    _exclusion_windows,
)


START_LOOKUP_DATETIME = get_datetime("2026-05-01 00:00:00")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
        {"label": _("Site"), "fieldname": "site", "fieldtype": "Data", "width": 140},
        {"label": _("Plant No."), "fieldname": "plant_no", "fieldtype": "Data", "width": 120},
        {"label": _("Plant Category"), "fieldname": "asset_category", "fieldtype": "Data", "width": 160},
        {"label": _("Breakdown/Maintenance Reason"), "fieldname": "breakdown_reason", "fieldtype": "Small Text", "width": 260},
        {"label": _("Resolution Summary"), "fieldname": "resolution_summary", "fieldtype": "Small Text", "width": 220},
        {"label": _("Breakdown/Maintenance Start Time"), "fieldname": "breakdown_start_datetime", "fieldtype": "Datetime", "width": 230},
        {"label": _("Datetime back in production"), "fieldname": "resolved_datetime", "fieldtype": "Datetime", "width": 220},
        {"label": _("Breakdown/Maintenance Hours"), "fieldname": "breakdown_hours", "fieldtype": "Float", "precision": 2, "width": 210},
        {"label": _("Open/Closed"), "fieldname": "open_closed", "fieldtype": "Data", "width": 120},
        {"label": _("Location"), "fieldname": "breakdown_location", "fieldtype": "Data", "width": 160},
        {"label": _("Comment"), "fieldname": "downtime_comment", "fieldtype": "Data", "width": 260},
    ]



def is_filter_set(value):
    value = str(value or "").strip()

    if not value:
        return False

    if value.lower() in ("all", "all sites", "undefined", "none", "null", "site"):
        return False

    return True


def normalise_shift(shift):
    shift = (shift or "").strip().lower()

    if shift in ("day", "day shift"):
        return "Day"

    if shift in ("night", "night shift"):
        return "Night"

    return ""


def get_report_windows(report_date, shift=None):
    shift = normalise_shift(shift)

    day_start = get_datetime(str(report_date) + " 06:00:00")
    day_end = get_datetime(str(report_date) + " 18:00:00")

    night_start = get_datetime(str(report_date) + " 18:00:00")
    night_end = get_datetime(str(report_date + timedelta(days=1)) + " 06:00:00")

    if shift == "Day":
        return [("Day", day_start, day_end)]

    if shift == "Night":
        return [("Night", night_start, night_end)]

    return [
        ("Day", day_start, day_end),
        ("Night", night_start, night_end),
    ]


def get_mpp_required_hours(site, report_date, shift=None):
    shift = normalise_shift(shift)

    planning_rows = frappe.get_all(
        "Monthly Production Planning",
        filters={
            "location": site,
            "site_status": "Producing",
            "prod_month_start_date": ["<=", report_date],
            "prod_month_end_date": [">=", report_date],
        },
        fields=["name"],
        limit=1,
    )

    if not planning_rows:
        return None

    planning_doc = frappe.get_doc(
        "Monthly Production Planning",
        planning_rows[0].name,
    )

    for day in planning_doc.month_prod_days:
        if getdate(day.shift_start_date) != getdate(report_date):
            continue

        if shift == "Day":
            return float(day.shift_day_hours or 0)

        if shift == "Night":
            return float(day.shift_night_hours or 0)

        return float(
            (day.shift_day_hours or 0)
            + (day.shift_night_hours or 0)
            + (day.shift_morning_hours or 0)
            + (day.shift_afternoon_hours or 0)
        )

    return None


def exclusion_windows(site, shift, window_start, window_end):
    shift = normalise_shift(shift)

    return _exclusion_windows(
        site,
        shift,
        window_start,
        window_end,
    )


def get_breakdown_history_intervals(site, plant_no, window_start, window_end):
    effective_window_start = max(window_start, START_LOOKUP_DATETIME)

    if window_end <= START_LOOKUP_DATETIME:
        return []

    base_filters = {
        "location": site,
        "asset_name": plant_no,
        "exclude_from_au": 0,
    }

    last_before = frappe.get_all(
        "Breakdown History",
        filters={**base_filters, "update_date_time": ["<", effective_window_start]},
        fields=["update_date_time", "breakdown_status"],
        order_by="update_date_time desc",
        limit=1,
    )

    events_in_window = frappe.get_all(
        "Breakdown History",
        filters={**base_filters, "update_date_time": ["between", [effective_window_start, window_end]]},
        fields=["update_date_time", "breakdown_status"],
        order_by="update_date_time asc",
    )

    intervals = []
    in_breakdown = False
    current_start = None

    if last_before and str(last_before[0].get("breakdown_status")) != "3":
        in_breakdown = True
        current_start = effective_window_start

    for event in events_in_window:
        event_time = get_datetime(event.get("update_date_time"))
        event_status = str(event.get("breakdown_status") or "")

        if event_status != "3" and not in_breakdown:
            in_breakdown = True
            current_start = event_time

        elif event_status == "3" and in_breakdown:
            clip_start = max(current_start, effective_window_start)
            clip_end = min(event_time, window_end)

            if clip_end > clip_start:
                intervals.append((clip_start, clip_end))

            in_breakdown = False
            current_start = None

    if in_breakdown and current_start:
        clip_start = max(current_start, effective_window_start)
        clip_end = window_end

        if clip_end > clip_start:
            intervals.append((clip_start, clip_end))

    return intervals


def calculate_availability_engine_breakdown_hours(site, plant_no, shift, window_start, window_end):
    if window_end <= START_LOOKUP_DATETIME:
        return 0.0

    effective_window_start = max(window_start, START_LOOKUP_DATETIME)

    intervals = get_breakdown_history_intervals(site, plant_no, effective_window_start, window_end)
    excluded = exclusion_windows(
        site,
        shift,
        effective_window_start,
        window_end,
    )

    effective_hours = 0.0

    for interval_start, interval_end in intervals:
        interval_hours = float(time_diff_in_hours(interval_end, interval_start))
        excluded_hours = 0.0

        for excluded_start, excluded_end in excluded:
            excluded_hours += overlap_hours(interval_start, interval_end, excluded_start, excluded_end)

        excluded_hours = min(excluded_hours, interval_hours)
        effective_hours += max(interval_hours - excluded_hours, 0.0)

    return round(max(effective_hours, 0), 2)


def get_availability_engine_hours(site, plant_no, report_date, shift=None):
    total_hours = 0.0

    for shift_name, window_start, window_end in get_report_windows(report_date, shift):
        total_hours += calculate_availability_engine_breakdown_hours(
            site,
            plant_no,
            shift_name,
            window_start,
            window_end,
        )

    return round(min(total_hours, 24), 2)



def get_open_closed_value(row):
    value = str(row.open_closed or "").strip()

    if value:
        return value

    if row.resolved_datetime:
        return "Closed"

    return "Open"


def get_summary_category_key(asset_category):
    value = str(asset_category or "").strip().lower()

    if "adt" in value or "articulated" in value or "dump truck" in value:
        return "adts"

    if "excavator" in value:
        return "excavators"

    if "dozer" in value:
        return "dozers"

    return ""


def blank_avail_util_summary():
    return {
        "adts": {
            "label": "ADT's",
            "availability": None,
            "utilisation": None,
            "working_hours": None,
            "breakdown_hours": None,
        },
        "excavators": {
            "label": "Excavators",
            "availability": None,
            "utilisation": None,
            "working_hours": None,
            "breakdown_hours": None,
        },
        "dozers": {
            "label": "Dozers",
            "availability": None,
            "utilisation": None,
            "working_hours": None,
            "breakdown_hours": None,
        },
    }


def get_avail_util_scope_summary(previous_date, site, machine_scope):
    """Use the same Engine rows and aggregation as the Daily A&U Dashboard."""
    rows = daily_au_dashboard.fetch_grouped_data(
        site,
        previous_date,
        previous_date,
        machine_scope,
        "100% A & U",
        "Isambane & Excavo Assets",
    ) or []

    summary = blank_avail_util_summary()
    shift_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and int(row.get("indent") or 0) == 3
        and not row.get("is_formula_row")
    ]

    for output_key in summary:
        category_rows = [
            row
            for row in shift_rows
            if get_summary_category_key(row.get("asset_category")) == output_key
        ]

        if not category_rows:
            continue

        engine_summary = daily_au_dashboard.au_engine.build_summary_row(
            category_rows,
            indent=0,
            asset_category=summary[output_key]["label"],
        )
        daily_au_dashboard.au_engine.apply_au_percentage_basis(
            [engine_summary],
            "100% A & U",
        )

        machine_totals = {}
        for row in category_rows:
            machine = row.get("asset_name") or row.get("plant_no")
            if not machine:
                continue

            totals = machine_totals.setdefault(
                machine,
                {"required": 0.0, "work": 0.0, "breakdown": 0.0},
            )
            totals["required"] += float(row.get("required_hours") or 0)
            totals["work"] += float(row.get("work_hours") or 0)
            totals["breakdown"] += float(row.get("pbm_total_downtime") or 0)

        valid_machines = [
            values
            for values in machine_totals.values()
            if values["required"] > 0
        ]

        summary[output_key].update({
            "availability": engine_summary.get("availability_percentage"),
            "utilisation": engine_summary.get("utilisation_percentage"),
            "working_hours": (
                round(sum(row["work"] for row in valid_machines) / len(valid_machines), 2)
                if valid_machines else None
            ),
            "breakdown_hours": (
                round(sum(row["breakdown"] for row in valid_machines) / len(valid_machines), 2)
                if valid_machines else None
            ),
        })

    return summary


def get_previous_day_breakdown_summary(previous_date, site=None):
    rows = get_data(frappe._dict({
        "report_date": previous_date,
        "site": site or "",
        "asset_category": "",
        "shift": "",
    })) or []

    summary = []

    for row in rows:
        summary.append({
            "plant_no": row.get("plant_no") or "",
            "reason": row.get("breakdown_reason") or "",
            "status": row.get("open_closed") or "",
            "start": row.get("breakdown_start_datetime") or "",
            "resolved": row.get("resolved_datetime") or "",
            "hours": row.get("breakdown_hours") or 0,
        })

    return summary


@frappe.whitelist()
def get_previous_day_avail_util_summary(report_date, site=None):
    previous_date = getdate(report_date) - timedelta(days=1)

    return {
        "previous_date": previous_date,
        "production": get_avail_util_scope_summary(previous_date, site, "Production Machines"),
        "spare": get_avail_util_scope_summary(previous_date, site, "Swing/Spare Machines"),
        "previous_day_breakdowns": get_previous_day_breakdown_summary(previous_date, site),
    }


def get_data(filters):
    report_date = getdate(filters.get("report_date")) if filters.get("report_date") else getdate(now_datetime())

    windows = get_report_windows(report_date, filters.get("shift"))
    window_start = windows[0][1]
    window_end = windows[-1][2]

    if window_end <= START_LOOKUP_DATETIME:
        return []

    conditions = [
        """
        (
            coalesce(nullif(pbm.breakdown_start_datetime, ''), pbm.creation) < %(window_end)s
            and
            (
                pbm.resolved_datetime is null
                or pbm.resolved_datetime = ''
                or pbm.resolved_datetime >= %(window_start)s
            )
            and
            (
                coalesce(nullif(pbm.breakdown_start_datetime, ''), pbm.creation) >= %(start_lookup_datetime)s
                or pbm.resolved_datetime >= %(start_lookup_datetime)s
            )
        )
        """,
    ]

    values = {
        "window_start": window_start,
        "window_end": window_end,
        "start_lookup_datetime": START_LOOKUP_DATETIME,
    }

    if is_filter_set(filters.get("site")):
        conditions.append("pbm.location = %(site)s")
        values["site"] = filters.get("site")

    if is_filter_set(filters.get("asset_category")):
        conditions.append("pbm.asset_category = %(asset_category)s")
        values["asset_category"] = filters.get("asset_category")

    rows = frappe.db.sql(
        f"""
        select
            pbm.name,
            pbm.location as site,
            pbm.location as breakdown_location,
            pbm.asset_name as plant_no,
            pbm.open_closed as open_closed,
            pbm.breakdown_reason as breakdown_reason,
            pbm.resolution_summary as resolution_summary,
            pbm.breakdown_start_datetime as breakdown_start_datetime,
            pbm.resolved_datetime as resolved_datetime,
            pbm.asset_category as asset_category,
            pbm.creation as creation
        from `tabPlant Breakdown or Maintenance` pbm
        where {" and ".join(conditions)}
        order by
            case
                when pbm.breakdown_start_datetime is not null then pbm.breakdown_start_datetime
                when pbm.resolved_datetime is not null then pbm.resolved_datetime
                else pbm.creation
            end desc,
            pbm.modified desc
        """,
        values,
        as_dict=True,
    )

    data = []
    hours_cache = {}

    for row in rows:

        cache_key = row.name


        if cache_key not in hours_cache:
            breakdown_start = (
                row.breakdown_start_datetime
                or row.creation
            )

            is_open = not row.resolved_datetime

            if is_open:
                clipped_start = max(
                    get_datetime(breakdown_start),
                    window_start,
                )

                clipped_end = min(
                    now_datetime(),
                    window_end,
                )
            else:
                clipped_start = max(
                    get_datetime(breakdown_start),
                    window_start,
                )

                clipped_end = min(
                    get_datetime(row.resolved_datetime),
                    window_end,
                )

            breakdown_hours = max(
                (
                    clipped_end - clipped_start
                ).total_seconds() / 3600,
                0,
            )

            hours_cache[cache_key] = round(
                max(breakdown_hours, 0),
                2,
            )

        data.append({
            "date": report_date,
            "site": row.site,
            "plant_no": row.plant_no,
            "open_closed": get_open_closed_value(row),
            "breakdown_location": row.get("breakdown_location"),
            "breakdown_reason": row.breakdown_reason,
            "resolution_summary": row.resolution_summary,
            "breakdown_start_datetime": row.breakdown_start_datetime,
            "resolved_datetime": row.resolved_datetime,
            "asset_category": row.asset_category,
            "breakdown_hours": hours_cache[cache_key],
            "breakdown_docname": row.name,
        })

    return data


@frappe.whitelist()
def save_downtime_signoff(
    report_date,
    site,
    asset_category,
    shift,
    signoff_section,
    signature,
    downtime_comments=None,
):
    report_date = getdate(report_date)
    signoff_shift = shift or ""
    report_shift = shift or "All Shifts"
    user = frappe.session.user
    roles = frappe.get_roles(user)
    full_name = frappe.db.get_value("User", user, "full_name") or user

    engineering_roles = [
        "Engineering Area Manager",
        "Engineering Foreman",
        "Engineering Manager",
        "Engineering Plant Manager",
        "Engineering Supervisor",
        "Engineering User",
    ]

    production_roles = [
        "Production Manager",
        "Production Supervisor",
        "Production Foreman",
        "Production User",
    ]

    is_engineering_user = any(
        role in roles for role in engineering_roles
    )

    is_production_user = any(
        role in roles for role in production_roles
    )

    signoff_section = str(signoff_section or "").strip()

    if signoff_section not in ("Engineering", "Production"):
        frappe.throw(_("Please select a valid sign-off section."))

    if signoff_section == "Engineering" and not is_engineering_user:
        frappe.throw(_(
            "You do not have permission to complete the Engineering sign-off."
        ))

    if signoff_section == "Production" and not is_production_user:
        frappe.throw(_(
            "You do not have permission to complete the Production sign-off."
        ))

    parent = get_or_create_signoff_parent(report_date, signoff_shift)
    row = get_or_create_signoff_row(parent, report_date, signoff_shift)

    formatted_downtime_comments = format_downtime_comments_for_signoff(
        downtime_comments
    )

    if signoff_section == "Engineering":
        row.date_time_e = now_datetime()
        row.shift_e = signoff_shift
        row.engineering_user = full_name
        row.engineering_signature = signature

        if formatted_downtime_comments:
            row.comments3 = formatted_downtime_comments

    elif signoff_section == "Production":
        row.date_time_p = now_datetime()
        row.shift_p = signoff_shift
        row.production_user = full_name
        row.production_signature = signature

        if formatted_downtime_comments:
            row.comments2 = formatted_downtime_comments

    parent.site = site
    parent.status = get_signoff_status(row)
    parent.save(ignore_permissions=True)

    new_name = make_signoff_name(row, report_date, report_shift, site)

    if parent.name != new_name:
        if frappe.db.exists("Mechanical Downtime sign-off", new_name):
            frappe.throw(_("A sign-off already exists with this name: {0}").format(new_name))

        frappe.rename_doc("Mechanical Downtime sign-off", parent.name, new_name, force=True)
        parent = frappe.get_doc("Mechanical Downtime sign-off", new_name)

    attach_signed_report_pdf(parent, report_date, site, asset_category, signoff_shift, downtime_comments)

    return _("Downtime sign-off saved. Status: {0}").format(parent.status)


def get_or_create_signoff_parent(report_date, shift):
    existing_parent = frappe.db.sql(
        """
        select distinct parent
        from `tabMechanical Downtime sign-off child`
        where parenttype = 'Mechanical Downtime sign-off'
            and (
                (
                    date(date_time_e) = %(report_date)s
                    and ifnull(shift_e, '') in (%(shift)s, '')
                )
                or
                (
                    date(date_time_p) = %(report_date)s
                    and ifnull(shift_p, '') in (%(shift)s, '')
                )
            )
        order by modified desc
        limit 1
        """,
        {
            "report_date": report_date,
            "shift": shift,
        },
    )

    if existing_parent:
        return frappe.get_doc(
            "Mechanical Downtime sign-off",
            existing_parent[0][0],
        )

    parent = frappe.new_doc("Mechanical Downtime sign-off")
    parent.status = "Open"
    parent.insert(ignore_permissions=True)

    return parent


def get_or_create_signoff_row(parent, report_date, shift):
    for row in parent.signoff_information:
        same_engineering = (
            row.date_time_e
            and getdate(row.date_time_e) == report_date
            and row.shift_e in (shift, None, "")
        )

        same_production = (
            row.date_time_p
            and getdate(row.date_time_p) == report_date
            and row.shift_p in (shift, None, "")
        )

        if same_engineering or same_production:
            return row

    row = parent.append("signoff_information", {})
    row.shift_e = shift
    row.shift_p = shift

    return row


def get_signoff_status(row):
    if row.engineering_signature and row.production_signature:
        return "Closed"

    return "Open"


def make_signoff_name(row, report_date, shift, site):
    production_user = row.production_user or "Pending Production"
    engineering_user = row.engineering_user or "Pending Engineering"
    shift = row.shift_e or row.shift_p or shift or "All Shifts"
    site = site or "All Sites"

    return clean_docname("{0}-{1}-{2}-{3}-{4}".format(
        site,
        production_user,
        engineering_user,
        report_date,
        shift,
    ))


def clean_docname(value):
    value = str(value or "").strip()
    value = value.replace("/", "-")
    value = value.replace("\\", "-")
    value = value.replace(":", "-")
    value = value.replace("\n", " ")
    value = " ".join(value.split())

    return value




def format_downtime_comments_for_signoff(downtime_comments=None):
    if isinstance(downtime_comments, str):
        downtime_comments = frappe.parse_json(downtime_comments) or {}

    downtime_comments = downtime_comments or {}

    lines = []

    for plant_no, comment in downtime_comments.items():
        plant_no = str(plant_no or "").strip()
        comment = str(comment or "").strip()

        if plant_no and comment:
            lines.append("{0}\n{1}".format(plant_no, comment))

    return "\n\n".join(lines)


def get_pdf_downtime_comments_map(downtime_comments=None, signoff_row=None):
    comments = {}

    if isinstance(downtime_comments, str):
        downtime_comments = frappe.parse_json(downtime_comments) or {}

    for plant_no, comment in (downtime_comments or {}).items():
        plant_no = str(plant_no or "").strip()
        comment = str(comment or "").strip()

        if plant_no and comment:
            comments.setdefault(plant_no, []).append({
                "source": "Current User",
                "comment": comment,
            })

    if comments:
        return comments

    if not signoff_row:
        return comments

    comment_groups = [
        ("Information Officer", getattr(signoff_row, "comments1", "")),
        ("Production Manager", getattr(signoff_row, "comments2", "")),
        ("Engineering Manager", getattr(signoff_row, "comments3", "")),
    ]

    for source, stored_comments in comment_groups:
        stored_comments = str(stored_comments or "").strip()

        if not stored_comments:
            continue

        blocks = [block.strip() for block in stored_comments.split("\n\n") if block.strip()]

        for block in blocks:
            lines = [line.strip() for line in block.split("\n") if line.strip()]

            if len(lines) >= 2:
                plant_no = lines[0]
                comment = "\n".join(lines[1:]).strip()

                if plant_no and comment:
                    comments.setdefault(plant_no, []).append({
                        "source": source,
                        "comment": comment,
                    })

    return comments


def attach_signed_report_pdf(parent, report_date, site, asset_category, shift, downtime_comments=None):
    filters = frappe._dict({
        "report_date": report_date,
        "site": site,
        "asset_category": asset_category,
        "shift": shift,
    })

    columns = get_columns()
    data = get_data(filters)

    signoff_row = parent.signoff_information[0] if parent.signoff_information else None

    avail_util_summary = get_previous_day_avail_util_summary(report_date, site)

    html = get_signed_report_html(
        parent=parent,
        report_date=report_date,
        site=site,
        asset_category=asset_category,
        shift=shift,
        columns=columns,
        data=data,
        signoff_row=signoff_row,
        downtime_comments=downtime_comments,
        avail_util_summary=avail_util_summary,
    )

    file_name = "Down Time {0} {1}.pdf".format(
        report_date,
        shift or "All Shifts",
    )

    pdf_file = get_pdf(html)

    file_doc = save_file(
        file_name,
        pdf_file,
        "Mechanical Downtime sign-off",
        parent.name,
        is_private=1,
    )

    parent.db_set("signed_report_excel", file_doc.file_url, update_modified=False)





def get_signed_report_html(parent, report_date, site, asset_category, shift, columns, data, signoff_row, downtime_comments=None, avail_util_summary=None):
    production_signature = signoff_row.production_signature if signoff_row else ""
    engineering_signature = signoff_row.engineering_signature if signoff_row else ""
    information_officer = signoff_row.information_officer if signoff_row else ""
    information_officer_date_time = format_datetime(signoff_row.date_time_io) if signoff_row and signoff_row.date_time_io else ""
    information_officer_signature = signoff_row.information_officer_signature if signoff_row else ""

    production_user = signoff_row.production_user if signoff_row else ""
    engineering_user = signoff_row.engineering_user if signoff_row else ""

    production_date_time = format_datetime(signoff_row.date_time_p) if signoff_row and signoff_row.date_time_p else ""
    engineering_date_time = format_datetime(signoff_row.date_time_e) if signoff_row and signoff_row.date_time_e else ""

    return """
    <html>
        <head>
            <style>
                @page {{
                    size: A4 portrait;
                    margin: 12mm 13mm 14mm 13mm;
                }}

                body {{
                    font-family: Arial, sans-serif;
                    color: #111;
                    font-size: 10px;
                }}

                .header-img {{
                    width: 100%;
                    height: auto;
                    margin-bottom: 16px;
                    display: block;
                }}

                .report-title {{
                    text-align: center;
                    font-size: 19px;
                    font-weight: 800;
                    text-transform: uppercase;
                    border: 2px solid #111;
                    background: #f2f2f2;
                    padding: 9px;
                    margin-bottom: 14px;
                }}

                .meta-table {{
                    width: 100%;
                    border-collapse: separate;
                    border-spacing: 0;
                    border: 1px solid #d9d9d9;
                    border-radius: 8px;
                    overflow: hidden;
                    margin-bottom: 20px;
                }}

                .meta-table td {{
                    padding: 8px;
                    border-right: 1px solid #d9d9d9;
                    font-size: 10px;
                }}

                .meta-table td:last-child {{
                    border-right: none;
                }}

                .sign-table {{
                    width: 100%;
                    border-collapse: separate;
                    border-spacing: 12px 0;
                    margin-bottom: 20px;
                    page-break-inside: avoid;
                }}

                .sign-box {{
                    width: 33.33%;
                    border: 1px solid #d9d9d9;
                    border-radius: 8px;
                    padding: 12px;
                    min-height: 92px;
                    vertical-align: top;
                }}

                .sign-title {{
                    font-size: 14px;
                    font-weight: 800;
                    margin-bottom: 8px;
                }}

                .signature-img {{
                    max-height: 45px;
                    max-width: 230px;
                    margin-top: 8px;
                }}

                .pending {{
                    font-style: italic;
                    margin-top: 22px;
                }}

                .record-card {{
                    width: 100%;
                    border-collapse: separate;
                    border-spacing: 0;
                    border: 1px solid #d9d9d9;
                    border-radius: 8px;
                    overflow: hidden;
                    margin-bottom: 14px;
                    page-break-inside: auto;
                    page-break-after: auto;
                }}

                .record-card th {{
                    background: #f2f2f2;
                    border-bottom: 1px solid #d9d9d9;
                    padding: 8px;
                    text-align: left;
                    font-size: 10px;
                }}

                .record-card td {{
                    border-bottom: 1px solid #d9d9d9;
                    border-right: 1px solid #d9d9d9;
                    padding: 8px;
                    vertical-align: top;
                    line-height: 1.35;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                    white-space: pre-wrap;
                }}

                .record-card td:last-child {{
                    border-right: none;
                }}

                .record-card tr {{
                    page-break-inside: avoid;
                }}

                .label-cell {{
                    width: 18%;
                    font-weight: 800;
                    background: #fafafa;
                }}

                .value-cell {{
                    width: 32%;
                }}

                .au-red {{
                    background: #ffe5e5;
                    color: #a8071a;
                    font-weight: 800;
                }}

                .au-yellow {{
                    background: #fff7d6;
                    color: #ad6800;
                    font-weight: 800;
                }}

                .au-green {{
                    background: #e6f7e6;
                    color: #237804;
                    font-weight: 800;
                }}

                .au-na {{
                    background: #f5f5f5;
                    color: #8c8c8c;
                    font-weight: 800;
                }}

            </style>
        </head>

        <body>
            {header_html}

            <div class="report-title">TMM Equipment Downtime Verification</div>

            <table class="meta-table">
                <tr>
                    <td><b>Date:</b> {report_date}</td>
                    <td><b>Site:</b> {site}</td>
                    <td><b>Shift:</b> {shift}</td>
                    <td><b>Status:</b> {status}</td>
                </tr>
            </table>

            {avail_util_html}

            <div class="report-title" style="font-size:13px;margin-top:8px;">TMM EQUIPMENT DOWNTIME</div>

            {downtime_cards}

            <table class="sign-table">
                <tr>
                    <td class="sign-box">
                        <div class="sign-title">Information Officer Sign-off</div>
                        <b>User:</b> {information_officer}<br>
                        <b>Date/Time:</b> {information_officer_date_time}<br>
                        {information_officer_signature_html}
                    </td>
                    <td class="sign-box">
                        <div class="sign-title">Production Sign-off</div>
                        <b>User:</b> {production_user}<br>
                        <b>Date/Time:</b> {production_date_time}<br>
                        {production_signature_html}
                    </td>
                    <td class="sign-box">
                        <div class="sign-title">Engineering Sign-off</div>
                        <b>User:</b> {engineering_user}<br>
                        <b>Date/Time:</b> {engineering_date_time}<br>
                        {engineering_signature_html}
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """.format(
        header_html=get_pdf_header_image_html(),
        report_date=frappe.utils.escape_html(str(report_date)),
        site=frappe.utils.escape_html(site or "All Sites"),
        shift=frappe.utils.escape_html(shift or "All Shifts"),
        status=frappe.utils.escape_html(parent.status or ""),
        information_officer=frappe.utils.escape_html(information_officer or ""),
        information_officer_date_time=frappe.utils.escape_html(str(information_officer_date_time or "")),
        information_officer_signature_html=get_signature_html(information_officer_signature),
        production_user=frappe.utils.escape_html(production_user or ""),
        engineering_user=frappe.utils.escape_html(engineering_user or ""),
        production_date_time=frappe.utils.escape_html(production_date_time or ""),
        engineering_date_time=frappe.utils.escape_html(engineering_date_time or ""),
        production_signature_html=get_signature_html(production_signature),
        engineering_signature_html=get_signature_html(engineering_signature),
        avail_util_html=get_avail_util_pdf_html(avail_util_summary),
        downtime_cards=get_downtime_cards_html(data, downtime_comments, signoff_row),
    )

def get_avail_util_pdf_html(summary):
    if not summary:
        return ""

    previous_date = frappe.utils.escape_html(str(summary.get("previous_date") or ""))
    production = summary.get("production") or {}
    spare = summary.get("spare") or {}

    return """
        <div class="report-title" style="font-size:13px;margin-top:8px;">Previous Day Availability and Utilisation {previous_date}</div>

        <table style="width:100%; border-collapse:separate; border-spacing:10px 0; margin-bottom:14px;">
            <tr>
                <td style="width:50%; vertical-align:top;">
                    {production_html}
                </td>
                <td style="width:50%; vertical-align:top;">
                    {spare_html}
                </td>
            </tr>
        </table>
    """.format(
        previous_date="({0})".format(previous_date) if previous_date else "",
        production_html=get_avail_util_pdf_scope_html(
            "Production Machine Availability and Utilisation",
            production,
        ),
        spare_html=get_avail_util_pdf_scope_html(
            "Spare Machine Availability and Utilisation",
            spare,
        ),
    )


def get_avail_util_pdf_scope_html(title, rows):
    return """
        <table class="record-card" style="margin-bottom:0;">
            <thead>
                <tr>
                    <th colspan="3">{title}</th>
                </tr>
                <tr>
                    <th>Machine Type</th>
                    <th>Availability</th>
                    <th>Utilisation</th>
                </tr>
            </thead>
            <tbody>
                <tr>{adt_html}</tr>
                <tr>{excavator_html}</tr>
                <tr>{dozer_html}</tr>
            </tbody>
        </table>
    """.format(
        title=frappe.utils.escape_html(title),
        adt_html=get_avail_util_pdf_cells(rows.get("adts")),
        excavator_html=get_avail_util_pdf_cells(rows.get("excavators")),
        dozer_html=get_avail_util_pdf_cells(rows.get("dozers")),
    )


def get_avail_util_pdf_cells(row):
    row = row or {}
    availability = row.get("availability")
    utilisation = row.get("utilisation")

    return """
        <td>{label}</td>
        <td class="{availability_class}">{availability}</td>
        <td class="{utilisation_class}">{utilisation}</td>
    """.format(
        label=frappe.utils.escape_html(str(row.get("label") or "")),
        availability=frappe.utils.escape_html(format_pdf_percent(availability)),
        utilisation=frappe.utils.escape_html(format_pdf_percent(utilisation)),
        availability_class=get_pdf_avail_util_colour_class(availability, "availability"),
        utilisation_class=get_pdf_avail_util_colour_class(utilisation, "utilisation"),
    )

def get_pdf_avail_util_colour_class(value, value_type):
    if value is None or value == "":
        return "au-na"

    percent = float(value or 0)

    if value_type == "availability":
        if percent <= 75:
            return "au-red"

        if percent <= 84:
            return "au-yellow"

        return "au-green"

    if percent <= 70:
        return "au-red"

    if percent <= 79:
        return "au-yellow"

    return "au-green"

def format_pdf_percent(value):
    if value is None or value == "":
        return "N/A"

    return "{0:.1f}%".format(float(value or 0))

def get_pdf_header_image_html():
    header_path = frappe.get_app_path(
        "engineering",
        "public",
        "images",
        "isambane_header.png",
    )

    try:
        with open(header_path, "rb") as header_file:
            encoded_header = base64.b64encode(header_file.read()).decode("utf-8")

        return '<img class="header-img" src="data:image/png;base64,{0}">'.format(encoded_header)
    except Exception:
        return ""


def get_pdf_comment_html(comment_rows):
    comment_rows = comment_rows or []

    if not comment_rows:
        return ""

    html = []

    for row in comment_rows:
        html.append("""
            <div style="margin-bottom:8px;">
                <div style="font-weight:800; margin-bottom:3px;">{source}</div>
                <div>{comment}</div>
            </div>
        """.format(
            source=frappe.utils.escape_html(str(row.get("source") or "")),
            comment=frappe.utils.escape_html(str(row.get("comment") or "")),
        ))

    return "".join(html)


def get_downtime_cards_html(data, downtime_comments=None, signoff_row=None):
    downtime_comments = get_pdf_downtime_comments_map(downtime_comments, signoff_row)
    if not data:
        return """
            <table class="record-card">
                <thead>
                    <tr>
                        <th>No downtime records found.</th>
                    </tr>
                </thead>
            </table>
        """

    cards = []

    for row in data:
        cards.append("""
            <table class="record-card">
                <thead>
                    <tr>
                        <th colspan="4">{plant_no} | {asset_category} | {status} | {hours} hrs</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td class="label-cell">Start</td>
                        <td class="value-cell">{start}</td>
                        <td class="label-cell">Back In Production</td>
                        <td class="value-cell">{resolved}</td>
                    </tr>
                    <tr>
                        <td class="label-cell">Reason</td>
                        <td colspan="3">{reason}</td>
                    </tr>
                    <tr>
                        <td class="label-cell">Resolution</td>
                        <td colspan="3">{resolution}</td>
                    </tr>
                    <tr>
                        <td class="label-cell">Comment</td>
                        <td colspan="3">{comment}</td>
                    </tr>
                </tbody>
            </table>
        """.format(
            plant_no=frappe.utils.escape_html(str(row.get("plant_no") or "")),
            asset_category=frappe.utils.escape_html(str(row.get("asset_category") or "")),
            status=frappe.utils.escape_html(str(row.get("open_closed") or "")),
            hours=frappe.utils.escape_html(str(row.get("breakdown_hours") or "")),
            start=frappe.utils.escape_html(str(row.get("breakdown_start_datetime") or "")),
            resolved=frappe.utils.escape_html(str(row.get("resolved_datetime") or "")),
            reason=frappe.utils.escape_html(str(row.get("breakdown_reason") or "")),
            resolution=frappe.utils.escape_html(str(row.get("resolution_summary") or "")),
            comment=get_pdf_comment_html(downtime_comments.get(row.get("plant_no"))),
        ))

    return "".join(cards)


def get_signature_html(signature):
    if not signature:
        return '<div class="pending">Pending signature</div>'

    if str(signature).startswith("data:image"):
        return '<img class="signature-img" src="{0}">'.format(signature)

    return '<img class="signature-img" src="{0}">'.format(frappe.utils.escape_html(signature))





DAILY_DOWNTIME_SITE_CHANNELS = {
    "Koppie": "Isambane Mining-kop-hourly-downtime-reporting",
    "Kriel Rehabilitation": "Isambane Mining-krl-hourly-downtime-reporting",
    "Klipfontein": "Isambane Mining-klp-hourly-downtime-reporting",
    "Gwab": "Isambane Mining-gwb-hourly-downtime-reporting",
    "Bankfontein": "Isambane Mining-bnk-hourly-downtime-reporting",
    "Uitgevallen": "Isambane Mining-uit-hourly-downtime-reporting",
}

def build_daily_downtime_message(report_date, site, shift):
    data = get_data(frappe._dict({
        "report_date": report_date,
        "site": site,
        "asset_category": "",
        "shift": shift,
    }))

    total_records = len(data)
    total_hours = round(sum(float(row.get("breakdown_hours") or 0) for row in data), 2)
    open_records = len([row for row in data if str(row.get("open_closed") or "").lower() == "open"])
    closed_records = total_records - open_records

    if shift == "Day Shift":
        shift_period = "06:00 TO 18:00"
    elif shift == "Full Daily":
        shift_period = "06:00 TO 06:00"
    else:
        shift_period = "18:00 TO 06:00"

    lines = [
        f"{site.upper()} DAILY DOWNTIME REPORT",
        str(report_date),
        shift.upper(),
        shift_period,
        "",
        f"Records: {total_records}",
        f"Total Hours: {total_hours}",
        f"Open: {open_records}",
        f"Closed: {closed_records}",
        "",
    ]

    if not data:
        lines.append("No downtime records found for this shift.")
        return "\n".join(lines), data

    for row in data:
        plant_no = row.get("plant_no") or "-"
        asset_category = row.get("asset_category") or "-"
        hours = row.get("breakdown_hours") or 0
        status = row.get("open_closed") or "-"
        reason = row.get("breakdown_reason") or "-"
        start = row.get("breakdown_start_datetime") or "-"
        resolved = row.get("resolved_datetime") or "OPEN"
        resolution = row.get("resolution_summary") or "-"

        lines.extend([
            f"{plant_no} - {asset_category} - {hours} HRS - {status}",
            f"Reason: {str(reason).upper()}",
            f"Start: {start}",
            f"Back in Production: {resolved}",
            f"Resolution: {resolution}",
            "",
        ])

    return "\n".join(lines), data


def create_daily_downtime_summary(site, report_date, shift):
    import json

    channel_id = DAILY_DOWNTIME_SITE_CHANNELS.get(site)

    if not channel_id:
        frappe.throw(f"No Raven channel configured for site: {site}")

    summary_message, data = build_daily_downtime_message(report_date, site, shift)

    existing = frappe.db.exists("Daily Downtime Summary", {
        "site": site,
        "report_date": report_date,
        "shift": shift,
    })

    if existing:
        return existing

    doc = frappe.get_doc({
        "doctype": "Daily Downtime Summary",
        "site": site,
        "report_date": report_date,
        "day": report_date,
        "shift": shift,
        "channel_id": channel_id,
        "summary_message": summary_message,
        "report_data_json": json.dumps(data, default=str),
        "sent_to_raven": 0,
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


def create_daily_downtime_summaries(shift):
    today = getdate(now_datetime())

    if shift in ("Night Shift", "Full Daily"):
        report_date = today - timedelta(days=1)
    else:
        report_date = today

    created = []

    for site in DAILY_DOWNTIME_SITE_CHANNELS:
        try:
            created.append(create_daily_downtime_summary(site, report_date, shift))
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Daily Downtime Summary failed for {site} {shift}"
            )

    return created


@frappe.whitelist()
def send_daily_downtime_day_shift():
    return create_daily_downtime_summaries("Day Shift")


@frappe.whitelist()
def send_daily_downtime_night_shift():
    return create_daily_downtime_summaries("Night Shift")


@frappe.whitelist()
def send_full_daily_downtime_summary():
    return create_daily_downtime_summaries("Full Daily")

# === DOWNTIME SELECTED DATE PRINT PREVIEW V3 START ===

def _dt_v3_filter_is_set(value):
    value = str(value or "").strip()

    if not value:
        return False

    return value.lower() not in (
        "all",
        "all sites",
        "all equipment",
        "undefined",
        "none",
        "null",
        "site",
        "asset category",
    )


def _dt_v3_normalise_shift(shift):
    value = str(shift or "").strip().lower()

    if value in ("day", "day shift"):
        return "Day"

    if value in ("night", "night shift"):
        return "Night"

    return ""


def _dt_v3_selected_window(report_date, shift=None):
    from datetime import timedelta as _timedelta
    from frappe.utils import (
        getdate as _getdate,
        get_datetime as _get_datetime,
    )

    selected_date = _getdate(report_date)
    next_date = selected_date + _timedelta(days=1)

    shift_key = _dt_v3_normalise_shift(shift)

    if shift_key == "Day":
        start = _get_datetime(
            f"{selected_date} 06:00:00"
        )

        end = _get_datetime(
            f"{selected_date} 18:00:00"
        )

        heading = "DAY SHIFT SELECTED"
        shift_label = "Day Shift"

        footer = (
            "Downtime after 18:00 not included "
            "in Day Shift"
        )

    elif shift_key == "Night":
        start = _get_datetime(
            f"{selected_date} 18:00:00"
        )

        end = _get_datetime(
            f"{next_date} 06:00:00"
        )

        heading = "NIGHT SHIFT SELECTED"
        shift_label = "Night Shift"

        footer = (
            "Night Shift includes downtime from "
            "18:00 to 06:00 next day"
        )

    else:
        start = _get_datetime(
            f"{selected_date} 06:00:00"
        )

        end = _get_datetime(
            f"{next_date} 06:00:00"
        )

        heading = "BOTH SHIFTS SELECTED"
        shift_label = "Both Shifts"

        footer = (
            "24 Hour Cycle: 06:00 to 06:00 next day"
        )

    return {
        "selected_date": selected_date,
        "shift": shift_label,
        "heading": heading,
        "footer": footer,
        "window_start": start,
        "window_end": end,
    }


def _dt_v3_hmm(minutes):
    try:
        minutes = int(round(float(minutes or 0)))
    except Exception:
        minutes = 0

    minutes = max(minutes, 0)

    hours = minutes // 60
    remainder = minutes % 60

    return f"{hours}:{remainder:02d}"


def _dt_v3_datetime_text(value):
    if not value:
        return ""

    from frappe.utils import get_datetime as _get_datetime

    return _get_datetime(value).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _dt_v3_get_selected_rows(
    report_date=None,
    site=None,
    asset_category=None,
    shift=None,
):
    import frappe as _frappe

    from frappe.utils import (
        getdate as _getdate,
        get_datetime as _get_datetime,
        now_datetime as _now_datetime,
    )

    if report_date:
        report_date = _getdate(report_date)
    else:
        report_date = _getdate(
            _now_datetime()
        )

    window = _dt_v3_selected_window(
        report_date,
        shift,
    )

    window_start = window["window_start"]
    window_end = window["window_end"]

    conditions = [
        """
        (
            coalesce(
                nullif(
                    pbm.breakdown_start_datetime,
                    ''
                ),
                pbm.creation
            ) < %(window_end)s

            and

            (
                pbm.resolved_datetime is null
                or pbm.resolved_datetime = ''
                or pbm.resolved_datetime > %(window_start)s
            )
        )
        """
    ]

    values = {
        "window_start": window_start,
        "window_end": window_end,
    }

    if _dt_v3_filter_is_set(site):
        conditions.append(
            "pbm.location = %(site)s"
        )

        values["site"] = site

    if _dt_v3_filter_is_set(asset_category):
        conditions.append(
            "pbm.asset_category = %(asset_category)s"
        )

        values["asset_category"] = asset_category

    raw_rows = _frappe.db.sql(
        f"""
        select
            pbm.name as pbm_document,
            pbm.location as site,
            pbm.asset_name as fleet_no,
            pbm.asset_category as asset_category,
            pbm.breakdown_reason as reason,
            pbm.open_closed as open_closed,
            pbm.breakdown_start_datetime
                as breakdown_start_datetime,
            pbm.resolved_datetime
                as resolved_datetime,
            pbm.creation as creation
        from `tabPlant Breakdown or Maintenance` pbm
        where {" and ".join(conditions)}
        order by
            coalesce(
                nullif(
                    pbm.breakdown_start_datetime,
                    ''
                ),
                pbm.creation
            ) asc,
            pbm.asset_name asc,
            pbm.name asc
        """,
        values,
        as_dict=True,
    )

    rows = []

    for row in raw_rows:
        actual_start = (
            row.get("breakdown_start_datetime")
            or row.get("creation")
        )

        if not actual_start:
            continue

        actual_start_dt = _get_datetime(
            actual_start
        )

        actual_resolved = row.get(
            "resolved_datetime"
        )

        resolved_dt = (
            _get_datetime(actual_resolved)
            if actual_resolved
            else None
        )

        effective_end = (
            resolved_dt
            if resolved_dt
            else window_end
        )

        clipped_start = max(
            actual_start_dt,
            window_start,
        )

        clipped_end = min(
            effective_end,
            window_end,
        )

        if clipped_end <= clipped_start:
            continue

        seconds = (
            clipped_end - clipped_start
        ).total_seconds()

        minutes = int(
            round(seconds / 60.0)
        )

        if minutes <= 0:
            continue

        status = str(
            row.get("open_closed") or ""
        ).strip()

        if not status:
            status = (
                "Closed"
                if resolved_dt
                else "Open"
            )

        rows.append({
            "pbm_document":
                row.get("pbm_document") or "",

            "fleet_no":
                row.get("fleet_no") or "",

            "reason":
                row.get("reason") or "",

            "status":
                status,

            "downtime":
                _dt_v3_hmm(minutes),

            "downtime_minutes":
                minutes,

            "start":
                _dt_v3_datetime_text(
                    row.get(
                        "breakdown_start_datetime"
                    )
                ),

            "back_in_production":
                _dt_v3_datetime_text(
                    actual_resolved
                ),

            "site":
                row.get("site") or "",

            "asset_category":
                row.get("asset_category") or "",
        })

    return {
        "selected_date":
            str(window["selected_date"]),

        "site":
            (
                str(site).strip()
                if _dt_v3_filter_is_set(site)
                else "All Sites"
            ),

        "asset_category":
            (
                str(asset_category).strip()
                if _dt_v3_filter_is_set(
                    asset_category
                )
                else "All Equipment"
            ),

        "shift":
            window["shift"],

        "heading":
            window["heading"],

        "footer":
            window["footer"],

        "window_start":
            _dt_v3_datetime_text(
                window_start
            ),

        "window_end":
            _dt_v3_datetime_text(
                window_end
            ),

        "rows":
            rows,
    }


@frappe.whitelist()
def get_selected_downtime_print_data(
    report_date=None,
    site=None,
    asset_category=None,
    shift=None,
):
    return _dt_v3_get_selected_rows(
        report_date=report_date,
        site=site,
        asset_category=asset_category,
        shift=shift,
    )


@frappe.whitelist()
def export_selected_downtime_excel(
    report_date=None,
    site=None,
    asset_category=None,
    shift=None,
):
    import frappe as _frappe

    from frappe.utils.xlsxutils import (
        make_xlsx as _make_xlsx,
    )

    data = _dt_v3_get_selected_rows(
        report_date=report_date,
        site=site,
        asset_category=asset_category,
        shift=shift,
    )

    excel_rows = [
        [data["heading"]],
        [
            "{} -> {}".format(
                data["window_start"],
                data["window_end"],
            )
        ],
        [],
        [
            "Fleet No.",
            "Reason",
            "Status",
            "Downtime",
            "Start",
            "Back in Production",
        ],
    ]

    for row in data["rows"]:
        excel_rows.append([
            row["fleet_no"],
            row["reason"],
            row["status"],
            row["downtime"],
            row["start"],
            row["back_in_production"],
        ])

    excel_rows.extend([
        [],
        [f"({data['footer']})"],
    ])

    workbook = _make_xlsx(
        excel_rows,
        "Downtime",
    )

    shift_file = (
        data["shift"]
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
    )

    filename = (
        "Downtime_{}_{}.xlsx".format(
            data["selected_date"],
            shift_file,
        )
    )

    _frappe.local.response.filename = filename

    _frappe.local.response.filecontent = (
        workbook.getvalue()
    )

    _frappe.local.response.type = "binary"


# === DOWNTIME SELECTED DATE PRINT PREVIEW V3 END ===


@frappe.whitelist()
def get_saved_downtime_summary(doctype, name):
    """Return one saved Hourly or Daily Downtime Summary."""

    allowed_doctypes = {
        "Hourly Downtime Summary",
        "Daily Downtime Summary",
    }

    if doctype not in allowed_doctypes:
        frappe.throw("Invalid downtime summary type.")

    if not name:
        frappe.throw("Please select a downtime report.")

    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")

    try:
        report_rows = json.loads(
            doc.get("report_data_json") or "[]"
        )
    except (TypeError, ValueError):
        report_rows = []

    return {
        "name": doc.name,
        "doctype": doctype,
        "site": doc.get("site"),
        "report_date": doc.get("report_date"),
        "hour_slot": doc.get("hour_slot"),
        "shift": doc.get("shift"),
        "summary_message": doc.get("summary_message") or "",
        "report_rows": report_rows,
    }


@frappe.whitelist()
def get_saved_downtime_summary_options(site):
    """Return saved Hourly and Daily reports for one site only."""

    site = str(site or "").strip()

    if not site:
        return {
            "hourly": [],
            "daily": [],
        }

    hourly = frappe.get_list(
        "Hourly Downtime Summary",
        filters={"site": site},
        fields=[
            "name",
            "site",
            "report_date",
            "hour_slot",
        ],
        order_by="report_date desc, creation desc",
        limit_page_length=200,
    )

    daily = frappe.get_list(
        "Daily Downtime Summary",
        filters={"site": site},
        fields=[
            "name",
            "site",
            "report_date",
            "shift",
        ],
        order_by="report_date desc, creation desc",
        limit_page_length=100,
    )

    return {
        "hourly": hourly,
        "daily": daily,
    }
