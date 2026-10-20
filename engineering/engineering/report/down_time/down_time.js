// Copyright (c) 2026, Isambane Mining (Pty) Ltd
// For license information, please see license.txt

let downtime_mobile_comment_cache = {};

function refresh_downtime_signoff_report() {
    const report = frappe.query_report;

    if (!report) {
        return;
    }

    report.__active_downtime_tab = "signoff";

    const $main =
        report.page
            ? report.page.main || report.page.$wrapper
            : null;

    if ($main && $main.length) {
        $main.find(".dt-saved-reports-panel").hide();
        $main.find(".report-wrapper").show();

        $main.find(".dt-report-tab")
            .removeClass("btn-primary")
            .addClass("btn-default");

        $main.find(
            '.dt-report-tab[data-tab="signoff"]'
        )
            .removeClass("btn-default")
            .addClass("btn-primary");
    }

    $(".downtime-signoff-action-wrapper").show();
    $(".mobile-downtime-wrapper").show();
    $(".downtime-avail-util-wrapper").show();

    report.refresh();
}


frappe.query_reports["Down Time"] = {
    filters: [
        {
            fieldname: "report_date",
            label: __("Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today(),
            onchange: function () {
                refresh_downtime_signoff_report();
            }
        },
        {
            fieldname: "site",
            label: __("Site"),
            fieldtype: "Link",
            options: "Location",
            onchange: function () {
                refresh_downtime_signoff_report();
            }
        },
        {
            fieldname: "asset_category",
            label: __("Asset Category"),
            fieldtype: "Link",
            options: "Asset Category",
            onchange: function () {
                refresh_downtime_signoff_report();
            }
        },
        {
            fieldname: "shift",
            label: __("Shift"),
            fieldtype: "Select",
            options: "\nDay Shift\nNight Shift",
            onchange: function () {
                refresh_downtime_signoff_report();
            }
        }
    ],

    formatter: function (value, row, column, data, default_formatter) {
        if (column.fieldname === "downtime_comment") {
            const plant_no = data && data.plant_no ? data.plant_no : "";

            return `
                <input
                    type="text"
                    class="form-control downtime-comment-input"
                    data-plant-no="${frappe.utils.escape_html(plant_no)}"
                    placeholder="Add comment..."
                    style="height: 28px; min-width: 220px;"
                >
            `;
        }

        return default_formatter(value, row, column, data);
    },

    onload: function (report) {
        hide_generate_button(report);
        add_signoff_button(report);
        setup_mobile_downtime_view(report);
        load_previous_day_avail_util_summary(report);
    },

    refresh: function (report) {
        hide_generate_button(report);
        add_signoff_button(report);
        setup_mobile_downtime_view(report);
        load_previous_day_avail_util_summary(report);
    },

    after_datatable_render: function (report) {
        render_downtime_cards(report);
        load_previous_day_avail_util_summary(report);
    }
};

function add_signoff_button(report) {
    if (!report || !report.page) {
        return;
    }

    $(".downtime-signoff-action-wrapper").remove();

    const html = `
        <div class="downtime-signoff-action-wrapper">
            <button type="button" class="btn btn-danger downtime-signoff-action-button">
                Submit Downtime Sign-off
            </button>
        </div>
    `;

    $(".report-wrapper").after(html);
    $(".downtime-signoff-action-button").prop("disabled", true);

    $(".downtime-signoff-action-button").off("click").on("click", function () {
        // dt_direct_red_button_v2
        // Record-level verification has its own handler on this red button.
        // Never open the legacy sign-off dialog for that workflow.
        if ($(".dt-verification-actions").length) {
            return;
        }

        // Historical workflow retains its original sign-off process.
        const report_date = frappe.query_report.get_filter_value("report_date");

        if (!report_date) {
            frappe.msgprint(__("Please select a Date first."));
            return;
        }

        const engineering_roles = [
            "Engineering Area Manager",
            "Engineering Foreman",
            "Engineering Manager",
            "Engineering Plant Manager",
            "Engineering Supervisor",
            "Engineering User"
        ];

        const production_roles = [
            "Production Manager",
            "Production Supervisor",
            "Production Foreman",
            "Production User"
        ];

        const can_sign_engineering = engineering_roles.some(function (role) {
            return frappe.user_roles.includes(role);
        });

        const can_sign_production = production_roles.some(function (role) {
            return frappe.user_roles.includes(role);
        });

        const signoff_options = [];

        if (can_sign_engineering) {
            signoff_options.push("Engineering");
        }

        if (can_sign_production) {
            signoff_options.push("Production");
        }

        if (!signoff_options.length) {
            frappe.throw(__(
                "You do not have permission to sign this downtime report."
            ));
            return;
        }

        const dialog = new frappe.ui.Dialog({
            title: __("Submit Downtime Sign-off"),
            fields: [
                {
                    fieldname: "signoff_section",
                    label: __("Sign-off Section"),
                    fieldtype: "Select",
                    options: signoff_options.join("\n"),
                    default: signoff_options[0],
                    reqd: 1
                }
            ],
            primary_action_label: __("Submit"),
            primary_action(values) {
                frappe.confirm(
                    __(
                        "Do you confirm that you have verified all downtime records and corrected any inaccuracies?"
                    ),
                    function () {
                        frappe.call({
                            method: "engineering.engineering.report.down_time.down_time.save_downtime_signoff",
                            args: {
                                report_date: report_date,
                                site: frappe.query_report.get_filter_value("site") || "",
                                asset_category: frappe.query_report.get_filter_value("asset_category") || "",
                                shift: frappe.query_report.get_filter_value("shift") || "",
                                signoff_section: values.signoff_section,
                                downtime_comments: get_mobile_downtime_comments()
                            },
                            freeze: true,
                            freeze_message: __("Submitting sign-off..."),
                            callback: function (r) {
                                if (r && r.message) {
                                    dialog.hide();
                                    frappe.msgprint(r.message);
                                }
                            }
                        });
                    }
                );
            }
        });

        dialog.show();
    });
}

function hide_generate_button(report) {
    if (!report || !report.page) {
        return;
    }

    report.page.clear_primary_action();

    setTimeout(function () {
        report.page.clear_primary_action();

        $(".btn-primary").each(function () {
            if ($(this).text().trim() === "Generate New Report") {
                $(this).hide();
            }
        });
    }, 500);

    setTimeout(function () {
        report.page.clear_primary_action();

        $(".btn-primary").each(function () {
            if ($(this).text().trim() === "Generate New Report") {
                $(this).hide();
            }
        });
    }, 1500);
}



function is_mobile_downtime_view() {
    return window.matchMedia("(max-width: 1024px), (pointer: coarse)").matches;
}

function setup_mobile_downtime_view(report) {
    if (!report || !report.page) {
        return;
    }

    add_mobile_downtime_styles();

    frappe.after_ajax(function () {
        render_downtime_cards(report);
    });

    $(window).off("resize.mobile_downtime").on("resize.mobile_downtime", function () {
        const active = document.activeElement;

        if (
            active &&
            (
                active.classList.contains("mobile-downtime-comment-input") ||
                active.classList.contains("downtime-comment-input") ||
                active.tagName === "TEXTAREA" ||
                active.tagName === "INPUT"
            )
        ) {
            return;
        }

        render_downtime_cards(report);
    });
}


function add_mobile_downtime_styles() {
    if ($("#mobile-downtime-styles").length) {
        return;
    }

    $("head").append(`
        <style id="mobile-downtime-styles">
            .query-report .dt-scrollable,
            .query-report .datatable,
            .query-report .frappe-datatable {
                display: none !important;
            }

            .mobile-downtime-wrapper {
                display: block;
                width: 100%;
                margin: 0 auto;
                padding: 10px 0 80px 0;
                box-sizing: border-box;
            }

            .mobile-downtime-summary {
                display: grid;
                grid-template-columns: repeat(4, minmax(140px, 1fr));
                gap: 12px;
                margin-bottom: 14px;
            }

            .mobile-downtime-summary-box {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 18px;
                font-size: 14px;
                color: #6b7280;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
            }

            .mobile-downtime-summary-box strong {
                display: block;
                font-size: 22px;
                color: #111827;
                margin-top: 5px;
            }

            .downtime-card-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(300px, 1fr));
                gap: 14px;
                align-items: stretch;
            }

            .mobile-downtime-card {
                background: #ffffff;
                border: 1px solid #dcdfe4;
                border-radius: 12px;
                padding: 14px;
                box-shadow: 0 2px 7px rgba(0, 0, 0, 0.06);
                display: flex;
                flex-direction: column;
                min-width: 0;
            }

            .mobile-downtime-card:hover {
                border-color: #c6cbd2;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.09);
            }

            .mobile-downtime-verify {
                display: flex;
                align-items: center;
                gap: 9px;
                padding: 10px 12px;
                margin-bottom: 12px;
                background: #fff7e6;
                border: 1px solid #ffd591;
                border-radius: 9px;
                font-size: 18px;
                font-weight: 700;
                cursor: pointer;
            }

            .mobile-downtime-verify input {
                width: 19px;
                height: 19px;
                margin: 0;
            }

            .mobile-downtime-title {
                font-size: 18px;
                font-weight: 800;
                color: #1f2937;
                margin-bottom: 9px;
            }

            .mobile-downtime-badges {
                display: flex;
                gap: 7px;
                flex-wrap: wrap;
                margin-bottom: 12px;
            }

            .mobile-downtime-badge {
                border-radius: 999px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 700;
                background: #f1f3f5;
                color: #4b5563;
            }

            .mobile-downtime-badge.open {
                background: #ffe5e5;
                color: #b00020;
            }

            .mobile-downtime-badge.closed {
                background: #e8f5e9;
                color: #1b5e20;
            }

            .mobile-downtime-details {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 9px 14px;
                margin-bottom: 10px;
            }

            .mobile-downtime-row {
                font-size: 13px;
                line-height: 1.4;
                color: #4b5563;
                min-width: 0;
                overflow-wrap: anywhere;
            }

            .mobile-downtime-row.full-width {
                grid-column: 1 / -1;
            }

            .mobile-downtime-label {
                font-weight: 800;
                color: #374151;
            }

            .mobile-downtime-comment {
                margin-top: auto;
                padding-top: 10px;
            }

            .mobile-downtime-comment textarea {
                width: 100%;
                min-height: 76px;
                border: 1px solid #d1d5db;
                border-radius: 9px;
                padding: 9px;
                font-size: 13px;
                resize: vertical;
                background: #ffffff;
                box-sizing: border-box;
            }

            .mobile-downtime-comment textarea:focus {
                border-color: #f0ad00;
                outline: none;
                box-shadow: 0 0 0 2px rgba(240, 173, 0, 0.15);
            }

            .downtime-signoff-action-wrapper {
                position: sticky;
                bottom: 10px;
                z-index: 100;
                margin: 14px 0;
                display: flex;
                justify-content: flex-end;
                pointer-events: none;
            }

            .downtime-signoff-action-button {
                pointer-events: auto;
                border-radius: 999px;
                padding: 12px 22px;
                font-size: 14px;
                font-weight: 800;
                box-shadow: 0 3px 12px rgba(176, 0, 32, 0.25);
            }

            .downtime-avail-util-wrapper {
                background: #ffffff;
                border: 1px solid #d9d9d9;
                border-radius: 12px;
                padding: 14px;
                margin: 10px 0 14px 0;
            }

            .downtime-avail-util-title {
                font-size: 14px;
                font-weight: 800;
                margin: 10px 0 8px 0;
            }

            .tmm-equipment-downtime-heading {
                background: #f2f2f2;
                border: 2px solid #111;
                padding: 9px;
                margin: 10px 0 8px 0;
                font-size: 13px;
                font-weight: 800;
                color: #111;
                text-align: center;
                text-transform: uppercase;
            }

            .downtime-avail-util-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(120px, 1fr));
                gap: 8px;
                margin-bottom: 8px;
            }

            .downtime-prev-breakdown-section {
                margin-top: 12px;
                padding-top: 12px;
                border-top: 1px solid #e5e7eb;
            }

            .downtime-prev-breakdown-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                flex-wrap: wrap;
                margin-bottom: 8px;
            }

            .downtime-prev-breakdown-title {
                font-size: 13px;
                font-weight: 800;
                color: #374151;
            }

            .downtime-prev-breakdown-button {
                border: 1px solid #1d4ed8 !important;
                background: #dbeafe !important;
                color: #1e3a8a !important;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                white-space: nowrap;
            }

            .downtime-prev-breakdown-button:hover {
                border-color: #1e40af !important;
                background: #bfdbfe !important;
                color: #1e3a8a !important;
            }

            .downtime-au-verify-wrapper {
                display: flex;
                align-items: center;
                gap: 10px;
                flex-wrap: wrap;
            }

            .downtime-au-verify-label {
                display: flex;
                align-items: center;
                gap: 7px;
                margin: 0;
                padding: 7px 10px;
                background: #fff7e6;
                border: 1px solid #ffd591;
                border-radius: 8px;
                color: #7a4f01;
                font-size: 12px;
                font-weight: 700;
                cursor: pointer;
                white-space: nowrap;
            }

            .downtime-au-verify-label input {
                width: 17px;
                height: 17px;
                margin: 0;
            }

            .downtime-prev-breakdown-list {
                display: grid;
                grid-template-columns: repeat(6, minmax(160px, 1fr));
                gap: 8px;
            }

            .downtime-prev-breakdown-item {
                position: relative;
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 9px 10px;
                font-size: 12px;
                color: #374151;
                line-height: 1.4;
                cursor: pointer;
                overflow: visible;
            }

            .downtime-prev-breakdown-item strong {
                color: #111827;
            }

            .downtime-prev-breakdown-item:hover {
                background: #dbeafe;
                border-color: #1d4ed8;
                color: #1e3a8a;
            }

            .downtime-prev-breakdown-item:hover strong {
                color: #1e3a8a;
            }

            .downtime-prev-breakdown-tooltip {
                display: none;
                position: absolute;
                left: 50%;
                top: calc(100% + 8px);
                transform: translateX(-50%);
                width: 300px;
                background: #ffffff;
                border: 1px solid #93c5fd;
                border-radius: 10px;
                padding: 12px;
                color: #1f2937;
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.18);
                z-index: 500;
                font-size: 12px;
                line-height: 1.5;
            }

            .downtime-prev-breakdown-item:hover .downtime-prev-breakdown-tooltip,
            .downtime-prev-breakdown-item.is-open .downtime-prev-breakdown-tooltip {
                display: block;
            }

            .downtime-prev-breakdown-tooltip-row {
                margin-bottom: 6px;
            }

            .downtime-prev-breakdown-tooltip-row:last-child {
                margin-bottom: 0;
            }

            @media (max-width: 1400px) {
                .downtime-prev-breakdown-list {
                    grid-template-columns: repeat(3, minmax(160px, 1fr));
                }
            }

            .downtime-prev-breakdown-empty {
                background: #fafafa;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 12px;
                color: #6b7280;
            }

            .downtime-prev-breakdown-more {
                font-size: 12px;
                font-weight: 700;
                color: #6b7280;
                margin-top: 2px;
            }

            .downtime-avail-util-bubble {
                background: #f7f7f7;
                border: 1px solid #e5e5e5;
                border-radius: 12px;
                padding: 9px;
                font-size: 12px;
                font-weight: 700;
                text-align: center;
            }

            .downtime-avail-util-bubble strong {
                display: block;
                font-size: 13px;
                margin-bottom: 5px;
            }

            .downtime-avail-util-values {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 5px;
            }

            .downtime-avail-util-value {
                background: #fff;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                padding: 6px;
                font-size: 11px;
                font-weight: 800;
            }

            .downtime-au-red {
                background: #ffe5e5 !important;
                border-color: #ff4d4f !important;
                color: #a8071a !important;
            }

            .downtime-au-yellow {
                background: #fff7d6 !important;
                border-color: #faad14 !important;
                color: #ad6800 !important;
            }

            .downtime-au-green {
                background: #e6f7e6 !important;
                border-color: #52c41a !important;
                color: #237804 !important;
            }

            .downtime-au-na {
                background: #f5f5f5 !important;
                border-color: #d9d9d9 !important;
                color: #8c8c8c !important;
            }

            @media (max-width: 1350px) {
                .downtime-card-grid {
                    grid-template-columns: repeat(2, minmax(300px, 1fr));
                }
            }

            @media (max-width: 1024px), (pointer: coarse) {
                .mobile-downtime-wrapper {
                    max-width: 720px;
                    padding: 10px 8px 80px 8px;
                }

                .downtime-card-grid {
                    grid-template-columns: 1fr;
                    gap: 10px;
                }

                .mobile-downtime-summary {
                    grid-template-columns: repeat(2, 1fr);
                    gap: 8px;
                }

                .mobile-downtime-details {
                    grid-template-columns: 1fr;
                }

                .mobile-downtime-row.full-width {
                    grid-column: auto;
                }

                .downtime-avail-util-grid {
                    grid-template-columns: 1fr;
                }

                .downtime-prev-breakdown-list {
                    grid-template-columns: repeat(2, minmax(140px, 1fr));
                }

                .downtime-prev-breakdown-tooltip {
                    left: 0;
                    right: auto;
                    top: calc(100% + 8px);
                    transform: none;
                    width: min(300px, calc(100vw - 40px));
                }

                .downtime-prev-breakdown-item.is-open .downtime-prev-breakdown-tooltip {
                    display: block !important;
                }

                .downtime-prev-breakdown-button {
                    width: 100%;
                    white-space: normal;
                }

                .downtime-au-verify-wrapper {
                    width: 100%;
                }

                .downtime-au-verify-label {
                    width: 100%;
                    justify-content: center;
                }

                .downtime-signoff-action-wrapper {
                    justify-content: stretch;
                }

                .downtime-signoff-action-button {
                    width: 100%;
                    padding: 13px 18px;
                    font-size: 15px;
                }
            }
        </style>
    `);
}

function format_downtime_duration(value) {
    const total_minutes = Math.round(flt(value || 0) * 60);
    const hours = Math.floor(total_minutes / 60);
    const minutes = total_minutes % 60;

    const parts = [];

    if (hours > 0) {
        parts.push(hours + (hours === 1 ? " hour" : " hours"));
    }

    if (minutes > 0 || hours === 0) {
        parts.push(minutes + (minutes === 1 ? " min" : " mins"));
    }

    return parts.join(" ");
}

function render_downtime_cards(report) {
    const data =
        frappe.query_report && frappe.query_report.data
            ? frappe.query_report.data
            : [];

    $(".mobile-downtime-wrapper").remove();
    $(".downtime-desktop-verify-wrapper").remove();

    $(".dt-scrollable, .datatable, .frappe-datatable").hide();

    const total_records = data.length;

    const open_records = data.filter(function (row) {
        return String(row.open_closed || "").toLowerCase() === "open";
    }).length;

    const closed_records = data.filter(function (row) {
        return String(row.open_closed || "").toLowerCase() === "closed";
    }).length;

    const total_hours = data.reduce(function (total, row) {
        return total + flt(row.breakdown_hours || 0);
    }, 0);

    let html = `
        <div class="mobile-downtime-wrapper">
            <div class="mobile-downtime-summary">
                <div class="mobile-downtime-summary-box">
                    Records
                    <strong>${total_records}</strong>
                </div>

                <div class="mobile-downtime-summary-box">
                    Total Downtime
                    <strong>${format_downtime_duration(total_hours)}</strong>
                </div>

                <div class="mobile-downtime-summary-box">
                    Open
                    <strong>${open_records}</strong>
                </div>

                <div class="mobile-downtime-summary-box">
                    Closed
                    <strong>${closed_records}</strong>
                </div>
            </div>

            <div class="downtime-card-grid">
    `;

    if (!data.length) {
        html += `
            <div class="mobile-downtime-card">
                No downtime records found.
            </div>
        `;
    }

    data.forEach(function (row) {
        const status = row.open_closed || "";

        const status_class =
            String(status).toLowerCase() === "open"
                ? "open"
                : "closed";

        const plant_no = row.plant_no || "";
        const record_key = row.breakdown_docname || "";

        html += `
            <div class="mobile-downtime-card">
                <div class="mobile-downtime-verify">
                    <strong>Downtime Verification</strong>

                    <label>
                        <input
                            type="radio"
                            name="verify-${frappe.utils.escape_html(record_key)}"
                            value="Verified"
                            class="dt-preview-verification"
                            data-record-key="${frappe.utils.escape_html(record_key)}"
                        >
                        Verified Downtime
                    </label>

                    <label>
                        <input
                            type="radio"
                            name="verify-${frappe.utils.escape_html(record_key)}"
                            value="Not Verified"
                            class="dt-preview-verification"
                            data-record-key="${frappe.utils.escape_html(record_key)}"
                        >
                        Not Verified Downtime
                    </label>
                </div>

                <div class="mobile-downtime-title">
                    ${frappe.utils.escape_html(plant_no)}
                </div>

                <div class="mobile-downtime-badges">
                    <span class="mobile-downtime-badge ${status_class}">
                        ${frappe.utils.escape_html(status)}
                    </span>

                    <span class="mobile-downtime-badge">
                        ${frappe.utils.escape_html(
                            format_downtime_duration(row.breakdown_hours)
                        )}
                    </span>

                    <span class="mobile-downtime-badge">
                        ${frappe.utils.escape_html(row.asset_category || "")}
                    </span>
                </div>

                <div class="mobile-downtime-details">
                    <div class="mobile-downtime-row">
                        <span class="mobile-downtime-label">Site:</span><br>
                        ${frappe.utils.escape_html(row.site || "")}
                    </div>

                    <div class="mobile-downtime-row">
                        <span class="mobile-downtime-label">Start:</span><br>
                        ${frappe.utils.escape_html(row.breakdown_start_datetime || "")}
                    </div>

                    <div class="mobile-downtime-row full-width">
                        <span class="mobile-downtime-label">Back in Production:</span><br>
                        ${frappe.utils.escape_html(row.resolved_datetime || "Still Open")}
                    </div>

                    <div class="mobile-downtime-row">
                        <span class="mobile-downtime-label">Reason:</span><br>
                        ${frappe.utils.escape_html(row.breakdown_reason || "")}
                    </div>

                    <div class="mobile-downtime-row">
                        <span class="mobile-downtime-label">Resolution:</span><br>
                        ${frappe.utils.escape_html(row.resolution_summary || "")}
                    </div>
                </div>

                <div class="mobile-downtime-comment">
                    <span class="mobile-downtime-label">
                        Downtime Comment:
                    </span>

                    <textarea
                        class="mobile-downtime-comment-input"
                        data-plant-no="${frappe.utils.escape_html(plant_no)}"
                        placeholder="Add comment for this downtime record..."
                    >${frappe.utils.escape_html(
                        downtime_mobile_comment_cache[plant_no] || ""
                    )}</textarea>
                </div>
            </div>
        `;
    });

    html += `
            </div>
        </div>
    `;

    $(".report-wrapper").append(html);

    render_downtime_summary_preview(data);
    load_downtime_summary_readonly(report);

    $(".mobile-downtime-comment-input")
        .off("input.mobile_comment")
        .on("input.mobile_comment", function () {
            const plant_no = $(this).data("plant-no");
            downtime_mobile_comment_cache[plant_no] = $(this).val() || "";
        });
}





function load_previous_day_avail_util_summary(report) {
    const report_date = frappe.query_report.get_filter_value("report_date");
    const site = frappe.query_report.get_filter_value("site") || "";

    if (!report_date) {
        return;
    }

    frappe.call({
        method: "engineering.engineering.report.down_time.down_time.get_previous_day_avail_util_summary",
        args: {
            report_date: report_date,
            site: site
        },
        callback: function (r) {
            render_previous_day_avail_util_summary(r.message || {});
        }
    });
}

function render_previous_day_avail_util_summary(summary) {
    $(".downtime-avail-util-wrapper").remove();

    const production = summary.production || {};
    const spare = summary.spare || {};
    const previous_date = summary.previous_date || "";
    const previous_day_breakdowns = summary.previous_day_breakdowns || [];
    const site = frappe.query_report.get_filter_value("site") || "";

    let html = `
        <div class="downtime-avail-util-wrapper">
            <div class="downtime-avail-util-title">
                Previous Day Production Machine Availability and Utilisation ${previous_date ? "(" + frappe.utils.escape_html(previous_date) + ")" : ""}
            </div>
            <div class="downtime-avail-util-grid">
                ${get_avail_util_bubble_html(production.adts)}
                ${get_avail_util_bubble_html(production.excavators)}
                ${get_avail_util_bubble_html(production.dozers)}
            </div>

            <div class="downtime-avail-util-title">
                Previous Day Spare Machine Availability and Utilisation ${previous_date ? "(" + frappe.utils.escape_html(previous_date) + ")" : ""}
            </div>
            <div class="downtime-avail-util-grid">
                ${get_avail_util_bubble_html(spare.adts)}
                ${get_avail_util_bubble_html(spare.excavators)}
                ${get_avail_util_bubble_html(spare.dozers)}
            </div>

            <div class="downtime-prev-breakdown-section">
                <div class="downtime-prev-breakdown-header">
                    <div class="downtime-prev-breakdown-title">
                        Previous Day Downtime Summary ${previous_date ? "(" + frappe.utils.escape_html(previous_date) + ")" : ""}
                    </div>

                    <div class="downtime-au-verify-wrapper">
                        <label class="downtime-au-verify-label">
                            <input
                                type="checkbox"
                                class="downtime-au-verify-checkbox"
                            >
                            <span>Verify Previous Day A&amp;U</span>
                        </label>

                        <button
                            type="button"
                            class="btn btn-default downtime-prev-breakdown-button"
                            data-previous-date="${frappe.utils.escape_html(previous_date)}"
                            data-site="${frappe.utils.escape_html(site)}"
                        >
                            Click the Button to see more detail on previous day Downtimes
                        </button>
                    </div>
                </div>

                ${get_previous_day_breakdown_summary_html(previous_day_breakdowns)}
            </div>
        </div>
    `;

    $(".report-wrapper").prepend(html);

    $(".tmm-equipment-downtime-heading").remove();

    $(".downtime-avail-util-wrapper").after(`
        <div class="tmm-equipment-downtime-heading">
            TMM EQUIPMENT DOWNTIME
        </div>
    `);

    $(".downtime-prev-breakdown-button").off("click").on("click", function () {
        const previous_date = $(this).data("previous-date") || "";
        const site = $(this).data("site") || "";
        const url = get_previous_day_breakdown_report_url(previous_date, site);
        window.open(url, "_blank");
    });

    $(".downtime-prev-breakdown-item")
        .off("click.previous_day_details")
        .on("click.previous_day_details", function (event) {
            event.stopPropagation();

            const $item = $(this);
            const should_open = !$item.hasClass("is-open");

            $(".downtime-prev-breakdown-item").removeClass("is-open");

            if (should_open) {
                $item.addClass("is-open");
            }
        });

    $(".downtime-prev-breakdown-tooltip")
        .off("click.previous_day_details")
        .on("click.previous_day_details", function (event) {
            event.stopPropagation();
        });

    $(document)
        .off("click.previous_day_details")
        .on("click.previous_day_details", function () {
            $(".downtime-prev-breakdown-item").removeClass("is-open");
        });
}


function get_previous_day_breakdown_summary_html(rows) {
    rows = rows || [];

    if (!rows.length) {
        return `
            <div class="downtime-prev-breakdown-empty">
                No previous day downtimes found.
            </div>
        `;
    }

    const visible_rows = rows;

    let html = `<div class="downtime-prev-breakdown-list">`;

    visible_rows.forEach(function (row) {
        const plant_no = frappe.utils.escape_html(row.plant_no || "");
        const reason = truncate_previous_day_breakdown_reason(row.reason || "", 28);
        const full_reason = frappe.utils.escape_html(row.reason || "");
        const status = frappe.utils.escape_html(row.status || "");
        const start = frappe.utils.escape_html(row.start || "");
        const resolved = frappe.utils.escape_html(row.resolved || "Still Open");
        const hours = frappe.utils.escape_html(
            format_downtime_duration(row.hours)
        );

        html += `
            <div class="downtime-prev-breakdown-item">
                <strong>${plant_no}</strong> - ${reason}

                <div class="downtime-prev-breakdown-tooltip">
                    <div class="downtime-prev-breakdown-tooltip-row">
                        <strong>Fleet No:</strong> ${plant_no}
                    </div>

                    <div class="downtime-prev-breakdown-tooltip-row">
                        <strong>Reason:</strong> ${full_reason}
                    </div>

                    <div class="downtime-prev-breakdown-tooltip-row">
                        <strong>Status:</strong> ${status}
                    </div>

                    <div class="downtime-prev-breakdown-tooltip-row">
                        <strong>Downtime:</strong> ${hours}
                    </div>

                    <div class="downtime-prev-breakdown-tooltip-row">
                        <strong>Start:</strong> ${start}
                    </div>

                    <div class="downtime-prev-breakdown-tooltip-row">
                        <strong>Back in Production:</strong> ${resolved}
                    </div>
                </div>
            </div>
        `;
    });

    html += `</div>`;

    return html;
}

function truncate_previous_day_breakdown_reason(reason, max_length) {
    reason = String(reason || "");

    if (reason.length <= max_length) {
        return frappe.utils.escape_html(reason);
    }

    return frappe.utils.escape_html(reason.slice(0, max_length).trim()) + "......";
}

function get_previous_day_breakdown_report_url(previous_date, site) {
    const params = new URLSearchParams({
        from_date: previous_date || "",
        to_date: previous_date || "",
        location: site || "",
        machine_scope: "Include Swing/Spare"
    });

    params.delete("from_date");
    params.delete("to_date");
    params.delete("location");
    params.delete("machine_scope");
    params.set("start_date", previous_date || "");
    params.set("end_date", previous_date || "");
    params.set("site", site || "");
    params.set("summary_type", "Average Per Machine");
    params.set("asset_ownership", "Isambane & Excavo Assets");

    return window.location.origin + "/desk/daily-availability-and-utilization-dashboard?" + params.toString();
}



function get_avail_util_bubble_html(row) {
    row = row || {};

    const raw_availability = row.availability;
    const raw_utilisation = row.utilisation;

    const label = frappe.utils.escape_html(row.label || "");
    const availability = format_avail_util_percent(raw_availability);
    const utilisation = format_avail_util_percent(raw_utilisation);

    const availability_class = get_avail_util_colour_class(raw_availability, "availability");
    const utilisation_class = get_avail_util_colour_class(raw_utilisation, "utilisation");
    const working_hours = format_avail_util_hours(row.working_hours);
    const breakdown_hours = format_avail_util_hours(row.breakdown_hours);

    return `
        <div class="downtime-avail-util-bubble">
            <strong>${label}</strong>
            <div class="downtime-avail-util-values">
                <div class="downtime-avail-util-value ${availability_class}">Avail<br>${availability}</div>
                <div class="downtime-avail-util-value ${utilisation_class}">Util<br>${utilisation}</div>
            </div>
            <div class="downtime-avail-util-hours">
                Avg Work: ${working_hours} &nbsp;|&nbsp; Avg Breakdown: ${breakdown_hours}
            </div>
        </div>
    `;
}

function format_avail_util_hours(value) {
    if (value === null || value === undefined || value === "") {
        return "-";
    }

    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2) + "h" : "-";
}

