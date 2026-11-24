"""Shared manual sync and LAB-only hourly scheduling for Kobelco."""
import hashlib
import json
import logging
import re
from contextlib import suppress
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


def _snapshot_record_name(machine, mapping, raw_json, fetched_at):
    """Build a readable, deterministic Kobelco result identifier."""
    value = machine.get("snapshot_timestamp") or fetched_at

    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))

        if not isinstance(value, datetime):
            raise ValueError("Invalid timestamp type")

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)

        timestamp = value.strftime("%Y%m%dT%H%M%SZ")
    except (TypeError, ValueError, OverflowError):
        raise KobelcoError(
            "Invalid Kobelco snapshot timestamp; result identifier cannot be generated."
        ) from None

    # The ERPNext Asset document name is our fleet number.
    fleet_number = str(getattr(mapping, "asset", None) or "").strip()
    fleet_number = fleet_number or "UNMAPPED"

    # Hash the canonical individual machine JSON, not the entire Fleet response.
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()[:8].upper()

    return f"KOB-{fleet_number}-{timestamp}-{digest}"


def _store_snapshot(raw, machine, mapping, raw_response=None, fleet_version=None):
    # Canonical machine JSON provides deterministic snapshot identity.
    raw_json = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    # Preserve compatibility with historical records named using the
    # original SHA-256(serial + machine JSON) identity.
    legacy_key = hashlib.sha256(
        (machine["serial_number"] + "\n" + raw_json).encode()
    ).hexdigest()
    if frappe.db.exists(RESULTS, legacy_key):
        return False

    # Also deduplicate readable-name records when the API has no source
    # timestamp and the fetch-time fallback would otherwise generate a new ID.
    if not machine.get("snapshot_timestamp") and frappe.db.exists(RESULTS, {
        "serial_number": machine["serial_number"],
        "raw_json": raw_json,
    }):
        return False

    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    key = _snapshot_record_name(machine, mapping, raw_json, fetched_at)

    existing = frappe.db.exists(RESULTS, key)
    if existing:
        existing_raw = frappe.db.get_value(RESULTS, existing, "raw_json")
        if existing_raw == raw_json:
            return False
        raise KobelcoError(
            "Kobelco snapshot identifier collision; existing result was not changed."
        )

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
    # Logging failures must not escape with a secret-bearing exception context.
    with suppress(Exception):
        logger = frappe.logger("kobelco", with_more_info=False, allow_site=True)
        logger.setLevel(logging.INFO)
        logger.info("Kobelco %s: %s", "sync" if store_results else "discovery", message)


_DATABASE_ERRORS = {
    1205: "Database lock-wait timeout.",
    1213: "Database deadlock.",
    1062: "Database duplicate-key conflict.",
    2002: "Database connection unavailable.",
    2003: "Database connection unavailable.",
    2006: "Database connection closed.",
    2013: "Database connection lost.",
}
_SAFE_ERRORS = {
    "Authentication failed. Check the Kobelco username and password.",
    "Kobelco connection failed or timed out.",
    "Kobelco username is required.", "Kobelco password is required.",
    "Kobelco returned invalid JSON.",
    "Kobelco serial/PIN conflict. Review Machine Mapping before syncing.",
    "Kobelco PIN belongs to a different serial. Review Machine Mapping.",
    "A Kobelco fetch or sync is already running. Try again shortly.",
}


