/* Read-only LAB Results verification. No Settings access, saves or vendor calls. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('../../raven/node_modules/playwright');
(async () => {
    const { sid } = JSON.parse(fs.readFileSync(process.env.KOBELCO_BROWSER_AUTH_FILE, 'utf8'));
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1600, height: 1050 }, ignoreHTTPSErrors: true });
    await context.addCookies([{ name: 'sid', value: sid, domain: 'juan.isambane.co.za', path: '/', secure: true, httpOnly: true }]);
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    try {
        await page.goto('https://juan.isambane.co.za/app/kobelco-results', { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForFunction(() => window.cur_list?.doctype === 'Kobelco Results' && cur_list.settings.formatters?.snapshot_timestamp);
        const name = await page.evaluate(async () => {
            const rows = await frappe.db.get_list('Kobelco Results', { fields: ['name'], filters: { serial_number: 'LY02510013' }, limit: 1 });
            if (!rows.length) throw new Error('Audited LAB machine has no result');
            return rows[0].name;
        });
        assert.equal(await page.evaluate(() => cur_list.settings.formatters.snapshot_timestamp('2026-11-19 12:06:25')), '2026-11-19 14:06:25');
        await page.evaluate(name => frappe.set_route('Form', 'Kobelco Results', name), name);
        await page.waitForFunction(() => window.cur_frm?.doctype === 'Kobelco Results' && cur_frm.fields_dict.fetched_at.df.hide_timezone === true);
        const data = await page.evaluate(() => {
            const fields = ['fetched_at', 'location_timestamp', 'engine_status_timestamp', 'operating_hours_timestamp'];
            return {
                systemZone: frappe.boot.time_zone.system,
                fields: Object.fromEntries(fields.map(field => [field, {
                    raw: cur_frm.doc[field],
                    displayed: cur_frm.fields_dict[field].disp_area.textContent.trim(),
                    description: cur_frm.fields_dict[field].$wrapper.find('.help-box').text(),
                    label: cur_frm.fields_dict[field].df.label,
                }])),
                engineNumber: cur_frm.doc.engine_number,
                pto: cur_frm.doc.pto_hours, loads: cur_frm.doc.load_count,
                fuel24: cur_frm.doc.fuel_used_last24, tank: cur_frm.doc.fuel_tank_capacity,
                def: cur_frm.doc.def_remaining, defAvailable: cur_frm.doc.def_remaining_available,
                warning: cur_frm.doc.source_time_warning,
                rawPresent: !!cur_frm.doc.raw_json,
            };
        });
        assert.equal(data.systemZone, 'Asia/Kolkata');
        assert.equal(data.fields.fetched_at.displayed, '2026-11-19 13:59:00');
        assert.equal(data.fields.location_timestamp.displayed, '2026-11-18 00:00:00');
        assert.equal(data.fields.operating_hours_timestamp.displayed, '2026-11-19 00:00:00');
        assert.equal(data.fields.engine_status_timestamp.displayed, '2026-11-19 23:45:00');
        for (const field of Object.values(data.fields)) {
            assert.ok(field.description.includes('Africa/Johannesburg'));
            assert.ok(!field.description.includes('Asia/Kolkata'));
            assert.ok(!field.label.includes('Johannesburg')); // export headings must not mislabel UTC
        }
        assert.equal(data.engineNumber, '00638737');
        assert.equal(data.pto, 9157); assert.equal(data.loads, 292);
        assert.equal(data.fuel24, 165); assert.equal(data.tank, 960);
        assert.equal(data.def, 0); assert.equal(data.defAvailable, 1);
        assert.ok(data.warning.includes('engine_status_timestamp'));
        assert.ok(data.rawPresent);
        await page.screenshot({ path: '/tmp/kobelco-results-audited.png', fullPage: true });
        assert.deepEqual(errors, []);
        console.log('LAB Results browser checks passed: UTC storage, Johannesburg form/list display, neutral export labels, recovered telemetry, genuine zero, source warning, unchanged system timezone.');
    } catch (error) {
        await page.screenshot({ path: '/tmp/kobelco-results-audit-failure.png', fullPage: true });
        console.error(JSON.stringify({ url: page.url(), errors }));
        throw error;
    } finally { await context.close(); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
