# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class WearCheckResults(Document):

    def on_update(self):
        from engineering.controllers.notifications import (
            wearcheck_results_on_update,
        )

        wearcheck_results_on_update(self, "on_update")
