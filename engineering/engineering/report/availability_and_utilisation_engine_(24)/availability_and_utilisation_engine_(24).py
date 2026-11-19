"""Permission-aware sources and presentation for the independent 24-hour report."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from html import escape

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, now_datetime

from engineering.engineering.machine_exclusions import is_pre_use_au_excluded
from engineering.engineering.doctype.availability_and_utilisation.availability_and_utilisation import get_shift_timings
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
    f.isambane_basis = f.get('isambane_basis') or '100% A & U'
    if f.isambane_basis not in ISAMBANE_BASES:
        frappe.throw(_('Choose 85% A & U or 100% A & U.'))
    f.asset_ownership = f.asset_ownership or 'Isambane & Excavo Assets'
    if f.asset_ownership not in ('Isambane & Excavo Assets', 'Supplier Assets', 'All Assets'):
        frappe.throw(_('Invalid asset ownership.'))
    f.machine_scope = f.get('machine_scope') or 'All Machines'
    if f.machine_scope not in ('All Machines', 'Production Machines', 'Spare Machines'):
        frappe.throw(_('Invalid machine filter.'))
    for key in ('sites', 'assets', 'companies'):
        f[key] = sources.parse_multiselect(f.get(key))
    return f


def permitted_sites(selected=()):
    filters = {'name': ['in', selected]} if selected else {}
    sites = frappe.get_list('Location', filters=filters, pluck='name', limit_page_length=0)
    if set(selected) - set(sites):
        frappe.throw(_('One or more selected sites are unavailable or not permitted.'), frappe.PermissionError)
    return sites


def filter_assets_by_scope(assets, spare_assets, machine_scope):
    """Use the original Engine's Asset ID and fleet-number spare classification."""
    spare_assets = {str(value).strip() for value in spare_assets if value}

    if machine_scope == "All Machines":
        return list(assets)

    def is_spare(asset):
        identifiers = {
            str(getattr(asset, "name", "") or "").strip(),
            str(getattr(asset, "asset_name", "") or "").strip(),
        }
        return bool(identifiers & spare_assets)

    if machine_scope == "Spare Machines":
        return [asset for asset in assets if is_spare(asset)]

    return [asset for asset in assets if not is_spare(asset)]


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

    if f.machine_scope != "All Machines":
        spare_assets = sources.get_spare_swing_assets(
            f.from_date, f.to_date, sites
        )
        assets = filter_assets_by_scope(
            assets, spare_assets, f.machine_scope
        )

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
    """Industry calculations are performed independently per scheduled shift."""
    warnings = set()
    downtime = defaultdict(list)
    clock = now_datetime()

    for row in pbm:
        start = get_datetime(row.breakdown_start_datetime)
        end = get_datetime(row.resolved_datetime) if row.resolved_datetime else clock
        if end > start:
            downtime[(row.location, str(row.asset_name).strip())].append(
                (row.downtime_type, start, end)
            )

    shift_work = defaultdict(float)
    observed_shifts = defaultdict(set)

    for (site, day, shift, fleet), reading in preuse.items():
        observed_shifts[(site, day, fleet)].add(shift)
        first = reading.get("eng_hrs_start")
        last = reading.get("eng_hrs_end")

        if first is not None and last is not None and float(last) >= float(first):
            shift_work[(site, day, fleet, shift)] += float(last) - float(first)
        else:
            warnings.add(_("Invalid or incomplete meter readings excluded from recorded working hours."))

    shift_rows = []

    for asset in assets:
        day = f.from_date

        while day <= f.to_date:
            key = (asset.location, str(day), asset.asset_name)
            planning = days.get((asset.location, str(day)))

            if planning is not None:
                intervals = list(downtime[(asset.location, asset.asset_name)])
                if asset.name != asset.asset_name:
                    intervals.extend(downtime[(asset.location, asset.name)])

                system = planning.get("shift_system") or ""
                canonical_system = {
                    "2x12hour": "2x12Hour",
                    "3x8hour": "3x8Hour",
                }.get(system.strip().lower(), system)

                shifts = set(sources.get_shifts(system)) | observed_shifts[key]

                for shift in sorted(shifts):
                    start, end = get_shift_timings(canonical_system, shift, str(day))

                    if not start or not end or end <= start:
                        frappe.throw(_(
                            "Cannot calculate Industry shift hours for {0} on {1}. "
                            "Shift timings are unavailable for shift system {2}."
                        ).format(shift, day, system or _("not configured")))

                    working = shift_work[(asset.location, str(day), asset.asset_name, shift)]

                    def downtime_hours(kind):
                        return sum(
                            max(0, (min(last, end) - max(first, start)).total_seconds() / 3600)
                            for recorded_kind, first, last in intervals
                            if recorded_kind == kind
                        )

                    breakdown = downtime_hours("Breakdown")
                    maintenance = downtime_hours("Planned Maintenance")

                    row = calculate_shift(
                        working=working,
                        breakdown=breakdown,
                        planned_maintenance=maintenance,
                    )

                    row.update(
                        site=asset.location,
                        asset_type=asset.asset_category,
                        fleet_number=asset.asset_name,
                        shift_date=str(day),
                        shift=shift,
                        is_atomic=True,
                    )

                    if row.get("use_of_availability_inconsistent") or row.get("utilisation_inconsistent"):
                        warning = _(
                            "{0} / {1} / {2}: recorded Working Hours exceed a shift utilisation denominator. "
                            "Ratios are not capped."
                        ).format(asset.location, asset.asset_name, shift)
                        row["performance_warning"] = warning
                        warnings.add(warning)

                    shift_rows.append(row)

            day += timedelta(days=1)

    return build_report_tree(shift_rows, f.formula), sorted(warnings)

