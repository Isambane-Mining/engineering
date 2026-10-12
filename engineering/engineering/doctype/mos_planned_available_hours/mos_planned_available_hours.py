import frappe
from frappe import _
from frappe.model.document import Document


class MOSPlannedAvailableHours(Document):
    def autoname(self):
        if self.hours is None:
            frappe.throw(_("Hours is required."))

        self.name = self._format_hours(self.hours)

    def validate(self):
        if self.hours is None:
            frappe.throw(_("Hours is required."))

        expected_name = self._format_hours(self.hours)

        duplicate = frappe.db.exists(
            "MOS Planned Available Hours",
            {
                "hours": self.hours,
                "name": ["!=", self.name],
            },
        )

        if duplicate:
            frappe.throw(
                _("Planned Available Hours {0} already exists.").format(
                    frappe.bold(expected_name)
                )
            )

    @staticmethod
    def _format_hours(value):
        number = float(value)

        if number.is_integer():
            return str(int(number))

        return f"{number:g}"
