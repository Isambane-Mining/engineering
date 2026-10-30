"""Stable authenticated HTTP entry point; business rules live in controllers."""

import frappe

from engineering.controllers import fleet_health_email as controller


@frappe.whitelist(methods=["POST"])
def send_fleet_health_email(
    subject=None, text=None, html=None, attachments=None, **kwargs
):
    try:
        return controller.send_fleet_health_email(
            subject=subject, text=text, html=html, attachments=attachments, **kwargs
        )
    except (frappe.ValidationError, frappe.PermissionError) as error:
        # Developer-mode error snapshots include request arguments and attachments.
        error.skip_error_log = True
        raise
    except Exception:  # noqa: BLE001 - never snapshot confidential endpoint arguments.
        # Includes unexpected failures before the controller enters private delivery.
        raise controller.delivery_error(frappe.ValidationError) from None
