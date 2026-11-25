"""Historical Bell operating-hour retrieval and site shift scheduling."""

import hashlib
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import now_datetime
from redis.exceptions import LockError

from engineering.controllers.bell_client import BellClient, BellError

SETTINGS = "API Bell Settings"
READINGS = "Bell Operating Hours Reading"
TZ = ZoneInfo("Africa/Johannesburg")


def _settings():
    settings = frappe.get_doc(SETTINGS, SETTINGS)
    if not settings.enabled:
        raise BellError("Bell integration is disabled.")
    return settings


def _as_time(value):
    if isinstance(value, time):
        return value
    return time.fromisoformat(str(value))


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if value:
        return datetime.fromisoformat(str(value))
    return None


def _mapping_index(settings):
    result = {}
    for row in settings.machine_mappings or []:
        for field in ("pin", "serial_number"):
            value = (row.get(field) or "").strip().upper()
            if value:
                result[value] = row
    return result


def _shift_window(row, shift_date):
    start_time = _as_time(row.shift_start)
    end_time = _as_time(row.shift_end)
    start = datetime.combine(shift_date, start_time)
    end = datetime.combine(shift_date, end_time)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _scheduled_run(row, shift_date):
    pull_time = _as_time(row.pull_time)
    start_time = _as_time(row.shift_start)
    pull_date = shift_date + timedelta(days=1) if pull_time < start_time else shift_date
    return datetime.combine(pull_date, pull_time)


def _due_schedules(settings, now):
    due = []
    for row in settings.operating_hours_schedule or []:
        if not row.enabled or not row.site:
            continue

        for shift_date in (now.date(), now.date() - timedelta(days=1)):
            weekday = shift_date.weekday()
            category = (
                "Weekday" if weekday < 5
                else "Saturday" if weekday == 5
                else "Sunday"
            )
            if category != row.day_of_week:
                continue

            scheduled_at = _scheduled_run(row, shift_date)
            age = (now - scheduled_at).total_seconds()

            # Allow a short retry window if the previous minute was busy.
            if 0 <= age < 360:
                run_key = f"{row.name}|{scheduled_at.isoformat()}"
                if row.last_run_key != run_key:
                    due.append((row, shift_date, run_key, scheduled_at))

    return due


def _reading_key(asset, source_time):
    return hashlib.sha256(
        f"{asset}|{source_time.isoformat()}".encode()
    ).hexdigest()


def _store_machine(machine, mapping, schedule=None, shift_date=None, manual=False):
    asset = mapping.asset
    if not asset:
        return "unmapped"

    site = frappe.db.get_value("Asset", asset, "location")
    if not site:
        return "no_site"

    # Do not store a reading under a site the machine has already left.
    if schedule and site != schedule.site:
        return "site_changed"

    hours = machine.get("operating_hours")
    source_time = _as_datetime(machine.get("operating_hours_timestamp"))

    if hours is None or source_time is None:
        return "missing_measurement"

    if source_time.tzinfo:
        source_time = source_time.astimezone(TZ).replace(tzinfo=None)

    key = _reading_key(asset, source_time)

    if frappe.db.exists(READINGS, key):
        return "duplicate"

    retrieved = now_datetime()
    values = {
        "doctype": READINGS,
        "reading_key": key,
        "asset": asset,
        "site": site,
        "shift_date": shift_date or retrieved.date(),
        "day_of_week": shift_date.strftime("%A") if shift_date else retrieved.strftime("%A"),
        "shift": "Manual" if manual else schedule.shift,
        "operating_hours": hours,
        "source_measurement_timestamp": source_time,
        "retrieved_at": retrieved,
        "fleet_snapshot_timestamp": machine.get("fleet_snapshot_timestamp"),
        "source_checksum": hashlib.sha256(
            f"{asset}|{hours}|{source_time}".encode()
        ).hexdigest(),
    }

    if schedule:
        start, end = _shift_window(schedule, shift_date)
        values.update({
            "shift_start": start,
            "shift_end": end,
            "scheduled_pull_time": schedule.pull_time,
        })

    frappe.get_doc(values).insert(ignore_permissions=True)
    return "created"


