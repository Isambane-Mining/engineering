"""Dashboard markup and compatibility imports for tyre damage calculations."""
from engineering.controllers.tyre_damage import (
    CATEGORIES, MAX_RECORDS, damage_counts, fetch_tyre_damage_records, is_classified_tyre_damage,
)

def tyre_damage_card(category, count):
    if category not in CATEGORIES:
        return ''
    value = '—' if count is None else str(int(count))
    title = 'Read access to breakdown records is required.' if count is None else 'Unique Breakdown records classified as Tyres / Wheels and Tyre Damage. Unclassified historical records are excluded.'
    return f'''<div class="frappe-card daily-tyre-kpi" data-category="{category}" data-count="{value}" title="{title}" role="button" tabindex="0" style="cursor:pointer;transition:box-shadow .2s,border-color .2s;">
        <div class="daily-tyre-title">{category} Tyre Related Breakdowns</div>
        <div class="daily-tyre-body"><svg class="daily-tyre-icon" viewBox="0 0 40 44" aria-hidden="true" focusable="false">
            <ellipse cx="20" cy="22" rx="15" ry="20" fill="#6b7280" stroke="#4b5563" stroke-width="2"/>
            <ellipse cx="23" cy="22" rx="10" ry="18" fill="#9ca3af" stroke="#374151" stroke-width="2"/>
            <ellipse cx="23" cy="22" rx="5" ry="12" fill="#e5e7eb" stroke="#4b5563" stroke-width="2"/>
            <path d="M9 9l6 3M6 17l7 2M6 26l7-1M10 35l5-3" stroke="#d1d5db" stroke-width="2"/>
        </svg><div><div class="daily-tyre-value">{value}</div><div class="daily-tyre-subtitle">Click to view related breakdowns</div></div></div></div>'''


def au_kpi_row(category, values, count):
    if category not in CATEGORIES:
        return ''
    def percentage(value):
        return '—' if value is None else f'{float(value):.1f}%'
    return f'''<div class="daily-damage-kpi-row" data-kpi-category="{category}">
        <div class="frappe-card daily-au-average" style="border-left:5px solid #387334;"><div class="daily-tyre-title">{category} Average Availability — Selected Period</div><strong style="color:#168749;">{percentage(values.get('avail'))}</strong></div>
        <div class="frappe-card daily-au-average" style="border-left:5px solid #168749;"><div class="daily-tyre-title">{category} Average Utilisation — Selected Period</div><strong style="color:#2563eb;">{percentage(values.get('util'))}</strong></div>
        {tyre_damage_card(category, count)}</div>'''
