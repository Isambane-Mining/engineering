"""Engineering Legals policy. Importing this module never reads a site or database.

Existing dates and recorded policies are authoritative. Configuration is consulted only
for new records or intentional changes to policy-driving inputs.
"""

from __future__ import annotations

import json
from copy import deepcopy

import frappe
from frappe.utils import add_days, add_months, cint, getdate, nowdate

CONFIG_DOCTYPE = "Engineering Legals Site Configuration"
ROLLOUT_SWITCH = "engineering_legals_site_rules_enabled"
DRIVING_FIELDS = (
    "site",
    "sections",
    "start_date",
    "vehicle_type",
    "lifting_type",
    "brake_wear_type",
)
AUDIT_FIELDS = ("site_configuration", "expiry_rule_source", "expiry_rule_snapshot")
LEGACY_SITE_MAPPING = {"Gwab": "gwab", "Klipfontein": "klp"}
MONTHLY_CATEGORIES = [
    ("01. Automatic Fire Suppression", "active_until_expiry", ["Fire Suppression"]),
    (
        "02. Condition Monitoring",
        "active_until_expiry",
        [
            "Illumination Baseline",
            "Noise Level Baseline & Measurement",
            "NDT",
            "Machine NDT",
        ],
    ),
    (
        "03. Dynamic Brake Testing",
        "active_until_expiry",
        [
            "Brake Test",
            "Brake Tester Calibration Certificate",
            "Brake Test Authorisations",
        ],
    ),
    (
        "04. Earth Leakage Testing & CoC",
        "active_until_expiry",
        [
            "CoC for Containers, Offices, Workshops",
            "Multi-meter Calibration Certificate",
            "Authorised LV Person",
            "Earth Leakage Testing",
            "Earth Leakage",
        ],
    ),
    (
        "05. Equipment list",
        "saved_in_month",
        ["Equipment Technical Information", "Equipment List"],
    ),
    ("06. FRCS Compliance", "active_until_expiry", ["FRCS"]),
    (
        "07. Load Testing",
        "active_until_expiry",
        ["Lifting Equipment", "Load Test Certificate"],
    ),
    (
        "08. Maintenance Schedules",
        "saved_in_month",
        [
            "Machine Service Records",
            "Service Schedule",
            "Wearcheck",
            "Brake Wear Measurements",
            "Tyre Inspection Report",
            "C-Track Inspection",
            "Maintenance Inspections",
        ],
    ),
    ("09. PDS-MPI Maintenance", "saved_in_month", ["PDS", "PDS Installation"]),
    (
        "10. Pressure Vessels",
        "active_until_expiry",
        ["Pressure Vessels", "Pressure Vessel"],
    ),
]
CATEGORY_CONFIG = [
    {"category": category, "mode": mode, "sections": sections}
    for category, mode, sections in MONTHLY_CATEGORIES
]
CATEGORIES = [category for category, _, _ in MONTHLY_CATEGORIES] + ["Other"]
MODES = {
    "Active Until Expiry": "active_until_expiry",
    "Saved In Month": "saved_in_month",
}
LEGACY_SUBFOLDERS = {
    "Machine Service Records": "Maintenance-Services",
    "Service Schedule": "Maintenance-Services",
    "Wearcheck": "Maintenance-Services",
    "Brake Wear Measurements": "Maintenance-Services",
    "Tyre Inspection Report": "Tyre Surveys",
    "C-Track Inspection": "Track Surveys",
}


def value(obj, field, default=None):
    return (
        obj.get(field, default)
        if isinstance(obj, dict)
        else getattr(obj, field, default)
    )


def text(value):
    return str(value or "").strip()


def fail(message):
    frappe.throw(message, frappe.ValidationError)


