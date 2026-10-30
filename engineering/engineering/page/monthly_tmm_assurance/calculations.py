"""Month boundaries, equipment presentation and non-overlapping cause intervals."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
import re

GROUPS = ('ADTs', 'Excavators', 'Drills', 'Graders', 'FELs', 'Dozers', 'Ancillary')
CATEGORY_GROUPS = {'ADT': 'ADTs', 'Excavator': 'Excavators', 'Drills': 'Drills',
                   'Grader': 'Graders', 'Loader': 'FELs', 'Dozer': 'Dozers',
                   'Service Truck': 'Ancillary', 'TLB': 'Ancillary',
                   'Water Bowser': 'Ancillary', 'Diesel Bowsers': 'Ancillary'}
BASIS = '85% A & U'
MACHINE_SCOPE = 'Production + Swing/Spare Machines'
OWNERSHIP = 'Isambane & Excavo Assets'


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
            by_asset[str(row['asset_name']).strip()].append((a, b, str(row.get('problem_category') or '').strip() or 'Uncategorised'))
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
