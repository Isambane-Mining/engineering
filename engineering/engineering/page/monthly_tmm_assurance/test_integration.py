"""Real schema/save/permission/PDF checks, on a disposable SQLite site only.

Run with TMM_TEST_SITES=/tmp/production-summary-validation-tmm/sites and bench Python.
Never reads credentials or connects to the working bench's site.
"""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import frappe

from . import monthly_tmm_assurance as api
from .calculations import GROUPS


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
            dict(fieldname='asset_name',fieldtype='Data'),dict(fieldname='shift_date',fieldtype='Date'),
            dict(fieldname='shift',fieldtype='Data'),dict(fieldname='shift_system',fieldtype='Data'),dict(fieldname='shift_required_hours',fieldtype='Float')])
        cls.schema('Pre-Use Hours', [dict(fieldname='location',fieldtype='Link',options='Location'),dict(fieldname='shift_date',fieldtype='Date')])
        cls.schema('Monthly Production Planning', [dict(fieldname='location',fieldtype='Link',options='Location'),
            dict(fieldname='site_status',fieldtype='Data'),dict(fieldname='prod_month_start_date',fieldtype='Date'),dict(fieldname='prod_month_end_date',fieldtype='Date')])
        cls.schema(api.PBM, [dict(fieldname='location',fieldtype='Link',options='Location'),
            *[dict(fieldname=f,fieldtype='Data') for f in ['asset_name','asset_category','problem_category','downtime_type','open_closed','breakdown_reason']],
            dict(fieldname='exclude_from_au',fieldtype='Check'),dict(fieldname='breakdown_start_datetime',fieldtype='Datetime'),
            dict(fieldname='resolved_datetime',fieldtype='Datetime')])
        from engineering.engineering.problem_categories import PROBLEM_CATEGORIES
        meta=frappe.get_doc('DocType',api.PBM)
        field=next(f for f in meta.fields if f.fieldname=='problem_category')
        field.fieldtype='Select'
        field.options='\n'+'\n'.join(PROBLEM_CATEGORIES)
        field.mandatory_depends_on="eval:doc.downtime_type === 'Breakdown' && doc.__islocal"
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

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback(save_point='tmm_case')

    def action(self, text='Inspect hoses'):
        return dict(cause='Hydraulics',action=text,owner_name='Engineer',due_date='2026-10-03',status='Open')

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
                     lambda: api.download_pdf('Gwab','2026-09-01')]:
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
            with patch.object(api,'_shift_rows',side_effect=AssertionError('Engine must not read denied source data')):
                with self.assertRaises(frappe.PermissionError):
                    api.get_report('Koppie','2026-09-01')
        finally:
            frappe.set_user('Administrator')
            frappe.delete_doc('User Permission',permission.name,ignore_permissions=True)
            frappe.clear_cache(user=user)

    def test_asset_restriction_cannot_change_fleet_percentage(self):
        self.fixture('Asset','visible-fleet-asset',asset_name='VISIBLE',asset_category='ADT',asset_owner='Company',location='Koppie',docstatus=1)
        self.fixture('Asset','hidden-fleet-asset',asset_name='HIDDEN',asset_category='ADT',asset_owner='Company',location='Koppie',docstatus=1)
        user='tmm-engineer@example.invalid'
        permission=frappe.get_doc(dict(doctype='User Permission',user=user,allow='Asset',
            for_value='visible-fleet-asset',apply_to_all_doctypes=1)).insert(ignore_permissions=True)
        frappe.clear_cache(user=user)
        try:
            frappe.set_user(user)
            with patch.object(api,'_shift_rows',side_effect=AssertionError('Cannot generate partial-fleet result')):
                with self.assertRaises(frappe.PermissionError): api.get_report('Koppie','2026-09-01')
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
        rows=[('prior','2026-08-31 23:59:59','Hydraulics',None,0),
              ('carried-closed','2026-08-15 12:00:00','Hydraulics','2026-09-02 12:00:00',0),
              ('ended-before','2026-08-15 12:00:00','Hydraulics','2026-08-31 23:59:59',0),
              ('ended-boundary','2026-08-15 12:00:00','Hydraulics','2026-09-01 00:00:00',0),
              ('first','2026-09-01 00:00:00','Hydraulics','2026-10-02 12:00:00',0),
              ('blank','2026-09-10 12:00:00','',None,0),
              ('legacy','2026-09-10 13:00:00','Obsolete category',None,0),
              ('excluded-au','2026-09-30 23:59:59','FRCS',None,1),
              ('next','2026-10-01 00:00:00','Hydraulics',None,0)]
        for name,stamp,category,resolved,excluded in rows:
            self.fixture(api.PBM,name,location='Koppie',asset_name='ADT-TEST',asset_category='ADT',
                problem_category=category,downtime_type='Breakdown',breakdown_start_datetime=stamp,
                resolved_datetime=resolved,exclude_from_au=excluded)
        self.fixture(api.PBM,'cancelled',location='Koppie',asset_category='ADT',downtime_type='Breakdown',
            breakdown_start_datetime='2026-09-15 12:00:00',problem_category='Brakes',docstatus=2)
        result,unassigned=api.breakdown_counts_by_group('Koppie','2026-09-01')
        c=result['ADTs']
        self.assertEqual((c['total_count'],c['categorised_count'],c['unresolved_count']),(6,4,2))
        self.assertEqual({r['category']:r['count'] for r in c['categories']},{'Hydraulics':3,'FRCS':1})
        self.assertEqual({r['name'] for r in c['priority_records']},{'prior','carried-closed','first','excluded-au'})
        self.assertEqual(unassigned,[])
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        with patch.object(dashboard,'fetch_grouped_data',return_value=[]):
            report=api.get_report('Koppie','2026-09-01')
        self.assertEqual(report['groups'][0]['counts'],c)
        self.assertIn('overlapping',report['population'])
        from .presentation import report_html
        html=report_html(report)
        self.assertIn('carried-closed',html)
        self.assertNotIn('ended-boundary',html)
        self.assertNotIn('ended-before',html)

    def test_report_uses_dashboard_defaults_and_pdf_all_groups_saved_actions(self):
        from .calculations import reporting_period
        from datetime import date
        api.save_actions('Koppie','2026-09-01','Dozers',[self.action('Saved dozer action')])
        api.save_actions('Koppie','2026-09-01','FELs',[self.action('Saved loader action')])
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        source=[dict(indent=3,asset_name='ADT-TEST',asset_category='ADT',required_hours=12,
                     availability_available_hours=9,utilisation_available_hours=9)]
        with patch.object(dashboard,'fetch_grouped_data',return_value=source) as fetch:
            result=api.get_report('Koppie','2026-09-01')
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(fetch.call_args.args,('Koppie','2026-09-01','2026-09-30',
                         'Production + Swing/Spare Machines','85% A & U','Isambane & Excavo Assets'))
        self.assertEqual(result['groups'][0]['availability'],[63.75]*3)
        from .presentation import report_html
        html=report_html(result)
        self.assertIn('Saved dozer action',html)
        self.assertIn('Saved loader action',html)
        self.assertIn('Three-month availability by equipment group',html)

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
            problem_category='FRCS',downtime_type='Breakdown',breakdown_start_datetime='2026-09-15 12:00:00')
        linked=api.save_actions('Koppie','2026-09-01','ADTs',
            [dict(self.action(),cause='FRCS',breakdown_reference='linked')],updated['version'])
        self.assertEqual(linked['actions'][0]['breakdown_reference'],'linked')
        with self.assertRaises(frappe.ValidationError):
            api.save_actions('Koppie','2026-09-01','Dozers',[dict(self.action(),breakdown_reference='linked')])
        with self.assertRaises(frappe.ValidationError):
            api.save_actions('Koppie','2026-09-01','ADTs',
                [dict(linked['actions'][0],name='foreign-child')],linked['version'])

    def test_capture_controller_persists_valid_and_unchanged_legacy_categories(self):
        from engineering.engineering.doctype.plant_breakdown_or_maintenance.plant_breakdown_or_maintenance import PlantBreakdownorMaintenance
        from engineering.engineering.problem_categories import PROBLEM_CATEGORIES
        from contextlib import ExitStack
        # Block unrelated breakdown workflow side effects while testing the actual
        # controller, Select validator and database writes on the disposable site.
        with ExitStack() as stack:
            for method in ('enforce_signature_role_permissions','before_insert','after_insert','on_update'):
                stack.enter_context(patch.object(PlantBreakdownorMaintenance,method))
            def make(category):
                return PlantBreakdownorMaintenance(dict(doctype=api.PBM,location='Koppie',asset_name='ADT-TEST',
                    asset_category='ADT',downtime_type='Breakdown',problem_category=category,
                    breakdown_start_datetime='2026-09-01 08:00:00'))
            with self.assertRaises(frappe.ValidationError): make('').insert()
            for category in PROBLEM_CATEGORIES:
                doc=make(category).insert()
                self.assertEqual(frappe.db.get_value(api.PBM,doc.name,'problem_category'),category)
            frappe.db.set_value(api.PBM,doc.name,'problem_category','Legacy unsupported')
            doc=PlantBreakdownorMaintenance(api.PBM,doc.name)
            doc.resolved_datetime='2026-09-02 12:00:00'
            doc.save()
            self.assertEqual(frappe.db.get_value(api.PBM,doc.name,'problem_category'),'Legacy unsupported')
            frappe.db.set_value(api.PBM,doc.name,'problem_category','')
            doc=PlantBreakdownorMaintenance(api.PBM,doc.name)
            doc.breakdown_reason='Unrelated legacy edit'
            doc.save()
            self.assertFalse(frappe.db.get_value(api.PBM,doc.name,'problem_category'))
            doc.problem_category='Invented option'
            with self.assertRaises(frappe.ValidationError): doc.save()

    def test_registered_page_loads_its_actual_assets(self):
        from frappe.desk.desk_page import get
        page=get('monthly-tmm-assurance')
        self.assertEqual(page.title,'Monthly TMM Assurance')
        self.assertIn('class MonthlyTMMAssurance',page.script)
        self.assertIn('make_app_page',page.script)

    def test_actual_frappe_pdf_contains_every_group_chart_and_saved_actions(self):
        from .calculations import reporting_period
        from .defects import category_counts, monthly_population
        from datetime import date
        import fitz
        result=dict(site='Koppie',**reporting_period('2026-09',today=date(2026,10,30)),groups=[],population='Distinct breakdown events overlapping the reporting calendar month, including carried-in and repaired/closed events',counting_unit='One breakdown record',status_basis='Current status')
        for group in GROUPS:
            saved=api.save_actions('Koppie','2026-09-01',group,[self.action(f'{group} saved action')])
            result['groups'].append(dict(group=group,availability=[None,0,85],
                counts=category_counts(monthly_population([dict(name=group+'-'+str(i),problem_category='Hydraulics' if i<2 else 'Engine / Starting',
                    asset_name='TEST',breakdown_start_datetime='2026-08-15 12:00:00' if i==0 else '2026-09-15 12:00:00',
                    resolved_datetime='2026-09-20 12:00:00') for i in range(3)],'2026-09-01')),actions=saved['actions']))
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
        for label in ['N/A','0.0%','85.0%','100.0%','Cumulative percentage','first 80%','66.7%']:
            self.assertIn(label,text)
        self.assertIn('2026-08-15',text)  # Earlier-started, now-closed event is present in exported priority details.
        self.assertIn('including carried-in and repaired/closed events',' '.join(text.split()))
        # Inspect actual rendered chart pixels, not just an HTML image tag.
        chart_pages=[p for p in doc if 'Number of breakdown records' in p.get_text()]
        self.assertEqual(len(chart_pages),7)
        for page in chart_pages:
            image=page.get_pixmap()
            pixels=image.samples
            blue=sum(1 for r,g,b in zip(pixels[0::3],pixels[1::3],pixels[2::3]) if b>180 and 80<g<190 and r<100)
            orange=sum(1 for r,g,b in zip(pixels[0::3],pixels[1::3],pixels[2::3]) if r>200 and 60<g<190 and b<80)
            self.assertGreater(blue,1000)
            self.assertGreater(orange,20)
        doc[0].get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(str(output/'pdf-availability.png'))
        doc[1].get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(str(output/'pdf-pareto-actions.png'))
