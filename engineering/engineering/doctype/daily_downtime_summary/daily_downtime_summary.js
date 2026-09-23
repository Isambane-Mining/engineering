// Copyright (c) 2026, Isambane Mining (Pty) Ltd
// For license information, please see license.txt

frappe.ui.form.on("Daily Downtime Summary", {
    refresh(frm) {
        frm.set_df_property("summary_message", "read_only", 1);
        frm.set_df_property("channel_id", "read_only", 1);
        frm.set_df_property("sent_to_raven", "read_only", 1);
        frm.set_df_property("report_data_json", "read_only", 1);

        render_daily_downtime(frm);

        if (!frm.is_new() && frm.doc.summary_message) {
            frm.add_custom_button(__("Copy Summary Message"), function () {
                frappe.utils.copy_to_clipboard(frm.doc.summary_message);

                frappe.show_alert({
                    message: __("Summary copied"),
                    indicator: "green"
                });
            });
        }

        if (!frm.is_new()) {
            frm.add_custom_button(__("Open Down Time Report"), function () {
                frappe.set_route("query-report", "Down Time", {
                    report_date: frm.doc.report_date,
                    site: frm.doc.site,
                    shift: frm.doc.shift
                });
            });
        }
    }
});


function get_daily_shift_period(shift) {
    if (shift === "Day Shift") {
        return "06:00 - 18:00";
    }

    if (shift === "Full Daily") {
        return "06:00 - 06:00 next day";
    }

    return "18:00 - 06:00";
}


