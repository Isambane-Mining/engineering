function format_dashboard_hours(value) {
    const total_minutes = Math.round(
        Number(value || 0) * 60
    );

    const hours = Math.floor(
        total_minutes / 60
    );

    const minutes = total_minutes % 60;

    if (hours > 0 && minutes > 0) {
        return `${hours}h ${minutes}m`;
    }

    if (hours > 0) {
        return `${hours}h`;
    }

    return `${minutes}m`;
}



frappe.pages["daily-availability-and-utilization-dashboard"].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Daily A&U Engine Dashboard"),
        single_column: true
    });

    wrapper.daily_availability_dashboard = new DailyAvailabilityAndUtilizationDashboardPage(wrapper, page);
};

class DailyAvailabilityAndUtilizationDashboardPage {
    constructor(wrapper, page) {
        this.wrapper = $(wrapper);
        this.page = page;
        this.method = "engineering.engineering.page.daily_availability_and_utilization_dashboard.daily_availability_and_utilization_dashboard.get_dashboard_html";
        this.pdf_method = "engineering.engineering.page.daily_availability_and_utilization_dashboard.daily_availability_and_utilization_dashboard.download_dashboard_pdf";
        this.downtime_method = "engineering.engineering.page.daily_availability_and_utilization_dashboard.daily_availability_and_utilization_dashboard.get_machine_downtime_details";
        this.loading = false;
        this.initializing = true;
        this.active_dashboard_tab = "hours";
        this.last_site_storage_key = `daily_availability_and_utilization_dashboard_last_site:${frappe.session.user || "Guest"}`;
        this.make();
    }

    async make() {
        this.add_mobile_styles();
        this.make_filters();
        this.make_body();
        this.make_buttons();
        await this.set_defaults();
    }

    add_mobile_styles() {
        if ($("#daily-availability-mobile-styles").length) {
            return;
        }

        $("head").append(`
            <style id="daily-availability-mobile-styles">
                .daily-availability-clickable-bar {
                    cursor: pointer;
                }

                .daily-availability-clickable-bar:hover {
                    filter: brightness(0.9);
                }

                /* Tiny bars keep their exact value in the native hover tooltip.
                   Hiding the cramped label avoids clipping and adjacent-bar overlap. */
                .daily-availability-page .isd-bar.util[data-utilisation-small="true"] > span {
                    display: none !important;
                }

                .daily-downtime-list {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(260px, 1fr));
                    gap: 10px;
                    max-height: 60vh;
                    overflow-y: auto;
                    padding: 4px;
                }

                .daily-downtime-item {
                    position: relative;
                    border: 1px solid #d1d5db;
                    border-radius: 10px;
                    padding: 12px;
                    background: #ffffff;
                    cursor: pointer;
                }

                .daily-downtime-item:hover,
                .daily-downtime-item.is-open {
                    border-color: #1d4ed8;
                    background: #eff6ff;
                }

                .daily-downtime-summary {
                    font-size: 13px;
                    line-height: 1.5;
                }

                .daily-downtime-summary strong {
                    color: #111827;
                }

                .daily-downtime-details {
                    display: none;
                    margin-top: 10px;
                    padding-top: 10px;
                    border-top: 1px solid #bfdbfe;
                    font-size: 12px;
                    line-height: 1.6;
                    color: #374151;
                }

                .daily-downtime-item:hover .daily-downtime-details,
                .daily-downtime-item.is-open .daily-downtime-details {
                    display: block;
                }

                @media (max-width: 768px) {
                    .daily-availability-and-utilization-dashboard-wrapper .page-form {
                        display: grid !important;
                        grid-template-columns: 1fr !important;
                        gap: 8px !important;
                    }

                    .daily-availability-and-utilization-dashboard-wrapper .page-form .form-group {
                        width: 100% !important;
                        min-width: 0 !important;
                    }

                    .daily-availability-page {
                        padding: 0 !important;
                    }

                    .daily-availability-page .isd-metrics {
                        display: grid !important;
                        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
                        gap: 8px !important;
                    }

                    .daily-availability-page .isd-metric {
                        width: 100% !important;
                        min-width: 0 !important;
                        margin: 0 !important;
                    }

                    .daily-availability-page .isd-contentrow {
                        display: block !important;
                    }

                    .daily-availability-page .isd-chart-stack {
                        width: 100% !important;
                        overflow-x: auto !important;
                        -webkit-overflow-scrolling: touch;
                    }

                    .daily-availability-page .isd-chart-section {
                        overflow-x: auto !important;
                    }

                    .daily-availability-page .isd-side {
                        width: 100% !important;
                        padding: 10px !important;
                    }

                    .daily-downtime-list {
                        grid-template-columns: 1fr;
                        max-height: 65vh;
                    }
                }
            </style>
        `);

        this.wrapper.addClass("daily-availability-and-utilization-dashboard-wrapper");
    }

