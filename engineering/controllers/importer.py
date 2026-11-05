# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import hashlib
import hmac
import json

import frappe
import requests
from frappe.utils import add_to_date, get_datetime, now, now_datetime


RESULT_ROW_FIELDS = (
    "sampno", "bottleno", "customer", "site", "machine", "component",
    "profileid", "status", "sampledate", "registerdate", "machread",
    "oilread", "perwater", "fueldilution", "oilsupplier", "oilbrand",
    "samp_taker", "commentstext", "actiontext", "feedbacktext", "tan",
    "tbn", "fe", "ag", "al", "ca", "cr", "cu", "mg", "na", "ni",
    "pb", "si", "sn", "p", "b", "ba", "mo", "v", "zn", "ti",
    "v40", "v100", "oxi", "soot", "iso4", "iso6", "iso14", "pq",
)


def _norm(value):
    return (value or "").strip()


def _key(value):
    return (value or "").strip().lower()


def _to_float(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_int(value):
    if value in (None, "", "null"):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _json_default(value):
    """Make checksums safe for API JSON and Frappe date objects on retry."""
    return str(value)


def _checksum(row):
    raw = json.dumps(
        row, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), default=_json_default,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _safe_link(doctype, value):
    value = _norm(value)
    if not value:
        return None
    return value if frappe.db.exists(doctype, value) else None


def _row_from_wearcheck_result(doc):
    return {fieldname: getattr(doc, fieldname, None) for fieldname in RESULT_ROW_FIELDS}


def _get_settings():
    return frappe.get_single("API Wearcheck Settings")


def _get_mapping(settings=None):
    settings = settings or _get_settings()
    mapping = {"Company": {}, "Location": {}, "Asset": {}}
    for row in settings.get("table_jqnq") or []:
        item_type = _norm(getattr(row, "item_type", ""))
        json_value = _key(getattr(row, "json_value", ""))
        frappe_value = _norm(getattr(row, "frappe_value", ""))
        if item_type and json_value and frappe_value:
            mapping.setdefault(item_type, {})[json_value] = frappe_value
    return mapping


def ensure_machine_mapping_rows(machines, settings=None):
    """Add unseen machine identifiers to the settings mapping review table.

    Existing JSON Values are respected even if their mapping columns are blank.
    Comparisons match the importer's existing case-insensitive lookup.
    Only JSON Value is populated on newly discovered rows.
    """
    settings = settings or _get_settings()
    existing = {
        _key(row.json_value)
        for row in (settings.get("table_jqnq") or [])
        if _key(row.json_value)
    }
    added = 0
    for machine in machines:
        value = _norm(machine)
        key = _key(value)
        if not key or key in existing:
            continue
        settings.append("table_jqnq", {
            "json_value": value,
            "item_type": "",
            "frappe_value": "",
        })
        existing.add(key)
        added += 1
    if added:
        settings.save(ignore_permissions=True)
    return added


def _schedule_interval_kwargs(schedule):
    schedule = _norm(schedule) or "Hourly"
    if schedule == "Hourly":
        return {"hours": 1}
    if schedule == "Daily":
        return {"days": 1}
    if schedule == "Weekly":
        return {"days": 7}
    return {"hours": 1}


def _is_sync_due(settings=None):
    settings = settings or _get_settings()
    if not getattr(settings, "enabled", 1):
        return False, "disabled"
    schedule = _norm(getattr(settings, "wearcheck_sync_schedule", "")) or "Hourly"
    last_attempt = getattr(settings, "last_wearcheck_sync_attempt", None)
    if not last_attempt:
        return True, "no previous sync attempt"
    last_attempt_dt = get_datetime(last_attempt)
    next_due = add_to_date(last_attempt_dt, **_schedule_interval_kwargs(schedule))
    if now_datetime() >= next_due:
        return True, f"{schedule} sync due"
    return False, f"{schedule} sync not due until {next_due}"


def _set_settings_sync_attempt(success=False, error=None):
    settings = _get_settings()
    meta = frappe.get_meta("API Wearcheck Settings")
    updates = {"last_wearcheck_sync_attempt": now()}
    if success:
        updates["last_wearcheck_sync_success"] = now()
        updates["last_wearcheck_sync_error"] = ""
    elif error:
        updates["last_wearcheck_sync_error"] = str(error)
    for fieldname, value in updates.items():
        if meta.has_field(fieldname):
            settings.set(fieldname, value)
    settings.save(ignore_permissions=True)
    frappe.db.commit()


def sync_wearcheck_rows(rows, force=False):
    """Import WearCheck rows, respecting checksums unless force=True."""
    settings = _get_settings()
    # Discover machines before checksum checks so unchanged samples count too.
    # Save once for the batch; never assign an Item Type or Frappe Value.
    ensure_machine_mapping_rows(
        (
            row.get("machine")
            for row in rows
            if isinstance(row, dict) and _to_int(row.get("sampno"))
        ),
        settings=settings,
    )
    mapping = _get_mapping(settings)

    created = 0
    updated = 0
    skipped = 0
    successful = 0
    failed = 0
    batch_size = 200
    processed_since_commit = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        sampno = _to_int(row.get("sampno"))
        if not sampno:
            continue
        name = str(sampno)
        new_checksum = _checksum(row)
        old_checksum = frappe.db.get_value("WearCheck Results", name, "checksum")
        if old_checksum and old_checksum == new_checksum and not force:
            skipped += 1
            continue

        exists = frappe.db.exists("WearCheck Results", name)
        doc = frappe.get_doc("WearCheck Results", name) if exists else frappe.new_doc("WearCheck Results")
        doc.sampno = sampno
        doc.bottleno = _to_int(row.get("bottleno"))
        raw_customer = row.get("customer") or ""
        raw_site = row.get("site") or ""
        raw_machine = row.get("machine") or ""
        raw_customer_s = _norm(raw_customer)
        raw_site_s = _norm(raw_site)
        raw_machine_s = _norm(raw_machine)
        mapped_company = mapping.get("Company", {}).get(_key(raw_customer)) or (raw_customer_s or None)
        mapped_location = mapping.get("Location", {}).get(_key(raw_site)) or (raw_site_s or None)
        mapped_asset = mapping.get("Asset", {}).get(_key(raw_machine)) or (raw_machine_s or None)

        doc.customer = raw_customer_s
        doc.site = raw_site_s
        doc.machine = raw_machine_s
        doc.raw_company_value = mapped_company or ""
        doc.raw_location_value = mapped_location or ""
        doc.raw_asset_value = mapped_asset or ""
        doc.last_import_attempt = now()
        doc.company = _safe_link("Company", mapped_company)
        doc.location = _safe_link("Location", mapped_location)
        doc.asset = _safe_link("Asset", mapped_asset)
        doc.component = row.get("component") or ""
        doc.profileid = _to_int(row.get("profileid"))
        doc.status = _to_int(row.get("status"))
        doc.sampledate = row.get("sampledate") or None
        doc.registerdate = row.get("registerdate") or None
        doc.machread = _to_int(row.get("machread"))
        doc.oilread = _to_float(row.get("oilread"))
        doc.perwater = _to_float(row.get("perwater"))
        doc.fueldilution = _to_float(row.get("fueldilution"))
        doc.oilsupplier = row.get("oilsupplier") or ""
        doc.oilbrand = row.get("oilbrand") or ""
        doc.samp_taker = row.get("samp_taker") or ""
        doc.commentstext = row.get("commentstext") or ""
        doc.actiontext = row.get("actiontext") or ""
        doc.feedbacktext = row.get("feedbacktext") or ""
        doc.tan = _to_float(row.get("tan"))
        doc.tbn = _to_float(row.get("tbn"))

        for fieldname in (
            "fe", "ag", "al", "ca", "cr", "cu", "mg", "na", "ni",
            "pb", "si", "sn", "p", "b", "ba", "mo", "v", "zn", "ti",
        ):
            setattr(doc, fieldname, _to_int(row.get(fieldname)))
        doc.v40 = _to_float(row.get("v40"))
        doc.v100 = _to_float(row.get("v100"))
        doc.oxi = _to_float(row.get("oxi"))
        doc.soot = _to_float(row.get("soot"))
        doc.iso4 = _to_int(row.get("iso4"))
        doc.iso6 = _to_int(row.get("iso6"))
        doc.iso14 = _to_int(row.get("iso14"))
        doc.pq = _to_int(row.get("pq"))

        link_errors = []
        if mapped_company and not doc.company:
            link_errors.append(f"Could not find Company: {mapped_company}")
        if mapped_location and not doc.location:
            link_errors.append(f"Could not find Location: {mapped_location}")
        if mapped_asset and not doc.asset:
            link_errors.append(f"Could not find Asset: {mapped_asset}")
        if link_errors:
            doc.import_failed = 1
            doc.import_status = "Failed"
            doc.import_error = " | ".join(link_errors)[:140]
            doc.import_error_details = "\n".join(link_errors)
            failed += 1
        else:
            doc.import_failed = 0
            doc.import_status = "Success"
            doc.import_error = ""
            doc.import_error_details = ""
            successful += 1
        doc.checksum = new_checksum
        if exists:
            doc.save(ignore_permissions=True)
            updated += 1
        else:
            doc.insert(ignore_permissions=True)
            created += 1
        processed_since_commit += 1
        if processed_since_commit % batch_size == 0:
            frappe.db.commit()

    frappe.db.commit()
    return {
        "ok": True, "count": len(rows), "created": created,
        "updated": updated, "skipped": skipped, "successful": successful,
        "failed": failed, "force": force, "ts": now(),
    }


@frappe.whitelist()
def fetch_and_sync():
    settings = _get_settings()
    if not getattr(settings, "enabled", 1):
        return {"ok": True, "skipped": "disabled"}
    endpoint_url = getattr(settings, "endpoint_url", None)
    if not endpoint_url:
        frappe.throw("API Wearcheck Settings: endpoint_url is required")
    api_key = settings.get_password("api_key") or ""
    headers = {"X-API-Key": api_key} if api_key else {}
    response = requests.get(endpoint_url, headers=headers, timeout=90)
    response.raise_for_status()
    rows = response.json() or []
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("results") or [rows]
    if not isinstance(rows, list):
        frappe.throw("WearCheck API response must be a list of result rows")
    return sync_wearcheck_rows(rows, force=False)


def run_scheduled_wearcheck_sync():
    """Hourly scheduler gate: retry failures, then sync when due."""
    settings = _get_settings()
    due, reason = _is_sync_due(settings)
    if not due:
        return {"ok": True, "skipped": reason}
    try:
        retry_result = retry_failed_imports()
        sync_result = fetch_and_sync()
        _set_settings_sync_attempt(success=True)
        return {
            "ok": True,
            "scheduler_reason": reason,
            "retry_failed_result": retry_result,
            "sync_result": sync_result,
        }
    except Exception:
        error = frappe.get_traceback()
        _set_settings_sync_attempt(success=False, error=error)
        frappe.log_error(title="WearCheck Scheduled Sync Failed", message=error)
        raise


@frappe.whitelist()
def retry_import(name):
    frappe.has_permission("WearCheck Results", "write", throw=True)
    doc = frappe.get_doc("WearCheck Results", name)
    row = _row_from_wearcheck_result(doc)
    result = sync_wearcheck_rows([row], force=True)
    doc.reload()
    return {
        "ok": True, "name": doc.name, "result": result,
        "import_failed": doc.import_failed,
        "import_status": doc.import_status,
        "import_error": doc.import_error,
    }


@frappe.whitelist()
def enqueue_retry_failed_imports():
    frappe.has_permission("WearCheck Results", "write", throw=True)
    job = frappe.enqueue(
        "engineering.controllers.importer.retry_failed_imports",
        queue="long", timeout=1800, now=False,
    )
    return {"ok": True, "job_id": getattr(job, "id", None)}


def retry_failed_imports(limit=None):
    names = frappe.get_all(
        "WearCheck Results", filters={"import_status": "Failed"},
        pluck="name", limit=limit, order_by="modified asc",
    )
    retried = 0
    fixed = 0
    still_failed = 0
    for name in names:
        doc = frappe.get_doc("WearCheck Results", name)
        row = _row_from_wearcheck_result(doc)
        sync_wearcheck_rows([row], force=True)
        doc.reload()
        retried += 1
        if doc.import_failed:
            still_failed += 1
        else:
            fixed += 1
        if retried % 50 == 0:
            frappe.db.commit()
    frappe.db.commit()
    return {
        "ok": True, "retried": retried, "fixed": fixed,
        "still_failed": still_failed, "ts": now(),
    }


@frappe.whitelist(allow_guest=True)
def receive_results():
    settings = _get_settings()
    if not getattr(settings, "enabled", 1):
        return {"ok": True, "skipped": "disabled"}
    expected_key = settings.get_password("api_key") or ""
    received_key = frappe.get_request_header("X-API-Key") or ""
    if not expected_key:
        frappe.throw("API Wearcheck Settings: api_key is required")
    if not hmac.compare_digest(received_key, expected_key):
        frappe.throw("Invalid X-API-Key")
    raw = frappe.local.request.get_data(as_text=True)
    rows = json.loads(raw or "[]")
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("results") or [rows]
    if not isinstance(rows, list):
        frappe.throw("JSON body must be a list of result rows")
    return sync_wearcheck_rows(rows, force=False)
