import frappe
from frappe.model.document import Document

from engineering.controllers.kobelco_client import KobelcoError, validate_base_url


class APIKobelcoSettings(Document):
    def validate(self):
        try:
            self.base_url = validate_base_url(self.base_url).rstrip("/")
        except KobelcoError as error:
            frappe.throw(str(error))
        self.username = (self.username or "").strip()
        previous = self.get_doc_before_save()
        previous_rows = {row.name: row for row in (previous.machine_mappings or [])} if previous else {}
        seen = {field: set() for field in ("serial_number", "pin", "asset")}
        for row in self.machine_mappings or []:
            row.serial_number = (row.serial_number or "").strip().upper()
            row.pin = (row.pin or "").strip().upper() or None
            row.asset = row.asset or None
            if not row.serial_number:
                frappe.throw("Kobelco serial number is required.")
            old = previous_rows.get(row.name)
            if old and (old.serial_number != row.serial_number or
                        (old.pin != row.pin and not (self.flags.kobelco_discovery and not old.pin))):
                frappe.throw("Kobelco serial number and PIN cannot be changed after discovery.")
            for field in seen:
                value = row.get(field)
                if value and value in seen[field]:
                    frappe.throw(f"A Kobelco mapping already exists for this {field.replace('_', ' ')}.")
                seen[field].add(value)
            if row.asset:
                frappe.has_permission("Asset", "read", doc=row.asset, throw=True)
            row.mapping_status = "Mapped" if row.asset else "Unmapped"
        if set(previous_rows) - {row.name for row in self.machine_mappings or []}:
            frappe.throw("Discovered machines cannot be removed. Clear the Asset to mark a machine Unmapped.")

    def on_update(self):
        # Only local result links change; telemetry history and ERPNext Assets do not.
        for row in self.machine_mappings or []:
            frappe.db.set_value("Kobelco Results", {"serial_number": row.serial_number}, {
                "mapping": row.name, "asset": row.asset, "mapping_status": row.mapping_status,
            }, update_modified=False)
