"""Run shipped standalone JS in Chromium with real jQuery and API/UI doubles."""
import json
from datetime import datetime, timedelta
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright, expect

PAGE = Path(__file__).parent
BENCH = PAGE.parents[5]
SOURCE = BENCH / 'apps/is_production/is_production/production/page/hourly_productivity_analysis'


def fixture():
    return dict(site='Test Site', hours=[f'{(i+6)%24:02}:00' for i in range(24)], rows=[
        dict(date=f'2026-{m:02}-01', day='Thu', month=label, month_key=str(m), fleet_total=4,
             cells=[dict(start=str(datetime(2026,m,1,6)+timedelta(hours=h)),
                         end=str(datetime(2026,m,1,6)+timedelta(hours=h+1)),available=[4, 3.5, 3, 3, 3, None][h%6], utilised=[4, 2, 1, 0, 0, None][h%6],
                         completed=h!=23, has_record=h!=22) for h in range(24)])
        for m, label in [(9, 'September 2026'), (10, 'October 2026')]])


class TestMachinesAvailableBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':1440, 'height':1000})
        self.page.set_default_timeout(5000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.set_content('<html><head><base href="https://lab.test/"></head><body><main></main></body></html>')
        self.page.add_script_tag(path=str(BENCH/'apps/frappe/node_modules/jquery/dist/jquery.min.js'))
        self.page.evaluate('''data => {
            window.wrapper={}; window.fixture=data; window.calls=[]; window.messages=[];
            window.frappe={pages:{'machines-available':{}},msgprint:m=>messages.push(m),
              call:async req=>{calls.push(req);return {message:req.method.endsWith('get_defaults')?
                {from_date:'2026-09-01',to_date:'2026-10-01'}:structuredClone(fixture)};},
              ui:{make_app_page:()=>({main:$('main')}),form:{make_control:({parent,df})=>{
                const input=$('<input>').attr('data-filter',df.fieldname).appendTo(parent);
                input.on('change',df.onchange);
                return {get_value:()=>input.val(),set_value:async value=>{input.val(value);await df.onchange();}};
              }}}};
        }''', fixture())
        self.page.add_style_tag(path=str(PAGE/'machines_available.css'))
        self.page.add_script_tag(path=str(PAGE/'machines_available.js'))
        self.page.evaluate("async()=>{frappe.pages['machines-available'].on_page_load(wrapper);await wrapper.machinesAvailable.ready;}")

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.page.close()

    def load(self):
        self.page.evaluate("wrapper.machinesAvailable.site.set_value('Test Site')")
        self.page.wait_for_selector('.hm-cal-day')
        self.page.click('#hm-mode-heatmap')
        self.page.wait_for_selector('.hm-cell')

    def test_independent_filters_scopes_dates_and_highlight(self):
        self.assertEqual(self.page.evaluate('calls.length'), 1)
        self.assertEqual(self.page.locator('[role=tab]').count(), 3)
        self.assertEqual(self.page.locator('script[src*="summary"]').count(), 0)
        self.load()
        self.assertEqual(self.page.locator('.hm-cell').count(), 24)
        self.assertEqual(self.page.locator('.hm-heat-table tbody tr').count(), 30)
        self.assertEqual(self.page.locator('.hpa-shift-day').inner_text().strip(), 'DAY SHIFT · 06:00–18:00')
        self.assertEqual(self.page.locator('.hpa-shift-night').inner_text().strip(), 'NIGHT SHIFT · 18:00–06:00')
        for scope in ['production', 'spare', 'all']:
            self.page.select_option('.hm-scope', scope)
            self.assertEqual(self.page.evaluate('calls.at(-1).args.machine_scope'), scope)
        self.page.evaluate("wrapper.machinesAvailable.from_date.set_value('2026-09-02')")
        self.assertEqual(self.page.evaluate('calls.at(-1).args.from_date'), '2026-09-02')
        self.page.evaluate("wrapper.machinesAvailable.to_date.set_value('2026-10-02')")
        self.assertEqual(self.page.evaluate('calls.at(-1).args.to_date'), '2026-10-02')
        count = self.page.evaluate('calls.length')
        self.page.select_option('.hm-unavailable', '1')
        self.assertGreater(self.page.locator('.hm-unavailable-match').count(), 0)
        self.assertEqual(self.page.evaluate('calls.length'), count)
        self.assertEqual(self.page.locator('.hm-unavailable-match').first.evaluate('(e)=>getComputedStyle(e).boxShadow'),
                         'rgb(220, 38, 38) 0px 0px 0px 2px inset')
        self.page.select_option('.hm-unavailable', '0')
        self.assertIn('4 / 4', self.page.locator('.hm-unavailable-match').first.text_content())

    def test_site_selected_while_defaults_load_still_refreshes(self):
        self.page.evaluate("""async()=>{
            const original=frappe.call;
            let completeDefaults;
            frappe.call=req=>req.method.endsWith('get_defaults')?
              new Promise(resolve=>{completeDefaults=resolve;}):original(req);
            frappe.pages['machines-available'].on_page_load(wrapper);
            await wrapper.machinesAvailable.site.set_value('Test Site');
            completeDefaults({message:{from_date:'2026-09-01',to_date:'2026-10-01'}});
            await wrapper.machinesAvailable.ready;
        }""")
        self.assertEqual(self.page.locator('.hm-cal-day').count(),30)

    def test_page_uses_own_defaults_and_preserves_manual_dates_across_views(self):
        self.assertEqual(self.page.evaluate('calls[0].method'),
                         'engineering.engineering.page.machines_available.machines_available.get_defaults')
        self.assertEqual(self.page.locator('[data-filter=hm_from_date]').input_value(), '2026-09-01')
        self.assertEqual(self.page.locator('[data-filter=hm_to_date]').input_value(), '2026-10-01')
        self.load()
        self.page.evaluate("""async()=>{
            await wrapper.machinesAvailable.from_date.set_value('2026-09-02');
            await wrapper.machinesAvailable.to_date.set_value('2026-10-02');
        }""")
        calls = self.page.evaluate('calls.length')
        for mode in ['calendar', 'day', 'heatmap', 'calendar']:
            self.page.click('#hm-mode-' + mode)
            self.assertEqual(self.page.locator('[data-filter=hm_from_date]').input_value(), '2026-09-02')
            self.assertEqual(self.page.locator('[data-filter=hm_to_date]').input_value(), '2026-10-02')
        self.assertEqual(self.page.evaluate('calls.length'), calls)

    def test_export_carries_all_selected_filters(self):
        self.load()
        self.page.select_option('.hm-scope','spare')
        self.page.select_option('.hm-unavailable','1')
        downloads=[]
        self.page.route('**/api/method/**', lambda route: (downloads.append(route.request.url), route.fulfill(status=200,body='test workbook',headers={'Content-Disposition':'attachment; filename=test.xlsx','Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})))
        from urllib.parse import urlparse, parse_qs
        for mode in ['calendar','day','heatmap']:
            self.page.click('#hm-mode-'+mode)
            selector='.hm-export' if mode=='day' else '.hm-view-export'
            with self.page.expect_request('**/api/method/**') as request, self.page.expect_download():
                self.page.click(selector, no_wait_after=True)
            self.assertEqual(parse_qs(urlparse(request.value.url).query), dict(site=['Test Site'],from_date=['2026-09-01'],
                             to_date=['2026-10-01'],machine_scope=['spare'],unavailable_number=['1']))

    def test_invalid_dates_errors_and_stale_responses_clear_data(self):
        self.load()
        self.page.evaluate("wrapper.machinesAvailable.from_date.set_value('2026-11-01')")
        self.assertEqual(self.page.locator('.hm-cell').count(),0)
        self.page.select_option('.hm-unavailable','1')
        self.assertEqual(self.page.locator('.hm-cell').count(),0)
        self.page.click('.hm-export')
        self.assertEqual(self.page.evaluate('messages.at(-1)'), 'Select valid site and dates.')
        self.page.evaluate("wrapper.machinesAvailable.from_date.set_value('2026-09-01')")
        self.page.evaluate('''async()=>{frappe.call=async()=>{throw Error('Denied')};await wrapper.machinesAvailable.refresh();}''')
        self.assertIn('permissions',self.page.locator('.hm-status').inner_text())
        self.page.select_option('.hm-unavailable','0')
        self.assertEqual(self.page.locator('.hm-cell').count(),0)
        self.page.evaluate('''()=>{window.pending=[];frappe.call=req=>new Promise(resolve=>pending.push(resolve));
            wrapper.machinesAvailable.refresh();wrapper.machinesAvailable.site.set_value('New Site');}''')
        self.page.evaluate("pending[1]({message:{...fixture,site:'New Site'}})")
        self.page.wait_for_selector('.hm-cell')
        self.page.evaluate("pending[0]({message:fixture})")
        self.assertIn('New Site', self.page.locator('caption').inner_text())
        for error in ['planning_error','configuration_error']:
            self.page.evaluate("async key=>{frappe.call=async()=>({message:{[key]:{title:'Unavailable plan'}}});await wrapper.machinesAvailable.refresh();}",error)
            self.assertEqual(self.page.locator('.hm-cell').count(),0)
            self.assertEqual(self.page.locator('.hm-status').inner_text(),'Unavailable plan')

    def test_visual_style_parity_and_no_css_leak(self):
        self.load()
        for width in [390, 1440]:
            self.page.set_viewport_size(dict(width=width,height=1000))
            actual=self.page.locator('.hm-cell').evaluate_all('(els)=>els.slice(0,6).map(e=>getComputedStyle(e).backgroundColor)')
            self.assertEqual(actual[:5],['rgb(185, 237, 197)','rgb(255, 240, 154)','rgb(255, 193, 138)','rgb(243, 166, 174)','rgb(243, 166, 174)'])
            self.assertTrue(self.page.locator('.hpa-scroll').is_visible())
        self.page.evaluate("$('body').append('<div id=sentinel class=hm-avail>Outside</div>')")
        self.assertNotEqual(self.page.locator('#sentinel').evaluate('(e)=>getComputedStyle(e).color'),'rgb(37, 99, 235)')
        self.page.screenshot(path='/tmp/machines-available-fixture.png',full_page=True)

    def install_popup_api(self):
        self.page.evaluate('''()=>{
          const original=frappe.call;
          frappe.call=async req=>{if(!req.method.endsWith('get_hour_breakdowns'))return original(req);
            calls.push(req);return {message:{start:'2026-09-01 06:00:00',end:'2026-09-01 07:00:00',machines:[{
              machine_number:'ADT <01>',downtime_minutes:30,breakdowns:[{failure_classification:'Hydraulic',
              description:'Hose <script>bad</script>',breakdown_start_datetime:'2026-09-01 06:30:00',
              resolved_datetime:null,overlap_minutes:30}]}]}};};
        }''')

    def test_popup_hover_pinning_switching_and_dismissal(self):
        self.install_popup_api(); self.load()
        first=self.page.locator('.hm-cell').nth(0)
        second=self.page.locator('.hm-cell').nth(19)
        card=self.page.locator('.hm-breakdown-popup')
        first.hover()
        card.wait_for(state='visible')
        expect(card).to_contain_text('ADT <01>')
        self.assertIn('ADT <01>',card.inner_text())
        self.assertIn('Hose <script>bad</script>',card.inner_text())
        self.assertIn('Still Open',card.inner_text())
        self.assertIn('4 / 4',card.inner_text())
        self.assertNotIn('Source PBM',card.inner_text())
        self.assertEqual(card.locator('script').count(),0)
        first.click(); self.page.mouse.move(5,5)
        self.assertTrue(card.is_visible())
        second.hover()
        self.assertIn('4 / 4',card.inner_text())
        second.click()
        self.assertIn('3.5 / 2',card.inner_text())
        second.click();self.assertFalse(card.is_visible())
        first.click();self.page.keyboard.press('Escape');self.assertFalse(card.is_visible())
        first.click();self.page.locator('.hm-breakdown-close').click();self.assertFalse(card.is_visible())
        first.click();self.page.mouse.click(5,5);self.assertFalse(card.is_visible())
        first.focus();first.press('Enter');self.page.mouse.move(5,5)
        self.assertTrue(card.is_visible())
        self.page.keyboard.press('Escape')

    def test_popup_empty_errors_late_responses_and_filter_reset(self):
        self.load()
        first=self.page.locator('.hm-cell').first
        self.page.evaluate('''()=>{const original=frappe.call;frappe.call=async req=>req.method.endsWith('get_hour_breakdowns')?
          {message:{machines:[]}}:original(req);}''')
        first.hover()
        card=self.page.locator('.hm-breakdown-popup')
        expect(card).to_contain_text('No recorded breakdowns')
        self.page.mouse.move(5,5);card.wait_for(state='hidden')
        self.page.evaluate('''()=>{frappe.call=req=>new Promise(resolve=>{window.resolveDetails=resolve;});}''')
        first.click();self.page.wait_for_function('typeof resolveDetails === \"function\"');self.page.keyboard.press('Escape')
        self.page.evaluate("resolveDetails({message:{machines:[]}})")
        self.assertFalse(card.is_visible())
        self.page.evaluate("()=>{frappe.call=async()=>{throw Error('denied')};}")
        first.click()
        expect(card).to_contain_text('Unable to load')
        self.page.locator('.hm-unavailable').hover()
        self.page.select_option('.hm-unavailable','1');self.assertFalse(card.is_visible())

    def test_popup_night_hour_scroll_and_mobile_viewport(self):
        self.install_popup_api();self.load()
        # Bring the post-midnight hour into the horizontal scroll viewport.
        night=self.page.locator('.hm-cell').nth(18)
        night.click()
        self.page.wait_for_function("calls.at(-1).method.endsWith('get_hour_breakdowns')")
        self.assertEqual(self.page.evaluate('calls.at(-1).args.hour'),18)
        self.assertEqual(self.page.evaluate('calls.at(-1).args.date'),'2026-09-01')
        self.assertIn('2026-09-01',self.page.locator('.hm-breakdown-popup h3').inner_text())
        self.assertIn('2026-09-02 00:00:00',self.page.locator('.hm-breakdown-period').inner_text())
        card=self.page.locator('.hm-breakdown-popup')
        self.assertTrue(card.is_visible())
        self.page.locator('.hpa-scroll').evaluate('(e)=>{e.scrollLeft-=30;e.dispatchEvent(new Event("scroll"))}')
        self.assertTrue(card.is_visible())
        self.page.set_viewport_size(dict(width=390,height=650))
        self.page.keyboard.press('Escape')
        mobile_cell=self.page.locator('.hm-cell').nth(18)
        mobile_cell.evaluate("""e=>{const scroller=e.closest('.hpa-scroll');
          const edge=scroller.querySelector('tbody .hm-date-head').getBoundingClientRect().right;
          scroller.scrollLeft+=e.getBoundingClientRect().left-edge-8;}""")
        mobile_cell.click()
        box=card.bounding_box()
        self.assertGreaterEqual(box['x'],0);self.assertLessEqual(box['x']+box['width'],390)
        self.assertGreaterEqual(box['y'],0);self.assertLessEqual(box['y']+box['height'],650)
        anchor=mobile_cell.bounding_box()
        self.assertTrue(box['y']+box['height']<=anchor['y'] or box['y']>=anchor['y']+anchor['height'])
        self.page.screenshot(path='/tmp/machines-available-popup-mobile.png',full_page=True)

    def test_calendar_drilldown_month_day_navigation_and_shared_state(self):
        self.page.evaluate("wrapper.machinesAvailable.site.set_value('Test Site')")
        self.page.wait_for_selector('.hm-cal-day')
        self.assertEqual(self.page.locator('[role=tab][aria-selected=true]').inner_text(),'Month')
        self.assertEqual(self.page.locator('.hm-cal-day').count(),30)
        self.assertEqual(self.page.locator('.hm-cal-day:not(:disabled)').count(),1)
        self.assertEqual(self.page.locator('.hm-kpi').count(),4)
        self.assertNotIn('sample',self.page.locator('.hm-content').inner_text().lower())
        initial=self.page.evaluate('calls.length')
        self.page.click('[data-view-date="2026-09-01"]')
        self.assertEqual(self.page.locator('.hm-hour-row').count(),24)
        self.assertEqual(self.page.locator('.hm-day-nav strong').inner_text(),'2026-09-01')
        self.assertTrue(self.page.locator('[data-day-step="-1"]').is_disabled())
        self.page.click('[data-day-step="1"]')
        self.assertEqual(self.page.locator('.hm-day-nav strong').inner_text(),'2026-10-01')
        self.assertEqual(self.page.locator('.hm-month').input_value(),'2026-10')
        self.page.click('#hm-mode-calendar')
        self.assertEqual(self.page.locator('.hm-cal-day').count(),31)
        self.page.select_option('.hm-month','2026-09')
        self.page.click('#hm-mode-heatmap')
        self.assertEqual(self.page.locator('.hm-heat-table tbody tr').count(),30)
        self.assertEqual(self.page.evaluate('calls.length'),initial)
        self.page.locator('#hm-mode-heatmap').press('Home')
        self.assertEqual(self.page.locator('[aria-selected=true]').inner_text(),'Month')
        self.page.select_option('.hm-unavailable','1')
        self.assertGreater(self.page.locator('.hm-cal-day.hm-unavailable-match').count(),0)
        self.page.click('#hm-mode-day')
        self.assertGreater(self.page.locator('.hm-hour-row.hm-unavailable-match').count(),0)

    def test_all_views_responsive_and_daily_popups_keep_counts(self):
        self.page.add_style_tag(path=str(BENCH/'apps/is_production/is_production/public/css/dashboards.css'))
        self.install_popup_api()
        self.page.evaluate("wrapper.machinesAvailable.site.set_value('Test Site')")
        self.page.wait_for_selector('.hm-cal-day')
        for width in [390,1440]:
            self.page.set_viewport_size(dict(width=width,height=900))
            if width==390:
                self.assertEqual(self.page.locator('.hm-unavailable-control').evaluate('(e)=>getComputedStyle(e).gridColumn'),'auto')
            for mode in ['calendar','day','heatmap']:
                self.page.click('#hm-mode-'+mode)
                self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                self.page.screenshot(path=f'/tmp/machines-view-{mode}-{width}.png',full_page=True)
        self.page.click('#hm-mode-day')
        self.page.locator('.hm-hour-row').first.click()
        card=self.page.locator('.hm-breakdown-popup')
        expect(card).to_contain_text('ADT <01>')
        self.assertIn('Available / Utilised: 4 / 4',card.inner_text())
        self.assertNotIn('−',card.locator('.hm-breakdown-counts').inner_text())
        anchor=self.page.locator('.hm-hour-row').first.bounding_box();box=card.bounding_box()
        self.assertTrue(box['y']+box['height']<=anchor['y'] or box['y']>=anchor['y']+anchor['height'])
        self.page.locator('.hm-hour-row').first.click()
        self.assertFalse(card.is_visible())
        self.page.locator('.hm-hour-row').first.click()
        self.page.click('#hm-mode-calendar')
        self.assertFalse(card.is_visible())

    def test_heatmap_selection_is_retained_when_switching_to_day(self):
        self.page.evaluate('''()=>{const row=structuredClone(fixture.rows[0]);row.date='2026-09-02';fixture.rows.splice(1,0,row);}''')
        self.load()
        self.page.locator('.hm-cell').nth(24).click()
        self.page.keyboard.press('Escape')
        self.page.click('#hm-mode-day')
        self.assertEqual(self.page.locator('.hm-day-nav strong').inner_text(),'2026-09-02')
