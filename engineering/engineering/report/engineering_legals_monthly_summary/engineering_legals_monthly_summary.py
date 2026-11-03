from __future__ import annotations

import calendar
from datetime import date

import frappe
from frappe import _
from frappe.utils import getdate


MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


from engineering.controllers.engineering_legals_rules import (
    CATEGORY_CONFIG,
    optional_snapshot_fields,
    record_reporting_rule,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})

    year = int(filters.get("year") or date.today().year)
    month_name = filters.get("month") or date.today().strftime("%b")
    month_number = MONTHS.get(month_name)
    site = (filters.get("site") or "").strip()

    if not month_number:
        frappe.throw(_("Please select a valid month."))

    month_start = date(year, month_number, 1)
    month_end = date(
        year,
        month_number,
        calendar.monthrange(year, month_number)[1],
    )

    columns = get_columns()
    legal_records = get_legal_records(site)

    data = []
    total = 0

    category_configs = list(CATEGORY_CONFIG)
    if any((record_reporting_rule(record) or {}).get("category") == "Other" for record in legal_records):
        category_configs.append(dict(category="Other", mode="saved_in_month", sections=[]))

    for config in category_configs:
        matching_records = []

        for record in legal_records:
            reporting = record_reporting_rule(record)
            if not reporting or reporting["category"] != config["category"]:
                continue

            if reporting["mode"] == "active_until_expiry":
                if is_active_during_month(
                    record,
                    month_start,
                    month_end,
                ):
                    matching_records.append(record)

            elif reporting["mode"] == "saved_in_month":
                if is_saved_in_month(
                    record,
                    month_start,
                    month_end,
                ):
                    matching_records.append(record)

        completed = len(matching_records)

        drill_count = sum(
            1
            for record in matching_records
            if (getattr(record, "asset_category", "") or "")
            .strip()
            .upper() == "DRILLS"
        )

        tmm_count = sum(
            1
            for record in matching_records
            if (record.vehicle_type or "").strip().upper() == "TMM"
            and (getattr(record, "asset_category", "") or "")
            .strip()
            .upper() != "DRILLS"
        )

        ldv_count = sum(
            1
            for record in matching_records
            if (record.vehicle_type or "").strip().upper() == "LDV"
        )

        record_names = [
            record.name
            for record in matching_records
        ]

        missing_items = []

        if config["category"] == "02. Condition Monitoring":
            active_sections = {
                (record.sections or "").strip()
                for record in matching_records
            }

            if "Illumination Baseline" not in active_sections:
                missing_items.append("Illumination Baseline")

            if (
                "Noise Level Baseline & Measurement"
                not in active_sections
            ):
                missing_items.append(
                    "Noise Level Baseline & Measurement"
                )

            if not (
                {"NDT", "Machine NDT"} & active_sections
            ):
                missing_items.append("NDT / Machine NDT")

        total += completed

        modes = {record_reporting_rule(record)["mode"] for record in matching_records}
        mode = next(iter(modes)) if len(modes) == 1 else "mixed" if modes else config["mode"]
        sections = sorted(set(config["sections"]) | {record.sections for record in matching_records})
        data.append({
            "category": config["category"],
            "frequency_rule": get_frequency_label(mode),
            "completed": completed,
            "site": site or "All Sites",
            "tmm": tmm_count,
            "ldv": ldv_count,
            "drills": drill_count,
            "mode": mode,
            "sections_json": frappe.as_json(sections),
            "record_names_json": frappe.as_json(record_names),
            "missing_items_json": frappe.as_json(missing_items),

            # Every legal category must provide access to its
            # contributing Engineering Legals records.
            "view_enabled": 1,
        })

    data.append({
        "category": "TOTAL",
        "frequency_rule": "",
        "completed": total,
        "site": site or "All Sites",
        "tmm": sum(row.get("tmm", 0) for row in data),
        "ldv": sum(row.get("ldv", 0) for row in data),
        "drills": sum(row.get("drills", 0) for row in data),
        "is_total": 1,
        "mode": "",
        "sections_json": "[]",
        "record_names_json": "[]",
        "view_enabled": 0,
    })

    chart = {
        "data": {
            "labels": [
                row["category"]
                for row in data
                if not row.get("is_total")
            ],
            "datasets": [
                {
                    "name": _("Completed"),
                    "values": [
                        row["completed"]
                        for row in data
                        if not row.get("is_total")
                    ],
                }
            ],
        },
        "type": "bar",
        "height": 300,
    }

    plant_counts = get_submitted_plant_counts(site)

    report_summary = [
        {
            "value": total,
            "label": _("Active Legals"),
            "datatype": "Int",
            "indicator": "Blue",
        },
        {
            "value": f"{month_name}-{str(year)[-2:]}",
            "label": _("Selected Month"),
            "datatype": "Data",
            "indicator": "Green",
        },
        {
            "value": site or _("All Sites"),
            "label": _("Site"),
            "datatype": "Data",
            "indicator": "Orange",
        },
    ]

    message = build_machine_plant_list_html(
        plant_counts,
        site or _("All Sites"),
    )

    return columns, data, message, chart, report_summary


