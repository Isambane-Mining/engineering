/* LAB E2E. Supply AU24_BROWSER_AUTH_FILE containing a temporary local sid.
 * Uses the bench's existing Playwright installation; never creates test business data.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('/home/juan/juan-bench/apps/raven/node_modules/playwright');

(async () => {
    const { sid } = JSON.parse(fs.readFileSync(process.env.AU24_BROWSER_AUTH_FILE, 'utf8'));
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1800, height: 1050 }, ignoreHTTPSErrors: true });
    await context.addCookies([{ name: 'sid', value: sid, domain: 'juan.isambane.co.za', path: '/', secure: true, httpOnly: true }]);
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    try {
        const query = new URLSearchParams({ from_date: '2026-08-01', to_date: '2026-08-07', sites: JSON.stringify(['Uitgevallen']), formula: 'Industry Formula' });
        await page.goto('https://juan.isambane.co.za/app/query-report/Availability%20and%20Utilisation%20Engine%20(24)?' + query, { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForFunction(() => window.frappe?.query_report?.data?.length > 1 && frappe.query_report.report_name === 'Availability and Utilisation Engine (24)', { timeout: 60000 });
        await page.waitForFunction(() => document.querySelector('.au24-report .dt-cell'));
        const desktop = await page.evaluate(() => {
            const r = frappe.query_report;
            const box = element => { const b = element.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, width: b.width }; };
            return { rows: r.data, columns: r.columns.map(c => c.fieldname),
                summaryVisible: r.$summary.is(':visible'),
                configurationTables: document.querySelectorAll('.au24-report table').length,
                green: document.querySelectorAll('.au24-availability').length,
                purple: document.querySelectorAll('.au24-utilisation').length,
                table: box(document.querySelector('.au24-report .report-wrapper')),
                notes: box(r.$report_message[0]),
                primary: r.page.btn_primary.text().trim(), filters: r.get_filter_values() };
        });
        const layout = await page.evaluate(() => ({
            labels: [...document.querySelectorAll('.au24-filter-label')].filter(e => e.getBoundingClientRect().height > 0).length,
            tableWidth: document.querySelector('.dt-scrollable').clientWidth,
            tableContent: document.querySelector('.dt-scrollable').scrollWidth,
            inlineRun: !!document.querySelector('.au24-run-filter'),
        }));
        assert.equal(layout.labels, 7);
        assert.equal(layout.inlineRun, true);
        assert.ok(layout.tableContent <= layout.tableWidth + 2, JSON.stringify(layout));
        assert.equal(desktop.rows.length, 28);
        assert.equal(desktop.columns.length, 15);
        assert.equal(desktop.rows.filter(r => r.is_total_row).length, 1);
        assert.equal(desktop.rows.at(-1).asset, 'Total / Average');
        assert.equal(new Set(desktop.rows.slice(0, -1).map(r => r.asset)).size, 27);
        assert.equal(desktop.primary, 'Run Report');
        assert.equal(desktop.summaryVisible, false);
        assert.equal(desktop.configurationTables, 0);
        assert.ok(desktop.green > 0);
        assert.ok(desktop.purple > 0);
        assert.equal(await page.evaluate(() => frappe.query_report.datatable.options.serialNoColumn), false);
        assert.ok(desktop.notes.top >= desktop.table.bottom - 1);
        await page.screenshot({ path: '/tmp/au24-desktop.png', fullPage: true });
        await page.evaluate(() => {
            const table = document.querySelector('.dt-scrollable');
            table.scrollLeft = table.scrollWidth;
            table.scrollTop = table.scrollHeight;
            table.dispatchEvent(new Event('scroll'));
        });
        await page.waitForFunction(() => [...document.querySelectorAll('.dt-row')].some(row => row.innerText.includes('Total / Average')));
        await page.screenshot({ path: '/tmp/au24-desktop-percentages.png', fullPage: true });

        await page.getByRole('button', { name: 'View Site Startup & Fatigue Configuration', exact: true }).click();
        const dialog = page.locator('.modal:visible');
        await dialog.locator('tbody tr').first().waitFor();
        assert.equal(await dialog.locator('tbody tr').count(), 4);
        const text = await dialog.innerText();
        for (const label of ['Uitgevallen', 'Weekday', 'Saturday', 'Sunday', 'Holiday', 'Not configured']) assert.ok(text.includes(label));
        await page.screenshot({ path: '/tmp/au24-configuration.png', fullPage: true });
        await page.keyboard.press('Escape');
        await dialog.waitFor({ state: 'hidden' });

        await page.evaluate(() => frappe.query_report.set_filter_value('formula', 'Isambane Formula'));
        await page.waitForFunction(() => frappe.query_report.data.length === 28 && frappe.query_report.columns[4].label === 'Required Hours (h)');
        assert.ok(await page.locator('.au24-report').innerText().then(text => text.includes('Utilisation 85%')));
        const unknown = await page.evaluate(() => ({
            tints: document.querySelectorAll('.au24-utilisation').length,
            dashes: [...document.querySelectorAll('.dt-cell__content .text-muted')].filter(e => e.textContent.trim() === '—').length,
        }));
        assert.ok(unknown.tints > 0);
        assert.ok(unknown.dashes > 0);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.screenshot({ path: '/tmp/au24-mobile.png', fullPage: true });
        assert.ok(await page.getByRole('button', { name: 'Run Report', exact: true }).isVisible());
        const mobile = await page.evaluate(() => ({ rows: frappe.query_report.data.length,
            docWidth: document.documentElement.scrollWidth, viewport: innerWidth,
            tableScroll: document.querySelector('.dt-scrollable')?.scrollWidth }));
        assert.equal(mobile.rows, 28);
        assert.ok(mobile.docWidth <= mobile.viewport + 2, JSON.stringify(mobile));
        await page.setViewportSize({ width: 1800, height: 1050 });
        await page.getByRole('button', { name: 'View Startup & Fatigue Configuration' }).click();
        await page.locator('.modal.show table').waitFor();
        const configuration = await page.locator('.modal.show').innerText();
        assert.match(configuration, /Site\\s+Shift\\s+Day Type\\s+Startup\\s+Fatigue/);
        assert.doesNotMatch(configuration, /Safety Meeting|Tramming Out/);
        await page.screenshot({ path: '/tmp/au24-original-configuration-dialog.png', fullPage: true });
        console.log(JSON.stringify({ desktopMachines: desktop.rows.length - 1, columns: desktop.columns.length,
            totals: 1, configurationDialog: true, mobile, pageErrors: errors }, null, 2));
        assert.equal(errors.length, 0);
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
