frappe.ui.form.on("Pre Use Deviation", {
	refresh(frm) {
		apply_pre_use_deviation_ui(frm);
		set_fleet_number_filter(frm);
	},

	onload(frm) {
		apply_pre_use_deviation_ui(frm);
		set_fleet_number_filter(frm);
	},

	site(frm) {
		frm.set_value("fleet_number", "");
		frm.set_value("machine_type", "");
		frm.set_value("machine_model", "");

		set_fleet_number_filter(frm);
	},

	reported_by_coy_number(frm) {
		fill_reported_by_name(frm);
	},

	actioned_by_coy_number(frm) {
		fill_actioned_by_name(frm);
	},

	fleet_number(frm) {
		fill_machine_details(frm);
	},

	action_date_and_time(frm) {
		set_action_status_and_completion(frm);
		apply_completion_colour(frm);
	}
});

function set_fleet_number_filter(frm) {
	frm.set_query("fleet_number", function () {
		if (!frm.doc.site) {
			return {
				filters: {
					docstatus: 1
				}
			};
		}

		return {
			filters: {
				docstatus: 1,
				location: frm.doc.site
			}
		};
	});
}

function apply_pre_use_deviation_ui(frm) {
	hide_series_and_id(frm);
	set_action_status_and_completion(frm);
	round_completion_percentage(frm);
	apply_completion_colour(frm);
	set_fleet_number_filter(frm);

	fill_reported_by_name(frm);
	fill_actioned_by_name(frm);
	fill_machine_details(frm);
}

function hide_series_and_id(frm) {
	if (frm.fields_dict.naming_series) {
		frm.set_df_property("naming_series", "hidden", 1);
	}

	if (frm.fields_dict.document_id) {
		frm.set_df_property("document_id", "hidden", 1);
	}
}

function set_action_status_and_completion(frm) {
	if (frm.doc.action_date_and_time) {
		if (frm.fields_dict.action_status) {
			frm.set_value("action_status", "Closed");
		}
		frm.set_value("completion_percentage", 100);
	} else {
		if (frm.fields_dict.action_status) {
			frm.set_value("action_status", "Open");
		}
		frm.set_value("completion_percentage", 0);
	}

	round_completion_percentage(frm);
}

function round_completion_percentage(frm) {
	let value = cint(frm.doc.completion_percentage || 0);

	if (value >= 100) {
		value = 100;
	} else {
		value = 0;
	}

	if (frm.doc.completion_percentage !== value) {
		frm.set_value("completion_percentage", value);
	}
}

function apply_completion_colour(frm) {
	const value = cint(frm.doc.completion_percentage || 0);

	setTimeout(() => {
		const field = frm.fields_dict.completion_percentage;
		if (!field || !field.$wrapper) return;

		field.$wrapper.find(".preuse-progress-wrap").remove();

		const colour = value === 100 ? "#28a745" : "#dc3545";
		const label = value === 100 ? "100%" : "0%";

		const progress_html = `
			<div class="preuse-progress-wrap" style="margin-top: 8px;">
				<div style="
					width: 100%;
					height: 14px;
					background: #e9ecef;
					border-radius: 10px;
					overflow: hidden;
				">
					<div style="
						width: ${value}%;
						height: 14px;
						background: ${colour};
						transition: width 0.3s ease;
					"></div>
				</div>
				<div style="
					margin-top: 4px;
					font-weight: 600;
					color: ${colour};
				">${label}</div>
			</div>
		`;

		field.$wrapper.append(progress_html);
	}, 100);
}

async function fill_reported_by_name(frm) {
	if (!frm.doc.reported_by_coy_number) {
		if (frm.fields_dict.reported_by_name_and_surname) {
			frm.set_value("reported_by_name_and_surname", "");
		}
		return;
	}

	const employee_name = await get_employee_name(frm.doc.reported_by_coy_number);

	if (frm.fields_dict.reported_by_name_and_surname) {
		frm.set_value("reported_by_name_and_surname", employee_name || "");
	}
}

async function fill_actioned_by_name(frm) {
	if (!frm.doc.actioned_by_coy_number) {
		if (frm.fields_dict.actioned_by_name_and_surname) {
			frm.set_value("actioned_by_name_and_surname", "");
		}
		return;
	}

	const employee_name = await get_employee_name(frm.doc.actioned_by_coy_number);

	if (frm.fields_dict.actioned_by_name_and_surname) {
		frm.set_value("actioned_by_name_and_surname", employee_name || "");
	}
}

async function get_employee_name(coy_number) {
	// 1. If Link field stores Employee document name
	try {
		let r1 = await frappe.db.get_value("Employee", coy_number, "employee_name");
		if (r1 && r1.message && r1.message.employee_name) {
			return r1.message.employee_name;
		}
	} catch (e) {}

	// 2. If the number is stored in employee field
	const possible_fields = [
		"employee",
		"employee_number",
		"attendance_device_id",
		"custom_coy_number",
		"coy_number"
	];

	for (const fieldname of possible_fields) {
		try {
			let r2 = await frappe.db.get_value(
				"Employee",
				{ [fieldname]: coy_number },
				"employee_name"
			);

			if (r2 && r2.message && r2.message.employee_name) {
				return r2.message.employee_name;
			}
		} catch (e) {}
	}

	return "";
}

async function fill_machine_details(frm) {
	if (!frm.doc.fleet_number) {
		if (frm.fields_dict.machine_type) {
			frm.set_value("machine_type", "");
		}
		if (frm.fields_dict.machine_model) {
			frm.set_value("machine_model", "");
		}
		return;
	}

	try {
		// Fleet Number matches Asset Name in Asset doctype
		const r = await frappe.db.get_value(
			"Asset",
			{ asset_name: frm.doc.fleet_number },
			["asset_category", "item_name"]
		);

		if (r && r.message) {
			if (frm.fields_dict.machine_type) {
				frm.set_value("machine_type", r.message.asset_category || "");
			}

			if (frm.fields_dict.machine_model) {
				frm.set_value("machine_model", r.message.item_name || "");
			}
			return;
		}
	} catch (e) {}

	// fallback: try if fleet number is actually Asset document name
	try {
		const r2 = await frappe.db.get_value(
			"Asset",
			frm.doc.fleet_number,
			["asset_category", "item_name"]
		);

		if (r2 && r2.message) {
			if (frm.fields_dict.machine_type) {
				frm.set_value("machine_type", r2.message.asset_category || "");
			}

			if (frm.fields_dict.machine_model) {
				frm.set_value("machine_model", r2.message.item_name || "");
			}
			return;
		}
	} catch (e) {}

	if (frm.fields_dict.machine_type) {
		frm.set_value("machine_type", "");
	}
	if (frm.fields_dict.machine_model) {
		frm.set_value("machine_model", "");
	}
}
