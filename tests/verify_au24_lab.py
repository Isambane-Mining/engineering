"""One read-only LAB report run for the confirmed formulas. No fixtures or reload.

Run from bench sites with bench Python. Optional AU24_FORMULA selects Industry.
"""
import json
import os
from unittest.mock import patch

import frappe


def main():
    frappe.init(site='juan.isambane.co.za', sites_path='/home/juan/juan-bench/sites')
    frappe.connect()
    frappe.set_user('Administrator')
    frappe.db.rollback()
    frappe.db.sql('START TRANSACTION READ ONLY')
    try:
        from engineering.engineering.report.availability_and_utilisation_engine_24 import availability_and_utilisation_engine_24 as report
        formula = os.environ.get('AU24_FORMULA', 'Isambane Formula')
        filters = dict(from_date='2026-08-01', to_date='2026-08-07', sites=['Uitgevallen'],
                       formula=formula, asset_ownership='Isambane & Excavo Assets')
        # The unchanged Engine logs missing legacy Sunday timings. Capture only
        # the logging side effect so this verification stays strictly read-only;
        # its normal zero-window fallback and arithmetic still run unchanged.
        assert report.CONFIG == 'Startup and Fatigue spesification'

        with patch.object(frappe, 'log_error') as legacy_logs:
            configurations = report.get_site_configurations(['Uitgevallen'])
            assert len(configurations) == 4, configurations
            assert {(r['shift'], r['day_type']) for r in configurations} == {
                ('Day', 'Weekday'), ('Day', 'Saturday'),
                ('Night', 'Weekday'), ('Night', 'Saturday'),
            }

            columns, rows, message, chart, summary, skip_total = report.execute(filters)
        assert len(columns) == 15 and len(rows) > 1
        assert sum(bool(r.get('is_total_row')) for r in rows) == 1 and rows[-1]['is_total_row']
        assert len({(r['site'], r['asset']) for r in rows[:-1]}) == len(rows) - 1
        total = rows[-1]
        for field in ('total_hours', 'breakdown_hours', 'planned_maintenance_hours',
                      'working_hours', 'availability_available', 'utilisation_available'):
            assert abs(total[field] - sum(r[field] for r in rows[:-1])) < 1e-6, field
        assert abs(total['availability_percent'] - total['availability_available'] / total['total_hours']) < 1e-9
        assert abs(total['utilisation_percent'] - total['working_hours'] / total['utilisation_available']) < 1e-9
        assert chart is None and summary is None and skip_total
        print(json.dumps(dict(formula=formula, machines=len(rows)-1, base_column=columns[4]['label'],
                              total=total, notes=message,
                              legacy_log_messages=sorted({str(call.kwargs.get('message', call.args)) for call in legacy_logs.call_args_list})), indent=2))
    finally:
        frappe.db.rollback()
        frappe.destroy()


if __name__ == '__main__':
    main()
