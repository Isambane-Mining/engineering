import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from engineering.controllers import bell


class FakeSettings:
    def __init__(self, rows=None):
        self.machine_mappings = rows or []
        self.counter = 0

    def append(self, fieldname, values):
        self.counter += 1
        row = SimpleNamespace(
            name=f"BELL-ROW-{self.counter}",
            equipment_id=None,
            pin=None,
            serial_number=None,
            oem=None,
            model=None,
            asset=None,
            mapping_status="Unmapped",
            last_seen=None,
        )
        self.machine_mappings.append(row)
        return row


def machine(pin="PIN-001", serial="SERIAL-001"):
    return {
        "equipment_id": "IS 532",
        "pin": pin,
        "serial_number": serial,
        "oem": "BELL",
        "model": "B40D",
    }


class TestBellIdentity(unittest.TestCase):

    def test_pin_is_primary_identity(self):
        self.assertEqual(
            bell._machine_key(machine()),
            "PIN-PIN-001",
        )

    def test_serial_is_fallback_identity(self):
        self.assertEqual(
            bell._machine_key(machine(pin=None)),
            "SERIAL-SERIAL-001",
        )

    def test_missing_identity_is_rejected(self):
        with self.assertRaises(bell.BellError):
            bell._machine_key(machine(pin=None, serial=None))


class TestBellMapping(unittest.TestCase):

    def test_discovery_preserves_manual_asset(self):
        row = SimpleNamespace(
            name="ROW-1",
            equipment_id="IS 532",
            pin="PIN-001",
            serial_number="SERIAL-001",
            oem="BELL",
            model="B40D",
            asset="EXISTING-ASSET",
            mapping_status="Mapped",
            last_seen=None,
        )
        settings = FakeSettings([row])

        with patch.object(bell, "now_datetime", return_value="2026-11-23 06:00:00"):
            result = bell._discover(machine(), settings)

        self.assertIs(result, row)
        self.assertEqual(result.asset, "EXISTING-ASSET")
        self.assertEqual(result.mapping_status, "Mapped")

    def test_new_machine_creates_unmapped_row(self):
        settings = FakeSettings()

        with patch.object(bell, "now_datetime", return_value="2026-11-23 06:00:00"):
            result = bell._discover(machine(), settings)

        self.assertEqual(len(settings.machine_mappings), 1)
        self.assertEqual(result.pin, "PIN-001")
        self.assertEqual(result.mapping_status, "Unmapped")
        self.assertIsNone(result.asset)

    def test_pin_and_serial_conflict_is_rejected(self):
        first = SimpleNamespace(
            name="ROW-1", pin="PIN-001",
            serial_number="SERIAL-001",
        )
        second = SimpleNamespace(
            name="ROW-2", pin="PIN-002",
            serial_number="SERIAL-002",
        )
        settings = FakeSettings([first, second])

        with self.assertRaises(bell.BellError):
            bell._discover(
                machine(pin="PIN-001", serial="SERIAL-002"),
                settings,
            )


class TestBellResultStorage(unittest.TestCase):

    def setUp(self):
        self.mapping = SimpleNamespace(
            name="ROW-1",
            asset="TEST-ASSET",
            mapping_status="Mapped",
        )

        self.telemetry = {
            **machine(),
            "operating_hours": 29144.8,
            "load_count": 50868,
            "engine_running": 1,
        }

    def test_existing_result_is_updated_not_duplicated(self):
        doc = Mock()

        fake_frappe = SimpleNamespace(
            db=SimpleNamespace(exists=Mock(return_value="PIN-PIN-001"), set_value=Mock()),
            get_doc=Mock(return_value=doc),
            new_doc=Mock(return_value=doc),
        )

        with patch.object(bell, "frappe", fake_frappe), \
             patch.object(bell, "now_datetime", return_value="2026-11-23 06:00:00"):
            result = bell._store_result(
                self.telemetry,
                self.mapping,
                "<Fleet/>",
            )

        self.assertEqual(result, "updated")
        doc.save.assert_called_once_with(ignore_permissions=True)
        doc.insert.assert_not_called()

        values = doc.update.call_args.args[0]
        self.assertEqual(values["asset"], "TEST-ASSET")
        self.assertEqual(values["operating_hours"], 29144.8)
        self.assertEqual(values["engine_running"], "Running")
        self.assertTrue(values["source_checksum"])

    def test_new_result_is_inserted_once(self):
        doc = Mock()

        fake_frappe = SimpleNamespace(
            db=SimpleNamespace(exists=Mock(return_value=None), set_value=Mock()),
            get_doc=Mock(return_value=doc),
            new_doc=Mock(return_value=doc),
        )

        with patch.object(bell, "frappe", fake_frappe), \
             patch.object(bell, "now_datetime", return_value="2026-11-23 06:00:00"):
            result = bell._store_result(
                self.telemetry,
                self.mapping,
                "<Fleet/>",
            )

        self.assertEqual(result, "created")
        doc.insert.assert_called_once_with(ignore_permissions=True)
        doc.save.assert_not_called()

    def test_checksum_is_deterministic(self):
        first = bell._checksum(self.telemetry)
        second = bell._checksum(dict(reversed(list(self.telemetry.items()))))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
