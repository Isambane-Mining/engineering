# availability_and_utilisation.py
# Drop-in replacement (safe import, worker-safe, no Pre-Use changes required)

import logging

import frappe
from frappe.utils import (
    flt,
    getdate,
    add_days,
    today,
    formatdate,
    get_first_day,
    get_last_day,
    time_diff_in_hours,
    get_datetime,
    now_datetime,
)
from datetime import timedelta
from frappe.model.document import Document


# =============================================================================
# Helpers (IMPORT-SAFE)
# =============================================================================

def _safe_flag(name: str) -> bool:
    """Avoid AttributeError on older/newer frappe flags."""
    try:
        return bool(getattr(frappe.flags, name, False))
    except Exception:
        return False


def _get_doc_asset_item_name(doc_name):
    """Safely retrieve asset_name and item_name from an existing AU doc."""
    try:
        d = frappe.get_doc("Availability and Utilisation", doc_name)
        return (d.asset_name or "Unknown", d.item_name or "Unknown")
    except Exception:
        return ("Unknown", "Unknown")


def _preuse_docname_from_au(doc):
    """
    Pre-Use Hours autoname is: format:{location}-{shift_date}-{shift}
    and shift_date is stored as YYYY-MM-DD.
    """
    sd = getdate(doc.shift_date).strftime("%Y-%m-%d")
    return f"{doc.location}-{sd}-{doc.shift}"


def _get_preuse_doc_for_au(doc):
    """
    Return a Pre-Use Hours doc matched for this AU doc WITHOUT requiring
    Pre-Use changes. Tries:
      1) Pre-Use Hours.avail_util_lookup == AU.pre_use_lookup
      2) Pre-Use Hours.name == {location}-{YYYY-MM-DD}-{shift} (autoname)
      3) Fallback search by location+shift_date+shift
    """
    # 1) Best: avail_util_lookup (if it exists and is populated)
    if getattr(doc, "pre_use_lookup", None):
        try:
            hit = frappe.get_all(
                "Pre-Use Hours",
                filters={"avail_util_lookup": doc.pre_use_lookup},
                fields=["name"],
                limit=1,
            )
            if hit:
                return frappe.get_doc("Pre-Use Hours", hit[0].name)
        except Exception:
            # Field may not exist on some sites; ignore and continue
            pass

    # 2) Autoname match
    name_guess = _preuse_docname_from_au(doc)
    if frappe.db.exists("Pre-Use Hours", name_guess):
        return frappe.get_doc("Pre-Use Hours", name_guess)

    # 3) Fallback filter match (handles renamed records / legacy)
    try:
        hit = frappe.get_all(
            "Pre-Use Hours",
            filters={
                "location": doc.location,
                "shift_date": doc.shift_date,
                "shift": doc.shift,
            },
            fields=["name"],
            limit=1,
        )
        if hit:
            return frappe.get_doc("Pre-Use Hours", hit[0].name)
    except Exception:
        pass

    return None


def _preuse_row_plant_no(preuse_row):
    """
    Pre-Use child row:
      - row.asset_name is Link -> Asset (stores Asset.name)
      - row.plant_no (Data) may exist and may be filled by JS
    We need Plant No (Asset.asset_name) to match AU.asset_name.
    """
    # Prefer plant_no if present and populated
    plant_no = getattr(preuse_row, "plant_no", None)
    if plant_no:
        return plant_no

    asset_link = getattr(preuse_row, "asset_name", None)
    if not asset_link:
        return None

    # asset_link is Asset.name
    try:
        return frappe.db.get_value("Asset", asset_link, "asset_name")
    except Exception:
        return None


def get_shift_timings(shift_system, shift, shift_date):
    """Calculate shift start and end timings based on the system and shift."""
    shift_start = None
    shift_end = None

    if shift_system == "3x8Hour":
        if shift == "Morning":
            shift_start = get_datetime(shift_date + " 06:00:00")
            shift_end = get_datetime(shift_date + " 14:00:00")
        elif shift == "Afternoon":
            shift_start = get_datetime(shift_date + " 14:00:00")
            shift_end = get_datetime(shift_date + " 22:00:00")
        elif shift == "Night":
            shift_start = get_datetime(shift_date + " 22:00:00")
            next_day = (getdate(shift_date) + timedelta(days=1)).strftime("%Y-%m-%d")
            shift_end = get_datetime(next_day + " 06:00:00")

    elif shift_system == "2x12Hour":
        if shift == "Day":
            shift_start = get_datetime(shift_date + " 06:00:00")
            shift_end = get_datetime(shift_date + " 18:00:00")
        elif shift == "Night":
            shift_start = get_datetime(shift_date + " 18:00:00")
            next_day = (getdate(shift_date) + timedelta(days=1)).strftime("%Y-%m-%d")
            shift_end = get_datetime(next_day + " 06:00:00")

    return shift_start, shift_end



