frappe.pages["service-schedule-dashboard"].on_page_load = function (wrapper) {
    wrapper.service_schedule_page = new ServiceSchedulePage(wrapper);
};

frappe.pages["service-schedule-dashboard"].on_page_show = function (wrapper) {
    if (wrapper.service_schedule_page) wrapper.service_schedule_page.load();
};

class ServiceSchedulePage {
    constructor(wrapper) {
        this.wrapper = $(wrapper).addClass("service-schedule-page");
        this.page = frappe.ui.make_app_page({
            parent: wrapper, title: __("Service Schedule"), single_column: true
        });
        this.method = "engineering.engineering.doctype.service_schedule.service_schedule.";
        this.rows = [];
        this.scheduleName = null;
        this.status = "";
        this.sortKey = "fleet_number";
        this.sortDirection = 1;
        this.loading = false;
        this.requestToken = 0;
        this.build();
        this.initialize();
    }

    escape(value) {
        return $("<div>").text(value == null ? "" : String(value)).html();
    }

    monthLabel() {
        const [year, month] = (this.monthInput.val() || "").split("-").map(Number);
        if (!year || !month || month < 1 || month > 12) return "";
        return `${["January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"][month - 1]} ${year}`;
    }

    monthValue(label) {
        const [name, year] = String(label || "").split(" ");
        const index = ["January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"].indexOf(name);
        return index >= 0 && year ? `${year}-${String(index + 1).padStart(2, "0")}` : "";
    }

    build() {
this.page.main.html(`<div class="ss-filters">
            <div class="ss-site"></div>
            <div class="ss-month-field"><label>${__("Month")}</label><input class="ss-month" type="month"></div>
            <div class="ss-date"></div><div class="ss-status"></div>
            <div class="ss-interval"></div><div class="ss-search"></div>
        </div><div class="ss-kpis"></div><div class="ss-info"></div>
        <div class="ss-table-wrap"></div>`);
        this.site = frappe.ui.form.make_control({
            parent: this.page.main.find(".ss-site"), render_input: true,
            df: {fieldtype: "Link", options: "Location", fieldname: "site",
                label: __("Site"), onchange: () => this.load()}
        });
        this.date = frappe.ui.form.make_control({
            parent: this.page.main.find(".ss-date"), render_input: true,
            df: {fieldtype: "Date", fieldname: "snapshot_date", label: __("Date / snapshot"),
                onchange: () => { if (!this.settingDate) this.load(this.date.get_value()); }}
        });
        this.statusField = frappe.ui.form.make_control({
            parent: this.page.main.find(".ss-status"), render_input: true,
            df: {fieldtype: "Select", fieldname: "status", label: __("Status"),
                options: ["All statuses", "Overdue", "Due", "Due within 65 hours",
                    "Due within 260 hours", "No Service History", "Normal"].join("\n"),
                onchange: () => { this.status = this.statusField.get_value(); this.render(); }}
        });
        this.intervalField = frappe.ui.form.make_control({
            parent: this.page.main.find(".ss-interval"), render_input: true,
            df: {fieldtype: "Select", fieldname: "interval", label: __("Service interval"),
                options: ["All intervals", "250 Hours", "500 Hours", "750 Hours",
                    "1000 Hours", "2000 Hours"].join("\n"), onchange: () => this.render()}
        });
        this.search = frappe.ui.form.make_control({
            parent: this.page.main.find(".ss-search"), render_input: true,
            df: {fieldtype: "Data", fieldname: "plant_search", label: __("Plant search"),
                placeholder: __("Plant, category, or model"), onchange: () => this.render()}
        });
        if (this.search.$input) this.search.$input.on("input", () => this.render());
        this.monthInput = this.page.main.find(".ss-month");
        this.monthInput.on("change", () => this.load());
        this.page.set_primary_action(__("Generate / Recalculate"), () => this.generate());
        this.page.add_inner_button(__("Refresh"), () => this.load(this.date.get_value()));
        this.page.add_inner_button(__("Open document"), () => this.openDocument());
        this.page.main.on("click", ".ss-kpi", event => {
            const value = $(event.currentTarget).data("status");
            this.status = this.status === value ? "" : value;
            this.statusField.set_value(this.status || "All statuses");
            this.render();
        });
        this.page.main.on("click", ".ss-table th[data-key]", event => {
            const key = $(event.currentTarget).data("key");
            this.sortDirection = this.sortKey === key ? -this.sortDirection : 1;
            this.sortKey = key;
            this.render();
        });
        this.page.main.on("click", "a[data-doctype]", event => {
            event.preventDefault();
            const link = $(event.currentTarget);
            frappe.set_route("Form", link.data("doctype"), link.data("name"));
        });
    }

