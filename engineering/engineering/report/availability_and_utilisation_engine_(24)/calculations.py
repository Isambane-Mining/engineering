"""Confirmed formula arithmetic. Report percentage fields contain decimal ratios.

Industry uses raw elapsed PBM and a fixed 24-hour utilisation denominator.
Isambane's actual shift inputs/aggregation come from the unchanged original Engine.
Time-window helpers remain shared with the separate configuration validator.
"""
from datetime import datetime, time

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
