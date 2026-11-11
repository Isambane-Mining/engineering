"""Real schema/save/permission/PDF checks, on a disposable SQLite site only.

Run with TMM_TEST_SITES=/tmp/production-summary-validation-tmm/sites and bench Python.
Never reads credentials or connects to the working bench's site.
"""
from unittest.mock import patch as patch_classification_configuration

from engineering.patches.failure_classification_seed import INITIAL_CLASSIFICATIONS as TEST_CLASSIFICATIONS, seed_configuration
TEST_CONFIGURATION = seed_configuration()
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import frappe

from . import monthly_tmm_assurance as api
from .monthly_tmm_assurance import GROUPS


@patch_classification_configuration('engineering.controllers.failure_classification.get_configuration', new=lambda: TEST_CONFIGURATION)
class TestTMMLabIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sites = Path(os.environ.get('TMM_TEST_SITES', '/nonexistent')).resolve()
        if not str(sites).startswith('/tmp/production-summary-validation-'):
            raise unittest.SkipTest('TMM_TEST_SITES must point at a disposable SQLite test site')
        config = json.loads((sites/'summary-test.local/site_config.json').read_text())
        if config['db_type'] != 'sqlite':
            raise RuntimeError('Only disposable SQLite is allowed')
        cls.previous_cwd = os.getcwd()
        os.chdir(sites)
        assets = sites/'assets'
        if not assets.exists():
            assets.symlink_to(Path(__file__).resolve().parents[6]/'sites/assets', target_is_directory=True)
        frappe.init('summary-test.local', sites_path=str(sites))
        frappe.connect()
        frappe.set_user('Administrator')
        frappe.db.set_global('installed_apps', json.dumps(['frappe', 'is_production', 'engineering']))
        frappe.local.request_cache.clear()
        frappe.local.module_app['engineering'] = 'engineering'
        frappe.flags.update(in_test=True, mute_emails=True, in_import=True)
        if not frappe.db.exists('Module Def', 'Engineering'):
            frappe.get_doc(dict(doctype='Module Def', module_name='Engineering', app_name='engineering')).insert(ignore_permissions=True)
        for role in ['Engineering Manager', 'Engineering User', 'Engineering Foreman', 'Engineering Area Manager',
                     'Engineering Supervisor', 'Production User', 'Production Manager', 'Production Foreman', 'Production Supervisor']:
            if not frappe.db.exists('Role', role):
                frappe.get_doc(dict(doctype='Role', role_name=role)).insert(ignore_permissions=True)
        # Minimal relational source fixtures. Source controllers are not imported/saved.
        cls.schema('Location', [dict(fieldname='location_name',fieldtype='Data')])
        cls.schema('Asset', [dict(fieldname='asset_name',fieldtype='Data'),dict(fieldname='asset_owner',fieldtype='Data'),dict(fieldname='asset_category',fieldtype='Data'),dict(fieldname='location',fieldtype='Link',options='Location')])
        cls.schema('Availability and Utilisation', [dict(fieldname='location',fieldtype='Link',options='Location'),
            dict(fieldname='asset_name',fieldtype='Data'),dict(fieldname='asset_category',fieldtype='Data'),dict(fieldname='shift_date',fieldtype='Date'),
            dict(fieldname='shift',fieldtype='Data'),dict(fieldname='shift_system',fieldtype='Data'),dict(fieldname='shift_required_hours',fieldtype='Float'),dict(fieldname='shift_available_hours',fieldtype='Float'),dict(fieldname='invalid_pre_use_hours',fieldtype='Check')])
        cls.schema('Pre-Use Hours', [dict(fieldname='location',fieldtype='Link',options='Location'),dict(fieldname='shift_date',fieldtype='Date')])
        cls.schema('Monthly Production Planning', [dict(fieldname='location',fieldtype='Link',options='Location'),
            dict(fieldname='site_status',fieldtype='Data'),dict(fieldname='prod_month_start_date',fieldtype='Date'),dict(fieldname='prod_month_end_date',fieldtype='Date')])
        cls.schema('Startup and Fatigue spesification', [dict(fieldname='site',fieldtype='Link',options='Location')])
        cls.schema(api.PBM, [dict(fieldname='location',fieldtype='Link',options='Location'),
            *[dict(fieldname=f,fieldtype='Data') for f in ['asset_name','asset_category','failure_classification','downtime_type','open_closed','breakdown_reason']],
            dict(fieldname='exclude_from_au',fieldtype='Check'),dict(fieldname='breakdown_start_datetime',fieldtype='Datetime'),
            dict(fieldname='resolved_datetime',fieldtype='Datetime')])
        from engineering.controllers.failure_classification import MASTER_DOCTYPE
        cls.schema(MASTER_DOCTYPE, [dict(fieldname='classification_name',fieldtype='Data')])
        for label in TEST_CLASSIFICATIONS:
            cls.fixture(MASTER_DOCTYPE,label,classification_name=label)
        meta=frappe.get_doc('DocType',api.PBM)
        field=next(f for f in meta.fields if f.fieldname=='failure_classification')
        field.fieldtype='Link'
        field.options=MASTER_DOCTYPE
        field.mandatory_depends_on=''
        field.reqd=0
        meta.save(ignore_permissions=True)
        for slug in ['monthly_tmm_assurance_action', 'monthly_tmm_assurance_actions']:
            frappe.reload_doc('engineering', 'doctype', slug, force=True)
        frappe.reload_doc('engineering', 'page', 'monthly_tmm_assurance', force=True)
        frappe.flags.in_import = False
        for site in ['Koppie','Gwab']:
            if not frappe.db.exists('Location',site):
                cls.fixture('Location',site,location_name=site)
        cls.fixture('Asset','TMM-asset',asset_name='ADT-TEST',asset_category='ADT',location='Koppie')
        for email, role in [('tmm-engineer@example.invalid','Engineering User'),('tmm-reader@example.invalid','Production User')]:
            if not frappe.db.exists('User',email):
                cls.fixture('User', email, email=email, first_name='TMM Test', enabled=1, user_type='System User')
                cls.fixture('Has Role', email+'-role', parent=email, parenttype='User', parentfield='roles', role=role)
            frappe.db.delete('User Permission',{'user':email})
            frappe.get_doc(dict(doctype='User Permission',user=email,allow='Location',for_value='Koppie',apply_to_all_doctypes=1)).insert(ignore_permissions=True)
            frappe.clear_cache(user=email)
        if not frappe.db.exists('Language','en'):
            cls.fixture('Language','en',language_name='English',date_format='yyyy-mm-dd',enabled=1)
        frappe.db.commit()

    @classmethod
    def schema(cls, name, fields):
        if not frappe.db.exists('DocType',name):
            frappe.get_doc(dict(doctype='DocType',name=name,module='Engineering',custom=1,fields=fields,
                permissions=[dict(role=r,read=1,write=1,create=1,print=1) for r in ['System Manager','Engineering User','Production User']])).insert(ignore_permissions=True)

        else:
            doc=frappe.get_doc('DocType',name)
            missing=[field for field in fields if field['fieldname'] not in {f.fieldname for f in doc.fields}]
            if missing:
                for field in missing: doc.append('fields',field)
                doc.save(ignore_permissions=True)

    @classmethod
    def fixture(cls, doctype, name, **values):
        from frappe.model.document import Document
        if frappe.db.exists(doctype,name):
            frappe.db.delete(doctype,{'name':name})
        doc = Document(dict(doctype=doctype,name=name,**values))
        doc.db_insert()
        return doc

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        frappe.destroy()
        os.chdir(cls.previous_cwd)

    def setUp(self):
        frappe.set_user('Administrator')
        frappe.db.savepoint('tmm_case')
        frappe.db.delete('Monthly TMM Assurance Action')
        frappe.db.delete(api.ACTIONS)
        frappe.db.delete(api.PBM)
        frappe.db.delete('Availability and Utilisation')
        frappe.db.delete('Monthly Production Planning')
        for month,end in [('2026-07','31'),('2026-08','31'),('2026-09','30')]:
            self.fixture('Monthly Production Planning',month,location='Koppie',
                prod_month_start_date=month+'-01',prod_month_end_date=month+'-'+end)

        from contextlib import ExitStack
        from datetime import timedelta
        from frappe.utils import getdate
        from engineering.engineering.report.availability_and_utilisation_engine import availability_and_utilisation_engine as engine
        from engineering.engineering.doctype.availability_and_utilisation import availability_and_utilisation as au
        self.adapters=ExitStack()
        def fixture_rows(a,b,sites):
            return frappe.get_all('Monthly Production Planning',filters={'location':['in',sites]},fields=['location','prod_month_start_date','prod_month_end_date'])
        def fixture_map(rows):
            result={}
            for row in rows:
                current=getdate(row.prod_month_start_date)
                while current<=getdate(row.prod_month_end_date):
                    result[(row.location,str(current))]=dict(shift_system='2x12Hour',shift_day_hours=12,shift_night_hours=12)
                    current+=timedelta(days=1)
            return result
        self.adapters.enter_context(patch.object(engine,'get_planning_rows',side_effect=fixture_rows))
        self.adapters.enter_context(patch.object(engine,'build_planning_map',side_effect=fixture_map))
        self.adapters.enter_context(patch.object(au,'_exclusion_windows',side_effect=lambda site,shift,a,b:[(a,a+timedelta(hours=1)),(b-timedelta(hours=1),b)]))
        self.adapters.enter_context(patch.object(api,'_subcategory_configuration',return_value={}))

    def tearDown(self):
        self.adapters.close()
        frappe.set_user('Administrator')
        frappe.db.rollback(save_point='tmm_case')

    def action(self, text='Inspect hoses'):
        return dict(cause='Hydraulic',action=text,owner_name='Engineer',due_date='2026-10-03',status='Open')

    def test_real_save_reload_group_and_month_isolation_and_conflict(self):
        frappe.set_user('tmm-engineer@example.invalid')
        first = api.save_actions('Koppie','2026-09-01','ADTs',[self.action()])
        saved = api._saved(api._scope('Koppie','2026-09-01','ADTs'))
        self.assertEqual(saved['actions'][0]['action'],'Inspect hoses')
        self.assertEqual(first,saved)
        self.assertEqual(api._saved(api._scope('Koppie','2026-09-01','Dozers'))['actions'],[])
        self.assertEqual(api._saved(api._scope('Koppie','2026-08-01','ADTs'))['actions'],[])
        second = api.save_actions('Koppie','2026-09-01','ADTs',[self.action('Repair')],first['version'])
        with self.assertRaises(frappe.TimestampMismatchError):
            api.save_actions('Koppie','2026-09-01','ADTs',[],first['version'])
        self.assertEqual(api._saved(api._scope('Koppie','2026-09-01','ADTs')),second)
        api.save_actions('Koppie','2026-09-01','ADTs',[],second['version'])
        self.assertEqual(api._saved(api._scope('Koppie','2026-09-01','ADTs'))['actions'],[])

    def test_site_permissions_on_read_write_pdf_and_direct_document(self):
        frappe.set_user('tmm-engineer@example.invalid')
        for call in [lambda: api.get_report('Gwab','2026-09-01'),
                     lambda: api.save_actions('Gwab','2026-09-01','ADTs',[self.action()]),
                     lambda: api.download_pdf('Gwab','2026-09-01'),
                     lambda: api.download_presentation('Gwab','2026-09-01')]:
            with self.assertRaises(frappe.PermissionError): call()
        doc = frappe.get_doc(dict(doctype=api.ACTIONS,site='Gwab',reporting_month='2026-09-01',
                                  equipment_group='ADTs',actions=[self.action()]))
        with self.assertRaises(frappe.PermissionError): doc.insert()

    def test_reader_can_read_but_cannot_save_and_guest_is_denied(self):
        api.save_actions('Koppie','2026-09-01','ADTs',[self.action()])
        frappe.set_user('tmm-reader@example.invalid')
        self.assertEqual(len(api._saved(api._scope('Koppie','2026-09-01','ADTs'))['actions']),1)
        with self.assertRaises(frappe.PermissionError):
            api.save_actions('Koppie','2026-09-01','ADTs',[self.action()])
        frappe.set_user('Guest')
        with self.assertRaises(frappe.PermissionError): api.get_report('Koppie','2026-09-01')

    def test_source_record_permission_cannot_be_bypassed_by_raw_engine_sql(self):
        self.fixture('Availability and Utilisation','allowed-au',location='Koppie',shift_date='2026-09-01')
        self.fixture('Availability and Utilisation','denied-au',location='Koppie',shift_date='2026-09-02')
        user='tmm-engineer@example.invalid'
        permission=frappe.get_doc(dict(doctype='User Permission',user=user,allow='Availability and Utilisation',
            for_value='allowed-au',apply_to_all_doctypes=1)).insert(ignore_permissions=True)
        frappe.clear_cache(user=user)
        try:
            frappe.set_user(user)
            with self.assertRaises(frappe.PermissionError):
                api.get_report('Koppie','2026-09-01')
        finally:
            frappe.set_user('Administrator')
            frappe.delete_doc('User Permission',permission.name,ignore_permissions=True)
            frappe.clear_cache(user=user)

    def test_stored_availability_does_not_apply_dashboard_asset_scope(self):
        self.fixture('Availability and Utilisation','stored-no-fleet',location='Koppie',shift_date='2026-09-10',
            asset_category='ADT',shift_required_hours=10,shift_available_hours=10)
        user='tmm-engineer@example.invalid'
        self.fixture('Asset','visible-fleet-asset',asset_name='VISIBLE',asset_category='ADT',location='Koppie')
        permission=frappe.get_doc(dict(doctype='User Permission',user=user,allow='Asset',
            for_value='visible-fleet-asset',apply_to_all_doctypes=1)).insert(ignore_permissions=True)
        frappe.clear_cache(user=user)
        try:
            frappe.set_user(user)
            report=api.get_report('Koppie','2026-09-01')
            self.assertEqual(report['groups'][0]['availability'],[None,None,85])
        finally:
            frappe.set_user('Administrator')
            frappe.delete_doc('User Permission',permission.name,ignore_permissions=True)
            frappe.clear_cache(user=user)


    def test_scope_is_immutable_and_invalid_actions_fail(self):
        saved=api.save_actions('Koppie','2026-09-01','ADTs',[self.action()])
        scope=api._scope('Koppie','2026-09-01','ADTs')
        doc=frappe.get_doc(api.ACTIONS,scope.name)
        doc.equipment_group='Dozers'
        with self.assertRaises(frappe.ValidationError): doc.save()
        with self.assertRaises(frappe.ValidationError):
            api.save_actions('Koppie','2026-09-01','Dozers',[dict(self.action(),status='Invented')])
        with self.assertRaises(frappe.ValidationError):
            api.save_actions('Koppie','2026-09-01','Dozers',[dict(self.action(),action='')])

    def test_monthly_record_population_and_group_counts_ignore_closure_and_au_flags(self):
        rows=[('prior','2026-08-31 23:59:59','Hydraulic',None,0),
              ('carried-closed','2026-08-15 12:00:00','Hydraulic','2026-09-02 12:00:00',0),
              ('ended-before','2026-08-15 12:00:00','Hydraulic','2026-08-31 23:59:59',0),
              ('ended-boundary','2026-08-15 12:00:00','Hydraulic','2026-09-01 00:00:00',0),
              ('first','2026-09-01 00:00:00','Hydraulic','2026-10-02 12:00:00',0),
              ('blank','2026-09-10 12:00:00','',None,0),
              ('legacy','2026-09-10 13:00:00','Obsolete category',None,0),
              ('excluded-au','2026-09-30 23:59:59','Safety Systems',None,1),
              ('next','2026-10-01 00:00:00','Hydraulic',None,0)]
        for name,stamp,category,resolved,excluded in rows:
            self.fixture(api.PBM,name,location='Koppie',asset_name='ADT-TEST',asset_category='ADT',
                failure_classification=category,downtime_type='Breakdown',breakdown_start_datetime=stamp,
                resolved_datetime=resolved,exclude_from_au=excluded)
        self.fixture(api.PBM,'cancelled',location='Koppie',asset_category='ADT',downtime_type='Breakdown',
            breakdown_start_datetime='2026-09-15 12:00:00',failure_classification='Braking System',docstatus=2)
        result,unassigned=api.breakdown_counts_by_group('Koppie','2026-09-01','2026-09-30')
        c=result['ADTs']
        self.assertEqual((c['total_count'],c['categorised_count'],c['unresolved_count']),(5,3,2))
        self.assertEqual({r['category']:r['count'] for r in c['categories']},{'Hydraulic':3})
        self.assertEqual({r['name'] for r in c['priority_records']},{'prior','carried-closed','first'})
        self.assertEqual(unassigned,[])
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        with patch.object(dashboard,'fetch_grouped_data',return_value=[]):
            report=api.get_report('Koppie','2026-09-01')
        self.assertEqual(report['groups'][0]['counts'],c)
        self.assertIn('overlapping',report['population'])
        self.assertGreater(c['classified_hours'],0)
        self.assertGreater(c['unresolved_hours'],0)
        from .monthly_tmm_assurance import report_html
        html=report_html(report)
        self.assertIn('carried-closed',html)
        self.assertNotIn('ended-boundary',html)
        self.assertNotIn('ended-before',html)

    def test_report_uses_stored_hours_and_pdf_all_groups_saved_actions(self):
        api.save_actions('Koppie','2026-09-01','Dozers',[self.action('Saved dozer action')])
        api.save_actions('Koppie','2026-09-01','FELs',[self.action('Saved loader action')])
        self.fixture('Availability and Utilisation','stored-measurement',location='Koppie',shift_date='2026-09-15',
            asset_category='ADT',shift_required_hours=12,shift_available_hours=9)
        result=api.get_report('Koppie','2026-09-01')
        self.assertEqual(result['groups'][0]['availability'],[None,None,63.75])
        self.assertEqual(result['selected_period']['start'],'2026-09-01')
        self.assertNotIn('ownership',result)
        self.assertNotIn('machine_scope',result)
        html=api.report_html(result)
        self.assertIn('Saved dozer action',html);self.assertIn('Saved loader action',html)
        self.assertNotIn('Daily A&amp;U Engine Dashboard basis',html)


    def test_legacy_actions_preserved_and_new_categories_and_references_validated(self):
        saved=api.save_actions('Koppie','2026-09-01','ADTs',[self.action()])
        row=saved['actions'][0]
        frappe.db.set_value('Monthly TMM Assurance Action',row['name'],'cause','Historical free text')
        saved=api._saved(api._scope('Koppie','2026-09-01','ADTs'))
        payload=saved['actions']
        payload[0]['action']='Updated action retaining legacy category'
        updated=api.save_actions('Koppie','2026-09-01','ADTs',payload,saved['version'])
        self.assertEqual(updated['actions'][0]['cause'],'Historical free text')
        with self.assertRaises(frappe.ValidationError):
            api.save_actions('Koppie','2026-09-01','Dozers',[dict(self.action(),cause='New arbitrary value')])
        self.fixture(api.PBM,'linked',location='Koppie',asset_name='ADT-TEST',asset_category='ADT',
            failure_classification='Safety Systems',downtime_type='Breakdown',breakdown_start_datetime='2026-09-15 12:00:00')
        linked=api.save_actions('Koppie','2026-09-01','ADTs',
            [dict(self.action(),cause='Safety Systems',breakdown_reference='linked')],updated['version'])
        self.assertEqual(linked['actions'][0]['breakdown_reference'],'linked')
        with self.assertRaises(frappe.ValidationError):
            api.save_actions('Koppie','2026-09-01','Dozers',[dict(self.action(),breakdown_reference='linked')])
        with self.assertRaises(frappe.ValidationError):
            api.save_actions('Koppie','2026-09-01','ADTs',
                [dict(linked['actions'][0],name='foreign-child')],linked['version'])

    def test_capture_controller_persists_all_master_choices_and_blank_history(self):
        from engineering.engineering.doctype.plant_breakdown_or_maintenance.plant_breakdown_or_maintenance import PlantBreakdownorMaintenance

        from contextlib import ExitStack
        # Block unrelated breakdown workflow side effects while testing the actual
        # controller, Link validator and database writes on the disposable site.
        with ExitStack() as stack:
            for method in ('enforce_signature_role_permissions','before_insert','after_insert','on_update'):
                stack.enter_context(patch.object(PlantBreakdownorMaintenance,method))
            def make(category):
                return PlantBreakdownorMaintenance(dict(doctype=api.PBM,location='Koppie',asset_name='ADT-TEST',
                    asset_category='ADT',downtime_type='Breakdown',failure_classification=category,
                    breakdown_start_datetime='2026-09-01 08:00:00'))
            with self.assertRaises(frappe.ValidationError):make('').insert()
            for category in TEST_CLASSIFICATIONS:
                doc=make(category).insert()
                self.assertEqual(frappe.db.get_value(api.PBM,doc.name,'failure_classification'),category)
            frappe.db.set_value(api.PBM,doc.name,'failure_classification','')
            doc=PlantBreakdownorMaintenance(api.PBM,doc.name)
            doc.breakdown_reason='Unrelated legacy edit'
            with self.assertRaises(frappe.ValidationError):doc.save()
            self.assertFalse(frappe.db.get_value(api.PBM,doc.name,'failure_classification'))
            doc.failure_classification='Invented option'
            with self.assertRaises(frappe.ValidationError): doc.save()

    def test_split_support_actions_and_historical_ancillary_remain_editable(self):
        self.fixture(api.PBM,'support-event',location='Koppie',asset_name='TLB-TEST',asset_category='TLB',
            failure_classification='Hydraulic',downtime_type='Breakdown',breakdown_start_datetime='2026-09-15 12:00:00')
        original=api.save_actions('Koppie','2026-09','Ancillary',[dict(self.action('Historic ancillary action'),breakdown_reference='support-event')])
        split=api.save_actions('Koppie','2026-09','TLBs',[self.action('Specific TLB action')])
        report=api.get_report('Koppie','2026-09')
        legacy=next(g for g in report['groups'] if g['group']=='Ancillary')
        self.assertEqual(legacy['actions'],original['actions'])
        self.assertEqual(next(g for g in report['groups'] if g['group']=='TLBs')['actions'],split['actions'])
        self.assertNotIn('data-group="Ancillary"',report['availability_chart'])
        changed=[dict(original['actions'][0],action='Retained original scope')]
        api.save_actions('Koppie','2026-09','Ancillary',changed,original['version'])

    def test_registered_page_loads_its_actual_assets(self):
        from frappe.desk.desk_page import get
        page=get('monthly-tmm-assurance')
        self.assertEqual(page.title,'Monthly TMM Assurance')
        self.assertIn('class MonthlyTMMAssurance',page.script)
        self.assertIn('make_app_page',page.script)
        self.assertIn('.monthly-tmm-assurance',page.style)

    def test_actual_frappe_pdf_contains_every_group_chart_and_saved_actions(self):
        from .monthly_tmm_assurance import reporting_period
        from .monthly_tmm_assurance import category_counts, monthly_population
        from datetime import date
        import fitz
        result=dict(site='Koppie',**reporting_period('2026-09',today=date(2026,10,30)),groups=[],population='Distinct breakdown events overlapping the reporting calendar month, including carried-in and repaired/closed events',counting_unit='One breakdown record',status_basis='Current status')
        for group in GROUPS:
            saved=api.save_actions('Koppie','2026-09-01',group,[self.action(f'{group} saved action')])
            result['groups'].append(dict(group=group,availability=[None,0,85],
                counts=category_counts(monthly_population([dict(name=group+'-'+str(i),failure_classification='Hydraulic' if i<2 else 'Engine',
                    asset_name='TEST',breakdown_start_datetime='2026-08-15 12:00:00' if i==0 else '2026-09-15 12:00:00',
                    resolved_datetime='2026-09-20 12:00:00') for i in range(3)],'2026-09-01','2026-09-30'), classifications=TEST_CLASSIFICATIONS),actions=saved['actions']))
        for group in result['groups']:
            rows=[dict(row,downtime_hours=1) for category in group['counts']['categories'] for row in category['records']]
            group['counts']=api.category_downtime(rows,TEST_CLASSIFICATIONS,{})
        with patch.object(api,'get_report',return_value=result):
            api.download_pdf('Koppie','2026-09-01')
        pdf=frappe.local.response.filecontent
        output=Path('/tmp/monthly-tmm-assurance-validation')
        output.mkdir(exist_ok=True)
        (output/'report.pdf').write_bytes(pdf)
        doc=fitz.open(stream=pdf,filetype='pdf')
        text='\n'.join(p.get_text() for p in doc)
        self.assertGreaterEqual(len(doc),8)
        for group in GROUPS:
            self.assertIn(f'{group} saved action',' '.join(text.split()))
        for label in ['N/A','0.00%','85.00%','100.0%','Cumulative percentage','first 80%','66.7%']:
            self.assertIn(label,text)
        self.assertIn('2026-08-15',text)  # Earlier-started, now-closed event is present in exported priority details.
        self.assertIn('including carried-in and repaired/closed events',' '.join(text.split()))
        # Inspect actual rendered chart pixels, not just an HTML image tag.
        chart_pages=[p for p in doc if 'Breakdown downtime (hours)' in p.get_text()]
        self.assertEqual(len(chart_pages),len(GROUPS))
        for page in chart_pages:
            image=page.get_pixmap()
            pixels=image.samples
            blue=sum(1 for r,g,b in zip(pixels[0::3],pixels[1::3],pixels[2::3]) if b>180 and 80<g<190 and r<100)
            orange=sum(1 for r,g,b in zip(pixels[0::3],pixels[1::3],pixels[2::3]) if r>200 and 60<g<190 and b<80)
            self.assertGreater(blue,1000)
            self.assertGreater(orange,20)
        doc[0].get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(str(output/'pdf-availability.png'))
        doc[1].get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(str(output/'pdf-pareto-actions.png'))


    def test_mpp_stored_sql_totals_october_boundary_and_editable_export(self):
        from io import BytesIO
        from pptx import Presentation
        frappe.db.delete('Monthly Production Planning')
        for i,(start,end) in enumerate([('2026-07-20','2026-08-23'),('2026-08-24','2026-09-20'),('2026-09-21','2026-10-18')]):
            self.fixture('Monthly Production Planning','mpp-'+str(i),location='Koppie',
                prod_month_start_date=start,prod_month_end_date=end)
        self.fixture('Monthly Production Planning','duplicate-mpp',location='Koppie',
            prod_month_start_date='2026-09-21',prod_month_end_date='2026-10-18')
        self.fixture('Availability and Utilisation','oct-valid',location='Koppie',shift_date='2026-10-18',
            asset_category='ADT',shift_required_hours=18240,shift_available_hours=14766.5299999999)
        for name,stamp,options in [('next-period','2026-10-19',{}),('before-period','2026-09-20',{}),
                                     ('invalid','2026-10-01',{'invalid_pre_use_hours':1}),
                                     ('cancelled','2026-10-01',{'docstatus':2})]:
            self.fixture('Availability and Utilisation',name,location='Koppie',shift_date=stamp,
                asset_category='ADT',shift_required_hours=100000,shift_available_hours=100000,**options)
        self.fixture('Availability and Utilisation','unsupported',location='Koppie',shift_date='2026-10-01',
            asset_category='LDV',shift_required_hours=1,shift_available_hours=1)
        for name,stamp,resolved in [('carry-in','2026-08-01','2026-09-22'),('last-day','2026-10-18 23:59:59',None),('subsequent','2026-10-19',None)]:
            self.fixture(api.PBM,name,location='Koppie',asset_category='ADT',failure_classification='Hydraulic',
                downtime_type='Breakdown',breakdown_start_datetime=stamp,resolved_datetime=resolved)
        result=api.get_report('Koppie','2026-10')
        self.assertEqual(f"{result['groups'][0]['availability'][-1]:.2f}",'68.81')
        self.assertEqual(result['groups'][0]['counts']['total_count'],2)
        self.assertEqual(result['selected_period']['end'],'2026-10-18')
        self.assertIn('LDV',result['unsupported_categories'][0]['categories'])
        self.assertTrue(any('duplicate' in w for w in result['warnings']))
        api.download_presentation('Koppie','2026-10')
        payload=frappe.local.response.filecontent
        self.assertGreaterEqual(len(Presentation(BytesIO(payload)).slides),5)
        self.assertTrue(frappe.local.response.filename.endswith('.pptx'))
        Path('/tmp/tmm-mpp-presentation/database-fixture.pptx').write_bytes(payload)

    def test_missing_and_conflicting_mpp_cannot_export_calendar_fallback(self):
        frappe.db.delete('Monthly Production Planning')
        with self.assertRaises(frappe.ValidationError):api.download_presentation('Koppie','2026-10')
        for i,start in enumerate(['2026-09-21','2026-09-22']):
            self.fixture('Monthly Production Planning','conflict-'+str(i),location='Koppie',
                prod_month_start_date=start,prod_month_end_date='2026-10-18')
        with self.assertRaises(frappe.ValidationError):api.download_presentation('Koppie','2026-10')
