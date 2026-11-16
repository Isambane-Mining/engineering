import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime


ALLOWED_SUPPLIER_SITES = ["Gwab", "Klipfontein"]

ACTION_STATUS_OPTIONS = ["Open", "Closed", "Cancelled"]

OPERATING_STATUS_OPTIONS = [
    "Off Site",
    "Parts Order",
    "Pending Incident report",
    "Go But 48 Hours",
    "Go But Plan ASP (WEEK)",
    "Working",
    "Repair within 24 hours",
    "Repair within 1 week",
    "Don't operate machine",
]


def get_context(context):
    context.no_cache = 1
    context.show_sidebar = False
    context.title = "Pre Use Deviation"
    context.base_template_path = "templates/base.html"

    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/pre_use_deviation_supplier"
        raise frappe.Redirect

    if not _get_user_suppliers():
        frappe.throw(_("Your user is not linked to a Supplier."), frappe.PermissionError)

    if getattr(frappe.local, "request", None) and frappe.local.request.method == "POST":
        _handle_post()

    doc = _get_doc_from_query()

    context.site_options = ALLOWED_SUPPLIER_SITES
    context.asset_options = _get_asset_options()
    context.asset_details = _get_asset_details(context.asset_options)
    context.action_status_options = ACTION_STATUS_OPTIONS
    context.operating_status_options = OPERATING_STATUS_OPTIONS

    try:
        context.csrf_token = frappe.sessions.get_csrf_token()
    except Exception:
        context.csrf_token = (
            getattr(frappe.session, "csrf_token", "")
            or getattr(getattr(frappe.local, "session", None), "csrf_token", "")
            or ""
        )

    context.form_values = {
        "name": doc.name if doc else "",
        "report_datetime": _format_datetime_for_input(doc.report_datetime) if doc else now_datetime().strftime("%d-%m-%Y %H:%M:%S"),
        "site": doc.site if doc else "",
        "fleet_number": doc.fleet_number if doc else "",
        "pre_use_no": doc.pre_use_no if doc else "",
        "recurring_deviation": doc.get("recurring_deviation") if doc else "",
        "machine_type": doc.machine_type if doc else "",
        "machine_model": doc.machine_model if doc else "",
        "operating_status": doc.operating_status if doc else "",
        "deviation_details": doc.deviation_details if doc else "",
        "reported_by_coy_number": doc.reported_by_coy_number if doc else "",
        "reported_by_name_and_surname": doc.reported_by_name_and_surname if doc else frappe.session.user,
        "resolution_summary": doc.resolution_summary if doc else "",
        "action": doc.get("action") if doc else "",
        "action_date_and_time": _format_datetime_for_input(doc.action_date_and_time) if doc and doc.action_date_and_time else "",
        "date_service_report_received": str(doc.get("date_service_report_received") or "") if doc else "",
        "actioned_by_coy_number": doc.actioned_by_coy_number if doc else "",
        "actioned_by_name_and_surname": doc.actioned_by_name_and_surname if doc else "",
        "job_card_number": doc.job_card_number if doc else "",
        "action_status": doc.action_status if doc else "Open",
        "completion_percentage": doc.completion_percentage if doc else 0,
    }

    return context


def _handle_post():
    name = frappe.form_dict.get("name")
    fleet_number = frappe.form_dict.get("fleet_number")

    if not fleet_number:
        frappe.throw(_("Fleet Number is required."))

    _validate_asset(fleet_number)

    # Use the location of an authorised supplier asset.
    asset_details = _get_asset_details(_get_asset_options())
    asset_site = (asset_details.get(fleet_number) or {}).get("site")

    if not asset_site:
        frappe.throw(
            _("Unable to determine the authorised machine site."),
            frappe.PermissionError,
        )

    submitted_site = frappe.form_dict.get("site") or ""

    if submitted_site and submitted_site != asset_site:
        frappe.throw(
            _("Selected Site does not match the machine location."),
            frappe.PermissionError,
        )

    if name:
        doc = frappe.get_doc("Pre Use Deviation", name)
        _validate_asset(doc.fleet_number)
    else:
        doc = frappe.new_doc("Pre Use Deviation")

    report_datetime = _parse_datetime(frappe.form_dict.get("report_datetime"))
    action_date_and_time = _parse_datetime(frappe.form_dict.get("action_date_and_time"))

    doc.report_datetime = report_datetime or now_datetime()
    doc.site = asset_site
    doc.fleet_number = fleet_number

    try:
        doc.pre_use_no = int(frappe.form_dict.get("pre_use_no") or 0)
    except Exception:
        doc.pre_use_no = 0

    doc.recurring_deviation = frappe.form_dict.get("recurring_deviation") or None
    doc.machine_type = frappe.form_dict.get("machine_type") or None
    doc.machine_model = frappe.form_dict.get("machine_model") or None
    doc.operating_status = frappe.form_dict.get("operating_status") or None
    doc.deviation_details = frappe.form_dict.get("deviation_details") or None

    reported_by_coy_number = frappe.form_dict.get("reported_by_coy_number") or None
    if reported_by_coy_number and not _link_value_exists("Employee", reported_by_coy_number):
        reported_by_coy_number = None

    doc.reported_by_coy_number = reported_by_coy_number
    doc.reported_by_name_and_surname = frappe.form_dict.get("reported_by_name_and_surname") or frappe.session.user
    doc.action = frappe.form_dict.get("action") or None
    doc.resolution_summary = frappe.form_dict.get("resolution_summary") or None
    doc.action_date_and_time = action_date_and_time

    service_date = (
        frappe.form_dict.get("date_service_report_received") or ""
    ).strip()

    if service_date:
        try:
            doc.date_service_report_received = getdate(service_date)
        except Exception:
            frappe.throw(_("Invalid Date Service Report Received."))
    else:
        doc.date_service_report_received = None

    actioned_by_coy_number = frappe.form_dict.get("actioned_by_coy_number") or None
    if actioned_by_coy_number and not _link_value_exists("Employee", actioned_by_coy_number):
        actioned_by_coy_number = None

    doc.actioned_by_coy_number = actioned_by_coy_number
    doc.actioned_by_name_and_surname = frappe.form_dict.get("actioned_by_name_and_surname") or None
    doc.job_card_number = frappe.form_dict.get("job_card_number") or None
    doc.action_status = frappe.form_dict.get("action_status") or "Open"

    try:
        doc.completion_percentage = int(frappe.form_dict.get("completion_percentage") or 0)
    except Exception:
        doc.completion_percentage = 0

    if not doc.site:
        asset_site = frappe.db.get_value("Asset", fleet_number, "location")
        doc.site = asset_site

    if not doc.machine_type:
        doc.machine_type = frappe.db.get_value("Asset", fleet_number, "asset_category")

    if not doc.machine_model:
        doc.machine_model = (
            frappe.db.get_value("Asset", fleet_number, "item_name")
            or frappe.db.get_value("Asset", fleet_number, "asset_name")
        )

    if doc.is_new():
        try:
            doc.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            frappe.db.rollback()
            frappe.msgprint(_("This Pre Use Deviation was already saved."))
            frappe.local.flags.redirect_location = "/pre_use_deviation_list"
            raise frappe.Redirect
    else:
        doc.save(ignore_permissions=True)

    frappe.db.commit()

    frappe.local.flags.redirect_location = "/pre_use_deviation_list"
    raise frappe.Redirect


