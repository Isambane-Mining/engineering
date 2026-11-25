function bell_settings_action(frm, method, label) {
    if (frm.is_dirty()) {
        frappe.msgprint(__("Save Bell Settings before contacting the API."));
        return;
    }

    frappe.call({
        method: `engineering.controllers.bell.${method}`,
        type: "POST",
        freeze: true,
        freeze_message: __("Contacting Bell..."),
        callback(r) {
            if (!r.message) return;

            frappe.msgprint({
                title: __(label),
                indicator: r.message.ok ? "green" : "red",
                message: frappe.utils.escape_html(
                    r.message.message || "Operation completed."
                )
            });

            frm.reload_doc();
        }
    });
}

frappe.ui.form.on("API Bell Settings", {
    refresh(frm) {
        const can_write = frm.perm.some(p => p.write);

        frm.fields_dict.test_connection.$input?.prop("disabled", !can_write);
        frm.fields_dict.fetch_fleet.$input?.prop(
            "disabled", !can_write || !frm.doc.enabled
        );
        frm.fields_dict.sync_now.$input?.prop(
            "disabled", !can_write || !frm.doc.enabled
        );

        frm.fields_dict.machine_mappings.grid.cannot_add_rows = true;
        frm.fields_dict.machine_mappings.grid.cannot_delete_rows = true;

        frm.fields_dict.username.$input?.attr("autocomplete", "off");
        frm.fields_dict.password.$input?.attr("autocomplete", "new-password");
        frm.fields_dict.client_secret.$input?.attr("autocomplete", "new-password");

        frappe.meta.get_docfield(
            "Bell Machine Mapping", "mapping_status"
        ).formatter = value => {
            const mapped = value === "Mapped";
            return `<span class="indicator-pill ${mapped ? "green" : "orange"}">${mapped ? __("Mapped") : __("Unmapped")}</span>`;
        };

        frm.add_custom_button(
            __("Results"),
            () => frappe.set_route("List", "Bell Results")
        );
    },

    enabled(frm) {
        frm.refresh_fields();
    },

    test_connection(frm) {
        bell_settings_action(frm, "test_connection", "Test Connection");
    },

    fetch_fleet(frm) {
        bell_settings_action(frm, "fetch_fleet", "Fetch Fleet");
    },

    sync_now(frm) {
        bell_settings_action(frm, "sync_now", "Sync Now");
    }
});

frappe.ui.form.on("Bell Machine Mapping", {
    asset(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        frappe.model.set_value(
            cdt, cdn, "mapping_status",
            row.asset ? "Mapped" : "Unmapped"
        );
    }
});

frappe.ui.form.on("API Bell Settings", {
    pull_fault_codes(frm) {
        bell_settings_action(frm, "pull_fault_codes", "Pull Fault Codes");
    },

    pull_fuel_consumption(frm) {
        bell_settings_action(frm, "pull_fuel_consumption", "Pull Fuel Consumption");
    }
});

frappe.ui.form.on("API Bell Settings", {
    refresh(frm) {
        [
            "fault_codes_status",
            "fuel_consumption_status"
        ].forEach(fieldname => {
            const df = frappe.meta.get_docfield(
                "Bell Machine Mapping", fieldname
            );

            if (df) {
                df.formatter = value => {
                    const color = value === "Not Reporting"
                        ? "red"
                        : value === "Reporting"
                            ? "green"
                            : "gray";

                    return `<span class="indicator-pill ${color}">
                        ${__(value || "Not Checked")}
                    </span>`;
                };
            }
        });
    }
});

frappe.ui.form.on("API Bell Settings", {
    view_fault_code_records(frm) {
        frappe.set_route("List", "Bell Equipment Fault Codes");
    },

    view_fuel_consumption_records(frm) {
        frappe.set_route("List", "Bell Equipment Fuel Consumption");
    },

    view_active_regeneration_records(frm) {
        frappe.set_route("List", "Bell Results");
    }
});

frappe.ui.form.on("API Bell Settings", {
    pull_operating_hours_now(frm) {
        bell_settings_action(
            frm,
            "pull_operating_hours_now",
            "Pull Operating Hours"
        );
    }
});
