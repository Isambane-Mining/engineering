"""Offline classification contract; no source records are written."""
import json
from pathlib import Path
import unittest
from engineering.controllers import tyre_damage
from engineering.engineering.page.machine_reliability import machine_reliability as reliability

ROOT = Path(__file__).resolve().parents[1]


class TestFailureClassificationContract(unittest.TestCase):
    def test_tyre_count_uses_existing_link_and_accepts_wheel_components(self):
        for reason in ('rim cracked', 'wheel stud broken', 'wheel bearing failed', 'routine description'):
            self.assertTrue(tyre_damage.is_classified_tyre_damage(
                dict(failure_classification='Tyres / Wheels', breakdown_reason=reason)))
        self.assertFalse(tyre_damage.is_classified_tyre_damage(dict(breakdown_reason='flat tyre')))

    def test_explicit_classification_cannot_be_overridden_by_extra_reason_keywords(self):
        record = dict(failure_classification='Engine', breakdown_reason='brakes and starter failed')
        match, _, _ = reliability.classify_record(record, ['brakes','starter'], 'Braking System', ['starter'])
        self.assertIsNone(match)
        record['resolution_summary'] = 'brakes repaired'
        self.assertEqual(reliability.classify_record(record, ['brakes'], 'Braking System')[0], 'additional')

    def test_blank_keyword_classification_does_not_match_every_historical_record(self):
        self.assertIsNone(reliability.classify_record({}, [], 'Mechanical')[0])
        self.assertEqual(reliability.classify_record(dict(failure_classification='Mechanical'), [], 'Mechanical')[0], 'direct')

    def test_schema_removes_retired_fields_but_keeps_link(self):
        schema=json.loads((ROOT/'engineering/engineering/doctype/plant_breakdown_or_maintenance/plant_breakdown_or_maintenance.json').read_text())
        names={f['fieldname'] for f in schema['fields']}
        for retired in ('problem_category','problem_subcategory'):
            self.assertNotIn(retired,names)
            self.assertNotIn(retired,schema['field_order'])
        field=next(f for f in schema['fields'] if f['fieldname']=='failure_classification')
        self.assertEqual(field['options'],'Breakdown Failure Classification')
        self.assertFalse(field.get('reqd'))

    def test_dozer_keeps_average_cards_without_tyre_card(self):
        from engineering.engineering.page.daily_availability_and_utilization_dashboard.tyre_damage import au_kpi_row,tyre_damage_card
        self.assertEqual(tyre_damage_card('Dozer',8),'')
        html=au_kpi_row('Dozer',dict(avail=82,util=58),8)
        self.assertIn('Dozer Average Availability',html)
        self.assertIn('Dozer Average Utilisation',html)
        self.assertNotIn('daily-tyre-kpi',html)