def build_machine_plant_list_html(plant_counts, site_label):
    rows = []

    machine_types = [
        "Excavator",
        "Dozer",
        "ADT",
        "Water Bowser",
        "Grader",
        "TLB",
        "Lighting Plant",
        "Service Truck",
        "Diesel Bowser",
        "Loader",
        "Drills",
        "LDV",
    ]

    safe_site = frappe.utils.escape_html(site_label)

    for machine_type in machine_types:
        count = plant_counts.get(machine_type, 0)
        safe_machine_type = frappe.utils.escape_html(
            machine_type
        )

        rows.append(
            f"""
            <tr>
                <td>{safe_machine_type}</td>

                <td class="text-right">
                    <div class="engineering-machine-actions">
                        <button
                            type="button"
                            class="btn btn-xs btn-default
                                   engineering-view-plant-list"
                            data-machine-type="{safe_machine_type}"
                            data-site="{safe_site}"
                        >
                            View Plant List
                        </button>

                        <button
                            type="button"
                            class="btn btn-xs btn-primary
                                   engineering-main-view-legals"
                            data-machine-type="{safe_machine_type}"
                            data-site="{safe_site}"
                        >
                            View Legals
                        </button>
                    </div>
                </td>
            </tr>
            """
        )

    total_fleet = sum(
        plant_counts.get(machine_type, 0)
        for machine_type in machine_types
    )

    rows.append(
        f"""
        <tr class="engineering-total-fleet-row">
            <td>
                <strong>Total Fleet</strong>
            </td>

            <td class="text-right">
                <div class="engineering-machine-actions">
                    <button
                        type="button"
                        class="btn btn-xs btn-default
                               engineering-view-plant-list"
                        data-machine-type="Total Fleet"
                        data-site="{safe_site}"
                    >
                        View Plant List
                    </button>

                    <button
                        type="button"
                        class="btn btn-xs btn-primary
                               engineering-main-view-legals"
                        data-machine-type="Total Fleet"
                        data-site="{safe_site}"
                    >
                        View Legals
                    </button>
                </div>
            </td>
        </tr>
        """
    )

    return f"""
    <div class="engineering-legals-machine-list">
        <div class="engineering-legals-machine-list__header">
            <h4>Machine Plant List</h4>
        </div>

        <div class="table-responsive">
            <table class="table table-bordered table-hover">
                <thead>
                    <tr>
                        <th>Machine Type</th>
                        <th class="text-right">Submitted</th>
                    </tr>
                </thead>

                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        </div>
    </div>
    """


