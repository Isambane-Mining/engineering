"""Monthly assurance API. Source reports and dashboard are intentionally unchanged."""
from datetime import datetime, time, timedelta

import frappe
from frappe.utils import getdate, nowdate, get_url
from .calculations import (GROUPS, BASIS, MACHINE_SCOPE, OWNERSHIP, reporting_period,
                           equipment_group, operational_window, month_offset)
from engineering.engineering.problem_categories import PROBLEM_CATEGORIES
from .defects import monthly_population, category_counts

ACTIONS = 'Monthly TMM Assurance Actions'
PBM = 'Plant Breakdown or Maintenance'


def _period(value=None):
    try:
        return reporting_period(value, today=getdate(nowdate()))
    except (ValueError, TypeError) as exc:
        frappe.throw(str(exc))


def _scope(site, month, group=GROUPS[0], permission='read'):
    if not site or group not in GROUPS:
        frappe.throw('Select a valid Site and Equipment Group.')
    from engineering.engineering.doctype.monthly_tmm_assurance_actions.monthly_tmm_assurance_actions import scope_name
    doc = frappe.get_doc(dict(doctype=ACTIONS, __islocal=1, site=site, reporting_month=month, equipment_group=group))
    # A named scope checks User Permissions even before the first action is saved.
    doc.name = scope_name(site, month, group)
    doc.check_permission(permission)
    frappe.get_doc('Location', site).check_permission('read')
    return doc


def _authorize_sources(site, month):
    _scope(site, month)
    for doctype in (PBM, 'Availability and Utilisation', 'Asset', 'Monthly Production Planning', 'Pre-Use Hours'):
        if not frappe.has_permission(doctype, 'read'):
            frappe.throw(f'No read access to {doctype}.', frappe.PermissionError)


def _assert_complete_source_access(site, period):
    """The Engine synthesizes rows from SQL, not permission-filtered documents.

    Do not silently substitute partial source data for a site-wide measurement.
    Comparing only identities reveals no denied data and preserves Engine maths
    for users with access to the complete requested scope.
    """
    first, last = period['months'][0]['key'], period['months'][-1]['end']
    start, _ = operational_window(first)
    _, end = operational_window(period['reporting_month'])
    sources = [
        ('Availability and Utilisation', {'location': site, 'shift_date': ['between', [first, last]]}, None),
        ('Pre-Use Hours', {'location': site, 'shift_date': ['between', [first, last]], 'docstatus': ['<', 2]}, None),
        ('Monthly Production Planning', {'location': site, 'docstatus': ['<', 2], 'site_status': 'Producing',
          'prod_month_start_date': ['<=', last], 'prod_month_end_date': ['>=', first]}, None),
        (PBM, {'location': site, 'exclude_from_au': 0, 'breakdown_start_datetime': ['<', end]},
         [['resolved_datetime', '>=', start], ['resolved_datetime', 'is', 'not set']]),
    ]
    for doctype, filters, or_filters in sources:
        query = dict(filters=filters, or_filters=or_filters, pluck='name', limit=0)
        visible = set(frappe.get_list(doctype, **query))
        complete = set(frappe.get_all(doctype, **query))
        if visible != complete:
            frappe.throw(f'Your read access does not cover all {doctype} records needed for this site report.',
                         frappe.PermissionError)


    # Match the Engine's submitted, in-house, supported-category Asset scope.
    # A permission-limited machine list must never become an unlabelled fleet KPI.
    from engineering.engineering.report.availability_and_utilisation_engine import availability_and_utilisation_engine as engine
    asset_filters = {'location': site, 'docstatus': 1, 'asset_category': ['in', list(engine.ALLOWED_ASSET_CATEGORIES)]}
    complete_assets = frappe.get_all('Asset', filters=asset_filters,
                                    fields=['name', 'asset_name', 'asset_owner'], limit=0)
    participating = {a.name for a in complete_assets if a.asset_name and (a.asset_owner == 'Company' or not str(a.asset_owner or '').strip())}
    visible_assets = set(frappe.get_list('Asset', filters=asset_filters, pluck='name', limit=0))
    if not participating.issubset(visible_assets):
        frappe.throw('Your Asset read access does not cover the complete participating fleet for this site report.',
                     frappe.PermissionError)


