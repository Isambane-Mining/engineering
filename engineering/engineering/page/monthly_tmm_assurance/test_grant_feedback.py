"""Grant feedback: presentation and canonical categorisation regression tests."""
import base64
from datetime import date
import unittest
import xml.etree.ElementTree as ET

from .calculations import GROUPS, reporting_period


class TestAvailabilityGraph(unittest.TestCase):
    def test_three_individual_months_missing_zero_and_above_100(self):
        from .presentation import availability_svg
        data=dict(**reporting_period('2026-09',today=date(2026,10,30)),
                  groups=[dict(group=g,availability=[None,0,105] if i==0 else [80,85,90]) for i,g in enumerate(GROUPS)])
        before=[g['availability'][:] for g in data['groups']]
        svg=availability_svg(data)
        root=ET.fromstring(svg)
        ns={'s':'http://www.w3.org/2000/svg'}
        self.assertEqual(len(root.findall('.//s:g[@data-group]',ns)),7)
        self.assertEqual(len(root.findall('.//s:rect[@data-month]',ns)),21)
        self.assertEqual([g['availability'] for g in data['groups']],before)
        for label in ['N/A','0.0%','105.0%','Jul 2026','Aug 2026','Sep 2026','Availability (%)']:
            self.assertIn(label,svg)
        self.assertIn('aria-label="ADTs',svg)


class TestControlledCategories(unittest.TestCase):
    def test_schema_and_capture_validation_share_canonical_options(self):
        import json
        from pathlib import Path
        from engineering.engineering.problem_categories import PROBLEM_CATEGORIES, validate_problem_category
        self.assertEqual(PROBLEM_CATEGORIES[-6:],('FRCS','Stop Blocks','Machine Locks','Bowl Lock Pins','Brake Test','Steps / Handrail'))
        self.assertNotIn('Cylinders',PROBLEM_CATEGORIES)
        path=Path(__file__).resolve().parents[2]/'doctype/plant_breakdown_or_maintenance/plant_breakdown_or_maintenance.json'
        field=next(f for f in json.loads(path.read_text())['fields'] if f['fieldname']=='problem_category')
        self.assertEqual(tuple(field['options'].splitlines()[1:]),PROBLEM_CATEGORIES)
        for value in PROBLEM_CATEGORIES:
            validate_problem_category(value,is_new=True)
        for value in ['', 'Cylinders','Legacy spelling']:
            with self.assertRaises(ValueError): validate_problem_category(value,is_new=True)
            validate_problem_category(value,is_new=False,previous=value)
        with self.assertRaises(ValueError): validate_problem_category('',is_new=False,previous='Brakes')


class TestCountPareto(unittest.TestCase):
    def test_counts_identity_not_days_and_denominator_excludes_unresolved(self):
        from .defects import category_counts
        records=[dict(name='one',problem_category='Hydraulics'),dict(name='one',problem_category='Hydraulics'),
                 dict(name='two',problem_category='Brakes'),dict(name='blank',problem_category=''),
                 dict(name='legacy',problem_category='Unknown legacy'),dict(name='cancelled',problem_category='Brakes',docstatus=2)]
        result=category_counts(records)
        self.assertEqual(result['total_count'],4)
        self.assertEqual(result['categorised_count'],2)
        self.assertEqual(result['unresolved_count'],2)
        self.assertEqual(sum(r['count'] for r in result['categories']),2)
        self.assertEqual(result['categories'][-1]['cumulative_percent'],100)
        self.assertEqual({r['name'] for r in result['priority_records']},{'one','two'})

    def test_80_crossing_ties_and_priority_beyond_top10(self):
        from .defects import category_counts
        from engineering.engineering.problem_categories import PROBLEM_CATEGORIES
        result=category_counts([dict(name=str(i),problem_category=c) for i,c in enumerate(PROBLEM_CATEGORIES)])
        self.assertEqual([r['category'] for r in result['categories']],[*PROBLEM_CATEGORIES])
        self.assertEqual(result['priority_category_count'],13)
        self.assertEqual(result['categories'][12]['priority'],True)
        self.assertEqual(result['categories'][13]['priority'],False)
        self.assertEqual(result['displayed_count'],10)
        self.assertEqual(result['omitted_count'],6)
        self.assertEqual(result['categories'][9]['cumulative_percent'],62.5)
        self.assertEqual(len(result['priority_records']),13)
        self.assertEqual(category_counts([])['priority_records'],[])


class TestCaptureController(unittest.TestCase):
    def test_server_requires_new_category_but_allows_unchanged_legacy_closure(self):
        from unittest.mock import patch
        import frappe
        from engineering.engineering.doctype.plant_breakdown_or_maintenance.plant_breakdown_or_maintenance import PlantBreakdownorMaintenance
        doc=object.__new__(PlantBreakdownorMaintenance)
        doc.__dict__.update(doctype='Plant Breakdown or Maintenance',downtime_type='Breakdown',problem_category='',flags=frappe._dict())
        def reject(message):
            raise ValueError(message)
        with patch.object(doc,'enforce_signature_role_permissions'), patch.object(frappe,'throw',side_effect=reject), \
             patch.object(doc,'is_new',return_value=True):
            with self.assertRaises(ValueError): doc.validate()
            doc.problem_category='Brake Test'
            doc.validate()
        previous=frappe._dict(downtime_type='Breakdown',problem_category='Old unsupported spelling')
        doc.problem_category=previous.problem_category
        doc.resolved_datetime='2026-09-30 16:00:00'
        with patch.object(doc,'enforce_signature_role_permissions'),patch.object(doc,'is_new',return_value=False), \
             patch.object(doc,'get_doc_before_save',return_value=previous),patch.object(frappe,'throw',side_effect=reject):
            doc.validate()
            doc.problem_category='Other invented category'
            with self.assertRaises(ValueError): doc.validate()


