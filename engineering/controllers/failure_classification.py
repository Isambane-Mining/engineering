"""Failure classification configuration; never infer or update source records."""
import re

MASTER_DOCTYPE = 'Breakdown Failure Classification'
TYRES_WHEELS_CLASSIFICATION = 'Tyres / Wheels'
# Bootstrap missing master records only. Existing masters remain authoritative.
INITIAL_CLASSIFICATIONS = (
    'Mechanical', 'Hydraulic', 'Electrical', 'Engine', 'Transmission / Drivetrain',
    'Braking System', 'Steering System', 'Cooling System', 'Fuel System',
    'Lubrication System', 'Undercarriage / Suspension', TYRES_WHEELS_CLASSIFICATION,
    'Structural', 'Pneumatic / Air System', 'Electronic / Control System',
    'Air Conditioning / Cab', 'Safety Systems', 'Attachments / Implements',
    'Pump / Fluid Transfer Systems', 'Tipping / Body Hoist Systems',
)
LEGACY_SETTINGS_MAP = {
    'Brakes': 'Braking System', 'Steering': 'Steering System',
    'Engine / Starting': 'Engine', 'Hydraulics': 'Hydraulic',
    'Cooling': 'Cooling System', 'Air Conditioning': 'Air Conditioning / Cab',
}
AMBIGUOUS_TERMS = {'pump', 'hose', 'leak'}


def terms(value):
    return list(dict.fromkeys(x.strip().casefold() for x in re.split(r'[,\n]+', value or '') if x.strip()))


def prepare_settings(rows, master_names):
    """Map only known equivalents; retain unresolved configuration visibly inactive.

    No PDF was supplied. New masters get empty keyword lists, not invented seeds.
    Inspection links and custom keyword lists on mapped rows are merged losslessly.
    """
    mapped = {name: dict(category=name, keywords='', test_sections='') for name in master_names}
    unresolved = []
    for row in rows:
        old = row.get('category') or row.get('legacy_category') or ''
        # Review rows remain inactive even if a same-named master is later added.
        # Selecting a Link in Settings is the explicit act that resolves them.
        if not row.get('category') and row.get('legacy_category'):
            unresolved.append(dict(category=None, legacy_category=old,
                keywords=row.get('keywords') or '', test_sections=row.get('test_sections') or '',
                mapping_warning=row.get('mapping_warning') or 'Unmapped legacy settings. Review before using; excluded from matching.'))
            continue
        target = old if old in mapped else LEGACY_SETTINGS_MAP.get(old)
        words = terms(row.get('keywords'))
        warning = None
        if old == 'Other' and (words or row.get('test_sections')):
            warning = 'Legacy Other mixes different systems. Review this configuration; it is excluded from matching.'
        elif target not in mapped:
            warning = 'No unambiguous master mapping. Review this configuration; it is excluded from matching.'
        elif set(words) & AMBIGUOUS_TERMS or any(len(word) > 100 for word in words):
            warning = 'Legacy keywords need component-specific phrases. Review this configuration; it is excluded from matching.'
        if warning:
            unresolved.append(dict(category=None, legacy_category=old,
                keywords=row.get('keywords') or '', test_sections=row.get('test_sections') or '',
                mapping_warning=warning))
            continue
        dest = mapped[target]
        dest['keywords'] = '\n'.join(dict.fromkeys(terms(dest['keywords']) + terms(row.get('keywords'))))
        dest['test_sections'] = '\n'.join(dict.fromkeys(
            x.strip() for x in (dest['test_sections'] + '\n' + (row.get('test_sections') or '')).splitlines() if x.strip()))
    return list(mapped.values()) + unresolved


def classification_names():
    """Current masters in the supplied display order, followed by custom masters."""
    import frappe
    names = set(frappe.get_all(MASTER_DOCTYPE, pluck='name', limit_page_length=0))
    return [x for x in INITIAL_CLASSIFICATIONS if x in names] + sorted(names - set(INITIAL_CLASSIFICATIONS))


def validate_failure_classification(value):
    """Optional capture: validate only explicit nonblank master choices."""
    import frappe
    value = str(value or '').strip()
    if value and not frappe.db.exists(MASTER_DOCTYPE, value):
        frappe.throw('Choose an existing Failure Classification or leave it blank.')
    return value
