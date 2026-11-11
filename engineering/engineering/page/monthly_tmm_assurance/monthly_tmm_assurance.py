"""Monthly assurance calculations, measured downtime, rendering and permission-checked API.

Source reports and the Daily A&U Engine Dashboard remain unchanged.
"""
import base64
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from html import escape
import math
import re
import textwrap
from urllib.parse import quote

import frappe
from frappe.utils import getdate, nowdate, now_datetime, get_url

from engineering.controllers.failure_classification import INITIAL_CLASSIFICATIONS, classification_names, standard_subcategory, terms


GROUPS = ('ADTs', 'Excavators', 'Drills', 'Graders', 'FELs', 'Dozers', 'Diesel bowsers', 'Water bowsers', 'TLBs', 'Service trucks')
ACTION_GROUPS = GROUPS + ('Ancillary',)
CATEGORY_GROUPS = {'ADT': 'ADTs', 'Excavator': 'Excavators', 'Drills': 'Drills',
                   'Grader': 'Graders', 'Loader': 'FELs', 'Dozer': 'Dozers',
                   'Service Truck': 'Service trucks', 'TLB': 'TLBs',
                   'Water Bowser': 'Water bowsers', 'Diesel Bowsers': 'Diesel bowsers'}
BASIS = '85 × SUM(stored available hours) / SUM(stored required hours)'
ACTIONS = 'Monthly TMM Assurance Actions'
PBM = 'Plant Breakdown or Maintenance'


def month_offset(value, offset):
    index = value.year * 12 + value.month - 1 + offset
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)


def reporting_period(value=None, today=None):
    """Reporting labels/due date only; source boundaries must come from MPP."""
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
        months.append(dict(key=start.isoformat(), label=start.strftime('%b %Y'), start=None, end=None))
    return dict(reporting_month=month.isoformat(), month_label=month.strftime('%B %Y'),
                months=months, due_date=month_offset(month, 1).replace(day=3).isoformat(),
                period_label=f"{months[0]['label']} – {months[-1]['label']}")


def equipment_group(category):
    # Deliberately explicit: unsupported categories are reported, not inferred.
    return CATEGORY_GROUPS.get(category)


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


def monthly_population(records, month, period_end):
    """One event per record whose recorded interval touches the inclusive MPP period.

    Starts within the period count even for instantaneous events. Earlier events
    require positive overlap (open or resolved strictly after period start).
    """
    start = datetime.combine(date.fromisoformat(month), time.min)
    end = datetime.combine(date.fromisoformat(str(period_end)) + timedelta(days=1), time.min)
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
    return 'N/A' if value is None else f'{value:.2f}%'


def availability_svg(data):
    """Three independently calculated monthly values per group; no averaging."""
    width, height, left, right, top, bottom = 1200, 290, 65, 1180, 30, 220
    groups = [g for g in data['groups'] if g['group'] in GROUPS]
    values = [v for g in groups for v in g['availability'] if v is not None]
    maximum = max(100, math.ceil(max(values, default=100)/20)*20)
    colors = ('#234f87', '#3293ff', '#9ad0ff')
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="Availability by equipment group for three individual months" style="width:100%;height:auto;min-width:850px">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<g font-family="Arial, sans-serif" font-size="12" fill="#192c48">']
    for tick in range(6):
        y = bottom - (bottom-top)*tick/5
        svg.extend([f'<path d="M{left} {y}H{right}" stroke="#e5eaf0"/>',
                    f'<text x="{left-10}" y="{y+4}" text-anchor="end">{maximum*tick/5:g}</text>'])
    step = (right-left)/len(groups)
    for i, group in enumerate(groups):
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
            svg.append(f'<text x="{bar_x+step*.11}" y="{bottom-bar_h-8}" text-anchor="middle" font-size="10">{text}</text>')
        svg.append(f'<text x="{x}" y="{bottom+22}" text-anchor="middle" font-size="11">{label}</text></g>')
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
    if 'classified_hours' not in counts:
        return f"{counts['priority_category_count']} categories account for {counts['priority_percent']:.1f}% of categorised breakdown records."
    if not counts['classified_hours']:
        return 'No classified planning-adjusted breakdown downtime in this period.'
    return f"{counts['priority_category_count']} classifications account for {counts['priority_percent']:.1f}% of classified downtime ({counts['classified_hours']:.2f} h)."


