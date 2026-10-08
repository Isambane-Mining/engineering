frappe.query_reports["Fleet Compliance Overview"] = {
	filters: [
		{
			fieldname: "location",
			label: "Location",
			fieldtype: "Link",
			options: "Location",
		},
		{
			fieldname: "driver",
			label: "Driver",
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "asset_category",
			label: "Asset Category",
			fieldtype: "Link",
			options: "Asset Category",
		},
		{
			fieldname: "overall_status",
			label: "Overall Status",
			fieldtype: "Select",
			options: "\nCompliant\nAttention Required\nNon-Compliant\nNot Registered",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		const status_columns = {
			overall_status: {
				Compliant: "green",
				"Attention Required": "orange",
				"Non-Compliant": "red",
				"Not Registered": "grey",
			},
			driver_licence_status: {
				Valid: "green",
				Expiring: "orange",
				Incomplete: "blue",
				Expired: "red",
				Outstanding: "red",
			},
			vehicle_licence_status: {
				Valid: "green",
				Expiring: "orange",
				Incomplete: "blue",
				Expired: "red",
				Outstanding: "red",
			},
			fleet_card_status: {
				Valid: "green",
				"None Issued": "green",
				Expiring: "orange",
				Incomplete: "blue",
				Expired: "red",
				Outstanding: "red",
			},
			addendum_status: {
				"On File": "green",
				Outstanding: "red",
			},
		};

		const colour_map = status_columns[column.fieldname];

		if (colour_map) {
			const colour = colour_map[data[column.fieldname]];

			if (colour) {
				value = `<span style="color: ${colour}; font-weight: 600;">${value}</span>`;
			}
		}

		return value;
	},
};
