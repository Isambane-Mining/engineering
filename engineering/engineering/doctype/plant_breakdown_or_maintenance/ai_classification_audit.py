import frappe
from frappe.utils import now_datetime


AUDIT_DOCTYPE = "PBM AI Classification Audit"


def _previous_document(doc):
    if doc.is_new():
        return None
    return doc.get_doc_before_save()


def _has_audited_changes(doc, previous):
    if not previous:
        return False

    return (
        (previous.failure_classification or "")
        != (doc.failure_classification or "")
        or
        (previous.breakdown_reason or "").strip()
        != (doc.breakdown_reason or "").strip()
    )


def _lock_audit(audit_id):
    rows = frappe.db.sql(
        """
        SELECT name
        FROM `tabPBM AI Classification Audit`
        WHERE name = %s
        FOR UPDATE
        """,
        (audit_id,),
        as_dict=True,
    )

    if not rows:
        frappe.throw("AI classification audit not found.")

    return frappe.get_doc(AUDIT_DOCTYPE, audit_id)


def validate_audit_reference(doc):
    """Validate audit ownership and PBM correction requirements."""

    audit_id = doc.get("ai_classification_audit")
    previous = _previous_document(doc)

    previous_id = (
        previous.get("ai_classification_audit")
        if previous else None
    )

    if previous_id and audit_id != previous_id:
        frappe.throw(
            "An existing AI audit reference cannot be removed "
            "or replaced."
        )

    if not audit_id:
        return

    if doc.downtime_type != "Breakdown":
        frappe.throw(
            "An AI-audited breakdown must remain a Breakdown."
        )

    audit = frappe.get_doc(AUDIT_DOCTYPE, audit_id)

    if audit.audit_status == "Finalised":
        if not previous_id or audit.breakdown_reference != doc.name:
            frappe.throw(
                "Finalised AI audit cannot be reused."
            )

        if _has_audited_changes(doc, previous):
            reason = (
                doc.get("ai_classification_correction_reason") or ""
            ).strip()

            if not reason:
                frappe.throw(
                    "Classification Correction Reason is required "
                    "when changing an audited classification "
                    "or breakdown description."
                )

            previous_reason = (
                previous.get("ai_classification_correction_reason")
                or ""
            ).strip()

            if reason == previous_reason:
                frappe.throw(
                    "Please provide a new Classification Correction "
                    "Reason for this change."
                )

            if not doc.failure_classification:
                frappe.throw(
                    "Final classification cannot be empty."
                )

        return

    if audit.audit_status != "Suggested":
        frappe.throw("Invalid AI audit status.")

    if previous_id:
        frappe.throw(
            "Cannot replace an existing audit with a pending suggestion."
        )

    if audit.suggested_by != frappe.session.user:
        frappe.throw(
            "AI suggestion belongs to another user.",
            frappe.PermissionError,
        )

    if (audit.breakdown_description or "").strip() != (
        doc.breakdown_reason or ""
    ).strip():
        frappe.throw(
            "AI suggestion does not match breakdown description."
        )

    if audit.breakdown_reference:
        frappe.throw("AI suggestion is already linked.")

    if not doc.failure_classification:
        frappe.throw(
            "A final classification is required."
        )


def finalise_audit(doc):
    """Finalise the initial decision or append a correction event."""

    audit_id = doc.get("ai_classification_audit")
    if not audit_id:
        return

    audit = _lock_audit(audit_id)

    validate_audit_reference(doc)

    if audit.audit_status == "Suggested":
        existing = frappe.db.get_value(
            AUDIT_DOCTYPE,
            {
                "breakdown_reference": doc.name,
                "audit_status": "Finalised",
            },
            "name",
        )

        if existing:
            frappe.throw(
                "A finalised AI audit already exists for this breakdown."
            )

        decision = (
            "Accepted"
            if doc.failure_classification
            == audit.ai_suggested_classification
            else "Overridden"
        )

        frappe.db.set_value(
            AUDIT_DOCTYPE,
            audit.name,
            {
                "breakdown_reference": doc.name,
                "final_classification": doc.failure_classification,
                "decision": decision,
                "event_type": "AI Decision",
                "verified_by": frappe.session.user,
                "verified_at": now_datetime(),
                "audit_status": "Finalised",
            },
        )
        return

    if audit.audit_status != "Finalised":
        frappe.throw("Invalid AI audit status.")

    previous = _previous_document(doc)

    if not _has_audited_changes(doc, previous):
        return

    correction_reason = (
        doc.get("ai_classification_correction_reason") or ""
    ).strip()

    if not correction_reason:
        frappe.throw("Classification Correction Reason is required.")

    correction = frappe.get_doc({
        "doctype": AUDIT_DOCTYPE,
        "breakdown_reference": doc.name,
        "breakdown_description": doc.breakdown_reason,
        "ai_suggested_classification":
            audit.ai_suggested_classification,
        "ai_model": audit.ai_model,
        "suggested_by": audit.suggested_by,
        "suggested_at": audit.suggested_at,
        "previous_classification":
            previous.failure_classification,
        "previous_breakdown_description":
            previous.breakdown_reason,
        "final_classification": doc.failure_classification,
        "event_type": "Correction",
        "decision": "Corrected",
        "correction_reason": correction_reason,
        "verified_by": frappe.session.user,
        "verified_at": now_datetime(),
        "audit_status": "Finalised",
    })

    correction.insert(ignore_permissions=True)