def _legacy_rules():
    periods = {
        "FRCS": 3,
        "Fire Suppression": 3,
        "Earth Leakage Testing": 3,
        "Brake Tester Calibration Certificate": 12,
        "Brake Test Authorisations": 12,
        "Multi-meter Calibration Certificate": 12,
        "Authorised LV Person": 12,
        "Pressure Vessels": 12,
        "NDT": 12,
        "Machine NDT": 12,
        "CoC for Containers, Offices, Workshops": 1,
        "C-Track Inspection": 1,
        "Tyre Inspection Report": 1,
        "Illumination Baseline": 24,
        "Noise Level Baseline & Measurement": 24,
    }
    no_expiry = {
        "Machine Service Records",
        "Service Schedule",
        "Wearcheck",
        "Brake Wear Measurements",
        "Equipment Technical Information",
        "Maintenance Inspections",
        "PDS Installation",
    }
    fleet_optional = {
        "Brake Tester Calibration Certificate",
        "Brake Test Authorisations",
        "CoC for Containers, Offices, Workshops",
        "Multi-meter Calibration Certificate",
        "Authorised LV Person",
        "Earth Leakage Testing",
        "Pressure Vessels",
    }
    rows = []
    for section in list(periods) + sorted(no_expiry):
        category, mode = next(
            (category, mode)
            for category, mode, sections in MONTHLY_CATEGORIES
            if section in sections
        )
        rows.append(
            {
                "section": section,
                "vehicle_type": "",
                "lifting_type": "",
                "active": 1,
                "no_expiry": int(section in no_expiry),
                "expiry_value": periods.get(section),
                "expiry_unit": "Months" if section in periods else "",
                "fleet_required": int(section not in fleet_optional),
                "start_date_policy": "Clear"
                if section == "Brake Wear Measurements"
                else "Optional"
                if section
                in {"Machine Service Records", "Service Schedule", "Wearcheck"}
                else "Required",
                "brake_wear_required": int(section == "Brake Wear Measurements"),
                "report_category": category,
                "counting_mode": next(k for k, v in MODES.items() if v == mode),
                "sharepoint_subfolder": LEGACY_SUBFOLDERS.get(section, ""),
            }
        )
    for section, field, variants, category, mode in [
        (
            "Brake Test",
            "vehicle_type",
            {"TMM": 1, "LDV": 3},
            CATEGORIES[2],
            "Active Until Expiry",
        ),
        ("PDS", "vehicle_type", {"TMM": 3, "LDV": 4}, CATEGORIES[8], "Saved In Month"),
        (
            "Lifting Equipment",
            "lifting_type",
            {"Inspection": 3, "Certificate": 12},
            CATEGORIES[6],
            "Active Until Expiry",
        ),
    ]:
        for condition, months in variants.items():
            row = {
                "section": section,
                "vehicle_type": "",
                "lifting_type": "",
                "active": 1,
                "no_expiry": 0,
                "expiry_value": months,
                "expiry_unit": "Months",
                "fleet_required": 1,
                "start_date_policy": "Required",
                "brake_wear_required": 0,
                "report_category": category,
                "counting_mode": mode,
                "sharepoint_subfolder": "",
            }
            row[field] = condition
            rows.append(row)
    return rows


LEGACY_RULES = _legacy_rules()


def _safe_path(part):
    part = text(part)
    return (
        part not in {".", ".."}
        and not any(c in part for c in '/\\:*?"<>|')
        and not any(ord(c) < 32 for c in part)
    )