def _diagnostic(error, stage, attempt_timestamp):
    """Allowlisted metadata only: never serialize exception text/args/locals.

    Frappe wraps a driver's OperationalError in QueryTimeoutError/DeadlockError.
    Traverse causes and wrapped exceptions to recover ONLY recognized numeric
    codes. Unrecognized codes and arbitrary exception descriptions stay private.
    """
    code, pending, visited = None, [error], set()
    while pending and len(visited) < 10:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        args = current.args
        module = type(current).__module__
        is_database = (isinstance(current, (frappe.QueryTimeoutError, frappe.QueryDeadlockError))
                       or module in ("pymysql", "MySQLdb")
                       or module.startswith(("pymysql.", "MySQLdb.")))
        if is_database and args and type(args[0]) is int and args[0] in _DATABASE_ERRORS:
            code = args[0]
            break
        pending.extend(arg for arg in args if isinstance(arg, BaseException))
        if current.__cause__:
            pending.append(current.__cause__)
    name = type(error).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", name):
        name = "Exception"
    description = _DATABASE_ERRORS.get(code, "Unexpected internal error; review the processing stage and exception class.")
    if code is None and isinstance(error, frappe.QueryTimeoutError):
        description = "Database query timed out."
    elif code is None and isinstance(error, frappe.QueryDeadlockError):
        description = "Database deadlock."
    elif code is None and isinstance(error, LockError):
        description = "A Kobelco fetch or sync is already running. Try again shortly." if stage == "acquire_sync_lock" else "Kobelco sync lock could not be retained."
    elif code is None and isinstance(error, KobelcoError):
        text = str(error)
        description = text if text in _SAFE_ERRORS or re.fullmatch(r"Kobelco returned HTTP [1-5][0-9]{2}\.", text) else "Kobelco request or machine data validation failed."
    return {"stage": stage, "exception_class": name, "database_error_code": code,
            "description": description, "attempt_timestamp_utc": attempt_timestamp}


def _safe_rollback(save_point=None):
    """Never commit an uncertain transaction or leak a secondary exception.

    If rollback fails, close/discard that connection. Detaching it also stops
    Frappe's HTTP transaction finalizer from committing partial import work.
    Restore a fresh safe connection when possible for DB-backed monitoring.
    Otherwise retain safe file/debug diagnostics and finish with a sanitized
    failure; native job accounting cannot persist while the DB is unavailable.
    """
    db = frappe.db
    if not db:
        return False
    try:
        if save_point:
            db.rollback(save_point=save_point)
        else:
            db.rollback()
        return True
    except Exception:
        with suppress(Exception):
            db.close()
        frappe.local.db = None
        try:
            # New DB object and transaction only; never reuse the uncertain
            # connection or elevate the current user. Native job failure logging
            # can then work if the database is reachable again.
            frappe.connect(set_admin_as_user=False)
            frappe.db.connect()
            return True
        except Exception:
            with suppress(Exception):
                frappe.db.close()
            frappe.local.db = None
            return False


def _failure_result(error, stage, attempt_timestamp, store_results=True, persist=True):
    diagnostic = _diagnostic(error, stage, attempt_timestamp)
    code = diagnostic["database_error_code"]
    label = diagnostic["exception_class"] + (f"/{code}" if code is not None else "")
    message = f"Kobelco import failed at {stage} ({label}): {diagnostic['description']}"
    payload = json.dumps(diagnostic, sort_keys=True)
    _log_attempt("Failed. " + payload, store_results)
    frappe.debug_log.append("Kobelco diagnostic: " + payload)
    result = {"ok": False, "message": message, "diagnostic": diagnostic}
    if not persist or not frappe.local.db:
        return result
    # Monitoring failures must not replace the original sanitized diagnostic or
    # let an original exception/its locals escape to the scheduler's traceback.
    try:
        _status(False, message)
    except Exception:
        _safe_rollback()
        _log_attempt("Last Sync status could not be persisted. " + payload, store_results)
    if not frappe.local.db:
        return result
    try:
        frappe.db.savepoint("kobelco_error_log")
        # Deliberately do not use frappe.log_error: its automatic request/job
        # metadata and external error capture can include sensitive context.
        frappe.get_doc({"doctype": "Error Log", "method": "Kobelco Sync Failure",
                        "error": payload}).insert(ignore_permissions=True)
    except Exception:
        _safe_rollback("kobelco_error_log")
        _log_attempt("Error Log could not be persisted. " + payload, store_results)
    return result


