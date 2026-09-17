import frappe
from frappe.desk.query_report import run
from urllib.parse import quote
from frappe.utils import flt, getdate, get_datetime, add_days, date_diff, nowdate, now_datetime, time_diff_in_hours
from datetime import timedelta
from engineering.engineering.report.availability_and_utilisation_engine import (
    availability_and_utilisation_engine as au_engine,
)
from engineering.engineering.page.daily_availability_dashboard.daily_availability_dashboard import (
    build_hours_based_performance_html,
  get_monthly_production_shift_hours,
)
from engineering.engineering.page.daily_availability_and_utilization_dashboard.ownership_sections import (
    get_ownership_average_sections,
    should_show_spare_average_section,
)


_ = frappe._

CATEGORY_MAP = {
    "ADT": "ADT",
    "ADT's": "ADT",
    "Dozer": "Dozer",
    "Dozer's": "Dozer",
    "Excavator": "Excavator",
    "Excavator's": "Excavator",
    "Grader": "Grader",
    "Service Truck": "Service Truck",
    "TLB": "TLB",
    "Water Bowser": "Water Bowser",
    "Diesel Bowsers": "Diesel Bowsers",
    "Drills": "Drills",
    "Loader": "Loader",
}

UI_CATEGORIES = [
    "ADT",
    "Dozer",
    "Excavator",
    "Grader",
    "Service Truck",
    "TLB",
    "Water Bowser",
    "Diesel Bowsers",
    "Drills",
    "Loader",
]

UI_TITLES = {
    "ADT": "ADT",
    "Dozer": "DOZER",
    "Excavator": "EXCAVATOR",
    "Grader": "GRADER",
    "Service Truck": "SERVICE TRUCK",
    "TLB": "TLB",
    "Water Bowser": "WATER BOWSER",
    "Diesel Bowsers": "DIESEL BOWSERS",
    "Drills": "DRILLS",
    "Loader": "LOADER",
}



def get_site_colour_map():
    """Return site header colours from Production Dashboard Setup singleton.

    This keeps the Daily Availability Dashboard aligned with the shared
    dashboard colour setup instead of hardcoding colours in this page.
    """
    try:
        setup = frappe.get_single("Production Dashboard Setup")
    except Exception:
        frappe.clear_messages()
        return {}

    colour_map = {}

    for row in setup.get("site_colour_mapping") or []:
        site = (row.location or "").strip()
        colour = (row.colour or "").strip()

        if site and colour:
            colour_map[site] = colour

    return colour_map


def get_site_header_colour(location):
    if not location:
        return "#f7f7f7"

    return get_site_colour_map().get(str(location).strip()) or "#f7f7f7"






def get_engine_spare_swing_asset_map(rows):
    """Build spare/swing highlighting directly from Engine shift rows."""

    out = {}

    for row in rows or []:

        if not isinstance(
            row,
            dict,
        ):
            continue

        if int(
            row.get("indent")
            or 0
        ) != 3:
            continue

        if not int(
            row.get(
                "is_spare_swing_unit"
            )
            or 0
        ):
            continue

        machine = get_machine(
            row
        )

        if not machine:
            continue

        out[machine] = (
            row.get(
                "spare_swing_reason"
            )
            or
            "Spare/Swing unit in Monthly Production Planning"
        )

    return out


def get_spare_swing_asset_map(filters):
    filters = filters or {}

    start_date = filters.get("start_date") or filters.get("from_date")
    end_date = filters.get("end_date") or filters.get("to_date")
    location = filters.get("location") or filters.get("site")

    if not start_date or not end_date:
        return {}

    args = {
        "start_date": start_date,
        "end_date": end_date,
    }

    conditions = [
        "mpp.docstatus < 2",
        "mpp.prod_month_start_date <= %(end_date)s",
        "mpp.prod_month_end_date >= %(start_date)s",
    ]

    if location:
        conditions.append("mpp.location = %(location)s")
        args["location"] = location

    condition_sql = " AND ".join(conditions)
    spare_map = {}

    def add_reason(asset_name, reason):
        if not asset_name:
            return

        asset_name = str(asset_name).strip()

        if not asset_name:
            return

        spare_map.setdefault(asset_name, set()).add(reason)

    try:
        truck_rows = frappe.db.sql(f"""
            SELECT DISTINCT etl.truck AS asset_name
            FROM `tabMonthly Production Planning` mpp
            INNER JOIN `tabExcavator Truck Link` etl
                ON etl.parent = mpp.name
               AND etl.parenttype = 'Monthly Production Planning'
            WHERE {condition_sql}
              AND IFNULL(etl.truck, '') != ''
              AND IFNULL(etl.excavator, '') = ''
        """, args, as_dict=True)

        for row in truck_rows:
            add_reason(row.get("asset_name"), "Spare/Swing unit Truck")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Daily Dashboard Spare/Swing Trucks")
        frappe.clear_messages()

    try:
        excavator_rows = frappe.db.sql(f"""
            SELECT DISTINCT etl.excavator AS asset_name
            FROM `tabMonthly Production Planning` mpp
            INNER JOIN `tabExcavator Truck Link` etl
                ON etl.parent = mpp.name
               AND etl.parenttype = 'Monthly Production Planning'
            WHERE {condition_sql}
              AND IFNULL(etl.excavator, '') != ''
              AND IFNULL(etl.truck, '') = ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM `tabExcavator Truck Link` assigned_etl
                  WHERE assigned_etl.parent = etl.parent
                    AND assigned_etl.parenttype = etl.parenttype
                    AND assigned_etl.excavator = etl.excavator
                    AND IFNULL(assigned_etl.truck, '') != ''
              )
        """, args, as_dict=True)

        for row in excavator_rows:
            add_reason(row.get("asset_name"), "Spare/Swing unit Excavator")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Daily Dashboard Spare/Swing Excavators")
        frappe.clear_messages()

    try:
        dozer_meta = frappe.get_meta("Dozers Planned")

        dozer_asset_field = None

        for fieldname in ("asset_name", "dozer", "asset"):
            if dozer_meta.has_field(fieldname):
                dozer_asset_field = fieldname
                break

        dozer_type_field = "dozing_type" if dozer_meta.has_field("dozing_type") else None

        if dozer_asset_field and dozer_type_field:
            dozer_rows = frappe.db.sql(f"""
                SELECT DISTINCT dp.`{dozer_asset_field}` AS asset_name
                FROM `tabMonthly Production Planning` mpp
                INNER JOIN `tabDozers Planned` dp
                    ON dp.parent = mpp.name
                   AND dp.parenttype = 'Monthly Production Planning'
                WHERE {condition_sql}
                  AND IFNULL(dp.`{dozer_asset_field}`, '') != ''
                  AND IFNULL(dp.`{dozer_type_field}`, '') = ''
            """, args, as_dict=True)

            for row in dozer_rows:
                add_reason(row.get("asset_name"), "Spare/Swing unit Dozer")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Daily Dashboard Spare/Swing Dozers")
        frappe.clear_messages()

    return {
        asset_name: ", ".join(sorted(reasons))
        for asset_name, reasons in spare_map.items()
    }


def apply_machine_scope_filter_to_dashboard_rows(rows, filters, spare_swing_asset_map):
    filters = filters or {}
    machine_scope = filters.get("machine_scope") or "Production + Swing/Spare Machines"
    frappe.local.daily_dashboard_au_target_filter = filters.get("au_target_filter") or "100% A & U"
    
    if machine_scope == "Production + Swing/Spare Machines":
        return rows

    filtered_rows = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        machine = get_machine(row)

        if not machine:
            continue

        is_spare = bool(machine in (spare_swing_asset_map or {}))

        if machine_scope == "Production Machines" and not is_spare:
            filtered_rows.append(row)

        elif machine_scope == "Swing/Spare Machines" and is_spare:
            filtered_rows.append(row)

    return filtered_rows



def build_summary_averages_from_machine_series(machine_series):
    out = {category: {"avail": None, "util": None} for category in UI_CATEGORIES}

    for category in UI_CATEGORIES:
        machines = machine_series.get(category) or []

        avail_values = [
            float(row.get("avail"))
            for row in machines
            if isinstance(row, dict) and row.get("avail") is not None
        ]

        util_values = [
            float(row.get("util"))
            for row in machines
            if isinstance(row, dict) and row.get("util") is not None
        ]

        out[category] = {
            "avail": (sum(avail_values) / len(avail_values)) if avail_values else None,
            "util": (sum(util_values) / len(util_values)) if util_values else None,
        }

    return out


def build_scope_averages_from_source_rows(rows):
    """Build Production and Swing/Spare averages using Engine maths."""

    production_avgs = {
        category: {
            "avail": None,
            "util": None,
        }
        for category in UI_CATEGORIES
    }

    spare_avgs = {
        category: {
            "avail": None,
            "util": None,
        }
        for category in UI_CATEGORIES
    }

    percentage_basis = getattr(
        frappe.local,
        "daily_dashboard_au_target_filter",
        "85% A & U",
    )

    shift_rows = [
        row
        for row in (rows or [])
        if isinstance(row, dict)
        and int(
            row.get("indent")
            or 0
        ) == 3
        and not row.get(
            "is_formula_row"
        )
    ]

    for want_spare, target in (
        (
            False,
            production_avgs,
        ),
        (
            True,
            spare_avgs,
        ),
    ):
        for category in UI_CATEGORIES:

            category_rows = [
                row
                for row in shift_rows
                if get_category(row)
                == category
                and bool(
                    int(
                        row.get(
                            "is_spare_swing_unit"
                        )
                        or 0
                    )
                )
                == want_spare
            ]

            if not category_rows:
                continue

            summary = (
                au_engine.build_summary_row(
                    category_rows,
                    indent=0,
                    asset_category=category,
                )
            )

            au_engine.apply_au_percentage_basis(
                [summary],
                percentage_basis,
            )

            target[category] = {
                "avail": (
                    summary.get(
                        "availability_percentage"
                    )
                ),
                "util": (
                    summary.get(
                        "utilisation_percentage"
                    )
                ),
            }

    return (
        production_avgs,
        spare_avgs,
    )


def get_au_target_multiplier(filters):
    au_target_filter = (filters or {}).get("au_target_filter") or "100% A & U"

    if au_target_filter == "85% A & U":
        return 0.85

    return 1.0


def apply_au_target_to_values(avgs, machine_series, filters):
    multiplier = get_au_target_multiplier(filters)

    if multiplier == 1.0:
        return avgs, machine_series

    for category, values in (avgs or {}).items():
        if not isinstance(values, dict):
            continue

        if values.get("util") is not None:
            values["util"] = round(
                float(values.get("util") or 0)
                * multiplier,
                1,
            )

    for category, machines in (machine_series or {}).items():
        for machine in machines or []:
            if not isinstance(machine, dict):
                continue

            if machine.get("util") is not None:
                machine["util"] = round(
                    float(machine.get("util") or 0)
                    * multiplier,
                    1,
                )

    return avgs, machine_series

def apply_true_availability_to_source_rows(
    source_rows,
    location,
    start_date,
    end_date,
    machine_scope,
    au_target_filter,
):
    if au_target_filter != "85% A & U":
        return source_rows

    report_machine_scope = machine_scope

    if (
        report_machine_scope
        == "Production + Swing/Spare Machines"
    ):
        report_machine_scope = "Include Swing/Spare"

    try:
        report_data = run(
            "Avail and Util report",
            filters={
                "start_date": start_date,
                "end_date": end_date,
                "from_date": start_date,
                "to_date": end_date,
                "location": location,
                "site": location,
                "machine_scope": report_machine_scope,
            },
            ignore_prepared_report=True,
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Daily Dashboard True Availability Error",
        )
        frappe.clear_messages()
        return source_rows

    report_rows = []

    if isinstance(report_data, dict):
        report_rows = (
            report_data.get("result")
            or report_data.get("data")
            or []
        )

    elif (
        isinstance(report_data, (list, tuple))
        and len(report_data) > 1
    ):
        report_rows = report_data[1] or []

    true_availability_values_by_machine = {}
    true_utilisation_values_by_machine = {}

    for row in report_rows:
        if not isinstance(row, dict):
            continue

        try:
            indent = int(
                row.get("indent")
                or 0
            )
        except Exception:
            indent = 0

        if indent != 2:
            continue

        required_hours = to_float(
            row.get("shift_required_hours")
            if row.get("shift_required_hours") not in (None, "")
            else row.get("Req Hrs")
        )

        if (
            required_hours is not None
            and required_hours <= 0
        ):
            continue

        machine = str(
            row.get("asset_name")
            or row.get("asset")
            or row.get("Asset")
            or ""
        ).strip()

        if not machine:
            continue

        true_availability = to_float(
            row.get("true_availability_percent")
            if row.get("true_availability_percent") not in (None, "")
            else row.get("True Availability %")
        )

        true_utilisation = to_float(
            row.get("true_utilisation_percent")
            if row.get("true_utilisation_percent") not in (None, "")
            else row.get("True Utilisation %")
        )

        if true_availability is not None:
            true_availability_values_by_machine.setdefault(
                machine,
                [],
            ).append(
                true_availability
            )

        if true_utilisation is not None:
            true_utilisation_values_by_machine.setdefault(
                machine,
                [],
            ).append(
                true_utilisation
            )

    true_availability_by_machine = {}
    true_utilisation_by_machine = {}

    for machine, values in (
        true_availability_values_by_machine.items()
    ):
        if not values:
            continue

        true_availability_by_machine[
            machine
        ] = round(
            sum(values) / len(values),
            1,
        )

    for machine, values in (
        true_utilisation_values_by_machine.items()
    ):
        if not values:
            continue

        true_utilisation_by_machine[
            machine
        ] = round(
            sum(values) / len(values),
            1,
        )

    for row in source_rows or []:
        if not isinstance(row, dict):
            continue

        machine = str(
            row.get("asset_name")
            or ""
        ).strip()

        if not machine:
            continue

        if machine in true_availability_by_machine:
            row["avail_percent"] = (
                true_availability_by_machine[
                    machine
                ]
            )

        if machine in true_utilisation_by_machine:
            row["util_percent"] = (
                true_utilisation_by_machine[
                    machine
                ]
            )

    return source_rows


