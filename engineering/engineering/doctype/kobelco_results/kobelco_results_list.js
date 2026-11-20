frappe.listview_settings["Kobelco Results"] = {
    add_fields: ["mapping_status"],
    get_indicator(doc) {
        return doc.mapping_status === "Mapped"
            ? [__("Mapped"), "green", "mapping_status,=,Mapped"]
            : [__("Unmapped"), "orange", "mapping_status,=,Unmapped"];
    },
    async onload(listview) {
        await frappe.require("/assets/engineering/js/kobelco_telemetry_format.js");
        listview.settings.formatters = listview.settings.formatters || {};
        listview.settings.formatters.snapshot_timestamp = frappe.kobelco_telemetry.format_datetime;
        listview.refresh();
        if (frappe.model.can_read("API Kobelco Settings")) {
            listview.page.add_inner_button(__("Machine Mapping"), () => {
                frappe.route_options = {scroll_to: "machine_mappings"};
                frappe.set_route("Form", "API Kobelco Settings", "API Kobelco Settings");
            });
        }
        if (!frappe.model.can_write("API Kobelco Settings")) return;
        listview.page.add_inner_button(__("Sync Now"), () => {
            frappe.call({
                method: "engineering.controllers.kobelco.sync_now",
                type: "POST",
                freeze: true,
                freeze_message: __("Syncing Kobelco fleet..."),
                callback(r) {
                    if (!r.message) return;
                    frappe.msgprint({
                        title: __("Kobelco Sync"),
                        indicator: r.message.ok ? "green" : "red",
                        message: frappe.utils.escape_html(r.message.message),
                    });
                    listview.refresh();
                },
            });
        });
    },
};
