import frappe
from frappe.desk import reportview


@frappe.whitelist()
@frappe.read_only()
def export_query():
    # Frappe v16.50.0 bug: Report View sends with_link_titles, which
    # DatabaseQuery.execute() rejects. Remove once fixed upstream.
    frappe.form_dict.pop("with_link_titles", None)
    return reportview.export_query()
