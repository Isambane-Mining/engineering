// Copyright (c) 2026, BuFf0k and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fleet Card Transaction", {
	setup(frm) {
		frm.set_query("fleet_card", () => ({
			filters: { docstatus: 1 },
		}));
	},
});
