"""Read-only classification configuration and deterministic description matching."""
import re

MASTER_DOCTYPE = 'Breakdown Failure Classification'
AMBIGUOUS_TERMS = {'pump', 'hose', 'leak'}
_CACHE_KEY = '_engineering_failure_classification_configuration'


def terms(value):
    return list(dict.fromkeys(x.strip().casefold() for x in re.split(r'[,\n]+', value or '') if x.strip()))


def _clean(value):
    return ' '.join(re.sub(r'[^\w\s]', ' ', str(value or '').casefold()).split())


def configuration_from_documents(documents):
    """Compile administrator-owned master records; no category-name fallbacks."""
    result = dict(names=[], synonyms={}, subcategories={}, approved={}, legacy_aliases={},
                  tyre_classifications=[], conflicting_aliases=set())
    documents = sorted(documents, key=lambda d: (int(d.get('display_order') or 1000), str(d.get('name') or d.get('classification_name') or '')))
    for doc in documents:
        name = doc.get('name') or doc.get('classification_name')
        if not name:
            continue
        result['names'].append(name)
        result['subcategories'][name] = {}
        result['approved'][name] = {}
        if int(doc.get('is_tyre_related') or 0):
            result['tyre_classifications'].append(name)
        for alias in str(doc.get('legacy_aliases') or '').splitlines():
            alias = alias.strip()
            if alias and alias not in result['names']:
                if alias not in result['legacy_aliases']:
                    result['legacy_aliases'][alias] = name
                elif result['legacy_aliases'][alias] != name:
                    result['legacy_aliases'][alias] = None
        for row in doc.get('matching_rules') or []:
            if not int(row.get('enabled', 1) or 0):
                continue
            kind = row.get('rule_type')
            replacement = str(row.get('replacement') or '').strip()
            sources = [s.strip() for s in str(row.get('match_text') or '').splitlines() if s.strip()]
            if not replacement or not sources:
                continue
            if kind == 'Spelling correction':
                for source in sources:
                    source, target = _clean(source), _clean(replacement)
                    if not source or not target:
                        continue
                    if source in result['synonyms'] and result['synonyms'][source] != target:
                        result['conflicting_aliases'].add(source)
                    else:
                        result['synonyms'][source] = target
            elif kind == 'Subcategory':
                result['subcategories'][name].setdefault(replacement, []).extend(sources)
            elif kind == 'Approved description':
                for source in sources:
                    result['approved'][name].setdefault(_clean(source), set()).add(replacement)
    for alias in result['conflicting_aliases']:
        result['synonyms'].pop(alias, None)
    return result


def clear_configuration_cache():
    import frappe
    local = getattr(frappe, 'local', None)
    if local is not None:
        setattr(local, _CACHE_KEY, None)


def classification_names():
    """The current master records, in administrator-configured order."""
    import frappe
    return list(frappe.get_all(MASTER_DOCTYPE, pluck='name',
        order_by='display_order asc, name asc', limit_page_length=0))


def get_configuration():
    import frappe
    local = getattr(frappe, 'local', None)
    cached = getattr(local, _CACHE_KEY, None) if local is not None else None
    if cached is not None:
        return cached
    docs = [frappe.get_cached_doc(MASTER_DOCTYPE, name).as_dict() for name in classification_names()]
    config = configuration_from_documents(docs)
    if local is not None:
        setattr(local, _CACHE_KEY, config)
    return config


def get_tyre_classifications():
    return list(get_configuration()['tyre_classifications'])


def prepare_settings(rows, master_names, legacy_aliases=None):
    """Retain unresolved settings and custom phrases without reclassifying PBM."""
    aliases = get_configuration()['legacy_aliases'] if legacy_aliases is None else legacy_aliases
    mapped = {name: dict(category=name, keywords='', test_sections='') for name in master_names}
    unresolved = []
    for row in rows:
        old = row.get('category') or row.get('legacy_category') or ''
        if not row.get('category') and row.get('legacy_category'):
            unresolved.append(dict(category=None, legacy_category=old,
                keywords=row.get('keywords') or '', test_sections=row.get('test_sections') or '',
                mapping_warning=row.get('mapping_warning') or 'Unmapped legacy settings. Review before using; excluded from matching.'))
            continue
        target = old if old in mapped else aliases.get(old)
        words = terms(row.get('keywords'))
        warning = None
        if target not in mapped:
            warning = 'No unambiguous master mapping. Review this configuration; it is excluded from matching.'
        elif set(words) & AMBIGUOUS_TERMS or any(len(word) > 100 for word in words):
            warning = 'Legacy keywords need component-specific phrases. Review this configuration; it is excluded from matching.'
        if warning:
            unresolved.append(dict(category=None, legacy_category=old,
                keywords=row.get('keywords') or '', test_sections=row.get('test_sections') or '',
                mapping_warning=warning))
            continue
        dest = mapped[target]
        dest['keywords'] = '\n'.join(dict.fromkeys(terms(dest['keywords']) + words))
        dest['test_sections'] = '\n'.join(dict.fromkeys(x.strip() for x in
            (dest['test_sections'] + '\n' + (row.get('test_sections') or '')).splitlines() if x.strip()))
    return list(mapped.values()) + unresolved