def build_isambane_rows(f):
    """Read the original Engine shifts, including its exact basis and exceptions."""
    assets, days = read_assets(f)
    if not assets:
        return build_report_tree([], 'Isambane Formula', f.isambane_basis), []
    engine_filters = frappe._dict(from_date=f.from_date, to_date=f.to_date,
        locations=sorted({a.location for a in assets}), assets=[a.name for a in assets],
        companies=f.companies, asset_ownership=f.asset_ownership,
        free_hours=0, production_machines_only=0,
        au_calculation='Isambane A&U Calculation', au_percentage_basis=f.isambane_basis)
    engine_rows = sources.get_data(engine_filters)
    allowed = {(a.location, a.asset_name) for a in assets}
    atoms = []
    for row in engine_rows:
        if row.get('indent') == 3 and (row.get('location'), row.get('asset_name')) in allowed:
            atom = engine_values(row)
            atom.update(site=row.get('location'), fleet_number=row.get('asset_name'),
                        asset_type=row.get('asset_category'), shift_date=str(row.get('shift_date')),
                        shift=row.get('shift'), is_atomic=True, engine_shift=dict(row))
            atoms.append(atom)
    warnings = []
    if any(row['engine_shift'].get('invalid_pre_use') for row in atoms):
        warnings.append(_('Original Engine Pre-Use integrity exclusions apply; invalid shifts are excluded from its summaries.'))
    return build_report_tree(atoms, 'Isambane Formula', f.isambane_basis), warnings


def engine_values(row):
    """Presentation mapping only; percentages already use the Engine's basis."""
    return dict(total_hours=row.get('required_hours'), breakdown_hours=row.get('breakdown_hours'),
        planned_maintenance_hours=row.get('planned_maintenance_hours'), working_hours=row.get('work_hours'),
        availability_available=row.get('availability_available_hours'),
        utilisation_available=row.get('utilisation_available_hours'),
        availability_percent=ratio(row.get('availability_percentage'), 100),
        utilisation_percent=ratio(row.get('utilisation_percentage'), 100))


def build_report_tree(atoms, formula="Industry Formula", isambane_basis="100% A & U"):
    """Build category/date/machine/shift tree from atomic shift records."""
    industry = formula == "Industry Formula"
    grouped = defaultdict(list)
    inputs = []

    for atom in atoms:
        category = atom.get("asset_type") or ""
        day = str(atom.get("shift_date"))
        machine = str(atom.get("fleet_number") or "") + "\\x1f" + str(atom.get("site") or "")

        for key in [(category,), (category, day), (category, day, machine)]:
            grouped[key].append(atom)

        if industry:
            inputs.append(dict(
                asset_category=category,
                shift_date=day,
                asset_name=machine,
                location=atom.get("site"),
                shift=atom.get("shift"),
                au24_atom=atom,
                indent=3,
            ))
        else:
            inputs.append(dict(atom["engine_shift"], asset_name=machine, au24_atom=atom))

    skeleton = sources.build_tree_rows(inputs)
    result = []

    for source in skeleton:
        indent = source["indent"]
        atom = source.get("au24_atom")

        if indent < 3:
            key = (source.get("asset_category") or "",)

            if indent >= 1:
                key += (str(source.get("shift_date")),)
            if indent == 2:
                key += (source.get("asset_name"),)

            children = grouped[key]

            if industry:
                row = total_row(children)
            else:
                summary = sources.build_summary_row(
                    [a["engine_shift"] for a in children], indent=indent
                )
                sources.apply_au_percentage_basis([summary], isambane_basis)
                row = engine_values(summary)

            identity = children[0]

        else:
            identity = atom
            row = dict(atom)

            if not industry:
                row["excluded_shift"] = bool(atom["engine_shift"].get("invalid_pre_use"))

        row.update(
            indent=indent,
            is_total_row=False,
            formula=formula,
            isambane_basis=isambane_basis,
            asset_type=identity.get("asset_type"),
            site=identity.get("site"),
            shift_date=identity.get("shift_date") if indent else None,
            fleet_number=identity.get("fleet_number") if indent >= 2 else None,
            is_atomic=indent == 3,
        )

        if indent == 0:
            row["asset"] = identity.get("asset_type") or _("Uncategorised")
        elif indent == 1:
            row["asset"] = str(identity.get("shift_date"))
        elif indent == 2:
            row["asset"] = identity.get("fleet_number")
            if industry:
                row["shift_details"] = [
                    {"shift": child.get("shift")} for child in children
                ]
        else:
            row["asset"] = source.get("shift") or _("Shift not recorded")
            row["shift"] = source.get("shift")

        result.append(row)

    if industry:
        bottom = total_row(atoms)
    else:
        summary = sources.build_summary_row(
            [a["engine_shift"] for a in atoms], indent=0
        )
        sources.apply_au_percentage_basis([summary], isambane_basis)
        bottom = dict(
            engine_values(summary),
            asset="Total / Average",
            is_total_row=True,
            formula=formula,
            isambane_basis=isambane_basis,
        )

    bottom["indent"] = 0
    result.append(bottom)
    return result

