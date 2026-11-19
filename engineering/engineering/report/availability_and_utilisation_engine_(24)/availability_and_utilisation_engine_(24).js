/* Independent report controls; no summary cards or permanent configuration table. */
(() => {
    const name = 'Availability and Utilisation Engine (24)';
    const endpoint = 'engineering.engineering.report.availability_and_utilisation_engine_(24).availability_and_utilisation_engine_(24)';
    const escape = value => frappe.utils.escape_html(String(value ?? ''));
    const run_button = report => report.page.set_primary_action(__('Run Report'), () => report.refresh());
    const link_filter = (fieldname, label, options) => ({
        fieldname, label: __(label), fieldtype: 'MultiSelectList', options,
        get_data: text => frappe.db.get_link_options(options, text),
    });

    const formula_details = {
        'Industry Formula': {
            availability: 'Available = 12 − Raw Breakdown − Raw Planned Maintenance\nAvailability = Available Hours / 12',
            utilisation: 'Use of Availability Available Hours = 12 − Raw Breakdown − Raw Planned Maintenance\nUse of Availability = Working Hours / Use of Availability Available Hours\nUtilisation Available Hours = 12 hours per shift\nUtilisation = Working Hours / 12',
            variables: 'Shift Hours = 12 hours per scheduled shift. Raw Breakdown and Raw Planned Maintenance = recorded downtime hours, including startup/fatigue overlap. Working Hours = valid recorded working hours.',
            example: 'One 12-hour shift: breakdown 2 h, planned maintenance 1 h, working 9 h. Available = 9 h; availability = 9 / 12 = 75%. Use of Availability available = 9 h; Use of Availability = 9 / 9 = 100%. Utilisation = 9 / 12 = 75%.',
            rules: 'No startup, fatigue, safety meeting or tramming out deductions. No Site Specific Startup and Fatigue lookup or old 18-hour threshold. Raw downtime is used without startup/fatigue overlap exclusions. Calculate each 12-hour shift separately. Use of Availability Available Hours equals Availability Available Hours for that shift; sum shift denominators for weighted period/parent/bottom results.',
        },
        'Isambane Formula': {
            availability: 'Remaining Required Hours = MAX(Required Hours − PBM Total Downtime, 0)\nAvailability Available Hours = MAX(Working Hours, Remaining Required Hours)\nAvailability = Availability Available Hours / Required Hours',
            utilisation: 'Utilisation Available Hours = MAX(Remaining Required Hours, MIN(Working Hours, Required Hours))\nUtilisation = Working Hours / Utilisation Available Hours',
            variables: 'Required Hours = original Engine required hours per shift. Working Hours = working hours accepted by the original Engine. PBM Total Downtime = breakdown and planned maintenance downtime after the original startup/fatigue overlap exclusions.',
            example: 'One shift: required 12 h, PBM downtime 2 h, working 9 h. Remaining = 10 h; availability available = 10 h; utilisation available = MAX(10, MIN(9, 12)) = 10 h. Availability = 10 / 12 = 83.33%; utilisation = 9 / 10 = 90.00%.',
            rules: 'PBM downtime excludes overlap with startup/fatigue according to the original Engine rules. Preserve its Pre-Use status exceptions, integrity checks, Sunday and zero-required-hours handling. MAX/MIN run per shift before period aggregation. Safety, fatigue and tramming columns are not additional deductions.',
        },
    };

    function target_text(report) {
        const targets = report._au24_targets?.[report.get_filter_value('formula')];
        const percent = value => value == null ? __('Not configured') : `${Number((value * 100).toFixed(2))}%`;
        if (!report._au24_targets) return __('Targets unavailable');
        return `${__('Availability')} ${percent(targets?.availability)} · ${__('Utilisation')} ${percent(targets?.utilisation)}`;
    }

    function render_targets_card(report) {
        const card = report.page.page_form.find('.au24-target-card');
        if (!card.length) return;

        const selected = report.get_filter_value('formula');
        const basis = report.get_filter_value('isambane_basis') || '85% A & U';
        const targets = report._au24_targets?.[selected] || {};

        let availability = targets.availability;
        let utilisation = targets.utilisation;
        let title = __('Targets');

        if (selected === 'Isambane Formula') {
            const target = basis === '100% A & U' ? 1 : 0.85;
            availability = target;
            utilisation = target;
            title = `${__('Target is')} ${basis === '100% A & U' ? 12 : 9} ${__('hours')}`;
        }

        const percent = value => value == null
            ? __('Not configured')
            : `${Number((Number(value) * 100).toFixed(2))}%`;

        card.find('.au24-target-title').text(`${__('Targets')} (${title})`);
        card.find('.au24-target-availability').text(percent(availability));
        card.find('.au24-target-utilisation').text(percent(utilisation));
    }

    function sync_formula(report) {
        render_targets_card(report);

        const isambane = report.get_filter_value('formula') === 'Isambane Formula';
        report.get_filter('isambane_basis')?.$wrapper.toggle(isambane);

        const dialog = report._au24_formula_dialog;
        if (!dialog) return;

        const selected = report.get_filter_value('formula');
        const details = formula_details[selected];
        if (!details) return;

        if (isambane) {
            const basis = report.get_filter_value('isambane_basis') || '100% A & U';
            const multiplier = basis === '85% A & U' ? 0.85 : 1;

            const card = (title, formula, kind) =>
                `<section class="au24-isambane-card ${kind}">
                    <h4>${escape(__(title))}</h4>
                    <div class="au24-isambane-expression">${escape(formula)}</div>
                </section>`;

            const availability = (10 / 12 * 100 * multiplier).toFixed(2);
            const utilisation = (9 / 10 * 100 * multiplier).toFixed(2);

            const content =
                `<div class="au24-isambane-formula">
                    <h3>Isambane Formula</h3>
                    ${card('Availability Available Hours',
                        'MAX(Working Hours, MAX(Required Hours - PBM Total Downtime, 0))',
                        'availability')}
                    ${card('Availability %',
                        'Availability Available Hours / Required Hours',
                        'availability')}
                    ${card('Utilisation Available Hours',
                        'MAX(MAX(Required Hours - PBM Total Downtime, 0), MIN(Working Hours, Required Hours))',
                        'utilisation')}
                    ${card('Utilisation %',
                        'Working Hours / Utilisation Available Hours',
                        'utilisation')}

                    <section class="au24-isambane-example">
                        <h4>Example</h4>
                        <div>Required Hours = 12 h · Working Hours = 9 h · PBM Downtime = 2 h</div>
                        <strong>Availability Available Hours = 10 h</strong>
                        <strong>Availability = ${availability}%</strong>
                        <strong>Utilisation Available Hours = 10 h</strong>
                        <strong>Utilisation = ${utilisation}%</strong>
                    </section>

                    <section class="au24-isambane-targets">
                        <h4>Reference Targets</h4>
                        <strong>Availability 85%</strong>
                        <strong>Utilisation 85%</strong>
                    </section>

                    <p class="au24-isambane-note">
                        Working Hours above Required Hours (e.g. 9 h) can result in
                        Availability and Utilisation above 100%. Results are not capped.
                        The ${escape(basis)} basis changes percentages only, not hours.
                    </p>
                    <p class="au24-isambane-note">
                        PBM Total Downtime = breakdown + planned maintenance after original Engine rules.
                    </p>
                </div>`;

            dialog.fields_dict.explanation.$wrapper.html(content);
            return;
        }

        const card = (title, formulas, kind) =>
            `<section class="au24-isambane-card ${kind}">
                <h4>${escape(__(title))}</h4>
                ${formulas.map(formula =>
                    `<div class="au24-isambane-expression">${escape(formula)}</div>`
                ).join('')}
            </section>`;

        const content =
            `<div class="au24-isambane-formula">
                <h3>Industry Formula</h3>

                ${card('Availability', [
                    'Available Hours = 12 - Raw Breakdown - Raw Planned Maintenance',
                    'Availability % = Available Hours / 12'
                ], 'availability')}

                ${card('Use of Availability', [
                    'Use of Availability Available Hours = Availability Available Hours',
                    'Use of Availability % = Working Hours / Use of Availability Available Hours'
                ], 'utilisation')}

                ${card('Utilisation', [
                    'Utilisation Available Hours = 12 hours per shift',
                    'Utilisation % = Working Hours / 12'
                ], 'utilisation')}

                <section class="au24-isambane-example">
                    <h4>Example</h4>
                    <div>Shift Hours = 12 h · Breakdown = 2 h · Planned Maintenance = 1 h · Working Hours = 9 h</div>
                    <strong>Availability Available Hours = 9 h</strong>
                    <strong>Availability = 75%</strong>
                    <strong>Use of Availability Available Hours = 9 h</strong>
                    <strong>Use of Availability = 100%</strong>
                    <strong>Utilisation Available Hours = 12 h</strong>
                    <strong>Utilisation = 75%</strong>
                </section>
            </div>`;

        dialog.fields_dict.explanation.$wrapper.html(content);
    }

    function show_formula(report) {
        if (!report._au24_formula_dialog) {
            report._au24_formula_dialog = new frappe.ui.Dialog({
                title: __('View Formula'), size: 'large',
                fields: [{fieldname: 'explanation', fieldtype: 'HTML'}],
            });
        }
        sync_formula(report);
        report._au24_formula_dialog.show();
    }

    function install_layout(report, configuration_button, formula_button) {
        const form = report.page.page_form;
        if (!form?.length) return;

        report.page.main.find('.au24-heading, .au24-actions').remove();
        form.find('.au24-run-filter, .au24-filter-label').remove();

        const formula = report.get_filter('formula');
        formula.$wrapper.addClass('au24-formula-filter');
        formula.$wrapper.find('.au24-targets').remove();

        if (!form.find('.au24-target-card').length) {
            $(
                '<div class="au24-target-card" role="status" aria-live="polite">' +
                    '<div class="au24-target-title"></div>' +
                    '<div class="au24-target-metric au24-target-availability-box">' +
                        '<span>Availability Target</span>' +
                        '<strong class="au24-target-availability">—</strong>' +
                    '</div>' +
                    '<div class="au24-target-metric au24-target-utilisation-box">' +
                        '<span>Utilisation Target</span>' +
                        '<strong class="au24-target-utilisation">—</strong>' +
                    '</div>' +
                '</div>'
            ).appendTo(form);
        }

        sync_formula(report);
    }

    function apply_group_styling(datatable) {
        const wrapper = datatable.datatableWrapper || datatable.wrapper;
        const table = wrapper?.querySelector?.('.datatable') || wrapper;
        const columns = datatable.datamanager.getColumns();

        if (!table || !columns?.length) return;

        const groups = [
            {
                key: 'availability',
                label: __('Availability'),
                fields: ['availability_available', 'availability_percent'],
            },
            {
                key: 'use',
                label: __('Use of Availability'),
                fields: ['use_of_availability_available', 'use_of_availability_percent'],
            },
            {
                key: 'utilisation',
                label: __('Utilisation'),
                fields: ['utilisation_available', 'utilisation_percent'],
            },
        ].filter(group =>
            group.fields.some(field =>
                columns.some(column => column.fieldname === field)
            )
        );

        const get_col_index = cell => {
            const match = [...cell.classList]
                .map(name => name.match(/^dt-cell--col-(\d+)$/))
                .find(Boolean);
            return match ? Number(match[1]) : null;
        };

        table.querySelectorAll('.dt-cell').forEach(cell => {
            [...cell.classList]
                .filter(name => name.startsWith('au24-group'))
                .forEach(name => cell.classList.remove(name));
            cell.removeAttribute('data-group-label');
        });

        for (const group of groups) {
            const indices = group.fields
                .map(field => columns.findIndex(column => column.fieldname === field))
                .filter(index => index >= 0);

            if (!indices.length) continue;

            const start = Math.min(...indices);
            const end = Math.max(...indices);

            table.querySelectorAll('.dt-row .dt-cell').forEach(cell => {
                const col_index = get_col_index(cell);
                if (col_index == null || col_index < start || col_index > end) return;

                cell.classList.add('au24-group-col', `au24-group-${group.key}`);

                if (col_index === start) {
                    cell.classList.add('au24-group-start');
                    if (cell.closest('.dt-row-header')) {
                        cell.classList.add('au24-group-label');
                        cell.setAttribute('data-group-label', group.label);
                    }
                }

                if (col_index === end) {
                    cell.classList.add('au24-group-end');
                }

                if (cell.closest('.dt-row-header')) {
                    cell.classList.add('au24-group-header');
                }
            });
        }
    }

    function fit_columns(datatable, remember_source = true) {
        if (remember_source) {
            datatable._au24_full_data = datatable.datamanager.data.slice();
            datatable._au24_full_rows = datatable.datamanager.rows.slice();
        }
        if (remember_source) datatable._au24_filter_signature = null;
        if (!datatable._au24_filter_handlers) {
            datatable._au24_filter_handlers = true;
            const native_apply = datatable.columnmanager.applyFilter.bind(datatable.columnmanager);
            datatable.columnmanager.applyFilter = filters => {
                const signature = JSON.stringify(filters);
                if (signature === datatable._au24_filter_signature) return;
                datatable._au24_filter_signature = signature;
                native_apply(filters);
            };
            // Keep editing keys in the inputs instead of DataTable cell navigation.
            // Native header keydown filtering still runs; only bubbling to the
            // outer keyboard handler is stopped. Input also covers paste/mobile.
            datatable.header.addEventListener('keydown', event => {
                if (event.target.matches('.dt-filter')) event.stopPropagation();
            });
            datatable.header.addEventListener('input', event => {
                if (!event.target.matches('.dt-filter')) return;
                clearTimeout(datatable._au24_input_timer);
                datatable._au24_input_timer = setTimeout(() => {
                    datatable.columnmanager.applyFilter(datatable.columnmanager.getAppliedFilters());
                }, 300);
            });
        }
        // Fixed, readable minimum widths on small screens; fit all columns on
        // desktop. Apply after every render because Frappe refreshes its model.
        const columns = datatable.datamanager.getColumns();
        const industry = columns.some(column => column.fieldname === 'use_of_availability_available');
        datatable.datatableWrapper.classList.toggle('au24-industry-columns', industry);
        const weights = columns.map(column => column.fieldname === 'asset' ? 240 : column.fieldname === 'asset_type' ? 125 :
            column.fieldname === 'use_of_availability_available' || column.fieldname === 'utilisation_available' ? 190 : column.fieldtype === 'Percent' ? 150 : 140);
        const width = Math.max(industry ? 1500 : 1100, datatable.datatableWrapper.clientWidth) - weights.length - 2;
        const total = weights.reduce((sum, value) => sum + value, 0);
        datatable.datamanager.getColumns().forEach((column, index) => {
            datatable.datamanager.updateColumn(column.colIndex, { width: Math.floor(width * weights[index] / total),
                sortable: false, dropdown: false,
                align: ['Int', 'Float', 'Percent', 'Currency'].includes(column.fieldtype) ? 'right' : 'left' });
        });
        datatable.columnmanager.toggleFilter(true);
        apply_group_styling(datatable);
        datatable.wrapper.querySelectorAll('.dt-filter').forEach((input, index) => {
            // DataTable disables column zero even without a serial-number column.
            input.disabled = false;
            input.setAttribute('aria-label', `${__('Search')} ${columns[index].name}`);
            input.placeholder = columns[index].fieldtype === 'Percent' ? __('e.g. >85') : __('Search');
        });
        datatable.style.setDimensions();
        fit_table_height(datatable);
        install_formula_tooltips(datatable);
    }

    // Fill the remaining browser viewport with the table body.
    // Headers and column searches remain above the independently
    // scrollable rows.
    function fit_table_height(datatable) {
        const wrapper = datatable.datatableWrapper || datatable.wrapper;
        const root = wrapper?.matches?.('.datatable')
            ? wrapper
            : wrapper?.querySelector('.datatable')
                || datatable.wrapper?.querySelector('.datatable');

        if (!root) return;

        const apply = () => {
            if (!root.isConnected) return;

            const viewportHeight = window.visualViewport?.height || window.innerHeight;
            const top = root.getBoundingClientRect().top;
            const availableHeight = Math.max(280, Math.floor(viewportHeight - top - 20));

            const scrollable = root.querySelector('.dt-scrollable');
            const header = root.querySelector('.dt-header');
            const footer = root.querySelector('.dt-footer');

            // Size the complete DataTable, not only its scrollable child.
            root.style.setProperty('height', `${availableHeight}px`, 'important');
            root.style.setProperty('max-height', `${availableHeight}px`, 'important');
            root.style.setProperty('min-height', '0', 'important');
            root.style.setProperty('display', 'flex', 'important');
            root.style.setProperty('flex-direction', 'column', 'important');
            root.style.setProperty('overflow', 'hidden', 'important');

            if (header) {
                header.style.setProperty('flex', '0 0 auto', 'important');
            }

            if (scrollable) {
                scrollable.style.setProperty('flex', '1 1 auto', 'important');
                scrollable.style.setProperty('min-height', '0', 'important');
                scrollable.style.setProperty('height', 'auto', 'important');
                scrollable.style.setProperty('max-height', 'none', 'important');
                scrollable.style.setProperty('overflow-y', 'auto', 'important');
                scrollable.style.setProperty('overflow-x', 'auto', 'important');
            }

            if (footer) {
                footer.style.setProperty('flex', '0 0 auto', 'important');
            }
        };

        apply();
        requestAnimationFrame(apply);
    }


    function get_formula_tooltip(data, fieldname) {
        const industry = data?.formula === 'Industry Formula';
        if (!industry && data?.formula !== 'Isambane Formula') return null;

        const definitions = {
            availability_available: [
                'Availability Available Hours (h)', 'availability',
                '12 − Raw Breakdowns − Raw Planned Maintenance',
                'MAX(Working Hours, MAX(Required Hours − PBM Total Downtime, 0))'
            ],
            availability_percent: [
                'Availability (%)', 'availability',
                'Availability Available Hours ÷ 12',
                'Availability Available Hours ÷ Required Hours'
            ],
            use_of_availability_available: [
                'Use of Availability Available Hours (h)', 'use',
                '12 − Raw Breakdowns − Raw Planned Maintenance',
                null
            ],
            use_of_availability_percent: [
                'Use of Availability (%)', 'use',
                'Working Hours ÷ Use of Availability Available Hours',
                null
            ],
            utilisation_available: [
                'Utilisation Available Hours (h)', 'utilisation',
                '12 hours per shift',
                'MAX(Required Hours − PBM Total Downtime, MIN(Working Hours, Required Hours))'
            ],
            utilisation_percent: [
                'Utilisation (%)', 'utilisation',
                'Working Hours ÷ 12',
                'Working Hours ÷ Utilisation Available Hours'
            ]
        };

        const definition = definitions[fieldname];
        if (!definition) return null;

        const [title, group, industryFormula, isambaneFormula] = definition;
        const formula = industry ? industryFormula : isambaneFormula;
        if (!formula) return null;

        return { title, group, formula };
    }

    function install_formula_tooltips(datatable) {
        const root = datatable.wrapper;
        if (!root || root._au24_formula_tooltip_bound) return;
        root._au24_formula_tooltip_bound = true;

        let tooltip = document.getElementById('au24-formula-tooltip');

        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'au24-formula-tooltip';
            tooltip.className = 'au24-formula-tooltip';
            tooltip.setAttribute('role', 'tooltip');

            tooltip.innerHTML =
                '<div class="au24-tooltip-title"></div>' +
                '<div class="au24-tooltip-formula"></div>';

            document.body.appendChild(tooltip);

        }

        const hide = () => {
            tooltip.style.display = 'none';
        };

        const show = target => {
            const { au24TooltipTitle, au24TooltipFormula, au24TooltipGroup } = target.dataset;

            if (!au24TooltipFormula) return hide();

            tooltip.className = `au24-formula-tooltip au24-formula-tooltip-${au24TooltipGroup}`;
            tooltip.querySelector('.au24-tooltip-title').textContent = au24TooltipTitle;
            tooltip.querySelector('.au24-tooltip-formula').textContent = au24TooltipFormula;
            tooltip.style.display = 'block';

            const cell = target.getBoundingClientRect();
            const popup = tooltip.getBoundingClientRect();

            const left = Math.max(8, Math.min(
                cell.left + cell.width / 2 - popup.width / 2,
                window.innerWidth - popup.width - 8
            ));

            let top = cell.bottom + 8;
            if (top + popup.height > window.innerHeight - 8) {
                top = Math.max(8, cell.top - popup.height - 8);
            }

            tooltip.style.left = `${left}px`;
            tooltip.style.top = `${top}px`;
        };

        root.addEventListener('pointerover', event => {
            const target = event.target.closest?.('.au24-formula-hover');
            if (!target || !root.contains(target)) return;

            // Remove Frappe/browser value tooltips from this result cell.
            const cell = target.closest('.dt-cell');
            if (cell) {
                cell.removeAttribute('title');
                cell.querySelectorAll('[title]').forEach(element => {
                    element.removeAttribute('title');
                });
            }
            target.removeAttribute('title');

            show(target);
        });

        root.addEventListener('pointerout', event => {
            if (!event.target.closest?.('.au24-formula-hover')) return;
            if (!event.relatedTarget?.closest?.('.au24-formula-hover')) hide();
        });

        root.addEventListener('focusin', event => {
            const target = event.target.closest?.('.au24-formula-hover');
            if (target) show(target);
        });

        root.addEventListener('focusout', event => {
            if (!event.relatedTarget?.closest?.('.au24-formula-hover')) hide();
        });

        root.addEventListener('scroll', hide, true);
        window.addEventListener('resize', hide);
    }

    async function filter_visible_rows(rows, filters, manager) {
        const report = frappe.query_report;
        const table = report.datatable;
        const full_data = table._au24_full_data;
        const full_rows = table._au24_full_rows;
        const previous = table._au24_filter_pending || Promise.resolve();
        const job = previous.catch(() => {}).then(async () => {
            if (report.datatable !== table || table._au24_full_data !== full_data) return manager.getAllRowIndices();
            let indices = full_data.map((row, index) => row.is_atomic ? index : -1).filter(index => index >= 0);
            // Match only atomic shift rows, never subtotal rows.
            // Parent context is searchable, so fleet/category/date searches keep
            // the whole relevant branch. Industry shifts are independently searchable.
            const searchable = full_rows.map((row, index) => {
                const data = full_data[index];
                const cells = row.map(cell => {
                    let value = cell.content;
                    if (cell.column.fieldname === 'asset') value = [data.asset, data.fleet_number,
                        data.asset_type, data.shift_date, data.shift,
                        ...(data.shift_details || []).map(detail => detail.shift)].filter(Boolean).join(' ');
                    else if (cell.column.fieldtype === 'Percent') value = value == null ? null : Number(value) * 100;
                    const content = value == null ? '' : String(value);
                    return {...cell, content, html: escape(content)};
                });
                cells.meta = row.meta;
                return cells;
            });
            for (const [column, keyword] of Object.entries(filters)) {
                const matches = await table.DEFAULT_OPTIONS.filterRows(searchable, {[column]: keyword}, manager);
                indices = indices.filter(index => matches.includes(index));
            }
            const context = full_data.at(-1);
            let tree;
            try {
                tree = await frappe.xcall(endpoint + '.get_filtered_tree', {
                    rows: indices.map(index => full_data[index]), formula: context.formula,
                    isambane_basis: context.isambane_basis,
                });
            } catch (error) {
                table._au24_filter_signature = null;
                frappe.msgprint(__('Column filtering could not be applied. The previous rows and totals are retained.'));
                return manager.getFilteredRowIndices();
            }
            if (report.datatable !== table || table._au24_full_data !== full_data) return manager.getAllRowIndices();
            // Preserve disclosure state and the existing header/input DOM. A
            // full table.refresh would replace the focused input and reset scroll.
            const key = data => data.is_total_row ? 'total' : JSON.stringify([
                data.indent, data.asset_type,
                data.indent >= 1 ? data.shift_date : null,
                data.indent >= 2 ? data.site : null,
                data.indent >= 2 ? data.fleet_number : null,
                data.indent >= 3 ? data.shift : null,
            ]);
            table._au24_closed_states ||= new Map();
            manager.rows.forEach(row => {
                const data = manager.data[row.meta.rowIndex];
                if (!row.meta.isLeaf) table._au24_closed_states.set(key(data), row.meta.isTreeNodeClose);
            });
            const columns = manager.getColumns().map(column => ({...column}));
            manager.init(tree, columns);
            report.data = tree;
            manager.rows.forEach(row => {
                if (!row.meta.isLeaf) row.meta.isTreeNodeClose = table._au24_closed_states.get(key(tree[row.meta.rowIndex])) ?? true;
            });
            // The standard filter callback renders only this body row set.
            // Existing expanded matching paths remain open; no other paths open.
            return table.bodyRenderer.getRowsToRender().map(row => row.meta.rowIndex);
        });
        table._au24_filter_pending = job;
        return job;
    }

    async function show_configuration(report) {
        const rows = await frappe.xcall(endpoint + '.get_site_configurations', {
            sites: report.get_filter_value('sites') || [],
        });
        const dialog = new frappe.ui.Dialog({
            title: __('Site Startup & Fatigue Configuration'), size: 'extra-large',
            fields: [{ fieldname: 'configuration', fieldtype: 'HTML' }],
        });
        const headings = ['Site', 'Shift', 'Day Type', 'Startup', 'Fatigue'];
        const time_text = value => {
            if (!value) return '-';
            const match = String(value).match(/^(\\d{1,2}):(\\d{2})/);
            return match ? `${match[1].padStart(2, '0')}:${match[2]}` : escape(value);
        };
        const interval_text = (row, key) =>
            `${time_text(row[key + '_start'])} - ${time_text(row[key + '_end'])}`;

        const body = rows.map(row =>
            `<tr>
                <td>${escape(row.site)}</td>
                <td>${escape(row.shift)}</td>
                <td>${escape(row.day_type)}</td>
                <td>${interval_text(row, 'startup')}</td>
                <td>${interval_text(row, 'fatigue')}</td>
            </tr>`
        ).join('');

        dialog.fields_dict.configuration.$wrapper.html(
            '<div class="table-responsive"><table class="table table-bordered table-sm"><thead><tr>' +
            headings.map(label => `<th>${escape(__(label))}</th>`).join('') +
            `</tr></thead><tbody>${body || `<tr><td colspan="5">${escape(__('No existing configurations found.'))}</td></tr>`}</tbody></table></div>` +
            `<p class="text-muted small">${escape(__('Read-only view of the original Startup and Fatigue specifications. Day and Night shifts are shown separately.'))}</p>`
        );
        dialog.show();
    }

    frappe.query_reports[name] = {
        initial_depth: 0,
        filters: [
            { fieldname: 'from_date', label: __('From Date'), fieldtype: 'Date', reqd: 1, default: frappe.datetime.month_start() },
            { fieldname: 'to_date', label: __('To Date'), fieldtype: 'Date', reqd: 1, default: frappe.datetime.get_today() },
            link_filter('sites', 'Site', 'Location'),
            link_filter('assets', 'Asset', 'Asset'),
            link_filter('companies', 'Company', 'Company'),
            { fieldname: 'asset_ownership', label: __('Asset Ownership'), fieldtype: 'Select',
                options: 'Isambane & Excavo Assets\nSupplier Assets\nAll Assets', default: 'Isambane & Excavo Assets' },
            { fieldname: 'machine_scope', label: __('Machine Filter'), fieldtype: 'Select',
                options: 'All Machines\nProduction Machines\nSpare Machines',
                default: 'All Machines',
                on_change(report) {
                    if (!report._no_refresh) report.refresh(true);
                } },
            { fieldname: 'formula', label: __('Formula'), fieldtype: 'Select',
                options: 'Industry Formula\nIsambane Formula', default: 'Isambane Formula', reqd: 1,
                on_change(report) {
                    sync_formula(report);
                    if (!report._no_refresh) report.refresh(true);
                } },
            { fieldname: 'isambane_basis', label: __('Isambane Calculation Basis'), fieldtype: 'Select',
                options: '85% A & U\n100% A & U', default: '85% A & U',
                depends_on: 'eval:doc.formula==="Isambane Formula"',
                on_change(report) {
                    sync_formula(report);
                    if (!report._no_refresh) report.refresh(true);
                } },
        ],
        onload(report) {
            report.page.main.addClass('au24-report');
            // Desk reuses the same Query Report wrapper when switching reports.

            run_button(report);

            if (!report._au24_resize_handler) {
                report._au24_resize_handler = () => {
                    if (report.datatable) fit_table_height(report.datatable);
                };
                window.addEventListener('resize', report._au24_resize_handler);
            }

            const configuration_button = report.page.add_inner_button(__('View Startup & Fatigue Configuration'), () => show_configuration(report));
            const formula_button = report.page.add_inner_button(__('View Formula'), () => show_formula(report));
            install_layout(report, configuration_button, formula_button);
            frappe.xcall(endpoint + '.get_formula_targets').then(targets => {
                report._au24_targets = targets;
                sync_formula(report);
            }).catch(() => sync_formula(report));
        },
        after_datatable_render: fit_columns,
        after_refresh(report) {
            run_button(report);
            // Keep the data table directly below controls; explanatory notes belong below it.
            if (report.$report_message && report.$report) report.$report_message.insertAfter(report.$report);
        },
        get_datatable_options(options) {
            // Keep the manual weighted total last, and recalculate it for the
            // exact rows selected by standard column search inputs.
            return { ...options, cellHeight: 40, minimumColumnWidth: 32, serialNoColumn: false, inlineFilters: true,
                filterRows: filter_visible_rows,
                columns: (options.columns || []).map(column => ({ ...column, sortable: false, dropdown: false,
                    align: ['Int', 'Float', 'Percent', 'Currency'].includes(column.fieldtype) ? 'right' : 'left' })) };
        },
        formatter(value, row, column, data, default_formatter) {
            let rendered;
            if (value === null || value === undefined) {
                rendered = '<span class="text-muted">—</span>';
                if (column.fieldname === 'use_of_availability_percent' && data?.use_of_availability_inconsistent) {
                    rendered += ` <span title="${escape(data.performance_warning || __('Working hours exceed available hours.'))}" aria-label="${escape(__('Data inconsistency'))}">⚠</span>`;
                }
            } else {
                const is_ratio = ['availability_percent', 'utilisation_percent', 'use_of_availability_percent'].includes(column.fieldname);
                // Backend values remain decimal ratios (0.85). Frappe's Percent
                // formatter expects 85, so scale only this display argument.
                rendered = default_formatter(is_ratio ? Number(value) * 100 : value, row, column, data);
                if (is_ratio) {
                    const kind = column.fieldname === 'availability_percent' ? 'availability' : column.fieldname === 'use_of_availability_percent' ? 'use' : 'utilisation';
                    const flag = column.fieldname === 'use_of_availability_percent' ? 'use_of_availability_inconsistent' : 'utilisation_inconsistent';
                    const flagged = false;
                    const warning = kind !== 'availability' && data?.performance_warning || __('Result exceeds 100%. Actual ratio is not capped.');
                    const title = flagged ? ` title="${escape(warning)}"` : '';
                    const progress = Math.min(100, Math.max(0, Number(value) * 100));
                    rendered = `<span class="au24-percent au24-${kind}${flagged ? ' au24-inconsistent' : ''}"${title}>${rendered}${flagged ? ` <span role="img" aria-label="${escape(__('Data warning'))}">⚠</span>` : ''}<span class="au24-track" aria-hidden="true"><span class="au24-fill" style="width:${progress}%"></span></span></span>`;
                }
            }
            if (['availability_available', 'utilisation_available', 'use_of_availability_available'].includes(column.fieldname) && value != null) {
                const kind = column.fieldname === 'availability_available' ? 'availability' : column.fieldname === 'use_of_availability_available' ? 'use' : 'utilisation';
                rendered = `<span class="au24-calculated-hours au24-${kind}">${rendered}</span>`;
            }
            const formulaHelp = value != null
                ? get_formula_tooltip(data, column.fieldname)
                : null;

            if (formulaHelp) {
                rendered = `<span class="au24-formula-hover"
                    data-au24-tooltip-group="${formulaHelp.group}"
                    data-au24-tooltip-title="${escape(__(formulaHelp.title))}"
                    data-au24-tooltip-formula="${escape(__(formulaHelp.formula))}"
                    tabindex="0">${rendered}</span>`;
            }

            if (data?.excluded_shift) rendered = `<span class="au24-excluded" title="${escape(__('Original Engine integrity exclusion: this shift is not included in parent or bottom totals.'))}">${rendered}</span>`;
            if (data && data.indent < 3 && !data.is_total_row) rendered = `<span class="au24-tree-summary">${rendered}</span>`;
            if (data?.indent === 3 && !data.is_total_row && column.fieldname === 'asset' && ['Day', 'Night'].includes(data.shift)) {
                rendered = `<span class="au24-shift-${data.shift.toLowerCase()}">${rendered}</span>`;
            }
            return data?.is_total_row ? `<strong class="au24-total-cell">${rendered}</strong>` : rendered;
        },
    };
})();
