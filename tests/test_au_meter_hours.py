"""Database-free regressions from EX015's October read-only investigation.

Run from the app root with the bench Python and PYTHONPATH set to this checkout.
Only source-read boundaries are mocked; Engine and report arithmetic is real.
"""
import copy
import json
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from engineering.engineering.report.availability_and_utilisation_engine import (
    availability_and_utilisation_engine as engine,
)
from engineering.engineering.report.availability_and_utilisation_month_end_report import (
    availability_and_utilisation_month_end_report as month_end,
)
from engineering.engineering.report.weekly_availability_and_utilisation_dashboard import (
    weekly_availability_and_utilisation_dashboard as weekly,
)
from engineering.engineering.page.daily_availability_and_utilization_dashboard import (
    daily_availability_and_utilization_dashboard as daily,
)

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/ex015_october_2026.json').read_text())
FLAGGED = [('2026-10-16', 'Day', 12), ('2026-10-23', 'Day', 8),
           ('2026-10-24', 'Day', 8), ('2026-10-25', 'Night', 5),
           ('2026-10-28', 'Day', 10)]


class NoDatabase:
    def __getattr__(self, name):
        raise AssertionError(f'Unexpected database access: {name}')


@contextmanager
def source_records():
    """Supply the actual plan/meters/PBM inputs without opening any site."""
    plan = {}
    preuse = {}
    pbm = {}
    downtime = {}
    for r in FIXTURE:
        key = ('Uitgevallen', r['shift_date'])
        plan.setdefault(key, dict(shift_system='2x12Hour', saturday_shift_hours=7))
        plan[key]['shift_' + r['shift'].lower() + '_hours'] = r['required_hours']
        if 'meter_start' in r:
            preuse[(*key, r['shift'], 'EX015')] = dict(
                eng_hrs_start=r['meter_start'], eng_hrs_end=r['meter_end'],
                pre_use_avail_status='1')
        pbm[('EX015', r['shift_date'], 'Uitgevallen', r['shift'])] = {
            k: v for k, v in r.items() if k.startswith(('pbm_', 'breakdown_', 'planned_maintenance_'))}
        downtime[(r['shift_date'], r['shift'])] = r['planned_downtime']
    asset = frappe._dict(name='EX015', asset_name='EX015', asset_category='Excavator',
                         location='Uitgevallen', company='Isambane')
    with ExitStack() as stack:
        for name, value in [('get_planning_rows', [frappe._dict(name='October', location='Uitgevallen')]),
                            ('build_planning_map', plan), ('get_assets', [asset]),
                            ('get_spare_swing_assets', set()), ('get_required_hours_exception_map', {}),
                            ('get_preuse_map', preuse), ('get_pbm_map', pbm)]:
            stack.enter_context(patch.object(engine, name, return_value=copy.deepcopy(value)))
        stack.enter_context(patch.object(engine, 'get_shift_planned_downtime',
            side_effect=lambda location, date, shift: downtime[(str(date), shift)]))
        stack.enter_context(patch.object(frappe, 'get_all', return_value=[]))
        yield asset


def engine_rows(basis='100% A & U'):
    return engine.get_data(frappe._dict(from_date='2026-10-01', to_date='2026-10-31',
        locations=['Uitgevallen'], assets=['EX015'], companies=[], free_hours=0,
        production_machines_only=0, au_percentage_basis=basis))


def shift_rows(rows):
    return [r for r in rows if r.get('indent') == 3 and not r.get('is_formula_row')]


