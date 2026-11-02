# Copyright (c) 2026, Isambane Mining (Pty) Ltd
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, now_datetime, time_diff_in_hours
from datetime import datetime, time, timedelta


CATEGORY_ORDER = {
    "ADT": 1,
    "Excavator": 2,
    "Dozer": 3,
    "Water Bowser": 4,
    "Diesel Bowser": 5,
    "Service Truck": 6,
    "FEL": 7,
    "Grader": 8,
}

# Ignore old dirty open records before this date
STALE_BREAKDOWN_CUTOFF_DATETIME = get_datetime("2026-03-01 00:00:00")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": _("Site"), "fieldname": "site", "fieldtype": "Data", "width": 140},
        {"label": _("Plant No."), "fieldname": "plant_no", "fieldtype": "Data", "width": 120},
        {"label": _("Plant Category"), "fieldname": "category_group", "fieldtype": "Data", "width": 160},
        {"label": _("Plant Model"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
        {"label": _("Reason"), "fieldname": "reason", "fieldtype": "Small Text", "width": 300},
        {"label": _("Start Time"), "fieldname": "start_time", "fieldtype": "Datetime", "width": 190},
        {"label": _("Resolved Time"), "fieldname": "resolved_time", "fieldtype": "Datetime", "width": 190},
        {"label": _("Open Hours at Hour End"), "fieldname": "open_hours", "fieldtype": "Float", "precision": 2, "width": 170},
        {"label": _("Breakdown Document"), "fieldname": "breakdown_docname", "fieldtype": "Data", "width": 180, "hidden": 1},
    ]


def get_hour_end(filters):
    report_date = getdate(filters.get("report_date")) if filters.get("report_date") else getdate(now_datetime())
    hour_slot = str(filters.get("hour_slot") or "").strip()

    if not hour_slot:
        current_hour = now_datetime().hour
        next_hour = current_hour + 1
        hour_slot = "23:00-24:00" if next_hour >= 24 else f"{current_hour:02d}:00-{next_hour:02d}:00"

    start_text, end_text = hour_slot.split("-")
    end_hour = int(end_text.split(":")[0])

    if end_hour == 24:
        return datetime.combine(report_date + timedelta(days=1), time.min)

    return datetime.combine(report_date, time(end_hour, 0, 0))


def get_category_group(asset_category):
    value = str(asset_category or "").strip().lower()

    if "adt" in value:
        return "ADT"
    if "excavator" in value:
        return "Excavator"
    if "dozer" in value:
        return "Dozer"
    if "water" in value and "bowser" in value:
        return "Water Bowser"
    if "diesel" in value and "bowser" in value:
        return "Diesel Bowser"
    if "service" in value and "truck" in value:
        return "Service Truck"
    if value == "fel" or "front end loader" in value:
        return "FEL"
    if "grader" in value:
        return "Grader"

    return ""


def get_data(filters, assets=None):
    """`assets` may be passed in (from get_report_assets) so callers that
    run many hours for the same site only query the fleet once."""
    hour_end = get_hour_end(filters)
    hour_start = hour_end - timedelta(hours=1)

    if assets is None:
        assets = get_report_assets(filters.get("site"))

    asset_names = [
        asset.name for asset in assets
    ]

    event_map = get_breakdowns_for_hour(
        asset_names,
        hour_start,
        hour_end,
    )

    data = []

    for asset in assets:
        breakdown = event_map.get(asset.name)

        if breakdown:
            breakdown_start = get_datetime(
                breakdown.breakdown_start_datetime
            )
            resolved = (
                get_datetime(breakdown.resolved_datetime)
                if breakdown.resolved_datetime
                else None
            )

            overlap_start = max(
                breakdown_start,
                hour_start,
            )
            overlap_end = min(
                resolved or hour_end,
                hour_end,
            )

            hours = round(
                max(
                    (
                        overlap_end - overlap_start
                    ).total_seconds() / 3600,
                    0,
                ),
                2,
            )

            is_open_at_end = (
                not resolved
                or resolved > hour_end
            )

            data.append({
                "status": (
                    "❌ OPEN"
                    if is_open_at_end
                    else "✅ CLOSED"
                ),
                "status_key": (
                    "open"
                    if is_open_at_end
                    else "closed"
                ),
                "site": asset.location,
                "plant_no": asset.name,
                "asset_category": asset.asset_category,
                "category_group": asset.category_group,
                "category_order": asset.category_order,
                "item_name": asset.item_name,
                "reason": breakdown.breakdown_reason or "-",
                "start_time": breakdown.breakdown_start_datetime,
                "resolved_time": breakdown.resolved_datetime,
                "open_hours": hours,
                "breakdown_docname": breakdown.name,
            })
        else:
            data.append({
                "status": "✅ AVAILABLE",
                "status_key": "available",
                "site": asset.location,
                "plant_no": asset.name,
                "asset_category": asset.asset_category,
                "category_group": asset.category_group,
                "category_order": asset.category_order,
                "item_name": asset.item_name,
                "reason": "-",
                "start_time": "",
                "resolved_time": "",
                "open_hours": 0,
                "breakdown_docname": "",
            })

    data.sort(key=lambda row: (
        row.get("category_order") or 999,
        row.get("plant_no") or "",
    ))

    return data


def get_report_assets(site=None):
    conditions = [
        "a.docstatus = 1",
        "ifnull(a.location, '') != ''",
    ]
    values = {}

    if site:
        conditions.append("a.location = %(site)s")
        values["site"] = site

    assets = frappe.db.sql(
        f"""
        SELECT
            a.name,
            a.location,
            a.asset_category,
            a.item_name
        FROM `tabAsset` a
        WHERE {" AND ".join(conditions)}
        ORDER BY a.location, a.asset_category, a.name
        """,
        values,
        as_dict=True,
    )

    filtered_assets = []

    for asset in assets:
        category_group = get_category_group(
            asset.asset_category
        )

        if not category_group:
            continue

        asset.category_group = category_group
        asset.category_order = CATEGORY_ORDER.get(
            category_group,
            999,
        )
        filtered_assets.append(asset)

    return filtered_assets


def get_breakdowns_for_hour(
    asset_names,
    hour_start,
    hour_end,
):
    if not asset_names:
        return {}

    rows = frappe.db.sql(
        """
        SELECT
            name,
            asset_name,
            breakdown_reason,
            breakdown_start_datetime,
            resolved_datetime
        FROM `tabPlant Breakdown or Maintenance`
        WHERE asset_name IN %(asset_names)s
          AND breakdown_start_datetime < %(hour_end)s
          AND (
              resolved_datetime IS NULL
              OR resolved_datetime > %(hour_start)s
          )
        ORDER BY
            asset_name,
            breakdown_start_datetime DESC,
            modified DESC
        """,
        {
            "asset_names": tuple(asset_names),
            "hour_start": hour_start,
            "hour_end": hour_end,
        },
        as_dict=True,
    )

    event_map = {}

    for row in rows:
        start_time = get_datetime(
            row.breakdown_start_datetime
        )
        resolved = (
            get_datetime(row.resolved_datetime)
            if row.resolved_datetime
            else None
        )

        if (
            not resolved
            and start_time
            < STALE_BREAKDOWN_CUTOFF_DATETIME
        ):
            continue

        current = event_map.get(row.asset_name)

        # Prefer a breakdown open at the period end.
        is_open_at_end = (
            not resolved
            or resolved > hour_end
        )

        if (
            current is None
            or (
                is_open_at_end
                and current.get("_status") != "open"
            )
        ):
            row["_status"] = (
                "open" if is_open_at_end else "closed"
            )
            event_map[row.asset_name] = row

    return event_map
