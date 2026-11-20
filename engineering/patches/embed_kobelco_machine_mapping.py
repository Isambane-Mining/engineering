"""Replace the empty legacy mapping master with the Settings child table.

Refuse to change schema or delete anything when legacy mappings contain data.
Run before model sync so that guard also protects normal `bench migrate`.
"""
import frappe

LEGACY_MAPPING = "Kobelco Asset Mapping"


def _ensure_empty():
    if frappe.db.table_exists(LEGACY_MAPPING) and frappe.db.count(LEGACY_MAPPING):
        raise frappe.ValidationError(
            "Kobelco mapping migration stopped: existing data in Kobelco Asset Mapping. "
            "Export and review those records before replacing the standalone DocType."
        )


def execute():
    _ensure_empty()
    for doctype in ("kobelco_machine_mapping", "api_kobelco_settings", "kobelco_results"):
        frappe.reload_doc("engineering", "doctype", doctype, force=True)

    if frappe.db.exists("Workspace", "Engineering"):
        workspace = frappe.get_doc("Workspace", "Engineering")
        old_links = workspace.links
        retained = [row for row in old_links if row.link_to != LEGACY_MAPPING]
        if len(retained) != len(old_links):
            workspace.set("links", retained)
            for idx, row in enumerate(workspace.links, 1):
                row.idx = idx
                if row.type == "Card Break" and row.label == "Kobelco Integration":
                    row.link_count = 2
            # Suppress source export: retain any unrelated edits in the checkout.
            previous_flag = frappe.flags.in_migrate
            try:
                frappe.flags.in_migrate = True
                workspace.save(ignore_permissions=True)
            finally:
                frappe.flags.in_migrate = previous_flag

    # Recheck after schema loading; never discard a mapping created meanwhile.
    _ensure_empty()
    if frappe.db.exists("DocType", LEGACY_MAPPING):
        frappe.db.delete("Custom DocPerm", {"parent": LEGACY_MAPPING})
        frappe.delete_doc("DocType", LEGACY_MAPPING, force=True, ignore_permissions=True)
    if frappe.db.table_exists(LEGACY_MAPPING):
        frappe.db.sql_ddl("DROP TABLE `tabKobelco Asset Mapping`")
    frappe.clear_cache(doctype="API Kobelco Settings")
