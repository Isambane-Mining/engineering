frappe.pages["reliability-engineering"].on_page_load = function (wrapper) {
    wrapper.reliabilityEngineering = new ReliabilityEngineeringPage(wrapper);
};

class ReliabilityEngineeringPage {
    constructor(wrapper) {
        this.wrapper = $(wrapper).addClass("reliability-engineering-page");
        this.page = frappe.ui.make_app_page({parent: wrapper, title: __("Reliability Engineering"), single_column: true});
        this.requestToken = 0;
        this.build();
        this.buildTabs();
        this.initialize();
    }

    escape(value) {
        return $("<div>").text(value == null ? "" : String(value)).html();
    }

    buildTabs() {
        const shell = this.page.main.find(".re-shell");
        shell.children().not(".re-header").wrapAll('<div class="re-analysis-tab" role="tabpanel" id="re-analysis-panel" aria-labelledby="re-analysis-tab"></div>');
        shell.find(".re-header").after(`<div class="re-tabs" role="tablist" aria-label="${__("Analysis views")}">
            <button type="button" id="re-analysis-tab" role="tab" aria-selected="true" aria-controls="re-analysis-panel" data-tab="analysis">${__("Breakdown Analysis")}</button>
            <button type="button" id="re-problems-tab" role="tab" aria-selected="false" aria-controls="re-problems-panel" tabindex="-1" data-tab="problems">${__("Problem Machines")}</button></div>`);
        shell.append('<div class="re-problems-tab" role="tabpanel" id="re-problems-panel" aria-labelledby="re-problems-tab" hidden></div>');
        this.problems = new ProblemMachinesPanel(shell.find(".re-problems-tab"), this);
        const select = name => {
            shell.find(".re-tabs button").each((index, button) => {
                const active = button.dataset.tab === name;
                $(button).attr({"aria-selected": String(active), tabindex: active ? "0" : "-1"});
            });
            shell.find(".re-analysis-tab").prop("hidden", name !== "analysis");
            shell.find(".re-problems-tab").prop("hidden", name !== "problems");
            if (name === "problems") this.problems.activate();
            shell.find(".re-period").prop("hidden", name === "problems");
        };
        shell.on("click", ".re-tabs button", event => select(event.currentTarget.dataset.tab));
        shell.on("keydown", ".re-tabs button", event => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const name = event.key === "Home" ? "analysis" : event.key === "End" ? "problems" :
                event.currentTarget.dataset.tab === "analysis" ? "problems" : "analysis";
            select(name);
            shell.find(`.re-tabs [data-tab="${name}"]`).trigger("focus");
        });
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

class ProblemMachinesPanel {
    constructor(root, page) {
        this.root = root;
        this.page = page;
        this.token = 0;
        this.initializing = true;
        root.html(`<div class="re-filters pm-filters"><div class="pm-site"></div><div class="pm-from"></div>
            <div class="pm-to"></div><div class="pm-top"></div></div>
            <div class="pm-status" role="status" aria-live="polite"></div>
            <div class="pm-results">
            <div class="pm-summary"></div>
            <div class="pm-charts"><section class="re-panel"><div class="re-panel-head"><h2>${__("Worst Machines by Breakdown Impact")}</h2></div>
            <p class="pm-caption">${__("Problem Score · higher means worse")}</p><div class="pm-impact"></div></section>
            <section class="re-panel"><div class="re-panel-head"><h2>${__("Breakdown Frequency")}</h2></div><div class="pm-frequency"></div></section></div>
            <section class="re-panel pm-ranking"><div class="re-panel-head"><h2>${__("Problem machine ranking")}</h2><span class="pm-count"></span></div>
            <div class="pm-table-wrap"></div><div class="pm-cards"></div></section></div>
            <details class="pm-method re-panel"><summary>${__("How scores and recurring problems are calculated")}</summary>
            <p>${__("Score (0–100) = 100 × average of metric / fleet maximum for breakdown hours, breakdown count, BDFR, MTTR, repeat rate and inverse MTBF. Each available metric contributes equally. Scores are relative to all machines with breakdowns in the selected site and dates, before Top N is applied.")}</p>
            <p>${__("BDFR and inverse MTBF express the same failure exposure relationship; both are included as requested. Missing metrics are excluded, not treated as zero. Scores with different metric coverage need care when comparing machines.")}</p>
            <p>${__("Breakdown hours include valid recorded completed repair intervals; open or invalid intervals are excluded. MTTR uses completed repairs only. Operating hours come from validated Pre-Use meter readings. MTBF and BDFR are unavailable when operating hours are zero.")}</p>
            <p>${__("A repeat is the same machine and failure classification within seven days, including the seven-day lookback. Repeat rate is available only at 100% classification coverage. Main recurring problem is the class with the most known repeats, then the most events. With no known repeats, the most frequent class is shown. For unclassified problems, the most frequent recorded reason is shown with recurrence unverified; free-text reasons do not establish repeats.")}</p></details>
            <div class="pm-quality"></div>`);
        [
            ["site", {fieldtype: "Link", options: "Location", fieldname: "pm_site", label: __("Site")}],
            ["from", {fieldtype: "Date", fieldname: "pm_from", label: __("Date From")}],
            ["to", {fieldtype: "Date", fieldname: "pm_to", label: __("Date To")}],
            ["top", {fieldtype: "Select", fieldname: "pm_top", label: __("Show Top"), options: Array.from({length: 10}, (_, i) => String(i + 1)).join("\n")}]
        ].forEach(([key, df]) => {
            this[key] = frappe.ui.form.make_control({parent: root.find(`.pm-${key}`), render_input: true,
                df: {...df, onchange: () => this.load()}});
        });
        this.ready = this.initialize();
    }

