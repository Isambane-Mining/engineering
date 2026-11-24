"""Deterministic preview/repair of legacy telemetry from its own saved machine JSON.

Not whitelisted, never fetches the API. Dry-run is the default. Preserve identity,
raw JSON, checksums, mappings, creation and modified audit fields.
"""
import json
from datetime import timezone
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_datetime, cint

from engineering.controllers.kobelco_client import NUMERIC_FIELDS, normalize_equipment


def repair_legacy_results(apply=False, legacy_timezone=None, names=None):
    frappe.has_permission("API Kobelco Settings", "write", throw=True)
    apply = bool(cint(apply))
    if apply and not legacy_timezone:
        raise frappe.ValidationError("Specify the verified legacy timezone before converting fetched_at.")
    zone = ZoneInfo(legacy_timezone) if legacy_timezone else None
    candidates = []
    with frappe.cache.lock(frappe.cache.make_key("kobelco_manual_sync"), timeout=300, blocking_timeout=1):
        filters = {"telemetry_version": ["<", 2]}
        if names is not None:
            filters["name"] = ["in", names]
        candidates_names = frappe.get_all("Kobelco Results", filters=filters, pluck="name")
        for name in candidates_names:
            doc = frappe.get_doc("Kobelco Results", name, for_update=apply)
            if doc.telemetry_version and doc.telemetry_version >= 2:
                continue
            raw = json.loads(doc.raw_json)
            values = normalize_equipment(raw)
            if values["serial_number"] != doc.serial_number:
                raise frappe.ValidationError("Saved Kobelco identity does not match its raw JSON; repair stopped.")
            for field in ("serial_number", "pin", "oem", "model"):
                values.pop(field, None)
            for field in NUMERIC_FIELDS:
                values[field + "_available"] = int(values.get(field) is not None)
            values["telemetry_version"] = 2
            if zone and doc.fetched_at:
                values["fetched_at"] = get_datetime(doc.fetched_at).replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
                if not values["fleet_snapshot_timestamp"]:
                    future = sorted(field for field, value in values.items() if field.endswith("_timestamp")
                                    and value and value > values["fetched_at"])
                    if future:
                        values["source_time_warning"] = "Source timestamps later than fetch time: " + ", ".join(future)
            changes = {field: {"before": doc.get(field), "after": value}
                       for field, value in values.items() if doc.get(field) != value}
            candidates.append({"name": name, "serial_number": doc.serial_number, "changes": changes})
            if apply:
                frappe.db.set_value("Kobelco Results", name, values, update_modified=False)
        return {"applied": apply, "count": len(candidates), "legacy_timezone": legacy_timezone,
                "results": candidates, "note": "Original Fleet envelopes were not retained by the legacy importer and cannot be reconstructed."}


MACHINE_FIELD_MAP = {
    "EquipmentHeader.OEMName": "oem", "EquipmentHeader.Model": "model",
    "EquipmentHeader.SerialNumber": "serial_number", "EquipmentHeader.PIN": "pin",
    "EquipmentHeader.UnitInstallDateTime": "unit_install_timestamp",
    "Location.Latitude": "latitude", "Location.Longitude": "longitude",
    "Location.Altitude": "altitude", "Location.AltitudeUnits": "altitude_units",
    "EngineStatus.EngineNumber": "engine_number", "EngineStatus.Running": "engine_status",
    "FuelUsed.FuelUnits": "fuel_units", "FuelUsedLast24.FuelUnits": "fuel_used_last24_units",
    "FuelRemaining.FuelTankCapacityUnits": "fuel_tank_capacity_units",
}
for source, key, target in (
    ("CumulativeOperatingHours", "Hour", "operating_hours"),
    ("CumulativeIdleHours", "Hour", "idle_hours"),
    ("CumulativePowerTakeOffHours", "Hour", "pto_hours"),
    ("CumulativeLoadCount", "Count", "load_count"),
    ("FuelUsed", "FuelConsumed", "fuel_consumption"),
    ("FuelUsedLast24", "FuelConsumed", "fuel_used_last24"),
    ("FuelRemaining", "Percent", "fuel_remaining"),
    ("DEFRemaining", "Percent", "def_remaining"),
):
    MACHINE_FIELD_MAP[source + "." + key] = target
    MACHINE_FIELD_MAP[source + ".@datetime"] = target + "_timestamp"
    MACHINE_FIELD_MAP[source + ".datetime"] = target + "_timestamp"
MACHINE_FIELD_MAP.update({"Location.@datetime": "location_timestamp", "Location.datetime": "location_timestamp",
                          "EngineStatus.@datetime": "engine_status_timestamp", "EngineStatus.datetime": "engine_status_timestamp",
                          "FuelRemaining.FuelTankCapacity": "fuel_tank_capacity"})


def field_coverage(payload):
    """Inventory every leaf in the complete JSON; unknown fields stay visible."""
    paths = {}

    def walk(value, prefix):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, prefix + "." + key if prefix else key)
        elif isinstance(value, list):
            for item in value:
                walk(item, prefix + "[]")
        else:
            paths.setdefault(prefix, []).append(value)

    walk(payload, "")
    result = []
    for path, values in sorted(paths.items()):
        plain = path.removeprefix("Fleet.")
        machine_path = plain.removeprefix("Equipment[].")
        target = MACHINE_FIELD_MAP.get(machine_path)
        if plain in ("@snapshotTime", "snapshotTime"):
            target = "fleet_snapshot_timestamp / snapshot_timestamp"
        elif plain in ("@version", "version"):
            target = "fleet_version"
        result.append({"path": path, "populated": sum(v is not None and v != "" for v in values),
                       "result_field": target, "preserved_in": "raw_json + raw_response" if plain.startswith("Equipment[].") else "raw_response"})
    return result
