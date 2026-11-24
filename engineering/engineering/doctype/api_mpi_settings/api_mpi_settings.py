import frappe
from frappe.model.document import Document


class APIMPISettings(Document):
    def before_validate(self):
        from engineering.controllers.mpi import SYNC_FIELDS

        previous = self.get_doc_before_save()
        if not previous:
            return
        # Background status never changes the form revision. An older form must
        # therefore retain current server-owned status and newly discovered rows.
        for field in SYNC_FIELDS:
            self.set(field, previous.get(field))
        submitted = {row.imei: row for row in self.vehicles}
        for current in previous.vehicles:
            row = submitted.get(current.imei)
            if row is None:
                # Frappe has already timestamped submitted children before this
                # hook. Preserve audit/custom fields when restoring an existing
                # discovered row, and timestamp it as part of this user save.
                values = current.as_dict()
                values.update(modified=self.modified, modified_by=self.modified_by)
                self.append("vehicles", values)
            else:
                for field in ("name", "plate", "vehicle_name", "mapping_status", "suggested_assets"):
                    row.set(field, current.get(field))

    def validate(self):
        from engineering.controllers.mpi import validate_configuration

        validate_configuration(self.endpoint, self.node)
        seen = set()
        previous = self.get_doc_before_save()
        old_assets = {row.name: row.asset for row in previous.vehicles} if previous else {}
        for row in self.vehicles:
            row.imei = str(row.imei or "").strip()
            if not row.imei.isdigit() or len(row.imei) > 32:
                frappe.throw("MPI IMEI must contain 1–32 digits.")
            if row.imei in seen:
                frappe.throw("Each MPI IMEI may appear only once in Vehicle Mapping.")
            seen.add(row.imei)
            if row.asset != old_assets.get(row.name):
                row.mapping_status = "Manual" if row.asset else "Unmatched"

    def on_update(self):
        # Review decisions take effect on existing results immediately.
        for row in self.vehicles:
            if frappe.db.exists("MPI Results", row.imei):
                frappe.db.set_value("MPI Results", row.imei, {"mapping": row.name, "asset": row.asset}, update_modified=False)
