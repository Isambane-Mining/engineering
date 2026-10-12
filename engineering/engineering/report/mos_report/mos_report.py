from datetime import datetime, timedelta
import frappe
from frappe.utils import getdate, get_timedelta, now_datetime
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})

    columns = get_columns()
    data = get_machine_data(filters)

    return columns, data


def get_machine_data(filters):
    """Return one MOS row per submitted Asset.

    Machine categories and shift preferences are read from ERP
    configuration. No machine names, shift times, hours or site
    preferences are hard-coded in this report.
    """

    asset_filters = {
        "docstatus": 1,
    }

    monthly_machine_status = (
        get_monthly_planning_machine_status(
            filters
        )
    )

    if filters.get("site"):
        asset_filters["location"] = filters.site

    selected_category = filters.get("asset_category")

    mos_categories = frappe.get_list(
        "Asset Category",
        filters={"custom_include_in_mos_report": 1},
        fields=[
            "name",
            "custom_mos_report_label",
            "custom_mos_report_order",
        ],
        order_by="custom_mos_report_order asc, name asc",
    )

    configured_categories = [
        row.name
        for row in mos_categories
    ]

    if (
        selected_category
        and selected_category != "All Machines"
    ):
        matching_category = next(
            (
                row.name
                for row in mos_categories
                if row.custom_mos_report_label
                == selected_category
            ),
            None,
        )

        if not matching_category:
            return []

        asset_filters["asset_category"] = matching_category

    else:
        if not configured_categories:
            return []

        asset_filters["asset_category"] = [
            "in",
            configured_categories,
        ]

    if filters.get("asset"):
        asset_filters["name"] = filters.asset

    assets = frappe.get_list(
        "Asset",
        filters=asset_filters,
        fields=["name", "asset_category"],
        order_by="name asc",
    )

    category_order = {
        row.name: row.custom_mos_report_order
        for row in mos_categories
    }

    assets.sort(
        key=lambda asset: (
            category_order.get(
                asset.asset_category,
                999999,
            ),
            asset.name,
        )
    )

    shift_values = get_shift_configuration_values(filters)

    operating_hours = get_pre_use_operating_hours(
        filters,
        shift_values,
    )

    engineering_downtime = get_engineering_downtime(
        filters,
        shift_values,
    )

    data = []

    for asset in assets:
        day_operating_hours = operating_hours[
            "day"
        ].get(
            asset.name,
            0,
        )

        night_operating_hours = operating_hours[
            "night"
        ].get(
            asset.name,
            0,
        )

        total_operating_hours = (
            day_operating_hours
            + night_operating_hours
        )

        day_engineering = engineering_downtime[
            "day"
        ].get(
            asset.name,
            {},
        )

        night_engineering = engineering_downtime[
            "night"
        ].get(
            asset.name,
            {},
        )

        row = {
            "night_machine": asset.name,
            "day_asset": asset.name,

            "machine_plan_status":
                monthly_machine_status.get(
                    asset.name
                ),

            "day_planned_available_hours":
                shift_values.get(
                    "day_planned_available_hours"
                ),

            "day_engineering_downtime":
                day_engineering.get(
                    "captured_reason",
                    day_engineering.get("reason"),
                ),

            "day_engineering_duration":
                day_engineering.get(
                    "duration",
                    0,
                ),

            "day_engineering_captured_hours":
                day_engineering.get(
                    "captured_duration",
                    0,
                ),

            "day_engineering_captured_reason":
                day_engineering.get(
                    "captured_reason",
                    "",
                ),
            "day_shift_change":
                shift_values.get(
                    "day_shift_change"
                ),
            "day_shift_change_duration":
                shift_values.get(
                    "day_shift_change_duration"
                ),
            "day_fatigue_break":
                shift_values.get(
                    "day_fatigue_break"
                ),
            "day_fatigue_duration":
                shift_values.get(
                    "day_fatigue_duration"
                ),

            "night_planned_available_hours":
                shift_values.get(
                    "night_planned_available_hours"
                ),

            "night_engineering_downtime":
                night_engineering.get(
                    "captured_reason",
                    night_engineering.get("reason"),
                ),

            "night_engineering_duration":
                night_engineering.get(
                    "duration",
                    0,
                ),

            "night_engineering_captured_hours":
                night_engineering.get(
                    "captured_duration",
                    0,
                ),

            "night_engineering_captured_reason":
                night_engineering.get(
                    "captured_reason",
                    "",
                ),
            "night_shift_change":
                shift_values.get(
                    "night_shift_change"
                ),
            "night_shift_change_duration":
                shift_values.get(
                    "night_shift_change_duration"
                ),
            "night_fatigue_break":
                shift_values.get(
                    "night_fatigue_break"
                ),
            "night_fatigue_duration":
                shift_values.get(
                    "night_fatigue_duration"
                ),

            "total_planned_available_hours":
                shift_values.get(
                    "total_planned_available_hours"
                ),

            "night_operating_hours":
                night_operating_hours,

            "day_operating_hours":
                day_operating_hours,

            "total_operating_hours":
                total_operating_hours,

            "tbd_hours": 0,
        }

        row["day_mining_duration"] = (
            float(
                row.get(
                    "day_planned_available_hours"
                )
                or 0
            )
            -
            float(
                row.get(
                    "day_engineering_duration"
                )
                or 0
            )
        )

        row["night_mining_duration"] = (
            float(
                row.get(
                    "night_planned_available_hours"
                )
                or 0
            )
            -
            float(
                row.get(
                    "night_engineering_duration"
                )
                or 0
            )
        )

        row["tbd_hours"] = (
            float(
                row.get(
                    "night_engineering_duration"
                )
                or 0
            )
            +
            float(
                row.get(
                    "day_engineering_duration"
                )
                or 0
            )
        )

        row["available_hours"] = (
            float(
                row.get(
                    "total_planned_available_hours"
                )
                or 0
            )
            -
            float(
                row.get(
                    "tbd_hours"
                )
                or 0
            )
        )

        data.append(row)

    # ---------------------------------------------------------
    # MOS MACHINE CATEGORY GROUPING
    #
    # Machine headings and numbering are derived dynamically
    # from Asset -> Asset Category.
    #
    # No individual machine names are hard-coded.
    # ---------------------------------------------------------

    machine_names = [
        (
            row.get("day_asset")
            or row.get("night_machine")
        )
        for row in data
        if (
            row.get("day_asset")
            or row.get("night_machine")
        )
    ]

    asset_category_map = {}

    if machine_names:
        asset_rows = frappe.get_all(
            "Asset",
            filters={
                "name": [
                    "in",
                    list(set(machine_names)),
                ],
            },
            fields=[
                "name",
                "asset_category",
            ],
        )

        asset_category_map = {
            item.name: item.asset_category
            for item in asset_rows
        }

    category_names = list(
        {
            category
            for category in asset_category_map.values()
            if category
        }
    )

    category_meta = {}

    if category_names:
        category_rows = frappe.get_all(
            "Asset Category",
            filters={
                "name": [
                    "in",
                    category_names,
                ],
            },
            fields=[
                "name",
                "custom_mos_report_label",
                "custom_mos_report_order",
            ],
        )

        category_meta = {
            item.name: {
                "label": (
                    item.custom_mos_report_label
                    or item.name
                ),
                "order": (
                    item.custom_mos_report_order
                    or 0
                ),
            }
            for item in category_rows
        }

    category_counters = {}
    grouped_data = []
    previous_category = None

    for row in data:
        machine = (
            row.get("day_asset")
            or row.get("night_machine")
        )

        category = asset_category_map.get(
            machine
        )

        if not category:
            grouped_data.append(row)
            continue

        meta = category_meta.get(
            category,
            {},
        )

        category_label = (
            meta.get("label")
            or category
        )

        #
        # Insert a dedicated heading row before the first
        # machine of every category.
        #
        if category != previous_category:
            heading_label = category_label

            if heading_label.lower().endswith("s"):
                heading_label = (
                    heading_label[:-1]
                    + "'s"
                )
            else:
                heading_label = (
                    heading_label
                    + "'s"
                )

            heading_row = {
                "day_asset": heading_label,
                "night_machine": heading_label,

                "mos_group_heading": 1,
                "mos_machine_category": category,
                "mos_machine_category_label":
                    category_label,
            }

            grouped_data.append(
                frappe._dict(heading_row)
            )

            previous_category = category

        category_counters.setdefault(
            category,
            0,
        )

        category_counters[category] += 1

        row["mos_machine_category"] = category

        row["mos_machine_category_label"] = (
            category_label
        )

        row["mos_machine_category_order"] = (
            meta.get("order")
            or 0
        )

        row["mos_machine_sequence"] = (
            category_counters[category]
        )

        row["mos_group_heading"] = 0

        grouped_data.append(row)

    return grouped_data


