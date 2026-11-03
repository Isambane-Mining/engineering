import json
import frappe
from frappe import _
from erpnext.controllers.website_list_for_contact import get_customers_suppliers
from engineering.controllers.engineering_legals_rules import authorize_capture


def get_context(context):
    context.no_cache = 1
    context.show_sidebar = True
    context.title = "My Engineering Legals"

    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/engineering_legals_list"
        raise frappe.Redirect

    if "Supplier" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Not permitted."), frappe.PermissionError)

    context.records = frappe.get_all(
        "Engineering Legals supplier Portal Draft",
        filters={"portal_user": frappe.session.user},
        fields=[
            "name",
            "sections",
            "site",
            "fleet_number",
            "start_date",
            "expiry_date",
            "sent_to_erp",
            "erp_document",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=100,
    )

    for row in context.records:
        row.status = "Submitted" if row.sent_to_erp else "Draft"
        row.open_route = ""





def _get_user_suppliers():
    customers, suppliers = get_customers_suppliers(
        "Request for Quotation Supplier",
        frappe.session.user
    )
    return suppliers or []


def _validate_supplier_asset_access(asset_name):
    suppliers = _get_user_suppliers()
    if not suppliers:
        frappe.throw(_("Your user is not linked to a Supplier."))

    if not frappe.db.exists("Asset", {
        "name": asset_name,
        "asset_owner": "Supplier",
        "supplier": ["in", suppliers],
    }):
        frappe.throw(_("This asset is not linked to your supplier access."), frappe.PermissionError)




@frappe.whitelist(allow_guest=False)
def send_engineering_legals():
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in first."))

    if "Supplier" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Not permitted."), frappe.PermissionError)

    names = frappe.form_dict.get("names")

    if isinstance(names, str):
        try:
            names = json.loads(names)
        except Exception:
            names = [names]

    if not names:
        frappe.throw(_("No records selected."))

    sent = []

    for name in names:
        draft = frappe.get_doc("Engineering Legals supplier Portal Draft", name)

        if draft.portal_user != frappe.session.user:
            frappe.throw(_("You can only send your own records."), frappe.PermissionError)

        if draft.sent_to_erp:
            continue

        authorize_capture(draft)

        erp_doc = frappe.get_doc({
            "doctype": "Engineering Legals",
            "sections": draft.sections,
            "site": draft.site,
            "fleet_number": draft.fleet_number,
            "vehicle_type": draft.vehicle_type,
            "lifting_type": draft.lifting_type,
            "brake_wear_type": getattr(draft, "brake_wear_type", None),
            "attach_paper": draft.attach_paper,
            "start_date": draft.start_date,
        })
        erp_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        draft.db_set("sent_to_erp", 1)
        draft.db_set("sent_on", frappe.utils.now())
        draft.db_set("erp_document", erp_doc.name)

        sent.append({"draft": draft.name, "erp_document": erp_doc.name})

    return {"ok": True, "sent": sent}
