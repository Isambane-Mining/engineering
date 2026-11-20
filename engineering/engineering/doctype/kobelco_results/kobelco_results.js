frappe.ui.form.on("Kobelco Results", {
    async refresh(frm) {
        await frappe.require("/assets/engineering/js/kobelco_telemetry_format.js");
        for (const df of frm.meta.fields.filter(field => field.fieldtype === "Datetime")) {
            frappe.meta.get_docfield(frm.doctype, df.fieldname).formatter = frappe.kobelco_telemetry.format_datetime;
            const control = frm.fields_dict[df.fieldname];
            control.df.formatter = frappe.kobelco_telemetry.format_datetime;
            control.df.hide_timezone = true;
            control.df.description = __("Stored in UTC. Displayed in Africa/Johannesburg.");
            control.set_description();
            control.refresh();
        }
        if (frappe.model.can_read("API Kobelco Settings")) {
            frm.add_custom_button(__("Machine Mapping"), () => {
                frappe.route_options = {scroll_to: "machine_mappings"};
                frappe.set_route("Form", "API Kobelco Settings", "API Kobelco Settings");
            });
        }
        frm.set_intro(__("Timestamps are stored in UTC and displayed in Africa/Johannesburg. Missing measurements remain empty; a reported zero is shown as zero. Original machine JSON and complete Fleet JSON are retained below."));
    },
});
