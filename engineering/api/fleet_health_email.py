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