def get_shift_type_window_definition(shift_type):
    """Return configured Shift Type start/end times."""

    if not shift_type:
        return None

    return frappe.db.get_value(
        "Shift Type",
        shift_type,
        [
            "start_time",
            "end_time",
        ],
        as_dict=True,
    )


def build_shift_window(shift_date, start_time, end_time):
    """Build one configured shift datetime window.

    Overnight shifts are supported automatically when the configured
    end time is earlier than or equal to the start time.
    """

    shift_date = getdate(shift_date)

    base = datetime.combine(
        shift_date,
        datetime.min.time(),
    )

    window_start = (
        base
        + get_timedelta(start_time)
    )

    window_end = (
        base
        + get_timedelta(end_time)
    )

    if window_end <= window_start:
        window_end += timedelta(days=1)

    return window_start, window_end


def get_shift_type_window_definition(shift_type):
    """Return the configured clock window for a Shift Type."""

    if not shift_type:
        return None

    return frappe.db.get_value(
        "Shift Type",
        shift_type,
        [
            "start_time",
            "end_time",
        ],
        as_dict=True,
    )


def build_shift_window(shift_date, start_time, end_time):
    """Build one real shift window for the supplied shift date.

    Overnight shifts are handled automatically when end_time is
    earlier than or equal to start_time.
    """

    shift_date = getdate(shift_date)

    base_datetime = datetime.combine(
        shift_date,
        datetime.min.time(),
    )

    window_start = (
        base_datetime
        + get_timedelta(start_time)
    )

    window_end = (
        base_datetime
        + get_timedelta(end_time)
    )

    if window_end <= window_start:
        window_end += timedelta(days=1)

    return window_start, window_end