function get_avail_util_colour_class(value, type) {
    if (value === null || value === undefined || value === "") {
        return "downtime-au-na";
    }

    const percent = flt(value);

    if (type === "availability") {
        if (percent <= 75) {
            return "downtime-au-red";
        }

        if (percent <= 84) {
            return "downtime-au-yellow";
        }

        return "downtime-au-green";
    }

    if (percent <= 70) {
        return "downtime-au-red";
    }

    if (percent <= 79) {
        return "downtime-au-yellow";
    }

    return "downtime-au-green";
}


function format_avail_util_percent(value) {
    if (value === null || value === undefined || value === "") {
        return "N/A";
    }

    return flt(value).toFixed(1) + "%";
}

function get_mobile_downtime_comments() {
    const comments = {};

    $(".mobile-downtime-comment-input, .downtime-comment-input").each(function () {
        const plant_no = $(this).data("plant-no");
        const comment = ($(this).val() || "").trim();

        if (plant_no && comment) {
            comments[plant_no] = comment;
            downtime_mobile_comment_cache[plant_no] = comment;
        }
    });

    Object.keys(downtime_mobile_comment_cache || {}).forEach(function (plant_no) {
        const comment = (downtime_mobile_comment_cache[plant_no] || "").trim();

        if (plant_no && comment) {
            comments[plant_no] = comment;
        }
    });

    return comments;
}


