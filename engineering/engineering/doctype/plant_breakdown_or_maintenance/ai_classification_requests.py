"""Temporary AI requests; no database audit records."""

import secrets

import frappe

EXPIRY_SECONDS = 3600
PREFIX = "pbm_ai_request:"


def _key(request_id):
    return PREFIX + request_id


def create_request(reason, user):
    request_id = secrets.token_urlsafe(24)

    frappe.cache().set_value(
        _key(request_id),
        {
            "user": user,
            "reason": reason,
            "status": "Queued",
            "classification": None,
            "model": None,
        },
        expires_in_sec=EXPIRY_SECONDS,
    )

    return request_id


def get_request(request_id, user):
    if not isinstance(request_id, str):
        frappe.throw("Invalid AI request ID.")

    result = frappe.cache().get_value(_key(request_id))

    if not result:
        return None

    if result.get("user") != user:
        frappe.throw("Not permitted", frappe.PermissionError)

    return result


def update_request(request_id, user, **updates):
    result = get_request(request_id, user)

    if result is None:
        return False

    result.update(updates)

    frappe.cache().set_value(
        _key(request_id),
        result,
        expires_in_sec=EXPIRY_SECONDS,
    )

    return True


@frappe.whitelist(methods=["POST"])
def get_classification_status(request_id):
    """Return the current AI request status to its owner."""

    if not (
        frappe.has_permission(
            "Plant Breakdown or Maintenance", "create"
        )
        or frappe.has_permission(
            "Plant Breakdown or Maintenance", "write"
        )
    ):
        frappe.throw("Not permitted", frappe.PermissionError)

    result = get_request(request_id, frappe.session.user)

    if result is None:
        return {"status": "Expired"}

    return {
        "status": result.get("status"),
        "classification": result.get("classification"),
        "model": result.get("model"),
    }



def verify_request_for_save(request_id, user, reason):
    """Verify a completed AI suggestion before PBM save."""
    result = get_request(request_id, user)

    if result is None:
        frappe.throw(
            "AI suggestion expired. Request a new classification."
        )

    if result.get("status") != "Completed":
        frappe.throw("AI classification is not completed.")

    if result.get("reason") != (reason or "").strip():
        frappe.throw(
            "AI suggestion does not match the breakdown reason."
        )

    if not result.get("classification"):
        frappe.throw("No valid AI classification was suggested.")

    if not result.get("model"):
        frappe.throw("AI model information is missing.")

    return result