def get_submitted_plant_counts(site=None):
    """
    Return submitted Asset counts for the selected site.

    Only submitted Assets are counted:
        docstatus = 1
    """
    category_aliases = {
        "Excavator": {
            "EXCAVATOR",
            "EXCAVATORS",
        },
        "Dozer": {
            "DOZER",
            "DOZERS",
        },
        "ADT": {
            "ADT",
            "ADTS",
            "ARTICULATED DUMP TRUCK",
            "ARTICULATED DUMP TRUCKS",
        },
        "Water Bowser": {
            "WATER BOWSER",
            "WATER BOWSERS",
            "WATERBOWSER",
            "WATERBOWSERS",
        },
        "Grader": {
            "GRADER",
            "GRADERS",
        },
        "TLB": {
            "TLB",
            "TLBS",
        },
        "Lighting Plant": {
            "LIGHTING PLANT",
            "LIGHTING PLANTS",
            "LIGHT TOWER",
            "LIGHT TOWERS",
        },
        "Service Truck": {
            "SERVICE TRUCK",
            "SERVICE TRUCKS",
        },
        "Diesel Bowser": {
            "DIESEL BOWSER",
            "DIESEL BOWSERS",
            "DIESELBOWSER",
            "DIESELBOWSERS",
        },
        "Loader": {
            "LOADER",
            "LOADERS",
            "FRONT END LOADER",
            "FRONT END LOADERS",
            "FRONT-END LOADER",
            "FRONT-END LOADERS",
        },
        "Drills": {
            "DRILL",
            "DRILLS",
        },
        "LDV": {
            "LDV",
            "LDVS",
        },
    }

    filters = {
        "docstatus": 1,
    }

    if site:
        filters["location"] = site

    rows = frappe.get_all(
        "Asset",
        filters=filters,
        fields=[
            "name",
            "asset_category",
        ],
    )

    counts = {
        label: 0
        for label in category_aliases
    }

    for row in rows:
        category = (
            row.asset_category or ""
        ).strip().upper()

        for label, aliases in category_aliases.items():
            if category in aliases:
                counts[label] += 1
                break

    return counts


def get_columns():
    return [
        {
            "label": _("Legal Category"),
            "fieldname": "category",
            "fieldtype": "Data",
            "width": 360,
        },
        {
            "label": _("Counting Rule"),
            "fieldname": "frequency_rule",
            "fieldtype": "Data",
            "width": 250,
        },
        {
            "label": _("Completed / Active"),
            "fieldname": "completed",
            "fieldtype": "Int",
            "width": 160,
        },
        {
            "label": _("TMM"),
            "fieldname": "tmm",
            "fieldtype": "Int",
            "width": 80,
        },
        {
            "label": _("LDV"),
            "fieldname": "ldv",
            "fieldtype": "Int",
            "width": 80,
        },
        {
            "label": _("Drills"),
            "fieldname": "drills",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "label": _("View Rows"),
            "fieldname": "view_rows",
            "fieldtype": "Data",
            "width": 120,
        },
    ]


def get_legal_records(site=None):
    filters = {}

    if site:
        filters["site"] = site

    records = frappe.get_all(
        "Engineering Legals",
        filters=filters,
        fields=[
            "name",
            "site",
            "sections",
            "start_date",
            "expiry_date",
            "creation",
            "vehicle_type",
            "fleet_number",
        ] + optional_snapshot_fields(),
        order_by="sections asc, start_date asc",
    )

    fleet_numbers = list({
        record.fleet_number
        for record in records
        if record.fleet_number
    })

    asset_category_by_fleet = {}

    if fleet_numbers:
        asset_rows = frappe.get_all(
            "Asset",
            filters={
                "name": ["in", fleet_numbers],
            },
            fields=[
                "name",
                "asset_category",
            ],
        )

        asset_category_by_fleet = {
            row.name: row.asset_category
            for row in asset_rows
        }

    for record in records:
        record.asset_category = (
            asset_category_by_fleet.get(
                record.fleet_number
            )
            or ""
        )

    return records


def is_active_during_month(record, month_start, month_end):
    """
    A recurring certificate counts when any part of its validity
    overlaps the selected month.

    Start Date <= month end
    Expiry Date >= month start
    """
    if not record.start_date or not record.expiry_date:
        return False

    start_date = getdate(record.start_date)
    expiry_date = getdate(record.expiry_date)

    return (
        start_date <= month_end
        and expiry_date >= month_start
    )


def is_saved_in_month(record, month_start, month_end):
    """
    Monthly-only documents count only in their relevant capture month.

    Start Date is used first. When Start Date is intentionally empty,
    the ERP creation date is used.
    """
    relevant_date = record.start_date

    if not relevant_date:
        relevant_date = record.creation

    if not relevant_date:
        return False

    relevant_date = getdate(relevant_date)

    return month_start <= relevant_date <= month_end


