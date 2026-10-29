"""Read-only tyre damage occurrences, scoped by the dashboard's Engine roster."""

from datetime import timedelta

from engineering.engineering.doctype.machine_reliability_settings.machine_reliability_settings import (
    TYRE_DAMAGE_SUBCATEGORY,
    TYRES_WHEELS_CATEGORY,
)

CATEGORIES = ("ADT", "Dozer")
MAX_RECORDS = 20000


def is_classified_tyre_damage(record):
    """An explicit classification; complaint and resolution text are not estimates."""
    return (
        record.get("problem_category") == TYRES_WHEELS_CATEGORY
        and record.get("problem_subcategory") == TYRE_DAMAGE_SUBCATEGORY
    )


def damage_counts(records, machine=None):
    if records is None:
        return dict.fromkeys(CATEGORIES)
    groups = {category: set() for category in CATEGORIES}
    for row in records:
        if row["category"] in groups and (not machine or row["machine"] == machine):
            groups[row["category"]].add(row["name"])
    return {category: len(names) for category, names in groups.items()}


def fetch_tyre_damage_records(
    source_rows, location, start_date, end_date, selected_asset=None
):
    import frappe
    from frappe.utils import getdate

    scope = {}
    for row in source_rows or []:
        if int(row.get("indent") or 0) != 3 or row.get("is_formula_row"):
            continue
        machine = str(row.get("asset_name") or "").strip()
        day = str(row.get("shift_date") or "")[:10]
        if machine and day:
            scope[(machine, day)] = row.get("asset_category")
    if not scope:
        return []
    if not frappe.has_permission("Plant Breakdown or Maintenance", "read"):
        return None  # Do not block existing performance reports or invent a zero.
    machines = sorted({machine for machine, _ in scope})
    identities = frappe.get_all(
        "Asset",
        or_filters=[["name", "in", machines], ["asset_name", "in", machines]],
        fields=["name", "asset_name"],
        limit_page_length=0,
    )
    names = {
        row.name: row.asset_name if row.asset_name in machines else row.name
        for row in identities
    }
    if selected_asset:
        names = {
            name: machine
            for name, machine in names.items()
            if selected_asset in (name, machine)
        }
    if not names:
        return []
    start, finish = getdate(start_date), getdate(end_date) + timedelta(days=1)
    rows = frappe.get_list(
        "Plant Breakdown or Maintenance",
        filters=[
            ["problem_category", "=", TYRES_WHEELS_CATEGORY],
            ["problem_subcategory", "=", TYRE_DAMAGE_SUBCATEGORY],
            ["docstatus", "<", 2],
            ["downtime_type", "=", "Breakdown"],
            ["location", "=", location],
            ["breakdown_start_datetime", ">=", str(start)],
            ["breakdown_start_datetime", "<", str(finish)],
            ["asset_name", "in", sorted(names)],
        ],
        fields=[
            "name",
            "asset_name",
            "asset_category",
            "location",
            "downtime_type",
            "breakdown_start_datetime",
            "problem_category",
            "problem_subcategory",
        ],
        limit_page_length=MAX_RECORDS + 1,
    )
    if len(rows) > MAX_RECORDS:
        frappe.throw(
            "Too many breakdown records to count tyre damage. Narrow the dates or select an asset."
        )
    result = []
    for row in rows:
        machine = names.get(row.asset_name)
        day = str(row.breakdown_start_datetime or "")[:10]
        if (
            (machine, day) not in scope
            or row.location != location
            or row.downtime_type != "Breakdown"
        ):
            continue
        category = row.asset_category or scope[(machine, day)]
        category = {"ADT's": "ADT", "Dozer's": "Dozer"}.get(category, category)
        if category in CATEGORIES and is_classified_tyre_damage(row):
            result.append({"name": row.name, "machine": machine, "category": category})
    return result
