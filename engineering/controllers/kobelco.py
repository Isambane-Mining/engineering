"""Shared manual sync and LAB-only hourly scheduling for Kobelco."""
import hashlib
import json
import logging
from datetime import datetime, timezone

import frappe
from frappe.utils import now_datetime
from redis.exceptions import LockError

from engineering.controllers.kobelco_client import (
    FleetSnapshot, KobelcoClient, KobelcoError, NUMERIC_FIELDS, normalize_equipment,
)

SETTINGS = "API Kobelco Settings"
RESULTS = "Kobelco Results"
LAB_SITE = "juan.isambane.co.za"



def _settings(require_enabled=True, for_update=False):
    frappe.has_permission(SETTINGS, "write", throw=True)
    settings = frappe.get_doc(SETTINGS, SETTINGS, for_update=for_update)
    if require_enabled and not settings.enabled:
        frappe.throw("Kobelco integration is disabled. Enable it in API Kobelco Settings first.")
    return settings


def _status(ok, message):
    values = {"last_sync_timestamp": now_datetime(), "last_sync_status": "Success" if ok else "Failed",
              "last_sync_message": message}
    if ok:
        values["last_successful_sync"] = now_datetime()
    frappe.db.set_single_value(SETTINGS, values)
    frappe.clear_document_cache(SETTINGS, SETTINGS)


def _discover(machine, settings):
    serial, pin = machine["serial_number"], machine["pin"]
    row = next((row for row in settings.machine_mappings or [] if row.serial_number == serial), None)
    if row and row.pin and pin and row.pin != pin:
        raise KobelcoError("Kobelco serial/PIN conflict. Review Machine Mapping before syncing.")
    if pin and any(other.pin == pin and other.serial_number != serial for other in settings.machine_mappings or []):
        raise KobelcoError("Kobelco PIN belongs to a different serial. Review Machine Mapping.")
    if row is None:
        row = settings.append("machine_mappings", {"serial_number": serial})
    # Refresh discovery fields only: retain row identity and the selected Asset.
    row.update({"pin": row.pin or pin, "oem": machine["oem"], "model": machine["model"],
                "last_seen": now_datetime()})
    return row


