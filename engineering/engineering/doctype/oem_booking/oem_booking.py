# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class OEMBooking(Document):

    def on_update(self):
        from engineering.controllers.notifications import (
            oem_booking_on_update,
        )

        oem_booking_on_update(self, "on_update")
