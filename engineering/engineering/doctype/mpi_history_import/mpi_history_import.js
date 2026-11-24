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
    const savedRows = new Map((response.message?.vehicles || []).map(row => [row.name, row]));
    for (const row of frm.doc.vehicles || []) {
        const saved = savedRows.get(row.name);
        if (saved && saved.imei === row.imei) {
            for (const field of fields) row[field] = saved[field];
        }
    }
    frm.refresh_field("vehicles");
}

function mpi_can_select_vehicles(frm) {
    return !frm.doc.status || frm.doc.status === "Draft";
}

function mpi_add_history_vehicles(frm, vehicles) {
    if (!mpi_can_select_vehicles(frm)) return;
    const selected = new Set((frm.doc.vehicles || []).map(row => row.imei));
    const additions = vehicles.filter(row => !selected.has(row.imei));
    if (selected.size + additions.length > 500) {
        frappe.msgprint(__("Select at most 500 MPI vehicles per import."));
        return;
    }
    for (const vehicle of additions) {
        if (selected.has(vehicle.imei)) continue;
        frm.add_child("vehicles", {imei: vehicle.imei, plate: vehicle.plate, asset: vehicle.asset,
            status: "Draft", records_processed: 0});
        selected.add(vehicle.imei);
    }
    if (additions.length) {
        frm.refresh_field("vehicles");
        frm.dirty();
    }
}

async function mpi_select_history_vehicles(frm, allMapped = false) {
    if (!mpi_can_select_vehicles(frm)) return;
    const response = await frappe.call({method: "engineering.controllers.mpi_history.get_history_vehicle_options"});
    const vehicles = response.message || [];
    if (allMapped) {
        mpi_add_history_vehicles(frm, vehicles.filter(row => row.asset));
        return;
    }
    const dialog = new frappe.ui.Dialog({
        title: __("Select MPI Vehicles"),
        fields: [{fieldname: "imeis", label: __("Vehicles"), fieldtype: "MultiSelectList", reqd: 1,
            get_data(text) {
                const search = (text || "").toLowerCase();
                return vehicles.filter(row => [row.imei, row.plate, row.asset].join(" ").toLowerCase().includes(search))
                    .map(row => ({value: row.imei, description: [row.plate, row.asset].filter(Boolean).join(" / ")}));
            }}],
        primary_action_label: __("Add Selected Vehicles"),
        primary_action(values) {
            const selected = new Set(values.imeis || []);
            mpi_add_history_vehicles(frm, vehicles.filter(row => selected.has(row.imei)));
            dialog.hide();
        },
    });
    dialog.show();
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
        const editable = mpi_can_select_vehicles(frm) && !!frm.perm[0]?.write;
        if (frm.set_df_property) frm.set_df_property("vehicles", "read_only", !editable);
        if (editable) {
            frm.add_custom_button(__("Add Selected Vehicles"), () => mpi_select_history_vehicles(frm));
            frm.add_custom_button(__("Add All Mapped Vehicles"), () => mpi_select_history_vehicles(frm, true));
        }
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
