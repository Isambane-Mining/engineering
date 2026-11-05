"""Page defaults and permission-checked PBM drill-down for ADT availability."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_datetime, getdate
from is_production.production.page.hourly_productivity_analysis import hourly_productivity_analysis as analysis
from is_production.production.page.hourly_productivity_summary import hourly_productivity_summary as summary
from engineering.engineering.page.adt_hourly_productivity.adt_hourly_productivity import _unavailable_seconds


@frappe.whitelist()
def get_defaults():
    """Use the Johannesburg calendar date, including today's pending hours."""
    today = datetime.now(ZoneInfo('Africa/Johannesburg')).date()
    return {'from_date': today.replace(day=1).isoformat(), 'to_date': today.isoformat()}


@frappe.whitelist()
def get_hour_breakdowns(site, date, hour, machine_scope='all'):
    """Hour is an operational-day index: 0=06:00, 18=next-day midnight.

    Only accessible historical MPP ADTs are queried. No production documents
    are loaded; counts stay with the existing matrix calculation API.
    """
    if frappe.session.user == 'Guest':
        raise frappe.PermissionError('Login required')
    if str(hour) not in {str(n) for n in range(24)}:
        raise ValueError('Hour must be an operational hour index from 0 to 23')
    if machine_scope not in ('all', 'production', 'spare'):
        raise ValueError('Invalid machine scope')
    if not site or not date:
        raise ValueError('Select Site and Date')
    day = getdate(date)
    plans = analysis.load_plans(site, day, day)
    plan = summary.select_plan(plans or [], site, day)
    if not plan:
        raise frappe.PermissionError('No accessible production plan for this date')
    for doctype in ('Asset', 'Plant Breakdown or Maintenance'):
        frappe.has_permission(doctype, 'read', throw=True)
    start = datetime.combine(day, time(6)) + timedelta(hours=int(hour))
    end = start + timedelta(hours=1)
    scope = analysis.mpp_adt_scope(plan, machine_scope)
    assets = []
    if scope:
        for row in summary._permitted_rows('Asset', {'name': ['in', sorted(scope)], 'asset_category': 'ADT'}):
            try:
                asset = summary._read_document('Asset', row.name)
            except frappe.PermissionError:
                continue
            if asset['name'] in scope and asset.get('asset_category') == 'ADT':
                assets.append(asset)
    # PBM.asset_name is a Link to Asset: labels must never widen the MPP scope.
    asset_by_name = {asset['name']: asset for asset in assets}
    groups = {}
    seen = set()
    if asset_by_name:
        records = summary._permitted_rows('Plant Breakdown or Maintenance', {
            'location': site, 'asset_name': ['in', sorted(asset_by_name)], 'docstatus': ['<', 2],
            'exclude_from_au': 0, 'breakdown_reason': ['!=', ''],
            'breakdown_start_datetime': ['<', end],
        }, or_filters=[['resolved_datetime', '>', start], ['resolved_datetime', 'is', 'not set']])
        for record in records:
            if record.name in seen:
                continue
            seen.add(record.name)
            try:
                row = summary._read_document('Plant Breakdown or Maintenance', record.name)
            except frappe.PermissionError:
                continue
            asset = asset_by_name.get(row.get('asset_name'))
            if (not asset or row.get('location') != site or row.get('docstatus', 0) >= 2
                    or row.get('exclude_from_au') or not row.get('breakdown_reason')
                    or not row.get('breakdown_start_datetime')):
                continue
            left = get_datetime(row['breakdown_start_datetime'])
            resolved = get_datetime(row['resolved_datetime']) if row.get('resolved_datetime') else None
            right = resolved or end
            overlap = (min(right, end) - max(left, start)).total_seconds()
            if overlap <= 0:
                continue
            group = groups.setdefault(asset['name'], {
                'machine_number': asset.get('asset_name') or asset['name'], 'breakdowns': [], 'intervals': []})
            group['intervals'].append((left, right))
            group['breakdowns'].append({
                # Values come from the field-permission-stripped document, including classification.
                'failure_classification': row.get('failure_classification'),
                'description': row.get('breakdown_reason'),
                'breakdown_start_datetime': str(left),
                'resolved_datetime': str(resolved) if resolved else None,
                'overlap_minutes': overlap / 60,
            })
    for group in groups.values():
        group['downtime_minutes'] = _unavailable_seconds(group.pop('intervals'), start, end) / 60
        group['breakdowns'].sort(key=lambda row: (row['breakdown_start_datetime'], row['description'] or ''))
    return {'start': str(start), 'end': str(end),
            'machines': sorted(groups.values(), key=lambda row: row['machine_number'])}