    make_filters() {
        this.start_date = this.page.add_field({
            fieldname: "start_date",
            label: __("Start Date"),
            fieldtype: "Date",
            reqd: 1,
            change: () => this.load_dashboard()
        });

        this.end_date = this.page.add_field({
            fieldname: "end_date",
            label: __("End Date"),
            fieldtype: "Date",
            reqd: 1,
            change: () => this.load_dashboard()
        });

        this.location = this.page.add_field({
            fieldname: "location",
            label: __("Site"),
            fieldtype: "Link",
            options: "Location",
            reqd: 1,
            change: () => {
                if (this.initializing) {
                    return;
                }

                this.set_production_dates_from_site();
            }
        });

        this.summary_type = this.page.add_field({
            fieldname: "summary_type",
            label: __("Summary Type"),
            fieldtype: "Select",
            options: [
                "Daily Summary",
                "Average Per Machine",
                "Weekly Summary",
                "Monthly Summary"
            ].join("\n"),
            default: "Average Per Machine",
            reqd: 1,
            change: () => this.load_dashboard()
        });

        this.machine_scope = this.page.add_field({
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
            change: () => this.load_dashboard()
        });

        this.asset_ownership = this.page.add_field({
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
            change: () => this.load_dashboard()
        });

        this.au_target_filter = this.page.add_field({
            fieldname: "au_target_filter",
            label: __("A & U Target"),
            fieldtype: "Select",
            options: [
                "100% A & U",
                "85% A & U"
            ].join("\n"),
            default: "85% A & U",
            reqd: 1,
            change: () => this.load_dashboard()
        });


        this.hours_display = this.page.add_field({
            fieldname: "hours_display",
            label: __("Hours Display"),
            fieldtype: "Select",
            options: [
                "Hours Average per Category",
                "Hours per Asset"
            ].join("\n"),
            default: "Hours Average per Category",
            change: () => {
                if (!this.initializing && this.active_dashboard_tab === "hours") {
                    this.load_dashboard();
                }
            }
        });

        this.hours_asset = this.page.add_field({
            fieldname: "hours_asset",
            label: __("Asset"),
            fieldtype: "Link",
            options: "Asset",
            get_query: () => ({
                filters: {
                    location: this.location.get_value(),
                    docstatus: 1
                }
            }),
            change: () => {
                if (!this.initializing && this.active_dashboard_tab === "hours") {
                    this.load_dashboard();
                }
            }
        });

        this.hours_display.$wrapper.hide();
        this.hours_asset.$wrapper.hide();
    }

    make_body() {
        this.body = $(`
            <div class="daily-availability-page eng-dashboard eng-dashboard--daily-availability">
                <div class="daily-availability-loading text-muted" style="display:none; padding: 12px 0;">
                    Loading dashboard...
                </div>
                <div class="daily-availability-error" style="display:none;"></div>
                <div class="daily-availability-and-utilization-dashboard-body"></div>
            </div>
        `).appendTo(this.page.main);
    }

