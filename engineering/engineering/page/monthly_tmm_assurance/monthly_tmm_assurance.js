frappe.pages['monthly-tmm-assurance'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __('Monthly TMM Assurance'), single_column: true});
    wrapper.monthly_tmm_assurance = new MonthlyTMMAssurance(page);
};

class MonthlyTMMAssurance {
    constructor(page) {
        this.page = page;
        this.method = 'engineering.engineering.page.monthly_tmm_assurance.monthly_tmm_assurance.';
        this.sequence = 0;
        this.dirty = false;
        this.busy = false;
        this.initializing = true;
        this.site = page.add_field({fieldname: 'site', label: __('Site'), fieldtype: 'Link', options: 'Location',
            reqd: 1, change: () => this.filters_changed()});
        const previous = frappe.datetime.add_months(frappe.datetime.month_start(), -1).slice(0, 7);
        this.month = page.add_field({fieldname: 'reporting_month', label: __('Reporting Month'), fieldtype: 'Data',
            reqd: 1, change: () => { this.update_month_navigation(); return this.filters_changed(); }});
        this.latest_month = previous;
        $(page.wrapper).addClass('monthly-tmm-assurance-page');
        this.month.$input.attr({type: 'month', max: previous, 'aria-label': __('Reporting month')});
        this.month.$input.wrap('<div class="tmm-month-navigation"></div>');
        this.month_previous = $('<button type="button" class="btn btn-default" aria-label="Previous month" title="Previous month">‹</button>');
        this.month_next = $('<button type="button" class="btn btn-default" aria-label="Next month" title="Next month">›</button>');
        this.month.$input.before(this.month_previous).after(this.month_next);
        this.month_previous.on('click', () => this.move_month(-1));
        this.month_next.on('click', () => this.move_month(1));
        this.body = $('<div class="monthly-tmm-assurance"></div>').appendTo(page.main);
        page.set_primary_action(__('Download Presentation'), () => this.download_presentation(), 'download');
        page.set_secondary_action(__('Save Actions'), () => this.save(), 'save');
        this.before_unload = event => {
            if (this.dirty) { event.preventDefault(); event.returnValue = ''; }
        };
        window.addEventListener('beforeunload', this.before_unload);
        // Desk navigation retains the page instance and its unsaved draft. Returning
        // to the page restores the draft; browser reload/close prompts above.
        this.ready = Promise.resolve(this.month.set_value(previous)).then(() => { this.initializing = false; });
        this.body.html('<p class="text-muted">Select Site to load Monthly TMM Assurance.</p>');
    }


    update_month_navigation() {
        if (!this.month_next) return;
        const value = this.month.get_value();
        this.month_previous.prop('disabled', !value || this.busy);
        this.month_next.prop('disabled', !value || value >= this.latest_month || this.busy);
    }

    move_month(offset) {
        if (this.busy || this.confirming) return;
        const value = this.month.get_value();
        if (!/^\d{4}-\d{2}$/.test(value || '')) return;
        const target = frappe.datetime.add_months(value + '-01', offset).slice(0, 7);
        if (target <= this.latest_month) this.month.set_value(target);
    }

    values() { return {site: this.site.get_value(), reporting_month: this.month.get_value()}; }
    esc(value) { return frappe.utils.escape_html(String(value ?? '')); }
    percent(value) { return value === null || value === undefined ? 'N/A' : `${Number(value).toFixed(2)}%`; }
    group() { return this.data?.groups.find(g => g.group === this.selected); }
    mark_dirty() {
        this.dirty = true;
        this.body.find('.tmm-state').text(__('Unsaved actions'));
    }

    async confirm_discard() {
        if (!this.dirty) return true;
        return new Promise(resolve => frappe.confirm(__('Discard unsaved actions?'), () => resolve(true), () => resolve(false)));
    }

