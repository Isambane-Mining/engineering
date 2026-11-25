"""Read-only OEM API data browser for Engineering."""

import frappe

HIDDEN_OEM_ID_FIELDS = {
    "equipment_id", "pin", "serial_number", "engine_number",
    "imei", "plate", "vehiclenumber", "agentid", "uniqid", "typeid",
}


DATASETS = {
    "BELL": {
        "fleet": {
            "doctype": "Bell Results",
            "label": "Machine & Fleet",
            "fields": ["fleet_number", "model", "mapping_status"],
            "search": ["fleet_number"],
            "raw": [],
        },
        "hours": {
            "doctype": "Bell Results",
            "label": "Operating Hours",
            "fields": [
                "fleet_number", "model", "operating_hours",
                "operating_hours_timestamp", "idle_hours",
                "idle_hours_timestamp", "active_regeneration_hours",
                "active_regeneration_hours_timestamp", "fetched_at",
            ],
            "search": ["fleet_number"],
            "raw": [],
        },
        "fuel": {
            "doctype": "Bell Results",
            "label": "Fuel & Fluids",
            "fields": [
                "fleet_number", "model", "fuel_consumed", "fuel_units",
                "fuel_consumed_timestamp", "fuel_remaining",
                "fuel_remaining_timestamp", "def_remaining",
                "def_tank_capacity_units", "def_remaining_timestamp",
            ],
            "search": ["fleet_number"],
            "raw": [],
        },
        "location": {
            "doctype": "Bell Results",
            "label": "Location & Movement",
            "fields": [
                "fleet_number", "model", "latitude", "longitude",
                "location_timestamp", "odometer", "odometer_units",
                "odometer_timestamp", "engine_running",
                "engine_status_timestamp",
            ],
            "search": ["fleet_number"],
            "raw": [],
        },
        "faults": {
            "doctype": "Bell Equipment Fault Codes",
            "label": "Fault Codes & Events",
            "fields": [
                "fleet_number", "model", "fault_code",
                "description", "occurred_at", "retrieved_at",
            ],
            "search": ["fleet_number"],
            "raw": ["source_event_xml"],
        },
        "source": {
            "doctype": "Bell Results",
            "label": "API Source Data",
            "fields": ["fleet_number", "model", "fetched_at", "fleet_snapshot_timestamp"],
            "search": ["fleet_number"],
            "raw": ["raw_xml"],
        },
        "fuel_events": {
            "doctype": "Bell Equipment Fuel Consumption",
            "label": "Fuel Consumption Events",
            "fields": [
                "fleet_number", "model", "fuel_consumed",
                "fuel_units", "measurement_timestamp", "retrieved_at",
            ],
            "search": ["fleet_number"],
            "raw": ["source_event_xml"],
        },
    },
    "KOBELCO": {
        "fleet": {
            "doctype": "Kobelco Results",
            "label": "Machine & Fleet",
            "fields": ["fleet_number", "model", "mapping_status"],
            "search": ["fleet_number"],
            "raw": [],
        },
        "hours": {
            "doctype": "Kobelco Results",
            "label": "Operating Hours",
            "fields": [
                "fleet_number", "model", "operating_hours",
                "operating_hours_timestamp", "idle_hours",
                "idle_hours_timestamp", "pto_hours",
                "pto_hours_timestamp", "snapshot_timestamp", "fetched_at",
            ],
            "search": ["fleet_number"],
            "raw": [],
        },
        "fuel": {
            "doctype": "Kobelco Results",
            "label": "Fuel & Fluids",
            "fields": [
                "fleet_number", "model", "fuel_consumption", "fuel_units",
                "fuel_consumption_timestamp", "fuel_used_last24",
                "fuel_used_last24_units", "fuel_used_last24_timestamp",
                "fuel_remaining", "fuel_remaining_timestamp",
                "def_remaining", "def_remaining_timestamp",
                "fuel_tank_capacity", "fuel_tank_capacity_units",
            ],
            "search": ["fleet_number"],
            "raw": [],
        },
        "location": {
            "doctype": "Kobelco Results",
            "label": "Location & Movement",
            "fields": [
                "fleet_number", "model", "latitude", "longitude",
                "location_timestamp", "altitude", "altitude_units",
                "engine_status", "engine_status_timestamp",
            ],
            "search": ["fleet_number"],
            "raw": [],
        },
        "source": {
            "doctype": "Kobelco Results",
            "label": "API Source Data",
            "fields": [
                "fleet_number", "model", "snapshot_timestamp",
                "fleet_snapshot_timestamp", "fetched_at", "fleet_version",
                "snapshot_time_basis", "source_time_warning",
            ],
            "search": ["fleet_number"],
            "raw": ["raw_json", "raw_response"],
        },
    },
    "MPI": {
        "fleet": {
            "doctype": "MPI Results",
            "label": "Machine & Fleet",
            "fields": ["fleet_number", "vehicle_name", "model", "active"],
            "search": ["fleet_number"],
            "raw": [],
        },
        "location": {
            "doctype": "MPI Results",
            "label": "Location & Movement",
            "fields": [
                "fleet_number", "latitude", "longitude", "speed",
                "direction", "moving", "parking_duration", "zone",
                "position_timestamp",
            ],
            "search": ["fleet_number"],
            "raw": [],
        },
        "activity": {
            "doctype": "MPI Results",
            "label": "Vehicle Activity",
            "fields": [
                "fleet_number", "current_mileage", "initial_mileage",
                "position_timestamp", "active",
            ],
            "search": ["fleet_number"],
            "raw": [],
        },
    },
}


