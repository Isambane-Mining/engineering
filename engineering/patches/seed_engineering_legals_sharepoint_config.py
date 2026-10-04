"""Copy the SharePoint / Microsoft Graph settings from site_config into the new
Engineering Legals SharePoint Config Single, which is now the only place they
are read from. Leaves an already-configured Single alone. Once this has run,
the ms_graph_* / sharepoint_* keys can be removed from site_config.json.
"""

import frappe

DOCTYPE = "Engineering Legals SharePoint Config"

SITE_CONFIG_KEYS = {
    "tenant_id": "ms_graph_tenant_id",
    "client_id": "ms_graph_client_id",
    "client_secret": "ms_graph_client_secret",
    "hostname": "sharepoint_hostname",
    "site_path": "sharepoint_site_path",
    "drive_name": "sharepoint_drive_name",
}


def execute():
    if frappe.db.get_single_value(DOCTYPE, "tenant_id"):
        return

    values = {field: frappe.conf.get(key) for field, key in SITE_CONFIG_KEYS.items()}
    if not any(values.values()):
        return

    doc = frappe.get_single(DOCTYPE)
    doc.update({field: value for field, value in values.items() if value})
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