    async filters_changed() {
        if (this.initializing) return;
        const next = this.values();
        if (this.busy || this.confirming) { this.restore_filters(); return; }
        this.confirming = true;
        const discard = await this.confirm_discard();
        this.confirming = false;
        if (!discard) { this.restore_filters(); return; }
        this.dirty = false;
        this.context = next;
        this.load();
    }

    async restore_filters() {
        if (!this.context) return;
        this.initializing = true;
        try {
            await Promise.all([this.site.set_value(this.context.site), this.month.set_value(this.context.reporting_month)]);
        } finally {
            this.initializing = false;
            this.update_month_navigation();
        }
    }

    async load() {
        const args = this.values();
        const sequence = ++this.sequence;
        this.data = null;
        if (!args.site || !args.reporting_month) {
            this.body.html('<p class="text-muted">Select Site and Reporting Month.</p>'); return;
        }
        this.body.html('<p class="text-muted">Loading monthly assurance…</p>');
        try {
            const response = await frappe.call({method: this.method + 'get_report', args});
            if (sequence !== this.sequence) return;
            this.data = response.message;
            this.data.groups = this.data.groups.filter(group => group.group !== 'FELs');
            this.context = args;
            this.selected = (this.data.groups.find(g => g.pareto.length || g.actions.length || g.availability.some(v => v !== null)) || this.data.groups[0]).group;
            this.render();
        } catch (error) {
            if (sequence !== this.sequence) return;
            this.body.html('<div class="alert alert-danger">Unable to load Monthly TMM Assurance. Check access and filters, then retry.</div>');
            this.data = null;
        }
    }

    render() {
        const d = this.data;
        this.body.html(`${(d.warnings || []).map(w => `<p class="text-warning">${this.esc(w)}</p>`).join('')}
            <section class="tmm-section"><h3>1. Availability by equipment group</h3>
            <div class="tmm-chart tmm-availability">${d.availability_chart}</div>
            </section>
            <div class="tmm-details"></div>${d.groups.some(g => g.group === 'Ancillary') ? '<button class="btn btn-default tmm-legacy-actions">Historical Ancillary actions</button>' : ''}`);
        this.body.find('[data-group]').on('click keydown', event => {
            if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
            event.preventDefault();
            if (this.busy) return;
            this.selected = event.currentTarget.dataset.group;
            this.show_all = false;
            this.render_details();
        });
        this.body.find('.tmm-legacy-actions').on('click', () => { if (this.busy) return; this.selected = 'Ancillary'; this.render_details(); });
        this.render_details();
    }

    records_table(records, add_action=true) {
        if (!records.length) return '<p class="text-muted">No breakdown records in this selection.</p>';
        return `<table class="tmm-breakdowns"><thead><tr><th>Failure Classification</th><th>Machine</th><th>Breakdown Reference</th><th>Reported Date</th><th>Description</th><th>Status (current)</th><th>Adjusted hours</th><th>Elapsed overlap (h)</th><th>Review</th>${add_action ? '<th></th>' : ''}</tr></thead><tbody>${records.map(r => `<tr>
            <td>${this.esc(r.failure_classification || 'Missing classification')}</td><td>${this.esc(r.asset_name)}</td>
            <td><a href="/app/plant-breakdown-or-maintenance/${encodeURIComponent(r.name)}" target="_blank" rel="noopener">${this.esc(r.name)}</a></td>
            <td>${this.esc(r.breakdown_start_datetime)}</td><td>${this.esc(r.breakdown_reason)}</td><td>${this.esc(r.status_label)}</td><td>${r.downtime_hours === null || r.downtime_hours === undefined ? 'N/A' : Number(r.downtime_hours).toFixed(2)}</td><td>${r.elapsed_overlap_hours === null || r.elapsed_overlap_hours === undefined ? 'N/A' : Number(r.elapsed_overlap_hours).toFixed(2)}</td><td>${this.esc(r.timestamp_review || r.review_reason)}</td>
            ${add_action && this.group()?.can_write ? `<td><button class="btn btn-default btn-xs tmm-action-for-record" data-reference="${this.esc(r.name)}">Add action</button></td>` : ''}</tr>`).join('')}</tbody></table>`;
    }

