import frappe
from frappe import _
from frappe.model.document import Document


class MechanicalDowntimesignoff(Document):

    def autoname(self):
        if not self.site or not self.report_date or not self.report_shift:
            frappe.throw(_("Site, Report Date and Shift are required."))

        from frappe.utils import getdate

        site = str(self.site).strip().replace(" ", "-")
        date = getdate(self.report_date).isoformat()
        shift = str(self.report_shift).strip().replace(" ", "-")

        if "/" in site or "\\\\" in site:
            frappe.throw(_("Invalid site name."))

        self.name = f"{site}-{date}-{shift}"


    def validate(self):
        previous = self.get_doc_before_save()
        rows = self.get("signoff_information") or []
        auth = frappe.flags.get("_mechanical_dt_signoff_save")

        if len(rows) > 1:
            frappe.throw(_("Multiple verification rows are not allowed."))

        if not previous:
            if rows or self.status != "Open":
                frappe.throw(_("New sign-offs must start without approvals."))
            return

        for field in ("site", "report_date", "report_shift"):
            if str(self.get(field) or "") != str(previous.get(field) or ""):
                frappe.throw(_("Sign-off reporting details cannot be changed."))

        old_rows = previous.get("signoff_information") or []

        if len(old_rows) > 1:
            frappe.throw(_("Multiple existing verification rows found."))

        authorized_section = None
        if (
            isinstance(auth, tuple)
            and len(auth) == 2
            and auth[0] == self.name
            and auth[1] in ("Engineering", "Production")
        ):
            authorized_section = auth[1]

        if len(rows) != len(old_rows):
            if not (
                authorized_section
                and not old_rows
                and len(rows) == 1
            ):
                frappe.throw(_("Verification rows cannot be changed manually."))

        old = old_rows[0] if old_rows else None
        new = rows[0] if rows else None

        fields = {
            "Engineering": (
                "engineering_user", "engineering_user_id",
                "date_time_e", "shift_e", "engineering_signature",
            ),
            "Production": (
                "production_user", "production_user_id",
                "date_time_p", "shift_p", "production_signature",
            ),
        }

        if old and new and old.name != new.name:
            frappe.throw(_("Verification rows cannot be replaced."))

        for section, names in fields.items():
            if section == authorized_section:
                continue

            for field in names:
                before = old.get(field) if old else None
                after = new.get(field) if new else None

                if str(before or "") != str(after or ""):
                    frappe.throw(
                        _("Existing electronic approvals cannot be modified.")
                    )

        if authorized_section:
            names = fields[authorized_section]
            if old:
                if any(old.get(field) for field in names):
                    frappe.throw(_("This section has already been approved."))

            if not new:
                frappe.throw(_("Missing verification row."))

            user_field = (
                "engineering_user_id"
                if authorized_section == "Engineering"
                else "production_user_id"
            )

            if new.get(user_field) != frappe.session.user:
                frappe.throw(_("Approval user does not match the session."))

            signature_field = (
                "engineering_signature"
                if authorized_section == "Engineering"
                else "production_signature"
            )
            if new.get(signature_field):
                frappe.throw(_("New handwritten signatures are not accepted."))

        expected = (
            "Closed"
            if new
            and new.engineering_user and new.date_time_e
            and new.production_user and new.date_time_p
            else "Open"
        )

        if self.status != expected:
            frappe.throw(_("Sign-off status does not match approvals."))

    def before_insert(self):
        if not self.site or not frappe.db.exists("Location", self.site):
            frappe.throw(_("Please select a valid site."))

        if not self.report_date:
            frappe.throw(_("Report Date is required."))


        if frappe.utils.getdate(
            self.report_date
        ) > frappe.utils.getdate(frappe.utils.today()):
            frappe.throw(
                _("Future report dates cannot be signed off.")
            )

        if self.report_shift not in (
            "Day Shift",
            "Night Shift",
            "All Shifts",
        ):
            frappe.throw(_("Please select a valid Report Shift."))
