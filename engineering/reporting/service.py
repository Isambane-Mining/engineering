"""Permission-aware list, preview and download access. Never invokes source reports."""
import re
import frappe
from frappe.utils import getdate
from .registry import REPORT_TYPES

PAGE_SIZE = 50
SCAN_LIMIT = 2000


def specification(report_type):
    if report_type not in REPORT_TYPES:
        raise frappe.ValidationError('Unknown report type.')
    return REPORT_TYPES[report_type]


def available(spec):
    return bool(frappe.db.exists('DocType', spec['doctype']) and
                frappe.has_permission(spec['doctype'], 'read'))


def production_windows():
    from is_production.production.controllers.production_summary_planning import get_plan_windows
    return get_plan_windows()


def production_eligible(site, report_date, windows=None):
    if not site or not report_date:
        return False
    if windows is not None:
        day = getdate(report_date)
        return any(start <= day <= end for start, end in windows.get(site, []))
    from is_production.production.controllers.production_summary_planning import get_covering_plan
    return bool(get_covering_plan(site, report_date))


def metadata():
    return [{'key': key, 'label': spec['label'], 'department': spec['department'],
             'filters': spec['filters'], 'shift_options': spec['shift_options']}
            for key, spec in REPORT_TYPES.items() if available(spec)]


def search(report_type, site=None, report_date=None, shift=None, hour_slot=None, start=0):
    spec = specification(report_type)
    if not available(spec):
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
    windows = production_windows() if spec['department'] == 'Production' else None
    rows, position = [], start
    while len(rows) < PAGE_SIZE and position - start < SCAN_LIMIT:
        chunk = frappe.get_list(spec['doctype'], filters=filters, fields=fields,
            order_by='report_date desc, creation desc, name desc', start=position, page_length=100)
        if not chunk:
            return {'rows': rows, 'next_start': None}
        for row in chunk:
            position += 1
            if windows is None or production_eligible(row.site, row.report_date, windows):
                rows.append(dict(row))
            if len(rows) == PAGE_SIZE or position-start >= SCAN_LIMIT:
                return {'rows': rows, 'next_start': position}
        if len(chunk) < 100:
            return {'rows': rows, 'next_start': None}
    return {'rows': rows, 'next_start': position}


def get_report(report_type, name, for_pdf=False):
    spec = specification(report_type)
    if not available(spec):
        raise frappe.PermissionError('This report type is not available to you.')
    if not name:
        raise frappe.ValidationError('Select a saved report.')
    doc = frappe.get_doc(spec['doctype'], name)
    doc.check_permission('read')
    if for_pdf:
        doc.check_permission('print')
    if spec['department'] == 'Production' and not production_eligible(doc.site, doc.report_date):
        raise frappe.PermissionError('No valid Monthly Production Planning covers this saved report.')
    model = spec['view_handler'](doc)
    model.update(report_type=report_type, title=spec['label'], department=spec['department'],
                 name=doc.name, site=doc.site, report_date=str(doc.report_date),
                 shift=doc.get('shift') or '', hour_slot=doc.get('hour_slot') or '',
                 generated_at=str(doc.get('generated_at') or doc.get('creation') or ''),
                 period_start=str(doc.get('period_start') or ''), period_end=str(doc.get('period_end') or ''))
    return model
