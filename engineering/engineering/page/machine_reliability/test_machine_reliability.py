"""API tests run in an initialized LAB Frappe test context."""
import unittest
from unittest.mock import patch

import frappe
from engineering.engineering.page.machine_reliability import machine_reliability as api


class TestMachineReliabilityAPI(unittest.TestCase):
    def test_guest_is_denied(self):
        with patch.object(frappe.local, 'session', frappe._dict(user='Guest')):
            with self.assertRaises(frappe.PermissionError):
                api.get_options()

    def test_invalid_dates_and_category_are_rejected(self):
        with patch.object(api, 'check_access', return_value=[]):
            with self.assertRaises(frappe.ValidationError):
                api.get_dashboard('2026-08-31', '2026-08-01')
            with self.assertRaises(frappe.ValidationError):
                api.get_dashboard('2010-01-01', '2026-08-01')
            with self.assertRaises(frappe.ValidationError):
                api.get_dashboard('2026-08-01', '2026-08-31', category='not a category')

    def test_requested_site_cannot_escape_assigned_locations(self):
        with patch.object(api, 'check_access', return_value=['Koppie']):
            with self.assertRaises(frappe.PermissionError):
                api.get_dashboard('2026-08-01', '2026-08-31', site='Other Site')

    def test_live_report_totals_are_not_page_totals(self):
        # Real LAB queries; no source records are inserted, amended or deleted.
        with patch.object(api, 'check_access', return_value=[]):
            first = api.get_dashboard('2026-07-01', '2026-08-31', category='Brakes', page_size=1)
            second = api.get_dashboard('2026-07-01', '2026-08-31', category='Brakes', page_size=50)
        self.assertEqual(first['summary'], second['summary'])
        self.assertLessEqual(len(first['tables']['history']['rows']), 1)
        self.assertGreater(first['summary']['problem_records'], 0)
        self.assertEqual(first['tables']['history']['total'], first['summary']['direct_failures'])

    def test_historical_site_and_category_fleet_query(self):
        with patch.object(api, 'check_access', return_value=[]):
            response = api.get_dashboard('2026-07-01', '2026-08-31', site='Koppie', category='Brakes')
            self.assertTrue(all(x['site'] == 'Koppie' for x in response['timeline']))
            fleets = api.get_fleets('Asset', '', 'name', 0, 50, dict(from_date='2026-07-01', to_date='2026-08-31', site='Koppie', asset_category='ADT'))
            for name, description in fleets:
                self.assertEqual(frappe.db.get_value('Asset', name, 'asset_category'), 'ADT')

    def test_settings_reject_duplicate_categories(self):
        doc = frappe.get_doc('Machine Reliability Settings')
        doc.set('categories', [dict(category='Brakes', keywords='brake'), dict(category='brakes', keywords='brakes')])
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_real_user_permissions_limit_all_site_results(self):
        # LAB's assigned users are disabled; use a transaction-only test user.
        original_user = frappe.session.user
        user = 'machine-reliability-test-' + frappe.generate_hash(length=8) + '@example.invalid'
        frappe.db.savepoint('machine_reliability_permissions')
        try:
            frappe.set_user('Administrator')
            frappe.get_doc(dict(doctype='User', email=user, first_name='Reliability test',
                                enabled=1, send_welcome_email=0, user_type='System User',
                                roles=[dict(role='Engineering User')])).insert(ignore_permissions=True)
            frappe.get_doc(dict(doctype='User Permission', user=user, allow='Location',
                                for_value='Uitgevallen', apply_to_all_doctypes=1)).insert(ignore_permissions=True)
            frappe.set_user(user)
            result = api.get_dashboard('2026-07-01', '2026-08-31', category='Brakes')
            self.assertGreater(len(result['timeline']), 0)
            permitted = frappe.get_list(api.PBM, filters=[['location', '=', 'Uitgevallen'], ['breakdown_start_datetime', '>=', '2026-07-01'], ['breakdown_start_datetime', '<', '2026-09-01'], ['downtime_type', '=', 'Breakdown']], fields=['name', 'asset_name', 'breakdown_reason'], limit_page_length=20000)
            moved = [x for x in permitted if frappe.db.get_value('Asset', x.asset_name, 'location') != 'Uitgevallen' and 'brake' in (x.breakdown_reason or '').lower()]
            self.assertGreater(len(moved), 0, 'Fixture must include a permitted historical record for a moved Asset')
            names = {x['name'] for x in result['timeline']}
            self.assertTrue(any(x.name in names for x in moved), 'Moving an Asset must not hide its permitted historical site records')
            self.assertTrue(all(x['site'] == 'Uitgevallen' for x in result['timeline']))
            with self.assertRaises(frappe.PermissionError):
                api.get_dashboard('2026-07-01', '2026-08-31', site='Klipfontein', category='Brakes')
        finally:
            frappe.set_user(original_user)
            frappe.db.rollback(save_point='machine_reliability_permissions')
            frappe.clear_cache(user=user)

    def test_unassigned_permitted_breakdown_is_not_silently_dropped(self):
        source = frappe._dict(name='unassigned', asset_name=None, location='Koppie', downtime_type='Breakdown',
                              breakdown_start_datetime='2026-08-01 00:00:00', resolved_datetime='2026-08-01 02:00:00',
                              breakdown_reason='brakes failed', resolution_summary='', hours_breakdown_starts=0)
        def read(doctype, **kwargs):
            return [source] if doctype == api.PBM else []
        with patch.object(api, 'check_access', return_value=[]), patch.object(frappe, 'get_list', side_effect=read):
            result = api.get_dashboard('2026-08-01', '2026-08-31', category='Brakes')
        self.assertEqual(result['summary']['problem_records'], 1)
        self.assertEqual(result['tables']['history']['rows'][0]['gap_status'], 'Missing fleet number')

    def test_source_limit_refuses_partial_summary(self):
        with patch.object(frappe, 'get_list', return_value=[frappe._dict(name='row')] * 20001):
            with self.assertRaises(frappe.ValidationError):
                api.limited_list(api.PBM, [], ['name'])

    def test_additional_words_extend_category_and_resolution_only_is_additional(self):
        source = frappe._dict(name='additional', asset_name=None, location='Koppie', downtime_type='Breakdown',
                              breakdown_start_datetime='2026-08-01 00:00:00', resolved_datetime='2026-08-01 02:00:00',
                              breakdown_reason='engine stopped', resolution_summary='starter replaced', hours_breakdown_starts=100)
        with patch.object(api, 'check_access', return_value=[]), patch.object(frappe, 'get_list', side_effect=lambda dt, **kw: [source] if dt == api.PBM else []):
            result = api.get_dashboard('2026-08-01', '2026-08-31', category='Brakes', additional_keywords='starter')
        self.assertIn('brakes', result['keywords'])
        self.assertIn('starter', result['keywords'])
        self.assertEqual(result['summary']['additional_work'], 1)
        self.assertEqual(result['summary']['direct_failures'], 0)

    def test_fleet_lookup_skips_unassigned_records(self):
        sources = ([frappe._dict(asset_name=None), frappe._dict(asset_name='A')], [], {'A': frappe._dict(asset_name='A')})
        with patch.object(api, 'check_access', return_value=[]), patch.object(api, 'load_sources', return_value=sources):
            fleets = api.get_fleets('Asset', '', 'name', 0, 50, dict(from_date='2026-08-01', to_date='2026-08-31'))
        self.assertEqual(fleets, [('A', 'A')])

    def test_frequency_matches_is545_erp_and_keeps_invalid_records(self):
        result = api.get_frequency('2025-10-01', '2026-08-31', fleet='IS545', category='Brakes', chart_fleet='IS545')
        self.assertEqual([x['hour_difference'] for x in result['rows']], [None, 9, 28, 22, -22581, 22620, 70])
        self.assertEqual([x['valid_difference'] for x in result['rows']], [False, True, True, True, False, False, True])
        self.assertTrue(all(x['fleet'] == 'IS545' for x in result['rows']))
        self.assertEqual(result['average_gap'], 32.25)
        self.assertEqual(result['valid_intervals'], 4)

    def test_chart_fleet_cannot_escape_global_fleet_filter(self):
        result = api.get_frequency('2026-07-01', '2026-08-31', fleet='IS545', category='Brakes', chart_fleet='IS558')
        self.assertEqual(result['rows'], [])

    def test_frequency_uses_same_keywords_and_site_scope(self):
        result = api.get_frequency('2026-07-01', '2026-08-31', site='Koppie', asset_category='ADT', category='Brakes', additional_keywords='starter')
        self.assertTrue(all(x['site'] == 'Koppie' and x['category'] == 'ADT' for x in result['rows']))
        self.assertIn('starter', result['keywords'])
        with patch.object(api, 'check_access', return_value=['Koppie']):
            with self.assertRaises(frappe.PermissionError):
                api.get_frequency('2026-07-01', '2026-08-31', site='Uitgevallen')