def validate_configuration(configuration):
    rows = value(configuration, "section_rules", []) or []
    if cint(value(configuration, "enabled")) and not value(
        configuration, "effective_from"
    ):
        fail("Effective From is required before enabling site rules.")
    if value(configuration, "effective_from"):
        getdate(value(configuration, "effective_from"))
    if not _safe_path(value(configuration, "sharepoint_site_code")):
        fail("SharePoint Site Code must be a single safe folder name.")
    if cint(value(configuration, "enabled")) and not any(
        cint(value(row, "active")) for row in rows
    ):
        fail("An enabled configuration needs at least one active section rule.")
    seen = []
    for row in rows:
        section = text(value(row, "section"))
        if not section:
            fail("Section is required for every rule.")
        vehicle, lifting = (
            text(value(row, "vehicle_type")),
            text(value(row, "lifting_type")),
        )
        if vehicle not in {"", "LDV", "TMM"} or lifting not in {
            "",
            "Inspection",
            "Certificate",
        }:
            fail("Invalid vehicle or lifting condition.")
        if value(row, "start_date_policy") not in {"Required", "Optional", "Clear"}:
            fail("Invalid start date policy.")
        if (
            value(row, "report_category") not in CATEGORIES
            or value(row, "counting_mode") not in MODES
        ):
            fail("Select a valid monthly category and counting mode.")
        if not _safe_path(value(row, "sharepoint_subfolder")):
            fail("SharePoint Subfolder must be a single safe folder name.")
        period = value(row, "expiry_value")
        if cint(value(row, "no_expiry")):
            if period not in (None, "", 0) or text(value(row, "expiry_unit")):
                fail("No-expiry rules cannot define an expiry interval.")
            if value(row, "counting_mode") != "Saved In Month":
                fail("No-expiry rules must count only in the saved month.")
        else:
            try:
                positive_integer = float(period) > 0 and float(period).is_integer()
            except (ValueError, TypeError):
                positive_integer = False
            if not positive_integer or value(row, "expiry_unit") not in {
                "Days",
                "Months",
                "Years",
            }:
                fail("Expiry needs a positive whole value and Days, Months or Years.")
            if value(row, "start_date_policy") != "Required":
                fail("Expiring rules require a start date.")
        for old_section, old_vehicle, old_lifting in seen:
            if old_section != section:
                continue
            if (vehicle, lifting) == (old_vehicle, old_lifting):
                fail(f"Duplicate section rule: {section}.")
            overlap = (not vehicle or not old_vehicle or vehicle == old_vehicle) and (
                not lifting or not old_lifting or lifting == old_lifting
            )
            if overlap and bool(vehicle) + bool(lifting) == bool(old_vehicle) + bool(
                old_lifting
            ):
                fail(f"Ambiguous overlapping section rules: {section}.")
        seen.append((section, vehicle, lifting))


def load_configuration(site):
    """Default-off; old databases are usable before the additive schema migration."""
    if not cint(frappe.conf.get(ROLLOUT_SWITCH)) or not site:
        return None
    if not frappe.db.table_exists(CONFIG_DOCTYPE):
        return None
    names = frappe.get_all(
        CONFIG_DOCTYPE, filters={"site": site}, pluck="name", limit_page_length=2
    )
    if len(names) > 1:
        fail(f"Duplicate Engineering Legals configuration for {site}.")
    return frappe.get_doc(CONFIG_DOCTYPE, names[0]) if names else None


def _effective_configuration(values, configuration=None):
    configuration = (
        load_configuration(value(values, "site"))
        if configuration is None
        else configuration
    )
    if not configuration or not cint(value(configuration, "enabled")):
        return None
    if text(value(configuration, "site")) != text(value(values, "site")):
        fail("Site configuration does not match the document site.")
    validate_configuration(configuration)
    relevant_date = (
        value(values, "start_date") or value(values, "creation") or nowdate()
    )
    if getdate(relevant_date) < getdate(value(configuration, "effective_from")):
        return None
    return configuration