def get_columns(formula='Industry Formula'):
    industry = formula == 'Industry Formula'
    specifications = [('Asset', 'asset', 'Data', 120),
        ('Asset Type', 'asset_type', 'Data', 120), ('Shift Hours (h)' if industry else 'Total Hours (24h)', 'total_hours', 'Float', 135),
        ('Raw Breakdowns (h)' if industry else 'Breakdowns (h)', 'breakdown_hours', 'Float', 135),
        ('Raw Planned Maintenance (h)' if industry else 'Planned Maintenance (h)', 'planned_maintenance_hours', 'Float', 175),
        ('Working Hours (h)', 'working_hours', 'Float', 150),
        ('Availability Available (h)', 'availability_available', 'Float', 185),
        ('Availability (%)', 'availability_percent', 'Percent', 140),
        ]
    if industry:
        specifications += [
            ('Use of Availability Available Hours (h)', 'use_of_availability_available', 'Float', 200),
            ('Use of Availability (%)', 'use_of_availability_percent', 'Percent', 170),
            ('Utilisation Available (Utilisation) (h)', 'utilisation_available', 'Float', 185),
            ('Utilisation (%)', 'utilisation_percent', 'Percent', 140)]
    else:
        specifications += [('Utilisation Available (h)', 'utilisation_available', 'Float', 185),
                           ('Utilisation (%)', 'utilisation_percent', 'Percent', 140)]
    columns = [dict(label=_(label), fieldname=key, fieldtype=kind, width=width, precision=2) for label, key, kind, width in specifications]
    if not industry:
        columns[2]['label'] = _('Required Hours (h)')
    return columns


def execute(filters=None):
    check_access()
    f = validate_filters(filters)
    if f.formula == 'Industry Formula':
        rows, warnings = build_rows(f, *read_sources(f))
        notes = [_('Industry: every scheduled shift uses a fixed 12-hour calculation base; availability deducts raw breakdown and raw maintenance, including startup/fatigue overlaps. Use of Availability Available Hours = Availability Available Hours (12 - Breakdown - Planned Maintenance), calculated per shift before summing. Use of Availability = summed Working Hours / summed Use of Availability Available Hours. Utilisation = Working Hours / Shift Hours. No startup, fatigue, safety or tramming deduction. Ratios above 1 are preserved and flagged.')]
    else:
        rows, warnings = build_isambane_rows(f)
        notes = [_('Isambane: original Engine Required Hours, PBM startup/fatigue exclusions, Pre-Use status/integrity rules and Sunday handling. MAX/MIN formulas run per shift before summing. Safety, Fatigue and Tramming columns are not separate deductions.')]
        notes.append(_('Calculation basis: {0}; original Engine percentage scaling and rounding apply; hours remain unchanged.').format(f.isambane_basis))
    if f.formula in TARGETS:
        availability_target, utilisation_target = TARGETS[f.formula]
        notes.append(_('Reference targets only: Availability {0}; Utilisation {1}. Targets do not scale results.').format(
            format(availability_target, '.0%'), format(utilisation_target, '.0%')))
    notes.append(_('Tree: category, date, machine, shift. Industry and Isambane calculations are performed per shift. Parent totals sum the underlying shift hours. Collapsing a branch does not remove its data from totals.'))
    notes.append(_('Decimal ratios are formatted as percentages; totals divide summed underlying hours. A dash means unavailable or a zero denominator. The separate configuration dialog does not affect either formula.'))
    message = None  # Suppress the long report-wide message block.
    return get_columns(f.formula), rows, message, None, None, True


