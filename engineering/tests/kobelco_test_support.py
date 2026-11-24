"""Fail-closed test isolation. Never borrow live Settings, Assets or Redis keys."""
import frappe

TEST_SITE = "kobelco-test.localhost"
TEST_DATABASE = "kobelco_test"


def require_isolated_site():
    if (frappe.local.site != TEST_SITE or frappe.conf.db_name != TEST_DATABASE
            or not frappe.conf.kobelco_isolated_tests or not frappe.conf.allow_tests
            or not frappe.conf.disable_scheduler or not frappe.conf.pause_scheduler):
        raise RuntimeError("Kobelco database tests require the designated isolated test site with scheduling disabled; LAB is forbidden.")


def prepare_site():
    """Bootstrap only the tested Engineering schemas on an isolated ERPNext site.

    Run explicitly during test-site provisioning, never from test setUp. Avoid
    installing unrelated Engineering fixtures/patches or enabling scheduled jobs.
    """
    require_isolated_site()
    from frappe.installer import add_to_installed_apps, add_module_defs
    if "erpnext" not in frappe.get_installed_apps():
        raise RuntimeError("Install ERPNext on the isolated site before preparing Kobelco tests.")
    add_to_installed_apps("engineering")
    add_module_defs("engineering", ignore_if_duplicate=True)
    for role in ("Engineering User", "Engineering Manager", "Engineering Area Manager",
                 "Procurement User", "Production Manager", "Production Area Manager"):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role}).insert()
    for doctype in ("kobelco_machine_mapping", "api_kobelco_settings", "kobelco_results"):
        frappe.reload_doc("engineering", "doctype", doctype, force=True)
