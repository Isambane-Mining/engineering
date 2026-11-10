import json
import urllib.error
import urllib.request

import frappe


CLASSIFICATION_DOCTYPE = "Breakdown Failure Classification"


@frappe.whitelist()
def classify_breakdown(reason):
    """Suggest an existing failure classification without modifying records."""

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

    payload = {
        "model": frappe.conf.get(
            "pbom_classification_model", "qwen3:8b"
        ),
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

        return {"classification": classification}

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
