"""Monthly assurance calculations, record counts, rendering and permission-checked API.

Source reports and the Daily A&U Engine Dashboard remain unchanged.
"""
import base64
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from html import escape
import math
import re
import textwrap
from urllib.parse import quote

import frappe
from frappe.utils import getdate, nowdate, get_url

from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS, classification_names


GROUPS = ('ADTs', 'Excavators', 'Drills', 'Graders', 'FELs', 'Dozers', 'Ancillary')
CATEGORY_GROUPS = {'ADT': 'ADTs', 'Excavator': 'Excavators', 'Drills': 'Drills',
                   'Grader': 'Graders', 'Loader': 'FELs', 'Dozer': 'Dozers',
                   'Service Truck': 'Ancillary', 'TLB': 'Ancillary',
                   'Water Bowser': 'Ancillary', 'Diesel Bowsers': 'Ancillary'}
BASIS = '85% A & U'
MACHINE_SCOPE = 'Production + Swing/Spare Machines'
OWNERSHIP = 'Isambane & Excavo Assets'
ACTIONS = 'Monthly TMM Assurance Actions'
PBM = 'Plant Breakdown or Maintenance'


def month_offset(value, offset):
    index = value.year * 12 + value.month - 1 + offset
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)


def reporting_period(value=None, today=None):
    today = today or date.today()
    if not value:
        month = month_offset(today, -1)
    else:
        value = str(value)
        if not re.fullmatch(r'\d{4}-\d{2}(-01)?', value):
            raise ValueError('Reporting Month must be a month (YYYY-MM).')
        month = date.fromisoformat(value[:7] + '-01')
    if month >= today.replace(day=1):
        raise ValueError('Select a completed reporting month.')
    months = []
    for offset in (-2, -1, 0):
        start = month_offset(month, offset)
        months.append(dict(key=start.isoformat(), label=start.strftime('%b %Y'),
                           end=(month_offset(start, 1)-timedelta(days=1)).isoformat()))
    return dict(reporting_month=month.isoformat(), month_label=month.strftime('%B %Y'),
                months=months, due_date=month_offset(month, 1).replace(day=3).isoformat(),
                period_label=f"{months[0]['label']} – {months[-1]['label']}")


def equipment_group(category):
    # Import the dashboard's aliases rather than creating a competing alias list.
    from engineering.engineering.page.daily_availability_and_utilization_dashboard.daily_availability_and_utilization_dashboard import CATEGORY_MAP
    return CATEGORY_GROUPS.get(CATEGORY_MAP.get(category, category))


def operational_window(month):
    start = date.fromisoformat(month)
    return datetime.combine(start, time(6)), datetime.combine(month_offset(start, 1), time(6))


def event_segments(rows, start, end):
    """Union per asset. Concurrent different categories retain a combined label.

    This avoids assigning shared hours arbitrarily to one cause or counting them
    twice. Free-text breakdown reasons are deliberately never classified.
    """
    by_asset = defaultdict(list)
    for row in rows:
        if row.get('exclude_from_au') or row.get('docstatus') == 2:
            continue
        if str(row.get('downtime_type') or 'Breakdown').strip() == 'Planned Maintenance':
            continue
        if not row.get('breakdown_start_datetime'):
            continue
        a = max(datetime.fromisoformat(str(row['breakdown_start_datetime'])), start)
        b = min(datetime.fromisoformat(str(row['resolved_datetime'])) if row.get('resolved_datetime') else end, end)
        if a < b:
            by_asset[str(row['asset_name']).strip()].append((a, b, str(row.get('failure_classification') or '').strip() or 'Uncategorised'))
    result = []
    for asset, events in sorted(by_asset.items()):
        bounds = sorted({point for a, b, _ in events for point in (a, b)})
        for a, b in zip(bounds, bounds[1:]):
            causes = sorted({cause for x, y, cause in events if x < b and y > a})
            if causes:
                label = ' / '.join(causes)
                if result and result[-1][0] == asset and result[-1][2] == a and result[-1][3] == label:
                    prior = result.pop()
                    a = prior[1]
                result.append((asset, a, b, label))
    return result


