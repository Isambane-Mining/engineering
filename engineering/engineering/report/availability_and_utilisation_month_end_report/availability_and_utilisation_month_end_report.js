// Copyright (c) 2026, BuFf0k and contributors
// For license information, please see license.txt



window.au_month_end_format_minutes = function(total_minutes) {
	total_minutes = Math.round(flt(total_minutes || 0));

	const hours = Math.floor(total_minutes / 60);
	const minutes = total_minutes % 60;

	if (hours && minutes) {
		return `${hours}h ${minutes}m`;
	}

	if (hours) {
		return `${hours}h`;
	}

	return `${minutes}m`;
};

window.au_month_end_format_hours_minutes = function(hours_value) {
	return window.au_month_end_format_minutes(flt(hours_value || 0) * 60);
};


window.au_month_end_update_target_legend = function() {
	const report = frappe.query_report;

	if (!report || !report.page) {
		return;
	}

	const target_filter =
		report.get_filter_value("au_target_filter") ||
		"85% A & U";

	const target =
		target_filter === "85% A & U" ? 85 : 100;

	const warning = target - 10;

	let legend = report.page.main.find(
		".au-target-colour-legend"
	);

	if (!legend.length) {
		legend = $(`
			<div class="au-target-colour-legend"></div>
		`).prependTo(report.page.main);
	}

	legend.html(`
		<div style="
			display:flex;
			gap:16px;
			flex-wrap:wrap;
			align-items:center;
			padding:10px 12px;
			margin:10px 0;
			border:1px solid #d8dde2;
			border-radius:8px;
			background:#ffffff;
			font-size:12px;
			font-weight:700;
		">
			<strong>Colour Legend (${target_filter}):</strong>

			<span>
				<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#dcfce7;border:2px solid #1e8e3e;vertical-align:middle;margin-right:5px;"></span>
				Green: ≥ ${target}%
			</span>

			<span>
				<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#dbeafe;border:2px solid #1a73e8;vertical-align:middle;margin-right:5px;"></span>
				Blue: ${warning}% – <${target}%
			</span>

			<span>
				<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#fee2e2;border:2px solid #d93025;vertical-align:middle;margin-right:5px;"></span>
				Red: <${warning}%
			</span>
		</div>
	`);
};