    bind_record_actions() {
        this.body.find('.tmm-action-for-record').off('click').on('click', event => {
            if (this.busy) return;
            const g = this.group();
            const records = [...g.counts.all_categories.flatMap(c => c.records), ...g.counts.unresolved_records];
            const record = records.find(r => r.name === event.currentTarget.dataset.reference);
            if (!record || !g.can_write) return;
            g.actions.push({cause: this.data.failure_classifications.includes(record.failure_classification) ? record.failure_classification : '',
                action: '', owner_name: '', due_date: '', status: 'Open', breakdown_reference: record.name});
            g.dirty = true; this.mark_dirty(); this.render_actions();
        });
    }

    hours(value) { return `${Number(value || 0).toFixed(2)} h`; }

    report_date(value) {
        if (!value) return 'Unavailable';
        return new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'})
            .format(new Date(`${String(value).slice(0, 10)}T00:00:00Z`));
    }

    // Screen drawing only: hours, order, priority membership and cumulative
    // percentages are supplied by the canonical report, including its full denominator.
    pareto_chart(counts) {
        const rows = this.show_all ? counts.categories : counts.categories.slice(0, 10);
        if (!rows.length) return '<p class="tmm-empty text-muted">No classified planning-adjusted breakdown downtime for this MPP period.</p>';
        const width = Math.max(760, rows.length * 96 + 135);
        const left = 65, right = width - 65, top = 35, bottom = 245;
        const step = (right - left) / rows.length;
        const maximum = Math.max(...rows.map(row => row.hours)) * 1.22;
        const y_hours = hours => bottom - (bottom - top) * hours / maximum;
        const y_percent = percent => bottom - (bottom - top) * percent / 100;
        const labels = rows.map(row => {
            const words = String(row.category).match(/.{1,15}(?:\s|$)|.{1,15}/g) || [''];
            return words.map(word => word.trim());
        });
        const height = bottom + Math.max(...labels.map(lines => lines.length)) * 15 + 35;
        const points = rows.map((row, i) => [left + step * (i + .5), y_percent(row.cumulative_percent)]);
        return `<svg class="tmm-pareto-svg" width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Planning-adjusted downtime by classification and cumulative percentage">
            <title>Classified downtime Pareto.</title>
            ${Array.from({length: 6}, (_, i) => {
                const y = bottom - (bottom - top) * i / 5;
                return `<path class="tmm-grid-line" d="M${left} ${y}H${right}"/><text x="${left - 10}" y="${y + 4}" text-anchor="end">${(maximum * i / 5).toFixed(1)}</text><text x="${right + 10}" y="${y + 4}">${i * 20}%</text>`;
            }).join('')}
            ${rows.map((row, i) => {
                const [x, cy] = points[i], y = y_hours(row.hours);
                const label_y = Math.abs(cy - y) < 26 ? y + 18 : y - 8;
                return `<rect class="tmm-pareto-bar ${row.priority ? 'is-priority' : ''}" x="${x - step * .35}" y="${y}" width="${step * .7}" height="${bottom - y}" rx="2"><title>${this.esc(row.category)}: ${this.hours(row.hours)}</title></rect>
                    <text class="tmm-bar-value" x="${x}" y="${label_y}" text-anchor="middle">${this.hours(row.hours)}</text>
                    <text x="${x}" y="${bottom + 21}" text-anchor="middle">${labels[i].map((line, index) => `<tspan x="${x}" dy="${index ? 15 : 0}">${this.esc(line)}</tspan>`).join('')}</text>`;
            }).join('')}
            <path class="tmm-reference-line" d="M${left} ${y_percent(80)}H${right}"/>
            <polyline class="tmm-cumulative-line" points="${points.map(point => point.join(',')).join(' ')}"/>
            ${rows.map((row, i) => `<circle class="tmm-pareto-point" cx="${points[i][0]}" cy="${points[i][1]}" r="4" data-percent="${row.cumulative_percent}"><title>${this.esc(row.category)}: ${this.percent(row.cumulative_percent)} cumulative</title></circle>`).join('')}
            <text class="tmm-axis-title" transform="translate(15 140) rotate(-90)" text-anchor="middle">Downtime (hours)</text>
            <text class="tmm-axis-title" transform="translate(${width - 10} 140) rotate(-90)" text-anchor="middle">Cumulative %</text>
        </svg>`;
    }