def validate_failure_classification(value):
    import frappe
    value = str(value or '').strip()
    if value and not frappe.db.exists(MASTER_DOCTYPE, value):
        frappe.throw('Choose an existing Failure Classification or leave it blank.')
    return value


def matching_phrases(text, keywords):
    text = str(text or '').casefold()
    return [word for word in keywords if re.search(r'(?<!\w)' +
        r'[\s\-/]+'.join(re.escape(p) for p in re.split(r'[\s\-/]+', word)) + r'(?!\w)', text)]


def normalise_description(value, synonyms=None):
    synonyms = get_configuration()['synonyms'] if synonyms is None else synonyms
    text = _clean(value)
    seen = {text}
    for _ in range(4):
        updated = text
        changed = False
        for old, new in sorted(synonyms.items(), key=lambda pair: (-len(pair[0]), pair[0])):
            if old == new:
                continue
            candidate = re.sub(r'(?<!\w)' + re.escape(old) + r'(?!\w)', new, updated)
            if candidate != updated:
                if candidate in seen:
                    raise ValueError('Spelling correction rules form a cycle')
                seen.add(candidate)
                changed = True
                updated = candidate
        if not changed:
            return text
        text = updated
    raise ValueError('Spelling correction rules do not stabilise')


def standard_subcategory(reason, classification, configured, approved_mapping=None, rule_config=None):
    """Return a configured label or a review state; do not diagnose vague text."""
    config = get_configuration() if rule_config is None else rule_config
    review = lambda why: dict(status='Review', subcategory=None, matched_phrases=[], review_reason=why)
    if classification not in config['names']:
        return review('Missing or unsupported Failure Classification')
    raw = _clean(reason)
    if any(matching_phrases(raw, [alias]) for alias in config.get('conflicting_aliases', ())):
        return review('Spelling correction has conflicting configured replacements')
    try:
        text = normalise_description(reason, config['synonyms'])
    except ValueError as exc:
        return review(str(exc))
    approved = set()
    for source, labels in config['approved'].get(classification, {}).items():
        if normalise_description(source, config['synonyms']) == text:
            approved.update(labels)
    if approved_mapping:
        approved = {approved_mapping}
    if len(approved) == 1:
        return dict(status='Approved', subcategory=next(iter(approved)), matched_phrases=[], review_reason='')
    if len(approved) > 1:
        return review('Several approved descriptions map to different subcategories')
    if not text or text in ('does not start', 'do not start', 'no power', 'oil leak', 'not starting', 'wont start', 'will not start'):
        return review('Insufficient component detail')
    matches = []
    for category in config['names']:
        phrases = {}
        for label, aliases in config['subcategories'].get(category, {}).items():
            for phrase in aliases:
                normalized = normalise_description(phrase, config['synonyms'])
                if normalized:
                    phrases.setdefault(normalized, set()).add(label)
        for phrase in configured.get(category, []):
            normalized = normalise_description(phrase, config['synonyms'])
            if normalized and normalized not in AMBIGUOUS_TERMS:
                phrases.setdefault(normalized, {phrase.strip().capitalize()})
        found = matching_phrases(text, list(phrases))
        found = [a for a in found if not any(a != b and matching_phrases(b, [a]) for b in found)]
        matches.extend((category, label, phrase) for phrase in found for label in phrases[phrase])
    if any(category != classification for category, _, _ in matches):
        return review('Description conflicts with or spans Failure Classifications')
    local = {(label, phrase) for category, label, phrase in matches if category == classification}
    labels = {label for label, _ in local}
    if len(labels) != 1:
        return review('Several subcategories match' if labels else 'No approved component phrase matches')
    return dict(status='Matched', subcategory=next(iter(labels)),
                matched_phrases=sorted(p for _, p in local), review_reason='')


def validate_matching_configuration(doc):
    config = configuration_from_documents([doc.as_dict()])
    for row in doc.get('matching_rules') or []:
        if not int(row.get('enabled', 1) or 0):
            continue
        if not str(row.get('match_text') or '').strip() or not str(row.get('replacement') or '').strip():
            raise ValueError('Enabled matching rules need matching text and a replacement/label')
        if row.get('rule_type') == 'Spelling correction':
            for source in str(row.get('match_text') or '').splitlines():
                if source.strip():
                    normalise_description(source, config['synonyms'])
    if config['conflicting_aliases']:
        raise ValueError('A spelling correction has conflicting replacements')
