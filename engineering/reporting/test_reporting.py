"""Saved report tests; source calculations and workflows must never be called."""
import json
import unittest
from unittest.mock import patch
import frappe

class TestReporting(unittest.TestCase):
    def setUp(self):
        from engineering.reporting import service, rendering
        self.service, self.rendering = service, rendering
        self.doc = frappe._dict(name='saved', site='Klipfontein', report_date='2026-08-03',
            shift='Day', hour_slot='06:00-07:00', period_bcm=123, generated_at='2026-08-04',
            period_start='2026-08-03 06:00:00', period_end='2026-08-03 07:00:00',
            report_data_json=json.dumps({'metrics':{'period_bcm':123,'required_hourly_rate':None},
                'monthly_values_basis':'planning_at_generation','missing_data':['drilling_reports']}),
            excavator_production_json='[{"excavator":"EX-1","bcms":123}]',
            dozer_production_json='[]', drill_production_json='[]')
        self.doc.check_permission = lambda permission: None

    def test_registry_has_five_types_and_consistent_handlers(self):
        from engineering.reporting.registry import REPORT_TYPES
        self.assertEqual(len(REPORT_TYPES),5)
        for spec in REPORT_TYPES.values():
            self.assertTrue(callable(spec['view_handler']))
            self.assertTrue(callable(spec['pdf_handler']))
            self.assertIn('report_date',spec['filters'])
        self.assertNotIn('shift',REPORT_TYPES['hourly_downtime']['filters'])

    def load(self, key='hourly_production', eligible=True):
        with patch.object(self.service,'available',return_value=True), \
             patch.object(self.service.frappe,'get_doc',return_value=self.doc), \
             patch.object(self.service,'production_eligible',return_value=eligible):
            return self.service.get_report(key,'saved')

    def test_production_uses_saved_values_and_null_availability(self):
        result=self.load()
        self.assertEqual(result['metrics']['period_bcm'],123)
        self.assertIsNone(result['metrics']['required_hourly_rate'])
        self.assertEqual(result['excavators'][0]['bcms'],123)
        self.assertIn('drilling_reports',result['missing_data'])

    def test_ineligible_saved_production_cannot_be_viewed(self):
        with self.assertRaises(frappe.PermissionError): self.load(eligible=False)

    def test_permissions_checked_on_snapshot(self):
        def deny(permission): raise frappe.PermissionError('denied')
        self.doc.check_permission=deny
        with self.assertRaises(frappe.PermissionError): self.load()

    def test_unknown_type_rejected_before_document_lookup(self):
        with patch.object(self.service.frappe,'get_doc',side_effect=AssertionError('must not load')):
            with self.assertRaises(frappe.ValidationError): self.service.get_report('User','saved')

    def test_malformed_json_fails_without_live_fallback(self):
        self.doc.report_data_json='{broken'
        with self.assertRaises(frappe.ValidationError): self.load()

    def test_downtime_uses_saved_rows(self):
        self.doc.report_data_json='[{"plant_no":"DZ-1","status_key":"open","reason":"Saved reason","open_hours":2}]'
        result=self.load('hourly_downtime',eligible=False)
        self.assertEqual(result['rows'][0]['reason'],'Saved reason')

    def test_daily_downtime_preserves_shift_and_hours(self):
        self.doc.shift='Night Shift'
        self.doc.report_data_json='[{"plant_no":"DZ-1","breakdown_hours":4,"open_closed":"Closed"}]'
        result=self.load('daily_downtime')
        self.assertEqual(result['shift'],'Night Shift')
        self.assertEqual(result['total_hours'],4)

    def test_list_hides_ineligible_snapshots(self):
        with patch.object(self.service,'available',return_value=True), \
             patch.object(self.service,'production_windows',return_value={}), \
             patch.object(self.service.frappe,'get_meta',return_value=frappe._dict(has_field=lambda f:True)), \
             patch.object(self.service.frappe,'get_list',return_value=[self.doc]), \
             patch.object(self.service,'production_eligible',return_value=False):
            result=self.service.search('hourly_production',report_date='2026-08-03')
        self.assertEqual(result['rows'],[])

    def test_invalid_and_inapplicable_filters_are_rejected(self):
        with patch.object(self.service,'available',return_value=True):
            with self.assertRaises(frappe.ValidationError):
                self.service.search('daily_production',hour_slot='06:00-07:00')
            with self.assertRaises(frappe.ValidationError):
                self.service.search('shift_production',shift='invalid')

    def test_pdf_uses_same_html_as_preview_and_requires_print(self):
        permissions=[]
        self.doc.check_permission=permissions.append
        with patch.object(self.service,'available',return_value=True), \
             patch.object(self.service.frappe,'get_doc',return_value=self.doc), \
             patch.object(self.service,'production_eligible',return_value=True), \
             patch.object(self.rendering,'render',return_value='<html>Saved report</html>'), \
             patch('frappe.utils.pdf.get_pdf',return_value=b'%PDF-test') as pdf:
            content=self.rendering.pdf_bytes(self.service.get_report('hourly_production','saved',for_pdf=True))
        self.assertEqual(content,b'%PDF-test')
        pdf.assert_called_once_with('<html>Saved report</html>',{'orientation':'Landscape'})
        self.assertEqual(permissions,['read','print'])

    def test_pagination_advances_over_hidden_rows_without_losing_visible_records(self):
        from datetime import date
        rows=[frappe._dict(name=str(i),site='Koppie' if i%2 else 'Inactive',report_date='2026-08-03') for i in range(220)]
        def get_list(*a,**kw): return rows[kw['start']:kw['start']+100]
        with patch.object(self.service,'available',return_value=True), \
             patch.object(self.service,'production_windows',return_value={'Koppie':[(date(2026,8,1),date(2026,8,31))]}), \
             patch.object(self.service.frappe,'get_meta',return_value=frappe._dict(has_field=lambda f:True)), \
             patch.object(self.service.frappe,'get_list',side_effect=get_list):
            first=self.service.search('daily_production')
            second=self.service.search('daily_production',start=first['next_start'])
            third=self.service.search('daily_production',start=second['next_start'])
        self.assertEqual([len(x['rows']) for x in (first,second,third)],[50,50,10])
        self.assertIsNone(third['next_start'])
        self.assertEqual(len({row['name'] for page in (first,second,third) for row in page['rows']}),110)