def get_frequency_label(mode):
    if mode == "mixed":
        return "Per recorded document rule"
    if mode == "active_until_expiry":
        return "Carried forward until expiry"

    return "Count only in saved month"


@frappe.whitelist()
def get_submitted_machine_rows(machine_type, site=None):
    """
    Return submitted Asset rows for a machine category and site.
    """
    machine_type = (machine_type or "").strip()
    site = (site or "").strip()

    category_aliases = {
        "Excavator": [
            "Excavator",
            "Excavators",
        ],
        "Dozer": [
            "Dozer",
            "Dozers",
        ],
        "ADT": [
            "ADT",
            "ADTs",
            "Articulated Dump Truck",
            "Articulated Dump Trucks",
        ],
        "Water Bowser": [
            "Water Bowser",
            "Water Bowsers",
            "Waterbowser",
            "Waterbowsers",
        ],
        "Grader": [
            "Grader",
            "Graders",
        ],
        "TLB": [
            "TLB",
            "TLBs",
        ],
        "Lighting Plant": [
            "Lighting Plant",
            "Lighting Plants",
            "Light Tower",
            "Light Towers",
        ],
        "Service Truck": [
            "Service Truck",
            "Service Trucks",
        ],
        "Diesel Bowser": [
            "Diesel Bowser",
            "Diesel Bowsers",
            "Dieselbowser",
            "Dieselbowsers",
        ],
        "Loader": [
            "Loader",
            "Loaders",
            "Front End Loader",
            "Front End Loaders",
            "Front-End Loader",
            "Front-End Loaders",
        ],
        "Drills": [
            "Drill",
            "Drills",
        ],
        "LDV": [
            "LDV",
            "LDVs",
        ],
    }

    if machine_type == "Total Fleet":
        aliases = sorted({
            alias
            for machine_aliases in category_aliases.values()
            for alias in machine_aliases
        })
    else:
        aliases = category_aliases.get(
            machine_type,
            [machine_type],
        )

    filters = {
        "docstatus": 1,
        "asset_category": ["in", aliases],
    }

    if site and site != "All Sites":
        filters["location"] = site

    rows = frappe.get_all(
        "Asset",
        filters=filters,
        fields=[
            "name",
            "asset_name",
            "item_name",
            "asset_category",
            "location",
        ],
        order_by="name asc",
    )

    return {
        "machine_type": machine_type,
        "site": site or "All Sites",
        "total": len(rows),
        "rows": rows,
    }


