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
            tooltip.style.cssText = [
                'position:fixed',
                'z-index:10000',
                'display:none',
                'width:max-content',
                'min-width:220px',
                'max-width:min(330px,calc(100vw - 24px))',
                'background:#fff',
                'color:#1f2937',
                'border:1px solid #d8dee8',
                'border-radius:9px',
                'box-shadow:0 8px 25px rgba(15,23,42,.20)',
                'overflow:hidden',
                'pointer-events:none',
                'font-size:12px',
                'line-height:1.55'
            ].join(';');

            tooltip.innerHTML =
                '<div class="au24-tooltip-title"></div>' +
                '<div class="au24-tooltip-formula"></div>';

            document.body.appendChild(tooltip);

            const style = document.createElement('style');
            style.textContent = `
                .au24-tooltip-title {
                    padding:9px 12px;
                    color:white;
                    font-weight:750;
                }
                .au24-tooltip-formula {
                    padding:11px 13px;
                    font-weight:600;
                    overflow-wrap:anywhere;
                }
                .au24-formula-tooltip-availability .au24-tooltip-title {
                    background:#15803d;
                }
                .au24-formula-tooltip-use .au24-tooltip-title {
                    background:#0369a1;
                }
                .au24-formula-tooltip-utilisation .au24-tooltip-title {
                    background:#7e22ce;
                }
                .au24-formula-hover {
                    cursor:help;
                }
            `;
            document.head.appendChild(style);
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
            const scope = `body[data-route="query-report/${name}"] .au24-report`;
            frappe.dom.set_style(`
                .au24-heading, .au24-actions { display: none; }
                ${scope} .au24-heading { display: block; margin: 0; padding: 24px 18px 26px;
                    font-size: 25px; font-weight: 700; color: var(--text-color); background: var(--fg-color);
                    border: 1px solid var(--border-color); border-bottom: 0; border-radius: 12px 12px 0 0; }
                ${scope} .page-form { display: grid !important; grid-template-columns: repeat(4, minmax(0, 1fr));
                    gap: 12px; align-items: start; margin: 0 0 18px; padding: 16px 18px;
                    border: 1px solid var(--border-color); border-top: 0; border-radius: 0 0 12px 12px; background: var(--fg-color); }
                ${scope} .page-form > .frappe-control { width: auto !important; max-width: none !important; min-width: 0; padding: 0; margin: 0 !important; }
                ${scope} .au24-filter-label { display: block; margin: 0 0 8px; font-size: 13px; font-weight: 650; color: var(--text-color); }
                ${scope} .page-form .form-control { height: 38px; min-height: 38px; font-size: 13px; border-radius: 7px; }
                ${scope} .page-form .multiselect-list { width: 100%; height: 38px; min-height: 38px; padding: 0; }
                ${scope} .page-form .select-icon { top: auto; bottom: 11px; }
                ${scope} .au24-run-filter { margin-top: 26px; height: 40px; font-size: 14px; background: #0866ff; border-color: #0866ff; color: white; border-radius: 7px; }
                ${scope} .au24-formula-filter .form-control { border: 1px solid #8ab4f8; background: #f0f6ff; color: #173e78; font-weight: 650; }
                ${scope} .au24-formula-filter .au24-filter-label { color: #173e78; }
                ${scope} .au24-target-card {
                    flex: 0 0 230px;
                    min-width: 220px;
                    max-width: 230px;
                    margin-left: auto;
                    padding: 7px 8px;
                    border: 1px solid var(--border-color);
                    border-radius: 10px;
                    background: var(--fg-color);
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 5px;
                    align-self: stretch;
                }
                ${scope} .au24-target-title {
                    grid-column: 1 / -1;
                    font-size: 12px;
                    font-weight: 700;
                    color: #DC2626;
                }
                ${scope} .au24-target-metric {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    gap: 3px;
                    min-width: 0;
                    padding: 6px 4px;
                    border-radius: 8px;
                    text-align: center;
                }
                ${scope} .au24-target-metric span {
                    font-size: 11px;
                    font-weight: 650;
                }
                ${scope} .au24-target-metric strong {
                    font-size: 18px;
                    line-height: 1.2;
                    font-weight: 800;
                }
                ${scope} .au24-target-availability-box {
                    background: #e1f9e4;
                    color: #174f2b;
                }
                ${scope} .au24-target-utilisation-box {
                    background: #eee2fb;
                    color: #61328c;
                }
                body[data-route="query-report/${name}"] .page-head .primary-action { display: none !important; }
                ${scope} .au24-actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; margin: 0 0 22px; }
                ${scope} .au24-actions .btn { white-space: normal; padding: 10px 14px; border: 1px solid var(--border-color); font-weight: 600; background: var(--fg-color); }
                ${scope} .datatable { font-size: 13px; border-radius: 8px; }
                ${scope} .dt-header { position: sticky; top: 0; z-index: 3; }
                ${scope} .dt-scrollable .dt-row:nth-child(even) .dt-cell { background: var(--subtle-fg); }
                ${scope} .dt-header .dt-cell { height: 64px !important; background: var(--subtle-fg); }
                ${scope} .dt-header, ${scope} .dt-header .dt-row { height: 64px !important; }
                ${scope} .dt-header { height: 104px !important; }
                ${scope} .dt-header .dt-row-filter, ${scope} .dt-row-filter .dt-cell { height: 40px !important; }
                ${scope} .dt-row-filter .dt-cell__content { min-height: 36px !important; height: 36px !important; padding: 3px 5px; }
                ${scope} .dt-filter { width: 100%; min-width: 0; height: 30px; border: 1px solid var(--border-color); border-radius: 4px; font-size: 12px; }
                ${scope} .dt-header .dt-cell__content { height: auto !important; min-height: 60px; white-space: normal; line-height: 1.4;
                    display: flex; align-items: center; font-size: 12px; font-weight: 700; text-overflow: clip; }
                ${scope} .au24-industry-columns .dt-header { height: 124px !important; }
                ${scope} .au24-industry-columns .dt-row-header, ${scope} .au24-industry-columns .dt-row-header .dt-cell { height: 84px !important; }
                ${scope} .au24-industry-columns .dt-row-header .dt-cell__content { min-height: 80px; }
                ${scope} .dt-row:has(.au24-shift-day) .dt-cell { background: #eaf4ff !important; }
                ${scope} .dt-row:has(.au24-shift-night) .dt-cell { background: #BFE5DC !important; }
                /* Result section grouping */
                ${scope} .dt-row-header .dt-cell.au24-group-header {
                    position: relative;
                    padding-top: 18px;
                }
                ${scope} .dt-row-header .dt-cell.au24-group-header .dt-cell__content {
                    min-height: 72px;
                }
                ${scope} .dt-row-header .dt-cell.au24-group-label::before {
                    content: attr(data-group-label);
                    position: absolute;
                    top: 4px;
                    left: 6px;
                    right: 6px;
                    text-align: center;
                    font-size: 10px;
                    line-height: 1.2;
                    font-weight: 800;
                    letter-spacing: .05em;
                    text-transform: uppercase;
                }
                ${scope} .dt-cell.au24-group-col.au24-group-availability {
                    background: rgba(34, 197, 94, 0.035);
                }
                ${scope} .dt-cell.au24-group-col.au24-group-use {
                    background: rgba(14, 165, 233, 0.04);
                }
                ${scope} .dt-cell.au24-group-col.au24-group-utilisation {
                    background: rgba(168, 85, 247, 0.04);
                }
                ${scope} .dt-row-header .dt-cell.au24-group-header.au24-group-availability {
                    background: #EFFAF1 !important;
                    border-top: 3px solid #22C55E !important;
                }
                ${scope} .dt-row-header .dt-cell.au24-group-header.au24-group-use {
                    background: #EFF8FC !important;
                    border-top: 3px solid #0EA5E9 !important;
                }
                ${scope} .dt-row-header .dt-cell.au24-group-header.au24-group-utilisation {
                    background: #F6F0FC !important;
                    border-top: 3px solid #A855F7 !important;
                }
                ${scope} .dt-row-header .dt-cell.au24-group-label.au24-group-availability::before {
                    color: #15803D;
                }
                ${scope} .dt-row-header .dt-cell.au24-group-label.au24-group-use::before {
                    color: #0369A1;
                }
                ${scope} .dt-row-header .dt-cell.au24-group-label.au24-group-utilisation::before {
                    color: #7E22CE;
                }
                ${scope} .dt-cell.au24-group-start.au24-group-availability {
                    border-left: 3px solid #22C55E !important;
                }
                ${scope} .dt-cell.au24-group-end.au24-group-availability {
                    border-right: 3px solid #22C55E !important;
                }
                ${scope} .dt-cell.au24-group-start.au24-group-use {
                    border-left: 3px solid #0EA5E9 !important;
                }
                ${scope} .dt-cell.au24-group-end.au24-group-use {
                    border-right: 3px solid #0EA5E9 !important;
                }
                ${scope} .dt-cell.au24-group-start.au24-group-utilisation {
                    border-left: 3px solid #A855F7 !important;
                }
                ${scope} .dt-cell.au24-group-end.au24-group-utilisation {
                    border-right: 3px solid #A855F7 !important;
                }
                ${scope} .dt-row-filter .dt-cell.au24-group-availability {
                    background: #F7FCF8 !important;
                }
                ${scope} .dt-row-filter .dt-cell.au24-group-use {
                    background: #F7FBFE !important;
                }
                ${scope} .dt-row-filter .dt-cell.au24-group-utilisation {
                    background: #FBF8FE !important;
                }
                ${scope} .dt-header .dt-cell__content {
                    justify-content: center !important;
                    text-align: center !important;
                }
                /* Force centre alignment over Frappe numeric alignment. */
                ${scope} .datatable .dt-scrollable .dt-cell:not(.dt-cell--col-0) .dt-cell__content,
                ${scope} .datatable .dt-scrollable .dt-cell--align-right .dt-cell__content {
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    text-align: center !important;
                }
                ${scope} .datatable .dt-scrollable .dt-cell:not(.dt-cell--col-0) .dt-cell__content > *,
                ${scope} .datatable .dt-scrollable .dt-cell--align-right .dt-cell__content > * {
                    text-align: center !important;
                }
                ${scope} .datatable .dt-scrollable .au24-percent,
                ${scope} .datatable .dt-scrollable .au24-calculated-hours {
                    width: 100%;
                    text-align: center !important;
                }
                ${scope} .dt-cell--col-0 .dt-cell__content {
                    text-align: left !important;
                    justify-content: flex-start !important;
                }
                ${scope} .au24-percent { display: block; padding: 2px 5px; border-radius: 5px; font-weight: 700; text-align: right; }
                ${scope} .au24-track { display: block; height: 3px; margin-top: 3px; background: rgba(0,0,0,.06); border-radius: 3px; overflow: hidden; }
                ${scope} .au24-fill { display: block; height: 100%; background: currentColor; opacity: .4; }
                ${scope} .au24-availability { background: #e1f9e4; color: #174f2b; }
                ${scope} .au24-utilisation { background: #eee2fb; color: #61328c; }
                ${scope} .au24-use { background: #e4f2f6; color: #23586a; }
                ${scope} .au24-calculated-hours { display: block; padding: 4px 5px; border-radius: 5px; font-weight: 700; }
                ${scope} .au24-tree-summary { font-weight: 650; }
                ${scope} .dt-cell--col-0 .dt-cell__content { white-space: nowrap; }
                ${scope} .au24-excluded { text-decoration: underline dotted; }
                ${scope} .au24-inconsistent { background: #fff0ca; color: #805300; box-shadow: inset 0 0 0 1px #c18413; }
                ${scope} .dt-cell:has(.au24-total-cell) { background: #edf2fa !important; border-top: 2px solid #8196b3; }
                ${scope} .au24-total-cell { display: block; font-weight: 750; }
                .au24-formula-help { color: var(--text-color); }
                .au24-formula-help h3 { font-size: 20px; margin: 0 0 16px; }
                .au24-isambane-formula { display: grid; gap: 10px; }
                .au24-isambane-formula h3 { font-size: 22px; font-weight: 750; margin: 0 0 8px; }
                .au24-isambane-card, .au24-isambane-example, .au24-isambane-targets {
                    padding: 12px 14px; border: 1px solid; border-radius: 10px;
                    border-left-width: 4px;
                }
                .au24-isambane-card h4, .au24-isambane-example h4,
                .au24-isambane-targets h4 { font-size: 15px; font-weight: 750; margin: 0 0 8px; }
                .au24-isambane-expression { background: rgba(255,255,255,.85);
                    border-radius: 7px; padding: 9px 11px; font-size: 14px;
                    line-height: 1.5; overflow-wrap: anywhere; }
                .au24-isambane-card.availability { background: #edf9ef;
                    border-color: #b9e8c2; border-left-color: #16a34a; }
                .au24-isambane-card.utilisation { background: #f5edff;
                    border-color: #ddc5fb; border-left-color: #7c3aed; }
                .au24-isambane-example, .au24-isambane-targets {
                    background: var(--subtle-fg); border-color: var(--border-color);
                    border-left-color: #87909d; display: flex; flex-direction: column; gap: 4px;
                }
                .au24-isambane-note { font-size: 12px; color: var(--text-muted);
                    line-height: 1.5; margin: 0; }
                .au24-formula-section { padding: 12px 14px; margin-bottom: 10px; border: 1px solid var(--border-color); border-radius: 7px; }
                .au24-formula-section h5 { font-size: 13px; font-weight: 700; margin: 0 0 7px; }
                .au24-formula-section p { white-space: pre-line; line-height: 1.6; margin: 0; font-size: 13px; overflow-wrap: anywhere; }
                .au24-formula-availability { border-left: 3px solid #319754; }
                .au24-formula-utilisation { border-left: 3px solid #8551b5; }
                ${scope} .report-summary, ${scope} .chart-wrapper { display: none !important; }
                ${scope} .form-message { font-size: 12px; }
                /* Match the original A&U Engine's compact native report layout. */
                ${scope} .page-form {
                    display: flex !important;
                    flex-flow: row wrap;
                    align-items: flex-end;
                    gap: 8px 10px;
                    margin: 0 0 10px;
                    padding: 0;
                    border: 0;
                    border-radius: 0;
                    background: transparent;
                }
                ${scope} .page-form > .frappe-control {
                    flex: 1 1 175px;
                    width: auto !important;
                    max-width: 220px !important;
                    min-width: 155px;
                    padding: 0;
                    margin: 0 !important;
                }
                ${scope} .page-form .form-control {
                    height: 32px;
                    min-height: 32px;
                    font-size: 12px;
                    border-radius: 4px;
                }
                ${scope} .page-form .multiselect-list {
                    width: 100%;
                    height: 32px;
                    min-height: 32px;
                    padding: 0;
                }
                ${scope} .page-form .select-icon {
                    top: auto;
                    bottom: 8px;
                }
                ${scope} .au24-filter-label {
                    display: none !important;
                }
                ${scope} .au24-targets {
                    font-size: 10px;
                    line-height: 1.2;
                    margin-top: 2px;
                    white-space: nowrap;
                }
                body[data-route="query-report/${name}"] .page-head .primary-action {
                    display: inline-flex !important;
                }
                @media (max-width: 1599px) {
                    ${scope} .page-form { grid-template-columns: repeat(4, minmax(0, 1fr)); }
                }
                @media (max-width: 767px) {
                    ${scope} .page-form { gap: 8px; }
                    ${scope} .page-form > .frappe-control {
                        flex: 1 1 145px;
                        max-width: none !important;
                    }
                }
                @media (max-width: 767px) {
                    ${scope} .au24-target-card {
                        flex: 1 1 100%;
                        max-width: none;
                        margin-left: 0;
                    }
                }
                @media (max-width: 479px) {
                    ${scope} .page-form > .frappe-control {
                        flex: 1 1 100%;
                    }
                }
            `);
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