def _store_snapshot(raw, machine, mapping, raw_response=None, fleet_version=None):
    # Identity ignores fetch time so repeat pulls of the same source observation
    # do not manufacture a new result. Source telemetry and timestamps are retained.
    raw_json = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    key = hashlib.sha256((machine["serial_number"] + "\n" + raw_json).encode()).hexdigest()
    if frappe.db.exists(RESULTS, key):
        return False
    doc = frappe.new_doc(RESULTS)
    doc.update(machine)
    doc.update({"mapping": mapping.name, "asset": mapping.asset,
                "mapping_status": mapping.mapping_status, "snapshot_key": key,
                "raw_json": raw_json, "raw_response": raw_response, "fleet_version": fleet_version,
                "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None), "telemetry_version": 2})
    for field in NUMERIC_FIELDS:
        doc.set(field + "_available", int(machine.get(field) is not None))
    doc.flags.kobelco_import = True
    doc.insert(ignore_permissions=True)
    return True


def _log_attempt(message, store_results=True):
    # Only locally constructed counts/status and sanitized errors. Never include
    # settings, response bodies, credentials, URLs or exception tracebacks.
    logger = frappe.logger("kobelco", with_more_info=False, allow_site=True)
    logger.setLevel(logging.INFO)
    logger.info("Kobelco %s: %s", "sync" if store_results else "discovery", message)


def _run(settings, store_results):
    _log_attempt("Started", store_results)
    # Serialize manual and scheduled API operations. Parent modified checks and child unique
    # indexes protect inline mapping saves. Roll back the whole batch on failure.
    try:
        with frappe.cache.lock(frappe.cache.make_key("kobelco_manual_sync"), timeout=7500, blocking_timeout=1):
            frappe.db.savepoint("kobelco_sync")
            try:
                rows = KobelcoClient(settings).fetch_fleet()
                machines = [normalize_equipment(row, rows.snapshot_time_for(i) if isinstance(rows, FleetSnapshot) else None)
                            for i, row in enumerate(rows)]
                # Reload after HTTP so Asset choices saved during the request are
                # preserved. Frappe's normal modified check rejects stale saves.
                settings = _settings(for_update=True)
                mappings = [_discover(machine, settings) for machine in machines]
                settings.flags.kobelco_discovery = True
                settings.save()
                created, skipped, unmapped = 0, 0, 0
                for index, (raw, machine, mapping) in enumerate(zip(rows, machines, mappings)):
                    unmapped += int(not mapping.asset)
                    if store_results:
                        if _store_snapshot(raw, machine, mapping,
                                           rows.raw_response_for(index) if isinstance(rows, FleetSnapshot) else None,
                                           rows.version_for(index) if isinstance(rows, FleetSnapshot) else None):
                            created += 1
                        else:
                            skipped += 1
                pages = len(rows.pages) if isinstance(rows, FleetSnapshot) else 1
                message = f"Fetched {len(rows)} machines across {pages} page(s); {unmapped} unmapped."
                if store_results:
                    message += f" {created} snapshots created; {skipped} unchanged."
                # Fetch Fleet is discovery, not a telemetry sync; leave the last
                # sync audit intact on successful discovery.
                if store_results:
                    _status(True, message)
                _log_attempt("Success. " + message, store_results)
                return {"ok": True, "count": len(rows), "unmapped": unmapped,
                        "created": created, "skipped": skipped, "pages": pages, "message": message}
            except Exception as error:
                # InnoDB deadlocks roll back the entire transaction, invalidating
                # every savepoint. Other failures retain the request transaction.
                if isinstance(error, frappe.QueryDeadlockError):
                    frappe.db.rollback()
                else:
                    frappe.db.rollback(save_point="kobelco_sync")
                message = str(error) if isinstance(error, KobelcoError) else "Kobelco import failed. Check configuration and machine mappings."
                _status(False, message)
                _log_attempt("Failed. " + message, store_results)
                return {"ok": False, "message": message}
    except LockError:
        message = "A Kobelco fetch or sync is already running. Try again shortly."
        _status(False, message)
        _log_attempt("Skipped. " + message, store_results)
        return {"ok": False, "message": message}


@frappe.whitelist(methods=["POST"])
def test_connection():
    settings = _settings(require_enabled=False)
    try:
        rows = KobelcoClient(settings).fetch_fleet()
        for index, row in enumerate(rows):
            normalize_equipment(row, rows.snapshot_time_for(index) if isinstance(rows, FleetSnapshot) else None)
        return {"ok": True, "count": len(rows), "pages": len(rows.pages) if isinstance(rows, FleetSnapshot) else 1,
                "message": f"Connection successful. {len(rows)} machines returned."}
    except KobelcoError as error:
        return {"ok": False, "message": str(error)}


@frappe.whitelist(methods=["POST"])
def fetch_fleet():
    return _run(_settings(), store_results=False)


@frappe.whitelist(methods=["POST"])
def sync_now():
    return _run(_settings(), store_results=True)


def run_hourly_sync():
    """Frappe hourly entry point. No remote calls or settings reads outside LAB.

    ScheduledJobType.execute isolates failures and records them in Scheduled Job
    Log. Persist the attempt before raising a sanitized failure, otherwise its
    rollback would erase last-sync monitoring. Do not whitelist this wrapper.
    """
    if frappe.local.site != LAB_SITE:
        return {"ok": True, "skipped": "not_lab"}
    if not frappe.db.get_single_value(SETTINGS, "enabled"):
        return {"ok": True, "skipped": "disabled"}
    try:
        result = sync_now()
    except Exception:
        # Do not let worker traceback-with-locals capture an original exception,
        # HTTP response, request URL or settings document containing credentials.
        frappe.db.rollback()
        result = {"ok": False, "message": "Kobelco scheduled sync failed. Check configuration and database availability."}
        _status(False, result["message"])
        _log_attempt("Failed. " + result["message"])
    frappe.debug_log.append("Kobelco hourly sync: " + json.dumps(result))
    frappe.db.commit()
    if not result["ok"]:
        # Raised outside the handler: original traceback/context is discarded.
        raise KobelcoError(result["message"]) from None
    return result
