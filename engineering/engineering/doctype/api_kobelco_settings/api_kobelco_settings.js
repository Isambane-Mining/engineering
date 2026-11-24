function kobelco_settings_action(frm, method, label) {
    if (frm.is_dirty()) {
        frappe.msgprint(__("Save the settings before contacting Kobelco."));
        return;
    }
    frappe.call({
        method: `engineering.controllers.kobelco.${method}`,
        type: "POST",
        freeze: true,
        freeze_message: __("Contacting Kobelco..."),
        callback(r) {
            if (!r.message) return;
            frappe.msgprint({
                title: __(label),
                indicator: r.message.ok ? "green" : "red",
                message: frappe.utils.escape_html(r.message.message),
            });
            frm.reload_doc();
        },
    });
}

frappe.ui.form.on("API Kobelco Settings", {
    setup(frm) {
        frappe.meta.get_docfield("Kobelco Machine Mapping", "mapping_status").formatter = (value) => {
            const mapped = value === "Mapped";
            return `<span class="indicator-pill ${mapped ? "green" : "orange"}">${mapped ? __("Mapped") : __("Unmapped")}</span>`;
        };
    },
    refresh(frm) {
        const can_write = frm.perm.some((permission) => permission.write);
        frm.fields_dict.test_connection.$input?.prop("disabled", !can_write);
        frm.fields_dict.fetch_fleet.$input?.prop("disabled", !can_write || !frm.doc.enabled);
        frm.fields_dict.machine_mappings.grid.cannot_add_rows = true;
        frm.fields_dict.machine_mappings.grid.cannot_delete_rows = true;
        // Use native form controls; prevent browser password-manager autofill.
        frm.fields_dict.username.$input?.attr("autocomplete", "off");
        frm.fields_dict.password.$input?.attr("autocomplete", "new-password");
        frm.add_custom_button(__("Results"), () => frappe.set_route("List", "Kobelco Results"));
        if (can_write && frm.doc.enabled) {
            frm.add_custom_button(__("Sync Now"), () => kobelco_settings_action(frm, "sync_now", "Sync Now"));
        }
    },
    enabled(frm) {
        frm.fields_dict.fetch_fleet.$input?.prop("disabled", !frm.doc.enabled || !frm.perm.some((permission) => permission.write));
    },
    test_connection(frm) {
        kobelco_settings_action(frm, "test_connection", "Test Connection");
    },
    fetch_fleet(frm) {
        kobelco_settings_action(frm, "fetch_fleet", "Fetch Fleet");
    },
});

frappe.ui.form.on("Kobelco Machine Mapping", {
    asset(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, "mapping_status", row.asset ? "Mapped" : "Unmapped");
    },
});