def _dataset(oem, dataset):
    oem = (oem or "").upper()
    config = DATASETS.get(oem, {}).get(dataset)
    if not config:
        frappe.throw("This OEM dataset is not available yet.")
    doctype = config["doctype"]
    if not frappe.has_permission(doctype, "read"):
        frappe.throw("You do not have permission to view this dataset.", frappe.PermissionError)
    return config, doctype


def _permitted_fields(doctype):
    """Only expose fields at permission level zero."""
    meta = frappe.get_meta(doctype)
    return {
        df.fieldname
        for df in meta.fields
        if df.fieldname and (df.permlevel or 0) == 0
    }


@frappe.whitelist()
def get_catalogue():
    result = {oem: [] for oem in (
        "BELL", "KOBELCO", "MPI", "CTRACK", "CAT", "VOLVO"
    )}
    for oem, datasets in DATASETS.items():
        result[oem] = [
            {"key": key, "label": value["label"], "doctype": value["doctype"]}
            for key, value in datasets.items()
            if frappe.has_permission(value["doctype"], "read")
        ]
    return result


@frappe.whitelist()
def get_dataset(oem, dataset, search="", start=0, page_length=25):
    config, doctype = _dataset(oem, dataset)
    permitted = _permitted_fields(doctype)

    field_map = {"fleet_number": "asset"}
    fields = [
        field for field in config["fields"]
        if field_map.get(field, field) in permitted
        and field not in HIDDEN_OEM_ID_FIELDS
    ]
    query_fields = ["name"] + list(dict.fromkeys(
        field_map.get(field, field) for field in fields
    ))

    try:
        start = max(0, int(start))
        page_length = min(100, max(1, int(page_length)))
    except (TypeError, ValueError):
        frappe.throw("Invalid pagination values.")

    search = (search or "").strip()[:100]
    filters = {}
    or_filters = []

    if search:
        for field in config["search"]:
            actual_field = field_map.get(field, field)
            if actual_field in permitted:
                or_filters.append([actual_field, "like", f"%{search}%"])

    rows = frappe.get_list(
        doctype,
        fields=query_fields,
        filters=filters,
        or_filters=or_filters,
        order_by="modified desc",
        start=start,
        page_length=page_length + 1,
    )

    has_more = len(rows) > page_length
    rows = rows[:page_length]

    for row in rows:
        row["fleet_number"] = row.pop("asset", None) or "Unmapped"

    labels = {}
    meta = frappe.get_meta(doctype)
    for field in fields:
        actual_field = {"fleet_number": "asset"}.get(field, field)
        df = meta.get_field(actual_field)
        labels[field] = "Fleet Number" if field == "fleet_number" else (df.label if df else field)

    return {
        "oem": oem.upper(),
        "dataset": dataset,
        "doctype": doctype,
        "label": config["label"],
        "fields": [{"fieldname": f, "label": labels[f]} for f in fields],
        "rows": rows,
        "start": start,
        "page_length": page_length,
        "has_more": has_more,
        "total": None,
        "raw_available": bool(config["raw"]),
    }


@frappe.whitelist()
def get_record(oem, dataset, name):
    config, doctype = _dataset(oem, dataset)
    permitted = _permitted_fields(doctype)

    fields = ["name"] + sorted(permitted)
    rows = frappe.get_list(
        doctype,
        filters={"name": name},
        fields=fields,
        page_length=1,
    )

    if not rows:
        frappe.throw("Record not found or you do not have permission to view it.")

    record = rows[0]
    raw_fields = [field for field in config["raw"] if field in permitted]
    raw = {field: record.get(field) for field in raw_fields}

    record["fleet_number"] = record.get("asset") or "Unmapped"
    for field in (
        "asset", *HIDDEN_OEM_ID_FIELDS,
    ):
        record.pop(field, None)

    # Do not send large source payloads as part of the ordinary detail object.
    for field in raw_fields:
        record.pop(field, None)

    return {
        "doctype": doctype,
        "record": record,
        "raw": raw,
        "raw_available": bool(raw_fields),
    }