class TestMonthlyPopulation(unittest.TestCase):
    def test_overlapping_calendar_month_counts_carried_and_closed_records_once(self):
        from .defects import monthly_population
        rows=[dict(name='prior',breakdown_start_datetime='2026-08-31 23:59:59'),
              dict(name='carried-closed',breakdown_start_datetime='2026-08-15 12:00:00',resolved_datetime='2026-09-02 08:00:00'),
              dict(name='ended-before',breakdown_start_datetime='2026-08-15 12:00:00',resolved_datetime='2026-08-31 23:59:59'),
              dict(name='ended-at-boundary',breakdown_start_datetime='2026-08-15 12:00:00',resolved_datetime='2026-09-01 00:00:00'),
              dict(name='instant',breakdown_start_datetime='2026-09-01 00:00:00',resolved_datetime='2026-09-01 00:00:00'),
              dict(name='first',breakdown_start_datetime='2026-09-01 00:00:00',resolved_datetime=None),
              dict(name='long',breakdown_start_datetime='2026-09-15 12:00:00',resolved_datetime='2026-11-01 12:00:00'),
              dict(name='last',breakdown_start_datetime='2026-09-30 23:59:59',exclude_from_au=1),
              dict(name='next',breakdown_start_datetime='2026-10-01 00:00:00'),
              dict(name='cancelled',breakdown_start_datetime='2026-09-10 00:00:00',docstatus=2),
              dict(name='maintenance',breakdown_start_datetime='2026-09-10 00:00:00',downtime_type='Planned Maintenance')]
        result=monthly_population(rows+[rows[1]],'2026-09-01')
        self.assertEqual([r['name'] for r in result],['prior','carried-closed','instant','first','long','last'])
        self.assertTrue(all('status_label' in r for r in result))

    def test_long_event_counted_once_in_each_month_it_overlaps_across_year(self):
        from .defects import monthly_population
        row=dict(name='same-record',breakdown_start_datetime='2026-11-28 12:00:00',resolved_datetime='2027-02-01 00:00:00')
        for month in ['2026-11-01','2026-12-01','2027-01-01']:
            self.assertEqual([r['name'] for r in monthly_population([row,row],month)],['same-record'])
        self.assertEqual(monthly_population([row],'2027-02-01'),[])



class TestCountPresentation(unittest.TestCase):
    def test_top10_stops_below100_and_80_reference_and_priority_are_visible(self):
        from .defects import category_counts
        from .presentation import count_chart_image, count_summary
        from engineering.engineering.problem_categories import PROBLEM_CATEGORIES
        result=category_counts([dict(name=str(i),problem_category=c) for i,c in enumerate(PROBLEM_CATEGORIES)])
        html=count_chart_image(result)
        svg=base64.b64decode(html.split('base64,')[1].split('"')[0]).decode()
        self.assertIn('80% reference',svg)
        self.assertIn('62.5%',svg)
        self.assertNotIn('>100.0%</text>',svg)
        self.assertIn('Number of breakdown records',svg)
        self.assertIn('13 categories account for 81.2%',count_summary(result))


class TestWhatsAppCapture(unittest.TestCase):
    def test_book_down_passes_explicit_controlled_category_without_text_inference(self):
        from unittest.mock import MagicMock, patch
        from types import SimpleNamespace
        from datetime import datetime
        import frappe
        from engineering.engineering.doctype.whatsapp_breakdown_message_log import whatsapp_breakdown_message_log as capture
        log=frappe._dict(target_site='Koppie',target_shift='Day Shift',detected_plant_no='TEST',
                        detected_reason='A cylinder mentioned in free text',raw_message='',detected_hours=100)
        log.save=MagicMock()
        doc=SimpleNamespace(name='test-ref',insert=MagicMock())
        with patch.object(capture,'combine_date_and_time',return_value=datetime(2026,9,15,8)), \
             patch.object(capture.frappe,'new_doc',return_value=doc), \
             patch.object(capture.frappe,'db',SimpleNamespace(commit=MagicMock())):
            capture.create_breakdown_from_log(log,problem_category='FRCS')
        doc.insert.assert_called_once_with()
        self.assertEqual(doc.problem_category,'FRCS')
        self.assertEqual(doc.breakdown_reason,'A cylinder mentioned in free text')

    def test_whatsapp_maintenance_and_book_back_do_not_require_category(self):
        from unittest.mock import MagicMock,patch
        import frappe
        from engineering.engineering.doctype.whatsapp_breakdown_message_log import whatsapp_breakdown_message_log as capture
        log=frappe._dict(detected_action='Book Down',raw_message='planned maintenance',detected_reason='',detected_resolution='')
        log.check_permission=MagicMock()
        with patch.object(capture.frappe,'get_doc',return_value=log):
            self.assertFalse(capture.requires_breakdown_category('test-log'))
            log.raw_message='Cylinder fault without category inference'
            self.assertTrue(capture.requires_breakdown_category('test-log'))
            log.detected_action='Book Back'
            self.assertFalse(capture.requires_breakdown_category('test-log'))
        log.check_permission.assert_called_with('read')
