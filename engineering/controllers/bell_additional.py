"""Additional Bell Equipment ISO 15143-3 telemetry."""

import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote, urljoin, urlparse
import xml.etree.ElementTree as ET

import frappe
import requests


SETTINGS = "API Bell Settings"
FAULT_DOCTYPE = "Bell Equipment Fault Codes"
FUEL_DOCTYPE = "Bell Equipment Fuel Consumption"

TOKEN_HOST = "sso.bellequipment.com"
FLEET_HOST = "b-fleet03.bellequipment.com"


class BellAdditionalError(Exception):
    pass


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _timestamp(value):
    if not value:
        raise BellAdditionalError("Bell measurement timestamp is missing.")

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        raise BellAdditionalError("Bell returned an invalid timestamp.") from None


def _credentials(settings):
    token_url = settings.token_url
    fleet_url = settings.fleet_url

    if urlparse(token_url).hostname != TOKEN_HOST:
        raise BellAdditionalError("Invalid Bell authentication URL.")

    if urlparse(fleet_url).hostname != FLEET_HOST:
        raise BellAdditionalError("Invalid Bell Fleet URL.")

    response = requests.post(
        token_url,
        data={
            "grant_type": "password",
            "username": settings.username.strip(),
            "password": settings.get_password("password"),
            "scope": settings.scope or "ISO_Exports",
        },
        auth=(
            settings.client_id.strip(),
            settings.get_password("client_secret"),
        ),
        timeout=60,
        allow_redirects=False,
    )

    if response.status_code != 200:
        raise BellAdditionalError(
            f"Bell authentication failed (HTTP {response.status_code})."
        )

    token = response.json().get("access_token")
    if not token:
        raise BellAdditionalError("Bell did not return an access token.")

    return token


def _links(root):
    result = {}

    for node in root:
        if _tag(node) == "Links":
            values = {_tag(child): child.text for child in node}
            if values.get("rel") and values.get("href"):
                result[values["rel"]] = values["href"]

    return result


def _fetch_events(settings, token, pin, metric, event_tag, start, end, allow_empty_404=False):
    base = settings.fleet_url.rstrip("/")
    url = (
        f"{base}/Equipment/{quote(pin, safe='')}/"
        f"{metric}/{start}/{end}"
    )

    visited = set()
    events = []

    for _ in range(100):
        parsed = urlparse(url)

        if parsed.scheme != "https" or parsed.hostname != FLEET_HOST:
            raise BellAdditionalError("Bell pagination URL is not approved.")

        if url in visited:
            raise BellAdditionalError("Bell pagination loop detected.")

        visited.add(url)

        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/xml",
            },
            timeout=max(int(settings.timeout or 30), 60),
            allow_redirects=False,
        )

        if response.status_code == 404 and allow_empty_404:
            return []

        if response.status_code != 200:
            raise BellAdditionalError(
                f"Bell {metric} request failed (HTTP {response.status_code})."
            )

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            raise BellAdditionalError(
                f"Bell returned invalid {metric} XML."
            ) from None

        for item in root:
            if _tag(item) == event_tag:
                events.append(
                    (
                        _timestamp(item.attrib.get("datetime")),
                        {
                            _tag(child): child.text
                            for child in item
                        },
                        ET.tostring(item, encoding="unicode"),
                    )
                )

        href = _links(root).get("next")
        if not href:
            return events

        url = urljoin(url, href)

    raise BellAdditionalError("Bell exceeded the 100-page safety limit.")


def _machine_mappings(settings):
    rows = [
        row for row in (settings.machine_mappings or [])
        if row.pin and row.asset
    ]

    if not rows:
        raise BellAdditionalError(
            "No mapped Bell machines found. Complete Asset Mapping first."
        )

    return rows


def _key(prefix, pin, values):
    raw = "|".join(str(value or "") for value in values)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{pin}-{digest}"


def _save_record(doctype, values):
    key = values["external_key"]
    existing = frappe.db.exists(doctype, {"external_key": key})

    if existing:
        doc = frappe.get_doc(doctype, existing)
        doc.update(values)
        doc.save(ignore_permissions=True)
        return "updated"

    if doctype == FUEL_DOCTYPE:
        title = values.get("record_title")
        if title and frappe.db.exists(doctype, title):
            values["record_title"] = f"{title} - {key[-6:]}"

    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    return "created"


def _identity(mapping):
    return {
        "asset": mapping.asset,
        "equipment_id": mapping.equipment_id,
        "pin": mapping.pin,
        "serial_number": mapping.serial_number,
        "oem": mapping.oem or "BELL",
        "model": mapping.model,
    }


