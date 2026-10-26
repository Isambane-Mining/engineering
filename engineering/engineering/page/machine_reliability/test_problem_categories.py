"""Manual category precedence and historical keyword compatibility."""
import unittest
from unittest.mock import patch
import frappe
from engineering.engineering.page.machine_reliability import machine_reliability as c
from engineering.engineering.page.machine_reliability import machine_reliability as api
from engineering.engineering.page.machine_reliability.test_calculations import row


class TestProblemCategoryMatching(unittest.TestCase):
    def report(self, records, category='Brakes', extra=None):
        return c.build_report(records, [], ['brake', 'brakes'] + (extra or []),
                              '2026-08-01', '2026-08-31', category=category, additional_keywords=extra)

    def test_manual_category_wins_without_keywords_and_counts_once(self):
        records = [dict(row('manual', reason='Machine will not stop'), problem_category='Brakes'),
                   dict(row('both'), problem_category='Brakes'), row('historical')]
        result = self.report(records)
        self.assertEqual(result['summary']['direct_failures'], 3)
        self.assertEqual(len({x['name'] for x in result['timeline']}), 3)
        self.assertEqual(result['timeline'][0]['match_source'], 'Manual category')

    def test_different_manual_category_is_not_overridden_by_reason_keywords(self):
        result = self.report([dict(row('engine', reason='brakes reported'), problem_category='Engine / Starting')])
        self.assertEqual(result['summary']['problem_records'], 0)

    def test_resolution_work_on_another_category_remains_additional(self):
        result = self.report([dict(row('engine', reason='engine stopped', resolution='brakes adjusted'),
                                   problem_category='Engine / Starting')])
        self.assertEqual(result['summary']['direct_failures'], 0)
        self.assertEqual(result['summary']['additional_work'], 1)

    def test_additional_words_extend_search_with_manual_categories(self):
        result = self.report([dict(row('extra', reason='starter failed'), problem_category='Electrical'),
                              dict(row('repair', reason='engine stopped', resolution='starter replaced'), problem_category='Other')], extra=['starter'])
        self.assertEqual(result['summary']['direct_failures'], 1)
        self.assertEqual(result['summary']['additional_work'], 1)

    def test_manual_maintenance_is_not_a_failure(self):
        result = self.report([dict(row('planned', reason='scheduled work', kind='Planned Maintenance'), problem_category='Brakes')])
        self.assertEqual(result['summary']['problem_records'], 1)
        self.assertEqual(result['summary']['direct_failures'], 0)

    def test_mixed_history_preserves_meter_and_duration_rules(self):
        records = [dict(row('a', meter=100, reason='pedal issue'), problem_category='Brakes'),
                   row('b', '2026-08-02 00:00:00', meter=110),
                   dict(row('c', '2026-08-03 00:00:00', meter=90, reason='pedal issue'), problem_category='Brakes')]
        result = self.report(records)
        self.assertEqual(result['summary']['average_failure_gap'], 10)
        self.assertEqual(result['summary']['valid_intervals'], 1)
        self.assertEqual(result['quality']['invalid_gaps'], 1)

    def test_all_problems_with_extra_words_still_searches_text(self):
        result = c.build_report([dict(row('manual', reason='pedal issue'), problem_category='Brakes'),
                                 row('text', reason='starter failed')], [], ['starter'], '2026-08-01', '2026-08-31',
                                additional_keywords=['starter'])
        self.assertEqual([x['name'] for x in result['timeline']], ['text'])


class TestProblemCategoryAPI(unittest.TestCase):
    def test_settings_category_names_stay_compatible_with_the_dropdown(self):
        settings = frappe.get_doc('Machine Reliability Settings')
        settings.categories[0].category = 'brakes'
        with self.assertRaises(frappe.ValidationError):
            settings.validate()

    def test_category_is_loaded_and_applied_through_existing_endpoint(self):
        source = frappe._dict(row('manual', fleet=None, reason='pedal issue'), problem_category='Brakes')
        def read(dt, **kwargs):
            if dt == api.PBM:
                self.assertIn('problem_category', kwargs['fields'])
                return [source]
            return []
        with patch.object(api, 'check_access', return_value=[]), patch.object(frappe, 'get_list', side_effect=read):
            result = api.get_dashboard('2026-08-01', '2026-08-31', category='Brakes')
        self.assertEqual(result['summary']['direct_failures'], 1)
        self.assertEqual(result['timeline'][0]['problem_category'], 'Brakes')
