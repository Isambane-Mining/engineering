import frappe
from frappe.model.document import Document
from frappe.utils import getdate, nowdate, cint, add_months
import calendar
import math
import re
from datetime import timedelta

class ServiceSchedule(Document):
    pass

def clamp_daily_usage(val, min_val=0.0, max_val=24.0):
    try:
        v = float(val or 0)
    except Exception:
        v = 0.0
    return max(float(min_val), min(v, float(max_val)))


@frappe.whitelist()
def queue_service_schedule_update(schedule_name=None, daily_usage_default=15):
    """Regenerate an explicit schedule, or existing current-month schedules for the daily job."""
    if schedule_name:
        names = [schedule_name]
    else:
        today = getdate(nowdate())
        month = f"{calendar.month_name[today.month]} {today.year}"
        names = frappe.get_all("Service Schedule", filters={"month": month},
            pluck="name", order_by="name asc")
    queued = []
    for name in names:
        try:
            frappe.enqueue(
                "engineering.engineering.doctype.service_schedule.service_schedule.generate_schedule_backend",
                queue="long", timeout=1800, schedule_name=name,
                daily_usage_default=clamp_daily_usage(daily_usage_default),
                job_name=f"service_schedule:{name}",
            )
            queued.append(name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Service Schedule update failed to queue: {name}")
    if not names:
        frappe.logger(__name__).info("No existing current-month Service Schedule to update.")
    return {"status": "queued" if queued else ("failed" if names else "no_current_schedule"),
            "schedule_names": queued}



def as_date(d):
    return getdate(d) if d else None

def parse_month_label(month_label):
    """Convert 'January 2025' -> (2025, 1)."""
    if not month_label:
        frappe.throw("Month label is required, e.g. 'January 2025'.")

    parts = str(month_label).strip().split()
    if len(parts) != 2:
        frappe.throw("Invalid month format. Use 'January 2025'.")

    month_name, year_str = parts[0], parts[1]
    try:
        year = int(year_str)
        month_index = list(calendar.month_name).index(month_name)
        if month_index <= 0:
            raise ValueError
        return year, month_index
    except Exception:
        frappe.throw(f"Invalid month label: {month_label}")

def parse_month_bounds(month_label):
    year, month_index = parse_month_label(month_label)
    last_day = calendar.monthrange(year, month_index)[1]
    month_start = getdate(f"{year}-{month_index:02d}-01")
    month_end = getdate(f"{year}-{month_index:02d}-{last_day:02d}")
    return year, month_index, month_start, month_end

def round_to_250(value):
    v = cint(value) or 0
    if v <= 0:
        return 0

    down = int(math.floor(v / 250.0) * 250)
    up = int(math.ceil(v / 250.0) * 250)

    # if equal distance, choose DOWN (e.g. 2625 -> 2500)
    if (v - down) <= (up - v):
        return down
    return up


def _extract_interval_number(interval_text):
    """
    "500 Hours" -> 500
    "500" -> 500
    "" / invalid -> 0
    """
    if not interval_text:
        return 0
    m = re.search(r"(\d+)", str(interval_text))
    return int(m.group(1)) if m else 0

def _fmt_hours(n):
    n = cint(n) or 0
    return f"{n} Hours" if n > 0 else ""

def interval_from_planned_hours(planned_hours):
    """Your rule:
    2000 interval = even thousands (2000,4000,6000,...)
    1000 interval = odd thousands  (1000,3000,5000,...)
    otherwise cycle by remainder in the 1000-block: 250/500/750
    """
    h = cint(planned_hours) or 0
    if h <= 0:
        return 250

    if h % 2000 == 0:
        return 2000
    if h % 1000 == 0:
        return 1000

    r = h % 1000
    if r == 250:
        return 250
    if r == 500:
        return 500
    if r == 750:
        return 750
    return 250


def ceiling_to_250(value):
    v = cint(value) or 0
    if v <= 0:
        return 0
    return int(math.ceil(v / 250.0) * 250)



def adjust_sunday_to_saturday(d, month_start=None):
    """If d is Sunday, move it back to Saturday. If that moves before month_start, keep original."""
    if not d:
        return None
    dd = getdate(d)
    if dd.weekday() == 6:  # Sunday
        sat = dd - timedelta(days=1)
        if month_start and sat < getdate(month_start):
            return dd
        return sat
    return dd

def get_assets_for_site(site):
    return frappe.get_all(
        "Asset",
        filters={
            "location": site,
            "docstatus": 1,
            "asset_category": ["in", ["ADT", "Diesel Bowsers", "Excavator", "Dozer", "Service Truck"]],
        },
        fields=["name", "asset_category", "item_name", "item_code"],
        order_by="name asc",
    )

def batch_get_day_shift_start_hours(asset_list, month_start, month_end):
    """Return Day-shift starts; the highest positive duplicate reading wins."""
    if not asset_list:
        return {}
    parents = frappe.get_all("Pre-Use Hours", filters={
        "shift_date": ("between", [month_start, month_end]), "shift": "Day"},
        fields=["name", "shift_date"], order_by="shift_date asc, name asc")
    if not parents:
        return {}
    dates = {p.name: getdate(p.shift_date).isoformat() for p in parents}
    children = frappe.get_all("Pre-use Assets", filters={
        "parent": ["in", list(dates)], "asset_name": ["in", asset_list]},
        fields=["parent", "asset_name", "eng_hrs_start"])
    out = {}
    for row in children:
        key = (dates.get(row.parent), row.asset_name)
        value = float(row.eng_hrs_start or 0)
        if key[0] and value > 0:
            out[key] = max(value, out.get(key, 0))
    return out


def get_latest_prev_start_hours(asset, month_start):
    """Use the latest positive Day-shift reading in the preceding 92 days."""
    if not asset or not month_start:
        return 0.0
    start = getdate(month_start)
    rows = frappe.db.sql(
        """
        SELECT pa.eng_hrs_start
        FROM `tabPre-Use Hours` pu
        JOIN `tabPre-use Assets` pa ON pa.parent = pu.name
        WHERE pa.asset_name = %s
          AND pu.shift = 'Day'
          AND pu.shift_date < %s
          AND pu.shift_date >= %s
          AND pa.eng_hrs_start > 0
        ORDER BY pu.shift_date DESC, pa.eng_hrs_start DESC, pu.name ASC, pa.name ASC
        LIMIT 1
        """,
        (asset, start, start - timedelta(days=92)),
        as_dict=True,
    )
    return float(rows[0].eng_hrs_start or 0) if rows else 0.0


def prev_month_label(month_label):
    year, month_index = parse_month_label(month_label)
    if month_index == 1:
        return f"December {year - 1}"
    return f"{calendar.month_name[month_index - 1]} {year}"


def get_last_30_day_avg_daily_usage(asset, anchor_date):
    """
    Compute average daily usage over the last 30 days ending at anchor_date (inclusive).
    Uses Day-shift Pre-Use Hours (eng_hrs_start) deltas between consecutive days.
    Includes 0 as valid start_hours (but delta requires consecutive days).
    Returns a float clamped to 0..24. Falls back to 15 if insufficient data.
    """
    if not asset or not anchor_date:
        return 15.0

    end = getdate(anchor_date)
    start = end - timedelta(days=29)

    # Pull day-shift pre-use docs for the window
    pre_use_docs = frappe.get_all(
        "Pre-Use Hours",
        filters={
            "shift_date": ("between", [start, end]),
            "shift": "Day",
        },
        fields=["name", "shift_date"],
        order_by="shift_date asc",
    )
    if not pre_use_docs:
        return 15.0

    parent_names = [d["name"] for d in pre_use_docs]
    parent_to_date = {d["name"]: getdate(d["shift_date"]) for d in pre_use_docs}

    # Pull only this asset's child rows
    child_rows = frappe.get_all(
        "Pre-use Assets",
        filters={
            "parent": ["in", parent_names],
            "asset_name": asset
        },
        fields=["parent", "eng_hrs_start"],
    )
    if not child_rows:
        return 15.0

    # Build date -> start_hours mapping (one per day)
    day_map = {}
    for r in child_rows:
        dt = parent_to_date.get(r.get("parent"))
        if not dt:
            continue
        try:
            day_map[dt] = float(r.get("eng_hrs_start") or 0)
        except Exception:
            day_map[dt] = 0.0

    # Calculate deltas on consecutive days only
    dates = sorted(day_map.keys())
    deltas = []
    prev_date = None
    prev_val = None

    for dt in dates:
        val = day_map.get(dt, 0.0)

        if prev_date is not None and prev_val is not None:
            if (dt - prev_date).days == 1:
                delta = val - prev_val
                # keep non-negative only (ignore resets / bad data)
                if delta >= 0:
                    deltas.append(delta)

        prev_date = dt
        prev_val = val

    if not deltas:
        return 15.0

    avg = sum(deltas) / float(len(deltas))
    return int(round(clamp_daily_usage(avg)))


def get_prev_month_seed(site, month_label, fleet_number):
    if not site or not month_label or not fleet_number:
        return (None, None)










def batch_get_oem_bookings(asset_list, month_start, month_end):
    """Return mapping (asset, date_iso) -> True for OEM Booking dates in this window.
    Draft + Submitted are valid; ignore Cancelled (docstatus=2).
    NOTE: OEM Booking does NOT have fleet_number; it uses `asset`.
    """
    if not asset_list:
        return {}

    rows = frappe.get_all(
        "OEM Booking",
        filters={
            "asset": ["in", asset_list],
            "booking_date": ("between", [month_start, month_end]),
            "docstatus": ["in", [0, 1]],
        },
        fields=["name", "asset", "booking_date"],
        order_by="booking_date asc",
    )

    out = {}
    for r in rows:
        a = r.get("asset")
        d = as_date(r.get("booking_date"))
        name = r.get("name")
        if a and d and name:
            # if multiple bookings same day, first one wins
            out.setdefault((a, d.isoformat()), name)
    return out


def recompute_oem_booking_flags(doc, lookup_start, lookup_end):
    """Stamp doc.service_schedule_child.oem_booking_date based on OEM Booking truth."""
    asset_list = sorted({r.fleet_number for r in (doc.service_schedule_child or []) if r.fleet_number})
    oem_map = batch_get_oem_bookings(asset_list, lookup_start, lookup_end) or {}

    for r in (doc.service_schedule_child or []):
        if not r.fleet_number or not r.date:
            continue
        d = getdate(r.date)
        key = (r.fleet_number, d.isoformat())
        booking_name = oem_map.get(key)
        r.oem_booking_date = 1 if booking_name else 0
        r.oem_booking_name = booking_name or ""






def batch_get_service_reports(asset_list, month_start, month_end):
    """Fetch all MSRs where service_breakdown='Service' up to month_end."""
    if not asset_list:
        return {}

    rows = frappe.get_all(
        "Mechanical Service Report",
        filters={
            "asset": ["in", asset_list],
            "service_breakdown": "Service",
            "service_date": ("<=", month_end),
            "current_hours": (">", 0),
            "docstatus": ("!=", 2),
        },
        fields=["name", "asset", "service_date", "current_hours", "service_interval"],
        order_by="asset asc, service_date asc, modified asc, name asc",
    )

    out = {a: {"before": None, "within": []} for a in asset_list}
    for r in rows:
        asset = r.get("asset")
        if asset not in out:
            continue
        sdate = as_date(r.get("service_date"))
        if not sdate:
            continue
        if sdate < month_start:
            out[asset]["before"] = r  # keep last before month start
        else:
            out[asset]["within"].append(r)
    return out

def next_service_interval_from_last(last_interval):
    """Cycle rule: 250->500, 500->750, 750->1000, 1000->250, 2000->250"""
    try:
        v = cint(str(last_interval or "").replace("Hours", "").strip()) or 0
    except Exception:
        v = 0

    mapping = {250: 500, 500: 750, 750: 1000, 1000: 250, 2000: 250}
    return mapping.get(v, 250)

def normalize_last_service_interval(last_interval):
    """Return numeric interval from MSR/service_interval field (e.g. '2000 Hours' -> 2000)."""
    try:
        v = cint(str(last_interval or "").replace("Hours", "").strip()) or 0
    except Exception:
        v = 0
    return v if v > 0 else 250


def interval_due_at_hours(planned_hours):
    """Service interval follows the target-hour cycle."""
    return interval_from_planned_hours(planned_hours)



def next_service_target_from_service_hours(last_service_hours):
    """Return the service threshold after the service represented by the latest MSR."""
    try:
        h = float(last_service_hours or 0)
    except Exception:
        h = 0.0

    if h <= 0:
        return 0

    completed_service_threshold = round_to_250(h)
    return int(completed_service_threshold + 250)


def planning_status_for_hours(estimate_hours, planned_hours):
    """Return persisted Service Planning Summary status and hours remaining."""
    try:
        estimate = float(estimate_hours or 0)
        planned = float(planned_hours or 0)
    except Exception:
        return "", 0

    if planned <= 0:
        return "", 0

    remaining = int(round(planned - estimate))

    if remaining < 0:
        return "Overdue", remaining
    if remaining == 0:
        return "Due", 0
    if remaining <= 65:
        return "Due within 65 hours", remaining
    if remaining <= 260:
        return "Due within 260 hours", remaining

    return "", remaining

def find_threshold_crossing_date(series, planned_hours):
    """series: list of (date, estimate_hours) sorted asc.
    Returns first date where estimate crosses planned (>= planned and previous < planned).
    """
    if not planned_hours:
        return None
    prev_est = None
    for d, est in series:
        if est is None:
            continue
        try:
            est_v = float(est)
        except Exception:
            continue
        
        # NEW RULE:
        # A "crossing" only counts when we go from below -> >= planned.
        # If day 1 is already >= planned, do NOT mark day 1.
        if prev_est is None:
            prev_est = est_v
            continue

        if prev_est < planned_hours <= est_v:
            return d

        prev_est = est_v
    return None

def recompute_planning_rows(rows, month_start):
    """Set persisted planning fields and future markers from each day's MSR baseline."""
    rows = sorted(rows, key=lambda r: getdate(r.date))
    segments = []
    for row in rows:
        baseline = (row.msr_record_name or "", cint(row.hours_previous_service) or 0,
                    str(row.date_of_previous_service or ""))
        if not segments or segments[-1][0] != baseline:
            segments.append((baseline, []))
        segments[-1][1].append(row)

    for baseline, segment in segments:
        hours = baseline[1]
        target = next_service_target_from_service_hours(hours) if hours > 0 else 0
        targets = (target, target + 250, target + 500) if target else (0, 0, 0)
        series = [(getdate(r.date), float(r.estimate_hours or 0)) for r in segment]
        for row in segment:
            status, remaining = planning_status_for_hours(row.estimate_hours, target)
            row.planning_planned_hours = target
            row.planning_status = status if target else "No Service History"
            row.planning_hours_remaining = remaining if target else 0
            row.planning_service_interval = _fmt_hours(interval_due_at_hours(target)) if target else ""
            row.planning_flagged_on = getdate(row.date) if status and target else None
            for n, planned in enumerate(targets, 1):
                setattr(row, f"planned_hours_next_service_{n}", planned or None)
                setattr(row, f"next_service_interval_{n}",
                        _fmt_hours(interval_due_at_hours(planned)) if planned else "")
                setattr(row, f"date_of_next_service_{n}", None)
        for n, planned in enumerate(targets, 1):
            crossing = find_threshold_crossing_date(series, planned)
            crossing = adjust_sunday_to_saturday(crossing, month_start=month_start)
            if crossing:
                for row in segment:
                    if getdate(row.date) == crossing:
                        setattr(row, f"date_of_next_service_{n}", crossing)
                        break


@frappe.whitelist()
def generate_schedule_backend(schedule_name, daily_usage_default=15):
    """Populate Service Schedule Child exactly as per Task 1 (based on latest DocTypes)."""
    doc = frappe.get_doc("Service Schedule", schedule_name)
    doc.check_permission("write")

    if not doc.month or not doc.site:
        frappe.throw("Please select Month and Site before generating the schedule.")

    _, _, month_start, month_end = parse_month_bounds(doc.month)

    assets = get_assets_for_site(doc.site)
    asset_list = [a["name"] for a in assets]

    # all dates in month
    date_list = []
    cur = month_start
    while cur <= month_end:
        date_list.append(cur)
        cur = cur + timedelta(days=1)

    start_hours_map = batch_get_day_shift_start_hours(asset_list, month_start, month_end)
    msr_map = batch_get_service_reports(asset_list, month_start, month_end)
    oem_map = batch_get_oem_bookings(asset_list, month_start, month_end) or {}

    # clear
    doc.set("service_schedule_child", [])

    rows_index = {}   # (asset, date_iso) -> row

    daily_usage_default = clamp_daily_usage(daily_usage_default or 0)

    # We'll compute per-asset default daily usage from last 30 days (rolling window)
    asset_daily_default = {}
    anchor = month_start - timedelta(days=1)  # same anchor for all assets
    for a in assets:
        asset_name = a["name"]
        asset_daily_default[asset_name] = get_last_30_day_avg_daily_usage(asset_name, anchor)



    # --- Now generate rows per asset ---
    for a in assets:
        asset = a["name"]

        prev_estimate = None  # track previous day's estimate per asset
        prev_start_hours = None  # track previous day's start_hours per asset


        # per-asset default daily usage (rolling 30 days)
        daily_use_asset = asset_daily_default.get(asset, daily_usage_default)

        before_row = (msr_map.get(asset) or {}).get("before")
        within_rows = (msr_map.get(asset) or {}).get("within") or []
        within_rows = sorted(within_rows, key=lambda r: as_date(r.get("service_date")) or month_start)
        ptr = 0
        latest_within = None

        for d in date_list:
            d_iso = d.isoformat()

            # start_hours from Day-shift pre-use (or 0)
            start_hours = start_hours_map.get((d_iso, asset), 0) or 0
            try:
                start_hours = float(start_hours)
            except Exception:
                start_hours = 0.0

            # Day 1 seed always comes from latest previous Day-shift eng_hrs_start (carry-forward)
            if d == month_start:
                start_hours = get_latest_prev_start_hours(asset, month_start)


            # RULE:
            # Day 1: Est = Day 1 start_hours
            # Day 2..end:
            #   if previous day had start_hours -> Est = prev_start_hours + daily_use
            #   else -> Est = prev_estimate + daily_use
            if d == month_start:
                estimate_hours = float(start_hours or 0.0)
            else:
                if float(prev_start_hours or 0.0) > 0:
                    estimate_hours = float(prev_start_hours) + float(daily_use_asset)
                else:
                    estimate_hours = float(prev_estimate or 0.0) + float(daily_use_asset)

            prev_estimate = float(estimate_hours or 0.0)
            prev_start_hours = float(start_hours or 0.0)


            # previous service per day (includes day 1)
            while ptr < len(within_rows):
                sr = within_rows[ptr]
                sr_date = as_date(sr.get("service_date"))
                if sr_date and sr_date <= d:
                    latest_within = sr
                    ptr += 1
                else:
                    break
            chosen = latest_within or before_row


            # Seed = latest MSR up to this day (can be before month)
            seed_service_date = as_date(chosen.get("service_date")) if chosen else None
            seed_hours = cint(chosen.get("current_hours")) if chosen else 0
            seed_interval = (chosen.get("service_interval") or "") if chosen else ""
            seed_name = (chosen.get("name") or "") if chosen else ""
            seed_ref = seed_name

            # Carry the latest valid completed service forward.
            # A newer MSR inside the month automatically replaces this baseline
            # from its service date onward.
            date_of_previous_service = seed_service_date
            hours_previous_service = seed_hours
            last_service_interval = seed_interval
            msr_reference_number = seed_ref
            msr_record_name = seed_name

            # Persist the authoritative next service target from the latest
            # completed MSR available as of this specific day.
            planning_planned_hours = next_service_target_from_service_hours(seed_hours)
            planning_status, planning_hours_remaining = planning_status_for_hours(
                estimate_hours,
                planning_planned_hours,
            )
            planning_service_interval = (
                _fmt_hours(interval_due_at_hours(planning_planned_hours))
                if planning_planned_hours
                else ""
            )

            row = doc.append("service_schedule_child", {
                "date": d,
                "fleet_number": asset,
                "asset_category": a.get("asset_category"),
                "model": a.get("item_name") or a.get("item_code"),
                "start_hours": start_hours if start_hours else 0,
                "daily_estimated_hours_usage": daily_use_asset,
                "estimate_hours": estimate_hours,
                "date_of_previous_service": date_of_previous_service,
                "hours_previous_service": hours_previous_service or 0,
                "last_service_interval": last_service_interval,
                "msr_reference_number": msr_reference_number,
                "msr_record_name": msr_record_name,
                "oem_booking_date": 1 if oem_map.get((asset, d_iso)) else 0,
                "oem_booking_name": oem_map.get((asset, d_iso)) or "",
                "planning_status": planning_status,
                "planning_hours_remaining": planning_hours_remaining,
                "planning_planned_hours": planning_planned_hours,
                "planning_service_interval": planning_service_interval,
                "planning_flagged_on": d if planning_status else None,

            })

            rows_index[(asset, d_iso)] = row




    for asset in asset_list:
        recompute_planning_rows(
            [rows_index[(asset, d.isoformat())] for d in date_list], month_start
        )

    # OEM Booking flags: current + previous month window
    lookup_start = add_months(month_start, -1)
    recompute_oem_booking_flags(doc, lookup_start, month_end)

    doc.save()
    frappe.db.commit()
    return {"ok": True, "rows": len(doc.service_schedule_child)}

@frappe.whitelist()
def set_daily_usage_and_recompute(schedule_name, fleet_number, daily_usage):
    """Capture daily usage edits from HTML and recompute estimates + next service markers for that asset."""
    doc = frappe.get_doc("Service Schedule", schedule_name)
    doc.check_permission("write")
    if not doc.month:
        frappe.throw("Month is required.")
    _, _, month_start, month_end = parse_month_bounds(doc.month)

    daily_use = clamp_daily_usage(daily_usage or 0)

    rows = [r for r in doc.service_schedule_child if r.fleet_number == fleet_number]
    rows.sort(key=lambda r: getdate(r.date))

    prev_estimate = None
    prev_start_hours = None
    for r in rows:
        r.daily_estimated_hours_usage = daily_use
        start_hours = float(r.start_hours or 0)
        # keep MSR link fields stable (never None)
        r.msr_reference_number = str(r.msr_reference_number or "")
        r.msr_record_name = str(r.msr_record_name or "")

        # RULE:
        # Day 1: Est = Day 1 start_hours
        # Day 2..end:
        #   if previous day had start_hours -> Est = prev_start_hours + daily_use
        #   else -> Est = prev_estimate + daily_use
        if prev_estimate is None or getdate(r.date) == month_start:
            r.estimate_hours = start_hours
        else:
            if float(prev_start_hours or 0.0) > 0:
                r.estimate_hours = float(prev_start_hours) + float(daily_use)
            else:
                r.estimate_hours = float(prev_estimate) + float(daily_use)


        prev_estimate = float(r.estimate_hours or 0.0)
        prev_start_hours = start_hours

    recompute_planning_rows(rows, month_start)

    lookup_start = add_months(month_start, -1)
    recompute_oem_booking_flags(doc, lookup_start, month_end)

    doc.save()
    frappe.db.commit()
    return {"ok": True, "rows": len(rows)}


def select_schedule_snapshot_date(dates, month_label, today=None, requested=None):
    """Choose an available snapshot date within the selected schedule."""
    available = sorted({getdate(d) for d in dates if d})
    if not available:
        return None
    if requested:
        wanted = getdate(requested)
        if wanted not in available:
            frappe.throw("The selected date has no Service Schedule snapshot.")
        return wanted
    current = getdate(today or nowdate())
    _, _, start, end = parse_month_bounds(month_label)
    if start <= current <= end:
        return current if current in available else next(
            (d for d in reversed(available) if d <= current), available[0])
    return available[-1] if end < current else available[0]


@frappe.whitelist()
def get_service_schedule_context():
    """List readable monthly schedules for page defaults."""
    schedules = frappe.get_list("Service Schedule", fields=["name", "site", "month"],
        order_by="modified desc", limit_page_length=500)
    return schedules


@frappe.whitelist()
def get_service_schedule_snapshot(site, month, snapshot_date=None):
    """Return one persisted daily view; calculations remain in the DocType backend."""
    parse_month_bounds(month)
    names = frappe.get_all("Service Schedule", filters={"site": site, "month": month},
        pluck="name", limit_page_length=2)
    if len(names) > 1:
        frappe.throw("Multiple Service Schedules exist for this site and month.")
    if not names:
        return {"schedule_name": None, "dates": [], "snapshot_date": None, "rows": []}
    doc = frappe.get_doc("Service Schedule", names[0])
    doc.check_permission("read")
    dates = sorted({getdate(r.date) for r in doc.service_schedule_child if r.date})
    selected = select_schedule_snapshot_date(dates, month, requested=snapshot_date)
    rows = {}
    for row in doc.service_schedule_child:
        if selected and getdate(row.date) == selected and row.fleet_number:
            rows.setdefault(row.fleet_number, row.as_dict())
    return {"schedule_name": doc.name,
            "dates": [d.isoformat() for d in dates],
            "snapshot_date": selected.isoformat() if selected else None,
            "rows": [rows[name] for name in sorted(rows)]}


@frappe.whitelist()
def create_or_generate_service_schedule(site, month):
    """Create a missing monthly document once, then generate its saved child rows."""
    parse_month_bounds(month)
    names = frappe.get_all("Service Schedule", filters={"site": site, "month": month},
        pluck="name", limit_page_length=2)
    if len(names) > 1:
        frappe.throw("Multiple Service Schedules exist for this site and month.")
    if names:
        doc = frappe.get_doc("Service Schedule", names[0])
        doc.check_permission("write")
        name = doc.name
    else:
        if not frappe.has_permission("Service Schedule", "create"):
            frappe.throw("You do not have permission to create a Service Schedule.")
        doc = frappe.get_doc({"doctype": "Service Schedule", "site": site, "month": month})
        doc.insert()
        name = doc.name
    result = generate_schedule_backend(name)
    return {"schedule_name": name, **result}
