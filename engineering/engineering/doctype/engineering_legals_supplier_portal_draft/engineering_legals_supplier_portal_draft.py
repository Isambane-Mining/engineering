# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from engineering.controllers.engineering_legals_rules import authorize_capture, calculate


class EngineeringLegalssupplierPortalDraft(Document):
    def validate(self):
        if "Supplier" in frappe.get_roles(frappe.session.user):
            if self.portal_user != frappe.session.user:
                raise frappe.PermissionError("You can only edit your own draft.")
            before = self.get_doc_before_save()
            if before and getattr(before, "portal_user", None) != frappe.session.user:
                raise frappe.PermissionError("You can only edit your own draft.")
            if before and before.sent_to_erp:
                raise frappe.PermissionError("Sent supplier drafts cannot be edited.")
        authorize_capture(self)
        result = calculate(self)
        for field in ("expiry_date", "start_date", "vehicle_type", "lifting_type", "brake_wear_type"):
            setattr(self, field, result[field])
