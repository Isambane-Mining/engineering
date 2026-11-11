"""Configuration tests use custom names and do not require a Frappe site."""
import unittest
from unittest.mock import patch
from engineering.controllers import failure_classification as fc


class TestClassificationConfiguration(unittest.TestCase):
    def config(self, name='Custom electrics', rules=None, tyre=0):
        return fc.configuration_from_documents([dict(name=name, display_order=1,
            is_tyre_related=tyre, legacy_aliases='Old custom name', matching_rules=rules or [])])

    def rules(self):
        return [dict(rule_type='Spelling correction', match_text='batery', replacement='battery', enabled=1),
                dict(rule_type='Subcategory', match_text='battery faulty\nbattery fault', replacement='Battery problem', enabled=1)]

    def test_custom_name_and_spelling_are_data_driven(self):
        cfg=self.config(rules=self.rules())
        result=fc.standard_subcategory('BATERY faulty!', 'Custom electrics', {}, rule_config=cfg)
        self.assertEqual(result['subcategory'], 'Battery problem')

    def test_renamed_master_and_new_label_work_without_code_edits(self):
        cfg=self.config(name='Renamed category', rules=self.rules())
        cfg['subcategories']['Renamed category']={'New component label':['battery faulty']}
        self.assertEqual(fc.standard_subcategory('batery faulty','Renamed category',{},rule_config=cfg)['subcategory'],'New component label')
        self.assertEqual(fc.standard_subcategory('batery faulty','Deleted category',{},rule_config=cfg)['status'],'Review')

    def test_tyre_selection_uses_checkbox_not_name(self):
        cfg=self.config(name='Custom wheel faults',tyre=1)
        with patch.object(fc,'get_configuration',return_value=cfg):
            self.assertEqual(fc.get_tyre_classifications(),['Custom wheel faults'])
        self.assertEqual(self.config(tyre=0)['tyre_classifications'],[])

    def test_uninformative_text_stays_in_review(self):
        cfg=self.config(rules=self.rules())
        for reason in ['does not start','no power','oil leak']:
            self.assertEqual(fc.standard_subcategory(reason,'Custom electrics',{},rule_config=cfg)['status'],'Review')

    def test_approved_description_wins(self):
        rules=self.rules()+[dict(rule_type='Approved description',match_text='strange lamp issue',replacement='Approved lamp problem',enabled=1)]
        self.assertEqual(fc.standard_subcategory('Strange lamp issue','Custom electrics',{},rule_config=self.config(rules=rules))['status'],'Approved')

    def test_legacy_mapping_is_configurable_and_idempotent(self):
        cfg=self.config()
        rows=fc.prepare_settings([dict(category='Old custom name',keywords='specific phrase')],cfg['names'],legacy_aliases=cfg['legacy_aliases'])
        self.assertEqual(rows[0]['category'],'Custom electrics')
        self.assertEqual(fc.prepare_settings(rows,cfg['names'],legacy_aliases=cfg['legacy_aliases']),rows)

    def test_conflicting_subcategory_phrases_require_review(self):
        rules=self.rules()+[dict(rule_type='Subcategory',match_text='battery faulty',replacement='Different label',enabled=1)]
        self.assertEqual(fc.standard_subcategory('battery faulty','Custom electrics',{},rule_config=self.config(rules=rules))['status'],'Review')

    def test_disabled_rule_is_not_used(self):
        rules=[dict(rule_type='Subcategory',match_text='battery faulty',replacement='Disabled',enabled=0)]
        self.assertEqual(fc.standard_subcategory('battery faulty','Custom electrics',{},rule_config=self.config(rules=rules))['status'],'Review')

    def test_cross_category_conflict_requires_review(self):
        cfg=fc.configuration_from_documents([
            dict(name='Custom A',matching_rules=[dict(rule_type='Subcategory',match_text='battery faulty',replacement='Battery issue',enabled=1)]),
            dict(name='Custom B',matching_rules=[dict(rule_type='Subcategory',match_text='tyre puncture',replacement='Tyre issue',enabled=1)])])
        self.assertEqual(fc.standard_subcategory('battery faulty and tyre puncture','Custom A',{},rule_config=cfg)['status'],'Review')


if __name__=='__main__':
    unittest.main()