def get_engineering_downtime(filters, shift_values):
    """Return Engineering downtime by PBM Shift and real shift cycle.

    Rules:

    - Plant Breakdown or Maintenance.shift decides DAY or NIGHT.
    - The configured Shift Type start/end times decide how many hours
      of that PBM belong to the selected report date.
    - A Night Shift PBM never moves into the Day section.
    - A Day Shift PBM never moves into the Night section.
    - A long/open PBM continues into the same shift on later dates.
    - One long PBM therefore contributes at most one configured shift
      window on each report date.
    - Multiple PBM records remain separate for raw validation, so bad
      or overlapping captures can still exceed planned hours and show
      N/A.
    """

    result = {
        "day": {},
        "night": {},
    }

    site = filters.get("site")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    if not site or not from_date or not to_date:
        return result

    config = frappe.db.get_value(
        "MOS Site Shift Configuration",
        {
            "site": site,
            "active": 1,
        },
        [
            "day_shift_type",
            "night_shift_type",
        ],
        as_dict=True,
    )

    if not config:
        return result

    from_date = getdate(from_date)
    to_date = getdate(to_date)

    shift_windows = {
        "day": [],
        "night": [],
    }

    def add_windows(shift_key, shift_type):
        if not shift_type:
            return

        definition = get_shift_type_window_definition(
            shift_type
        )

        if (
            not definition
            or definition.start_time is None
            or definition.end_time is None
        ):
            return

        current_date = from_date

        while current_date <= to_date:
            window_start, window_end = build_shift_window(
                current_date,
                definition.start_time,
                definition.end_time,
            )

            shift_windows[shift_key].append(
                (
                    window_start,
                    window_end,
                )
            )

            current_date += timedelta(days=1)

    if shift_values.get("day_selected"):
        add_windows(
            "day",
            config.day_shift_type,
        )

    if shift_values.get("night_selected"):
        add_windows(
            "night",
            config.night_shift_type,
        )

    all_windows = (
        shift_windows["day"]
        + shift_windows["night"]
    )

    if not all_windows:
        return result

    range_start = min(
        window[0]
        for window in all_windows
    )

    range_end = max(
        window[1]
        for window in all_windows
    )

    rows = frappe.db.sql(
        """
        SELECT
            name,
            asset_name,
            shift,
            breakdown_reason,
            breakdown_start_datetime,
            resolved_datetime,
            open_closed,
            IFNULL(breakdown_hours, 0) AS breakdown_hours
        FROM `tabPlant Breakdown or Maintenance`
        WHERE
            location = %(site)s
            AND asset_name IS NOT NULL
            AND IFNULL(exclude_from_au, 0) = 0
            AND breakdown_start_datetime < %(range_end)s
            AND (
                resolved_datetime > %(range_start)s

                OR (
                    resolved_datetime IS NULL
                    AND IFNULL(open_closed, '') != 'Closed'
                )

                OR (
                    resolved_datetime IS NULL
                    AND IFNULL(open_closed, '') = 'Closed'
                    AND TIMESTAMPADD(
                        SECOND,
                        CAST(
                            IFNULL(breakdown_hours, 0) * 3600
                            AS SIGNED
                        ),
                        breakdown_start_datetime
                    ) > %(range_start)s
                )
            )
        ORDER BY
            asset_name ASC,
            breakdown_start_datetime ASC,
            name ASC
        """,
        {
            "site": site,
            "range_start": range_start,
            "range_end": range_end,
        },
        as_dict=True,
    )

    collected = {
        "day": {},
        "night": {},
    }

    def merge_intervals(intervals):
        if not intervals:
            return []

        ordered = sorted(
            intervals,
            key=lambda item: item[0],
        )

        merged = [
            [
                ordered[0][0],
                ordered[0][1],
            ]
        ]

        for interval_start, interval_end in ordered[1:]:
            last = merged[-1]

            if interval_start <= last[1]:
                if interval_end > last[1]:
                    last[1] = interval_end
            else:
                merged.append(
                    [
                        interval_start,
                        interval_end,
                    ]
                )

        return [
            (
                item[0],
                item[1],
            )
            for item in merged
        ]

    def interval_hours(intervals):
        return sum(
            (
                interval_end - interval_start
            ).total_seconds() / 3600
            for interval_start, interval_end in intervals
        )

    current_datetime = now_datetime()

    for row in rows:
        #
        # PBM SHIFT CONTROLS WHICH MOS SECTION RECEIVES IT.
        #
        if row.shift == "Day Shift":
            shift_key = "day"

        elif row.shift == "Night Shift":
            shift_key = "night"

        else:
            continue

        #
        # Ignore this PBM if that shift was not selected in MOS.
        #
        if not shift_windows[shift_key]:
            continue

        pbm_start = row.breakdown_start_datetime

        if not pbm_start:
            continue

        #
        # Determine the real end of the breakdown.
        #
        # Closed record:
        # use Datetime back in production.
        #
        # Legacy closed record with no resolved datetime:
        # use stored breakdown_hours.
        #
        # Open record:
        # continues up to current time.
        #
        if row.resolved_datetime:
            pbm_end = row.resolved_datetime

        elif (
            row.open_closed == "Closed"
            and float(row.breakdown_hours or 0) > 0
        ):
            pbm_end = (
                pbm_start
                + timedelta(
                    hours=float(
                        row.breakdown_hours or 0
                    )
                )
            )

        else:
            pbm_end = current_datetime

        if pbm_end <= pbm_start:
            continue

        reason = (
            row.breakdown_reason
            or "No reason captured"
        ).strip()

        #
        # Only compare against the shift family selected on PBM.
        #
        # Example:
        # row.shift == Night Shift
        #
        # It is only compared with Night windows.
        # Day windows are deliberately ignored.
        #
        for window_start, window_end in shift_windows[
            shift_key
        ]:
            overlap_start = max(
                pbm_start,
                window_start,
            )

            overlap_end = min(
                pbm_end,
                window_end,
            )

            if overlap_start >= overlap_end:
                continue

            overlap_hours = (
                overlap_end
                - overlap_start
            ).total_seconds() / 3600

            asset_bucket = collected[
                shift_key
            ].setdefault(
                row.asset_name,
                {
                    "intervals": [],
                    "captured_duration": 0.0,
                    "entry_order": [],
                    "entries": {},
                },
            )

            #
            # Actual Engineering Duration:
            # overlapping real-time PBMs are merged later.
            #
            asset_bucket["intervals"].append(
                (
                    overlap_start,
                    overlap_end,
                )
            )

            #
            # Validation total:
            # every PBM remains separately counted.
            #
            asset_bucket[
                "captured_duration"
            ] += overlap_hours

            if row.name not in asset_bucket["entries"]:
                asset_bucket["entry_order"].append(
                    row.name
                )

                asset_bucket["entries"][
                    row.name
                ] = {
                    "reason": reason,
                    "duration": 0.0,
                }

            asset_bucket["entries"][
                row.name
            ]["duration"] += overlap_hours

    for shift_key in ("day", "night"):
        for asset_name, values in collected[
            shift_key
        ].items():
            merged_intervals = merge_intervals(
                values["intervals"]
            )

            duration = interval_hours(
                merged_intervals
            )

            reason_parts = []

            for entry_name in values["entry_order"]:
                entry = values["entries"][
                    entry_name
                ]

                entry_duration = float(
                    entry["duration"] or 0
                )

                if entry_duration <= 0:
                    continue

                reason_parts.append(
                    f'{entry["reason"]} '
                    f'({entry_duration:.2f}h)'
                )

            captured_reason = " | ".join(
                reason_parts
            )

            result[shift_key][asset_name] = {
                "reason": captured_reason,
                "duration": duration,

                "captured_duration": float(
                    values["captured_duration"]
                    or 0
                ),

                "captured_reason": captured_reason,
            }

    return result


