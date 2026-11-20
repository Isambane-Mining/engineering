"""Read-only Kobelco AEMP JSON client. No Frappe database or outbound writes."""
import math
import json
import posixpath
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import requests
from requests.auth import HTTPBasicAuth


class KobelcoError(ValueError):
    """Safe to display: never include response bodies, credentials or request URLs."""


def validate_base_url(value):
    parts = urlsplit((value or "").strip())
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or "\\" in parts.path):
        raise KobelcoError("Base URL must be an HTTPS URL without credentials, query or fragment.")
    decoded = unquote(parts.path)
    if "\\" in decoded or any(p in (".", "..") for p in decoded.split("/")):
        raise KobelcoError("Base URL cannot contain path traversal.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + "/", "", ""))


NUMERIC_FIELDS = ("operating_hours", "idle_hours", "fuel_consumption", "fuel_remaining", "def_remaining",
                  "latitude", "longitude", "pto_hours", "load_count", "fuel_used_last24",
                  "fuel_tank_capacity", "altitude")
TIMESTAMP_FIELDS = ("snapshot_timestamp", "fleet_snapshot_timestamp", "unit_install_timestamp",
                    "operating_hours_timestamp", "idle_hours_timestamp", "fuel_consumption_timestamp",
                    "fuel_remaining_timestamp", "def_remaining_timestamp", "location_timestamp",
                    "engine_status_timestamp", "pto_hours_timestamp", "load_count_timestamp",
                    "fuel_used_last24_timestamp", "fuel_tank_capacity_timestamp")


class FleetSnapshot(list):
    """List-compatible fleet plus unmodified original response pages/provenance."""
    def __init__(self):
        super().__init__()
        self.pages = []
        self.page_indices = []

    def raw_response_for(self, index):
        return self.pages[self.page_indices[index]]["text"]

    def snapshot_time_for(self, index):
        payload = self.pages[self.page_indices[index]]["payload"]
        fleet = payload.get("Fleet", payload)
        return fleet.get("@snapshotTime") or fleet.get("snapshotTime")

    def version_for(self, index):
        payload = self.pages[self.page_indices[index]]["payload"]
        fleet = payload.get("Fleet", payload)
        return fleet.get("@version") or fleet.get("version")


class KobelcoClient:
    def __init__(self, settings):
        self.base_url = validate_base_url(settings.base_url)
        if not settings.username or not settings.username.strip():
            raise KobelcoError("Kobelco username is required.")
        password = settings.get_password("password", raise_exception=False)
        if not password:
            raise KobelcoError("Kobelco password is required.")
        self.auth = HTTPBasicAuth(settings.username.strip(), password)

    def resolve_url(self, link, current=None):
        """Leading-slash API links are relative to the configured API base path."""
        if not isinstance(link, str) or not link or "\\" in link:
            raise KobelcoError("Invalid Kobelco pagination link.")
        parts, base = urlsplit(link), urlsplit(self.base_url)
        decoded = unquote(parts.path)
        if "\\" in decoded or ".." in decoded.split("/") or parts.username or parts.password:
            raise KobelcoError("Unsafe Kobelco pagination link.")
        if parts.netloc or parts.scheme:
            url = link
        elif not parts.path:
            url = urljoin(current or self.base_url, link)
        elif decoded.startswith(base.path):
            url = urlunsplit((base.scheme, base.netloc, parts.path, parts.query, ""))
        elif parts.path.startswith("/") or parts.path.startswith("Fleet/"):
            url = urljoin(self.base_url, link.lstrip("/"))
        else:
            url = urljoin(current or self.base_url, link)
        target = urlsplit(url)
        normalized = posixpath.normpath(unquote(target.path))
        if ((target.scheme, target.netloc) != (base.scheme, base.netloc)
                or not normalized.startswith(unquote(base.path)) or target.fragment):
            raise KobelcoError("Kobelco pagination must stay within the configured API base URL.")
        return url

    def _get(self, url):
        try:
            response = requests.get(url, auth=self.auth, headers={"Accept": "application/json"},
                                    timeout=(10, 60), allow_redirects=False)
        except requests.RequestException:
            raise KobelcoError("Kobelco connection failed or timed out.") from None
        if response.status_code in (401, 403):
            raise KobelcoError("Authentication failed. Check the Kobelco username and password.")
        if 300 <= response.status_code < 400:
            raise KobelcoError("Kobelco returned a redirect. Configure the final HTTPS Base URL.")
        if response.status_code != 200:
            raise KobelcoError(f"Kobelco returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError:
            raise KobelcoError("Kobelco returned invalid JSON.") from None
        body = response.text if isinstance(response.text, str) else json.dumps(payload)
        return payload, body

    def fetch_fleet(self):
        url, visited, rows = self.resolve_url("Fleet/1"), set(), FleetSnapshot()
        for _ in range(100):
            if url in visited:
                raise KobelcoError("Kobelco pagination loop detected.")
            visited.add(url)
            payload, body = self._get(url)
            if not isinstance(payload, dict):
                raise KobelcoError("Kobelco Fleet response must be a JSON object.")
            fleet = payload.get("Fleet", payload)
            if not isinstance(fleet, dict) or not isinstance(fleet.get("Equipment"), list):
                raise KobelcoError("Kobelco Fleet response must contain an Equipment list.")
            rows.pages.append({"payload": payload, "text": body})
            for item in fleet["Equipment"]:
                if not isinstance(item, dict):
                    raise KobelcoError("Kobelco Equipment entries must be JSON objects.")
                rows.append(item)
                rows.page_indices.append(len(rows.pages) - 1)
            links = fleet.get("Links", [])
            if not isinstance(links, list) or any(not isinstance(link, dict) for link in links):
                raise KobelcoError("Kobelco pagination Links must be a list of objects.")
            next_links = [link.get("href") for link in links if str(link.get("rel", "")).lower() == "next"]
            if len(next_links) > 1:
                raise KobelcoError("Kobelco returned multiple next-page links.")
            if not next_links:
                return rows
            url = self.resolve_url(next_links[0], url)
        raise KobelcoError("Kobelco Fleet exceeds the 100-page safety limit.")


def _timestamp(value):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (ValueError, TypeError):
        raise KobelcoError("Kobelco returned an invalid snapshot timestamp.") from None


def _source_timestamp(metric):
    # Kobelco's XML-derived JSON uses @datetime; also retain plain AEMP JSON support.
    return _timestamp(metric.get("@datetime") or metric.get("datetime"))


def _metric(row, name):
    value = row.get(name)
    if value is None:
        return {}
    if isinstance(value, list):
        if not value:
            return {}
        if any(not isinstance(item, dict) for item in value):
            raise KobelcoError(f"Invalid Kobelco {name} data.")
        value = max(value, key=lambda item: _source_timestamp(item) or datetime.min)
    if not isinstance(value, dict):
        raise KobelcoError(f"Invalid Kobelco {name} data.")
    return value


def _number(value, label, minimum=0, maximum=None):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise KobelcoError(f"Invalid Kobelco {label} measurement.") from None
    if isinstance(value, bool) or not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise KobelcoError(f"Invalid Kobelco {label} measurement.")
    return result


def normalize_equipment(row, fleet_timestamp=None):
    header = row.get("EquipmentHeader")
    if not isinstance(header, dict) or not str(header.get("SerialNumber") or "").strip():
        raise KobelcoError("Kobelco machine is missing its serial number; model-only mapping is not allowed.")
    result = {
        "serial_number": str(header["SerialNumber"]).strip().upper(),
        "pin": str(header.get("PIN") or "").strip().upper() or None,
        "oem": str(header.get("OEMName") or "").strip(),
        "model": str(header.get("Model") or "").strip(),
        "unit_install_timestamp": _timestamp(header.get("UnitInstallDateTime")),
    }
    metrics = (
        ("CumulativeOperatingHours", "Hour", "operating_hours", None),
        ("CumulativeIdleHours", "Hour", "idle_hours", None),
        ("FuelUsed", "FuelConsumed", "fuel_consumption", None),
        ("FuelRemaining", "Percent", "fuel_remaining", 100),
        ("DEFRemaining", "Percent", "def_remaining", 100),
        ("CumulativePowerTakeOffHours", "Hour", "pto_hours", None),
        ("CumulativeLoadCount", "Count", "load_count", None),
        ("FuelUsedLast24", "FuelConsumed", "fuel_used_last24", None),
        ("FuelRemaining", "FuelTankCapacity", "fuel_tank_capacity", None),
    )
    for source, key, field, maximum in metrics:
        metric = _metric(row, source)
        result[field] = _number(metric.get(key), field, maximum=maximum)
        result[field + "_timestamp"] = _source_timestamp(metric)
        if source == "FuelUsed":
            result["fuel_units"] = metric.get("FuelUnits")
        elif source == "FuelUsedLast24":
            result["fuel_used_last24_units"] = metric.get("FuelUnits")
        elif field == "fuel_tank_capacity":
            result["fuel_tank_capacity_units"] = metric.get("FuelTankCapacityUnits")
    location = _metric(row, "Location")
    result["latitude"] = _number(location.get("Latitude"), "latitude", -90, 90)
    result["longitude"] = _number(location.get("Longitude"), "longitude", -180, 180)
    result["location_timestamp"] = _source_timestamp(location)
    result["altitude"] = _number(location.get("Altitude"), "altitude", minimum=-math.inf)
    result["altitude_units"] = location.get("AltitudeUnits")
    engine = _metric(row, "EngineStatus")
    running = engine.get("Running")
    if running is None or running == "":
        result["engine_status"] = None
    elif running is True or str(running).lower() in ("true", "1"):
        result["engine_status"] = "Running"
    elif running is False or str(running).lower() in ("false", "0"):
        result["engine_status"] = "Stopped"
    else:
        raise KobelcoError("Invalid Kobelco engine status.")
    result["engine_status_timestamp"] = _source_timestamp(engine)
    result["engine_number"] = str(engine["EngineNumber"]) if engine.get("EngineNumber") is not None else None
    if result["load_count"] is not None:
        if not result["load_count"].is_integer():
            raise KobelcoError("Invalid Kobelco load count measurement.")
        result["load_count"] = int(result["load_count"])
    timestamps = [v for k, v in result.items()
                  if k.endswith("_timestamp") and k != "unit_install_timestamp" and v is not None]
    fleet_stamp = _timestamp(fleet_timestamp or row.get("_fleet_timestamp"))
    result["fleet_snapshot_timestamp"] = fleet_stamp
    result["snapshot_timestamp"] = fleet_stamp or max(timestamps, default=None)
    result["snapshot_time_basis"] = "Fleet snapshot" if fleet_stamp else "Latest source measurement" if timestamps else None
    future_fields = sorted(k for k, value in result.items() if k.endswith("_timestamp")
                           and value and fleet_stamp and value > fleet_stamp)
    result["source_time_warning"] = ("Source timestamps later than Fleet snapshot: " + ", ".join(future_fields)) if future_fields else None
    return result