    async initialize() {
        try {
            const response = await frappe.call({method: this.method + "get_service_schedule_context"});
            const schedules = response.message || [];
            const todayMonth = frappe.datetime.get_today().slice(0, 7);
            const initial = schedules.find(r => this.monthValue(r.month) === todayMonth) || schedules[0];
            if (initial) {
                this.settingDate = true;
                await this.site.set_value(initial.site);
                this.monthInput.val(this.monthValue(initial.month));
                this.settingDate = false;
            } else {
                this.monthInput.val(frappe.datetime.get_today().slice(0, 7));
            }
            await this.load();
        } catch (error) {
            this.showError(error);
        }
    }

    async load(requestedDate = null) {
        const token = ++this.requestToken;
        const site = this.site.get_value();
        const month = this.monthLabel();
        if (!site || !month) {
            this.scheduleName = null;
            this.rows = [];
            this.loading = false;
            this.render();
            this.page.main.find(".ss-info").text(__("Choose a site and month."));
            this.page.main.find(".ss-table-wrap").html(`<div class="ss-empty">${__("Choose a site and month.")}</div>`);
            return;
        }
        this.loading = true;
        this.scheduleName = null;
        this.rows = [];
        this.page.main.find(".ss-kpis").empty();
        this.page.main.find(".ss-table-wrap").html(`<div class="ss-empty">${__("Loading saved Service Schedule data...")}</div>`);
        this.page.main.find(".ss-info").text(__("Loading saved Service Schedule data..."));
        try {
            const response = await frappe.call({
                method: this.method + "get_service_schedule_snapshot",
                args: {site, month, snapshot_date: requestedDate || null}
            });
            if (token !== this.requestToken) return;
            const data = response.message || {};
            this.scheduleName = data.schedule_name || null;
            this.rows = data.rows || [];
            this.settingDate = true;
            await this.date.set_value(data.snapshot_date || "");
            this.settingDate = false;
            this.page.set_primary_action(this.scheduleName ?
                __("Generate / Recalculate") : __("Create & Generate"), () => this.generate());
            this.render();
        } catch (error) {
            if (token === this.requestToken) this.showError(error);
        } finally {
            if (token === this.requestToken) {
                this.loading = false;
                this.settingDate = false;
            }
        }
    }

    async generate() {
        if (this.loading) return;
        const site = this.site.get_value();
        const month = this.monthLabel();
        if (!site || !month) {
            frappe.msgprint(__("Choose a site and month first."));
            return;
        }
        try {
            const response = await frappe.call({
                method: this.method + "create_or_generate_service_schedule",
                args: {site, month}, freeze: true,
                freeze_message: __("Generating Service Schedule...")
            });
            if (!response.message || !response.message.ok)
                throw new Error(__("Generation did not complete."));
            await this.load(this.date.get_value());
        } catch (error) {
            this.showError(error);
        }
    }

    openDocument() {
        if (this.scheduleName) frappe.set_route("Form", "Service Schedule", this.scheduleName);
        else frappe.msgprint(__("No Service Schedule exists for this site and month."));
    }

    showError(error) {
        this.scheduleName = null;
        this.rows = [];
        this.page.main.find(".ss-kpis").empty();
        this.page.main.find(".ss-info").text("");
        this.page.main.find(".ss-table-wrap").html(`<div class="ss-empty">${__("Unable to refresh Service Schedule. Use Refresh to retry.")}</div>`);
        frappe.msgprint({title: __("Service Schedule error"),
            message: this.escape(error.message || __("Check the error log and retry.")),
            indicator: "red"});
    }

    statusClass(status) {
        return ({
            "Overdue": "overdue", "Due": "due",
            "Due within 65 hours": "due65", "Due within 260 hours": "due260",
            "No Service History": "nohistory"
        })[status] || "";
    }

