frappe.listview_settings["Bell Equipment Fault Codes"] = {
    add_fields: ["asset", "fault_code", "occurred_at", "pin"],
    get_indicator(doc) {
        return [__("Fault Event"), "orange", "fault_code,!=,"];
    }
};
