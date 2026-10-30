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
            reqd: 1, change: () => this.filters_changed()});
        this.month.$input.attr('type', 'month');
        this.month.$input.attr('max', previous);
        this.body = $('<div class="monthly-tmm-assurance"></div>').appendTo(page.main);
        this.add_styles();
        page.set_primary_action(__('Download PDF'), () => this.download_pdf(), 'download');
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

    add_styles() {
        if ($('#monthly-tmm-assurance-style').length) return;
        $('head').append(`<style id="monthly-tmm-assurance-style">
            .monthly-tmm-assurance {width:100%;min-width:0;padding: 12px 0; color:var(--text-color)}
            .monthly-tmm-assurance .tmm-section {background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--border-radius, 6px);padding:14px 16px;margin:12px 0}
            .monthly-tmm-assurance .table-responsive {display:block;width:100%;overflow-x:auto}
            .monthly-tmm-assurance h3 {font-size:18px;margin:0 0 10px;font-weight:600}
            .monthly-tmm-assurance .tmm-subtitle {font-size:16px;margin-bottom:12px}
            .monthly-tmm-assurance table {width:100%;margin:0 0 8px;border-collapse:collapse}
            .monthly-tmm-assurance th,.monthly-tmm-assurance td {border:1px solid var(--border-color);padding:6px 12px;vertical-align:middle}
            .monthly-tmm-assurance th {background:var(--subtle-fg);font-weight:600}
            .monthly-tmm-assurance .tmm-availability td:not(:first-child),.monthly-tmm-assurance .tmm-availability th:not(:first-child) {text-align:center;width:23%}
            .monthly-tmm-assurance tr[data-group] {cursor:pointer}
            .monthly-tmm-assurance tr.is-selected {background:var(--blue-50, #e6f1ff)}
            .monthly-tmm-assurance tr[data-group]:focus {outline:2px solid var(--primary)}
            .monthly-tmm-assurance .tmm-actions-heading {display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
            .monthly-tmm-assurance .tmm-actions-heading h3 {margin:0}
            .monthly-tmm-assurance .tmm-actions-table {min-width:780px}
            .monthly-tmm-assurance .tmm-actions-table textarea {min-width:170px;resize:vertical;height:50px;min-height:50px}
            .monthly-tmm-assurance .tmm-actions-table input,.monthly-tmm-assurance .tmm-actions-table select,.monthly-tmm-assurance .tmm-actions-table textarea {width:100%;margin:0}
            .monthly-tmm-assurance .tmm-actions-table td {padding:5px}
            .monthly-tmm-assurance .tmm-chart {overflow-x:auto}
            .monthly-tmm-assurance .tmm-chart img {min-width:750px}
            .monthly-tmm-assurance details {margin:10px 0}
            .monthly-tmm-assurance summary {cursor:pointer;font-weight:600}
            .monthly-tmm-assurance .tmm-breakdowns {font-size:12px;min-width:820px}
            .monthly-tmm-assurance .tmm-breakdowns td {vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}
            .monthly-tmm-assurance .tmm-category-list {font-size:12px}
            .monthly-tmm-assurance .tmm-state {min-height:20px}
        </style>`);
    }

    values() { return {site: this.site.get_value(), reporting_month: this.month.get_value()}; }
    esc(value) { return frappe.utils.escape_html(String(value ?? '')); }
    percent(value) { return value === null || value === undefined ? 'N/A' : `${Number(value).toFixed(1)}%`; }
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
        this.body.html(`<div class="text-muted tmm-subtitle">Monthly equipment availability and downtime review</div>
            <div class="text-muted">${this.esc(d.period_label)} · Due ${this.esc(frappe.datetime.str_to_user(d.due_date))}</div>
            <section class="tmm-section"><h3>1. Availability by equipment group</h3>
            <div class="tmm-chart tmm-availability">${d.availability_chart}</div>
            <div class="text-muted">Select a group to view its breakdowns and actions. N/A means no valid data.</div></section>
            ${d.unassigned_records?.length ? `<details><summary>${d.unassigned_records.length} records require equipment-group review</summary><div class="table-responsive">${this.records_table(d.unassigned_records, false)}</div></details>` : ''}
            <div class="tmm-details"></div>`);
        this.body.find('[data-group]').on('click keydown', event => {
            if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
            event.preventDefault();
            if (this.busy) return;
            this.selected = event.currentTarget.dataset.group;
            this.show_all = false;
            this.render_details();
        });
        this.render_details();
    }

    records_table(records, add_action=true) {
        if (!records.length) return '<p class="text-muted">No breakdown records in this selection.</p>';
        return `<table class="tmm-breakdowns"><thead><tr><th>Category</th><th>Machine</th><th>Breakdown Reference</th><th>Reported Date</th><th>Description</th><th>Status (current)</th>${add_action ? '<th></th>' : ''}</tr></thead><tbody>${records.map(r => `<tr>
            <td>${this.esc(r.problem_category || 'Missing category')}</td><td>${this.esc(r.asset_name)}</td>
            <td><a href="/app/plant-breakdown-or-maintenance/${encodeURIComponent(r.name)}" target="_blank" rel="noopener">${this.esc(r.name)}</a></td>
            <td>${this.esc(r.breakdown_start_datetime)}</td><td>${this.esc(r.breakdown_reason)}</td><td>${this.esc(r.status_label)}</td>
            ${add_action && this.group()?.can_write ? `<td><button class="btn btn-default btn-xs tmm-action-for-record" data-reference="${this.esc(r.name)}">Add action</button></td>` : ''}</tr>`).join('')}</tbody></table>`;
    }

    bind_record_actions() {
        this.body.find('.tmm-action-for-record').off('click').on('click', event => {
            if (this.busy) return;
            const g = this.group();
            const records = [...g.counts.categories.flatMap(c => c.records), ...g.counts.unresolved_records];
            const record = records.find(r => r.name === event.currentTarget.dataset.reference);
            if (!record || !g.can_write) return;
            g.actions.push({cause: this.data.problem_categories.includes(record.problem_category) ? record.problem_category : '',
                action: '', owner_name: '', due_date: '', status: 'Open', breakdown_reference: record.name});
            g.dirty = true; this.mark_dirty(); this.render_actions();
        });
    }

    render_details() {
        const g = this.group(), c = g.counts;
        this.body.find('[data-group]').each((_, row) => {
            const selected = row.dataset.group === this.selected;
            $(row).toggleClass('is-selected', selected).attr('aria-pressed', String(selected));
            $(row).find('.tmm-group-highlight').attr('opacity', selected ? '1' : '0');
        });
        this.body.find('.tmm-details').html(`<section class="tmm-section"><h3>2. ${this.esc(g.group)} · Breakdown records by category</h3>
            <div class="text-muted">${this.esc(this.data.month_label)} · ${this.esc(this.data.population)} · One count per breakdown record</div>
            <div class="tmm-chart">${this.show_all ? g.full_chart : g.chart}</div>
            <p><strong>${this.esc(g.summary)}</strong></p>
            <p class="text-muted">${c.categorised_count} categorised + ${c.unresolved_count} unresolved = ${c.total_count} records. Cumulative percentages exclude unresolved categorisation. Status below is current.</p>
            ${c.omitted_categories ? `<p class="text-muted">Top 10: ${c.omitted_categories} omitted categories contain ${c.omitted_count} records, included in the cumulative denominator. ${c.priority_category_count > 10 ? `${c.priority_category_count - 10} additional priority categories are beyond the top 10.` : ''} <button class="btn btn-default btn-xs tmm-toggle-categories">${this.show_all ? 'Show top 10' : 'Show all categories'}</button></p>` : ''}
            <details class="tmm-priority"><summary>Breakdowns contributing to the first 80% (${c.priority_records.length})</summary><div class="table-responsive">${this.records_table(c.priority_records)}</div></details>
            <details class="tmm-all-categories"><summary>All categories — inspect individual category records</summary><table class="tmm-category-list"><thead><tr><th>Category</th><th>Records</th><th>80% priority</th></tr></thead><tbody>${c.all_categories.map(row => `<tr><td><button class="btn btn-link btn-xs tmm-inspect-category" data-category="${this.esc(row.category)}">${this.esc(row.category)}</button></td><td>${row.count}</td><td>${row.priority ? 'Priority' : ''}</td></tr>`).join('')}</tbody></table><div class="tmm-category-records"></div></details>
            <details class="tmm-unresolved"><summary>${c.unresolved_count} unresolved categorisation · Review</summary><p class="text-muted">Blank and unsupported legacy categories require review. Open the original breakdown to correct it through the existing authorised workflow.</p><div class="table-responsive">${this.records_table(c.unresolved_records)}</div></details></section>
            <section class="tmm-section"><div class="tmm-actions-heading"><h3>Corrective actions · ${this.esc(g.group)}</h3>
            <button class="btn btn-primary btn-sm tmm-add" ${g.can_write ? '' : 'disabled'}>+ Add Action</button></div>
            <div class="table-responsive"><table class="tmm-actions-table"><thead><tr><th>Category</th><th>Action</th><th>Owner</th><th>Due Date</th><th>Status</th><th>Breakdown Reference (optional)</th><th></th></tr></thead><tbody></tbody></table></div>
            <div class="tmm-state text-muted">${this.dirty ? 'Unsaved actions' : ''}</div></section>`);
        this.render_actions();
        this.bind_record_actions();
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
        const category_select = a => `<select class="form-control input-sm" data-field="cause" aria-label="Category" ${disabled}><option value="">Select category…</option>${a.cause && !this.data.problem_categories.includes(a.cause) ? `<option value="${this.esc(a.cause)}" selected>${this.esc(a.cause)} (legacy — review)</option>` : ''}${this.data.problem_categories.map(c => `<option value="${this.esc(c)}" ${a.cause === c ? 'selected' : ''}>${this.esc(c)}</option>`).join('')}</select>`;
        const rows = g.actions.map((a, i) => `<tr data-index="${i}"><td>${category_select(a)}</td>
            <td><textarea class="form-control input-sm" data-field="action" aria-label="Action" ${disabled}>${this.esc(a.action)}</textarea></td>
            <td>${input('owner_name', a.owner_name)}</td><td>${input('due_date', a.due_date, 'date')}</td>
            <td><select class="form-control input-sm" data-field="status" aria-label="Status" ${disabled}>${['Open','In progress','Completed'].map(s => `<option ${a.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></td>
            <td>${input('breakdown_reference', a.breakdown_reference)}</td><td><button class="btn btn-default btn-xs tmm-remove" aria-label="Remove action ${i+1}" ${disabled}>×</button></td></tr>`).join('');
        this.body.find('.tmm-actions-table tbody').html(rows || '<tr><td colspan="7" class="text-muted">No saved corrective actions.</td></tr>');
        this.body.find('[data-field]').on('input change', event => {
            const row = Number($(event.currentTarget).closest('tr').attr('data-index'));
            g.actions[row][event.currentTarget.dataset.field] = event.currentTarget.value;
            g.dirty = true; this.mark_dirty();
        });
        this.body.find('.tmm-remove').on('click', event => {
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

    async download_pdf() {
        if (this.busy || !this.data) return;
        if (this.dirty && !(await this.save())) return;
        const url = '/api/method/' + this.method + 'download_pdf?' + $.param(this.context);
        window.open(url, '_blank', 'noopener');
    }
}
