// Copyright (c) 2026, BuFf0k and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fleet Card", {
	setup(frm) {
		frm.set_query("fleet_number", () => ({
			query: "engineering.engineering.doctype.vehicle_allocation.vehicle_allocation.public_road_asset_query",
		}));
	},

	refresh(frm) {
		// Available on Draft and Submitted (not on a new, unsaved doc, nor a
		// Cancelled one — reissuing from a voided record doesn't make sense).
		if (frm.is_new() || frm.doc.docstatus === 2) {
			return;
		}

		frm.add_custom_button(__("Reissue"), () => {
			frappe.new_doc("Fleet Card", {
				fleet_number: frm.doc.fleet_number,
				registration_number: frm.doc.registration_number,
				bank: frm.doc.bank,
				card_number: frm.doc.card_number,
				card_limit: frm.doc.card_limit,
				covers_fuel: frm.doc.covers_fuel,
				covers_toll: frm.doc.covers_toll,
				covers_oil: frm.doc.covers_oil,
				issue_date: frappe.datetime.get_today(),
			});
		});
	},
});