def build_scope_averages_from_machine_series(
    machine_series,
    spare_swing_asset_map,
):
    production_series = {
        category: []
        for category in UI_CATEGORIES
    }

    spare_series = {
        category: []
        for category in UI_CATEGORIES
    }

    for category in UI_CATEGORIES:
        machines = (
            machine_series.get(category)
            or []
        )

        for machine in machines:
            if not isinstance(machine, dict):
                continue

            machine_name = str(
                machine.get("machine")
                or ""
            ).strip()

            if (
                machine_name
                and machine_name
                in (
                    spare_swing_asset_map
                    or {}
                )
            ):
                spare_series[category].append(
                    machine
                )
            else:
                production_series[category].append(
                    machine
                )

    production_avgs = (
        build_summary_averages_from_machine_series(
            production_series
        )
    )

    spare_avgs = (
        build_summary_averages_from_machine_series(
            spare_series
        )
    )

    return production_avgs, spare_avgs


def execute(filters=None):
    filters = frappe._dict(filters or {})

    if filters.get("site") and not filters.get("location"):
        filters["location"] = filters.get("site")

    if filters.get("location") and not filters.get("site"):
        filters["site"] = filters.get("location")

    summary_type = filters.get("summary_type") or "Average Per Machine"
    start_date = filters.get("start_date") or filters.get("from_date")
    end_date = filters.get("end_date") or filters.get("to_date")
    location = filters.get("location") or filters.get("site")
    machine_scope = filters.get("machine_scope") or "Production + Swing/Spare Machines"
    hours_display = filters.get("hours_display") or "Hours Average per Category"
    hours_asset = filters.get("hours_asset") or ""
    asset_ownership = (
        filters.get("asset_ownership")
        or "Isambane & Excavo Assets"
    )

    if not start_date:
        frappe.throw("Please select Start Date.")

    if not end_date:
        frappe.throw("Please select End Date.")

    if not location:
        frappe.throw("Please select Site.")

    # Do not display or calculate dates after today.
    if getdate(end_date) > getdate(nowdate()):
        end_date = nowdate()
        filters["end_date"] = end_date
        filters["to_date"] = end_date

    au_target_filter = (
        filters.get("au_target_filter")
        or "85% A & U"
    )

    frappe.local.daily_dashboard_au_target_filter = (
        au_target_filter
    )

    source_rows = fetch_grouped_data(
        location,
        start_date,
        end_date,
        machine_scope,
        au_target_filter,
        asset_ownership,
    )

    spare_swing_asset_map = get_engine_spare_swing_asset_map(source_rows)

    machine_series = build_machine_series_from_source_rows(
        source_rows
    )

    avgs = build_summary_averages_from_source_rows(
        source_rows
    )

    ownership_average_sections = []

    for ownership_scope, ownership_label in get_ownership_average_sections(
        asset_ownership
    ):
        ownership_rows = (
            source_rows
            if ownership_scope == asset_ownership
            else fetch_grouped_data(
                location,
                start_date,
                end_date,
                machine_scope,
                au_target_filter,
                ownership_scope,
            )
        )

        (
            ownership_production_avgs,
            ownership_spare_avgs,
        ) = build_scope_averages_from_source_rows(
            ownership_rows
        )

        ownership_average_sections.append({
            "asset_ownership": ownership_scope,
            "label": ownership_label,
            "production_avgs": ownership_production_avgs,
            "spare_avgs": ownership_spare_avgs,
        })

    dashboard_html = build_dashboard_html(
        location,
        start_date,
        end_date,
        avgs,
        machine_series,
        source_rows,
        summary_type,
        machine_scope,
        spare_swing_asset_map,
        ownership_average_sections,
        hours_display,
        hours_asset,
        asset_ownership,
    )

    columns = [{"label": "", "fieldname": "noop", "fieldtype": "Data", "width": 1}]
    data = [{"noop": ""}]

    return columns, data, dashboard_html


def fetch_grouped_data(
    location,
    start_date,
    end_date,
    machine_scope=None,
    au_target_filter=None,
    asset_ownership="Isambane & Excavo Assets",
):
    """Return dashboard rows calculated by the Availability and Utilisation Engine.

    The Engine is the source of truth.

    We request Engine shift rows at the 100% basis, apply the dashboard
    Production / Swing scope to those Engine shift rows, rebuild all
    category/date/machine summaries with Engine helpers, and finally apply
    the selected 85% or 100% A&U basis using the Engine itself.
    """
    frappe.clear_messages()

    percentage_basis = (
        au_target_filter
        or "85% A & U"
    )

    frappe.local.daily_dashboard_au_target_filter = (
        percentage_basis
    )

    engine_filters = frappe._dict({
        "from_date": start_date,
        "to_date": end_date,
        "locations": (
            [location]
            if location
            else []
        ),
        "assets": [],
        "companies": [],
        "asset_ownership": asset_ownership,
        "free_hours": 0,
        "production_machines_only": 0,
        "au_percentage_basis": "100% A & U",
    })

    engine_rows = (
        au_engine.get_data(
            engine_filters
        )
        or []
    )

    shift_rows = [
        dict(row)
        for row in engine_rows
        if isinstance(row, dict)
        and int(
            row.get("indent")
            or 0
        ) == 3
        and not row.get(
            "is_formula_row"
        )
    ]

    scope = (
        machine_scope
        or "Production + Swing/Spare Machines"
    )

    if scope == "Production Machines":
        shift_rows = [
            row
            for row in shift_rows
            if not int(
                row.get(
                    "is_spare_swing_unit"
                )
                or 0
            )
        ]

    elif scope == "Swing/Spare Machines":
        shift_rows = [
            row
            for row in shift_rows
            if int(
                row.get(
                    "is_spare_swing_unit"
                )
                or 0
            )
        ]

    if not shift_rows:
        frappe.clear_messages()
        return []

    rows = au_engine.build_tree_rows(
        shift_rows
    )

    au_engine.apply_au_percentage_basis(
        rows,
        percentage_basis,
    )

    frappe.clear_messages()

    return rows


def to_float(value):
    if value in (None, ""):
        return None

    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").strip()

    try:
        return float(value)
    except Exception:
        return None


def get_any(row, keys):
    for key in keys:
        if isinstance(row, dict) and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def get_category(row):
    value = get_any(row, [
        "asset_category",
        "Asset Category",
        "category",
        "Category",
    ])

    if value in CATEGORY_MAP:
        return CATEGORY_MAP[value]

    return value


def get_indent(row):
    try:
        return int(row.get("indent") or 0)
    except Exception:
        return 0


def get_machine(row):
    machine = get_any(row, [
        "asset_name",
        "Asset Name",
        "asset",
        "Asset",
        "machine",
        "Machine",
        "plant_no",
        "Plant No",
    ])

    if not machine:
        return ""

    machine = str(machine).strip()

    if machine in CATEGORY_MAP:
        return ""

    return machine


def get_avail(row):
    return to_float(get_any(row, [
        "availability_percentage",
        "avail_percent",
        "plant_shift_availability",
        "Avail",
        "availability",
        "Availability",
    ]))


def get_util(row):
    return to_float(get_any(row, [
        "utilisation_percentage",
        "util_percent",
        "plant_shift_utilisation",
        "Util",
        "utilisation",
        "Utilisation",
    ]))


def build_summary_averages_from_source_rows(rows):
    out = {category: {"avail": None, "util": None} for category in UI_CATEGORIES}

    for row in rows:
        if not isinstance(row, dict):
            continue

        category = get_category(row)

        if category not in out:
            continue

        machine = get_machine(row)

        if machine:
            continue

        summary_scope = (
            row.get("summary_scope")
            or "overall"
        )

        if summary_scope != "overall":
            continue

        out[category] = {
            "avail": get_avail(row),
            "util": get_util(row),
        }

    for category in UI_CATEGORIES:
        if out[category]["avail"] is not None or out[category]["util"] is not None:
            continue

        category_rows = [
            row for row in rows
            if isinstance(row, dict) and get_category(row) == category
        ]

        if not category_rows:
            continue

        min_indent = min(get_indent(row) for row in category_rows)
        parent_rows = [row for row in category_rows if get_indent(row) == min_indent]

        if parent_rows:
            row = parent_rows[0]
            out[category] = {
                "avail": get_avail(row),
                "util": get_util(row),
            }

    return out


def build_machine_series_from_source_rows(rows):
    """Build one period summary per machine using Engine summary logic."""

    grouped = {
        category: {}
        for category in UI_CATEGORIES
    }

    for row in rows or []:

        if not isinstance(
            row,
            dict,
        ):
            continue

        if int(
            row.get("indent")
            or 0
        ) != 3:
            continue

        category = get_category(
            row
        )

        machine = get_machine(
            row
        )

        if (
            category not in grouped
            or not machine
        ):
            continue

        grouped[
            category
        ].setdefault(
            machine,
            [],
        ).append(
            row
        )

    percentage_basis = getattr(
        frappe.local,
        "daily_dashboard_au_target_filter",
        "85% A & U",
    )

    output = {
        category: []
        for category in UI_CATEGORIES
    }

    for category in UI_CATEGORIES:

        for machine, machine_rows in sorted(
            grouped[
                category
            ].items()
        ):

            summary = (
                au_engine.build_summary_row(
                    machine_rows,
                    indent=2,
                    asset_category=category,
                    asset_name=machine,
                )
            )

            au_engine.apply_au_percentage_basis(
                [summary],
                percentage_basis,
            )

            output[
                category
            ].append({
                "machine": machine,
                "avail": (
                    summary.get(
                        "availability_percentage"
                    )
                ),
                "util": (
                    summary.get(
                        "utilisation_percentage"
                    )
                ),
            })

    return output


def bubble_colour(metric, value):
    if value is None:
        return "isd-mbubble-red"

    value = float(value)

    target_filter = getattr(
        frappe.local,
        "daily_dashboard_au_target_filter",
        "85% A & U",
    )

    target = 85 if target_filter == "85% A & U" else 100
    warning = target - 10

    if value >= target:
        return "isd-mbubble-green"

    if value >= warning:
        return "isd-mbubble-blue" + chr(34) + " style=" + chr(34) + "background:#bfdbfe !important;border-color:#1d4ed8 !important;"

    return "isd-mbubble-red"


def fmt_percent(value):
    if value is None:
        return "0.0%"
    return f"{min(100.0, max(0.0, float(value))):.1f}%"

def esc(value):
    return frappe.utils.escape_html(str(value or ""))


def get_popup_shift_window(breakdown_start):
    breakdown_start = get_datetime(breakdown_start)
    breakdown_time = breakdown_start.time()

    if breakdown_time >= get_datetime("2000-01-01 06:00:00").time() and breakdown_time < get_datetime("2000-01-01 18:00:00").time():
        shift_name = "Day Shift"
        window_start = get_datetime(
            f"{getdate(breakdown_start)} 06:00:00"
        )
        window_end = get_datetime(
            f"{getdate(breakdown_start)} 18:00:00"
        )

        excluded_windows = [
            (
                get_datetime(
                    f"{getdate(breakdown_start)} 06:00:00"
                ),
                get_datetime(
                    f"{getdate(breakdown_start)} 08:00:00"
                ),
                "Startup",
            ),
            (
                get_datetime(
                    f"{getdate(breakdown_start)} 13:00:00"
                ),
                get_datetime(
                    f"{getdate(breakdown_start)} 14:00:00"
                ),
                "Fatigue",
            ),
        ]

        return (
            shift_name,
            window_start,
            window_end,
            excluded_windows,
        )

    if breakdown_time >= get_datetime("2000-01-01 18:00:00").time():
        shift_date = getdate(breakdown_start)
    else:
        shift_date = add_days(
            getdate(breakdown_start),
            -1,
        )

    next_date = add_days(shift_date, 1)

    shift_name = "Night Shift"
    window_start = get_datetime(
        f"{shift_date} 18:00:00"
    )
    window_end = get_datetime(
        f"{next_date} 06:00:00"
    )

    excluded_windows = [
        (
            get_datetime(
                f"{shift_date} 18:00:00"
            ),
            get_datetime(
                f"{shift_date} 20:00:00"
            ),
            "Startup",
        ),
        (
            get_datetime(
                f"{next_date} 01:00:00"
            ),
            get_datetime(
                f"{next_date} 02:00:00"
            ),
            "Fatigue",
        ),
    ]

    return (
        shift_name,
        window_start,
        window_end,
        excluded_windows,
    )