    make_buttons() {
        this.page.set_primary_action(__("Refresh"), () => {
            this.load_dashboard();
        });

        this.page.add_inner_button(__("Download PDF"), () => {
            this.download_pdf();
        });
    }

    async set_defaults() {
        this.initializing = true;

        await this.start_date.set_value(null);
        await this.end_date.set_value(null);
        await this.summary_type.set_value("Average Per Machine");
        await this.machine_scope.set_value(
            "Production + Swing/Spare Machines"
        );
        await this.asset_ownership.set_value(
            "Isambane & Excavo Assets"
        );
        await this.au_target_filter.set_value("85% A & U");
        await this.hours_display.set_value("Hours Average per Category");
        await this.hours_asset.set_value(null);

        let saved_site = "";

        try {
            saved_site = localStorage.getItem(
                this.last_site_storage_key
            ) || "";
        } catch (error) {
            saved_site = "";
        }

        if (saved_site) {
            await this.location.set_value(saved_site);
            await this.set_production_dates_from_site();
        } else {
            this.body.find(
                ".daily-availability-and-utilization-dashboard-body"
            ).html(`
                <div class="frappe-card" style="padding: 18px;">
                    Please select Site. The latest Monthly Production Planning dates will load automatically.
                </div>
            `);
        }

        this.initializing = false;

        if (
            this.location.get_value() &&
            this.start_date.get_value() &&
            this.end_date.get_value()
        ) {
            this.load_dashboard();
        }
    }

    async set_production_dates_from_site() {
        const site = this.location.get_value();

        await this.start_date.set_value(null);
        await this.end_date.set_value(null);

        if (!site) {
            return;
        }

        try {
            localStorage.setItem(
                this.last_site_storage_key,
                site
            );
        } catch (error) {
            // Continue even if browser storage is unavailable.
        }

        const records = await frappe.db.get_list(
            "Monthly Production Planning",
            {
                filters: {
                    location: site
                },
                fields: [
                    "name",
                    "location",
                    "prod_month_start_date",
                    "prod_month_end_date"
                ],
                order_by: "prod_month_end_date desc",
                limit: 1
            }
        );

        if (!records.length) {
            frappe.msgprint(
                __("No Monthly Production Planning record was found for {0}.", [site])
            );
            return;
        }

        const production_plan = records[0];

        if (
            !production_plan.prod_month_start_date ||
            !production_plan.prod_month_end_date
        ) {
            frappe.msgprint(
                __("The latest Monthly Production Planning record does not have both production dates.")
            );
            return;
        }

        await this.start_date.set_value(
            production_plan.prod_month_start_date
        );

        const today = frappe.datetime.get_today();

        const effective_end_date =
            production_plan.prod_month_end_date > today
                ? today
                : production_plan.prod_month_end_date;

        await this.end_date.set_value(
            effective_end_date
        );

        if (!this.initializing) {
            this.load_dashboard();
        }
    }

    get_values() {
        return {
            start_date: this.start_date.get_value(),
            end_date: this.end_date.get_value(),
            location: this.location.get_value(),
            site: this.location.get_value(),
            summary_type: this.summary_type.get_value() || "Average Per Machine",
            machine_scope: this.machine_scope.get_value() || "Production + Swing/Spare Machines",
            asset_ownership: this.asset_ownership.get_value() || "Isambane & Excavo Assets",
            au_target_filter: this.au_target_filter.get_value() || "85% A & U",
            hours_display: this.hours_display.get_value() || "Hours Average per Category",
            hours_asset: this.hours_asset.get_value() || ""
        };
    }

    validate(values) {
        if (!values.start_date || !values.end_date || !values.location) {
            this.body.find(".daily-availability-and-utilization-dashboard-body").html(`
                <div class="frappe-card" style="padding: 18px;">
                    Please select Start Date, End Date and Site.
                </div>
            `);
            return false;
        }

        return true;
    }