frappe.query_reports["Availability and Utilisation Month End Report"] = {
	onload: function() {
		setTimeout(
			window.au_month_end_update_target_legend,
			0
		);
	},

	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start()
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end()
		},
		{
			fieldname: "location",
			label: __("Production Site"),
			fieldtype: "Link",
			options: "Location"
		},
		{
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Select",
			options: `All Equipment
ADT
Dozer
Excavator
Grader
Service Truck
TLB
Water Bowser
Diesel Bowsers
Drills
Loader`,
                        default: "All Equipment"
		},
		{
			fieldname: "machine_scope",
			label: __("Machine Filter"),
			fieldtype: "Select",
			options: [
				"Production Machines",
				"Swing/Spare Machines",
				"Production + Swing/Spare Machines"
			].join("\n"),
			default: "Production + Swing/Spare Machines",
			reqd: 1,
			on_change: function() {
				frappe.query_report.refresh();
			}
		},
		{
			fieldname: "asset_ownership",
			label: __("Asset Ownership"),
			fieldtype: "Select",
			options: [
				"Isambane & Excavo Assets",
				"Suppliers Assets",
				"All Assets"
			].join("\n"),
			default: "Isambane & Excavo Assets",
			reqd: 1,
			on_change: function() {
				frappe.query_report.refresh();
			}
		},
		{
			fieldname: "au_target_filter",
			label: __("A & U Target"),
			fieldtype: "Select",
			options: [
				"100% A & U",
				"85% A & U"
			].join("\n"),
			default: "85% A & U",
			reqd: 1,
			on_change: function() {
				window.au_month_end_update_target_legend();
				frappe.query_report.refresh();
			}
		}
	],

	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) {
			return value;
		}




		if (data.is_separator) {
			return "";
		}

		const is_na_percentage = (
			["avail_percent", "util_percent"].includes(column.fieldname)
			&& (
				data[column.fieldname] === null
				|| data[column.fieldname] === undefined
				|| data[column.fieldname] === ""
			)
		);

		if (is_na_percentage) {
			value = `
				<span style="
					display:inline-block;
					min-width:70px;
					text-align:center;
					padding:4px 10px;
					border-radius:999px;
					background:#e5e7eb;
					color:#4b5563;
					font-weight:700;
					font-size:12px;
				">
					N/A
				</span>
			`;
		}


		if (column.fieldname === "mechanical_downtime" && data[column.fieldname] != null) {
			value = window.au_month_end_format_hours_minutes(data[column.fieldname]);
		}


		if (column.fieldname === "breakdown_reason" || column.fieldname === "other_delay_reason") {
			const detail_field = column.fieldname === "breakdown_reason"
				? "breakdown_reason_details"
				: "other_delay_reason_details";

			let details = data[detail_field] || [];

			if (!details.length && data[column.fieldname]) {
				details = [{
					date: "",
					reason: data[column.fieldname]
				}];
			}

			if (!details.length) {
				return "";
			}

			window.au_month_end_reason_details = window.au_month_end_reason_details || {};

			const key = `${column.fieldname}-${data.asset_name || ""}-${Math.random()}`;

			window.au_month_end_reason_details[key] = {
				details: details
			};

			const title = column.fieldname === "breakdown_reason"
				? "Breakdown Reasons"
				: "Other Delay Reasons";

			const button_style = data.is_spare_swing_unit
				? "background:#e6d6ff;color:#4b0082;border:1px solid #7b2cbf;"
				: "background:#dbeafe;color:#1d4ed8;border:1px solid #2563eb;";

			return `
				<button class="btn btn-xs"
					style="
						${button_style}
						font-weight:800;
						border-radius:999px;
						padding:3px 12px;
					"
					onclick="window.show_au_month_end_reason_dialog('${key}', '${title}', '${frappe.utils.escape_html(data.asset_name || '')}', '${data.is_spare_swing_unit ? "purple" : "blue"}')">
					View
				</button>
			`;
		}

		if (data.is_scope_total) {
			const is_spare =
				data.summary_scope === "spare";

			const is_production =
				data.summary_scope === "production";

			let background = "#f8fafc";
			let colour = "#0f172a";
			let border = "#94a3b8";

			if (is_production) {
				background = "#dbeafe";
				colour = "#1e3a8a";
				border = "#3b82f6";
			}

			if (is_spare) {
				background = "#e6d6ff";
				colour = "#4b0082";
				border = "#7b2cbf";
			}

			let display_value = value;

			if (
				column.fieldname ===
					"asset_category" &&
				data.summary_label
			) {
				display_value =
					frappe.utils.escape_html(
						data.summary_label
					);
			}

			if (
				display_value == null ||
				String(display_value).trim() === ""
			) {
				display_value = "&nbsp;";
			}

			return `
				<span style="
					display:block;
					margin:-8px -10px;
					padding:8px 10px;
					min-height:100%;
					background:${background};
					color:${colour};
					font-weight:900;
					border-left:4px solid ${border};
				">
					${display_value}
				</span>
			`;
		}


		if (data.is_spare_swing_unit) {
			const reason = data.spare_swing_reason || "Spare/Swing unit in Monthly Production Planning";

			return `
				<span style="
					display: block;
					margin: -8px -10px;
					padding: 8px 10px;
					background: #e6d6ff;
					color: #4b0082;
					font-weight: 700;
					border-left: 3px solid #7b2cbf;
					min-height: 100%;
				" title="${frappe.utils.escape_html ? frappe.utils.escape_html(reason) : reason}">
					${value || ""}
				</span>
			`;
		}

		if (data.is_category_total) {
			if (!value || String(value).trim() === "") {
				return "";
			}

			return `
				<span style="
					display: block;
					padding: 2px 4px;
					color: #0f172a;
					font-weight: 800;
					font-size: 14px;
					border-bottom: 2px solid #94a3b8;
				">
					${value}
				</span>
			`;
		}




		const percent_fields = [
			"avail_percent",
			"util_percent",
			"emp_avail_percent"
		];

		if (percent_fields.includes(column.fieldname)) {
			if (is_na_percentage) {
				return value;
			}

			const raw_value = flt(
				data[column.fieldname]
			);

			let bg = "#fee2e2";
			let color = "#991b1b";

			const target_filter =
				frappe.query_report.get_filter_value("au_target_filter") ||
				"85% A & U";

			const target =
				target_filter === "85% A & U" ? 85 : 100;

			const warning = target - 10;

			if (raw_value >= target) {
				bg = "#dcfce7";
				color = "#166534";
			} else if (raw_value >= warning) {
				bg = "#dbeafe";
				color = "#1d4ed8";
			}

			return `
				<span style="
					display: inline-block;
					min-width: 70px;
					text-align: center;
					padding: 4px 10px;
					border-radius: 999px;
					background: ${bg};
					color: ${color};
					font-weight: 700;
					font-size: 12px;
				">
					${value}
				</span>
			`;
		}

		if (column.fieldname === "asset_category") {
			return `
				<span style="
					display: inline-block;
					padding: 4px 10px;
					border-radius: 8px;
					background: #eef2ff;
					color: #3730a3;
					font-weight: 700;
				">
					${value}
				</span>
			`;
		}

		if (column.fieldname === "mechanical_downtime" && flt(data.mechanical_downtime) > 0) {
			return `
				<span style="
					color: #b91c1c;
					font-weight: 700;
				">
					${value}
				</span>
			`;
		}

		if (column.fieldname === "work_hrs" || column.fieldname === "required_hrs") {
			return `
				<span style="
					color: #0f172a;
					font-weight: 700;
				">
					${value}
				</span>
			`;
		}

		return value;
	}
};