def resolve_rule(values, configuration=None, partial=False):
    configuration = _effective_configuration(values, configuration)
    rows = value(configuration, "section_rules") if configuration else LEGACY_RULES
    section = text(value(values, "sections"))
    section_rows = [r for r in rows if text(value(r, "section")) == section]
    if not section_rows:
        fail(f"No configured rule for section: {section}.")
    conditions = ("vehicle_type", "lifting_type")
    matches = [
        r
        for r in section_rows
        if all(
            not text(value(r, f)) or text(value(r, f)) == text(value(values, f))
            for f in conditions
        )
    ]
    incomplete = False
    if not matches and partial:
        matches = [
            r
            for r in section_rows
            if all(
                not text(value(r, f))
                or not text(value(values, f))
                or text(value(r, f)) == text(value(values, f))
                for f in conditions
            )
        ]
        incomplete = True
    if not matches:
        fail("Select a supported Vehicle Type / Lifting Type for this section.")
    specificity = max(sum(bool(text(value(r, f))) for f in conditions) for r in matches)
    matches = [
        r
        for r in matches
        if sum(bool(text(value(r, f))) for f in conditions) == specificity
    ]
    if len(matches) > 1 and not incomplete:
        fail("Ambiguous section rule.")
    selected = matches[0]
    if incomplete:
        selected = next((r for r in matches if cint(value(r, "active"))), selected)
    if not cint(value(selected, "active")):
        fail("This section/equipment rule is inactive at this site.")
    rule = {
        f: value(selected, f)
        for f in (
            "section",
            "vehicle_type",
            "lifting_type",
            "active",
            "no_expiry",
            "expiry_value",
            "expiry_unit",
            "fleet_required",
            "start_date_policy",
            "brake_wear_required",
            "report_category",
            "counting_mode",
            "sharepoint_subfolder",
        )
    }
    rule["sharepoint_subfolder"] = text(
        rule["sharepoint_subfolder"]
    ) or LEGACY_SUBFOLDERS.get(section, "")
    rule.update(
        source="Site Configuration" if configuration else "Legacy",
        configuration=value(configuration, "name"),
        configuration_modified=str(value(configuration, "modified") or ""),
        sharepoint_site_code=text(value(configuration, "sharepoint_site_code")),
        vehicle_options=sorted(
            {
                text(value(r, "vehicle_type"))
                for r in section_rows
                if text(value(r, "vehicle_type"))
            }
        ),
        lifting_options=sorted(
            {
                text(value(r, "lifting_type"))
                for r in section_rows
                if text(value(r, "lifting_type"))
            }
        ),
        incomplete=incomplete,
        version=1,
    )
    return rule


def calculate(values, configuration=None, partial=False):
    rule = resolve_rule(values, configuration, partial)
    result = {field: value(values, field) for field in DRIVING_FIELDS}
    result["fleet_number"] = value(values, "fleet_number")
    if not partial:
        if cint(rule["fleet_required"]) and not result["fleet_number"]:
            fail("Fleet Number is required for this Section.")
        if rule["start_date_policy"] == "Required" and not result["start_date"]:
            fail("Start Date is required.")
        if cint(rule["brake_wear_required"]) and result["brake_wear_type"] not in {
            "ADT",
            "FEL",
        }:
            fail("Brake Wear Type (ADT/FEL) is required for this Section.")
    for field in ("vehicle_type", "lifting_type"):
        if not rule[field] and not rule[field.replace("_type", "_options")]:
            result[field] = None
    if not cint(rule["brake_wear_required"]):
        result["brake_wear_type"] = None
    if rule["start_date_policy"] == "Clear":
        result["start_date"] = None
    expiry = None
    if not cint(rule["no_expiry"]) and result["start_date"] and not rule["incomplete"]:
        start, period = getdate(result["start_date"]), int(rule["expiry_value"])
        expiry = (
            add_days(start, period)
            if rule["expiry_unit"] == "Days"
            else add_months(
                start, period * (12 if rule["expiry_unit"] == "Years" else 1)
            )
        )
    result.update(expiry_date=expiry, rule=rule)
    return result


def _same_input(left, right, field):
    a, b = value(left, field), value(right, field)
    if field == "start_date":
        return (getdate(a) if a else None) == (getdate(b) if b else None)
    return text(a) == text(b)


