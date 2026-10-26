import unittest
from datetime import datetime

from engineering.engineering.page.machine_reliability import calculations as c


def row(name, start='2026-08-01 00:00:00', end='2026-08-01 04:00:00', meter=100, fleet='A', reason='brakes failed', resolution='', kind='Breakdown'):
    return dict(name=name, asset_name=fleet, breakdown_start_datetime=start,
                resolved_datetime=end, hours_breakdown_starts=meter,
                breakdown_reason=reason, resolution_summary=resolution,
                downtime_type=kind, location='Old Site', asset_category='ADT')


class TestCalculations(unittest.TestCase):
    def test_reason_wins_and_keywords_are_words_or_phrases(self):
        self.assertEqual(c.classify('brakes failed', 'brake replaced', ['brake', 'brakes'])[0], 'direct')
        self.assertEqual(c.classify('engine stopped', 'brakes adjusted', ['brakes'])[0], 'additional')
        self.assertIsNone(c.classify('aircon repaired', '', ['air'])[0])
        self.assertEqual(c.classify('AIR-conditioning failed', '', ['air conditioning'])[0], 'direct')
        self.assertEqual(c.terms('brake, BRAKE\noil leak'), ['brake', 'oil leak'])

    def test_record_average_is_separate_from_unique_time_and_overlap(self):
        records = [row('one'), row('two', '2026-08-01 02:00:00', '2026-08-01 06:00:00', 102),
                   row('reverse', end='2026-07-31 23:00:00'), row('open', end=None)]
        report = c.build_report(records, [], ['brakes'], '2026-08-01', '2026-08-31')
        self.assertEqual(report['summary']['average_standing_hours'], 4)
        self.assertEqual(report['summary']['unique_standing_hours'], 6)
        self.assertEqual(report['summary']['standing_records'], 2)
        self.assertEqual(report['quality']['overlapping_records'], 2)
        self.assertEqual(report['quality']['reversed_intervals'], 1)
        self.assertEqual(report['quality']['incomplete_intervals'], 1)

    def test_intervals_never_mix_fleets_and_additional_work_is_not_failure(self):
        records = [row('a1'), row('b1', meter=5000, fleet='B'),
                   row('extra', '2026-08-02 00:00:00', meter=105, reason='engine', resolution='brakes adjusted'),
                   row('a2', '2026-08-03 00:00:00', meter=110),
                   row('b2', '2026-08-03 00:00:00', meter=5030, fleet='B')]
        report = c.build_report(records, [], ['brakes'], '2026-08-01', '2026-08-31')
        self.assertEqual([x['gap_hours'] for x in report['intervals']], [10, 30])
        self.assertEqual(report['summary']['average_failure_gap'], 20)
        self.assertEqual(report['summary']['direct_failures'], 4)
        self.assertEqual(report['summary']['additional_work'], 1)
        self.assertEqual([(x['fleet'], x['average_gap']) for x in report['machines']], [('A', 10), ('B', 30)])

    def test_invalid_meter_does_not_get_bridged(self):
        records = [row('a'), row('missing', '2026-08-02 00:00:00', meter=0),
                   row('c', '2026-08-03 00:00:00', meter=110),
                   row('down', '2026-08-04 00:00:00', meter=90),
                   row('same', '2026-08-05 00:00:00', meter=90),
                   row('jump', '2026-08-06 00:00:00', meter=10000)]
        report = c.build_report(records, [], ['brakes'], '2026-08-01', '2026-08-31')
        self.assertEqual(report['intervals'], [])
        self.assertIsNone(report['summary']['average_failure_gap'])
        self.assertEqual([x['gap_status'] for x in report['history']],
                         ['First failure in range', 'Missing reading', 'Missing reading', 'Decreasing reading', 'Unchanged reading', 'Implausible increase'])

    def test_planned_maintenance_and_legal_services_are_context_not_failures(self):
        records = [row('planned', kind='Planned Maintenance'), row('additional', reason='engine', resolution='brakes'), row('other', reason='tyre')]
        legal = [dict(name='test', sections='Brake Test', fleet_number='A', start_date='2026-08-02', event_type='test'),
                 dict(name='service', sections='Machine Service Records', fleet_number='A', start_date='2026-08-03', event_type='service')]
        report = c.build_report(records, legal, ['brakes'], '2026-08-01', '2026-08-31')
        self.assertEqual(report['summary']['problem_records'], 2)
        self.assertEqual(report['summary']['direct_failures'], 0)
        self.assertEqual(report['summary']['tests'], 1)
        self.assertEqual(report['summary']['services'], 1)
        self.assertEqual(len(report['top_all']), 2)  # All faults: Breakdown only.
        self.assertEqual(report['top_problem'], [])
        self.assertTrue(all(x['machine_hours'] is None for x in report['legal']))

    def test_window_clips_unique_time_but_not_recorded_duration(self):
        report = c.build_report([row('long', '2026-08-31 22:00:00', '2026-09-01 06:00:00')], [], ['brakes'], '2026-08-01', '2026-08-31')
        self.assertEqual(report['summary']['average_standing_hours'], 8)
        self.assertEqual(report['summary']['unique_standing_hours'], 2)

    def test_empty_report_has_unavailable_averages(self):
        report = c.build_report([], [], ['brakes'], '2026-08-01', '2026-08-31')
        self.assertIsNone(report['summary']['average_failure_gap'])
        self.assertIsNone(report['summary']['average_standing_hours'])
        self.assertEqual(report['summary']['problem_records'], 0)

    def test_frequency_retains_invalid_deltas_without_changing_averages(self):
        records = [row('a', meter=100), row('b', '2026-08-02 00:00:00', meter=110),
                   row('c', '2026-08-03 00:00:00', meter=90),
                   row('d', '2026-08-04 00:00:00', meter=0),
                   row('other', '2026-08-04 00:00:00', meter=5000, fleet='B')]
        report = c.build_report(records, [], ['brakes'], '2026-08-01', '2026-08-31')
        frequency = c.build_frequency(report['history'], records)
        self.assertEqual([x['hour_difference'] for x in frequency], [None, 10, -20, None, None])
        self.assertEqual([x['valid_difference'] for x in frequency], [False, True, False, False, False])
        self.assertEqual(frequency[2]['previous_machine_hours'], 110)
        self.assertEqual(frequency[2]['current_machine_hours'], 90)
        self.assertEqual(frequency[3]['current_machine_hours'], 0)
        self.assertIsNone(frequency[4]['previous_machine_hours'])
        self.assertEqual(report['summary']['average_failure_gap'], 10)
