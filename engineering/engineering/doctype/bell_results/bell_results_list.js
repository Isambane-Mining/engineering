frappe.listview_settings["Bell Results"] = {
    add_fields: [
        "equipment_id",
        "pin",
        "model",
        "asset",
        "operating_hours",
        "fleet_snapshot_timestamp",
        "mapping_status"
    ],

    get_indicator(doc) {
        if (doc.mapping_status === "Mapped") {
            return [__("Mapped"), "green", "mapping_status,=,Mapped"];
        }

        return [__("Unmapped"), "orange", "mapping_status,=,Unmapped"];
    }
};
