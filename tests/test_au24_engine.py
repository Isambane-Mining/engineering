"""Confirmed formula checks plus configuration metadata contracts.

For the requested minimal check, run just Engine24Tests (two examples).
"""
import importlib
import json
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

MODULE = 'engineering.engineering.report.availability_and_utilisation_engine_(24).availability_and_utilisation_engine_(24)'
ROOT = Path(__file__).resolve().parents[1]


class Engine24Tests(unittest.TestCase):
    def test_machine_scope_classification(self):
        from types import SimpleNamespace
        module = importlib.import_module(MODULE)
        filter_assets_by_scope = module.filter_assets_by_scope

        assets = [
            SimpleNamespace(name="ASSET-001", asset_name="ADT001"),
            SimpleNamespace(name="ASSET-002", asset_name="ADT002"),
            SimpleNamespace(name="ASSET-003", asset_name="ADT003"),
        ]
        spares = {"ASSET-002", "ADT003"}

        self.assertEqual(
            len(filter_assets_by_scope(assets, spares, "All Machines")), 3
        )
        self.assertEqual(
            [a.asset_name for a in filter_assets_by_scope(assets, spares, "Production Machines")],
            ["ADT001"],
        )
        self.assertEqual(
            [a.asset_name for a in filter_assets_by_scope(assets, spares, "Spare Machines")],
            ["ADT002", "ADT003"],
        )

    def test_industry_shift_level_calculations_and_weighted_totals(self):
        c = importlib.import_module(MODULE)

        day = c.calculate_shift(
            working=9,
            breakdown=2,
            planned_maintenance=1,
        )
        night = c.calculate_shift(
            working=7,
            breakdown=1,
            planned_maintenance=0,
        )

        self.assertEqual(day["total_hours"], 12)
        self.assertEqual(day["availability_available"], 9)
        self.assertEqual(day["use_of_availability_available"], 9)
        self.assertEqual(day["utilisation_available"], 12)
        self.assertAlmostEqual(day["availability_percent"], .75)
        self.assertAlmostEqual(day["use_of_availability_percent"], 1)
        self.assertAlmostEqual(day["utilisation_percent"], .75)

        self.assertEqual(night["total_hours"], 12)
        self.assertEqual(night["availability_available"], 11)
        self.assertEqual(night["use_of_availability_available"], 11)
        self.assertEqual(night["utilisation_available"], 12)
        self.assertAlmostEqual(night["availability_percent"], 11 / 12)
        self.assertAlmostEqual(night["use_of_availability_percent"], 7 / 11)
        self.assertAlmostEqual(night["utilisation_percent"], 7 / 12)

        total = c.total_row([day, night])
        self.assertEqual(total["total_hours"], 24)
        self.assertEqual(total["working_hours"], 16)
        self.assertEqual(total["availability_available"], 20)
        self.assertEqual(total["use_of_availability_available"], 20)
        self.assertEqual(total["utilisation_available"], 24)
        self.assertAlmostEqual(total["availability_percent"], 20 / 24)
        self.assertAlmostEqual(total["use_of_availability_percent"], 16 / 20)
        self.assertAlmostEqual(total["utilisation_percent"], 16 / 24)

    def test_industry_shift_overrun_and_negative_availability(self):
        c = importlib.import_module(MODULE)

        overrun = c.calculate_shift(
            working=13,
            breakdown=0,
            planned_maintenance=0,
        )
        self.assertGreater(overrun["utilisation_percent"], 1)
        self.assertTrue(overrun["utilisation_inconsistent"])
        self.assertTrue(overrun["use_of_availability_inconsistent"])

        overdrawn = c.calculate_shift(
            working=0,
            breakdown=13,
            planned_maintenance=0,
        )
        self.assertEqual(overdrawn["availability_available"], -1)
        self.assertAlmostEqual(overdrawn["availability_percent"], -1 / 12)
        self.assertIsNone(overdrawn["use_of_availability_percent"])

    def test_industry_use_availability_hours_equal_availability_hours(self):
        c = importlib.import_module(MODULE)

        result = c.calculate_shift(
            working=11,
            breakdown=2,
            planned_maintenance=1,
        )

        self.assertEqual(result["availability_available"], 9)
        self.assertEqual(result["use_of_availability_available"], 9)
        self.assertAlmostEqual(result["use_of_availability_percent"], 11 / 9)
        self.assertTrue(result["use_of_availability_inconsistent"])

        total = c.total_row([result])
        self.assertEqual(total["availability_available"], 9)
        self.assertEqual(total["use_of_availability_available"], 9)
        self.assertAlmostEqual(total["use_of_availability_percent"], 11 / 9)

    def test_isambane_original_engine_formula_and_ratios(self):
        c = importlib.import_module(MODULE)
        from engineering.engineering.report.availability_and_utilisation_engine import availability_and_utilisation_engine as engine
        # Actual canonical formula used by the Isambane report path, not a copy.
        row = dict(required_hours=18, work_hours=12, pbm_total_downtime=4)
        engine.calculate_availability_values(row)
        self.assertEqual(row['availability_available_hours'], 14)
        self.assertEqual(row['utilisation_available_hours'], 14)
        self.assertAlmostEqual(c.ratio(row['availability_available_hours'], 18), 14 / 18)
        self.assertAlmostEqual(c.ratio(12, row['utilisation_available_hours']), 12 / 14)
        self.assertEqual(c.TARGETS['Isambane Formula'], (.85, .85))
        print('Isambane example: R=18; PBM=4; W=12; A/U hours=14; A ratio=0.7777777778; U ratio=0.8571428571')


class MetadataTests(unittest.TestCase):
    def test_original_startup_fatigue_metadata(self):
        doc = json.loads((ROOT / 'engineering/engineering/doctype/startup_and_fatigue_spesification/startup_and_fatigue_spesification.json').read_text())
        fields = {f['fieldname']: f for f in doc['fields']}

        self.assertEqual(fields['shift']['options'].splitlines(), ['Day', 'Night'])
        self.assertEqual(fields['day_type']['options'].splitlines(), ['Weekday', 'Saturday', 'Sunday'])

        for key in ('site', 'shift', 'day_type', 'startup_start', 'startup_end', 'fatigue_start', 'fatigue_end'):
            self.assertIn(key, fields)

        self.assertFalse((ROOT / 'engineering/engineering/doctype/site_specific_startup_and_fatigue').exists())

    def test_report_is_resolvable_by_frappe_exact_name(self):
        # Frappe scrub retains parentheses; do not silently use a different title.
        package = 'engineering.engineering.report.availability_and_utilisation_engine_(24).availability_and_utilisation_engine_(24)'
        module = importlib.import_module(package)
        self.assertTrue(callable(module.execute))



if __name__ == '__main__':
    unittest.main()
