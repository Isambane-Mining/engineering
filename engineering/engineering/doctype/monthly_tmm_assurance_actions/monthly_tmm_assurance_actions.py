"""One action set per immutable site / completed month / equipment group."""
import hashlib
import json
import frappe
from frappe.model.document import Document
from frappe.utils import getdate, nowdate
from engineering.engineering.page.monthly_tmm_assurance.calculations import GROUPS, reporting_period, equipment_group
from engineering.engineering.problem_categories import PROBLEM_CATEGORIES


def scope_name(site, month, group):
    identity = json.dumps([site, str(month), group], separators=(',', ':'))
    return 'TMM-' + hashlib.sha256(identity.encode()).hexdigest()[:32]


class MonthlyTMMAssuranceActions(Document):
    def autoname(self):
        self.name = scope_name(self.site, self.reporting_month, self.equipment_group)

    def validate(self):
        try:
            period = reporting_period(str(self.reporting_month), today=getdate(nowdate()))
        except (ValueError, TypeError) as exc:
            frappe.throw(str(exc))
        self.reporting_month = period['reporting_month']
        if self.equipment_group not in GROUPS:
            frappe.throw('Invalid Equipment Group.')
        if self.name and self.name != scope_name(self.site, self.reporting_month, self.equipment_group):
            frappe.throw('Site, Reporting Month and Equipment Group cannot be changed. Open the correct monthly scope.')
        # Protect direct Desk/REST saves as well as the Page API. No permission bypass.
        frappe.get_doc('Location', self.site).check_permission('read')
        self.check_permission('create' if self.is_new() else 'write')
        if len(self.actions) > 200:
            frappe.throw('At most 200 actions are allowed per group.')
        previous = self.get_doc_before_save()
        old_rows = {row.name: row for row in previous.actions} if previous else {}
        for row in self.actions:
            old = old_rows.get(row.name)
            if row.cause not in PROBLEM_CATEGORIES and not (old and old.cause == row.cause):
                frappe.throw(f'Row {row.idx}: Choose a controlled Problem Category. Unchanged historical action categories may be retained.')
            if row.get('breakdown_reference'):
                breakdown = frappe.get_doc('Plant Breakdown or Maintenance', row.breakdown_reference)
                breakdown.check_permission('read')
                category = breakdown.asset_category
                if not category and breakdown.asset_name:
                    asset = frappe.get_doc('Asset', breakdown.asset_name)
                    asset.check_permission('read')
                    category = asset.asset_category
                if breakdown.location != self.site or equipment_group(category) != self.equipment_group:
                    frappe.throw(f'Row {row.idx}: Breakdown Reference must belong to this Site and Equipment Group.')
            for field in ('cause', 'action', 'owner_name', 'due_date', 'status'):
                if not str(row.get(field) or '').strip():
                    frappe.throw(f'Row {row.idx}: {field.replace("_", " ").title()} is required.')
            if row.status not in ('Open', 'In progress', 'Completed'):
                frappe.throw(f'Row {row.idx}: Invalid status.')
            getdate(row.due_date)
