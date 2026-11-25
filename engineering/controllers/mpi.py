"""Manual MPI fleet activity import. No scheduler hooks and no raw payload storage."""

import base64
import json
import math
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode

import frappe
import requests
from frappe.utils import convert_utc_to_system_timezone, get_datetime, now_datetime

SETTINGS = "API MPI Settings"
ENDPOINT = "https://web.mpitracking.co.za"
JOB_ID = "mpi-fleet-activity-sync"
BATCH_SIZE = 10
MAX_WORKERS = 5
MAX_VEHICLES = 500
JOB_TIMEOUT = 3600
SYNC_FIELDS = ("last_attempt", "last_success", "last_error", "vehicle_list_outcome", "status_outcome")
RECORD_TEXT_FIELDS = ("agentid", "configuration", "driver_name", "driver_phone", "folder", "info",
                      "model", "type", "typeid", "uniqid", "vehiclenumber", "vin")
RECORD_NUMBER_FIELDS = ("created_time", "current_mileage", "initial_mileage")
STATUS_FIELDS = {"active": "active", "alt": "alt", "direction": "direction", "firing": "firing",
                 "lat": "latitude", "lon": "longitude", "moving": "moving", "parking": "parking_duration",
                 "satsinview": "satsinview", "speed": "speed", "unixtimestamp": "unixtimestamp", "zone": "zone"}


class MPIError(Exception):
    """Only locally authored, credential-free messages may be used here."""


def validate_configuration(endpoint, node):
    # Credentials must only ever be sent to the verified MPI HTTPS origin.
    if str(endpoint or "").rstrip("/") != ENDPOINT:
        frappe.throw("MPI Endpoint must be https://web.mpitracking.co.za.")
    try:
        valid_node = int(node) > 0 and float(node) == int(node)
    except (TypeError, ValueError, OverflowError):
        valid_node = False
    if not valid_node:
        frappe.throw("MPI Node must be a positive integer.")


def _text(value):
    return str(value).strip() if value is not None else ""


def _normalized(value):
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper())


def match_vehicle(plate, vehicle_name, assets):
    """Raw, case-sensitive identifiers may link; normalized ones only suggest."""
    identifiers = {_text(value) for value in (plate, vehicle_name)} - {""}
    raw = set()
    normalized = set()
    keys = {_normalized(value) for value in identifiers} - {""}
    for asset in assets:
        values = {_text(asset.get(field)) for field in ("name", "asset_name")} - {""}
        if values & identifiers:
            raw.add(asset["name"])
        if {_normalized(value) for value in values} & keys:
            normalized.add(asset["name"])
    if len(raw) == 1:
        return {"asset": next(iter(raw)), "mapping_status": "Exact Match", "suggested_assets": ""}
    candidates = raw if raw else normalized
    return {
        "asset": None,
        "mapping_status": "Ambiguous" if len(candidates) > 1 else "Suggested" if candidates else "Unmatched",
        "suggested_assets": "\n".join(sorted(candidates)),
    }


