function get_daily_au_dashboard_date(
    storage_key,
    fallback_value
) {
    try {
        const value = localStorage.getItem(
            storage_key
        );

        if (
            value
            && /^\\d{4}-\\d{2}-\\d{2}$/.test(
                value
            )
        ) {
            return value;
        }
    } catch (error) {
        // Browser storage may be unavailable.
    }

    return fallback_value;
}


function sync_engine_dates_from_daily_dashboard(report) {
    if (!report) {
        return;
    }

    let from_date = "";
    let to_date = "";

    try {
        from_date = (
            localStorage.getItem(
                "daily_au_engine_dashboard_from_date"
            )
            || ""
        );

        to_date = (
            localStorage.getItem(
                "daily_au_engine_dashboard_to_date"
            )
            || ""
        );
    } catch (error) {
        return;
    }

    const valid_date = function(value) {
        return /^\d{4}-\d{2}-\d{2}$/.test(
            String(value || "")
        );
    };

    if (
        !valid_date(from_date)
        || !valid_date(to_date)
    ) {
        return;
    }

    const from_filter = report.get_filter(
        "from_date"
    );

    const to_filter = report.get_filter(
        "to_date"
    );

    if (
        !from_filter
        || !to_filter
    ) {
        return;
    }

    const current_from = String(
        from_filter.get_value() || ""
    );

    const current_to = String(
        to_filter.get_value() || ""
    );

    if (
        current_from === from_date
        && current_to === to_date
    ) {
        return;
    }

    from_filter.set_value(
        from_date
    );

    to_filter.set_value(
        to_date
    );

    setTimeout(
        function() {
            if (
                report
                && typeof report.refresh === "function"
            ) {
                report.refresh();
            }
        },
        150
    );
}


frappe.query_reports["Availability and Utilisation Engine"] = {
    initial_depth: 0,

    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: get_daily_au_dashboard_date(
                "daily_au_engine_dashboard_from_date",
                frappe.datetime.month_start()
            )
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: get_daily_au_dashboard_date(
                "daily_au_engine_dashboard_to_date",
                frappe.datetime.month_end()
            )
        },
        {
            fieldname: "locations",
            label: __("Location"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Location", txt);
            }
        },
        {
            fieldname: "assets",
            label: __("Asset"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Asset", txt);
            }
        },
        {
            fieldname: "companies",
            label: __("Company"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Company", txt);
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
            reqd: 1
        },
        {
            fieldname: "au_calculation",
            label: __("A&U Calculation"),
            fieldtype: "Select",
            options: [
                "Isambane A&U Calculation",
                "Industry A&U Calculation"
            ].join("\n"),
            default: "Isambane A&U Calculation",
            reqd: 1
        },
        {
            fieldname: "free_hours",
            label: __("Free Hours"),
            fieldtype: "Float",
            default: 0
        },
        {
            fieldname: "production_machines_only",
            label: __("Production Machines Only"),
            fieldtype: "Check",
            default: 0
        },
        {
            fieldname: "au_percentage_basis",
            label: __("A & U Percentage"),
            fieldtype: "Select",
            options: [
                "85% A & U",
                "100% A & U"
            ].join("\n"),
            default: "85% A & U",
            reqd: 1
        }
    ],


    get_datatable_options: function(options) {
        return Object.assign(
            options,
            {
                freezeColumns: 8
            }
        );
    },



    formatter: function(value, row, column, data, default_formatter) {


        const hour_fields = [
            "actual_hours",
            "planned_downtime",
            "required_hours",
            "work_hours",
            "industry_required_hours",
            "industry_work_hours",
            "industry_util_available_hours",
            "pbm_elapsed_time",
            "pbm_startup_fatigue_time",
            "pbm_sunday_time",
            "planned_maintenance_hours",
            "breakdown_hours",
            "pbm_total_downtime",
            "utilisation_available_hours",
            "availability_available_hours"
            // OLD UTILISATION SUPPORT FIELDS
            // "utilisation_work_hours",
            // "utilisation_available_hours"
        ];

        const raw_value = data
            ? data[column.fieldname]
            : 0;

        value = default_formatter(
            value,
            row,
            column,
            data
        );

        // Industry-only visual separator.
        // This field exists only in Industry A&U columns,
        // therefore Isambane A&U is unaffected.
        if (
            column.fieldname
            === "industry_separator"
        ) {
            return `
                <div style="
                    background:#000000;
                    width:100%;
                    min-width:10px;
                    height:34px;
                    margin:-7px -8px;
                    padding:0;
                "></div>
            `;
        }

        if (hour_fields.includes(column.fieldname)) {
            value = format_engine_hours(raw_value);
        }

        if (
            data
            && Number(data.indent || 0) === 1
            && column.fieldname === "shift_date"
        ) {
            value = `
                <span class="availability-engine-date-label">
                    ${value}
                </span>
            `;
        }

        if (
            [
                "availability_percentage",
                "utilisation_percentage"
            ].includes(column.fieldname)
            && (
                raw_value === null
                || raw_value === undefined
                || raw_value === ""
            )
        ) {
            value = "N/A";

            if (
                data
                && column.fieldname === "utilisation_percentage"
                && data.au_validation_level === "invalid"
            ) {
                value = `
                    <span style="
                        display:inline-block;
                        padding:3px 8px;
                        border-radius:999px;
                        background:#fee2e2;
                        color:#991b1b;
                        font-weight:700;
                    ">
                        N/A
                    </span>
                `;
            }
        }

        if (
            data
            && Number(data.indent || 0) === 0
            && column.fieldname === "asset_category"
            && Number(
                data.au_problem_day_count || 0
            ) > 0
        ) {
            const problem_day_count = Number(
                data.au_problem_day_count || 0
            );

            value = `
                ${value}
                <span
                    title="${problem_day_count} day(s) contain A&U warnings or invalid shifts"
                    style="
                        display:inline-flex;
                        align-items:center;
                        justify-content:center;
                        min-width:18px;
                        height:18px;
                        margin-left:6px;
                        padding:0 5px;
                        border-radius:9px;
                        background:#f97316;
                        color:#ffffff;
                        font-size:10px;
                        font-weight:700;
                        line-height:18px;
                    "
                >
                    ${problem_day_count}
                </span>
            `;
        }


        if (
            data
            && Number(data.indent || 0) === 3
            && (
                data.shift === "Day"
                || data.shift === "Night"
            )
        ) {
            value = apply_engine_shift_highlight(
                value,
                data.shift
            );
        }

        if (
            data
            && Number(
                data.is_spare_swing_unit || 0
            ) === 1
        ) {
            value = apply_engine_spare_highlight(
                value,
                data.spare_swing_reason
            );
        }

        if (
            data
            && column.fieldname === "invalid_pre_use_status"
            && data.invalid_pre_use_status
        ) {
            const invalid = String(
                data.invalid_pre_use_status
            ).startsWith("Invalid");

            const contains_invalid = (
                data.invalid_pre_use_status
                === "Contains Invalid Shift"
            );

            if (invalid || contains_invalid) {
                value = `
                    <span style="
                        display:inline-block;
                        padding:3px 8px;
                        border-radius:999px;
                        background:#fee2e2;
                        color:#991b1b;
                        font-weight:700;
                    ">
                        ${frappe.utils.escape_html(
                            data.invalid_pre_use_status
                        )}
                    </span>
                `;
            }
        }

        if (
            data
            && [1, 2, 3].includes(
                Number(data.indent || 0)
            )
            && (
                data.au_validation_level === "invalid"
                || data.au_validation_level === "warning"
            )
        ) {
            const is_invalid = (
                data.au_validation_level === "invalid"
            );

            const background = (
                is_invalid
                ? "#fee2e2"
                : "#ffedd5"
            );

            const border = (
                is_invalid
                ? "#dc2626"
                : "#f97316"
            );

            const safe_status = (
                frappe.utils.escape_html(
                    data.au_validation_status || ""
                )
            );

            value = `
                <span
                    title="${safe_status}"
                    style="
                        display:block;
                        min-height:100%;
                        margin:-8px -10px;
                        padding:8px 10px;
                        background:${background} !important;
                        border-left:3px solid ${border} !important;
                    "
                >
                    ${value || ""}
                </span>
            `;
        }

        return value;
    },

    onload: function(report) {
        ensure_engine_filter_dropdowns_in_front();
        bind_engine_formula_header_clicks(report);
        add_engine_legend(report);

        // Query Report can restore old filter values after the
        // field defaults are created. Apply the Daily A&U Engine
        // Dashboard date range after the report has initialised.
        setTimeout(
            function() {
                sync_engine_dates_from_daily_dashboard(
                    report
                );
            },
            250
        );

        setTimeout(
            apply_engine_freeze_columns,
            500
        );

        setTimeout(
            apply_engine_freeze_columns,
            1500
        );
    },

    after_datatable_render: function() {
        setTimeout(
            function() {
                apply_engine_freeze_columns();
                mark_engine_formula_headers_clickable();
                bind_engine_expanded_date_highlight();
                update_invalid_au_button(
                    frappe.query_report
                );
            },
            200
        );
    }
};


