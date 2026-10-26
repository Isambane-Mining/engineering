"""Read-only, permission-aware Machine Reliability endpoints."""
from datetime import timedelta

import frappe
from frappe.utils import cint, getdate, nowdate
from engineering.engineering.page.downtime_correction_dashboard.downtime_correction_dashboard import get_allowed_sites
from engineering.engineering.page.machine_reliability.calculations import build_report, build_frequency, mean, terms

MAX_SOURCE_ROWS = 20000
CHART_LIMIT = 1000
PBM = 'Plant Breakdown or Maintenance'
LEGALS = 'Engineering Legals'


def check_access():
    if frappe.session.user == 'Guest':
        frappe.throw('Login required.', frappe.PermissionError)
    for doctype in (PBM, LEGALS, 'Asset'):
        if not frappe.has_permission(doctype, 'read'):
            frappe.throw(f'You need read access to {doctype} to view Machine Reliability.', frappe.PermissionError)
    return get_allowed_sites()


def date_range(from_date=None, to_date=None):
    try:
        end = getdate(to_date or nowdate())
        start = getdate(from_date or end - timedelta(days=30))
    except (ValueError, TypeError):
        frappe.throw('Enter valid From Date and To Date.')
    if end < start:
        frappe.throw('To Date must be on or after From Date.')
    if (end - start).days > 366 * 5:
        frappe.throw('Choose a date range of five years or less.')
    return start, end


def categories():
    return [dict(category=x.category, keywords=terms(x.keywords),
                 test_sections=[s.strip() for s in (x.test_sections or '').splitlines() if s.strip()])
            for x in frappe.get_cached_doc('Machine Reliability Settings').categories]


@frappe.whitelist()
def get_options():
    check_access()
    return dict(categories=categories(), chart_limit=CHART_LIMIT)


def source_filters(start, end, site, allowed_sites, legal=False):
    site_field, date_field = ('site', 'start_date') if legal else ('location', 'breakdown_start_datetime')
    filters = [['docstatus', '<', 2], [date_field, '>=', str(start)], [date_field, '<', str(end + timedelta(days=1))]]
    if site:
        if allowed_sites and site not in allowed_sites:
            frappe.throw('You do not have permission to access this site.', frappe.PermissionError)
        filters.append([site_field, '=', site])
    elif allowed_sites:
        filters.append([site_field, 'in', allowed_sites])
    return filters


def limited_list(doctype, filters, fields, **kwargs):
    # get_list enforces document and User Permissions; broad read is insufficient.
    rows = frappe.get_list(doctype, filters=filters, fields=fields, limit_page_length=MAX_SOURCE_ROWS + 1, **kwargs)
    if len(rows) > MAX_SOURCE_ROWS:
        frappe.throw('Too many source records. Narrow the dates, site, category or fleet; no partial totals have been calculated.')
    return rows


def load_sources(start, end, site, asset_category, fleet, allowed_sites, lookup=False):
    breakdown_filters = source_filters(start, end, site, allowed_sites)
    legal_filters = source_filters(start, end, site, allowed_sites, legal=True)
    if fleet:
        breakdown_filters.append(['asset_name', '=', fleet])
        legal_filters.append(['fleet_number', '=', fleet])
    breakdowns = limited_list(PBM, breakdown_filters, ['name', 'asset_name'] if lookup else [
        'name', 'asset_name', 'location', 'downtime_type', 'breakdown_start_datetime',
        'resolved_datetime', 'hours_breakdown_starts', 'breakdown_reason', 'problem_category', 'resolution_summary', 'exclude_from_au'],
        order_by='breakdown_start_datetime asc, name asc')
    legals = limited_list(LEGALS, legal_filters, ['name', 'fleet_number'] if lookup else [
        'name', 'fleet_number', 'site', 'sections', 'start_date'], order_by='start_date asc, name asc')
    # Start with authorized event rows, so Asset transfers cannot rewrite
    # historical site scope. Read only identity/category metadata for their
    # linked Assets; never expose current location or bypass event permissions.
    ids = {x.asset_name for x in breakdowns if x.asset_name} | {x.fleet_number for x in legals if x.fleet_number}
    assets = frappe.get_all('Asset', filters={'name': ['in', list(ids)], 'docstatus': ['<', 2]},
                            fields=['name', 'asset_name', 'asset_category'], limit_page_length=MAX_SOURCE_ROWS + 1) if ids else []
    asset_map = {x.name: x for x in assets}
    def matches(asset_id):
        return not asset_category or (asset_id in asset_map and asset_map[asset_id].asset_category == asset_category)
    breakdowns = [x for x in breakdowns if matches(x.asset_name)]
    # Machine-specific tests/services require an actual linked machine.
    legals = [x for x in legals if x.fleet_number and matches(x.fleet_number)]
    for row in breakdowns:
        row['asset_category'] = asset_map[row.asset_name].asset_category if row.asset_name in asset_map else None
    return breakdowns, legals, asset_map


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_fleets(doctype, txt, searchfield, start, page_len, filters):
    allowed = check_access()
    filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
    began, end = date_range(filters.get('from_date'), filters.get('to_date'))
    breakdowns, legals, assets = load_sources(began, end, filters.get('site'), filters.get('asset_category'), None, allowed, lookup=True)
    ids = {x.asset_name for x in breakdowns if x.asset_name} | {x.fleet_number for x in legals if x.fleet_number}
    txt = (txt or '').casefold()
    rows = [(name, assets[name].asset_name or name) for name in sorted(ids)
            if name in assets and (txt in name.casefold() or txt in (assets[name].asset_name or '').casefold())]
    offset, size = max(0, cint(start)), min(50, max(1, cint(page_len)))
    return rows[offset:offset + size]


