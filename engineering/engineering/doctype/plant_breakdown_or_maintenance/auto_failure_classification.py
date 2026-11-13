import json
import urllib.error
import urllib.request

import frappe


CLASSIFICATION_DOCTYPE = "Breakdown Failure Classification"


@frappe.whitelist(methods=["POST"])
def classify_breakdown(reason):
    """Suggest a failure classification and record its AI audit."""

    reason = (reason or "").strip()

    if not reason or len(reason) > 1000:
        return {"classification": None}


    if not (
        frappe.has_permission("Plant Breakdown or Maintenance", "create")
        or frappe.has_permission("Plant Breakdown or Maintenance", "write")
    ):
        frappe.throw("Not permitted", frappe.PermissionError)

    records = frappe.get_list(
        CLASSIFICATION_DOCTYPE,
        fields=["name", "description"],
        limit_page_length=100,
    )

    if not records:
        return {"classification": None}

    names = [row.name for row in records]

    schema = {
        "type": "object",
        "properties": {
            "classification": {
                "type": ["string", "null"],
                "enum": names + [None],
            },
        },
        "required": ["classification"],
        "additionalProperties": False,
    }

    model = frappe.conf.get(
        "pbom_classification_model", "qwen3:8b"
    )

    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "format": schema,
        "options": {
            "temperature": 0,
            "num_predict": 100,
            "num_ctx": 4096,
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify breakdowns on heavy mining equipment. "
                    "Identify the failed equipment system, not the "
                    "general symptom or safety consequence. "
                    "Understand informal maintenance terminology. "
                    "Return null if the failed system is unclear. "
                    "Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "classifications": names,
                    "breakdown_reason": reason,
                }),
            },
        ],
    }

    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=45
        ) as response:
            result = json.load(response)

        answer = json.loads(
            result.get("message", {}).get("content", "")
        )

        classification = answer.get("classification")
        if classification not in names:
            return {"classification": None}

        # Create the suggestion audit on the server.
        # The operator has not yet accepted or verified it.
        audit = frappe.get_doc({
            "doctype": "PBM AI Classification Audit",
            "breakdown_description": reason,
            "ai_suggested_classification": classification,
            "ai_model": model,
            "suggested_by": frappe.session.user,
            "suggested_at": frappe.utils.now_datetime(),
            "audit_status": "Suggested",
        })

        # A suggestion must have a persisted audit record.
        # Never return an unaudited automatic classification.
        frappe.db.savepoint("pbm_ai_suggestion_audit")

        try:
            audit.insert(ignore_permissions=True)
        except Exception:
            frappe.db.rollback(
                save_point="pbm_ai_suggestion_audit"
            )
            frappe.logger("engineering").exception(
                "PBM AI suggestion audit insertion failed"
            )
            return {"classification": None}

        return {
            "classification": classification,
            "audit_id": audit.name,
        }

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ):
        # AI failure must not prevent manual breakdown capture.
        return {"classification": None}