def _set_status(kind, success, message, partial=False):
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    status = "Partial" if partial else ("Success" if success else "Failed")

    values = {
        f"last_{kind}_status": status,
        f"last_{kind}_message": message[:500],
    }

    if success or partial:
        values[f"last_{kind}_sync"] = now

    frappe.db.set_single_value(SETTINGS, values)
    frappe.clear_document_cache(SETTINGS, SETTINGS)


def _as_utc(value):
    if not value:
        return None
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _set_machine_status(mapping, kind, success, message, checked_at):
    values = {
        f"{kind}_status": "Reporting" if success else "Not Reporting",
        f"{kind}_last_checked": checked_at.replace(tzinfo=None),
        f"{kind}_last_error": "" if success else str(message)[:500],
    }

    if success:
        values[f"{kind}_last_successful_at"] = checked_at.replace(tzinfo=None)

    frappe.db.set_value(
        "Bell Machine Mapping",
        mapping.name,
        values,
        update_modified=False,
    )

    if kind == "fuel_consumption" and mapping.pin:
        frappe.db.set_value(
            FUEL_DOCTYPE,
            {"pin": mapping.pin},
            "retrieval_status",
            "Reporting" if success else "Not Reporting",
            update_modified=False,
        )


def _run(kind, scheduled=False, site_filter=None, schedule_entries=None):
    settings = frappe.get_single(SETTINGS)

    if not settings.enabled:
        return {"ok": False, "message": "Enable Bell API Settings first."}

    enabled_field = (
        "fault_codes_enabled"
        if kind == "fault_codes"
        else "fuel_consumption_enabled"
    )

    if not settings.get(enabled_field):
        return {"ok": False, "message": f"{kind} retrieval is disabled."}

    try:
        days = int(
            settings.get(
                "fault_codes_lookback_days"
                if kind == "fault_codes"
                else "fuel_consumption_lookback_days"
            ) or 30
        )

        if not 1 <= days <= 365:
            raise BellAdditionalError("Lookback period must be 1-365 days.")

        now = datetime.now(timezone.utc)
        initial_start = now - timedelta(days=days)
        mappings = _machine_mappings(settings)

        if site_filter is not None:
            mappings = [
                row for row in mappings
                if frappe.db.get_value("Asset", row.asset, "location") in site_filter
            ]
            if not mappings:
                return {
                    "ok": True,
                    "count": 0,
                    "message": "No mapped Bell machines at scheduled sites.",
                }

        schedule_by_site = {
            entry[0].site: entry
            for entry in (schedule_entries or [])
        }

        token = _credentials(settings)

        pending = []
        failures = []
        successful_machines = 0
        skipped_machines = 0

        for mapping in mappings:
            mapping_site = (
                frappe.db.get_value("Asset", mapping.asset, "location")
                if mapping.asset else None
            )
            schedule_entry = (
                schedule_by_site.get(mapping_site)
                if schedule_entries is not None else None
            )

            if schedule_entries is not None and not schedule_entry:
                continue

            if schedule_entry:
                schedule_row, shift_date, run_key, scheduled_at = schedule_entry
                shift_name = schedule_row.shift
                pull_time = str(schedule_row.pull_time)[:5]
            else:
                local_now = datetime.now(ZoneInfo("Africa/Johannesburg"))
                shift_date = local_now.date()
                shift_name = "Manual"
                pull_time = local_now.strftime("%H:%M")

            checked = _as_utc(mapping.get(f"{kind}_last_checked"))
            status = mapping.get(f"{kind}_status")

            # Do not repeatedly hammer machines already known to be failing.
            if (
                scheduled
                and status == "Not Reporting"
                and checked
                and (now - checked) < timedelta(hours=6)
            ):
                skipped_machines += 1
                continue

            successful_at = _as_utc(
                mapping.get(f"{kind}_last_successful_at")
            )

            if not successful_at and status == "Reporting":
                successful_at = checked

            if successful_at:
                overlap = (
                    timedelta(minutes=15)
                    if kind == "fault_codes"
                    else timedelta(hours=26)
                )
                machine_start = max(
                    successful_at - overlap,
                    initial_start,
                )
            else:
                machine_start = initial_start

            start = machine_start.strftime("%Y-%m-%dT%H:%M:%SZ")
            end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            try:
                if kind == "fault_codes":
                    events = _fetch_events(
                        settings, token, mapping.pin,
                        "CautionCodes", "CautionDescription",
                        start, end,
                        allow_empty_404=bool(successful_at),
                    )
                else:
                    events = _fetch_events(
                        settings, token, mapping.pin,
                        "FuelUsedInThePreceding24Hours", "FuelUsedLast24",
                        start, end,
                    )

                machine_pending = []
                identity = _identity(mapping)

                for timestamp, data, raw_xml in events:
                    checksum = hashlib.sha256(
                        raw_xml.encode("utf-8")
                    ).hexdigest()

                    if kind == "fault_codes":
                        code = (data.get("Identifier") or "").strip()
                        if not code:
                            raise BellAdditionalError(
                                "Fault without an identifier."
                            )

                        key = _key(
                            "FAULT", mapping.pin,
                            (code, timestamp.isoformat()),
                        )

                        values = {
                            **identity,
                            "external_key": key,
                            "fault_code": code,
                            "description": data.get("Description") or "",
                            "occurred_at": timestamp,
                            "retrieved_at": now.replace(tzinfo=None),
                            "query_start": machine_start.replace(tzinfo=None),
                            "query_end": now.replace(tzinfo=None),
                            "source_event_xml": raw_xml,
                            "source_checksum": checksum,
                        }
                        doctype = FAULT_DOCTYPE

                    else:
                        try:
                            consumed = float(data["FuelConsumed"])
                        except (ValueError, TypeError, KeyError):
                            raise BellAdditionalError(
                                "Invalid fuel consumption measurement."
                            ) from None

                        if consumed < 0:
                            raise BellAdditionalError(
                                "Negative fuel consumption measurement."
                            )

                        units = data.get("FuelUnits") or ""
                        key = _key(
                            "FUEL24", mapping.pin,
                            (timestamp.isoformat(),),
                        )

                        measurement_local = timestamp.replace(
                            tzinfo=timezone.utc
                        ).astimezone(ZoneInfo("Africa/Johannesburg"))

                        record_title = (
                            f"{mapping.asset} - {shift_date:%d-%m-%Y} - "
                            f"{shift_name} ({pull_time}) - "
                            f"{measurement_local:%H%M} - {key[-6:]}"
                        )

                        values = {
                            **identity,
                            "external_key": key,
                            "record_title": record_title,
                            "site": mapping_site,
                            "shift_date": shift_date,
                            "shift": shift_name,
                            "scheduled_pull_time": (
                                pull_time if schedule_entry else None
                            ),
                            "retrieval_status": "Reporting",
                            "fuel_consumed": consumed,
                            "fuel_units": units,
                            "measurement_timestamp": timestamp,
                            "retrieved_at": now.replace(tzinfo=None),
                            "query_start": machine_start.replace(tzinfo=None),
                            "query_end": now.replace(tzinfo=None),
                            "source_event_xml": raw_xml,
                            "source_checksum": checksum,
                        }
                        doctype = FUEL_DOCTYPE

                    machine_pending.append((doctype, values))

                pending.extend(machine_pending)
                successful_machines += 1
                _set_machine_status(mapping, kind, True, "", now)

            except Exception as error:
                _set_machine_status(mapping, kind, False, str(error), now)
                failures.append(
                    f"{mapping.equipment_id or mapping.pin}: {str(error)[:180]}"
                )

        if successful_machines == 0 and skipped_machines:
            return {
                "ok": True,
                "count": 0,
                "skipped_machines": skipped_machines,
                "message": "No machines due for retry. Existing reporting errors remain flagged.",
            }

        if successful_machines == 0:
            raise BellAdditionalError(
                "All eligible machines failed. No records imported. "
                + "; ".join(failures[:5])
            )

        frappe.db.savepoint("bell_additional_sync")

        try:
            created = 0
            updated = 0

            for doctype, values in pending:
                outcome = _save_record(doctype, values)
                created += outcome == "created"
                updated += outcome == "updated"

        except Exception:
            frappe.db.rollback(save_point="bell_additional_sync")
            raise

        label = "fault events" if kind == "fault_codes" else "fuel readings"
        message = (
            f"Retrieved {len(pending)} {label}. "
            f"{successful_machines}/{len(mappings)} machines successful. "
            f"{created} created; {updated} updated."
        )

        if skipped_machines:
            message += f" {skipped_machines} failed machines temporarily skipped."

        if failures:
            message += " Machine failures: " + "; ".join(failures[:5])

        _set_status(kind, not failures and not skipped_machines, message, partial=bool(failures or skipped_machines) and successful_machines > 0)

        return {
            "ok": not failures and not skipped_machines,
            "partial": bool(failures or skipped_machines),
            "count": len(pending),
            "created": created,
            "updated": updated,
            "machines": successful_machines,
            "failed_machines": len(failures),
            "skipped_machines": skipped_machines,
            "message": message,
        }

    except Exception as error:
        message = (
            str(error)
            if isinstance(error, BellAdditionalError)
            else f"Bell additional retrieval failed ({type(error).__name__})."
        )
        _set_status(kind, False, message)
        return {"ok": False, "message": message}