window.show_au_month_end_reason_dialog = async function(key, title, asset_name, theme) {
	const payload = (window.au_month_end_reason_details || {})[key] || {};
	const details = Array.isArray(payload) ? payload : (payload.details || []);

        // GLH_DIRECT_POPUP_START

        if (
                title === "Other Delay Reasons"
                && asset_name
        ) {

                const escape_value = function(value) {

                        return frappe.utils.escape_html(
                                String(
                                        value == null
                                                ? ""
                                                : value
                                )
                        );
                };


                const response =
                        await frappe.call({
                                method:
                                        "engineering.engineering.report." +
                                        "availability_and_utilisation_month_end_report." +
                                        "availability_and_utilisation_month_end_report." +
                                        "get_general_lost_hour_popup_rows",

                                args: {
                                        asset_name:
                                                asset_name,

                                        from_date:
                                                frappe.query_report
                                                        .get_filter_value(
                                                                "from_date"
                                                        ),

                                        to_date:
                                                frappe.query_report
                                                        .get_filter_value(
                                                                "to_date"
                                                        ),

                                        location:
                                                frappe.query_report
                                                        .get_filter_value(
                                                                "location"
                                                        )
                                },

                                freeze:
                                        false
                        });


                const glh_details =
                        response.message
                        || [];


                if (glh_details.length) {

                        const format_total =
                                function(value) {

                                        const number =
                                                Number(
                                                        value || 0
                                                );


                                        if (
                                                !Number.isFinite(
                                                        number
                                                )
                                        ) {
                                                return "-";
                                        }


                                        return number
                                                .toFixed(2)
                                                .replace(
                                                        /\.00$/,
                                                        ""
                                                )
                                                .replace(
                                                        /(\.\d)0$/,
                                                        "$1"
                                                );
                                };


                        const rows =
                                glh_details
                                        .map(
                                                detail => {

                                                        const raw_date =
                                                                String(
                                                                        detail.date
                                                                        || ""
                                                                );


                                                        let display_date =
                                                                raw_date;


                                                        if (
                                                                /^\d{4}-\d{2}-\d{2}$/.test(
                                                                        raw_date
                                                                )
                                                        ) {

                                                                const parts =
                                                                        raw_date.split(
                                                                                "-"
                                                                        );


                                                                display_date =
                                                                        `${parts[2]}-${parts[1]}-${parts[0]}`;
                                                        }


                                                        const date =
                                                                escape_value(
                                                                        display_date
                                                                );


                                                        const shift =
                                                                escape_value(
                                                                        detail.shift
                                                                        || ""
                                                                );


                                                        const reason =
                                                                escape_value(
                                                                        detail.reason_description
                                                                        || ""
                                                                );


                                                        const start =
                                                                escape_value(
                                                                        detail.start_time
                                                                        || ""
                                                                );


                                                        const end =
                                                                escape_value(
                                                                        detail.end_time
                                                                        || ""
                                                                );


                                                        const total =
                                                                escape_value(
                                                                        format_total(
                                                                                detail.total_hours
                                                                        )
                                                                );


                                                        const location =
                                                                escape_value(
                                                                        detail.location
                                                                        || ""
                                                                );


                                                        return `
                                                                <tr>

                                                                        <td style="
                                                                                padding:9px 10px;
                                                                                border-bottom:1px solid #dbeafe;
                                                                                white-space:nowrap;
                                                                        ">
                                                                                ${date || "-"}
                                                                        </td>

                                                                        <td style="
                                                                                padding:9px 10px;
                                                                                border-bottom:1px solid #dbeafe;
                                                                                white-space:nowrap;
                                                                        ">
                                                                                ${shift || "-"}
                                                                        </td>

                                                                        <td style="
                                                                                padding:9px 10px;
                                                                                border-bottom:1px solid #dbeafe;
                                                                                font-weight:600;
                                                                                vertical-align:top;
                                                                        ">
                                                                                ${reason || "-"}
                                                                        </td>

                                                                        <td style="
                                                                                padding:9px 10px;
                                                                                border-bottom:1px solid #dbeafe;
                                                                                white-space:nowrap;
                                                                        ">
                                                                                ${start || "-"}
                                                                        </td>

                                                                        <td style="
                                                                                padding:9px 10px;
                                                                                border-bottom:1px solid #dbeafe;
                                                                                white-space:nowrap;
                                                                        ">
                                                                                ${end || "-"}
                                                                        </td>

                                                                        <td style="
                                                                                padding:9px 10px;
                                                                                border-bottom:1px solid #dbeafe;
                                                                                text-align:right;
                                                                                font-weight:700;
                                                                                white-space:nowrap;
                                                                        ">
                                                                                ${total}
                                                                        </td>

                                                                        <td style="
                                                                                padding:9px 10px;
                                                                                border-bottom:1px solid #dbeafe;
                                                                                white-space:nowrap;
                                                                        ">
                                                                                ${location || "-"}
                                                                        </td>
                                                                </tr>
                                                        `;
                                                }
                                        )
                                        .join("");


                        const dialog =
                                new frappe.ui.Dialog({
                                        title:
                                                `Other Delay Reasons - ${
                                                        escape_value(
                                                                asset_name
                                                        )
                                                }`,

                                        size:
                                                "extra-large"
                                });


                        dialog.$body.html(`
                                <div style="
                                        border:1px solid #2563eb;
                                        border-radius:10px;
                                        overflow:hidden;
                                ">

                                        <div style="
                                                background:#dbeafe;
                                                color:#1d4ed8;
                                                font-weight:900;
                                                padding:10px 12px;
                                        ">
                                                Other Delay Reasons for ${
                                                        escape_value(
                                                                asset_name
                                                        )
                                                }
                                        </div>


                                        <div style="
                                                overflow-x:auto;
                                        ">

                                                <table style="
                                                        width:100%;
                                                        border-collapse:collapse;
                                                        min-width:1050px;
                                                ">

                                                        <thead>

                                                                <tr style="
                                                                        background:#eff6ff;
                                                                        color:#1d4ed8;
                                                                ">

                                                                        <th style="
                                                                                padding:9px 10px;
                                                                                text-align:left;
                                                                                width:11%;
                                                                                white-space:nowrap;
                                                                        ">
                                                                                Date
                                                                        </th>

                                                                        <th style="
                                                                                padding:9px 10px;
                                                                                text-align:left;
                                                                                width:8%;
                                                                                white-space:nowrap;
                                                                        ">
                                                                                Shift
                                                                        </th>

                                                                        <th style="
                                                                                padding:9px 10px;
                                                                                text-align:left;
                                                                                width:31%;
                                                                        ">
                                                                                Reason / Description
                                                                        </th>

                                                                        <th style="
                                                                                padding:9px 10px;
                                                                                text-align:left;
                                                                                width:14%;
                                                                        ">
                                                                                Start Time
                                                                        </th>

                                                                        <th style="
                                                                                padding:9px 10px;
                                                                                text-align:left;
                                                                                width:14%;
                                                                        ">
                                                                                End Time
                                                                        </th>

                                                                        <th style="
                                                                                padding:9px 10px;
                                                                                text-align:right;
                                                                                width:10%;
                                                                        ">
                                                                                Total
                                                                        </th>

                                                                        <th style="
                                                                                padding:9px 10px;
                                                                                text-align:left;
                                                                                width:16%;
                                                                        ">
                                                                                Location
                                                                        </th>

                                                                </tr>

                                                        </thead>

                                                        <tbody>
                                                                ${rows}
                                                        </tbody>

                                                </table>

                                        </div>

                                </div>
                        `);


                        dialog.show();

                        return;
                }
        }

        // GLH_DIRECT_POPUP_END


const colours = theme === "purple"
		? {
			border: "#7b2cbf",
			header_bg: "#e6d6ff",
			head_bg: "#f3e8ff",
			text: "#4b0082",
			line: "#eadcff",
		}
		: {
			border: "#2563eb",
			header_bg: "#dbeafe",
			head_bg: "#eff6ff",
			text: "#1d4ed8",
			line: "#dbeafe",
		};

	const format_total_time = function(start_datetime, resolved_datetime) {
		if (!start_datetime || !resolved_datetime) {
			return "Open";
		}

		const start = moment(start_datetime);
		const resolved = moment(resolved_datetime);

		if (!start.isValid() || !resolved.isValid() || resolved.isBefore(start)) {
			return "-";
		}

		return window.au_month_end_format_minutes(resolved.diff(start, "minutes"));
	};

	const has_times = details.some(detail => detail.start_datetime || detail.resolved_datetime);

	const total_raw_minutes = details.reduce((total, detail) => total + flt(detail.total_minutes || 0), 0);
	const total_excluded_minutes = details.reduce((total, detail) => total + flt(detail.startup_fatigue_minutes || 0), 0);
	const total_sunday_minutes = details.reduce((total, detail) => total + flt(detail.sunday_minutes || 0), 0);
	const total_au_minutes = details.reduce(
		(total, detail) => total + flt(detail.au_minutes || 0),
		0
	);

	const header = has_times
		? `
			<tr style="background:${colours.head_bg};color:${colours.text};">
				<th style="padding:8px 10px;text-align:left;width:150px;">Start</th>
				<th style="padding:8px 10px;text-align:left;width:150px;">Resolved</th>
				<th style="padding:8px 10px;text-align:left;width:100px;">Total Time</th>
				<th style="padding:8px 10px;text-align:left;width:150px;">Start-up + Fatigue</th>
				<th style="padding:8px 10px;text-align:left;width:110px;">Sunday Hours</th>
				<th style="padding:8px 10px;text-align:left;width:100px;">A&U Time</th>
				<th style="padding:8px 10px;text-align:left;">Reason</th>
			</tr>
		`
		: `
			<tr style="background:${colours.head_bg};color:${colours.text};">
				<th style="padding:8px 10px;text-align:left;width:130px;">Date</th>
				<th style="padding:8px 10px;text-align:left;">Reason</th>
			</tr>
		`;

	const rows = details.map(detail => {
		const date_value = frappe.utils.escape_html(detail.date || "");
		const start_value = frappe.utils.escape_html(detail.start_datetime || "");
		const resolved_value = frappe.utils.escape_html(detail.resolved_datetime || "");
		const total_time_value = frappe.utils.escape_html(
			detail.total_minutes
				? window.au_month_end_format_minutes(detail.total_minutes)
				: format_total_time(detail.start_datetime, detail.resolved_datetime)
		);
		const startup_fatigue_value = frappe.utils.escape_html(window.au_month_end_format_minutes(detail.startup_fatigue_minutes || 0));
		const sunday_value = frappe.utils.escape_html(window.au_month_end_format_minutes(detail.sunday_minutes || 0));
		const au_time_value = frappe.utils.escape_html(window.au_month_end_format_minutes(detail.au_minutes || 0));
		const reason_value = frappe.utils.escape_html(detail.reason || "");

		if (has_times) {
			return `
				<tr>
					<td style="padding:8px 10px;border-bottom:1px solid ${colours.line};font-weight:700;white-space:nowrap;">
						${start_value || "-"}
					</td>
					<td style="padding:8px 10px;border-bottom:1px solid ${colours.line};font-weight:700;white-space:nowrap;">
						${resolved_value || "Open"}
					</td>
					<td style="padding:8px 10px;border-bottom:1px solid ${colours.line};font-weight:700;white-space:nowrap;">
						${total_time_value}
					</td>
					<td style="padding:8px 10px;border-bottom:1px solid ${colours.line};font-weight:700;white-space:nowrap;color:#b45309;">
						${startup_fatigue_value}
					</td>
					<td style="padding:8px 10px;border-bottom:1px solid ${colours.line};font-weight:700;white-space:nowrap;color:#7c3aed;">
						${sunday_value}
					</td>
					<td style="padding:8px 10px;border-bottom:1px solid ${colours.line};font-weight:700;white-space:nowrap;color:#166534;">
						${au_time_value}
					</td>
					<td style="padding:8px 10px;border-bottom:1px solid ${colours.line};">
						${reason_value}
					</td>
				</tr>
			`;
		}

		return `
			<tr>
				<td style="padding:8px 10px;border-bottom:1px solid ${colours.line};font-weight:700;white-space:nowrap;">
					${date_value || "-"}
				</td>
				<td style="padding:8px 10px;border-bottom:1px solid ${colours.line};">
					${reason_value}
				</td>
			</tr>
		`;
	}).join("");

	const total_row = has_times
		? `
			<tr style="background:${colours.head_bg};color:${colours.text};font-weight:900;">
				<td colspan="2" style="padding:9px 10px;text-align:right;">Totals</td>
				<td style="padding:9px 10px;white-space:nowrap;">${window.au_month_end_format_minutes(total_raw_minutes)}</td>
				<td style="padding:9px 10px;white-space:nowrap;color:#b45309;">${window.au_month_end_format_minutes(total_excluded_minutes)}</td>
				<td style="padding:9px 10px;white-space:nowrap;color:#7c3aed;">${window.au_month_end_format_minutes(total_sunday_minutes)}</td>
				<td style="padding:9px 10px;white-space:nowrap;color:#166534;">${window.au_month_end_format_minutes(total_au_minutes)}</td>
				<td style="padding:9px 10px;"></td>
			</tr>
		`
		: "";

	const reconciliation_note = "";


	const dialog = new frappe.ui.Dialog({
		title: `${title} - ${asset_name || ""}`,
		size: "extra-large"
	});

	dialog.$body.html(`
		<div style="border:1px solid ${colours.border};border-radius:10px;overflow:hidden;">
			<div style="background:${colours.header_bg};color:${colours.text};font-weight:900;padding:10px 12px;">
				${frappe.utils.escape_html(title)} for ${frappe.utils.escape_html(asset_name || "Machine")}
			</div>

			<table style="width:100%;border-collapse:collapse;">
				<thead>
					${header}
				</thead>
				<tbody>
					${rows || `<tr><td colspan="7" style="padding:10px;">No reasons found.</td></tr>`}
					${rows ? total_row : ""}
				</tbody>
			</table>
		</div>
		${reconciliation_note}
	`);

	dialog.show();
};