def _shift_length_hours(shift_system) -> float:
    """Max hours one shift can last: 8 for 3x8Hour, otherwise 12 (2x12Hour / unknown)."""
    return 8.0 if (shift_system or "").strip().lower() == "3x8hour" else 12.0


def _working_hours_from_engine_hours(doc):
    """
    Working hours = end - start engine hours, rejected when impossible.

    A missing start reading (captured as 0) turns end - start into the whole hour
    meter (e.g. 0 -> 6414 = 6414h in one shift). Anything above the shift length
    is treated as bad Pre-Use data: working hours are set to 0 and a message is
    returned so the caller can report it as an error. Returns (hours, problem).
    """
    if doc.shift_start_hours is None or doc.shift_end_hours is None:
        return 0, None

    hours = max(0, flt(doc.shift_end_hours) - flt(doc.shift_start_hours))
    max_hours = _shift_length_hours(doc.shift_system)
    if hours > max_hours:
        return 0, (
            f"engine hours {doc.shift_start_hours} -> {doc.shift_end_hours} give {hours:g}h, "
            f"more than the {max_hours:g}h shift; working hours set to 0. "
            f"Fix the start/end reading on Pre-Use Hours {doc.pre_use_link} for Plant No={doc.asset_name}"
        )
    return hours, None


def _overlap_hours(a_start, a_end, b_start, b_end) -> float:
    """Return overlap in hours between [a_start,a_end] and [b_start,b_end]."""
    s = max(a_start, b_start)
    e = min(a_end, b_end)
    if e <= s:
        return 0.0
    return float(time_diff_in_hours(e, s))


def _exclusion_windows(
    location: str,
    shift: str,
    shift_start,
    shift_end,
):
    shift_date = getdate(
        shift_start
    )

    if shift_date.weekday() == 5:
        day_type = "Saturday"
    elif shift_date.weekday() == 6:
        day_type = "Sunday"
    else:
        day_type = "Weekday"

    configuration_fields = [
        "startup_start",
        "startup_end",
        "fatigue_start",
        "fatigue_end",
    ]

    # First preference:
    # use an explicit day-type configuration when one exists.
    configuration = frappe.db.get_value(
        "Startup and Fatigue spesification",
        {
            "site": location,
            "shift": shift,
            "day_type": day_type,
        },
        configuration_fields,
        as_dict=True,
    )

    # Backward compatibility:
    # historically there was only one configuration per site + shift.
    #
    # If there is exactly one such row, use it as the generic
    # configuration for Weekday / Saturday / Sunday.
    #
    # If multiple rows exist, do not choose one arbitrarily because
    # the site is then using day-specific rules.
    if not configuration:
        legacy_configurations = frappe.get_all(
            "Startup and Fatigue spesification",
            filters={
                "site": location,
                "shift": shift,
            },
            fields=configuration_fields,
            limit=2,
        )

        if len(legacy_configurations) == 1:
            configuration = frappe._dict(
                legacy_configurations[0]
            )

    if not configuration:
        frappe.log_error(
            title=(
                "Missing Startup and Fatigue "
                "specification"
            ),
            message=(
                "No configuration found for "
                f"{location}-{shift}-{day_type}"
            ),
        )
        return []

    def time_text(value):
        if isinstance(
            value,
            timedelta,
        ):
            seconds = (
                int(
                    value.total_seconds()
                )
                % 86400
            )

            hours, remainder = divmod(
                seconds,
                3600,
            )

            minutes, seconds = divmod(
                remainder,
                60,
            )

            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )

        return str(
            value
        ).split(".")[0]

    def build_windows(
        start_time,
        end_time,
    ):
        windows = []

        start_time = time_text(
            start_time
        )

        end_time = time_text(
            end_time
        )

        base_date = getdate(
            shift_start
        )

        for day_offset in (
            0,
            1,
        ):
            window_date = add_days(
                base_date,
                day_offset,
            )

            window_start = get_datetime(
                f"{window_date} "
                f"{start_time}"
            )

            window_end_date = (
                window_date
            )

            if end_time <= start_time:
                window_end_date = add_days(
                    window_date,
                    1,
                )

            window_end = get_datetime(
                f"{window_end_date} "
                f"{end_time}"
            )

            if (
                window_end <= shift_start
                or window_start >= shift_end
            ):
                continue

            windows.append(
                (
                    max(
                        window_start,
                        shift_start,
                    ),
                    min(
                        window_end,
                        shift_end,
                    ),
                )
            )

        return windows

    windows = []

    # Startup exclusion.
    windows.extend(
        build_windows(
            configuration.startup_start,
            configuration.startup_end,
        )
    )

    # Fatigue exclusion.
    windows.extend(
        build_windows(
            configuration.fatigue_start,
            configuration.fatigue_end,
        )
    )

    return windows