@frappe.whitelist(methods=["POST"])
def pull_fault_codes():
    frappe.has_permission(SETTINGS, "write", throw=True)
    return _run("fault_codes")


@frappe.whitelist(methods=["POST"])
def pull_fuel_consumption():
    frappe.has_permission(SETTINGS, "write", throw=True)
    return _run("fuel_consumption")


def _schedule_time(value):
    if hasattr(value, "hour"):
        return value
    return datetime.strptime(str(value)[:8], "%H:%M:%S").time()


def _due_fuel_schedules(settings, now):
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

            pull_time = _schedule_time(row.pull_time)
            start_time = _schedule_time(row.shift_start)

            pull_date = (
                shift_date + timedelta(days=1)
                if pull_time < start_time else shift_date
            )

            scheduled_at = datetime.combine(
                pull_date, pull_time
            ).replace(tzinfo=ZoneInfo("Africa/Johannesburg"))

            age = (now - scheduled_at).total_seconds()

            run_key = f"{row.name}|{scheduled_at.isoformat()}"

            if 0 <= age < 360 and row.last_fuel_run_key != run_key:
                due.append((row, shift_date, run_key, scheduled_at))

    return due


def run_scheduled_syncs():
    """Run Bell fault polling and the daily 18:00 SAST fuel pull."""
    settings = frappe.get_single(SETTINGS)

    if not settings.enabled:
        return

    lock_name = "bell_additional_telemetry_scheduler"
    locked = frappe.db.sql(
        "SELECT GET_LOCK(%s, 0)", (lock_name,)
    )

    if not locked or locked[0][0] != 1:
        return

    try:
        now_utc = datetime.now(timezone.utc)
        now_db = now_utc.replace(tzinfo=None)

        # Fault polling: never run the same cycle less than 320 seconds apart.
        if settings.fault_codes_enabled:
            last_run = _as_utc(
                frappe.db.get_single_value(
                    SETTINGS, "last_fault_codes_scheduled_at"
                )
            )
            interval = max(
                320,
                int(settings.fault_codes_interval_seconds or 320),
            )

            if not last_run or (now_utc - last_run).total_seconds() >= interval:
                frappe.db.set_single_value(
                    SETTINGS,
                    "last_fault_codes_scheduled_at",
                    now_db,
                    update_modified=False,
                )
                frappe.db.commit()

                result = _run("fault_codes", scheduled=True)
                frappe.db.commit()
                frappe.logger("bell_additional").info(
                    "Scheduled Bell fault retrieval: %s", result
                )

        # Fuel uses the same site/shift schedule as Operating Hours.
        if (
            settings.fuel_consumption_enabled
            and settings.operating_hours_schedule_enabled
        ):
            local_now = datetime.now(
                ZoneInfo("Africa/Johannesburg")
            ).replace(second=0, microsecond=0)

            due = _due_fuel_schedules(settings, local_now)

            if due:
                sites = {entry[0].site for entry in due}
                checked_at = datetime.now(timezone.utc).replace(tzinfo=None)

                # Reserve each shift before contacting Bell to prevent duplicates.
                for row, shift_date, run_key, scheduled_at in due:
                    frappe.db.set_value(
                        "Bell Operating Hours Schedule",
                        row.name,
                        {
                            "last_fuel_run_key": run_key,
                            "last_fuel_run_at": checked_at,
                        },
                        update_modified=False,
                    )

                frappe.db.commit()

                result = _run(
                    "fuel_consumption",
                    scheduled=True,
                    site_filter=sites,
                    schedule_entries=due,
                )
                frappe.db.commit()

                frappe.logger("bell_additional").info(
                    "Scheduled Bell fuel retrieval: %s", result
                )

        # Run operating-hours retrieval sequentially under the Bell scheduler.
        # This avoids two independent Bell jobs competing at the same time.
        from engineering.controllers.bell_operating_hours import (
            run_scheduled_retrieval,
        )
        run_scheduled_retrieval()

    finally:
        frappe.db.sql("SELECT RELEASE_LOCK(%s)", (lock_name,))
