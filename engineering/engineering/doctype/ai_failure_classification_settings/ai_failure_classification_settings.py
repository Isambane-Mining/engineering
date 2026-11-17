import frappe
from frappe.model.document import Document
from frappe.utils import cint


def validate_ollama_endpoint(endpoint):
    """Validate the configured local Ollama endpoint."""
    from urllib.parse import urlparse

    endpoint = (endpoint or "").strip().rstrip("/")
    parsed = urlparse(endpoint)

    if (
        parsed.scheme != "http"
        or parsed.hostname not in ("127.0.0.1", "localhost")
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not parsed.port
    ):
        frappe.throw("Invalid local Ollama endpoint.")

    return endpoint


class AIFailureClassificationSettings(Document):

    def validate(self):
        self.ollama_endpoint = validate_ollama_endpoint(
            self.ollama_endpoint
        )
        timeout = cint(self.request_timeout)

        if not 1 <= timeout <= 120:
            frappe.throw(
                "Request Timeout must be between 1 and 120 seconds."
            )

        self.request_timeout = timeout

        if not (self.preferred_model or "").strip():
            frappe.throw("Preferred Model is required.")

        self.preferred_model = self.preferred_model.strip()

        seen = set()

        for row in self.allowed_classifications or []:
            classification = row.failure_classification

            if classification in seen:
                frappe.throw(
                    f"Duplicate allowed classification: {classification}"
                )

            seen.add(classification)


@frappe.whitelist(methods=["POST"])
def get_available_models():
    """Retrieve installed models from the configured Ollama server."""
    import json
    import urllib.error
    import urllib.request

    frappe.only_for((
        "System Manager",
        "Engineering Manager",
        "Engineering Area Manager",
    ))

    settings = frappe.get_single(
        "AI Failure Classification Settings"
    )

    endpoint = validate_ollama_endpoint(
        settings.ollama_endpoint
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        NoRedirect(),
    )

    request = urllib.request.Request(
        endpoint + "/api/tags",
        method="GET",
    )

    try:
        with opener.open(request, timeout=5) as response:
            payload = json.load(response)

        if not isinstance(payload, dict):
            raise ValueError("Invalid Ollama response")

        models = payload.get("models", [])

        if not isinstance(models, list):
            raise ValueError("Invalid model list")

        return [
            item["name"]
            for item in models
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item["name"]
        ]

    except (
        urllib.error.URLError,
        OSError,
        ValueError,
        TypeError,
    ):
        frappe.throw("Unable to retrieve Ollama models.")