def availability_by_group(rows):
    from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
    shifts = [r for r in rows if int(r.get('indent') or 0) == 3 and not r.get('is_formula_row')]
    values = {}
    for group in GROUPS:
        selected = [r for r in shifts if equipment_group(r.get('asset_category')) == group]
        summary = dashboard.au_engine.build_summary_row(selected, indent=0, asset_category=group)
        dashboard.au_engine.apply_au_percentage_basis([summary], BASIS)
        values[group] = summary.get('availability_percentage')
    return values


def _shift_rows(site, month):
    from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
    return dashboard.fetch_grouped_data(site, month['key'], month['end'], MACHINE_SCOPE, BASIS, OWNERSHIP) or []


def breakdown_counts_by_group(site, month):
    """Confirmed population: distinct breakdown records overlapping the calendar month.

    Counts include closed/repaired and A&U-excluded records, including carry-ins.
    Planning, Pre-Use validity and measured downtime do not affect counts. Blank legacy types remain breakdowns.
    Group uses captured asset_category, with permission-filtered Asset fallback.
    """
    start = datetime.combine(getdate(month), time.min)
    end = datetime.combine(month_offset(getdate(month), 1), time.min)
    rows = frappe.get_list(PBM, filters=[['location', '=', site], ['docstatus', '<', 2],
                                    ['breakdown_start_datetime', '<', end]],
                           or_filters=[['breakdown_start_datetime', '>=', start - timedelta(seconds=1)],
                                       ['resolved_datetime', '>', start - timedelta(seconds=1)],
                                       ['resolved_datetime', 'is', 'not set']],
                           fields=['name', 'asset_name', 'asset_category', 'breakdown_start_datetime',
                                   'resolved_datetime', 'problem_category', 'downtime_type',
                                   'breakdown_reason', 'docstatus'],
                           order_by='breakdown_start_datetime asc, name asc', limit=0)
    # The exact half-open calendar window is enforced here too. A one-second
    # query guard tolerates SQLite's legacy timestamp text lacking microseconds.
    rows = monthly_population(rows, month)
    # Asset fallback must not bypass Asset permissions. Do not require a machine
    # to remain at this site today to count its recorded breakdown at this site.
    identifiers = list({r.get('asset_name') for r in rows if r.get('asset_name')})
    assets = frappe.get_list('Asset', or_filters=[['name', 'in', identifiers], ['asset_name', 'in', identifiers]],
                             fields=['name', 'asset_name', 'asset_category'], limit=0) if identifiers else []
    asset_categories = {str(key).strip(): a.asset_category for a in assets for key in (a.name, a.asset_name) if key}
    grouped = {g: [] for g in GROUPS}
    unassigned = []
    for row in rows:
        group = equipment_group(row.get('asset_category') or asset_categories.get(str(row.get('asset_name') or '').strip()))
        if group:
            grouped[group].append(row)
        else:
            row['review_reason'] = 'Missing or unsupported equipment group'
            unassigned.append(row)
    return {g: category_counts(records) for g, records in grouped.items()}, unassigned


def _saved(scope):
    if frappe.db.exists(ACTIONS, scope.name):
        doc = frappe.get_doc(ACTIONS, scope.name)
        doc.check_permission('read')
        return dict(version=str(doc.modified), actions=[{field: row.get(field) for field in
                    ('name', 'cause', 'action', 'owner_name', 'due_date', 'status', 'breakdown_reference')} for row in doc.actions])
    return dict(version=None, actions=[])


