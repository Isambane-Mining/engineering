"""Read-only visual context for the Daily A&U Engine Dashboard."""

from collections import defaultdict
from datetime import datetime, timedelta


CATEGORY = "Short Haul Reduced Fleet Lost Hours"


def short_haul_percentage(hours, available_hours):
    return hours / available_hours * 100 if available_hours > 0 else None


def _seconds(value):
    if value is None or value == "":
        return None
    if isinstance(value, timedelta):
        return value.total_seconds()
    parts = str(value).split(":")
    try:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except (ValueError, IndexError):
        return None


def aggregate_short_haul_hours(records, scope):
    """Union captured intervals per machine, restricted to Engine machine/date/shift.

    Night entries before 06:00 belong to the following calendar day, matching
    existing 2x12/3x8 shift conventions. Union absolute intervals across parents
    and shifts, including ALL Equipment, so overlapping captures count once.
    Missing/invalid times cannot be safely deduplicated and are not counted.
    """
    intervals = defaultdict(list)
    by_shift = defaultdict(set)
    for machine, day, shift in scope:
        by_shift[(day, shift)].add(machine)

    for row in records:
        day = str(row.get("shift_date") or "")[:10]
        shift = str(row.get("shift") or "").strip()
        machine = str(row.get("machine") or "").strip()
        machines = by_shift.get((day, shift), set())
        if machine.lower() != "all equipment":
            machines = machines.intersection({machine})
        if not machines:
            continue
        start, end = _seconds(row.get("start_time")), _seconds(row.get("end_time"))
        if start is None or end is None or not (0 <= start < 86400 and 0 <= end < 86400):
            continue
        duration = (end - start) % 86400
        if not duration:
            continue
        origin = datetime.fromisoformat(day)
        if shift.lower() == "night" and start < 6 * 3600:
            origin += timedelta(days=1)
        begin = origin + timedelta(seconds=start)
        finish = begin + timedelta(seconds=duration)
        for target in machines:
            intervals[target].append((begin, finish))

    result = {}
    for machine, windows in intervals.items():
        merged = []
        for start, end in sorted(windows):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        result[machine] = sum((end - start).total_seconds() for start, end in merged) / 3600
    return result


def fetch_short_haul_hours(source_rows, location, start_date, end_date):
    import frappe

    scope = {
        (str(row.get("asset_name") or "").strip(), str(row.get("shift_date") or "")[:10],
         str(row.get("shift") or "").strip())
        for row in source_rows or []
        if int(row.get("indent") or 0) == 3 and row.get("asset_name")
    }
    if not scope:
        return {}
    records = frappe.db.sql(
        """
        SELECT g.machine, r.shift_date, r.shift, g.start_time, g.end_time
        FROM `tabDaily Lost Hours Recon` r
        INNER JOIN `tabDaily General Lost Hours` g
            ON g.parent = r.name
            AND g.parenttype = 'Daily Lost Hours Recon'
            AND g.parentfield = 'general_lost_hours_table'
        WHERE r.docstatus < 2
          AND r.location = %(location)s
          AND r.shift_date BETWEEN %(start_date)s AND %(end_date)s
          AND g.lost_hour_category = %(category)s
          AND (TRIM(g.machine) IN %(machines)s
               OR LOWER(TRIM(g.machine)) = 'all equipment')
        """,
        dict(location=location, start_date=start_date, end_date=end_date,
             category=CATEGORY, machines=tuple(sorted({key[0] for key in scope}))),
        as_dict=True,
    )
    return aggregate_short_haul_hours(records, scope)
