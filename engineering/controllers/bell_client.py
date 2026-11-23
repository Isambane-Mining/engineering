"""Bell ISO 15143-3 fleet API client and XML parser."""

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests


TOKEN_HOST = "sso.bellequipment.com"
FLEET_HOST = "b-fleet03.bellequipment.com"


class BellError(Exception):
    pass


@dataclass
class FleetSnapshot:
    machines: list
    snapshot_timestamp: datetime | None
    raw_xml: str


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _child(element, name):
    for item in element:
        if _tag(item) == name:
            return item
    return None


def _text(element, name):
    child = _child(element, name)
    return child.text.strip() if child is not None and child.text else None


def _datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        raise BellError("Bell returned an invalid timestamp.") from None


def _number(value):
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        raise BellError("Bell returned an invalid numeric measurement.") from None


def _boolean(value):
    if value is None:
        return None
    value = value.strip().lower()
    if value in ("true", "1", "yes"):
        return 1
    if value in ("false", "0", "no"):
        return 0
    raise BellError("Bell returned an invalid engine status.")


def _measurement(machine, element, fields):
    name = _tag(element)
    timestamp = _datetime(element.attrib.get("datetime"))

    for source, target in fields.items():
        value = _text(element, source)
        machine[target] = value

    return timestamp


def parse_fleet_xml(raw_xml):
    """Convert an ISO 15143-3 Fleet XML snapshot into normalized machines."""
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        raise BellError("Bell returned invalid XML.") from None

    if _tag(root) != "Fleet":
        raise BellError("Bell returned an unexpected fleet response.")

    machines = []
    snapshot_timestamp = _datetime(root.attrib.get("snapshotTime"))

    mappings = {
        "Location": {
            "Latitude": "latitude",
            "Longitude": "longitude",
        },
        "CumulativeIdleHours": {"Hour": "idle_hours"},
        "CumulativeLoadCount": {"Count": "load_count"},
        "CumulativeOperatingHours": {"Hour": "operating_hours"},
        "CumulativePayloadTotals": {
            "Payload": "payload",
            "PayloadUnits": "payload_units",
        },
        "DEFRemaining": {
            "Percent": "def_remaining",
            "DEFTankCapacityUnits": "def_tank_capacity_units",
        },
        "Distance": {
            "Odometer": "odometer",
            "OdometerUnits": "odometer_units",
        },
        "FuelUsed": {
            "FuelConsumed": "fuel_consumed",
            "FuelUnits": "fuel_units",
        },
        "FuelRemaining": {"Percent": "fuel_remaining"},
        "EngineStatus": {
            "EngineNumber": "engine_number",
            "Running": "engine_running",
        },
    }

    numeric = {
        "latitude", "longitude", "idle_hours", "load_count",
        "operating_hours", "payload", "def_remaining",
        "odometer", "fuel_consumed", "fuel_remaining",
    }

    for equipment in root:
        if _tag(equipment) != "Equipment":
            continue

        header = _child(equipment, "EquipmentHeader")
        if header is None:
            raise BellError("Bell equipment is missing its EquipmentHeader.")

        machine = {
            "equipment_id": _text(header, "EquipmentID"),
            "serial_number": _text(header, "SerialNumber"),
            "pin": _text(header, "PIN"),
            "oem": _text(header, "OEMName"),
            "model": _text(header, "Model"),
            "unit_install_timestamp": _datetime(
                _text(header, "UnitInstallDateTime")
            ),
            "fleet_snapshot_timestamp": snapshot_timestamp,
        }

        if not machine["pin"] and not machine["serial_number"]:
            raise BellError("Bell equipment has no reliable machine identifier.")

        for metric in equipment:
            name = _tag(metric)
            if name not in mappings:
                continue

            timestamp = _measurement(machine, metric, mappings[name])
            timestamp_fields = {
                "Location": "location_timestamp",
                "CumulativeIdleHours": "idle_hours_timestamp",
                "CumulativeLoadCount": "load_count_timestamp",
                "CumulativeOperatingHours": "operating_hours_timestamp",
                "CumulativePayloadTotals": "payload_timestamp",
                "DEFRemaining": "def_remaining_timestamp",
                "Distance": "odometer_timestamp",
                "FuelUsed": "fuel_consumed_timestamp",
                "FuelRemaining": "fuel_remaining_timestamp",
                "EngineStatus": "engine_status_timestamp",
            }
            machine[timestamp_fields[name]] = timestamp

        for field in numeric:
            if field in machine:
                machine[field] = _number(machine[field])

        if machine.get("load_count") is not None:
            if not machine["load_count"].is_integer():
                raise BellError("Bell returned a non-integer load count.")
            machine["load_count"] = int(machine["load_count"])

        if "engine_running" in machine:
            machine["engine_running"] = _boolean(machine["engine_running"])

        machines.append(machine)

    if not machines:
        raise BellError("Bell returned no equipment records.")

    return FleetSnapshot(
        machines=machines,
        snapshot_timestamp=snapshot_timestamp,
        raw_xml=raw_xml.decode("utf-8") if isinstance(raw_xml, bytes) else raw_xml,
    )


class BellClient:
    def __init__(self, settings, session=None):
        self.settings = settings
        self.session = session
        self.timeout = int(getattr(settings, "timeout", 30) or 30)

    def _post(self, url, **kwargs):
        if self.session is not None:
            return self.session.post(url, **kwargs)
        return requests.post(url, **kwargs)

    def _secret(self, field):
        try:
            return self.settings.get_password(field) or ""
        except Exception:
            return ""

    def _validate_url(self, url, expected_host):
        parsed = urlparse(url or "")
        if parsed.scheme != "https" or parsed.hostname != expected_host:
            raise BellError("Bell API URL is invalid or not approved.")

    def fetch_fleet(self):
        token_url = self.settings.token_url
        fleet_url = self.settings.fleet_url

        self._validate_url(token_url, TOKEN_HOST)
        self._validate_url(fleet_url, FLEET_HOST)

        username = (self.settings.username or "").strip()
        password = self._secret("password")
        client_id = (self.settings.client_id or "").strip()
        client_secret = self._secret("client_secret")
        scope = (self.settings.scope or "ISO_Exports").strip()

        if not all((username, password, client_id, client_secret)):
            raise BellError("Bell API credentials are incomplete.")

        try:
            response = self._post(
                token_url,
                data={
                    "grant_type": "password",
                    "username": username,
                    "password": password,
                    "scope": scope,
                },
                auth=(client_id, client_secret),
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise BellError("Bell authentication connection failed.") from None

        if not response.ok:
            raise BellError(
                f"Bell authentication failed (HTTP {response.status_code})."
            )

        try:
            token = response.json().get("access_token")
        except (ValueError, AttributeError):
            token = None

        if not token:
            raise BellError("Bell did not return an access token.")

        try:
            fleet = self._post(
                fleet_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/xml",
                },
                timeout=max(self.timeout, 60),
                allow_redirects=False,
            )
        except requests.RequestException:
            raise BellError("Bell fleet connection failed.") from None

        if not fleet.ok:
            raise BellError(
                f"Bell fleet request failed: "
                f"HTTP {fleet.status_code}; "
                f"method={fleet.request.method}; "
                f"url={fleet.url}; "
                f"allow={fleet.headers.get('Allow')}; "
                f"content_type={fleet.headers.get('Content-Type')}; "
                f"server={fleet.headers.get('Server')}."
            )

        return parse_fleet_xml(fleet.content)
