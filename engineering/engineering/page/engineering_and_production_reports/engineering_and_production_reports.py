"""Saved Engineering and Production report definitions and Desk Page endpoints.

Listing, previews and PDF downloads use saved snapshots only. Source production
calculations and downtime verification/sign-off remain in their existing apps.
"""
import json
import re
from decimal import Decimal

import frappe
from frappe.utils import getdate


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


def _saved_json(doc, field, expected):
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


def _render_production_snapshot(doc):
    raw = _saved_json(doc, 'report_data_json', dict)
    if not isinstance(raw.get('metrics'), dict):
        raise frappe.ValidationError('Saved snapshot metrics are missing.')
    metrics = {field: (None if raw['metrics'].get(field) is None else doc.get(field))
               for field, label in PRODUCTION_METRICS}
    missing = raw.get('missing_data') or []
    if 'drilling_reports' in missing:
        metrics['drill_meters'] = None
    return dict(template='production_snapshot.html', metrics=metrics, metric_labels=PRODUCTION_METRICS,
        excavators=_saved_json(doc, 'excavator_production_json', list),
        dozers=_saved_json(doc, 'dozer_production_json', list),
        drills=_saved_json(doc, 'drill_production_json', list), missing_data=missing,
        missing_hours=raw.get('missing_hour_slots') or [],
        source_hour_count=doc.get('source_hour_count'), expected_hour_count=doc.get('expected_hour_count'),
        monthly_values_basis=raw.get('monthly_values_basis') or 'Saved planning values',
        planning_name=doc.get('monthly_production_planning') or '',
        planning_modified=raw.get('monthly_planning_modified') or '',
        calculation_version=doc.get('calculation_version') or '')


def _render_hourly_downtime(doc):
    rows = _saved_json(doc, 'report_data_json', list)
    open_count = sum(str(row.get('status_key') or '').lower() == 'open' for row in rows)
    return dict(template='hourly_downtime_snapshot.html', rows=rows, fleet_total=len(rows),
        open_count=open_count, available_count=len(rows)-open_count,
        closed_count=sum(str(row.get('status_key') or '').lower() == 'closed' for row in rows))


def _render_daily_downtime(doc):
    rows = _saved_json(doc, 'report_data_json', list)
    return dict(template='daily_downtime_snapshot.html', rows=rows,
        total_hours=sum(float(row.get('breakdown_hours') or 0) for row in rows),
        event_count=len(rows), status=doc.get('status') or '',
        signatures={field: doc.get(field) for field in ('site_manager', 'supervisor',
            'engineering_manager_signature', 'information_officer')})


def _amount(value):
    if value is None:
        return 'Unavailable / not applicable'
    if isinstance(value, (int, float, Decimal)):
        return f'{value:,.3f}'
    return str(value)


def _render(model):
    return frappe.render_template('engineering/templates/reports/snapshot_report.html',
        dict(model, amount=_amount, report_template='engineering/templates/reports/'+model['template']))


def _pdf_bytes(model):
    from frappe.utils.pdf import get_pdf
    return get_pdf(_render(model), {'orientation': 'Landscape'})


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
        'view_handler': _render_production_snapshot if production else
            _render_hourly_downtime if hours else _render_daily_downtime,
        'pdf_handler': _pdf_bytes,
    }


PAGE_SIZE = 50
SCAN_LIMIT = 2000


def _specification(report_type):
    if report_type not in REPORT_TYPES:
        raise frappe.ValidationError('Unknown report type.')
    return REPORT_TYPES[report_type]


def _available(spec):
    return bool(frappe.db.exists('DocType', spec['doctype']) and
                frappe.has_permission(spec['doctype'], 'read'))


def _production_windows():
    from is_production.production.controllers.production_summary_planning import get_plan_windows
    return get_plan_windows()


def _production_eligible(site, report_date, windows=None):
    if not site or not report_date:
        return False
    if windows is not None:
        day = getdate(report_date)
        return any(start <= day <= end for start, end in windows.get(site, []))
    from is_production.production.controllers.production_summary_planning import get_covering_plan
    return bool(get_covering_plan(site, report_date))


def _metadata():
    return [{'key': key, 'label': spec['label'], 'department': spec['department'],
             'filters': spec['filters'], 'shift_options': spec['shift_options']}
            for key, spec in REPORT_TYPES.items() if _available(spec)]


