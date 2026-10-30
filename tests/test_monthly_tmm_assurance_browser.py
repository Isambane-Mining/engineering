"""Browser checks of shipped Page JS with native Desk CSS and a test-only API.

No runtime/demo data is installed. Run using bench Python from the app root.
"""
from datetime import date
import json
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright
from engineering.engineering.page.monthly_tmm_assurance.defects import category_counts
from engineering.engineering.problem_categories import PROBLEM_CATEGORIES
from engineering.engineering.page.monthly_tmm_assurance.calculations import GROUPS, reporting_period
from engineering.engineering.page.monthly_tmm_assurance.presentation import count_chart_image, count_summary, availability_svg

APP = Path(__file__).resolve().parents[1]
FRAPPE = APP.parent/'frappe'
ARTIFACTS = Path('/tmp/monthly-tmm-assurance-validation')


def fixture():
    data = dict(site='Koppie',**reporting_period('2026-09',today=date(2026,10,30)),groups=[])
    for index, group in enumerate(GROUPS):
        records=[dict(name=f'{group}-{i}',problem_category=c,asset_name='TEST-MACHINE',
                      breakdown_start_datetime='2026-09-15 08:00:00',breakdown_reason='Test-only recorded description',status_label='Open (current)')
                 for i,c in enumerate(PROBLEM_CATEGORIES)] if index<2 else []
        records += [dict(name=group+'-blank',problem_category='',status_label='Open (current)')] if index<2 else []
        counts=category_counts(records)
        data['groups'].append(dict(group=group,availability=[82+index,85+index,88+index],counts=counts,pareto=counts['categories'],
            chart=count_chart_image(counts),full_chart=count_chart_image(counts,limit=None),summary=count_summary(counts),actions=[],version=None,can_write=True))
    data.update(problem_categories=PROBLEM_CATEGORIES,population='Distinct breakdown events overlapping the reporting calendar month, including carried-in and repaired/closed events',unassigned_records=[])
    data['availability_chart']=availability_svg(data)
    return data


class TestBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ARTIFACTS.mkdir(exist_ok=True)
        cls.p = sync_playwright().start()
        cls.browser = cls.p.chromium.launch(headless=True,args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':1514,'height':1100})
        self.errors=[]
        self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        css=next((APP.parents[1]/'sites/assets/frappe/dist/css').glob('desk.bundle.*.css')).read_text()
        self.page.set_content('<!doctype html><html><head><style>'+css+'</style></head><body><div style="padding:25px;max-width:1300px;margin:auto"><div style="display:flex;justify-content:space-between"><h2>Monthly TMM Assurance</h2><div id="buttons"></div></div><div id="filters" style="display:flex;gap:18px;border:1px solid #ddd;padding:12px"></div><main></main></div></body></html>')
        self.page.add_script_tag(path=str(FRAPPE/'node_modules/jquery/dist/jquery.min.js'))
        self.page.evaluate('''data => {
            window.__ = text => text;
            window.responseData = data; window.calls=[]; window.confirmAnswer=false; window.failSave=false;
            window.frappe = {pages:{'monthly-tmm-assurance':{}}, datetime:{month_start:()=> '2026-10-01',add_months:()=> '2026-09-01',str_to_user:x=>x},
                utils:{escape_html:x=>$('<div>').text(x).html()},show_alert:()=>{},
                confirm:(message,yes,no)=>window.confirmAnswer?yes():no(),
                call:async req=>{window.calls.push(req);if(req.method.endsWith('get_report')) return {message:structuredClone(window.responseData)};
                    if(window.failSave) throw Error('Conflict');return {message:{version:'v2',actions:JSON.parse(req.args.actions)}};},
                ui:{make_app_page:()=>({main:$('main'),add_field:spec=>{
                    const wrap=$('<label>').text(spec.label+' ').appendTo('#filters');
                    const input=$('<input class="form-control">').appendTo(wrap).attr('data-filter',spec.fieldname);
                    input.on('change',spec.change);
                    return {$input:input,get_value:()=>input.val(),set_value:value=>{input.val(value);spec.change();}};
                },set_primary_action:(label,callback)=>$('<button class="btn btn-primary">').text(label).on('click',callback).appendTo('#buttons'),
                  set_secondary_action:(label,callback)=>$('<button class="btn btn-default">').text(label).on('click',callback).prependTo('#buttons')})}};
        }''',fixture())
        self.page.add_script_tag(path=str(APP/'engineering/engineering/page/monthly_tmm_assurance/monthly_tmm_assurance.js'))
        self.page.evaluate("async () => {window.wrapper={};frappe.pages['monthly-tmm-assurance'].on_page_load(wrapper);window.view=wrapper.monthly_tmm_assurance;await view.ready;view.site.set_value('Koppie');}")
        self.page.wait_for_selector('[data-group]')

    def tearDown(self):
        self.assertEqual(self.errors,[])
        self.page.close()

    def add(self):
        self.page.get_by_role('button',name='+ Add Action').click()
        for key,value in [('cause','Hydraulics'),('action','Inspect hoses'),('owner_name','Engineer'),('due_date','2026-10-03')]:
            field=self.page.locator('[data-field="'+key+'"]')
            if key=='cause': field.select_option(value)
            else: field.fill(value)

    def test_layout_selection_draft_retention_and_filter_cancel(self):
        self.assertEqual(self.page.locator('[data-filter]').count(),2)
        self.assertEqual(self.page.locator('[data-group]').count(),7)
        self.add()
        self.page.locator('[data-group="Excavators"]').click()
        self.page.locator('[data-group="ADTs"]').click()
        self.assertEqual(self.page.locator('[data-field="action"]').input_value(),'Inspect hoses')
        self.page.locator('[data-filter="site"]').fill('Gwab')
        self.page.locator('[data-filter="site"]').dispatch_event('change')
        self.assertEqual(self.page.locator('[data-filter="site"]').input_value(),'Koppie')
        self.assertTrue(self.page.evaluate('view.dirty'))
        self.page.screenshot(path=str(ARTIFACTS/'page-desktop.png'),full_page=True)
        self.page.set_viewport_size({'width':390,'height':844})
        self.page.screenshot(path=str(ARTIFACTS/'page-mobile.png'),full_page=True)

    def test_save_persists_across_groups_and_conflict_retains_draft(self):
        self.add()
        self.page.evaluate('window.failSave=true')
        self.assertFalse(self.page.evaluate('view.save()'))
        self.assertTrue(self.page.evaluate('view.dirty'))
        self.assertEqual(self.page.locator('[data-field="action"]').input_value(),'Inspect hoses')
        self.page.evaluate('window.failSave=false')
        self.assertTrue(self.page.evaluate('view.save()'))
        self.assertFalse(self.page.evaluate('view.dirty'))
        self.assertEqual(self.page.evaluate('view.group().version'),'v2')

    def test_export_saves_dirty_groups_before_download(self):
        self.add()
        self.page.locator('[data-group="Dozers"]').click()
        self.add()
        self.page.evaluate('window.open=(url)=>window.exportURL=url')
        self.page.evaluate('view.download_pdf()')
        calls=self.page.evaluate("calls.filter(c=>c.method.endsWith('save_actions')).map(c=>c.args.equipment_group)")
        self.assertEqual(calls,['ADTs','Dozers'])
        self.assertIn('download_pdf?site=Koppie',self.page.evaluate('window.exportURL'))

    def test_stale_responses_do_not_replace_latest_filters(self):
        self.page.evaluate('''() => {window.pending=[];frappe.call=req=>new Promise(resolve=>pending.push({resolve,req}));view.site.set_value('Gwab');}''')
        self.page.wait_for_function('pending.length===1')
        self.page.evaluate("view.site.set_value('Koppie')")
        self.page.wait_for_function('pending.length===2')
        self.page.evaluate("pending[1].resolve({message:{...structuredClone(responseData),site:'Koppie'}})")
        self.page.wait_for_selector('[data-group]')
        self.page.evaluate("pending[0].resolve({message:{...structuredClone(responseData),site:'Gwab'}})")
        self.assertEqual(self.page.evaluate('view.data.site'),'Koppie')

    def test_restore_waits_for_async_frappe_controls(self):
        result=self.page.evaluate("""async () => {
            view.site.$input.val('Gwab');
            view.site.set_value=value=>new Promise(resolve=>setTimeout(()=>{view.site.$input.val(value);view.filters_changed();resolve();},10));
            view.month.set_value=value=>new Promise(resolve=>setTimeout(()=>{view.month.$input.val(value);view.filters_changed();resolve();},10));
            await view.restore_filters();
            return {site:view.site.get_value(),initializing:view.initializing};
        }""")
        self.assertEqual(result,{'site':'Koppie','initializing':False})

    def test_priority_drilldown_full_categories_and_add_action_from_record(self):
        self.page.locator('.tmm-priority summary').click()
        self.assertEqual(self.page.locator('.tmm-priority tbody tr').count(),13)
        self.assertIn('3 additional priority categories',self.page.locator('.tmm-details').inner_text())
        self.page.locator('.tmm-all-categories summary').click()
        self.assertEqual(self.page.locator('.tmm-inspect-category').count(),16)
        self.page.locator('[data-category="Brake Test"]').click()
        self.assertEqual(self.page.locator('.tmm-category-records tbody tr').count(),1)
        self.page.locator('.tmm-category-records .tmm-action-for-record').click()
        self.assertEqual(self.page.locator('[data-field="cause"]').input_value(),'Brake Test')
        self.assertEqual(self.page.locator('[data-field="breakdown_reference"]').input_value(),'ADTs-14')
        self.page.locator('.tmm-unresolved summary').click()
        self.assertEqual(self.page.locator('.tmm-unresolved tbody tr').count(),1)
        self.assertIn('Missing category',self.page.locator('.tmm-unresolved').inner_text())
        self.page.locator('.tmm-toggle-categories').click()
        self.assertTrue(self.page.evaluate('view.show_all'))
        self.assertTrue(self.page.evaluate('view.dirty'))

    def test_legacy_action_category_survives_group_changes(self):
        self.page.evaluate("view.group().actions=[{name:'old-action',cause:'Old unsupported value',action:'Saved text',owner_name:'Engineer',due_date:'2026-10-03',status:'Open'}];view.render_actions()")
        self.assertEqual(self.page.locator('[data-field="cause"]').input_value(),'Old unsupported value')
        self.assertIn('legacy',self.page.locator('[data-field="cause"]').inner_text())
        self.page.locator('[data-group="Excavators"]').click()
        self.page.locator('[data-group="ADTs"]').click()
        self.assertEqual(self.page.locator('[data-field="cause"]').input_value(),'Old unsupported value')

    def test_read_only_and_empty_states(self):
        self.page.evaluate("view.data.groups.forEach(g=>{g.can_write=false;g.availability=[null,null,0];g.pareto=[];g.chart='<p>No measured breakdown downtime for this reporting month.</p>'});view.render()")
        self.assertTrue(self.page.get_by_role('button',name='+ Add Action').is_disabled())
        self.assertEqual(self.page.locator('.tmm-availability [data-group]').count(),7)
        self.assertIn('No saved corrective actions',self.page.locator('.tmm-details').inner_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
