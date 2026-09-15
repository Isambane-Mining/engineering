"""Request-scoped protection for contextual OAuth diagnostics in LAB Frappe."""
from contextlib import contextmanager
from contextvars import ContextVar

import frappe
from frappe.utils import _get_traceback_sanitizer
from sentry_sdk import Hub

_private = ContextVar("fleet_health_private_delivery", default=False)


def _hide_variables(*_args):
    return _private.get()


# Extend the framework formatter once, rather than replacing any global function.
# The ContextVar makes this a no-op for every other request/thread/context.
_get_traceback_sanitizer().custom_var_printers.insert(
    0, (_hide_variables, lambda _value: "[REDACTED]")
)


@contextmanager
def private_delivery():
    marker = _private.set(True)
    try:
        # Frappe's telemetry captures raw exceptions independently of its formatter.
        # A cloned hub keeps event suppression local to this delivery request.
        with Hub(Hub.current) as hub:
            with hub.push_scope() as scope:
                scope.add_event_processor(lambda _event, _hint: None)
                yield
    finally:
        _private.reset(marker)


def redact_error_log(doc, method=None):
    """Frappe before_insert hook: also discard raw exception messages/metadata."""
    if _private.get() and frappe.local.site == "juan.isambane.co.za":
        doc.error = "Fleet Health delivery failed. Diagnostics redacted."
        doc.method = "Fleet Health delivery"
        doc.metadata = None
