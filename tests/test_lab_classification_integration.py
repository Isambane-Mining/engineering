"""Classification regressions for the newer LAB features; no ERP writes."""
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from datetime import datetime
import frappe


class TestCombinedClassification(unittest.TestCase):
    def test_tmm_counts_link_values_and_keeps_missing_classification_visible(self):
        from engineering.engineering.page.monthly_tmm_assurance.monthly_tmm_assurance import category_counts
        rows=[dict(name='one',failure_classification='Hydraulic'),dict(name='one',failure_classification='Hydraulic'),
              dict(name='two',failure_classification='Braking System'),dict(name='blank',failure_classification='')]
        result=category_counts(rows)
        self.assertEqual(result['categorised_count'],2)
        self.assertEqual(result['unresolved_count'],1)
        self.assertEqual(sum(x['count'] for x in result['categories']),2)

    def test_tmm_export_displays_link_classification(self):
        from engineering.engineering.page.monthly_tmm_assurance.monthly_tmm_assurance import record_table
        html=record_table([dict(name='one',failure_classification='Steering System')])
        self.assertIn('Steering System',html)

    def test_whatsapp_uses_optional_explicit_link_without_inference(self):
        from engineering.engineering.doctype.whatsapp_breakdown_message_log import whatsapp_breakdown_message_log as capture
        log=frappe._dict(target_site='Koppie',target_shift='Day Shift',detected_plant_no='TEST',
                        detected_reason='Rim cracked',raw_message='',detected_hours=100)
        log.save=MagicMock()
        for classification in [None,'Tyres / Wheels']:
            doc=SimpleNamespace(name='test-ref',insert=MagicMock())
            with patch.object(capture,'combine_date_and_time',return_value=datetime(2026,9,15,8)),patch.object(frappe,'new_doc',return_value=doc),patch.object(frappe,'db',SimpleNamespace(commit=MagicMock(),exists=lambda *args:True)):
                capture.create_breakdown_from_log(log,failure_classification=classification)
            self.assertEqual(doc.failure_classification,classification or '')
            self.assertEqual(doc.breakdown_reason,'Rim cracked')
            doc.insert.assert_called_once_with()