    render() {
        const statuses = ["Overdue", "Due", "Due within 65 hours",
            "Due within 260 hours", "No Service History"];
        const colors = ["#dc2626", "#b91c1c", "#ea580c", "#ca8a04", "#6b7280"];
        const cards = statuses.map((status, index) => {
            const count = this.rows.filter(row => row.planning_status === status).length;
            return `<button class="ss-kpi ${this.status === status ? "active" : ""}"
                style="--accent:${colors[index]}" data-status="${this.escape(status)}">
                <strong>${count}</strong><span>${this.escape(status === "Due" ? "Due Now" : status)}</span></button>`;
        }).join("");
        this.page.main.find(".ss-kpis").html(cards);
        if (!this.scheduleName) {
            this.page.main.find(".ss-info").text(__("No Service Schedule exists for this site and month."));
            this.page.main.find(".ss-table-wrap").html(`<div class="ss-empty">${__("Use Create & Generate to create the monthly schedule.")}</div>`);
            return;
        }
        const search = String(this.search.get_value() || "").toLowerCase().trim();
        const interval = this.intervalField.get_value();
        const status = this.status || this.statusField.get_value();
        const filtered = this.rows.filter(row => {
            if (status && status !== "All statuses" &&
                (status === "Normal" ? !!row.planning_status : row.planning_status !== status)) return false;
            if (interval && interval !== "All intervals" && row.planning_service_interval !== interval) return false;
            if (search && ![row.fleet_number, row.asset_category, row.model]
                .some(value => String(value || "").toLowerCase().includes(search))) return false;
            return true;
        });
        const numeric = new Set(["start_hours", "estimate_hours", "hours_previous_service",
            "planning_planned_hours", "planning_hours_remaining"]);
        filtered.sort((a, b) => {
            const left = a[this.sortKey] || "";
            const right = b[this.sortKey] || "";
            return this.sortDirection * (numeric.has(this.sortKey) ?
                Number(left) - Number(right) : String(left).localeCompare(String(right)));
        });
        this.page.main.find(".ss-info").text(
            `${this.scheduleName} · ${this.date.get_value() || __("No snapshot")} · ${filtered.length} / ${this.rows.length} ${__("plants")}`
        );
        const columns = [
            ["fleet_number", "Plant"], ["asset_category", "Category / Type"],
            ["model", "Model"], ["date", "Snapshot Date"], ["start_hours", "Start Hours"],
            ["estimate_hours", "Estimated Hours"], ["date_of_previous_service", "Last Service Date"],
            ["hours_previous_service", "Last Service Hours"], ["last_service_interval", "Last Interval"],
            ["planning_planned_hours", "Next Planned Hours"], ["planning_service_interval", "Next Interval"],
            ["planning_hours_remaining", "Hours Remaining"], ["planning_status", "Planning Status"],
            ["oem_booking_name", "OEM Booking"]
        ];
        const header = columns.map(([key, label]) =>
            `<th data-key="${key}">${this.escape(__(label))}${this.sortKey === key ? (this.sortDirection > 0 ? " ↑" : " ↓") : ""}</th>`).join("");
        const body = filtered.map(row => {
            const cells = columns.map(([key]) => {
                let value = row[key];
                if (key === "fleet_number" && value)
                    value = `<a href="#" data-doctype="Asset" data-name="${this.escape(value)}">${this.escape(value)}</a>`;
                else if (key === "oem_booking_name" && value)
                    value = `<a href="#" data-doctype="OEM Booking" data-name="${this.escape(value)}">${this.escape(value)}</a>`;
                else if (key === "planning_status")
                    value = `<span class="ss-badge ${this.statusClass(value)}">${this.escape(value || __("Normal"))}</span>`;
                else if (key === "date_of_previous_service" && row.msr_record_name)
                    value = `<a href="#" data-doctype="Mechanical Service Report" data-name="${this.escape(row.msr_record_name)}">${this.escape(value || row.msr_record_name)}</a>`;
                else if (key === "planning_hours_remaining" && row.planning_status === "No Service History")
                    value = "—";
                else value = this.escape(value);
                const title = ["asset_category", "model"].includes(key) && row[key] ?
                    ` title="${this.escape(row[key])}"` : "";
                return `<td class="${numeric.has(key) ? "num" : ""}"${title}>${value}</td>`;
            }).join("");
            return `<tr>${cells}</tr>`;
        }).join("");
        this.page.main.find(".ss-table-wrap").html(
            filtered.length ? `<table class="ss-table"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>` :
            `<div class="ss-empty">${__("No plants match these filters.")}</div>`
        );
    }
}