@frappe.whitelist()
def get_machine_legal_status_rows(
    machine_type,
    site=None,
    year=None,
    month=None,
):
    """
    Return submitted machines together with active legal-document
    status for the selected report month.
    """
    machine_type = (machine_type or "").strip()
    site = (site or "").strip()

    year = int(year or date.today().year)
    month_number = MONTHS.get(
        month or date.today().strftime("%b")
    )

    if not month_number:
        frappe.throw(_("Please select a valid month."))

    month_start = date(year, month_number, 1)
    month_end = date(
        year,
        month_number,
        calendar.monthrange(year, month_number)[1],
    )

    category_aliases = {
        "Excavator": ["Excavator", "Excavators"],
        "Dozer": ["Dozer", "Dozers"],
        "ADT": [
            "ADT",
            "ADTs",
            "Articulated Dump Truck",
            "Articulated Dump Trucks",
        ],
        "Water Bowser": [
            "Water Bowser",
            "Water Bowsers",
            "Waterbowser",
            "Waterbowsers",
        ],
        "Grader": ["Grader", "Graders"],
        "TLB": ["TLB", "TLBs"],
        "Lighting Plant": [
            "Lighting Plant",
            "Lighting Plants",
            "Light Tower",
            "Light Towers",
        ],
        "Service Truck": [
            "Service Truck",
            "Service Trucks",
        ],
        "Diesel Bowser": [
            "Diesel Bowser",
            "Diesel Bowsers",
            "Dieselbowser",
            "Dieselbowsers",
        ],
        "Loader": [
            "Loader",
            "Loaders",
            "Front End Loader",
            "Front End Loaders",
            "Front-End Loader",
            "Front-End Loaders",
        ],
        "Drills": ["Drill", "Drills"],
        "LDV": ["LDV", "LDVs"],
    }

    if machine_type == "Total Fleet":
        aliases = sorted({
            alias
            for machine_aliases in category_aliases.values()
            for alias in machine_aliases
        })
    else:
        aliases = category_aliases.get(
            machine_type,
            [machine_type],
        )

    asset_filters = {
        "docstatus": 1,
        "asset_category": ["in", aliases],
    }

    if site and site != "All Sites":
        asset_filters["location"] = site

    assets = frappe.get_all(
        "Asset",
        filters=asset_filters,
        fields=[
            "name",
            "asset_name",
            "item_name",
            "asset_category",
            "location",
        ],
        order_by="name asc",
    )

    fleet_numbers = [row.name for row in assets]

    active_legal_groups = {
        "fire_suppression": "01. Automatic Fire Suppression",
        "brake_tested": "03. Dynamic Brake Testing",
        "frcs": "06. FRCS Compliance",
        "load_testing": "07. Load Testing",
        "pressure_vessels": "10. Pressure Vessels",
    }

    legal_by_fleet = {
        fleet_number: {
            "fire_suppression": False,
            "condition_monitoring_sections": set(),
            "brake_tested": False,
            "frcs": False,
            "load_testing": False,
            "maintenance_sections": set(),
            "pds_mpi": False,
            "pressure_vessels": False,
        }
        for fleet_number in fleet_numbers
    }

    if fleet_numbers:
        legal_rows = frappe.get_all(
            "Engineering Legals",
            filters={
                "fleet_number": ["in", fleet_numbers],
            },
            fields=[
                "fleet_number",
                "sections",
                "start_date",
                "expiry_date",
                "creation",
            ] + optional_snapshot_fields(),
        )

        for legal in legal_rows:
            fleet_number = legal.fleet_number
            section = (legal.sections or "").strip()

            if fleet_number not in legal_by_fleet:
                continue

            is_active = False

            if legal.start_date and legal.expiry_date:
                start_date = getdate(legal.start_date)
                expiry_date = getdate(legal.expiry_date)

                is_active = (
                    start_date <= month_end
                    and expiry_date >= month_start
                )

            relevant_date = legal.start_date or legal.creation
            is_saved_in_selected_month = False

            if relevant_date:
                relevant_date = getdate(relevant_date)

                is_saved_in_selected_month = (
                    month_start
                    <= relevant_date
                    <= month_end
                )

            reporting = record_reporting_rule(legal)
            if not reporting:
                continue
            selected = is_active if reporting["mode"] == "active_until_expiry" else is_saved_in_selected_month
            if selected:
                if reporting["category"] == "02. Condition Monitoring":
                    legal_by_fleet[fleet_number][
                        "condition_monitoring_sections"
                    ].add(section)

                for status_key, category in active_legal_groups.items():
                    if reporting["category"] == category:
                        legal_by_fleet[fleet_number][
                            status_key
                        ] = True

            if selected:
                if reporting["category"] == "08. Maintenance Schedules":
                    legal_by_fleet[fleet_number][
                        "maintenance_sections"
                    ].add(section)

                if reporting["category"] == "09. PDS-MPI Maintenance":
                    legal_by_fleet[fleet_number][
                        "pds_mpi"
                    ] = True

    result_rows = []

    for asset in assets:
        statuses = legal_by_fleet.get(asset.name, {})

        raw_category = (
            asset.asset_category or ""
        ).strip().upper()

        machine_type_labels = {
            "EXCAVATOR": "Excavator",
            "EXCAVATORS": "Excavator",
            "DOZER": "Dozer",
            "DOZERS": "Dozer",
            "ADT": "ADT",
            "ADTS": "ADT",
            "ARTICULATED DUMP TRUCK": "ADT",
            "ARTICULATED DUMP TRUCKS": "ADT",
            "WATER BOWSER": "Water Bowser",
            "WATER BOWSERS": "Water Bowser",
            "WATERBOWSER": "Water Bowser",
            "WATERBOWSERS": "Water Bowser",
            "GRADER": "Grader",
            "GRADERS": "Grader",
            "TLB": "TLB",
            "TLBS": "TLB",
            "LIGHTING PLANT": "Lighting Plant",
            "LIGHTING PLANTS": "Lighting Plant",
            "LIGHT TOWER": "Lighting Plant",
            "LIGHT TOWERS": "Lighting Plant",
            "SERVICE TRUCK": "Service Truck",
            "SERVICE TRUCKS": "Service Truck",
            "DIESEL BOWSER": "Diesel Bowser",
            "DIESEL BOWSERS": "Diesel Bowser",
            "DIESELBOWSER": "Diesel Bowser",
            "DIESELBOWSERS": "Diesel Bowser",
            "LOADER": "Loader",
            "LOADERS": "Loader",
            "FRONT END LOADER": "Loader",
            "FRONT END LOADERS": "Loader",
            "FRONT-END LOADER": "Loader",
            "FRONT-END LOADERS": "Loader",
            "DRILL": "Drills",
            "DRILLS": "Drills",
            "LDV": "LDV",
            "LDVS": "LDV",
        }

        active_condition_sections = set(
            statuses.get(
                "condition_monitoring_sections",
                set(),
            )
        )

        condition_monitoring_done = []
        condition_monitoring_missing = []

        if "Illumination Baseline" in active_condition_sections:
            condition_monitoring_done.append(
                "Illumination Baseline"
            )
        else:
            condition_monitoring_missing.append(
                "Illumination Baseline"
            )

        if (
            "Noise Level Baseline & Measurement"
            in active_condition_sections
        ):
            condition_monitoring_done.append(
                "Noise Level Baseline & Measurement"
            )
        else:
            condition_monitoring_missing.append(
                "Noise Level Baseline & Measurement"
            )

        if (
            {"NDT", "Machine NDT"}
            & active_condition_sections
        ):
            condition_monitoring_done.append(
                "NDT / Machine NDT"
            )
        else:
            condition_monitoring_missing.append(
                "NDT / Machine NDT"
            )

        active_maintenance_sections = set(
            statuses.get(
                "maintenance_sections",
                set(),
            )
        )

        maintenance_done = []

        if (
            {
                "Machine Service Records",
                "Service Schedule",
                "Wearcheck",
                "Brake Wear Measurements",
                "Maintenance Inspections",
            }
            & active_maintenance_sections
        ):
            maintenance_done.append(
                "Maintenance / Service"
            )

        if (
            "Tyre Inspection Report"
            in active_maintenance_sections
        ):
            maintenance_done.append("Tyre Surveys")

        if (
            "C-Track Inspection"
            in active_maintenance_sections
        ):
            maintenance_done.append("Track Surveys")

        is_service_truck = raw_category in {
            "SERVICE TRUCK",
            "SERVICE TRUCKS",
        }

        is_drill = raw_category in {
            "DRILL",
            "DRILLS",
        }

        result_rows.append({
            "name": asset.name,
            "asset_name": asset.asset_name,
            "item_name": asset.item_name,
            "asset_category": asset.asset_category,
            "machine_type": (
                machine_type_labels.get(
                    raw_category,
                    asset.asset_category or ""
                )
            ),
            "location": asset.location,
            "fire_suppression": bool(
                statuses.get("fire_suppression")
            ),
            "condition_monitoring": (
                not condition_monitoring_missing
            ),
            "condition_monitoring_done": (
                condition_monitoring_done
            ),
            "condition_monitoring_missing": (
                condition_monitoring_missing
            ),
            "brake_tested": bool(
                statuses.get("brake_tested")
            ),
            "frcs": bool(statuses.get("frcs")),

            "load_testing_applicable": is_service_truck,
            "load_testing": bool(
                statuses.get("load_testing")
            ),

            "maintenance_done": maintenance_done,

            "pds_mpi": bool(
                statuses.get("pds_mpi")
            ),

            "pressure_vessels_applicable": (
                is_drill or is_service_truck
            ),
            "pressure_vessels": bool(
                statuses.get("pressure_vessels")
            ),
        })

    return {
        "machine_type": machine_type,
        "site": site or "All Sites",
        "month": f"{month or ''}-{str(year)[-2:]}",
        "total": len(result_rows),
        "rows": result_rows,
    }
