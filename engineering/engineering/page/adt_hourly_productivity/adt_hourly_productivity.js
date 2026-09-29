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
        this.addStyles();
        this.build();
        this.initialize();
    }

    escape(value) {
        return $("<div>").text(value == null ? "" : String(value)).html();
    }

    addStyles() {
        if ($("#adt-hourly-productivity-styles").length) return;
        $("head").append(`<style id="adt-hourly-productivity-styles">
            .adt-hourly-productivity-page .layout-main-section {background:#f2f6f7;}
            .adt-hourly-productivity-page .page-head {background:#f2f6f7;}
            .ahp-shell {max-width:1500px;margin:auto;padding:10px 12px 42px;color:#163446;}
            .ahp-header {display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:5px 0 15px;}
            .ahp-eyebrow {font-size:11px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#237e81;}
            .ahp-title {font-size:clamp(25px,4vw,36px);font-weight:800;letter-spacing:-.035em;line-height:1.1;margin:5px 0 3px;}
            .ahp-subtitle {font-size:13px;color:#667d89;}
            .ahp-filters {position:sticky;top:0;z-index:12;background:#fff;border:1px solid #dce6e9;
                box-shadow:0 10px 28px rgba(21,52,70,.07);border-radius:16px;padding:12px;display:grid;
                grid-template-columns:repeat(3,minmax(0,1fr)) auto;align-items:end;gap:10px;margin-bottom:18px;}
            .ahp-filters .form-group {margin-bottom:0;}
            .ahp-filters .control-label {font-size:11px;font-weight:800;color:#5f7986;text-transform:uppercase;letter-spacing:.07em;}
            .ahp-filters .form-control,.ahp-filters .btn {min-height:43px;}
            .ahp-refresh,.ahp-download {border:0;border-radius:10px;min-height:43px;padding:0 17px;font-weight:800;cursor:pointer;}
            .ahp-refresh {background:#173f53;color:#fff;}
            .ahp-download {background:#d9f1e9;color:#0a654d;white-space:nowrap;}
            .ahp-refresh:focus-visible,.ahp-download:focus-visible {outline:3px solid #60b9bf;outline-offset:2px;}
            .ahp-summary {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:20px;}
            .ahp-summary-card {background:#fff;border:1px solid #dce6e9;border-radius:15px;padding:17px 18px;
                box-shadow:0 5px 16px rgba(21,52,70,.035);min-width:0;}
            .ahp-summary-card:nth-child(2) {background:#e8f4f3;border-color:#c8e4df;}
            .ahp-summary-card:nth-child(3) {background:#eaf1f8;border-color:#d6e4f0;}
            .ahp-summary-card:nth-child(4) {background:#f5f0e8;border-color:#eaddca;}
            .ahp-kpi-label {font-size:11px;letter-spacing:.09em;text-transform:uppercase;font-weight:800;color:#68808a;}
            .ahp-kpi-value {font-size:clamp(28px,4vw,40px);font-weight:800;line-height:1.15;letter-spacing:-.04em;margin-top:6px;font-variant-numeric:tabular-nums;}
            .ahp-kpi-note {font-size:11px;color:#68808a;margin-top:3px;}
            .ahp-section-head {display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 10px;}
            .ahp-section-head h2 {font-size:17px;font-weight:800;margin:0;}
            .ahp-section-head span {font-size:12px;color:#69808b;}
            .ahp-hours {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px;}
            .ahp-hour {background:#fff;border:1px solid #dce6e9;border-radius:16px;overflow:hidden;
                box-shadow:0 5px 17px rgba(21,52,70,.04);}
            .ahp-hour-top {padding:11px 15px;background:#173f53;color:#fff;display:flex;align-items:center;justify-content:space-between;gap:10px;}
            .ahp-hour-index {font-size:10px;color:#9bd6d4;letter-spacing:.1em;font-weight:800;text-transform:uppercase;}
            .ahp-hour-time {font-size:17px;font-weight:800;font-variant-numeric:tabular-nums;}
            .ahp-hour-values {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));padding:16px 12px 17px;}
            .ahp-hour-value {text-align:center;min-width:0;border-right:1px solid #e5eef0;}
            .ahp-hour-value:last-child {border-right:0;}
            .ahp-hour-value strong {display:block;font-size:28px;line-height:1.1;font-weight:800;font-variant-numeric:tabular-nums;}
            .ahp-hour-value span {display:block;font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:800;color:#6b818b;margin-top:6px;}
            .ahp-hour-value.available strong {color:#13866e;}
            .ahp-hour-value.utilised strong {color:#2875a9;}
            .ahp-hour-value.loads strong {color:#b66c22;}
            .ahp-message {padding:25px;background:#fff;border:1px solid #dce6e9;border-radius:15px;text-align:center;color:#667d89;}
            .ahp-footer {margin:16px 2px 0;font-size:12px;color:#69808b;line-height:1.5;}
            @media(max-width:1100px){.ahp-hours {grid-template-columns:repeat(3,minmax(0,1fr));}}
            @media(max-width:800px){.ahp-hours {grid-template-columns:repeat(2,minmax(0,1fr));}
                .ahp-summary {grid-template-columns:repeat(2,minmax(0,1fr));}}
            @media(max-width:580px){.ahp-shell {padding:5px 5px 30px;}.ahp-header {display:block;}
                .ahp-filters {grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:10px;}
                .ahp-site {grid-column:1 / -1;}.ahp-refresh {grid-column:1 / -1;}
                .ahp-download {width:100%;margin-top:10px;}.ahp-hours {grid-template-columns:1fr;gap:9px;}
                .ahp-hour-values {padding:13px 9px;}.ahp-summary-card {padding:13px;}
                .ahp-kpi-value {font-size:29px;}.ahp-section-head {align-items:baseline;}}
        </style>`);
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
            </div></article>`).join(""));
        this.page.main.find(".ahp-footer").text(__("Available ADTs are weighted by available minutes in each hour. An ADT is utilised once it records at least one load in that hour."));
        this.page.main.find(".ahp-download").prop("disabled", false);
    }

    download() {
        if (!this.data) return;
        const query = new URLSearchParams(this.filters()).toString();
        window.open(`/api/method/${this.method}download_detailed_pdf?${query}`, "_blank", "noopener");
    }
}
