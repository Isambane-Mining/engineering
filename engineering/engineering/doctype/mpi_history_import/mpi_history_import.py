import frappe
from frappe.model.document import Document

from engineering.controllers.mpi_history import MPIError, PARAMETERS, SETTINGS, STATUS_FIELDS, _mapping, import_vehicles, utc_windows


def _selection(doc):
    return [(row.name, row.imei, row.plate, row.asset) for row in doc.get("vehicles") or []]


class MPIHistoryImport(Document):
    def before_validate(self):
        previous = self.get_doc_before_save()
        if previous:
            # Status refresh/background writes never invalidate the user's form revision.
            for field in STATUS_FIELDS:
                self.set(field, previous.get(field))
        else:
            self.status = "Draft"
            self.records_processed = 0
        saved_rows = {row.name: row for row in previous.get("vehicles") or []} if previous else {}
        for row in self.get("vehicles") or []:
            saved = saved_rows.get(row.name)
            for field in STATUS_FIELDS:
                row.set(field, saved.get(field) if saved else ("Draft" if field == "status" else 0 if field == "records_processed" else None))

    def validate(self):
        try:
            utc_windows(self.start_date, self.end_date)
            import_vehicles(self)
        except MPIError as error:
            frappe.throw(str(error))
        previous = self.get_doc_before_save()
        if previous and previous.status != "Draft":
            if (_selection(self) != _selection(previous)
                    or any(str(self.get(field) or "") != str(previous.get(field) or "") for field in PARAMETERS)):
                frappe.throw("Create another history request to change parameters after queuing.")
        else:
            settings = frappe.get_single(SETTINGS)
            settings.check_permission("write")
            try:
                rows = import_vehicles(self, settings)
                for row in rows:
                    mapping = _mapping(settings, row.imei)
                    row.plate, row.asset = mapping.plate, mapping.asset
            except MPIError as error:
                frappe.throw(str(error))
