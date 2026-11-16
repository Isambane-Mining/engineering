import frappe
from frappe import _
from erpnext.controllers.website_list_for_contact import get_customers_suppliers

from engineering.templates.pages.pre_use_file.pre_use_deviation_supplier import (
    ALLOWED_SUPPLIER_SITES,
    _get_asset_options as _get_supplier_asset_options,
)


def get_context(context):
    context.no_cache = 1
    context.show_sidebar = True
    context.title = "My Pre Use Deviations"

    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/pre_use_deviation_list"
        raise frappe.Redirect

    if "Supplier" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Not permitted."), frappe.PermissionError)

    context.records = _get_portal_records()


def _get_portal_records():
    assets = _get_supplier_asset_options()

    if not assets:
        return []

    return frappe.get_all(
        "Pre Use Deviation",
        filters={
            "fleet_number": ["in", assets],
            "site": ["in", ALLOWED_SUPPLIER_SITES],
        },
        fields=[
            "name",
            "report_datetime",
            "machine_model",
            "fleet_number",
            "pre_use_no",
            "recurring_deviation",
            "deviation_details",
            "reported_by_name_and_surname",
            "action",
            "action_date_and_time",
            "date_service_report_received",
            "job_card_number",
            "resolution_summary",
            "actioned_by_name_and_surname",
            "action_status",
            "completion_percentage",
        ],
        order_by="modified desc",
        limit_page_length=100,
    )


@frappe.whitelist()
def export_supplier_pre_use_excel():
    """Export only records available to this supplier portal user."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required."), frappe.PermissionError)

    if "Supplier" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Not permitted."), frappe.PermissionError)

    import io
    import xlsxwriter

    records = _get_portal_records()

    columns = [
        ("Date", "report_datetime"),
        ("Machine Model", "machine_model"),
        ("Fleet Number", "fleet_number"),
        ("Pre-Use No.", "pre_use_no"),
        ("Recurring Deviation", "recurring_deviation"),
        ("Deviation Details", "deviation_details"),
        ("Reported By", "reported_by_name_and_surname"),
        ("Action", "action"),
        ("Action Date and Time", "action_date_and_time"),
        ("Date Service Report Received", "date_service_report_received"),
        ("Job Card Number", "job_card_number"),
        ("Resolution Summary", "resolution_summary"),
        ("Actioned By Name and Surname", "actioned_by_name_and_surname"),
        ("Action Status", "action_status"),
        ("Completion Percentage", "completion_percentage"),
    ]

    output = io.BytesIO()

    workbook = xlsxwriter.Workbook(output, {
        "in_memory": True,
        "strings_to_formulas": False,
        "strings_to_urls": False,
    })

    sheet = workbook.add_worksheet("Pre Use Deviations")

    green = workbook.add_format({
        "bold": True,
        "bg_color": "#00AD50",
        "font_color": "#000000",
        "border": 1,
        "border_color": "#000000",
        "text_wrap": True,
        "valign": "vcenter",
    })

    yellow = workbook.add_format({
        "bold": True,
        "bg_color": "#FFFF00",
        "font_color": "#000000",
        "border": 1,
        "border_color": "#000000",
        "text_wrap": True,
        "valign": "vcenter",
    })

    data_format = workbook.add_format({
        "border": 1,
        "border_color": "#000000",
        "valign": "top",
        "text_wrap": True,
    })

    sheet.set_row(0, 42)
    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(len(records), 1), 14)

    for col_idx, (heading, fieldname) in enumerate(columns):
        header_format = yellow if (
            fieldname == "recurring_deviation"
        ) else green

        sheet.write_string(0, col_idx, heading, header_format)

        width = 35 if fieldname in (
            "deviation_details",
            "resolution_summary",
            "actioned_by_name_and_surname",
        ) else 24

        sheet.set_column(col_idx, col_idx, width)

    for row_idx, record in enumerate(records, start=1):
        for col_idx, (_, fieldname) in enumerate(columns):
            value = record.get(fieldname)

            if fieldname == "completion_percentage":
                value = str(value if value is not None else 0) + "%"

            if value is None:
                value = ""

            # Writing explicitly as a string prevents spreadsheet
            # formulas supplied through text fields from executing.
            sheet.write_string(
                row_idx,
                col_idx,
                str(value),
                data_format,
            )

    workbook.close()

    frappe.local.response["filename"] = (
        "Pre_Use_Supplier_Report.xlsx"
    )
    frappe.local.response["filecontent"] = output.getvalue()
    frappe.local.response["type"] = "download"



def _get_user_suppliers():
    suppliers = []

    try:
        customers, rfq_suppliers = get_customers_suppliers(
            "Request for Quotation Supplier",
            frappe.session.user,
        )
        suppliers.extend(rfq_suppliers or [])
    except Exception:
        pass

    contact_names = frappe.db.sql_list(
        """
        SELECT DISTINCT c.name
        FROM `tabContact` c
        LEFT JOIN `tabContact Email` ce ON ce.parent = c.name
        WHERE c.email_id = %(user)s
           OR ce.email_id = %(user)s
        """,
        {"user": frappe.session.user},
    )

    if contact_names:
        linked_suppliers = frappe.db.sql_list(
            """
            SELECT DISTINCT link_name
            FROM `tabDynamic Link`
            WHERE parenttype = 'Contact'
              AND parent IN %(contacts)s
              AND link_doctype = 'Supplier'
            """,
            {"contacts": tuple(contact_names)},
        )
        suppliers.extend(linked_suppliers or [])

    return sorted(set([s for s in suppliers if s]))


def _get_asset_options():
    suppliers = _get_user_suppliers()

    if not suppliers:
        return []

    return frappe.get_all(
        "Asset",
        filters={
            "asset_owner": "Supplier",
            "supplier": ["in", suppliers],
        },
        pluck="name",
        order_by="name asc",
        limit_page_length=0,
    )
