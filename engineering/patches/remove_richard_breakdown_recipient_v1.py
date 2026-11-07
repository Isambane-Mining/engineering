import frappe


def execute():
    if not frappe.db.exists(
        "DocType", "Plant Breakdown Settings"
    ):
        return

    settings = frappe.get_single("Plant Breakdown Settings")

    matches = [
        row
        for row in settings.get("recipients_per_site") or []
        if (row.location or "").strip().lower() == "gwab"
        and (row.user or "").strip().lower()
        == "richard@isambane.co.za"
    ]

    if not matches:
        return

    for row in matches:
        settings.remove(row)

    settings.save(ignore_permissions=True)
