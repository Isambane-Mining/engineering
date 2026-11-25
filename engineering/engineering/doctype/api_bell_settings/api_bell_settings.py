from urllib.parse import urlparse
from datetime import datetime
from zoneinfo import ZoneInfo

import frappe
from frappe.model.document import Document


class APIBellSettings(Document):

    def validate(self):
        self._validate_configuration()
        self._validate_mappings()
        self._validate_operating_hours_schedule()

    def _validate_operating_hours_schedule(self):
        seen = set()

        for row in self.operating_hours_schedule or []:
            if not row.enabled:
                continue

            key = (row.site, row.day_of_week, row.shift)
            if key in seen:
                frappe.throw(
                    f"Duplicate operating-hours schedule: {row.site}, "
                    f"{row.day_of_week}, {row.shift}."
                )
            seen.add(key)

            if row.shift_start == row.shift_end:
                frappe.throw(
                    f"Shift start and end cannot be identical for {row.site}."
                )

            if row.pull_time is None:
                frappe.throw(
                    f"Pull time is required for {row.site}, {row.day_of_week}."
                )

    def _validate_configuration(self):
        approved = {
            "token_url": "sso.bellequipment.com",
            "fleet_url": "b-fleet03.bellequipment.com",
        }

        for fieldname, hostname in approved.items():
            value = (self.get(fieldname) or "").strip()
            parsed = urlparse(value)

            if parsed.scheme != "https" or parsed.hostname != hostname:
                frappe.throw(f"Invalid Bell {fieldname.replace('_', ' ')}.")

            if parsed.username or parsed.password:
                frappe.throw("Credentials must not be included in API URLs.")

            self.set(fieldname, value)

        for fieldname in ("client_id", "username", "scope"):
            self.set(fieldname, (self.get(fieldname) or "").strip())

        try:
            timeout = int(self.timeout or 30)
        except (ValueError, TypeError):
            frappe.throw("Bell connection timeout must be a number.")

        if not 5 <= timeout <= 120:
            frappe.throw("Bell connection timeout must be between 5 and 120 seconds.")

        self.timeout = timeout

    def _validate_mappings(self):
        previous = self.get_doc_before_save()
        previous_rows = {
            row.name: row
            for row in (previous.machine_mappings or [])
        } if previous else {}

        seen = {
            "equipment_id": set(),
            "pin": set(),
            "serial_number": set(),
            "asset": set(),
        }

        for row in self.machine_mappings or []:
            for fieldname in ("equipment_id", "pin", "serial_number", "oem", "model"):
                value = (row.get(fieldname) or "").strip()
                row.set(fieldname, value or None)

            row.pin = row.pin.upper() if row.pin else None
            row.serial_number = row.serial_number.upper() if row.serial_number else None

            if not row.pin and not row.serial_number:
                frappe.throw("Each Bell mapping requires a PIN or serial number.")

            old = previous_rows.get(row.name)

            if old:
                for fieldname in ("equipment_id", "pin", "serial_number"):
                    old_value = old.get(fieldname)
                    new_value = row.get(fieldname)

                    if old_value and old_value != new_value:
                        frappe.throw(
                            "Discovered Bell machine identifiers cannot be changed."
                        )

            for fieldname in seen:
                value = row.get(fieldname)
                if value:
                    if value in seen[fieldname]:
                        frappe.throw(
                            f"Duplicate Bell mapping for {fieldname.replace('_', ' ')}."
                        )
                    seen[fieldname].add(value)

            if row.asset:
                frappe.has_permission(
                    "Asset", "read", doc=row.asset, throw=True
                )

            row.mapping_status = "Mapped" if row.asset else "Unmapped"

        if previous_rows and set(previous_rows) - {
            row.name for row in self.machine_mappings or []
        }:
            frappe.throw(
                "Discovered Bell machines cannot be deleted from the mapping table."
            )

    def on_update(self):
        today = datetime.now(
            ZoneInfo("Africa/Johannesburg")
        ).strftime("%Y%m%d")

        for row in self.machine_mappings or []:
            records = frappe.get_all(
                "Bell Results",
                filters={"mapping": row.name},
                fields=["name", "fetched_at", "pin", "serial_number"],
            )

            for record in records:
                day = (
                    record.fetched_at.strftime("%Y%m%d")
                    if record.fetched_at else today
                )

                identifier = row.pin or record.pin or row.serial_number or record.serial_number
                prefix = row.asset or "UNMAPPED-" + identifier.upper()
                new_name = f"{prefix}-{day}"
                current_name = record.name

                if current_name != new_name:
                    if frappe.db.exists("Bell Results", new_name):
                        frappe.throw(
                            f"Bell daily result {new_name} already exists. "
                            "Check duplicate Asset mappings."
                        )

                    frappe.rename_doc(
                        "Bell Results", current_name, new_name, force=True
                    )
                    current_name = new_name

                frappe.db.set_value(
                    "Bell Results",
                    current_name,
                    {
                        "external_key": current_name,
                        "asset": row.asset,
                        "mapping": row.name,
                        "mapping_status": row.mapping_status,
                    },
                    update_modified=False,
                )
