"""Align configurable search categories without classifying any ERP records."""
import frappe
from engineering.engineering.doctype.machine_reliability_settings.machine_reliability_settings import DEFAULT_CATEGORIES, PROBLEM_CATEGORIES
from engineering.engineering.page.machine_reliability.calculations import terms


def update_categories(settings):
    current = [dict(category=x.category, keywords=x.keywords, test_sections=x.test_sections or '') for x in settings.categories]
    by_name = {x['category']: x for x in current}
    retired = [x for x in current if x['category'] not in PROBLEM_CATEGORIES]
    updated = []
    for category, keywords, sections in DEFAULT_CATEGORIES:
        original = by_name.get(category)
        words = terms(original['keywords'] if original else keywords)
        tests = (original['test_sections'] if original else sections).splitlines()
        if category == 'Other':
            for row in retired:
                words.extend(terms(row['keywords']))
                tests.extend(row['test_sections'].splitlines())
        updated.append(dict(category=category, keywords='\n'.join(dict.fromkeys(words)),
                            test_sections='\n'.join(dict.fromkeys(s.strip() for s in tests if s.strip()))))
    if updated == current:
        return False
    settings.set('categories', updated)
    return True


def execute():
    settings = frappe.get_doc('Machine Reliability Settings')
    if update_categories(settings):
        settings.save(ignore_permissions=True)