def _get_doc_from_query():
    name = frappe.form_dict.get("name")

    if not name:
        return None

    if not frappe.db.exists("Pre Use Deviation", name):
        frappe.throw(_("Pre Use Deviation not found."), frappe.DoesNotExistError)

    doc = frappe.get_doc("Pre Use Deviation", name)
    _validate_asset(doc.fleet_number)

    return doc


def _get_user_suppliers():
    suppliers = frappe.get_all(
        "Portal User",
        filters={"user": frappe.session.user},
        pluck="parent",
        limit_page_length=0,
    )

    return sorted(set([s for s in suppliers if s]))


def _get_asset_options():
    suppliers = _get_user_suppliers()

    if not suppliers:
        return []

    rows = frappe.get_all(
        "Asset",
        filters={
            "supplier": ["in", suppliers],
            "location": ["in", ALLOWED_SUPPLIER_SITES],
            "docstatus": ["!=", 2],
        },
        fields=[
            "name",
            "asset_name",
            "location",
            "supplier",
            "asset_category",
            "item_name",
        ],
        order_by="location asc, name asc",
        limit_page_length=0,
    )

    values = []

    for row in rows:
        fleet_no = row.get("name")
        if fleet_no and fleet_no not in values:
            values.append(fleet_no)

    return values


def _get_asset_details(asset_options):
    details = {}

    if not asset_options:
        return details

    rows = frappe.get_all(
        "Asset",
        filters={
            "name": ["in", asset_options],
        },
        fields=[
            "name",
            "asset_name",
            "location",
            "asset_category",
            "item_name",
            "supplier",
            "asset_owner",
        ],
        limit_page_length=0,
    )

    for row in rows:
        data = {
            "site": row.location or "",
            "machine_type": row.asset_category or "",
            "machine_model": row.item_name or row.asset_name or row.name or "",
        }

        if row.name:
            details[row.name] = data

        if row.asset_name:
            details[row.asset_name] = data

    return details


def _validate_asset(fleet_number):
    if not fleet_number:
        frappe.throw(_("Fleet Number is required."))

    suppliers = _get_user_suppliers()

    if not suppliers:
        frappe.throw(_("Your user is not linked to a Supplier."), frappe.PermissionError)

    asset_rows = frappe.get_all(
        "Asset",
        filters={
            "supplier": ["in", suppliers],
            "location": ["in", ALLOWED_SUPPLIER_SITES],
            "docstatus": ["!=", 2],
        },
        fields=["name", "asset_name"],
        limit_page_length=0,
    )

    allowed = set()

    for row in asset_rows:
        for value in [row.name, row.asset_name]:
            if value:
                allowed.add(value)
                allowed.add(_norm_asset(value))

    if fleet_number not in allowed and _norm_asset(fleet_number) not in allowed:
        frappe.throw(_("This asset is not linked to your supplier access."), frappe.PermissionError)


def _parse_datetime(value):
    if not value:
        return None

    value = str(value).strip()

    for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return get_datetime(value, fmt)
        except Exception:
            pass

    try:
        return get_datetime(value)
    except Exception:
        return None


def _format_datetime_for_input(value):
    if not value:
        return ""

    try:
        return get_datetime(value).strftime("%d-%m-%Y %H:%M:%S")
    except Exception:
        return str(value)


def _link_value_exists(doctype, value):
    if not value:
        return False

    try:
        return bool(frappe.db.exists(doctype, value))
    except Exception:
        return False


def _norm_asset(value):
    return (
        str(value or "")
        .strip()
        .upper()
        .replace("IS0", "IS")
        .replace(" ", "")
    )
