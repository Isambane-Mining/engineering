"""Real document saves, isolated by transaction savepoints on LAB."""
import unittest
import frappe
from engineering.engineering.problem_categories import PROBLEM_CATEGORIES, BASE_PROBLEM_CATEGORIES
from engineering.engineering.page.machine_reliability.machine_reliability import get_dashboard

PBM = 'Plant Breakdown or Maintenance'


class TestOptionalProblemCategory(unittest.TestCase):
    def setUp(self):
        frappe.db.savepoint('optional_problem_category')
        self.original_user = frappe.session.user
        frappe.set_user('Administrator')
        self.old_flags = {key: frappe.flags.get(key) for key in ('in_test', 'in_import', 'mute_emails')}
        frappe.flags.update(in_test=True, in_import=True, mute_emails=True)
        self.asset = frappe.db.sql('''select a.name, a.location from `tabAsset` a
            where a.docstatus = 1 and a.asset_category = 'ADT' and ifnull(a.location, '') != '' and not exists
            (select 1 from `tabPlant Breakdown or Maintenance` b
             where b.asset_name = a.name and b.open_closed = 'Open')
            order by a.name limit 1''', as_dict=True)[0]

    def tearDown(self):
        frappe.db.rollback(save_point='optional_problem_category')
        frappe.flags.update(self.old_flags)
        frappe.set_user(self.original_user)

    def make_breakdown(self, **values):
        values.setdefault('problem_category','Hydraulics')
        return frappe.get_doc(dict(doctype=PBM, asset_name=self.asset.name, location=self.asset.location,
            shift='Day Shift', downtime_type='Breakdown', hours_breakdown_starts=100,
            breakdown_start_datetime='2020-01-02 08:00:00', resolved_datetime='2020-01-02 09:00:00',
            breakdown_reason='Operator reported an unspecified fault', **values))

    def test_field_required_for_new_breakdowns_and_beside_reason(self):
        meta = frappe.get_meta(PBM)
        field = meta.get_field('problem_category')
        self.assertIsNotNone(field)
        self.assertEqual(field.fieldtype, 'Select')
        self.assertFalse(field.reqd)
        self.assertIn('doc.__islocal',field.mandatory_depends_on)
        self.assertFalse(field.default)
        self.assertEqual(field.options.splitlines()[1:], list(PROBLEM_CATEGORIES))
        order = [x.fieldname for x in meta.fields]
        self.assertEqual(order.index('problem_category'), order.index('breakdown_reason') + 1)

    def test_new_breakdown_rejects_blank_and_existing_category_cannot_be_cleared(self):
        with self.assertRaises(frappe.ValidationError):
            self.make_breakdown(problem_category='').insert(ignore_permissions=True)
        doc=self.make_breakdown(problem_category='Steering').insert(ignore_permissions=True)
        doc.problem_category=''
        with self.assertRaises(frappe.ValidationError): doc.save(ignore_permissions=True)

    def test_saves_every_category_and_reads_it_in_live_report(self):
        for category in PROBLEM_CATEGORIES:
            with self.subTest(category=category):
                doc = self.make_breakdown(problem_category=category).insert(ignore_permissions=True)
                doc.reload()
                self.assertEqual(doc.problem_category, category)
                if category not in BASE_PROBLEM_CATEGORIES:
                    continue  # Other report's existing keyword configuration remains unchanged.
                report = get_dashboard('2020-01-01', '2020-01-31', fleet=self.asset.name, category=category)
                self.assertEqual(report['summary']['direct_failures'], 1)
                self.assertEqual(report['timeline'][0]['name'], doc.name)
                self.assertEqual(report['timeline'][0]['match_source'], 'Manual category')

    def test_existing_historical_record_opens_and_saves_blank(self):
        doc=self.make_breakdown().insert(ignore_permissions=True)
        frappe.db.set_value(PBM,doc.name,'problem_category','')  # Simulate historical imported data.
        doc.reload()
        self.assertFalse(doc.problem_category)
        original_reason = doc.breakdown_reason
        doc.save(ignore_permissions=True)
        doc.reload()
        self.assertFalse(doc.problem_category)
        self.assertEqual(doc.breakdown_reason, original_reason)

    def test_optional_subcategory_saves_and_classified_query_ignores_text(self):
        from engineering.engineering.page.daily_availability_and_utilization_dashboard.tyre_damage import fetch_tyre_damage_records, damage_counts
        field = frappe.get_meta(PBM).get_field('problem_subcategory')
        self.assertIsNotNone(field)
        self.assertFalse(field.reqd)
        self.assertFalse(field.mandatory_depends_on)
        self.assertFalse(field.default)
        self.assertEqual(field.options, '\nTyre Damage')
        doc = self.make_breakdown().insert(ignore_permissions=True)
        self.assertFalse(doc.reload().problem_subcategory)
        doc.problem_category = 'Tyres / Wheels'
        doc.problem_subcategory = 'Tyre Damage'
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.reload().problem_subcategory, 'Tyre Damage')
        fleet = frappe.db.get_value('Asset', self.asset.name, 'asset_name')
        source = [dict(indent=3, asset_name=fleet or self.asset.name, shift_date='2020-01-02', asset_category='ADT')]
        def records():
            return fetch_tyre_damage_records(source, self.asset.location, '2020-01-01', '2020-01-31', self.asset.name)
        self.assertEqual(damage_counts(records()), {'ADT': 1, 'Dozer': 0})
        doc.downtime_type = 'Planned Maintenance'
        doc.save(ignore_permissions=True)
        self.assertEqual(records(), [])
        doc.downtime_type = 'Breakdown'
        doc.problem_category = 'Other'
        doc.save(ignore_permissions=True)
        self.assertEqual(records(), [])
        frappe.db.set_value(PBM,doc.name,'problem_category','')  # Historical blank, not a new capture.
        doc.reload()
        doc.problem_subcategory = ''
        doc.breakdown_reason = 'Flat tyre, tyre burst and sidewall damage'
        doc.save(ignore_permissions=True)
        self.assertFalse(doc.reload().problem_subcategory)
        self.assertEqual(records(), [])
