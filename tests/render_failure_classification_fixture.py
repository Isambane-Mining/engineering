"""Render real dashboard markup with isolated fixtures, without an ERP connection."""
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import frappe
from engineering.engineering.page.daily_availability_and_utilization_dashboard.test_tyre_damage import DashboardFixtures
from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard


def render(destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    with patch.object(frappe,'conf',frappe._dict()),patch.object(frappe,'flags',frappe._dict()),patch('frappe.translate.get_all_translations',return_value={}):
        fixture=DashboardFixtures()
        fixture.setUp()
        try:
            html=dashboard.execute(frappe._dict(location='Koppie',start_date='2026-07-01',end_date='2026-07-01'))[2]
        finally:fixture.doCleanups()
    styles=Path(__file__).resolve().parents[1]/'engineering/public/css/engineering.css'
    (destination/'engineering.css').write_text(styles.read_text())
    (destination/'index.html').write_text('''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
    <link rel="stylesheet" href="desk.css"><link rel="stylesheet" href="engineering.css">
    <style>html,body{display:block!important;position:static!important;width:100%!important;min-width:0!important;margin:0!important;padding:12px;box-sizing:border-box}.frappe-card{background:white;border:1px solid #ddd;border-radius:8px}</style></head><body>'''+html+'''
    <script>document.querySelectorAll('.daily-dashboard-tab-button').forEach(button=>button.addEventListener('click',()=>{
    document.querySelectorAll('.daily-dashboard-tab-panel').forEach(panel=>panel.style.display=panel.dataset.panel===button.dataset.tab?'':'none');
    }));</script></body></html>''')


if __name__=='__main__':render(sys.argv[1])