function ensure_engine_filter_dropdowns_in_front() {
    const style_id = "availability-engine-filter-layer-style";

    if (!document.getElementById(style_id)) {
        const style = document.createElement("style");
        style.id = style_id;
        style.textContent = `
            .page-form {
                position: relative !important;
                z-index: 50 !important;
                overflow: visible !important;
            }

            .page-form .form-group,
            .page-form .control-input-wrapper,
            .page-form .control-input,
            .page-form .awesomplete,
            .page-form .frappe-control {
                overflow: visible !important;
            }

            .page-form .dropdown-menu,
            .page-form .awesomplete > ul,
            .page-form .multiselect-list,
            .page-form .multiselect-list .dropdown-menu {
                z-index: 2000 !important;
            }

            .report-wrapper,
            .datatable {
                position: relative;
                z-index: 1;
            }
        `;
        document.head.appendChild(style);
    }
}


function add_engine_legend(report) {
    const $wrapper = $(report.page.wrapper);

    if (
        $wrapper.find(
            ".availability-engine-legend"
        ).length
    ) {
        return;
    }

    const legend = `
        <div
            class="availability-engine-legend"
            style="
                display:flex;
                align-items:center;
                gap:14px;
                flex-wrap:wrap;
                margin:6px 0 8px;
                font-size:11px;
                font-weight:600;
            "
        >
            <span
                class="availability-engine-warning-legend"
                title="Click to view warning rules"
                style="
                    display:inline-flex;
                    align-items:center;
                    gap:5px;
                    cursor:pointer;
                "
            >
                <span style="
                    width:12px;
                    height:12px;
                    border-radius:3px;
                    background:#ffedd5;
                    border-left:3px solid #f97316;
                "></span>
                A&amp;U Warning
            </span>

            <span
                class="availability-engine-invalid-legend"
                title="Click to view invalid rules"
                style="
                    display:inline-flex;
                    align-items:center;
                    gap:5px;
                    cursor:pointer;
                "
            >
                <span style="
                    width:12px;
                    height:12px;
                    border-radius:3px;
                    background:#fee2e2;
                    border-left:3px solid #dc2626;
                "></span>
                Invalid A&amp;U
            </span>

            <button
                type="button"
                class="
                    btn
                    btn-xs
                    btn-default
                    availability-engine-invalid-view
                "
                style="
                    border:1px solid #dc2626;
                    color:#991b1b;
                    background:#fff;
                    font-size:11px;
                    font-weight:700;
                    padding:3px 9px;
                    border-radius:6px;
                "
            >
                View Invalid A&amp;U (0)
            </button>

            <span style="
                display:inline-flex;
                align-items:center;
                gap:5px;
            ">
                <span style="
                    width:12px;
                    height:12px;
                    border-radius:3px;
                    background:#e6d6ff;
                    border-left:3px solid #7b2cbf;
                "></span>
                Spare / Swing Machine
            </span>
        </div>
    `;

    const $filter_area = $wrapper.find(
        ".page-form"
    ).first();

    if ($filter_area.length) {
        $filter_area.append(legend);
    } else {
        $wrapper.prepend(legend);
    }

    $wrapper
        .find(".availability-engine-warning-legend")
        .off("click.auWarningLegend")
        .on(
            "click.auWarningLegend",
            show_au_warning_explanation
        );

    $wrapper
        .find(".availability-engine-invalid-legend")
        .off("click.auInvalidLegend")
        .on(
            "click.auInvalidLegend",
            show_au_invalid_explanation
        );

    $wrapper
        .find(".availability-engine-invalid-view")
        .off("click.auInvalidView")
        .on(
            "click.auInvalidView",
            function() {
                show_invalid_au_rows(
                    report
                );

                // Insert the PBM drill-down column after the
                // Invalid A&U dialog has been rendered.
                [
                    50,
                    200,
                    500,
                    1000
                ].forEach(
                    function(delay) {
                        setTimeout(
                            function() {
                                add_invalid_au_pbm_view_column(
                                    report
                                );
                            },
                            delay
                        );
                    }
                );
            }
        );

    update_invalid_au_button(
        report
    );
}


function get_invalid_au_shift_rows(report) {
    let rows = [];

    if (
        report
        && Array.isArray(report.data)
    ) {
        rows = report.data;
    } else if (
        frappe.query_report
        && Array.isArray(
            frappe.query_report.data
        )
    ) {
        rows = frappe.query_report.data;
    }

    return rows
        .filter(
            function(row) {
                return (
                    row
                    && Number(row.invalid_au_excluded || 0) !== 1
                    && Number(
                        row.indent || 0
                    ) === 3
                    && (
                        row.shift === "Day"
                        || row.shift === "Night"
                    )
                    && (
                        row.au_validation_level
                        === "invalid"
                        || Number(
                            row.invalid_au || 0
                        ) === 1
                    )
                );
            }
        )
        .sort(
            function(a, b) {
                const date_compare = String(
                    a.shift_date || ""
                ).localeCompare(
                    String(
                        b.shift_date || ""
                    )
                );

                if (date_compare !== 0) {
                    return date_compare;
                }

                const machine_compare = String(
                    a.asset_name || ""
                ).localeCompare(
                    String(
                        b.asset_name || ""
                    )
                );

                if (machine_compare !== 0) {
                    return machine_compare;
                }

                return String(
                    a.shift || ""
                ).localeCompare(
                    String(
                        b.shift || ""
                    )
                );
            }
        );
}


function update_invalid_au_button(report) {
    if (
        !report
        || !report.page
        || !report.page.wrapper
    ) {
        return;
    }

    const rows = get_invalid_au_shift_rows(
        report
    );

    const $button = $(
        report.page.wrapper
    ).find(
        ".availability-engine-invalid-view"
    );

    if (!$button.length) {
        return;
    }

    $button.text(
        `View Invalid A&U (${rows.length})`
    );

    $button.prop(
        "disabled",
        rows.length === 0
    );

    $button.css(
        "opacity",
        rows.length === 0
            ? "0.55"
            : "1"
    );

    $button.attr(
        "title",
        rows.length
            ? (
                `${rows.length} invalid A&U `
                + "shift(s) in the current report"
            )
            : "No invalid A&U shifts in the current report"
    );
}


function format_invalid_au_date(value) {
    const text = String(
        value || ""
    ).slice(
        0,
        10
    );

    const match = text.match(
        /^(\d{4})-(\d{2})-(\d{2})$/
    );

    if (!match) {
        return text;
    }

    return (
        `${match[3]}/${match[2]}/${match[1]}`
    );
}


function get_invalid_au_reason(row) {
    return String(
        row.au_validation_status || ""
    )
        .replace(
            /^Invalid A&U:\s*/,
            ""
        )
        .trim();
}


function show_invalid_au_rows(report) {
    const rows = get_invalid_au_shift_rows(
        report
    );

    if (!rows.length) {
        frappe.msgprint({
            title: __("Invalid A&U"),
            message: __(
                "There are no invalid A&U shifts "
                + "in the current report."
            ),
            indicator: "green"
        });

        return;
    }

    const body_rows = rows
        .map(
            function(row) {
                const date = (
                    frappe.utils.escape_html(
                        format_invalid_au_date(
                            row.shift_date
                        )
                    )
                );

                const shift = (
                    frappe.utils.escape_html(
                        String(
                            row.shift || ""
                        )
                    )
                );

                const machine = (
                    frappe.utils.escape_html(
                        String(
                            row.asset_name || ""
                        )
                    )
                );

                const work_hours = (
                    frappe.utils.escape_html(
                        format_engine_hours(
                            row.work_hours
                        )
                    )
                );

                const pbm_hours = (
                    frappe.utils.escape_html(
                        format_engine_hours(
                            row.pbm_total_downtime
                        )
                    )
                );

                const required_hours = (
                    frappe.utils.escape_html(
                        format_engine_hours(
                            row.required_hours
                        )
                    )
                );

                const reason = (
                    frappe.utils.escape_html(
                        get_invalid_au_reason(
                            row
                        )
                    )
                );

                return `
                    <tr>
                        <td>${date}</td>
                        <td>${shift}</td>
                        <td>
                            <strong>
                                ${machine}
                            </strong>
                        </td>
                        <td>${work_hours}</td>
                        <td>${pbm_hours}</td>
                        <td>${required_hours}</td>
                        <td
                            style="
                                color:#991b1b;
                                min-width:280px;
                            "
                        >
                            ${reason}
                        </td>
                    </tr>
                `;
            }
        )
        .join("");

    const dialog = new frappe.ui.Dialog({
        title: __(
            `Invalid A&U Shifts (${rows.length})`
        ),
        size: "extra-large",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "invalid_rows_html"
            }
        ]
    });

    dialog
        .fields_dict
        .invalid_rows_html
        .$wrapper
        .html(`
            <div style="
                padding:4px 2px 12px;
            ">
                <div style="
                    display:flex;
                    align-items:center;
                    justify-content:space-between;
                    gap:12px;
                    flex-wrap:wrap;
                    margin-bottom:12px;
                    padding:12px 14px;
                    background:#fee2e2;
                    border:1px solid #dc2626;
                    border-radius:8px;
                ">
                    <div>
                        <strong style="
                            color:#991b1b;
                            font-size:14px;
                        ">
                            ${rows.length}
                            invalid A&amp;U shift(s)
                        </strong>

                        <div style="
                            margin-top:3px;
                            color:#7f1d1d;
                            font-size:12px;
                        ">
                            Current report filters only
                        </div>
                    </div>

                    <div style="
                        color:#7f1d1d;
                        font-size:12px;
                    ">
                        Invalid shifts are excluded from
                        A&amp;U KPI totals.
                    </div>
                </div>

                <div style="
                    max-height:60vh;
                    overflow:auto;
                    border:1px solid #d1d8dd;
                    border-radius:8px;
                ">
                    <table
                        class="table table-bordered"
                        style="
                            margin:0;
                            width:100%;
                            font-size:12px;
                            background:#fff;
                        "
                    >
                        <thead>
                            <tr style="
                                background:#f8fafc;
                            ">
                                <th
                                    style="
                                        position:sticky;
                                        top:0;
                                        background:#f8fafc;
                                        z-index:1;
                                    "
                                >
                                    Date
                                </th>
                                <th
                                    style="
                                        position:sticky;
                                        top:0;
                                        background:#f8fafc;
                                        z-index:1;
                                    "
                                >
                                    Shift
                                </th>
                                <th
                                    style="
                                        position:sticky;
                                        top:0;
                                        background:#f8fafc;
                                        z-index:1;
                                    "
                                >
                                    Machine
                                </th>
                                <th
                                    style="
                                        position:sticky;
                                        top:0;
                                        background:#f8fafc;
                                        z-index:1;
                                    "
                                >
                                    Work Hours
                                </th>
                                <th
                                    style="
                                        position:sticky;
                                        top:0;
                                        background:#f8fafc;
                                        z-index:1;
                                    "
                                >
                                    PBM Total Downtime
                                </th>
                                <th
                                    style="
                                        position:sticky;
                                        top:0;
                                        background:#f8fafc;
                                        z-index:1;
                                    "
                                >
                                    Required Hours
                                </th>
                                <th
                                    style="
                                        position:sticky;
                                        top:0;
                                        background:#f8fafc;
                                        z-index:1;
                                    "
                                >
                                    Invalid Reason
                                </th>
                            </tr>
                        </thead>

                        <tbody>
                            ${body_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        `);

    dialog.show();
}


