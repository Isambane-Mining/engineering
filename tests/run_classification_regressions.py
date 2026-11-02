"""Offline combined-code checks: block ERP writes, HTTP, queues and email."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from contextlib import ExitStack
from unittest.mock import patch
import frappe

APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP))
MODULES=[
 'engineering.engineering.page.daily_availability_and_utilization_dashboard.test_tyre_damage',
 'engineering.engineering.page.daily_availability_and_utilization_dashboard.test_ownership_sections',
 'engineering.engineering.page.machine_reliability.test_calculations',
 'engineering.engineering.page.machine_reliability.test_problem_categories.TestProblemCategoryMatching',
 'engineering.engineering.page.reliability_engineering.test_reliability_engineering',
 'engineering.engineering.page.reliability_engineering.test_problem_machines',
 'engineering.engineering.page.monthly_tmm_assurance.test_grant_feedback',
 'engineering.engineering.page.monthly_tmm_assurance.test_monthly_tmm_assurance',
]

def blocked(*args,**kwargs):raise AssertionError('Unexpected external or ERP access')
class NoDB:
 def __getattr__(self,name):return blocked

if __name__=='__main__':
 import smtplib,requests
 with ExitStack() as stack:
  stack.enter_context(patch.object(frappe,'db',NoDB()))
  stack.enter_context(patch.object(frappe,'conf',frappe._dict()))
  stack.enter_context(patch.object(frappe,'flags',frappe._dict()))
  stack.enter_context(patch('frappe.translate.get_all_translations',return_value={}))
  for name in ('init','connect','sendmail','enqueue'):stack.enter_context(patch.object(frappe,name,side_effect=blocked))
  stack.enter_context(patch.object(requests.sessions.Session,'request',side_effect=blocked))
  stack.enter_context(patch.object(smtplib.SMTP,'connect',side_effect=blocked))
  suite=unittest.defaultTestLoader.loadTestsFromNames(MODULES)
  for pattern in ('test_failure_classification*.py','test_lab_classification_integration.py'):
   suite.addTests(unittest.defaultTestLoader.discover(str(APP/'tests'),pattern=pattern))
  result=unittest.TextTestRunner(verbosity=2).run(suite)
 sys.exit(not result.wasSuccessful())
