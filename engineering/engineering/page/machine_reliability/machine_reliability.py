"""Read-only, permission-aware Machine Reliability endpoints."""
from datetime import timedelta

import frappe
from frappe.utils import cint, getdate, nowdate
from engineering.engineering.page.downtime_correction_dashboard.downtime_correction_dashboard import get_allowed_sites


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


# Machine reliability calculations

"""Pure calculations for Machine Reliability; source records are never changed."""
import re
from collections import defaultdict
from datetime import datetime, timedelta
from math import isfinite


def terms(value):
    return list(dict.fromkeys(x.strip().casefold() for x in re.split(r'[,\n]+', value or '') if x.strip()))


def classify(reason, resolution, keywords):
    def matches(text):
        text = str(text or '').casefold()
        return [word for word in keywords if re.search(
            r'(?<!\w)' + r'[\s\-/]+'.join(re.escape(p) for p in re.split(r'[\s\-/]+', word)) + r'(?!\w)', text)]
    direct = matches(reason)
    additional = matches(resolution)
    if not keywords:
        return 'direct', []
    return ('direct', direct) if direct else ('additional', additional) if additional else (None, [])


def classify_record(record, keywords, category=None, additional_keywords=None):
    """Manual complaint categories take precedence; extra terms extend the search.

    A different manual category suppresses category-keyword complaints, but not
    repair work in the resolution. Blank categories retain historical matching.
    """
    reason, resolution = record.get('breakdown_reason'), record.get('resolution_summary')
    manual = (record.get('problem_category') or '').strip()
    if category and manual:
        if manual == category:
            return 'direct', [], 'Manual category'
        if additional_keywords:
            match, matched = classify(reason, '', additional_keywords)
            if match == 'direct':
                return match, matched, 'Additional keywords in reason'
        match, matched = classify('', resolution, keywords)
    else:
        match, matched = classify(reason, resolution, keywords)
    source = 'Resolution keywords' if match == 'additional' else 'Reason keywords' if keywords else 'All records'
    return match, matched, source if match else None


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except (ValueError, TypeError):
        return None


def meter(value):
    try:
        number = float(value)
        return number if isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def mean(values):
    return round(sum(values) / len(values), 2) if values else None