function show_au_warning_explanation() {
    const dialog = new frappe.ui.Dialog({
        title: __("A&U Warning"),
        size: "large",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "warning_html"
            }
        ]
    });

    dialog.fields_dict.warning_html.$wrapper.html(`
        <div style="
            padding:6px 4px 12px;
            line-height:1.6;
        ">
            <div style="
                background:#ffedd5;
                border:1px solid #f97316;
                border-radius:10px;
                padding:16px;
                margin-bottom:14px;
            ">
                <strong style="
                    color:#9a3412;
                    font-size:15px;
                ">
                    What does an A&amp;U Warning mean?
                </strong>

                <div style="margin-top:8px;">
                    The record is mathematically possible, but the
                    underlying hours are unusual and should be reviewed.
                </div>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Warning rules</strong>

                <ul style="
                    margin-top:8px;
                    margin-bottom:0;
                    padding-left:22px;
                ">
                    <!-- OLD UTILISATION AVAILABLE HOURS WARNING
                    <li>
                        Work Hours &gt; 0 while Utilisation Available Hours = 0.
                    </li>
                    -->
                    <li>
                        Required Hours = 0 while the machine still recorded Work Hours.
                    </li>
                    <li>
                        Utilisation is greater than 150%.
                    </li>
                </ul>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
            ">
                <strong>Important</strong>

                <div style="margin-top:8px;">
                    Warning rows are still included in the A&amp;U totals.
                    Orange does not automatically mean the data is wrong.
                </div>
            </div>
        </div>
    `);

    dialog.show();
}


function show_au_invalid_explanation() {
    const dialog = new frappe.ui.Dialog({
        title: __("Invalid A&U"),
        size: "large",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "invalid_html"
            }
        ]
    });

    dialog.fields_dict.invalid_html.$wrapper.html(`
        <div style="
            padding:6px 4px 12px;
            line-height:1.6;
        ">
            <div style="
                background:#fee2e2;
                border:1px solid #dc2626;
                border-radius:10px;
                padding:16px;
                margin-bottom:14px;
            ">
                <strong style="
                    color:#991b1b;
                    font-size:15px;
                ">
                    What does Invalid A&amp;U mean?
                </strong>

                <div style="margin-top:8px;">
                    The individual shift contains a physically impossible
                    or invalid combination of hours.
                </div>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Invalid rules</strong>

                <ul style="
                    margin-top:8px;
                    margin-bottom:0;
                    padding-left:22px;
                ">
                    <li>
                        Work Hours exceed Required Hours + Planned Downtime.
                    </li>
                    <li>
                        PBM Total Downtime exceeds Required Hours + Planned Downtime.
                    </li>
                    <li>
                        Work Hours + PBM Total Downtime exceed Required Hours + Planned Downtime.
                    </li>
                    <!-- OLD UTILISATION AVAILABLE HOURS VALIDATION
                    <li>
                        Utilisation Available Hours exceed the physical shift length.
                    </li>
                    -->
                </ul>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Example</strong>

                <div style="margin-top:8px;">
                    Required Hours = 7<br>
                    Planned Downtime = 2<br>
                    Validation Limit = 9 hours<br>
                    Work Hours = 6<br>
                    PBM Total Downtime = 4<br><br>

                    Work + PBM = 10 hours.<br>
                    10 hours exceeds the 9-hour planned shift limit,
                    so the shift is flagged red.
                </div>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
            ">
                <strong>Important</strong>

                <div style="margin-top:8px;">
                    The validation limit for each individual shift is:
                    Required Hours + Planned Downtime.

                    This allows the validation to follow the actual production
                    plan for weekdays, Saturdays and other planned shift changes.

                    Date, machine and category rows may naturally total
                    more than one shift.

                    Invalid shift rows are excluded from A&amp;U totals.
                </div>
            </div>
        </div>
    `);

    dialog.show();
}


function bind_engine_formula_header_clicks(report) {
    const $wrapper = $(report.page.wrapper);

    $wrapper.off(
        "click.availabilityFormulaHeaders",
        ".dt-cell--header"
    );

    $wrapper.on(
        "click.availabilityFormulaHeaders",
        ".dt-cell--header",
        function(event) {
            const text = (
                $(this)
                    .find(".dt-cell__content")
                    .clone()
                    .children()
                    .remove()
                    .end()
                    .text()
                    || ""
            )
                .replace(/\s+/g, " ")
                .trim();

            if (text === "Utilisation Available Hours") {
                event.preventDefault();
                event.stopPropagation();
                show_shift_available_formula();
                return;
            }

            if (text === "Availability Available Hours") {
                event.preventDefault();
                event.stopPropagation();
                show_availability_available_hours_formula();
                return;
            }

            if (text === "Utilisation %") {
                event.preventDefault();
                event.stopPropagation();
                show_utilisation_formula();
            }
        }
    );
}


function mark_engine_formula_headers_clickable() {
    const is_industry_calculation = (
        frappe.query_report
        && frappe.query_report.get_filter_value(
            "au_calculation"
        )
        === "Industry A&U Calculation"
    );

    const formulas = {
        "Utilisation Available Hours": (
            "MAX(Req - PBM, MIN(Work, Req))"
        ),
        "Availability Available Hours": (
            "MAX(Work, MAX(Req - PBM, 0))"
        ),
        "Availability %": (
            is_industry_calculation
                ? (
                    "Working Hours + Startup/Fatigue, capped at Required Hours; "
                    + "÷ Required Hours × 100"
                )
                : (
                    "(Availability Available Hours / Req Hrs) × 100 × A&U"
                )
        ),
        "Utilisation %": (
            "(Work Hrs / Utilisation Available Hours) × 100 × A&U"
        )
    };

    const clickable_headers = [
        "Utilisation Available Hours",
        "Availability Available Hours",
        "Utilisation %"
    ];

    const filter_row = document.querySelector(
        ".dt-row-filter"
    );

    if (!filter_row) {
        return;
    }

    document.querySelectorAll(
        ".dt-cell--header"
    ).forEach(function(header) {
        const content = header.querySelector(
            ".dt-cell__content"
        );

        if (!content) {
            return;
        }

        const text = (
            content.innerText || ""
        )
            .replace(/\s+/g, " ")
            .trim();

        const formula = formulas[text];

        if (!formula) {
            return;
        }

        const column_class = Array.from(
            header.classList
        ).find(function(class_name) {
            return class_name.startsWith(
                "dt-cell--col-"
            );
        });

        if (!column_class) {
            return;
        }

        const filter_cell = filter_row.querySelector(
            `.${column_class}`
        );

        if (
            !filter_cell
            || filter_cell.querySelector(
                ".availability-engine-header-formula"
            )
        ) {
            return;
        }

        const filter_content = filter_cell.querySelector(
            ".dt-cell__content"
        );

        if (!filter_content) {
            return;
        }

        filter_content.innerHTML = "";

        const formula_element = document.createElement(
            "div"
        );

        formula_element.className = (
            "availability-engine-header-formula"
        );

        formula_element.textContent = formula;

        filter_content.prepend(formula_element);

        if (clickable_headers.includes(text)) {
            header.style.cursor = "pointer";
            header.title = "Click to view formula";
        }
    });
}




function bind_shift_available_formula_header() {
    const headers = document.querySelectorAll(
        ".dt-cell--header"
    );

    headers.forEach(function(header) {
        const text = (
            header.innerText || ""
        ).trim();

        if (
            text !== "Utilisation Available Hours"
        ) {
            return;
        }

        if (
            header.dataset.shiftFormulaBound === "1"
        ) {
            return;
        }

        header.dataset.shiftFormulaBound = "1";
        header.style.cursor = "pointer";
        header.title = "Click to view formula";

        header.addEventListener(
            "click",
            show_shift_available_formula
        );
    });
}

