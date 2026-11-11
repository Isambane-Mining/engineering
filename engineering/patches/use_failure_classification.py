"""Migrate report configuration only; retain retired columns and all source records."""
import frappe
from engineering.controllers.failure_classification import MASTER_DOCTYPE, prepare_settings
from engineering.patches.failure_classification_seed import INITIAL_CLASSIFICATIONS, seed_legacy_aliases


def migrate_settings():
    for label in INITIAL_CLASSIFICATIONS:
        if not frappe.db.exists(MASTER_DOCTYPE, label):
            frappe.get_doc(dict(doctype=MASTER_DOCTYPE, classification_name=label)).insert(ignore_permissions=True)
    names = frappe.get_all(MASTER_DOCTYPE, pluck='name', order_by='name', limit_page_length=0)
    settings = frappe.get_doc('Machine Reliability Settings')
    rows = prepare_settings(settings.categories, names, legacy_aliases=seed_legacy_aliases())
    settings.set('categories', [])
    for row in rows:
        settings.append('categories', row)
    settings.save(ignore_permissions=True)
    return settings


def execute():
    migrate_settings()
    # Frappe model sync removes the standard DocField definitions, keeping their
    # physical database columns. Remove only obsolete custom metadata as well.
    retired = ['problem_category', 'problem_subcategory']
    for name in frappe.get_all('Custom Field', filters={
        'dt': 'Plant Breakdown or Maintenance', 'fieldname': ['in', retired]}, pluck='name'):
        frappe.delete_doc('Custom Field', name, ignore_permissions=True)
    frappe.db.delete('Property Setter', {
        'doc_type': 'Plant Breakdown or Maintenance', 'field_name': ['in', retired]})
    frappe.clear_cache(doctype='Plant Breakdown or Maintenance')
