frappe.pages["adt-hourly-productivity"].on_page_load = function (wrapper) {
    wrapper.adtHourlyProductivity = new ADTHourlyProductivityPage(wrapper);
};

class ADTHourlyProductivityPage {
    constructor(wrapper) {
        this.wrapper = $(wrapper).addClass("adt-hourly-productivity-page");
        this.page = frappe.ui.make_app_page({
            parent: wrapper, title: __("ADT hourly productivity"), single_column: true
        });
        this.method = "engineering.engineering.page.adt_hourly_productivity.adt_hourly_productivity.";
        this.requestToken = 0;
        this.storageKey = `adt-hourly-productivity-site:${frappe.session.user}`;
        this.build();
        this.initialize();
    }

    escape(value) {
        return $("<div>").text(value == null ? "" : String(value)).html();
    }

    build() {
        this.page.main.html(`<div class="ahp-shell">
            <div class="ahp-header"><div><div class="ahp-eyebrow">${__("Fleet control board")}</div>
            <h1 class="ahp-title">${__("ADT hourly productivity")}</h1>
            <div class="ahp-subtitle">${__("Availability, utilisation and loads across each shift hour")}</div></div>
            <button type="button" class="ahp-download">${__("Download Detailed Report")}</button></div>
            <div class="ahp-filters"><div class="ahp-site"></div><div class="ahp-date"></div>
            <div class="ahp-shift"></div><button type="button" class="ahp-refresh">${__("Refresh")}</button></div>
            <div class="ahp-summary"></div>
            <div class="ahp-section-head"><h2>${__("Hourly performance")}</h2><span>${__("12 hourly periods")}</span></div>
            <div class="ahp-hours"></div><div class="ahp-footer"></div>
            <section class="ahp-exc-section" aria-label="${__("Excavator First / Last Load Performance")}"></section>
        </div>`);
        this.site = frappe.ui.form.make_control({
            parent: this.page.main.find(".ahp-site"), render_input: true,
            df: {fieldtype: "Link", options: "Location", fieldname: "site", label: __("Site"),
                reqd: 1, onchange: () => this.load()}
        });
        this.date = frappe.ui.form.make_control({
            parent: this.page.main.find(".ahp-date"), render_input: true,
            df: {fieldtype: "Date", fieldname: "shift_date", label: __("Shift date"), onchange: () => this.load()}
        });
        this.shift = frappe.ui.form.make_control({
            parent: this.page.main.find(".ahp-shift"), render_input: true,
            df: {fieldtype: "Select", fieldname: "shift", label: __("Shift"), options: "Day\nNight",
                onchange: () => this.load()}
        });
        this.page.main.on("click", ".ahp-refresh", () => this.load());
        this.page.main.on("click", ".ahp-download", () => this.download());
        this.page.main.find(".ahp-download").prop("disabled", true);
        this.message(__("Select a site to view hourly productivity."));
    }

    async initialize() {
        try {
            const response = await frappe.call({method: this.method + "get_defaults"});
            const defaults = response.message || {};
            this.initializing = true;
            await this.date.set_value(defaults.date);
            await this.shift.set_value(defaults.shift);
            const previousSite = localStorage.getItem(this.storageKey);
            if (previousSite) await this.site.set_value(previousSite);
            this.initializing = false;
            if (previousSite) this.load();
        } catch (error) {
            this.initializing = false;
            this.message(__("Could not load the current shift. Refresh the page to retry."));
        }
    }

    message(value) {
        this.page.main.find(".ahp-summary").empty();
        this.page.main.find(".ahp-hours").html(`<div class="ahp-message">${this.escape(value)}</div>`);
        this.page.main.find(".ahp-footer").empty();
        this.page.main.find(".ahp-exc-section").empty();
        this.page.main.find(".ahp-download").prop("disabled", true);
    }

    filters() {
        return {date: this.date.get_value(), shift: this.shift.get_value(), site: this.site.get_value()};
    }

    async load() {
        if (this.initializing) return;
        const token = ++this.requestToken;
        const args = this.filters();
        if (!args.site) {
            this.message(__("Select a site to view hourly productivity."));
            return;
        }
        if (!args.date || !args.shift) return;
        localStorage.setItem(this.storageKey, args.site);
        this.message(__("Loading shift data…"));
        try {
            const response = await frappe.call({method: this.method + "get_dashboard", args});
            if (token !== this.requestToken) return;
            this.data = response.message;
            this.render();
        } catch (error) {
            if (token !== this.requestToken) return;
            this.data = null;
            this.message(__("Could not load this shift. Check the filters and try again."));
        }
    }

