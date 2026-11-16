import calendar
from datetime import datetime

import frappe

from engineering.engineering.page.downtime_correction_dashboard.downtime_correction_dashboard import (
    get_allowed_sites,
)


def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)
    chart = get_chart_data(data)
    summary = get_report_summary(data)

    return columns, data, None, chart, summary


def get_columns():
    return [
        {"label": "Date", "fieldname": "report_datetime_display", "fieldtype": "Data", "width": 145},
        {"label": "Machine Model", "fieldname": "machine_model", "fieldtype": "Data", "width": 155},
        {"label": "Fleet Number", "fieldname": "fleet_number", "fieldtype": "Data", "width": 125},
        {"label": "Pre-Use No.", "fieldname": "pre_use_no", "fieldtype": "Int", "width": 120},
        {"label": "Recurring Deviation", "fieldname": "recurring_deviation", "fieldtype": "Data", "width": 155},
        {"label": "Deviation Details", "fieldname": "deviation_details", "fieldtype": "Data", "width": 260},
        {"label": "Reported By", "fieldname": "reported_by_name_and_surname", "fieldtype": "Data", "width": 205},
        {"label": "Action", "fieldname": "action", "fieldtype": "Data", "width": 190},
        {"label": "Action Date and Time", "fieldname": "action_date_and_time_display", "fieldtype": "Data", "width": 160},
        {"label": "Date Service Report Received", "fieldname": "date_service_report_received_display", "fieldtype": "Data", "width": 195},
        {"label": "Job Card Number", "fieldname": "job_card_number", "fieldtype": "Data", "width": 155},
        {"label": "Resolution Summary", "fieldname": "resolution_summary", "fieldtype": "Data", "width": 220},
        {"label": "Actioned By Name and Surname", "fieldname": "actioned_by_name_and_surname", "fieldtype": "Data", "width": 235},
        {"label": "Action Status", "fieldname": "action_status_badge", "fieldtype": "Data", "width": 120},
        {"label": "Completion Percentage", "fieldname": "completion_percentage_badge", "fieldtype": "Data", "width": 150},
    ]


def get_data(filters):
    filters = filters or {}

    if not frappe.has_permission("Pre Use Deviation", "read"):
        frappe.throw(
            "You do not have permission to read Pre Use Deviations.",
            frappe.PermissionError,
        )

    allowed_sites = get_allowed_sites()
    selected_site = filters.get("site")

    query_filters = []

    if selected_site and selected_site != "All Sites":
        if allowed_sites and selected_site not in allowed_sites:
            frappe.throw(
                "You do not have permission to view this site.",
                frappe.PermissionError,
            )
        query_filters.append(["site", "=", selected_site])
    elif allowed_sites:
        query_filters.append(["site", "in", allowed_sites])

    if filters.get("fleet_number"):
        query_filters.append([
            "fleet_number", "=", filters["fleet_number"]
        ])

    operating_status = filters.get("operating_status")
    if operating_status and operating_status != "All Statuses":
        query_filters.append([
            "operating_status", "=", operating_status
        ])

    if filters.get("action_status"):
        query_filters.append([
            "action_status", "=", filters["action_status"]
        ])

    year_value = filters.get("year")
    month_value = filters.get("month")

    if month_value and not year_value:
        frappe.throw("Select a year when filtering by month.")

    if year_value:
        year = int(year_value)

        if year < 1900 or year > 9999:
            frappe.throw("Invalid report year.")

        if month_value:
            try:
                month = list(calendar.month_name).index(month_value)
            except ValueError:
                frappe.throw("Invalid report month.")

            if month == 0:
                frappe.throw("Invalid report month.")

            last_day = calendar.monthrange(year, month)[1]
            start_date = f"{year:04d}-{month:02d}-01"
            end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
        else:
            start_date = f"{year:04d}-01-01"
            end_date = f"{year:04d}-12-31"

        query_filters.extend([
            ["report_datetime", ">=", start_date + " 00:00:00"],
            ["report_datetime", "<=", end_date + " 23:59:59"],
        ])

    fields = [
        "name",
        "report_datetime",
        "site",
        "machine_model",
        "fleet_number",
        "pre_use_no",
        "recurring_deviation",
        "deviation_details",
        "reported_by_name_and_surname",
        "action",
        "action_date_and_time",
        "date_service_report_received",
        "job_card_number",
        "resolution_summary",
        "actioned_by_name_and_surname",
        "operating_status",
        "action_status",
        "completion_percentage",
    ]

    records = []
    page_size = 500

    while True:
        batch = frappe.get_list(
            "Pre Use Deviation",
            fields=fields,
            filters=query_filters,
            order_by="report_datetime desc, creation desc",
            start=len(records),
            page_length=page_size,
        )

        if not batch:
            break

        records.extend(batch)

        if len(batch) < page_size:
            break

    for row in records:
        pct = row.get("completion_percentage")
        if pct is None:
            pct = 100 if row.get("action_date_and_time") else 0

        pct = int(round(flt(pct), 0))

        row["completion_percentage"] = pct
        row["completion_percentage_badge"] = f"{pct}%"
        row["action_status_badge"] = row.get("action_status") or ""
        row["operating_status_badge"] = row.get("operating_status") or ""

        row["report_datetime_display"] = format_dt_short(row.get("report_datetime"))
        row["action_date_and_time_display"] = format_dt_short(row.get("action_date_and_time"))
        service_date = row.get("date_service_report_received")
        row["date_service_report_received_display"] = (
            service_date.strftime("%d-%m-%Y")
            if hasattr(service_date, "strftime")
            else str(service_date or "")[:10]
        )

        row["site"] = str(row.get("site") or "")
        row["machine_model"] = str(row.get("machine_model") or "")
        row["fleet_number"] = str(row.get("fleet_number") or "")
        row["recurring_deviation"] = str(row.get("recurring_deviation") or "")
        row["action"] = str(row.get("action") or "")
        row["job_card_number"] = str(row.get("job_card_number") or "")
        row["reported_by_name_and_surname"] = str(row.get("reported_by_name_and_surname") or "")
        row["deviation_details"] = str(row.get("deviation_details") or "")
        row["resolution_summary"] = str(row.get("resolution_summary") or "")
        row["actioned_by_name_and_surname"] = str(row.get("actioned_by_name_and_surname") or "")

    return records