def pareto(hours_by_cause):
    pairs = sorted(((cause, hours) for cause, hours in hours_by_cause.items() if hours > 0), key=lambda x: (-x[1], x[0]))
    total = sum(hours for _, hours in pairs)
    running, result = 0, []
    for index, (cause, hours) in enumerate(pairs):
        running += hours
        result.append(dict(cause=cause, hours=hours,
                           cumulative_percent=100.0 if index == len(pairs)-1 else running / total * 100))
    return result


def category_counts(records, classifications=None):
    classifications = tuple(INITIAL_CLASSIFICATIONS if classifications is None else classifications)
    by_name = {}
    for record in records:
        if record.get('docstatus') == 2:
            continue
        if not record.get('name'):
            raise ValueError('A stable breakdown reference is required for counting.')
        by_name.setdefault(record['name'], dict(record))
    grouped = {category: [] for category in classifications}
    unresolved = []
    for record in by_name.values():
        category = record.get('failure_classification')
        if category in grouped:
            grouped[category].append(record)
        else:
            record['review_reason'] = 'Missing classification' if not category else f'Unsupported classification: {category}'
            unresolved.append(record)
    categories = sorted((dict(category=c, count=len(rows), records=rows) for c, rows in grouped.items() if rows),
                        key=lambda row: (-row['count'], classifications.index(row['category'])))
    total = sum(row['count'] for row in categories)
    running = 0
    priority_records = []
    priority_count = 0
    for row in categories:
        row['priority'] = running < total * .8
        running += row['count']
        row['cumulative_percent'] = running / total * 100
        if row['priority']:
            priority_records.extend(row['records'])
            priority_count += 1
    full = categories + [dict(category=c, count=0, records=[], priority=False, cumulative_percent=100 if total else 0) for c in classifications if not grouped[c]]
    return dict(categories=categories, all_categories=full, total_count=len(by_name), categorised_count=total,
                unresolved_count=len(unresolved), unresolved_records=unresolved,
                priority_records=priority_records, priority_category_count=priority_count,
                priority_percent=len(priority_records)/total*100 if total else 0,
                displayed_count=min(len(categories),10),
                omitted_categories=max(len(categories)-10,0),
                omitted_count=sum(row['count'] for row in categories[10:]))


def monthly_population(records, month):
    """One event per record whose recorded interval touches the calendar month.

    Starts within the month count even for instantaneous events. Earlier events
    require positive overlap (open or resolved strictly after month start).
    """
    start = datetime.combine(date.fromisoformat(month), time.min)
    end = datetime.combine(month_offset(start.date(), 1), time.min)
    selected = {}
    for row in records:
        if row.get('docstatus') == 2 or str(row.get('downtime_type') or '').strip() not in ('', 'Breakdown'):
            continue
        stamp = row.get('breakdown_start_datetime')
        if not stamp:
            continue
        reported = datetime.fromisoformat(str(stamp))
        if reported >= end:
            continue
        resolved = row.get('resolved_datetime')
        if reported < start and resolved and datetime.fromisoformat(str(resolved)) <= start:
            continue
        record = dict(row)
        record['status_label'] = 'Closed (current)' if record.get('resolved_datetime') else 'Open (current)'
        selected.setdefault(record['name'], record)
    return list(selected.values())


def percent(value):
    return 'N/A' if value is None else f'{value:.1f}%'


