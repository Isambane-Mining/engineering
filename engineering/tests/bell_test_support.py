"""Isolated database preparation for Bell integration tests."""

import frappe

from engineering.tests.kobelco_test_support import (
    TEST_SITE,
    TEST_DATABASE,
    require_isolated_site,
)


def prepare_site():
    require_isolated_site()

    if "erpnext" not in frappe.get_installed_apps():
        raise RuntimeError("ERPNext is required.")

    # Only load Bell schemas. Do not reload or modify Kobelco.
    for doctype in (
        "bell_machine_mapping",
        "api_bell_settings",
        "bell_results",
    ):
        frappe.reload_doc("engineering", "doctype", doctype, force=True)

    for role in (
        "Engineering User",
        "Engineering Manager",
        "Engineering Area Manager",
    ):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({
                "doctype": "Role",
                "role_name": role,
            }).insert()

    frappe.clear_cache()

    print("Bell isolated schemas prepared.")
    print("Site:", TEST_SITE)
    print("Database:", TEST_DATABASE)
