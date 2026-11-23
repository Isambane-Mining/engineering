"""Run mocked Kobelco tests only on the designated isolated site, never LAB."""
import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
import frappe
from engineering.tests.kobelco_test_support import TEST_SITE, require_isolated_site


def blocked(*args, **kwargs):
    raise AssertionError("Unmocked HTTP, background jobs and commits are forbidden in Kobelco tests")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=TEST_SITE)
    options = parser.parse_args()
    if options.site != TEST_SITE:
        parser.error("Only the designated isolated Kobelco test site is allowed; LAB is forbidden")
    os.chdir(root.parents[1] / "sites")
    frappe.init(site=options.site)
    require_isolated_site()  # Check config before opening a DB connection.
    frappe.connect()
    frappe.set_user("Administrator")
    initial_logs = set(frappe.get_all("Error Log", filters={"method": "Kobelco Sync Failure"}, pluck="name"))
    try:
        with ExitStack() as stack:
            stack.enter_context(patch("requests.sessions.Session.request", side_effect=blocked))
            stack.enter_context(patch.object(frappe, "enqueue", side_effect=blocked))
            stack.enter_context(patch.object(frappe, "connect", side_effect=blocked))
            stack.enter_context(patch.object(frappe.db, "commit", side_effect=blocked))
            suite = unittest.defaultTestLoader.loadTestsFromNames([
                "engineering.controllers.test_kobelco",
                "engineering.controllers.test_kobelco_scheduler",
                "engineering.controllers.test_kobelco_diagnostics",
                "engineering.engineering.doctype.api_kobelco_settings.test_api_kobelco_settings",
            ])
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1
    finally:
        created_logs = set(frappe.get_all("Error Log", filters={"method": "Kobelco Sync Failure"}, pluck="name")) - initial_logs
        frappe.db.rollback()
        if created_logs:
            frappe.db.delete("Error Log", {"name": ["in", list(created_logs)]})
        frappe.clear_document_cache("API Kobelco Settings", "API Kobelco Settings")
        frappe.destroy()


if __name__ == "__main__":
    sys.exit(main())
