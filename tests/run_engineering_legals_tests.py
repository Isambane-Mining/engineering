"""Run from the app root. Deliberately never initializes a Frappe site.

All DB, queue, email and HTTP use is blocked unless an individual test supplies
an explicit in-memory fixture. No production or LAB credentials are loaded.
"""

import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import frappe
import requests


class NoDatabase:
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        raise AssertionError(f"Unexpected database access: {name}")


def main():
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    with ExitStack() as stack:
        stack.enter_context(patch.object(frappe, "conf", frappe._dict()))
        stack.enter_context(patch.object(frappe, "db", NoDatabase()))
        stack.enter_context(patch.object(frappe, "flags", frappe._dict()))
        stack.enter_context(patch.object(frappe, "message_log", []))
        stack.enter_context(patch.object(frappe, "get_roles", return_value=[]))
        stack.enter_context(
            patch("frappe.translate.get_all_translations", return_value={})
        )
        for name in ("init", "connect", "sendmail", "enqueue"):
            stack.enter_context(
                patch.object(
                    frappe, name, side_effect=AssertionError(f"Blocked {name}")
                )
            )
        stack.enter_context(
            patch.object(
                requests.sessions.Session,
                "request",
                side_effect=AssertionError("Blocked HTTP"),
            )
        )
        suite = unittest.defaultTestLoader.discover(
            str(root), pattern="test_engineering_legals*.py"
        )
        suite.addTests(
            unittest.defaultTestLoader.loadTestsFromName(
                "engineering.engineering.doctype.engineering_legals.test_engineering_legals"
            )
        )
        suite.addTests(
            unittest.defaultTestLoader.loadTestsFromName(
                "engineering.engineering.page.machine_reliability.test_calculations"
            )
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
