"""Exercise the migration against an in-memory store; no active LAB schema changes."""

from engineering.patches.failure_classification_seed import INITIAL_CLASSIFICATIONS as TEST_CLASSIFICATIONS, seed_configuration
TEST_CONFIGURATION = seed_configuration()
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import frappe
from engineering.controllers.failure_classification import MASTER_DOCTYPE
from engineering.patches import use_failure_classification as migration


class Settings:
    def __init__(self):
        self.categories=[frappe._dict(category='Brakes',keywords='custom brake phrase',test_sections='Brake Test'),
                         frappe._dict(category='Other',keywords='custom uncertain phrase',test_sections='Wearcheck')]
    def set(self,field,value):setattr(self,field,value)
    def append(self,field,row):getattr(self,field).append(frappe._dict(row))
    def save(self,**kwargs):return self


class TestMigration(unittest.TestCase):
    def test_master_seed_settings_mapping_idempotence_and_metadata_only_cleanup(self):
        masters={'Custom master'}
        settings=Settings()
        deleted=[]
        def get_doc(doctype):
            if isinstance(doctype,str):
                self.assertEqual(doctype,'Machine Reliability Settings')
                return settings
            self.assertEqual(doctype['doctype'],MASTER_DOCTYPE)
            def insert(**kwargs):masters.add(doctype['classification_name'])
            return SimpleNamespace(insert=insert)
        def get_all(doctype,**kwargs):
            if doctype==MASTER_DOCTYPE:return sorted(masters)
            self.assertEqual(doctype,'Custom Field')
            return []
        def delete(doctype,filters):
            self.assertEqual(doctype,'Property Setter')
            deleted.append(filters)
        db=SimpleNamespace(exists=lambda doctype,label:label in masters,delete=delete)
        with patch.object(frappe,'db',db),patch.object(frappe,'get_doc',side_effect=get_doc),patch.object(frappe,'get_all',side_effect=get_all),patch.object(frappe,'clear_cache'):
            migration.execute()
            first=[dict(x) for x in settings.categories]
            migration.execute()
        self.assertEqual(masters,set(TEST_CLASSIFICATIONS)|{'Custom master'})
        self.assertEqual(first,[dict(x) for x in settings.categories])
        self.assertEqual(len([x for x in first if x['category']]),21)
        self.assertEqual(next(x for x in first if x['category']=='Braking System')['keywords'],'custom brake phrase')
        self.assertEqual(first[-1]['legacy_category'],'Other')
        self.assertEqual(first[-1]['test_sections'],'Wearcheck')
        self.assertEqual(len(deleted),2)