def apply_document_rules(doc):
    before = (
        doc.get_doc_before_save()
        if callable(getattr(doc, "get_doc_before_save", None))
        else None
    )
    if before and all(_same_input(doc, before, field) for field in DRIVING_FIELDS):
        if not _same_input(doc, before, "fleet_number") and not value(
            doc, "fleet_number"
        ):
            snapshot = value(before, "expiry_rule_snapshot")
            if snapshot:
                previous_rule = (
                    json.loads(snapshot) if isinstance(snapshot, str) else snapshot
                )
            else:
                try:
                    previous_rule = resolve_rule(
                        before, configuration=False, partial=True
                    )
                except frappe.ValidationError:
                    previous_rule = {"fleet_required": True}
            if cint(previous_rule["fleet_required"]):
                fail("Fleet Number is required for this Section.")
        for field in ("expiry_date",) + AUDIT_FIELDS:
            setattr(doc, field, value(before, field))
        return
    result = calculate(doc)
    for field in (
        "start_date",
        "expiry_date",
        "vehicle_type",
        "lifting_type",
        "brake_wear_type",
    ):
        setattr(doc, field, result[field])
    rule = result["rule"]
    doc.site_configuration = rule["configuration"]
    doc.expiry_rule_source = rule["source"]
    doc.expiry_rule_snapshot = json.dumps(rule, sort_keys=True)


def record_reporting_rule(record):
    """Never consult today's site configuration when reading historical records."""
    snapshot = value(record, "expiry_rule_snapshot")
    if snapshot:
        rule = json.loads(snapshot) if isinstance(snapshot, str) else deepcopy(snapshot)
        if (
            rule.get("version") != 1
            or rule.get("report_category") not in CATEGORIES
            or rule.get("counting_mode") not in MODES
        ):
            fail("Invalid recorded Engineering Legals reporting policy.")
        return {
            "category": rule["report_category"],
            "mode": MODES[rule["counting_mode"]],
            "sharepoint_site_code": rule.get("sharepoint_site_code", ""),
            "sharepoint_subfolder": rule.get("sharepoint_subfolder", ""),
        }
    section = text(value(record, "sections"))
    for category, mode, sections in MONTHLY_CATEGORIES:
        if section in sections:
            return {
                "category": category,
                "mode": mode,
                "sharepoint_site_code": "",
                "sharepoint_subfolder": LEGACY_SUBFOLDERS.get(section, ""),
            }
    return None


def optional_snapshot_fields():
    """Do not select not-yet-installed columns while rollout is disabled."""
    return (
        ["expiry_rule_snapshot"]
        if frappe.get_meta("Engineering Legals").has_field("expiry_rule_snapshot")
        else []
    )


def skip_no_expiry_section(record, legacy_exclusions):
    snapshot = value(record, "expiry_rule_snapshot")
    if snapshot:
        policy = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
        return bool(cint(policy.get("no_expiry")))
    return value(record, "sections") in legacy_exclusions


def apply_no_expiry_overrides(records):
    """A new recorded no-expiry policy supersedes old due alerts, never history.

    Otherwise callers retain their existing maximum-expiry selection semantics.
    Use only for current-status views, not history or monthly membership.
    """
    groups = {}
    for record in records:
        fleet = value(record, "fleet_number")
        key = (
            value(record, "sections"),
            fleet,
            None if fleet else value(record, "site"),
        )
        groups.setdefault(key, []).append(record)
    retained = set()
    for group in groups.values():
        latest = max(
            group,
            key=lambda record: (
                str(value(record, "start_date") or value(record, "creation") or ""),
                str(value(record, "modified") or ""),
                str(value(record, "name") or ""),
            ),
        )
        snapshot = value(latest, "expiry_rule_snapshot")
        policy = json.loads(snapshot) if isinstance(snapshot, str) else (snapshot or {})
        selected = [latest] if cint(policy.get("no_expiry")) else group
        retained.update(id(record) for record in selected)
    return [record for record in records if id(record) in retained]


