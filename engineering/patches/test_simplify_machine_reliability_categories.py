import unittest
import frappe
from engineering.patches.simplify_machine_reliability_categories import update_categories
from engineering.engineering.doctype.machine_reliability_settings.machine_reliability_settings import PROBLEM_CATEGORIES


class TestCategorySettingsMigration(unittest.TestCase):
    def test_preserves_edited_keywords_and_merges_retired_categories(self):
        settings = frappe.get_doc(dict(doctype='Machine Reliability Settings', categories=[
            dict(category='Brakes', keywords='custom brake phrase', test_sections='Brake Test'),
            dict(category='Oil Leaks / Lubrication', keywords='custom oil phrase', test_sections='Wearcheck'),
            dict(category='Safety / PDS', keywords='custom safety phrase', test_sections='PDS')]))
        self.assertTrue(update_categories(settings))
        self.assertEqual([x.category for x in settings.categories], list(PROBLEM_CATEGORIES))
        mapped = {x.category: x for x in settings.categories}
        self.assertEqual(mapped['Brakes'].keywords, 'custom brake phrase')
        self.assertIn('steering', mapped['Steering'].keywords)
        self.assertIn('custom oil phrase', mapped['Other'].keywords)
        self.assertIn('custom safety phrase', mapped['Other'].keywords)
        self.assertIn('Wearcheck', mapped['Other'].test_sections)
        self.assertIn('PDS', mapped['Other'].test_sections)
        self.assertFalse(update_categories(settings))

    def test_unknown_custom_category_keywords_are_preserved_in_other(self):
        settings = frappe.get_doc(dict(doctype='Machine Reliability Settings', categories=[
            dict(category='Custom old category', keywords='special fault', test_sections='')]))
        update_categories(settings)
        self.assertIn('special fault', settings.categories[-1].keywords)

    def test_merging_full_keyword_lists_does_not_reject_or_drop_terms(self):
        settings = frappe.get_doc(dict(doctype='Machine Reliability Settings', categories=[
            dict(category=label, keywords='\n'.join(f'{prefix} fault {i}' for i in range(100)), test_sections='')
            for label, prefix in [('Oil Leaks / Lubrication', 'oil'), ('Safety / PDS', 'safety')]]))
        update_categories(settings)
        settings.validate()
        other = settings.categories[-1].keywords.splitlines()
        self.assertTrue(all(f'oil fault {i}' in other and f'safety fault {i}' in other for i in range(100)))