def get_pre_use_operating_hours(filters, shift_values):
    """Return Pre-Use Working Hours grouped by Asset and MOS shift."""

    result = {
        "day": {},
        "night": {},
    }

    site = filters.get("site")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    if not site or not from_date or not to_date:
        return result

    include_day = bool(
        shift_values.get("day_selected")
    )

    include_night = bool(
        shift_values.get("night_selected")
    )

    if include_day:
        rows = frappe.db.sql(
            """
            SELECT
                child.asset_name,
                COALESCE(SUM(child.working_hours), 0) AS working_hours
            FROM `tabPre-Use Hours` parent
            INNER JOIN `tabPre-use Assets` child
                ON child.parent = parent.name
            WHERE
                parent.location = %(site)s
                AND parent.shift_date BETWEEN %(from_date)s AND %(to_date)s
                AND parent.shift = %(shift)s
                AND child.asset_name IS NOT NULL
            GROUP BY child.asset_name
            """,
            {
                "site": site,
                "from_date": from_date,
                "to_date": to_date,
                "shift": "Day",
            },
            as_dict=True,
        )

        result["day"] = {
            row.asset_name: float(row.working_hours or 0)
            for row in rows
        }

    if include_night:
        rows = frappe.db.sql(
            """
            SELECT
                child.asset_name,
                COALESCE(SUM(child.working_hours), 0) AS working_hours
            FROM `tabPre-Use Hours` parent
            INNER JOIN `tabPre-use Assets` child
                ON child.parent = parent.name
            WHERE
                parent.location = %(site)s
                AND parent.shift_date BETWEEN %(from_date)s AND %(to_date)s
                AND parent.shift = %(shift)s
                AND child.asset_name IS NOT NULL
            GROUP BY child.asset_name
            """,
            {
                "site": site,
                "from_date": from_date,
                "to_date": to_date,
                "shift": "Night",
            },
            as_dict=True,
        )

        result["night"] = {
            row.asset_name: float(row.working_hours or 0)
            for row in rows
        }

    return result


