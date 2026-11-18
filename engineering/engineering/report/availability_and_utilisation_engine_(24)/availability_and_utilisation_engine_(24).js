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
            availability: 'Available = MAX(24 − Raw Breakdown − Raw Planned Maintenance, 0)\nAvailability = Available / 24',
            utilisation: 'Utilisation Available Hours = 24\nUtilisation = Working Hours / 24',
            variables: '24 = fixed hours per reported day. Raw Breakdown and Raw Planned Maintenance = recorded downtime hours, including startup/fatigue overlap. Working Hours = valid recorded working hours.',
            example: 'One day: breakdown 3 h, planned maintenance 1 h, working 15 h. Available = 20 h; availability = 20 / 24 = 83.33%; utilisation = 15 / 24 = 62.50%.',
            rules: 'No startup, fatigue, safety meeting or tramming out deductions. No Site Specific Startup and Fatigue lookup or old 18-hour threshold. Raw downtime is used without startup/fatigue overlap exclusions.',
        },
        'Isambane Formula': {
            availability: 'Remaining Required Hours = MAX(Required Hours − PBM Total Downtime, 0)\nAvailability Available Hours = MAX(Working Hours, Remaining Required Hours)\nAvailability = Availability Available Hours / Required Hours',
            utilisation: 'Utilisation Available Hours = MAX(Remaining Required Hours, MIN(Working Hours, Required Hours))\nUtilisation = Working Hours / Utilisation Available Hours',
            variables: 'Required Hours = original Engine required hours per shift. Working Hours = working hours accepted by the original Engine. PBM Total Downtime = breakdown and planned maintenance downtime after the original startup/fatigue overlap exclusions.',
            example: 'One shift: required 12 h, PBM downtime 2 h, working 9 h. Remaining = 10 h; availability available = 10 h; utilisation available = MAX(10, MIN(9, 12)) = 10 h. Availability = 10 / 12 = 83.33%; utilisation = 9 / 10 = 90.00%.',
            rules: 'PBM downtime excludes overlap with startup/fatigue according to the original Engine rules. Preserve its Pre-Use status exceptions, integrity checks, Sunday and zero-required-hours handling. MAX/MIN run per shift before period aggregation. Safety, fatigue and tramming columns are not additional deductions.',
        },
        'Use of Availability': {
            availability: 'Available = MAX(24 − Raw Breakdown − Raw Planned Maintenance, 0)\nAvailability = Available / 24',
            utilisation: 'Utilisation Available Hours = Available\nUtilisation = Working Hours / Available',
            variables: '24 = fixed hours per reported day. Raw Breakdown and Raw Planned Maintenance = recorded downtime hours, including startup/fatigue overlap. Available = hours remaining after those raw deductions. Working Hours = valid recorded working hours.',
            example: 'One day: breakdown 3 h, planned maintenance 1 h, working 15 h. Available = 20 h; availability = 20 / 24 = 83.33%; utilisation = 15 / 20 = 75.00%.',
            rules: 'No startup, fatigue, safety meeting or tramming out deductions. No Site Specific Startup and Fatigue lookup or old 18-hour threshold. Preserve utilisation above 100% and flag inconsistent records, including days with working hours but zero available hours.',
        },
    };

    function target_text(report) {
        const targets = report._au24_targets?.[report.get_filter_value('formula')];
        const percent = value => value == null ? __('Not configured') : `${Number((value * 100).toFixed(2))}%`;
        if (!report._au24_targets) return __('Targets unavailable');
        return `${__('Availability')} ${percent(targets?.availability)} · ${__('Utilisation')} ${percent(targets?.utilisation)}`;
    }

    function sync_formula(report) {
        report.page.page_form.find('.au24-targets').text(target_text(report));
        const dialog = report._au24_formula_dialog;
        if (!dialog) return;
        const selected = report.get_filter_value('formula');
        const details = formula_details[selected];
        if (!details) return;
        const section = (label, content, kind = '') => `<section class="au24-formula-section ${kind}"><h5>${escape(__(label))}</h5><p>${escape(__(content))}</p></section>`;
        dialog.fields_dict.explanation.$wrapper.html(
            `<div class="au24-formula-help"><h3>${escape(__(selected))}</h3>` +
            section('Availability calculation', details.availability, 'au24-formula-availability') +
            section('Utilisation calculation', details.utilisation, 'au24-formula-utilisation') +
            section('Variables', details.variables) + section('Worked example', details.example) +
            section('Reference targets', target_text(report)) +
            section('Important rules', details.rules + ' Period and bottom-row percentages divide summed underlying hours, not averages of displayed percentages. Zero denominators display a dash. Decimal ratios are formatted as percentages only for display. Targets are reference values and do not scale results. Values above 100% are retained and highlighted.') + '</div>'
        );
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
        $('<h2 class="au24-heading"></h2>').append('<span aria-hidden="true">📊</span> ')
            .append(document.createTextNode(__(name))).insertBefore(form);
        for (const filter of report.filters) {
            const label = $('<label class="au24-filter-label"></label>')
                .html(escape(filter.df.label) + (filter.df.reqd ? ' <span class="text-danger">*</span>' : ''));
            const id = 'au24-filter-' + filter.df.fieldname;
            label.attr('for', id).prependTo(filter.$wrapper);
            filter.$wrapper.find('input, select, button').first().attr({ id, 'aria-label': filter.df.label });
        }
        $('<button type="button" class="btn btn-primary au24-run-filter"></button>')
            .text(__('Run Report')).on('click', () => report.refresh()).appendTo(form);
        const actions = $('<div class="au24-actions"></div>').insertAfter(form);
        formula_button?.appendTo(actions);
        configuration_button?.appendTo(actions);
        const formula = report.get_filter('formula');
        formula.$wrapper.addClass('au24-formula-filter');
        $('<div class="au24-targets" role="status" aria-live="polite"></div>').appendTo(formula.$wrapper);
        sync_formula(report);
    }

    function fit_columns(datatable) {
        // Fixed, readable minimum widths on small screens; fit all columns on
        // desktop. Apply after every render because Frappe refreshes its model.
        const weights = [36, 94, 120, 100, 95, 95, 112, 110, 76, 100, 124, 110, 124, 110, 110];
        const width = Math.max(1380, datatable.datatableWrapper.clientWidth) - weights.length - 2;
        const total = weights.reduce((sum, value) => sum + value, 0);
        datatable.datamanager.getColumns().forEach((column, index) => {
            datatable.datamanager.updateColumn(column.colIndex, { width: Math.floor(width * weights[index] / total) });
        });
        datatable.style.setDimensions();
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
        filters: [
            { fieldname: 'from_date', label: __('From Date'), fieldtype: 'Date', reqd: 1, default: frappe.datetime.month_start() },
            { fieldname: 'to_date', label: __('To Date'), fieldtype: 'Date', reqd: 1, default: frappe.datetime.get_today() },
            link_filter('sites', 'Site', 'Location'),
            link_filter('assets', 'Asset', 'Asset'),
            link_filter('companies', 'Company', 'Company'),
            { fieldname: 'asset_ownership', label: __('Asset Ownership'), fieldtype: 'Select',
                options: 'Isambane & Excavo Assets\nSupplier Assets\nAll Assets', default: 'Isambane & Excavo Assets' },
            { fieldname: 'formula', label: __('Formula'), fieldtype: 'Select',
                options: 'Industry Formula\nIsambane Formula\nUse of Availability', default: 'Isambane Formula', reqd: 1,
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
                ${scope} .page-form { display: grid !important; grid-template-columns: repeat(7, minmax(0, 1fr)) 125px;
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
                ${scope} .au24-targets { font-size: 11px; line-height: 1.5; margin-top: 6px; color: var(--text-muted); }
                body[data-route="query-report/${name}"] .page-head .primary-action { display: none !important; }
                ${scope} .au24-actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; margin: 0 0 22px; }
                ${scope} .au24-actions .btn { white-space: normal; padding: 10px 14px; border: 1px solid var(--border-color); font-weight: 600; background: var(--fg-color); }
                ${scope} .datatable { font-size: 13px; border-radius: 8px; }
                ${scope} .dt-header { position: sticky; top: 0; z-index: 3; }
                ${scope} .dt-scrollable .dt-row:nth-child(even) .dt-cell { background: var(--subtle-fg); }
                ${scope} .dt-header .dt-cell { height: 64px !important; background: var(--subtle-fg); }
                ${scope} .dt-header, ${scope} .dt-header .dt-row { height: 64px !important; }
                ${scope} .dt-header .dt-cell__content { height: auto !important; min-height: 60px; white-space: normal; line-height: 1.4;
                    display: flex; align-items: center; font-size: 12px; font-weight: 700; text-overflow: clip; }
                ${scope} .dt-cell--align-right .dt-cell__content { text-align: right; justify-content: flex-end; }
                ${scope} .au24-percent { display: block; padding: 2px 5px; border-radius: 5px; font-weight: 700; text-align: right; }
                ${scope} .au24-track { display: block; height: 3px; margin-top: 3px; background: rgba(0,0,0,.06); border-radius: 3px; overflow: hidden; }
                ${scope} .au24-fill { display: block; height: 100%; background: currentColor; opacity: .4; }
                ${scope} .au24-availability { background: #e1f9e4; color: #174f2b; }
                ${scope} .au24-utilisation { background: #eee2fb; color: #61328c; }
                ${scope} .au24-inconsistent { background: #fff0ca; color: #805300; box-shadow: inset 0 0 0 1px #c18413; }
                ${scope} .dt-cell:has(.au24-total-cell) { background: #edf2fa !important; border-top: 2px solid #8196b3; }
                ${scope} .au24-total-cell { display: block; font-weight: 750; }
                .au24-formula-help { color: var(--text-color); }
                .au24-formula-help h3 { font-size: 20px; margin: 0 0 16px; }
                .au24-formula-section { padding: 12px 14px; margin-bottom: 10px; border: 1px solid var(--border-color); border-radius: 7px; }
                .au24-formula-section h5 { font-size: 13px; font-weight: 700; margin: 0 0 7px; }
                .au24-formula-section p { white-space: pre-line; line-height: 1.6; margin: 0; font-size: 13px; overflow-wrap: anywhere; }
                .au24-formula-availability { border-left: 3px solid #319754; }
                .au24-formula-utilisation { border-left: 3px solid #8551b5; }
                ${scope} .report-summary, ${scope} .chart-wrapper { display: none !important; }
                ${scope} .form-message { font-size: 12px; }
                @media (max-width: 1599px) {
                    ${scope} .page-form { grid-template-columns: repeat(4, minmax(0, 1fr)); }
                }
                @media (max-width: 767px) {
                    ${scope} .page-form { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 12px; }
                    ${scope} .au24-heading { font-size: 20px; padding: 18px; }
                }
                @media (max-width: 479px) {
                    ${scope} .page-form { grid-template-columns: minmax(0, 1fr); }
                    ${scope} .au24-actions .btn { width: 100%; }
                }
            `);
            run_button(report);
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
            // The explicit # column is the only numbering column. Use report
            // filters, not local row filters/sorts that could move the manual
            // weighted total or make it describe a different set of rows.
            return { ...options, cellHeight: 40, minimumColumnWidth: 32, serialNoColumn: false, inlineFilters: false,
                columns: (options.columns || []).map(column => ({ ...column, sortable: false, dropdown: false,
                    align: ['Int', 'Float', 'Percent', 'Currency'].includes(column.fieldtype) ? 'right' : 'left' })) };
        },
        formatter(value, row, column, data, default_formatter) {
            let rendered;
            if (value === null || value === undefined) {
                rendered = '<span class="text-muted">—</span>';
                if (column.fieldname === 'utilisation_percent' && data?.utilisation_inconsistent) {
                    rendered += ` <span title="${escape(data.utilisation_warning || __('Working hours exceed available hours.'))}" aria-label="${escape(__('Data inconsistency'))}">⚠</span>`;
                }
            } else {
                const is_ratio = column.fieldname === 'availability_percent' || column.fieldname === 'utilisation_percent';
                // Backend values remain decimal ratios (0.85). Frappe's Percent
                // formatter expects 85, so scale only this display argument.
                rendered = default_formatter(is_ratio ? Number(value) * 100 : value, row, column, data);
                if (is_ratio) {
                    const kind = column.fieldname === 'availability_percent' ? 'availability' : 'utilisation';
                    const flagged = Number(value) > 1 || (kind === 'utilisation' && data?.utilisation_inconsistent);
                    const warning = kind === 'utilisation' && data?.utilisation_warning || __('Result exceeds 100%. Actual ratio is not capped.');
                    const title = flagged ? ` title="${escape(warning)}"` : '';
                    const progress = Math.min(100, Math.max(0, Number(value) * 100));
                    rendered = `<span class="au24-percent au24-${kind}${flagged ? ' au24-inconsistent' : ''}"${title}>${rendered}${flagged ? ` <span role="img" aria-label="${escape(__('Data warning'))}">⚠</span>` : ''}<span class="au24-track" aria-hidden="true"><span class="au24-fill" style="width:${progress}%"></span></span></span>`;
                }
            }
            return data?.is_total_row ? `<strong class="au24-total-cell">${rendered}</strong>` : rendered;
        },
    };
})();