class TestFrappeReporting(unittest.TestCase):
    """Real permission/list/render checks in the guarded disposable SQLite site."""
    @classmethod
    def setUpClass(cls):
        from is_production.production.production_summaries.test_production_summaries import TestFrappeIntegration
        cls.fixture_case=TestFrappeIntegration()
        TestFrappeIntegration.setUpClass()
        frappe.db.set_global('installed_apps',json.dumps(['frappe','is_production','engineering']))
        frappe.local.request_cache.clear()
        frappe.local.module_app['engineering']='engineering'
        from pathlib import Path
        apps_path=Path(frappe.local.sites_path)/'apps.txt'
        apps=apps_path.read_text().splitlines()
        if 'engineering' not in apps:
            apps_path.write_text('\n'.join([*apps,'engineering'])+'\n')
        frappe.cache.delete_value('all_apps')
        from frappe.utils.jinja import _get_jloader
        _get_jloader.clear_cache()
        if not frappe.db.exists('Module Def','Engineering'):
            frappe.get_doc(dict(doctype='Module Def',module_name='Engineering',app_name='engineering')).insert(ignore_permissions=True)
        frappe.flags.in_import=True
        for slug in ('hourly_downtime_summary','daily_downtime_summary'):
            frappe.reload_doc('engineering','doctype',slug,force=True)
        frappe.flags.in_import=False
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        from is_production.production.production_summaries.test_production_summaries import TestFrappeIntegration
        TestFrappeIntegration.tearDownClass()

    def setUp(self):
        self.fixture_case.setUp()
        for doctype in ('Hourly Downtime Summary','Daily Downtime Summary'):
            frappe.db.delete(doctype)
        self.fixture_case.fixture('Hourly Downtime Summary','engineering-saved',site='Koppie',
            report_date='2026-10-01',hour_slot='23:00-24:00',
            report_data_json=json.dumps([dict(plant_no='DZ-1',status_key='open',open_hours=2,reason='<script>unsafe</script>')]))
        self.fixture_case.fixture('Daily Downtime Summary','daily-saved',site='Koppie',report_date='2026-10-01',
            shift='Full Daily',report_data_json=json.dumps([dict(plant_no='DZ-1',breakdown_hours=4,open_closed='Closed')]))
        from datetime import datetime
        from is_production.production.production_summaries.snapshot import create_snapshot
        from is_production.production.production_summaries.periods import make_period
        self.names={kind:create_snapshot('Koppie',make_period(kind,datetime(2026,10,1,6))) for kind in ('hourly','shift','daily')}

    def test_all_five_types_list_and_render_actual_saved_documents(self):
        from . import service,rendering
        from .registry import REPORT_TYPES
        self.assertEqual(len(service.metadata()),5)
        for key in REPORT_TYPES:
            result=service.search(key,site='Koppie',report_date='2026-10-01')
            self.assertEqual(len(result['rows']),1,key)
            model=service.get_report(key,result['rows'][0]['name'])
            html=rendering.render(model)
            self.assertIn('Koppie',html)
            self.assertIn('Saved report reference',html)
            self.assertNotIn('<script>unsafe</script>',html)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;',rendering.render(service.get_report('hourly_downtime','engineering-saved')))

    def test_cancelled_plan_hides_stored_snapshots_and_blocks_direct_pdf(self):
        from . import service
        from is_production.production.production_summaries.snapshot import DOCTYPES
        frappe.db.set_value('Monthly Production Planning','BASE-Koppie','docstatus',2)
        for kind,name in self.names.items():
            key=kind+'_production'
            self.assertEqual(service.search(key)['rows'],[])
            with self.assertRaises(frappe.PermissionError): service.get_report(key,name,for_pdf=True)
            self.assertTrue(frappe.db.exists(DOCTYPES[kind],name))
        self.assertEqual(len(service.search('hourly_downtime')['rows']),1)

    def test_filters_and_non_privileged_permissions_are_enforced(self):
        from . import service
        self.assertEqual(len(service.search('hourly_downtime',hour_slot='23:00-00:00')['rows']),1)
        self.assertEqual(service.search('hourly_downtime',site='Gwab')['rows'],[])
        self.assertEqual(service.search('daily_downtime',shift='Night Shift')['rows'],[])
        original=frappe.session.user
        try:
            frappe.set_user('Guest')
            self.assertEqual(service.metadata(),[])
            with self.assertRaises(frappe.PermissionError): service.search('daily_production')
            with self.assertRaises(frappe.PermissionError): service.get_report('hourly_downtime','engineering-saved',for_pdf=True)
        finally:
            frappe.set_user(original)

    def test_site_user_permission_restricts_list_preview_and_download(self):
        from datetime import datetime
        from . import service
        from is_production.production.production_summaries.snapshot import create_snapshot
        from is_production.production.production_summaries.periods import make_period
        fixture=self.fixture_case.fixture
        fixture('Monthly Production Planning','GWAB-VALID',location='Gwab',prod_month_start_date='2026-10-01',prod_month_end_date='2026-10-01')
        other=create_snapshot('Gwab',make_period('daily',datetime(2026,10,1,6)))
        reader='report-reader@example.invalid'
        if not frappe.db.exists('User',reader):
            fixture('User',reader,email=reader,enabled=1,user_type='System User',first_name='Report Reader')
            fixture('Has Role','report-reader-role',parent=reader,parenttype='User',parentfield='roles',role='Production User')
        frappe.db.delete('User Permission',{'user':reader})
        fixture('User Permission','report-reader-site',user=reader,allow='Location',for_value='Koppie',apply_to_all_doctypes=1)
        frappe.clear_cache(user=reader)
        original=frappe.session.user
        try:
            frappe.set_user(reader)
            rows=service.search('daily_production')['rows']
            self.assertEqual([row['site'] for row in rows],['Koppie'])
            self.assertEqual(service.get_report('daily_production',self.names['daily'])['site'],'Koppie')
            with self.assertRaises(frappe.PermissionError): service.get_report('daily_production',other)
            with self.assertRaises(frappe.PermissionError): service.get_report('daily_production',other,for_pdf=True)
        finally:
            frappe.set_user(original)
