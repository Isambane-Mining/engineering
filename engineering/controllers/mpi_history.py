"""Manual UTC history imports. Only proven activity endpoints and typed fields are persisted."""
import hashlib
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from time import monotonic

import frappe
from frappe import _dict

from engineering.controllers.mpi import MPIClient, MPIError, SETTINGS, _number

IMPORT = "MPI History Import"
HISTORY = "MPI Activity History"
VEHICLE = "MPI History Vehicle"
COMMANDS = ("run", "runstops", "get_idle", "ag_geozones", "distance")
MAX_DAYS = 7
MAX_ENDPOINT_ROWS = 2000
MAX_IMPORT_ROWS = 20000
JOB_TIMEOUT = 1800
MAX_VEHICLES = 500
VEHICLE_BATCH_SIZE = 5
REPORT_NAME = "mileage report"
PARAMETERS = ("imei", "start_date", "end_date", "include_report")
STATUS_FIELDS = ("status", "started_at", "completed_at", "records_processed", "endpoint_outcomes", "last_error")
METRICS = ("distance", "max_speed", "avg_speed", "latitude", "longitude", "start_latitude", "start_longitude",
           "end_latitude", "end_longitude", "trips_count", "trip_seconds", "driving_seconds", "parking_count", "parking_seconds")


def utc_windows(start_date, end_date, now=None):
    """Inclusive ISO dates -> completed daily half-open UTC windows."""
    try:
        if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)) for value in (start_date, end_date)):
            raise ValueError
        start, end = date.fromisoformat(str(start_date)), date.fromisoformat(str(end_date))
        today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
        days = (end - start).days + 1
        if start.year < 1970 or not 1 <= days <= MAX_DAYS or end >= today:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise MPIError("Select one to seven completed UTC dates in chronological order.") from None
    first = int(datetime.combine(start, time.min, timezone.utc).timestamp())
    return [(first + day * 86400, first + (day + 1) * 86400) for day in range(days)]