def get_monthly_planning_machine_status(filters):
    """Return machine Production / Standby status from Monthly Planning.

    Source of truth:
        Monthly Production Planning

    Excavators:
        Assigned to one or more trucks -> production
        Listed without assigned truck -> standby

    ADTs:
        Assigned to an excavator -> production
        Listed without excavator -> standby

    Dozers:
        Planned working type populated -> production
        Planned working type blank -> standby

    Production always wins if the same Asset appears in both states.
    """

    site = filters.get("site")
    report_date = (
        filters.get("from_date")
        or filters.get("to_date")
    )

    if not site or not report_date:
        return {}

    plan_name = frappe.db.get_value(
        "Monthly Production Planning",
        {
            "location": site,
            "prod_month_start_date": [
                "<=",
                report_date,
            ],
            "prod_month_end_date": [
                ">=",
                report_date,
            ],
        },
        "name",
        order_by="prod_month_start_date desc",
    )

    if not plan_name:
        return {}

    plan = frappe.get_doc(
        "Monthly Production Planning",
        plan_name,
    )

    statuses = {}

    def set_status(asset_name, status):
        if not asset_name:
            return

        asset_name = str(asset_name).strip()

        if not asset_name:
            return

        current = statuses.get(asset_name)

        # Production must always override Standby / Swing.
        if current == "production":
            return

        if status == "production":
            statuses[asset_name] = "production"
        elif current is None:
            statuses[asset_name] = "standby"

    #
    # Excavators + ADTs
    #
    for assignment in (
        plan.excavator_truck_assignments or []
    ):
        excavator = assignment.excavator
        truck = assignment.truck

        if excavator:
            set_status(
                excavator,
                (
                    "production"
                    if truck
                    else "standby"
                ),
            )

        if truck:
            set_status(
                truck,
                (
                    "production"
                    if excavator
                    else "standby"
                ),
            )

    #
    # Dozers
    #
    for dozer in plan.dozer_table or []:
        asset_name = dozer.asset_name

        if not asset_name:
            continue

        dozing_type = str(
            dozer.dozing_type or ""
        ).strip()

        set_status(
            asset_name,
            (
                "production"
                if dozing_type
                else "standby"
            ),
        )

    return statuses


