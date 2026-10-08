// Copyright (c) 2026, BuFf0k and contributors
// For license information, please see license.txt

function fleet_card_update_model(frm) {
	// "model" has no fetch_from (removed deliberately - fetch_from against
	// a Dynamic Link whose target doctype doesn't have the fetched field
	// throws a raw DB error in Frappe, it doesn't skip gracefully), so this
	// does the same job by hand, only when there's actually an Asset to
	// fetch it from.
	if (frm.doc.allocation_type === "Asset" && frm.doc.fleet_number) {
		frappe.db.get_value("Asset", frm.doc.fleet_number, "item_code").then((r) => {
			frm.set_value("model", (r.message && r.message.item_code) || "");
		});
	} else {
		frm.set_value("model", "");
	}
}

frappe.ui.form.on("Fleet Card", {
	setup(frm) {
		frm.set_query("allocation_type", () => ({ filters: { name: ["in", ["Asset", "Employee"]] } }));

		frm.set_query("fleet_number", () => {
			if (frm.doc.allocation_type === "Employee") {
				return { filters: { status: "Active" } };
			}
			return {
				query: "engineering.engineering.doctype.vehicle_allocation.vehicle_allocation.public_road_asset_query",
			};
		});

		frm.set_query("issued_to", () => ({ filters: { status: "Active" } }));
		frm.set_query("previous_fleet_card", () => ({
			filters: {
				allocation_type: frm.doc.allocation_type,
				fleet_number: frm.doc.fleet_number,
				docstatus: 1,
			},
		}));
	},

	allocation_type(frm) {
		// A Dynamic Link field's own options follow allocation_type
		// automatically, but any value already picked under the OLD
		// doctype is meaningless under the new one.
		frm.set_value("fleet_number", null);
	},

	fleet_number(frm) {
		fleet_card_update_model(frm);
	},

	refresh(frm) {
		fleet_card_update_model(frm);

		// Available on Draft and Submitted (not on a new, unsaved doc, nor a
		// Cancelled one — reissuing from a voided record doesn't make sense).
		if (frm.is_new() || frm.doc.docstatus === 2) {
			return;
		}

		frm.add_custom_button(__("Reissue"), () => {
			frappe.new_doc("Fleet Card", {
				allocation_type: frm.doc.allocation_type,
				fleet_number: frm.doc.fleet_number,
				registration_number: frm.doc.registration_number,
				issued_to: frm.doc.issued_to,
				bank: frm.doc.bank,
				card_number: frm.doc.card_number,
				card_limit: frm.doc.card_limit,
				covers_fuel: frm.doc.covers_fuel,
				covers_toll: frm.doc.covers_toll,
				covers_oil: frm.doc.covers_oil,
				issue_date: frappe.datetime.get_today(),
				previous_fleet_card: frm.doc.name,
			});
		});
	},
});
