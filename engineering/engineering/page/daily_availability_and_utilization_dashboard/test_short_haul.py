import unittest
from unittest.mock import patch

from engineering.engineering.page.daily_availability_and_utilization_dashboard.short_haul import (
    aggregate_short_haul_hours, short_haul_percentage, fetch_short_haul_hours, CATEGORY,
)
from engineering.engineering.page.daily_availability_and_utilization_dashboard import (
    daily_availability_and_utilization_dashboard as dashboard,
)


class TestShortHaul(unittest.TestCase):
    def row(self, start='08:00:00', end='12:00:00', **kwargs):
        return dict(machine='IS534', shift_date='2026-09-01', shift='Day',
                    start_time=start, end_time=end, **kwargs)

    def test_example_and_zero_denominator(self):
        self.assertAlmostEqual(short_haul_percentage(4, 9), 44.44444444)
        self.assertIsNone(short_haul_percentage(4, 0))

    def test_union_duplicates_overlap_and_scope(self):
        scope = {('IS534', '2026-09-01', 'Day')}
        rows = [self.row(), self.row(), self.row('10:00:00', '13:00:00'),
                dict(self.row(), machine='EXCLUDED'),
                dict(self.row(), shift_date='2026-09-02')]
        self.assertEqual(aggregate_short_haul_hours(rows, scope), {'IS534': 5})

    def test_all_equipment_does_not_duplicate_machine_interval(self):
        scope = {('IS534', '2026-09-01', 'Day')}
        rows = [self.row(), dict(self.row(), machine='ALL Equipment')]
        self.assertEqual(aggregate_short_haul_hours(rows, scope), {'IS534': 4})

    def test_midnight_and_adjacent_shift_overlap(self):
        scope = {('IS534', '2026-09-01', 'Night'), ('IS534', '2026-09-02', 'Day')}
        rows = [dict(self.row('22:00:00', '07:00:00'), shift='Night'),
                dict(self.row('01:00:00', '03:00:00'), shift='Night'),
                dict(self.row('06:00:00', '08:00:00'), shift_date='2026-09-02')]
        self.assertEqual(aggregate_short_haul_hours(rows, scope), {'IS534': 10})

    def test_invalid_or_missing_times_are_not_added(self):
        scope = {('IS534', '2026-09-01', 'Day')}
        rows = [self.row(start=''), self.row(start='invalid'), self.row(end='08:00:00')]
        self.assertEqual(aggregate_short_haul_hours(rows, scope), {})

    def test_query_limits_category_site_date_and_source_machines(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        import frappe
        db = SimpleNamespace(sql=Mock(return_value=[self.row()]))
        with patch.object(frappe, 'db', db, create=True):
            actual = fetch_short_haul_hours(
                [dict(indent=3, asset_name='IS534', shift_date='2026-09-01', shift='Day')],
                'Koppie', '2026-09-01', '2026-09-02',
            )
        self.assertEqual(actual, {'IS534': 4})
        query, values = db.sql.call_args.args
        self.assertIn('r.docstatus < 2', query)
        self.assertIn('g.lost_hour_category = %(category)s', query)
        self.assertIn('r.location = %(location)s', query)
        self.assertIn('r.shift_date BETWEEN %(start_date)s AND %(end_date)s', query)
        self.assertEqual(values['machines'], ('IS534',))
        self.assertEqual(values['category'], CATEGORY)
        self.assertEqual(values['location'], 'Koppie')

    def test_zero_denominator_retains_hours_without_inventing_percentage(self):
        html = self.render(dict(util=0, short_haul_hours=4, short_haul_percentage=None))
        self.assertNotIn('isd-short-haul-segment', html)
        self.assertIn('Short Haul Lost Hours: 4.00 h', html)
        self.assertIn('Short Haul: N/A', html)

    def test_uncapped_short_haul_component(self):
        html = self.render(dict(util=10, short_haul_hours=12, short_haul_percentage=150))
        self.assertIn('Short Haul: 150.0%', html)
        self.assertIn('Combined visual potential: 160.0%', html)

    def test_summary_uses_engine_denominator_without_changing_official_values(self):
        from types import SimpleNamespace
        row = dict(indent=3, asset_name='IS534', asset_category='ADT')
        for basis, expected in [('100% A & U', 33.333), ('85% A & U', 28.333)]:
            with self.subTest(basis=basis), patch.object(
                dashboard.frappe, 'local', SimpleNamespace(daily_dashboard_au_target_filter=basis)
            ), patch.object(dashboard.au_engine, 'build_summary_row', return_value={
                'availability_percentage': 90, 'utilisation_percentage': 33.333333,
                'utilisation_available_hours': 9,
            }):
                item = dashboard.build_machine_series_from_source_rows([row], {'IS534': 4})['ADT'][0]
                self.assertEqual(item['util'], expected)
                self.assertEqual(item['short_haul_hours'], 4)
                self.assertAlmostEqual(item['short_haul_percentage'], 400 / 9)

    def render(self, item):
        with patch.object(dashboard, 'build_scope_averages_from_source_rows', return_value=({}, {})):
            return dashboard.build_chart_html({'ADT': [dict(machine='IS534', avail=90, **item)]})

    def test_stack_and_real_tooltip_values_are_not_capped(self):
        html = self.render(dict(util=80, short_haul_hours=4, short_haul_percentage=44.444444))
        self.assertIn('isd-short-haul-segment', html)
        self.assertIn('height:220px', html)
        self.assertIn('Actual Utilisation: 80.0%', html)
        self.assertIn('Short Haul Lost Hours: 4.00 h', html)
        self.assertIn('Combined visual potential: 124.4%', html)
        self.assertIn('Short Haul Reduced Fleet Lost Hours', html)

    def test_no_short_haul_keeps_single_bar_and_small_value_hover(self):
        html = self.render(dict(util=0.1))
        self.assertNotIn('isd-short-haul-segment', html)
        self.assertIn('IS534 Utilisation: 0.1%', html)
        self.assertIn('height:2px', html)
        self.assertIn('data-utilisation-small', html)


if __name__ == '__main__':
    unittest.main()
