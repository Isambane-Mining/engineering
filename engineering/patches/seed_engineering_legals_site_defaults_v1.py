"""Seed existing Engineering Legals rules for Klipfontein and Gwab."""

import frappe
from engineering.controllers.engineering_legals_rules import (
    CONFIG_DOCTYPE,
    LEGACY_RULES,
)

SITES = {
    "Klipfontein": "klp",
    "Gwab": "gwab",
}


def execute():
    if len(LEGACY_RULES) != 28:
        frappe.throw("Unexpected legacy rule count.")

    # Validate dependencies before making any changes.
    for site in SITES:
        if not frappe.db.exists("Location", site):
            frappe.throw(f"Missing Location: {site}")

    missing = {
        rule["section"]
        for rule in LEGACY_RULES
        if not frappe.db.exists("Engineering Legals Sections", rule["section"])
    }

    if missing - {"Machine NDT"}:
        frappe.throw(f"Unexpected missing sections: {sorted(missing)}")

    if "Machine NDT" in missing:
        frappe.get_doc({
            "doctype": "Engineering Legals Sections",
            "section": "Machine NDT",
        }).insert(ignore_permissions=True)
        print("CREATED: Machine NDT section")

    for site, code in SITES.items():
        if frappe.db.exists(CONFIG_DOCTYPE, {"site": site}):
            print(f"SKIPPED: {site} already exists")
            continue

        doc = frappe.get_doc({
            "doctype": CONFIG_DOCTYPE,
            "site": site,
            "enabled": 0,
            "sharepoint_site_code": code,
            "section_rules": LEGACY_RULES,
        })

        doc.insert(ignore_permissions=True)

        print(f"CREATED: {site} - {len(doc.section_rules)} rules")