def get_shift_configuration_values(filters):
    """Read configured Day/Night MOS values for the selected Site.

    A section is populated only when its configured Shift Type
    is included in the user's Shift filter.
    """

    values = {}

    site = filters.get("site")

    if not site:
        return values

    selected_shifts = normalise_selected_shifts(
        filters.get("shift")
    )

    if not selected_shifts:
        return values

    config_name = frappe.db.get_value(
        "MOS Site Shift Configuration",
        {
            "site": site,
            "active": 1,
        },
        "name",
    )

    if not config_name:
        return values

    config = frappe.get_doc(
        "MOS Site Shift Configuration",
        config_name,
    )

    total_planned_available_hours = 0

    values["day_selected"] = bool(
        config.day_shift_type
        and config.day_shift_type in selected_shifts
    )

    values["night_selected"] = bool(
        config.night_shift_type
        and config.night_shift_type in selected_shifts
    )

    if values["day_selected"]:
        day_planned_hours = (
            get_planned_available_hours_value(
                config.day_planned_available_hours
            )
        )

        values["day_planned_available_hours"] = (
            day_planned_hours
        )

        if day_planned_hours is not None:
            total_planned_available_hours += (
                float(day_planned_hours)
            )

        values["day_shift_change"] = (
            config.day_shift_change or None
        )

        values["day_shift_change_duration"] = (
            get_duration_value(
                "MOS Shift Change",
                config.day_shift_change,
            )
        )

        values["day_fatigue_break"] = (
            config.day_fatigue_break or None
        )

        values["day_fatigue_duration"] = (
            get_duration_value(
                "MOS Fatigue Break",
                config.day_fatigue_break,
            )
        )

    if values["night_selected"]:
        night_planned_hours = (
            get_planned_available_hours_value(
                config.night_planned_available_hours
            )
        )

        values["night_planned_available_hours"] = (
            night_planned_hours
        )

        if night_planned_hours is not None:
            total_planned_available_hours += (
                float(night_planned_hours)
            )

        values["night_shift_change"] = (
            config.night_shift_change or None
        )

        values["night_shift_change_duration"] = (
            get_duration_value(
                "MOS Shift Change",
                config.night_shift_change,
            )
        )

        values["night_fatigue_break"] = (
            config.night_fatigue_break or None
        )

        values["night_fatigue_duration"] = (
            get_duration_value(
                "MOS Fatigue Break",
                config.night_fatigue_break,
            )
        )

    values["total_planned_available_hours"] = (
        total_planned_available_hours
    )

    return values


def get_planned_available_hours_value(link_name):
    if not link_name:
        return None

    return frappe.db.get_value(
        "MOS Planned Available Hours",
        link_name,
        "hours",
    )


