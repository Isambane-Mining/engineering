"""Permission-aware sources and presentation for the independent 24-hour report."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from html import escape

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, now_datetime

from engineering.engineering.machine_exclusions import is_pre_use_au_excluded
from engineering.engineering.report.availability_and_utilisation_engine import availability_and_utilisation_engine as sources

REPORT = 'Availability and Utilisation Engine (24)'
CONFIG = 'Startup and Fatigue spesification'


def check_access():
    if not frappe.get_doc('Report', REPORT).is_permitted() or not frappe.has_permission('Plant Breakdown or Maintenance', 'report'):
        frappe.throw(_('Not permitted to run this report.'), frappe.PermissionError)


def validate_filters(filters):
    f = frappe._dict(filters or {})
    if not f.from_date or not f.to_date:
        frappe.throw(_('From Date and To Date are required.'))
    f.from_date, f.to_date = getdate(f.from_date), getdate(f.to_date)
    if f.from_date > f.to_date:
        frappe.throw(_('From Date must be on or before To Date.'))
    f.formula = f.formula or 'Isambane Formula'
    if f.formula not in FORMULAS:
        frappe.throw(_('Choose Industry Formula or Isambane Formula.'))
    f.asset_ownership = f.asset_ownership or 'Isambane & Excavo Assets'
    if f.asset_ownership not in ('Isambane & Excavo Assets', 'Supplier Assets', 'All Assets'):
        frappe.throw(_('Invalid asset ownership.'))
    for key in ('sites', 'assets', 'companies'):
        f[key] = sources.parse_multiselect(f.get(key))
    return f


def permitted_sites(selected=()):
    filters = {'name': ['in', selected]} if selected else {}
    sites = frappe.get_list('Location', filters=filters, pluck='name', limit_page_length=0)
    if set(selected) - set(sites):
        frappe.throw(_('One or more selected sites are unavailable or not permitted.'), frappe.PermissionError)
    return sites


def read_assets(f):
    sites = permitted_sites(f.sites)
    if not sites:
        return [], {}
    planning = sources.get_planning_rows(f.from_date, f.to_date, sites)
    allowed_plans = set(frappe.get_list('Monthly Production Planning',
        filters={'name': ['in', [p.name for p in planning]]}, pluck='name', limit_page_length=0)) if planning else set()
    planning = [p for p in planning if p.name in allowed_plans]
    if not planning:
        return [], {}
    days = sources.build_planning_map(planning)
    assets = sources.get_assets(planning, f.assets, f.companies, f.asset_ownership)
    allowed_assets = set(frappe.get_list('Asset', filters={'name': ['in', [a.name for a in assets]]},
        pluck='name', limit_page_length=0)) if assets else set()
    assets = [a for a in assets if a.name in allowed_assets and not any(
        is_pre_use_au_excluded(a.location, value) for value in (a.name, a.asset_name))]
    return assets, days


def read_sources(f):
    assets, days = read_assets(f)
    if not assets:
        return [], days, {}, []
    sites = sorted({a.location for a in assets})
    preuse = read_preuse(f, sites, assets)
    start = datetime.combine(f.from_date, time(6))
    end = datetime.combine(f.to_date + timedelta(days=1), time(6))
    pbm = frappe.get_list('Plant Breakdown or Maintenance', filters={
        'docstatus': ['<', 2], 'location': ['in', sites],
        'asset_name': ['in', sorted({a.asset_name for a in assets} | {a.name for a in assets})],
        'exclude_from_au': 0, 'downtime_type': ['in', ['Breakdown', 'Planned Maintenance']],
        'breakdown_start_datetime': ['<', end]},
        or_filters=[['resolved_datetime', '>=', start], ['resolved_datetime', 'is', 'not set']],
        fields=['asset_name', 'location', 'downtime_type', 'breakdown_start_datetime', 'resolved_datetime'], limit_page_length=0)
    return assets, days, preuse, pbm


def read_preuse(f, sites, assets):
    """Same parent/child/meter source and last-record-per-shift policy as the engine.

    Parent reads enforce permissions; child records inherit those permissions.
    No 18-hour validation or legacy denominator is used here.
    """
    parents = frappe.get_list('Pre-Use Hours', filters={'docstatus': ['<', 2],
        'location': ['in', sites], 'shift_date': ['between', [f.from_date, f.to_date]]},
        fields=['name', 'location', 'shift_date', 'shift'], order_by='shift_date, name', limit_page_length=0)
    if not parents:
        return {}
    children = frappe.get_all('Pre-use Assets', filters={'parent': ['in', [p.name for p in parents]],
        'parenttype': 'Pre-Use Hours', 'parentfield': 'pre_use_assets'},
        fields=['parent', 'idx', 'plant_no', 'asset_name', 'eng_hrs_start', 'eng_hrs_end'], order_by='idx')
    by_parent = defaultdict(list)
    for row in children:
        by_parent[row.parent].append(row)
    fleets = {a.name: a.asset_name for a in assets}
    result = {}
    for p in parents:
        for row in by_parent[p.name]:
            fleet = (row.plant_no or '').strip() or fleets.get(row.asset_name)
            if fleet:
                result[(p.location, str(p.shift_date), p.shift, fleet)] = row
    return result


def build_rows(f, assets, days, preuse, pbm):
    """Industry path only: raw PBM, no startup/fatigue/configuration access."""
    warnings = set()
    downtime = defaultdict(list)
    clock = now_datetime()
    for row in pbm:
        start = get_datetime(row.breakdown_start_datetime)
        end = get_datetime(row.resolved_datetime) if row.resolved_datetime else clock
        if end > start:
            downtime[(row.location, str(row.asset_name).strip())].append((row.downtime_type, start, end))
    work = defaultdict(float)
    for (site, day, shift, fleet), reading in preuse.items():
        first, last = reading.get('eng_hrs_start'), reading.get('eng_hrs_end')
        if first is not None and last is not None and float(last) >= float(first):
            work[(site, day, fleet)] += float(last) - float(first)
        else:
            warnings.add(_('Invalid or incomplete meter readings excluded from recorded working hours.'))
    rows = []
    for asset in assets:
        daily = []
        day = f.from_date
        while day <= f.to_date:
            if (asset.location, str(day)) in days:
                daily.append(calculate_day(day, f.formula, working=work[(asset.location, str(day), asset.asset_name)],
                    downtime=downtime[(asset.location, asset.asset_name)] + (downtime[(asset.location, asset.name)] if asset.name != asset.asset_name else [])))
            day += timedelta(days=1)
        if daily:
            row = total_row(daily)
            row.update(index=len(rows) + 1, site=asset.location, asset=asset.asset_name,
                       asset_type=asset.asset_category, is_total_row=False)
            rows.append(row)
    rows.append(total_row(rows))
    return rows, sorted(warnings)


def build_isambane_rows(f):
    """Reuse the canonical Engine's shifts, PBM exclusions and integrity rules.

    Do not call its Industry branch or its report execute/reason decorators.
    Targets must never activate the original report's 0.85 result multiplier.
    """
    assets, days = read_assets(f)
    if not assets:
        return [total_row([])], []
    engine_filters = frappe._dict(from_date=f.from_date, to_date=f.to_date,
        locations=sorted({a.location for a in assets}), assets=[a.name for a in assets],
        companies=f.companies, asset_ownership=f.asset_ownership,
        free_hours=0, production_machines_only=0,
        au_calculation='Isambane A&U Calculation', au_percentage_basis='100% A & U')
    engine_rows = sources.get_data(engine_filters)
    shifts = defaultdict(list)
    for row in engine_rows:
        if row.get('indent') == 3:
            shifts[(row.get('location'), row.get('asset_name'))].append(row)
    rows = []
    warnings = []
    for asset in assets:
        machine_shifts = shifts.get((asset.location, asset.asset_name), [])
        if not machine_shifts:
            continue
        # Engine summaries sum valid underlying shifts, including Sunday work
        # with zero Required Hours. Never recalculate MAX/MIN on period totals.
        summary = sources.build_summary_row(machine_shifts, indent=2)
        row = dict(index=len(rows) + 1, site=asset.location, asset=asset.asset_name,
            asset_type=asset.asset_category, is_total_row=False,
            total_hours=summary['required_hours'], breakdown_hours=summary['breakdown_hours'],
            planned_maintenance_hours=summary['planned_maintenance_hours'],
            safety_meeting_hours=None, fatigue_hours=None, tramming_out_hours=None,
            availability_available=summary['availability_available_hours'],
            utilisation_available=summary['utilisation_available_hours'], working_hours=summary['work_hours'])
        row['availability_percent'] = ratio(row['availability_available'], row['total_hours'])
        row['utilisation_percent'] = ratio(row['working_hours'], row['utilisation_available'])
        rows.append(row)
    if any(row.get('invalid_pre_use') for row in engine_rows if row.get('indent') == 3):
        warnings.append(_('Original Engine Pre-Use integrity exclusions apply; invalid shifts are excluded from its summaries.'))
    rows.append(total_row(rows))
    return rows, warnings


def get_columns(formula='Industry Formula'):
    specifications = [('#', 'index', 'Int', 45), ('Site', 'site', 'Link', 145), ('Asset', 'asset', 'Data', 110),
        ('Asset Type', 'asset_type', 'Data', 120), ('Total Hours (24h)', 'total_hours', 'Float', 135),
        ('Breakdowns (h)', 'breakdown_hours', 'Float', 135), ('Planned Maintenance (h)', 'planned_maintenance_hours', 'Float', 175),
        ('Safety Meeting (h)', 'safety_meeting_hours', 'Float', 145), ('Fatigue (h)', 'fatigue_hours', 'Float', 115),
        ('Tramming Out (h)', 'tramming_out_hours', 'Float', 140), ('Availability Available (h)', 'availability_available', 'Float', 185),
        ('Availability (%)', 'availability_percent', 'Percent', 140), ('Utilisation Available (h)', 'utilisation_available', 'Float', 185),
        ('Working Hours (h)', 'working_hours', 'Float', 150), ('Utilisation (%)', 'utilisation_percent', 'Percent', 140)]
    columns = [dict(label=_(label), fieldname=key, fieldtype=kind, width=width, precision=2) for label, key, kind, width in specifications]
    columns[1]['options'] = 'Location'
    if formula == 'Isambane Formula':
        columns[4]['label'] = _('Required Hours (h)')
    return columns


def execute(filters=None):
    check_access()
    f = validate_filters(filters)
    if f.formula == 'Industry Formula':
        rows, warnings = build_rows(f, *read_sources(f))
        notes = [_('Industry: fixed 24-hour daily base; availability deducts raw breakdown and raw maintenance, including startup/fatigue overlaps. Utilisation is Working Hours / 24. No startup, fatigue, safety or tramming deduction.')]
    else:
        rows, warnings = build_isambane_rows(f)
        notes = [_('Isambane: original Engine Required Hours, PBM startup/fatigue exclusions, Pre-Use status/integrity rules and Sunday handling. MAX/MIN formulas run per shift before summing. Safety, Fatigue and Tramming columns are not separate deductions.')]
    availability_target, utilisation_target = TARGETS[f.formula]
    notes.append(_('Reference targets only: Availability {0}; Utilisation {1}. Targets do not scale results.').format(
        format(availability_target, '.0%'), format(utilisation_target, '.0%')))
    notes.append(_('Decimal ratios are formatted as percentages; totals divide summed underlying hours. A dash means unavailable or a zero denominator. The separate configuration dialog does not affect either formula.'))
    message = '<br>'.join(escape(s) for s in warnings + notes)
    return get_columns(f.formula), rows, message, None, None, True


@frappe.whitelist()
def get_site_configurations(sites=None):
    """Read existing site/shift/day-type startup and fatigue records."""
    check_access()
    selected = sources.parse_multiselect(sites)
    allowed_sites = permitted_sites(selected)

    if not allowed_sites:
        return []

    return frappe.get_list(
        CONFIG,
        filters={"site": ["in", allowed_sites]},
        fields=[
            "site",
            "shift",
            "day_type",
            "startup_start",
            "startup_end",
            "fatigue_start",
            "fatigue_end",
        ],
        order_by="site asc, day_type asc, shift asc",
        limit_page_length=0,
    )


# AU24 CALCULATION LOGIC - kept in the report controller.
FORMULAS = ('Industry Formula', 'Isambane Formula')
TARGETS = {'Industry Formula': (0.85, 0.75), 'Isambane Formula': (0.85, 0.85)}
DAY_TYPES = ('Weekday', 'Saturday', 'Sunday', 'Holiday')
WINDOWS = ('safety_meeting', 'fatigue', 'tramming_out')
HOUR_FIELDS = ('total_hours', 'breakdown_hours', 'planned_maintenance_hours',
               'safety_meeting_hours', 'fatigue_hours', 'tramming_out_hours',
               'availability_available', 'utilisation_available', 'working_hours')


def merge(intervals):
    result = []
    for start, end in sorted((max(0, s), min(24, e)) for s, e in intervals if e > s):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def hours(intervals):
    return sum(end - start for start, end in merge(intervals))


def window(start, end):
    if not start and not end:
        return []
    if not start or not end:
        raise ValueError('Both start and end times are required')
    def minutes(value):
        h, m = map(int, value.split(':'))
        if not 0 <= h < 24 or m not in (0, 15, 30, 45):
            raise ValueError('Times must be in 15-minute intervals')
        return h * 60 + m
    first, last = minutes(start), minutes(end)
    duration = (last - first) % 1440 / 60
    offset = (first - 360) % 1440 / 60
    # A time window belongs to the operational day; retain both pieces if it
    # crosses its 06:00 boundary rather than losing the early-morning tail.
    return merge([(offset, min(24, offset + duration)), (0, max(0, offset + duration - 24))])


def day_type(day, holidays):
    if day in holidays:
        return 'Holiday'
    return {5: 'Saturday', 6: 'Sunday'}.get(day.weekday(), 'Weekday')


def ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator is not None and denominator > 0 else None


def calculate_day(day, formula='Industry Formula', working=0, downtime=(), configuration=None):
    """Raw Industry day; the configuration callback is deliberately never used."""
    if formula != 'Industry Formula':
        raise ValueError('Isambane must use the original Engine shift calculation')
    origin = datetime.combine(day, time(6))
    raw = {'Breakdown': 0.0, 'Planned Maintenance': 0.0}
    for kind, start, end in downtime:
        if kind in raw:
            first = max(0, (start - origin).total_seconds() / 3600)
            last = min(24, (end - origin).total_seconds() / 3600)
            # Preserve each record's raw duration, including overlapping PBMs.
            # Availability is bounded, not the reported raw downtime columns.
            raw[kind] += max(0, last - first)
    r = dict.fromkeys(HOUR_FIELDS, 0.0)
    r.update(total_hours=24.0, breakdown_hours=raw['Breakdown'],
             planned_maintenance_hours=raw['Planned Maintenance'],
             availability_available=max(0, 24 - sum(raw.values())),
             utilisation_available=24.0, working_hours=working)
    r['availability_percent'] = ratio(r['availability_available'], 24)
    r['utilisation_percent'] = ratio(working, 24)
    return r


def total_row(rows):
    result = {'asset': 'Total / Average', 'is_total_row': True}
    for field in HOUR_FIELDS:
        values = [row.get(field) for row in rows]
        result[field] = None if any(v is None for v in values) else sum(values)
    result['availability_percent'] = ratio(result['availability_available'], result['total_hours'])
    result['utilisation_percent'] = ratio(result['working_hours'], result['utilisation_available'])
    return result