def get_popup_overlap_hours(
    first_start,
    first_end,
    second_start,
    second_end,
):
    overlap_start = max(
        first_start,
        second_start,
    )

    overlap_end = min(
        first_end,
        second_end,
    )

    if overlap_end <= overlap_start:
        return 0.0

    return float(
        time_diff_in_hours(
            overlap_end,
            overlap_start,
        )
    )


def calculate_popup_availability(
    breakdown_start,
    resolved_datetime=None,
    au_target_filter=None,
):
    required_hours = 9.0

    if not breakdown_start:
        return {
            "shift": "",
            "required_hours": required_hours,
            "raw_downtime": 0.0,
            "startup_excluded": 0.0,
            "fatigue_excluded": 0.0,
            "total_excluded": 0.0,
            "total_downtime": 0.0,
            "available_hours": required_hours,
            "actual_availability": 100.0,
            "displayed_availability": (
                85.0
                if au_target_filter == "85% A & U"
                else 100.0
            ),
            "target_label": (
                au_target_filter
                or "100% A & U"
            ),
        }

    (
        shift_name,
        shift_start,
        shift_end,
        excluded_windows,
    ) = get_popup_shift_window(
        breakdown_start
    )

    actual_start = max(
        get_datetime(breakdown_start),
        shift_start,
    )

    actual_end = min(
        get_datetime(
            resolved_datetime
            or now_datetime()
        ),
        shift_end,
    )

    if actual_end <= actual_start:
        raw_downtime = 0.0
    else:
        raw_downtime = float(
            time_diff_in_hours(
                actual_end,
                actual_start,
            )
        )

    startup_excluded = 0.0
    fatigue_excluded = 0.0

    for (
        excluded_start,
        excluded_end,
        excluded_type,
    ) in excluded_windows:
        excluded_hours = get_popup_overlap_hours(
            actual_start,
            actual_end,
            excluded_start,
            excluded_end,
        )

        if excluded_type == "Startup":
            startup_excluded += excluded_hours
        else:
            fatigue_excluded += excluded_hours

    total_excluded = min(
        startup_excluded + fatigue_excluded,
        raw_downtime,
    )

    effective_downtime = max(
        raw_downtime - total_excluded,
        0.0,
    )

    effective_downtime = min(
        effective_downtime,
        required_hours,
    )

    available_hours = max(
        required_hours - effective_downtime,
        0.0,
    )

    actual_availability = round(
        (
            available_hours
            / required_hours
        ) * 100,
        1,
    )

    multiplier = (
        0.85
        if au_target_filter == "85% A & U"
        else 1.0
    )

    return {
        "shift": shift_name,
        "required_hours": required_hours,
        "raw_downtime": round(
            raw_downtime,
            2,
        ),
        "startup_excluded": round(
            startup_excluded,
            2,
        ),
        "fatigue_excluded": round(
            fatigue_excluded,
            2,
        ),
        "total_excluded": round(
            total_excluded,
            2,
        ),
        "total_downtime": round(
            effective_downtime,
            2,
        ),
        "available_hours": round(
            available_hours,
            2,
        ),
        "actual_availability": actual_availability,
        "displayed_availability": round(
            actual_availability * multiplier,
            1,
        ),
        "target_label": (
            au_target_filter
            or "100% A & U"
        ),
    }





