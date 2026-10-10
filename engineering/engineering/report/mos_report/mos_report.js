
const MOS_REPORT_LEGEND_HTML = `
    <div
        class="mos-report-legend"
        style="
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            align-items: center;
            margin: 8px 0 12px 0;
            padding: 10px 12px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background: var(--subtle-fg);
            font-size: 12px;
        "
    >
        <div style="font-weight: 700; margin-right: 6px;">
            Legend
        </div>

        <div style="display: flex; align-items: center; gap: 6px;">
            <span
                style="
                    display: inline-block;
                    width: 14px;
                    height: 14px;
                    border-radius: 3px;
                    background: #22c55e;
                    border: 1px solid rgba(0,0,0,0.08);
                "
            ></span>
            <span>Green (Colour) = Production Machine</span>
        </div>

        <div style="display: flex; align-items: center; gap: 6px;">
            <span
                style="
                    display: inline-block;
                    width: 14px;
                    height: 14px;
                    border-radius: 3px;
                    background: #f59e0b;
                    border: 1px solid rgba(0,0,0,0.08);
                "
            ></span>
            <span>Orange (Colour) = Standby / Swing Machine</span>
        </div>

        <div style="display: flex; align-items: center; gap: 6px;">
            <span
                style="
                    display: inline-block;
                    min-width: 28px;
                    text-align: center;
                    font-weight: 700;
                    color: #dc2626;
                    text-decoration: underline;
                "
            >N/A</span>
            <span>Duration (N/A) = Click on button</span>
        </div>
    </div>
`;

function render_mos_report_legend(report) {
    const active_report = report || frappe.query_report;

    if (
        !active_report
        || !active_report.page
        || !active_report.page.wrapper
    ) {
        return;
    }

    const $wrapper = $(active_report.page.wrapper);

    $wrapper.find(".mos-report-legend").remove();

    const $target = $wrapper.find(".report-wrapper");

    if ($target.length) {
        $target.first().prepend(MOS_REPORT_LEGEND_HTML);
        return;
    }

    const $fallback = $wrapper.find(".layout-main-section");

    if ($fallback.length) {
        $fallback.first().prepend(MOS_REPORT_LEGEND_HTML);
    }
}

const MOS_PLANNED_HOURS_WARNING_FORMATTER = function (
    value,
    row,
    column,
    data,
    default_formatter
) {
    const formatted = default_formatter(
        value,
        row,
        column,
        data
    );

    if (!data || !column || !column.fieldname) {
        return formatted;
    }

    const fieldname = column.fieldname;
    const column_label = String(
        column.label || ""
    ).trim().toLowerCase();

    if (data.mos_group_heading) {
        const is_machine_column =
            fieldname === "night_machine"
            || fieldname === "day_asset";

        if (!is_machine_column) {
            return "";
        }
    }

    if (
        fieldname === "night_machine"
        || fieldname === "day_asset"
    ) {
        const machine = String(
            value || ""
        ).trim();

        if (!machine) {
            return formatted;
        }

        /*
         * Dedicated category heading row.
         */
        if (data.mos_group_heading) {
            return `
                <div
                    style="
                        font-weight: 700;
                        font-size: 12px;
                        padding: 2px 5px;
                        white-space: nowrap;
                        color: var(--heading-color);
                    "
                >
                    ${frappe.utils.escape_html(machine)}
                </div>
            `;
        }

        const sequence = Number(
            data.mos_machine_sequence || 0
        );

        const machine_text =
            sequence > 0
                ? `${sequence}. ${machine}`
                : machine;

        const machine_status = String(
            data.machine_plan_status || ""
        ).toLowerCase();

        let background = "";
        let foreground = "";
        let tooltip = "";

        if (machine_status === "production") {
            background = "#22c55e";
            foreground = "#ffffff";
            tooltip = "Production Machine";
        } else if (
            machine_status === "standby"
        ) {
            background = "#f59e0b";
            foreground = "#ffffff";
            tooltip = "Standby / Swing Machine";
        }

        const colour_style = background
            ? `
                background-color: ${background};
                color: ${foreground};
            `
            : `
                color: var(--text-color);
            `;

        return `
            <span
                title="${
                    frappe.utils.escape_html(
                        tooltip
                    )
                }"
                style="
                    display: block;
                    width: 100%;
                    box-sizing: border-box;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-weight: 600;
                    white-space: nowrap;
                    ${colour_style}
                "
            >
                ${frappe.utils.escape_html(
                    machine_text
                )}
            </span>
        `;
    }

    const warning_map = {
        night_operating_hours: {
            planned_field: "night_planned_available_hours",
            type: "hours"
        },
        day_operating_hours: {
            planned_field: "day_planned_available_hours",
            type: "hours"
        },
        night_engineering_duration: {
            planned_field: "night_planned_available_hours",
            type: "engineering"
        },
        day_engineering_duration: {
            planned_field: "day_planned_available_hours",
            type: "engineering"
        }
    };

    const warning = warning_map[fieldname];

    if (!warning) {
        return formatted;
    }

    let validation_actual = Number(
        data[fieldname] || 0
    );

    if (warning.type === "engineering") {
        const captured_hours_field =
            fieldname === "night_engineering_duration"
                ? "night_engineering_captured_hours"
                : "day_engineering_captured_hours";

        validation_actual = Number(
            data[captured_hours_field] || 0
        );
    }

    const planned = Number(
        data[warning.planned_field] || 0
    );

    if (
        !planned
        || validation_actual <= planned
    ) {
        return formatted;
    }

    const planned_display = Number.isInteger(planned)
        ? planned.toFixed(0)
        : planned.toFixed(2);

    let popup_lines = [];

    if (warning.type === "engineering") {
        popup_lines.push(
            "Downtime/planned maintenance (engineering)"
        );

        popup_lines.push(
            `more than ${planned_display} planned hours.`
        );

        const reason_field =
            fieldname === "night_engineering_duration"
                ? "night_engineering_captured_reason"
                : "day_engineering_captured_reason";

        const raw_reasons = String(
            data[reason_field] || ""
        ).trim();

        if (raw_reasons) {
            popup_lines.push("");

            raw_reasons
                .split("|")
                .map((item) => item.trim())
                .filter(Boolean)
                .forEach((item) => {
                    const display_item = item.replace(
                        /\(([^()]*)\)\s*$/,
                        "{$1}"
                    );

                    popup_lines.push(display_item);
                });
        }
    } else {
        popup_lines.push(
            `Hours more than ${planned_display} Planned hours.`
        );
    }

    const popup_html = popup_lines
        .map((line) => {
            if (!line) {
                return "<br>";
            }

            return frappe.utils.escape_html(line);
        })
        .join("<br>");

    const encoded_popup = encodeURIComponent(
        popup_html
    );

    return `
        <a
            href="#"
            class="text-danger"
            style="
                font-weight: 600;
                text-decoration: underline;
                cursor: pointer;
            "
            title="Click to view validation warning"
            onclick="
                frappe.msgprint({
                    title: 'MOS Validation Warning',
                    indicator: 'red',
                    message: decodeURIComponent(
                        '${encoded_popup}'
                    )
                });
                return false;
            "
        >
            N/A
        </a>
    `;
};