    problems_table(priority) {
        const gear = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z"/><path d="m19.4 13 .1-2 2-1.5-2-3.4-2.4 1a7.5 7.5 0 0 0-1.7-1L15 3h-4l-.4 3.1a7.5 7.5 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.5a7.9 7.9 0 0 0 0 2l-2 1.5 2 3.4 2.4-1a7.5 7.5 0 0 0 1.7 1L11 21h4l.4-3.1a7.5 7.5 0 0 0 1.7-1l2.4 1 2-3.4-2.1-1.5Z"/></svg>`;
        const hydraulicIcon = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3S6.5 10 6.5 14.2a5.5 5.5 0 0 0 11 0C17.5 10 12 3 12 3Z"/><path d="M9.5 15.5a2.8 2.8 0 0 0 2.5 2"/></svg>`;
        const brakeIcon = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3.5"/><path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M16 5.5l2-2"/></svg>`;

        return `<div class="tmm-problem-cards">
            ${priority.map((row, index) => {
                const matches = row.subcategories || [];
                const leading = matches[0];
                const review = row.subcategory_review_records || [];
                const hydraulic = /hydraulic/i.test(row.category || '');
                const braking = /brak/i.test(row.category || '');
                const icon = hydraulic ? hydraulicIcon : braking ? brakeIcon : gear;
                const iconClass = hydraulic ? 'hydraulic' : braking ? 'braking' : 'mechanical';

                return `<article class="tmm-problem-card">
                    <div class="tmm-problem-classification">
                        <span class="tmm-problem-icon tmm-problem-icon--${iconClass}">${icon}</span>
                        <div class="tmm-problem-classification-text">
                            <span class="tmm-problem-label">Classification</span>
                            <strong>${this.esc(row.category)}</strong>
                        </div>
                    </div>

                    <div class="tmm-problem-main">
                        <span class="tmm-problem-label">Most frequent problem</span>
                        <strong class="tmm-problem-name">${leading ? this.esc(leading.subcategory) : '<span class="text-muted">No approved subcategory match — review descriptions.</span>'}</strong>
                        ${review.length ? `<details class="tmm-description-review"><summary>Description / timestamp review: ${review.length} events · ${this.hours(row.subcategory_review_hours)} known</summary><div class="table-responsive">${this.records_table(review, false)}</div></details>` : ''}
                    </div>

                    <div class="tmm-problem-action">
                        ${matches.length ? `<button type="button" class="btn btn-default btn-xs tmm-top-three" aria-expanded="false" aria-controls="tmm-subcategories-${index}">View top 3</button>
                        <div id="tmm-subcategories-${index}" class="tmm-subcategory-detail" hidden>
                            <table><thead><tr><th>Matched subcategory</th><th>Events</th><th>Downtime</th></tr></thead>
                            <tbody>${matches.map(sub => `<tr><td>${this.esc(sub.subcategory)}</td><td>${sub.count}</td><td>${this.hours(sub.hours)}</td></tr>`).join('')}</tbody></table>
                            ${matches.length < 3 ? '<p class="text-muted">Fewer than three matched subcategories.</p>' : ''}
                        </div>` : ''}
                    </div>

                    <div class="tmm-problem-stats">
                        <div class="tmm-problem-stat">
                            <span>Events</span>
                            <strong>${leading ? leading.count : '—'}</strong>
                        </div>
                        <div class="tmm-problem-stat">
                            <span>Downtime</span>
                            <strong>${leading ? this.hours(leading.hours) : '—'}</strong>
                        </div>
                    </div>
                </article>`;
            }).join('') || '<p class="tmm-empty text-muted">No priority classifications with measured downtime in this MPP period.</p>'}
        </div>`;
    }

    render_details() {
        const g = this.group(), c = g.counts;
        const priority = c.all_categories.filter(row => row.priority);
        const period = this.data.selected_period;
        this.body.find('.tmm-availability [data-group]').each((_, row) => {
            const selected = row.dataset.group === this.selected;
            $(row).toggleClass('is-selected', selected).attr('aria-pressed', String(selected));
            $(row).find('.tmm-group-highlight').attr('opacity', selected ? '1' : '0');
        });
        this.body.find('.tmm-details').html(`<header class="tmm-assurance-heading"><h2>Breakdown assurance</h2><p>${this.esc(this.data.site)} · ${this.esc(this.data.month_label)}</p></header>
            <div class="tmm-selection-row"><div class="tmm-tabs" role="tablist" aria-label="Breakdown equipment group">${['ADTs', 'Excavators', 'Dozers'].filter(name => this.data.groups.some(group => group.group === name)).map(name => `<button type="button" role="tab" id="tmm-tab-${name}" class="tmm-tab ${g.group === name ? 'is-selected' : ''}" data-group="${name}" aria-selected="${g.group === name}" aria-controls="tmm-group-panel" tabindex="${g.group === name ? 0 : -1}">${name}</button>`).join('')}</div>
            <p class="tmm-period">MPP reporting period: ${this.esc(this.report_date(period.start))} – ${this.esc(this.report_date(period.end))}</p></div>
            <div id="tmm-group-panel" role="tabpanel" aria-label="${this.esc(g.group)} breakdown assurance">
            ${!['ADTs', 'Excavators', 'Dozers'].includes(g.group) ? `<h3>${this.esc(g.group)}</h3>` : ''}
            <div class="tmm-summary-cards">
                <div class="tmm-summary-card"><span>Classified breakdown downtime</span><strong>${this.hours(c.classified_hours)}</strong><small>Planning-adjusted</small></div>
                <div class="tmm-summary-card"><span>Total eligible breakdown events</span><strong>${c.total_count}</strong></div>
                <div class="tmm-summary-card"><span>First 80% priority set</span><strong>${c.priority_category_count} classifications</strong><small>${this.percent(c.priority_percent)} of classified downtime</small></div>
            </div>
            <div class="tmm-analysis-row"><section class="tmm-section tmm-pareto"><h3>Downtime by failure classification</h3>
                <div class="tmm-chart-legend"><span><i class="tmm-legend-bar"></i>Downtime (hours)</span><span><i class="tmm-legend-line"></i>Cumulative %</span><span><i class="tmm-legend-reference"></i>80% reference</span></div>
                <div class="tmm-chart">${this.pareto_chart(c)}</div>
                ${c.omitted_categories ? `<p class="tmm-chart-note text-muted">Top 10: ${c.omitted_categories} omitted classifications · ${this.hours(c.omitted_hours)} remain in the denominator. ${c.priority_category_count > 10 ? `${c.priority_category_count - 10} additional priority classifications are beyond the top 10. ` : ''}<button type="button" class="btn btn-link btn-xs tmm-toggle-categories">${this.show_all ? 'Show top 10' : 'Show all classifications'}</button></p>` : ''}
            </section><aside class="tmm-section tmm-focus"><h3>Where to focus</h3>
                ${priority.length ? `<p class="tmm-focus-summary">${c.priority_category_count} classifications account for <strong>${this.percent(c.priority_percent)}</strong> of classified downtime.</p><ol class="tmm-focus-list">${priority.map((row, index) => `<li><span class="tmm-focus-rank">${index + 1}</span><span>${this.esc(row.category)}</span><span class="tmm-focus-hours">${this.hours(row.hours)}</span></li>`).join('')}</ol>` : '<p class="tmm-empty text-muted">No classified downtime to prioritise.</p>'}
            </aside></div>
            <section class="tmm-section"><h3>Most frequent problems in priority classifications</h3><p class="text-muted">Configured subcategories ranked by distinct breakdown-event frequency; downtime uses the same MPP period.</p>${this.problems_table(priority)}</section>
            <section class="tmm-section"><div class="tmm-actions-heading"><h3>Corrective actions</h3>
                <button type="button" class="btn btn-default btn-sm tmm-add" ${g.can_write ? '' : 'disabled'}>+ Add Action</button></div>
                ${g.can_write ? '' : '<p class="text-muted">Read-only: corrective actions cannot be edited with your current access.</p>'}
                <div class="table-responsive"><table class="tmm-actions-table"><thead><tr><th>Classification</th><th>Action</th><th>Owner</th><th>Due</th><th>Status</th></tr></thead><tbody></tbody></table></div>
                <div class="tmm-state text-muted" role="status">${this.dirty ? 'Unsaved actions' : ''}</div></section>
            <details class="tmm-section tmm-records"><summary>View breakdown records</summary><p class="text-muted">${this.esc(this.data.population)}. ${this.esc(this.data.status_basis || '')}</p>
                <details class="tmm-priority"><summary>Breakdowns contributing to the first 80% (${c.priority_records.length})</summary><div class="table-responsive">${this.records_table(c.priority_records)}</div></details>
                <details class="tmm-all-categories"><summary>All classifications — inspect breakdown records</summary><div class="table-responsive"><table class="tmm-category-list"><thead><tr><th>Classification</th><th>Events</th><th>Downtime</th><th>80% priority</th></tr></thead><tbody>${c.all_categories.map(row => `<tr><td><button type="button" class="btn btn-link btn-xs tmm-inspect-category" data-category="${this.esc(row.category)}">${this.esc(row.category)}</button></td><td>${row.count}</td><td>${this.hours(row.hours)}</td><td>${row.priority ? 'Priority' : ''}</td></tr>`).join('')}</tbody></table></div><div class="tmm-category-records"></div></details>
            </details></div>`);
        this.render_actions();
        this.bind_record_actions();
        this.body.find('.tmm-tab').on('click', event => {
            if (this.busy) return;
            this.selected = event.currentTarget.dataset.group;
            this.show_all = false;
            this.render_details();
            this.body.find('.tmm-tab.is-selected').trigger('focus');
        }).on('keydown', event => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            const tabs = this.body.find('.tmm-tab'), index = tabs.index(event.currentTarget);
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
            tabs.eq(next).trigger('click');
        });
        this.body.find('.tmm-top-three').on('click', event => {
            const button = $(event.currentTarget), expanded = button.attr('aria-expanded') === 'true';
            button.attr('aria-expanded', String(!expanded)).text(expanded ? 'View top 3' : 'Hide top 3');
            button.next('.tmm-subcategory-detail').prop('hidden', expanded);
        });
        this.body.find('.tmm-toggle-categories').on('click', () => { this.show_all = !this.show_all; this.render_details(); });
        this.body.find('.tmm-inspect-category').on('click', event => {
            const category = event.currentTarget.dataset.category;
            const records = c.all_categories.find(row => row.category === category).records;
            this.body.find('.tmm-category-records').html(`<h4>${this.esc(category)} (${records.length})</h4><div class="table-responsive">${this.records_table(records)}</div>`);
            this.bind_record_actions();
        });
        this.body.find('.tmm-add').on('click', () => {
            if (this.busy || !g.can_write) return;
            g.actions.push({cause: '', action: '', owner_name: '', due_date: '', status: 'Open', breakdown_reference: ''});
            g.dirty = true; this.mark_dirty(); this.render_actions();
        });
    }

    render_actions() {
        const g = this.group();
        const disabled = !g.can_write || this.busy ? 'disabled' : '';
        const input = (key, value, type='text') => `<input class="form-control input-sm" type="${type}" data-field="${key}" aria-label="${this.esc(key.replace('_', ' '))}" value="${this.esc(value)}" ${disabled}>`;
        const category_select = a => `<select class="form-control input-sm" data-field="cause" aria-label="Category" ${disabled}><option value="">Select category…</option>${a.cause && !this.data.failure_classifications.includes(a.cause) ? `<option value="${this.esc(a.cause)}" selected>${this.esc(a.cause)} (legacy — review)</option>` : ''}${this.data.failure_classifications.map(c => `<option value="${this.esc(c)}" ${a.cause === c ? 'selected' : ''}>${this.esc(c)}</option>`).join('')}</select>`;
        const rows = g.actions.map((a, i) => `<tr data-index="${i}"><td>${category_select(a)}</td>
            <td><textarea class="form-control input-sm" data-field="action" aria-label="Action" ${disabled}>${this.esc(a.action)}</textarea>
                <details class="tmm-action-secondary"><summary>Action details${a.breakdown_reference ? ` · ${this.esc(a.breakdown_reference)}` : ''}</summary>
                    <label>Breakdown reference (optional)${input('breakdown_reference', a.breakdown_reference)}</label>
                    <button type="button" class="btn btn-default btn-xs tmm-remove" aria-label="Remove action ${i+1}" ${disabled}>Remove action</button></details></td>
            <td>${input('owner_name', a.owner_name)}</td><td>${input('due_date', a.due_date, 'date')}</td>
            <td><select class="form-control input-sm" data-field="status" aria-label="Status" ${disabled}>${['Open','In progress','Completed'].map(s => `<option ${a.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></td>
            </tr>`).join('');
        this.body.find('.tmm-actions-table tbody').html(rows || '<tr><td colspan="5" class="text-muted">No saved corrective actions.</td></tr>');
        this.body.find('[data-field]').on('input change', event => {
            if (this.busy || !g.can_write) return;
            const row = Number($(event.currentTarget).closest('tr').attr('data-index'));
            g.actions[row][event.currentTarget.dataset.field] = event.currentTarget.value;
            g.dirty = true; this.mark_dirty();
        });
        this.body.find('.tmm-remove').on('click', event => {
            if (this.busy || !g.can_write) return;
            const row = Number($(event.currentTarget).closest('tr').attr('data-index'));
            g.actions.splice(row, 1); g.dirty = true; this.mark_dirty(); this.render_actions();
        });
    }

    async save() {
        if (this.busy || !this.data) return false;
        const dirty = this.data.groups.filter(g => g.dirty);
        if (!dirty.length) { frappe.show_alert(__('No unsaved actions')); return true; }
        this.busy = true;
        this.render_actions();
        try {
            for (const g of dirty) {
                const response = await frappe.call({method: this.method + 'save_actions', type: 'POST',
                    args: {...this.context, equipment_group: g.group, actions: JSON.stringify(g.actions), version: g.version}});
                Object.assign(g, response.message, {dirty: false});
            }
            this.dirty = this.data.groups.some(g => g.dirty);
            this.body.find('.tmm-state').text(__('Actions saved'));
            frappe.show_alert({message: __('Actions saved'), indicator: 'green'});
            return true;
        } catch (error) {
            this.dirty = this.data.groups.some(g => g.dirty);
            this.body.find('.tmm-state').text(__('Save failed. Your unsaved actions are retained.'));
            return false;
        } finally {
            this.busy = false;
            this.render_actions();
        }
    }

    async download_presentation() {
        if (this.busy || !this.data) return;
        if (this.dirty && !(await this.save())) return;
        const url = '/api/method/' + this.method + 'download_presentation?' + $.param(this.context);
        window.open(url, '_blank', 'noopener');
    }
}
