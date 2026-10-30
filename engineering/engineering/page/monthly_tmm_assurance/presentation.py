"""Shared, script-free SVG charts and printable record tables."""
import base64
from html import escape
import math
import textwrap
from urllib.parse import quote


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
        category=row.get('problem_category') or 'Missing category'
        cells=[esc(category),esc(row.get('asset_name')),f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(row["name"])}</a>',
               esc(row.get('breakdown_start_datetime')),esc(row.get('breakdown_reason')),esc(row.get('status_label'))]
        if add_action:
            cells.append(f'<button class="btn btn-default btn-xs tmm-action-for-record" data-reference="{esc(row["name"])}">Add action</button>')
        rows.append('<tr>'+''.join('<td>'+value+'</td>' for value in cells)+'</tr>')
    headers=['Category','Machine','Breakdown Reference','Reported Date','Description','Status (current)']+([''] if add_action else [])
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