frappe.query_reports["MOS Report"] = {
    formatter: MOS_PLANNED_HOURS_WARNING_FORMATTER,

    refresh: function (report) {
        setTimeout(() => {
            render_mos_report_legend(report);
        }, 0);
    },

    after_datatable_render: function () {
        setTimeout(() => {
            render_mos_report_legend(frappe.query_report);
        }, 0);
    },

    mos_category_map: {},

    onload: function (report) {
        render_mos_report_legend(report);
        frappe.db.get_list("Asset Category", {
            filters: {
                custom_include_in_mos_report: 1
            },
            fields: [
                "name",
                "custom_mos_report_label"
            ],
            order_by: "name asc",
            limit: 100
        }).then((rows) => {
            const category_filter = report.get_filter("asset_category");

            if (!category_filter) {
                return;
            }

            const category_map = {};
            const options = ["All Machines"];

            (rows || []).forEach((row) => {
                if (!row.custom_mos_report_label) {
                    return;
                }

                options.push(row.custom_mos_report_label);
                category_map[row.custom_mos_report_label] = row.name;
            });

            frappe.query_reports["MOS Report"].mos_category_map =
                category_map;

            category_filter.df.options = options.join("\n");
            category_filter.refresh();

            const current_value = category_filter.get_value();

            if (!current_value || !options.includes(current_value)) {
                category_filter.set_value("All Machines");
            }
        });
    },

    filters: [
        {
            fieldname: "site",
            label: __("Site"),
            fieldtype: "Link",
            options: "Location"
        },
        {
            fieldname: "from_date",
            label: __("Start Date"),
            fieldtype: "Date"
        },
        {
            fieldname: "to_date",
            label: __("End Date"),
            fieldtype: "Date"
        },
        {
            fieldname: "shift",
            label: __("Shift"),
            fieldtype: "MultiSelectList",

            get_data: function (txt) {
                return frappe.db.get_link_options(
                    "Shift Type",
                    txt
                );
            }
        },
        {
            fieldname: "asset_category",
            label: __("Category"),
            fieldtype: "Select",
            options: "All Machines",
            default: "All Machines",
            on_change: function () {
                frappe.query_report.set_filter_value("asset", "");
                frappe.query_report.refresh();
            }
        },
        {
            fieldname: "asset",
            label: __("Asset"),
            fieldtype: "Link",
            options: "Asset",

            get_query: function () {
                const filters = {};

                const site =
                    frappe.query_report.get_filter_value("site");

                const selected_category =
                    frappe.query_report.get_filter_value(
                        "asset_category"
                    );

                const category_map =
                    frappe.query_reports["MOS Report"]
                        .mos_category_map || {};

                if (site) {
                    filters.location = site;
                }

                if (
                    selected_category &&
                    selected_category !== "All Machines" &&
                    category_map[selected_category]
                ) {
                    filters.asset_category =
                        category_map[selected_category];
                }

                return {
                    filters: filters
                };
            }
        }
    ]
};