# =============================================================================
# Main DocType
# =============================================================================

class AvailabilityandUtilisation(Document):
    @staticmethod
    def generate_records():
        # Prevent execution during migration or app install
        if _safe_flag("in_migrate") or _safe_flag("in_install_app"):
            frappe.logger().info("Skipped generate_records during migrate/install")
            return

        process_started_at = now_datetime()
        created_records = []
        updated_records = []
        error_records = []
        record_logs = {}  # aggregated per record

        def append_log(record_key, message):
            record_logs.setdefault(record_key, []).append(message)

        current_date = getdate(today())

        # =============================================================================
        # Phase 1: Create or Update AU docs (last 7 days)
        # =============================================================================
        start_date = current_date - timedelta(days=7)
        end_date = current_date

        production_planning_records = frappe.get_all(
            "Monthly Production Planning",
            filters={
                "site_status": "Producing",
                "prod_month_start_date": ["<=", end_date],
                "prod_month_end_date": [">=", start_date],
            },
            fields=["location", "prod_month_start_date", "prod_month_end_date", "shift_system"],
            order_by="prod_month_start_date asc",
        )

        date = start_date
        while date <= end_date:
            for planning_record in production_planning_records:
                location = planning_record.location
                shift_system = (planning_record.shift_system or "").strip()
                prod_month_start_date = planning_record.prod_month_start_date
                prod_month_end_date = planning_record.prod_month_end_date

                if not (getdate(date) >= getdate(prod_month_start_date) and getdate(date) <= getdate(prod_month_end_date)):
                    continue

                assets = frappe.get_all(
                    "Asset",
                    filters={
                        "location": location,
                        "asset_category": [
            "in",
            [
                "Dozer",
                "ADT",
                "Rigid",
                "Excavator",
                "Grader",
                "Service Truck",
                "TLB",
                "Water Bowser",
                "Diesel Bowsers",
                "Drills",
            ],
        ],
                        "docstatus": 1,
                    },
                    fields=["name", "asset_name", "item_name", "asset_category"],
                )

                shifts = ["Day", "Night"] if shift_system.lower() == "2x12hour" else ["Morning", "Afternoon", "Night"]

                for shift in shifts:
                    for asset in assets:
                        record_key = f"{location}-{asset.asset_name}-{date}-{shift}"
                        try:
                            existing_record = frappe.get_all(
                                "Availability and Utilisation",
                                filters={
                                    "shift_date": date,
                                    "location": location,
                                    "shift": shift,
                                    "asset_name": asset.asset_name,  # AU stores Plant No in asset_name
                                },
                                fields=["name"],
                                limit=1,
                            )

                            if existing_record:
                                doc = frappe.get_doc("Availability and Utilisation", existing_record[0].name)
                                doc.pre_use_lookup = None
                                doc.pre_use_link = None
                                doc.save(ignore_permissions=True)

                                doc.db_set("day_number", getdate(date).day, update_modified=True)
                                doc.db_set("asset_category", asset.asset_category, update_modified=True)

                                updated_records.append(doc.name)
                                append_log(
                                    doc.name,
                                    (
                                        f"Phase 1: Updated record={doc.name}, shift={shift}, date={date}, "
                                        f"asset_name={doc.asset_name}, item_name={doc.item_name}, "
                                        f"day_number={getdate(date).day}, asset_category={asset.asset_category}"
                                    ),
                                )
                            else:
                                doc = frappe.get_doc(
                                    {
                                        "doctype": "Availability and Utilisation",
                                        "shift_date": date,
                                        "shift": shift,
                                        "asset_name": asset.asset_name,  # Plant No
                                        "location": location,
                                        "shift_system": shift_system,
                                        "pre_use_lookup": None,
                                        "pre_use_link": None,
                                    }
                                )
                                doc.insert(ignore_permissions=True)

                                doc.db_set("day_number", getdate(date).day, update_modified=True)
                                doc.db_set("asset_category", asset.asset_category, update_modified=True)

                                created_records.append(doc.name)
                                append_log(
                                    doc.name,
                                    (
                                        f"Phase 1: Created record={doc.name}, shift={shift}, date={date}, "
                                        f"asset_name={doc.asset_name}, item_name={doc.item_name}, "
                                        f"day_number={getdate(date).day}, asset_category={asset.asset_category}"
                                    ),
                                )
                        except Exception as e:
                            err_msg = (
                                f"Phase 1 Error: asset_name={asset.asset_name}, item_name={asset.item_name}, "
                                f"location={location}, date={date}, shift={shift}: {str(e)}"
                            )
                            append_log(record_key, err_msg)
                            error_records.append(err_msg)

            date = add_days(date, 1)

        # =============================================================================
        # Phase 2: Update pre_use_lookup field
        # =============================================================================
        for doc_name in created_records + updated_records:
            try:
                doc = frappe.get_doc("Availability and Utilisation", doc_name)
                formatted_date = formatdate(doc.shift_date, "dd-mm-yyyy")
                doc.pre_use_lookup = f"{doc.location}-{formatted_date}-{doc.shift}"
                doc.save(ignore_permissions=True)
                append_log(doc.name, f"Phase 2: pre_use_lookup updated for doc={doc.name}")
            except Exception as e:
                asset_name, item_name = _get_doc_asset_item_name(doc_name)
                err_msg = f"Phase 2 Error for doc={doc_name}, asset_name={asset_name}, item_name={item_name}: {str(e)}"
                append_log(doc_name, err_msg)
                error_records.append(err_msg)

        # =============================================================================
        # Phase 3: Update pre_use_link using pre_use_lookup (WITH FALLBACKS)
        # =============================================================================
        for doc_name in created_records + updated_records:
            try:
                doc = frappe.get_doc("Availability and Utilisation", doc_name)

                pre_use_doc = _get_preuse_doc_for_au(doc)
                if pre_use_doc:
                    doc.pre_use_link = pre_use_doc.name
                    doc.save(ignore_permissions=True)
                    append_log(doc.name, f"Phase 3: pre_use_link set to {pre_use_doc.name} for doc={doc.name}")
                else:
                    append_log(doc.name, f"Phase 3: No Pre-Use Hours found for doc={doc.name} lookup={doc.pre_use_lookup}")

            except Exception as e:
                asset_name, item_name = _get_doc_asset_item_name(doc_name)
                err_msg = f"Phase 3 Error for doc={doc_name}, asset_name={asset_name}, item_name={item_name}: {str(e)}"
                append_log(doc_name, err_msg)
                error_records.append(err_msg)

        # =============================================================================
        # Phase 4: Update shift_required_hours  (LAST 7 DAYS)
        # =============================================================================
        current_date = getdate(today())
        start_date = current_date - timedelta(days=7)

        relevant_records = frappe.get_all(
            "Availability and Utilisation",
            filters=[
                ["shift_date", ">=", start_date],
                ["shift_date", "<=", current_date],
            ],
            fields=["name", "shift_date", "location", "shift"],
        )

        for record in relevant_records:
            try:
                doc = frappe.get_doc("Availability and Utilisation", record.name)
                shift_date = getdate(doc.shift_date)
                location = doc.location

                planning_doc_row = frappe.get_all(
                    "Monthly Production Planning",
                    filters={
                        "prod_month_start_date": ["<=", shift_date],
                        "prod_month_end_date": [">=", shift_date],
                        "location": location,
                        "site_status": "Producing",
                    },
                    fields=["name"],
                    limit=1,
                )
                if not planning_doc_row:
                    continue

                planning_doc = frappe.get_doc("Monthly Production Planning", planning_doc_row[0].name)
                for day in planning_doc.month_prod_days:
                    if getdate(day.shift_start_date) == shift_date:
                        base_hours = 0

                        if doc.shift == "Day":
                            base_hours = day.shift_day_hours or 0
                        elif doc.shift == "Night":
                            base_hours = day.shift_night_hours or 0
                        elif doc.shift == "Morning":
                            base_hours = day.shift_morning_hours or 0
                        elif doc.shift == "Afternoon":
                            base_hours = day.shift_afternoon_hours or 0

                        doc.shift_required_hours = base_hours or 0

                        doc.save(ignore_permissions=True)
                        append_log(doc.name, f"Phase 4: shift_required_hours updated for doc={doc.name}")
                        break

            except Exception as e:
                asset_name, item_name = _get_doc_asset_item_name(record["name"])
                err_msg = f"Phase 4 Error for doc={record['name']}, asset_name={asset_name}, item_name={item_name}: {str(e)}"
                append_log(record["name"], err_msg)
                error_records.append(err_msg)

        # =============================================================================
        # Phase 5: Update from Pre-Use Hours (FIXED ASSET MATCHING, NO PRE-USE CHANGES)
        # =============================================================================
        for doc_name in created_records + updated_records:
            try:
                doc = frappe.get_doc("Availability and Utilisation", doc_name)

                pre_use_doc = _get_preuse_doc_for_au(doc)
                if not pre_use_doc:
                    append_log(doc.name, f"Phase 5: No Pre-Use Hours found for doc={doc.name} lookup={doc.pre_use_lookup}")
                    continue

                # AU asset_name is Plant No
                target_plant_no = doc.asset_name
                matched_row = None

                for asset_row in pre_use_doc.pre_use_assets:
                    row_plant_no = _preuse_row_plant_no(asset_row)
                    if row_plant_no and row_plant_no == target_plant_no:
                        matched_row = asset_row
                        break

                if not matched_row:
                    append_log(
                        doc.name,
                        f"Phase 5: Pre-Use Hours {pre_use_doc.name} found but no asset matched Plant No={target_plant_no}",
                    )
                    continue

                # Apply values
                if matched_row.eng_hrs_start is not None:
                    doc.shift_start_hours = matched_row.eng_hrs_start
                if matched_row.eng_hrs_end is not None:
                    doc.shift_end_hours = matched_row.eng_hrs_end

                if getattr(matched_row, "pre_use_avail_status", None) is not None:
                    doc.pre_use_avail_status = matched_row.pre_use_avail_status

                # Ensure link is set too
                doc.pre_use_link = pre_use_doc.name

                doc.shift_working_hours, hours_problem = _working_hours_from_engine_hours(doc)
                doc.save(ignore_permissions=True)

                append_log(doc.name, f"Phase 5: Pre-Use Hours applied for doc={doc.name} from {pre_use_doc.name}")
                if hours_problem:
                    err_msg = (
                        f"Phase 5 Error for doc={doc.name}, asset_name={doc.asset_name}, "
                        f"item_name={doc.item_name}: {hours_problem}"
                    )
                    append_log(doc.name, err_msg)
                    error_records.append(err_msg)

            except Exception as e:
                asset_name, item_name = _get_doc_asset_item_name(doc_name)
                err_msg = f"Phase 5 Error for doc={doc_name}, asset_name={asset_name}, item_name={item_name}: {str(e)}"
                append_log(doc_name, err_msg)
                error_records.append(err_msg)

        # =============================================================================
        # Phase 6: Update item_name using asset lookup
        # =============================================================================
        for doc_name in created_records + updated_records:
            previous_item_name = None
            try:
                doc = frappe.get_doc("Availability and Utilisation", doc_name)
                previous_item_name = doc.item_name

                asset_doc = frappe.get_all(
                    "Asset",
                    filters={"asset_name": doc.asset_name, "docstatus": 1},  # doc.asset_name = Plant No
                    fields=["item_name"],
                    limit=1,
                )
                if asset_doc:
                    fetched_item_name = asset_doc[0].get("item_name")
                    if fetched_item_name != previous_item_name:
                        doc.item_name = fetched_item_name or None
                        doc.save(ignore_permissions=True)
                        append_log(doc.name, f"Phase 6: item_name updated for doc={doc.name}")
            except Exception as e:
                asset_name, item_name = _get_doc_asset_item_name(doc_name)
                err_msg = (
                    f"Phase 6 Error for doc={doc_name}, asset_name={asset_name}, item_name={item_name}: {str(e)}. "
                    f"Previous item_name: {previous_item_name}."
                )
                append_log(doc_name, err_msg)
                error_records.append(err_msg)



        # =============================================================================
        # Phase 7: Update shift_breakdown_hours directly from PBM
        # =============================================================================
        current_date = getdate(today())
        start_date = current_date - timedelta(days=7)

        parent_records = frappe.get_all(
            "Availability and Utilisation",
            filters=[
                ["shift_date", ">=", start_date],
                ["shift_date", "<=", current_date],
            ],
            fields=[
                "name",
                "shift_date",
                "shift",
                "shift_system",
                "location",
                "asset_name",
                "shift_required_hours",
            ],
            order_by="shift_date asc",
        )

        for parent_record in parent_records:
            try:
                shift_start, shift_end = get_shift_timings(
                    parent_record["shift_system"],
                    parent_record["shift"],
                    str(parent_record["shift_date"]),
                )

                breakdown_rows = frappe.db.sql(
                    """
                    SELECT
                        name,
                        breakdown_start_datetime,
                        resolved_datetime
                    FROM `tabPlant Breakdown or Maintenance`
                    WHERE location = %(location)s
                      AND asset_name = %(asset_name)s
                      AND IFNULL(exclude_from_au, 0) = 0
                      AND breakdown_start_datetime IS NOT NULL
                      AND breakdown_start_datetime >= %(trust_datetime)s
                      AND breakdown_start_datetime < %(shift_end)s
                      AND (
                            resolved_datetime IS NULL
                            OR resolved_datetime = ''
                            OR resolved_datetime > %(shift_start)s
                      )
                    ORDER BY breakdown_start_datetime ASC
                    """,
                    {
                        "location": parent_record["location"],
                        "asset_name": parent_record["asset_name"],
                        "shift_start": shift_start,
                        "shift_end": shift_end,
                        "trust_datetime": "2026-01-01 00:00:00",
                    },
                    as_dict=True,
                )

                excluded_windows = _exclusion_windows(
                    parent_record["location"],
                    parent_record["shift"],
                    shift_start,
                    shift_end,
                )

                effective_hours = 0.0
                excluded_hours = 0.0

                for breakdown in breakdown_rows:
                    breakdown_start = get_datetime(
                        breakdown["breakdown_start_datetime"]
                    )

                    breakdown_end = (
                        get_datetime(breakdown["resolved_datetime"])
                        if breakdown.get("resolved_datetime")
                        else min(now_datetime(), shift_end)
                    )

                    interval_start = max(
                        breakdown_start,
                        shift_start,
                    )

                    interval_end = min(
                        breakdown_end,
                        shift_end,
                    )

                    if interval_end <= interval_start:
                        continue

                    interval_hours = _overlap_hours(
                        interval_start,
                        interval_end,
                        shift_start,
                        shift_end,
                    )

                    interval_excluded = 0.0

                    for window_start, window_end in excluded_windows:
                        interval_excluded += _overlap_hours(
                            interval_start,
                            interval_end,
                            window_start,
                            window_end,
                        )

                    interval_excluded = min(
                        interval_excluded,
                        interval_hours,
                    )

                    excluded_hours += interval_excluded
                    effective_hours += max(
                        interval_hours - interval_excluded,
                        0,
                    )

                shift_required_hours = max(
                    flt(parent_record["shift_required_hours"]),
                    0,
                )

                shift_breakdown_hours = min(
                    effective_hours,
                    shift_required_hours,
                )

                frappe.db.set_value(
                    "Availability and Utilisation",
                    parent_record["name"],
                    "shift_breakdown_hours",
                    shift_breakdown_hours,
                )

                append_log(
                    parent_record["name"],
                    (
                        f"Phase 7: PBM downtime updated for "
                        f"doc={parent_record['name']}. "
                        f"Breakdowns={len(breakdown_rows)}, "
                        f"Excluded={excluded_hours:.2f}h, "
                        f"A&U Downtime={shift_breakdown_hours:.3f}h."
                    ),
                )

            except Exception as e:
                asset_name, item_name = _get_doc_asset_item_name(
                    parent_record["name"]
                )

                err_msg = (
                    f"Phase 7 Error for doc={parent_record['name']}, "
                    f"asset_name={asset_name}, "
                    f"item_name={item_name}: {str(e)}"
                )

                append_log(
                    parent_record["name"],
                    err_msg,
                )

                error_records.append(err_msg)



        # =============================================================================
        # Phase 8: Calculate and set final fields
        # =============================================================================
        for doc_name in created_records + updated_records:
            try:
                doc = frappe.get_doc("Availability and Utilisation", doc_name)

                shift_required_hours = doc.shift_required_hours or 0
                shift_breakdown_hours = doc.shift_breakdown_hours or 0
                shift_working_hours = doc.shift_working_hours or 0

                if doc.pre_use_avail_status in ("3", "6"):
                    shift_required_hours = 0
                    shift_available_hours = shift_working_hours
                    shift_other_lost_hours = 0
                else:
                    shift_available_hours = max(shift_required_hours - shift_breakdown_hours, 0)
                    if shift_working_hours > shift_available_hours:
                        shift_other_lost_hours = max(shift_required_hours - shift_working_hours, 0)
                    else:
                        shift_other_lost_hours = max(shift_available_hours - shift_working_hours, 0)

                doc.shift_required_hours = shift_required_hours
                doc.shift_available_hours = shift_available_hours
                doc.shift_other_lost_hours = shift_other_lost_hours

                max_val = max(
                    shift_working_hours,
                    shift_available_hours,
                )

                doc.plant_shift_utilisation = (
                    (shift_working_hours / shift_available_hours) * 100
                    if shift_available_hours > 0
                    else 0
                )

                # Existing availability field stays unchanged.
                if doc.pre_use_avail_status in ("3", "6"):
                    doc.plant_shift_availability = 100
                else:
                    doc.plant_shift_availability = (
                        (max_val / shift_required_hours) * 100
                        if shift_required_hours > 0
                        else 0
                    )

                # Existing fields remain capped at 100%.
                doc.plant_shift_utilisation = min(
                    doc.plant_shift_utilisation,
                    100,
                )

                doc.plant_shift_availability = min(
                    doc.plant_shift_availability,
                    100,
                )

                # New availability fields may exceed 100%.
                doc.shift_available_hours_above_100 = max_val

                if doc.pre_use_avail_status in ("3", "6"):
                    doc.plant_shift_availability_above_100 = 100
                else:
                    doc.plant_shift_availability_above_100 = (
                        (max_val / shift_required_hours) * 100
                        if shift_required_hours > 0
                        else 0
                    )

                available_hours_above_100_capped = (
                    shift_required_hours
                )

                doc.available_hours_above_100_capped = (
                    available_hours_above_100_capped
                )

                doc.plant_shift_utilisation_above_100 = (
                    (
                        shift_working_hours
                        / available_hours_above_100_capped
                    )
                    * 100
                    if available_hours_above_100_capped > 0
                    else 0
                )

                doc.save(ignore_permissions=True)

                append_log(
                    doc.name,
                    (
                        f"Phase 8: Final fields updated for doc={doc.name}. "
                        f"(shift_required_hours={shift_required_hours}, "
                        f"shift_breakdown_hours={shift_breakdown_hours}, "
                        f"shift_working_hours={shift_working_hours}, "
                        f"shift_available_hours={shift_available_hours}, "
                        f"shift_other_lost_hours={shift_other_lost_hours}, "
                        f"plant_shift_utilisation={doc.plant_shift_utilisation}, "
                        f"plant_shift_availability={doc.plant_shift_availability})"
                    ),
                )

            except Exception as e:
                asset_name, item_name = _get_doc_asset_item_name(doc_name)
                err_msg = f"Phase 8 Error for doc={doc_name}, asset_name={asset_name}, item_name={item_name}: {str(e)}"
                append_log(doc_name, err_msg)
                error_records.append(err_msg)

        # =============================================================================
        # Phase 9: Per-record log
        # Progress goes to logs/availability_utilisation.log; only records that hit a
        # "Phase N Error" are written to Error Log, so real failures aren't buried.
        # =============================================================================
        au_logger = frappe.logger("availability_utilisation", allow_site=True, max_size=5_000_000, file_count=5)
        au_logger.setLevel(logging.INFO)  # frappe defaults to ERROR in production, which drops progress lines
        error_keys = []
        for key, messages in record_logs.items():
            line = f"{key}: " + " | ".join(messages)
            if any(" Error" in m for m in messages):
                error_keys.append(key)
                au_logger.warning(line)
            else:
                au_logger.info(line)

        max_logs_per_entry = 200
        for i in range(0, len(error_keys), max_logs_per_entry):
            batch_keys = error_keys[i : i + max_logs_per_entry]
            batch_messages = [f"{key}: " + " | ".join(record_logs[key]) for key in batch_keys]
            frappe.log_error(
                title=f"Phase Update Log - Errors {i // max_logs_per_entry + 1}",
                message="\n".join(batch_messages),
            )

        # =============================================================================
        # Phase 10: Summary Log
        # =============================================================================
        process_completed_at = now_datetime()
        duration = process_completed_at - process_started_at

        success_message = (
            f"Successfully created {len(created_records)} records. "
            f"Updated {len(updated_records)} records. "
            f"Started at {process_started_at.strftime('%Y-%m-%d %H:%M:%S')}, "
            f"completed at {process_completed_at.strftime('%Y-%m-%d %H:%M:%S')}, "
            f"duration {duration}. "
        )
        if error_records:
            success_message += f"Errors encountered: {len(error_records)}. Check 'Phase Update Log - Errors' for details."
            frappe.log_error(message=success_message, title="Availability & Utilisation - Process Completion")
        else:
            au_logger.info(success_message)
        return success_message