def availability_svg(data):
    """Three independently calculated monthly values per group; no averaging."""
    width, height, left, right, top, bottom = 1200, 290, 65, 1180, 30, 220
    values = [v for g in data['groups'] for v in g['availability'] if v is not None]
    maximum = max(100, math.ceil(max(values, default=100)/20)*20)
    colors = ('#234f87', '#3293ff', '#9ad0ff')
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="Availability by equipment group for three individual months" style="width:100%;height:auto;min-width:850px">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<g font-family="Arial, sans-serif" font-size="12" fill="#192c48">']
    for tick in range(6):
        y = bottom - (bottom-top)*tick/5
        svg.extend([f'<path d="M{left} {y}H{right}" stroke="#e5eaf0"/>',
                    f'<text x="{left-10}" y="{y+4}" text-anchor="end">{maximum*tick/5:g}</text>'])
    step = (right-left)/len(data['groups'])
    for i, group in enumerate(data['groups']):
        x = left + step*(i+.5)
        label = escape(group['group'], quote=True)
        svg.append(f'<g data-group="{label}" tabindex="0" role="button" aria-label="{label}: view breakdown categories and actions" style="cursor:pointer">')
        svg.append(f'<rect class="tmm-group-highlight" x="{left+step*i}" y="{top-20}" width="{step}" height="{bottom-top+54}" fill="#e6f1ff" opacity="0"/>')
        for j, value in enumerate(group['availability']):
            bar_x = x + (j-1)*step*.25 - step*.11
            bar_h = 0 if value is None else (bottom-top)*max(value,0)/maximum
            text = percent(value)
            month = escape(data['months'][j]['label'])
            svg.append(f'<rect data-month="{month}" x="{bar_x}" y="{bottom-bar_h}" width="{step*.22}" height="{bar_h}" fill="{colors[j]}"><title>{label} · {month}: {text}</title></rect>')
            svg.append(f'<text x="{bar_x+step*.11}" y="{bottom-bar_h-8}" text-anchor="middle" font-size="11">{text}</text>')
        svg.append(f'<text x="{x}" y="{bottom+22}" text-anchor="middle">{label}</text></g>')
    for j, month in enumerate(data['months']):
        x = 400 + j*180
        svg.append(f'<rect x="{x}" y="265" width="14" height="14" fill="{colors[j]}"/><text x="{x+22}" y="277">{escape(month["label"])}</text>')
    svg.append('<text transform="translate(16 130) rotate(-90)" text-anchor="middle">Availability (%)</text></g></svg>')
    return ''.join(svg)


def availability_image(data):
    svg = availability_svg(data).replace(' style="width:100%;height:auto;min-width:850px"', '')
    encoded = base64.b64encode(svg.encode()).decode()
    return f'<img alt="Three-month availability by equipment group" src="data:image/svg+xml;base64,{encoded}" style="width:100%;height:auto"/>'


def count_summary(counts):
    if not counts['categorised_count']:
        return 'No categorised breakdown records in this population.'
    return f"{counts['priority_category_count']} categories account for {counts['priority_percent']:.1f}% of categorised breakdown records."


def completeness(counts):
    return (f"{counts['categorised_count']} categorised + {counts['unresolved_count']} unresolved = "
            f"{counts['total_count']} breakdown records. Cumulative percentages exclude unresolved categories.")


