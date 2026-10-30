import unittest
from datetime import date, datetime


class TestCalculations(unittest.TestCase):
    def test_previous_month_and_year_rollover(self):
        from .calculations import reporting_period
        p = reporting_period(today=date(2027, 1, 15))
        self.assertEqual(p['reporting_month'], '2026-12-01')
        self.assertEqual([m['key'] for m in p['months']], ['2026-10-01', '2026-11-01', '2026-12-01'])
        self.assertEqual(p['due_date'], '2027-01-03')
        self.assertEqual(reporting_period('2027-01', today=date(2027,2,1))['months'][0]['key'], '2026-11-01')

    def test_future_and_invalid_month_rejected(self):
        from .calculations import reporting_period
        for value in ['garbage', '2026-13', '2026-10-31', '2027-02']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                reporting_period(value, today=date(2027, 1, 15))

    def test_group_mapping_uses_dashboard_aliases_and_known_ancillaries(self):
        from .calculations import equipment_group
        for category, group in [("ADT's", 'ADTs'), ('Loader', 'FELs'), ('Drills', 'Drills'),
                                ('TLB', 'Ancillary'), ('Diesel Bowsers', 'Ancillary')]:
            self.assertEqual(equipment_group(category), group)
        self.assertIsNone(equipment_group('Unknown'))

    def test_disjoint_events_clip_open_cross_month_and_keep_uncategorised(self):
        from .calculations import event_segments
        start, end = datetime(2026, 10, 1, 6), datetime(2026, 11, 1, 6)
        rows = [dict(name='a', asset_name='A', breakdown_start_datetime='2026-09-30 05:00:00',
                     resolved_datetime='2026-10-01 08:00:00', problem_category='Engine'),
                dict(name='duplicate', asset_name='A', breakdown_start_datetime='2026-09-30 05:00:00',
                     resolved_datetime='2026-10-01 08:00:00', problem_category='Engine'),
                dict(name='b', asset_name='A', breakdown_start_datetime='2026-10-01 07:00:00',
                     resolved_datetime='2026-10-01 09:00:00', problem_category='Hydraulics'),
                dict(name='open', asset_name='B', breakdown_start_datetime='2026-10-31 23:00:00',
                     resolved_datetime=None, problem_category='', breakdown_reason='engine free text')]
        parts = event_segments(rows, start, end)
        self.assertEqual(sum((b-a).total_seconds()/3600 for _, a, b, _ in parts), 10)
        self.assertIn(('A', datetime(2026,10,1,7), datetime(2026,10,1,8), 'Engine / Hydraulics'), parts)
        self.assertEqual(parts[-1][-1], 'Uncategorised')

    def test_pareto_sorts_preserves_totals_and_finishes_at_100(self):
        from .calculations import pareto
        rows = pareto({'Engine': 60, 'Hydraulics': 80, 'Uncategorised': 60, 'Zero': 0})
        self.assertEqual(rows[0]['cause'], 'Hydraulics')
        self.assertEqual(sum(r['hours'] for r in rows), 200)
        self.assertEqual(rows[-1]['cumulative_percent'], 100)
        self.assertEqual(pareto({}), [])

class TestReportData(unittest.TestCase):
    def test_group_totals_use_engine_hours_and_keep_missing_distinct_from_zero(self):
        from .monthly_tmm_assurance import availability_by_group
        rows = [dict(indent=3, asset_category='TLB', required_hours=10,
                     availability_available_hours=10, utilisation_available_hours=10),
                dict(indent=3, asset_category='Water Bowser', required_hours=30,
                     availability_available_hours=0, utilisation_available_hours=0),
                dict(indent=3, asset_category='ADT', required_hours=12,
                     availability_available_hours=0, utilisation_available_hours=0),
                dict(indent=3, asset_category='Loader', required_hours=20,
                     availability_available_hours=20, invalid_pre_use=1),
                dict(indent=0, asset_category='TLB', required_hours=999,
                     availability_available_hours=999)]
        values = availability_by_group(rows)
        self.assertEqual(values['Ancillary'], 21.25)
        self.assertEqual(values['ADTs'], 0)
        self.assertIsNone(values['FELs'])
        self.assertIsNone(values['Drills'])

    def test_count_chart_and_complete_pdf_content(self):
        from .presentation import count_chart_image, report_html
        from .defects import category_counts
        from .calculations import reporting_period, GROUPS
        counts=category_counts([dict(name=str(i),problem_category='Hydraulics',status_label='Open (current)') for i in range(4)]+[dict(name='last',problem_category='Engine / Starting')])
        chart=count_chart_image(counts)
        self.assertIn('data:image/svg+xml;base64,',chart)
        import base64,re
        svg=base64.b64decode(re.search('base64,([^"]+)',chart)[1]).decode()
        for label in ['80.0%','100.0%','Number of breakdown records','Cumulative percentage','<polyline','<rect']:
            self.assertIn(label,svg)
        data=dict(site='A < B',**reporting_period('2026-09',today=date(2026,10,2)),
                  population='Distinct breakdown events overlapping the reporting calendar month, including carried-in and repaired/closed events',counting_unit='One breakdown record',status_basis='Current status',
                  groups=[dict(group=g,availability=[None,0,85],counts=counts if g=='FELs' else category_counts([]),
                    actions=[dict(cause='Engine / Starting',action='Repair saved',owner_name='Engineer',due_date='2026-10-03',status='Open')] if g=='Dozers' else []) for g in GROUPS])
        html=report_html(data)
        for text in ['A &lt; B','Repair saved','FELs','Dozers','Three-month availability by equipment group','first 80%']:
            self.assertIn(text,html)
