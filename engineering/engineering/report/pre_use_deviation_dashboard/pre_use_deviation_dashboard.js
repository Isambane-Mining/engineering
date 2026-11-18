frappe.query_reports["Pre Use Deviation Dashboard"] = {
    onload: function(report) {
        report.page.wrapper.addClass("pre-use-deviation-header-wrap");





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
            return `<span class="pud-chip pud-chip--neutral pud-chip--w-${min_width}">${frappe.utils.escape_html(text || "")}</span>`;
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
                return `<span class="pud-chip pud-chip--warning pud-chip--w-72">Open</span>`;
            }

            if (status === "Closed") {
                return `<span class="pud-chip pud-chip--success pud-chip--w-72">Closed</span>`;
            }

            return gray_chip(status, 72);
        }

        if (column.fieldname === "operating_status_badge") {
            const status = (data.operating_status || "").trim();

            if (!status) {
                return "";
            }

            if (status.toLowerCase() === "working") {
                return `<span class="pud-chip pud-chip--info pud-chip--w-88">Working</span>`;
            }

            if (status.toLowerCase() === "pending incident report") {
                return `<span class="pud-chip pud-chip--warning pud-chip--w-182">Pending Incident report</span>`;
            }

            return gray_chip(status, 120);
        }

        if (column.fieldname === "completion_percentage_badge") {
            const pct = Math.round(Number(data.completion_percentage || 0));

            const variant = pct >= 100
                ? "success"
                : pct <= 0
                    ? "warning"
                    : "info";

            return `<span class="pud-chip pud-chip--${variant} pud-chip--w-64">${pct}%</span>`;
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