function show_shift_available_formula() {
    const dialog = new frappe.ui.Dialog({
        title: __("Utilisation Available Hours"),
        size: "large",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "formula_html"
            }
        ]
    });

    dialog.fields_dict.formula_html.$wrapper.html(`
        <div style="
            padding:6px 4px 12px;
            line-height:1.6;
        ">
            <div style="
                background:#eff6ff;
                border:1px solid #93c5fd;
                border-radius:10px;
                padding:16px;
                margin-bottom:14px;
            ">
                <strong>Utilisation Available Hours Formula</strong>

                <div style="
                    margin-top:10px;
                    font-size:16px;
                    font-weight:700;
                ">
                    MAX(
                        Required Hours - PBM Total Downtime,
                        MIN(Work Hours, Required Hours)
                    )
                </div>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Why is this formula used?</strong>

                <div style="margin-top:8px;">
                    PBM downtime reduces the Required Hours available to work.
                    However, if the machine physically records more Work Hours
                    than that reduced amount, those Work Hours prove that the
                    machine was available for at least that amount of time.
                    <br><br>

                    The denominator therefore cannot be lower than Work Hours
                    while Work Hours remain below the Required Hours.
                    <br><br>

                    The denominator is capped at Required Hours so that work
                    performed above the required target is recognised as
                    recovery above 100%.
                </div>
            </div>

            <div style="
                background:#ecfdf5;
                border:1px solid #86efac;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Example — Machine recovers during the shift</strong>

                <div style="margin-top:8px;">
                    Required Hours = 9<br>
                    Work Hours = 8<br>
                    PBM Total Downtime = 1.933<br><br>

                    Required - PBM = 9 - 1.933 =
                    <strong>7.067h</strong><br><br>

                    But the machine physically worked
                    <strong>8 hours</strong>, so it must have been available
                    for at least 8 hours.<br><br>

                    MIN(Work, Required) =
                    MIN(8, 9) =
                    <strong>8h</strong><br><br>

                    Utilisation Available Hours =
                    MAX(7.067, 8) =
                    <strong>8h</strong><br><br>

                    Utilisation =
                    8 ÷ 8 × 100 =
                    <strong>100%</strong>
                </div>
            </div>

            <div style="
                background:#ecfdf5;
                border:1px solid #86efac;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Example — Recovery above Required Hours</strong>

                <div style="margin-top:8px;">
                    Required Hours = 9<br>
                    Work Hours = 10<br>
                    PBM Total Downtime = 1.933<br><br>

                    MIN(Work, Required) =
                    MIN(10, 9) =
                    <strong>9h</strong><br><br>

                    Utilisation Available Hours =
                    <strong>9h</strong><br><br>

                    Utilisation =
                    10 ÷ 9 × 100 =
                    <strong>111.11%</strong><br><br>

                    The additional work is therefore recognised as recovery
                    above the required target.
                </div>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
            ">
                <strong>Important</strong>

                <div style="margin-top:8px;">
                    If Required Hours are zero, Utilisation is 0%.
                </div>
            </div>
        </div>
    `);

    dialog.show();
}


function bind_available_hours_formula_header() {
    const headers = document.querySelectorAll(
        ".dt-cell--header"
    );


    headers.forEach(function(header) {
        const text = (
            header.innerText || ""
        ).trim();

        if (
            text !== "Availability Available Hours"
        ) {
            return;
        }

        if (
            header.dataset.formulaBound === "1"
        ) {
            return;
        }

        header.dataset.formulaBound = "1";
        header.style.cursor = "pointer";
        header.title = "Click to view formula";

        header.addEventListener(
            "click",
            show_availability_available_hours_formula
        );
    });
}

function show_availability_available_hours_formula() {
    const dialog = new frappe.ui.Dialog({
        title: __("Availability Available Hours"),
        size: "large",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "formula_html"
            }
        ]
    });

    dialog.fields_dict.formula_html.$wrapper.html(`
        <div style="
            padding:6px 4px 12px;
            line-height:1.6;
        ">
            <div style="
                background:#eff6ff;
                border:1px solid #93c5fd;
                border-radius:10px;
                padding:16px;
                margin-bottom:14px;
            ">
                <strong>Availability Available Hours Formula</strong>

                <div style="
                    margin-top:8px;
                    font-size:16px;
                    font-weight:700;
                ">
                    MAX(
                        Work Hours,
                        MAX(
                            Required Hours - PBM Total Downtime,
                            0
                        )
                    )
                </div>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Utilisation Available Hours</strong>

                <div style="margin-top:8px;">
                    Utilisation uses a separate denominator:
                </div>

                <div style="
                    margin-top:10px;
                    font-weight:700;
                ">
                    MAX(
                        Required Hours - PBM Total Downtime,
                        MIN(Work Hours, Required Hours)
                    )
                </div>

                <div style="margin-top:10px;">
                    This prevents the utilisation denominator from being lower
                    than hours the machine actually worked, while still
                    capping the denominator at Required Hours so recovery
                    above 100% can be recognised.
                </div>
            </div>


            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Purpose</strong>

                <div style="margin-top:8px;">
                    Availability can exceed 100% when the machine records
                    more Work Hours than its Required Hours.
                </div>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
            ">
                <strong>Totals</strong>

                <div style="margin-top:8px;">
                    Each valid shift is calculated first.
                    Invalid shifts are excluded from the machine,
                    date and category totals.
                </div>
            </div>
        </div>
    `);

    dialog.show();
}

function show_utilisation_formula() {
    const dialog = new frappe.ui.Dialog({
        title: __("Utilisation %"),
        size: "large",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "formula_html"
            }
        ]
    });

    dialog.fields_dict.formula_html.$wrapper.html(`
        <div style="
            padding:6px 4px 12px;
            line-height:1.6;
        ">
            <div style="
                background:#eff6ff;
                border:1px solid #93c5fd;
                border-radius:10px;
                padding:16px;
                margin-bottom:14px;
            ">
                <div style="
                    color:#1d4ed8;
                    font-size:15px;
                    font-weight:700;
                    margin-bottom:8px;
                ">
                    Utilisation Formula
                </div>

                <div style="
                    color:#1d4ed8;
                    font-size:16px;
                    font-weight:700;
                ">
                    Work Hours
                    ÷
                    Utilisation Available Hours
                    × 100
                    × A&amp;U Percentage
                </div>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Utilisation Available Hours</strong>

                <div style="
                    margin-top:8px;
                    font-weight:700;
                ">
                    MAX(
                        Required Hours - PBM Total Downtime,
                        MIN(Work Hours, Required Hours)
                    )
                </div>
            </div>

            <div style="
                background:#f8fafc;
                border:1px solid #d1d8dd;
                border-radius:10px;
                padding:16px;
                margin-bottom:12px;
            ">
                <strong>Example — Why the denominator adjusts</strong>

                <div style="margin-top:8px;">
                    Required Hours = 9<br>
                    PBM Total Downtime = 1.933<br>
                    Work Hours = 8<br><br>

                    Required - PBM =
                    9 - 1.933 =
                    <strong>7.067h</strong><br><br>

                    The machine physically worked 8 hours, so its utilisation
                    denominator cannot reasonably be only 7.067 hours.<br><br>

                    MIN(8, 9) =
                    <strong>8h</strong><br>

                    MAX(7.067, 8) =
                    <strong>8h</strong><br><br>

                    Utilisation =
                    8 ÷ 8 × 100 =
                    <strong>100%</strong><br><br>

                    If the machine works 10 hours against a 9-hour requirement,
                    the denominator remains 9 hours and Utilisation becomes
                    <strong>111.11%</strong>, recognising recovery.
                </div>
            </div>

            <div style="
                background:#ecfdf5;
                border:1px solid #86efac;
                border-radius:10px;
                padding:16px;
            ">
                <strong>Combined / Total Utilisation</strong>

                <div style="margin-top:8px;">
                    Total Work Hours
                    ÷
                    Total Utilisation Available Hours
                    × 100
                    × A&amp;U Percentage
                </div>
            </div>
        </div>
    `);

    dialog.show();
}



function apply_engine_shift_highlight(value, shift) {
    const background = (
        shift === "Day"
        ? "#eaf4ff"
        : "#f3f4f6"
    );

    return `
        <span
            class="availability-engine-shift-cell"
            style="
                display:block;
                min-height:100%;
                margin:-8px -10px;
                padding:8px 10px;
                background:${background} !important;
            "
        >
            ${value || ""}
        </span>
    `;
}


function bind_engine_expanded_date_highlight() {
    const report = document.querySelector(
        '.query-report[data-report-name="Availability and Utilisation Engine"]'
    );

    if (
        !report
        || report.dataset.expandedDateBound === "1"
    ) {
        return;
    }

    report.dataset.expandedDateBound = "1";

    report.addEventListener("click", function(event) {
        const toggle = event.target.closest(
            ".dt-cell__toggle, .dt-cell__tree-node, .dt-tree-node"
        );

        if (!toggle) {
            return;
        }

        const row = toggle.closest(".dt-row");

        if (!row) {
            return;
        }

        row.classList.toggle(
            "availability-engine-row-expanded"
        );
    });
}




function apply_engine_spare_highlight(value, reason) {
    const safe_reason = frappe.utils.escape_html(
        reason
        || "Spare/Swing unit in Monthly Production Planning"
    );

    return `
        <span
            class="availability-engine-spare-cell"
            title="${safe_reason}"
            style="
                display:block;
                min-height:100%;
                margin:-8px -10px;
                padding:8px 10px;
                background:#e6d6ff !important;
                color:#4b0082 !important;
                font-weight:600 !important;
                border-left:3px solid #7b2cbf !important;
            "
        >
            ${value || ""}
        </span>
    `;
}

