"""Run Bell integration tests only on the designated isolated database."""

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

from engineering.tests.kobelco_test_support import (
    TEST_SITE,
    require_isolated_site,
)


def blocked(*args, **kwargs):
    raise AssertionError(
        "Unexpected network, background job, reconnect or commit in Bell tests."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=TEST_SITE)
    options = parser.parse_args()

    if options.site != TEST_SITE:
        parser.error("Bell tests may only run on the designated isolated site.")

    os.chdir(root.parents[1] / "sites")
    frappe.init(site=options.site)
    require_isolated_site()
    frappe.connect()
    frappe.set_user("Administrator")

    try:
        with ExitStack() as stack:
            stack.enter_context(
                patch("requests.sessions.Session.request", side_effect=blocked)
            )
            stack.enter_context(patch.object(frappe, "enqueue", side_effect=blocked))
            stack.enter_context(patch.object(frappe, "connect", side_effect=blocked))
            stack.enter_context(patch.object(frappe.db, "commit", side_effect=blocked))

            suite = unittest.defaultTestLoader.loadTestsFromName(
                "engineering.engineering.doctype.api_bell_settings.test_api_bell_settings"
            )

            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1

    finally:
        frappe.db.rollback()
        frappe.clear_document_cache("API Bell Settings", "API Bell Settings")
        frappe.destroy()


if __name__ == "__main__":
    sys.exit(main())
