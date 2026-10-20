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

        self._validate_downtime_verifications(previous)
        rows = self.get("signoff_information") or []
        auth = frappe.flags.get("_mechanical_dt_signoff_save")

        if len(rows) > 1:
            frappe.throw(_("Multiple verification rows are not allowed."))

        if not previous:
            version = int(self.get("verification_workflow_version") or 0)

            if version not in (0, 1):
                frappe.throw(_("Invalid verification workflow version."))

            if rows or self.status != "Open":
                frappe.throw(_("New sign-offs must start without approvals."))

            if version == 1:
                authorization = frappe.flags.get(
                    "_mechanical_dt_verification_create"
                )

                if authorization != self.name:
                    frappe.throw(
                        _("New verification sign-offs must be created through the report.")
                    )

                if self.get("downtime_verifications"):
                    frappe.throw(
                        _("New verification sign-offs must start without records.")
                    )

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

        version = int(self.get("verification_workflow_version") or 0)
        previous_version = (
            int(previous.get("verification_workflow_version") or 0)
            if previous else version
        )

        if version not in (0, 1):
            frappe.throw(_("Invalid verification workflow version."))

        if previous and previous_version != version:
            frappe.throw(_("Verification workflow version cannot be changed."))

        if version == 1:
            from engineering.engineering.report.down_time.downtime_verification import (
                build_summary,
                get_required_records,
            )

            from engineering.engineering.report.down_time.down_time import (
                get_report_windows,
            )

            report_shift = self.report_shift or "All Shifts"
            query_shift = (
                "" if report_shift == "All Shifts" else report_shift
            )

            required = get_required_records(
                self.report_date,
                self.site,
                query_shift,
            )

            expected = build_summary(
                self,
                required,
            )["overall_status"]
        else:
            expected = (
                "Closed"
                if new
                and new.engineering_user and new.date_time_e
                and new.production_user and new.date_time_p
                else "Open"
            )

        if self.status != expected:
            frappe.throw(_("Sign-off status does not match verification results."))


    def _validate_downtime_verifications(self, previous):
        fields = (
            "downtime_record",
            "department",
            "verification_status",
            "verified_by",
            "verified_on",
            "verification_role",
            "comments",
        )

        old_rows = (
            previous.get("downtime_verifications") or []
            if previous else []
        )
        new_rows = self.get("downtime_verifications") or []

        old_by_name = {row.name: row for row in old_rows}
        new_by_name = {row.name: row for row in new_rows}

        if len(old_by_name) != len(old_rows):
            frappe.throw(_("Duplicate existing verification rows found."))

        if len(new_by_name) != len(new_rows):
            frappe.throw(_("Duplicate verification row identifiers found."))

        # Historical entries must never be removed or altered.
        for name, old in old_by_name.items():
            new = new_by_name.get(name)

            if not new:
                frappe.throw(
                    _("Existing downtime verifications cannot be deleted.")
                )

            for field in fields:
                if str(old.get(field) or "") != str(new.get(field) or ""):
                    frappe.throw(
                        _("Existing downtime verifications cannot be modified.")
                    )

        added = [
            row for row in new_rows
            if row.name not in old_by_name
        ]

        if added and int(
            self.get("verification_workflow_version") or 0
        ) != 1:
            frappe.throw(
                _("Record-level verification is not enabled for this sign-off.")
            )

        if added:
            authorization = frappe.flags.get(
                "_mechanical_dt_verification_append"
            )

            if (
                not isinstance(authorization, tuple)
                or len(authorization) != 2
                or authorization[0] != self.name
                or authorization[1] not in ("Engineering", "Production")
            ):
                frappe.throw(
                    _("Downtime verifications must be submitted through the report.")
                )

            for row in added:
                if row.department != authorization[1]:
                    frappe.throw(
                        _("Verification department does not match authorization.")
                    )

                if row.verified_by != frappe.session.user:
                    frappe.throw(
                        _("Verification user does not match the session.")
                    )

                if not row.downtime_record:
                    frappe.throw(_("Missing downtime record."))

                if row.verification_status not in (
                    "Verified", "Not Verified"
                ):
                    frappe.throw(_("Invalid verification status."))

                if not row.verified_on:
                    frappe.throw(_("Verification timestamp is required."))

                from engineering.engineering.report.down_time.downtime_verification import (
                    VERIFICATION_ROLES,
                )

                if row.verification_role not in VERIFICATION_ROLES[row.department]:
                    frappe.throw(_("Invalid verification role."))

                if row.verification_role not in frappe.get_roles(
                    frappe.session.user
                ):
                    frappe.throw(_("Verification role is not assigned to user."))

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