function all_downtime_records_verified() {
    const checkboxes = $(".downtime-verify-checkbox:visible");

    if (!checkboxes.length) {
        return true;
    }

    let all_verified = true;

    checkboxes.each(function () {
        if (!$(this).is(":checked")) {
            all_verified = false;
        }
    });

    return all_verified;
}

// === DOWNTIME SELECTED DATE PRINT PREVIEW V3 START ===

(function () {
    const settings =
        frappe.query_reports["Down Time"];

    if (!settings) {
        return;
    }

    if (
        settings.__downtime_selected_print_v3
    ) {
        return;
    }

    settings.__downtime_selected_print_v3 = true;

    const original_onload = settings.onload;


    settings.onload = function (report) {
        if (
            typeof original_onload === "function"
        ) {
            original_onload.apply(
                this,
                arguments
            );
        }

        setTimeout(function () {
            install_downtime_export_button(
                report
            );

            install_downtime_print_button(
                report
            );
        }, 300);
    };


    function get_filter_value(
        report,
        names
    ) {
        for (const name of names) {
            try {
                if (
                    report &&
                    typeof report.get_filter ===
                        "function"
                ) {
                    const filter =
                        report.get_filter(name);

                    if (filter) {
                        const value =
                            filter.get_value();

                        if (
                            value !== undefined &&
                            value !== null &&
                            String(value).trim() !== ""
                        ) {
                            return value;
                        }
                    }
                }
            } catch (e) {
                // Continue.
            }

            try {
                if (
                    frappe.query_report &&
                    typeof frappe.query_report
                        .get_filter_value ===
                        "function"
                ) {
                    const value =
                        frappe.query_report
                            .get_filter_value(
                                name
                            );

                    if (
                        value !== undefined &&
                        value !== null &&
                        String(value).trim() !== ""
                    ) {
                        return value;
                    }
                }
            } catch (e) {
                // Continue.
            }
        }

        return "";
    }


    function get_current_filters(report) {
        return {
            report_date:
                get_filter_value(
                    report,
                    [
                        "report_date",
                        "date",
                    ]
                ),

            site:
                get_filter_value(
                    report,
                    [
                        "site",
                        "location",
                        "location1",
                    ]
                ),

            asset_category:
                get_filter_value(
                    report,
                    [
                        "asset_category",
                    ]
                ),

            shift:
                get_filter_value(
                    report,
                    ["shift"]
                ),
        };
    }


    function install_downtime_export_button(
        report
    ) {
        if (
            !report ||
            !report.page
        ) {
            return;
        }

        const $wrapper =
            report.page.$wrapper ||
            $(
                report.page.wrapper ||
                document.body
            );

        if (
            $wrapper.find(
                ".dt-selected-export-v3"
            ).length
        ) {
            return;
        }

        const $button =
            report.page.add_inner_button(
                __("Export Excel"),
                function () {
                    const filters =
                        get_current_filters(
                            report
                        );

                    if (!filters.report_date) {
                        frappe.msgprint(
                            __(
                                "Please select a date first."
                            )
                        );

                        return;
                    }

                    const params =
                        new URLSearchParams();

                    params.set(
                        "report_date",
                        filters.report_date
                    );

                    params.set(
                        "site",
                        filters.site || ""
                    );

                    params.set(
                        "asset_category",
                        filters.asset_category || ""
                    );

                    params.set(
                        "shift",
                        filters.shift || ""
                    );

                    const method =
                        "engineering.engineering.report." +
                        "down_time.down_time." +
                        "export_selected_downtime_excel";

                    window.location.href =
                        "/api/method/" +
                        method +
                        "?" +
                        params.toString();
                }
            );

        if ($button && $button.addClass) {
            $button.addClass(
                "dt-selected-export-v3"
            );
        }
    }


    function install_downtime_print_button(
        report
    ) {
        if (
            !report ||
            !report.page
        ) {
            return;
        }

        const $wrapper =
            report.page.$wrapper ||
            $(
                report.page.wrapper ||
                document.body
            );

        if (
            $wrapper.find(
                ".dt-print-preview-v3"
            ).length
        ) {
            return;
        }

        const $button =
            report.page.add_inner_button(
                "🖨",
                function () {
                    open_downtime_print_preview(
                        report
                    );
                }
            );

        if ($button && $button.addClass) {
            $button.addClass(
                "dt-print-preview-v3"
            );

            $button.attr(
                "title",
                __("Print / Screenshot")
            );

            $button.css({
                "min-width": "46px",
                "min-height": "36px",
                "padding-left": "10px",
                "padding-right": "10px",
                "font-size": "22px",
                "line-height": "1",
                "display": "inline-flex",
                "align-items": "center",
                "justify-content": "center",
            });
        }
    }


    function open_downtime_print_preview(
        report
    ) {
        const filters =
            get_current_filters(report);

        if (!filters.report_date) {
            frappe.msgprint(
                __(
                    "Please select a date first."
                )
            );

            return;
        }

        frappe.call({
            method:
                "engineering.engineering.report." +
                "down_time.down_time." +
                "get_selected_downtime_print_data",

            args: {
                report_date:
                    filters.report_date,

                site:
                    filters.site || "",

                asset_category:
                    filters.asset_category || "",

                shift:
                    filters.shift || "",
            },

            freeze: true,

            freeze_message:
                __("Loading downtime..."),

            callback: function (r) {
                const data =
                    r.message || {};

                show_downtime_print_dialog(
                    data
                );
            },
        });
    }


    function escape_html(value) {
        return frappe.utils.escape_html(
            String(
                value === undefined ||
                value === null
                    ? ""
                    : value
            )
        );
    }


    function build_downtime_preview_html(
        data
    ) {
        const rows =
            Array.isArray(data.rows)
                ? data.rows
                : [];

        const body = rows.length
            ? rows.map(function (row) {
                const status =
                    String(
                        row.status || ""
                    );

                const status_class =
                    status.toLowerCase() ===
                    "closed"
                        ? "dtp-status-closed"
                        : "dtp-status-open";

                return `
                    <tr>
                        <td class="dtp-fleet">
                            ${escape_html(row.fleet_no)}
                        </td>

                        <td class="dtp-reason">
                            ${escape_html(row.reason)}
                        </td>

                        <td class="${status_class}">
                            ${escape_html(row.status)}
                        </td>

                        <td class="dtp-center dtp-downtime">
                            ${escape_html(row.downtime)}
                        </td>

                        <td class="dtp-center">
                            ${escape_html(row.start)}
                        </td>

                        <td class="dtp-center">
                            ${escape_html(
                                row.back_in_production
                            )}
                        </td>
                    </tr>
                `;
            }).join("")
            : `
                <tr>
                    <td colspan="6"
                        class="dtp-empty">
                        No downtime records found
                        for this selected date and shift.
                    </td>
                </tr>
            `;

        return `
            <style>
                .dt-print-preview-shell {
                    background: #ffffff;
                    padding: 14px;
                    font-family:
                        Arial,
                        Helvetica,
                        sans-serif;
                    color: #111;
                }

                .dtp-report {
                    border:
                        1px solid #a9c9ad;
                    border-radius: 7px;
                    overflow: hidden;
                    background: #ffffff;
                }

                .dtp-title {
                    padding:
                        12px 12px 5px 12px;
                    text-align: center;
                    font-weight: 700;
                    font-size: 14px;
                    color: #16812c;
                    background: #f4fbf4;
                }

                .dtp-window {
                    padding:
                        5px 12px 11px 12px;
                    text-align: center;
                    font-weight: 700;
                    font-size: 12px;
                    color: #16812c;
                    background: #f4fbf4;
                    border-bottom:
                        1px solid #a9c9ad;
                }

                .dtp-meta {
                    text-align: center;
                    padding: 7px 10px;
                    font-size: 12px;
                    color: #555;
                    border-bottom:
                        1px solid #d7e5d8;
                }

                .dtp-table {
                    width: 100%;
                    border-collapse: collapse;
                    table-layout: fixed;
                    font-size: 12px;
                    color: #111;
                    font-weight: 600;
                }

                .dtp-table th {
                    padding: 9px 6px;
                    border-right:
                        1px solid #d5dfd6;
                    border-bottom:
                        1px solid #c7d5c8;
                    background: #fafafa;
                    text-align: center;
                    font-weight: 700;
                    font-size: 11px;
                }

                .dtp-table th:last-child {
                    border-right: none;
                }

                .dtp-table td {
                    padding: 9px 7px;
                    border-right:
                        1px solid #dfe6df;
                    border-bottom:
                        1px solid #dfe6df;
                    vertical-align: middle;
                    line-height: 1.35;
                    font-size: 11px;
                    font-weight: 600;
                    word-wrap: break-word;
                }

                .dtp-table td:last-child {
                    border-right: none;
                }

                .dtp-table tr:last-child td {
                    border-bottom: none;
                }

                .dtp-fleet {
                    width: 10%;
                    font-weight: 800;
                    text-align: center;
                }

                .dtp-reason {
                    width: 28%;
                }

                .dtp-center {
                    text-align: center;
                    white-space: nowrap;
                }

                .dtp-downtime {
                    font-weight: 700;
                }

                .dtp-status-closed {
                    text-align: center;
                    color: #222;
                }

                .dtp-status-open {
                    text-align: center;
                    font-weight: 800;
                    color: #a25000;
                }

                .dtp-footer {
                    padding: 8px 10px;
                    text-align: center;
                    color: #16812c;
                    background: #f4fbf4;
                    border-top:
                        1px solid #a9c9ad;
                    font-weight: 700;
                    font-size: 12px;
                }

                .dtp-empty {
                    padding: 32px !important;
                    text-align: center;
                    color: #777;
                    font-style: italic;
                    font-size: 12px;
                    font-weight: 600;
                }

                .dtp-col-fleet {
                    width: 10%;
                }

                .dtp-col-reason {
                    width: 27%;
                }

                .dtp-col-status {
                    width: 10%;
                }

                .dtp-col-downtime {
                    width: 10%;
                }

                .dtp-col-start {
                    width: 21.5%;
                }

                .dtp-col-back {
                    width: 21.5%;
                }

                @media print {
                    body {
                        margin: 0;
                    }

                    .dt-print-preview-shell {
                        padding: 0;
                    }
                }
            </style>

            <div class="dt-print-preview-shell">
                <div class="dtp-report">

                    <div class="dtp-title">
                        ${escape_html(data.heading || "DOWNTIME")}
                    </div>

                    <div class="dtp-window">
                        ${escape_html(data.window_start)}
                        &nbsp;&rarr;&nbsp;
                        ${escape_html(data.window_end)}
                    </div>

                    <div class="dtp-meta">
                        ${escape_html(data.site || "")}
                        ${
                            data.asset_category &&
                            data.asset_category !==
                                "All Equipment"
                                ? " | " +
                                  escape_html(
                                      data.asset_category
                                  )
                                : ""
                        }
                    </div>

                    <table class="dtp-table">
                        <colgroup>
                            <col class="dtp-col-fleet">
                            <col class="dtp-col-reason">
                            <col class="dtp-col-status">
                            <col class="dtp-col-downtime">
                            <col class="dtp-col-start">
                            <col class="dtp-col-back">
                        </colgroup>

                        <thead>
                            <tr>
                                <th>Fleet No.</th>
                                <th>Reason</th>
                                <th>Status</th>
                                <th>Downtime</th>
                                <th>Start</th>
                                <th>Back in Production</th>
                            </tr>
                        </thead>

                        <tbody>
                            ${body}
                        </tbody>
                    </table>

                    <div class="dtp-footer">
                        (${escape_html(data.footer || "")})
                    </div>

                </div>
            </div>
        `;
    }


    function show_downtime_print_dialog(
        data
    ) {
        const html =
            build_downtime_preview_html(
                data
            );

        const dialog =
            new frappe.ui.Dialog({
                title:
                    __("Downtime Print / Screenshot"),

                size: "extra-large",

                fields: [
                    {
                        fieldtype: "HTML",
                        fieldname:
                            "downtime_print_preview",
                    },
                ],

                primary_action_label:
                    __("Print"),

                primary_action:
                    function () {
                        print_downtime_preview(
                            data
                        );
                    },
            });

        dialog.fields_dict
            .downtime_print_preview
            .$wrapper
            .html(html);

        dialog.show();

        setTimeout(function () {
            dialog.$wrapper
                .find(".modal-dialog")
                .css(
                    "max-width",
                    "1280px"
                );

            dialog.$wrapper
                .find(".modal-body")
                .css({
                    "padding": "12px",
                    "background": "#f7f7f7",
                });
        }, 50);
    }


    function print_downtime_preview(
        data
    ) {
        const preview_html =
            build_downtime_preview_html(
                data
            );

        const print_window =
            window.open(
                "",
                "_blank",
                "width=1200,height=800"
            );

        if (!print_window) {
            frappe.msgprint(
                __(
                    "Please allow pop-ups to print this report."
                )
            );

            return;
        }

        print_window.document.open();

        print_window.document.write(`
            <!doctype html>
            <html>
                <head>
                    <meta charset="utf-8">

                    <title>
                        Downtime
                    </title>

                    <style>
                        @page {
                            size: A4 landscape;
                            margin: 10mm;
                        }

                        body {
                            margin: 0;
                            padding: 0;
                            background: #ffffff;
                        }
                    </style>
                </head>

                <body>
                    ${preview_html}
                </body>
            </html>
        `);

        print_window.document.close();

        print_window.focus();

        setTimeout(function () {
            print_window.print();
        }, 350);
    }
})();