def _number(value, minimum=None, maximum=None):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise MPIError("MPI returned an invalid activity number.") from None
    if not math.isfinite(number) or (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise MPIError("MPI returned an out-of-range activity number.")
    return number


def activity_values(row):
    """Allowlist only requested activity fields; never copy API objects to a DocType."""
    status = row.get("status")
    if not isinstance(status, dict):
        raise MPIError("MPI response has no vehicle activity object.")
    timestamp = _number(status.get("unixtimestamp"), minimum=0)
    position_time = None
    if timestamp:
        try:
            utc = datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
            position_time = convert_utc_to_system_timezone(utc).replace(tzinfo=None)
        except (ValueError, OverflowError, OSError):
            raise MPIError("MPI returned an invalid position timestamp.") from None
    zone = status.get("zone", row.get("zone"))
    return {
        "active": _number(status.get("active"), minimum=0, maximum=1),
        "latitude": _number(status.get("lat"), minimum=-90, maximum=90),
        "longitude": _number(status.get("lon"), minimum=-180, maximum=180),
        "speed": _number(status.get("speed"), minimum=0),
        "direction": _number(status.get("direction"), minimum=0, maximum=360),
        "moving": _number(status.get("moving"), minimum=0),
        "parking_duration": _number(status.get("parking"), minimum=0),
        "zone": _text(zone) if isinstance(zone, (str, int, float)) else None,
        "position_timestamp": position_time,
    }


def result_values(row):
    """Flatten the allowlisted record/status; serialize only the two nested values."""
    values = activity_values(row)
    status = row["status"]
    values["zone_data"] = json.dumps(status.get("zone"), ensure_ascii=False)
    for source in ("alt", "firing", "satsinview", "unixtimestamp"):
        if source in status:
            values[source] = _number(status[source])
    for field in RECORD_TEXT_FIELDS:
        if field in row:
            value = row[field]
            if isinstance(value, (dict, list)):
                raise MPIError("MPI returned an invalid metadata value.")
            values[field] = str(value) if value is not None else None
    for field in RECORD_NUMBER_FIELDS:
        if field in row:
            values[field] = _number(row[field])
    if "sensors_status" in row:
        if row["sensors_status"] is not None and not isinstance(row["sensors_status"], (list, dict)):
            raise MPIError("MPI returned an invalid sensors structure.")
        values["sensors_status"] = json.dumps(row["sensors_status"], ensure_ascii=False)
    return values


class MPIClient:
    def __init__(self, endpoint, node, username, password):
        validate_configuration(endpoint, node)
        self.endpoint = endpoint.rstrip("/")
        self.node = int(node)
        self.username = username
        self.password = password
        self.outcomes = {}
        self._outcome_lock = threading.Lock()

    def _request(self, method, path, **kwargs):
        response = None
        label = "vehicle_list" if path == "/api/CRIT/api.php" else "status"
        outcome = {"http_status": None, "api_code": None, "ok": False}
        try:
            headers = {"User-Agent": f"Python-urllib/{sys.version_info.major}.{sys.version_info.minor}",
                       "Accept-Encoding": "identity", "Connection": "close"}
            if "data" in kwargs:
                kwargs["data"] = urlencode(kwargs["data"]).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            if "auth" in kwargs:
                username, password = kwargs.pop("auth")
                headers["Authorization"] = "Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            with requests.Session() as session:
                session.headers.clear()
                session.trust_env = False
                response = session.request(method, self.endpoint + path, headers=headers,
                                           timeout=(5, 20), allow_redirects=False, **kwargs)
            outcome["http_status"] = int(response.status_code)
            if response.status_code in (401, 403):
                raise MPIError("MPI authentication failed (HTTP 401/403); check credentials and access.")
            if response.status_code != 200:
                raise MPIError(f"MPI request failed (HTTP {int(response.status_code)}).")
            try:
                payload = response.json()
            except ValueError:
                raise MPIError("MPI returned invalid JSON.") from None
            if isinstance(payload, dict) and isinstance(payload.get("code"), (int, float)):
                outcome["api_code"] = payload["code"]
            if isinstance(payload, dict) and "code" in payload and str(payload["code"]) != "0":
                # Remote messages can echo input or include personal data. Never store them.
                raise MPIError("MPI returned a nonzero API code.")
            outcome["ok"] = True
            return payload
        except requests.Timeout:
            raise MPIError("MPI request timed out (connect 5s / read 20s).") from None
        except requests.RequestException:
            raise MPIError("MPI network or TLS request failed.") from None
        finally:
            with self._outcome_lock:
                previous = self.outcomes.get(label, {})
                for key, success in (("successful_requests", True), ("failed_requests", False)):
                    outcome[key] = previous.get(key, 0) + int(outcome["ok"] == success)
                self.outcomes[label] = outcome
            if response is not None:
                response.close()

    def object_list(self):
        payload = self._request("POST", "/api/CRIT/api.php", params={"node": self.node}, data={
            "functionName": "api_objectlist", "Username": self.username, "Password": self.password,
        })
        if not isinstance(payload, list):
            raise MPIError("MPI vehicle list must be a JSON array.")
        if len(payload) > MAX_VEHICLES:
            raise MPIError(f"MPI returned more than the Phase 1 limit of {MAX_VEHICLES} vehicles; review the limit.")
        vehicles = {}
        for row in payload:
            if not isinstance(row, dict):
                raise MPIError("MPI vehicle list contains an invalid record.")
            imei = _text(row.get("IMEI"))
            if not imei.isdigit() or len(imei) > 32:
                raise MPIError("MPI vehicle list contains an invalid IMEI.")
            vehicle = {"imei": imei, "plate": _text(row.get("PLATE")),
                       "vehicle_name": _text(row.get("NAME")),
                       "list_latitude": _number(row.get("LATITUDE"), -90, 90),
                       "list_longitude": _number(row.get("LONGITUDE"), -180, 180)}
            if imei in vehicles and vehicles[imei] != vehicle:
                raise MPIError("MPI vehicle list contains conflicting records for the same IMEI.")
            vehicles[imei] = vehicle
        return list(vehicles.values())

    def status(self, imei):
        payload = self._request("GET", "/api/api.php", auth=(self.username, self.password),
                                params={"cmd": "status", "imei": imei, "node": self.node})
        if not isinstance(payload, dict) or str(payload.get("code")) != "0" or not isinstance(payload.get("data"), list):
            raise MPIError("MPI status response has an unexpected shape or missing success code.")
        matches = [row for row in payload["data"] if isinstance(row, dict) and _text(row.get("imei")) == imei]
        if len(matches) != 1:
            raise MPIError("MPI status did not return exactly one record for the requested IMEI.")
        row = matches[0]
        status = row.get("status")
        if not isinstance(status, dict):
            raise MPIError("MPI status response has no activity object.")
        return {key: row[key] for key in (*RECORD_TEXT_FIELDS, *RECORD_NUMBER_FIELDS, "imei", "sensors_status") if key in row} | {
            "status": {key: status[key] for key in STATUS_FIELDS if key in status}}


@frappe.whitelist(methods=["POST"])
def sync_now():
    settings = frappe.get_single(SETTINGS)
    settings.check_permission("write")
    if not settings.enabled:
        frappe.throw("Enable and save MPI settings before syncing.")
    validate_configuration(settings.endpoint, settings.node)
    if not settings.username:
        frappe.throw("Save an MPI username and API password before syncing.")
    frappe.enqueue(
        "engineering.controllers.mpi.run_sync", queue="long", timeout=JOB_TIMEOUT,
        job_id=JOB_ID, deduplicate=True, enqueue_after_commit=True,
    )
    return {"queued": True}


@frappe.whitelist(methods=["POST"])
def fetch_fleet():
    settings = frappe.get_single(SETTINGS)
    settings.check_permission("write")
    if not settings.enabled:
        frappe.throw("Enable and save MPI settings before fetching the fleet.")
    validate_configuration(settings.endpoint, settings.node)
    password = settings.get_password("api_password", raise_exception=False)
    if not settings.username or not password:
        frappe.throw("Save the MPI username and API password before fetching the fleet.")

    lock = frappe.cache.lock(
        f"{frappe.local.site}:mpi-fleet-sync",
        timeout=JOB_TIMEOUT + 60,
        blocking_timeout=1,
    )
    if not lock.acquire(blocking=True):
        frappe.throw("An MPI sync or fleet fetch is already running. Try again shortly.")

    client = None
    try:
        _sync_state(
            last_attempt=now_datetime(),
            last_error="MPI fleet discovery in progress.",
            vehicle_list_outcome="Not attempted.",
        )
        client = MPIClient(settings.endpoint, settings.node, settings.username, password)
        vehicles = client.object_list()
        if not vehicles:
            raise MPIError("MPI returned an empty vehicle list; existing mappings were retained.")

        filters = {"parent": SETTINGS, "parenttype": SETTINGS, "parentfield": "vehicles"}
        before = set(frappe.get_all("MPI Vehicle Mapping", filters=filters, pluck="imei"))
        _discover(vehicles)
        rows = frappe.get_all("MPI Vehicle Mapping", filters=filters, fields=["imei", "asset"])
        added = len({row.imei for row in rows} - before)
        unmapped = sum(not row.asset for row in rows)

        _sync_state(last_error="", **_endpoint_outcomes(client))
        return {
            "ok": True,
            "message": (
                f"Fleet fetched: {len(vehicles)} vehicles; {added} new mappings; "
                f"{unmapped} still need an Asset selection."
            ),
        }
    except MPIError as error:
        frappe.db.rollback()
        message = str(error)
    except Exception:
        frappe.db.rollback()
        message = "MPI fleet fetch failed internally; check the settings and retry on LAB."
    finally:
        lock.release()

    try:
        _sync_state(last_error=message, **_endpoint_outcomes(client))
    except Exception:
        pass
    return {"ok": False, "message": message}


def _sync_state(**values):
    frappe.db.set_single_value(SETTINGS, values, update_modified=False)
    frappe.db.commit()


@frappe.whitelist()
def get_sync_status():
    settings = frappe.get_single(SETTINGS)
    settings.check_permission("read")
    return {field: settings.get(field) for field in SYNC_FIELDS}


def _discover(vehicles):
    # Serialize discovery with a form save, including its child mapping updates.
    settings = frappe.get_doc(SETTINGS, SETTINGS, for_update=True)
    existing = {row.imei: row for row in settings.vehicles}
    assets = frappe.get_all("Asset", fields=["name", "asset_name"])
    for vehicle in vehicles:
        row = existing.get(vehicle["imei"])
        if row is None:
            row = settings.append("vehicles", {key: vehicle[key] for key in ("imei", "plate", "vehicle_name")})
            existing[vehicle["imei"]] = row
        row.plate, row.vehicle_name = vehicle["plate"], vehicle["vehicle_name"]
        # Includes both human selections and prior exact matches: neither is overwritten.
        if not row.asset:
            row.update(match_vehicle(row.plate, row.vehicle_name, assets))
        if row.is_new():
            row.insert(ignore_permissions=True)
        else:
            frappe.db.set_value("MPI Vehicle Mapping", row.name,
                {field: row.get(field) for field in ("plate", "vehicle_name", "asset", "mapping_status", "suggested_assets")},
                update_modified=False)
    frappe.clear_document_cache(SETTINGS, SETTINGS)
    frappe.db.commit()


def _fetch_status(client, vehicle):
    """Network only: executor threads must never access Frappe DB/local context."""
    try:
        return client.status(vehicle["imei"]), None
    except MPIError as error:
        return None, str(error)
    except Exception:
        return None, "Unexpected MPI response processing failure."


def _upsert(vehicle, status):
    # Lock/re-read the child so a committed manual mapping edit wins over discovery data.
    names = frappe.db.sql(
        "SELECT name FROM `tabMPI Vehicle Mapping` WHERE parent=%s AND parenttype=%s "
        "AND parentfield='vehicles' AND imei=%s FOR UPDATE",
        (SETTINGS, SETTINGS, vehicle["imei"]),
    )
    if len(names) != 1:
        raise MPIError("Vehicle mapping was removed or duplicated during sync; review and sync again.")
    mapping = frappe.get_doc("MPI Vehicle Mapping", names[0][0])
    values = result_values(status)
    required = ("active", "latitude", "longitude", "speed", "direction", "moving",
                "parking_duration", "position_timestamp")
    if any(values[field] is None for field in required):
        # Frappe coerces missing Check/Float values to zero on save. Never turn an
        # incomplete response into an inactive, parked vehicle at coordinates 0,0.
        raise MPIError("MPI status is incomplete; previous activity was retained.")
    imei = vehicle["imei"]
    doc = frappe.get_doc("MPI Results", imei) if frappe.db.exists("MPI Results", imei) else frappe.new_doc("MPI Results")
    doc.update({"imei": imei, "mapping": mapping.name, "asset": mapping.asset,
                "plate": vehicle["plate"], "vehicle_name": vehicle["vehicle_name"],
                "list_latitude": vehicle.get("list_latitude"), "list_longitude": vehicle.get("list_longitude")})
    previous = doc.position_timestamp
    incoming = values["position_timestamp"]
    nulls = set(json.loads(doc.get("null_fields") or "[]"))
    # Retain a known newer snapshot if MPI serves stale or undated status.
    if not previous or (incoming and get_datetime(incoming) >= get_datetime(previous)):
        if not previous:
            for field in (*RECORD_NUMBER_FIELDS, "alt", "firing", "satsinview", "unixtimestamp"):
                if field not in values:
                    nulls.add(field)
        doc.update(values)
        # Record null optional numeric fields explicitly before Frappe applies numeric defaults.
        for field, value in values.items():
            if value is None:
                nulls.add(field)
            else:
                nulls.discard(field)
    for field in ("list_latitude", "list_longitude"):
        if vehicle.get(field) is None:
            nulls.add(field)
        else:
            nulls.discard(field)
    doc.null_fields = json.dumps(sorted(nulls))
    doc.save(ignore_permissions=True)
    frappe.db.commit()


def run_sync():
    """Queued manual job. Exceptions and remote payloads are never sent to error logs."""
    lock = frappe.cache.lock(f"{frappe.local.site}:mpi-fleet-sync", timeout=JOB_TIMEOUT + 60, blocking_timeout=1)
    if not lock.acquire(blocking=True):
        return {"skipped": True}
    try:
        settings = frappe.get_single(SETTINGS)
        if not settings.enabled:
            return {"skipped": True}
        _sync_state(last_attempt=now_datetime(), last_error="Sync in progress.",
                    vehicle_list_outcome="Not attempted.", status_outcome="Not attempted.")
        client = None
        try:
            password = settings.get_password("api_password", raise_exception=False)
            if not settings.username or not password:
                raise MPIError("MPI username or API password is missing; save credentials in settings.")
            client = MPIClient(settings.endpoint, settings.node, settings.username, password)
            vehicles = client.object_list()
            if not vehicles:
                raise MPIError("MPI returned an empty vehicle list; no existing mappings or results were removed.")
            _discover(vehicles)
            errors, succeeded = [], 0
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                for offset in range(0, len(vehicles), BATCH_SIZE):
                    batch = vehicles[offset:offset + BATCH_SIZE]
                    futures = [pool.submit(_fetch_status, client, vehicle) for vehicle in batch]
                    for vehicle, future in zip(batch, futures):
                        status, error = future.result()
                        if not error:
                            try:
                                _upsert(vehicle, status)
                                succeeded += 1
                            except MPIError as failure:
                                frappe.db.rollback()
                                error = str(failure)
                            except Exception:
                                frappe.db.rollback()
                                error = "Could not save vehicle activity; review the mapping and result on LAB."
                        if error:
                            errors.append(f"IMEI {vehicle['imei']}: {error}")
            if errors:
                summary = f"Partial sync: {succeeded}/{len(vehicles)} results saved; {len(errors)} failed.\n"
                _sync_state(last_error=summary + "\n".join(errors[:50]), **_endpoint_outcomes(client))
            else:
                _sync_state(last_success=now_datetime(), last_error="", **_endpoint_outcomes(client))
            return {"succeeded": succeeded, "failed": len(errors), "vehicles": len(vehicles)}
        except Exception as error:
            frappe.db.rollback()
            message = str(error) if isinstance(error, MPIError) else "MPI sync failed internally; check configuration and retry on LAB."
            _sync_state(last_error=message, **_endpoint_outcomes(client))
            return {"failed": True}
    finally:
        lock.release()


def _endpoint_outcomes(client):
    outcomes = client.outcomes if client else {}
    return {field: json.dumps(outcomes[label], sort_keys=True) if label in outcomes else "Not attempted."
            for field, label in (("vehicle_list_outcome", "vehicle_list"), ("status_outcome", "status"))}
