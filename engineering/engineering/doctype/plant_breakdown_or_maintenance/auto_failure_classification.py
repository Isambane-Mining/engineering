import json
import urllib.error
import urllib.request

import frappe


CLASSIFICATION_DOCTYPE = "Breakdown Failure Classification"


@frappe.whitelist(methods=["POST"])
def classify_breakdown(reason):
    """Queue classification through the existing Frappe MCP method."""
    return queue_classification(reason)



def _run_classification_job(request_id, user):
    """Classify in background; never create a PBM audit."""
    from engineering.engineering.doctype.ai_failure_classification_settings.ai_failure_classification_settings import (
        validate_ollama_endpoint,
    )
    from .ai_classification_requests import get_request, update_request

    try:
        pending = get_request(request_id, user)
        if not pending or pending.get("status") != "Queued":
            return

        update_request(request_id, user, status="Processing")

        settings = frappe.get_single("AI Failure Classification Settings")
        if not settings.enabled:
            update_request(request_id, user, status="Failed")
            return

        endpoint = validate_ollama_endpoint(settings.ollama_endpoint)
        model = (settings.preferred_model or "").strip()
        timeout = int(settings.request_timeout)

        allowed = {
            row.failure_classification
            for row in settings.allowed_classifications or []
        }

        if not allowed or not model or not 1 <= timeout <= 120:
            update_request(request_id, user, status="Failed")
            return

        names = sorted(
            set(frappe.get_all(
                CLASSIFICATION_DOCTYPE,
                filters={"name": ["in", list(allowed)]},
                pluck="name",
                limit_page_length=100,
            ))
        )

        if not names:
            update_request(request_id, user, status="Failed")
            return

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

        payload = {
            "model": model,
            "stream": False,
            "think": False,
            "format": schema,
            "options": {"temperature": 0, "num_predict": 100},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Classify the failed system of heavy mining "
                        "equipment. Return null if unclear. Return JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "classifications": names,
                        "breakdown_reason": pending["reason"],
                    }),
                },
            ],
        }

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirect(),
        )

        request = urllib.request.Request(
            endpoint + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with opener.open(request, timeout=timeout) as response:
            result = json.load(response)

        answer = json.loads(result["message"]["content"])
        classification = answer.get("classification")

        if classification not in names:
            update_request(
                request_id,
                user,
                status="No Suggestion",
                classification=None,
                model=model,
            )
            return

        update_request(
            request_id,
            user,
            status="Completed",
            classification=classification,
            model=model,
        )

    except Exception:
        frappe.logger("engineering").exception(
            "Background AI classification failed"
        )
        try:
            update_request(request_id, user, status="Failed")
        except Exception:
            frappe.logger("engineering").exception(
                "Could not update AI request status"
            )


@frappe.whitelist(methods=["POST"])
def queue_classification(reason):
    """Queue an AI suggestion without creating an audit."""
    from .ai_classification_requests import create_request

    reason = (reason or "").strip()

    if not reason or len(reason) > 1000:
        return {"status": "Invalid"}

    if not (
        frappe.has_permission(
            "Plant Breakdown or Maintenance", "create"
        )
        or frappe.has_permission(
            "Plant Breakdown or Maintenance", "write"
        )
    ):
        frappe.throw("Not permitted", frappe.PermissionError)

    settings = frappe.get_single(
        "AI Failure Classification Settings"
    )

    if not settings.enabled:
        return {"status": "Disabled"}

    user = frappe.session.user
    request_id = create_request(reason, user)

    try:
        frappe.enqueue(
            "engineering.engineering.doctype."
            "plant_breakdown_or_maintenance."
            "auto_failure_classification._run_classification_job",
            queue="long",
            timeout=max(120, int(settings.request_timeout) + 30),
            enqueue_after_commit=False,
            request_id=request_id,
            user=user,
        )
    except Exception:
        frappe.cache().delete_value(
            "pbm_ai_request:" + request_id
        )
        raise

    return {
        "status": "Queued",
        "request_id": request_id,
    }
