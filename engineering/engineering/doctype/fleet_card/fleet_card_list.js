frappe.listview_settings["Fleet Card"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			Active: "green",
			Expiring: "orange",
			Expired: "red",
			Superseded: "grey",
			Cancelled: "grey",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},

	onload(listview) {
		listview.page.add_inner_button(__("Export to Excel"), () => {
			frappe.call({
				method: "engineering.engineering.doctype.fleet_card.fleet_card.export_fleet_card_assignments_xlsx",
				freeze: true,
				freeze_message: __("Building Excel file…"),
				callback(r) {
					if (!r || !r.message || !r.message.content) return;

					const filename = r.message.filename || "fleet_card_assignments.xlsx";
					const mime =
						r.message.type ||
						"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

					download_base64_file_fleet_card(r.message.content, filename, mime);
				},
			});
		});
	},
};

function download_base64_file_fleet_card(base64_content, filename, mime_type) {
	const byte_chars = atob(base64_content);
	const byte_numbers = new Array(byte_chars.length);

	for (let i = 0; i < byte_chars.length; i++) {
		byte_numbers[i] = byte_chars.charCodeAt(i);
	}

	const byte_array = new Uint8Array(byte_numbers);
	const blob = new Blob([byte_array], { type: mime_type });
	const url = window.URL.createObjectURL(blob);

	const link = document.createElement("a");
	link.href = url;
	link.download = filename;

	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);

	window.URL.revokeObjectURL(url);
}
