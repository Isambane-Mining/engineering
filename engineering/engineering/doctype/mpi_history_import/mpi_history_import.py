import frappe
from frappe.model.document import Document

from engineering.controllers.mpi_history import MPIError, PARAMETERS, STATUS_FIELDS, utc_windows


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

    def validate(self):
        try:
            utc_windows(self.start_date, self.end_date)
        except MPIError as error:
            frappe.throw(str(error))
        self.imei = str(self.imei or "").strip()
        if not self.imei.isascii() or not self.imei.isdigit() or len(self.imei) > 32:
            frappe.throw("Enter a valid mapped MPI IMEI.")
        previous = self.get_doc_before_save()
        if previous and previous.status != "Draft":
            if any(str(self.get(field) or "") != str(previous.get(field) or "") for field in PARAMETERS):
                frappe.throw("Create another history request to change parameters after queuing.")
