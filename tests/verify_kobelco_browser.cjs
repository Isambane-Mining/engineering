/* LAB UI check. Sample rows are browser-only and discarded without saving.
 * No credential writes or vendor API calls. Supply KOBELCO_BROWSER_AUTH_FILE.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('../../raven/node_modules/playwright');
(async () => {
    const { sid } = JSON.parse(fs.readFileSync(process.env.KOBELCO_BROWSER_AUTH_FILE, 'utf8'));
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1600, height: 1050 }, ignoreHTTPSErrors: true });
    await context.addCookies([{ name: 'sid', value: sid, domain: 'juan.isambane.co.za', path: '/', secure: true, httpOnly: true }]);
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    try {
        await page.goto('https://juan.isambane.co.za/app/api-kobelco-settings', { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForFunction(() => window.cur_frm?.doctype === 'API Kobelco Settings' && cur_frm.fields_dict.machine_mappings);
        assert.deepEqual(await page.locator('.form-tabs [role="tab"]').allTextContents().then(labels => labels.map(x => x.trim())), ['API Configuration', 'Machine Mapping']);
        const settings = await page.evaluate(() => ({
            username: cur_frm.doc.username || '', usernameInput: cur_frm.fields_dict.username.$input.val(),
            passwordType: cur_frm.fields_dict.password.df.fieldtype, passwordPresent: !!cur_frm.doc.password,
            tableType: cur_frm.fields_dict.machine_mappings.df.fieldtype, tableOptions: cur_frm.fields_dict.machine_mappings.df.options,
        }));
        assert.equal(settings.username, '');
        assert.equal(settings.usernameInput, '');
        assert.equal(settings.passwordType, 'Password');
        assert.equal(settings.passwordPresent, false);
        assert.equal(settings.tableType, 'Table');
        assert.equal(settings.tableOptions, 'Kobelco Machine Mapping');
        await page.getByRole('button', { name: 'Test Connection', exact: true }).waitFor();
        await page.getByRole('button', { name: 'Fetch Fleet', exact: true }).waitFor();
        assert.ok(await page.getByRole('button', { name: 'Fetch Fleet', exact: true }).isDisabled());
        await page.screenshot({ path: '/tmp/kobelco-settings-revised.png', fullPage: true });
        await page.getByRole('tab', { name: 'Machine Mapping', exact: true }).click();
        await page.locator('[data-fieldname="machine_mappings"] .grid-body').waitFor();
        const asset = await page.evaluate(async () => {
            const assets = await frappe.db.get_list('Asset', { fields: ['name'], limit: 1 });
            cur_frm.add_child('machine_mappings', { serial_number: 'UI-ONLY-SAMPLE', pin: 'UI-ONLY-PIN', oem: 'KOBELCO', model: 'SK850LC', mapping_status: 'Unmapped', last_seen: '2026-11-19 08:00:00' });
            cur_frm.refresh_field('machine_mappings');
            return assets[0].name;
        });
        const grid = page.locator('[data-fieldname="machine_mappings"]');
        await grid.getByText('Unmapped', { exact: true }).waitFor();
        await grid.locator('.grid-row').filter({ hasText: 'UI-ONLY-SAMPLE' }).locator('.grid-static-col[data-fieldname="asset"]').click();
        const assetInput = grid.locator('[data-fieldname="asset"] input:visible');
        await assetInput.fill(asset);
        await page.getByRole('option').filter({hasText: asset}).first().click();
        await page.waitForFunction(name => cur_frm.doc.machine_mappings.some(row => row.asset === name && row.mapping_status === 'Mapped'), asset);
        assert.equal(await page.evaluate(() => cur_frm.doctype), 'API Kobelco Settings');
        await page.getByRole('tab', { name: 'Machine Mapping', exact: true }).click();
        await page.screenshot({ path: '/tmp/kobelco-mapping-revised.png', fullPage: true });
        await page.evaluate(() => { cur_frm.doc.__unsaved = 0; frappe.set_route('List', 'Kobelco Results'); });
        await page.waitForFunction(() => window.cur_list?.doctype === 'Kobelco Results' && cur_list.page?.inner_toolbar?.text()?.includes('Sync Now'));
        await page.getByRole('button', { name: 'Machine Mapping', exact: true }).click();
        await page.waitForFunction(() => cur_frm?.doctype === 'API Kobelco Settings' && cur_frm.fields_dict.machine_mappings.tab.is_active());
        await page.goto('https://juan.isambane.co.za/app/engineering', { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.getByText('Kobelco Integration', { exact: true }).waitFor();
        for (const route of ['api-kobelco-settings', 'kobelco-results']) assert.ok(await page.locator(`a[href*="/${route}"]`).count() > 0, route);
        assert.equal(await page.locator('a[href*="/kobelco-asset-mapping"]').count(), 0);
        assert.deepEqual(errors, []);
        console.log(JSON.stringify({ ok: true, checks: ['two native tabs', 'blank credentials', 'native API buttons', 'inline Asset selection and status', 'Results-to-mapping tab', 'workspace links'] }));
    } catch (error) {
        await page.screenshot({ path: '/tmp/kobelco-browser-revised-failure.png', fullPage: true });
        console.error(JSON.stringify({ url: page.url(), errors }));
        throw error;
    } finally { await context.close(); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