// === DOWNTIME SELECTED DATE PRINT PREVIEW V3 END ===


// === SAVED HOURLY / DAILY DOWNTIME REPORTS START ===

(function install_saved_downtime_reports() {
    const settings = frappe.query_reports["Down Time"];

    if (!settings || settings.__saved_downtime_reports) {
        return;
    }

    settings.__saved_downtime_reports = true;

    const original_onload = settings.onload;
    const original_refresh = settings.refresh;

    settings.onload = function(report) {
        if (typeof original_onload === "function") {
            original_onload.apply(this, arguments);
        }

        window.setTimeout(() => setup_saved_reports(report), 200);
    };

    settings.refresh = function(report) {
        if (typeof original_refresh === "function") {
            original_refresh.apply(this, arguments);
        }

        window.setTimeout(() => {
            setup_saved_reports(report);

            // Main filters belong to Downtime Sign-Off.
            // Keep its report visible while Frappe renders.
            report.__active_downtime_tab = "signoff";

            show_downtime_tab(
                report,
                "signoff"
            );

            render_downtime_cards(report);
        }, 200);
    };


    function setup_saved_reports(report) {
        if (!report || !report.page) {
            return;
        }

        const $main = report.page.main || report.page.$wrapper;

        if (!$main || $main.find(".dt-report-tabs").length) {
            return;
        }

        report.__active_downtime_tab = "signoff";

        const html = `
            <style>
                .dt-report-tabs {
                    display:flex;
                    gap:8px;
                    margin:12px 0;
                    flex-wrap:wrap;
                }

                .dt-saved-reports-panel {
                    display:none;
                    background:#f5f7fa;
                    border:1px solid #d8dce3;
                    border-radius:8px;
                    padding:16px;
                    margin-bottom:16px;
                }

                .dt-saved-filter-grid {
                    display:grid;
                    grid-template-columns:
                        repeat(auto-fit, minmax(260px, 1fr));
                    gap:12px;
                    align-items:end;
                }

                .dt-saved-filter label {
                    display:block;
                    font-weight:700;
                    margin-bottom:6px;
                }

                .dt-saved-filter select {
                    width:100%;
                    min-height:36px;
                }

                .dt-saved-report-preview {
                    margin-top:16px;
                    background:#fff;
                    border:1px solid #cfd5dd;
                    border-radius:8px;
                    padding:24px;
                    color:#111;
                }

                .dt-saved-report-title {
                    text-align:center;
                    font-size:22px;
                    font-weight:800;
                    color:#173f73;
                    margin-bottom:6px;
                }

                .dt-saved-report-meta {
                    text-align:center;
                    color:#52606d;
                    font-weight:600;
                    padding-bottom:14px;
                    margin-bottom:16px;
                    border-bottom:2px solid #dbeafe;
                }

                .dt-saved-report-message {
                    white-space:pre-wrap;
                    font-family:Arial, sans-serif;
                    font-size:15px;
                    line-height:1.55;
                    margin:0;
                }

                .dt-saved-actions {
                    display:flex;
                    gap:8px;
                    margin-top:14px;
                    flex-wrap:wrap;
                }
            </style>

            <div class="dt-report-tabs">
                <button
                    type="button"
                    class="btn btn-primary dt-report-tab"
                    data-tab="signoff">
                    ${__("Downtime Sign-Off")}
                </button>

                <button
                    type="button"
                    class="btn btn-default dt-report-tab"
                    data-tab="saved">
                    ${__("Hourly/Daily Reports")}
                </button>
            </div>

            <div class="dt-saved-reports-panel">
                <div class="dt-saved-filter-grid">
                    <div class="dt-saved-filter dt-hourly-filter">
                        <label>${__("Hourly Downtime Report")}</label>
                        <select class="form-control dt-hourly-select">
                            <option value="">
                                ${__("Select Hourly Report")}
                            </option>
                        </select>
                    </div>

                    <div class="dt-saved-filter dt-daily-filter">
                        <label>${__("Daily Downtime Report")}</label>
                        <select class="form-control dt-daily-select">
                            <option value="">
                                ${__("Select Daily Report")}
                            </option>
                        </select>
                    </div>
                </div>

                <div class="dt-saved-actions">
                    <button
                        type="button"
                        class="btn btn-default dt-clear-saved-report">
                        ${__("Clear Selection")}
                    </button>

                    <button
                        type="button"
                        class="btn btn-primary dt-download-saved-jpeg"
                        style="display:none;">
                        ${__("Download Report")}
                    </button>
                </div>

                <div
                    class="dt-saved-report-preview"
                    style="display:none;">
                </div>
            </div>
        `;

        const $report_wrapper = $main.find(".report-wrapper").first();

        if ($report_wrapper.length) {
            $report_wrapper.before(html);
        } else {
            $main.prepend(html);
        }

        bind_saved_report_actions(report, $main);
        load_saved_report_options($main);
    }


    function show_downtime_tab(report, tab) {
        const $main = report.page.main || report.page.$wrapper;
        const saved = tab === "saved";

        report.__active_downtime_tab = tab;

        $main.find(".dt-report-tab")
            .removeClass("btn-primary")
            .addClass("btn-default");

        $main.find(
            `.dt-report-tab[data-tab="${tab}"]`
        )
            .removeClass("btn-default")
            .addClass("btn-primary");

        $main.find(".dt-saved-reports-panel").toggle(saved);
        $main.find(".report-wrapper").toggle(!saved);

        $(".downtime-signoff-action-wrapper").toggle(!saved);
        $(".mobile-downtime-wrapper").toggle(!saved);
        $(".downtime-avail-util-wrapper").toggle(!saved);
    }


    function bind_saved_report_actions(report, $main) {
        $main
            .off("click.dt_report_tab", ".dt-report-tab")
            .on("click.dt_report_tab", ".dt-report-tab", function() {
                const tab = $(this).data("tab");

                show_downtime_tab(
                    report,
                    tab
                );

                if (tab === "saved") {
                    load_saved_report_options($main);
                }
            });

        $main
            .off("change.dt_hourly", ".dt-hourly-select")
            .on("change.dt_hourly", ".dt-hourly-select", function() {
                const name = $(this).val();

                if (!name) {
                    reset_saved_report_filters($main);
                    return;
                }

                $main.find(".dt-daily-filter").hide();

                load_saved_report(
                    $main,
                    "Hourly Downtime Summary",
                    name
                );
            });

        $main
            .off("change.dt_daily", ".dt-daily-select")
            .on("change.dt_daily", ".dt-daily-select", function() {
                const name = $(this).val();

                if (!name) {
                    reset_saved_report_filters($main);
                    return;
                }

                $main.find(".dt-hourly-filter").hide();

                load_saved_report(
                    $main,
                    "Daily Downtime Summary",
                    name
                );
            });

        $main
            .off("click.dt_clear", ".dt-clear-saved-report")
            .on("click.dt_clear", ".dt-clear-saved-report", function() {
                reset_saved_report_filters($main);
            });

        $main
            .off("click.dt_jpeg", ".dt-download-saved-jpeg")
            .on("click.dt_jpeg", ".dt-download-saved-jpeg", function() {
                download_saved_report_jpeg($main);
            });
    }


    function load_saved_report_options($main) {
        const site = frappe.query_report.get_filter_value("site");

        const $hourly = $main.find(".dt-hourly-select");
        const $daily = $main.find(".dt-daily-select");

        $hourly.html(
            `<option value="">${__("Select Hourly Report")}</option>`
        );

        $daily.html(
            `<option value="">${__("Select Daily Report")}</option>`
        );

        reset_saved_report_filters($main);

        if (!site) {
            return;
        }

        frappe.call({
            method:
                "engineering.engineering.report.down_time.down_time." +
                "get_saved_downtime_summary_options",

            args: {
                site: site
            },

            callback: function(response) {
                const data = response.message || {};

                populate_summary_select(
                    $hourly,
                    data.hourly || [],
                    "hourly"
                );

                populate_summary_select(
                    $daily,
                    data.daily || [],
                    "daily"
                );
            }
        });
    }

    function populate_summary_select($select, rows, type) {
        rows.forEach(row => {
            const extra = type === "hourly"
                ? row.hour_slot || ""
                : row.shift || "";

            const label = [
                row.report_date,
                row.site,
                extra
            ].filter(Boolean).join(" | ");

            $("<option>")
                .val(row.name)
                .text(label)
                .appendTo($select);
        });
    }


    function load_saved_report($main, doctype, name) {
        frappe.call({
            method:
                "engineering.engineering.report.down_time.down_time." +
                "get_saved_downtime_summary",

            args: {
                doctype: doctype,
                name: name
            },

            freeze: true,
            freeze_message: __("Loading saved report..."),

            callback: function(response) {
                const data = response.message || {};

                render_saved_report($main, data);
            }
        });
    }


    function render_saved_report($main, data) {
        const hourly =
            data.doctype === "Hourly Downtime Summary";

        const title = hourly
            ? __("Hourly Downtime Report")
            : __("Daily Downtime Report");

        const period = hourly
            ? data.hour_slot || ""
            : data.shift || "";

        const all_rows = Array.isArray(data.report_rows)
            ? data.report_rows.map(row => ({
                plant:
                    row.plant_no
                    || row.asset_name
                    || "-",

                category:
                    row.category_group
                    || row.asset_category
                    || "Other",

                status:
                    row.status_key
                    || row.open_closed
                    || row.status
                    || "",

                hours: Number(
                    hourly
                        ? row.open_hours || 0
                        : row.breakdown_hours || 0
                ),

                reason:
                    row.reason
                    || row.breakdown_reason
                    || "-",

                start:
                    row.start_time
                    || row.breakdown_start_datetime
                    || "-",

                resolved:
                    row.resolved_time
                    || row.resolved_datetime
                    || "OPEN"
            }))
            : [];

        // Display breakdown events only: open and closed.
        // Available machines remain hidden.
        const rows = all_rows.filter(row => {
            const status = String(row.status).toLowerCase();

            return (
                status.includes("open")
                || status.includes("closed")
            );
        });

        const open_rows = rows.filter(row =>
            String(row.status).toLowerCase().includes("open")
        );

        const closed_rows = rows.filter(row =>
            String(row.status).toLowerCase().includes("closed")
        );

        const available_rows =
            all_rows.length - open_rows.length;

        const category_map = {};

        all_rows.forEach(row => {
            const category = row.category || "Other";

            if (!category_map[category]) {
                category_map[category] = {
                    category: category,
                    total: 0,
                    available: 0,
                    down: 0
                };
            }

            category_map[category].total += 1;

            if (
                String(row.status)
                    .toLowerCase()
                    .includes("open")
            ) {
                category_map[category].down += 1;
            } else {
                category_map[category].available += 1;
            }
        });

        const category_summaries = Object.values(
            category_map
        )
            .map(summary => {
                const percentage = summary.total
                    ? (summary.available / summary.total) * 100
                    : 0;

                return {
                    ...summary,
                    percentage: percentage,
                    colour:
                        percentage >= 85
                            ? "green"
                            : percentage >= 80
                                ? "yellow"
                                : "red"
                };
            })
            .sort((a, b) =>
                a.category.localeCompare(b.category)
            );

        const category_html = category_summaries
            .map(summary => `
                <div class="dt-modern-category-card ${summary.colour}">
                    <div>
                        <strong>
                            ${summary.available}/${summary.total}
                        </strong>
                        <span>${frappe.utils.escape_html(summary.category)}</span>
                    </div>

                    <small class="${
                        summary.down > 0
                            ? "has-down"
                            : "all-clear"
                    }">
                        ${summary.down} ${__("down")}
                    </small>
                </div>
            `)
            .join("");

        const total_hours = rows.reduce(
            (total, row) => total + row.hours,
            0
        );

        const row_html = rows.length
            ? rows.map(row => {
                const is_open = String(row.status)
                    .toLowerCase()
                    .includes("open");

                return `
                    <div class="dt-modern-row ${is_open ? "is-open" : "is-available"}">
                        <div class="dt-modern-machine">
                            <span class="dt-modern-machine-icon">
                                ${is_open ? "⚠" : "✓"}
                            </span>

                            <div>
                                <strong>${frappe.utils.escape_html(row.plant)}</strong>
                                <small>${frappe.utils.escape_html(row.category)}</small>
                            </div>
                        </div>

                        <div class="dt-modern-reason">
                            <span>${__("Reason")}</span>
                            <strong>${frappe.utils.escape_html(row.reason)}</strong>
                        </div>

                        <div class="dt-modern-time">
                            <span>${__("Start")}</span>
                            <strong>${frappe.utils.escape_html(row.start)}</strong>
                        </div>

                        <div class="dt-modern-hours">
                            <span>${__("Downtime")}</span>
                            <strong>${format_saved_duration(row.hours)}</strong>
                        </div>

                        <div>
                            <span class="dt-modern-status ${is_open ? "open" : "available"}">
                                ${is_open ? __("OPEN") : __("CLOSED")}
                            </span>
                        </div>
                    </div>
                `;
            }).join("")
            : `
                <div class="dt-modern-empty">
                    ${__("No downtime information found.")}
                </div>
            `;

        const meta = [
            data.site,
            data.report_date,
            period
        ].filter(Boolean).join(" • ");

        $main.find(".dt-saved-report-preview")
            .html(`
                <style>
                    .dt-modern-report {
                        overflow:hidden;
                        border-radius:16px;
                        background:#f4f7fb;
                        box-shadow:0 10px 35px rgba(15,23,42,.12);
                    }

                    .dt-modern-header {
                        padding:28px;
                        color:#fff;
                        background:
                            linear-gradient(135deg,#0f172a,#1d4ed8);
                    }

                    .dt-modern-header h2 {
                        margin:0 0 8px;
                        color:#fff;
                        font-size:25px;
                        font-weight:900;
                    }

                    .dt-modern-header p {
                        margin:0;
                        color:#dbeafe;
                        font-size:14px;
                        font-weight:600;
                    }

                    .dt-modern-kpis {
                        display:grid;
                        grid-template-columns:repeat(4,minmax(130px,1fr));
                        gap:12px;
                        padding:18px;
                    }

                    .dt-modern-kpi {
                        padding:16px;
                        border-radius:12px;
                        background:#fff;
                        border-left:5px solid #2563eb;
                        box-shadow:0 3px 12px rgba(15,23,42,.07);
                    }

                    .dt-modern-kpi.red {
                        border-left-color:#dc2626;
                    }

                    .dt-modern-kpi.green {
                        border-left-color:#16a34a;
                    }

                    .dt-modern-kpi.orange {
                        border-left-color:#f59e0b;
                    }

                    .dt-modern-kpi span {
                        display:block;
                        color:#64748b;
                        font-size:11px;
                        font-weight:800;
                        text-transform:uppercase;
                    }

                    .dt-modern-kpi strong {
                        display:block;
                        margin-top:5px;
                        color:#0f172a;
                        font-size:24px;
                    }

                    .dt-modern-category-section {
                        padding:0 18px 18px;
                    }

                    .dt-modern-category-title {
                        margin-bottom:9px;
                        color:#475569;
                        font-size:12px;
                        font-weight:900;
                        text-transform:uppercase;
                    }

                    .dt-modern-category-grid {
                        display:grid;
                        grid-template-columns:
                            repeat(auto-fit,minmax(150px,1fr));
                        gap:10px;
                    }

                    .dt-modern-category-card {
                        display:flex;
                        align-items:center;
                        justify-content:space-between;
                        padding:12px 14px;
                        border-radius:11px;
                        background:#fff;
                        border:1px solid #dbe4ef;
                        border-top:4px solid #2563eb;
                    }

                    .dt-modern-category-card.green {
                        border-top-color:#16a34a;
                        background:#f0fdf4;
                    }

                    .dt-modern-category-card.yellow {
                        border-top-color:#f59e0b;
                        background:#fffbeb;
                    }

                    .dt-modern-category-card.red {
                        border-top-color:#dc2626;
                        background:#fef2f2;
                    }

                    .dt-modern-category-card strong {
                        display:block;
                        color:#0f172a;
                        font-size:22px;
                    }

                    .dt-modern-category-card span {
                        display:block;
                        color:#475569;
                        font-size:12px;
                        font-weight:800;
                    }

                    .dt-modern-category-card small {
                        padding:5px 8px;
                        border-radius:15px;
                        font-weight:800;
                    }

                    .dt-modern-category-card small.has-down {
                        color:#991b1b;
                        background:#fee2e2;
                    }

                    .dt-modern-category-card small.all-clear {
                        color:#166534;
                        background:#dcfce7;
                    }

                    .dt-modern-body {
                        padding:0 18px 20px;
                    }

                    .dt-modern-row {
                        display:grid;
                        grid-template-columns:
                            minmax(150px,1fr)
                            minmax(220px,2fr)
                            minmax(170px,1.2fr)
                            110px
                            110px;
                        gap:14px;
                        align-items:center;
                        margin-bottom:10px;
                        padding:15px;
                        background:#fff;
                        border:1px solid #e2e8f0;
                        border-radius:12px;
                    }

                    .dt-modern-row.is-open {
                        border-left:5px solid #ef4444;
                    }

                    .dt-modern-row.is-available {
                        border-left:5px solid #22c55e;
                    }

                    .dt-modern-machine {
                        display:flex;
                        align-items:center;
                        gap:10px;
                    }

                    .dt-modern-machine-icon {
                        display:flex;
                        width:34px;
                        height:34px;
                        align-items:center;
                        justify-content:center;
                        border-radius:50%;
                        background:#fee2e2;
                        color:#b91c1c;
                        font-weight:900;
                    }

                    .is-available .dt-modern-machine-icon {
                        background:#dcfce7;
                        color:#15803d;
                    }

                    .dt-modern-machine strong,
                    .dt-modern-reason strong,
                    .dt-modern-time strong,
                    .dt-modern-hours strong {
                        display:block;
                        color:#172033;
                    }

                    .dt-modern-machine small,
                    .dt-modern-row span:not(.dt-modern-status):not(.dt-modern-machine-icon) {
                        display:block;
                        color:#64748b;
                        font-size:11px;
                        font-weight:700;
                    }

                    .dt-modern-reason strong {
                        font-size:12px;
                    }

                    .dt-modern-status {
                        display:inline-block;
                        padding:7px 11px;
                        border-radius:20px;
                        font-size:11px;
                        font-weight:900;
                    }

                    .dt-modern-status.open {
                        color:#991b1b;
                        background:#fee2e2;
                    }

                    .dt-modern-status.available {
                        color:#166534;
                        background:#dcfce7;
                    }

                    .dt-modern-empty {
                        padding:35px;
                        text-align:center;
                        color:#64748b;
                        background:#fff;
                        border-radius:12px;
                    }

                    @media (max-width:900px) {
                        .dt-modern-kpis {
                            grid-template-columns:repeat(2,1fr);
                        }

                        .dt-modern-row {
                            grid-template-columns:1fr;
                        }
                    }
                </style>

                <div class="dt-modern-report">
                    <div class="dt-modern-header">
                        <h2>${frappe.utils.escape_html(title)}</h2>
                        <p>${frappe.utils.escape_html(meta)}</p>
                    </div>

                    <div class="dt-modern-kpis">
                        <div class="dt-modern-kpi">
                            <span>${__("Breakdown Records")}</span>
                            <strong>${rows.length}</strong>
                        </div>

                        <div class="dt-modern-kpi red">
                            <span>${__("Open Breakdowns")}</span>
                            <strong>${open_rows.length}</strong>
                        </div>

                        <div class="dt-modern-kpi green">
                            <span>${hourly ? __("Available") : __("Closed")}</span>
                            <strong>${available_rows}</strong>
                        </div>

                        <div class="dt-modern-kpi orange">
                            <span>${__("Total Downtime")}</span>
                            <strong>${format_saved_duration(total_hours)}</strong>
                        </div>
                    </div>

                    <div class="dt-modern-category-section">
                        <div class="dt-modern-category-title">
                            ${__("Fleet availability by category")}
                        </div>

                        <div class="dt-modern-category-grid">
                            ${category_html}
                        </div>
                    </div>

                    <div class="dt-modern-body">
                        ${row_html}
                    </div>
                </div>
            `)
            .show()
            .data("report", {
                title: title,
                meta: meta,
                message: data.summary_message || "",
                name: data.name,
                rows: rows,
                all_count: all_rows.length,
                available_count: available_rows,
                category_summaries: category_summaries
            });

        $main.find(".dt-download-saved-jpeg")
            .text(
                hourly
                    ? __("Download Hourly Report")
                    : __("Download Daily Report")
            )
            .show();
    }

    function reset_saved_report_filters($main) {
        $main.find(".dt-hourly-select").val("");
        $main.find(".dt-daily-select").val("");
        $main.find(".dt-hourly-filter").show();
        $main.find(".dt-daily-filter").show();
        $main.find(".dt-saved-report-preview").hide().empty();
        $main.find(".dt-download-saved-jpeg").hide();
    }


    function download_saved_report_jpeg($main) {
        const report =
            $main.find(".dt-saved-report-preview").data("report");

        if (!report) {
            frappe.msgprint(__("Please select a report first."));
            return;
        }

        const rows = Array.isArray(report.rows)
            ? report.rows
            : [];

        const open_rows = rows.filter(row =>
            String(row.status).toLowerCase().includes("open")
        );

        const available_count =
            Number(report.available_count || 0);

        const total_hours = rows.reduce(
            (total, row) => total + Number(row.hours || 0),
            0
        );

        const category_summaries =
            Array.isArray(report.category_summaries)
                ? report.category_summaries
                : [];

        const category_rows = Math.ceil(
            category_summaries.length / 4
        );

        const fleet_height = category_summaries.length
            ? 65 + (category_rows * 105)
            : 0;

        const width = 1600;
        const padding = 55;
        const row_height = 125;
        const header_height = 190;
        const kpi_height = 145;

        const height = Math.max(
            760,
            header_height
                + kpi_height
                + fleet_height
                + 90
                + (rows.length * row_height)
        );

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext("2d");

        // Keep the outer canvas transparent for presentations.
        ctx.clearRect(0, 0, width, height);

        const gradient = ctx.createLinearGradient(
            0,
            0,
            width,
            header_height
        );

        gradient.addColorStop(0, "#0f172a");
        gradient.addColorStop(1, "#1d4ed8");

        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, width, header_height);

        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 48px Arial";
        ctx.textAlign = "left";
        ctx.fillText(report.title, padding, 78);

        ctx.fillStyle = "#dbeafe";
        ctx.font = "bold 25px Arial";
        ctx.fillText(report.meta, padding, 125);

        const kpis = [
            {
                label: "BREAKDOWN RECORDS",
                value: String(rows.length),
                colour: "#2563eb"
            },
            {
                label: "OPEN BREAKDOWNS",
                value: String(open_rows.length),
                colour: "#dc2626"
            },
            {
                label: "AVAILABLE AT END",
                value: String(available_count),
                colour: "#16a34a"
            },
            {
                label: "TOTAL DOWNTIME",
                value: format_saved_duration(total_hours),
                colour: "#f59e0b"
            }
        ];

        const gap = 20;
        const card_width =
            (width - (padding * 2) - (gap * 3)) / 4;

        kpis.forEach((kpi, index) => {
            const x = padding + index * (card_width + gap);
            const y = header_height + 28;

            draw_canvas_round_rect(
                ctx,
                x,
                y,
                card_width,
                105,
                14,
                "#ffffff"
            );

            ctx.fillStyle = kpi.colour;
            ctx.fillRect(x, y, 8, 105);

            ctx.fillStyle = "#64748b";
            ctx.font = "bold 17px Arial";
            ctx.textAlign = "left";
            ctx.fillText(kpi.label, x + 28, y + 35);

            ctx.fillStyle = "#0f172a";
            ctx.font = "bold 35px Arial";
            ctx.fillText(kpi.value, x + 28, y + 78);
        });

        let y = header_height + kpi_height;

        if (category_summaries.length) {
            ctx.fillStyle = "#475569";
            ctx.font = "bold 18px Arial";
            ctx.textAlign = "left";
            ctx.fillText(
                "FLEET AVAILABILITY BY CATEGORY",
                padding,
                y + 22
            );

            y += 45;

            const category_gap = 15;
            const category_width =
                (
                    width
                    - (padding * 2)
                    - (category_gap * 3)
                ) / 4;

            category_summaries.forEach(
                (summary, index) => {
                    const column = index % 4;
                    const row_index = Math.floor(index / 4);

                    const x =
                        padding
                        + column
                        * (category_width + category_gap);

                    const card_y =
                        y + (row_index * 105);

                    draw_canvas_round_rect(
                        ctx,
                        x,
                        card_y,
                        category_width,
                        85,
                        12,
                        "#ffffff"
                    );

                    ctx.fillStyle =
                        summary.colour === "green"
                            ? "#16a34a"
                            : summary.colour === "yellow"
                                ? "#f59e0b"
                                : "#dc2626";

                    ctx.fillRect(
                        x,
                        card_y,
                        category_width,
                        5
                    );

                    ctx.fillStyle = "#0f172a";
                    ctx.font = "bold 30px Arial";
                    ctx.textAlign = "left";
                    ctx.fillText(
                        `${summary.available}/${summary.total}`,
                        x + 18,
                        card_y + 42
                    );

                    ctx.fillStyle = "#475569";
                    ctx.font = "bold 16px Arial";
                    ctx.fillText(
                        summary.category,
                        x + 18,
                        card_y + 69
                    );

                    ctx.fillStyle = "#991b1b";
                    ctx.font = "bold 16px Arial";
                    ctx.textAlign = "right";
                    ctx.fillText(
                        `${summary.down} down`,
                        x + category_width - 18,
                        card_y + 48
                    );
                }
            );

            y += category_rows * 105;
        }

        rows.forEach(row => {
            const is_open = String(row.status)
                .toLowerCase()
                .includes("open");

            draw_canvas_round_rect(
                ctx,
                padding,
                y,
                width - (padding * 2),
                105,
                14,
                "#ffffff"
            );

            ctx.fillStyle = is_open
                ? "#ef4444"
                : "#22c55e";

            ctx.fillRect(padding, y, 8, 105);

            ctx.fillStyle = is_open
                ? "#fee2e2"
                : "#dcfce7";

            ctx.beginPath();
            ctx.arc(padding + 47, y + 52, 25, 0, Math.PI * 2);
            ctx.fill();

            ctx.fillStyle = is_open
                ? "#991b1b"
                : "#166534";

            ctx.font = "bold 24px Arial";
            ctx.textAlign = "center";
            ctx.fillText(
                is_open ? "!" : "✓",
                padding + 47,
                y + 61
            );

            ctx.textAlign = "left";
            ctx.fillStyle = "#0f172a";
            ctx.font = "bold 24px Arial";
            ctx.fillText(row.plant, padding + 90, y + 38);

            ctx.fillStyle = "#64748b";
            ctx.font = "bold 16px Arial";
            ctx.fillText(row.category, padding + 90, y + 68);

            ctx.fillStyle = "#64748b";
            ctx.font = "bold 14px Arial";
            ctx.fillText("REASON", padding + 330, y + 27);

            ctx.fillStyle = "#172033";
            ctx.font = "bold 17px Arial";

            draw_wrapped_canvas_text(
                ctx,
                row.reason || "-",
                padding + 330,
                y + 52,
                570,
                21,
                2
            );

            ctx.fillStyle = "#64748b";
            ctx.font = "bold 14px Arial";
            ctx.fillText("START", padding + 930, y + 27);

            ctx.fillStyle = "#172033";
            ctx.font = "bold 16px Arial";
            ctx.fillText(
                String(row.start || "-").slice(0, 19),
                padding + 930,
                y + 55
            );

            ctx.fillStyle = "#64748b";
            ctx.font = "bold 14px Arial";
            ctx.fillText("DOWNTIME", padding + 1220, y + 27);

            ctx.fillStyle = is_open
                ? "#dc2626"
                : "#16a34a";

            ctx.font = "bold 24px Arial";
            ctx.fillText(
                format_saved_duration(row.hours),
                padding + 1220,
                y + 59
            );

            ctx.fillStyle = is_open
                ? "#fee2e2"
                : "#dcfce7";

            draw_canvas_round_rect(
                ctx,
                padding + 1380,
                y + 31,
                105,
                40,
                20,
                ctx.fillStyle
            );

            ctx.fillStyle = is_open
                ? "#991b1b"
                : "#166534";

            ctx.font = "bold 14px Arial";
            ctx.textAlign = "center";
            ctx.fillText(
                is_open ? "OPEN" : "CLOSED",
                padding + 1432,
                y + 57
            );

            ctx.textAlign = "left";
            y += row_height;
        });

        if (!rows.length) {
            ctx.fillStyle = "#64748b";
            ctx.font = "bold 26px Arial";
            ctx.textAlign = "center";
            ctx.fillText(
                "No downtime information found.",
                width / 2,
                y + 80
            );
        }

        const link = document.createElement("a");

        link.download =
            String(report.name || "downtime-report")
                .replace(/[^a-z0-9_-]+/gi, "_") +
            ".png";

        link.href = canvas.toDataURL("image/png");
        link.click();
    }


    function format_saved_duration(hours_value) {
        const total_minutes = Math.max(
            0,
            Math.round(Number(hours_value || 0) * 60)
        );

        const days = Math.floor(total_minutes / 1440);
        const hours = Math.floor(
            (total_minutes % 1440) / 60
        );
        const minutes = total_minutes % 60;

        const parts = [];

        if (days) {
            parts.push(`${days}d`);
        }

        if (hours || days) {
            parts.push(`${hours}h`);
        }

        parts.push(`${minutes}m`);

        return parts.join(" ");
    }


    function draw_canvas_round_rect(
        ctx,
        x,
        y,
        width,
        height,
        radius,
        colour
    ) {
        ctx.beginPath();
        ctx.roundRect(x, y, width, height, radius);
        ctx.fillStyle = colour;
        ctx.fill();
    }


    function draw_wrapped_canvas_text(
        ctx,
        text,
        x,
        y,
        max_width,
        line_height,
        max_lines
    ) {
        const words = String(text || "").split(/\s+/);
        const lines = [];
        let line = "";

        words.forEach(word => {
            const candidate = line
                ? `${line} ${word}`
                : word;

            if (
                ctx.measureText(candidate).width > max_width
                && line
            ) {
                lines.push(line);
                line = word;
            } else {
                line = candidate;
            }
        });

        if (line) {
            lines.push(line);
        }

        lines.slice(0, max_lines).forEach(
            (current_line, index) => {
                let output = current_line;

                if (
                    index === max_lines - 1
                    && lines.length > max_lines
                ) {
                    output += "…";
                }

                ctx.fillText(
                    output,
                    x,
                    y + (index * line_height)
                );
            }
        );
    }

    function wrap_canvas_line(context, text, max_width, output) {
        if (!text) {
            output.push("");
            return;
        }

        const words = String(text).split(/\s+/);
        let line = "";

        words.forEach(word => {
            const candidate = line
                ? `${line} ${word}`
                : word;

            if (
                context.measureText(candidate).width > max_width &&
                line
            ) {
                output.push(line);
                line = word;
            } else {
                line = candidate;
            }
        });

        output.push(line);
    }
})();

