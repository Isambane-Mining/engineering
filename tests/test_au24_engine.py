"""Confirmed formula checks plus configuration metadata contracts.

For the requested minimal check, run just Engine24Tests (two examples).
"""
import importlib
import json
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

MODULE = 'engineering.engineering.report.availability_and_utilisation_engine_(24).calculations'
ROOT = Path(__file__).resolve().parents[1]


class Engine24Tests(unittest.TestCase):
    def test_industry_fixed_24_raw_downtime_and_ratios(self):
        c = importlib.import_module(MODULE)
        forbidden = Mock(side_effect=AssertionError('Industry accessed configuration'))
        result = c.calculate_day(date(2026, 3, 2), working=12, configuration=forbidden,
            downtime=[('Breakdown', datetime(2026, 3, 2, 6), datetime(2026, 3, 2, 9)),
                      ('Planned Maintenance', datetime(2026, 3, 2, 8), datetime(2026, 3, 2, 9))])
        self.assertEqual(result['breakdown_hours'], 3)
        self.assertEqual(result['planned_maintenance_hours'], 1)
        self.assertEqual(result['availability_available'], 20)
        self.assertEqual(result['utilisation_available'], 24)
        self.assertAlmostEqual(result['availability_percent'], 20 / 24)
        self.assertEqual(result['utilisation_percent'], .5)
        self.assertEqual(c.TARGETS['Industry Formula'], (.85, .75))
        forbidden.assert_not_called()
        print('Industry example: A hours=20; U hours=24; A ratio=0.8333333333; U ratio=0.5')

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
