from datetime import datetime
from unittest import TestCase
from unittest.mock import patch
import frappe
from engineering.engineering.page.machines_available import machines_available as popup


class TestHourBreakdowns(TestCase):
    def setUp(self):
        self.plan=dict(name='PLAN',location='Site',prod_month_start_date='2026-09-01',prod_month_end_date='2026-09-30',
                       excavator_truck_assignments=[dict(truck='ADT1',excavator='EX1'),dict(truck='ADT2',excavator='')])
        self.asset=dict(name='ADT1',asset_name='Truck 1',location='Moved Site',asset_category='ADT')
        self.rows=[dict(name='PBM1',location='Site',asset_name='ADT1',failure_classification='Hydraulic',breakdown_reason='Hose',
                       breakdown_start_datetime='2026-10-01 00:30:00',resolved_datetime='2026-10-01 01:15:00'),
                   dict(name='PBM2',location='Site',asset_name='ADT1',failure_classification='Brakes',breakdown_reason='Brake',
                       breakdown_start_datetime='2026-10-01 00:45:00',resolved_datetime=None)]

    def request(self, scope='all', rows=None):
        rows=self.rows if rows is None else rows
        def permitted(doctype, filters, **kwargs):
            self.queries.append((doctype,filters,kwargs))
            return [frappe._dict(name=self.asset['name'])] if doctype=='Asset' else [frappe._dict(name=r['name']) for r in rows]
        def read(doctype,name):
            if doctype=='Asset':return self.asset
            row=next(r for r in rows if r['name']==name)
            if row.get('denied'):raise frappe.PermissionError
            return row
        self.queries=[]
        with patch.object(popup.frappe,'session',frappe._dict(user='test')), \
             patch.object(popup.frappe,'has_permission',return_value=True), \
             patch.object(popup.analysis,'load_plans',return_value=[self.plan]), \
             patch.object(popup.summary,'_permitted_rows',side_effect=permitted), \
             patch.object(popup.summary,'_read_document',side_effect=read):
            return popup.get_hour_breakdowns('Site','2026-09-30',18,scope)

    def test_night_rollover_clipping_union_and_record_details(self):
        result=self.request()
        self.assertEqual(result['start'],'2026-10-01 00:00:00')
        self.assertEqual(result['end'],'2026-10-01 01:00:00')
        machine=result['machines'][0]
        self.assertEqual(machine['machine_number'],'Truck 1')
        self.assertEqual(machine['downtime_minutes'],30)
        self.assertEqual([r['overlap_minutes'] for r in machine['breakdowns']],[30,15])
        self.assertEqual(machine['breakdowns'][0]['failure_classification'],'Hydraulic')
        self.assertIsNone(machine['breakdowns'][1]['resolved_datetime'])
        pbm=next(q for q in self.queries if q[0]=='Plant Breakdown or Maintenance')
        self.assertEqual(pbm[1]['breakdown_start_datetime'],['<',datetime(2026,10,1,1)])
        self.assertEqual(pbm[2]['or_filters'][0],['resolved_datetime','>',datetime(2026,10,1)])

    def test_historical_scope_does_not_use_current_location(self):
        self.assertEqual(len(self.request('production')['machines']),1)
        self.assertEqual(self.request('spare')['machines'],[])
        filters=self.queries[0][1]
        self.assertEqual(filters['name'],['in',['ADT2']])
        self.assertNotIn('location',filters)

    def test_boundaries_cancellations_exclusions_and_inaccessible_documents(self):
        for changes in [dict(resolved_datetime='2026-10-01 00:00:00'),dict(breakdown_start_datetime='2026-10-01 01:00:00'),
                        dict(denied=True),dict(location='Other'),dict(exclude_from_au=1),dict(docstatus=2),dict(asset_name='UNRELATED')]:
            with self.subTest(changes=changes):
                self.assertEqual(self.request(rows=[dict(self.rows[0],**changes)])['machines'],[])

    def test_duplicate_records_and_subminute_precision(self):
        row=dict(self.rows[0],breakdown_start_datetime='2026-10-01 00:00:10',resolved_datetime='2026-10-01 00:00:40')
        machine=self.request(rows=[row,row])['machines'][0]
        self.assertEqual(machine['downtime_minutes'],.5)
        self.assertEqual(len(machine['breakdowns']),1)

    def test_guest_invalid_hour_scope_and_missing_plan(self):
        with patch.object(popup.frappe,'session',frappe._dict(user='Guest')):
            with self.assertRaises(frappe.PermissionError):popup.get_hour_breakdowns('Site','2026-09-30',0)
        with patch.object(popup.frappe,'session',frappe._dict(user='test')):
            for hour in [-1,24,'bad',1.5]:
                with self.assertRaises(ValueError):popup.get_hour_breakdowns('Site','2026-09-30',hour)
            with self.assertRaises(ValueError):popup.get_hour_breakdowns('Site','2026-09-30',0,'invalid')
            with patch.object(popup.analysis,'load_plans',return_value=[]):
                with self.assertRaises(frappe.PermissionError):popup.get_hour_breakdowns('Site','2026-09-30',0)

    def test_permission_denial_stops_before_details_query(self):
        with patch.object(popup.frappe,'session',frappe._dict(user='test')), \
             patch.object(popup.analysis,'load_plans',return_value=[self.plan]), \
             patch.object(popup.frappe,'has_permission',side_effect=frappe.PermissionError), \
             patch.object(popup.summary,'_permitted_rows') as query:
            with self.assertRaises(frappe.PermissionError):popup.get_hour_breakdowns('Site','2026-09-30',0)
            query.assert_not_called()

    def test_redacted_classification_is_not_recovered_from_original_document(self):
        row=dict(self.rows[0],failure_classification=None)
        result=self.request(rows=[row])
        self.assertIsNone(result['machines'][0]['breakdowns'][0]['failure_classification'])
        # Exercise the reused helper with a document that strips the classification field.
        from unittest.mock import Mock
        doc=Mock()
        doc.as_dict.side_effect=[self.rows[0],row]
        with patch.object(popup.summary.frappe,'get_doc',return_value=doc):
            stripped=popup.summary._read_document('Plant Breakdown or Maintenance','PBM1')
        doc.check_permission.assert_called_once_with('read')
        doc.apply_fieldlevel_read_permissions.assert_called_once()
        self.assertIsNone(stripped['failure_classification'])

    def test_display_label_cannot_admit_another_assets_breakdowns(self):
        self.asset['asset_name']='OTHER-ASSET-ID'
        row=dict(self.rows[0],asset_name='OTHER-ASSET-ID')
        self.assertEqual(self.request(rows=[row])['machines'],[])
        filters=next(q[1] for q in self.queries if q[0]=='Plant Breakdown or Maintenance')
        self.assertEqual(filters['asset_name'],['in',['ADT1']])
