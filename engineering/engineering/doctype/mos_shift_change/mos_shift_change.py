import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_timedelta


class MOSShiftChange(Document):
    def autoname(self):
        self.name = self._make_name()

    def validate(self):
        self.duration_hours = self._calculate_duration()

        expected_name = self._make_name()

        if self.is_new():
            self.name = expected_name

        duplicate = frappe.db.exists(
            "MOS Shift Change",
            {
                "start_time": self.start_time,
                "end_time": self.end_time,
                "name": ["!=", self.name],
            },
        )

        if duplicate:
            frappe.throw(
                _("This Shift Change time already exists.")
            )

    def _make_name(self):
        if not self.start_time or not self.end_time:
            frappe.throw(
                _("Start Time and End Time are required.")
            )

        start = str(self.start_time)[:5]
        end = str(self.end_time)[:5]

        return f"{start}-{end} Shift Change"

    def _calculate_duration(self):
        start_seconds = get_timedelta(
            self.start_time
        ).total_seconds()

        end_seconds = get_timedelta(
            self.end_time
        ).total_seconds()

        if end_seconds < start_seconds:
            end_seconds += 24 * 60 * 60

        return round(
            (end_seconds - start_seconds) / 3600,
            3,
        )