// MONTH_END_PLANNED_POPUP_SAME_AS_BREAKDOWN_START

(function install_month_end_planned_popup_same_as_breakdown() {

    const REPORT_NAME =
        "Availability and Utilisation Month End Report";


    const report =
        frappe.query_reports[
            REPORT_NAME
        ];


    if (!report) {
        return;
    }


    const previous_formatter =
        report.formatter;


    report.formatter = function(
        value,
        row,
        column,
        data,
        default_formatter
    ) {

        // ====================================================
        // ONLY INTERCEPT PLANNED MAINTENANCE REASON
        // ====================================================

        if (
            column.fieldname
            === "planned_maintenance_reason"
        ) {

            if (
                !data
                || !data.asset_name
            ) {
                return "";
            }


            let details = (
                data.planned_maintenance_reason_details
                || []
            );


            // Fallback if actual reason text exists but
            // detail array is unexpectedly empty.
            if (
                !details.length
                && data.planned_maintenance_reason
            ) {

                details = [{
                    date: "",
                    start_datetime: "",
                    resolved_datetime: "",
                    total_minutes: 0,
                    startup_fatigue_minutes: 0,
                    sunday_minutes: 0,
                    au_minutes: 0,
                    reason:
                        data.planned_maintenance_reason
                }];
            }


            if (!details.length) {
                return "";
            }


            window.au_month_end_reason_details =
                window.au_month_end_reason_details
                || {};


            const key =
                "planned_maintenance_reason-"
                + String(
                    data.asset_name
                    || ""
                )
                + "-"
                + Math.random();


            window.au_month_end_reason_details[
                key
            ] = {
                details: details
            };


            const button_style =
                data.is_spare_swing_unit
                    ?
                    (
                        "background:#e6d6ff;"
                        + "color:#4b0082;"
                        + "border:1px solid #7b2cbf;"
                    )
                    :
                    (
                        "background:#dbeafe;"
                        + "color:#1d4ed8;"
                        + "border:1px solid #2563eb;"
                    );


            const asset_name =
                frappe.utils.escape_html(
                    String(
                        data.asset_name
                        || ""
                    )
                );


            const theme =
                data.is_spare_swing_unit
                    ? "purple"
                    : "blue";


            return `
                <button
                    class="btn btn-xs"
                    style="
                        ${button_style}
                        font-weight:800;
                        border-radius:999px;
                        padding:3px 12px;
                    "
                    onclick="
                        window.show_au_month_end_reason_dialog(
                            '${key}',
                            'Planned Maintenance Reasons',
                            '${asset_name}',
                            '${theme}'
                        )
                    "
                >
                    View
                </button>
            `;
        }


        // Everything else remains unchanged.
        return previous_formatter.call(
            this,
            value,
            row,
            column,
            data,
            default_formatter
        );
    };

})();

// MONTH_END_PLANNED_POPUP_SAME_AS_BREAKDOWN_END