# =============================================================================
# Whitelisted: Manual trigger
# =============================================================================

@frappe.whitelist()
def create_availability_and_utilisation():
    """Manual trigger to run generation of records."""
    return AvailabilityandUtilisation.generate_records()


# =============================================================================
# Whitelisted: Targeted single-record sync (FAST TEST, NO ENGINE)
# =============================================================================

@frappe.whitelist()
def sync_single_au(au_name: str):
    """
    Fast, end-to-end test:
      - updates pre_use_lookup
      - finds matching Pre-Use Hours (no Pre-Use changes required)
      - pulls start/end/working hours into AU

    Safe to run in production for ONE doc.
    """
    doc = frappe.get_doc("Availability and Utilisation", au_name)

    # build lookup same as engine
    formatted_date = formatdate(doc.shift_date, "dd-mm-yyyy")
    doc.pre_use_lookup = f"{doc.location}-{formatted_date}-{doc.shift}"

    pre_use_doc = _get_preuse_doc_for_au(doc)
    if not pre_use_doc:
        doc.save(ignore_permissions=True)
        return f"No Pre-Use Hours found for AU={doc.name} lookup={doc.pre_use_lookup}"

    target_plant_no = doc.asset_name
    matched_row = None
    for r in pre_use_doc.pre_use_assets:
        if _preuse_row_plant_no(r) == target_plant_no:
            matched_row = r
            break

    if not matched_row:
        doc.pre_use_link = pre_use_doc.name
        doc.save(ignore_permissions=True)
        return f"Pre-Use {pre_use_doc.name} found but no matching asset for Plant No={target_plant_no}"

    doc.pre_use_link = pre_use_doc.name
    doc.shift_start_hours = matched_row.eng_hrs_start
    doc.shift_end_hours = matched_row.eng_hrs_end
    doc.pre_use_avail_status = matched_row.pre_use_avail_status

    doc.shift_working_hours, hours_problem = _working_hours_from_engine_hours(doc)

    doc.save(ignore_permissions=True)
    if hours_problem:
        return f"Synced AU={doc.name} from Pre-Use={pre_use_doc.name} with error: {hours_problem}"
    return f"Synced AU={doc.name} from Pre-Use={pre_use_doc.name} (Plant No={target_plant_no})"


