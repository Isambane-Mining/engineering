/* Shared Machine Reliability dashboard. All data access uses the existing APIs. */
frappe.provide('engineering');
engineering.MachineReliabilityDashboard = class MachineReliabilityDashboard {
    constructor(wrapper, main = null) {
        this.wrapper = wrapper;
        this.page = main ? {main: $(main)} : frappe.ui.make_app_page({parent: wrapper, title: __('Machine Reliability'), single_column: true});
        this.root = this.page.main.addClass('mr-page');
        this.api = 'engineering.engineering.page.machine_reliability.machine_reliability.';
        this.token = 0;
        this.mode = 'date';
        this.initializing = true;
        this.initialize();
    }

    e(value) { return frappe.utils.escape_html(String(value == null ? '' : value)); }
    n(value, unit = '') { return value == null ? 'Not recorded' : Number(value).toLocaleString(undefined, {maximumFractionDigits: 2}) + unit; }
    empty(text = 'No matching records for these filters.') { return `<div class="mr-empty">${__(text)}</div>`; }
    async call(method, args = {}) { return (await frappe.call({method: this.api + method, args})).message; }

    async initialize() {
        try {
            await frappe.require('/assets/engineering/css/machine_reliability.css');
            this.build();
            const options = await this.call('get_options');
            this.fields.category.df.options = ['All Problems', ...options.categories.map(x => x.category)];
            this.fields.category.refresh();
            const today = frappe.datetime.get_today();
            await this.fields.from_date.set_value(frappe.datetime.add_days(today, -30));
            await this.fields.to_date.set_value(today);
            await this.fields.category.set_value(options.categories.some(x => x.category === 'Brakes') ? 'Brakes' : 'All Problems');
            this.initializing = false;
            await this.load();
        } catch (error) {
            this.root.find('.mr-status').text(__('Unable to open Machine Reliability. Check your access and try again.'));
        }
    }

    build() {
        this.root.html(`<div class="mr-shell">
            <header class="mr-header"><div><span class="mr-eyebrow">ENGINEERING / MACHINE HISTORY</span>
            <h1>${__('Machine Reliability')}</h1><p>${__('Reported faults, repair work, tests and services')}</p></div>
            <a class="btn btn-default btn-sm" href="/app/machine-reliability-settings">${__('Category settings')}</a></header>
            <div class="mr-filter-panel"><div class="mr-filters"></div><button type="button" class="mr-refresh btn btn-primary btn-sm">${__('Refresh')}</button></div>
            <div class="mr-status" role="status" aria-live="polite"></div>
            <section id="mr-overview" role="region" aria-label="Machine reliability overview"><div class="mr-cards"></div>
                <div class="mr-panel"><div class="mr-panel-head"><div><h2>${__('Machine timeline')}</h2><p>${__('Select a marker for the source record and full details.')}</p></div>
                <div class="mr-mode" role="group" aria-label="${__('Timeline scale')}"><button class="btn btn-default btn-sm active" data-mode="date" aria-pressed="true">${__('By Date')}</button><button class="btn btn-default btn-sm" data-mode="hours" aria-pressed="false">${__('By Machine Hours')}</button></div></div>
                <div class="mr-legend"><span class="failure">${__('Direct failure')}</span><span class="additional">${__('Additional / planned work')}</span><span class="test">${__('Inspection / test')}</span><span class="service">${__('Service')}</span></div>
                <div class="mr-timeline-note"></div><div class="mr-timeline"></div><div class="mr-unpositioned"></div></div>
                <div class="mr-quality mr-panel"></div></section>
            <footer class="mr-footnote">${__('Selected categories identify reported complaints. Blank categories use keyword matches. Resolution-only matches show additional repair work. They do not confirm a diagnosis or accident root cause. Dates use the historical record site; asset categories use the current Asset master. Records without a date cannot appear in this dated report.')}</footer>
            </div>`);
        this.fields = {};
        const definitions = [
            ['from_date', 'From Date', 'Date'], ['to_date', 'To Date', 'Date'], ['site', 'Site', 'Link', 'Location'],
            ['asset_category', 'Asset Category', 'Link', 'Asset Category'], ['fleet', 'Fleet Number', 'Link', 'Asset'],
            ['category', 'Problem Category', 'Select', ['All Problems']], ['additional_keywords', 'Additional Keywords', 'Data']
        ];
        definitions.forEach(([name, label, type, options]) => {
            const parent = $('<div>').appendTo(this.root.find('.mr-filters'));
            this.fields[name] = frappe.ui.form.make_control({parent, render_input: true, df: {
                fieldname: name, label: __(label), fieldtype: type, options,
                reqd: ['from_date', 'to_date'].includes(name),
                placeholder: name === 'additional_keywords' ? __('Comma-separated words or phrases') : undefined,
                onchange: async () => {
                    if (this.initializing) return;
                    if (['site', 'asset_category', 'from_date', 'to_date'].includes(name)) {
                        this.initializing = true;
                        await this.fields.fleet.set_value('');
                        this.initializing = false;
                    }
                    this.load();
                }
            }});
        });
        this.fields.fleet.get_query = () => ({query: this.api + 'get_fleets', filters: this.filters()});
        this.root.on('click', '.mr-refresh', () => this.load());
        this.root.on('click', '[data-mode]', event => {
            this.mode = event.currentTarget.dataset.mode;
            this.root.find('[data-mode]').each((_, element) => $(element).toggleClass('active', element.dataset.mode === this.mode).attr('aria-pressed', String(element.dataset.mode === this.mode)));
            this.renderTimeline();
        });
        this.root.on('click', '[data-record]', event => {
            const record = this.recordMap.get(event.currentTarget.dataset.record);
            if (record) this.showRecord(record);
        });

    }

    filters() {
        const values = Object.fromEntries(Object.entries(this.fields).map(([key, field]) => [key, field.get_value()]));
        if (values.category === 'All Problems') values.category = '';
        return values;
    }

    async load() {
        if (this.initializing) return;
        const token = ++this.token, filters = this.filters();
        this.data = null;
        this.recordMap = new Map();
        this.root.find('#mr-overview').attr('aria-busy', 'true');
        this.root.find('.mr-refresh').prop('disabled', true);
        if (!filters.from_date || !filters.to_date || filters.from_date > filters.to_date) {
            this.root.find('.mr-status').text(__('Enter a valid date range.'));
            this.clearResults();
            this.root.find('#mr-overview').attr('aria-busy', 'false');
            this.root.find('.mr-refresh').prop('disabled', false);
            return;
        }
        this.root.find('.mr-status').text(__('Loading live ERP records…'));
        this.clearResults();
        try {
            const data = await this.call('get_dashboard', filters);
            if (token !== this.token) return;
            this.data = data;
            this.render();
        } catch (error) {
            if (token !== this.token) return;
            this.root.find('.mr-status').text(__('Unable to load this report. Check the filters, your permissions and any message shown.'));
        } finally {
            if (token === this.token) {
                this.root.find('#mr-overview').attr('aria-busy', 'false');
                this.root.find('.mr-refresh').prop('disabled', false);
            }
        }
    }

    clearResults() {
        this.root.find('.mr-cards,.mr-timeline,.mr-unpositioned,.mr-timeline-note,.mr-quality').empty();
    }

    render() {
        const d = this.data, s = d.summary;
        const records = d.timeline;
        records.forEach(record => this.recordMap.set(record.doctype + ':' + record.name, record));
        this.root.find('.mr-status').text(`${d.scope.from_date} — ${d.scope.to_date} · ${d.scope.category} · ${this.n(s.direct_failures)} ${__('direct failures')} · ${this.n(s.additional_work)} ${__('additional work records')} · ${this.n(s.planned_work)} ${__('planned work records')}`);
        const cards = [
            ['Matching records', s.problem_records, '', 'Breakdown and maintenance records'],
            ['Average hours between failures', s.average_failure_gap, ' h', `${s.valid_intervals} valid gaps · calculated per machine`],
            ['Average standing time', s.average_standing_hours, ' h', `${s.standing_records} completed breakdowns · includes overlaps`],
            ['Tests and inspections', s.tests, '', 'Recorded tests for this problem'],
            ['Services recorded', s.services, '', 'Service records for these machines'],
            ['Standing time without overlaps', s.unique_standing_hours, ' h', 'Completed breakdowns within these dates']
        ];
        this.root.find('.mr-cards').html(cards.map(([label, value, unit, help]) => `<div class="mr-card"><span>${__(label)}</span><strong>${value == null ? '—' : this.n(value, unit)}</strong><small>${this.e(__(help))}</small></div>`).join(''));
        const q = d.quality;
        this.root.find('.mr-quality').html(`<h2>${__('Data checks')}</h2><div class="mr-checks"><span>${this.n(q.overlapping_records)} ${__('overlapping records')}</span><span>${this.n(q.reversed_intervals)} ${__('reversed intervals')}</span><span>${this.n(q.incomplete_intervals)} ${__('incomplete intervals')}</span><span>${this.n(q.missing_readings)} ${__('direct failures without valid readings')}</span><span>${this.n(q.invalid_gaps)} ${__('excluded hour gaps')}</span></div>
            <details class="mr-calculation-help"><summary>${__('How the figures are calculated')}</summary><p>${__('Data checks cover all faults in the selected scope. Average standing time uses completed breakdown durations, including overlaps. Reversed and incomplete durations are excluded. Standing time without overlaps counts each completed period once per machine, within these dates. Averages show — when no eligible records exist.')}</p><p>${__('Active search terms:')} ${this.e(d.keywords.join(', ') || __('All problems'))}</p></details>`);
        this.renderTimeline();
    }

    sourceButton(row) {
        return `<button type="button" class="mr-record-link" data-record="${this.e(row.doctype + ':' + row.name)}">${__('Details')}</button>`;
    }
    table(rows, columns) {
        if (!rows.length) return this.empty();
        return `<div class="mr-table-wrap"><table class="mr-table"><thead><tr>${columns.map(([key, label]) => `<th data-column="${key}">${__(label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${columns.map(([key]) => {
            let value = row[key];
            if (key === 'source') return `<td data-column="source">${this.sourceButton(row)}</td>`;
            if (typeof value === 'number') value = this.n(value);
            const text = value == null ? '—' : String(value);
            return `<td data-column="${key}" title="${this.e(text)}">${this.e(text)}</td>`;
        }).join('')}</tr>`).join('')}</tbody></table></div>`;
    }
    renderTimeline() {
        if (!this.data) return;
        const rows = this.data.timeline, hours = this.mode === 'hours', limit = this.data.limits.timeline;
        let note = hours ? __('Each lane uses that machine’s own hour-meter scale. Readings from different machines are never combined.') : __('Each lane is one fleet number on the same date scale.');
        if (limit.total > limit.shown) note += ` ${__('Showing the first')} ${limit.shown} / ${limit.total} ${__('events. Narrow the filters for the rest; summary cards use the full scope.')}`;
        this.root.find('.mr-timeline-note').text(note);
        const visible = hours ? rows.filter(x => x.machine_hours != null) : rows;
        const missing = hours ? rows.filter(x => x.machine_hours == null) : [];
        const groups = new Map();
        visible.forEach(row => { const fleet = row.fleet || __('Unassigned'); if (!groups.has(fleet)) groups.set(fleet, []); groups.get(fleet).push(row); });
        const start = Date.parse(this.data.scope.from_date + 'T00:00:00'), end = Date.parse(this.data.scope.to_date + 'T23:59:59');
        this.root.find('.mr-timeline').html(!groups.size ? this.empty('No events with readings on this scale.') : `<div class="mr-timeline-scroll">${Array.from(groups).sort(([a], [b]) => a.localeCompare(b)).map(([fleet, events]) => {
            const values = events.map(x => hours ? x.machine_hours : Date.parse(x.date.replace(' ', 'T')));
            const low = hours ? Math.min(...values) : start, high = hours ? Math.max(...values) : end;
            const tracks = [];
            const markers = events.map((row, i) => {
                const x = high === low ? 50 : Math.max(1, Math.min(99, (values[i] - low) / (high - low) * 96 + 2));
                let track = tracks.findIndex(last => Math.abs(x - last) >= 2);
                if (track < 0) track = tracks.length;
                tracks[track] = x;
                const title = `${row.date}\n${row.fleet}\n${row.reason}\n${row.resolution || ''}\n${__('Machine hours')}: ${this.n(row.machine_hours)}\n${__('Standing hours')}: ${this.n(row.standing_hours)}\n${(row.flags || []).join('; ')}`;
                return `<button type="button" class="mr-marker ${row.event_type}" style="left:${x}%;top:${10 + track * 21}px" data-record="${this.e(row.doctype + ':' + row.name)}" title="${this.e(title)}" aria-label="${this.e(title)}"></button>`;
            }).join('');
            return `<div class="mr-lane"><div class="mr-lane-label">${this.e(fleet)}<small>${hours ? `${this.n(low)} — ${this.n(high)} h` : `${this.data.scope.from_date} — ${this.data.scope.to_date}`}</small></div><div class="mr-track" style="height:${Math.max(44, 23 + tracks.length * 21)}px">${markers}</div></div>`;
        }).join('')}</div>`);
        this.root.find('.mr-unpositioned').html(missing.length ? `<details><summary>${this.n(missing.length)} ${__('events without machine-hour readings — view by date')}</summary>${this.table(missing, [['date', 'Date'], ['fleet', 'Fleet Number'], ['reason', 'Record'], ['source', 'Source']])}</details>` : '');
    }

    showRecord(row) {
        const dialog = new frappe.ui.Dialog({title: row.event_type === 'failure' ? __('Direct failure') : row.downtime_type === 'Planned Maintenance' ? __('Planned work') : row.event_type === 'additional' ? __('Additional repair work') : __(row.sections || 'Record'), size: 'large'});
        const fields = [['Date', row.date], ['Fleet Number', row.fleet], ['Site', row.site], ['Problem Category', row.problem_category || __('Not selected')], ['Matched by', row.match_source || '—'], ['Breakdown reason / record', row.reason], ['Repair description', row.resolution || __('Not recorded')], ['Machine hours', this.n(row.machine_hours)], ['Standing hours', this.n(row.standing_hours)], ['Matched terms', (row.matched_terms || []).join(', ') || '—'], ['Interval checks', (row.flags || []).join('; ') || '—']];
        if (row.gap_status) fields.push(['Hour-gap check', row.gap_status]);
        if (row.exclude_from_au) fields.push(['A&U', __('Source record is excluded from A&U downtime')]);
        dialog.$body.html(`<dl class="mr-record-detail">${fields.map(([label, value]) => `<dt>${__(label)}</dt><dd>${this.e(value)}</dd>`).join('')}</dl><a class="btn btn-primary btn-sm" href="${frappe.utils.get_form_link(row.doctype, row.name)}">${__('Open source record')}</a>`);
        dialog.show();
    }
};