function render_daily_downtime(frm) {
    if (!frm.fields_dict.daily_downtime) {
        return;
    }

    let data = [];

    try {
        data = JSON.parse(frm.doc.report_data_json || "[]");
    } catch (e) {
        data = [];
    }

    const site = frm.doc.site || "";
    const report_date = frm.doc.report_date || "";
    const shift = frm.doc.shift || "";
    const period = get_daily_shift_period(shift);

    const total = data.length;
    const open = data.filter(row => String(row.open_closed || "").toLowerCase() === "open").length;
    const closed = total - open;
    const total_hours = data.reduce((sum, row) => sum + flt(row.breakdown_hours || 0), 0);

    const category_order = [
        "ADT",
        "Excavator",
        "Dozer",
        "Water Bowser",
        "Diesel Bowser",
        "Service Truck",
        "FEL",
        "Grader"
    ];

    const grouped = {};

    data.forEach(function (row) {
        const category = get_daily_category_group(row.asset_category || "Uncategorised");

        if (!grouped[category]) {
            grouped[category] = [];
        }

        grouped[category].push(row);
    });

    let html = `
        <style>
            .dds-wrapper {
                border: 1px solid #d9d9d9;
                border-radius: 12px;
                padding: 14px;
                margin-top: 10px;
                background: #fff;
            }

            .dds-title {
                font-size: 18px;
                font-weight: 900;
                text-transform: uppercase;
                margin-bottom: 4px;
            }

            .dds-subtitle {
                font-size: 13px;
                color: #666;
                margin-bottom: 14px;
            }

            .dds-summary {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 8px;
                margin-bottom: 14px;
            }

            .dds-box {
                border-radius: 10px;
                border: 1px solid #e5e7eb;
                background: #f8fafc;
                padding: 10px;
                font-size: 12px;
                font-weight: 800;
            }

            .dds-box strong {
                display: block;
                font-size: 22px;
                margin-top: 4px;
            }

            .dds-open-box {
                background: #ffe5e5;
                color: #a8071a;
                border-color: #ff4d4f;
            }

            .dds-closed-box {
                background: #e6f7e6;
                color: #237804;
                border-color: #52c41a;
            }

            .dds-hours-box {
                background: #fff7e6;
                color: #ad6800;
                border-color: #faad14;
            }

            .dds-category {
                margin-top: 12px;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                overflow: hidden;
            }

            .dds-category-heading {
                background: #f2f2f2;
                padding: 9px 11px;
                font-weight: 900;
                text-transform: uppercase;
            }

            .dds-row {
                display: grid;
                grid-template-columns: 34px 130px 110px 1fr;
                gap: 8px;
                padding: 10px 11px;
                border-top: 1px solid #f0f0f0;
                font-size: 13px;
                align-items: start;
            }

            @media (max-width: 768px) {
                .dds-wrapper {
                    padding: 10px;
                    margin: 0;
                    border-radius: 10px;
                }

                .dds-title {
                    font-size: 15px;
                }

                .dds-subtitle {
                    font-size: 12px;
                    line-height: 1.4;
                }

                .dds-summary {
                    grid-template-columns: 1fr 1fr;
                    gap: 6px;
                }

                .dds-box {
                    padding: 8px;
                    font-size: 11px;
                }

                .dds-box strong {
                    font-size: 17px;
                }

                .dds-row {
                    grid-template-columns: 28px 1fr;
                    gap: 6px;
                    padding: 10px;
                }

                .dds-plant {
                    font-size: 14px;
                }

                .dds-hours {
                    grid-column: 2;
                    font-size: 13px;
                }

                .dds-detail {
                    grid-column: 1 / -1;
                    font-size: 12px;
                    padding-left: 34px;
                }
            }

            .dds-row-open {
                background: #fff1f0;
                color: #a8071a;
                font-weight: 700;
            }

            .dds-row-closed {
                background: #f6ffed;
                color: #237804;
            }

            .dds-plant {
                font-weight: 900;
            }

            .dds-hours {
                font-weight: 900;
            }

            .dds-detail {
                line-height: 1.35;
            }

            .dds-label {
                font-weight: 900;
            }

            .dds-empty {
                border: 1px solid #faad14;
                background: #fff7e6;
                color: #ad6800;
                border-radius: 10px;
                padding: 12px;
                font-weight: 800;
            }

            .dds-row-clickable {
                cursor: pointer;
            }

            .dds-row-clickable:hover {
                outline: 2px solid rgba(168, 7, 26, 0.35);
                outline-offset: -2px;
            }
        </style>

        <div class="dds-wrapper">
            <div class="dds-title">${frappe.utils.escape_html(site)} Daily Downtime Report</div>
            <div class="dds-subtitle">
                Date: ${frappe.utils.escape_html(report_date)}
                | Shift: ${frappe.utils.escape_html(shift)}
                | Period: ${frappe.utils.escape_html(period)}
            </div>

            <div class="dds-summary">
                <div class="dds-box">Records<strong>${total}</strong></div>
                <div class="dds-box dds-hours-box">Total Hours<strong>${format_daily_hours(total_hours)}</strong></div>
                <div class="dds-box dds-open-box">Open<strong>${open}</strong></div>
                <div class="dds-box dds-closed-box">Closed<strong>${closed}</strong></div>
            </div>
    `;

    if (!data.length) {
        html += `
            <div class="dds-empty">
                No downtime records found for this shift.
            </div>
        `;
    }

    category_order.forEach(function (category) {
        const rows = grouped[category] || [];

        if (!rows.length) {
            return;
        }

        html += `
            <div class="dds-category">
                <div class="dds-category-heading">${frappe.utils.escape_html(category)}</div>
        `;

        rows.forEach(function (row) {
            const is_open = String(row.open_closed || "").toLowerCase() === "open";
            const icon = is_open ? "❌" : "✅";
            const row_class = is_open ? "dds-row-open" : "dds-row-closed";
            const is_clickable = !!row.breakdown_docname;
            const clickable_class = is_clickable ? "dds-row-clickable" : "";
            const clickable_attr = is_clickable ? `data-breakdown-docname="${frappe.utils.escape_html(row.breakdown_docname)}"` : "";

            html += `
                <div class="dds-row ${row_class} ${clickable_class}" ${clickable_attr}>
                    <div>${icon}</div>
                    <div class="dds-plant">${frappe.utils.escape_html(row.plant_no || "")}</div>
                    <div class="dds-hours">${frappe.utils.escape_html(format_daily_hours(row.breakdown_hours || 0))}</div>
                    <div class="dds-detail">
                        <span class="dds-label">Status:</span> ${frappe.utils.escape_html(row.open_closed || "-")}
                        <br>
                        <span class="dds-label">Reason:</span> ${frappe.utils.escape_html(row.breakdown_reason || "-")}
                        <br>
                        <small>
                            Start: ${frappe.utils.escape_html(row.breakdown_start_datetime || "-")}
                            | Back in Production: ${frappe.utils.escape_html(row.resolved_datetime || "OPEN")}
                        </small>
                        <br>
                        <small>
                            Resolution: ${frappe.utils.escape_html(row.resolution_summary || "-")}
                        </small>
                    </div>
                </div>
            `;
        });

        html += `</div>`;
    });

    html += `</div>`;


    frm.fields_dict.daily_downtime.$wrapper.html(html);

    frm.fields_dict.daily_downtime.$wrapper
        .find(".dds-row-clickable")
        .off("click")
        .on("click", function () {
            const breakdown_docname = $(this).attr("data-breakdown-docname");

            if (breakdown_docname) {
                frappe.set_route("Form", "Plant Breakdown or Maintenance", breakdown_docname);
            }
        });
}


function get_daily_category_group(asset_category) {
    const value = String(asset_category || "").trim().toLowerCase();

    if (value.includes("adt")) {
        return "ADT";
    }

    if (value.includes("excavator")) {
        return "Excavator";
    }

    if (value.includes("dozer")) {
        return "Dozer";
    }

    if (value.includes("water") && value.includes("bowser")) {
        return "Water Bowser";
    }

    if (value.includes("diesel") && value.includes("bowser")) {
        return "Diesel Bowser";
    }

    if (value.includes("service") && value.includes("truck")) {
        return "Service Truck";
    }

    if (value === "fel" || value.includes("front end loader")) {
        return "FEL";
    }

    if (value.includes("grader")) {
        return "Grader";
    }

    return asset_category || "Uncategorised";
}


function format_daily_hours(value) {
    const total_minutes = Math.round(flt(value || 0) * 60);
    const hours = Math.floor(total_minutes / 60);
    const minutes = total_minutes % 60;

    if (hours && minutes) {
        return `${hours} Hour ${minutes} Min`;
    }

    if (hours) {
        return `${hours} Hour`;
    }

    return `${minutes} Min`;
}