def _search(report_type, site=None, report_date=None, shift=None, hour_slot=None, start=0):
    spec = _specification(report_type)
    if not _available(spec):
        raise frappe.PermissionError('This report type is not available to you.')
    try:
        start = int(start)
    except (TypeError, ValueError):
        raise frappe.ValidationError('Invalid page position.')
    if start < 0:
        raise frappe.ValidationError('Invalid page position.')
    filters = {}
    for field, value in [('site', site), ('report_date', report_date), ('shift', shift), ('hour_slot', hour_slot)]:
        if value:
            if field not in spec['filters']:
                raise frappe.ValidationError('This filter does not apply to the selected report.')
            if field == 'shift' and value not in spec['shift_options']:
                raise frappe.ValidationError('Invalid shift.')
            if field == 'report_date':
                value = getdate(value)
            if field == 'hour_slot':
                match = re.fullmatch(r'(\d{1,2}):00-(\d{1,2}):00', str(value))
                if not match:
                    raise frappe.ValidationError('Invalid hour slot.')
                first, last = map(int, match.groups())
                if not 0 <= first <= 23 or last not in ((first+1)%24, 24 if first==23 else (first+1)%24):
                    raise frappe.ValidationError('Invalid hour slot.')
                value = f'{first:02}:00-{(24 if first==23 and spec["department"]=="Engineering" else (first+1)%24):02}:00'
            filters[spec.get(field.replace('report_date', 'date').replace('hour_slot', 'hour')+'_field') or field] = value
    fields = ['name', 'site', 'report_date', 'creation']
    fields += [field for field in ('shift', 'hour_slot') if frappe.get_meta(spec['doctype']).has_field(field)]
    if spec['department'] == 'Production':
        fields += ['period_start', 'period_end', 'generated_at', 'source_data_missing', 'period_bcm']
    windows = _production_windows() if spec['department'] == 'Production' else None
    rows, position = [], start
    while len(rows) < PAGE_SIZE and position - start < SCAN_LIMIT:
        chunk = frappe.get_list(spec['doctype'], filters=filters, fields=fields,
            order_by='report_date desc, creation desc, name desc', start=position, page_length=100)
        if not chunk:
            return {'rows': rows, 'next_start': None}
        for row in chunk:
            position += 1
            if windows is None or _production_eligible(row.site, row.report_date, windows):
                rows.append(dict(row))
            if len(rows) == PAGE_SIZE or position-start >= SCAN_LIMIT:
                return {'rows': rows, 'next_start': position}
        if len(chunk) < 100:
            return {'rows': rows, 'next_start': None}
    return {'rows': rows, 'next_start': position}


def _get_report(report_type, name, for_pdf=False):
    spec = _specification(report_type)
    if not _available(spec):
        raise frappe.PermissionError('This report type is not available to you.')
    if not name:
        raise frappe.ValidationError('Select a saved report.')
    doc = frappe.get_doc(spec['doctype'], name)
    doc.check_permission('read')
    if for_pdf:
        doc.check_permission('print')
    if spec['department'] == 'Production' and not _production_eligible(doc.site, doc.report_date):
        raise frappe.PermissionError('No valid Monthly Production Planning covers this saved report.')
    model = spec['view_handler'](doc)
    model.update(report_type=report_type, title=spec['label'], department=spec['department'],
                 name=doc.name, site=doc.site, report_date=str(doc.report_date),
                 shift=doc.get('shift') or '', hour_slot=doc.get('hour_slot') or '',
                 generated_at=str(doc.get('generated_at') or doc.get('creation') or ''),
                 period_start=str(doc.get('period_start') or ''), period_end=str(doc.get('period_end') or ''))
    return model


@frappe.whitelist()
def get_report_types():
    return _metadata()


@frappe.whitelist()
def search_reports(report_type, site=None, report_date=None, shift=None, hour_slot=None, start=0):
    return _search(report_type, site, report_date, shift, hour_slot, start)


@frappe.whitelist()
def view_report(report_type, name):
    return {'html': _render(_get_report(report_type, name))}


@frappe.whitelist()
def download_pdf(report_type, name):
    model = _get_report(report_type, name, for_pdf=True)
    content = REPORT_TYPES[report_type]['pdf_handler'](model)
    filename = '_'.join(str(model.get(field) or '') for field in ('title', 'site', 'report_date', 'shift', 'hour_slot'))
    frappe.local.response.filename = re.sub(r'[^\w.\-]+', '_', filename).strip('_') + '.pdf'
    frappe.local.response.filecontent = content
    frappe.local.response.type = 'download'
