"""Initialise new configuration fields once, preserving configured master data.

No PBM records, captured descriptions, actions or existing Settings are rewritten.
"""
import frappe
from engineering.controllers.failure_classification import MASTER_DOCTYPE, clear_configuration_cache
from engineering.patches.failure_classification_seed import seed_documents


def execute():
    frappe.reload_doc('engineering', 'doctype', 'breakdown_classification_rule')
    frappe.reload_doc('engineering', 'doctype', 'breakdown_failure_classification')
    for original in seed_documents():
        name = original['classification_name']
        # A deleted/renamed master is an administrator decision; do not recreate it.
        if not frappe.db.exists(MASTER_DOCTYPE, name):
            continue
        doc = frappe.get_doc(MASTER_DOCTYPE, name)
        fresh = (int(doc.get('display_order') or 1000) == 1000
                 and not doc.get('matching_rules') and not doc.get('legacy_aliases')
                 and not doc.get('is_tyre_related'))
        if not fresh:
            continue
        for field in ('display_order', 'is_tyre_related', 'legacy_aliases'):
            doc.set(field, original.get(field))
        for row in original.get('matching_rules', []):
            doc.append('matching_rules', row)
        doc.save(ignore_permissions=True)
    clear_configuration_cache()
