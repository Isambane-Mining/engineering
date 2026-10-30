from engineering.controllers.engineering_legals_rules import apply_no_expiry_overrides, filter_expiry_range, optional_snapshot_fields, skip_no_expiry_section
# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

# import frappe



import frappe
from frappe.utils import getdate, today
from collections import defaultdict
from frappe.query_builder import DocType
from engineering.engineering.report.engineering_legals_report.fetch_second_table import (
    _get_expiry_bucket,
    _build_combined_status,
)


EXCLUDED_SITES = ("Duplicate Assets",)

NO_EXPIRY_SECTIONS = (
    "Machine Service Records",
    "Service Schedule",
    "Wearcheck",
)

BUCKETS = [
    ("overdue", "Overdue", None, -1),     # < 0
    ("d0_7", "0–7", 0, 7),
    ("d8_14", "8–14", 8, 14),
    ("d15_21", "15–21", 15, 21),
    ("d22_28", "22–28", 22, 28),
]


def _get_asset_site_field():
    meta = frappe.get_meta("Asset")

    for fn in ("location", "site", "custom_location", "custom_site"):
        if meta.has_field(fn):
            return fn

    return None


def _get_asset_site_map(asset_names):
    asset_names = [a for a in (asset_names or []) if a]
    if not asset_names:
        return {}

    site_field = _get_asset_site_field()
    if not site_field:
        return {}

    Asset = DocType("Asset")

    rows = (
        frappe.qb.from_(Asset)
        .select(
            Asset.name,
            getattr(Asset, site_field).as_("current_site"),
        )
        .where(Asset.name.isin(asset_names))
    ).run(as_dict=True)

    return {
        (r.get("name") or "").strip(): (r.get("current_site") or "").strip()
        for r in rows
    }





def execute(filters=None):
    filters = filters or {}

    as_at = getdate(today())
    site = (filters.get("site") or "").strip() or None
    section = (filters.get("section") or "").strip() or None
    asset = (filters.get("asset") or "").strip() or None
    from_expiry_date = getdate(filters.get("from_expiry_date")) if filters.get("from_expiry_date") else None
    to_expiry_date = getdate(filters.get("to_expiry_date")) if filters.get("to_expiry_date") else None
    view = (filters.get("view") or "Summary").strip() or "Summary"
    bucket = (filters.get("bucket") or "").strip() or None

    # Click behaviour:
    # - Summary view (default): show section rows + bucket counts
    # - Assets view: show list of assets inside one chosen bucket (and optional section/asset)
    if view == "Assets" and bucket:
        return _assets_view(as_at, site, section, asset, bucket, from_expiry_date, to_expiry_date)

    return _summary_view(as_at, site, section, asset, from_expiry_date, to_expiry_date)


def _base_latest_expiry_sql(where_sql: str) -> str:
    """
    One "current" legal per Asset+Section+Site = MAX(expiry_date)
    (Renewals push expiry forward; this is what should drive due/overdue.)
    """
    return f"""
        SELECT
            el.site,
            el.sections AS section,
            el.fleet_number AS asset,
            MAX(el.expiry_date) AS expiry_date
        FROM `tabEngineering Legals` el
        WHERE
            el.expiry_date IS NOT NULL
            AND el.sections NOT IN %(no_expiry_sections)s
            AND el.site NOT IN %(excluded_sites)s
            {where_sql}
        GROUP BY el.site, el.sections, el.fleet_number
    """