def count_chart_image(counts, limit=10):
    rows = counts['categories'] if limit is None else counts['categories'][:limit]
    if not rows:
        return '<p class="text-muted">No categorised breakdown records for this reporting month.</p>'
    width = max(1200, len(rows)*110+140)
    left, right, top, bottom = 75, width-80, 40, 230
    maximum = max(r['count'] for r in rows)
    maximum = max(1, math.ceil(maximum/5)*5) if maximum > 5 else maximum
    step = (right-left)/len(rows)
    labels = [textwrap.wrap(r['category'],width=18) for r in rows]
    height = bottom+70+max(len(x) for x in labels)*15
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<g font-family="Arial, sans-serif" font-size="12" fill="#192c48">']
    for tick in range(6):
        y = bottom-(bottom-top)*tick/5
        svg.extend([f'<path d="M{left} {y}H{right}" stroke="#e5eaf0"/>',
                    f'<text x="{right+10}" y="{y+4}">{tick*20}%</text>'])
    for tick in range(0, maximum+1, max(1, math.ceil(maximum/5))):
        y = bottom-(bottom-top)*tick/maximum
        svg.append(f'<text x="{left-10}" y="{y+4}" text-anchor="end">{tick}</text>')
    y80 = bottom-(bottom-top)*.8
    points=[]
    for index,row in enumerate(rows):
        x=left+step*(index+.5)
        y=bottom-(bottom-top)*row['count']/maximum
        cy=bottom-(bottom-top)*row['cumulative_percent']/100
        points.append(f'{x},{cy}')
        fill='#3293ff' if row['priority'] else '#9ab7d8'
        svg.append(f'<rect x="{x-step*.29}" y="{y}" width="{step*.58}" height="{bottom-y}" fill="{fill}"/>')
        label_y=y+16 if abs(cy-y)<28 else max(y-7,15)
        svg.append(f'<text x="{x}" y="{label_y}" text-anchor="middle" font-weight="bold">{row["count"]}</text>')
        for line,label in enumerate(labels[index]):
            svg.append(f'<text x="{x}" y="{bottom+21+line*15}" text-anchor="middle">{escape(label)}</text>')
    svg.extend([f'<path d="M{left} {y80}H{right}" stroke="#c18016" stroke-dasharray="6 5"/>',
                f'<rect x="{right-118}" y="{y80-21}" width="118" height="18" fill="white" opacity="0.95"/>',
                f'<text x="{right}" y="{y80-7}" text-anchor="end">80% reference</text>'])
    svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#ff9400" stroke-width="2"/>')
    for index,row in enumerate(rows):
        x,cy=points[index].split(',')
        svg.extend([f'<circle cx="{x}" cy="{cy}" r="4" fill="#ff9400"/>',
                    f'<text x="{x}" y="{float(cy)-10}" text-anchor="middle">{row["cumulative_percent"]:.1f}%</text>'])
    svg.extend(['<text transform="translate(18 140) rotate(-90)" text-anchor="middle">Number of breakdown records</text>',
                f'<text transform="translate({width-12} 140) rotate(-90)" text-anchor="middle">Cumulative percentage</text>',
                f'<text x="{left}" y="{height-12}">Blue bars: first 80% priority set · Orange line: cumulative percentage of all categorised records</text>',
                '</g></svg>'])
    encoded=base64.b64encode(''.join(svg).encode()).decode()
    return f'<img class="tmm-pareto-image" alt="Breakdown record counts and cumulative percentage" src="data:image/svg+xml;base64,{encoded}" style="width:100%;height:auto"/>'


