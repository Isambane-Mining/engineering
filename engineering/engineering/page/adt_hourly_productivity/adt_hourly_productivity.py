"""Hourly, minute-weighted ADT availability and production for a single site."""

import re
from collections import defaultdict
from datetime import datetime, time, timedelta
from html import escape

import frappe
from frappe.utils import get_datetime, getdate, now_datetime


HOUR_SLOT = re.compile(r"^\s*(\d{1,2}):00\s*[-–]\s*(\d{1,2}):00\s*$")


def current_shift(now=None):
    now = now or now_datetime()
    shift_date = now.date()
    if now.time() < time(6):
        shift_date -= timedelta(days=1)
        shift = "Night"
    elif now.time() < time(18):
        shift = "Day"
    else:
        shift = "Night"
    return {"date": shift_date.isoformat(), "shift": shift}


def _value(row, key, default=None):
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def _bucket_start(shift_date, shift):
    return datetime.combine(shift_date, time(6 if shift == "Day" else 18))


def _production_hour(slot, shift):
    match = HOUR_SLOT.match(str(slot or ""))
    if not match:
        return None
    start_hour, end_hour = map(int, match.groups())
    if start_hour > 23 or end_hour != (start_hour + 1) % 24:
        return None
    order = (start_hour - (6 if shift == "Day" else 18)) % 24
    return order if order < 12 else None


def _clock_time(value):
    """Read Frappe Time values, including MariaDB TIME values returned as timedeltas."""
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    if isinstance(value, timedelta):
        seconds = value.total_seconds()
        if not 0 <= seconds < 86400:
            return None
        return (datetime.min + value).time()
    if not value:
        return None
    try:
        return time.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _event_hour(value, shift):
    clock = _clock_time(value)
    if clock is None:
        return None, None
    index = (clock.hour - (6 if shift == "Day" else 18)) % 24
    return (clock, index) if index < 12 else (None, None)


def _excavator_events(production, shift, hours):
    grouped = {}
    for row in production:
        asset = str(_value(row, "asset_name_shoval") or "").strip()
        if not asset:
            continue
        item = grouped.setdefault(asset, {"label": asset, "first": None, "last": None})
        label = _value(row, "excavator_label") or _value(row, "excavator_plant_no")
        if label:
            item["label"] = str(label).strip()

        # Hourly Production copies load times forward as excavator setup. Select
        # the latest nonblank value by operational hour, not by child-row order
        # or event clock time. Within a duplicate hour, modified/creation/name
        # and child index/name provide a deterministic correction order.
        hour_index = _production_hour(_value(row, "hour_slot"), shift)
        if hour_index is None:
            continue
        order = (
            hour_index,
            str(_value(row, "hp_modified") or ""),
            str(_value(row, "hp_creation") or ""),
            str(_value(row, "hp_name") or ""),
            int(_value(row, "truck_idx") or 0),
            str(_value(row, "truck_row_name") or ""),
        )
        for field, event_name in (("exc_start_load_time", "first"), ("exc_end_load_time", "last")):
            clock, event_hour = _event_hour(_value(row, field), shift)
            if clock is not None and (item[event_name] is None or order > item[event_name][0]):
                item[event_name] = (order, clock, event_hour)

    excavators = []
    for item in sorted(grouped.values(), key=lambda row: row["label"]):
        result = {"excavator": item["label"]}
        for event_name in ("first", "last"):
            event = item[event_name]
            result[f"{event_name}_load_time"] = event[1].strftime("%H:%M") if event else None
            result[f"{event_name}_load_hour"] = hours[event[2]]["label"] if event else None
            if event:
                hours[event[2]][f"{event_name}_load_events"].append({
                    "excavator": item["label"], "time": result[f"{event_name}_load_time"]
                })
        excavators.append(result)
    return excavators


def _unavailable_seconds(intervals, start, end):
    clipped = sorted(
        (max(start, left), min(end, right))
        for left, right in intervals
        if left < end and right > start
    )
    total = 0.0
    merged_end = start
    for left, right in clipped:
        if right > merged_end:
            total += (right - max(left, merged_end)).total_seconds()
            merged_end = right
    return min(total, 3600.0)


