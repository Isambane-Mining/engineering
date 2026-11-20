"""Run Kobelco tests against LAB; HTTP mocked and all test records rolled back."""
import os
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
import frappe


def main():
    os.chdir(root.parents[1] / "sites")
    frappe.init(site="juan.isambane.co.za")
    frappe.connect()
    frappe.set_user("Administrator")
    try:
        suite = unittest.defaultTestLoader.loadTestsFromNames([
            "engineering.controllers.test_kobelco",
            "engineering.controllers.test_kobelco_scheduler",
            "engineering.engineering.doctype.api_kobelco_settings.test_api_kobelco_settings",
        ])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    finally:
        frappe.db.rollback()
        frappe.destroy()


if __name__ == "__main__":
    sys.exit(main())