# =============================================================================
# Scheduled job: enqueue heavy processing on long queue
# =============================================================================




@frappe.whitelist()
def run_hourly_gate():
    """Hourly scheduler gate.
    Weekdays: 06:00 and 18:00
    Weekends: 06:00 and 15:00
    """
    now = now_datetime()
    hour = now.hour
    dow = now.weekday()  # Mon=0 ... Sun=6

    is_weekend = dow in (5, 6)  # Sat/Sun
    allowed_hours = {6, 15} if is_weekend else {6, 18}

    if hour not in allowed_hours:
        return "SKIP"

    # Same enqueue as run_daily
    frappe.enqueue(
        "engineering.engineering.doctype.availability_and_utilisation.availability_and_utilisation.create_availability_and_utilisation",
        queue="long",
        job_name=f"Availability & Utilisation Engine (Hourly Gate {now.strftime('%Y-%m-%d %H:%M')})",
        timeout=60 * 60,
    )
    return "ENQUEUED"







@frappe.whitelist()
def run_daily():
    """Scheduled job: enqueue heavy processing on the long queue."""
    started_at = now_datetime()
    frappe.log_error(
        f"Scheduled job enqueuing at {started_at.strftime('%Y-%m-%d %H:%M:%S')} for Availability and Utilisation",
        "Daily Job Start",
    )

    frappe.enqueue(
        "engineering.engineering.doctype.availability_and_utilisation.availability_and_utilisation.create_availability_and_utilisation",
        queue="long",
        job_name="Availability & Utilisation Engine (Scheduled)",
        timeout=60 * 60,
    )

    enqueued_at = now_datetime()
    frappe.log_error(
        f"Scheduled job enqueued at {enqueued_at.strftime('%Y-%m-%d %H:%M:%S')} for Availability and Utilisation",
        "Daily Job Enqueued",
    )


# =============================================================================
# Background queue function
# =============================================================================

@frappe.whitelist()
def queue_availability_and_utilisation():
    """
    Enqueue the AU generation process to run in background (async).
    """
    frappe.enqueue(
        "engineering.engineering.doctype.availability_and_utilisation.availability_and_utilisation.create_availability_and_utilisation",
        queue="long",
        job_name="Availability & Utilisation Engine Run",
        timeout=60 * 60,
    )
    frappe.msgprint(
        msg="⏳ Availability & Utilisation generation has been queued. Check Error Log for progress.",
        title="Process Queued",
        indicator="blue",
    )
    return "Queued"