    load_dashboard() {
        if (this.initializing) {
            return;
        }

        const values = this.get_values();

        if (!this.validate(values)) {
            return;
        }

        // Keep the A&U Engine aligned with the date range selected
        // on the Daily A&U Engine Dashboard.
        try {
            localStorage.setItem(
                "daily_au_engine_dashboard_from_date",
                values.start_date || ""
            );

            localStorage.setItem(
                "daily_au_engine_dashboard_to_date",
                values.end_date || ""
            );
        } catch (error) {
            // Continue normally when browser storage is unavailable.
        }

        if (this.loading) {
            this.pending_reload = true;
            return;
        }

        this.loading = true;
        this.pending_reload = false;

        this.body.find(".daily-availability-error").hide().empty();

        this.body.find(
            ".daily-availability-and-utilization-dashboard-body"
        ).html(`
            <div class="frappe-card"
                 style="
                    padding: 32px;
                    text-align: center;
                    min-height: 140px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    gap: 10px;
                 ">
                <div style="font-size:16px;font-weight:700;">
                    Loading Availability & Utilisation...
                </div>

                <div class="text-muted" style="font-size:12px;">
                    ${frappe.utils.escape_html(values.location)}
                    |
                    ${frappe.utils.escape_html(values.start_date)}
                    to
                    ${frappe.utils.escape_html(values.end_date)}
                </div>
            </div>
        `);

        this.body.find(".daily-availability-loading").hide();

        const finish_request = () => {
            this.loading = false;

            if (this.pending_reload) {
                this.pending_reload = false;

                window.setTimeout(() => {
                    this.load_dashboard();
                }, 50);
            }
        };

        frappe.call({
            method: this.method,
            args: values,
            freeze: false,

            callback: (r) => {
                const html = r.message || "";

                if (!html) {
                    this.body.find(
                        ".daily-availability-and-utilization-dashboard-body"
                    ).html(`
                        <div class="frappe-card" style="padding:18px;">
                            No dashboard data returned.
                        </div>
                    `);

                    finish_request();
                    return;
                }

                this.body.find(
                    ".daily-availability-and-utilization-dashboard-body"
                ).html(html);

                this.bind_dashboard_actions();
                this.body
                    .find(".daily-dashboard-tab-button[data-tab=\"" + (this.active_dashboard_tab || "hours") + "\"]")
                    .trigger("click");

                finish_request();
            },

            error: () => {
                this.body.find(
                    ".daily-availability-and-utilization-dashboard-body"
                ).empty();

                this.body.find(".daily-availability-error")
                    .show()
                    .html(`
                        <div class="frappe-card"
                             style="padding:18px;color:#b42318;">
                            Could not load Daily A&U Engine Dashboard.
                            Please check the filters and try again.
                        </div>
                    `);

                finish_request();
            }
        });
    }


    bind_dashboard_actions() {
        this.body
            .off("click.daily_dashboard_tab", ".daily-dashboard-tab-button")
            .on("click.daily_dashboard_tab", ".daily-dashboard-tab-button", (event) => {
                const tab = $(event.currentTarget).data("tab");
                this.active_dashboard_tab = tab;
                this.hours_display.$wrapper.toggle(tab === "hours");
                this.hours_asset.$wrapper.toggle(tab === "hours");
                this.body.find(".daily-dashboard-tab-button").removeClass("btn-primary").addClass("btn-default");
                $(event.currentTarget).removeClass("btn-default").addClass("btn-primary");
                this.body.find(".daily-dashboard-tab-panel").hide();
                this.body.find(`.daily-dashboard-tab-panel[data-panel="${tab}"]`).show();
            });

        this.body
            .off("click.daily_availability_bar", ".daily-availability-clickable-bar")
            .on(
                "click.daily_availability_bar",
                ".daily-availability-clickable-bar",
                (event) => {
                    const machine = $(event.currentTarget).data("machine") || "";

                    if (machine) {
                        this.open_machine_downtime_popup(machine);
                    }
                }
            );
    }


