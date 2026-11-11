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


# Explicit local vocabulary. Changes are reviewed in source control; no fuzzy or
# external inference is used. These aliases never alter the captured complaint.
DESCRIPTION_SYNONYMS = {
    'tyer': 'tyre', 'tire': 'tyre', 'batery': 'battery',
    'head light': 'headlight', 'tyre puncher': 'tyre puncture',
    'tyre punctured': 'tyre puncture', 'a/c': 'air conditioning',
    'alt.': 'alternator', 'batt.': 'battery',
}
SUBCATEGORY_PHRASES = {
    'Tyres / Wheels': {'Tyre puncture': ('tyre puncture',)},
    'Electrical': {
        'Battery fault': ('battery faulty', 'battery fault', 'battery will not hold charge'),
        'Lighting fault': ('headlight faulty', 'headlight not working', 'headlight fault'),
        'Alternator fault': ('alternator faulty', 'alternator fault', 'alternator not charging'),
    },
}
# Explicit manual approvals keyed by (recorded classification, normalised reason).
# An approved value wins over automatic matching; never auto-populate this map.
APPROVED_SUBCATEGORY_MAPPINGS = {}


def matching_phrases(text, keywords):
    """Shared existing whole-phrase matcher used by Machine Reliability and TMM."""
    text = str(text or '').casefold()
    return [word for word in keywords if re.search(
        r'(?<!\w)' + r'[\s\-/]+'.join(re.escape(p) for p in re.split(r'[\s\-/]+', word)) + r'(?!\w)', text)]


def normalise_description(value):
    value = str(value or '').casefold()
    for old, new in sorted(DESCRIPTION_SYNONYMS.items(), key=lambda pair: -len(pair[0])):
        value = re.sub(r'(?<!\w)' + re.escape(old) + r'(?!\w)', new, value)
    value = ' '.join(re.sub(r'[^\w\s]', ' ', value).split())
    # Punctuation can split an approved phrase (head-light); token corrections
    # can expose another explicit phrase (tyer puncher). Two deterministic passes
    # resolve these combinations without approximate/fuzzy matching.
    for _ in range(2):
        for old, new in sorted(DESCRIPTION_SYNONYMS.items(), key=lambda pair: -len(pair[0])):
            value = re.sub(r'(?<!\w)' + re.escape(old) + r'(?!\w)', new, value)
    return value


def standard_subcategory(reason, classification, configured, approved_mapping=None):
    """One stable label or an explicit review result; never diagnose vague text."""
    text = normalise_description(reason)
    approved = approved_mapping or APPROVED_SUBCATEGORY_MAPPINGS.get((classification, text))
    if approved:
        return dict(status='Approved', subcategory=approved, matched_phrases=[], review_reason='')
    review = lambda why: dict(status='Review', subcategory=None, matched_phrases=[], review_reason=why)
    if not text or text in ('does not start', 'no power', 'oil leak', 'not starting', 'wont start', 'will not start'):
        return review('Insufficient component detail')
    vocabulary = {}
    for category in set(configured) | set(SUBCATEGORY_PHRASES):
        phrases = {}
        for label, aliases in SUBCATEGORY_PHRASES.get(category, {}).items():
            for phrase in aliases:
                phrases[normalise_description(phrase)] = label
        for phrase in configured.get(category, []):
            normalized = normalise_description(phrase)
            if normalized and normalized not in AMBIGUOUS_TERMS:
                phrases.setdefault(normalized, phrase.strip().capitalize())
        vocabulary[category] = phrases
    matches = []
    for category, phrases in vocabulary.items():
        found = matching_phrases(text, list(phrases))
        # Contained generic phrases cannot override a more specific component.
        found = [p for p in found if not any(p != q and matching_phrases(q, [p]) for q in found)]
        matches.extend((category, phrases[p], p) for p in found)
    local = {(label, phrase) for category, label, phrase in matches if category == classification}
    other = {category for category, _, _ in matches if category != classification}
    if other:
        return review('Description conflicts with or spans Failure Classifications')
    labels = {label for label, _ in local}
    if len(labels) != 1:
        return review('Several subcategories match' if labels else 'No approved component phrase matches')
    return dict(status='Matched', subcategory=next(iter(labels)), matched_phrases=sorted(p for _, p in local), review_reason='')
