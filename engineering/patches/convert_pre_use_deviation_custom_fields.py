"""Convert three Pre Use Deviation Custom Fields to standard DocType fields.

The existing physical database columns and their values are preserved.
Run before DocType model synchronisation.
"""

import frappe


DOCTYPE = "Pre Use Deviation"

FIELDS = {
    "recurring_deviation": "Data",
    "action": "Data",
    "date_service_report_received": "Date",
}


def execute():
    # A fresh installation has no legacy Custom Fields or columns yet.
    # Only verify columns for legacy metadata that actually exists.
    existing = frappe.get_all(
        "Custom Field",
        filters={
            "dt": DOCTYPE,
            "fieldname": ["in", list(FIELDS)],
        },
        fields=["name", "fieldname", "fieldtype"],
        limit_page_length=0,
    )

    for row in existing:
        # Protect existing values before removing legacy field metadata.
        if not frappe.db.has_column(DOCTYPE, row.fieldname):
            frappe.throw(
                f"Missing database column: {DOCTYPE}.{row.fieldname}. "
                "Migration stopped to protect existing data."
            )

        expected_type = FIELDS[row.fieldname]

        if row.fieldtype != expected_type:
            frappe.throw(
                f"Unexpected field type for {row.fieldname}: "
                f"{row.fieldtype}, expected {expected_type}"
            )

        expected_name = f"{DOCTYPE}-{row.fieldname}"

        if row.name != expected_name:
            frappe.throw(
                f"Unexpected Custom Field record: {row.name}"
            )

    if existing:
        # Delete metadata only. Do not invoke Custom Field deletion hooks,
        # schema deletion or DROP COLUMN operations.
        frappe.db.delete(
            "Custom Field",
            {
                "dt": DOCTYPE,
                "fieldname": ["in", list(FIELDS)],
            },
        )

        frappe.clear_cache(doctype=DOCTYPE)

    print(
        "Pre Use Deviation: standard-field metadata conversion "
        f"completed ({len(existing)} old Custom Field records removed)"
    )