    async initialize() {
        const today = frappe.datetime.get_today();
        await this.from.set_value(today.slice(0, 8) + "01");
        await this.to.set_value(today);
        await this.top.set_value("5");
        this.initializing = false;
    }

    async activate() {
        await this.ready;
        if (!this.data) await this.load();
        else this.render();
    }

    async load() {
        if (this.initializing) return;
        const token = ++this.token;
        const from_date = this.from.get_value(), to_date = this.to.get_value();
        this.data = null;
        this.root.find(".pm-results").prop("hidden", true);
        this.root.find(".pm-quality").empty();
        if (!from_date || !to_date || to_date < from_date) {
            this.root.find(".pm-status").text(__("Select dates with Date To on or after Date From."));
            return;
        }
        this.root.find(".pm-status").text(__("Loading problem machines…"));
        try {
            const response = await frappe.call({
                method: "engineering.engineering.page.reliability_engineering.problem_machines.get_problem_machines",
                args: {from_date, to_date, location: this.site.get_value() || null, show_top: this.top.get_value() || "5"}
            });
            if (token !== this.token) return;
            this.data = response.message;
            if (!this.root.prop("hidden")) this.render();
        } catch (error) {
            if (token !== this.token) return;
            this.root.find(".pm-status").text(__("Unable to load problem machines. Check the filters and try again."));
        }
    }

    escape(value) { return this.page.escape(value); }
    number(value, suffix = "", digits = 1) { return this.page.number(value, suffix, digits); }

    coverage(row) {
        return row.score_metrics === 6 ? __("6/6 score metrics") :
            `${row.score_metrics}/6 ${__("score metrics")} · ${__("Unavailable")}: ${row.missing_metrics.join(", ")}`;
    }

    problem(row) {
        return `${this.escape(row.main_problem)}<small>${row.main_problem_unverified ? __("Most frequent reason; recurrence unverified") : row.main_problem_repeats ?
            `${row.main_problem_repeats} ${__("known repeats")}` : __("Most frequent class; no known repeats")} · ${row.main_problem_events} ${__("events")}</small>`;
    }

