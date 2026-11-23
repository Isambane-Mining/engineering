"""Bell Equipment ISO 15143-3 ERPNext integration."""

import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import suppress

import frappe
from frappe.utils import now_datetime
from redis.exceptions import LockError

from engineering.controllers.bell_client import BellClient, BellError


SETTINGS = "API Bell Settings"
RESULTS = "Bell Results"


def _settings(require_enabled=True):
    frappe.has_permission(SETTINGS, "write", throw=True)
    settings = frappe.get_doc(SETTINGS, SETTINGS)

    if require_enabled and not settings.enabled:
        frappe.throw("Bell integration is disabled. Enable API Bell Settings first.")

    return settings


def _status(ok, message):
    values = {
        "last_sync_timestamp": now_datetime(),
        "last_sync_status": "Success" if ok else "Failed",
        "last_sync_message": message,
    }

    if ok:
        values["last_successful_sync"] = now_datetime()

    frappe.db.set_single_value(SETTINGS, values)
    frappe.clear_document_cache(SETTINGS, SETTINGS)


def _machine_key(machine):
    pin = (machine.get("pin") or "").strip().upper()
    serial = (machine.get("serial_number") or "").strip().upper()

    if pin:
        return "PIN-" + pin
    if serial:
        return "SERIAL-" + serial

    raise BellError("Bell machine has no reliable identifier.")


def _daily_result_key(machine, mapping):
    day = datetime.now(
        ZoneInfo("Africa/Johannesburg")
    ).strftime("%Y%m%d")

    prefix = (mapping.asset or "").strip()

    if not prefix:
        prefix = "UNMAPPED-" + _machine_key(machine).split("-", 1)[-1]

    return f"{prefix}-{day}"


def _discover(machine, settings):
    pin = (machine.get("pin") or "").strip().upper()
    serial = (machine.get("serial_number") or "").strip().upper()

    rows = settings.machine_mappings or []

    by_pin = next(
        (r for r in rows if pin and (r.pin or "").upper() == pin), None
    )
    by_serial = next(
        (r for r in rows if serial and (r.serial_number or "").upper() == serial),
        None,
    )

    if by_pin and by_serial and by_pin.name != by_serial.name:
        raise BellError("Bell PIN and serial number point to different mappings.")

    row = by_pin or by_serial

    if row:
        if row.pin and pin and row.pin.upper() != pin:
            raise BellError("Bell PIN conflict. Review machine mapping.")
        if row.serial_number and serial and row.serial_number.upper() != serial:
            raise BellError("Bell serial number conflict. Review machine mapping.")
    else:
        row = settings.append("machine_mappings", {})

    # Refresh discovery information without changing a manually selected Asset.
    row.equipment_id = machine.get("equipment_id") or row.equipment_id
    row.pin = row.pin or pin or None
    row.serial_number = row.serial_number or serial or None
    row.oem = machine.get("oem")
    row.model = machine.get("model")
    row.last_seen = now_datetime()
    row.mapping_status = "Mapped" if row.asset else "Unmapped"

    return row


def _checksum(machine):
    raw = json.dumps(
        machine,
        sort_keys=True,
        ensure_ascii=False,
        default=lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value),
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _store_result(machine, mapping, raw_xml):
    key = _daily_result_key(machine, mapping)
    existing = frappe.db.exists(RESULTS, key)

    # Rename the previous PIN-based record instead of duplicating it.
    if not existing:
        legacy_key = _machine_key(machine)
        if frappe.db.exists(RESULTS, legacy_key):
            frappe.rename_doc(
                RESULTS, legacy_key, key, force=True
            )
            existing = key

    doc = (
        frappe.get_doc(RESULTS, existing)
        if existing else frappe.new_doc(RESULTS)
    )

    running = machine.get("engine_running")
    engine_status = (
        "Running" if running == 1
        else "Stopped" if running == 0
        else None
    )

    values = {
        "external_key": key,
        "equipment_id": machine.get("equipment_id"),
        "pin": machine.get("pin"),
        "serial_number": machine.get("serial_number"),
        "oem": machine.get("oem"),
        "model": machine.get("model"),
        "asset": mapping.asset,
        "mapping": mapping.name,
        "mapping_status": mapping.mapping_status,
        "unit_install_timestamp": machine.get("unit_install_timestamp"),
        "fleet_snapshot_timestamp": machine.get("fleet_snapshot_timestamp"),
        "fetched_at": now_datetime(),
        "operating_hours": machine.get("operating_hours"),
        "operating_hours_timestamp": machine.get("operating_hours_timestamp"),
        "idle_hours": machine.get("idle_hours"),
        "idle_hours_timestamp": machine.get("idle_hours_timestamp"),
        "load_count": machine.get("load_count"),
        "load_count_timestamp": machine.get("load_count_timestamp"),
        "payload": machine.get("payload"),
        "payload_units": machine.get("payload_units"),
        "payload_timestamp": machine.get("payload_timestamp"),
        "fuel_consumed": machine.get("fuel_consumed"),
        "fuel_units": machine.get("fuel_units"),
        "fuel_consumed_timestamp": machine.get("fuel_consumed_timestamp"),
        "fuel_remaining": machine.get("fuel_remaining"),
        "fuel_remaining_timestamp": machine.get("fuel_remaining_timestamp"),
        "def_remaining": machine.get("def_remaining"),
        "def_tank_capacity_units": machine.get("def_tank_capacity_units"),
        "def_remaining_timestamp": machine.get("def_remaining_timestamp"),
        "odometer": machine.get("odometer"),
        "odometer_units": machine.get("odometer_units"),
        "odometer_timestamp": machine.get("odometer_timestamp"),
        "latitude": machine.get("latitude"),
        "longitude": machine.get("longitude"),
        "location_timestamp": machine.get("location_timestamp"),
        "engine_number": machine.get("engine_number"),
        "engine_running": engine_status,
        "engine_status_timestamp": machine.get("engine_status_timestamp"),
        "raw_xml": raw_xml,
        "source_checksum": _checksum(machine),
    }

    doc.update(values)

    if existing:
        doc.save(ignore_permissions=True)
        outcome = "updated"
    else:
        doc.insert(ignore_permissions=True)
        outcome = "created"

    # Explicitly preserve the original XML source response.
    frappe.db.set_value(
        RESULTS,
        doc.name,
        "raw_xml",
        raw_xml,
        update_modified=False,
    )

    return outcome