@frappe.whitelist()
def get_formula_targets():
    """Expose existing reference targets to the report UI without changing results."""
    check_access()
    return {formula: dict(availability=values[0], utilisation=values[1])
            for formula, values in TARGETS.items()}


@frappe.whitelist()
def get_filtered_total(rows, formula='Industry Formula', isambane_basis='100% A & U'):
    """Summarise the browser's visible rows with the canonical weighted rules.

    This permission-checked, read-only operation performs no source queries or writes.
    """
    check_access()
    if formula not in FORMULAS or isambane_basis not in ISAMBANE_BASES:
        frappe.throw(_('Invalid formula or calculation basis.'))
    rows = frappe.parse_json(rows)
    if any('indent' in row for row in rows):
        # Keep existing callers safe if they pass a tree instead of a flat list.
        return build_report_tree([row for row in rows if row.get('is_atomic')], formula, isambane_basis)[-1]
    return total_row([row for row in rows if not row.get('is_total_row')], formula, isambane_basis)


@frappe.whitelist()
def get_filtered_tree(rows, formula='Industry Formula', isambane_basis='100% A & U'):
    """Rebuild matching ancestors, subtotals and bottom total from atomic rows."""
    check_access()
    if formula not in FORMULAS or isambane_basis not in ISAMBANE_BASES:
        frappe.throw(_('Invalid formula or calculation basis.'))
    atoms = [row for row in frappe.parse_json(rows) if row.get('is_atomic') and not row.get('is_total_row')]
    return build_report_tree(atoms, formula, isambane_basis)


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
ISAMBANE_BASES = ('85% A & U', '100% A & U')
TARGETS = {'Industry Formula': (0.85, 0.75), 'Isambane Formula': (0.85, 0.85)}
DAY_TYPES = ('Weekday', 'Saturday', 'Sunday', 'Holiday')
WINDOWS = ('safety_meeting', 'fatigue', 'tramming_out')
HOUR_FIELDS = ('total_hours', 'breakdown_hours', 'planned_maintenance_hours',
               'safety_meeting_hours', 'fatigue_hours', 'tramming_out_hours',
               'availability_available', 'utilisation_available', 'working_hours',
               'use_of_availability_available')


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



INDUSTRY_SHIFT_HOURS = 12.0


def calculate_shift(working=0, breakdown=0, planned_maintenance=0):
    """Industry calculation using a fixed 12-hour shift."""
    shift_hours = INDUSTRY_SHIFT_HOURS
    working = float(working)
    breakdown = float(breakdown)
    planned_maintenance = float(planned_maintenance)

    available = shift_hours - breakdown - planned_maintenance
    use_available = available

    result = dict.fromkeys(HOUR_FIELDS, 0.0)
    result.update(
        total_hours=shift_hours,
        breakdown_hours=breakdown,
        planned_maintenance_hours=planned_maintenance,
        working_hours=working,
        availability_available=available,
        utilisation_available=shift_hours,
        use_of_availability_available=use_available,
        formula="Industry Formula",
    )

    result["availability_percent"] = ratio(available, shift_hours)
    result["use_of_availability_percent"] = ratio(working, use_available)
    result["utilisation_percent"] = ratio(working, shift_hours)

    result["use_of_availability_inconsistent"] = (
        working > use_available
    )
    result["utilisation_inconsistent"] = (
        working > shift_hours
    )

    return result


def total_row(rows, formula='Industry Formula', isambane_basis='100% A & U'):
    result = {'asset': 'Total / Average', 'is_total_row': True,
              'formula': formula, 'isambane_basis': isambane_basis}
    for field in HOUR_FIELDS:
        values = [row.get(field) for row in rows]
        result[field] = None if any(v is None for v in values) else sum(values)
    result['availability_percent'] = ratio(result['availability_available'], result['total_hours'])
    result['utilisation_percent'] = ratio(result['working_hours'], result['utilisation_available'])
    if formula == 'Industry Formula':
        result['use_of_availability_percent'] = ratio(result['working_hours'], result['use_of_availability_available'])
        for field in ('use_of_availability_inconsistent', 'utilisation_inconsistent'):
            result[field] = any(row.get(field) for row in rows)
        if result['use_of_availability_inconsistent'] or result['utilisation_inconsistent']:
            result['performance_warning'] = 'Contains shift Working Hours exceeding a utilisation denominator; actual ratios are not capped.'
    else:
        percentages = dict(availability_percentage=None if result['availability_percent'] is None else result['availability_percent'] * 100,
                           utilisation_percentage=None if result['utilisation_percent'] is None else result['utilisation_percent'] * 100)
        sources.round_engine_row(percentages)
        sources.apply_au_percentage_basis([percentages], isambane_basis)
        result['availability_percent'] = ratio(percentages['availability_percentage'], 100)
        result['utilisation_percent'] = ratio(percentages['utilisation_percentage'], 100)
    return result
