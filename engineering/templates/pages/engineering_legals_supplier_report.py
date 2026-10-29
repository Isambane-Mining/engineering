from engineering.controllers.engineering_legals_rules import apply_no_expiry_overrides, filter_expiry_range, optional_snapshot_fields, skip_no_expiry_section
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import getdate, today
from erpnext.controllers.website_list_for_contact import get_customers_suppliers


EXCLUDED_SITES = ("Duplicate Assets",)

NO_EXPIRY_SECTIONS = (
    "Machine Service Records",
    "Service Schedule",
    "Wearcheck",
    "Brake Wear Measurements",
)

BUCKET_KEYS = ["overdue", "d0_7", "d8_14", "d15_21", "d22_28"]


def get_context(context):
    context.no_cache = 1
    context.show_sidebar = True
    context.title = "Supplier Engineering Legals Report"

    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/engineering_legals_supplier_report"
        raise frappe.Redirect

    if "Supplier" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Not permitted."), frappe.PermissionError)

    filters = {
        "site": (frappe.form_dict.get("site") or "").strip(),
        "section": (frappe.form_dict.get("section") or "").strip(),
        "asset": (frappe.form_dict.get("asset") or "").strip(),
        "from_expiry_date": (frappe.form_dict.get("from_expiry_date") or "").strip(),
        "to_expiry_date": (frappe.form_dict.get("to_expiry_date") or "").strip(),
    }

    assets = _get_supplier_assets()
    asset_names = [a.name for a in assets]

    context.filters = filters
    context.asset_options = assets
    context.site_options = sorted({a.site for a in assets if a.site})
    context.section_options = _get_sections_options()

    context.total_fleet = _get_asset_category_counts(assets, filters)
    context.summary_rows = _get_summary_rows(asset_names, filters)
    context.draft_rows = _get_draft_rows(asset_names, filters)
    context.history_tree = _get_history_tree(asset_names, filters)


def _get_user_suppliers():
    user = frappe.session.user

    customers, suppliers = get_customers_suppliers(
        "Request for Quotation Supplier",
        user
    )

    out = list(suppliers or [])

    contact_names = frappe.get_all(
        "Contact Email",
        filters={"email_id": user},
        pluck="parent",
        limit_page_length=0,
    )

    if contact_names:
        supplier_links = frappe.get_all(
            "Dynamic Link",
            filters={
                "parenttype": "Contact",
                "parent": ["in", contact_names],
                "link_doctype": "Supplier",
            },
            pluck="link_name",
            limit_page_length=0,
        )

        out.extend(supplier_links or [])

    return sorted(set(out))

def _get_asset_site_field():
    meta = frappe.get_meta("Asset")

    for fn in ("location", "site", "custom_location", "custom_site"):
        if meta.has_field(fn):
            return fn

    return None


def _get_supplier_assets():
    suppliers = _get_user_suppliers()
    if not suppliers:
        return []

    site_field = _get_asset_site_field()

    fields = ["name", "asset_name", "asset_category"]
    if site_field:
        fields.append(f"{site_field} as site")
    else:
        fields.append("'Unknown' as site")

    rows = frappe.get_all(
        "Asset",
        filters={
            "asset_owner": "Supplier",
            "supplier": ["in", suppliers],
        },
        fields=fields,
        order_by="name asc",
        limit_page_length=0,
    )

    return [
        r for r in rows
        if (r.get("site") or "").strip() not in EXCLUDED_SITES
    ]


def _get_sections_options():
    return frappe.get_all(
        "Engineering Legals Sections",
        pluck="name",
        order_by="name asc",
        limit_page_length=0,
    )


def _get_expiry_bucket(expiry_date, as_at):
    if not expiry_date:
        return ""

    days_left = (getdate(expiry_date) - as_at).days

    if days_left < 0:
        return "overdue"
    if days_left <= 7:
        return "d0_7"
    if days_left <= 14:
        return "d8_14"
    if days_left <= 21:
        return "d15_21"
    if days_left <= 28:
        return "d22_28"

    return ""


def _bucket_label(bucket):
    return {
        "overdue": "Overdue",
        "d0_7": "0-7 days",
        "d8_14": "8-14 days",
        "d15_21": "15-21 days",
        "d22_28": "22-28 days",
    }.get(bucket, "-")


def _days_left(expiry_date):
    if not expiry_date:
        return ""

    return (getdate(expiry_date) - getdate(today())).days


def _apply_common_filters(filters, include_expiry=True):
    out = []

    if filters.get("section"):
        out.append(["sections", "=", filters["section"]])

    if filters.get("asset"):
        out.append(["fleet_number", "=", filters["asset"]])

    if include_expiry and filters.get("from_expiry_date"):
        out.append(["expiry_date", ">=", getdate(filters["from_expiry_date"])])

    if include_expiry and filters.get("to_expiry_date"):
        out.append(["expiry_date", "<=", getdate(filters["to_expiry_date"])])

    return out


