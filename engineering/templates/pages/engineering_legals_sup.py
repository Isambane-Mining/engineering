import frappe
from frappe import _
from erpnext.controllers.website_list_for_contact import get_customers_suppliers
from engineering.controllers.engineering_legals_rules import supplier_sites


def _get_draft_name():
    draft_name = (frappe.form_dict.get("draft_name") or "").strip()

    if not draft_name and getattr(frappe.request, "args", None):
        draft_name = (frappe.request.args.get("draft_name") or "").strip()

    return draft_name


def _get_editable_draft():
    draft_name = _get_draft_name()
    if not draft_name:
        return None

    draft = frappe.get_doc("Engineering Legals supplier Portal Draft", draft_name)

    if draft.portal_user != frappe.session.user:
        frappe.throw(_("You can only edit your own draft."), frappe.PermissionError)

    if draft.sent_to_erp:
        frappe.throw(_("Submitted records cannot be edited."), frappe.PermissionError)

    return draft



def get_context(context):
    context.no_cache = 1
    context.show_sidebar = True
    context.title = "Engineering Legals"

    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/engineering_legals_sup"
        raise frappe.Redirect

    if "Supplier" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Not permitted."), frappe.PermissionError)

    if frappe.request.method == "POST":
        _handle_post(context)

    context.sections_options = _get_sections_options()
    context.asset_options = _get_asset_options()
    context.site_options = supplier_sites()

    draft = _get_editable_draft() if frappe.request.method != "POST" else None

    context.form_values = {
        "draft_name": frappe.form_dict.get("draft_name") or (draft.name if draft else ""),
        "sections": frappe.form_dict.get("sections") or (draft.sections if draft else ""),
        "site": frappe.form_dict.get("site") or (draft.site if draft else ""),
        "fleet_number": frappe.form_dict.get("fleet_number") or (draft.fleet_number if draft else ""),
        "vehicle_type": frappe.form_dict.get("vehicle_type") or (draft.vehicle_type if draft else ""),
        "lifting_type": frappe.form_dict.get("lifting_type") or (draft.lifting_type if draft else ""),
        "brake_wear_type": frappe.form_dict.get("brake_wear_type") or (getattr(draft, "brake_wear_type", "") if draft else ""),
        "attach_paper": frappe.form_dict.get("attach_paper") or (draft.attach_paper if draft else ""),
        "start_date": frappe.form_dict.get("start_date") or (draft.start_date if draft else ""),
        "expiry_date": frappe.form_dict.get("expiry_date") or (draft.expiry_date if draft else ""),
    }


def _handle_post(context):
    sections = (frappe.form_dict.get("sections") or "").strip()
    site = (frappe.form_dict.get("site") or "").strip()
    fleet_number = (frappe.form_dict.get("fleet_number") or "").strip()
    vehicle_type = (frappe.form_dict.get("vehicle_type") or "").strip()
    lifting_type = (frappe.form_dict.get("lifting_type") or "").strip()
    attach_paper = (frappe.form_dict.get("attach_paper") or "").strip()
    start_date = (frappe.form_dict.get("start_date") or "").strip()

    if not sections:
        frappe.throw(_("Section is required."))
    if not site:
        frappe.throw(_("Site is required."))
    if not attach_paper:
        frappe.throw(_("Attach Paper is required."))

    file_name = frappe.db.get_value("File", {"file_url": attach_paper}, "name")
    if not file_name:
        frappe.throw(_("Attachment is still uploading. Please wait a few seconds and submit again."))

    draft_name = _get_draft_name()

    if draft_name:
        doc = frappe.get_doc("Engineering Legals supplier Portal Draft", draft_name)

        if doc.portal_user != frappe.session.user:
            frappe.throw(_("You can only edit your own draft."), frappe.PermissionError)

        if doc.sent_to_erp:
            frappe.throw(_("Submitted records cannot be edited."), frappe.PermissionError)
    else:
        doc = frappe.get_doc(
            {
                "doctype": "Engineering Legals supplier Portal Draft",
                "portal_user": frappe.session.user,
                "sent_to_erp": 0,
            }
        )

    doc.sections = sections
    doc.site = site
    doc.fleet_number = fleet_number
    doc.vehicle_type = vehicle_type or None
    doc.lifting_type = lifting_type or None
    doc.brake_wear_type = (frappe.form_dict.get("brake_wear_type") or "").strip() or None
    doc.attach_paper = attach_paper
    doc.start_date = start_date
    # The draft controller calculates expiry; never trust the browser's preview.

    if draft_name:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)

    frappe.local.flags.redirect_location = "/engineering_legals_list"
    raise frappe.Redirect







def _get_user_suppliers():
    customers, suppliers = get_customers_suppliers(
        "Request for Quotation Supplier",
        frappe.session.user
    )
    return suppliers or []


def _get_supplier_asset_filters():
    suppliers = _get_user_suppliers()
    if not suppliers:
        return None

    return {
        "asset_owner": "Supplier",
        "supplier": ["in", suppliers],
    }


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


def _get_asset_options():
    filters = _get_supplier_asset_filters()
    if not filters:
        return []

    return frappe.get_all(
        "Asset",
        filters=filters,
        pluck="name",
        order_by="name asc",
        limit_page_length=0,
    )




def _get_sections_options():
    return frappe.get_all(
        "Engineering Legals Sections",
        pluck="name",
        order_by="name asc",
        limit_page_length=0,
    )


