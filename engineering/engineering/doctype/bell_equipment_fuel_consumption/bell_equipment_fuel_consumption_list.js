frappe.listview_settings["Bell Equipment Fuel Consumption"] = {
    add_fields: ["asset", "fuel_consumed", "fuel_units", "measurement_timestamp"],
    get_indicator(doc) {
        return [__("Fuel Reading"), "blue", "fuel_consumed,>=,0"];
    }
};