def filter_expiry_range(records, from_date=None, to_date=None):
    """Apply date filters only after no-expiry replacements suppress older alerts."""
    lower, upper = (
        getdate(from_date) if from_date else None,
        getdate(to_date) if to_date else None,
    )
    if not lower and not upper:
        return records
    return [
        record
        for record in records
        if value(record, "expiry_date")
        and (not lower or getdate(value(record, "expiry_date")) >= lower)
        and (not upper or getdate(value(record, "expiry_date")) <= upper)
    ]


def get_record_sharepoint_parts(record):
    from engineering.engineering.doctype.engineering_legals.engineering_legals import (
        NEW_SHAREPOINT_SECTION_MAPPING,
    )

    snapshot = value(record, "expiry_rule_snapshot")
    policy = json.loads(snapshot) if isinstance(snapshot, str) else (snapshot or {})
    site = LEGACY_SITE_MAPPING.get(text(value(record, "site")))
    if policy.get("source") == "Site Configuration":
        reporting = record_reporting_rule(record)
        site = reporting["sharepoint_site_code"] or site
        parts = [reporting["category"]]
        if reporting["sharepoint_subfolder"]:
            parts.append(reporting["sharepoint_subfolder"])
        if not _safe_path(site) or any(not _safe_path(part) for part in parts):
            fail("Unsafe recorded SharePoint routing.")
        return site, parts
    return site, NEW_SHAREPOINT_SECTION_MAPPING.get(text(value(record, "sections")))


def get_sharepoint_site_mapping():
    """Include recorded routes even after rules are disabled; never delete old paths."""
    mapping = dict(LEGACY_SITE_MAPPING)
    if optional_snapshot_fields():
        records = frappe.get_all(
            "Engineering Legals",
            filters={"expiry_rule_snapshot": ["is", "set"]},
            fields=["site", "sections", "expiry_rule_snapshot"],
            limit_page_length=0,
        )
        for record in records:
            site_code, _ = get_record_sharepoint_parts(record)
            if site_code:
                mapping.setdefault(value(record, "site"), site_code)
    if cint(frappe.conf.get(ROLLOUT_SWITCH)) and frappe.db.table_exists(CONFIG_DOCTYPE):
        for site in frappe.get_all(
            CONFIG_DOCTYPE, filters={"enabled": 1}, pluck="site", limit_page_length=0
        ):
            configuration = _effective_configuration({"site": site})
            code = text(value(configuration, "sharepoint_site_code"))
            if code:
                mapping[site] = code
    return mapping


def supplier_sites():
    from engineering.templates.pages.engineering_legals_sup import (
        _get_supplier_asset_filters,
    )

    filters = _get_supplier_asset_filters()
    locations = (
        frappe.get_all("Asset", filters=filters, pluck="location", limit_page_length=0)
        if filters
        else []
    )
    # Preserve the portal's two existing site choices, and allow the supplier's other sites.
    return sorted(set(LEGACY_SITE_MAPPING) | {site for site in locations if site})


