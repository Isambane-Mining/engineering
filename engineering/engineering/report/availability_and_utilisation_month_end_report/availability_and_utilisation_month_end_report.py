# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import frappe
from engineering.engineering.machine_exclusions import is_pre_use_au_excluded
from datetime import timedelta
from frappe.utils import flt, get_datetime, getdate, nowdate

_ = frappe._

MONTH_END_CATEGORIES = [
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

from is_production.production.report.avail_and_util_summary import (
    avail_and_util_summary as summary,
)

from is_production.production.report.avail_and_util_report import (
    avail_and_util_report as detailed_au,
)

from engineering.engineering.report.availability_and_utilisation_engine import (
    availability_and_utilisation_engine as au_engine,
)

def safe_msr_datetime(value, service_date=None):
    if value in (None, ""):
        return None

    value_text = str(value).strip()
    if not value_text:
        return None

    service_date_text = str(service_date).strip() if service_date else None

    if (
        "0000-00-00" in value_text
        or "-00-" in value_text
        or value_text.startswith("2008-00-00")
    ):
        if service_date_text and " " in value_text:
            time_text = value_text.split()[-1].split(".")[0]
            try:
                return safe_msr_datetime(f"{service_date_text} {time_text}")
            except Exception:
                return None
        return None

    try:
        return get_datetime(value)
    except Exception:
        if service_date_text and ":" in value_text:
            time_text = value_text.split()[-1].split(".")[0]
            try:
                return safe_msr_datetime(f"{service_date_text} {time_text}")
            except Exception:
                return None
        return None


def safe_getdate(value):
    if value in (None, ""):
        return None

    value_text = str(value).strip()
    if not value_text:
        return None

    if "0000-00-00" in value_text or "-00-" in value_text or value_text.startswith("2008-00-00"):
        return None

    try:
        return getdate(value)
    except Exception:
        return None

def get_au_target_multiplier(filters):
	filters = filters or {}
	au_target_filter = filters.get("au_target_filter") or "85% A & U"

	if au_target_filter == "85% A & U":
		return 0.85

	return 1.0


def apply_au_target(value, filters):
	if value in (None, ""):
		return value

	multiplier = get_au_target_multiplier(filters)

	return summary.r1(flt(value) * multiplier)

def execute(filters=None):
	filters = filters or {}

	# "All Equipment" means no Asset Category filter.
	if filters.get("asset_category") == "All Equipment":
	    filters["asset_category"] = None

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns():
	return [
		{"label": _("Asset Category"), "fieldname": "asset_category", "fieldtype": "Data", "width": 130},
		{"label": _("Asset Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 110},
		{"label": _("Req Hrs"), "fieldname": "required_hrs", "fieldtype": "Float", "precision": 1, "width": 90},
		{"label": _("Work Hrs"), "fieldname": "work_hrs", "fieldtype": "Float", "precision": 1, "width": 90},
		{"label": _("Avail Hrs"), "fieldname": "available_hrs", "fieldtype": "Float", "precision": 1, "width": 95},
		{"label": _("Avail Hrs Above 100"), "fieldname": "available_hrs_above_100", "fieldtype": "Float", "precision": 1, "width": 155},
		{"label": _("Mechanical Downtime"), "fieldname": "mechanical_downtime", "fieldtype": "Float", "precision": 1, "width": 160},
		{"label": _("Avail (%)"), "fieldname": "avail_percent", "fieldtype": "Percent", "precision": 1, "width": 100},
		{"label": _("Util (%)"), "fieldname": "util_percent", "fieldtype": "Percent", "precision": 1, "width": 100},
		{"label": _("Breakdown Reason"), "fieldname": "breakdown_reason", "fieldtype": "Small Text", "width": 300},
		{"label": _("Other Delay Reason"), "fieldname": "other_delay_reason", "fieldtype": "Small Text", "width": 300},
	]






def get_data(filters):
	filters = frappe._dict(filters or {})

	# Do not calculate dates after today.
	to_date = filters.get("to_date") or filters.get("end_date")

	if to_date and getdate(to_date) > getdate(nowdate()):
		filters["to_date"] = nowdate()
		filters["end_date"] = nowdate()

	machine_scope = (
		filters.get("machine_scope")
		or "Production + Swing/Spare Machines"
	)

	source_machine_scope = machine_scope

	if machine_scope == "Production + Swing/Spare Machines":
		source_machine_scope = "Include Swing/Spare"

	summary_filters = {
		"start_date": filters.get("from_date"),
		"end_date": filters.get("to_date"),
		"location": filters.get("location"),
		"machine_scope": source_machine_scope,
	}

	summary_rows = summary.get_grouped_data(summary_filters)

	machine_rows = [
		row for row in summary_rows
		if row.get("indent") == 2
	]

	if filters.get("asset_category"):
		machine_rows = [
			row for row in machine_rows
			if row.get("asset_category") == filters.get("asset_category")
		]

	grouped = {}

	for row in machine_rows:
		key = (
			row.get("asset_category"),
			row.get("asset_name"),
			row.get("location"),
		)

		if key not in grouped:
			grouped[key] = {
				"asset_category": row.get("asset_category"),
				"asset_name": row.get("asset_name"),
				"location": row.get("location"),
				"shift_required_hours": 0,
				"shift_working_hours": 0,
				"shift_breakdown_hours": 0,
				"shift_available_hours": 0,
				"shift_other_lost_hours": 0,
				"avail_percentages": [],
				"true_avail_percentages": [],
				"util_percentages": [],
				"emp_avail_percentages": [],
				"breakdown_reason": [],
				"other_delay_reason": [],
			}

		target = grouped[key]

		target["shift_required_hours"] += flt(row.get("shift_required_hours"))
		target["shift_working_hours"] += flt(row.get("shift_working_hours"))
		target["shift_breakdown_hours"] += flt(row.get("shift_breakdown_hours"))
		target["shift_available_hours"] += flt(row.get("shift_available_hours"))
		target["shift_other_lost_hours"] += flt(row.get("shift_other_lost_hours"))

		target["avail_percentages"].append(
			flt(row.get("plant_shift_availability"))
		)

		target["true_avail_percentages"].append(
			flt(row.get("true_availability_percent"))
		)

		target["util_percentages"].append(
			flt(row.get("plant_shift_utilisation"))
		)

		target["emp_avail_percentages"].append(
			flt(row.get("employee_availability"))
		)

		if row.get("breakdown_reason"):
			target["breakdown_reason"].append(row.get("breakdown_reason"))

		if row.get("other_delay_reason"):
			target["other_delay_reason"].append(row.get("other_delay_reason"))

	data = []

	use_true_availability = (
		filters.get("au_target_filter")
		== "85% A & U"
	)

	availability_list_field = (
		"true_avail_percentages"
		if use_true_availability
		else "avail_percentages"
	)

	category_total_rows = [
		row for row in summary_rows
		if row.get("indent") == 0
	]

	if filters.get("asset_category"):
		category_total_rows = [
			row for row in category_total_rows
			if row.get("asset_category") == filters.get("asset_category")
		]

	for row in category_total_rows:
		category = row.get("asset_category")

		category_machines = [
			machine
			for machine in grouped.values()
			if machine.get("asset_category") == category
		]

		machine_avail_values = [
			average_percent(
				machine.get(
					availability_list_field
				)
				or []
			)
			for machine in category_machines
		]

		machine_util_values = [
			average_percent(machine.get("util_percentages") or [])
			for machine in category_machines
		]

		data.append({
			"asset_category": category,
			"asset_name": "",
			"required_hrs": summary.r1(row.get("shift_required_hours")),
			"work_hrs": summary.r1(row.get("shift_working_hours")),
			"mechanical_downtime": summary.r1(row.get("shift_breakdown_hours")),
			"avail_percent": summary.r1(
				average_percent(
					machine_avail_values
				)
			),
			"util_percent": apply_au_target(
				average_percent(machine_util_values),
				filters,
			),
			"emp_avail_percent": summary.r1(
				row.get("employee_availability")
			),
			"breakdown_reason": "",
			"other_delay_reason": "",
			"is_category_total": 1,
		})

	data.append({
		"asset_category": "",
		"asset_name": "",
		"required_hrs": None,
		"work_hrs": None,
		"mechanical_downtime": None,
		"avail_percent": None,
		"util_percent": None,
		"emp_avail_percent": None,
		"breakdown_reason": "",
		"other_delay_reason": "",
		"is_separator": 1,
	})

	for row in grouped.values():
		required_hrs = flt(row["shift_required_hours"])
		work_hrs = flt(row["shift_working_hours"])
		mechanical_downtime = flt(row["shift_breakdown_hours"])

		data.append({
			"asset_category": row["asset_category"],
			"asset_name": row["asset_name"],
			"required_hrs": summary.r1(required_hrs),
			"work_hrs": summary.r1(work_hrs),
			"mechanical_downtime": summary.r1(mechanical_downtime),
			"avail_percent": summary.r1(
				average_percent(
					row.get(
						availability_list_field
					)
					or []
				)
			),
			"util_percent": apply_au_target(
				average_percent(row["util_percentages"]),
				filters,
			),
			"emp_avail_percent": average_percent(
				row["emp_avail_percentages"]
			),
			"breakdown_reason": clean_join(row["breakdown_reason"]),
			"other_delay_reason": clean_join(row["other_delay_reason"]),
		})

	return data


def ensure_all_category_total_rows(data):
    existing_categories = {
        row.get("asset_category")
        for row in data
        if row.get("asset_category") and not row.get("asset_name")
    }

    insert_at = 0

    for category in UI_CATEGORIES:
        if category in existing_categories:
            continue

        data.insert(insert_at, {
            "asset_category": category,
            "asset_name": "",
            "required_hrs": 0,
            "work_hrs": 0,
            "mechanical_downtime": 0,
            "avail_percent": 0,
            "util_percent": 0,
            "emp_avail_percent": 0,
            "breakdown_reason": "",
            "other_delay_reason": "",
            "is_category_total": 1,
        })

        insert_at += 1

    data.sort(
        key=lambda row: (
            UI_CATEGORIES.index(row.get("asset_category"))
            if row.get("asset_category") in UI_CATEGORIES
            else 999,
            0 if not row.get("asset_name") else 1,
            row.get("asset_name") or "",
        )
    )

    return data


def average_percent(values):
	valid_values = [
		flt(value)
		for value in values
		if value is not None
	]

	if not valid_values:
		return 0

	return summary.r1(
		sum(valid_values)
		/ len(valid_values)
	)


def average_percent_or_none(values):
	valid_values = [
		flt(value)
		for value in values
		if value not in (None, "")
	]

	if not valid_values:
		return None

	return summary.r1(
		sum(valid_values)
		/ len(valid_values)
	)




def clean_join(values):
	cleaned = []

	for value in values:
		if not value:
			continue

		for part in str(value).split(";"):
			part = part.strip()
			if part and part not in cleaned:
				cleaned.append(part)

	return "\n".join(cleaned)


def clean_reason_details(details):
    grouped = {}
    order = []

    for detail in details or []:
        date_value = str(
            detail.get("date") or ""
        )[:10]

        start_datetime = str(
            detail.get("start_datetime") or ""
        )[:16]

        resolved_datetime = str(
            detail.get("resolved_datetime") or ""
        )[:16]

        total_minutes = int(
            flt(detail.get("total_minutes"))
        )

        startup_fatigue_minutes = int(
            flt(
                detail.get(
                    "startup_fatigue_minutes"
                )
            )
        )

        sunday_minutes = int(
            flt(detail.get("sunday_minutes"))
        )

        au_minutes = int(
            flt(detail.get("au_minutes"))
        )

        interval_key = (
            date_value,
            start_datetime,
            resolved_datetime,
        )

        if interval_key not in grouped:
            grouped[interval_key] = {
                "date": date_value,
                "start_datetime": start_datetime,
                "resolved_datetime": resolved_datetime,
                "total_minutes": total_minutes,
                "startup_fatigue_minutes": (
                    startup_fatigue_minutes
                ),
                "sunday_minutes": sunday_minutes,
                "au_minutes": au_minutes,
                "reasons": [],
            }

            order.append(interval_key)

        reason_value = str(
            detail.get("reason") or ""
        )

        for part in (
            reason_value
            .replace("\n", ";")
            .split(";")
        ):
            part = part.strip()

            if (
                part
                and part
                not in grouped[
                    interval_key
                ]["reasons"]
            ):
                grouped[
                    interval_key
                ]["reasons"].append(part)

    cleaned = []

    for interval_key in order:
        grouped_row = grouped[interval_key]

        cleaned.append({
            "date": grouped_row["date"],
            "start_datetime": (
                grouped_row[
                    "start_datetime"
                ]
            ),
            "resolved_datetime": (
                grouped_row[
                    "resolved_datetime"
                ]
            ),
            "total_minutes": (
                grouped_row[
                    "total_minutes"
                ]
            ),
            "startup_fatigue_minutes": (
                grouped_row[
                    "startup_fatigue_minutes"
                ]
            ),
            "sunday_minutes": (
                grouped_row[
                    "sunday_minutes"
                ]
            ),
            "au_minutes": (
                grouped_row[
                    "au_minutes"
                ]
            ),
            "reason": "\n".join(
                grouped_row["reasons"]
            ),
        })

    return cleaned


def get_required_downtime_minutes_for_breakdown(
    filters,
    asset_name,
    start_datetime,
    resolved_datetime,
):
    """Calculate PBM overlap using Engine planning data.

    Shift system and required hours come from Monthly Production
    Planning. Startup/fatigue exclusions come from the configured
    Startup and Fatigue specification.
    """

    empty_result = {
        "total_minutes": 0,
        "required_downtime_minutes": 0,
        "excluded_minutes": 0,
        "sunday_minutes": 0,
    }

    if not start_datetime or not resolved_datetime:
        return empty_result

    filters = frappe._dict(filters or {})

    location = _month_end_get_filter_value(
        filters,
        "location",
        "site",
        "production_site",
    )

    if not location:
        return empty_result

    start_dt = get_datetime(start_datetime)
    end_dt = get_datetime(resolved_datetime)

    if not start_dt or not end_dt or end_dt <= start_dt:
        return empty_result

    from engineering.engineering.report.availability_and_utilisation_engine import (
        availability_and_utilisation_engine as engine,
    )

    # This helper reads Startup and Fatigue specification records.
    # It does not read Availability and Utilisation shift records.
    from engineering.engineering.doctype.availability_and_utilisation.availability_and_utilisation import (
        _exclusion_windows,
    )

    planning_from_date = (
        getdate(start_dt)
        - timedelta(days=1)
    )

    planning_to_date = (
        getdate(end_dt)
        + timedelta(days=1)
    )

    planning_rows = engine.get_planning_rows(
        planning_from_date,
        planning_to_date,
        [location],
    )

    planning_map = engine.build_planning_map(
        planning_rows
    )

    def overlap_hours(
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

        return (
            overlap_end - overlap_start
        ).total_seconds() / 3600.0

    def get_shift_window(
        shift_system,
        shift,
        shift_date,
    ):
        shift_system = str(
            shift_system or ""
        ).strip().lower()

        shift_date = getdate(shift_date)

        if shift_system == "2x12hour":
            timings = {
                "Day": (6, 18, 0),
                "Night": (18, 6, 1),
            }
        else:
            timings = {
                "Morning": (6, 14, 0),
                "Afternoon": (14, 22, 0),
                "Night": (22, 6, 1),
            }

        timing = timings.get(shift)

        if not timing:
            return None, None

        start_hour, end_hour, end_day_offset = timing

        shift_start = get_datetime(
            f"{shift_date} {start_hour:02d}:00:00"
        )

        shift_end_date = (
            shift_date
            + timedelta(days=end_day_offset)
        )

        shift_end = get_datetime(
            f"{shift_end_date} {end_hour:02d}:00:00"
        )

        return shift_start, shift_end

    raw_overlap_hours = 0.0
    required_downtime_hours = 0.0
    excluded_overlap_hours = 0.0
    sunday_overlap_hours = 0.0

    current_date = planning_from_date

    while current_date <= planning_to_date:
        planning = planning_map.get(
            (
                location,
                str(current_date),
            )
        )

        if not planning:
            current_date += timedelta(days=1)
            continue

        shift_system = planning.get(
            "shift_system"
        )

        for shift in engine.get_shifts(
            shift_system
        ):
            shift_start, shift_end = (
                get_shift_window(
                    shift_system,
                    shift,
                    current_date,
                )
            )

            if not shift_start or not shift_end:
                continue

            shift_overlap_hours = overlap_hours(
                start_dt,
                end_dt,
                shift_start,
                shift_end,
            )

            if shift_overlap_hours <= 0:
                continue

            raw_overlap_hours += shift_overlap_hours

            excluded_hours = 0.0

            for window_start, window_end in (
                _exclusion_windows(
                    location,
                    shift,
                    shift_start,
                    shift_end,
                )
            ):
                excluded_hours += overlap_hours(
                    start_dt,
                    end_dt,
                    window_start,
                    window_end,
                )

            excluded_hours = min(
                excluded_hours,
                shift_overlap_hours,
            )

            valid_overlap_hours = max(
                shift_overlap_hours
                - excluded_hours,
                0,
            )

            excluded_overlap_hours += (
                excluded_hours
            )

            required_hours = max(
                flt(
                    engine.get_required_hours(
                        planning,
                        shift,
                    )
                ),
                0,
            )

            if (
                current_date.weekday() == 6
                and required_hours <= 0
            ):
                sunday_overlap_hours += (
                    valid_overlap_hours
                )
                continue

            if required_hours <= 0:
                continue

            required_downtime_hours += min(
                valid_overlap_hours,
                required_hours,
            )

        current_date += timedelta(days=1)

    return {
        "total_minutes": int(round(
            raw_overlap_hours * 60
        )),
        "required_downtime_minutes": int(round(
            required_downtime_hours * 60
        )),
        "excluded_minutes": int(round(
            excluded_overlap_hours * 60
        )),
        "sunday_minutes": int(round(
            sunday_overlap_hours * 60
        )),
    }


def get_plant_breakdown_reason_details(filters, asset_names):
	if not asset_names:
		return {}

	if not frappe.db.exists(
		"DocType",
		"Plant Breakdown or Maintenance",
	):
		return {}

	filters = frappe._dict(filters or {})

	from_date = _month_end_get_filter_value(
		filters,
		"from_date",
		"start_date",
	)

	to_date = _month_end_get_filter_value(
		filters,
		"to_date",
		"end_date",
	)

	location = _month_end_get_filter_value(
		filters,
		"location",
		"site",
		"production_site",
	)

	if not from_date or not to_date:
		return {}

	report_start = get_datetime(
		f"{getdate(from_date)} 06:00:00"
	)

	report_end_date = getdate(to_date) + timedelta(
		days=1
	)

	report_end = get_datetime(
		f"{report_end_date} 06:00:00"
	)

	values = {
		"from_datetime": report_start,
		"to_datetime": report_end,
		"asset_names": tuple(asset_names),
		"plant_breakdown_trust_datetime": (
			"2026-01-01 00:00:00"
		),
	}

	conditions = [
		"IFNULL(asset_name, '') != ''",
		"IFNULL(breakdown_reason, '') != ''",
		"IFNULL(exclude_from_au, 0) = 0",
		"asset_name IN %(asset_names)s",
		(
			"breakdown_start_datetime >= "
			"%(plant_breakdown_trust_datetime)s"
		),
		(
			"breakdown_start_datetime <= "
			"%(to_datetime)s"
		),
		(
			"(resolved_datetime >= "
			"%(from_datetime)s "
			"OR resolved_datetime IS NULL)"
		),
	]

	if location:
		conditions.append(
			"location = %(location)s"
		)

		values["location"] = location

	rows = frappe.db.sql(
		f"""
		SELECT
			asset_name,
			location,
			breakdown_start_datetime,
			resolved_datetime,
			breakdown_reason
		FROM `tabPlant Breakdown or Maintenance`
		WHERE {" AND ".join(conditions)}
		ORDER BY breakdown_start_datetime ASC
		""",
		values,
		as_dict=True,
	)

	details_by_asset = {}
	seen_intervals = set()

	for row in rows:
		start_datetime = row.get(
			"breakdown_start_datetime"
		)

		resolved_datetime = row.get(
			"resolved_datetime"
		)

		if not start_datetime:
			continue

		start_dt = get_datetime(
			start_datetime
		)

		end_dt = (
			get_datetime(
				resolved_datetime
			)
			if resolved_datetime
			else report_end
		)

		clipped_start = max(
			start_dt,
			report_start,
		)

		clipped_end = min(
			end_dt,
			report_end,
		)

		if clipped_end <= clipped_start:
			continue

		interval_key = (
			row.get("asset_name"),
			row.get("location"),
			str(clipped_start),
			str(clipped_end),
			row.get("breakdown_reason"),
		)

		if interval_key in seen_intervals:
			continue

		seen_intervals.add(
			interval_key
		)

		row_filters = frappe._dict(
			filters.copy()
		)

		row_filters["location"] = (
			row.get("location")
		)

		current_date = getdate(
			clipped_start
		)

		current_day_start = get_datetime(
			f"{current_date} 06:00:00"
		)

		if clipped_start < current_day_start:
			current_date = (
				current_date
				- timedelta(days=1)
			)

		while True:
			day_start = get_datetime(
				f"{current_date} 06:00:00"
			)

			day_end = (
				day_start
				+ timedelta(days=1)
			)

			if day_start >= clipped_end:
				break

			segment_start = max(
				clipped_start,
				day_start,
			)

			segment_end = min(
				clipped_end,
				day_end,
			)

			if segment_end > segment_start:
				required_downtime = (
					get_required_downtime_minutes_for_breakdown(
						row_filters,
						row.get(
							"asset_name"
						),
						segment_start,
						segment_end,
					)
				)

				details_by_asset.setdefault(
					row.get("asset_name"),
					[],
				).append({
					"date": str(
						current_date
					),
					"start_datetime": (
						segment_start
					),
					"resolved_datetime": (
						segment_end
					),
					"total_minutes": (
						required_downtime[
							"total_minutes"
						]
					),
					"startup_fatigue_minutes": (
						required_downtime[
							"excluded_minutes"
						]
					),
					"sunday_minutes": (
						required_downtime[
							"sunday_minutes"
						]
					),
					"au_minutes": (
						required_downtime[
							"required_downtime_minutes"
						]
					),
					"reason": row.get(
						"breakdown_reason"
					),
				})

			current_date = (
				current_date
				+ timedelta(days=1)
			)

	return details_by_asset


def get_breakdown_reason(row, filters):
	if not frappe.db.exists("DocType", "Breakdown History"):
		return None

	meta = frappe.get_meta("Breakdown History")
	possible_fields = [
		"breakdown_reason",
		"reason",
		"remarks",
		"description",
		"comment",
		"comments",
	]

	reason_field = None
	for fieldname in possible_fields:
		if meta.has_field(fieldname):
			reason_field = fieldname
			break

	if not reason_field:
		return None

	reasons = frappe.db.sql(
		f"""
		select distinct `{reason_field}`
		from `tabBreakdown History`
		where asset_name = %(asset_name)s
			and location = %(location)s
			and date(update_date_time) between %(from_date)s and %(to_date)s
			and ifnull(`{reason_field}`, '') != ''
		order by update_date_time asc
		""",
		{
			"asset_name": row.asset_name,
			"location": row.location,
			"from_date": filters.get("from_date"),
			"to_date": filters.get("to_date"),
		},
		as_dict=True,
	)

	return "; ".join([d.get(reason_field) for d in reasons if d.get(reason_field)])







def get_other_delay_reason(row):
	reasons = []

	if flt(row.other_lost_hrs) > 0:
		reasons.append("Other lost hours")

	return "\n".join(reasons) if reasons else None

# GLH_MONTH_END_MACHINE_REASON_HELPER_START

def get_general_lost_hour_machine_reason_details(
    filters,
    asset_rows,
    categories,
):
    """
    General Lost Hours for Month End popup.

    Rules:
    - Specific machine -> that machine only
    - ALL Equipment    -> every applicable machine
    - Blank machine    -> ignored

    Saved Draft Daily Lost Hours Recon records are included.
    """

    filters = frappe._dict(
        filters or {}
    )

    from_date = (
        filters.get("from_date")
        or filters.get("start_date")
    )

    to_date = (
        filters.get("to_date")
        or filters.get("end_date")
    )

    location = filters.get(
        "location"
    )


    if (
        not from_date
        or not to_date
    ):
        return {}


    if not frappe.db.exists(
        "DocType",
        "Daily General Lost Hours",
    ):
        return {}


    if not frappe.db.exists(
        "DocType",
        "Daily Lost Hours Recon",
    ):
        return {}


    # ========================================================
    # MONTH END MACHINE LIST
    # ========================================================

    asset_category_by_name = {}

    machines = []


    for asset in asset_rows or []:

        if hasattr(
            asset,
            "get",
        ):
            asset_name = (
                asset.get(
                    "asset_name"
                )
            )

            asset_category = (
                asset.get(
                    "asset_category"
                )
            )

        else:
            asset_name = getattr(
                asset,
                "asset_name",
                None,
            )

            asset_category = getattr(
                asset,
                "asset_category",
                None,
            )


        asset_name = str(
            asset_name or ""
        ).strip()

        asset_category = str(
            asset_category or ""
        ).strip()


        if not asset_name:
            continue


        if (
            categories
            and asset_category
            not in categories
        ):
            continue


        asset_category_by_name[
            asset_name
        ] = asset_category


        if asset_name not in machines:
            machines.append(
                asset_name
            )


    if not machines:
        return {}


    # ========================================================
    # GENERAL LOST HOURS
    # ========================================================

    conditions = [
        (
            "r.shift_date BETWEEN "
            "%(from_date)s AND %(to_date)s"
        ),
        (
            "IFNULL(TRIM(g.machine), '') != ''"
        ),
    ]


    values = {
        "from_date": from_date,
        "to_date": to_date,
    }


    if location:

        conditions.append(
            "r.location = %(location)s"
        )

        values[
            "location"
        ] = location


    rows = frappe.db.sql(
        f"""
        SELECT
            r.name AS recon_name,
            r.location,
            r.shift_date,
            r.shift,

            g.idx,
            g.machine,
            g.lost_hour_category,
            g.reason_description,
            g.start_time,
            g.end_time,
            g.total_hours,
            g.location AS delay_location

        FROM `tabDaily Lost Hours Recon` r

        INNER JOIN `tabDaily General Lost Hours` g
            ON g.parent = r.name

        WHERE
            {" AND ".join(conditions)}

        ORDER BY
            r.shift_date ASC,
            r.shift ASC,
            g.idx ASC
        """,
        values,
        as_dict=True,
    )


    result = {}


    # ========================================================
    # FORMAT TIME
    # ========================================================

    def clean_time(value):

        if value is None:
            return ""

        value = str(
            value
        ).strip()


        if "." in value:
            value = value.split(
                ".",
                1,
            )[0]


        parts = value.split(
            ":"
        )


        if (
            len(parts) >= 2
            and len(parts[0]) == 1
        ):
            value = (
                "0"
                + value
            )


        return value


    # ========================================================
    # ADD ONE CAPTURE TO ONE MACHINE
    # ========================================================

    def append_reason(
        target_machine,
        row,
    ):

        target_machine = str(
            target_machine or ""
        ).strip()


        if not target_machine:
            return


        category = (
            asset_category_by_name.get(
                target_machine
            )
        )


        if not category:
            return


        if (
            categories
            and category
            not in categories
        ):
            return


        key = (
            category,
            target_machine,
        )


        lost_hour_category = str(
            row.get(
                "lost_hour_category"
            )
            or ""
        ).strip()


        reason_description = str(
            row.get(
                "reason_description"
            )
            or ""
        ).strip()


        start_time = clean_time(
            row.get(
                "start_time"
            )
        )


        end_time = clean_time(
            row.get(
                "end_time"
            )
        )


        total_hours = round(
            flt(
                row.get(
                    "total_hours"
                )
            ),
            2,
        )


        delay_location = str(
            row.get(
                "delay_location"
            )
            or ""
        ).strip()


        reason_text = (
            reason_description
            or lost_hour_category
        )


        detail = {
            "detail_type":
                "general_lost_hour",

            "is_general_lost_hour":
                1,

            "date":
                str(
                    row.get(
                        "shift_date"
                    )
                    or ""
                )[:10],

            "machine":
                target_machine,

            "lost_hour_category":
                lost_hour_category,

            "reason_description":
                reason_description,

            # Keep standard reason field so existing
            # Month End logic continues to work.
            "reason":
                reason_text,

            "start_time":
                start_time,

            "end_time":
                end_time,

            "total_hours":
                total_hours,

            "location":
                delay_location,
        }


        result.setdefault(
            key,
            {
                "other_delay_reason_details": [],
            },
        )


        existing_keys = {
            (
                str(
                    existing.get(
                        "date"
                    )
                    or ""
                )[:10],

                str(
                    existing.get(
                        "reason_description"
                    )
                    or existing.get(
                        "reason"
                    )
                    or ""
                ).strip(),

                str(
                    existing.get(
                        "start_time"
                    )
                    or ""
                ),

                str(
                    existing.get(
                        "end_time"
                    )
                    or ""
                ),

                round(
                    flt(
                        existing.get(
                            "total_hours"
                        )
                    ),
                    2,
                ),

                str(
                    existing.get(
                        "location"
                    )
                    or ""
                ).strip(),
            )

            for existing
            in result[
                key
            ][
                "other_delay_reason_details"
            ]
        }


        detail_key = (
            detail[
                "date"
            ],

            detail[
                "reason_description"
            ],

            detail[
                "start_time"
            ],

            detail[
                "end_time"
            ],

            detail[
                "total_hours"
            ],

            detail[
                "location"
            ],
        )


        if detail_key not in existing_keys:

            result[
                key
            ][
                "other_delay_reason_details"
            ].append(
                detail
            )


    # ========================================================
    # MACHINE RULE
    # ========================================================

    for row in rows:

        captured_machine = str(
            row.get(
                "machine"
            )
            or ""
        ).strip()


        if not captured_machine:
            # Blank machine applies to nobody.
            continue


        if (
            captured_machine.casefold()
            ==
            "ALL Equipment".casefold()
        ):

            for asset_name in machines:

                append_reason(
                    asset_name,
                    row,
                )

        else:

            # Specific machine only.
            append_reason(
                captured_machine,
                row,
            )


    return result

# GLH_MONTH_END_MACHINE_REASON_HELPER_END

# BEGIN DIRECT AU MONTH END TOTALS

MONTH_END_CATEGORIES = [
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


def _month_end_get_filter_value(filters, *keys):
    filters = frappe._dict(filters or {})
    for key in keys:
        value = filters.get(key)
        if value not in (None, ""):
            return value
    return None


def _month_end_category_sort(category):
    return MONTH_END_CATEGORIES.index(category) if category in MONTH_END_CATEGORIES else 999


def _month_end_percent(value):
    value = flt(value)

    if value < 0:
        return 0

    if value > 100:
        return 100

    return round(value, 1)


def _month_end_calc_row(
    asset_category,
    asset_name,
    required_hrs,
    work_hrs,
    available_hrs,
    available_hrs_above_100,
    mechanical_downtime,
):
    required_hrs = flt(required_hrs)
    work_hrs = flt(work_hrs)
    available_hrs = flt(available_hrs)
    available_hrs_above_100 = flt(
        available_hrs_above_100
    )
    mechanical_downtime = flt(
        mechanical_downtime
    )

    avail_percent = _month_end_percent(
        (
            available_hrs
            / required_hrs
            * 100
        )
        if required_hrs
        else 0
    )

    util_percent = _month_end_percent(
        (
            work_hrs
            / available_hrs
            * 100
        )
        if available_hrs
        else 0
    )

    emp_avail_percent = _month_end_percent(
        (
            mechanical_downtime
            / required_hrs
            * 100
        )
        if required_hrs
        else 0
    )

    return {
        "asset_category": asset_category,
        "asset_name": asset_name or "",
        "required_hrs": round(
            required_hrs,
            1,
        ),
        "work_hrs": round(
            work_hrs,
            1,
        ),
        "available_hrs": round(
            available_hrs,
            1,
        ),
        "available_hrs_above_100": round(
            available_hrs_above_100,
            1,
        ),
        "mechanical_downtime": round(
            mechanical_downtime,
            3,
        ),
        "avail_percent": _month_end_percent(
            avail_percent
        ),
        "util_percent": _month_end_percent(
            util_percent
        ),
        "emp_avail_percent": _month_end_percent(
            emp_avail_percent
        ),
        "breakdown_reason": "",
        "other_delay_reason": "",
        "is_category_total": (
            0 if asset_name else 1
        ),
    }


def _asset_columns():
    return {row.Field for row in frappe.db.sql("SHOW COLUMNS FROM `tabAsset`", as_dict=True)}


def _asset_condition_and_values(
    categories,
    location,
    asset_ownership=None,
):
    columns = _asset_columns()
    conditions = ["asset_category in %(categories)s"]
    values = {"categories": tuple(categories)}

    if "docstatus" in columns:
        conditions.append("docstatus = 1")

    location_field = None
    for candidate in ["location", "current_location", "custodian_location"]:
        if candidate in columns:
            location_field = candidate
            break

    if location and location_field:
        conditions.append(f"{location_field} = %(location)s")
        values["location"] = location

    if asset_ownership == "Isambane & Excavo Assets":
        conditions.append(
            "("
            "asset_owner = 'Company' "
            "OR IFNULL(TRIM(asset_owner), '') = ''"
            ")"
        )
    elif asset_ownership == "Suppliers Assets":
        conditions.append(
            "asset_owner IN ('Supplier', 'Customer')"
        )

    return conditions, values

SPARE_SWING_PURPLE = "#e6d6ff"
SPARE_SWING_TEXT = "#4b0082"


def add_asset_identifiers(asset_set, asset_name):
    if not asset_name:
        return

    value = str(asset_name).strip()
    if not value:
        return

    asset_set.add(value)

    try:
        asset_doc = frappe.db.get_value("Asset", value, ["name", "asset_name"], as_dict=True)
        if asset_doc:
            if asset_doc.get("name"):
                asset_set.add(str(asset_doc.get("name")).strip())
            if asset_doc.get("asset_name"):
                asset_set.add(str(asset_doc.get("asset_name")).strip())
    except Exception:
        pass


def get_spare_swing_asset_map(filters):
    filters = frappe._dict(filters or {})

    start_date = _month_end_get_filter_value(filters, "from_date", "start_date")
    end_date = _month_end_get_filter_value(filters, "to_date", "end_date")
    location = _month_end_get_filter_value(filters, "location", "site", "production_site")

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
        identifiers = set()
        add_asset_identifiers(identifiers, asset_name)

        for identifier in identifiers:
            spare_map.setdefault(identifier, set()).add(reason)

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
        frappe.log_error(frappe.get_traceback(), "Month End Spare/Swing Trucks")
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
        frappe.log_error(frappe.get_traceback(), "Month End Spare/Swing Excavators")
        frappe.clear_messages()

    try:
        dozer_rows = frappe.db.sql(f"""
            SELECT DISTINCT dp.asset_name AS asset_name
            FROM `tabMonthly Production Planning` mpp
            INNER JOIN `tabDozers Planned` dp
                ON dp.parent = mpp.name
               AND dp.parenttype = 'Monthly Production Planning'
            WHERE {condition_sql}
              AND IFNULL(dp.asset_name, '') != ''
              AND IFNULL(dp.dozing_type, '') = ''
        """, args, as_dict=True)

        for row in dozer_rows:
            add_reason(row.get("asset_name"), "Spare/Swing unit Dozer")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Month End Spare/Swing Dozers")
        frappe.clear_messages()

    return {
        asset_name: ", ".join(sorted(reasons))
        for asset_name, reasons in spare_map.items()
    }


def is_spare_swing_asset(asset_name, spare_swing_asset_map):
    if not asset_name or not spare_swing_asset_map:
        return False

    value = str(asset_name).strip()
    if value in spare_swing_asset_map:
        return True

    identifiers = set()
    add_asset_identifiers(identifiers, value)
    return any(identifier in spare_swing_asset_map for identifier in identifiers)


def get_spare_swing_reason(asset_name, spare_swing_asset_map):
    if not asset_name or not spare_swing_asset_map:
        return ""

    value = str(asset_name).strip()
    if value in spare_swing_asset_map:
        return spare_swing_asset_map.get(value) or ""

    identifiers = set()
    add_asset_identifiers(identifiers, value)

    for identifier in identifiers:
        if identifier in spare_swing_asset_map:
            return spare_swing_asset_map.get(identifier) or ""

    return ""


def apply_spare_swing_flags(row, spare_swing_asset_map):
    reason = get_spare_swing_reason(row.get("asset_name"), spare_swing_asset_map)

    if reason:
        row["is_spare_swing_unit"] = 1
        row["spare_swing_reason"] = reason
        row["spare_swing_background"] = SPARE_SWING_PURPLE
        row["spare_swing_text_colour"] = SPARE_SWING_TEXT

    return row


def _get_submitted_assets(
    categories,
    location,
    asset_ownership=None,
):
    columns = _asset_columns()

    if "asset_category" not in columns or "name" not in columns:
        return []

    conditions, values = _asset_condition_and_values(
        categories,
        location,
        asset_ownership,
    )

    rows = frappe.db.sql(
        f"""
        SELECT
            asset_category,
            name AS asset_name
        FROM `tabAsset`
        WHERE {" AND ".join(conditions)}
        ORDER BY asset_category, name
        """,
        values,
        as_dict=True,
    )

    return rows or []


def _month_end_direct_rows(filters):
    filters = frappe._dict(filters or {})

    from_date = _month_end_get_filter_value(
        filters,
        "from_date",
        "start_date",
    )

    selected_to_date = _month_end_get_filter_value(
        filters,
        "to_date",
        "end_date",
    )

    location = _month_end_get_filter_value(
        filters,
        "location",
        "site",
        "production_site",
    )

    # Use the complete user-selected period. The A&U Engine already
    # reads every Monthly Production Planning record that overlaps it.
    # Clamping to one plan's end date can incorrectly reduce a month
    # to a single day when plans overlap or contain partial periods.
    possible_end_dates = [
        getdate(value)
        for value in [
            selected_to_date,
            nowdate(),
        ]
        if value
    ]

    to_date = (
        min(possible_end_dates)
        if possible_end_dates
        else getdate(nowdate())
    )

    filters["to_date"] = to_date
    filters["end_date"] = to_date
    selected_category = _month_end_get_filter_value(
        filters,
        "asset_category",
    )

    machine_scope = (
        _month_end_get_filter_value(
            filters,
            "machine_scope",
        )
        or "Include Swing/Spare"
    )

    asset_ownership = (
        _month_end_get_filter_value(
            filters,
            "asset_ownership",
        )
        or "Isambane & Excavo Assets"
    )

    use_true_availability = (
        filters.get("au_target_filter")
        == "85% A & U"
    )

    spare_swing_asset_map = get_spare_swing_asset_map(
        filters
    )

    categories = [selected_category] if selected_category else list(MONTH_END_CATEGORIES)

    asset_rows = _get_submitted_assets(
        categories,
        location,
        asset_ownership,
    )

    # Shared Pre Use / A&U exclusions must not enter
    # the Month End machine population.
    asset_rows = [
        row
        for row in asset_rows
        if not is_pre_use_au_excluded(
            location,
            (
                row.get("asset_name")
                if hasattr(row, "get")
                else getattr(row, "asset_name", None)
            ),
        )
    ]

    detailed_machine_scope = machine_scope

    if (
        detailed_machine_scope
        == "Production + Swing/Spare Machines"
    ):
        detailed_machine_scope = "Include Swing/Spare"

    # -----------------------------------------------------
    # Availability and Utilisation Engine is the source of
    # truth for all A&U hours and percentages.
    #
    # detailed_au remains below only for supplementary
    # employee-availability / other-delay information.
    # -----------------------------------------------------

    percentage_basis = (
        filters.get("au_target_filter")
        or filters.get("au_percentage_basis")
        or "85% A & U"
    )

    engine_filters = frappe._dict({
        "from_date": from_date,
        "to_date": to_date,
        "locations": (
            [location]
            if location
            else []
        ),
        "assets": [],
        "companies": [],
        "free_hours": 0,
        "production_machines_only": 0,
        "asset_ownership": asset_ownership,

        # Build summaries from raw Engine hours first.
        # Apply the selected basis after grouping.
        "au_percentage_basis": "100% A & U",
    })

    engine_data = (
        au_engine.get_data(
            engine_filters
        )
        or []
    )

    engine_shift_rows = [
        row
        for row in engine_data
        if isinstance(row, dict)
        and int(
            row.get("indent")
            or 0
        ) == 3
        and not row.get(
            "is_formula_row"
        )
        and row.get(
            "asset_category"
        ) in categories
    ]

    engine_rows_by_key = {}

    for row in engine_shift_rows:
        category = row.get(
            "asset_category"
        )
        asset_name = row.get(
            "asset_name"
        )

        if not category or not asset_name:
            continue

        key = (
            category,
            asset_name,
        )

        engine_rows_by_key.setdefault(
            key,
            [],
        ).append(row)

    au_by_key = {}

    for key, rows in engine_rows_by_key.items():
        category, asset_name = key

        engine_summary = (
            au_engine.build_summary_row(
                rows,
                indent=2,
                asset_category=category,
                asset_name=asset_name,
                location=location,
            )
        )

        au_engine.apply_au_percentage_basis(
            [engine_summary],
            percentage_basis,
        )

        au_by_key[key] = (
            engine_summary
        )

    # -----------------------------------------------------
    # Supplementary data only.
    # These rows are NOT used for A&U calculations.
    # -----------------------------------------------------

    summary_filters = {
        "start_date": from_date,
        "end_date": to_date,
        "location": location,
        "machine_scope": detailed_machine_scope,
        "asset_ownership": asset_ownership,
        "include_excluded_asset_categories": 1,
    }

    detailed_au_rows = (
        detailed_au.get_grouped_data(
            summary_filters
        )
        or []
    )

    other_delay_reasons_by_key = {}
    legacy_rows_by_key = {}

    machines_by_category = {
        category: set()
        for category in categories
    }

    for row in asset_rows:
        if (
            row.asset_category
            in machines_by_category
            and row.asset_name
        ):
            machines_by_category[
                row.asset_category
            ].add(
                row.asset_name
            )

    for key in engine_rows_by_key:
        category, asset_name = key

        machines_by_category.setdefault(
            category,
            set(),
        ).add(
            asset_name
        )

    for row in detailed_au_rows:
        if row.get("indent") != 2:
            continue

        category = row.get(
            "asset_category"
        )
        asset_name = row.get(
            "asset_name"
        )

        if not category or not asset_name:
            continue

        if category not in categories:
            continue

        key = (
            category,
            asset_name,
        )

        legacy_rows_by_key.setdefault(
            key,
            [],
        ).append(row)

        reason_date = (
            row.get("shift_date")
            or row.get("date")
            or row.get("posting_date")
            or ""
        )

        other_delay_reasons_by_key.setdefault(
            key,
            {
                "other_delay_reason_details": [],
            },
        )

        if row.get(
            "other_delay_reason"
        ):
            other_delay_reasons_by_key[
                key
            ][
                "other_delay_reason_details"
            ].append({
                "date": reason_date,
                "reason": row.get(
                    "other_delay_reason"
                ),
            })


    # GLH_MONTH_END_DIRECT_REASON_MERGE_START

    # --------------------------------------------------------
    # Read General Lost Hours DIRECTLY from the saved child
    # table. Do not depend only on detailed_au.get_grouped_data
    # for Other Delay popup reasons.
    # --------------------------------------------------------

    direct_general_delay_reasons = (
        get_general_lost_hour_machine_reason_details(
            filters,
            asset_rows,
            categories,
        )
    )


    for (
        key,
        direct_reason_row,
    ) in direct_general_delay_reasons.items():

        target = (
            other_delay_reasons_by_key.setdefault(
                key,
                {
                    "other_delay_reason_details": [],
                },
            )
        )


        existing = {
            (
                str(
                    detail.get(
                        "date"
                    )
                    or ""
                )[:10],

                str(
                    detail.get(
                        "reason"
                    )
                    or ""
                ).strip(),
            )
            for detail
            in target.get(
                "other_delay_reason_details"
            )
            or []
        }


        for detail in (
            direct_reason_row.get(
                "other_delay_reason_details"
            )
            or []
        ):

            detail_key = (
                str(
                    detail.get(
                        "date"
                    )
                    or ""
                )[:10],

                str(
                    detail.get(
                        "reason"
                    )
                    or ""
                ).strip(),
            )


            if detail_key in existing:
                continue


            target[
                "other_delay_reason_details"
            ].append(
                detail
            )


            existing.add(
                detail_key
            )

    # GLH_MONTH_END_DIRECT_REASON_MERGE_END

    employee_availability_by_key = {}

    for key, rows in (
        legacy_rows_by_key.items()
    ):
        category, asset_name = key

        legacy_summary = (
            detailed_au.summary_row(
                rows,
                indent=2,
                asset_category=category,
                asset_name=asset_name,
                location=location,
            )
        )

        employee_availability_by_key[
            key
        ] = legacy_summary.get(
            "employee_availability"
        )


    all_asset_names = sorted({
        asset_name
        for asset_names in machines_by_category.values()
        for asset_name in asset_names
        if asset_name
    })

    plant_breakdown_details_by_asset = get_plant_breakdown_reason_details(filters, all_asset_names)

    output = []

    for category in categories:
        machine_rows = []

        for asset_name in sorted(machines_by_category.get(category) or []):

            # Final shared machine exclusion for Month End.
            if is_pre_use_au_excluded(
                location,
                asset_name,
            ):
                continue

            is_spare = is_spare_swing_asset(asset_name, spare_swing_asset_map)

            if machine_scope == "Production Machines" and is_spare:
                continue

            if machine_scope == "Swing/Spare Machines" and not is_spare:
                continue

            au_row = au_by_key.get((category, asset_name))

            breakdown_details = clean_reason_details(
                plant_breakdown_details_by_asset.get(asset_name) or []
            )

            if au_row:
                machine_row = _month_end_calc_row(
                    category,
                    asset_name,
                    au_row.get(
                        "required_hours"
                    ),
                    au_row.get(
                        "work_hours"
                    ),
                    au_row.get(
                        "utilisation_available_hours"
                    ),
                    au_row.get(
                        "availability_available_hours"
                    ),
                    au_row.get(
                        "pbm_total_downtime"
                    ),
                )

                # Percentages are copied directly from
                # Availability and Utilisation Engine.
                machine_row["avail_percent"] = (
                    au_row.get(
                        "availability_percentage"
                    )
                )

                machine_row["util_percent"] = (
                    au_row.get(
                        "utilisation_percentage"
                    )
                )

                # Employee Availability is supplementary
                # and is not currently exposed by Engine.
                machine_row[
                    "emp_avail_percent"
                ] = (
                    employee_availability_by_key.get(
                        (
                            category,
                            asset_name,
                        )
                    )
                )

                machine_row["_au_source_row"] = (
                    au_row
                )

                machine_row["_au_source_rows"] = (
                    engine_rows_by_key.get(
                        (
                            category,
                            asset_name,
                        ),
                        [],
                    )
                )

                reason_row = (
                    other_delay_reasons_by_key.get(
                        (
                            category,
                            asset_name,
                        ),
                        {},
                    )
                )

                other_delay_details = clean_reason_details(reason_row.get("other_delay_reason_details") or [])

                machine_row["breakdown_reason_details"] = breakdown_details
                machine_row["other_delay_reason_details"] = other_delay_details

                machine_row["breakdown_reason"] = "\n".join([d.get("reason") for d in breakdown_details])
                machine_row["other_delay_reason"] = "\n".join([d.get("reason") for d in other_delay_details])
            else:
                machine_row = _month_end_calc_row(
                    category,
                    asset_name,
                    0,
                    0,
                    0,
                    0,
                    0,
                )


                machine_row["breakdown_reason_details"] = breakdown_details
                machine_row["other_delay_reason_details"] = []
                machine_row["breakdown_reason"] = "\n".join([d.get("reason") for d in breakdown_details])


            # GLH_MONTH_END_FINAL_REASON_ASSIGN_START

            # Always assign Other Delay reasons after both
            # machine-row branches.
            #
            # This prevents a valid General Lost Hour reason
            # from being cleared when the machine has no
            # legacy AU source row.

            final_reason_row = (
                other_delay_reasons_by_key.get(
                    (
                        category,
                        asset_name,
                    ),
                    {},
                )
            )


            final_other_delay_details = (
                clean_reason_details(
                    final_reason_row.get(
                        "other_delay_reason_details"
                    )
                    or []
                )
            )


            machine_row[
                "other_delay_reason_details"
            ] = final_other_delay_details


            machine_row[
                "other_delay_reason"
            ] = "\n".join(
                [
                    detail.get(
                        "reason"
                    )
                    for detail
                    in final_other_delay_details
                    if detail.get(
                        "reason"
                    )
                ]
            )

            # GLH_MONTH_END_FINAL_REASON_ASSIGN_END

            machine_rows.append(apply_spare_swing_flags(machine_row, spare_swing_asset_map))

        if not machine_rows:
            continue

        production_machine_rows = [
            row
            for row in machine_rows
            if not row.get(
                "is_spare_swing_unit"
            )
        ]

        spare_machine_rows = [
            row
            for row in machine_rows
            if row.get(
                "is_spare_swing_unit"
            )
        ]

        def build_scope_total_row(
            scope_rows,
            summary_scope,
            summary_label,
        ):
            source_rows = [
                source_row
                for machine_row in scope_rows
                for source_row in (
                    machine_row.get(
                        "_au_source_rows"
                    )
                    or []
                )
            ]

            if source_rows:
                au_scope_row = (
                    au_engine.build_summary_row(
                        source_rows,
                        indent=0,
                        asset_category=category,
                        location=location,
                    )
                )

                au_engine.apply_au_percentage_basis(
                    [au_scope_row],
                    percentage_basis,
                )

                scope_row = _month_end_calc_row(
                    category,
                    "",
                    au_scope_row.get(
                        "required_hours"
                    ),
                    au_scope_row.get(
                        "work_hours"
                    ),
                    au_scope_row.get(
                        "utilisation_available_hours"
                    ),
                    au_scope_row.get(
                        "availability_available_hours"
                    ),
                    au_scope_row.get(
                        "pbm_total_downtime"
                    ),
                )

                scope_row["avail_percent"] = (
                    au_scope_row.get(
                        "availability_percentage"
                    )
                )

                scope_row["util_percent"] = (
                    au_scope_row.get(
                        "utilisation_percentage"
                    )
                )

                # Keep the existing Employee Availability
                # aggregation because Engine does not
                # currently expose this percentage.
                emp_values = [
                    row.get(
                        "emp_avail_percent"
                    )
                    for row in scope_rows
                    if row.get(
                        "emp_avail_percent"
                    ) is not None
                ]

                scope_row[
                    "emp_avail_percent"
                ] = (
                    round(
                        sum(
                            flt(value)
                            for value in emp_values
                        )
                        / len(emp_values),
                        1,
                    )
                    if emp_values
                    else None
                )
            else:
                scope_row = _month_end_calc_row(
                    category,
                    "",
                    0,
                    0,
                    0,
                    0,
                    0,
                )

            scope_row["summary_scope"] = (
                summary_scope
            )

            scope_row["summary_label"] = (
                summary_label
            )

            scope_row["is_scope_total"] = 1

            if summary_scope == "spare":
                scope_row[
                    "is_spare_scope_total"
                ] = 1

            return scope_row

        overall_row = build_scope_total_row(
            machine_rows,
            "overall",
            f"{category} - Overall Total",
        )

        production_row = build_scope_total_row(
            production_machine_rows,
            "production",
            f"{category} - Production Machines",
        )

        spare_row = build_scope_total_row(
            spare_machine_rows,
            "spare",
            f"{category} - Swing/Spare Machines",
        )

        output.append(overall_row)

        if production_machine_rows:
            output.append(production_row)
            output.extend(production_machine_rows)

        if spare_machine_rows:
            output.append(spare_row)
            output.extend(spare_machine_rows)

    return output


def get_data(filters):
    return _month_end_direct_rows(filters)

# END DIRECT AU MONTH END TOTALS

# GLH_DIRECT_POPUP_API_START

@frappe.whitelist()
def get_general_lost_hour_popup_rows(
    asset_name,
    from_date=None,
    to_date=None,
    location=None,
):
    """
    Return General Lost Hours popup rows directly from capture.

    Rules:
    - Specific machine = that machine only
    - ALL Equipment = applies to every machine
    - Blank machine = ignored
    """

    asset_name = str(
        asset_name or ""
    ).strip()


    if not asset_name:
        return []


    if not from_date:
        from_date = "1900-01-01"


    if not to_date:
        to_date = "2999-12-31"


    conditions = [
        "r.shift_date BETWEEN %(from_date)s AND %(to_date)s",
        (
            "("
            "TRIM(g.machine) = %(asset_name)s "
            "OR LOWER(TRIM(g.machine)) = 'all equipment'"
            ")"
        ),
    ]


    values = {
        "asset_name": asset_name,
        "from_date": from_date,
        "to_date": to_date,
    }


    if location:

        conditions.append(
            "r.location = %(location)s"
        )

        values[
            "location"
        ] = location


    rows = frappe.db.sql(
        f"""
        SELECT
            r.shift_date,
            r.shift,

            g.machine,
            g.lost_hour_category,
            g.reason_description,
            g.start_time,
            g.end_time,
            g.total_hours,
            g.location AS delay_location

        FROM `tabDaily Lost Hours Recon` r

        INNER JOIN `tabDaily General Lost Hours` g
            ON g.parent = r.name

        WHERE
            {" AND ".join(conditions)}

        ORDER BY
            r.shift_date ASC,
            g.start_time ASC,
            g.idx ASC
        """,
        values,
        as_dict=True,
    )


    result = []


    def clean_time(value):

        if value is None:
            return ""

        value = str(
            value
        ).strip()

        if "." in value:
            value = value.split(
                ".",
                1,
            )[0]

        parts = value.split(
            ":"
        )

        if (
            len(parts) >= 2
            and len(parts[0]) == 1
        ):
            value = "0" + value

        return value


    for row in rows:

        result.append({
            "date":
                str(
                    row.shift_date
                    or ""
                )[:10],

            "shift":
                row.shift or "",

            "machine":
                row.machine or "",

            "lost_hour_category":
                row.lost_hour_category or "",

            "reason_description":
                row.reason_description or "",

            "start_time":
                clean_time(
                    row.start_time
                ),

            "end_time":
                clean_time(
                    row.end_time
                ),

            "total_hours":
                round(
                    flt(
                        row.total_hours
                    ),
                    2,
                ),

            "location":
                row.delay_location or "",
        })


    return result

# GLH_DIRECT_POPUP_API_END

# MONTH_END_PLANNED_REASON_SPLIT_START


def get_month_end_pbm_reason_details_by_type(
    filters,
    asset_names,
    downtime_type,
):
    """
    Return Month End PBM detail rows for one downtime type.

    Used only for reason display/export.

    downtime_type:
        Breakdown
        Planned Maintenance

    IMPORTANT:
        This does not change any Month End A&U calculations.
    """

    from datetime import timedelta

    from frappe.utils import (
        getdate,
        get_datetime,
    )


    if not asset_names:
        return {}


    if not frappe.db.exists(
        "DocType",
        "Plant Breakdown or Maintenance",
    ):
        return {}


    filters = frappe._dict(
        filters or {}
    )


    from_date = _month_end_get_filter_value(
        filters,
        "from_date",
        "start_date",
    )


    to_date = _month_end_get_filter_value(
        filters,
        "to_date",
        "end_date",
    )


    location = _month_end_get_filter_value(
        filters,
        "location",
        "site",
        "production_site",
    )


    if not from_date or not to_date:
        return {}


    # ========================================================
    # MONTH END OPERATIONAL WINDOW
    #
    # From date 06:00
    # through day after To date 06:00.
    # ========================================================

    report_start = get_datetime(
        f"{getdate(from_date)} 06:00:00"
    )


    report_end_date = (
        getdate(to_date)
        + timedelta(
            days=1
        )
    )


    report_end = get_datetime(
        f"{report_end_date} 06:00:00"
    )


    values = {
        "from_datetime":
            report_start,

        "to_datetime":
            report_end,

        "asset_names":
            tuple(
                asset_names
            ),

        "downtime_type":
            downtime_type,

        "plant_breakdown_trust_datetime":
            "2026-01-01 00:00:00",
    }


    conditions = [
        (
            "IFNULL(asset_name, '') != ''"
        ),
        (
            "IFNULL(breakdown_reason, '') != ''"
        ),
        (
            "IFNULL(exclude_from_au, 0) = 0"
        ),
        (
            "asset_name IN %(asset_names)s"
        ),
        (
            "LOWER(TRIM(IFNULL(downtime_type, ''))) "
            "= LOWER(%(downtime_type)s)"
        ),
        (
            "breakdown_start_datetime >= "
            "%(plant_breakdown_trust_datetime)s"
        ),
        (
            "breakdown_start_datetime <= "
            "%(to_datetime)s"
        ),
        (
            "("
            "resolved_datetime >= %(from_datetime)s "
            "OR resolved_datetime IS NULL"
            ")"
        ),
    ]


    if location:

        conditions.append(
            "location = %(location)s"
        )

        values[
            "location"
        ] = location


    rows = frappe.db.sql(
        f"""
        SELECT
            asset_name,
            location,
            downtime_type,
            breakdown_start_datetime,
            resolved_datetime,
            breakdown_reason

        FROM `tabPlant Breakdown or Maintenance`

        WHERE
            {" AND ".join(conditions)}

        ORDER BY
            asset_name ASC,
            breakdown_start_datetime ASC
        """,
        values,
        as_dict=True,
    )


    details_by_asset = {}

    seen_intervals = set()


    for row in rows:

        start_datetime = row.get(
            "breakdown_start_datetime"
        )


        resolved_datetime = row.get(
            "resolved_datetime"
        )


        if not start_datetime:
            continue


        start_dt = get_datetime(
            start_datetime
        )


        end_dt = (
            get_datetime(
                resolved_datetime
            )
            if resolved_datetime
            else report_end
        )


        # Clip to selected report range.
        clipped_start = max(
            start_dt,
            report_start,
        )


        clipped_end = min(
            end_dt,
            report_end,
        )


        if clipped_end <= clipped_start:
            continue


        interval_key = (
            row.get(
                "asset_name"
            ),

            row.get(
                "location"
            ),

            row.get(
                "downtime_type"
            ),

            str(
                clipped_start
            ),

            str(
                clipped_end
            ),

            row.get(
                "breakdown_reason"
            ),
        )


        if interval_key in seen_intervals:
            continue


        seen_intervals.add(
            interval_key
        )


        row_filters = frappe._dict(
            filters.copy()
        )


        row_filters[
            "location"
        ] = row.get(
            "location"
        )


        # ====================================================
        # SPLIT LONG PBM RECORD INTO OPERATIONAL DAYS
        #
        # This matches the current Month End popup structure.
        # ====================================================

        current_date = getdate(
            clipped_start
        )


        current_day_start = get_datetime(
            f"{current_date} 06:00:00"
        )


        if clipped_start < current_day_start:

            current_date = (
                current_date
                - timedelta(
                    days=1
                )
            )


        while True:

            day_start = get_datetime(
                f"{current_date} 06:00:00"
            )


            day_end = (
                day_start
                + timedelta(
                    days=1
                )
            )


            if day_start >= clipped_end:
                break


            segment_start = max(
                clipped_start,
                day_start,
            )


            segment_end = min(
                clipped_end,
                day_end,
            )


            if segment_end > segment_start:

                # Reuse exactly the same A&U exclusion calculation
                # currently used by the Month End breakdown popup.
                required_downtime = (
                    get_required_downtime_minutes_for_breakdown(
                        row_filters,
                        row.get(
                            "asset_name"
                        ),
                        segment_start,
                        segment_end,
                    )
                )


                details_by_asset.setdefault(
                    row.get(
                        "asset_name"
                    ),
                    [],
                ).append({

                    "date":
                        str(
                            current_date
                        ),

                    "start_datetime":
                        segment_start,

                    "resolved_datetime":
                        segment_end,

                    "total_minutes":
                        required_downtime[
                            "total_minutes"
                        ],

                    "startup_fatigue_minutes":
                        required_downtime[
                            "excluded_minutes"
                        ],

                    "sunday_minutes":
                        required_downtime[
                            "sunday_minutes"
                        ],

                    "au_minutes":
                        required_downtime[
                            "required_downtime_minutes"
                        ],

                    "reason":
                        row.get(
                            "breakdown_reason"
                        ),

                    "downtime_type":
                        row.get(
                            "downtime_type"
                        ),
                })


            current_date = (
                current_date
                + timedelta(
                    days=1
                )
            )


    return details_by_asset


def _month_end_add_planned_reason_column(
    columns,
):
    """
    Insert Planned Maintenance Reason directly after
    Breakdown Reason.
    """

    if not columns:
        return


    existing = {
        column.get(
            "fieldname"
        )
        for column in columns
        if isinstance(
            column,
            dict,
        )
    }


    if (
        "planned_maintenance_reason"
        in existing
    ):
        return


    new_column = {
        "label":
            _("Planned Maintenance Reason"),

        "fieldname":
            "planned_maintenance_reason",

        "fieldtype":
            "Data",

        "width":
            175,
    }


    for index, column in enumerate(
        columns
    ):

        if (
            isinstance(
                column,
                dict,
            )
            and column.get(
                "fieldname"
            )
            == "breakdown_reason"
        ):

            columns.insert(
                index + 1,
                new_column,
            )

            return


    # Fallback: place before Other Delay Reason.
    for index, column in enumerate(
        columns
    ):

        if (
            isinstance(
                column,
                dict,
            )
            and column.get(
                "fieldname"
            )
            == "other_delay_reason"
        ):

            columns.insert(
                index,
                new_column,
            )

            return


    columns.append(
        new_column
    )


def _month_end_split_pbm_reasons(
    data,
    filters,
):
    """
    Separate PBM reasons into:

        Breakdown Reason
        Planned Maintenance Reason

    This is deliberately performed AFTER the existing report
    calculations, so Mechanical Downtime, Required Hours,
    Availability and Utilisation are not recalculated.
    """

    if not data:
        return


    asset_names = sorted({
        str(
            row.get(
                "asset_name"
            )
            or ""
        ).strip()

        for row in data

        if (
            isinstance(
                row,
                dict,
            )
            and row.get(
                "asset_name"
            )
        )
    })


    if not asset_names:
        return


    breakdown_map = (
        get_month_end_pbm_reason_details_by_type(
            filters,
            asset_names,
            "Breakdown",
        )
    )


    planned_map = (
        get_month_end_pbm_reason_details_by_type(
            filters,
            asset_names,
            "Planned Maintenance",
        )
    )


    for row in data:

        if not isinstance(
            row,
            dict,
        ):
            continue


        asset_name = str(
            row.get(
                "asset_name"
            )
            or ""
        ).strip()


        # Category / scope total rows stay blank.
        if not asset_name:

            row[
                "planned_maintenance_reason"
            ] = ""

            row[
                "planned_maintenance_reason_details"
            ] = []

            continue


        breakdown_details = clean_reason_details(
            breakdown_map.get(
                asset_name
            )
            or []
        )


        planned_details = clean_reason_details(
            planned_map.get(
                asset_name
            )
            or []
        )


        # ====================================================
        # BREAKDOWN ONLY
        # ====================================================

        row[
            "breakdown_reason_details"
        ] = breakdown_details


        row[
            "breakdown_reason"
        ] = "\n".join(
            [
                detail.get(
                    "reason"
                )
                for detail
                in breakdown_details
                if detail.get(
                    "reason"
                )
            ]
        )


        # ====================================================
        # PLANNED MAINTENANCE ONLY
        # ====================================================

        row[
            "planned_maintenance_reason_details"
        ] = planned_details


        row[
            "planned_maintenance_reason"
        ] = "\n".join(
            [
                detail.get(
                    "reason"
                )
                for detail
                in planned_details
                if detail.get(
                    "reason"
                )
            ]
        )


# ------------------------------------------------------------
# WRAP EXISTING EXECUTE
#
# Existing Month End calculations happen FIRST.
# We modify reason display/export only afterwards.
# ------------------------------------------------------------

_month_end_execute_before_pbm_reason_split = execute


def execute(filters=None):

    result = (
        _month_end_execute_before_pbm_reason_split(
            filters
        )
    )


    if not result:
        return result


    if (
        not isinstance(
            result,
            (tuple, list),
        )
        or len(result) < 2
    ):
        return result


    columns = result[0]

    data = result[1]


    _month_end_add_planned_reason_column(
        columns
    )


    _month_end_split_pbm_reasons(
        data,
        filters,
    )


    if isinstance(
        result,
        tuple,
    ):

        return (
            columns,
            data,
            *result[2:],
        )


    result = list(
        result
    )

    result[0] = columns

    result[1] = data

    return result


# MONTH_END_PLANNED_REASON_SPLIT_END


# ============================================================
# MONTH END IS538 DUPLICATE CLEANUP
#
# IS538 can enter the Month End machine population under more
# than one source identifier. Only one machine row must be
# displayed. If duplicates exist, retain the row containing
# the most meaningful A&U values.
# ============================================================

_month_end_execute_before_is538_dedupe = execute


def _month_end_is538_score(row):
    """
    Rank duplicate IS538 rows.

    Always prefer the row created from the
    Availability and Utilisation Engine.
    """

    if not hasattr(row, "get"):
        return (-1, -1, -1)

    def number(fieldname):
        try:
            return float(
                row.get(fieldname)
                or 0
            )
        except Exception:
            return 0.0

    has_engine_source = bool(
        row.get("_au_source_row")
    )

    work_hours = number(
        "work_hrs"
    )

    required_hours = number(
        "required_hrs"
    )

    return (
        1 if has_engine_source else 0,
        work_hours,
        required_hours,
    )


def _month_end_remove_duplicate_is538(rows):
    if not rows:
        return rows

    target_indexes = []

    for index, row in enumerate(rows):
        if not hasattr(row, "get"):
            continue

        asset_name = "".join(
            str(
                row.get("asset_name")
                or ""
            )
            .strip()
            .upper()
            .split()
        )

        # Only individual IS538 machine rows.
        if (
            asset_name == "IS538"
            and row.get("asset_name")
        ):
            target_indexes.append(index)

    if len(target_indexes) <= 1:
        return rows

    keep_index = max(
        target_indexes,
        key=lambda index: _month_end_is538_score(
            rows[index]
        ),
    )

    return [
        row
        for index, row in enumerate(rows)
        if (
            index == keep_index
            or index not in target_indexes
        )
    ]


def execute(filters=None):
    result = _month_end_execute_before_is538_dedupe(
        filters
    )

    if not result:
        return result

    # Standard Script Report:
    # (columns, data, ...)
    if isinstance(result, tuple):
        result = list(result)

        if len(result) > 1:
            result[1] = (
                _month_end_remove_duplicate_is538(
                    result[1]
                )
            )

        return tuple(result)

    # Defensive support if this report returns a list.
    if isinstance(result, list):
        return _month_end_remove_duplicate_is538(
            result
        )

    return result