def completeness(counts):
    records = (f"{counts['categorised_count']} categorised + {counts['unresolved_count']} unresolved = "
               f"{counts['total_count']} breakdown records.")
    if 'classified_hours' in counts:
        return records + f" Classified: {counts['classified_hours']:.2f} h; classification review: {counts['unresolved_hours']:.2f} h (excluded from denominator). Timestamp review: {len(counts['invalid_records'])}."
    return records + ' Cumulative percentages exclude unresolved categories.'


def count_chart_image(counts, limit=10):
    metric = 'hours' if 'classified_hours' in counts else 'count'
    axis_title = 'Breakdown downtime (hours)' if metric == 'hours' else 'Number of breakdown records'
    rows = counts['categories'] if limit is None else counts['categories'][:limit]
    if not rows:
        return '<p class="text-muted">No classified breakdown downtime for this reporting month.</p>'
    width = max(1200, len(rows)*110+140)
    left, right, top, bottom = 75, width-80, 40, 230
    maximum = max(r[metric] for r in rows)
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
    for tick in range(0, math.ceil(maximum)+1, max(1, math.ceil(maximum/5))):
        y = bottom-(bottom-top)*tick/maximum
        svg.append(f'<text x="{left-10}" y="{y+4}" text-anchor="end">{tick}</text>')
    y80 = bottom-(bottom-top)*.8
    points=[]
    for index,row in enumerate(rows):
        x=left+step*(index+.5)
        y=bottom-(bottom-top)*row[metric]/maximum
        cy=bottom-(bottom-top)*row['cumulative_percent']/100
        points.append(f'{x},{cy}')
        fill='#3293ff' if row['priority'] else '#9ab7d8'
        svg.append(f'<rect x="{x-step*.29}" y="{y}" width="{step*.58}" height="{bottom-y}" fill="{fill}"/>')
        label_y=y+16 if abs(cy-y)<28 else max(y-7,15)
        svg.append(f'<text x="{x}" y="{label_y}" text-anchor="middle" font-weight="bold">{row[metric]:.2f}</text>')
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
    svg.extend([f'<text transform="translate(18 140) rotate(-90)" text-anchor="middle">{axis_title}</text>',
                f'<text transform="translate({width-12} 140) rotate(-90)" text-anchor="middle">Cumulative percentage</text>',
                f'<text x="{left}" y="{height-12}">Blue bars: first 80% priority set · Orange line: cumulative percentage of all classified downtime</text>',
                '</g></svg>'])
    encoded=base64.b64encode(''.join(svg).encode()).decode()
    return f'<img class="tmm-pareto-image" alt="Breakdown downtime hours and cumulative percentage" src="data:image/svg+xml;base64,{encoded}" style="width:100%;height:auto"/>'