// === SAVED HOURLY / DAILY DOWNTIME REPORTS END ===


// Database-backed downtime verification summary.
// LAB read-only stage: no verification submissions.



function render_downtime_summary_preview(data) {

    $(".dt-summary-preview").remove();

    const total = new Set(
        data.map(row => row.breakdown_docname).filter(Boolean)
    ).size;

    function departmentCard(department) {
        return `
            <div class="col-sm-6 mb-3"
                 data-verification-department="${department}">
                <div class="card p-3 h-100">
                    <h5>${department}</h5>
                    <div class="mb-2">
                        <span class="dt-status indicator-pill orange">
                            Open
                        </span>
                    </div>
                    <h3 class="dt-count mb-1">0 / ${total}</h3>
                    <small class="text-muted">Records verified</small>
                    <div class="progress mt-2">
                        <div class="dt-progress progress-bar bg-warning"
                             role="progressbar"
                             style="width:0%"
                             aria-valuenow="0"
                             aria-valuemin="0"
                             aria-valuemax="${total}">
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    const html = `
        <div class="dt-summary-preview card p-3 mb-3">
            <!-- dt_heading_order_v3 -->


            <h4 class="dt-main-heading dt-heading-summary">
                2. Downtime Verification Summary
            </h4>

            <p class="text-muted dt-verification-message">
                Loading saved downtime verification results...
            </p>

            <div class="row dt-verification-summary-row">
                ${departmentCard("Production")}
                ${departmentCard("Engineering")}
            </div>

            <small class="text-muted mt-2 dt-verification-guidance">
                Select Verified or Not Verified for every outstanding downtime record. Not Verified records will remain outstanding.
            </small>
        </div>
    `;

    $(".mobile-downtime-wrapper").first().before(html);

    // Do not present browser-only selections as saved decisions.
    $(".dt-preview-verification")
        .off("change.dt_preview")
        .prop("checked", false)
        .prop("disabled", true);
}


// Saved results are reused when the report rebuilds its machine cards.
const downtime_summary_cache = new Map();

// Administrator may test either verification department.
let downtime_admin_department = "Engineering";


// Unsaved verification decisions, isolated by user, period and record ID.
const downtime_verification_draft_cache = new Map();

function load_downtime_summary_readonly(report) {
    const $panel = $(".dt-summary-preview").first();
    if (!$panel.length) return;

    $(".dt-preview-verification")
        .off("change.dt_preview")
        .prop("checked", false)
        .prop("disabled", true);

    const date = frappe.query_report.get_filter_value("report_date");
    const site = frappe.query_report.get_filter_value("site");
    const shift = frappe.query_report.get_filter_value("shift") || "";
    const roles = frappe.user_roles || [];

    const hasEngineering = [
        "Engineering Manager", "Engineering Foreman"
    ].some(role => roles.includes(role));

    const hasProduction = [
        "Production Manager", "Production Foreman"
    ].some(role => roles.includes(role));

    const $message = $panel.find(".dt-verification-message");

    function showMessage(message, hideSummary) {
        const $current = $(".dt-summary-preview").first();
        $current.find(".dt-verification-message").text(message);

        $current.find(
            ".dt-verification-summary-row, " +
            ".dt-verification-divider, " +
            ".dt-verification-overall-row"
        ).toggle(!hideSummary);
    }

    if (!date || !site) {
        showMessage(__("Select a report date and site."), true);
        return;
    }

    if (!hasEngineering && !hasProduction) {
        showMessage(
            __("Your account does not have a downtime verification role."),
            true
        );
        return;
    }

    if (
        hasEngineering && hasProduction &&
        frappe.session.user !== "Administrator"
    ) {
        showMessage(
            __("Conflicting Engineering and Production verification roles."),
            true
        );
        return;
    }

    // dt_admin_department_selector_v1
    const isAdministrator = frappe.session.user === "Administrator";

    const department = isAdministrator
        ? downtime_admin_department
        : (hasEngineering ? "Engineering" : "Production");

    // Only Administrator can change verification department.
    $panel.find(".dt-admin-department-selector").remove();

    if (isAdministrator) {
        const $selector = $(`
            <div class="dt-admin-department-selector form-group mb-3">
                <label class="dt-main-heading dt-heading-department"><strong>1. Verification Department</strong></label>
                <select class="form-control dt-admin-department-select">
                    <option value="Engineering">Engineering</option>
                    <option value="Production">Production</option>
                </select>
            </div>
        `);

        $selector.find("select").val(department);

        $panel.prepend($selector);

        $selector.find("select").on("change", function () {
            const selected = $(this).val();

            if (!["Engineering", "Production"].includes(selected)) {
                return;
            }

            // Stop any previous submission interface immediately.
            $(".downtime-signoff-action-button")
                .off("click.dt_submission")
                .prop("disabled", true);

            $panel.find(".dt-verification-actions").remove();

            downtime_admin_department = selected;

            // Fetch this department's authoritative verification state.
            load_downtime_summary_readonly(report);
        });
    }

    const key = JSON.stringify([
        frappe.session.user, date, site, shift, department
    ]);

    function stillSelected() {
        return frappe.query_report.get_filter_value("report_date") === date &&
            frappe.query_report.get_filter_value("site") === site &&
            (frappe.query_report.get_filter_value("shift") || "") === shift;
    }

    function applyResult(result) {
        if (!stillSelected()) return;

        const $current = $(".dt-summary-preview").first();
        if (!$current.length) return;

        if (result.historical_workflow) {
            $current.find(".dt-verification-actions").remove();
            $(".downtime-signoff-action-button")
                .off("click.dt_submission")
                .prop("disabled", false);
            showMessage(
                __("Historical electronic sign-off period. " +
                   "Existing approvals are preserved."),
                true
            );
            return;
        }

        const summary = result.summary;
        if (!summary) {
            showMessage(__("No verification summary was returned."), true);
            return;
        }

        ["Production", "Engineering"].forEach(function (name) {
            const item = summary[name] || {};
            const verified = Number(item.verified || 0);
            const total = Number(item.total || 0);
            const closed = item.status === "Closed";

            const $card = $current.find(
                '[data-verification-department="' + name + '"]'
            );

            $card.find(".dt-count").text(
                verified + " / " + total
            );

            $card.find(".dt-status")
                .text(closed ? "Closed" : "Open")
                .removeClass("orange green")
                .addClass(closed ? "green" : "orange");

            $card.find(".dt-progress")
                .css(
                    "width",
                    total ? (verified / total * 100) + "%" : "0%"
                )
                .toggleClass("bg-success", closed)
                .toggleClass("bg-warning", !closed)
                .attr("aria-valuenow", verified)
                .attr("aria-valuemax", total);
        });

        const closed = summary.overall_status === "Closed";

        $current.find(".dt-overall-status")
            .text(closed ? "Closed" : "Open")
            .removeClass("orange green")
            .addClass(closed ? "green" : "orange");

        $(".downtime-signoff-action-button")
            .prop("disabled", true);

        setup_downtime_submission_ui(
            result, department, key
        );

        let dtVerificationHeadingMessage = __(
            "Saved ERPNext verification results loaded successfully. " +
            "Select Verified or Not Verified for every outstanding record."
        );

        if (summary.overall_status === "Closed") {
            dtVerificationHeadingMessage = __(
                "All downtime records have been verified successfully. " +
                "Overall sign-off is Closed."
            );
        } else if (
            summary[department] &&
            summary[department].status === "Closed"
        ) {
            dtVerificationHeadingMessage = __(
                "All {0} downtime records have been verified successfully. " +
                "No outstanding records for this department.",
                [department]
            );
        }

        let dtVerificationGuidanceMessage =
            "Select Verified or Not Verified for every outstanding downtime record. " +
            "Not Verified records will remain outstanding.";

        if (summary.overall_status === "Closed") {
            dtVerificationGuidanceMessage =
                "All downtime records have been verified successfully. " +
                "No outstanding verification records remain.";
        } else if (
            summary[department] &&
            summary[department].status === "Closed"
        ) {
            dtVerificationGuidanceMessage =
                `All ${department} downtime records have been verified successfully. ` +
                "No outstanding records for this department.";
        }

        $(".dt-summary-preview .dt-verification-guidance")
            .text(dtVerificationGuidanceMessage);

        showMessage(
            summary.status_outdated
                ? __("Saved results loaded. Stored sign-off " +
                     "status requires reconciliation.")
                : dtVerificationHeadingMessage,
            false
        );
    }

    const cached = downtime_summary_cache.get(key);

    if (cached && cached.result) {
        applyResult(cached.result);
        return;
    }

    if (cached && cached.pending) {
        showMessage(
            __("Loading saved downtime verification results..."),
            false
        );
        return;
    }

    showMessage(
        __("Loading saved downtime verification results..."),
        false
    );

    downtime_summary_cache.clear();
    downtime_summary_cache.set(key, { pending: true });

    frappe.call({
        method:
            "engineering.engineering.report.down_time." +
            "downtime_verification.get_downtime_verification_summary",
        args: {
            report_date: date,
            site: site,
            shift: shift,
            department: department
        },
        callback: function (response) {
            const entry = downtime_summary_cache.get(key);
            if (!entry || !entry.pending) return;

            if (!response.message) {
                downtime_summary_cache.delete(key);
                if (stillSelected()) {
                    showMessage(
                        __("Verification API returned no data."),
                        true
                    );
                }
                return;
            }

            downtime_summary_cache.set(key, {
                result: response.message
            });

            applyResult(response.message);
        },
        error: function () {
            const entry = downtime_summary_cache.get(key);
            if (!entry || !entry.pending) return;

            downtime_summary_cache.delete(key);

            if (stillSelected()) {
                showMessage(
                    __("Unable to load saved verification results. " +
                       "Check roles and site permissions."),
                    true
                );
            }
        }
    });
}


// LAB verification interface: controls are rendered against the
// authoritative outstanding record IDs returned by the server.
function setup_downtime_submission_ui(result, department, cacheKey) {
    const $panel = $(".dt-summary-preview").first();
    if (!$panel.length) return;

    const outstanding = new Set(
        (result.outstanding_records || []).map(
            item => String(item.downtime_record || "")
        )
    );

    const available = new Set(
        (result.all_records || []).map(
            item => String(item.downtime_record || "")
        )
    );

    $panel.find(".dt-verification-actions").remove();

    $panel.append(`
        <div class="dt-verification-actions mt-3">
            <hr>
            <h5>${frappe.utils.escape_html(department)}
                Downtime Verification</h5>

            <div class="form-group">
                <label>Records to display</label>
                <select class="form-control dt-verification-view">
                    <option value="outstanding">Show Outstanding</option>
                    <option value="all">Show All</option>
                </select>
            </div>

            <p class="text-muted dt-verification-hint"></p>

            <!-- Submission uses the existing bottom-right red button. -->
        </div>
    `);

    const $actions = $panel.find(".dt-verification-actions");

    if (!downtime_verification_draft_cache.has(cacheKey)) {
        downtime_verification_draft_cache.set(cacheKey, new Map());
    }

    const draft = downtime_verification_draft_cache.get(cacheKey);

    const $cards = $(".mobile-downtime-card").filter(function () {
        return $(this).find(".dt-preview-verification").length > 0;
    });

    $cards.each(function () {
        const $card = $(this);
        const $inputs = $card.find(".dt-preview-verification");
        const id = String($inputs.first().attr("data-record-key") || "");

        $card.attr("data-verification-id", id);

        $inputs.off("change.dt_preview change.dt_submission");

        const saved = draft.get(id);

        $inputs.prop("checked", false);
        $inputs.prop("disabled", !outstanding.has(id));

        if (outstanding.has(id) && saved && saved.status) {
            $inputs.filter(function () {
                return $(this).val() === saved.status;
            }).prop("checked", true);
        }

        if (outstanding.has(id) && saved && saved.comment !== undefined) {
            $card.find(".mobile-downtime-comment-input")
                .val(saved.comment);
        }

        if (!outstanding.has(id)) {
            draft.delete(id);
        }

        $card.find(".dt-verification-comment-group").remove();

        if (!outstanding.has(id)) {
            $card.find(".mobile-downtime-verify").hide();
            $card.find(".mobile-downtime-comment-input")
                .prop("readOnly", true);
            $card.find(".mobile-downtime-verify").after(`
                <p class="dt-verification-comment-group text-muted mt-2">
                    Verified — Read-only
                </p>
            `);
        } else {
            $card.find(".mobile-downtime-verify").show();
            $card.find(".mobile-downtime-comment-input")
                .prop("readOnly", false);
        }
    });

    function updateDisplay() {
        const showAll =
            $actions.find(".dt-verification-view").val() === "all";

        $cards.each(function () {
            const $card = $(this);
            const id = String($card.attr("data-verification-id") || "");

            $card.toggle(
                available.has(id) &&
                (showAll || outstanding.has(id))
            );
        });

        $actions.find(".dt-verification-hint").text(
            outstanding.size + " outstanding record(s) for " + department
        );
    }

    $actions.find(".dt-verification-view")
        .on("change", updateDisplay);

    updateDisplay();

    // dt_verification_submit_live
    // Only explicitly selected, outstanding breakdown records can be sent.
    const $save = $(".downtime-signoff-action-button").first();

    if (!$save.length) {
        console.warn("Downtime sign-off action button is missing.");
        return;
    }

    function currentScope() {
        const date = frappe.query_report.get_filter_value("report_date");
        const site = frappe.query_report.get_filter_value("site");
        const shift = frappe.query_report.get_filter_value("shift") || "";

        return {
            date: date,
            site: site,
            shift: shift,
            key: JSON.stringify([
                frappe.session.user, date, site, shift, department
            ])
        };
    }

    function selectedEntries() {
        const entries = [];

        $cards.each(function () {
            const $card = $(this);
            const id = String($card.attr("data-verification-id") || "");

            if (!id || !outstanding.has(id)) return;

            const $selected = $card.find(
                ".dt-preview-verification:checked:not(:disabled)"
            );

            if (!$selected.length) return;

            // Read the existing comment from this exact breakdown card.
            const comment = String(
                $card.find(".mobile-downtime-comment-input").val() || ""
            ).trim();

            entries.push({
                downtime_record: id,
                verification_status: $selected.val(),
                comments: comment
            });
        });

        return entries;
    }

    function updateSaveButton() {
        const validScope = currentScope().key === cacheKey;
        const noCategory = !frappe.query_report.get_filter_value(
            "asset_category"
        );

        const entries = selectedEntries();
        const allDecided = outstanding.size > 0 &&
            entries.length === outstanding.size;

        const disabled =
            saving || !validScope || !noCategory || !allDecided;

        $save.prop("disabled", disabled);
    }

    $cards.find(".dt-preview-verification")
        .off("change.dt_submission")
        .on("change.dt_submission", function () {
            const $card = $(this).closest(".mobile-downtime-card");
            const id = String($card.attr("data-verification-id") || "");

            if (outstanding.has(id)) {
                const previous = draft.get(id) || {};
                draft.set(id, {
                    ...previous,
                    status: $(this).val(),
                    comment: String(
                        $card.find(".mobile-downtime-comment-input").val() || ""
                    )
                });
            }

            updateSaveButton();
        });

    $cards.find(".mobile-downtime-comment-input")
        .off("input.dt_verification_draft")
        .on("input.dt_verification_draft", function () {
            const $card = $(this).closest(".mobile-downtime-card");
            const id = String($card.attr("data-verification-id") || "");

            if (!outstanding.has(id)) return;

            const previous = draft.get(id) || {};
            draft.set(id, {
                ...previous,
                comment: String($(this).val() || "")
            });
        });

    $actions.find(".dt-verification-view")
        .on("change", updateSaveButton);

    // dt_freshness_check_v1
    let saving = false;

    $save.off("click.dt_submission").on("click.dt_submission", function () {
        if (saving) return;

        const scope = currentScope();

        if (scope.key !== cacheKey) {
            frappe.msgprint(
                __("Report filters changed. Refresh before submitting.")
            );
            return;
        }

        if (frappe.query_report.get_filter_value("asset_category")) {
            frappe.msgprint(
                __("Clear Asset Category before submitting verification.")
            );
            return;
        }

        const entries = selectedEntries();

        if (
            outstanding.size === 0 ||
            entries.length !== outstanding.size ||
            new Set(entries.map(item => item.downtime_record)).size
                !== outstanding.size
        ) {
            frappe.msgprint(
                __("Select Verified or Not Verified for every outstanding machine.")
            );
            return;
        }

        if (entries.some(item => item.comments.length > 1000)) {
            frappe.msgprint(
                __("Downtime comments cannot exceed 1000 characters.")
            );
            return;
        }

        frappe.confirm(
            __("By submitting this Downtime Sign-off, you confirm that you have checked the downtime records and that the information is accurate."),
            function () {
                if (saving) return;

                if (
                    currentScope().key !== cacheKey ||
                    frappe.query_report.get_filter_value("asset_category")
                ) {
                    frappe.msgprint(
                        __("Report filters changed. Refresh before submitting.")
                    );
                    return;
                }

                saving = true;
                $save.prop("disabled", true);

                function stopSaving() {
                    saving = false;
                    updateSaveButton();
                }

                // Recheck all currently outstanding IDs on the server
                // before committing any selected decisions.
                frappe.call({
                    method:
                        "engineering.engineering.report.down_time." +
                        "downtime_verification.get_downtime_verification_summary",
                    args: {
                        report_date: scope.date,
                        site: scope.site,
                        shift: scope.shift,
                        department: department
                    },
                    callback: function (response) {
                        const latest = response.message;

                        if (!latest || latest.historical_workflow) {
                            stopSaving();
                            frappe.msgprint(
                                __("Verification state could not be confirmed. Refresh the report.")
                            );
                            return;
                        }

                        if (
                            currentScope().key !== cacheKey ||
                            frappe.query_report.get_filter_value("asset_category")
                        ) {
                            stopSaving();
                            frappe.msgprint(
                                __("Report filters changed. Refresh before submitting.")
                            );
                            return;
                        }

                        const latestOutstanding = new Set(
                            (latest.outstanding_records || []).map(
                                item => String(item.downtime_record || "")
                            )
                        );

                        const latestAll = new Set(
                            (latest.all_records || []).map(
                                item => String(item.downtime_record || "")
                            )
                        );

                        const unchanged =
                            latestOutstanding.size === outstanding.size &&
                            [...outstanding].every(
                                id => latestOutstanding.has(id)
                            ) &&
                            latestAll.size === available.size &&
                            [...available].every(id => latestAll.has(id));

                        if (!unchanged) {
                            stopSaving();
                            downtime_summary_cache.clear();
                            frappe.msgprint(
                                __("Downtime verification changed since this report was opened. Refresh and review the latest records before submitting.")
                            );
                            return;
                        }

                        // The server performs final checks again under
                        // its database lock before accepting this batch.
                        frappe.call({
                            method:
                                "engineering.engineering.report.down_time." +
                                "downtime_verification.submit_downtime_verifications",
                            type: "POST",
                            args: {
                                report_date: scope.date,
                                site: scope.site,
                                shift: scope.shift,
                                department: department,
                                verifications: entries
                            },
                            freeze: true,
                            freeze_message:
                                __("Saving downtime verification..."),
                            callback: function (saveResponse) {
                                if (!saveResponse.message) {
                                    stopSaving();
                                    return;
                                }

                                downtime_verification_draft_cache.delete(
                                    cacheKey
                                );
                                downtime_summary_cache.clear();

                                frappe.show_alert({
                                    message: __("Verification saved successfully."),
                                    indicator: "green"
                                });

                                frappe.query_report.refresh();
                            },
                            error: function () {
                                stopSaving();
                            }
                        });
                    },
                    error: function () {
                        stopSaving();
                        frappe.msgprint(
                            __("Unable to confirm the latest verification records. Nothing was submitted. Please try again.")
                        );
                    }
                });
            }
        );
    });

    updateSaveButton();
}