function format_engine_hours(hours_value) {
    const total_minutes = Math.round(
        flt(hours_value || 0) * 60
    );

    const hours = Math.floor(
        total_minutes / 60
    );

    const minutes = total_minutes % 60;

    if (hours && minutes) {
        return `${hours}h ${minutes}m`;
    }

    if (hours) {
        return `${hours}h`;
    }

    return `${minutes}m`;
}


function apply_engine_freeze_columns() {
    if (
        !frappe.query_report
        || !frappe.query_report.datatable
    ) {
        return;
    }

    if (
        frappe.query_report.report_name
        !== "Availability and Utilisation Engine"
    ) {
        return;
    }

    frappe.query_report.datatable.options.freezeColumns = 8;

    apply_engine_styles();
}


function apply_engine_styles() {
    const style_id = "availability-utilisation-engine-style";
    const old_style = document.getElementById(style_id);

    if (old_style) {
        old_style.remove();
    }

    const style = document.createElement("style");

    style.id = style_id;

    style.innerHTML = `
        .query-report[data-report-name="Availability and Utilisation Engine"]
        .dt-row-filter {
            min-height: 68px !important;
            height: 68px !important;
        }

        .query-report[data-report-name="Availability and Utilisation Engine"]
        .dt-row-filter .dt-cell {
            min-height: 68px !important;
            height: 68px !important;
        }

        .query-report[data-report-name="Availability and Utilisation Engine"]
        .dt-row-filter .dt-cell__content {
            height: 100% !important;
            overflow: visible !important;
            white-space: normal !important;
        }

        .availability-engine-header-formula {
            margin-bottom: 5px;
            padding: 4px 3px;
            border: 1px solid #60a5fa;
            border-radius: 4px;
            background: #eff6ff;
            color: #1d4ed8;
            font-size: 9px;
            font-weight: 700;
            line-height: 1.15;
            text-align: center;
            white-space: normal;
        }


        .query-report[data-report-name="Availability and Utilisation Engine"]
        .dt-cell--header {
            background: #dcfce7 !important;
            color: #166534 !important;
            font-weight: 800 !important;
            border-bottom: 2px solid #16a34a !important;
        }


        .dt-cell--col-0,
        .dt-cell--col-1,
        .dt-cell--col-2,
        .dt-cell--col-3,
        .dt-cell--col-4,
        .dt-cell--col-5,
        .dt-cell--col-6,
        .dt-cell--col-7 {
            position: sticky !important;
            background: #ffffff !important;
            z-index: 30 !important;
            box-shadow: 1px 0 0 #d1d8dd !important;
        }

        .dt-header .dt-cell--col-0,
        .dt-header .dt-cell--col-1,
        .dt-header .dt-cell--col-2,
        .dt-header .dt-cell--col-3,
        .dt-header .dt-cell--col-4,
        .dt-header .dt-cell--col-5,
        .dt-header .dt-cell--col-6,
        .dt-header .dt-cell--col-7,
        .dt-cell--header.dt-cell--col-0,
        .dt-cell--header.dt-cell--col-1,
        .dt-cell--header.dt-cell--col-2,
        .dt-cell--header.dt-cell--col-3,
        .dt-cell--header.dt-cell--col-4,
        .dt-cell--header.dt-cell--col-5,
        .dt-cell--header.dt-cell--col-6,
        .dt-cell--header.dt-cell--col-7 {
            position: sticky !important;
            background: #dcfce7 !important;
            z-index: 60 !important;
        }

        .dt-cell--col-0 {
            left: 0 !important;
        }

        .dt-cell--col-1 {
            left: 38px !important;
        }

        .dt-cell--col-2 {
            left: 168px !important;
        }

        .dt-cell--col-3 {
            left: 268px !important;
        }

        .dt-cell--col-4 {
            left: 383px !important;
        }

        .dt-cell--col-5 {
            left: 468px !important;
        }

        .dt-cell--col-6 {
            left: 603px !important;
        }

        .dt-cell--col-7 {
            left: 723px !important;
        }

        .query-report[data-report-name="Availability and Utilisation Engine"]
        .availability-engine-spare-cell {
            display: block;
            min-height: 100%;
            margin: -8px -10px;
            padding: 8px 10px;
            background: #e6d6ff !important;
            color: #4b0082 !important;
            font-weight: 600 !important;
            border-left: 3px solid #7b2cbf !important;
        }

        .query-report[data-report-name="Availability and Utilisation Engine"]
        .dt-cell__tree-node,
        .query-report[data-report-name="Availability and Utilisation Engine"]
        .dt-tree-node,
        .query-report[data-report-name="Availability and Utilisation Engine"]
        .dt-cell__toggle {
            position: relative !important;
            z-index: 20 !important;
            color: #111111 !important;
            opacity: 1 !important;
            visibility: visible !important;
        }

        .query-report[data-report-name="Availability and Utilisation Engine"]
        .availability-engine-date-label {
            font-weight: 600;
        }

        .query-report[data-report-name="Availability and Utilisation Engine"]
        .availability-engine-row-expanded
        .dt-cell {
            border-top: 2px solid #22c55e !important;
            border-bottom: 2px solid #22c55e !important;
        }

        .query-report[data-report-name="Availability and Utilisation Engine"]
        .availability-engine-row-expanded
        .dt-cell:first-child {
            border-left: 3px solid #16a34a !important;
        }

        .query-report[data-report-name="Availability and Utilisation Engine"]
        .availability-engine-row-expanded
        .dt-cell:last-child {
            border-right: 2px solid #22c55e !important;
        }
    `;

    document.head.appendChild(style);
}
// BEGIN INVALID AU PBM DRILLDOWN

function get_open_invalid_au_dialog() {
    let $match = $();

    $(".modal:visible").each(
        function() {
            const $modal = $(this);

            const modal_text = (
                $modal.text()
                || ""
            );

            let has_pbm_header = false;

            $modal
                .find("thead th")
                .each(
                    function() {
                        if (
                            (
                                $(this).text()
                                || ""
                            ).trim()
                            === "PBM Total Downtime"
                        ) {
                            has_pbm_header = true;
                        }
                    }
                );

            if (
                modal_text.indexOf(
                    "Invalid A&U Shifts"
                ) !== -1
                && has_pbm_header
            ) {
                $match = $modal;
            }
        }
    );

    return $match;
}


function add_invalid_au_pbm_view_column(
    report
) {
    const rows = (
        get_invalid_au_shift_rows(
            report
        )
        || []
    );

    if (!rows.length) {
        return;
    }

    const $modal = (
        get_open_invalid_au_dialog()
    );

    if (!$modal.length) {
        return;
    }

    const $table = (
        $modal
            .find("table")
            .first()
    );

    if (!$table.length) {
        return;
    }

    if (
        $table.find(
            ".availability-engine-invalid-pbm-header"
        ).length
    ) {
        return;
    }

    let pbm_column_index = -1;
    let $pbm_header = $();

    $table
        .find("thead tr")
        .first()
        .children("th")
        .each(
            function(index) {
                const heading = (
                    $(this).text()
                    || ""
                ).trim();

                if (
                    heading
                    === "PBM Total Downtime"
                ) {
                    pbm_column_index = index;
                    $pbm_header = $(this);
                }
            }
        );

    if (
        pbm_column_index < 0
        || !$pbm_header.length
    ) {
        return;
    }

    $pbm_header.after(`
        <th
            class="
                availability-engine-invalid-pbm-header
            "
            style="
                position:sticky;
                top:0;
                background:#f8fafc;
                z-index:1;
                min-width:165px;
                white-space:nowrap;
            "
        >
            PBM Total Downtime View
        </th>
    `);

    $table
        .find("tbody tr")
        .each(
            function(index) {
                const row = rows[index];

                if (!row) {
                    return;
                }

                const $cells = (
                    $(this).children("td")
                );

                if (
                    $cells.length
                    <= pbm_column_index
                ) {
                    return;
                }

                const $button = $(`
                    <button
                        type="button"
                        class="
                            btn
                            btn-xs
                            btn-primary
                            availability-engine-invalid-pbm-view
                        "
                        style="
                            min-width:70px;
                            border-radius:12px;
                            font-weight:600;
                        "
                    >
                        View
                    </button>
                `);

                $button.on(
                    "click",
                    function() {
                        open_invalid_au_pbm_records(
                            row
                        );
                    }
                );

                const $view_cell = $(`
                    <td
                        style="
                            text-align:center;
                            vertical-align:middle;
                            white-space:nowrap;
                        "
                    ></td>
                `);

                $view_cell.append(
                    $button
                );

                $cells
                    .eq(
                        pbm_column_index
                    )
                    .after(
                        $view_cell
                    );
            }
        );

    window.setTimeout(function() {
        add_invalid_au_exclusion_column(report);
    }, 0);
}


