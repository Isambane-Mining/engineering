frappe.listview_settings["Fleet Card Transaction Import"] = {
	get_indicator(doc) {
		const colors = {
			"Not Parsed": "grey",
			"Missing Information": "orange",
			"Pending Import": "blue",
			Importing: "yellow",
			"Partially Imported": "orange",
			Completed: "green",
			Error: "red",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