class TestClassificationSettings(unittest.TestCase):
    def test_all_twenty_are_supported_without_pdf_keyword_invention(self):
        from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS,prepare_settings
        result=prepare_settings([],INITIAL_CLASSIFICATIONS)
        self.assertEqual(len(result),20)
        self.assertEqual({x['category'] for x in result},set(INITIAL_CLASSIFICATIONS))
        self.assertTrue(all(not x['keywords'] and not x['test_sections'] for x in result))

    def test_preserves_custom_terms_inspection_links_and_flags_ambiguous_mapping(self):
        from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS,prepare_settings
        rows=[dict(category='Brakes',keywords='brake, custom pedal fault',test_sections='Brake Test'),
              dict(category='Braking System',keywords='brake, retarder failure',test_sections='Brake Wear Measurements'),
              dict(category='Other',keywords='custom ambiguous term',test_sections='Wearcheck\nPDS')]
        result=prepare_settings(rows,INITIAL_CLASSIFICATIONS)
        brakes=next(x for x in result if x['category']=='Braking System')
        self.assertEqual(brakes['keywords'].splitlines(),['brake','custom pedal fault','retarder failure'])
        self.assertEqual(brakes['test_sections'],'Brake Test\nBrake Wear Measurements')
        unresolved=result[-1]
        self.assertIsNone(unresolved['category'])
        self.assertEqual(unresolved['legacy_category'],'Other')
        self.assertEqual(unresolved['keywords'],'custom ambiguous term')
        self.assertEqual(unresolved['test_sections'],'Wearcheck\nPDS')
        self.assertIn('Review',unresolved['mapping_warning'])
        self.assertEqual(prepare_settings(result,INITIAL_CLASSIFICATIONS),result)

    def test_ambiguous_existing_keywords_and_same_named_other_master_stay_inactive(self):
        from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS,prepare_settings
        names=INITIAL_CLASSIFICATIONS+('Other',)
        rows=[dict(category='Other',keywords='oil leak',test_sections='Wearcheck'),
              dict(category='Hydraulics',keywords='hydraulic cylinder, pump, hose, leak',test_sections='')]
        result=prepare_settings(rows,names)
        pending=[x for x in result if not x['category']]
        self.assertEqual(len(pending),2)
        self.assertEqual(pending[1]['keywords'],rows[1]['keywords'])
        self.assertEqual(next(x for x in result if x['category']=='Hydraulic')['keywords'],'')
        self.assertEqual(next(x for x in result if x['category']=='Other')['keywords'],'')
        self.assertEqual(prepare_settings(result,names),result)
        # Even creating an exact legacy name does not silently resolve a review row.
        self.assertTrue(any(x.get('legacy_category')=='Hydraulics' for x in prepare_settings(result,names+('Hydraulics',))))

    def test_settings_accept_all_master_records_and_blank_keywords(self):
        import frappe
        from types import SimpleNamespace
        from unittest.mock import patch
        from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS,prepare_settings
        from engineering.engineering.doctype.machine_reliability_settings.machine_reliability_settings import MachineReliabilitySettings
        settings=SimpleNamespace(categories=[frappe._dict(x) for x in prepare_settings([],INITIAL_CLASSIFICATIONS)])
        with patch.object(frappe,'db',SimpleNamespace(exists=lambda *args:True)):
            MachineReliabilitySettings.validate(settings)
            # Newly added master records also work; validation does not enforce a fixed list.
            settings.categories.append(frappe._dict(category='New controlled class',keywords='',test_sections=''))
            MachineReliabilitySettings.validate(settings)

    def test_standalone_ambiguous_words_and_duplicate_classifications_are_rejected(self):
        import frappe
        from types import SimpleNamespace
        from unittest.mock import patch
        from engineering.engineering.doctype.machine_reliability_settings.machine_reliability_settings import MachineReliabilitySettings
        def throw(message,*args,**kwargs):raise frappe.ValidationError(message)
        for keywords in ['pump','hose','leak']:
            settings=SimpleNamespace(categories=[frappe._dict(category='Hydraulic',keywords=keywords)])
            with patch.object(frappe,'db',SimpleNamespace(exists=lambda *args:True)),patch.object(frappe,'throw',side_effect=throw):
                with self.assertRaises(frappe.ValidationError):MachineReliabilitySettings.validate(settings)
        settings=SimpleNamespace(categories=[frappe._dict(category='Engine',keywords='',test_sections='') for _ in range(2)])
        with patch.object(frappe,'db',SimpleNamespace(exists=lambda *args:True)),patch.object(frappe,'throw',side_effect=throw):
            with self.assertRaises(frappe.ValidationError):MachineReliabilitySettings.validate(settings)

    def test_categories_follow_master_and_omit_unmapped_keywords(self):
        import frappe
        from unittest.mock import patch
        from types import SimpleNamespace
        from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS,prepare_settings
        rows=prepare_settings([dict(category='Brakes',keywords='custom brake phrase'),dict(category='Other',keywords='ambiguous')],INITIAL_CLASSIFICATIONS)
        settings=SimpleNamespace(categories=[frappe._dict(x) for x in rows])
        with patch.object(frappe,'get_cached_doc',return_value=settings),patch.object(frappe,'get_all',return_value=list(INITIAL_CLASSIFICATIONS)):
            result=reliability.categories()
            self.assertEqual(len(result),20)
            self.assertNotIn('Other',[x['category'] for x in result])
            self.assertEqual(next(x for x in result if x['category']=='Braking System')['keywords'],['custom brake phrase'])
            self.assertEqual(len(reliability.configuration_warnings()),1)


class TestReliabilityAPIContract(unittest.TestCase):
    def test_each_of_twenty_master_filters_uses_classification_without_keywords(self):
        import frappe
        from unittest.mock import patch
        from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS
        configured=[dict(category=name,keywords=[],test_sections=[]) for name in INITIAL_CLASSIFICATIONS]
        source=[frappe._dict(name=str(i),failure_classification=name,asset_name='IS1',location='Old Site',
                    downtime_type='Breakdown',breakdown_start_datetime='2026-08-01 08:00:00',resolved_datetime='2026-08-01 09:00:00',
                    hours_breakdown_starts=100,breakdown_reason='No keyword complaint') for i,name in enumerate(INITIAL_CLASSIFICATIONS)]
        with patch.object(reliability,'check_access',return_value=[]),patch.object(reliability,'categories',return_value=configured),patch.object(reliability,'configuration_warnings',return_value=[]),patch.object(reliability,'load_sources',return_value=(source,[],{})):
            for name in INITIAL_CLASSIFICATIONS:
                result=reliability.get_dashboard('2026-08-01','2026-08-31',category=name)
                self.assertEqual(result['summary']['direct_failures'],1)
                self.assertEqual(result['timeline'][0]['failure_classification'],name)

    def test_source_queries_request_only_existing_classification_and_enforce_record_permissions(self):
        import frappe
        from unittest.mock import patch
        def read(doctype,**kwargs):
            if doctype==reliability.PBM:
                self.assertIn('failure_classification',kwargs['fields'])
                self.assertIn(['docstatus','<',2],kwargs['filters'])
            return []
        with patch.object(frappe,'get_list',side_effect=read) as permission_read,patch.object(frappe,'get_all') as identity_read:
            reliability.load_sources(reliability.getdate('2026-08-01'),reliability.getdate('2026-08-31'),'Old Site',None,None,[])
            self.assertEqual(permission_read.call_count,2)
            identity_read.assert_not_called()

    def test_guest_and_missing_breakdown_permission_are_denied(self):
        import frappe
        from unittest.mock import patch
        def throw(message,exc=frappe.ValidationError):raise exc(message)
        with patch.object(frappe,'throw',side_effect=throw),patch.object(frappe,'session',frappe._dict(user='Guest')):
            with self.assertRaises(frappe.PermissionError):reliability.check_access()
        with patch.object(frappe,'throw',side_effect=throw),patch.object(frappe,'session',frappe._dict(user='operator')),patch.object(frappe,'has_permission',return_value=False):
            with self.assertRaises(frappe.PermissionError):reliability.check_access()