def get_duration_value(doctype, link_name):
    if not link_name:
        return None

    return frappe.db.get_value(
        doctype,
        link_name,
        "duration_hours",
    )


def normalise_selected_shifts(value):
    """Normalise Frappe MultiSelectList values to a set."""

    if not value:
        return set()

    if isinstance(value, (list, tuple, set)):
        return {
            str(item).strip()
            for item in value
            if str(item).strip()
        }

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return set()

        if stripped.startswith("["):
            try:
                parsed = frappe.parse_json(stripped)

                if isinstance(parsed, list):
                    return {
                        str(item).strip()
                        for item in parsed
                        if str(item).strip()
                    }
            except Exception:
                pass

        return {
            item.strip()
            for item in stripped.split(",")
            if item.strip()
        }

    return {str(value).strip()}


def get_columns():
    return [
        # ============================================================
        # NIGHT SHIFT
        # ============================================================
        {
            "label": _("Machine"),
            "fieldname": "night_machine",
            "fieldtype": "Link",
            "options": "Asset",
            "width": 220,
        },
        {
            "label": _("Planned Available Hours"),
            "fieldname": "night_planned_available_hours",
            "fieldtype": "Float",
            "width": 150,
            "precision": 2,
        },
        {
            "label": _("Downtime/Planned Maintenance (Engineering)"),
            "fieldname": "night_engineering_downtime",
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "label": _("Duration"),
            "fieldname": "night_engineering_duration",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },
        {
            "label": _("Reason for Delay (Mining)"),
            "fieldname": "night_mining_delay",
            "fieldtype": "Data",
            "width": 260,
        },
        {
            "label": _("Duration"),
            "fieldname": "night_mining_duration",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },
        {
            "label": _("Shift Change"),
            "fieldname": "night_shift_change",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Duration"),
            "fieldname": "night_shift_change_duration",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },
        {
            "label": _("Fatigue Break"),
            "fieldname": "night_fatigue_break",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Duration"),
            "fieldname": "night_fatigue_duration",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },

        # ============================================================
        # DAY SHIFT
        # ============================================================
        {
            "label": _("Machine"),
            "fieldname": "day_asset",
            "fieldtype": "Link",
            "options": "Asset",
            "width": 220,
        },
        {
            "label": _("Planned Available Hours"),
            "fieldname": "day_planned_available_hours",
            "fieldtype": "Float",
            "width": 150,
            "precision": 2,
        },
        {
            "label": _("Downtime/Planned Maintenance (Engineering)"),
            "fieldname": "day_engineering_downtime",
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "label": _("Duration"),
            "fieldname": "day_engineering_duration",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },
        {
            "label": _("Reason for Delay (Mining)"),
            "fieldname": "day_mining_delay",
            "fieldtype": "Data",
            "width": 260,
        },
        {
            "label": _("Duration"),
            "fieldname": "day_mining_duration",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },
        {
            "label": _("Shift Change"),
            "fieldname": "day_shift_change",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Duration"),
            "fieldname": "day_shift_change_duration",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },
        {
            "label": _("Fatigue Break"),
            "fieldname": "day_fatigue_break",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Duration"),
            "fieldname": "day_fatigue_duration",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },

        # ============================================================
        # TOTALS
        # ============================================================
        {
            "label": _("Total Planned Available Hours"),
            "fieldname": "total_planned_available_hours",
            "fieldtype": "Float",
            "width": 180,
            "precision": 2,
        },
        {
            "label": _("Night Operating Hours"),
            "fieldname": "night_operating_hours",
            "fieldtype": "Float",
            "width": 150,
            "precision": 2,
        },
        {
            "label": _("Day Operating Hours"),
            "fieldname": "day_operating_hours",
            "fieldtype": "Float",
            "width": 150,
            "precision": 2,
        },
        {
            "label": _("Total Operating Hours"),
            "fieldname": "total_operating_hours",
            "fieldtype": "Float",
            "width": 150,
            "precision": 2,
        },
        {
            "label": _("TBD"),
            "fieldname": "tbd_hours",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },
        {
            "label": _("Available Hours"),
            "fieldname": "available_hours",
            "fieldtype": "Float",
            "width": 130,
            "precision": 2,
        },
    ]