def _summary_view(as_at, site, section, asset, from_expiry_date=None, to_expiry_date=None):
    columns = [
        {"label": "Section", "fieldname": "section", "fieldtype": "Data", "width": 220},
        {"label": "🔴 Overdue", "fieldname": "overdue", "fieldtype": "Int", "width": 110},
        {"label": "🟠 0–7", "fieldname": "d0_7", "fieldtype": "Int", "width": 90},
        {"label": "🟡 8–14", "fieldname": "d8_14", "fieldtype": "Int", "width": 90},
        {"label": "🟩 15–21", "fieldname": "d15_21", "fieldtype": "Int", "width": 95},
        {"label": "🟦 22–28", "fieldname": "d22_28", "fieldtype": "Int", "width": 95},
    ]

    filters = [["docstatus", "<", 2]]

    if section:
        filters.append(["sections", "=", section])

    if asset:
        filters.append(["fleet_number", "=", asset])


    docs = frappe.get_all(
        "Engineering Legals",
        filters=filters,
        fields=[
            "name",
            "site",
            "sections",
            "fleet_number",
            "start_date",
            "creation",
            "expiry_date",
            "modified",
            "attach_paper",
        ] + optional_snapshot_fields(),
        order_by="sections asc, fleet_number asc, start_date desc, expiry_date desc, modified desc",
        limit_page_length=0,
    )

    asset_site_map = _get_asset_site_map([d.get("fleet_number") for d in docs])

    grouped = {}
    for d in filter_expiry_range(apply_no_expiry_overrides(docs), from_expiry_date, to_expiry_date):
        sec = (d.get("sections") or "").strip()
        fleet = (d.get("fleet_number") or "").strip()

        if skip_no_expiry_section(d, NO_EXPIRY_SECTIONS):
            continue
        if not fleet:
            continue

        current_site = (asset_site_map.get(fleet) or "").strip()

        if current_site in EXCLUDED_SITES:
            continue

        if site and current_site != site:
            continue

        key = (sec, fleet)
        existing = grouped.get(key)

        if not existing:
            grouped[key] = d
            continue

        existing_expiry = existing.get("expiry_date")
        new_expiry = d.get("expiry_date")

        if new_expiry and (not existing_expiry or getdate(new_expiry) > getdate(existing_expiry)):
            grouped[key] = d

    summary = defaultdict(lambda: {
        "section": "",
        "overdue": 0,
        "d0_7": 0,
        "d8_14": 0,
        "d15_21": 0,
        "d22_28": 0,
    })

    for (_, _), latest_doc in grouped.items():
        sec = (latest_doc.get("sections") or "").strip()
        expiry_date = latest_doc.get("expiry_date")

        if not expiry_date:
            continue

        bucket = _get_expiry_bucket(expiry_date, as_at)
        row = summary[sec]
        row["section"] = sec

        if bucket == "Overdue":
            row["overdue"] += 1
        elif bucket == "0-7 days":
            row["d0_7"] += 1
        elif bucket == "8-14 days":
            row["d8_14"] += 1
        elif bucket == "15-21 days":
            row["d15_21"] += 1
        elif bucket == "22-28 days":
            row["d22_28"] += 1

    data = [summary[k] for k in sorted(summary.keys())]
    return columns, data, None, None


