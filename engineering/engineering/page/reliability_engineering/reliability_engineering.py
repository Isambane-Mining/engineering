"""Reusable reliability calculations and the Reliability Engineering page API.

Failure events are every Breakdown PBM, including records excluded from A&U.
Operating hours are validated Pre-use meter deltas, keyed by Asset document ID.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from math import isfinite

import frappe
from frappe.utils import getdate, nowdate


def _value(row, key, default=None):
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def _datetime(value):
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _meter_hours(row):
    start, end = _value(row, "eng_hrs_start"), _value(row, "eng_hrs_end")
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError):
        return None
    # A&U treats a zero start as a missing reading. Negative and over-shift
    # deltas are impossible, so they must not inflate the MTBF/BDFR denominator.
    maximum = 8 if str(_value(row, "shift_system") or "").lower() == "3x8hour" else 12
    if not isfinite(start) or not isfinite(end) or start <= 0 or end <= 0 or end < start or end - start > maximum:
        return None
    return end - start


def _ratios(failures, hours, repair_hours, repairs, repeats, classified):
    return {
        "breakdowns": failures,
        "operating_hours": round(hours, 2),
        "mtbf": round(hours / failures, 2) if failures else None,
        "mttr": round(repair_hours / repairs, 2) if repairs else None,
        "bdfr": round(failures * 1000 / hours, 2) if hours else None,
        "classification_coverage": round(classified * 100 / failures, 1) if failures else None,
        # Partial classification hides repeats among unclassified failures.
        "repeat_rate": round(repeats * 100 / failures, 1) if failures and classified == failures else None,
        "repeat_breakdowns": repeats,
    }


def build_report(breakdowns, meter_rows, from_date, to_date, asset_labels=None, location=None, asset=None):
    """Calculate report from source rows. `breakdowns` includes seven prior days.

    A repeat is the same Asset ID + classification within the previous seven
    days. Unclassified events cannot establish or match a repeat. Exact duplicate
    meter shifts count once; conflicting valid readings exclude that shift.
    """
    start_day, end_day = getdate(from_date), getdate(to_date)
    asset_labels = asset_labels or {}
    quality = {"invalid_repairs": 0, "invalid_meter_rows": 0, "conflicting_hour_groups": 0, "missing_asset_breakdowns": 0, "invalid_start_times": 0}
    meter_groups = defaultdict(set)
    asset_locations = defaultdict(set)
    for row in meter_rows:
        if location and _value(row, "location") != location:
            continue
        if asset and _value(row, "asset_name") != asset:
            continue
        day = getdate(_value(row, "shift_date"))
        if not start_day <= day <= end_day:
            continue
        hours = _meter_hours(row)
        if hours is None:
            quality["invalid_meter_rows"] += 1
            continue
        key = (_value(row, "location"), day, _value(row, "shift"), _value(row, "asset_name"))
        meter_groups[key].add(round(hours, 6))

    asset_totals = defaultdict(lambda: {"hours": 0.0, "failures": 0, "repair_hours": 0.0, "repairs": 0, "repeats": 0, "classified": 0})
    trend_totals = defaultdict(lambda: {"hours": 0.0, "failures": 0, "repair_hours": 0.0, "repairs": 0, "repeats": 0, "classified": 0})
    total = {"hours": 0.0, "failures": 0, "repair_hours": 0.0, "repairs": 0, "repeats": 0, "classified": 0}
    for (site, day, shift, asset_id), values in meter_groups.items():
        if len(values) != 1:
            quality["conflicting_hour_groups"] += 1
            continue
        hours = next(iter(values))
        total["hours"] += hours
        if asset_id:
            asset_totals[asset_id]["hours"] += hours
            if site:
                asset_locations[asset_id].add(site)
        trend_totals[day]["hours"] += hours

    previous = {}
    details = []
    ordered = sorted(breakdowns, key=lambda row: (_datetime(_value(row, "breakdown_start_datetime")) or _datetime(_value(row, "creation")) or datetime.min, str(_value(row, "name") or "")))
    for row in ordered:
        if location and _value(row, "location") != location:
            continue
        if asset and _value(row, "asset_name") != asset:
            continue
        timestamp = _datetime(_value(row, "breakdown_start_datetime"))
        fallback = _datetime(_value(row, "creation"))
        event_time = timestamp or fallback
        if event_time is None:
            continue  # Cannot attribute an undated record to any date range.
        asset_id = _value(row, "asset_name")
        classification = _value(row, "failure_classification") or None
        key = (asset_id, classification)
        prior = previous.get(key) if asset_id and classification else None
        repeat = bool(prior and 0 <= (event_time - prior[0]).total_seconds() <= 7 * 86400)
        if asset_id and classification:
            previous[key] = (event_time, _value(row, "name"))
        if not start_day <= event_time.date() <= end_day:
            continue
        duration = None
        resolved = _datetime(_value(row, "resolved_datetime"))
        if timestamp and resolved and resolved >= timestamp:
            duration = (resolved - timestamp).total_seconds() / 3600
        else:
            quality["invalid_repairs"] += 1
        if not timestamp:
            quality["invalid_start_times"] += 1
        if not asset_id:
            quality["missing_asset_breakdowns"] += 1
        detail = {
            "name": _value(row, "name"), "asset": asset_id, "asset_label": asset_labels.get(asset_id, asset_id or "Unassigned"),
            "location": _value(row, "location"), "date": event_time.date().isoformat(),
            "start": str(_value(row, "breakdown_start_datetime") or ""),
            "resolved": str(_value(row, "resolved_datetime") or ""), "repair_hours": round(duration, 2) if duration is not None else None,
            "classification": classification, "reason": _value(row, "breakdown_reason") or "",
            "resolution": _value(row, "resolution_summary") or "", "exclude_from_au": int(_value(row, "exclude_from_au") or 0),
            "repeat": repeat, "previous_breakdown": prior[1] if repeat else None,
            "days_since_previous": round((event_time - prior[0]).total_seconds() / 86400, 2) if repeat else None,
        }
        details.append(detail)
        if asset_id and _value(row, "location"):
            asset_locations[asset_id].add(_value(row, "location"))
        for aggregate in (total, asset_totals[asset_id or ""], trend_totals[event_time.date()]):
            aggregate["failures"] += 1
            aggregate["classified"] += bool(classification)
            aggregate["repeats"] += repeat
            if duration is not None:
                aggregate["repair_hours"] += duration
                aggregate["repairs"] += 1

    ranking = []
    for asset, aggregate in asset_totals.items():
        if not asset:
            continue
        ranking.append({"asset": asset, "asset_label": asset_labels.get(asset, asset),
                        "locations": sorted(asset_locations[asset]), "breakdown_hours": round(aggregate["repair_hours"], 2),
                        **_ratios(**aggregate)})
    ranking.sort(key=lambda row: (-row["breakdowns"], row["asset_label"] or row["asset"]))
    daily = [{"date": day.isoformat(), **aggregate, **_ratios(**aggregate)} for day, aggregate in sorted(trend_totals.items())]
    return {"kpis": {**_ratios(**total), "breakdown_hours": round(total["repair_hours"], 2)}, "ranking": ranking, "trend": daily,
            "breakdowns": list(reversed(details)), "quality": quality}


@frappe.whitelist()
def get_dashboard(from_date=None, to_date=None, location=None, asset=None):
    if not frappe.has_permission("Plant Breakdown or Maintenance", "read") or not frappe.has_permission("Pre-Use Hours", "read"):
        frappe.throw("You need read access to breakdowns and Pre-Use Hours to view this report", frappe.PermissionError)
    today = getdate(nowdate())
    from_date = getdate(from_date or today.replace(day=1))
    to_date = getdate(to_date or today)
    if to_date < from_date:
        frappe.throw("To Date must be on or after From Date")
    if location and not frappe.db.exists("Location", location):
        frappe.throw("Invalid Location")
    if asset and not frappe.db.exists("Asset", asset):
        frappe.throw("Invalid Asset")
    params = {"start": from_date, "end_exclusive": to_date + timedelta(days=1), "lookback": from_date - timedelta(days=7), "location": location, "asset": asset}
    breakdowns = frappe.db.sql("""
        SELECT name, creation, location, asset_name, breakdown_start_datetime,
               resolved_datetime, failure_classification, breakdown_reason,
               resolution_summary, exclude_from_au
        FROM `tabPlant Breakdown or Maintenance`
        WHERE downtime_type = 'Breakdown'
          AND COALESCE(breakdown_start_datetime, creation) >= %(lookback)s
          AND COALESCE(breakdown_start_datetime, creation) < %(end_exclusive)s
          AND (%(location)s IS NULL OR location = %(location)s)
          AND (%(asset)s IS NULL OR asset_name = %(asset)s)
        ORDER BY COALESCE(breakdown_start_datetime, creation), name
    """, params, as_dict=True)
    meters = frappe.db.sql("""
        SELECT child.name, parent.location, parent.shift_date, parent.shift,
               parent.shift_system, child.asset_name, child.eng_hrs_start, child.eng_hrs_end
        FROM `tabPre-use Assets` child
        INNER JOIN `tabPre-Use Hours` parent ON child.parent = parent.name
        WHERE parent.shift_date >= %(start)s AND parent.shift_date < %(end_exclusive)s
          AND (%(location)s IS NULL OR parent.location = %(location)s)
          AND (%(asset)s IS NULL OR child.asset_name = %(asset)s)
    """, params, as_dict=True)
    asset_ids = {row.asset_name for row in breakdowns + meters if row.asset_name}
    labels = {}
    if asset_ids:
        for row in frappe.get_all("Asset", filters={"name": ["in", list(asset_ids)]}, fields=["name", "asset_name"]):
            labels[row.name] = row.asset_name or row.name
    return build_report(breakdowns, meters, from_date, to_date, labels, location, asset)