function open_invalid_au_pbm_records(
    row
) {
    if (!row) {
        return;
    }

    let location = (
        row.location
        || ""
    );

    if (
        !location
        && frappe.query_report
        && frappe.query_report
            .get_filter_value
    ) {
        location = (
            frappe.query_report
                .get_filter_value(
                    "location"
                )
            || ""
        );
    }

    frappe.call({
        method:
            "engineering.engineering.report.availability_and_utilisation_engine.availability_and_utilisation_engine.get_invalid_au_pbm_records",

        args: {
            asset_name: (
                row.asset_name
                || ""
            ),
            location: location,
            shift_date: (
                row.shift_date
                || ""
            ),
            shift: (
                row.shift
                || ""
            ),
        },

        freeze: true,

        freeze_message:
            __(
                "Loading PBM records..."
            ),

        callback(response) {
            const result = (
                response.message
                || {}
            );

            const records = (
                result.records
                || []
            );

            if (!records.length) {
                frappe.msgprint({
                    title:
                        __(
                            "PBM Total Downtime"
                        ),
                    indicator:
                        "orange",
                    message:
                        __(
                            "No contributing Plant Breakdown or Maintenance record was found for this shift."
                        ),
                });

                return;
            }

            if (records.length === 1) {
                window.open(
                    frappe.utils.get_form_link(
                        "Plant Breakdown or Maintenance",
                        records[0].name
                    ),
                    "_blank"
                );

                return;
            }

            show_invalid_au_pbm_record_dialog(
                row,
                records
            );
        },
    });
}


function format_invalid_au_pbm_datetime(
    value
) {
    if (!value) {
        return "-";
    }

    try {
        if (
            frappe.datetime
            && frappe.datetime
                .str_to_user
        ) {
            return (
                frappe.datetime
                    .str_to_user(
                        String(value)
                    )
            );
        }
    } catch (error) {
        // Fall back to source value.
    }

    return String(value);
}


function format_invalid_au_pbm_minutes(
    minutes
) {
    const total_minutes = Math.max(
        0,
        Math.round(
            Number(
                minutes
                || 0
            )
        )
    );

    const hours = Math.floor(
        total_minutes / 60
    );

    const mins = (
        total_minutes % 60
    );

    if (
        hours
        && mins
    ) {
        return (
            `${hours}h ${mins}m`
        );
    }

    if (hours) {
        return `${hours}h`;
    }

    return `${mins}m`;
}


function show_invalid_au_pbm_record_dialog(
    row,
    records
) {
    const date_text = (
        typeof format_invalid_au_date
            === "function"
        ? format_invalid_au_date(
            row.shift_date
        )
        : String(
            row.shift_date
            || ""
        )
    );

    const machine_text = (
        row.asset_name
        || ""
    );

    const shift_text = (
        row.shift
        || ""
    );

    const body_rows = records
        .map(
            function(record) {
                return `
                    <tr>
                        <td
                            style="
                                padding:8px 10px;
                                vertical-align:middle;
                                font-weight:600;
                                white-space:nowrap;
                            "
                        >
                            ${frappe.utils.escape_html(
                                String(
                                    record.name
                                    || ""
                                )
                            )}
                        </td>

                        <td
                            style="
                                padding:8px 10px;
                                vertical-align:middle;
                            "
                        >
                            ${frappe.utils.escape_html(
                                String(
                                    record.breakdown_reason
                                    || ""
                                )
                            )}
                        </td>

                        <td
                            style="
                                padding:8px 10px;
                                vertical-align:middle;
                                white-space:nowrap;
                            "
                        >
                            ${frappe.utils.escape_html(
                                format_invalid_au_pbm_datetime(
                                    record.breakdown_start_datetime
                                )
                            )}
                        </td>

                        <td
                            style="
                                padding:8px 10px;
                                vertical-align:middle;
                                white-space:nowrap;
                            "
                        >
                            ${frappe.utils.escape_html(
                                format_invalid_au_pbm_datetime(
                                    record.resolved_datetime
                                )
                            )}
                        </td>

                        <td
                            style="
                                padding:8px 10px;
                                vertical-align:middle;
                                white-space:nowrap;
                                font-weight:600;
                            "
                        >
                            ${frappe.utils.escape_html(
                                format_invalid_au_pbm_minutes(
                                    record.contributing_minutes
                                )
                            )}
                        </td>

                        <td
                            style="
                                padding:8px 10px;
                                text-align:center;
                                vertical-align:middle;
                                white-space:nowrap;
                            "
                        >
                            <button
                                type="button"
                                class="
                                    btn
                                    btn-xs
                                    btn-primary
                                    availability-engine-open-pbm
                                "
                            >
                                Open PBM
                            </button>
                        </td>
                    </tr>
                `;
            }
        )
        .join("");

    const dialog = new frappe.ui.Dialog({
        title:
            __(
                "PBM Total Downtime - {0} - {1} {2}",
                [
                    machine_text,
                    date_text,
                    shift_text,
                ]
            ),

        size: "extra-large",

        fields: [
            {
                fieldtype: "HTML",
                fieldname:
                    "invalid_au_pbm_html",
            },
        ],
    });

    dialog
        .fields_dict
        .invalid_au_pbm_html
        .$wrapper
        .html(`
            <div
                style="
                    max-height:65vh;
                    overflow:auto;
                "
            >
                <table
                    class="
                        table
                        table-bordered
                        table-hover
                    "
                    style="
                        margin-bottom:0;
                    "
                >
                    <thead>
                        <tr>
                            <th>PBM Record</th>
                            <th>Breakdown Reason</th>
                            <th>Breakdown Start</th>
                            <th>Resolved</th>
                            <th>A&U PBM Time</th>
                            <th>View</th>
                        </tr>
                    </thead>

                    <tbody>
                        ${body_rows}
                    </tbody>
                </table>
            </div>
        `);

    dialog
        .fields_dict
        .invalid_au_pbm_html
        .$wrapper
        .find(
            ".availability-engine-open-pbm"
        )
        .each(
            function(index) {
                $(this).on(
                    "click",
                    function() {
                        const record = (
                            records[index]
                        );

                        if (
                            !record
                            || !record.name
                        ) {
                            return;
                        }

                        dialog.hide();

                        window.open(
                            frappe.utils.get_form_link(
                                "Plant Breakdown or Maintenance",
                                record.name
                            ),
                            "_blank"
                        );
                    }
                );
            }
        );

    dialog.show();
}


/*
 * Wrap the existing Invalid A&U dialog rather than rewriting it.
 * The existing calculation/table code remains untouched.
 */
(function install_invalid_au_pbm_drilldown() {
    if (
        window
            .__availability_engine_invalid_pbm_drilldown_installed
    ) {
        return;
    }

    window
        .__availability_engine_invalid_pbm_drilldown_installed = true;

    const original_show_invalid_au_rows = (
        show_invalid_au_rows
    );

    show_invalid_au_rows = function(
        report
    ) {
        const result = (
            original_show_invalid_au_rows
                .apply(
                    this,
                    arguments
                )
        );

        window.setTimeout(
            function() {
                add_invalid_au_pbm_view_column(
                    report
                );
            },
            100
        );

        return result;
    };
})();

// END INVALID AU PBM DRILLDOWN

// BEGIN INVALID AU PERMANENT EXCLUSION

function can_exclude_invalid_au_shift() {
    return (
        frappe.session.user === "Administrator"
        || frappe.user.has_role("Engineering Manager")
        || frappe.user.has_role("Production Manager")
    );
}

function open_invalid_au_exclusion_dialog(
    report,
    invalid_dialog,
    row
) {
    const dialog = new frappe.ui.Dialog({
        title: __("Exclude Invalid A&U Flag"),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "shift_summary"
            },
            {
                fieldtype: "Small Text",
                fieldname: "exclusion_comment",
                label: __("Reason for Exclusion"),
                reqd: 1,
                description: __(
                    "This comment becomes part of the permanent audit record."
                )
            }
        ],
        primary_action_label: __("Permanently Exclude Flag"),
        primary_action(values) {
            const comment = String(
                values.exclusion_comment || ""
            ).trim();

            if (comment.length < 5) {
                frappe.msgprint(
                    __("Please provide a meaningful exclusion comment.")
                );
                return;
            }

            frappe.call({
                method: (
                    "engineering.engineering.doctype."
                    + "au_invalid_shift_exclusion."
                    + "au_invalid_shift_exclusion."
                    + "exclude_invalid_au_shift"
                ),
                args: {
                    location: row.location,
                    shift_date: row.shift_date,
                    shift: row.shift,
                    asset_name: row.asset_name,
                    asset_category: row.asset_category,
                    company: row.company,
                    work_hours: row.work_hours,
                    pbm_total_downtime: row.pbm_total_downtime,
                    required_hours: row.required_hours,
                    invalid_reason: get_invalid_au_reason(row),
                    exclusion_comment: comment
                },
                freeze: true,
                freeze_message: __("Saving permanent exclusion..."),
                callback(response) {
                    const result = response.message || {};

                    dialog.hide();

                    if (
                        invalid_dialog
                        && invalid_dialog.length
                    ) {
                        invalid_dialog.modal("hide");
                    }

                    frappe.show_alert({
                        message: result.message || __(
                            "Invalid A&U flag excluded."
                        ),
                        indicator: "green"
                    }, 7);

                    report.refresh();
                }
            });
        }
    });

    dialog.fields_dict.shift_summary.$wrapper.html(`
        <div style="
            padding:12px;
            margin-bottom:12px;
            border:1px solid #d1d8dd;
            border-radius:8px;
            background:#f8fafc;
            line-height:1.7;
        ">
            <strong>${frappe.utils.escape_html(String(row.asset_name || ""))}</strong><br>
            Site: ${frappe.utils.escape_html(String(row.location || ""))}<br>
            Date: ${frappe.utils.escape_html(format_invalid_au_date(row.shift_date))}<br>
            Shift: ${frappe.utils.escape_html(String(row.shift || ""))}<br>
            Work Hours: ${frappe.utils.escape_html(format_engine_hours(row.work_hours))}<br>
            PBM: ${frappe.utils.escape_html(format_engine_hours(row.pbm_total_downtime))}<br>
            Required Hours: ${frappe.utils.escape_html(format_engine_hours(row.required_hours))}
        </div>
    `);

    dialog.show();
}


