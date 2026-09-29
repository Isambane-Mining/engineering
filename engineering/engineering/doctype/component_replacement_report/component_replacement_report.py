# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ComponentReplacementReport(Document):

    def on_update(self):
        from engineering.controllers.isambane_sample_input import (
            component_replacement_report_on_update,
        )

        component_replacement_report_on_update(self, "on_update")
