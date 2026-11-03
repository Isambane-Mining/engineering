"""Grant feedback: presentation and canonical categorisation regression tests."""
import base64
from datetime import date
import unittest
import xml.etree.ElementTree as ET

from .monthly_tmm_assurance import GROUPS, reporting_period


class TestAvailabilityGraph(unittest.TestCase):
    def test_three_individual_months_missing_zero_and_above_100(self):
        from .monthly_tmm_assurance import availability_svg
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
    def test_schema_and_capture_share_optional_master_link(self):
        import json
        from pathlib import Path
        from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS
        self.assertEqual(len(INITIAL_CLASSIFICATIONS),20)
        path=Path(__file__).resolve().parents[2]/'doctype/plant_breakdown_or_maintenance/plant_breakdown_or_maintenance.json'
        field=next(f for f in json.loads(path.read_text())['fields'] if f['fieldname']=='failure_classification')
        self.assertEqual(field['fieldtype'],'Link')
        self.assertEqual(field['options'],'Breakdown Failure Classification')
        self.assertFalse(field.get('reqd'))
        self.assertFalse(field.get('mandatory_depends_on'))


class TestCountPareto(unittest.TestCase):
    def test_counts_identity_not_days_and_denominator_excludes_unresolved(self):
        from .monthly_tmm_assurance import category_counts
        records=[dict(name='one',failure_classification='Hydraulic'),dict(name='one',failure_classification='Hydraulic'),
                 dict(name='two',failure_classification='Braking System'),dict(name='blank',failure_classification=''),
                 dict(name='legacy',failure_classification='Unknown legacy'),dict(name='cancelled',failure_classification='Braking System',docstatus=2)]
        result=category_counts(records)
        self.assertEqual(result['total_count'],4)
        self.assertEqual(result['categorised_count'],2)
        self.assertEqual(result['unresolved_count'],2)
        self.assertEqual(sum(r['count'] for r in result['categories']),2)
        self.assertEqual(result['categories'][-1]['cumulative_percent'],100)
        self.assertEqual({r['name'] for r in result['priority_records']},{'one','two'})

    def test_80_crossing_ties_and_priority_beyond_top10(self):
        from .monthly_tmm_assurance import category_counts
        from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS
        result=category_counts([dict(name=str(i),failure_classification=c) for i,c in enumerate(INITIAL_CLASSIFICATIONS)])
        self.assertEqual([r['category'] for r in result['categories']],[*INITIAL_CLASSIFICATIONS])
        self.assertEqual(result['priority_category_count'],16)
        self.assertEqual(result['categories'][15]['priority'],True)
        self.assertEqual(result['categories'][16]['priority'],False)
        self.assertEqual(result['displayed_count'],10)
        self.assertEqual(result['omitted_count'],10)
        self.assertEqual(result['categories'][9]['cumulative_percent'],50.0)
        self.assertEqual(len(result['priority_records']),16)
        self.assertEqual(category_counts([])['priority_records'],[])


class TestCaptureController(unittest.TestCase):
    def test_optional_classification_keeps_signature_permissions(self):
        from unittest.mock import patch
        import frappe
        from engineering.engineering.doctype.plant_breakdown_or_maintenance.plant_breakdown_or_maintenance import PlantBreakdownorMaintenance
        doc=object.__new__(PlantBreakdownorMaintenance)
        doc.__dict__.update(doctype='Plant Breakdown or Maintenance',downtime_type='Breakdown',failure_classification='',flags=frappe._dict())
        with patch.object(doc,'enforce_signature_role_permissions') as signatures:
            doc.validate()
            doc.failure_classification='Safety Systems'
            doc.validate()
            self.assertEqual(signatures.call_count,2)


class TestMonthlyPopulation(unittest.TestCase):
    def test_overlapping_calendar_month_counts_carried_and_closed_records_once(self):
        from .monthly_tmm_assurance import monthly_population
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
        from .monthly_tmm_assurance import monthly_population
        row=dict(name='same-record',breakdown_start_datetime='2026-11-28 12:00:00',resolved_datetime='2027-02-01 00:00:00')
        for month in ['2026-11-01','2026-12-01','2027-01-01']:
            self.assertEqual([r['name'] for r in monthly_population([row,row],month)],['same-record'])
        self.assertEqual(monthly_population([row],'2027-02-01'),[])



class TestCountPresentation(unittest.TestCase):
    def test_top10_stops_below100_and_80_reference_and_priority_are_visible(self):
        from .monthly_tmm_assurance import category_counts
        from .monthly_tmm_assurance import count_chart_image, count_summary
        from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS
        result=category_counts([dict(name=str(i),failure_classification=c) for i,c in enumerate(INITIAL_CLASSIFICATIONS)])
        html=count_chart_image(result)
        svg=base64.b64decode(html.split('base64,')[1].split('"')[0]).decode()
        self.assertIn('80% reference',svg)
        self.assertIn('50.0%',svg)
        self.assertNotIn('>100.0%</text>',svg)
        self.assertIn('Number of breakdown records',svg)
        self.assertIn('16 categories account for 80.0%',count_summary(result))


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
             patch.object(capture.frappe,'db',SimpleNamespace(commit=MagicMock(), exists=lambda *args: True)):
            capture.create_breakdown_from_log(log,failure_classification='Safety Systems')
        doc.insert.assert_called_once_with()
        self.assertEqual(doc.failure_classification,'Safety Systems')
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
