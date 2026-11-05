"""Verify Page wiring and the reused permission-checked Excel contract.

Run with bench Python unittest; uses no database writes.
"""
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

import frappe
from openpyxl import load_workbook
from is_production.production.page.hourly_productivity_analysis import hourly_productivity_analysis as api
from engineering.engineering.page.machines_available import machines_available as machines

PAGE = Path(__file__).parent


class TestMachinesAvailable(unittest.TestCase):
    def test_defaults_use_johannesburg_calendar_month_and_today(self):
        # UTC is still in the preceding day/month/year at Johannesburg midnight.
        for instant, expected in [
            ('2026-11-05T12:00:00', ('2026-11-01', '2026-11-05')),
            ('2026-10-31T21:59:59', ('2026-10-01', '2026-10-31')),
            ('2026-10-31T22:00:00', ('2026-11-01', '2026-11-01')),
            ('2026-12-31T22:30:00', ('2027-01-01', '2027-01-01')),
            ('2024-02-29T12:00:00', ('2024-02-01', '2024-02-29')),
        ]:
            with self.subTest(instant=instant), patch.object(machines, 'datetime', wraps=datetime) as clock:
                utc = datetime.fromisoformat(instant).replace(tzinfo=timezone.utc)
                clock.now.side_effect = lambda tz: utc.astimezone(tz)
                self.assertEqual(machines.get_defaults(), dict(zip(('from_date', 'to_date'), expected)))

    def test_native_page_and_workspace_navigation(self):
        page = json.loads((PAGE / 'machines_available.json').read_text())
        self.assertEqual((page['module'], page['name']), ('Engineering', 'machines-available'))
        self.assertIn({'role': 'Engineering User'}, page['roles'])
        workspace = json.loads((PAGE.parents[1] / 'workspace/engineering/engineering.json').read_text())
        self.assertTrue(any(x.get('link_to') == page['name'] for x in workspace['shortcuts']))
        self.assertTrue(any(x.get('link_to') == page['name'] for x in workspace['links']))
        self.assertTrue(any(x.get('data', {}).get('shortcut_name') == 'Machines Available'
                            for x in json.loads(workspace['content'])))

    def test_excel_reuses_analysis_filters_and_preserves_red_borders(self):
        cells = [dict(available=3.5, utilised=3, completed=True, has_record=True) for _ in range(24)]
        cells[1] = dict(cells[0], available=4)
        cells[2] = dict(cells[0], has_record=False)
        cells[3] = dict(cells[0], completed=False)
        data = dict(hours=[f'{(i + 6) % 24:02}:00' for i in range(24)], rows=[
            dict(date=f'2026-{month:02}-01', day='Thu', month=label, month_key=str(month),
                 fleet_total=4, cells=cells) for month, label in [(9, 'September 2026'), (10, 'October 2026')]])
        for scope in ['all', 'production', 'spare']:
            for selection, highlighted in [('1', 'D7'), ('0', 'E7'), ('', None)]:
                response = {}
                with patch.object(api, 'get_analysis', return_value=data) as analysis, \
                     patch.object(api.frappe, 'response', response):
                    api.export_machine_excel('Test Site', '2026-09-01', '2026-10-01', scope, selection)
                analysis.assert_called_once_with('Test Site', '2026-09-01', '2026-10-01', machine_scope=scope)
                self.assertEqual(response['type'], 'download')
                book = load_workbook(BytesIO(response['filecontent']))
                self.assertEqual(book.sheetnames, ['Summary', 'September 2026', 'October 2026'])
                self.assertEqual(book['Summary']['B4'].value, 'Test Site')
                self.assertEqual(book['Summary']['B5'].value, '2026-09-01')
                self.assertEqual(book['Summary']['B6'].value, '2026-10-01')
                self.assertEqual(book['Summary']['B7'].value, scope.title())
                self.assertEqual(book['Summary']['B9'].value, 'No highlight' if selection == '' else
                                 '0 - Fully available' if selection == '0' else '0-1 unavailable')
                sheet = book['September 2026']
                self.assertEqual(sheet['D7'].value, '3.5 / 3')
                self.assertEqual(sheet['F7'].value, '-')
                self.assertEqual(sheet['G7'].value, '-')
                if highlighted:
                    self.assertEqual(sheet[highlighted].border.left.color.rgb, 'FFDC2626')
                    self.assertEqual(sheet[highlighted].border.left.style, 'medium')
                else:
                    self.assertEqual(sheet['D7'].border.left.style, 'thin')

    def test_export_cannot_bypass_analysis_permission_checks(self):
        with patch.object(api, 'get_analysis', side_effect=frappe.PermissionError), \
             patch.object(api.frappe, 'response', {}) as response:
            with self.assertRaises(frappe.PermissionError):
                api.export_machine_excel('Denied Site', '2026-09-01', '2026-09-01')
            self.assertEqual(response, {})

    def test_analysis_checks_source_read_permission(self):
        with patch.object(api.frappe, 'session', frappe._dict(user='test@example.com')), \
             patch.object(api.summary, '_read_document', side_effect=frappe.PermissionError):
            with self.assertRaises(frappe.PermissionError):
                api.get_analysis('Denied Site', '2026-09-01', '2026-09-01')