    open_machine_downtime_popup(machine) {
        const values = this.get_values();

        const format_percent = (value) => {
            return `${Number(value || 0).toFixed(1)}%`;
        };

        const format_popup_datetime = (value) => {
            if (!value) {
                return "Still Open";
            }

            if (typeof moment !== "undefined") {
                return moment(value).format(
                    "D MMMM YYYY HH:mm"
                );
            }

            return String(value);
        };

        frappe.call({
            method: this.downtime_method,
            args: {
                machine: machine,
                location: values.location,
                start_date: values.start_date,
                end_date: values.end_date,
                au_target_filter: values.au_target_filter
            },
            freeze: true,
            freeze_message: __("Loading availability details..."),
            callback: (r) => {
                const response = r.message || {};
                const rows = response.rows || [];

                const effective_end_date =
                    response.effective_end_date ||
                    values.end_date;

                const dialog = new frappe.ui.Dialog({
                    title: __(
                        "{0} Availability & Utilisation Details",
                        [machine]
                    ),
                    size: "extra-large"
                });

                let event_cards = "";

                if (!rows.length) {
                    event_cards = `
                        <div style="
                            padding:18px;
                            border:1px solid #dbe3ee;
                            border-radius:10px;
                            background:#ffffff;
                            color:#64748b;
                        ">
                            No breakdown records found.
                        </div>
                    `;
                }

                rows.forEach((row) => {
                    const calculation = row.calculation || {};

                    const status = frappe.utils.escape_html(
                        row.status || ""
                    );

                    const reason = frappe.utils.escape_html(
                        row.reason || "No reason captured"
                    );

                    const resolution = frappe.utils.escape_html(
                        row.resolution || "-"
                    );

                    const downtime_type = frappe.utils.escape_html(
                        row.downtime_type || ""
                    );

                    const start = frappe.utils.escape_html(
                        row.start || ""
                    );

                    const resolved = frappe.utils.escape_html(
                        row.resolved || "Still Open"
                    );

                    const shift = frappe.utils.escape_html(
                        calculation.shift || "Not available"
                    );

                    const raw_time = format_dashboard_hours(
                        calculation.raw_downtime || 0
                    );

                    const startup_time = format_dashboard_hours(
                        calculation.startup_excluded || 0
                    );

                    const fatigue_time = format_dashboard_hours(
                        calculation.fatigue_excluded || 0
                    );

                    const excluded_time = format_dashboard_hours(
                        calculation.total_excluded || 0
                    );

                    const au_time = format_dashboard_hours(
                        calculation.total_downtime || 0
                    );

                    const required_value = Number(
                        calculation.required_hours || 0
                    );

                    const work_value = Number(
                        calculation.work_hours || 0
                    );

                    const event_downtime_value = Number(
                        calculation.total_downtime || 0
                    );

                    const available_value = Number(
                        calculation.available_hours || 0
                    );

                    const required = format_dashboard_hours(
                        required_value
                    );

                    const event_downtime = format_dashboard_hours(
                        event_downtime_value
                    );

                    const available = format_dashboard_hours(
                        available_value
                    );

                    const raw_availability = format_percent(
                        calculation.raw_availability
                    );

                    const raw_utilisation = format_percent(
                        calculation.raw_utilisation
                    );

                    const displayed_availability = format_percent(
                        calculation.displayed_availability
                    );

                    const displayed_utilisation = format_percent(
                        calculation.displayed_utilisation
                    );

                    const target_label = frappe.utils.escape_html(
                        calculation.target_label ||
                        values.au_target_filter ||
                        "100% A & U"
                    );

                    const affected_shift_count = Number(
                        calculation.affected_shift_count || 0
                    );

                    const calculation_start =
                        frappe.utils.escape_html(
                            format_popup_datetime(row.start)
                        );

                    const calculation_end =
                        frappe.utils.escape_html(
                            format_popup_datetime(row.resolved)
                        );

                    event_cards += `
                        <div class="daily-downtime-item">
                            <div class="daily-downtime-summary">
                                <div style="
                                    display:flex;
                                    justify-content:space-between;
                                    align-items:center;
                                    gap:10px;
                                    margin-bottom:8px;
                                ">
                                    <span style="
                                        background:#dbeafe;
                                        border:1px solid #60a5fa;
                                        color:#1d4ed8;
                                        border-radius:5px;
                                        padding:3px 8px;
                                        font-weight:800;
                                        font-size:11px;
                                    ">
                                        ${status}
                                    </span>

                                    <span style="
                                        color:#475569;
                                        font-size:11px;
                                        font-weight:700;
                                    ">
                                        ${downtime_type}
                                    </span>
                                </div>

                                <div style="
                                    font-weight:800;
                                    color:#172033;
                                    margin-bottom:8px;
                                ">
                                    ${reason}
                                </div>

                                <div style="
                                    display:grid;
                                    grid-template-columns:
                                        repeat(3, minmax(0, 1fr));
                                    gap:6px;
                                    font-size:11px;
                                    color:#475569;
                                    margin-bottom:8px;
                                ">
                                <div>
                                    <strong>Duration:</strong>
                                    <span style="
                                        color:#dc2626;
                                        font-weight:800;
                                    ">
                                        ${raw_time}
                                    </span>
                                </div>

                                    <div>
                                        <strong>Type:</strong>
                                        ${downtime_type}
                                    </div>

                                    <div>
                                        <strong>Shift:</strong>
                                        ${shift}
                                    </div>
                                </div>

                                <div style="
                                    font-size:11px;
                                    line-height:1.7;
                                    color:#334155;
                                ">
                                    <div>
                                        <strong>Start:</strong>
                                        ${start}
                                    </div>

                                    <div>
                                        <strong>
                                            Back in Production:
                                        </strong>
                                        ${resolved}
                                    </div>

                                    <div>
                                        <strong>Resolution:</strong>
                                        ${resolution}
                                    </div>
                                </div>

                                <div style="
                                    margin-top:8px;
                                    color:#1d4ed8;
                                    font-size:10px;
                                    font-weight:800;
                                ">
                                    Hover to view A&amp;U calculation
                                </div>
                            </div>

                            <div class="daily-downtime-details">
                                <div style="
                                    margin-bottom:10px;
                                    padding:8px 10px;
                                    border:1px solid #bfdbfe;
                                    border-radius:7px;
                                    background:#eff6ff;
                                    color:#1d4ed8;
                                    font-size:11px;
                                    font-weight:800;
                                ">
                                    A&amp;U calculation for
                                    ${affected_shift_count}
                                    affected
                                    ${affected_shift_count === 1
                                        ? "shift"
                                        : "shifts"}
                                    from
                                    ${calculation_start}
                                    to
                                    ${calculation_end}
                                </div>

                                <div style="
                                    display:grid;
                                    grid-template-columns:
                                        repeat(3, minmax(0, 1fr));
                                    border:1px solid #dbe3ee;
                                    border-radius:7px;
                                    overflow:hidden;
                                    text-align:center;
                                    font-size:11px;
                                ">
                                    <div style="
                                        padding:8px;
                                        background:#fff7ed;
                                        color:#c2410c;
                                    ">
                                        <strong>Total Time</strong>
                                        <br>
                                        ${raw_time}
                                    </div>

                                    <div style="
                                        padding:8px;
                                        background:#fff1f2;
                                        color:#dc2626;
                                        border-left:
                                            1px solid #dbe3ee;
                                        border-right:
                                            1px solid #dbe3ee;
                                    ">
                                        <strong>
                                            Start-up + Fatigue
                                        </strong>
                                        <br>
                                        ${excluded_time}

                                        <div style="
                                            font-size:9px;
                                            margin-top:2px;
                                        ">
                                            ${startup_time}
                                            +
                                            ${fatigue_time}
                                        </div>
                                    </div>

                                    <div style="
                                        padding:8px;
                                        background:#f0fdf4;
                                        color:#15803d;
                                    ">
                                        <strong>A&amp;U Time</strong>
                                        <br>
                                        ${au_time}
                                    </div>
                                </div>

                                <div style="
                                    margin-top:10px;
                                    border:1px solid #bfdbfe;
                                    background:#eff6ff;
                                    border-radius:8px;
                                    padding:10px;
                                    line-height:1.8;
                                    color:#172033;
                                    font-size:11px;
                                ">
                                    <div>
                                        <strong>
                                            Available Hours
                                        </strong>
                                        =
                                        ${required}
                                        -
                                        ${event_downtime}
                                        =
                                        <strong>
                                            ${available}
                                        </strong>
                                    </div>

                                    <div>
                                        <strong>Availability</strong>
                                        =
                                        ${available_value.toFixed(2)}
                                        ÷
                                        ${required_value.toFixed(2)}
                                        × 100
                                        =
                                        <strong style="
                                            color:#15803d;
                                        ">
                                            ${raw_availability}
                                        </strong>
                                    </div>

                                    <div>
                                        <strong>Utilisation</strong>
                                        =
                                        ${work_value.toFixed(2)}
                                        ÷
                                        ${available_value.toFixed(2)}
                                        × 100
                                        =
                                        <strong style="
                                            color:#15803d;
                                        ">
                                            ${raw_utilisation}
                                        </strong>
                                    </div>

                                    <div style="
                                        margin-top:4px;
                                        color:#1d4ed8;
                                        font-weight:800;
                                    ">
                                        ${target_label}:
                                        ${displayed_availability}
                                        availability /
                                        ${displayed_utilisation}
                                        utilisation
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                });

                const html = `
                    <div style="
                        margin-bottom:12px;
                        color:#475569;
                        font-size:13px;
                    ">
                        ${frappe.utils.escape_html(
                            values.location || ""
                        )}
                        |
                        ${frappe.utils.escape_html(
                            values.start_date || ""
                        )}
                        to
                        ${frappe.utils.escape_html(
                            effective_end_date || ""
                        )}
                    </div>

                    <div class="daily-downtime-list">
                        ${event_cards}
                    </div>
                `;

                dialog.$body.html(html);

                dialog.$body
                    .off(
                        "click.daily_downtime_item",
                        ".daily-downtime-item"
                    )
                    .on(
                        "click.daily_downtime_item",
                        ".daily-downtime-item",
                        function() {
                            $(this).toggleClass("is-open");
                        }
                    );

                dialog.show();
            }
        });
    }




    download_pdf() {
        const values = this.get_values();

        values.summary_type = this.summary_type.get_value() || "Average Per Machine";
        values.machine_scope = this.machine_scope.get_value() || "Production + Swing/Spare Machines";
        values.au_target_filter = this.au_target_filter.get_value() || "85% A & U";
        values.location = this.location.get_value();
        values.site = this.location.get_value();

        // PDF_SELECTED_TAB_V1
        // Send the currently selected dashboard tab to the PDF endpoint.
        values.dashboard_tab = this.active_dashboard_tab || "hours";
        values.hours_display =
            this.hours_display.get_value() ||
            "Hours Average per Category";
        values.hours_asset =
            this.hours_asset.get_value() || "";

        if (!this.validate(values)) {
            return;
        }

        const query = $.param({
            start_date: values.start_date,
            end_date: values.end_date,
            location: values.location,
            site: values.site,
            summary_type: values.summary_type,
            machine_scope: values.machine_scope,
            asset_ownership: values.asset_ownership,
            au_target_filter: values.au_target_filter,
            dashboard_tab: values.dashboard_tab,
            hours_display: values.hours_display,
            hours_asset: values.hours_asset
        });

        const url = "/api/method/" + this.pdf_method + "?" + query;

        window.open(url, "_blank");
    }
}