def build_report(shift_date, shift, site, assets, breakdowns, production):
    """Calculate twelve buckets using bounded, already-fetched source rows."""
    if shift not in ("Day", "Night"):
        raise ValueError("Shift must be Day or Night")
    shift_date = getdate(shift_date)
    start = _bucket_start(shift_date, shift)
    asset_rows = sorted(
        (row for row in assets if not _value(row, "location") or _value(row, "location") == site),
        key=lambda row: (_value(row, "asset_name") or _value(row, "name") or ""),
    )
    asset_names = {_value(row, "name") for row in asset_rows}
    aliases = {
        alias: _value(row, "name")
        for row in asset_rows
        for alias in (_value(row, "name"), _value(row, "asset_name"))
        if alias
    }
    intervals = defaultdict(list)
    for row in breakdowns:
        asset = aliases.get(str(_value(row, "asset_name") or "").strip())
        started = _value(row, "breakdown_start_datetime")
        if not asset or not started:
            continue
        left = get_datetime(started)
        right_value = _value(row, "resolved_datetime")
        right = get_datetime(right_value) if right_value else start + timedelta(hours=12)
        if right > left:
            intervals[asset].append((left, right))

    loads_by_hour = defaultdict(int)
    for row in production:
        asset = aliases.get(str(_value(row, "asset_name_truck") or "").strip())
        index = _production_hour(_value(row, "hour_slot"), shift)
        if asset in asset_names and index is not None:
            loads_by_hour[(index, asset)] += max(int(_value(row, "loads") or 0), 0)

    hours = []
    details = []
    used_assets = set()
    for index in range(12):
        left = start + timedelta(hours=index)
        right = left + timedelta(hours=1)
        label = f"{left:%H:%M}–{right:%H:%M}"
        available = 0.0
        utilised = 0
        total_loads = 0
        for row in asset_rows:
            asset = _value(row, "name")
            name = _value(row, "asset_name") or asset
            minutes = (3600 - _unavailable_seconds(intervals[asset], left, right)) / 60
            loads = loads_by_hour[(index, asset)]
            status = "full" if minutes >= 60 else "partial" if minutes > 0 else "unavailable"
            available += minutes / 60
            utilised += int(loads > 0)
            total_loads += loads
            if loads:
                used_assets.add(asset)
            details.append({
                "adt": name,
                "hour": label,
                "available": minutes > 0,
                "available_minutes": minutes,
                "availability_contribution": minutes / 60,
                "availability_status": status,
                "utilised": loads > 0,
                "loads": loads,
            })
        hours.append({
            "label": label,
            "start": left.strftime("%Y-%m-%d %H:%M:%S"),
            "end": right.strftime("%Y-%m-%d %H:%M:%S"),
            "available": available,
            "utilised": utilised,
            "loads": total_loads,
            "first_load_events": [],
            "last_load_events": [],
        })
    excavators = _excavator_events(production, shift, hours)
    return {
        "date": shift_date.isoformat(),
        "shift": shift,
        "site": site,
        "hours": hours,
        "excavators": excavators,
        "details": details,
        "summary": {
            "adts_at_site": len(asset_rows),
            "average_available": sum(row["available"] for row in hours) / 12,
            "adts_utilised": len(used_assets),
            "total_loads": sum(row["loads"] for row in hours),
        },
    }


@frappe.whitelist()
def get_defaults():
    return current_shift()


def _validated_filters(date, shift, site):
    defaults = current_shift()
    date = getdate(date or defaults["date"])
    shift = shift or defaults["shift"]
    if shift not in ("Day", "Night"):
        frappe.throw("Shift must be Day or Night")
    if not site or not frappe.db.exists("Location", site):
        frappe.throw("Select a valid Site")
    return date, shift, site


def _load_report(date, shift, site):
    date, shift, site = _validated_filters(date, shift, site)
    start = _bucket_start(date, shift)
    end = start + timedelta(hours=12)
    assets = frappe.db.sql("""
        SELECT name, asset_name, location FROM `tabAsset`
        WHERE docstatus = 1 AND asset_category = 'ADT' AND location = %(site)s
        ORDER BY asset_name, name
    """, {"site": site}, as_dict=True)
    names = tuple({value for row in assets for value in (row.name, row.asset_name) if value})
    breakdowns = frappe.db.sql("""
        SELECT asset_name, breakdown_start_datetime, resolved_datetime
        FROM `tabPlant Breakdown or Maintenance`
        WHERE location = %(site)s AND asset_name IN %(names)s
          AND IFNULL(exclude_from_au, 0) = 0
          AND IFNULL(breakdown_reason, '') != ''
          AND breakdown_start_datetime < %(end)s
          AND (resolved_datetime > %(start)s OR resolved_datetime IS NULL)
    """, {"site": site, "names": names, "start": start, "end": end}, as_dict=True) if names else []
    production = frappe.db.sql("""
        SELECT hp.name AS hp_name, hp.hour_slot, hp.modified AS hp_modified,
               hp.creation AS hp_creation, tl.name AS truck_row_name,
               tl.idx AS truck_idx, tl.asset_name_truck, tl.loads,
               tl.asset_name_shoval, tl.excavator_plant_no,
               COALESCE(NULLIF(tl.excavator_plant_no, ''), exc.asset_name,
                        tl.asset_name_shoval) AS excavator_label,
               tl.exc_start_load_time, tl.exc_end_load_time
        FROM `tabHourly Production` hp
        INNER JOIN `tabTruck Loads` tl
          ON tl.parent = hp.name AND tl.parenttype = 'Hourly Production'
        LEFT JOIN `tabAsset` exc ON exc.name = tl.asset_name_shoval
        WHERE hp.location = %(site)s AND hp.prod_date = %(date)s
          AND hp.shift = %(shift)s
    """, {"site": site, "date": date, "shift": shift}, as_dict=True)
    return build_report(date, shift, site, assets, breakdowns, production)