def record_table(records, base_url='', add_action=False):
    if not records:
        return '<p class="text-muted">No breakdown records in this selection.</p>'
    rows=[]
    esc=lambda v:escape(str(v or ''))
    for row in records:
        url=base_url.rstrip('/')+'/app/plant-breakdown-or-maintenance/'+quote(row['name'],safe='')
        category=row.get('failure_classification') or 'Missing classification'
        cells=[esc(category),esc(row.get('asset_name')),f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(row["name"])}</a>',
               esc(row.get('breakdown_start_datetime')),esc(row.get('breakdown_reason')),esc(row.get('status_label')), ('N/A' if row.get('downtime_hours') is None else f"{row['downtime_hours']:.2f} h"), esc(row.get('timestamp_review') or row.get('review_reason'))]
        if add_action:
            cells.append(f'<button class="btn btn-default btn-xs tmm-action-for-record" data-reference="{esc(row["name"])}">Add action</button>')
        rows.append('<tr>'+''.join('<td>'+value+'</td>' for value in cells)+'</tr>')
    headers=['Failure Classification','Machine','Breakdown Reference','Reported Date','Description','Status (current)','Adjusted downtime','Review']+([''] if add_action else [])
    cols='<colgroup>'+''.join('<col style="width:'+width+'">' for width in ['16%','11%','17%','15%','27%','14%'])+'</colgroup>' if not add_action else ''
    return '<table class="tmm-breakdowns">'+'<thead><tr>'+''.join('<th>'+x+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


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
                cells.extend([esc(row['category']),f"{row.get('hours', row['count']):.2f}",'Yes' if row['priority'] else ''] if row else ['','',''])
            full_rows.append('<tr>'+''.join('<td>'+value+'</td>' for value in cells)+'</tr>')
        cols='<colgroup>'+''.join('<col style="width:'+width+'">' for width in ['30%','8%','12%']*2)+'</colgroup>'
        category_table='<table class="tmm-category-counts">'+cols+'<thead><tr><th>Category — full breakdown</th><th>Hours</th><th>80% set</th><th>Category — continued</th><th>Hours</th><th>80% set</th></tr></thead><tbody>'+''.join(full_rows)+'</tbody></table>'
        actions=[]
        for action in group['actions']:
            actions.append('<tr>'+''.join(f'<td>{esc(action.get(k))}</td>' for k in ('cause','action','owner_name','due_date','status','breakdown_reference'))+'</tr>')
        action_table='<table><thead><tr><th>Category</th><th>Action</th><th>Owner</th><th>Due</th><th>Status</th><th>Breakdown Reference</th></tr></thead><tbody>'+''.join(actions)+'</tbody></table>' if actions else '<p class="text-muted">No saved corrective actions.</p>'
        omitted=f"Top 10 shown; {counts['omitted_categories']} categories / {counts.get('omitted_hours',0):.2f} hours omitted from chart (included in the denominator and full breakdown below)." if counts['omitted_categories'] else 'All categories with records are shown.'
        sections.append(f'<section class="group-detail"><h2>{esc(group["group"])} · Breakdown downtime by classification</h2><p>{esc(data["population"])} · {esc(data["month_label"])}</p>{count_chart_image(counts)}<p>{esc(count_summary(counts))}</p><p>{esc(completeness(counts))}</p><p>{esc(omitted)}</p>{category_table}<h3>Breakdowns contributing to the first 80%</h3>{record_table(counts["priority_records"],data.get("base_url",""))}<h3>Unresolved categorisation — review</h3>{record_table(counts["unresolved_records"],data.get("base_url",""))}<h3>Corrective actions · {esc(group["group"])}</h3>{action_table}</section>')
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
    <p class="text-muted">Stored A&amp;U hours: 85 × SUM(available hours) / SUM(required hours), once only. No dashboard fleet or ownership filters. N/A means no valid required-hour data.</p>
    {''.join(sections)}</body></html>'''


def _period(value=None):
    try:
        return reporting_period(value, today=getdate(nowdate()))
    except (ValueError, TypeError) as exc:
        frappe.throw(str(exc))


def _scope(site, month, group=GROUPS[0], permission='read'):
    if not site or group not in ACTION_GROUPS:
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
    for doctype in (PBM, 'Availability and Utilisation', 'Asset', 'Monthly Production Planning'):
        if not frappe.has_permission(doctype, 'read'):
            frappe.throw(f'No read access to {doctype}.', frappe.PermissionError)


def _complete_records(doctype, **query):
    """Permission-filtered rows; fail closed instead of showing partial totals."""
    rows = frappe.get_list(doctype, **query, limit=0)
    ids = set(frappe.get_all(doctype, filters=query.get('filters'),
                            or_filters=query.get('or_filters'), pluck='name', limit=0))
    if {r['name'] for r in rows} != ids:
        frappe.throw(f'Your read access does not cover all {doctype} records needed for this site report.',
                     frappe.PermissionError)
    return rows


def resolve_mpp_periods(plans, months):
    """End-date month labels; identical plans are flagged and never multiply rows.

    Distinct intervals with the same label, inverted dates, and overlaps with any
    another supplied interval for this site are conflicts. Missing plans stay missing.
    """
    buckets = defaultdict(list)
    intervals = set()
    for plan in plans:
        if plan.get('docstatus') == 2:
            continue
        end = plan.get('prod_month_end_date')
        if not end:
            continue
        end = getdate(end)
        start = getdate(plan['prod_month_start_date']) if plan.get('prod_month_start_date') else None
        buckets[end.strftime('%Y-%m')].append((start, end, plan.get('name')))
        if start and start <= end:
            intervals.add((start, end))
    result = []
    for month in months:
        item = dict(month, start=None, end=None, status='missing', plan_names=[], warnings=[])
        candidates = buckets[month['key'][:7]]
        if candidates:
            unique = {(a,b) for a,b,_ in candidates}
            item['plan_names'] = sorted(str(n) for _,_,n in candidates)
            if len(unique) != 1 or any(not a or a > b for a,b,_ in candidates):
                item['status'] = 'conflict'
            else:
                start,end = next(iter(unique))
                if any((a,b) != (start,end) and a <= end and b >= start for a,b in intervals):
                    item['status'] = 'conflict'
                else:
                    item.update(start=start.isoformat(), end=end.isoformat(), status='ok')
                    if len(candidates)>1:
                        item['warnings'].append(f"{month['label']}: {len(candidates)} duplicate MPP plans share one period; shifts counted once.")
        item['dates_label'] = (f"{getdate(item['start']).strftime('%d %b %Y')} – {getdate(item['end']).strftime('%d %b %Y')}"
                               if item['status']=='ok' else f"MPP planning {item['status']}")
        result.append(item)
    return result


def _mpp_periods(site, period):
    plans = _complete_records('Monthly Production Planning',
        filters={'location':site,'docstatus':['<',2]},
        fields=['name','prod_month_start_date','prod_month_end_date','docstatus'])
    return resolve_mpp_periods(plans, period['months'])


def availability_by_group(rows):
    """Approved stored-hour ratio, scaled exactly once; no fleet/ownership cap."""
    totals = {g:[Decimal(0),Decimal(0),False] for g in GROUPS}
    seen = set()
    for row in rows:
        if row.get('docstatus') == 2 or row.get('invalid_pre_use_hours') == 1:
            continue
        if row.get('name'):
            if row['name'] in seen:
                continue
            seen.add(row['name'])
        group = equipment_group(row.get('asset_category'))
        if not group:
            continue
        required,available,present = totals[group]
        required += Decimal(str(row.get('shift_required_hours') or 0))
        if row.get('shift_available_hours') is not None:
            available += Decimal(str(row['shift_available_hours']))
            present = True
        totals[group] = [required,available,present]
    return {g:float(Decimal(85)*a/r) if r and present else None for g,(r,a,present) in totals.items()}


def _shift_rows(site, month):
    # One resolved date interval is equivalent to a site/date EXISTS join with
    # MPP, avoiding duplicate shifts even when duplicate plans exist.
    return _complete_records('Availability and Utilisation',
        filters={'location':site,'shift_date':['between',[month['start'],month['end']]],'docstatus':['<',2]},
        fields=['name','asset_category','shift_required_hours','shift_available_hours',
                'invalid_pre_use_hours','docstatus'])


def planning_downtime(site, record, start, end):
    """Existing Month End / Engine MPP-required overlap, at its minute precision."""
    from engineering.engineering.report.availability_and_utilisation_month_end_report import availability_and_utilisation_month_end_report as month_end
    measured = month_end.get_required_downtime_minutes_for_breakdown(
        frappe._dict(location=site), record.get('asset_name'), start, end)
    return measured['required_downtime_minutes'] / 60.0


def measure_records(records, period_start, period_end, current_time, measure):
    """Distinct PBMs, current TMM midnight MPP boundaries, never future hours.

    Invalid timestamps remain review rows with unknown hours (None), never 0.
    A&U-excluded, cancelled and Planned Maintenance events do not contribute.
    """
    start = datetime.combine(getdate(period_start), time.min)
    end = min(datetime.combine(getdate(period_end) + timedelta(days=1), time.min), current_time)
    result, seen = [], set()
    for source in records:
        name = source.get('name')
        if not name or name in seen:
            continue
        seen.add(name)
        if source.get('docstatus') == 2 or source.get('exclude_from_au') or str(source.get('downtime_type') or '').strip() not in ('', 'Breakdown'):
            continue
        row = dict(source, downtime_hours=None, timestamp_review='', elapsed_overlap_hours=None)
        row['status_label'] = 'Closed (current)' if row.get('resolved_datetime') else 'Open (current)'
        try:
            a = datetime.fromisoformat(str(row.get('breakdown_start_datetime')))
            b = datetime.fromisoformat(str(row['resolved_datetime'])) if row.get('resolved_datetime') else end
            if a.tzinfo or b.tzinfo:
                raise ValueError('Expected site-local timestamps')
            if a >= end:
                continue
            if b < a:
                raise ValueError('Resolved timestamp precedes start')
        except (ValueError, TypeError) as exc:
            row['timestamp_review'] = 'Invalid or missing timestamp: ' + str(exc)
            result.append(row)
            continue
        if a >= end or b < start or (a < start and b <= start):
            continue
        a, b = max(a, start), min(b, end)
        row['elapsed_overlap_hours'] = max(0, (b-a).total_seconds()/3600)
        row['downtime_hours'] = measure(row, a, b) if b > a else 0.0
        if not math.isfinite(row['downtime_hours']) or row['downtime_hours'] < 0:
            raise ValueError('Invalid planning-adjusted downtime result')
        result.append(row)
    return result


def category_downtime(records, classifications, configured):
    unique = {r['name']: dict(r) for r in records if r.get('docstatus') != 2}
    # Retain event counts for supporting details, while percentages use hours only.
    result = category_counts(list(unique.values()), classifications)
    grouped = {c: [] for c in classifications}
    for row in unique.values():
        row.update(standard_subcategory(row.get('breakdown_reason'), row.get('failure_classification'), configured))
        if row.get('failure_classification') in grouped:
            grouped[row['failure_classification']].append(row)
    categories = []
    invalid = [r for r in unique.values() if r.get('timestamp_review')]
    for category, rows in grouped.items():
        hours = sum(r.get('downtime_hours') or 0 for r in rows)
        subs = defaultdict(list)
        review = []
        for row in rows:
            if row['subcategory'] and not row.get('timestamp_review'):
                subs[row['subcategory']].append(row)
            else:
                review.append(row)
        ranked = sorted((dict(subcategory=label, count=len(items), hours=sum(r.get('downtime_hours') or 0 for r in items)) for label, items in subs.items()), key=lambda r: (-r['count'], r['subcategory'].casefold()))
        categories.append(dict(category=category, count=len(rows), records=rows, hours=hours,
            subcategories=ranked[:3], subcategory_review_records=review,
            subcategory_review_hours=sum(r.get('downtime_hours') or 0 for r in review)))
    positive = sorted((r for r in categories if r['hours'] > 0), key=lambda r: (-r['hours'], classifications.index(r['category'])))
    total = sum(r['hours'] for r in positive)
    running, priority_records = 0.0, []
    for index, row in enumerate(positive):
        row['priority'] = running < total*.8 - 1e-10
        running += row['hours']
        row['cumulative_percent'] = 100.0 if index == len(positive)-1 else running/total*100
        if row['priority']:
            priority_records.extend(row['records'])
    for row in categories:
        if row['hours'] <= 0:
            row.update(priority=False, cumulative_percent=100 if total else 0)
    unresolved = [r for r in unique.values() if r.get('failure_classification') not in grouped]
    result.update(categories=positive, all_categories=positive+[r for r in categories if r['hours']<=0],
        classified_hours=total, unresolved_hours=sum(r.get('downtime_hours') or 0 for r in unresolved),
        unresolved_records=unresolved, invalid_records=invalid, priority_records=priority_records,
        priority_category_count=sum(r['priority'] for r in positive),
        priority_percent=sum(r['hours'] for r in positive if r['priority'])/total*100 if total else 0,
        displayed_count=min(len(positive),10), omitted_categories=max(0,len(positive)-10),
        omitted_count=sum(r['count'] for r in positive[10:]), omitted_hours=sum(r['hours'] for r in positive[10:]))
    return result


def _subcategory_configuration():
    settings = frappe.get_single('Machine Reliability Settings')
    return {r.category: terms(r.keywords) for r in settings.categories if r.category}


def breakdown_counts_by_group(site, month, period_end):
    # Read the permitted site's records, including invalid/missing timestamps for
    # review; measure_records enforces the exact reporting overlap once per PBM.
    rows = _complete_records(PBM, filters={'location':site,'docstatus':['<',2]},
        fields=['name','asset_name','asset_category','breakdown_start_datetime','resolved_datetime',
                'failure_classification','downtime_type','breakdown_reason','exclude_from_au','docstatus'],
        order_by='breakdown_start_datetime asc, name asc')
    rows = measure_records(rows, month, period_end, now_datetime(),
        lambda record, a, b: planning_downtime(site, record, a, b))
    identifiers = list({r.get('asset_name') for r in rows if r.get('asset_name')})
    assets = frappe.get_list('Asset', or_filters=[['name','in',identifiers],['asset_name','in',identifiers]],
        fields=['name','asset_name','asset_category'], limit=0) if identifiers else []
    fallback = {str(key).strip(): a.asset_category for a in assets for key in (a.name,a.asset_name) if key}
    grouped, unassigned = {g: [] for g in GROUPS}, []
    for row in rows:
        group = equipment_group(row.get('asset_category') or fallback.get(str(row.get('asset_name') or '').strip()))
        if group:
            grouped[group].append(row)
        else:
            row['review_reason'] = 'Missing or unsupported equipment group'
            unassigned.append(row)
    configured = _subcategory_configuration()
    choices = classification_names()
    return {g: category_downtime(records, choices, configured) for g, records in grouped.items()}, unassigned


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
    period['months'] = _mpp_periods(site, period)
    selected = period['months'][-1]
    if selected['status'] != 'ok':
        frappe.throw(f"{site}: {selected['label']} MPP planning is {selected['status']}. No calendar-period substitution is allowed.")
    period['selected_period'] = selected
    warnings = []
    unsupported = []
    monthly = []
    for month in period['months']:
        warnings.extend(month['warnings'])
        if month['status'] != 'ok':
            warnings.append(f"{month['label']}: MPP planning {month['status']}; availability is N/A.")
            monthly.append({g:None for g in GROUPS})
            continue
        rows = _shift_rows(site, month)
        monthly.append(availability_by_group(rows))
        unknown = sorted({str(r.get('asset_category') or '(blank)') for r in rows
                          if r.get('docstatus')!=2 and r.get('invalid_pre_use_hours')!=1
                          and not equipment_group(r.get('asset_category'))})
        if unknown:
            unsupported.append(dict(month=month['label'],categories=unknown))
            warnings.append(f"{month['label']}: unsupported availability categories: {', '.join(unknown)}.")
    counts, unassigned = breakdown_counts_by_group(site, selected['start'], selected['end'])
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
    legacy_scope = _scope(site, period['reporting_month'], 'Ancillary')
    legacy = _saved(legacy_scope)
    if legacy['actions']:
        empty = category_downtime([], classification_names(), {})
        groups.append(dict(group='Ancillary', availability=[None]*3, counts=empty, pareto=[], chart='', full_chart='', summary='Historical combined Ancillary actions; availability is now split by equipment category.', can_write=bool(legacy_scope.has_permission('write')), **legacy))
    result = dict(site=site, **period, groups=groups, basis=BASIS, warnings=warnings, unsupported_categories=unsupported)
    result.update(availability_chart=availability_svg(result), failure_classifications=classification_names(),
                  population='Planning-adjusted breakdown downtime overlapping the MPP period; distinct PBM records, including carried-in and repaired/closed events',
                  counting_unit='Required downtime minutes from A&U/Month End divided by 60; one clipped contribution per PBM',
                  status_basis='Current status shown; open and repaired/closed events are included when their recorded interval overlaps the MPP period',
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

def presentation_bytes(data):
    """Editable prime/support availability and three downtime Paretos.

    Priority subcategory detail uses continuation slides, never raw PBM records.
    All source values are the same authorised period totals used on the Page.
    """
    from copy import deepcopy
    from pathlib import Path
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.chart.datalabel import DataLabels
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
    from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.util import Inches, Pt

    prs = Presentation(Path(__file__).with_name('monthly_tmm_template.pptx'))
    for node in list(prs.slides._sldIdLst):
        prs.part.drop_rel(node.rId)
        prs.slides._sldIdLst.remove(node)
    navy, blue, orange = '19324F', '3293FF', 'ED8B00'
    palette = ('234F87','3293FF','9AD0FF')
    selected = data['selected_period']
    caption = f"{data['site']} · {data['month_label']} · {selected['dates_label']}"

    def text(slide, value, x, y, w, h, size=16, color=navy, bold=False):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        shape.text_frame.word_wrap = True
        for index, line in enumerate(str(value).split('\n')):
            paragraph = shape.text_frame.paragraphs[0] if index == 0 else shape.text_frame.add_paragraph()
            paragraph.text = line
            paragraph.font.name = 'Arial'
            paragraph.font.size = Pt(size)
            paragraph.font.bold = bold
            paragraph.font.color.rgb = RGBColor.from_string(color)
        return shape

    def slide(title):
        result = prs.slides.add_slide(prs.slide_layouts[6])
        for shape in list(result.shapes):
            shape._element.getparent().remove(shape._element)
        result.background.fill.solid()
        result.background.fill.fore_color.rgb = RGBColor(255,255,255)
        band = result.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE,0,0,prs.slide_width,Inches(.85))
        band.fill.solid();band.fill.fore_color.rgb = RGBColor.from_string(navy)
        band.line.fill.background()
        heading = text(result,title,.45,.12,12.4,.65,28,'FFFFFF',True)
        heading.name = 'tmm-title'
        text(result,caption,.45,.92,12.4,.55,15)
        text(result,f"Monthly TMM Assurance · Due {data['due_date']} · {len(prs.slides)}",.45,7.06,12.4,.3,11)
        return result

    def style(chart):
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(12)
        chart.category_axis.tick_labels.font.size = Pt(12)
        chart.value_axis.tick_labels.font.size = Pt(12)
        chart.value_axis.minimum_scale = 0
        chart.value_axis.has_title = True
        chart.chart_style = 10
        chart.plots[0].gap_width = 55

    by_group = {g['group']:g for g in data['groups']}
    for title, names in [
        ('Prime movers availability', ('ADTs','Excavators','Dozers','Drills')),
        ('Support equipment availability', ('Diesel bowsers','Water bowsers','TLBs','Service trucks')),
    ]:
        page = slide(title)
        cd = CategoryChartData();cd.categories = names
        for index, month in enumerate(data['months']):
            cd.add_series(month['label'],[by_group[name]['availability'][index] for name in names])
        chart = page.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,Inches(.5),Inches(1.65),Inches(12.3),Inches(3.85),cd).chart
        style(chart)
        chart.value_axis.axis_title.text_frame.text = 'Availability (%) — 85% basis'
        maximum = max((v for name in names for v in by_group[name]['availability'] if v is not None),default=100)
        chart.value_axis.maximum_scale = max(100,math.ceil(maximum/20)*20)
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.number_format = '0.00"%"'
        chart.plots[0].data_labels.font.size = Pt(12)
        chart.plots[0].data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
        for index, series in enumerate(chart.series):
            series.format.fill.solid();series.format.fill.fore_color.rgb = RGBColor.from_string(palette[index])
            series.format.line.fill.background()
        text(page,'\n'.join(f"{m['label']}: {m['dates_label']}" for m in data['months']),.55,5.65,12.2,.9,15)
        missing = [f"{m['label']}: "+', '.join(n for n in names if by_group[n]['availability'][i] is None)
                   for i,m in enumerate(data['months']) if any(by_group[n]['availability'][i] is None for n in names)]
        text(page,'85 × Σ stored available hours / Σ stored required hours. N/A = no valid denominator; blank bars are N/A.',.55,6.56,12.2,.4,12)
        # Four groups × three months fit as native editable text in a dedicated
        # continuation if missing-data notes exceed the available caption area.

    def element(tag, **attrs):
        node = OxmlElement('c:'+tag)
        for key,value in attrs.items():node.set(key,str(value))
        return node

    for group,title in [('ADTs','ADT Pareto'),('Excavators','Excavator Pareto'),('Dozers','Dozer Pareto')]:
        page = slide(title)
        counts = by_group[group]['counts']
        rows = counts['categories'][:10]
        if rows:
            cd = CategoryChartData()
            cd.categories = ['\n'.join(textwrap.wrap(r['category'],width=18,break_long_words=False)) for r in rows]
            cd.add_series('Breakdown downtime (hours)',[r['hours'] for r in rows])
            cd.add_series('Cumulative percentage',[r['cumulative_percent'] for r in rows])
            cd.add_series('80% reference',[80]*len(rows))
            chart = page.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,Inches(.45),Inches(1.6),Inches(12.4),Inches(4.2),cd).chart
            style(chart)
            chart.category_axis.tick_labels.font.size = Pt(11)
            chart.value_axis.axis_title.text_frame.text = 'Breakdown downtime (hours)'
            chart.value_axis.maximum_scale = max(1,max(r['hours'] for r in rows)*1.25)
            plot = chart.plots[0]
            plot.has_data_labels = True
            plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
            plot.data_labels.font.size = Pt(12)
            labels = DataLabels(chart.series[0]._element.get_or_add_dLbls())
            labels.show_value = True;labels.number_format = '0.00'
            labels.show_category_name = False;labels.show_series_name = False
            for index,row in enumerate(rows):
                point = chart.series[0].points[index]
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = RGBColor.from_string(blue if row['priority'] else '9AB7D8')
                point.format.line.fill.background()
            space=chart._chartSpace
            area=space.xpath('.//c:plotArea')[0]
            bars=area.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}barChart')
            lines=element('lineChart');lines.append(element('grouping',val='standard'))
            series=list(bars.findall('{http://schemas.openxmlformats.org/drawingml/2006/chart}ser'))
            for index,ser in enumerate(series[1:]):
                bars.remove(ser);lines.append(ser)
                # Native line styling; reference line remains dashed without labels.
                sp=OxmlElement('c:spPr');ln=OxmlElement('a:ln');ln.set('w','25400')
                fill=OxmlElement('a:solidFill');color=OxmlElement('a:srgbClr')
                color.set('val',orange if index==0 else '9B8B70');fill.append(color);ln.append(fill)
                if index==1:
                    dash=OxmlElement('a:prstDash');dash.set('val','dash');ln.append(dash)
                sp.append(ln)
                ser.insert(3,sp)
                marker=element('marker');marker.append(element('symbol',val='circle' if index==0 else 'none'))
                if index==0:marker.append(element('size',val=5))
                # spPr/marker precede category/value references in CT_LineSer.
                ser.insert(4,marker)
                if index==0:
                    labels=element('dLbls');labels.append(element('numFmt',formatCode='0.0"%"',sourceLinked=0))
                    labels.append(element('dLblPos',val='t'))
                    for flag,value in [('showLegendKey',0),('showVal',1),('showCatName',0),('showSerName',0),('showPercent',0),('showBubbleSize',0)]:
                        labels.append(element(flag,val=value))
                    DataLabels(labels).font.size=Pt(11)
                    ser.insert(5,labels)
            cat=area.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}catAx')
            val=area.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}valAx')
            cat_id=int(cat.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}axId').get('val'))+10
            val_id=int(val.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}axId').get('val'))+10
            lines.append(element('axId',val=cat_id));lines.append(element('axId',val=val_id))
            # Chart-type nodes must precede axes in OOXML.
            area.insert(list(area).index(cat),lines)
            secondary_cat=deepcopy(cat)
            secondary_cat.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}axId').set('val',str(cat_id))
            secondary_cat.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}crossAx').set('val',str(val_id))
            deleted=secondary_cat.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}delete')
            if deleted is None:secondary_cat.insert(2,element('delete',val=1))
            else:deleted.set('val','1')
            area.append(secondary_cat)
            secondary_val=element('valAx');secondary_val.append(element('axId',val=val_id))
            scaling=element('scaling');scaling.extend([element('orientation',val='minMax'),element('max',val=100),element('min',val=0)])
            secondary_val.extend([scaling,element('delete',val=0),element('axPos',val='r'),
                element('numFmt',formatCode='0"%"',sourceLinked=0),element('majorTickMark',val='none'),
                element('minorTickMark',val='none'),element('tickLblPos',val='nextTo'),
                element('crossAx',val=cat_id),element('crosses',val='max'),element('crossBetween',val='between'),element('majorUnit',val=20)])
            area.append(secondary_val)
        else:
            text(page,'No classified planning-adjusted breakdown downtime for this group in the selected MPP period.',.7,2.3,11.9,1.3,24)
        text(page,count_summary(counts),.55,5.95,12.2,.45,16,bold=True)
        text(page,f"Top 10 shown; percentages use all {counts['classified_hours']:.2f} classified hours. Blue: first 80% set; grey: remaining. Dashed line: 80%.",.55,6.43,12.2,.4,12)
        text(page,f"Classification review: {counts['unresolved_hours']:.2f} h (excluded); invalid timestamp records: {len(counts['invalid_records'])} — review in ERP.",.55,6.78,12.2,.3,12)
        priority = [row for row in counts['categories'] if row['priority']]
        for offset in range(0,len(priority),2):
            detail = slide(title+' · priority detail continued')
            text(detail,'Top matched subcategories ranked by distinct event frequency; hours use the same MPP overlap.',.55,1.55,12.1,.5,16)
            for index,row in enumerate(priority[offset:offset+2]):
                y = 2.0 + index*2.5
                text(detail,f"{row['category']} — {row['hours']:.2f} h · cumulative {row['cumulative_percent']:.1f}%",.6,y,12.0,.55,19,bold=True)
                table_rows = row['subcategories']
                if table_rows:
                    table = detail.shapes.add_table(len(table_rows)+1,3,Inches(.65),Inches(y+.6),Inches(11.9),Inches(.38*(len(table_rows)+1))).table
                    table.columns[0].width = Inches(7.5)
                    table.columns[1].width = Inches(1.8)
                    table.columns[2].width = Inches(2.6)
                    values = [('Subcategory','Events','Downtime (h)')]+[(r['subcategory'],str(r['count']),f"{r['hours']:.2f}") for r in table_rows]
                    for ri,values_row in enumerate(values):
                        for ci,value in enumerate(values_row):
                            cell = table.cell(ri,ci);cell.text = value
                            for paragraph in cell.text_frame.paragraphs:paragraph.font.size = Pt(15)
                else:
                    text(detail,'No approved component matches.',.65,y+.6,11.9,.45,16)
                text(detail,f"Description/timestamp review: {len(row['subcategory_review_records'])} events · {row['subcategory_review_hours']:.2f} known hours. Details remain in ERP.",.65,y+2.2,11.9,.25,11)
    output = BytesIO();prs.save(output)
    return output.getvalue()


@frappe.whitelist()
def download_presentation(site, reporting_month):
    data=get_report(site, reporting_month)
    for group in data['groups']:
        _scope(site,data['reporting_month'],group['group']).check_permission('print')
    frappe.local.response.filename=f"Monthly TMM Assurance {site} {data['reporting_month'][:7]}.pptx"
    frappe.local.response.filecontent=presentation_bytes(data)
    frappe.local.response.type='download'
    frappe.local.response.content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation'
