"""Run focused A&U arithmetic and browser regressions without a site or network.

Run from the app root with the bench Python and PYTHONPATH pointing here.
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
        if name.startswith('_'):
            raise AttributeError(name)
        raise AssertionError(f'Unexpected database access: {name}')


def main():
    root = Path(__file__).resolve().parent
    with ExitStack() as stack:
        for name, value in [('conf', frappe._dict()), ('db', NoDatabase()),
                            ('flags', frappe._dict()), ('message_log', [])]:
            stack.enter_context(patch.object(frappe, name, value))
        stack.enter_context(patch.object(frappe, 'get_roles', return_value=[]))
        stack.enter_context(patch('frappe.translate.get_all_translations', return_value={}))
        for name in ('init', 'connect', 'sendmail', 'enqueue'):
            stack.enter_context(patch.object(frappe, name, side_effect=AssertionError(f'Blocked {name}')))
        stack.enter_context(patch.object(requests.sessions.Session, 'request',
                                        side_effect=AssertionError('Blocked HTTP')))
        suite = unittest.defaultTestLoader.discover(str(root), pattern='test_au_*.py')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