def build_report(records, legals, keywords, from_date, to_date, category=None, additional_keywords=None):
    start = timestamp(str(from_date)[:10])
    end = timestamp(str(to_date)[:10]) + timedelta(days=1)
    enriched, groups = [], defaultdict(list)
    quality = dict(overlapping_records=0, reversed_intervals=0, incomplete_intervals=0, missing_readings=0, invalid_gaps=0)
    for source in records:
        match, matched, match_source = classify_record(source, keywords, category, additional_keywords)
        began, finished = timestamp(source.get('breakdown_start_datetime')), timestamp(source.get('resolved_datetime'))
        duration, flags = None, []
        if not began or not finished:
            flags.append('Incomplete interval')
            quality['incomplete_intervals'] += 1
        elif finished < began:
            flags.append('Reversed interval')
            quality['reversed_intervals'] += 1
        else:
            duration = (finished - began).total_seconds() / 3600
        item = dict(name=source['name'], doctype='Plant Breakdown or Maintenance',
                    fleet=source.get('asset_name'), site=source.get('location'), category=source.get('asset_category'),
                    date=str(began or ''), end=str(finished or ''), reason=source.get('breakdown_reason') or '',
                    resolution=source.get('resolution_summary') or '', machine_hours=meter(source.get('hours_breakdown_starts')),
                    standing_hours=round(duration, 2) if duration is not None else None,
                    downtime_type=source.get('downtime_type'), match=match, matched_terms=matched,
                    problem_category=source.get('problem_category') or '', match_source=match_source,
                    flags=flags, exclude_from_au=bool(source.get('exclude_from_au')))
        item['is_failure'] = match == 'direct' and item['downtime_type'] == 'Breakdown'
        item['event_type'] = 'failure' if item['is_failure'] else 'additional'
        if duration is not None and duration > 0 and item['fleet']:
            groups[item['fleet']].append((began, finished, item))
        enriched.append(item)

    # Mark *both* records in every overlap, including overlaps with other faults.
    for group in groups.values():
        latest_end, latest_item = None, None
        for began, finished, item in sorted(group, key=lambda x: (x[0], x[2]['name'])):
            if latest_end and began < latest_end:
                for record in (latest_item, item):
                    if 'Overlapping interval' not in record['flags']:
                        record['flags'].append('Overlapping interval')
            if latest_end is None or finished > latest_end:
                latest_end, latest_item = finished, item
    quality['overlapping_records'] = sum('Overlapping interval' in x['flags'] for x in enriched)

    relevant = [x for x in enriched if x['match']]
    history = sorted((x for x in relevant if x['is_failure']), key=lambda x: (x['date'], x['name']))
    previous, machine_map, intervals = {}, {}, []
    for item in history:
        fleet = item['fleet']
        item['gap_hours'], item['previous_failure'] = None, None
        item['gap_status'] = 'First failure in range'
        stats = machine_map.setdefault(fleet or '', dict(fleet=fleet or 'Unassigned', failures=0, valid_intervals=0, invalid_intervals=0, gaps=[]))
        stats['failures'] += 1
        if item['machine_hours'] is None:
            quality['missing_readings'] += 1
        prior = previous.get(fleet) if fleet else None
        if not fleet:
            item['gap_status'] = 'Missing fleet number'
        elif prior:
            item['previous_failure'] = prior['name']
            h, p = item['machine_hours'], prior['machine_hours']
            elapsed = (timestamp(item['date']) - timestamp(prior['date'])).total_seconds() / 3600
            if h is None or p is None:
                item['gap_status'] = 'Missing reading'
            elif h < p:
                item['gap_status'] = 'Decreasing reading'
            elif h == p:
                item['gap_status'] = 'Unchanged reading'
            elif h - p > elapsed:
                item['gap_status'] = 'Implausible increase'
            else:
                item['gap_hours'], item['gap_status'] = round(h - p, 2), 'Valid interval'
                intervals.append(item)
                stats['gaps'].append(item['gap_hours'])
            if item['gap_hours'] is None:
                stats['invalid_intervals'] += 1
                quality['invalid_gaps'] += 1
        if fleet:
            previous[fleet] = item  # Never bridge over missing or invalid readings.

    machines = []
    for stats in machine_map.values():
        gaps = stats.pop('gaps')
        stats.update(average_gap=mean(gaps), valid_intervals=len(gaps))
        machines.append(stats)
    machines.sort(key=lambda x: x['fleet'])

    unique = 0
    completed = [x for x in history if x['standing_hours'] is not None]
    windows = defaultdict(list)
    for item in completed:
        if item['fleet']:
            a, b = max(start, timestamp(item['date'])), min(end, timestamp(item['end']))
            if b > a:
                windows[item['fleet']].append((a, b))
    for group in windows.values():
        stop = None
        for a, b in sorted(group):
            effective_start = max(a, stop) if stop else a
            if b > effective_start:
                unique += (b - effective_start).total_seconds() / 3600
            stop = max(stop, b) if stop else b

    legal = [dict(name=x['name'], doctype='Engineering Legals', fleet=x.get('fleet_number'), site=x.get('site'),
                  date=str(x.get('start_date') or ''), reason=x.get('sections') or '', resolution='',
                  sections=x.get('sections'), event_type=x['event_type'], machine_hours=None, standing_hours=None,
                  flags=[], matched_terms=[]) for x in legals]
    summary = dict(problem_records=len(relevant), direct_failures=len(history),
                   additional_work=sum(x['match'] == 'additional' for x in relevant),
                   planned_work=sum(x['downtime_type'] == 'Planned Maintenance' for x in relevant),
                   average_failure_gap=mean([x['gap_hours'] for x in intervals]), valid_intervals=len(intervals),
                   average_standing_hours=mean([x['standing_hours'] for x in completed]), standing_records=len(completed),
                   unique_standing_hours=round(unique, 2), tests=sum(x['event_type'] == 'test' for x in legal),
                   services=sum(x['event_type'] == 'service' for x in legal))
    ranking = sorted((x for x in enriched if x['downtime_type'] == 'Breakdown' and x['standing_hours'] is not None),
                     key=lambda x: (-x['standing_hours'], x['name']))
    return dict(summary=summary, quality=quality, machines=machines, intervals=intervals, history=history,
                top_all=ranking[:10], top_problem=[x for x in ranking if x['is_failure']][:10], legal=legal,
                timeline=sorted(relevant + legal, key=lambda x: (x['date'], x['name'])))


def build_frequency(history, source_records):
    """Chart-only projection: keep suspect deltas visible, never in averages."""
    def reading(value):
        try:
            number = float(value)
            return number if isfinite(number) else None
        except (ValueError, TypeError):
            return None
    readings = {x['name']: reading(x.get('hours_breakdown_starts')) for x in source_records}
    result = []
    for item in history:
        previous = readings.get(item['previous_failure'])
        current = readings.get(item['name'])
        # Zero/missing readings cannot establish any operating-hour difference.
        delta = round(current - previous, 2) if previous is not None and current is not None and previous > 0 and current > 0 else None
        result.append(dict(item, previous_machine_hours=previous, current_machine_hours=current,
                           hour_difference=delta, valid_difference=item['gap_status'] == 'Valid interval'))
    return result