def _get_legal_docs(asset_names, filters):
    if not asset_names:
        return []

    legal_filters = [
        ["docstatus", "<", 2],
        ["fleet_number", "in", asset_names],
    ]
    legal_filters.extend(_apply_common_filters(filters))

    rows = frappe.get_all(
        "Engineering Legals",
        filters=legal_filters,
        fields=[
            "name",
            "site",
            "sections",
            "fleet_number",
            "start_date",
            "creation",
            "expiry_date",
            "attach_paper",
            "modified",
        ] + optional_snapshot_fields(),
        order_by="sections asc, fleet_number asc, start_date desc, expiry_date desc, modified desc",
        limit_page_length=0,
    )

    if filters.get("site"):
        rows = [r for r in rows if (r.get("site") or "").strip() == filters["site"]]

    return rows


def _get_latest_docs(asset_names, filters):
    status_filters = {key: value for key, value in filters.items() if key not in {"from_expiry_date", "to_expiry_date"}}
    docs = _get_legal_docs(asset_names, status_filters)
    grouped = {}

    for d in filter_expiry_range(apply_no_expiry_overrides(docs), filters.get("from_expiry_date"), filters.get("to_expiry_date")):
        sec = (d.get("sections") or "").strip()
        fleet = (d.get("fleet_number") or "").strip()

        if not fleet or skip_no_expiry_section(d, NO_EXPIRY_SECTIONS):
            continue

        key = (sec, fleet)
        existing = grouped.get(key)

        if not existing:
            grouped[key] = d
            continue

        old_expiry = existing.get("expiry_date")
        new_expiry = d.get("expiry_date")

        if new_expiry and (not old_expiry or getdate(new_expiry) > getdate(old_expiry)):
            grouped[key] = d

    return list(grouped.values())


def _get_summary_rows(asset_names, filters):
    as_at = getdate(today())
    latest_docs = _get_latest_docs(asset_names, filters)

    summary = defaultdict(lambda: {
        "section": "",
        "overdue": 0,
        "d0_7": 0,
        "d8_14": 0,
        "d15_21": 0,
        "d22_28": 0,
        "assets": [],
    })

    for d in latest_docs:
        section = (d.get("sections") or "").strip()
        bucket = _get_expiry_bucket(d.get("expiry_date"), as_at)

        if not bucket:
            continue

        row = summary[section]
        row["section"] = section
        row[bucket] += 1

        row["assets"].append({
            "name": d.get("name"),
            "site": d.get("site"),
            "section": section,
            "fleet_number": d.get("fleet_number"),
            "start_date": d.get("start_date"),
            "expiry_date": d.get("expiry_date"),
            "days_left": _days_left(d.get("expiry_date")),
            "bucket": bucket,
            "bucket_label": _bucket_label(bucket),
            "attach_paper": d.get("attach_paper"),
        })

    return [summary[k] for k in sorted(summary.keys())]


def _get_asset_category_counts(assets, filters):
    rows = defaultdict(int)

    for asset in assets:
        if filters.get("site") and (asset.get("site") or "") != filters["site"]:
            continue

        if filters.get("asset") and asset.get("name") != filters["asset"]:
            continue

        category = asset.get("asset_category") or "Unknown"
        rows[category] += 1

    return [
        {"category": category, "count": count}
        for category, count in sorted(rows.items(), key=lambda x: (-x[1], x[0]))
    ]


def _get_draft_rows(asset_names, filters):
    if not asset_names:
        return []

    draft_filters = [
        ["portal_user", "=", frappe.session.user],
        ["fleet_number", "in", asset_names],
    ]

    if filters.get("site"):
        draft_filters.append(["site", "=", filters["site"]])

    if filters.get("section"):
        draft_filters.append(["sections", "=", filters["section"]])

    if filters.get("asset"):
        draft_filters.append(["fleet_number", "=", filters["asset"]])

    rows = frappe.get_all(
        "Engineering Legals supplier Portal Draft",
        filters=draft_filters,
        fields=[
            "name",
            "site",
            "sections",
            "fleet_number",
            "start_date",
            "creation",
            "expiry_date",
            "attach_paper",
            "sent_to_erp",
            "erp_document",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=200,
    )

    return rows


def _get_history_tree(asset_names, filters):
    docs = _get_legal_docs(asset_names, filters)

    tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for d in docs:
        site = (d.get("site") or "Unknown").strip()
        section = (d.get("sections") or "Unknown").strip()
        fleet = (d.get("fleet_number") or "Unknown").strip()

        tree[site][section][fleet].append(d)

    out = []

    for site in sorted(tree.keys()):
        site_node = {
            "label": site,
            "count": 0,
            "sections": [],
        }

        for section in sorted(tree[site].keys()):
            section_node = {
                "label": section,
                "count": 0,
                "fleets": [],
            }

            for fleet in sorted(tree[site][section].keys()):
                docs_for_fleet = tree[site][section][fleet]
                section_node["fleets"].append({
                    "label": fleet,
                    "count": len(docs_for_fleet),
                    "docs": docs_for_fleet,
                })
                section_node["count"] += len(docs_for_fleet)
                site_node["count"] += len(docs_for_fleet)

            site_node["sections"].append(section_node)

        out.append(site_node)

    return out