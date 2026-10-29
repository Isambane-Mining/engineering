"""Offline regression runner: no site initialization, DB, queues, HTTP or SMTP."""

import argparse
import smtplib
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import frappe
import requests

MODULES = [
    "engineering.api.test_fleet_health_email",
    "engineering.api.test_fleet_health_privacy",
    "engineering.api.test_private_delivery_boundaries",
    "engineering.api.test_controller_compatibility",
    "engineering.engineering.page.daily_availability_and_utilization_dashboard.test_tyre_damage",
    "engineering.engineering.page.daily_availability_and_utilization_dashboard.test_ownership_sections",
    "engineering.engineering.page.machine_reliability.test_calculations",
    "engineering.engineering.page.machine_reliability.test_problem_categories.TestProblemCategoryMatching",
    "engineering.engineering.page.reliability_engineering.test_reliability_engineering",
    "engineering.engineering.page.reliability_engineering.test_problem_machines",
]


class NoDatabase:
    def __getattr__(self, name):
        raise AssertionError("Unexpected database access: " + name)


def blocked(*args, **kwargs):
    raise AssertionError("Live site, transport or background action blocked")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Also audit pre-existing Short Haul and site-dependent Machine Reliability tests",
    )
    options = parser.parse_args()
    with ExitStack() as stack:
        stack.enter_context(patch.object(frappe, "db", NoDatabase()))
        stack.enter_context(patch.object(frappe, "conf", frappe._dict()))
        stack.enter_context(patch.object(frappe, "flags", frappe._dict()))
        stack.enter_context(
            patch("frappe.translate.get_all_translations", return_value={})
        )
        for name in ("init", "connect", "sendmail", "enqueue"):
            stack.enter_context(patch.object(frappe, name, side_effect=blocked))
        stack.enter_context(
            patch.object(requests.sessions.Session, "request", side_effect=blocked)
        )
        stack.enter_context(patch.object(smtplib.SMTP, "connect", side_effect=blocked))
        modules = list(MODULES)
        if options.extended:
            modules += [
                "engineering.engineering.page.daily_availability_and_utilization_dashboard.test_short_haul",
                "engineering.engineering.page.machine_reliability.test_machine_reliability",
                "engineering.engineering.page.machine_reliability.test_problem_categories.TestProblemCategoryAPI",
            ]
        suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    # Give worktree sources precedence over the installed editable LAB checkout.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