function add_invalid_au_exclusion_column(report) {
    if (!can_exclude_invalid_au_shift()) {
        return;
    }

    const rows = get_invalid_au_shift_rows(report);
    const $modal = get_open_invalid_au_dialog();

    if (!$modal.length || !rows.length) {
        return;
    }

    const $table = $modal.find("table").first();

    if (
        !$table.length
        || $table.find(
            ".availability-engine-invalid-exclusion-header"
        ).length
    ) {
        return;
    }

    $table.find("thead tr").first().append(`
        <th
            class="availability-engine-invalid-exclusion-header"
            style="
                position:sticky;
                top:0;
                background:#f8fafc;
                z-index:1;
                min-width:130px;
                white-space:nowrap;
            "
        >
            Flag Action
        </th>
    `);

    $table.find("tbody tr").each(function(index) {
        const row = rows[index];

        if (!row) {
            return;
        }

        const $button = $(`
            <button
                type="button"
                class="btn btn-xs btn-danger"
                style="
                    min-width:105px;
                    border-radius:12px;
                    font-weight:700;
                "
            >
                Exclude Flag
            </button>
        `);

        $button.on("click", function() {
            open_invalid_au_exclusion_dialog(
                report,
                $modal,
                row
            );
        });

        const $cell = $(`
            <td style="
                text-align:center;
                vertical-align:middle;
                white-space:nowrap;
            "></td>
        `);

        $cell.append($button);
        $(this).append($cell);
    });
}


(function install_invalid_au_exclusion_action() {
    if (
        typeof show_invalid_au_rows !== "function"
        || show_invalid_au_rows
            .__invalid_au_exclusion_installed
    ) {
        return;
    }

    const original_show_invalid_au_rows = show_invalid_au_rows;

    show_invalid_au_rows = function(report) {
        original_show_invalid_au_rows(report);

        window.setTimeout(function() {
            add_invalid_au_exclusion_column(report);
        }, 100);
    };

    show_invalid_au_rows
        .__invalid_au_exclusion_installed = true;
})();

// END INVALID AU PERMANENT EXCLUSION

// AU_ENGINE_REASON_VIEW_START

