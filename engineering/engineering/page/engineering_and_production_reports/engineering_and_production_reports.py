"""Desk endpoints for the central saved-report interface."""
import re
import frappe
from engineering.reporting import service, rendering
from engineering.reporting.registry import REPORT_TYPES


@frappe.whitelist()
def get_report_types():
    return service.metadata()


@frappe.whitelist()
def search_reports(report_type, site=None, report_date=None, shift=None, hour_slot=None, start=0):
    return service.search(report_type, site, report_date, shift, hour_slot, start)


@frappe.whitelist()
def view_report(report_type, name):
    return {'html': rendering.render(service.get_report(report_type, name))}


@frappe.whitelist()
def download_pdf(report_type, name):
    model = service.get_report(report_type, name, for_pdf=True)
    content = REPORT_TYPES[report_type]['pdf_handler'](model)
    filename = '_'.join(str(model.get(field) or '') for field in ('title', 'site', 'report_date', 'shift', 'hour_slot'))
    frappe.local.response.filename = re.sub(r'[^\w.\-]+', '_', filename).strip('_') + '.pdf'
    frappe.local.response.filecontent = content
    frappe.local.response.type = 'download'