def _assets_view(as_at, site, section, asset, bucket, from_expiry_date=None, to_expiry_date=None):
    columns = [
        {"label": "Asset", "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 130},
        {"label": "Site", "fieldname": "site", "fieldtype": "Link", "options": "Location", "width": 120},
        {"label": "Section", "fieldname": "section", "fieldtype": "Data", "width": 170},
        {"label": "Start Date", "fieldname": "start_date", "fieldtype": "Date", "width": 110},
        {"label": "Expiry Date", "fieldname": "expiry_date", "fieldtype": "Date", "width": 110},
        {"label": "Days Left", "fieldname": "days_left", "fieldtype": "Int", "width": 90},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 180},
    ]

    filters = [["docstatus", "<", 2]]
    if section:
        filters.append(["sections", "=", section])
    if asset:
        filters.append(["fleet_number", "=", asset])




    docs = frappe.get_all(
        "Engineering Legals",
        filters=filters,
        fields=[
            "name",
            "site",
            "sections",
            "fleet_number",
            "start_date",
            "creation",
            "expiry_date",
            "modified",
            "attach_paper",
        ] + optional_snapshot_fields(),
        order_by="site asc, sections asc, fleet_number asc, start_date desc, expiry_date desc, modified desc",
        limit_page_length=0,
    )

    def get_expiry_bucket(expiry_date):
        if not expiry_date:
            return ""

        days_left = (getdate(expiry_date) - as_at).days

        if days_left < 0:
            return "Overdue"
        if days_left <= 7:
            return "0-7 days"
        if days_left <= 14:
            return "8-14 days"
        if days_left <= 21:
            return "15-21 days"
        if days_left <= 28:
            return "22-28 days"
        return ""

    def is_recently_done(previous_expiry_date, latest_start_date):
        if not previous_expiry_date or not latest_start_date:
            return False

        previous_expiry_date = getdate(previous_expiry_date)
        latest_start_date = getdate(latest_start_date)

        window_start = frappe.utils.add_days(previous_expiry_date, -10)
        window_end = frappe.utils.add_days(previous_expiry_date, 15)

        return window_start <= latest_start_date <= window_end

    def build_combined_status(latest_doc, previous_doc):
        statuses = []

        prev_expiry = previous_doc.get("expiry_date") if previous_doc else None
        latest_start = latest_doc.get("start_date")
        latest_expiry = latest_doc.get("expiry_date")

        is_recent = is_recently_done(prev_expiry, latest_start)
        expiry_bucket = get_expiry_bucket(latest_expiry)

        if is_recent:
            statuses.append("Recently done")

        if expiry_bucket and not (is_recent and expiry_bucket == "Overdue"):
            statuses.append(expiry_bucket)

        return " | ".join(statuses) if statuses else "-"

    def bucket_matches(expiry_bucket_value):
        if bucket == "overdue":
            return expiry_bucket_value == "Overdue"
        if bucket == "d0_7":
            return expiry_bucket_value == "0-7 days"
        if bucket == "d8_14":
            return expiry_bucket_value == "8-14 days"
        if bucket == "d15_21":
            return expiry_bucket_value == "15-21 days"
        if bucket == "d22_28":
            return expiry_bucket_value == "22-28 days"
        return False

    asset_site_map = _get_asset_site_map([d.get("fleet_number") for d in docs])

    grouped = defaultdict(list)
    for d in filter_expiry_range(apply_no_expiry_overrides(docs), from_expiry_date, to_expiry_date):
        sec = (d.get("sections") or "").strip()
        fleet = (d.get("fleet_number") or "").strip()

        if skip_no_expiry_section(d, NO_EXPIRY_SECTIONS):
            continue
        if not fleet:
            continue

        current_site = (asset_site_map.get(fleet) or "").strip()

        if current_site in EXCLUDED_SITES:
            continue

        if site and current_site != site:
            continue

        key = (
            current_site,
            sec,
            fleet,
        )
        grouped[key].append(d)

    data = []
    for (_, sec, fleet), group_docs in grouped.items():
        latest_doc = None

        for doc in group_docs:
            doc_expiry = doc.get("expiry_date")
            if not doc_expiry:
                continue

            if not latest_doc:
                latest_doc = doc
                continue

            latest_expiry = latest_doc.get("expiry_date")
            if getdate(doc_expiry) > getdate(latest_expiry):
                latest_doc = doc

        if not latest_doc:
            continue

        status = get_expiry_bucket(latest_doc.get("expiry_date"))

        expiry_bucket_value = get_expiry_bucket(latest_doc.get("expiry_date"))
        if not bucket_matches(expiry_bucket_value):
            continue

        expiry_date = latest_doc.get("expiry_date")
        days_left = (getdate(expiry_date) - as_at).days if expiry_date else None

        data.append({
            "asset": latest_doc.get("fleet_number"),
            "site": asset_site_map.get(latest_doc.get("fleet_number")) or "",
            "section": latest_doc.get("sections"),
            "start_date": latest_doc.get("start_date"),
            "expiry_date": expiry_date,
            "days_left": days_left,
            "status": status,
        })

    data.sort(key=lambda x: (
        x.get("days_left") if x.get("days_left") is not None else 999999,
        (x.get("section") or "").lower(),
        (x.get("asset") or "").lower(),
    ))

    message = f"Assets view: Bucket={bucket}, As-at={as_at}"
    return columns, data, message, None