def _epoch(value, optional=False):
    if value is None and optional:
        return None
    number = _number(value, minimum=0)
    if number is None or isinstance(value, bool) or int(number) != number:
        raise MPIError("MPI history returned an invalid UTC timestamp.")
    try:
        datetime.fromtimestamp(number, timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise MPIError("MPI history returned an invalid UTC timestamp.") from None
    return int(number)


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if epoch is not None else ""


def _text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise MPIError("MPI history returned an invalid activity label.")
    return value


def _rows(value):
    if isinstance(value, dict):
        if len(value) > MAX_ENDPOINT_ROWS:
            raise MPIError("MPI history exceeded the endpoint row limit.")
        value = list(value.values())
    if not isinstance(value, list) or len(value) > MAX_ENDPOINT_ROWS or any(not isinstance(row, dict) for row in value):
        raise MPIError("MPI history returned an unsupported or oversized row collection.")
    return value


def _event(kind, source, row, window, start_key="ts", end_key="te", allow_open=False):
    if start_key not in row or end_key not in row:
        raise MPIError("MPI history is missing activity timestamps.")
    start, end = _epoch(row.get(start_key)), _epoch(row.get(end_key), optional=allow_open)
    if end is not None and end < start:
        raise MPIError("MPI history returned a reversed activity interval.")
    intersects = window[0] <= start < window[1] if end == start else start < window[1] and (end is None or end > window[0])
    if not intersects:
        return None
    duration = _number(row.get("dur"), minimum=0) if "dur" in row else (end - start if end is not None else None)
    return {"activity_type": kind, "source_endpoint": source, "start_epoch": start, "end_epoch": end,
            "start_utc": _iso(start), "end_utc": _iso(end), "duration_seconds": duration}


def _metrics(value, row, mapping):
    for source, target in mapping.items():
        if source in row:
            minimum, maximum = (-90, 90) if "latitude" in target else (-180, 180) if "longitude" in target else (0, None)
            value[target] = _number(row[source], minimum, maximum)


def select_activity_template(payload):
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        raise MPIError("MPI activity template discovery failed.")
    for row in _rows(payload.get("data")):
        name, group = str(row.get("name", "")).strip(), str(row.get("group", ""))
        # These names were inspected on LAB; only Mileage report has a verified row schema.
        if name.casefold() == REPORT_NAME and not re.search(r"fuel|driver|device|admin|sensor", group, re.I):
            identifier = row.get("id")
            if str(identifier).isdigit() and int(identifier) > 0:
                return {"id": int(identifier), "name": name}
    raise MPIError("The audited Mileage report activity template is not available.")


def _report_rows(payload, template, vehicle_id):
    if not template or template.get("name", "").strip().casefold() != REPORT_NAME or not vehicle_id:
        raise MPIError("Select an audited activity report with a saved vehicle identity.")
    if (not isinstance(payload, dict) or payload.get("success") is not True
            or str(payload.get("report_type")) != str(template["id"]) or not isinstance(payload.get("data"), dict)):
        raise MPIError("MPI returned an unsupported activity report envelope.")
    result = []

    def visit(value, depth=0):
        if depth > 6 or not isinstance(value, (dict, list)):
            raise MPIError("MPI returned an unsupported activity report grouping.")
        if isinstance(value, dict) and {"ts", "te", "agentid"} & value.keys():
            required = {"ts", "te", "agentid", "length"}
            if not required <= value.keys() or value.keys() - (required | {"fn", "data"}):
                raise MPIError("MPI returned unrecognized activity report row keys.")
            if str(value["agentid"]) != str(vehicle_id):
                raise MPIError("MPI activity report returned a different vehicle.")
            result.append(value)
            if len(result) > MAX_ENDPOINT_ROWS:
                raise MPIError("MPI activity report exceeded the row limit.")
            return  # Never traverse or persist the row's presentation data/fn.
        children = value.values() if isinstance(value, dict) else value
        for child in children:
            visit(child, depth + 1)
    visit(payload["data"])
    return result


def parse_endpoint(command, payload, imei, window, template=None, vehicle_id=None):
    if command not in (*COMMANDS, "get_report"):
        raise MPIError("This MPI history endpoint is not supported.")
    if command != "get_report" and (not isinstance(payload, dict) or str(payload.get("code")) != "0"):
        raise MPIError("MPI history did not return a success code.")
    values = []

    def add(kind, row, mapping=None, **options):
        value = _event(kind, command, row, window, **options)
        if value is None:
            return
        _metrics(value, row, mapping or {})
        if kind == "Geozone Visit":
            value.update(zone_name=_text(row.get("zonename")), zone_group=_text(row.get("group")))
            if not value["zone_name"]:
                raise MPIError("MPI geozone visit is missing its zone name.")
        if kind == "Activity Report":
            value.update(template_id=str(template["id"]), template_name=template["name"])
        values.append(value)

    if command == "run":
        for row in _rows(payload.get("tracks")):
            add("Trip", row, {"length": "distance", "maxspeed": "max_speed", "avgspeed": "avg_speed",
                "lats": "start_latitude", "lons": "start_longitude", "late": "end_latitude", "lone": "end_longitude"})
    elif command == "runstops":
        for field, kind in (("stops", "Stop"), ("parkings", "Parking")):
            for row in _rows(payload.get(field)):
                add(kind, row, {"lat": "latitude", "lon": "longitude"})
    elif command in ("get_idle", "ag_geozones"):
        data = payload.get("data")
        if isinstance(data, dict):
            if set(data) != {imei}:
                raise MPIError("MPI history returned an unexpected vehicle grouping.")
            data = data[imei]
        for row in _rows(data):
            if command == "get_idle":
                add("Idle", row, start_key="idle_start", end_key="idle_end")
            else:
                add("Geozone Visit", row, allow_open=True)
    elif command == "distance":
        row = payload.get("distance")
        if not isinstance(row, dict) or _number(row.get("length"), minimum=0) is None:
            raise MPIError("MPI distance summary is missing its distance value.")
        value = {"activity_type": "Distance Summary", "source_endpoint": command,
                 "start_epoch": window[0], "end_epoch": window[1], "start_utc": _iso(window[0]), "end_utc": _iso(window[1]),
                 "duration_seconds": _number(row.get("duration"), minimum=0)}
        _metrics(value, row, {"length": "distance", "max_speed": "max_speed", "avg_speed": "avg_speed",
            "trips_cnt": "trips_count", "trips_time": "trip_seconds", "trips_driving": "driving_seconds",
            "parking_count": "parking_count", "parking_time": "parking_seconds"})
        values.append(value)
    else:
        for row in _report_rows(payload, template, vehicle_id):
            add("Activity Report", row, {"length": "distance"})
    unique = {}
    for value in values:
        value["missing_fields"] = ", ".join(field for field in (*METRICS, "end_epoch", "duration_seconds") if value.get(field) is None)
        unique[history_key(imei, value)] = value
    if len(unique) > MAX_ENDPOINT_ROWS:
        raise MPIError("MPI history exceeded the endpoint row limit.")
    return list(unique.values())


def history_key(imei, value):
    parts = [imei, value["activity_type"], value["start_epoch"]]
    if value["activity_type"] == "Geozone Visit":
        parts += [value.get("zone_name", ""), value.get("zone_group", "")]
    if value["activity_type"] == "Activity Report":
        parts.append(value["template_id"])
    if value["activity_type"] == "Distance Summary":
        parts.append(value["end_epoch"])
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


class HistoryClient(MPIClient):
    def templates(self):
        return self._request("GET", "/api/api.php", auth=(self.username, self.password),
                             params={"cmd": "reports_list", "node": self.node})

    def fetch(self, command, imei, window, template=None, vehicle_id=None):
        if command not in (*COMMANDS, "get_report"):
            raise MPIError("This MPI history endpoint is not supported.")
        params = {"cmd": command, "node": self.node}
        start, stop = window[0], window[1] - 1
        if command == "get_report":
            if not template or template.get("name", "").casefold() != REPORT_NAME or not vehicle_id:
                raise MPIError("An audited report and saved vehicle identity are required.")
            params.update(report_type=template["id"], veh_id=vehicle_id, start=start, stop=stop,
                          format="json", tz="Africa/Johannesburg", explode=3, group=2)
        elif command == "get_idle":
            params.update(imei=imei, time_start=start, time_end=stop)
        else:
            params.update(imei=imei, start=start, stop=stop)
            if command == "run":
                params["zones"] = 0
        return self._request("GET", "/api/api.php", auth=(self.username, self.password), params=params)


def upsert_history(imei, asset, value):
    key = history_key(imei, value)
    doc = frappe.get_doc(HISTORY, key) if frappe.db.exists(HISTORY, key) else frappe.new_doc(HISTORY)
    # Explicit parser fields only; the caller never passes raw response dictionaries.
    allowed = ("activity_type", "source_endpoint", "start_epoch", "end_epoch", "start_utc", "end_utc",
               "duration_seconds", "missing_fields", "zone_name", "zone_group", "template_id", "template_name", *METRICS)
    doc.update({field: value.get(field) for field in allowed})
    # Keep historical attribution when the vehicle mapping changes between imports.
    doc.update({"source_key": key, "imei": imei, "asset": doc.get("asset") or asset})
    doc.save(ignore_permissions=True)
    return key


def _mapping(settings, imei):
    if not re.fullmatch(r"[0-9]{1,32}", str(imei)):
        raise MPIError("Choose a valid mapped MPI IMEI.")
    matches = [row for row in settings.vehicles if row.imei == imei]
    if len(matches) != 1:
        raise MPIError("The IMEI must have exactly one saved MPI vehicle mapping.")
    return matches[0]


def import_vehicles(doc, settings=None):
    """Validate saved child selections, with a fallback for pre-table single imports."""
    rows = doc.get("vehicles") or []
    if not rows and doc.imei:
        rows = [_dict(imei=doc.imei)]
    if not rows or len(rows) > MAX_VEHICLES:
        raise MPIError("Select between one and 500 MPI vehicles.")
    seen = set()
    for row in rows:
        if not re.fullmatch(r"[0-9]{1,32}", str(row.imei or "")):
            raise MPIError("Choose a valid mapped MPI IMEI for every vehicle.")
        if row.imei in seen:
            raise MPIError("Each MPI IMEI may appear only once in an import.")
        seen.add(row.imei)
        if settings is not None:
            mapping = _mapping(settings, row.imei)
            if not row.get("name"):  # Legacy requests have no saved child display snapshot.
                row.update({"plate": mapping.plate, "asset": mapping.asset})
    return rows


@frappe.whitelist()
def get_history_vehicle_options():
    settings = frappe.get_single(SETTINGS)
    settings.check_permission("write")
    counts = {}
    for row in settings.vehicles:
        counts[row.imei] = counts.get(row.imei, 0) + 1
    return [{"imei": row.imei, "plate": row.plate, "asset": row.asset} for row in settings.vehicles
            if re.fullmatch(r"[0-9]{1,32}", str(row.imei or "")) and counts[row.imei] == 1]


@frappe.whitelist(methods=["POST"])
def enqueue_import(request_name):
    doc = frappe.get_doc(IMPORT, request_name, for_update=True)
    doc.check_permission("write")
    settings = frappe.get_single(SETTINGS)
    settings.check_permission("write")
    if not settings.enabled:
        frappe.throw("Enable MPI settings before importing history.")
    try:
        utc_windows(doc.start_date, doc.end_date)
        vehicles = import_vehicles(doc, settings)
    except MPIError as error:
        frappe.throw(str(error))
    if doc.status in ("Queued", "Running"):
        return {"queued": True, "name": doc.name}
    frappe.db.set_value(IMPORT, doc.name, {"status": "Queued", "last_error": "", "endpoint_outcomes": "",
        "records_processed": 0, "started_at": None, "completed_at": None}, update_modified=False)
    for row in vehicles:
        if row.get("name"):
            frappe.db.set_value(VEHICLE, row.name, {"status": "Queued", "last_error": "", "endpoint_outcomes": "",
                "records_processed": 0, "started_at": None, "completed_at": None}, update_modified=False)
    frappe.enqueue("engineering.controllers.mpi_history.run_import", request_name=doc.name,
        queue="long", timeout=JOB_TIMEOUT * len(vehicles) + 60,
        job_id=f"mpi-history-{doc.name}", deduplicate=True, enqueue_after_commit=True)
    return {"queued": True, "name": doc.name}


@frappe.whitelist()
def get_import_status(request_name):
    doc = frappe.get_doc(IMPORT, request_name)
    doc.check_permission("read")
    return {**{field: doc.get(field) for field in STATUS_FIELDS}, "vehicles": [
        {"name": row.name, "imei": row.imei, **{field: row.get(field) for field in STATUS_FIELDS}}
        for row in doc.get("vehicles") or []]}


def _state(name, **values):
    frappe.db.set_value(IMPORT, name, values, update_modified=False)
    frappe.db.commit()


def _execute(doc, client, asset, windows, progress=None, deadline=None):
    progress = progress or (lambda **values: _state(doc.name, **values))
    outcomes, errors, keys = {}, [], set()
    template, vehicle_id, report_error = None, None, None
    if doc.include_report:
        try:
            template = select_activity_template(client.templates())
            vehicle_id = frappe.db.get_value("MPI Results", doc.imei, "agentid")
            if not str(vehicle_id).isdigit() or int(vehicle_id) <= 0:
                raise MPIError("Optional activity report needs a saved snapshot vehicle identity.")
        except Exception as error:
            report_error = str(error) if isinstance(error, MPIError) else "Activity template discovery failed."
    for window in windows:
        for command in (*COMMANDS, "get_report") if doc.include_report else COMMANDS:
            label = f"{_iso(window[0])[:10]} {command}"
            try:
                if deadline is not None and monotonic() >= deadline:
                    raise MPIError("This vehicle exceeded its import time limit; retry a shorter date range.")
                if command == "get_report" and report_error:
                    raise MPIError(report_error)
                payload = client.fetch(command, doc.imei, window, template=template, vehicle_id=vehicle_id)
                rows = parse_endpoint(command, payload, doc.imei, window, template=template, vehicle_id=vehicle_id)
                new_keys = {history_key(doc.imei, row) for row in rows}
                if len(keys | new_keys) > MAX_IMPORT_ROWS:
                    raise MPIError("MPI history exceeded the import record limit.")
                for row in rows:
                    upsert_history(doc.imei, asset, row)
                frappe.db.commit()
                keys.update(new_keys)
                outcomes[label] = {"status": "Success", "records": len(rows)}
            except Exception as error:
                frappe.db.rollback()
                message = str(error) if isinstance(error, MPIError) else "Could not import this MPI activity batch."
                errors.append(f"{label}: {message}")
                outcomes[label] = {"status": "Failed", "error": message}
            progress(endpoint_outcomes=json.dumps(outcomes, sort_keys=True), records_processed=len(keys))
    result = dict(status="Partial" if errors and keys else "Failed" if errors else "Completed",
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None), last_error="\n".join(errors),
        endpoint_outcomes=json.dumps(outcomes, sort_keys=True), records_processed=len(keys))
    progress(**result)
    return result


