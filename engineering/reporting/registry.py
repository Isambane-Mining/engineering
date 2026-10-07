"""Allowlisted report configuration. Add report types here, not in page JavaScript."""
from .rendering import render_production_snapshot, render_hourly_downtime, render_daily_downtime, pdf_bytes

REPORT_TYPES = {}
for key, label, shifts, hours in [
    ('hourly_production', 'Hourly Production Summary', ('Day', 'Night'), True),
    ('shift_production', 'Shift Production Summary', ('Day', 'Night'), False),
    ('daily_production', 'Daily Production Summary', (), False),
    ('hourly_downtime', 'Hourly Downtime Summary', (), True),
    ('daily_downtime', 'Daily Downtime Summary', ('Day Shift', 'Night Shift', 'Full Daily'), False),
]:
    production = 'production' in key
    REPORT_TYPES[key] = {
        'label': label, 'doctype': label, 'department': 'Production' if production else 'Engineering',
        'filters': ('site', 'report_date') + (('shift',) if shifts else ()) + (('hour_slot',) if hours else ()),
        'shift_options': shifts, 'site_field': 'site', 'date_field': 'report_date',
        'shift_field': 'shift' if shifts else None, 'hour_field': 'hour_slot' if hours else None,
        'view_handler': render_production_snapshot if production else
            render_hourly_downtime if hours else render_daily_downtime,
        'pdf_handler': pdf_bytes,
    }
