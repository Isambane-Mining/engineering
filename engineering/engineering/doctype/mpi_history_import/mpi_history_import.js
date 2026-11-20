async function mpi_refresh_import_status(frm) {
    const response = await frappe.call({
        method: "engineering.controllers.mpi_history.get_import_status",
        args: {request_name: frm.doc.name},
    });
    const fields = ["status", "started_at", "completed_at", "records_processed", "endpoint_outcomes", "last_error"];
    for (const [field, value] of Object.entries(response.message || {})) {
        if (fields.includes(field)) {
            frm.doc[field] = value;
            frm.refresh_field(field);
        }
    }
}

frappe.ui.form.on("MPI History Import", {
    onload(frm) {
        if (frm.is_new() && !frm.doc.start_date && !frm.doc.end_date) {
            const yesterday = new Date();
            yesterday.setUTCDate(yesterday.getUTCDate() - 1);
            const utcDate = yesterday.toISOString().slice(0, 10);
            frm.set_value({start_date: utcDate, end_date: utcDate});
        }
    },
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__("Refresh Import Status"), () => mpi_refresh_import_status(frm));
        if (frm.perm[0]?.write) {
            frm.add_custom_button(__("Import History"), async () => {
                if (frm.is_dirty()) {
                    frappe.msgprint(__("Save this request before importing history."));
                    return;
                }
                await frappe.call({
                    method: "engineering.controllers.mpi_history.enqueue_import",
                    args: {request_name: frm.doc.name},
                    freeze: true,
                    freeze_message: __("Queuing MPI history import..."),
                });
                await mpi_refresh_import_status(frm);
                frappe.msgprint(__("History import is queued. Use Refresh Import Status to review the outcome."));
            });
        }
    },
});
