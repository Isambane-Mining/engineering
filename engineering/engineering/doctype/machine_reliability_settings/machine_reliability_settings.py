import frappe
from frappe.model.document import Document
from engineering.controllers.failure_classification import MASTER_DOCTYPE, AMBIGUOUS_TERMS, terms


class MachineReliabilitySettings(Document):
    def validate(self):
        seen = set()
        for row in self.categories:
            label = (row.category or '').strip()
            if not label:
                if not row.legacy_category:
                    frappe.throw('Select a Failure Classification for each configuration row.')
                row.mapping_warning = 'Unmapped legacy settings. Review before using; excluded from matching.'
                continue
            if label in seen or not frappe.db.exists(MASTER_DOCTYPE, label):
                frappe.throw('Failure Classifications must be existing, unique master records.')
            seen.add(label)
            words = terms(row.keywords)
            if any(len(w) > 100 for w in words):
                frappe.throw('Use keyword phrases of 100 characters or fewer.')
            if set(words) & AMBIGUOUS_TERMS:
                frappe.throw('Use component-specific phrases instead of standalone pump, hose or leak.')
            row.category, row.keywords = label, '\n'.join(words)
            row.legacy_category, row.mapping_warning = '', ''
            for section in (row.test_sections or '').splitlines():
                section = section.strip()
                if section and (section == 'Machine Service Records' or not frappe.db.exists('Engineering Legals Sections', section)):
                    frappe.throw('Choose existing test / inspection sections; services are counted separately.')
