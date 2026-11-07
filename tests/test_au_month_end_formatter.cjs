// Exercise the actual Desk formatter without a browser or Frappe site.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = {
    __: value => value,
    flt: value => Number(value) || 0,
    frappe: {
        query_reports: {},
        datetime: { month_start: () => '2026-10-01', month_end: () => '2026-10-31' },
        query_report: { get_filter_value: () => '85% A & U' },
        utils: { escape_html: value => String(value) },
    },
};
context.window = context;
vm.runInNewContext(fs.readFileSync(path.join(__dirname,
    '../engineering/engineering/report/availability_and_utilisation_month_end_report/availability_and_utilisation_month_end_report.js'), 'utf8'), context);
const formatter = context.frappe.query_reports['Availability and Utilisation Month End Report'].formatter;
for (const field of ['avail_percent', 'util_percent']) {
    for (const value of [null, undefined, '']) {
        const html = formatter(value, 0, { fieldname: field },
            { asset_name: 'EX015', [field]: value }, raw => raw == null ? '' : String(raw));
        assert.match(html, /N\/A/, `${field} must disclose an undefined denominator`);
        assert.doesNotMatch(html, /#fee2e2/, 'N/A must not look like measured zero performance');
    }
    const html = formatter(0, 0, { fieldname: field },
        { asset_name: 'EX015', [field]: 0 }, String);
    assert.doesNotMatch(html, /N\/A/, 'A measured zero must remain zero');
}
console.log('Month End formatter: undefined availability/utilisation are N/A; real zero remains zero.');