def authorize_capture(values, docname=None, draft_name=None):
    if frappe.session.user == "Guest":
        raise frappe.PermissionError("Please log in first.")
    if docname and draft_name:
        fail("Specify a legal document or supplier draft, not both.")
    supplier = "Supplier" in frappe.get_roles(frappe.session.user)
    existing = None
    if docname:
        existing = frappe.get_doc("Engineering Legals", docname)
        existing.check_permission("read")
    if (
        not supplier
        and not existing
        and not frappe.has_permission("Engineering Legals", "create")
    ):
        raise frappe.PermissionError("Engineering Legals create access is required.")
    if supplier:
        from engineering.templates.pages.engineering_legals_sup import (
            _get_user_suppliers,
        )

        suppliers = _get_user_suppliers()
        if not suppliers:
            raise frappe.PermissionError("Your user is not linked to a Supplier.")
        asset = value(values, "fleet_number")
        if asset and not frappe.db.exists(
            "Asset",
            {"name": asset, "asset_owner": "Supplier", "supplier": ["in", suppliers]},
        ):
            raise frappe.PermissionError(
                "This asset is not linked to your supplier access."
            )
        if value(values, "site") and value(values, "site") not in supplier_sites():
            raise frappe.PermissionError("This site is outside your supplier access.")
    elif (
        value(values, "site")
        and (not existing or value(existing, "site") != value(values, "site"))
        and not frappe.has_permission("Location", "read", doc=value(values, "site"))
    ):
        raise frappe.PermissionError("You do not have access to this Location.")
    if (
        existing
        and supplier
        and (
            not existing.fleet_number
            or not frappe.db.exists(
                "Asset",
                {
                    "name": existing.fleet_number,
                    "asset_owner": "Supplier",
                    "supplier": ["in", suppliers],
                },
            )
        )
    ):
        raise frappe.PermissionError(
            "This legal record is outside your supplier access."
        )
    if draft_name:
        draft = frappe.get_doc("Engineering Legals supplier Portal Draft", draft_name)
        if supplier and (draft.portal_user != frappe.session.user or draft.sent_to_erp):
            raise frappe.PermissionError("You can only edit your own unsent draft.")
        if not supplier:
            draft.check_permission("write")
        existing = draft
    return existing


def section_options(values):
    configuration = _effective_configuration(values)
    rows = value(configuration, "section_rules") if configuration else LEGACY_RULES
    permitted = {
        text(value(row, "section")) for row in rows if cint(value(row, "active"))
    }
    masters = frappe.get_all(
        "Engineering Legals Sections", pluck="name", limit_page_length=0
    )
    return sorted(permitted.intersection(masters))


@frappe.whitelist()
def get_capture_preview(values=None, docname=None, draft_name=None):
    """Shared Desk/portal API. Never accepts client-supplied dates or policy provenance."""
    raw = frappe.parse_json(values) if isinstance(values, str) else (values or {})
    if not isinstance(raw, dict):
        fail("Capture values must be an object.")
    inputs = {field: raw.get(field) for field in DRIVING_FIELDS + ("fleet_number",)}
    existing = authorize_capture(inputs, docname, draft_name)
    if existing:
        inputs["creation"] = value(existing, "creation")
    preserved = (
        existing
        and docname
        and all(_same_input(inputs, existing, field) for field in DRIVING_FIELDS)
    )
    if preserved:
        snapshot = value(existing, "expiry_rule_snapshot")
        if snapshot:
            rule = json.loads(snapshot)
        else:
            try:
                rule = resolve_rule(existing, configuration=False, partial=True)
            except frappe.ValidationError:
                # Historic aliases may no longer be capturable, but must remain editable.
                rule = {
                    "vehicle_options": [],
                    "lifting_options": [],
                    "fleet_required": bool(existing.fleet_number),
                    "start_date_policy": "Required"
                    if existing.start_date
                    else "Optional",
                    "brake_wear_required": bool(value(existing, "brake_wear_type")),
                    "no_expiry": not existing.expiry_date,
                }
        result = {field: value(existing, field) for field in DRIVING_FIELDS}
        result.update(expiry_date=existing.expiry_date, rule=rule, preserved=True)
        # Do not let a later broken/disabled site policy prevent an unrelated historic edit.
        try:
            available_sections = section_options(inputs)
        except frappe.ValidationError:
            available_sections = []
        result["sections"] = sorted(
            set(available_sections) | {text(value(existing, "sections"))}
        )
        return result
    sections = section_options(inputs)
    if not inputs["sections"]:
        return {
            "sections": sections,
            "rule": None,
            "expiry_date": None,
            "preserved": False,
        }
    result = calculate(inputs, partial=True)
    result.update(sections=sections, preserved=False)
    return result
