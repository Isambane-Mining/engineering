// Copyright (c) 2026, BuFf0k and contributors
// For license information, please see license.txt

frappe.ui.form.on("Engineering Legals SharePoint Config", {
	refresh(frm) {
		show_expiry_intro(frm);
		show_status_indicator(frm);

		frm.add_custom_button(__("Test Connection"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save your changes before testing."));
				return;
			}
			frappe.call({
				method: "engineering.engineering.doctype.engineering_legals_sharepoint_config.engineering_legals_sharepoint_config.test_connection",
				freeze: true,
				freeze_message: __("Contacting Microsoft..."),
				callback(r) {
					frappe.msgprint({
						title: __("Connection OK"),
						indicator: "green",
						message: __("Connected to {0}, document library {1}.", [
							r.message.site,
							r.message.drive_name,
						]),
					});
				},
				always() {
					frm.reload_doc();
				},
			});
		});
	},

	client_secret_expires_on(frm) {
		show_expiry_intro(frm);
	},
});

function show_expiry_intro(frm) {
	const expires = frm.doc.client_secret_expires_on;
	if (!expires) {
		frm.set_intro(
			__("Set <b>Client Secret Expires On</b> so you can see when the secret needs renewing."),
			"blue"
		);
		return;
	}

	const days = frappe.datetime.get_diff(expires, frappe.datetime.get_today());
	const date = frappe.datetime.str_to_user(expires);
	if (days < 0) {
		frm.set_intro(
			__("The client secret expired on {0}. SharePoint sync will fail until it is renewed - see Renewing the Client Secret below.", [date]),
			"red"
		);
	} else if (days <= 30) {
		frm.set_intro(__("The client secret expires in {0} day(s), on {1}. Renew it soon.", [days, date]), "orange");
	} else {
		frm.set_intro(__("The client secret is valid until {0} ({1} days).", [date, days]), "green");
	}
}

function show_status_indicator(frm) {
	if (frm.doc.last_status === "Success") {
		frm.page.set_indicator(__("Last sync OK"), "green");
	} else if (frm.doc.last_status === "Error") {
		frm.page.set_indicator(__("Last sync failed"), "red");
	}
}
