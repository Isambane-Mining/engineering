"""Permission-checked manual retry of unsynced Engineering Legals."""

import frappe

DOCTYPE = "Engineering Legals"
METHOD = (
    "engineering.engineering.doctype.engineering_legals."
    "engineering_legals.run_engineering_legals_sharepoint_sync"
)
ALLOWED_ROLES = {"System Manager", "Engineering Manager"}
BATCH_SIZE = 200


def _authorized():
    if frappe.session.user == "Guest" or not (
        set(frappe.get_roles()) & ALLOWED_ROLES
    ):
        frappe.throw("Not permitted to retry SharePoint sync.", frappe.PermissionError)


def _eligible():
    _authorized()

    names = frappe.get_all(
        DOCTYPE,
        filters={
            "sharepoint_synced": 0,
            "attach_paper": ["is", "set"],
            "docstatus": ["<", 2],
        },
        pluck="name",
        order_by="modified asc",
        limit_page_length=BATCH_SIZE,
    )

    permitted = []
    for name in names:
        doc = frappe.get_doc(DOCTYPE, name)
        if doc.has_permission("read") and doc.has_permission("write"):
            permitted.append(name)

    return permitted


@frappe.whitelist(methods=["POST"])
def retry_unsynced_sharepoint(preview=1):
    names = _eligible()

    if frappe.utils.cint(preview):
        return {"eligible": len(names), "limit": BATCH_SIZE}

    for name in names:
        frappe.enqueue(
            METHOD,
            queue="short",
            timeout=300,
            enqueue_after_commit=True,
            docname=name,
        )

    return {"queued": len(names), "limit": BATCH_SIZE}