    render() {
        const data = this.data;
        const s = data.summary;
        const cards = [
            [__("ADTs at site"), s.adts_at_site, __("Current site fleet")],
            [__("Average available"), Number(s.average_available).toFixed(2), __("Mean of 12 hourly counts")],
            [__("ADTs utilised"), s.adts_utilised, __("Unique ADTs with loads")],
            [__("Total loads"), s.total_loads, __("Across the selected shift")]
        ];
        this.page.main.find(".ahp-summary").html(cards.map(([label, value, note]) => `
            <div class="ahp-summary-card"><div class="ahp-kpi-label">${this.escape(label)}</div>
            <div class="ahp-kpi-value">${this.escape(value)}</div><div class="ahp-kpi-note">${this.escape(note)}</div></div>
        `).join(""));
        this.page.main.find(".ahp-hours").html(data.hours.map((hour, index) => `
            <article class="ahp-hour"><div class="ahp-hour-top"><span class="ahp-hour-index">${__("Hour")} ${index + 1}</span>
            <span class="ahp-hour-time">${this.escape(hour.label)}</span></div>
            <div class="ahp-hour-values">
              <div class="ahp-hour-value available"><strong>${Number(hour.available).toFixed(2)}</strong><span>${__("Available")}</span></div>
              <div class="ahp-hour-value utilised"><strong>${this.escape(hour.utilised)}</strong><span>${__("Utilised")}</span></div>
              <div class="ahp-hour-value loads"><strong>${this.escape(hour.loads)}</strong><span>${__("Loads")}</span></div>
            </div>${this.renderEvents(hour)}</article>`).join(""));
        this.page.main.find(".ahp-footer").text(__("Available ADTs are weighted by available minutes in each hour. An ADT is utilised once it records at least one load in that hour."));
        this.renderExcavators(data.excavators || []);
        this.page.main.find(".ahp-download").prop("disabled", false);
    }

    renderEvents(hour) {
        const groups = [
            [__("First Loads"), hour.first_load_events || [], "first"],
            [__("Last Loads"), hour.last_load_events || [], "last"]
        ];
        const content = groups.filter(([, events]) => events.length).map(([title, events, kind]) => `
            <div class="ahp-event-group ahp-event-${kind}">
              <div class="ahp-event-title">${this.escape(title)}</div>
              ${events.map(event => `<div class="ahp-event-item"><span>${this.escape(event.excavator)}</span>
                <strong>${this.escape(event.time)}</strong></div>`).join("")}
            </div>`).join("");
        return content ? `<div class="ahp-hour-events">${content}</div>` : "";
    }

    renderExcavators(excavators) {
        const section = this.page.main.find(".ahp-exc-section");
        const title = `<div class="ahp-section-head"><h2>${__("Excavator First / Last Load Performance")}</h2>
            <span>${this.escape(excavators.length)} ${__("excavators")}</span></div>`;
        if (!excavators.length) {
            section.html(`${title}<div class="ahp-message">${__("No excavators recorded for this shift.")}</div>`);
            return;
        }
        section.html(`${title}<div class="ahp-exc-wrap"><table class="ahp-exc-table">
            <thead><tr><th>${__("Excavator")}</th><th>${__("First Load Time")}</th>
            <th>${__("First Load Hour")}</th><th>${__("Last Load Time")}</th>
            <th>${__("Last Load Hour")}</th></tr></thead><tbody>
            ${excavators.map(row => `<tr>
              <td data-label="${__("Excavator")}" class="ahp-exc-name">${this.escape(row.excavator)}</td>
              <td data-label="${__("First Load Time")}">${this.escape(row.first_load_time || "-")}</td>
              <td data-label="${__("First Load Hour")}">${this.escape(row.first_load_hour || "-")}</td>
              <td data-label="${__("Last Load Time")}">${this.escape(row.last_load_time || "-")}</td>
              <td data-label="${__("Last Load Hour")}">${this.escape(row.last_load_hour || "-")}</td>
            </tr>`).join("")}</tbody></table></div>`);
    }

    download() {
        if (!this.data) return;
        const query = new URLSearchParams(this.filters()).toString();
        window.open(`/api/method/${this.method}download_detailed_pdf?${query}`, "_blank", "noopener");
    }
}