@frappe.whitelist()
def get_report(site, reporting_month=None):
    period = _period(reporting_month)
    _authorize_sources(site, period['reporting_month'])
    _assert_complete_source_access(site, period)
    # Honor Asset record permissions even though the existing Engine queries SQL.
    assets = frappe.get_list('Asset', filters={'location': site}, fields=['asset_name'], limit=0)
    allowed_assets = {str(a.asset_name or '').strip() for a in assets}
    monthly = []
    for month in period['months']:
        rows = _shift_rows(site, month)
        rows = [r for r in rows if int(r.get('indent') or 0) == 3
                and str(r.get('asset_name') or '').strip() in allowed_assets]
        monthly.append(availability_by_group(rows))
    counts, unassigned = breakdown_counts_by_group(site, period['reporting_month'])
    from .presentation import count_chart_image, count_summary, availability_svg
    groups = []
    for group in GROUPS:
        scope = _scope(site, period['reporting_month'], group)
        saved = _saved(scope)
        groups.append(dict(group=group, availability=[values[group] for values in monthly],
                           counts=counts[group], pareto=counts[group]['categories'],
                           chart=count_chart_image(counts[group]), full_chart=count_chart_image(counts[group], limit=None),
                           summary=count_summary(counts[group]), **saved,
                           can_write=bool(scope.has_permission('write') and
                                          (frappe.db.exists(ACTIONS, scope.name) or scope.has_permission('create')))))
    result = dict(site=site, **period, groups=groups, basis=BASIS, machine_scope=MACHINE_SCOPE, ownership=OWNERSHIP)
    result.update(availability_chart=availability_svg(result), problem_categories=PROBLEM_CATEGORIES,
                  population='Distinct breakdown events overlapping the reporting calendar month, including carried-in and repaired/closed events',
                  counting_unit='One Plant Breakdown or Maintenance record',
                  status_basis='Current status shown; open and repaired/closed events are included when their recorded interval overlaps the month',
                  unassigned_records=unassigned, base_url=get_url())
    return result


@frappe.whitelist(methods=['POST'])
def save_actions(site, reporting_month, equipment_group, actions, version=None):
    month = _period(reporting_month)['reporting_month']
    scope = _scope(site, month, equipment_group, 'write')
    actions = frappe.parse_json(actions) if isinstance(actions, str) else actions
    if not isinstance(actions, list) or len(actions) > 200:
        frappe.throw('Actions must be a list of at most 200 rows.')
    # Lock the existing row before checking the version; a unique scope name also
    # protects simultaneous first saves. Ordinary Document.save handles permissions.
    existing = frappe.db.get_value(ACTIONS, scope.name, 'name', for_update=True)
    if existing:
        doc = frappe.get_doc(ACTIONS, scope.name)
        if str(doc.modified) != str(version):
            frappe.throw('Actions changed in another session. Reload before saving.', frappe.TimestampMismatchError)
    else:
        if version:
            frappe.throw('Actions changed in another session. Reload before saving.', frappe.TimestampMismatchError)
        doc = scope
        doc.check_permission('create')
    existing_names = {row.name for row in doc.actions}
    doc.set('actions', [])
    submitted_names = set()
    for action in actions:
        if not isinstance(action, dict):
            frappe.throw('Invalid action row.')
        if action.get('name') and (action['name'] not in existing_names or action['name'] in submitted_names):
            frappe.throw('Invalid action row reference.')
        if action.get('name'):
            submitted_names.add(action['name'])
        values = {key: action.get(key) for key in ('cause', 'action', 'owner_name', 'due_date', 'status', 'breakdown_reference')}
        if action.get('name'):
            values['name'] = action['name']
        doc.append('actions', values)
    doc.save()
    return _saved(doc)


@frappe.whitelist()
def download_pdf(site, reporting_month):
    data = get_report(site, reporting_month)
    _scope(site, data['reporting_month']).check_permission('print')
    from frappe.utils.pdf import get_pdf
    from .presentation import report_html
    frappe.local.response.filename = f"Monthly TMM Assurance {data['reporting_month'][:7]}.pdf"
    frappe.local.response.filecontent = get_pdf(report_html(data), {'page-size': 'A4', 'encoding': 'UTF-8',
                                                                 'margin-top': '12mm', 'margin-bottom': '12mm'})
    frappe.local.response.type = 'pdf'