def _run(settings, store_results):
    attempt_timestamp = datetime.now(timezone.utc).isoformat()
    stage = "acquire_sync_lock"
    _log_attempt("Started", store_results)
    # Serialize manual and scheduled API operations. Parent modified checks and child unique
    # indexes protect inline mapping saves. Roll back the whole batch on failure.
    try:
        with frappe.cache.lock(frappe.cache.make_key("kobelco_manual_sync"), timeout=7500, blocking_timeout=1):
            savepoint_created = False
            try:
                stage = "create_sync_savepoint"
                frappe.db.savepoint("kobelco_sync")
                savepoint_created = True
                stage = "initialize_client"
                client = KobelcoClient(settings)
                stage = "fetch_fleet"
                rows = client.fetch_fleet()
                stage = "normalize_telemetry"
                machines = [normalize_equipment(row, rows.snapshot_time_for(i) if isinstance(rows, FleetSnapshot) else None)
                            for i, row in enumerate(rows)]
                # Reload after HTTP so Asset choices saved during the request are
                # preserved. Frappe's normal modified check rejects stale saves.
                stage = "lock_settings"
                settings = _settings(for_update=True)
                stage = "update_mappings"
                mappings = [_discover(machine, settings) for machine in machines]
                settings.flags.kobelco_discovery = True
                stage = "save_settings"
                settings.save()
                stage = "store_snapshots"
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
                    stage = "update_sync_status"
                    _status(True, message)
                _log_attempt("Success. " + message, store_results)
                return {"ok": True, "count": len(rows), "unmapped": unmapped,
                        "created": created, "skipped": skipped, "pages": pages, "message": message}
            except Exception as error:
                # InnoDB deadlocks roll back the entire transaction, invalidating
                # every savepoint. Other failures retain the request transaction.
                rolled_back = _safe_rollback(None if not savepoint_created or isinstance(error, frappe.QueryDeadlockError) else "kobelco_sync")
                return _failure_result(error, stage, attempt_timestamp, store_results, persist=rolled_back)
    except Exception as error:
        # Covers lock-service/lock-release failures as well as acquisition
        # contention, retaining the original class without raw exception text.
        # No import transaction has started if acquisition failed; preserve the
        # caller's existing transaction, as the shared-lock path always did.
        rolled_back = bool(frappe.local.db) if stage == "acquire_sync_lock" else _safe_rollback()
        return _failure_result(error, stage, attempt_timestamp, store_results, persist=rolled_back)


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
    attempt_timestamp = datetime.now(timezone.utc).isoformat()
    stage = "load_settings"
    try:
        if not frappe.db.get_single_value(SETTINGS, "enabled"):
            return {"ok": True, "skipped": "disabled"}
        stage = "sync_dispatch"
        result = sync_now()
    except Exception as error:
        # Do not let worker traceback-with-locals capture an original exception,
        # HTTP response, request URL or settings document containing credentials.
        rolled_back = _safe_rollback()
        result = _failure_result(error, stage, attempt_timestamp, persist=rolled_back)
    if frappe.local.db:
        try:
            frappe.db.commit()
        except Exception as error:
            rolled_back = _safe_rollback()
            result = _failure_result(error, "commit_sync_status", attempt_timestamp, persist=rolled_back)
    frappe.debug_log.append("Kobelco hourly sync: " + json.dumps(result))
    if not result["ok"]:
        # Raised outside the handler: original traceback/context is discarded.
        raise KobelcoError(result["message"]) from None
    return result


def sanitize_scheduled_job_log(doc, method=None):
    """Keep Kobelco's native Failed log free of traceback locals.

    Frappe writes a contextual traceback after the method returns. Replace that
    Details value in the same transaction with our structured diagnostics. Only
    this method's Failed records are touched; other jobs retain native behavior.
    """
    if frappe.local.site != LAB_SITE or doc.status != "Failed":
        return
    scheduled_method = frappe.db.get_value("Scheduled Job Type", doc.scheduled_job_type, "method", cache=True)
    if scheduled_method != "engineering.controllers.kobelco.run_hourly_sync":
        return
    details = "Kobelco sync failed. See sanitized diagnostics in Debug Log."
    prefix = "Kobelco hourly sync: "
    for line in reversed((doc.debug_log or "").splitlines()):
        if not line.startswith(prefix):
            continue
        try:
            diagnostic = json.loads(line[len(prefix):])["diagnostic"]
            details = json.dumps({key: diagnostic[key] for key in (
                "stage", "exception_class", "database_error_code", "description", "attempt_timestamp_utc")}, sort_keys=True)
        except (ValueError, KeyError, TypeError):
            pass
        break
    if doc.details != details:
        # Direct DB update avoids recursively invoking on_change. Native log
        # commit happens afterward, so no contextual traceback remains stored.
        frappe.db.set_value("Scheduled Job Log", doc.name, "details", details, update_modified=False)
        doc.details = details