def get_chart_data(data):
    open_count = len([d for d in data if d.get("action_status") == "Open"])
    closed_count = len([d for d in data if d.get("action_status") == "Closed"])

    return {
        "data": {
            "labels": ["Open", "Closed"],
            "datasets": [
                {
                    "name": "Status",
                    "values": [open_count, closed_count]
                }
            ]
        },
        "type": "donut",
        "height": 220,
        "colors": ["#f97316", "#22c55e"]
    }


def get_report_summary(data):
    total_records = len(data)

    avg_completion = 0
    if total_records:
        avg_completion = sum([flt(d.get("completion_percentage", 0)) for d in data]) / total_records

    avg_completion = int(round(avg_completion, 0))

    return [
        {
            "value": f"{avg_completion}%",
            "label": "Average Completion",
            "datatype": "Data",
            "indicator": "Blue"
        }
    ]


@frappe.whitelist()
def get_site_options():
    allowed_sites = get_allowed_sites()

    conditions = ["IFNULL(site, '') != ''"]
    values = {}

    if allowed_sites:
        conditions.append("site IN %(allowed_sites)s")
        values["allowed_sites"] = tuple(allowed_sites)

    where_clause = " AND ".join(conditions)

    sites = frappe.db.sql(
        f"""
        SELECT DISTINCT site
        FROM `tabPre Use Deviation`
        WHERE {where_clause}
        ORDER BY site
        """,
        values=values,
        as_dict=True,
    )

    options = ["All Sites"]
    options.extend(d.site for d in sites if d.site)

    return "\n".join(options)

@frappe.whitelist()
def get_operating_status_options():
    allowed_sites = get_allowed_sites()

    conditions = [
        "IFNULL(operating_status, '') != ''"
    ]
    values = {}

    if allowed_sites:
        conditions.append("site IN %(allowed_sites)s")
        values["allowed_sites"] = tuple(allowed_sites)

    where_clause = " AND ".join(conditions)

    statuses = frappe.db.sql(
        f"""
        SELECT DISTINCT operating_status
        FROM `tabPre Use Deviation`
        WHERE {where_clause}
        ORDER BY operating_status
        """,
        values=values,
        as_dict=True,
    )

    options = ["All Statuses"]
    options.extend(
        d.operating_status for d in statuses
        if d.operating_status
    )

    return "\n".join(options)


def format_dt_short(value):
    if not value:
        return ""

    if isinstance(value, datetime):
        return value.strftime("%d-%m-%y %H:%M")

    text = str(value).replace("T", " ")
    try:
        dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d-%m-%y %H:%M")
    except Exception:
        return text[:14]


def flt(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

# PRE USE NATIVE XLSX STYLING START
def get_xlsx_styles(metadata):
    """Style native Frappe Excel exports for this report only."""
    from frappe.utils.xlsxutils import XLSXStyleBuilder

    builder = XLSXStyleBuilder(metadata)

    # Thin black borders for every exported data cell.
    data_border = builder.register_style({
        "border": 1,
        "border_color": "#000000",
    })

    for row_idx in range(
        metadata.get_first_row_index(),
        metadata.get_last_row_index() + 1,
    ):
        for col_idx in metadata.column_map:
            builder.style_cell(row_idx, col_idx, data_border)

    green_header = builder.register_style({
        "bg_color": "#00AD50",
        "font_color": "#000000",
        "bold": True,
        "text_wrap": True,
        "valign": "vcenter",
        "border": 1,
    })

    yellow_header = builder.register_style({
        "bg_color": "#FFFF00",
        "font_color": "#000000",
        "bold": True,
        "text_wrap": True,
        "valign": "vcenter",
        "border": 1,
    })

    header_row = metadata.get_header_index()

    for col_idx, column in metadata.column_map.items():
        is_reported = (
            column.get("fieldname") == "recurring_deviation"
            or column.get("label") == "Reported"
        )

        builder.style_cell(
            header_row,
            col_idx,
            yellow_header if is_reported else green_header,
        )

    return builder.result
# PRE USE NATIVE XLSX STYLING END
