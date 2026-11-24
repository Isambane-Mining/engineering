import unittest
import xml.etree.ElementTree as ET
from types import SimpleNamespace

from engineering.controllers.bell_client import (
    BellClient,
    BellError,
    parse_fleet_xml,
)


XML = b"""<?xml version="1.0"?>
<Fleet xmlns="http://standards.iso.org/iso/15143/-3"
       snapshotTime="2026-11-20T11:28:13Z">
  <Equipment>
    <EquipmentHeader>
      <OEMName>BELL</OEMName>
      <Model>B40D</Model>
      <EquipmentID>IS 532</EquipmentID>
      <SerialNumber>AEBA840DC07204772</SerialNumber>
      <PIN>AEBA840DC07204772</PIN>
      <UnitInstallDateTime>2013-09-10T06:22:23Z</UnitInstallDateTime>
    </EquipmentHeader>
    <Location datetime="2026-11-20T10:00:01Z">
      <Latitude>-25.9777</Latitude>
      <Longitude>29.50140</Longitude>
    </Location>
    <CumulativeOperatingHours datetime="2026-11-19T22:00:00Z">
      <Hour>29144.80</Hour>
    </CumulativeOperatingHours>
    <CumulativeIdleHours datetime="2026-11-19T22:00:00Z">
      <Hour>4745.47</Hour>
    </CumulativeIdleHours>
    <CumulativeLoadCount datetime="2026-11-19T22:00:00Z">
      <Count>50868</Count>
    </CumulativeLoadCount>
    <DEFRemaining datetime="2026-11-19T22:00:00Z">
      <Percent>0.0</Percent>
      <DEFTankCapacityUnits>litre</DEFTankCapacityUnits>
    </DEFRemaining>
    <EngineStatus datetime="2026-11-19T22:00:00Z">
      <EngineNumber>1</EngineNumber>
      <Running>true</Running>
    </EngineStatus>
  </Equipment>
</Fleet>"""


class TestBellParser(unittest.TestCase):
    def test_fleet_identity_and_telemetry(self):
        result = parse_fleet_xml(XML)
        self.assertEqual(len(result.machines), 1)
        machine = result.machines[0]

        self.assertEqual(machine["equipment_id"], "IS 532")
        self.assertEqual(machine["pin"], "AEBA840DC07204772")
        self.assertEqual(machine["model"], "B40D")
        self.assertEqual(machine["operating_hours"], 29144.8)
        self.assertEqual(machine["idle_hours"], 4745.47)
        self.assertEqual(machine["load_count"], 50868.0)
        self.assertEqual(machine["latitude"], -25.9777)
        self.assertEqual(machine["engine_running"], 1)

    def test_zero_is_not_missing(self):
        machine = parse_fleet_xml(XML).machines[0]
        self.assertEqual(machine["def_remaining"], 0.0)

    def test_missing_measurements_remain_missing(self):
        root = ET.fromstring(XML)
        ns = "{http://standards.iso.org/iso/15143/-3}"
        equipment = root.find(f"{ns}Equipment")
        equipment.remove(equipment.find(f"{ns}CumulativeIdleHours"))

        xml = ET.tostring(root, encoding="utf-8")
        machine = parse_fleet_xml(xml).machines[0]

        self.assertNotIn("idle_hours", machine)
        self.assertNotIn("idle_hours_timestamp", machine)

    def test_raw_xml_is_retained(self):
        result = parse_fleet_xml(XML)
        self.assertIn("<Fleet", result.raw_xml)

    def test_invalid_xml_rejected(self):
        with self.assertRaises(BellError):
            parse_fleet_xml(b"<Fleet><broken></Fleet>")

    def test_wrong_root_rejected(self):
        with self.assertRaises(BellError):
            parse_fleet_xml(b"<Other/>")


class FakeResponse:
    def __init__(self, status, content=b"", data=None):
        self.status_code = status
        self.content = content
        self.ok = 200 <= status < 300
        self._data = data or {}

    def json(self):
        return self._data


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if "connect/token" in url:
            return FakeResponse(200, data={"access_token": "test-token"})
        return FakeResponse(200, content=XML)


class TestBellClient(unittest.TestCase):
    def test_oauth_and_fleet_request(self):
        settings = SimpleNamespace(
            token_url="https://sso.bellequipment.com/connect/token",
            fleet_url="https://b-fleet03.bellequipment.com:8080/Fleet",
            username="test-user",
            client_id="ISO_Export_Service",
            scope="ISO_Exports",
            timeout=30,
            get_password=lambda field: {
                "password": "test-password",
                "client_secret": "test-secret",
            }[field],
        )

        session = FakeSession()
        result = BellClient(settings, session=session).fetch_fleet()

        self.assertEqual(len(result.machines), 1)
        self.assertEqual(len(session.calls), 2)

        auth_call = session.calls[0][1]
        self.assertEqual(auth_call["data"]["grant_type"], "password")
        self.assertEqual(
            auth_call["auth"],
            ("ISO_Export_Service", "test-secret"),
        )

        fleet_call = session.calls[1][1]
        self.assertEqual(
            fleet_call["headers"]["Authorization"],
            "Bearer test-token",
        )

    def test_unapproved_token_host_rejected(self):
        settings = SimpleNamespace(
            token_url="https://example.com/token",
            fleet_url="https://b-fleet03.bellequipment.com:8080/Fleet",
        )
        with self.assertRaises(BellError):
            BellClient(settings).fetch_fleet()


if __name__ == "__main__":
    unittest.main()
