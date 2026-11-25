frappe.ui.form.on("API MPI Settings", {
    setup(frm) {
        frm.get_field("vehicles").grid.cannot_add_rows = true;
        frm.get_field("vehicles").df.cannot_delete_rows = true;
    },
    refresh(frm) {
        frm.add_custom_button(__("Refresh Sync Status"), async () => {
            const response = await frappe.call({method: "engineering.controllers.mpi.get_sync_status"});
            // Update only server-owned display fields. Do not reload the document,
            // change its revision or clear its dirty state and unsaved edits.
            for (const [field, value] of Object.entries(response.message || {})) {
                if (["last_attempt", "last_success", "last_error", "vehicle_list_outcome", "status_outcome"].includes(field)) {
                    frm.doc[field] = value;
                    frm.refresh_field(field);
                }
            }
        });
        if (!frm.is_new() && frm.perm[0]?.write) {
            frm.add_custom_button(__("Import History"), () => {
                frappe.new_doc("MPI History Import");
            });
            frm.add_custom_button(__("Fetch Fleet"), async () => {
                if (frm.is_dirty()) {
                    frappe.msgprint(__("Save the MPI settings and mapping changes before fetching the fleet."));
                    return;
                }
                const response = await frappe.call({
                    method: "engineering.controllers.mpi.fetch_fleet",
                    freeze: true,
                    freeze_message: __("Fetching MPI vehicle list..."),
                });
                const result = response.message || {};
                if (result.ok) {
                    frappe.show_alert({message: __(result.message), indicator: "green"});
                    await frm.reload_doc();
                } else {
                    frappe.msgprint(result.message || __("MPI fleet fetch failed."));
                }
            });
            frm.add_custom_button(__("Sync Now"), async () => {
                if (frm.is_dirty()) {
                    frappe.msgprint(__("Save the MPI settings and mapping changes before syncing."));
                    return;
                }
                const response = await frappe.call({
                    method: "engineering.controllers.mpi.sync_now",
                    freeze: true,
                    freeze_message: __("Queuing MPI sync..."),
                });
                if (response.message?.queued) {
                    frappe.msgprint(__("MPI sync is queued. Use Refresh Sync Status after the job finishes. Your unsaved edits will be preserved."));
                }
            });
        }
    },
});