def _pull(schedule_entries=None, manual=False):
    settings = _settings()

    # One Bell Fleet request supplies all mapped machines.
    snapshot = BellClient(settings).fetch_fleet()
    mappings = _mapping_index(settings)

    by_site = {}
    for entry in schedule_entries or []:
        row, shift_date, run_key, scheduled_at = entry
        by_site.setdefault(row.site, []).append(entry)

    counts = {
        "created": 0, "duplicate": 0, "unmapped": 0,
        "no_site": 0, "missing_measurement": 0,
        "site_changed": 0, "ambiguous_schedule": 0,
    }

    for machine in snapshot.machines:
        identifiers = [
            (machine.get(field) or "").strip().upper()
            for field in ("pin", "serial_number")
        ]
        mapping = next(
            (mappings[value] for value in identifiers if value in mappings),
            None,
        )

        if not mapping or not mapping.asset:
            counts["unmapped"] += 1
            continue

        site = frappe.db.get_value("Asset", mapping.asset, "location")
        if not site:
            counts["no_site"] += 1
            continue

        entries = by_site.get(site, []) if schedule_entries else []
        if schedule_entries and not entries:
            continue

        if len(entries) > 1:
            counts["ambiguous_schedule"] += 1
            continue

        entry = entries[0] if entries else None
        outcome = _store_machine(
            machine,
            mapping,
            schedule=entry[0] if entry else None,
            shift_date=entry[1] if entry else None,
            manual=manual,
        )
        counts[outcome] = counts.get(outcome, 0) + 1

    return {
        "ok": True,
        **counts,
        "machines_received": len(snapshot.machines),
        "fleet_snapshot_timestamp": snapshot.snapshot_timestamp,
        "retrieved_at": now_datetime(),
    }


def _mark_schedules(settings, entries, retrieved_at):
    for row, shift_date, run_key, scheduled_at in entries:
        row.last_run_key = run_key
        row.last_run_at = retrieved_at

    settings.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def pull_operating_hours_now():
    frappe.has_permission(SETTINGS, "write", throw=True)
    try:
        with frappe.cache.lock(
            "bell_operating_hours_manual", timeout=600, blocking_timeout=1
        ):
            result = _pull(manual=True)

        result["message"] = (
            f"Bell returned {result['machines_received']} machines. "
            f"{result['created']} new readings stored; "
            f"{result['duplicate']} duplicate readings skipped; "
            f"{result['unmapped']} unmapped machines."
        )
        return result
    except LockError:
        return {"ok": False, "message": "An operating-hours retrieval is already running."}
    except BellError as exc:
        return {"ok": False, "message": str(exc)}


def run_scheduled_retrieval():
    settings = frappe.get_doc(SETTINGS, SETTINGS)
    if not settings.enabled or not settings.operating_hours_schedule_enabled:
        return

    now = datetime.now(TZ).replace(second=0, microsecond=0)
    entries = _due_schedules(settings, now)
    if not entries:
        return

    # A single scheduled run may include multiple sites, but only one
    # applicable shift per site at the same pull time.
    sites = [entry[0].site for entry in entries]
    if len(sites) != len(set(sites)):
        frappe.log_error(
            "Multiple Bell shift schedules are due for the same site and minute.",
            "Bell Operating Hours Schedule",
        )
        return

    run_id = hashlib.sha256(
        "|".join(sorted(entry[2] for entry in entries)).encode()
    ).hexdigest()

    try:
        with frappe.cache.lock(
            f"bell_operating_hours_schedule_{run_id}",
            timeout=600,
            blocking_timeout=1,
        ):
            # Reload under lock so another worker cannot reuse stale markers.
            settings = frappe.get_doc(SETTINGS, SETTINGS)
            entries = _due_schedules(settings, now)
            if not entries:
                return

            result = _pull(schedule_entries=entries)
            if result.get("ok"):
                _mark_schedules(settings, entries, now_datetime())

    except LockError:
        return
    except BellError as exc:
        frappe.log_error(str(exc), "Bell Operating Hours Scheduled Retrieval")
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Bell Operating Hours Scheduled Retrieval",
        )
