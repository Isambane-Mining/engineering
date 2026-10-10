import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_timedelta


class MOSSiteShiftConfiguration(Document):
    def validate(self):
        self.validate_unique_site()
        self.validate_shift_setup()

    def validate_unique_site(self):
        filters = {
            "site": self.site,
        }

        if not self.is_new():
            filters["name"] = ["!=", self.name]

        existing = frappe.db.exists(
            "MOS Site Shift Configuration",
            filters,
        )

        if existing:
            frappe.throw(
                _(
                    "A MOS Site Shift Configuration already exists "
                    "for Site {0}."
                ).format(
                    frappe.bold(self.site)
                )
            )

    def validate_shift_setup(self):
        if not self.day_shift_type and not self.night_shift_type:
            frappe.throw(
                _(
                    "Configure at least one Day Shift Type "
                    "or Night Shift Type."
                )
            )
