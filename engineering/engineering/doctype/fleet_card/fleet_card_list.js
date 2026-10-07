frappe.listview_settings["Fleet Card"] = {
	// status/days_left are virtual (computed live from expiry_date, and — for
	// "Superseded" — from sibling records), so they aren't available in bulk
	// list-view queries. This gives a close approximation from expiry_date
	// alone; open the record for the fully accurate status.
	add_fields: ["expiry_date", "docstatus"],
	get_indicator(doc) {
		if (doc.docstatus === 2) {
			return [__("Cancelled"), "grey", "docstatus,=,2"];
		}

		if (!doc.expiry_date) {
			return [__("Active"), "green"];
		}

		const days_left = frappe.datetime.get_diff(doc.expiry_date, frappe.datetime.get_today());

		if (days_left < 0) {
			return [__("Expired"), "red"];
		}

		if (days_left <= 90) {
			return [__("Expiring"), "orange"];
		}

		return [__("Active"), "green"];
	},
};
