"""Saved-data adapters and a single HTML path for page previews and PDF downloads."""
import json
from decimal import Decimal
import frappe

PRODUCTION_METRICS = (
    ('period_bcm', 'Period BCM'), ('hour_bcm', 'Hour BCM'),
    ('shift_accumulated_bcm', 'Shift accumulated BCM'), ('daily_bcm', 'Daily BCM through period end'),
    ('excavator_bcm', 'Excavator BCM'), ('dozer_bcm', 'Dozer BCM'), ('drill_meters', 'Drilling meters'),
    ('coal_bcm', 'Coal BCM'), ('coal_tons', 'Coal tons'), ('waste_bcm', 'Waste BCM'),
    ('monthly_target_bcm', 'Monthly target BCM'), ('daily_target', 'Daily target BCM'),
    ('hourly_target', 'Hourly target BCM'), ('production_to_date', 'Production to date BCM'),
    ('remaining_bcm', 'Remaining BCM'), ('actual_hourly_rate', 'Actual hourly rate BCM'),
    ('actual_daily_rate', 'Actual daily rate BCM'), ('required_hourly_rate', 'Required hourly rate BCM'),
    ('required_daily_rate', 'Required daily rate BCM'), ('strip_ratio', 'Monthly strip ratio'),
    ('survey_variance_bcm', 'Survey variance BCM'), ('forecast_bcm', 'Forecast BCM'),
)


def saved_json(doc, field, expected):
    value = doc.get(field)
    if not value:
        raise frappe.ValidationError(f'Saved snapshot data is missing: {field}.')
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        raise frappe.ValidationError(f'Saved snapshot data is invalid: {field}.')
    if not isinstance(parsed, expected):
        raise frappe.ValidationError(f'Unexpected saved snapshot structure: {field}.')
    if expected is list and any(not isinstance(row, dict) for row in parsed):
        raise frappe.ValidationError(f'Unexpected saved snapshot rows: {field}.')
    return parsed


def render_production_snapshot(doc):
    raw = saved_json(doc, 'report_data_json', dict)
    if not isinstance(raw.get('metrics'), dict):
        raise frappe.ValidationError('Saved snapshot metrics are missing.')
    metrics = {field: (None if raw['metrics'].get(field) is None else doc.get(field))
               for field, label in PRODUCTION_METRICS}
    missing = raw.get('missing_data') or []
    if 'drilling_reports' in missing:
        metrics['drill_meters'] = None
    return dict(template='production_snapshot.html', metrics=metrics, metric_labels=PRODUCTION_METRICS,
        excavators=saved_json(doc, 'excavator_production_json', list),
        dozers=saved_json(doc, 'dozer_production_json', list),
        drills=saved_json(doc, 'drill_production_json', list), missing_data=missing,
        missing_hours=raw.get('missing_hour_slots') or [],
        source_hour_count=doc.get('source_hour_count'), expected_hour_count=doc.get('expected_hour_count'),
        monthly_values_basis=raw.get('monthly_values_basis') or 'Saved planning values',
        planning_name=doc.get('monthly_production_planning') or '',
        planning_modified=raw.get('monthly_planning_modified') or '',
        calculation_version=doc.get('calculation_version') or '')


def render_hourly_downtime(doc):
    rows = saved_json(doc, 'report_data_json', list)
    open_count = sum(str(row.get('status_key') or '').lower() == 'open' for row in rows)
    return dict(template='hourly_downtime_snapshot.html', rows=rows, fleet_total=len(rows),
        open_count=open_count, available_count=len(rows)-open_count,
        closed_count=sum(str(row.get('status_key') or '').lower() == 'closed' for row in rows))


def render_daily_downtime(doc):
    rows = saved_json(doc, 'report_data_json', list)
    return dict(template='daily_downtime_snapshot.html', rows=rows,
        total_hours=sum(float(row.get('breakdown_hours') or 0) for row in rows),
        event_count=len(rows), status=doc.get('status') or '',
        signatures={field: doc.get(field) for field in ('site_manager', 'supervisor',
            'engineering_manager_signature', 'information_officer')})


def amount(value):
    if value is None:
        return 'Unavailable / not applicable'
    if isinstance(value, (int, float, Decimal)):
        return f'{value:,.3f}'
    return str(value)


def render(model):
    return frappe.render_template('engineering/templates/reports/snapshot_report.html',
        dict(model, amount=amount, report_template='engineering/templates/reports/'+model['template']))


def pdf_bytes(model):
    from frappe.utils.pdf import get_pdf
    return get_pdf(render(model), {'orientation': 'Landscape'})
