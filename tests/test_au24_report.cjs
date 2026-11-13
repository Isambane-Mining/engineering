const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const filename = path.join(__dirname, '../engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js');

function load() {
    const state = { calls: [], dialogs: [], styles: [] };
    const context = {
        __: text => text,
        frappe: {
            query_reports: {},
            datetime: { get_today: () => '2026-03-31', month_start: () => '2026-03-01' },
            utils: { escape_html: value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;') },
            db: { get_link_options: () => [] },
            dom: { set_style: css => state.styles.push(css) },
            xcall: async (method, args) => { state.calls.push({ method, args }); return state.rows || []; },
            ui: { Dialog: class {
                constructor(options) { this.options = options; state.dialogs.push(this); this.fields_dict = { configuration: { $wrapper: { html: html => { this.html = html; } } } }; }
                show() { this.shown = true; }
            } },
        },
    };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(filename, 'utf8'), context);
    return { state, settings: context.frappe.query_reports['Availability and Utilisation Engine (24)'] };
}

test('seven filters, Isambane default, explicit Run Report, no summaries', () => {
    const { settings, state } = load();
    assert.deepEqual(Array.from(settings.filters, f => f.label), ['From Date', 'To Date', 'Site', 'Asset', 'Company', 'Asset Ownership', 'Formula']);
    assert.equal(settings.filters.at(-1).default, 'Isambane Formula');
    const buttons = [];
    let runs = 0;
    const report = { page: { main: { addClass() {} }, set_primary_action: (label, fn) => buttons.push({ label, fn }), add_inner_button: (label, fn) => buttons.push({ label, fn }) }, refresh: () => runs++ };
    settings.onload(report);
    assert.equal(buttons[0].label, 'Run Report');
    buttons[0].fn();
    assert.equal(runs, 1);
    assert.equal(buttons[1].label, 'View Site Startup & Fatigue Configuration');
    assert.equal(state.calls.length, 0);
    assert.equal(settings.report_summary, undefined);
    assert.equal(state.dialogs.length, 0);
    assert.ok(state.styles[0].includes('body[data-route="query-report/Availability and Utilisation Engine (24)"]'));
    assert.ok(!/^\s*\.au24-report/m.test(state.styles[0]), 'all styles must be scoped to this report route');
});

test('configuration only in dialog, selected sites passed, all four types and escaping', async () => {
    const { settings, state } = load();
    const buttons = [];
    state.rows = ['Weekday', 'Saturday', 'Sunday', 'Holiday'].map(day_type => ({ site: '<script>', day_type, configured: false }));
    const report = { get_filter_value: () => ['Uitgevallen'], page: { main: { addClass() {} }, set_primary_action() {}, add_inner_button: (label, fn) => buttons.push(fn) } };
    settings.onload(report);
    await buttons[0]();
    assert.deepEqual(Array.from(state.calls[0].args.sites), ['Uitgevallen']);
    const dialog = state.dialogs[0];
    assert.equal(dialog.shown, true);
    for (const day of ['Weekday', 'Saturday', 'Sunday', 'Holiday']) assert.ok(dialog.html.includes(day));
    assert.ok(dialog.html.includes('Not configured'));
    assert.ok(dialog.html.includes('&lt;script&gt;'));
    assert.ok(!dialog.html.includes('<script>'));
    report.get_filter_value = () => [];
    await buttons[0]();
    assert.equal(state.calls[1].args.sites.length, 0);
});

test('percent column tints, dashes and bottom total formatting', () => {
    const { settings } = load();
    const format = (value, col) => settings.formatter(value, null, { fieldname: col }, {}, v => String(v));
    assert.ok(format(.875, 'availability_percent').includes('au24-availability'));
    assert.ok(format(.75, 'utilisation_percent').includes('au24-utilisation'));
    assert.ok(format(null, 'utilisation_percent').includes('—'));
    assert.ok(!format(null, 'utilisation_percent').includes('au24-utilisation'));
    assert.ok(format(0, 'availability_percent').includes('0'));
    assert.ok(format(.875, 'availability_percent').includes('87.5'));
    assert.ok(format(.75, 'utilisation_percent').includes('75'));
    const total = settings.formatter('Total / Average', null, { fieldname: 'asset' }, { is_total_row: true }, v => v);
    assert.ok(total.includes('<strong>'));
});

test('one rank column and bottom totals cannot be moved by local sorting/filtering', () => {
    const { settings } = load();
    const options = settings.get_datatable_options({ columns: [{ id: 'index' }, { id: 'asset' }] });
    assert.equal(options.serialNoColumn, false);
    assert.equal(options.inlineFilters, false);
    assert.ok(options.columns.every(c => c.sortable === false && c.dropdown === false));
});
