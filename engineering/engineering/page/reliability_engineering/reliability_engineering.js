frappe.pages["reliability-engineering"].on_page_load = function (wrapper) {
    wrapper.reliabilityEngineering = new ReliabilityEngineeringPage(wrapper);
};

class ReliabilityEngineeringPage {
    constructor(wrapper) {
        this.wrapper = $(wrapper).addClass("reliability-engineering-page");
        this.page = frappe.ui.make_app_page({parent: wrapper, title: __("Reliability Engineering"), single_column: true});
        this.requestToken = 0;
        this.build();
        this.initialize();
    }

    escape(value) {
        return $("<div>").text(value == null ? "" : String(value)).html();
    }

    build() {
        this.page.main.html(`<div class="re-shell">
            <header class="re-header"><div><div class="re-eyebrow">${__("ENGINEERING INTELLIGENCE")}</div>
            <h1>${__("Reliability Engineering")}</h1><p>${__("Failure frequency, repair time and verified operating hours")}</p></div>
            <span class="re-period"></span></header>
            <div class="re-filters"><div class="re-from"></div><div class="re-to"></div>
            <div class="re-location"></div><div class="re-asset"></div><div class="re-measurement"></div>
            <button class="re-refresh" type="button">${__("Refresh report")}</button></div>
            <div class="re-status" role="status"></div>
            <section class="re-kpis" aria-label="${__("Reliability metrics")}"></section>
            <div class="re-insights"><section class="re-panel re-focus" hidden></section>
            <section class="re-panel re-trend"><div class="re-panel-head"><div><div class="re-eyebrow">${__("PERFORMANCE OVER TIME")}</div><h2>${__("Trend")}</h2></div><span class="re-trend-label"></span></div><div class="re-chart"></div></section></div>
            <section class="re-panel re-ranking"><div class="re-panel-head"><div><div class="re-eyebrow">${__("FLEET COMPARISON")}</div><h2>${__("Machine ranking")}</h2></div><span class="re-ranking-count"></span></div><div class="re-table-wrap"></div></section>
            <section class="re-panel re-drill"><div class="re-panel-head"><div><div class="re-eyebrow">${__("SOURCE RECORDS")}</div><h2>${__("Breakdown drill-down")}</h2></div><span class="re-breakdown-count"></span></div><div class="re-breakdowns"></div></section>
            <div class="re-quality"></div></div>`);
        const fields = [
            ["from", {fieldtype: "Date", label: __("From Date"), fieldname: "from_date"}],
            ["to", {fieldtype: "Date", label: __("To Date"), fieldname: "to_date"}],
            ["location", {fieldtype: "Link", options: "Location", label: __("Location"), fieldname: "location"}],
            ["asset", {fieldtype: "Link", options: "Asset", label: __("Asset"), fieldname: "asset"}],
            ["measurement", {fieldtype: "Select", label: __("Measurement"), fieldname: "measurement",
                options: "Overview\nMTBF\nMTTR\nBDFR\nRepeat Breakdown Rate"}]
        ];
        fields.forEach(([key, df]) => {
            this[key] = frappe.ui.form.make_control({parent: this.page.main.find(`.re-${key}`), render_input: true,
                df: {...df, onchange: () => key === "measurement" ? this.render() : this.load()}});
        });
        this.page.main.on("click", ".re-refresh", () => this.load());
        this.page.main.on("click", ".re-table tbody tr", event => {
            this.selectedAsset = decodeURIComponent($(event.currentTarget).attr("data-asset"));
            this.renderBreakdowns(this.data.breakdowns.filter(row => row.asset === this.selectedAsset));
            this.page.main.find(".re-drill")[0].scrollIntoView({behavior: "smooth", block: "start"});
        });
        this.page.main.on("keydown", ".re-table tbody tr", event => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                $(event.currentTarget).trigger("click");
            }
        });
        this.page.main.on("click", ".re-show-all", () => {
            this.selectedAsset = null;
            this.renderBreakdowns(this.data.breakdowns);
        });
    }

    async initialize() {
        this.initializing = true;
        const today = frappe.datetime.get_today();
        await this.from.set_value(today.slice(0, 8) + "01");
        await this.to.set_value(today);
        await this.measurement.set_value("Overview");
        this.initializing = false;
        this.load();
    }

    async load() {
        if (this.initializing) return;
        const token = ++this.requestToken;
        const from_date = this.from.get_value(), to_date = this.to.get_value();
        if (!from_date || !to_date) return;
        if (to_date < from_date) {
            this.page.main.find(".re-status").text(__("To Date must be on or after From Date."));
            return;
        }
        this.page.main.find(".re-status").text(__("Loading reliability data…"));
        try {
            const response = await frappe.call({
                method: "engineering.engineering.page.reliability_engineering.reliability_engineering.get_dashboard",
                args: {from_date, to_date, location: this.location.get_value(), asset: this.asset.get_value()}
            });
            if (token !== this.requestToken) return;
            this.data = response.message;
            this.render();
        } catch (error) {
            if (token !== this.requestToken) return;
            this.page.main.find(".re-status").text(__("Unable to load reliability data. Check the filters and try again."));
        }
    }

    number(value, suffix = "", digits = 1) {
        return value == null ? "—" : `${Number(value).toLocaleString(undefined, {maximumFractionDigits: digits})}${suffix}`;
    }

    metric() {
        return ({MTBF: "mtbf", MTTR: "mttr", BDFR: "bdfr", "Repeat Breakdown Rate": "repeat_rate"})[this.measurement.get_value()] || "bdfr";
    }

    metricLabel(key) {
        return ({mtbf: __("MTBF"), mttr: __("MTTR"), bdfr: __("BDFR"), repeat_rate: __("Repeat Breakdown Rate")})[key];
    }

    metricValue(row, key) {
        return this.number(row[key], key === "repeat_rate" ? "%" : key === "bdfr" ? " / 1,000 h" : " h", 1);
    }

    render() {
        if (!this.data) return;
        const {kpis, ranking, breakdowns, quality} = this.data;
        const focused = this.measurement.get_value() || "Overview";
        const key = this.metric();
        this.page.main.find(".re-status").empty();
        this.page.main.find(".re-period").text(`${this.from.get_value()} – ${this.to.get_value()}`);
        const cards = [
            ["mtbf", __("MTBF"), this.metricValue(kpis, "mtbf"), __("Operating hours / breakdowns")],
            ["mttr", __("MTTR"), this.metricValue(kpis, "mttr"), __("Valid repair hours / completed repairs")],
            ["bdfr", __("BDFR"), this.metricValue(kpis, "bdfr"), __("Breakdowns per 1,000 operating hours")],
            ["repeat_rate", __("Repeat Breakdown Rate"), this.metricValue(kpis, "repeat_rate"),
                kpis.repeat_rate == null && kpis.breakdowns ? __("Available at 100% classification coverage") : __("Same machine and class within 7 days")],
            ["operating_hours", __("Validated operating hours"), this.number(kpis.operating_hours, " h"), __("Pre-Use engine meter deltas")],
            ["breakdowns", __("Breakdowns"), this.number(kpis.breakdowns, "", 0), `${__("Known repeats")}: ${this.number(kpis.repeat_breakdowns, "", 0)}`],
            ["breakdown_hours", __("Breakdown hours"), this.number(kpis.breakdown_hours, " h"), __("Valid recorded repair intervals")],
            ["classification_coverage", __("Classification Coverage %"), this.number(kpis.classification_coverage, "%"), __("Classified / total breakdowns")]
        ];
        this.page.main.find(".re-kpis").html(cards.map(([id, label, value, note], index) =>
            `<div class="re-kpi ${index < 4 ? "re-kpi-primary" : ""} ${focused !== "Overview" && key === id ? "re-kpi-active" : ""}"><span>${this.escape(label)}</span><strong>${this.escape(value)}</strong><small>${this.escape(note)}</small></div>`).join(""));
        this.page.main.find(".re-insights").toggleClass("re-insights-focused", focused !== "Overview");
        this.page.main.find(".re-focus").prop("hidden", focused === "Overview").html(`<div class="re-eyebrow">${__("MEASUREMENT FOCUS")}</div>
            <h2>${this.escape(focused)}</h2><div class="re-focus-value">${this.escape(focused === "Overview" ? this.number(kpis.breakdowns, "", 0) : this.metricValue(kpis, key))}</div>
            <p>${this.escape(focused === "Overview" ? __("Breakdown events in the selected period") :
                focused === "MTBF" ? __("Validated operating hours per breakdown. Higher is better.") :
                focused === "MTTR" ? __("Average duration of valid completed repairs. Lower is better.") :
                focused === "BDFR" ? __("Breakdowns per 1,000 validated operating hours. Lower is better.") :
                __("Repeat failures on the same machine and classification within seven days. Lower is better."))}</p>`);
        this.renderTrend(key);
        this.renderRanking(ranking);
        this.selectedAsset = null;
        this.renderBreakdowns(breakdowns);
        this.page.main.find(".re-quality").text(
            `${__("Data quality")}: ${quality.invalid_repairs} ${__("open/invalid repairs excluded from MTTR")}; ` +
            `${quality.invalid_meter_rows} ${__("invalid Pre-Use meter rows")}; ` +
            `${quality.conflicting_hour_groups} ${__("conflicting meter shifts excluded")}; ` +
            `${quality.invalid_start_times} ${__("missing breakdown start times")}; ` +
            `${quality.missing_asset_breakdowns} ${__("breakdowns without an Asset link")}.`
        );
    }

    renderTrend(key) {
        const rows = this.data.trend;
        const target = this.page.main.find(".re-chart").empty();
        this.page.main.find(".re-trend-label").text(this.metricLabel(key));
        if (key === "repeat_rate" && this.data.kpis.breakdowns && this.data.kpis.repeat_rate == null) {
            target.html(`<div class="re-empty">${__("Repeat trend is available when all breakdowns are classified.")}</div>`);
            return;
        }
        const monthly = (new Date(this.to.get_value()) - new Date(this.from.get_value())) / 86400000 > 90;
        const groups = {};
        rows.forEach(row => {
            const label = monthly ? row.date.slice(0, 7) : row.date.slice(5);
            if (!groups[label]) groups[label] = {hours: 0, failures: 0, repair_hours: 0, repairs: 0, repeats: 0, classified: 0};
            Object.keys(groups[label]).forEach(field => groups[label][field] += Number(row[field] || 0));
        });
        const series = Object.keys(groups).map(label => {
            const row = groups[label];
            let value;
            if (key === "mtbf") value = row.failures ? row.hours / row.failures : null;
            else if (key === "mttr") value = row.repairs ? row.repair_hours / row.repairs : null;
            else if (key === "repeat_rate") value = row.failures && row.classified === row.failures ? 100 * row.repeats / row.failures : null;
            else value = row.hours ? 1000 * row.failures / row.hours : null;
            return {label, value};
        }).filter(point => point.value != null);
        if (!series.length) {
            target.html(`<div class="re-empty">${__("No trend data for this measurement and period.")}</div>`);
            return;
        }
        new frappe.Chart(target[0], {type: "line", height: 260,
            data: {labels: series.map(point => point.label), datasets: [{name: this.metricLabel(key), values: series.map(point => Number(point.value.toFixed(2)))}]},
            colors: ["#087f83"], lineOptions: {regionFill: 1, hideDots: series.length > 45},
            tooltipOptions: {formatTooltipY: value => this.number(value, key === "repeat_rate" ? "%" : key === "bdfr" ? " / 1,000 h" : " h")}});
    }

    renderRanking(rows) {
        const metric = this.measurement.get_value();
        const key = this.metric();
        const highlight = metric === "Overview" ? null : key;
        rows = [...rows];
        if (metric !== "Overview") {
            rows.sort((left, right) => {
                const a = left[key], b = right[key];
                if (a == null) return 1;
                if (b == null) return -1;
                return (metric === "MTBF" ? a - b : b - a) || left.asset_label.localeCompare(right.asset_label);
            });
        }
        this.page.main.find(".re-ranking-count").text(`${rows.length} ${__("machines")}`);
        if (!rows.length) {
            this.page.main.find(".re-table-wrap").html(`<div class="re-empty">${__("No machine data for these filters.")}</div>`);
            return;
        }
        this.page.main.find(".re-table-wrap").html(`<table class="re-table"><thead><tr>
            <th>${__("Machine")}</th><th>${__("Location")}</th><th>${__("Operating h")}</th><th>${__("Breakdowns")}</th><th>${__("Breakdown h")}</th>
            <th class="${highlight === "mtbf" ? "re-highlight" : ""}">${__("MTBF")}</th>
            <th class="${highlight === "mttr" ? "re-highlight" : ""}">${__("MTTR")}</th>
            <th class="${highlight === "bdfr" ? "re-highlight" : ""}">${__("BDFR")}</th>
            <th>${__("Repeats")}</th><th class="${highlight === "repeat_rate" ? "re-highlight" : ""}">${__("Repeat rate")}</th>
            <th>${__("Coverage")}</th></tr></thead><tbody>
            ${rows.map(row => `<tr tabindex="0" data-asset="${encodeURIComponent(row.asset)}"><td><strong>${this.escape(row.asset_label)}</strong><small>${this.escape(row.asset)}</small></td>
            <td>${this.escape(row.locations.join(", ") || "—")}</td><td>${this.number(row.operating_hours)}</td>
            <td>${this.number(row.breakdowns, "", 0)}</td><td>${this.number(row.breakdown_hours)}</td>
            <td class="${highlight === "mtbf" ? "re-highlight" : ""}">${this.number(row.mtbf)}</td>
            <td class="${highlight === "mttr" ? "re-highlight" : ""}">${this.number(row.mttr)}</td>
            <td class="${highlight === "bdfr" ? "re-highlight" : ""}">${this.number(row.bdfr)}</td>
            <td>${this.number(row.repeat_breakdowns, "", 0)}</td>
            <td class="${highlight === "repeat_rate" ? "re-highlight" : ""}">${this.number(row.repeat_rate, "%")}</td>
            <td>${this.number(row.classification_coverage, "%")}</td></tr>`).join("")}</tbody></table>`);
    }

    renderBreakdowns(rows) {
        this.page.main.find(".re-breakdown-count").html(`${rows.length} ${__("events")}${this.selectedAsset ? ` · <button type="button" class="re-show-all">${__("Show all")}</button>` : ""}`);
        const target = this.page.main.find(".re-breakdowns");
        if (!rows.length) {
            target.html(`<div class="re-empty">${__("No breakdowns for these filters.")}</div>`);
            return;
        }
        target.html(rows.map(row => `<details class="re-event"><summary><span class="re-event-machine">${this.escape(row.asset_label)}</span>
            <span>${this.escape(row.start || __("Start time missing"))}</span>
            <span class="re-event-class">${this.escape(row.classification || __("Unclassified"))}</span>
            <span class="re-event-tag ${row.repeat ? "re-repeat" : ""}">${row.repeat ? __("Repeat") : __("Breakdown")}</span></summary>
            <div class="re-event-body"><dl><div><dt>${__("Breakdown date")}</dt><dd>${this.escape(row.date)}</dd></div>
            <div><dt>${__("PBM record")}</dt><dd><a href="/app/plant-breakdown-or-maintenance/${encodeURIComponent(row.name)}" target="_blank" rel="noopener">${this.escape(row.name)}</a></dd></div>
            <div><dt>${__("Site")}</dt><dd>${this.escape(row.location || "—")}</dd></div>
            <div><dt>${__("Start")}</dt><dd>${this.escape(row.start || "—")}</dd></div>
            <div><dt>${__("Resolved")}</dt><dd>${this.escape(row.resolved || "—")}</dd></div>
            <div><dt>${__("Valid repair hours")}</dt><dd>${this.number(row.repair_hours, " h")}</dd></div>
            <div><dt>${__("Excluded from A&U")}</dt><dd>${row.exclude_from_au ? __("Yes") : __("No")}</dd></div>
            <div><dt>${__("Previous matching breakdown")}</dt><dd>${this.escape(row.previous_breakdown || "—")}</dd></div></dl>
            <p><strong>${__("Days since previous matching failure")}</strong> ${this.number(row.days_since_previous, " days", 2)}</p>
            <p><strong>${__("Reason")}</strong> ${this.escape(row.reason || "—")}</p>
            <p><strong>${__("Resolution")}</strong> ${this.escape(row.resolution || "—")}</p></div></details>`).join(""));
    }
}
