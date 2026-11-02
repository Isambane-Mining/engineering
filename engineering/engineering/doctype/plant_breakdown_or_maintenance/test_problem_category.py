"""Transaction-only saves after the failure-classification migration is activated."""
import unittest
import frappe
from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS, MASTER_DOCTYPE
from engineering.engineering.page.machine_reliability.machine_reliability import get_dashboard

PBM = 'Plant Breakdown or Maintenance'


class TestFailureClassificationSave(unittest.TestCase):
    def setUp(self):
        # Live activation can intentionally be deferred while worktree changes are reviewed.
        from pathlib import Path
        import json
        schema=json.loads(Path(__file__).with_name('plant_breakdown_or_maintenance.json').read_text())
        expected={f['fieldname'] for f in schema['fields']}
        actual={f.fieldname for f in frappe.get_meta(PBM).fields}
        if not expected.issubset(actual) or actual.intersection({'problem_category', 'problem_subcategory'}):
            self.skipTest('LAB schema has not activated this worktree; do not migrate a different running checkout.')
        frappe.db.savepoint('failure_classification_saves')
        self.original_user=frappe.session.user
        frappe.set_user('Administrator')
        self.old_flags={key:frappe.flags.get(key) for key in ('in_test','in_import','mute_emails')}
        frappe.flags.update(in_test=True,in_import=True,mute_emails=True)
        for label in INITIAL_CLASSIFICATIONS:
            if not frappe.db.exists(MASTER_DOCTYPE,label):
                frappe.get_doc(dict(doctype=MASTER_DOCTYPE,classification_name=label)).insert(ignore_permissions=True)
        self.asset=frappe.db.sql('''select a.name,a.location from `tabAsset` a
            where a.docstatus=1 and a.asset_category='ADT' and ifnull(a.location,'')!=''
            and not exists (select 1 from `tabPlant Breakdown or Maintenance` b
              where b.asset_name=a.name and b.open_closed='Open') order by a.name limit 1''',as_dict=True)[0]

    def tearDown(self):
        frappe.db.rollback(save_point='failure_classification_saves')
        frappe.flags.update(self.old_flags)
        frappe.set_user(self.original_user)

    def make_breakdown(self,**values):
        return frappe.get_doc(dict(doctype=PBM,asset_name=self.asset.name,location=self.asset.location,
            shift='Day Shift',downtime_type='Breakdown',hours_breakdown_starts=100,
            breakdown_start_datetime='2020-01-02 08:00:00',resolved_datetime='2020-01-02 09:00:00',
            breakdown_reason='Operator reported a fault',**values))

    def test_blank_classification_saves_and_can_be_cleared(self):
        doc=self.make_breakdown().insert(ignore_permissions=True)
        self.assertFalse(doc.reload().failure_classification)
        doc.failure_classification='Steering System'
        doc.save(ignore_permissions=True)
        doc.failure_classification=''
        doc.save(ignore_permissions=True)
        self.assertFalse(doc.reload().failure_classification)

    def test_all_twenty_classifications_save_and_filter_without_keywords(self):
        for label in INITIAL_CLASSIFICATIONS:
            with self.subTest(classification=label):
                doc=self.make_breakdown(failure_classification=label).insert(ignore_permissions=True)
                self.assertEqual(doc.reload().failure_classification,label)
                report=get_dashboard('2020-01-01','2020-01-31',fleet=self.asset.name,category=label)
                self.assertEqual(report['summary']['direct_failures'],1)
                self.assertEqual(report['timeline'][0]['name'],doc.name)
                self.assertEqual(report['timeline'][0]['match_source'],'Failure classification')

    def test_existing_record_still_opens_and_saves(self):
        name=frappe.db.get_value(PBM,{'docstatus':0,'open_closed':'Closed'},'name')
        doc=frappe.get_doc(PBM,name)
        before=(doc.breakdown_reason,doc.failure_classification)
        doc.save(ignore_permissions=True)
        self.assertEqual((doc.reload().breakdown_reason,doc.failure_classification),before)

    def test_whatsapp_optional_capture_and_positive_tyre_drilldown_use_real_records(self):
        from unittest.mock import MagicMock, patch
        from engineering.engineering.doctype.whatsapp_breakdown_message_log import whatsapp_breakdown_message_log as capture
        from engineering.controllers.tyre_damage import fetch_tyre_damage_records, damage_counts
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as daily
        log=frappe._dict(target_site=self.asset.location,target_shift='Day Shift',detected_plant_no=self.asset.name,
            detected_reason='Wheel studs and rim damaged',raw_message='',detected_hours=100,
            message_datetime='2020-01-02 08:00:00',detected_start_time='08:00:00')
        log.save=MagicMock()
        with patch.object(frappe.db,'commit'):
            for classification in (None,'Tyres / Wheels'):
                created=capture.create_breakdown_from_log(log,failure_classification=classification)
                doc=frappe.get_doc(PBM,created['breakdown'])
                self.assertEqual(doc.failure_classification or '',classification or '')
                doc.resolved_datetime='2020-01-02 10:00:00'
                doc.open_closed='Closed'
                doc.save(ignore_permissions=True)
        fleet=frappe.db.get_value('Asset',self.asset.name,'asset_name') or self.asset.name
        source=[dict(indent=3,asset_name=fleet,shift_date='2020-01-02',asset_category='ADT')]
        counted=damage_counts(fetch_tyre_damage_records(source,self.asset.location,'2020-01-01','2020-01-31'))
        self.assertEqual(counted['ADT'],1)
        with patch.object(daily,'fetch_grouped_data',return_value=source):
            details=daily.get_tyre_breakdown_details(category='ADT',location=self.asset.location,start_date='2020-01-01',end_date='2020-01-31')
        self.assertEqual(details['total_records'],1)
        self.assertEqual(details['rows'][0]['name'],doc.name)