def _vehicle_state(row, **values):
    row.update(values)
    if row.get("name"):
        frappe.db.set_value(VEHICLE, row.name, values, update_modified=False)
        frappe.db.commit()


def _parent_progress(doc, rows, final=False):
    statuses = [row.get("status") for row in rows]
    status = "Running"
    if final:
        status = "Completed" if all(s == "Completed" for s in statuses) else (
            "Failed" if all(s == "Failed" for s in statuses) else "Partial")
    errors = [f"Vehicle {idx}: {row.last_error}" for idx, row in enumerate(rows, 1) if row.get("last_error")]
    outcomes = {row.imei: {"status": row.get("status"), "records_processed": row.get("records_processed") or 0}
                for row in rows}
    # Legacy single-vehicle requests retain their original parent endpoint detail.
    if len(rows) == 1 and not rows[0].get("name"):
        outcomes = json.loads(rows[0].get("endpoint_outcomes") or "{}")
    values = dict(status=status, records_processed=sum(row.get("records_processed") or 0 for row in rows),
                  endpoint_outcomes=json.dumps(outcomes, sort_keys=True), last_error="\n".join(errors))
    if final:
        values["completed_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    _state(doc.name, **values)


def _run_vehicles(doc, settings, client, windows):
    rows = import_vehicles(doc)
    for row in rows:
        _vehicle_state(row, status="Queued", records_processed=0, endpoint_outcomes="", last_error="",
                       started_at=None, completed_at=None)
    for offset in range(0, len(rows), VEHICLE_BATCH_SIZE):
        for row in rows[offset:offset + VEHICLE_BATCH_SIZE]:
            lock = None
            try:
                mapping = _mapping(settings, row.imei)
                candidate = frappe.cache.lock(f"{frappe.local.site}:mpi-history:{row.imei}",
                    timeout=JOB_TIMEOUT + 60, blocking_timeout=1)
                if not candidate.acquire(blocking=True):
                    raise MPIError("Another history import is running for this vehicle; retry later.")
                lock = candidate
                _vehicle_state(row, status="Running", started_at=datetime.now(timezone.utc).replace(tzinfo=None))

                def progress(**values):
                    _vehicle_state(row, **values)
                    _parent_progress(doc, rows)

                result = _execute(_dict(name=doc.name, imei=row.imei, include_report=doc.include_report),
                    client, row.get("asset") if row.get("name") else mapping.asset, windows,
                    progress=progress, deadline=monotonic() + JOB_TIMEOUT)
                _vehicle_state(row, **result)
            except Exception as error:
                frappe.db.rollback()
                message = str(error) if isinstance(error, MPIError) else "MPI history import failed for this vehicle."
                _vehicle_state(row, status="Failed", last_error=message,
                               completed_at=datetime.now(timezone.utc).replace(tzinfo=None))
            finally:
                if lock is not None:
                    try:
                        lock.release()
                    except Exception:
                        _vehicle_state(row, status="Partial" if row.get("records_processed") else "Failed",
                            last_error="Could not release this vehicle's import lock; retry later.",
                            completed_at=datetime.now(timezone.utc).replace(tzinfo=None))
            _parent_progress(doc, rows)
    _parent_progress(doc, rows, final=True)


def run_import(request_name):
    doc, authorized = None, False
    try:
        doc = frappe.get_doc(IMPORT, request_name)
        doc.check_permission("write")
        settings = frappe.get_single(SETTINGS)
        settings.check_permission("write")
        authorized = True
        if not settings.enabled:
            raise MPIError("MPI settings are disabled.")
        windows = utc_windows(doc.start_date, doc.end_date)
        password = settings.get_password("api_password", raise_exception=False)
        if not settings.username or not password:
            raise MPIError("Save the MPI credentials before importing history.")
        client = HistoryClient(settings.endpoint, settings.node, settings.username, password)
        _state(doc.name, status="Running", started_at=datetime.now(timezone.utc).replace(tzinfo=None), last_error="")
        _run_vehicles(doc, settings, client, windows)
    except Exception as error:
        frappe.db.rollback()
        if not authorized:
            raise
        message = str(error) if isinstance(error, MPIError) else "MPI history import failed; review the request and settings."
        for row in doc.get("vehicles") or []:
            if row.status not in ("Completed", "Partial", "Failed"):
                _vehicle_state(row, status="Failed", last_error=message,
                    completed_at=datetime.now(timezone.utc).replace(tzinfo=None))
        _state(request_name, status="Failed", last_error=message, completed_at=datetime.now(timezone.utc).replace(tzinfo=None))
