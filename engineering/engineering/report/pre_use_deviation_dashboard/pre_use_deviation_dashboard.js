frappe.query_reports["Pre Use Deviation Dashboard"] = {
    onload: function(report) {
        // PRE USE DASHBOARD HEADER WRAP START
        report.page.wrapper.addClass(
            "pre-use-deviation-header-wrap"
        );

        if (!document.getElementById(
            "pre-use-deviation-header-wrap-style"
        )) {
            const headerStyle = document.createElement("style");
            headerStyle.id =
                "pre-use-deviation-header-wrap-style";

            headerStyle.textContent = `
                .pre-use-deviation-header-wrap .dt-header {
                    height: 64px !important;
                    min-height: 64px !important;
                }

                .pre-use-deviation-header-wrap .dt-header .dt-row {
                    height: 64px !important;
                    min-height: 64px !important;
                }

                .pre-use-deviation-header-wrap .dt-header .dt-cell {
                    height: 64px !important;
                    min-height: 64px !important;
                    box-sizing: border-box !important;
                }

                .pre-use-deviation-header-wrap .dt-header .dt-cell__content {
                    white-space: normal !important;
                    overflow-wrap: break-word !important;
                    text-overflow: clip !important;
                    line-height: 18px !important;
                    height: auto !important;
                    max-height: none !important;
                    text-align: center !important;
                    padding: 8px 4px !important;
                    box-sizing: border-box !important;
                }
            `;

            document.head.appendChild(headerStyle);
        }
        // PRE USE DASHBOARD HEADER WRAP END

        if (!document.getElementById("pre-use-deviation-dashboard-style")) {
            const style = document.createElement("style");
            style.id = "pre-use-deviation-dashboard-style";
            style.innerHTML = `
                .query-report .dt-header .dt-cell__content,
                .query-report .dt-cell__content--header,
                .query-report .dt-header .dt-cell {
                    font-weight: 700 !important;
                    color: #000000 !important;
                }
            `;
            document.head.appendChild(style);
        }



        frappe.call({
            method: "engineering.engineering.report.pre_use_deviation_dashboard.pre_use_deviation_dashboard.get_site_options",
            callback: function(r) {
                const site_filter = report.get_filter("site");
                if (site_filter) {
                    const options = (
                        r.message || "All Sites"
                    ).split("\n").filter(Boolean);

                    const default_site = (
                        options.length === 2 &&
                        options[0] === "All Sites"
                    ) ? options[1] : "All Sites";

                    site_filter.df.options = options.join("\n");
                    site_filter.df.default = default_site;
                    site_filter.refresh();
                    site_filter.set_input(default_site);
                }
            }
        });

        frappe.call({
            method: "engineering.engineering.report.pre_use_deviation_dashboard.pre_use_deviation_dashboard.get_operating_status_options",
            callback: function(r) {
                const status_filter = report.get_filter("operating_status");
                if (status_filter) {
                    status_filter.df.options = r.message || "All Statuses";
                    status_filter.df.default = "All Statuses";
                    status_filter.refresh();
                    status_filter.set_input("All Statuses");
                }
            }
        });
    },

    formatter: function(value, row, column, data, default_formatter) {
        if (!data) {
            return default_formatter(value, row, column, data);
        }

        const gray_chip = function(text, min_width = 70) {
            return `<span style="
                display:inline-block;
                min-width:${min_width}px;
                text-align:center;
                padding:4px 10px;
                border-radius:14px;
                background:#f3f4f6;
                color:#111827;
                font-weight:700;
                border:1px solid #d1d5db;
                white-space:nowrap;
            ">${frappe.utils.escape_html(text || "")}</span>`;
        };

        if (column.fieldname === "report_datetime_display") {
            return gray_chip(data.report_datetime_display || "", 120);
        }

        if (column.fieldname === "site") {
            return gray_chip(data.site || "", 90);
        }

        if (column.fieldname === "fleet_number") {
            return gray_chip(data.fleet_number || "", 72);
        }

        if (column.fieldname === "reported_by_name_and_surname") {
            return gray_chip(data.reported_by_name_and_surname || "", 170);
        }

        if (column.fieldname === "deviation_details") {
            return gray_chip(data.deviation_details || "", 100);
        }

        if (column.fieldname === "resolution_summary") {
            return gray_chip(data.resolution_summary || "", 110);
        }

        if (column.fieldname === "actioned_by_name_and_surname") {
            return gray_chip(data.actioned_by_name_and_surname || "", 170);
        }

        if (column.fieldname === "action") {
            return gray_chip(data.action || "", 140);
        }

        if (column.fieldname === "action_date_and_time_display") {
            return gray_chip(data.action_date_and_time_display || "", 120);
        }

        if (column.fieldname === "action_status_badge") {
            const status = (data.action_status || "").trim();

            if (status === "Open") {
                return `<span style="
                    display:inline-block;
                    min-width:72px;
                    text-align:center;
                    padding:4px 10px;
                    border-radius:14px;
                    background:#fff7ed;
                    color:#c2410c;
                    font-weight:700;
                    border:1px solid #fdba74;
                    white-space:nowrap;
                ">Open</span>`;
            }

            if (status === "Closed") {
                return `<span style="
                    display:inline-block;
                    min-width:72px;
                    text-align:center;
                    padding:4px 10px;
                    border-radius:14px;
                    background:#ecfdf5;
                    color:#15803d;
                    font-weight:700;
                    border:1px solid #86efac;
                    white-space:nowrap;
                ">Closed</span>`;
            }

            return gray_chip(status, 72);
        }

        if (column.fieldname === "operating_status_badge") {
            const status = (data.operating_status || "").trim();

            if (!status) {
                return "";
            }

            if (status.toLowerCase() === "working") {
                return `<span style="
                    display:inline-block;
                    min-width:88px;
                    text-align:center;
                    padding:4px 10px;
                    border-radius:14px;
                    background:#eff6ff;
                    color:#1d4ed8;
                    font-weight:700;
                    border:1px solid #93c5fd;
                    white-space:nowrap;
                ">Working</span>`;
            }

            if (status.toLowerCase() === "pending incident report") {
                return `<span style="
                    display:inline-block;
                    min-width:182px;
                    text-align:center;
                    padding:4px 10px;
                    border-radius:14px;
                    background:#fff7ed;
                    color:#c2410c;
                    font-weight:700;
                    border:1px solid #fdba74;
                    white-space:nowrap;
                ">Pending Incident report</span>`;
            }

            return gray_chip(status, 120);
        }

        if (column.fieldname === "completion_percentage_badge") {
            const pct = Math.round(Number(data.completion_percentage || 0));

            let bg = "#eff6ff";
            let color = "#1d4ed8";
            let border = "#93c5fd";

            if (pct >= 100) {
                bg = "#ecfdf5";
                color = "#15803d";
                border = "#86efac";
            } else if (pct <= 0) {
                bg = "#fff7ed";
                color = "#c2410c";
                border = "#fdba74";
            }

            return `<span style="
                display:inline-block;
                min-width:64px;
                text-align:center;
                padding:4px 10px;
                border-radius:14px;
                background:${bg};
                color:${color};
                font-weight:700;
                border:1px solid ${border};
                white-space:nowrap;
            ">${pct}%</span>`;
        }

        return default_formatter(value, row, column, data);
    },

    filters: [
        {
            fieldname: "site",
            label: "Site",
            fieldtype: "Select",
            options: "All Sites",
            default: "All Sites"
        },
        {
            fieldname: "month",
            label: "Month",
            fieldtype: "Select",
            options: [
                "",
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December"
            ].join("\n"),
            default: ""
        },
        {
            fieldname: "year",
            label: "Year",
            fieldtype: "Int",
            default: new Date().getFullYear()
        },
        {
            fieldname: "fleet_number",
            label: "Fleet",
            fieldtype: "Data",
            default: ""
        },
        {
            fieldname: "operating_status",
            label: "Operating Status",
            fieldtype: "Select",
            options: "All Statuses",
            default: "All Statuses"
        },
        {
            fieldname: "action_status",
            label: "Status",
            fieldtype: "Select",
            options: "\nOpen\nClosed",
            default: ""
        }
    ]
};