def paginate(rows, page, size):
    page = max(1, min(cint(page) or 1, max(1, (len(rows) + size - 1) // size)))
    return dict(rows=rows[(page - 1) * size:page * size], total=len(rows), page=page, page_size=size)


@frappe.whitelist()
def get_dashboard(from_date=None, to_date=None, site=None, asset_category=None, fleet=None,
                  category=None, additional_keywords=None, history_page=1, legal_page=1, page_size=50,
                  include_frequency=0, frequency_fleet=None):
    allowed = check_access()
    start, end = date_range(from_date, to_date)
    source_filters(start, end, site, allowed)
    configured = categories()
    chosen = next((x for x in configured if x['category'] == category), None)
    if category and not chosen:
        frappe.throw('Choose a configured Problem Category.')
    extra = additional_keywords or ''
    if len(extra) > 1000:
        frappe.throw('Additional Keywords must be 1,000 characters or fewer.')
    keywords = list(dict.fromkeys((chosen['keywords'] if chosen else []) + terms(extra)))
    sections = chosen['test_sections'] if chosen else list(dict.fromkeys(s for x in configured for s in x['test_sections']))
    breakdowns, legal_rows, _ = load_sources(start, end, site, asset_category, fleet, allowed)
    legals = []
    for row in legal_rows:
        if row.sections == 'Machine Service Records':
            row['event_type'] = 'service'
        elif row.sections in sections:
            row['event_type'] = 'test'
        else:
            continue
        legals.append(row)
    report = build_report(breakdowns, legals, keywords, start, end,
                          category=category, additional_keywords=terms(extra))
    if cint(include_frequency):
        frequency = build_frequency(report['history'], breakdowns)
        if frequency_fleet:
            frequency = [x for x in frequency if (x['fleet'] or 'Unassigned') == frequency_fleet]
        valid = [x['gap_hours'] for x in frequency if x['valid_difference']]
        report['frequency'] = dict(rows=frequency[:CHART_LIMIT], total=len(frequency),
                                   average_gap=mean(valid), valid_intervals=len(valid))
    size = min(100, max(1, cint(page_size) or 50))
    report['tables'] = dict(history=paginate(list(reversed(report.pop('history'))), history_page, size),
                            legal=paginate(list(reversed(report.pop('legal'))), legal_page, size))
    report['limits'] = {}
    for key in ('timeline', 'intervals', 'machines'):
        rows = report[key]
        report['limits'][key] = dict(total=len(rows), shown=min(CHART_LIMIT, len(rows)))
        report[key] = rows[:CHART_LIMIT]
    report['keywords'] = keywords
    report['scope'] = dict(from_date=str(start), to_date=str(end), category=category or 'All Problems', site=site,
                           asset_category=asset_category, fleet=fleet)
    return report


@frappe.whitelist()
def get_frequency(from_date=None, to_date=None, site=None, asset_category=None, fleet=None,
                  category=None, additional_keywords=None, chart_fleet=None):
    # Reuse the exact same permission checks, filters and matching as Overview.
    report = get_dashboard(from_date=from_date, to_date=to_date, site=site,
                           asset_category=asset_category, fleet=fleet, category=category,
                           additional_keywords=additional_keywords, include_frequency=1,
                           frequency_fleet=chart_fleet)
    return dict(report['frequency'], keywords=report['keywords'])
