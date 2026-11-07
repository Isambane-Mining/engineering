"""Exercise shipped Engine JS/CSS in Chromium without a Frappe site or network."""
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parents[1]
REPORT = APP / 'engineering/engineering/report/availability_and_utilisation_engine/availability_and_utilisation_engine.js'
CSS = APP / 'engineering/public/css/engineering.css'
ROUTE = 'query-report/Availability and Utilisation Engine'


class TestEngineStyles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.route('**/*', lambda route: route.abort())
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.set_content('''<body><div class="page-container" data-page-route="query-report">
          <div class="page-form"><div class="form-group">Filters</div></div>
          <div class="report-wrapper"><div class="datatable"><div class="dt-row">
          <div id="cell" class="dt-cell dt-cell--col-3">Cell</div></div></div></div>
          <div id="rendered"></div></div></body>''')
        self.page.add_style_tag(path=str(CSS))
        self.page.evaluate('''() => {
          window.__ = text => text;
          window.flt = value => Number(value) || 0;
          window.frappe = {query_reports: {},
            datetime: {month_start: () => '2026-10-01', month_end: () => '2026-10-31'},
            query_report: {report_name: 'Availability and Utilisation Engine',
              get_filter_value: () => 'Isambane A&U Calculation'},
            utils: {escape_html: value => String(value)},
            ui: {Dialog: class {
              constructor(options) {
                this.node = document.createElement('section');
                this.node.className = 'modal'; document.body.append(this.node);
                this.$body = {html: html => {this.node.innerHTML = html;}};
                this.fields_dict = Object.fromEntries((options.fields || []).map(
                  field => [field.fieldname, {$wrapper: this.$body}]));
              }
              show() {}
            }}
          };
        }''')
        self.page.evaluate('(route) => document.body.dataset.route = route', ROUTE)
        self.page.add_script_tag(path=str(REPORT))

    def test_frozen_columns_and_filters_are_scoped_when_switching_reports(self):
        cell = self.page.locator('#cell')
        self.assertEqual(cell.evaluate('(node) => getComputedStyle(node).position'), 'sticky')
        self.assertEqual(cell.evaluate('(node) => getComputedStyle(node).left'), '268px')
        self.assertEqual(self.page.locator('.page-form').evaluate('(node) => getComputedStyle(node).zIndex'), '50')
        # Frappe reuses this exact wrapper for the next report.
        self.page.evaluate("document.body.dataset.route = 'query-report/Stock Balance'")
        self.assertEqual(cell.evaluate('(node) => getComputedStyle(node).position'), 'static')
        self.assertEqual(cell.evaluate('(node) => getComputedStyle(node).left'), 'auto')
        self.assertEqual(self.page.locator('.page-form').evaluate('(node) => getComputedStyle(node).zIndex'), 'auto')
        self.assertEqual(self.errors, [])

    def test_actual_formatter_preserves_work_status_and_shift_highlights(self):
        for level, expected in [('invalid', 'rgb(254, 226, 226)'), ('warning', 'rgb(255, 237, 213)')]:
            with self.subTest(level=level):
                self.page.evaluate('''level => {
                  const data = {indent: 3, asset_name: 'EX015', shift: 'Day', work_hours: 12,
                    au_validation_level: level, au_validation_status: 'Work plus PBM exceeds plan'};
                  const formatter = frappe.query_reports['Availability and Utilisation Engine'].formatter;
                  document.getElementById('rendered').innerHTML = formatter(12, 0,
                    {fieldname: 'work_hours'}, data, String);
                }''', level)
                rendered = self.page.locator('#rendered')
                self.assertIn('12', rendered.inner_text())
                flag = rendered.locator('[title="Work plus PBM exceeds plan"]')
                self.assertEqual(flag.evaluate('(node) => getComputedStyle(node).backgroundColor'), expected)
                self.assertEqual(rendered.locator('.availability-engine-shift-cell').evaluate(
                    '(node) => getComputedStyle(node).backgroundColor'), 'rgb(234, 244, 255)')
        self.assertEqual(self.errors, [])

    def test_investigation_dialog_outside_report_wrapper_keeps_styles(self):
        self.page.evaluate('show_au_invalid_explanation()')
        dialog = self.page.locator('.modal')
        self.assertIn('Pre-Use meter integrity', dialog.inner_text())
        self.assertEqual(dialog.locator('strong').first.evaluate(
            '(node) => getComputedStyle(node).color'), 'rgb(153, 27, 27)')
        self.assertEqual(self.errors, [])

    def test_engine_does_not_inject_styles_or_inline_presentation(self):
        self.page.evaluate('''() => {
          document.getElementById('rendered').innerHTML = apply_engine_shift_highlight('9h', 'Night');
        }''')
        self.assertEqual(self.page.locator('#rendered [style]').count(), 0)
        self.assertEqual(self.page.locator('#availability-engine-filter-layer-style').count(), 0)
        self.assertEqual(self.page.locator('#availability-utilisation-engine-style').count(), 0)
        self.assertEqual(self.page.locator('#rendered .availability-engine-shift-cell').evaluate(
            '(node) => getComputedStyle(node).backgroundColor'), 'rgb(243, 244, 246)')
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