def record_table(records, base_url='', add_action=False):
    if not records:
        return '<p class="text-muted">No breakdown records in this selection.</p>'
    rows=[]
    esc=lambda v:escape(str(v or ''))
    for row in records:
        url=base_url.rstrip('/')+'/app/plant-breakdown-or-maintenance/'+quote(row['name'],safe='')
        category=row.get('failure_classification') or 'Missing classification'
        cells=[esc(category),esc(row.get('asset_name')),f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(row["name"])}</a>',
               esc(row.get('breakdown_start_datetime')),esc(row.get('breakdown_reason')),esc(row.get('status_label'))]
        if add_action:
            cells.append(f'<button class="btn btn-default btn-xs tmm-action-for-record" data-reference="{esc(row["name"])}">Add action</button>')
        rows.append('<tr>'+''.join('<td>'+value+'</td>' for value in cells)+'</tr>')
    headers=['Failure Classification','Machine','Breakdown Reference','Reported Date','Description','Status (current)']+([''] if add_action else [])
    cols='<colgroup>'+''.join('<col style="width:'+width+'">' for width in ['16%','11%','17%','15%','27%','14%'])+'</colgroup>' if not add_action else ''
    return '<table class="tmm-breakdowns">'+cols+'<thead><tr>'+''.join('<th>'+x+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


def report_html(data):
    esc=lambda v:escape(str(v or ''))
    sections=[]
    for group in data['groups']:
        counts=group['counts']
        if not (counts['total_count'] or group['actions'] or any(v is not None for v in group['availability'])):
            continue
        all_rows=counts['all_categories']
        midpoint=math.ceil(len(all_rows)/2)
        full_rows=[]
        for index in range(midpoint):
            cells=[]
            for offset in (0,midpoint):
                row=all_rows[index+offset] if index+offset<len(all_rows) else None
                cells.extend([esc(row['category']),str(row['count']),'Yes' if row['priority'] else ''] if row else ['','',''])
            full_rows.append('<tr>'+''.join('<td>'+value+'</td>' for value in cells)+'</tr>')
        cols='<colgroup>'+''.join('<col style="width:'+width+'">' for width in ['30%','8%','12%']*2)+'</colgroup>'
        category_table='<table class="tmm-category-counts">'+cols+'<thead><tr><th>Category — full breakdown</th><th>Count</th><th>80% set</th><th>Category — continued</th><th>Count</th><th>80% set</th></tr></thead><tbody>'+''.join(full_rows)+'</tbody></table>'
        actions=[]
        for action in group['actions']:
            actions.append('<tr>'+''.join(f'<td>{esc(action.get(k))}</td>' for k in ('cause','action','owner_name','due_date','status','breakdown_reference'))+'</tr>')
        action_table='<table><thead><tr><th>Category</th><th>Action</th><th>Owner</th><th>Due</th><th>Status</th><th>Breakdown Reference</th></tr></thead><tbody>'+''.join(actions)+'</tbody></table>' if actions else '<p class="text-muted">No saved corrective actions.</p>'
        omitted=f"Top 10 shown; {counts['omitted_categories']} categories / {counts['omitted_count']} records omitted from chart (included in the denominator and full breakdown below)." if counts['omitted_categories'] else 'All categories with records are shown.'
        sections.append(f'<section class="group-detail"><h2>{esc(group["group"])} · Breakdown records by category</h2><p>{esc(data["population"])} · {esc(data["month_label"])}</p>{count_chart_image(counts)}<p>{esc(count_summary(counts))}</p><p>{esc(completeness(counts))}</p><p>{esc(omitted)}</p>{category_table}<h3>Breakdowns contributing to the first 80%</h3>{record_table(counts["priority_records"],data.get("base_url",""))}<h3>Unresolved categorisation — review</h3>{record_table(counts["unresolved_records"],data.get("base_url",""))}<h3>Corrective actions · {esc(group["group"])}</h3>{action_table}</section>')
    if data.get('unassigned_records'):
        sections.append('<section class="group-detail"><h2>Equipment group requires review</h2>'+record_table(data['unassigned_records'],data.get('base_url',''))+'</section>')
    if not sections:
        sections=['<p class="text-muted">No availability, breakdown records or saved actions for this period.</p>']
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
    body{{font:12px Arial,sans-serif;color:#182b45}}h1{{font-size:24px}}h2{{font-size:18px}}h3{{font-size:15px;page-break-after:avoid}}
    table{{border-collapse:collapse;width:100%;margin:12px 0;table-layout:fixed}}td,th{{border:1px solid #dce4ed;padding:6px;text-align:left;vertical-align:top;white-space:pre-wrap;word-wrap:break-word}}th{{background:#f0f4f8}}thead{{display:table-header-group}}tr{{page-break-inside:avoid}}
    .tmm-category-counts{{font-size:11px}}.tmm-category-counts td,.tmm-category-counts th{{padding:4px}}.text-muted{{color:#63738b}}.group-detail{{page-break-before:always}}.tmm-pareto-image{{display:block}}img{{page-break-inside:avoid}}a{{color:#145b96}}
    </style></head><body><h1>Monthly TMM Assurance</h1><p><b>Site:</b> {esc(data['site'])}</p>
    <p><b>Reporting month:</b> {esc(data['month_label'])} · <b>Period:</b> {esc(data['period_label'])} · <b>Submission due:</b> {esc(data['due_date'])}</p>
    <p>{esc(data['population'])}. Counting unit: {esc(data['counting_unit'])}. {esc(data['status_basis'])}.</p>
    <h2>Availability by equipment group</h2>{availability_image(data)}
    <p class="text-muted">Daily A&amp;U Engine Dashboard basis: 85% A &amp; U; Production + Swing/Spare Machines; Isambane &amp; Excavo Assets. N/A means no valid required-hour data.</p>
    {''.join(sections)}</body></html>'''


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
                                   'resolved_datetime', 'failure_classification', 'downtime_type',
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
    choices = classification_names()
    return {g: category_counts(records, choices) for g, records in grouped.items()}, unassigned


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
    result.update(availability_chart=availability_svg(result), failure_classifications=classification_names(),
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
    frappe.local.response.filename = f"Monthly TMM Assurance {data['reporting_month'][:7]}.pdf"
    frappe.local.response.filecontent = get_pdf(report_html(data), {'page-size': 'A4', 'encoding': 'UTF-8',
                                                                 'margin-top': '12mm', 'margin-bottom': '12mm'})
    frappe.local.response.type = 'pdf'