def _run(store_results):
    settings = _settings()

    try:
        lock_key = frappe.cache.make_key("bell_manual_sync")

        with frappe.cache.lock(
            lock_key,
            timeout=600,
            blocking_timeout=1,
        ):
            snapshot = BellClient(settings).fetch_fleet()

            savepoint_created = False

            try:
                frappe.db.savepoint("bell_sync")
                savepoint_created = True

                # Reload after HTTP so manual Asset selections are preserved.
                settings = frappe.get_doc(SETTINGS, SETTINGS, for_update=True)

                keys = [_machine_key(m) for m in snapshot.machines]
                if len(keys) != len(set(keys)):
                    raise BellError("Bell returned duplicate machine identifiers.")

                mappings = [
                    _discover(machine, settings)
                    for machine in snapshot.machines
                ]

                settings.save(ignore_permissions=True)

                created = 0
                updated = 0

                if store_results:
                    for machine, mapping in zip(snapshot.machines, mappings):
                        outcome = _store_result(
                            machine,
                            mapping,
                            snapshot.raw_xml,
                        )
                        created += outcome == "created"
                        updated += outcome == "updated"

                unmapped = sum(not row.asset for row in mappings)

                message = (
                    f"Fetched {len(snapshot.machines)} Bell machines. "
                    f"{unmapped} unmapped."
                )

                if store_results:
                    message += (
                        f" {created} results created; {updated} updated."
                    )
                    _status(True, message)

                return {
                    "ok": True,
                    "count": len(snapshot.machines),
                    "unmapped": unmapped,
                    "created": created,
                    "updated": updated,
                    "message": message,
                }

            except Exception:
                if savepoint_created:
                    frappe.db.rollback(save_point="bell_sync")
                raise

    except LockError:
        return {
            "ok": False,
            "message": "A Bell fetch or sync is already running. Try again shortly.",
        }

    except BellError as error:
        message = str(error)
        if store_results:
            with suppress(Exception):
                _status(False, message)
        return {"ok": False, "message": message}

    except Exception as error:
        message = f"Bell operation failed ({type(error).__name__})."
        if store_results:
            with suppress(Exception):
                _status(False, message)
        with suppress(Exception):
            frappe.log_error(message=message, title="Bell API Integration")
        return {"ok": False, "message": message}


@frappe.whitelist(methods=["POST"])
def test_connection():
    settings = _settings(require_enabled=False)

    try:
        snapshot = BellClient(settings).fetch_fleet()
        return {
            "ok": True,
            "count": len(snapshot.machines),
            "message": (
                f"Bell connection successful. "
                f"{len(snapshot.machines)} machines returned."
            ),
        }
    except BellError as error:
        return {"ok": False, "message": str(error)}
    except Exception as error:
        return {
            "ok": False,
            "message": f"Bell connection failed ({type(error).__name__}).",
        }


@frappe.whitelist(methods=["POST"])
def fetch_fleet():
    return _run(store_results=False)


@frappe.whitelist(methods=["POST"])
def sync_now():
    return _run(store_results=True)


@frappe.whitelist(methods=["POST"])
def pull_fault_codes():
    from engineering.controllers.bell_additional import pull_fault_codes as pull
    return pull()


@frappe.whitelist(methods=["POST"])
def pull_fuel_consumption():
    from engineering.controllers.bell_additional import pull_fuel_consumption as pull
    return pull()