@frappe.whitelist()
def get_dashboard(date=None, shift=None, site=None):
    return _load_report(date, shift, site)


def build_pdf_html(data):
    summary = data["summary"]
    rows = []
    excavator_rows = []
    for row in data["excavators"]:
        excavator_rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                escape(str(row["excavator"])),
                escape(row["first_load_time"] or "-"),
                escape(row["first_load_hour"] or "-"),
                escape(row["last_load_time"] or "-"),
                escape(row["last_load_hour"] or "-"),
            )
        )
    for row in data["details"]:
        available = "✓" if row["available"] else "✗"
        utilised = "✓" if row["utilised"] else "✗"
        status = row["availability_status"].title()
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{} {}</td><td>{:.2f}</td>"
            "<td>{:.2f}</td><td>{}</td><td>{}</td></tr>".format(
                escape(str(row["adt"])), escape(row["hour"]), available, status,
                row["available_minutes"], row["availability_contribution"],
                utilised, row["loads"],
            )
        )
    return """<html><head><meta charset="utf-8"><style>
        body {{ font-family: Arial, sans-serif; color: #173047; font-size: 10px; }}
        h1 {{ font-size: 23px; margin-bottom: 3px; }}
        h2 {{ font-size: 15px; margin: 16px 0 7px; }}
        .meta {{ color: #586c7e; margin-bottom: 16px; }}
        .summary {{ background: #e9f3f5; padding: 11px; margin-bottom: 14px; font-size: 12px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #143c52; color: white; text-align: left; padding: 7px; }}
        td {{ border-bottom: 1px solid #d9e3e8; padding: 6px 7px; }}
        tr {{ page-break-inside: avoid; }}
        thead {{ display: table-header-group; }}
        .note {{ margin-top: 12px; color: #586c7e; font-size: 9px; }}
    </style></head><body>
      <h1>ADT hourly productivity</h1>
      <div class="meta">{site} · {date} · {shift} shift</div>
      <div class="summary"><b>ADTs at site:</b> {count} &nbsp; <b>Average available:</b> {average:.2f}
      &nbsp; <b>ADTs utilised:</b> {used} &nbsp; <b>Total loads:</b> {loads}</div>
      <h2>Excavator First / Last Load Performance</h2>
      <table><thead><tr><th>Excavator</th><th>First Load Time</th><th>First Load Hour</th>
      <th>Last Load Time</th><th>Last Load Hour</th></tr></thead><tbody>{excavator_rows}</tbody></table>
      <h2>ADT Hourly Detail</h2>
      <table><thead><tr><th>ADT</th><th>Hour</th><th>Available</th><th>Minutes</th>
      <th>Contribution</th><th>Utilised</th><th>Loads</th></tr></thead><tbody>{rows}</tbody></table>
      <p class="note">Available contribution = available minutes / 60. Average available = sum of twelve
      hourly available ADT counts / 12. ADTs utilised counts unique ADTs with at least one load.
      Total loads is the sum of recorded Truck Loads rows for these ADTs and hours.</p>
    </body></html>""".format(
        site=escape(str(data["site"])), date=escape(data["date"]), shift=escape(data["shift"]),
        count=summary["adts_at_site"], average=summary["average_available"],
        used=summary["adts_utilised"], loads=summary["total_loads"], rows="".join(rows),
        excavator_rows="".join(excavator_rows) or "<tr><td colspan='5'>No excavators recorded</td></tr>",
    )


@frappe.whitelist()
def download_detailed_pdf(date=None, shift=None, site=None):
    from frappe.utils.pdf import get_pdf

    data = _load_report(date, shift, site)
    pdf = get_pdf(build_pdf_html(data), {"orientation": "Landscape"})
    frappe.local.response.filename = f"ADT_hourly_productivity_{data['site']}_{data['date']}_{data['shift']}.pdf"
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "download"