    render() {
        if (!this.data) return;
        const rows = this.data.ranking;
        this.root.find(".pm-status").empty();
        this.root.find(".pm-results").prop("hidden", false);
        this.root.find(".pm-count").text(`${rows.length} ${__("of")} ${this.data.total_machines} ${__("machines with breakdowns")}`);
        const worst = rows[0];
        const summaries = [
            [__("Highest ranked machine"), worst ? worst.asset_label : "—", worst ? `${__("Problem Score")}: ${this.number(worst.problem_score)}` : __("No breakdowns")],
            [__("Selected breakdown hours"), this.number(rows.reduce((sum, row) => sum + row.breakdown_hours, 0), " h"), `${__("Top")} ${this.data.show_top} · ${__("completed repair intervals")}`],
            [__("Selected breakdowns"), this.number(rows.reduce((sum, row) => sum + row.breakdowns, 0), "", 0), `${rows.length} ${__("ranked machines")}`],
            [__("Period / site"), this.site.get_value() || __("All sites"), `${this.from.get_value()} – ${this.to.get_value()}`]
        ];
        this.root.find(".pm-summary").html(summaries.map(([label, value, note]) => `<div class="re-kpi re-kpi-primary"><span>${this.escape(label)}</span><strong>${this.escape(value)}</strong><small>${this.escape(note)}</small></div>`).join(""));
        const impact = this.root.find(".pm-impact").empty();
        if (this.frequencyChart) this.frequencyChart.destroy();
        const frequency = this.root.find(".pm-frequency").empty();
        if (!rows.length) {
            const empty = `<div class="re-empty">${__("No machines with breakdowns for this site and period.")}</div>`;
            impact.html(empty); frequency.html(empty);
            this.root.find(".pm-table-wrap").html(empty);
            this.root.find(".pm-cards").html(empty);
        } else {
            // Frappe Charts supplies the frequency chart. Its bar chart has no
            // horizontal mode, so score bars use semantic HTML and the same palette.
            impact.html(`<ol class="pm-bars" aria-label="${__("Problem Scores from 0 to 100")}">${rows.map(row =>
                `<li><div class="pm-bar-label"><strong>#${row.rank} ${this.escape(row.asset_label)}</strong><span>${this.number(row.problem_score)}</span></div>
                <div class="pm-bar-track"><div class="pm-bar-fill ${row.rank === 1 ? "pm-worst" : ""}" style="width:${row.problem_score}%"></div></div></li>`).join("")}</ol><div class="pm-axis"><span>0</span><span>${__("Problem Score")}</span><span>100</span></div>`);
            this.frequencyChart = new frappe.Chart(frequency[0], {type: "bar", height: 280,
                animate: false, disableEntryAnimation: true,
                data: {labels: rows.map(row => row.asset_label), datasets: [{name: __("Breakdowns"), values: rows.map(row => row.breakdowns)}]},
                colors: ["#16858a"], barOptions: {spaceRatio: 0.35},
                tooltipOptions: {formatTooltipY: value => this.number(value, ` ${__("breakdowns")}`, 0)}});
            this.renderRanking(rows);
        }
        const q = this.data.quality;
        this.root.find(".pm-quality").text(`${__("Data quality")}: ${q.invalid_repairs} ${__("open/invalid repair intervals")}; ${q.invalid_meter_rows} ${__("invalid meter rows")}; ${q.conflicting_hour_groups} ${__("conflicting shifts")}; ${q.missing_asset_breakdowns} ${__("events without a machine link, excluded from ranking")}; ${q.invalid_start_times} ${__("missing breakdown start times")}.`);
    }

    renderRanking(rows) {
        const metrics = row => [
            [__("Breakdown Hours"), this.number(row.breakdown_hours, " h")],
            [__("Breakdowns"), this.number(row.breakdowns, "", 0)],
            [__("MTBF"), this.number(row.score_mtbf, " h")],
            [__("MTTR"), this.number(row.mttr, " h")],
            [__("BDFR"), this.number(row.bdfr, " / 1,000 h")],
            [__("Repeat Rate"), this.number(row.repeat_rate, "%")]
        ];
        this.root.find(".pm-table-wrap").html(`<table class="pm-table"><thead><tr>
            <th>${__("Rank")}</th><th>${__("Machine")}</th><th>${__("Problem Score")}</th>
            ${metrics(rows[0]).map(([label]) => `<th>${label}</th>`).join("")}<th>${__("Main Recurring Problem")}</th></tr></thead>
            <tbody>${rows.map(row => `<tr class="${row.rank === 1 ? "pm-first" : ""}"><td>#${row.rank}</td>
            <td><strong>${this.escape(row.asset_label)}</strong><small>${this.escape(row.asset)}</small></td>
            <td><strong>${this.number(row.problem_score)}</strong><small>${this.escape(this.coverage(row))}</small></td>
            ${metrics(row).map(([, value]) => `<td>${this.escape(value)}</td>`).join("")}
            <td class="pm-problem">${this.problem(row)}</td></tr>`).join("")}</tbody></table>`);
        this.root.find(".pm-cards").html(rows.map(row => `<article class="pm-card ${row.rank === 1 ? "pm-first" : ""}">
            <div class="pm-card-head"><h3>#${row.rank} ${this.escape(row.asset_label)}</h3><span>${__("Problem Score")}<strong>${this.number(row.problem_score)}</strong></span></div>
            <div class="pm-coverage">${this.escape(this.coverage(row))}</div><dl>${metrics(row).map(([label, value]) =>
                `<div><dt>${label}</dt><dd>${this.escape(value)}</dd></div>`).join("")}</dl>
            <div class="pm-main-problem"><span>${__("Main Recurring Problem")}</span><strong>${this.problem(row)}</strong></div></article>`).join(""));
    }
}
