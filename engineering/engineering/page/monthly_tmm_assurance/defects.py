"""Count and prioritise an already authorised, confirmed record population.

Population selection is deliberately separate from these deterministic helpers.
One count is one stable Plant Breakdown or Maintenance record identity, not an
individual fault in its description or a shift/day/history entry.
"""
from engineering.engineering.problem_categories import PROBLEM_CATEGORIES


def category_counts(records):
    by_name = {}
    for record in records:
        if record.get('docstatus') == 2:
            continue
        if not record.get('name'):
            raise ValueError('A stable breakdown reference is required for counting.')
        by_name.setdefault(record['name'], dict(record))
    grouped = {category: [] for category in PROBLEM_CATEGORIES}
    unresolved = []
    for record in by_name.values():
        category = record.get('problem_category')
        if category in grouped:
            grouped[category].append(record)
        else:
            record['review_reason'] = 'Missing category' if not category else f'Unsupported legacy category: {category}'
            unresolved.append(record)
    categories = sorted((dict(category=c, count=len(rows), records=rows) for c, rows in grouped.items() if rows),
                        key=lambda row: (-row['count'], PROBLEM_CATEGORIES.index(row['category'])))
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
    full = categories + [dict(category=c, count=0, records=[], priority=False, cumulative_percent=100 if total else 0) for c in PROBLEM_CATEGORIES if not grouped[c]]
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
    from datetime import date, datetime, time
    from .calculations import month_offset
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