def get_adt_dozer_excavator_cards_all_summary_types(location, start_date, end_date, machine_scope):
    """
    ADT, Dozer, Excavator cards for all summary types.
    Reads Production > Avail and Util report top rows only.
    """
    out = {
        "ADT": {"avail": 0.0, "util": 0.0},
        "Dozer": {"avail": 0.0, "util": 0.0},
        "Excavator": {"avail": 0.0, "util": 0.0},
    }

    def clean_number(value):
        if value in (None, ""):
            return None
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        try:
            return float(value)
        except Exception:
            return None

    def norm(value):
        return (
            str(value or "")
            .strip()
            .lower()
            .replace(" ", "")
            .replace("_", "")
            .replace("-", "")
            .replace("'", "")
        )

    category_map = {
        "adt": "ADT",
        "adts": "ADT",
        "dozer": "Dozer",
        "dozers": "Dozer",
        "excavator": "Excavator",
        "excavators": "Excavator",
    }

    try:
        from frappe.desk.query_report import run

        report_data = run(
            "Avail and Util report",
            filters={
                "start_date": start_date,
                "end_date": end_date,
                "from_date": start_date,
                "to_date": end_date,
                "location": location,
                "site": location,
                "machine_scope": machine_scope or "Production Machines",
            },
            ignore_prepared_report=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Dashboard ADT Dozer Excavator Cards Error")
        return out

    rows = []

    if isinstance(report_data, dict):
        rows = report_data.get("result") or report_data.get("data") or []
    elif isinstance(report_data, (list, tuple)) and len(report_data) > 1:
        rows = report_data[1] or []
    elif isinstance(report_data, list):
        rows = report_data

    for row in rows or []:
        if not isinstance(row, dict):
            continue

        try:
            indent = int(row.get("indent") or 0)
        except Exception:
            indent = 0

        if indent != 0:
            continue

        raw_category = (
            row.get("asset_category")
            or row.get("Asset Category")
            or row.get("category")
            or row.get("Category")
            or ""
        )

        category = category_map.get(norm(raw_category))

        if category not in out:
            continue

        avail = clean_number(
            row.get("plant_shift_availability")
            if row.get("plant_shift_availability") not in (None, "")
            else row.get("Avail (%)")
        )

        util = clean_number(
            row.get("plant_shift_utilisation")
            if row.get("plant_shift_utilisation") not in (None, "")
            else row.get("Util (%)")
        )

        if avail is not None:
            out[category]["avail"] = avail

        if util is not None:
            out[category]["util"] = util

    return out



def build_dashboard_html(
    location,
    start_date,
    end_date,
    avgs,
    machine_series,
    source_rows=None,
    summary_type="Average Per Machine",
    machine_scope="Production + Swing/Spare Machines",
    spare_swing_asset_map=None,
    ownership_average_sections=None,
    hours_display="Hours Average per Category",
    hours_asset=None,
    asset_ownership="Isambane & Excavo Assets",
):
    site_safe = esc(location)
    summary_type_safe = esc(summary_type or "Average Per Machine")
    header_colour = get_site_header_colour(location)


    ownership_average_sections = ownership_average_sections or []

    au_target_filter = getattr(
        frappe.local,
        "daily_dashboard_au_target_filter",
        "85% A & U",
    )

    month_end_url = (
        "/app/query-report/"
        "Availability%20and%20Utilisation%20Month%20End%20Report"
        f"?from_date={quote(str(start_date or ''))}"
        f"&to_date={quote(str(end_date or ''))}"
        f"&start_date={quote(str(start_date or ''))}"
        f"&end_date={quote(str(end_date or ''))}"
        f"&location={quote(str(location or ''))}"
        f"&site={quote(str(location or ''))}"
        f"&au_target_filter={quote(str(au_target_filter))}"
        f"&au_percentage_basis={quote(str(au_target_filter))}"
    )


    def build_metric_cards(
        metric_values,
        card_machine_scope,
        card_asset_ownership,
    ):
        cards = []

        for category in UI_CATEGORIES:
            values = (
                metric_values.get(category)
                or {}
            )

            av = values.get("avail")
            ut = values.get("util")

            category_month_end_url = (
                f"{month_end_url}"
                f"&asset_category={quote(str(category))}"
                f"&machine_scope={quote(str(card_machine_scope))}"
                f"&asset_ownership={quote(str(card_asset_ownership))}"
            )

            cards.append(f'''
<div class="isd-metric">
    <div class="isd-metric-title">
        {esc(category)} Avg
    </div>

    <div class="isd-pill-row">
        <div
            class="isd-mbubble {bubble_colour('avail', av)}"
            onclick="window.open('{category_month_end_url}', '_blank')"
            title="Open Availability and Utilisation Month End Report"
            style="cursor:pointer;"
        >
            <div class="isd-mbubble-label">
                Avail.
            </div>

            <div class="isd-mbubble-value">
                {fmt_percent(av)}
            </div>
        </div>

        <div
            class="isd-mbubble {bubble_colour('util', ut)}"
            onclick="window.open('{category_month_end_url}', '_blank')"
            title="Open Availability and Utilisation Month End Report"
            style="cursor:pointer;"
        >
            <div class="isd-mbubble-label">
                Util.
            </div>

            <div class="isd-mbubble-value">
                {fmt_percent(ut)}
            </div>
        </div>
    </div>
</div>
''')

        return "".join(cards)

    metric_bands = []

    for ownership_section in ownership_average_sections:
        ownership_label = esc(
            ownership_section.get("label")
        )
        ownership_scope = ownership_section.get(
            "asset_ownership"
        )

        production_metric_cards = build_metric_cards(
            ownership_section.get("production_avgs") or {},
            "Production Machines",
            ownership_scope,
        )

        metric_bands.append(f'''
        <div
            class="isd-scope-banner-title"
            style="
                padding:8px 12px;
                background:#dbeafe;
                color:#1e3a8a;
                border-bottom:1px solid #93c5fd;
                font-size:12px;
                font-weight:900;
                text-transform:uppercase;
            "
        >
            {ownership_label} - Production Machines
        </div>

        <div class="isd-band" style="--site-colour:#4fa3dc;">
            <div class="isd-metrics">
                {production_metric_cards}
            </div>
        </div>
''')

        if not should_show_spare_average_section(ownership_scope):
            continue

        spare_metric_cards = build_metric_cards(
            ownership_section.get("spare_avgs") or {},
            "Swing/Spare Machines",
            ownership_scope,
        )

        metric_bands.append(f'''
        <div
            class="isd-scope-banner-title"
            style="
                padding:8px 12px;
                background:#dcfce7;
                color:#166534;
                border-top:1px solid #86efac;
                border-bottom:1px solid #86efac;
                font-size:12px;
                font-weight:900;
                text-transform:uppercase;
            "
        >
            {ownership_label} - Swing/Spare Machines
        </div>

        <div class="isd-band" style="--site-colour:#55c878;">
            <div class="isd-metrics">
                {spare_metric_cards}
            </div>
        </div>
''')

    metric_bands_html = "".join(metric_bands)

    chart_html = build_selected_summary_chart_html(
        summary_type,
        location,
        source_rows or [],
        avgs,
        machine_series,
        start_date,
        end_date,
        machine_scope,
        spare_swing_asset_map,
        getattr(frappe.local, "daily_dashboard_au_target_filter", "100% A & U")
    )
    trend_html = build_trend_html(location, start_date, end_date, machine_scope)

    legend_target = 85 if au_target_filter == "85% A & U" else 100
    legend_warning = legend_target - 10

    au_dashboard_html = f'''
<div class="isd-hourly-dashboard isd-daily-availability-dashboard">
    <div class="isd-note">
        Showing: {summary_type_safe} | {site_safe} | {start_date} to {end_date}. Averages and graphs are calculated by the Availability and Utilisation Engine.
    </div>

    <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;padding:10px 12px;margin:8px 0;border:1px solid #d8dde2;border-radius:8px;background:#ffffff;font-size:12px;font-weight:700;">
        <strong>Colour Legend ({esc(au_target_filter)}):</strong>

        <span>
            <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#dcfce7;border:2px solid #1e8e3e;vertical-align:middle;margin-right:5px;"></span>
            Green: ≥ {legend_target}%
        </span>

        <span>
            <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#dbeafe;border:2px solid #1a73e8;vertical-align:middle;margin-right:5px;"></span>
            Blue: {legend_warning}% – &lt;{legend_target}%
        </span>

        <span>
            <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#fee2e2;border:2px solid #d93025;vertical-align:middle;margin-right:5px;"></span>
            Red: &lt;{legend_warning}%
        </span>
    </div>

    <div class="isd-site">
        <div class="isd-site-title">{summary_type_safe} | {site_safe} | {start_date} to {end_date}</div>

        {metric_bands_html}

        <div class="isd-contentrow">
            {chart_html}
            {trend_html}
        </div>
    </div>
</div>
'''

    hours_groups = {}

    for row in source_rows or []:
        if (
            not isinstance(row, dict)
            or get_indent(row) != 3
            or row.get("is_formula_row")
        ):
            continue

        category = get_category(row)
        machine = get_machine(row)

        if category not in UI_CATEGORIES or not machine:
            continue

        hours_groups.setdefault((category, machine), []).append(row)

    hours_source_rows = [
        {
            "asset_category": category,
            "asset_name": machine,
            "_au_source_rows": rows,
        }
        for (category, machine), rows in hours_groups.items()
    ]

    planned_shift_hours = get_monthly_production_shift_hours(
        location,
        start_date,
        end_date,
    )

    if hours_asset:
        hours_source_rows = [
            row
            for row in hours_source_rows
            if get_machine(row) == hours_asset
        ]

    if hours_display == "Hours per Asset":
        if hours_asset and hours_source_rows:
            source_row = hours_source_rows[0]
            machine = get_machine(source_row)
            category = get_category(source_row)

            hours_dashboard_html = build_hours_based_performance_html(
                [source_row],
                start_date,
                end_date,
                heading_override=(
                    f"{machine} — "
                    f"{UI_TITLES.get(category, category)}"
                ),
                planned_shift_hours=planned_shift_hours,
            )
        elif hours_source_rows:
            category_groups = {}

            for source_row in hours_source_rows:
                category = get_category(source_row)
                category_groups.setdefault(
                    category,
                    [],
                ).append(source_row)

            grouped_sections = []

            for category in UI_CATEGORIES:
                category_rows = category_groups.get(category) or []

                if not category_rows:
                    continue

                category_title = esc(
                    UI_TITLES.get(category, category)
                )

                asset_sections = []

                for source_row in sorted(
                    category_rows,
                    key=lambda row: get_machine(row),
                ):
                    machine = get_machine(source_row)

                    asset_sections.append(
                        build_hours_based_performance_html(
                            [source_row],
                            start_date,
                            end_date,
                            heading_override=machine,
                            planned_shift_hours=planned_shift_hours,
                        )
                    )

                grouped_sections.append(f"""
<div style="margin:8px 0 18px;padding:10px 14px;background:#dbeafe;color:#1e3a8a;font-size:14px;font-weight:900;">
    {category_title} · {len(category_rows)} asset(s)
</div>
<div style="padding-left:16px;">
    {"".join(asset_sections)}
</div>
""")

            hours_dashboard_html = "".join(grouped_sections)
        else:
            hours_dashboard_html = '<div class="frappe-card" style="padding:18px;">No hours data found for the selected asset.</div>'
    else:
        hours_dashboard_html = build_hours_based_performance_html(
            hours_source_rows,
            start_date,
            end_date,
            planned_shift_hours=planned_shift_hours,
        )

    return f'''
<div class="daily-dashboard-tabs" style="margin-bottom:14px;display:flex;gap:8px;flex-wrap:wrap;">
    <button type="button" class="btn btn-primary daily-dashboard-tab-button" data-tab="hours">Hours Based Performance</button>
    <button type="button" class="btn btn-default daily-dashboard-tab-button" data-tab="au">A&amp;U Performance</button>
</div>
<div class="daily-dashboard-tab-panel" data-panel="hours">{hours_dashboard_html}</div>
<div class="daily-dashboard-tab-panel" data-panel="au" style="display:none;">{au_dashboard_html}</div>
'''




def get_row_date(row):
    value = get_any(row, [
        "date",
        "Date",
        "posting_date",
        "Posting Date",
        "transaction_date",
        "Transaction Date",
        "shift_date",
        "Shift Date",
        "work_date",
        "Work Date",
        "from_date",
        "From Date",
    ])

    if not value:
        return ""

    return str(value)[:10]


def avg_or_none(values):
    values = [float(v) for v in values if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def daily_height(value):
    if value is None:
        return 2

    try:
        value = float(value)
    except Exception:
        return 2

    value = max(0.0, min(100.0, value))

    if value <= 0:
        return 2

    # Align bars with Y-axis percentage scale.
    # Chart plot height is 220px:
    # 100% = 220px
    # 75%  = 165px
    # 62.5% = 138px
    return max(2, int(round((value / 100.0) * 220)))



def dashboard_bar_height(value):
    if value is None:
        return 2

    try:
        value = float(value)
    except Exception:
        return 2

    value = max(0.0, min(100.0, value))

    if value <= 0:
        return 2

    return max(2, int(round((value / 100.0) * 220)))

def build_selected_summary_chart_html(summary_type, location, source_rows, avgs, machine_series, start_date, end_date, machine_scope="Production + Swing/Spare Machines", spare_swing_asset_map=None, au_target_filter="100% A & U"):
    summary_type = summary_type or "Average Per Machine"

    if summary_type == "Daily Summary":
        return build_daily_summary_chart_html(location, start_date, end_date, machine_scope, au_target_filter)

    if summary_type == "Weekly Summary":
        return build_weekly_summary_chart_html(avgs, machine_scope)

    if summary_type == "Monthly Summary":
        return build_monthly_summary_chart_html(avgs, machine_scope)

    return build_chart_html(machine_series, machine_scope, spare_swing_asset_map)


def build_daily_summary_chart_html(location, start_date, end_date, machine_scope="Production + Swing/Spare Machines", au_target_filter="100% A & U"):
    all_dates = []

    try:
        start = getdate(start_date)
        end = getdate(end_date)
        total_days = date_diff(end, start) + 1

        for i in range(max(total_days, 0)):
            all_dates.append(str(add_days(start, i)))
    except Exception:
        all_dates = []

    if not all_dates:
        return f'''
<div class="isd-chart-stack">
    <div class="isd-chart-section isd-daily-summary-section">
        <div class="isd-chart-section-title">FULL DAY AVERAGE AVAILABILITY &amp; UTILISATION - {esc(machine_scope or "Production + Swing/Spare Machines").upper()}</div>
        <div class="isd-no-machine-data">No daily summary data found for the selected date range.</div>
    </div>
</div>
'''

    daily_category_values = {}

    for date_value in all_dates:
        effective_au_target_filter = (
            au_target_filter
            or "85% A & U"
        )

        day_rows = fetch_grouped_data(
            location,
            date_value,
            date_value,
            machine_scope,
            effective_au_target_filter,
        )

        day_avgs = build_summary_averages_from_source_rows(
            day_rows
        )

        for category in UI_CATEGORIES:
            values = day_avgs.get(category) or {}

            daily_category_values[(category, date_value)] = {
                "avail": values.get("avail") if values.get("avail") is not None else 0.0,
                "util": values.get("util") if values.get("util") is not None else 0.0,
            }

    bars = []
    day_labels = []
    group_labels = []
    total_day_count = 0

    for category in UI_CATEGORIES:
        for date_value in all_dates:
            day = str(date_value)[8:10]
            values = daily_category_values.get((category, date_value)) or {}

            av = values.get("avail")
            ut = values.get("util")

            if av is None:
                av = 0.0

            if ut is None:
                ut = 0.0

            bars.append(
                f"<div class='isd-bar avail' title='{esc(category)} {day} Availability: {fmt_percent(av)}' style='height:{daily_height(av)}px;position:relative;overflow:visible;'>"
                f"<span style='position:absolute;top:-16px;left:50%;transform:translateX(-50%);font-size:9px;font-weight:800;color:#111827;white-space:nowrap;'>{fmt_percent(av)}</span>"
                f"</div>"
            )

            bars.append(
                f"<div class='isd-bar util' title='{esc(category)} {day} Utilisation: {fmt_percent(ut)}' style='height:{daily_height(ut)}px;position:relative;overflow:visible;'>"
                f"<span style='position:absolute;top:-16px;left:50%;transform:translateX(-50%);font-size:9px;font-weight:800;color:#111827;white-space:nowrap;'>{fmt_percent(ut)}</span>"
                f"</div>"
            )

            day_labels.append(f"<div class='isd-machinelab'>{esc(day)}</div>")

        group_labels.append(
            f"<div class='isd-summary-group-label' style='grid-column: span {len(all_dates)};'>{esc(UI_TITLES.get(category, category))}</div>"
        )

        total_day_count += len(all_dates)

    grid_template = f"repeat({total_day_count * 2}, minmax(18px, 1fr))"
    day_template = f"repeat({total_day_count}, minmax(44px, 1fr))"
    min_width = max(1200, total_day_count * 58)

    return f'''
<div class="isd-chart-stack">
    <div class="isd-chart-section isd-daily-summary-section">
        <div class="isd-chart-section-title">FULL DAY AVERAGE AVAILABILITY &amp; UTILISATION - {esc(machine_scope or "Production + Swing/Spare Machines").upper()}</div>

        <div class="isd-chart" style="min-width:{min_width}px;">
            <div class="isd-yaxis">
                <div>100%</div>
                <div>90%</div>
                <div>80%</div>
                <div>70%</div>
                <div>60%</div>
                <div>50%</div>
                <div>40%</div>
                <div>30%</div>
                <div>20%</div>
                <div>10%</div>
                <div>0%</div>
            </div>



            <div class="isd-chart-grid" style="grid-template-columns:{grid_template};">
                {''.join(bars)}
            </div>

            <div class="isd-machinelabels" style="grid-template-columns:{day_template};">
                {''.join(day_labels)}
                {''.join(group_labels)}
            </div>
        </div>
    </div>
</div>
'''



def build_weekly_summary_chart_html(avgs, machine_scope="Production + Swing/Spare Machines"):
    top_categories = ["ADT", "Excavator", "Dozer"]
    bottom_categories = ["Grader", "Service Truck", "TLB", "Water Bowser", "Diesel Bowsers", "Drills", "Loader"]

    machine_scope_safe = esc(machine_scope or "Production + Swing/Spare Machines")

    top_title = f"Weekly Summary- ADT / EXCAVATOR / DOZER- {machine_scope_safe}"
    bottom_title = f"Weekly Summary- SUPPORT EQUIPMENT & DRILLS- {machine_scope_safe}"

    return f'''
<div class="isd-chart-stack">
    {build_monthly_summary_section(top_title, top_categories, avgs)}
    {build_monthly_summary_section(bottom_title, bottom_categories, avgs)}
</div>
'''

def build_monthly_summary_chart_html(avgs, machine_scope="Production + Swing/Spare Machines"):
    top_categories = ["ADT", "Excavator", "Dozer"]
    bottom_categories = ["Grader", "Service Truck", "TLB", "Water Bowser", "Diesel Bowsers", "Drills", "Loader"]

    machine_scope_safe = esc(machine_scope or "Production + Swing/Spare Machines")

    top_title = f"Monthly Summary - ADT / EXCAVATOR / DOZER- {machine_scope_safe}"
    bottom_title = f"Monthly Summary - SUPPORT EQUIPMENT & DRILLS- {machine_scope_safe}"

    return f'''
<div class="isd-chart-stack">
    {build_monthly_summary_section(top_title, top_categories, avgs)}
    {build_monthly_summary_section(bottom_title, bottom_categories, avgs)}
</div>
'''

def build_monthly_summary_section(title, categories, avgs):
    bars = []
    labels = []

    for category in categories:
        values = avgs.get(category) or {}
        av = values.get("avail")
        ut = values.get("util")

        av_class = "isd-bar avail" + (" nodata" if av is None else "")
        ut_class = "isd-bar util" + (" nodata" if ut is None else "")

        bars.append(
            f"<div class='{av_class}' title='{esc(category)} Availability: {fmt_percent(av)}' style='height:{daily_height(av)}px;position:relative;overflow:visible;'>"
            f"<span style='position:absolute;top:-16px;left:50%;transform:translateX(-50%);font-size:9px;font-weight:800;color:#111827;white-space:nowrap;'>{fmt_percent(av)}</span>"
            f"</div>"
        )

        bars.append(
            f"<div class='{ut_class}' title='{esc(category)} Utilisation: {fmt_percent(ut)}' style='height:{daily_height(ut)}px;position:relative;overflow:visible;'>"
            f"<span style='position:absolute;top:-16px;left:50%;transform:translateX(-50%);font-size:9px;font-weight:800;color:#111827;white-space:nowrap;'>{fmt_percent(ut)}</span>"
            f"</div>"
        )

        labels.append(f"<div class='isd-machinelab'>{esc(UI_TITLES.get(category, category))}</div>")

    grid_template = f"repeat({len(categories) * 2}, minmax(90px, 1fr))"
    label_template = f"repeat({len(categories)}, minmax(180px, 1fr))"

    return f'''
<div class="isd-chart-section">
    <div class="isd-chart-section-title">{esc(title)}</div>

    <div class="isd-chart" style="min-width:100%;">
        <div class="isd-yaxis">
            <div>100%</div><div>90%</div><div>80%</div><div>70%</div><div>60%</div>
            <div>50%</div><div>40%</div><div>30%</div><div>20%</div><div>10%</div><div>0%</div>
        </div>



        <div class="isd-chart-grid" style="grid-template-columns:{grid_template};">
            {''.join(bars)}
        </div>

        <div class="isd-machinelabels" style="grid-template-columns:{label_template};">
            {''.join(labels)}
        </div>
    </div>
</div>
'''


def build_trend_html(location, start_date, end_date, machine_scope="Production + Swing/Spare Machines"):

    avail_util_url = (
        "/app/query-report/Availability%20and%20Utilisation%20Engine"
        f"?start_date={quote(str(start_date or ''))}"
        f"&end_date={quote(str(end_date or ''))}"
        f"&location={quote(str(location or ''))}"
        f"&machine_scope={quote(str(machine_scope or 'Production + Swing/Spare Machines'))}"
    )

    return f'''
<div class="isd-side">
    <div
        id="open-avail-util-only-button"
        onclick="window.open('{avail_util_url}', '_blank')"
        style="width:140px;min-height:38px;border:2px solid #0d6efd;border-radius:8px;background:#dbeafe;color:#000000;font-size:12px;font-weight:800;text-align:center;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:6px;box-sizing:border-box;"
    >
        Open Avail Util
    </div>

    <div class="isd-legend">
        <span class="isd-legitem"><i class="isd-legswatch isd-leg-avail"></i>Availability</span>
        <span class="isd-legitem"><i class="isd-legswatch isd-leg-util"></i>Utilisation</span>
    </div>
</div>
'''

def build_chart_html(
    machine_series,
    machine_scope="Production + Swing/Spare Machines",
    spare_swing_asset_map=None,
):
    spare_swing_asset_map = spare_swing_asset_map or {}
    machine_scope = (
        machine_scope
        or "Production + Swing/Spare Machines"
    )

    def height(value):
        if value is None:
            return 2

        value = max(
            0.0,
            min(100.0, float(value)),
        )

        if value <= 0:
            return 2

        return max(
            2,
            int(round((value / 100.0) * 220)),
        )

    def chart_section(
        category,
        items,
        section_scope,
        spare_section=False,
    ):
        title = UI_TITLES.get(category, category)
        items = items or []

        section_class = "isd-chart-section"
        section_style = ""
        title_style = ""

        if spare_section:
            section_class += " isd-chart-section-spare"
            section_style = (
                "border:2px solid #a855f7;"
            )
            title_style = (
                "color:#7e22ce;"
            )

        if not items:
            return f'''
<div class="{section_class}" style="{section_style}">
    <div
        class="isd-chart-section-title"
        style="{title_style}"
    >
        {esc(title)} AVAILABILITY &amp; UTILISATION
        - {esc(section_scope)}
    </div>

    <div class="isd-no-machine-data">
        No machines found for {esc(title)}
        in {esc(section_scope)}.
    </div>
</div>
'''

        count = max(len(items), 1)

        # PDF_COMPACT_MACHINE_GRAPHS_V12
        #
        # PDF only marker class.
        #
        # Small machine fleets get a compact PDF width.
        # Large fleets (>18 machines) keep the existing
        # full-page horizontal fit.
        pdf_compact_count = (
            count
            if count <= 18
            else 0
        )
        
        pdf_chart_class = (
            f"isd-chart isd-pdf-compact-{pdf_compact_count}"
            if pdf_compact_count
            else "isd-chart"
        )

        grid_template = (
            f"repeat({count * 2}, minmax(18px, 1fr))"
        )

        label_template = (
            f"repeat({count}, minmax(54px, 2fr))"
        )

        min_width = max(820, count * 70)

        bars = []
        labels = []

        for item in items:
            machine_raw = str(
                item.get("machine") or ""
            ).strip()

            machine = esc(machine_raw)
            av = item.get("avail")
            ut = item.get("util")

            av_class = (
                "isd-bar avail"
                + (" nodata" if av is None else "")
            )

            ut_class = (
                "isd-bar util"
                + (" nodata" if ut is None else "")
            )

            label_class = "isd-machinelab"
            label_style = ""

            # Keep graph labels at 1 decimal, but rotate them vertically
            # so they fit clearly inside the narrow 30px bars.
            # This changes display only; KPI calculations stay unchanged.
            av_graph_label = (
                ""
                if av is None
                else fmt_percent(av)
            )

            ut_graph_label = (
                ""
                if ut is None
                else fmt_percent(ut)
            )

            bars.append(
                f"<div class='{av_class} "
                f"daily-availability-clickable-bar' "
                f"data-machine='{machine}' "
                f"title='Click to view {machine} "
                f"downtime details' "
                f"style='height:{height(av)}px;"
                f"position:relative;"
                f"overflow:visible;'>"
                f"<span style='"
                f"position:absolute;"
                f"top:18px;"
                f"left:50%;"
                f"transform:translate(-50%,-50%) rotate(-90deg);"
                f"transform-origin:center center;"
                f"z-index:50;"
                f"display:inline-block;"
                f"font-family:Arial,sans-serif;"
                f"font-size:10px;"
                f"font-weight:900;"
                f"line-height:1;"
                f"letter-spacing:0;"
                f"text-align:center;"
                f"color:#000000;"
                f"text-shadow:none;"
                f"white-space:nowrap;"
                f"pointer-events:none;'>"
                f"{av_graph_label}"
                f"</span>"
                f"</div>"
            )

            bars.append(
                f"<div class='{ut_class} "
                f"daily-availability-clickable-bar' "
                f"data-machine='{machine}' "
                f"title='Click to view {machine} "
                f"downtime details' "
                f"style='height:{height(ut)}px;"
                f"position:relative;"
                f"overflow:visible;'>"
                f"<span style='"
                f"position:absolute;"
                f"top:18px;"
                f"left:50%;"
                f"transform:translate(-50%,-50%) rotate(-90deg);"
                f"transform-origin:center center;"
                f"z-index:50;"
                f"display:inline-block;"
                f"font-family:Arial,sans-serif;"
                f"font-size:10px;"
                f"font-weight:900;"
                f"line-height:1;"
                f"letter-spacing:0;"
                f"text-align:center;"
                f"color:#000000;"
                f"text-shadow:none;"
                f"white-space:nowrap;"
                f"pointer-events:none;'>"
                f"{ut_graph_label}"
                f"</span>"
                f"</div>"
            )

            labels.append(
                f"<div class='{label_class}' "
                f"title='{machine}' "
                f"style='{label_style}'>"
                f"<span style='{label_style}'>"
                f"{machine}"
                f"</span>"
                f"</div>"
            )

        return f'''
<div class="{section_class}" style="{section_style}">
    <div
        class="isd-chart-section-title"
        style="{title_style}"
    >
        {esc(title)} AVAILABILITY &amp; UTILISATION
        - {esc(section_scope)}
    </div>

    <div
        class="{pdf_chart_class}"
        style="min-width:{min_width}px;"
    >
        <div class="isd-yaxis">
            <div>100%</div>
            <div>90%</div>
            <div>80%</div>
            <div>70%</div>
            <div>60%</div>
            <div>50%</div>
            <div>40%</div>
            <div>30%</div>
            <div>20%</div>
            <div>10%</div>
            <div>0%</div>
        </div>

        <div
            class="isd-chart-grid"
            style="grid-template-columns:{grid_template};"
        >
            {''.join(bars)}
        </div>

        <div
            class="isd-machinelabels"
            style="grid-template-columns:{label_template};"
        >
            {''.join(labels)}
        </div>
    </div>
</div>
'''

    sections = []

    for category in UI_CATEGORIES:
        category_items = (
            machine_series.get(category) or []
        )

        if (
            machine_scope
            == "Production + Swing/Spare Machines"
        ):
            production_items = []
            spare_items = []

            for item in category_items:
                machine_name = str(
                    item.get("machine") or ""
                ).strip()

                if (
                    machine_name
                    and machine_name
                    in spare_swing_asset_map
                ):
                    spare_items.append(item)
                else:
                    production_items.append(item)

            sections.append(
                chart_section(
                    category,
                    production_items,
                    "PRODUCTION MACHINES",
                    spare_section=False,
                )
            )

            sections.append(
                chart_section(
                    category,
                    spare_items,
                    "SWING/SPARE MACHINES",
                    spare_section=True,
                )
            )

        elif machine_scope == "Swing/Spare Machines":
            sections.append(
                chart_section(
                    category,
                    category_items,
                    "SWING/SPARE MACHINES",
                    spare_section=True,
                )
            )

        else:
            sections.append(
                chart_section(
                    category,
                    category_items,
                    "PRODUCTION MACHINES",
                    spare_section=False,
                )
            )

    return f'''
<div class="isd-chart-stack">
    {''.join(sections)}
</div>
'''

def get_popup_au_rows(
    machine,
    location,
    window_start,
    window_end,
):
    return frappe.db.sql(
        """
        SELECT
            name,
            asset_name,
            shift_date,
            shift,
            shift_system,
            location,
            COALESCE(
                shift_required_hours,
                0
            ) AS required_hours,
            COALESCE(
                shift_working_hours,
                0
            ) AS working_hours
        FROM `tabAvailability and Utilisation`
        WHERE asset_name = %(machine)s
          AND location = %(location)s
          AND shift_date >=
              DATE(%(window_start)s) - INTERVAL 1 DAY
          AND shift_date <=
              DATE(%(window_end)s)
        ORDER BY
            shift_date ASC,
            FIELD(
                shift,
                'Day',
                'Night'
            ) ASC
        """,
        {
            "machine": machine,
            "location": location,
            "window_start": window_start,
            "window_end": window_end,
        },
        as_dict=True,
    )


def calculate_breakdown_au(
    au_rows,
    breakdown_start,
    breakdown_end,
):
    from engineering.engineering.doctype.availability_and_utilisation import (
        availability_and_utilisation as au,
    )

    start_dt = get_datetime(breakdown_start)
    end_dt = get_datetime(breakdown_end)

    required_hours = 0.0
    working_hours = 0.0
    counted_downtime = 0.0
    startup_hours = 0.0
    fatigue_hours = 0.0
    shift_names = []

    seen_rows = set()

    for au_row in au_rows or []:
        try:
            row_required_hours = max(
                flt(au_row.required_hours),
                0,
            )

            if row_required_hours <= 0:
                continue

            shift_start, shift_end = au.get_shift_timings(
                au_row.shift_system,
                au_row.shift,
                str(au_row.shift_date),
            )

            overlap_start = max(
                start_dt,
                shift_start,
            )

            overlap_end = min(
                end_dt,
                shift_end,
            )

            if overlap_end <= overlap_start:
                continue

            row_key = au_row.name

            if row_key in seen_rows:
                continue

            seen_rows.add(row_key)

            required_hours += row_required_hours
            working_hours += flt(
                au_row.working_hours
            )

            shift_name = str(
                au_row.shift or ""
            ).strip()

            if shift_name and shift_name not in shift_names:
                shift_names.append(shift_name)

            shift_overlap_hours = au._overlap_hours(
                start_dt,
                end_dt,
                shift_start,
                shift_end,
            )

            startup_overlap = 0.0
            fatigue_overlap = 0.0

            excluded_windows = au._exclusion_windows(
                au_row.location,
                au_row.shift,
                shift_start,
                shift_end,
            )

            for index, (
                excluded_start,
                excluded_end,
            ) in enumerate(excluded_windows):
                excluded_overlap = au._overlap_hours(
                    start_dt,
                    end_dt,
                    excluded_start,
                    excluded_end,
                )

                if index == 0:
                    startup_overlap += excluded_overlap
                else:
                    fatigue_overlap += excluded_overlap

            startup_hours += startup_overlap
            fatigue_hours += fatigue_overlap

            valid_overlap_hours = max(
                shift_overlap_hours
                - startup_overlap
                - fatigue_overlap,
                0,
            )

            counted_downtime += min(
                valid_overlap_hours,
                row_required_hours,
            )

        except Exception:
            continue

    return {
        "required_hours": round(required_hours, 2),
        "working_hours": round(working_hours, 2),
        "counted_downtime": round(counted_downtime, 2),
        "startup_hours": round(startup_hours, 2),
        "fatigue_hours": round(fatigue_hours, 2),
        "excluded_hours": round(
            startup_hours + fatigue_hours,
            2,
        ),
        "shift_names": shift_names,
        "affected_shift_count": len(seen_rows),
    }


@frappe.whitelist()
def get_machine_downtime_details(
    machine=None,
    location=None,
    start_date=None,
    end_date=None,
    au_target_filter=None,
):
    if not machine:
        frappe.throw("Machine is required.")

    if not location:
        frappe.throw("Site is required.")

    if not start_date or not end_date:
        frappe.throw(
            "Start Date and End Date are required."
        )

    au_target_filter = (
        au_target_filter
        or "100% A & U"
    )

    effective_end_date = min(
        getdate(end_date),
        getdate(nowdate()),
    )

    end_date = str(effective_end_date)

    window_start = get_datetime(
        f"{start_date} 00:00:00"
    )

    window_end = get_datetime(
        f"{add_days(end_date, 1)} 00:00:00"
    )

    downtime_rows = frappe.db.sql(
        """
        SELECT
            pbm.name,
            pbm.asset_name,
            pbm.location,
            pbm.downtime_type,
            pbm.breakdown_reason,
            pbm.resolution_summary,
            pbm.breakdown_start_datetime,
            pbm.resolved_datetime,
            pbm.breakdown_hours,
            pbm.open_closed
        FROM `tabPlant Breakdown or Maintenance` pbm
        WHERE pbm.docstatus < 2
          AND pbm.asset_name = %(machine)s
          AND pbm.location = %(location)s
          AND COALESCE(
                NULLIF(
                    pbm.breakdown_start_datetime,
                    ''
                ),
                pbm.creation
              ) < %(window_end)s
          AND (
                pbm.resolved_datetime IS NULL
                OR pbm.resolved_datetime = ''
                OR pbm.resolved_datetime >= %(window_start)s
              )
        ORDER BY
            COALESCE(
                NULLIF(
                    pbm.breakdown_start_datetime,
                    ''
                ),
                pbm.creation
            ) DESC
        """,
        {
            "machine": machine,
            "location": location,
            "window_start": window_start,
            "window_end": window_end,
        },
        as_dict=True,
    )

    rows = []

    au_rows = get_popup_au_rows(
        machine,
        location,
        window_start,
        window_end,
    )

    for row in downtime_rows:
        breakdown_start = row.get(
            "breakdown_start_datetime"
        )

        resolved_datetime = row.get(
            "resolved_datetime"
        )

        raw_start = (
            get_datetime(breakdown_start)
            if breakdown_start
            else window_start
        )

        raw_end = (
            get_datetime(resolved_datetime)
            if resolved_datetime
            else window_end
        )

        clipped_start = max(
            raw_start,
            window_start,
        )

        clipped_end = min(
            raw_end,
            window_end,
        )

        if clipped_end > clipped_start:
            raw_downtime = time_diff_in_hours(
                clipped_end,
                clipped_start,
            )
        else:
            raw_downtime = 0


        event_au = calculate_breakdown_au(
            au_rows,
            clipped_start,
            clipped_end,
        )

        startup_excluded = flt(
            event_au.get("startup_hours")
        )

        fatigue_excluded = flt(
            event_au.get("fatigue_hours")
        )

        excluded_hours = flt(
            event_au.get("excluded_hours")
        )

        required_hours = flt(
            event_au.get("required_hours")
        )

        work_hours = flt(
            event_au.get("working_hours")
        )

        counted_downtime = flt(
            event_au.get("counted_downtime")
        )

        available_hours = max(
            required_hours - counted_downtime,
            0,
        )

        raw_availability = (
            available_hours / required_hours * 100
            if required_hours
            else 0
        )

        raw_utilisation = (
            work_hours / available_hours * 100
            if available_hours
            else 0
        )

        target_multiplier = (
            0.85
            if au_target_filter == "85% A & U"
            else 1.0
        )

        shift_label = ", ".join(
            event_au.get("shift_names") or []
        )

        calculation = {
            "shift": shift_label or "Not available",
            "affected_shift_count": event_au.get(
                "affected_shift_count"
            ) or 0,
            "raw_downtime": round(
                flt(raw_downtime),
                2,
            ),
            "startup_excluded": round(
                startup_excluded,
                2,
            ),
            "fatigue_excluded": round(
                fatigue_excluded,
                2,
            ),
            "total_excluded": round(
                excluded_hours,
                2,
            ),
            "total_downtime": round(
                counted_downtime,
                2,
            ),
            "required_hours": round(
                required_hours,
                2,
            ),
            "work_hours": round(
                work_hours,
                2,
            ),
            "available_hours": round(
                available_hours,
                2,
            ),
            "raw_availability": round(
                raw_availability,
                1,
            ),
            "raw_utilisation": round(
                raw_utilisation,
                1,
            ),
            "displayed_availability": round(
                raw_availability * target_multiplier,
                1,
            ),
            "displayed_utilisation": round(
                raw_utilisation * target_multiplier,
                1,
            ),
            "target_label": au_target_filter,
        }

        rows.append({
            "name": row.get("name") or "",
            "machine": (
                row.get("asset_name")
                or ""
            ),
            "location": (
                row.get("location")
                or ""
            ),
            "downtime_type": (
                row.get("downtime_type")
                or ""
            ),
            "reason": (
                row.get("breakdown_reason")
                or ""
            ),
            "resolution": (
                row.get("resolution_summary")
                or ""
            ),
            "start": (
                row.get(
                    "breakdown_start_datetime"
                )
                or ""
            ),
            "resolved": (
                row.get("resolved_datetime")
                or ""
            ),
            "hours": flt(
                calculation.get(
                    "total_downtime"
                ),
                2,
            ),
            "status": (
                row.get("open_closed")
                or (
                    "Closed"
                    if row.get(
                        "resolved_datetime"
                    )
                    else "Open"
                )
            ),
            "calculation": calculation,
        })


    grouped_rows = {}

    for detail in rows:
        start_value = detail.get("start")
        resolved_value = detail.get("resolved")

        start_key = (
            str(get_datetime(start_value))
            if start_value
            else ""
        )

        resolved_key = (
            str(get_datetime(resolved_value))
            if resolved_value
            else ""
        )

        interval_key = (
            start_key,
            resolved_key,
        )

        if interval_key not in grouped_rows:
            grouped_rows[interval_key] = detail
            continue

        existing = grouped_rows[interval_key]

        existing_reasons = [
            value.strip()
            for value in str(
                existing.get("reason") or ""
            ).split("\n")
            if value.strip()
        ]

        new_reasons = [
            value.strip()
            for value in str(
                detail.get("reason") or ""
            ).split("\n")
            if value.strip()
        ]

        for reason in new_reasons:
            if reason not in existing_reasons:
                existing_reasons.append(reason)

        existing["reason"] = "\n".join(
            existing_reasons
        )

        existing_resolutions = [
            value.strip()
            for value in str(
                existing.get("resolution") or ""
            ).split("\n")
            if value.strip()
        ]

        new_resolutions = [
            value.strip()
            for value in str(
                detail.get("resolution") or ""
            ).split("\n")
            if value.strip()
        ]

        for resolution in new_resolutions:
            if resolution not in existing_resolutions:
                existing_resolutions.append(
                    resolution
                )

        existing["resolution"] = "\n".join(
            existing_resolutions
        )

        existing_names = [
            value.strip()
            for value in str(
                existing.get("name") or ""
            ).split(",")
            if value.strip()
        ]

        new_name = str(
            detail.get("name") or ""
        ).strip()

        if new_name and new_name not in existing_names:
            existing_names.append(new_name)

        existing["name"] = ", ".join(
            existing_names
        )

    rows = list(grouped_rows.values())


    frappe.clear_messages()

    return {
        "rows": rows,
        "effective_end_date": end_date,
    }


@frappe.whitelist()
def download_dashboard_pdf(
    start_date=None,
    end_date=None,
    location=None,
    site=None,
    summary_type=None,
    machine_scope=None,
    asset_ownership=None,
    au_target_filter=None,
    dashboard_tab=None,
    hours_display=None,
    hours_asset=None,
):
    from frappe.utils.pdf import get_pdf
    from frappe.utils import now_datetime

    location = location or site
    summary_type = summary_type or "Average Per Machine"
    machine_scope = machine_scope or "Production + Swing/Spare Machines"

    # PDF_SELECTED_TAB_V1
    dashboard_tab = str(
        dashboard_tab or "hours"
    ).strip().lower()

    if dashboard_tab not in ("hours", "au"):
        dashboard_tab = "hours"

    hours_display = (
        hours_display or "Hours Average per Category"
    )
    hours_asset = hours_asset or ""

    html = get_dashboard_html(
        start_date=start_date,
        end_date=end_date,
        location=location,
        site=site,
        summary_type=summary_type,
        machine_scope=machine_scope,
        asset_ownership=asset_ownership or "Isambane & Excavo Assets",
        au_target_filter=au_target_filter or "85% A & U",
        hours_display=hours_display,
        hours_asset=hours_asset,
    )

    engineering_css = get_engineering_css_for_pdf()
    pdf_override_css = get_daily_dashboard_pdf_override_css()

    # PDF_SELECTED_TAB_V1
    #
    # The browser dashboard contains both performance panels.
    # PDF output must contain only the panel selected by the user.
    if dashboard_tab == "au":
        selected_tab_css = """
            .daily-dashboard-tabs {
                display: none !important;
            }

            .daily-dashboard-tab-panel[data-panel="hours"] {
                display: none !important;
            }

            .daily-dashboard-tab-panel[data-panel="au"] {
                display: block !important;
            }
        """
        safe_tab = "AU_Performance"
    else:
        selected_tab_css = """
            .daily-dashboard-tabs {
                display: none !important;
            }

            .daily-dashboard-tab-panel[data-panel="au"] {
                display: none !important;
            }

            .daily-dashboard-tab-panel[data-panel="hours"] {
                display: block !important;
            }
        """
        safe_tab = "Hours_Based_Performance"

    full_html = f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">

        <style>
            @page {{
                size: A3 landscape;
                margin: 6mm;
            }}

            html,
            body {{
                margin: 0;
                padding: 0;
                width: 100%;
                background: #ffffff;
                font-family: Arial, sans-serif;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }}

            * {{
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }}
        </style>

        <style>
            {engineering_css}
        </style>

        <style>
            {pdf_override_css}
        </style>

        <style>
            {selected_tab_css}
        </style>
    </head>
    <body>
        <div class="eng-dashboard eng-dashboard--daily-availability">
            {html}
        </div>
    </body>
    </html>
    """


    # PDF_GRID_FIT_LIVE_V3
    # PDF only: reduce minimum graph column widths before get_pdf().
    if (summary_type or "Average Per Machine") == "Average Per Machine":
        full_html = full_html.replace(
            "minmax(18px, 1fr)",
            "minmax(6px, 1fr)",
        )
        full_html = full_html.replace(
            "minmax(54px, 2fr)",
            "minmax(18px, 1fr)",
        )

    # PDF_MACHINE_BAR_SCALE_V11
    #
    # Machine bars are generated from a 216px source bar scale.
    #
    # Final PDF graph scale:
    #     100% = 170px
    #
    # Therefore:
    #     PDF bar height = source height * 170 / 216
    #
    # Example:
    #     90.7%:
    #     source = 90.7 x 2.16 = 195.91px
    #     PDF    = 195.91 x 170 / 216 = 154.19px
    #     154.19 / 170 = 90.7%
    #
    # PDF only. Browser dashboard is unchanged.
    if (summary_type or "Average Per Machine") == "Average Per Machine":
        import re as _pdf_bar_re

        _machine_bar_pattern = _pdf_bar_re.compile(
            r"""(
                <div
                \s+
                class=['"]isd-bar\s+(?:avail|util)[^'"]*['"]
                [^>]*?
                style=['"]
                [^'"]*?
                height:
            )
            ([0-9]+(?:\.[0-9]+)?)
            (px)
            """,
            _pdf_bar_re.IGNORECASE | _pdf_bar_re.VERBOSE,
        )

        def _scale_pdf_machine_bar(match):
            source_height = float(match.group(2))

            scaled_height = (
                source_height
                * 170.0
                / 216.0
            )

            scaled_height = max(
                1.0,
                min(
                    170.0,
                    scaled_height,
                ),
            )

            scaled_text = (
                f"{scaled_height:.2f}"
                .rstrip("0")
                .rstrip(".")
            )

            return (
                match.group(1)
                + scaled_text
                + match.group(3)
            )

        full_html = _machine_bar_pattern.sub(
            _scale_pdf_machine_bar,
            full_html,
        )

    pdf = get_pdf(
        full_html,
        options={
            "orientation": "Landscape",
            "page-size": "A3",
            "margin-top": "6mm",
            "margin-right": "6mm",
            "margin-bottom": "6mm",
            "margin-left": "6mm",
            "encoding": "UTF-8",
            "disable-smart-shrinking": None,
            "print-media-type": None,
        },
    )

    safe_location = str(location or "site").replace(" ", "_")
    safe_summary = str(summary_type or "summary").replace(" ", "_")
    safe_scope = str(machine_scope or "scope").replace(" ", "_").replace("/", "_")
    safe_start = str(start_date or "")
    safe_end = str(end_date or "")
    timestamp = now_datetime().strftime("%Y%m%d_%H%M%S")

    filename = f"Daily_Availability_Dashboard_{safe_tab}_{safe_summary}_{safe_scope}_{safe_location}_{safe_start}_to_{safe_end}_{timestamp}.pdf"

    frappe.local.response.filename = filename
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "download"


def build_pdf_dashboard_html(location, start_date, end_date, avgs, machine_series):
    sections = []

    for category in UI_CATEGORIES:
        items = machine_series.get(category) or []

        if not items:
            continue

        rows = []
        for item in items:
            machine = esc(item.get("machine") or "")
            avail = max(0, min(100, flt(item.get("avail"))))
            util = max(0, min(100, flt(item.get("util"))))

            rows.append(f'''
<tr>
    <td class="machine-label">{machine}</td>
    <td>
        <div class="bar-wrap">
            <div class="target-line avail-target"></div>
            <div class="target-line util-target"></div>
            <div class="bar availability" style="width:{avail}%;">{avail:.1f}%</div>
            <div class="bar utilisation" style="width:{util}%;">{util:.1f}%</div>
        </div>
    </td>
</tr>
''')

        sections.append(f'''
<div class="pdf-section">
    <h2>{esc(category)} AVAILABILITY &amp; UTILISATION</h2>
    <table class="pdf-chart">
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
</div>
''')

    return f'''
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: A4 landscape;
    margin: 7mm;
}}

body {{
    font-family: Arial, sans-serif;
    color: #111;
    margin: 0;
    padding: 0;
}}

.header {{
    font-size: 14px;
    font-weight: bold;
    margin-bottom: 8px;
}}

.summary {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12px;
}}

.summary td {{
    border: 1px solid #333;
    padding: 4px 6px;
    font-size: 11px;
    font-weight: bold;
}}

.legend-line {{
    display: inline-block;
    width: 42px;
    height: 4px;
    vertical-align: middle;
    margin-left: 6px;
}}

.red {{
    background: #ff0000;
}}

.green {{
    background: #92d050;
}}

.pdf-section {{
    page-break-inside: avoid;
    margin-bottom: 14px;
    border: 1px solid #222;
    padding: 8px;
}}

h2 {{
    text-align: center;
    font-size: 18px;
    margin: 0 0 8px 0;
}}

.pdf-chart {{
    width: 100%;
    border-collapse: collapse;
}}

.pdf-chart td {{
    padding: 3px 4px;
    vertical-align: middle;
}}

.machine-label {{
    width: 90px;
    font-size: 10px;
    font-weight: bold;
    white-space: nowrap;
}}

.bar-wrap {{
    position: relative;
    height: 34px;
    border-left: 1px solid #333;
    border-bottom: 1px solid #bbb;
    background: #eeeeee;
}}

.target-line {{
    position: absolute;
    left: 0;
    right: 0;
    height: 3px;
    z-index: 5;
}}

.avail-target {{
    top: 5px;
    background: #ff0000;
}}

.util-target {{
    top: 9px;
    background: #92d050;
}}

.bar {{
    position: relative;
    height: 13px;
    line-height: 13px;
    font-size: 9px;
    font-weight: bold;
    color: #000;
    padding-left: 4px;
    box-sizing: border-box;
    white-space: nowrap;
}}

.availability {{
    background: #f4b000;
    margin-top: 3px;
}}

.utilisation {{
    background: #2f75b5;
    color: #fff;
    margin-top: 2px;
}}
</style>
</head>
<body>
    <div class="header">
        Daily Availability and Utilisation Dashboard | {esc(location)} | {esc(start_date)} to {esc(end_date)}
    </div>

    <table class="summary">
        <tr>
            <td>Availability Target <span class="legend-line red"></span></td>
            <td>85%</td>
            <td>Utilization Target <span class="legend-line green"></span></td>
            <td>80%</td>
        </tr>
    </table>

    {''.join(sections)}
</body>
</html>
'''


@frappe.whitelist()
def download_daily_dashboard_pdf_v2(start_date=None, end_date=None, location=None, site=None, machine_scope=None):
    location = location or site
    machine_scope = machine_scope or "Production + Swing/Spare Machines"

    if not start_date:
        frappe.throw("Please select Start Date.")

    if not end_date:
        frappe.throw("Please select End Date.")

    if not location:
        frappe.throw("Please select Site.")

    source_rows = fetch_grouped_data(
        location,
        start_date,
        end_date,
        machine_scope,
        "100% A & U",
    )
    spare_swing_asset_map = get_engine_spare_swing_asset_map(source_rows)
    avgs = build_summary_averages_from_source_rows(source_rows)
    machine_series = build_machine_series_from_source_rows(source_rows)

    html = build_pdf_dashboard_html(location, start_date, end_date, avgs, machine_series)

    pdf = frappe.utils.pdf.get_pdf(html)

    filename = f"Daily Availability and Utilisation Dashboard - {location} - {start_date} to {end_date}.pdf"

    frappe.local.response.filename = filename
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "download"

@frappe.whitelist()
def get_daily_availability_dashboard_html(start_date=None, end_date=None, location=None, site=None, summary_type=None, machine_scope=None, asset_ownership=None, au_target_filter=None, hours_display=None, hours_asset=None):
    location = location or site
    summary_type = summary_type or "Average Per Machine"
    machine_scope = machine_scope or "Production + Swing/Spare Machines"

    if not start_date:
        frappe.throw("Please select Start Date.")

    if not end_date:
        frappe.throw("Please select End Date.")

    if not location:
        frappe.throw("Please select Site.")

    columns, data, dashboard_html = execute(
        frappe._dict({
            "start_date": start_date,
            "end_date": end_date,
            "from_date": start_date,
            "to_date": end_date,
            "location": location,
            "site": location,
            "summary_type": summary_type,
            "machine_scope": machine_scope,
            "asset_ownership": asset_ownership or "Isambane & Excavo Assets",
            "au_target_filter": au_target_filter or "85% A & U",
            "hours_display": hours_display or "Hours Average per Category",
            "hours_asset": hours_asset or "",
        })
    )

    return dashboard_html



@frappe.whitelist()
def get_dashboard_html(start_date=None, end_date=None, location=None, site=None, summary_type=None, machine_scope=None, asset_ownership=None, au_target_filter=None, hours_display=None, hours_asset=None):
    location = location or site
    summary_type = summary_type or "Average Per Machine"
    machine_scope = machine_scope or "Production + Swing/Spare Machines"

    if not start_date:
        frappe.throw("Please select Start Date.")

    if not end_date:
        frappe.throw("Please select End Date.")

    if not location:
        frappe.throw("Please select Site.")

    result = execute(
        frappe._dict({
            "start_date": start_date,
            "end_date": end_date,
            "from_date": start_date,
            "to_date": end_date,
            "location": location,
            "site": location,
            "summary_type": summary_type,
            "machine_scope": machine_scope,
            "asset_ownership": asset_ownership or "Isambane & Excavo Assets",
            "au_target_filter": au_target_filter or "85% A & U",
            "hours_display": hours_display or "Hours Average per Category",
            "hours_asset": hours_asset or "",
        })
    )

    if isinstance(result, (list, tuple)) and len(result) >= 3:
        return result[2]

    frappe.throw("Dashboard HTML was not returned by the page.")


def get_engineering_css_for_pdf():
    try:
        css_path = frappe.get_app_path(
            "engineering",
            "public",
            "css",
            "engineering.css",
        )

        with open(css_path, "r", encoding="utf-8") as css_file:
            return css_file.read()

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Daily Dashboard PDF CSS Load Error")
        frappe.clear_messages()
        return ""


def get_daily_dashboard_pdf_override_css():
    return """
    .eng-dashboard,
    .eng-dashboard * {
        box-sizing: border-box !important;
    }

    .eng-dashboard--daily-availability {
        padding: 0 !important;
        color: #1f272e !important;
    }

    .isd-hourly-dashboard {
        padding: 0 !important;
        color: #1f272e !important;
    }

    .isd-note {
        display: none !important;
    }

    .isd-site {
        border: 1px solid #d8dde2 !important;
        border-radius: 8px !important;
        overflow: hidden !important;
        box-shadow: none !important;
        background: #ffffff !important;
    }

    .isd-site-title {
        padding: 7px 9px !important;
        font-size: 10px !important;
        font-weight: 900 !important;
        color: #111827 !important;
        background: #ffffff !important;
        border-bottom: 1px solid #e5e7eb !important;
    }

    .isd-band {
        padding: 8px !important;
        background: var(--site-colour, #f7f7f7) !important;
        border-top: 0 !important;
        border-bottom: 1px solid #d8dde2 !important;
    }

    .isd-metrics {
        display: block !important;
        width: 100% !important;
        font-size: 0 !important;
        line-height: 0 !important;
    }

    .isd-metric {
        display: inline-block !important;
        vertical-align: top !important;
        width: 106px !important;
        height: 86px !important;
        min-height: 86px !important;
        margin: 0 6px 6px 0 !important;
        padding: 6px !important;
        border: 1px solid #d8dde2 !important;
        border-radius: 8px !important;
        background: rgba(255, 255, 255, 0.82) !important;
        box-shadow: none !important;
        overflow: hidden !important;
    }

    .isd-metric-title {
        display: block !important;
        width: 100% !important;
        height: 24px !important;
        min-height: 24px !important;
        margin: 0 0 4px 0 !important;
        padding: 0 !important;
        text-align: center !important;
        font-size: 8px !important;
        font-weight: 900 !important;
        line-height: 1.1 !important;
        color: #000000 !important;
        text-transform: uppercase !important;
    }

    .isd-pill-row {
        display: block !important;
        width: 100% !important;
        height: 48px !important;
        min-height: 48px !important;
        text-align: center !important;
        white-space: nowrap !important;
        font-size: 0 !important;
        line-height: 0 !important;
    }

    .isd-mbubble {
        display: inline-block !important;
        vertical-align: top !important;
        width: 44px !important;
        height: 44px !important;
        min-height: 44px !important;
        margin: 0 2px !important;
        padding: 7px 2px 2px 2px !important;
        border-radius: 999px !important;
        text-align: center !important;
        box-shadow: none !important;
        color: #111827 !important;
        line-height: 1 !important;
    }

    .isd-mbubble-green {
        border: 2px solid #1e8e3e !important;
        background: rgba(30, 142, 62, 0.16) !important;
    }

    .isd-mbubble-blue {
        border: 2px solid #1d4ed8 !important;
        background: #bfdbfe !important;
    }

    .isd-mbubble-red {
        border: 2px solid #d93025 !important;
        background: rgba(217, 48, 37, 0.15) !important;
    }

    .isd-mbubble-label {
        display: block !important;
        margin: 0 !important;
        padding: 0 !important;
        font-size: 6px !important;
        font-weight: 900 !important;
        line-height: 1 !important;
        text-transform: uppercase !important;
        white-space: nowrap !important;
        color: inherit !important;
    }

    .isd-mbubble-value {
        display: block !important;
        margin: 2px 0 0 0 !important;
        padding: 0 !important;
        font-size: 7px !important;
        font-weight: 900 !important;
        line-height: 1 !important;
        color: inherit !important;
    }

    .isd-contentrow {
        display: block !important;
        width: 100% !important;
        border-top: 1px solid #d8dde2 !important;
        background: #ffffff !important;
    }

    .isd-side {
        display: none !important;
    }

    .isd-chart-stack {
        display: block !important;
        width: 100% !important;
        padding: 8px !important;
        overflow: visible !important;
    }

    .isd-chart-section {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 0 10px 0 !important;
        border: 1px solid #d8dde2 !important;
        border-radius: 8px !important;
        background: #ffffff !important;
        overflow: hidden !important;
        page-break-inside: avoid !important;
        break-inside: avoid !important;
        box-shadow: none !important;
    }

    .isd-chart-section-title {
        display: block !important;
        width: 100% !important;
        padding: 7px 8px !important;
        font-size: 11px !important;
        font-weight: 900 !important;
        line-height: 1.2 !important;
        text-align: center !important;
        color: #111827 !important;
        background: #ffffff !important;
        border-bottom: 1px solid #e5e7eb !important;
        text-shadow: none !important;
        text-transform: uppercase !important;
    }

    .isd-chart {
        display: block !important;
        width: 100% !important;
        min-width: 0 !important;
        max-width: 100% !important;
        padding: 10px 10px 44px 10px !important;
        position: relative !important;
        overflow: hidden !important;
        background: #ffffff !important;
    }

    .isd-yaxis {
        position: absolute !important;
        left: 8px !important;
        top: 10px !important;
        width: 44px !important;
        height: 170px !important;
        min-height: 170px !important;
        max-height: 170px !important;
        display: -webkit-box !important;
        -webkit-box-orient: vertical !important;
        -webkit-box-pack: justify !important;
        padding-right: 5px !important;
        background: #ffffff !important;
        color: #475569 !important;
        font-size: 8px !important;
        font-weight: 900 !important;
        line-height: 1 !important;
        text-align: right !important;
        text-shadow: none !important;
        z-index: 20 !important;
    }

    .isd-chart-grid {
        display: block !important;
        white-space: nowrap !important;
        width: auto !important;
        max-width: none !important;
        height: 170px !important;
        min-height: 170px !important;
        max-height: 170px !important;
        margin-left: 54px !important;
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
        border-bottom: 2px solid #94a3b8 !important;
        background:
            linear-gradient(
                to top,
                rgba(107, 114, 128, 0.20) 1px,
                transparent 1px
            ) !important;
        background-size: 100% 17px !important;
        font-size: 0 !important;
        line-height: 0 !important;
    }

    .isd-bar,
    .isd-bar.avail,
    .isd-bar.util {
        display: inline-block !important;
        vertical-align: bottom !important;
        width: 30px !important;
        min-width: 30px !important;
        max-width: 30px !important;
        margin: 0 3px 0 0 !important;
        border-radius: 2px 2px 0 0 !important;
        min-height: 2px !important;
        max-height: 170px !important;
        box-sizing: border-box !important;
    }

    .isd-bar.avail {
        background: #f39c12 !important;
    }

    .isd-bar.util {
        background: #6b6b6b !important;
    }

    .isd-avgline {
        position: absolute !important;
        left: 64px !important;
        right: 10px !important;
        height: 2px !important;
        z-index: 30 !important;
        opacity: 0.95 !important;
        box-shadow:
            0 -1px 0 rgba(255, 255, 255, 0.95),
            0 1px 0 rgba(0, 0, 0, 0.35) !important;
    }

    .isd-avgline.isd-avg-85 {
        background: #ff0000 !important;
        top: 36px !important;
    }

    .isd-avgline.isd-avg-80 {
        background: #92d050 !important;
        top: 44px !important;
    }

    .isd-machinelabels {
        display: block !important;
        white-space: nowrap !important;
        width: auto !important;
        max-width: none !important;
        margin-left: 54px !important;
        margin-top: 6px !important;
        min-height: 34px !important;
        max-height: 34px !important;
        overflow: hidden !important;
        font-size: 0 !important;
        line-height: 0 !important;
        color: #475569 !important;
    }

    .isd-machinelab,
    .isd-summary-group-label {
        display: inline-block !important;
        vertical-align: top !important;
        width: 66px !important;
        min-width: 66px !important;
        max-width: 66px !important;
        height: 34px !important;
        min-height: 34px !important;
        max-height: 34px !important;
        padding: 3px 1px 0 1px !important;
        margin: 0 !important;
        overflow: hidden !important;
        white-space: normal !important;
        text-align: center !important;
        font-size: 7px !important;
        font-weight: 900 !important;
        line-height: 1.05 !important;
        color: #475569 !important;
        text-shadow: none !important;
        border: 0 !important;
    }

    .isd-daily-summary-section .isd-machinelab {
        display: none !important;
    }

    .isd-daily-summary-section .isd-summary-group-label {
        display: inline-block !important;
        color: #111827 !important;
    }



    .isd-no-machine-data {
        padding: 12px !important;
        font-size: 9px !important;
        font-weight: 700 !important;
        color: #475569 !important;
    }
    

    /* PDF_HORIZONTAL_FIT_V3

       PDF ONLY.
       Fit the complete machine fleet on one landscape page.
    */

    .isd-chart-section {
        overflow: hidden !important;
        max-width: 100% !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section) .isd-chart {
        width: 147.0588235% !important;
        min-width: 0 !important;
        max-width: none !important;

        -webkit-transform: scaleX(0.68) !important;
        transform: scaleX(0.68) !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart-grid {
        height: 185px !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis {
        height: 185px !important;
        min-height: 185px !important;
        max-height: 185px !important;

        font-size: 9px !important;
        font-weight: 900 !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-machinelab {
        font-size: 9px !important;
        font-weight: 900 !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar {
        overflow: visible !important;
    }

    /* END PDF_HORIZONTAL_FIT_V3 */


    /* PDF_VERTICAL_PERCENT_LABELS_V4

       PDF ONLY.
       Percentage labels vertical.
       Orange and grey percentages both white.
    */

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar {
        position: relative !important;
        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar > span,

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar .isd-bar-label,

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar .isd-bar-value {

        position: absolute !important;

        left: 50% !important;
        top: 8px !important;

        display: inline-block !important;

        white-space: nowrap !important;
        line-height: 1 !important;

        font-size: 9px !important;
        font-weight: 800 !important;

        color: #ffffff !important;

        text-shadow:
            1px 1px 2px rgba(0,0,0,0.85) !important;

        transform:
            translateX(-50%) rotate(-90deg) !important;

        -webkit-transform:
            translateX(-50%) rotate(-90deg) !important;

        transform-origin:
            center center !important;

        -webkit-transform-origin:
            center center !important;

        z-index: 30 !important;

        pointer-events: none !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar.avail > span,

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar.avail .isd-bar-label,

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar.avail .isd-bar-value {

        color: #ffffff !important;

        text-shadow:
            1px 1px 2px rgba(0,0,0,0.85) !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar.util > span,

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar.util .isd-bar-label,

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-bar.util .isd-bar-value {

        color: #ffffff !important;

        text-shadow:
            1px 1px 2px rgba(0,0,0,0.85) !important;
    }

    /* END PDF_VERTICAL_PERCENT_LABELS_V4 */


    


    


    


    


    
    /* PDF_FINAL_PERCENT_GEOMETRY_V10

       FINAL PDF GRAPH SCALE FIX

       Keep the working horizontal fit and vertical percentage labels.
       Keep the bars bottom-anchored at 0%.
       Only correct the graph scale so bar height matches its percentage.

       IMPORTANT:
       The graph must use the original 170px plotting height.
       That is the scale that matches the percentage bar heights.
    */


    /* ========================================================
       CHART CONTAINER
       ======================================================== */

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart {

        position: relative !important;

        padding-top: 10px !important;
        padding-bottom: 44px !important;

        overflow: visible !important;
    }


    /* ========================================================
       PLOT AREA = 170PX
       ======================================================== */

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart-grid {

        display: block !important;
        white-space: nowrap !important;

        width: auto !important;
        max-width: none !important;

        height: 170px !important;
        min-height: 170px !important;
        max-height: 170px !important;

        line-height: 170px !important;
        font-size: 0 !important;

        margin-top: 0 !important;
        margin-bottom: 0 !important;

        padding-top: 0 !important;
        padding-bottom: 0 !important;

        position: relative !important;
        overflow: visible !important;

        border-bottom: 2px solid #94a3b8 !important;

        background:
            linear-gradient(
                to top,
                rgba(100,116,139,0.18) 1px,
                transparent 1px
            ) !important;

        background-size: 100% 17px !important;

        -webkit-transform: none !important;
        transform: none !important;
    }


    /* ========================================================
       BARS
       ======================================================== */

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart-grid > .isd-bar {

        display: inline-block !important;
        vertical-align: bottom !important;

        position: relative !important;

        top: auto !important;
        bottom: auto !important;

        margin-top: 0 !important;
        margin-bottom: 0 !important;

        padding-top: 0 !important;
        padding-bottom: 0 !important;

        line-height: normal !important;

        max-height: 170px !important;

        box-sizing: border-box !important;
        overflow: visible !important;
    }


    /* ========================================================
       Y AXIS = SAME 170PX
       ======================================================== */

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis {

        position: absolute !important;

        left: 8px !important;
        top: 10px !important;
        bottom: auto !important;

        width: 44px !important;

        height: 170px !important;
        min-height: 170px !important;
        max-height: 170px !important;

        display: block !important;

        margin: 0 !important;
        padding: 0 5px 0 0 !important;

        box-sizing: border-box !important;

        font-size: 9px !important;
        font-weight: 900 !important;
        line-height: 1 !important;

        text-align: right !important;

        color: #475569 !important;
        background: transparent !important;

        -webkit-transform: none !important;
        transform: none !important;

        z-index: 20 !important;
    }


    /* ========================================================
       Y AXIS LABELS
       ======================================================== */

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div {

        position: absolute !important;
        right: 5px !important;
        width: 36px !important;

        margin: 0 !important;
        padding: 0 !important;

        line-height: 1 !important;
        white-space: nowrap !important;

        -webkit-transform: translateY(-50%) !important;
        transform: translateY(-50%) !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(1)  { top: 0%   !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(2)  { top: 10%  !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(3)  { top: 20%  !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(4)  { top: 30%  !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(5)  { top: 40%  !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(6)  { top: 50%  !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(7)  { top: 60%  !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(8)  { top: 70%  !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(9)  { top: 80%  !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(10) { top: 90%  !important; }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-yaxis > div:nth-child(11) { top: 100% !important; }


    /* ========================================================
       TARGET LINES
       ======================================================== */

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-avgline.isd-avg-85 {
        top: calc(10px + 170px * 0.15) !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-avgline.isd-avg-80 {
        top: calc(10px + 170px * 0.20) !important;
    }


    /* ========================================================
       MACHINE LABELS
       ======================================================== */

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-machinelabels {

        margin-top: 7px !important;
        padding-top: 0 !important;

        -webkit-transform: none !important;
        transform: none !important;
    }


    /* END PDF_FINAL_PERCENT_GEOMETRY_V10 */



    


    /* PDF_COMPACT_MACHINE_GRAPHS_V13

       PDF ONLY.

       Small machine graphs need a little more right-side space
       so the final fleet and bars are not clipped.

       This fixes cases like:
       - ADT IS553
       - DOZER IS340
       - EXC IS343

       No changes to:
       - percentage heights
       - 0% baseline
       - vertical white percentages
       - A3 page size
    */


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-1 {

        width: 430px !important;
        min-width: 430px !important;
        max-width: 430px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-1 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-1 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-2 {

        width: 430px !important;
        min-width: 430px !important;
        max-width: 430px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-2 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-2 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-3 {

        width: 430px !important;
        min-width: 430px !important;
        max-width: 430px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-3 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-3 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-4 {

        width: 430px !important;
        min-width: 430px !important;
        max-width: 430px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-4 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-4 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-5 {

        width: 440px !important;
        min-width: 440px !important;
        max-width: 440px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-5 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-5 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-6 {

        width: 504px !important;
        min-width: 504px !important;
        max-width: 504px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-6 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-6 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-7 {

        width: 568px !important;
        min-width: 568px !important;
        max-width: 568px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-7 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-7 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-8 {

        width: 632px !important;
        min-width: 632px !important;
        max-width: 632px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-8 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-8 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-9 {

        width: 696px !important;
        min-width: 696px !important;
        max-width: 696px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-9 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-9 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-10 {

        width: 760px !important;
        min-width: 760px !important;
        max-width: 760px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-10 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-10 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-11 {

        width: 824px !important;
        min-width: 824px !important;
        max-width: 824px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-11 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-11 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-12 {

        width: 888px !important;
        min-width: 888px !important;
        max-width: 888px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-12 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-12 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-13 {

        width: 952px !important;
        min-width: 952px !important;
        max-width: 952px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-13 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-13 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-14 {

        width: 1016px !important;
        min-width: 1016px !important;
        max-width: 1016px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-14 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-14 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-15 {

        width: 1080px !important;
        min-width: 1080px !important;
        max-width: 1080px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-15 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-15 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-16 {

        width: 1144px !important;
        min-width: 1144px !important;
        max-width: 1144px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-16 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-16 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-17 {

        width: 1208px !important;
        min-width: 1208px !important;
        max-width: 1208px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-17 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-17 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-18 {

        width: 1272px !important;
        min-width: 1272px !important;
        max-width: 1272px !important;

        padding-right: 42px !important;
        box-sizing: border-box !important;

        -webkit-transform: none !important;
        transform: none !important;

        -webkit-transform-origin: left top !important;
        transform-origin: left top !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-18 .isd-chart-grid {

        display: inline-block !important;

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }

    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-18 .isd-machinelabels {

        width: auto !important;
        min-width: 0 !important;
        max-width: none !important;

        padding-right: 28px !important;
        margin-right: 0 !important;

        overflow: visible !important;
    }


    /* END PDF_COMPACT_MACHINE_GRAPHS_V13 */



    /* PDF_COMPACT_LABEL_ROW_V15

       PDF ONLY.

       Fix ONLY the machine-name row on compact graphs.

       Bars are already correct.

       The Python renderer creates:
         2 bars per machine
         1 label per machine

       This gives the label row one exact slot per machine
       so the final fleet name is not clipped.

       Expected fixes:
         ADT       IS553
         DOZER     IS340
         EXCAVATOR IS343

       DO NOT alter graph/bar geometry here.
    */



    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-1
    .isd-machinelabels {

        width: 58px !important;
        min-width: 58px !important;
        max-width: 58px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                1,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-1
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-1
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-2
    .isd-machinelabels {

        width: 116px !important;
        min-width: 116px !important;
        max-width: 116px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                2,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-2
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-2
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-3
    .isd-machinelabels {

        width: 174px !important;
        min-width: 174px !important;
        max-width: 174px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                3,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-3
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-3
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-4
    .isd-machinelabels {

        width: 232px !important;
        min-width: 232px !important;
        max-width: 232px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                4,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-4
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-4
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-5
    .isd-machinelabels {

        width: 290px !important;
        min-width: 290px !important;
        max-width: 290px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                5,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-5
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-5
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-6
    .isd-machinelabels {

        width: 348px !important;
        min-width: 348px !important;
        max-width: 348px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                6,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-6
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-6
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-7
    .isd-machinelabels {

        width: 406px !important;
        min-width: 406px !important;
        max-width: 406px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                7,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-7
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-7
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-8
    .isd-machinelabels {

        width: 464px !important;
        min-width: 464px !important;
        max-width: 464px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                8,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-8
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-8
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-9
    .isd-machinelabels {

        width: 522px !important;
        min-width: 522px !important;
        max-width: 522px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                9,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-9
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-9
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-10
    .isd-machinelabels {

        width: 580px !important;
        min-width: 580px !important;
        max-width: 580px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                10,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-10
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-10
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-11
    .isd-machinelabels {

        width: 638px !important;
        min-width: 638px !important;
        max-width: 638px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                11,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-11
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-11
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-12
    .isd-machinelabels {

        width: 696px !important;
        min-width: 696px !important;
        max-width: 696px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                12,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-12
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-12
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-13
    .isd-machinelabels {

        width: 754px !important;
        min-width: 754px !important;
        max-width: 754px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                13,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-13
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-13
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-14
    .isd-machinelabels {

        width: 812px !important;
        min-width: 812px !important;
        max-width: 812px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                14,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-14
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-14
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-15
    .isd-machinelabels {

        width: 870px !important;
        min-width: 870px !important;
        max-width: 870px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                15,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-15
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-15
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-16
    .isd-machinelabels {

        width: 928px !important;
        min-width: 928px !important;
        max-width: 928px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                16,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-16
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-16
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-17
    .isd-machinelabels {

        width: 986px !important;
        min-width: 986px !important;
        max-width: 986px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                17,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-17
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-17
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }




    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-18
    .isd-machinelabels {

        width: 1044px !important;
        min-width: 1044px !important;
        max-width: 1044px !important;

        margin-left: 54px !important;
        margin-right: 0 !important;

        padding-left: 0 !important;
        padding-right: 0 !important;

        grid-template-columns:
            repeat(
                18,
                minmax(0, 1fr)
            ) !important;

        gap: 0 !important;

        overflow: visible !important;

        box-sizing: border-box !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-18
    .isd-machinelab {

        min-width: 0 !important;
        max-width: none !important;

        margin: 0 !important;

        padding-left: 1px !important;
        padding-right: 1px !important;

        text-align: center !important;

        white-space: nowrap !important;
        overflow: visible !important;
    }


    .isd-chart-section:not(.isd-daily-summary-section)
    .isd-chart.isd-pdf-compact-18
    .isd-machinelab:last-child {

        padding-right: 4px !important;

        overflow: visible !important;
    }



    /* END PDF_COMPACT_LABEL_ROW_V15 */

"""