(() => {

    const REPORT_NAME =
        "Availability and Utilisation Engine";


    const report =
        frappe.query_reports[
            REPORT_NAME
        ];


    if (!report) {
        return;
    }


    const original_formatter =
        report.formatter;


    function escape_html(value) {

        return frappe.utils.escape_html(
            String(
                value == null
                    ? ""
                    : value
            )
        );
    }


    // ========================================================
    // VIEW BUTTON
    // ========================================================

    report.formatter = function(
        value,
        row,
        column,
        data,
        default_formatter
    ) {

        if (
            data
            && data.asset_name
            && (
                column.fieldname
                    === "breakdown_reason"
                ||
                column.fieldname
                    === "other_delay_reason"
            )
        ) {

            if (!value) {
                return "";
            }


            const asset =
                escape_html(
                    data.asset_name
                );


            const type = (
                column.fieldname
                    === "breakdown_reason"
            )
                ? "breakdown"
                : "delay";


            return `
                <button
                    type="button"
                    class="btn btn-xs btn-default"
                    style="
                        color:#1d4ed8;
                        border:1px solid #2563eb;
                        border-radius:12px;
                        padding:2px 12px;
                        font-weight:700;
                        background:#eff6ff;
                    "
                    onclick="
                        window.show_au_engine_reason_popup(
                            '${asset}',
                            '${type}'
                        );
                        return false;
                    "
                >
                    View
                </button>
            `;
        }


        if (
            typeof original_formatter
            === "function"
        ) {

            return original_formatter.call(
                this,
                value,
                row,
                column,
                data,
                default_formatter
            );
        }


        return default_formatter(
            value,
            row,
            column,
            data
        );
    };


    // ========================================================
    // POPUP
    // ========================================================

    window.show_au_engine_reason_popup =
        async function(
            asset_name,
            type
        ) {

            const filters =
                frappe.query_report
                    .get_filter_values();


            const is_breakdown =
                type === "breakdown";


            const method =
                is_breakdown
                    ?
                    (
                        "engineering.engineering.report." +
                        "availability_and_utilisation_engine." +
                        "availability_and_utilisation_engine." +
                        "get_au_engine_breakdown_reasons"
                    )
                    :
                    (
                        "engineering.engineering.report." +
                        "availability_and_utilisation_engine." +
                        "availability_and_utilisation_engine." +
                        "get_au_engine_other_delay_reasons"
                    );


            const response =
                await frappe.call({
                    method: method,

                    args: {
                        asset_name:
                            asset_name,

                        from_date:
                            filters.from_date,

                        to_date:
                            filters.to_date,

                        location:
                            filters.location
                            || null
                    },

                    freeze: false
                });


            const details =
                response.message
                || [];


            if (!details.length) {

                frappe.msgprint(
                    "No reasons found for "
                    + asset_name
                    + "."
                );

                return;
            }


            const title =
                is_breakdown
                    ? "Breakdown Reasons"
                    : "Other Delay Reasons";


            const rows =
                details.map(
                    detail => {

                        const date =
                            escape_html(
                                detail.date
                                || ""
                            );


                        const shift =
                            escape_html(
                                detail.shift
                                || ""
                            );


                        const reason =
                            escape_html(
                                detail.reason
                                || ""
                            );


                        if (is_breakdown) {

                            return `
                                <tr>
                                    <td style="
                                        padding:8px 10px;
                                        border-bottom:1px solid #dbeafe;
                                        white-space:nowrap;
                                    ">
                                        ${date || "-"}
                                    </td>

                                    <td style="
                                        padding:8px 10px;
                                        border-bottom:1px solid #dbeafe;
                                        font-weight:600;
                                    ">
                                        ${reason || "-"}
                                    </td>
                                </tr>
                            `;
                        }


                        return `
                            <tr>
                                <td style="
                                    padding:8px 10px;
                                    border-bottom:1px solid #dbeafe;
                                    white-space:nowrap;
                                ">
                                    ${date || "-"}
                                </td>

                                <td style="
                                    padding:8px 10px;
                                    border-bottom:1px solid #dbeafe;
                                    white-space:nowrap;
                                ">
                                    ${shift || "-"}
                                </td>

                                <td style="
                                    padding:8px 10px;
                                    border-bottom:1px solid #dbeafe;
                                    font-weight:600;
                                ">
                                    ${reason || "-"}
                                </td>
                            </tr>
                        `;
                    }
                ).join("");


            const headers =
                is_breakdown
                    ?
                    `
                        <th style="
                            padding:8px 10px;
                            text-align:left;
                            width:130px;
                        ">
                            Date
                        </th>

                        <th style="
                            padding:8px 10px;
                            text-align:left;
                        ">
                            Breakdown Reason
                        </th>
                    `
                    :
                    `
                        <th style="
                            padding:8px 10px;
                            text-align:left;
                            width:130px;
                        ">
                            Date
                        </th>

                        <th style="
                            padding:8px 10px;
                            text-align:left;
                            width:90px;
                        ">
                            Shift
                        </th>

                        <th style="
                            padding:8px 10px;
                            text-align:left;
                        ">
                            Reason / Description
                        </th>
                    `;


            const dialog =
                new frappe.ui.Dialog({
                    title:
                        `${title} - ${asset_name}`,

                    size:
                        "large"
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
                        ${title} for ${escape_html(asset_name)}
                    </div>

                    <div style="
                        overflow-x:auto;
                    ">

                        <table style="
                            width:100%;
                            border-collapse:collapse;
                        ">

                            <thead>
                                <tr style="
                                    background:#eff6ff;
                                    color:#1d4ed8;
                                ">
                                    ${headers}
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
        };

})();

// AU_ENGINE_REASON_VIEW_END

// ============================================================
// AU ENGINE - PLANNED MAINTENANCE REASON VIEW
// ============================================================

(function install_planned_maintenance_reason_view() {

    const REPORT_NAME =
        "Availability and Utilisation Engine";


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

        if (
            column.fieldname
            === "planned_maintenance_reason"
        ) {

            if (
                !data
                || !data.asset_name
                || !data.shift
                || !value
            ) {
                return "";
            }


            const asset =
                frappe.utils.escape_html(
                    String(
                        data.asset_name
                        || ""
                    )
                );


            return `
                <button
                    type="button"
                    class="btn btn-xs btn-default"
                    style="
                        color:#1d4ed8;
                        border:1px solid #2563eb;
                        border-radius:12px;
                        padding:2px 12px;
                        font-weight:700;
                        background:#eff6ff;
                    "
                    onclick="
                        window.show_au_engine_planned_maintenance_popup(
                            '${asset}'
                        );
                        return false;
                    "
                >
                    View
                </button>
            `;
        }


        return previous_formatter.call(
            this,
            value,
            row,
            column,
            data,
            default_formatter
        );
    };


    window.show_au_engine_planned_maintenance_popup =
        async function(
            asset_name
        ) {

            const filters =
                frappe.query_report
                    .get_filter_values();


            const response =
                await frappe.call({

                    method:
                        "engineering.engineering.report." +
                        "availability_and_utilisation_engine." +
                        "availability_and_utilisation_engine." +
                        "get_au_engine_planned_maintenance_reasons",

                    args: {
                        asset_name:
                            asset_name,

                        from_date:
                            filters.from_date,

                        to_date:
                            filters.to_date,

                        location:
                            filters.location
                            || null
                    }
                });


            const records =
                response.message
                || [];


            if (!records.length) {

                frappe.msgprint(
                    "No Planned Maintenance records found for "
                    + asset_name
                    + "."
                );

                return;
            }


            const esc = function(value) {

                return frappe.utils.escape_html(
                    String(
                        value
                        || ""
                    )
                );
            };


            const body =
                records.map(
                    record => `
                        <tr>
                            <td style="
                                padding:8px 10px;
                                border-bottom:1px solid #dbeafe;
                                white-space:nowrap;
                            ">
                                ${esc(record.start)}
                            </td>

                            <td style="
                                padding:8px 10px;
                                border-bottom:1px solid #dbeafe;
                                white-space:nowrap;
                            ">
                                ${esc(record.resolved || "Open")}
                            </td>

                            <td style="
                                padding:8px 10px;
                                border-bottom:1px solid #dbeafe;
                                font-weight:600;
                            ">
                                ${esc(record.reason)}
                            </td>
                        </tr>
                    `
                ).join("");


            const dialog =
                new frappe.ui.Dialog({

                    title:
                        "Planned Maintenance Reasons - "
                        + asset_name,

                    size:
                        "large"
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
                        Planned Maintenance Reasons for
                        ${esc(asset_name)}
                    </div>

                    <div style="
                        overflow-x:auto;
                    ">

                        <table style="
                            width:100%;
                            border-collapse:collapse;
                        ">

                            <thead>
                                <tr style="
                                    background:#eff6ff;
                                    color:#1d4ed8;
                                ">

                                    <th style="
                                        padding:9px 10px;
                                        text-align:left;
                                    ">
                                        Start
                                    </th>

                                    <th style="
                                        padding:9px 10px;
                                        text-align:left;
                                    ">
                                        Resolved
                                    </th>

                                    <th style="
                                        padding:9px 10px;
                                        text-align:left;
                                    ">
                                        Reason
                                    </th>

                                </tr>
                            </thead>

                            <tbody>
                                ${body}
                            </tbody>

                        </table>

                    </div>

                </div>
            `);


            dialog.show();
        };

})();

// ============================================================
// END PLANNED MAINTENANCE REASON VIEW
// ============================================================

// ============================================================
// INDUSTRY A&U FORMULA BUTTONS
// ============================================================

(function install_industry_formula_buttons() {
    const REPORT_NAME =
        "Availability and Utilisation Engine";

    function is_industry_mode() {
        return (
            frappe.query_report
            && frappe.query_report.get_filter_value(
                "au_calculation"
            ) === "Industry A&U Calculation"
        );
    }


    function formula_button(handler_name) {
        return `
            <div
                data-industry-formula-button="1"
                style="
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    width:100%;
                    height:100%;
                "
            >
                <button
                    type="button"
                    class="btn btn-xs btn-default"
                    style="
                        color:#1d4ed8;
                        border:1px solid #2563eb;
                        border-radius:10px;
                        background:#eff6ff;
                        font-size:10px;
                        font-weight:700;
                        padding:2px 8px;
                        white-space:nowrap;
                    "
                    onclick="
                        window.${handler_name}();
                        return false;
                    "
                >
                    View Formula
                </button>
            </div>
        `;
    }


    function place_industry_formula_buttons() {
        if (!is_industry_mode()) {
            return;
        }

        const filter_row =
            document.querySelector(
                ".dt-row-filter"
            );

        if (!filter_row) {
            return;
        }

        const headers = Array.from(
            document.querySelectorAll(
                ".dt-cell--header"
            )
        );

        const filter_cells = Array.from(
            filter_row.querySelectorAll(
                ".dt-cell"
            )
        );

        const buttons = {
            "Availability %":
                "show_industry_availability_formula",

            "Utilisation Available Hours":
                "show_industry_util_available_formula",

            "Utilisation %":
                "show_industry_utilisation_formula"
        };

        headers.forEach(
            function(header, index) {
                const text = (
                    header.innerText || ""
                )
                    .replace(/\s+/g, " ")
                    .trim();

                const handler_name =
                    buttons[text];

                if (!handler_name) {
                    return;
                }

                const cell =
                    filter_cells[index];

                if (!cell) {
                    return;
                }

                if (
                    cell.querySelector(
                        "[data-industry-formula-button='1']"
                    )
                ) {
                    return;
                }

                cell.innerHTML =
                    formula_button(
                        handler_name
                    );
            }
        );
    }


    function show_formula_dialog(
        title,
        formula,
        explanation
    ) {
        const dialog =
            new frappe.ui.Dialog({
                title: __(title),
                size: "large",
                fields: [
                    {
                        fieldtype: "HTML",
                        fieldname: "formula_html"
                    }
                ]
            });

        dialog.fields_dict
            .formula_html
            .$wrapper
            .html(`
                <div style="
                    padding:4px;
                ">
                    <div style="
                        background:#eff6ff;
                        border:1px solid #93c5fd;
                        border-radius:10px;
                        padding:18px;
                        margin-bottom:14px;
                    ">
                        <div style="
                            font-size:13px;
                            font-weight:700;
                            color:#1e3a8a;
                            margin-bottom:10px;
                        ">
                            Formula
                        </div>

                        <div style="
                            font-size:17px;
                            line-height:1.7;
                            font-weight:700;
                            color:#111827;
                        ">
                            ${formula}
                        </div>
                    </div>

                    <div style="
                        background:#f8fafc;
                        border:1px solid #d1d8dd;
                        border-radius:10px;
                        padding:16px;
                        line-height:1.6;
                    ">
                        ${explanation}
                    </div>
                </div>
            `);

        dialog.show();
    }


    window.show_industry_availability_formula =
        function() {
            show_formula_dialog(
                "Industry Availability %",
                `
                    MIN(
                        Working Hours + Startup/Fatigue,
                        Required Hours
                    )
                    <br>
                    ÷ Required Hours
                    <br>
                    × 100
                `,
                `
                    Availability is based on
                    <strong>Working Hours + Startup/Fatigue</strong>.

                    <br><br>

                    The available hours are capped at
                    <strong>Required Hours</strong>,
                    so Availability cannot exceed 100%.

                    <br><br>

                    Industry Required Hours =
                    <strong>24h per day</strong>.
                `
            );
        };


    window.show_industry_util_available_formula =
        function() {
            show_formula_dialog(
                "Industry Utilisation Available Hours",
                `
                    Calculated Available Hours =
                    <br>
                    MAX(
                        24h - PBM Total Downtime,
                        MIN(Working Hours, 24h)
                    )
                    <br><br>
                    If Calculated Available Hours &gt;= 18h:
                    <strong>Use 24h</strong>
                    <br>
                    If Calculated Available Hours &lt; 18h:
                    <strong>Use Calculated Available Hours</strong>
                `,
                `
                    If the machine was available for
                    <strong>18 hours or more</strong>,
                    Industry Utilisation uses the full
                    <strong>24 hours</strong>.

                    <br><br>

                    If actual calculated availability is
                    <strong>below 18 hours</strong>,
                    those available hours are used.

                    <br><br>

                    <strong>Example:</strong><br>
                    Work = 15h, PBM = 8h<br>
                    Available = MAX(24 - 8, 15) = 16h<br>
                    Denominator = <strong>16h</strong>.
                `
            );
        };


    window.show_industry_utilisation_formula =
        function() {
            show_formula_dialog(
                "Industry Utilisation %",
                `
                    Working Hours
                    <br>
                    ÷ Utilisation Available Hours
                    <br>
                    × 100
                `,
                `
                    <strong>
                        Working Hours / Utilisation Available Hours × 100
                    </strong>

                    <br><br>

                    If calculated available hours are
                    <strong>18h or more</strong>,
                    Utilisation Available Hours = <strong>24h</strong>.

                    <br><br>

                    If calculated available hours are
                    <strong>below 18h</strong>,
                    those calculated available hours are used.

                    <br><br>

                    Example: Work = 15h, PBM = 8h<br>
                    Available = 16h<br>
                    Utilisation = 15 / 16 × 100 =
                    <strong>93.75%</strong>.
                `
            );
        };


    // Literal formula references used for verification:
    //
    // MIN(Working Hours + Startup/Fatigue, Required Hours)
    //
    // MAX(24h - PBM Total Downtime, MIN(Working Hours, 24h))
    // If Calculated Available Hours >= 18h: use 24h
    // If Calculated Available Hours < 18h: use Calculated Available Hours
    //
    // Working Hours / Utilisation Available Hours × 100


    const report =
        frappe.query_reports[
            REPORT_NAME
        ];

    if (report) {
        const previous_after_render =
            report.after_datatable_render;

        report.after_datatable_render =
            function() {
                if (
                    typeof previous_after_render
                    === "function"
                ) {
                    previous_after_render.apply(
                        this,
                        arguments
                    );
                }

                setTimeout(
                    place_industry_formula_buttons,
                    0
                );
            };
    }


    // Handles refreshes/filter changes where the table DOM
    // is recreated after the report callback.
    const observer =
        new MutationObserver(
            function() {
                if (!is_industry_mode()) {
                    return;
                }

                setTimeout(
                    place_industry_formula_buttons,
                    0
                );
            }
        );

    observer.observe(
        document.body,
        {
            childList: true,
            subtree: true
        }
    );


    setTimeout(
        place_industry_formula_buttons,
        100
    );

    setTimeout(
        place_industry_formula_buttons,
        500
    );
})();