class TestRecordedMeterHours(unittest.TestCase):
    def setUp(self):
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        self.context.enter_context(patch.object(frappe, 'db', NoDatabase(), create=True))
        self.context.enter_context(patch.object(frappe, 'local', SimpleNamespace(lang='en')))
        self.context.enter_context(patch('frappe.translate.get_all_translations', return_value={}))
        for name in ('init', 'connect', 'sendmail', 'enqueue'):
            self.context.enter_context(patch.object(frappe, name, side_effect=AssertionError(name)))

    def test_each_flagged_shift_keeps_integrity_valid_work_and_reason(self):
        with source_records():
            shifts = shift_rows(engine_rows())
        for date, shift, hours in FLAGGED:
            with self.subTest(date=date, shift=shift):
                row = next(r for r in shifts if str(r['shift_date']) == date and r['shift'] == shift)
                self.assertEqual(row['invalid_pre_use'], 0)
                self.assertEqual(row['invalid_au'], 1)
                self.assertIn('exceeds', row['au_validation_status'])
                summary = engine.build_summary_row([row], indent=2)
                self.assertEqual(summary['work_hours'], hours)
                self.assertEqual(summary['required_hours'], row['required_hours'])
                self.assertEqual(summary['au_validation_level'], 'invalid')
                self.assertEqual(summary['au_problem_day_count'], 1)

    def test_full_month_and_tree_levels_reconcile_hours_and_downtime(self):
        with source_records():
            rows = engine_rows()
        summary = next(r for r in rows if r['indent'] == 0)
        self.assertEqual(summary['work_hours'], 314)
        self.assertEqual(summary['required_hours'], 466)
        self.assertEqual(summary['pbm_total_downtime'], 45.733)
        self.assertEqual(summary['utilisation_available_hours'], 446.834)
        self.assertEqual(summary['availability_available_hours'], 479.834)
        self.assertEqual(summary['utilisation_percentage'], 70.272)
        self.assertEqual(summary['availability_percentage'], 102.969)
        self.assertEqual(summary['au_problem_day_count'], 5)
        self.assertIn('5 invalid', summary['au_validation_status'])
        for indent in (1, 2):
            self.assertEqual(sum(r['work_hours'] for r in rows if r['indent'] == indent), 314)
            self.assertEqual(sum(r['required_hours'] for r in rows if r['indent'] == indent), 466)
        self.assertEqual(sum(r['work_hours'] for r in shift_rows(rows)), 314)
        self.assertAlmostEqual(summary['utilisation_percentage'],
            314 / summary['utilisation_available_hours'] * 100, places=3)
        self.assertAlmostEqual(summary['availability_percentage'],
            summary['availability_available_hours'] / 466 * 100, places=3)

    def test_flag_does_not_blank_defined_shift_percentage(self):
        with source_records():
            rows = shift_rows(engine_rows())
        row = next(r for r in rows if str(r['shift_date']) == '2026-10-16' and r['shift'] == 'Day')
        self.assertEqual(row['utilisation_percentage'], 133.333)
        self.assertEqual(row['invalid_au'], 1)

    def test_sunday_work_retained_without_inventing_a_percentage(self):
        with source_records():
            rows = shift_rows(engine_rows())
        sunday = [r for r in rows if str(r['shift_date']) == '2026-10-25']
        summary = engine.build_summary_row(sunday, indent=1)
        self.assertEqual(summary['work_hours'], 5)
        self.assertEqual(summary['required_hours'], 0)
        self.assertEqual(summary['availability_available_hours'], 5)
        self.assertIsNone(summary['availability_percentage'])
        self.assertIsNone(summary['utilisation_percentage'])
        self.assertEqual(sunday[1]['invalid_au'], 1)

    def test_integrity_limits_still_exclude_bad_meter_hours(self):
        cases = [
            # date, Saturday plan, shift hours, expected accepted work
            ('2026-10-14', 7, [12], 12),
            ('2026-10-14', 7, [12.01], 0),
            ('2026-10-14', 7, [12, 12], 24),
            ('2026-10-14', 7, [9, 8, 8], 0),  # daily >24, each shift <=12
            ('2026-10-17', 7, [9, 9], 18),
            ('2026-10-17', 7, [9.01], 0),
            ('2026-10-17', 7, [7, 6, 6], 0),  # daily >18, each shift <=9
            ('2026-10-17', 9, [12, 12], 24),
            ('2026-10-17', 9, [12.01], 0),
            ('2026-10-17', 8, [1], 0),  # unsupported Saturday configuration
        ]
        for date, saturday, hours, expected in cases:
            with self.subTest(date=date, saturday=saturday, hours=hours):
                rows = [dict(asset_category='Excavator', asset_name='EX015', location='Uitgevallen',
                    shift_date=date, shift=str(i), work_hours=h, required_hours=9,
                    planned_downtime=3, saturday_shift_hours=saturday, pbm_total_downtime=0)
                    for i, h in enumerate(hours)]
                engine.mark_invalid_preuse_rows(rows)
                for row in rows:
                    engine.calculate_availability_values(row)
                    engine.validate_au_row(row)
                self.assertEqual(engine.build_summary_row(rows, 0)['work_hours'], expected)

    def test_invalid_meter_does_not_remove_valid_sibling_shift(self):
        rows = [dict(asset_category='Excavator', asset_name='EX015', location='Uitgevallen',
            shift_date='2026-10-14', shift=shift, work_hours=hours, required_hours=9,
            planned_downtime=3, pbm_total_downtime=0) for shift, hours in [('Day', 13), ('Night', 8)]]
        engine.mark_invalid_preuse_rows(rows)
        self.assertEqual(engine.build_summary_row(rows, 0)['work_hours'], 8)

    def test_manual_au_flag_exclusion_never_changes_recorded_work(self):
        row = dict(work_hours=8, required_hours=9, planned_downtime=3,
            pbm_total_downtime=4, invalid_pre_use=0, invalid_au=1,
            au_validation_level='invalid', invalid_au_excluded=1, shift_date='2026-10-23')
        engine.calculate_availability_values(row)
        self.assertEqual(engine.build_summary_row([row], 0)['work_hours'], 8)

    def test_month_end_machine_and_scopes_retain_hours_and_visible_reasons(self):
        with source_records() as asset, ExitStack() as stack:
            for name, value in [('get_spare_swing_asset_map', {}), ('_get_submitted_assets', [asset]),
                                ('get_general_lost_hour_machine_reason_details', {}),
                                ('get_plant_breakdown_reason_details', {})]:
                stack.enter_context(patch.object(month_end, name, return_value=value))
            stack.enter_context(patch.object(month_end.detailed_au, 'get_grouped_data', return_value=[]))
            stack.enter_context(patch.object(month_end, 'nowdate', return_value='2026-11-06'))
            for basis in ('100% A & U', '85% A & U'):
                with self.subTest(basis=basis):
                    rows = month_end.get_data(frappe._dict(from_date='2026-10-01', to_date='2026-10-31',
                        location='Uitgevallen', asset_category='Excavator', au_target_filter=basis))
                    self.assertEqual(len(rows), 3)  # overall, production, machine
                    for row in rows:
                        self.assertEqual(row['work_hrs'], 314)
                        self.assertEqual(row['required_hrs'], 466)
                        self.assertEqual(row['mechanical_downtime'], 45.733)
                        self.assertEqual(row['available_hrs'], 446.8)
                        self.assertEqual(row['available_hrs_above_100'], 479.8)
                        self.assertEqual(row['util_percent'], 70.272 if basis == '100% A & U' else 59.731)
                        self.assertEqual(row['avail_percent'], 102.969 if basis == '100% A & U' else 87.524)
                        self.assertEqual(row['au_validation_level'], 'invalid')
                        self.assertIn('5 invalid', row['au_validation_status'])
                    machine = next(r for r in rows if r.get('asset_name') == 'EX015')
                    for date, shift, hours in FLAGGED:
                        self.assertIn(date, machine['au_validation_status'])
                    self.assertTrue(any(col['fieldname'] == 'au_validation_status' for col in month_end.get_columns()))

    def test_month_end_keeps_production_and_spare_scopes_separate(self):
        with source_records():
            rows = shift_rows(engine_rows())
        spare = copy.deepcopy(next(r for r in rows if str(r['shift_date']) == '2026-10-16' and r['shift'] == 'Day'))
        spare.update(asset_name='EX016', is_spare_swing_unit=1)
        source = engine.build_tree_rows(rows + [spare])
        with ExitStack() as stack:
            for name, value in [('get_spare_swing_asset_map', {'EX016': 'Spare unit'}),
                                ('_get_submitted_assets', []),
                                ('get_general_lost_hour_machine_reason_details', {}),
                                ('get_plant_breakdown_reason_details', {})]:
                stack.enter_context(patch.object(month_end, name, return_value=value))
            stack.enter_context(patch.object(month_end, '_month_end_mpp_excluded_asset_keys', return_value=set()))
            stack.enter_context(patch.object(engine, 'get_data', return_value=source))
            stack.enter_context(patch.object(month_end.detailed_au, 'get_grouped_data', return_value=[]))
            stack.enter_context(patch.object(month_end, 'nowdate', return_value='2026-11-06'))
            result = month_end.get_data(frappe._dict(from_date='2026-10-01', to_date='2026-10-31',
                location='Uitgevallen', asset_category='Excavator', au_target_filter='100% A & U'))
        totals = {r['summary_scope']: r for r in result if r.get('is_scope_total')}
        self.assertEqual(totals['production']['work_hrs'], 314)
        self.assertEqual(totals['spare']['work_hrs'], 12)
        self.assertEqual(totals['overall']['work_hrs'], 326)
        self.assertEqual(totals['overall']['required_hrs'], 475)
        self.assertEqual(totals['overall']['mechanical_downtime'], 45.967)
        self.assertIn('6 invalid', totals['overall']['au_validation_status'])

    def test_warning_keeps_hours_and_investigation_reason_visible(self):
        row = dict(asset_name='EX015', shift_date='2026-10-25', shift='Night',
            work_hours=5, required_hours=0, planned_downtime=12, pbm_total_downtime=0)
        engine.calculate_availability_values(row)
        engine.validate_au_row(row)
        self.assertEqual(row['au_validation_level'], 'warning')
        self.assertIn('Required Hours is 0', row['au_validation_status'])
        summary = engine.build_summary_row([row], 2)
        self.assertEqual(summary['work_hours'], 5)
        self.assertIn('1 A&U warning', summary['au_validation_status'])
        output = {}
        month_end._month_end_attach_au_validation(output, summary, [row])
        self.assertIn('Required Hours is 0', output['au_validation_status'])

    def test_down_time_uses_corrected_hours_without_changing_mechanical_downtime(self):
        from engineering.engineering.report.down_time import down_time
        with source_records():
            rows = shift_rows(engine_rows())
        with patch.object(down_time.daily_au_dashboard, 'fetch_grouped_data', return_value=rows):
            result = down_time.get_avail_util_scope_summary('2026-10-31', 'Uitgevallen',
                                                           'Production + Swing/Spare Machines')
        self.assertEqual(result['excavators']['working_hours'], 314)
        self.assertEqual(result['excavators']['breakdown_hours'], 45.73)
        self.assertEqual(result['excavators']['utilisation'], 70.272)

    def test_downstream_daily_and_weekly_use_retained_hours(self):
        with source_records():
            rows = shift_rows(engine_rows())
        self.assertEqual(weekly.build_daily_series(rows, ['2026-10-25'])['Excavators'][0]['util'], None)
        series = daily.build_machine_series_from_source_rows(rows)['Excavator'][0]
        self.assertEqual(series['util'], 59.731)
        weekly_series = weekly.build_asset_series(rows)['Excavators'][0]
        self.assertEqual(weekly_series['util'], 70.272)
        production, spare = daily.build_scope_averages_from_source_rows(rows)
        self.assertEqual(production['Excavator']['util'], 59.731)
        self.assertIsNone(spare['Excavator']['util'])


if __name__ == '__main__':
    unittest.main()
