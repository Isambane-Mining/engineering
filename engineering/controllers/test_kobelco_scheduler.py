"""Isolated-site scheduler checks; real DB/Redis, mocked vendor HTTP, rollback."""
import json
import unittest
from unittest.mock import Mock, patch

import frappe
from engineering.engineering.doctype.api_kobelco_settings import test_api_kobelco_settings as _integration
from engineering.controllers.test_kobelco import equipment


# Only borrow the fixture lifecycle; unittest should collect this class's own tests.
class TestKobelcoScheduler(unittest.TestCase):
    _cleanup_isolated_transaction = _integration.TestKobelcoIntegration._cleanup_isolated_transaction

    def setUp(self):
        _integration.TestKobelcoIntegration.setUp(self)
        # Exercise the LAB-only wrapper on the isolated connection. Do not rename
        # frappe.local.site: that would reuse live site Redis keys and caches.
        gate = patch.object(self.api, "LAB_SITE", frappe.local.site)
        gate.start()
        self.addCleanup(gate.stop)

    def scheduled(self):
        # Workers commit at their transaction boundary; keep tests rollback-only.
        with patch.object(frappe.db, 'commit'):
            return self.api.run_hourly_sync()

    def test_hourly_hook_and_due_time(self):
        from engineering import hooks
        from frappe.core.doctype.scheduled_job_type.scheduled_job_type import ScheduledJobType
        method = 'engineering.controllers.kobelco.run_hourly_sync'
        self.assertIn(method, hooks.scheduler_events['hourly'])
        job = ScheduledJobType({'doctype': 'Scheduled Job Type', 'method': method,
                                'frequency': 'Hourly', 'last_execution': '2026-11-20 10:15:00'})
        self.assertEqual(str(job.get_next_execution()), '2026-11-20 11:00:00')

    def test_non_lab_guard_precedes_settings_or_http(self):
        for site in ('example.test', 'isambane.co.za', None):
            with self.subTest(site=site), patch.object(frappe.local, 'site', site), \
                    patch.object(frappe.db, 'get_single_value', side_effect=AssertionError('settings read outside LAB')):
                self.assertEqual(self.scheduled()['skipped'], 'not_lab')
        self.get.assert_not_called()

    def test_disabled_does_not_sync_or_change_last_attempt(self):
        self.settings.enabled = 0
        self.settings.save()
        before = frappe.db.get_single_value('API Kobelco Settings', 'last_sync_timestamp')
        self.assertEqual(self.scheduled()['skipped'], 'disabled')
        self.get.assert_not_called()
        self.assertEqual(frappe.db.get_single_value('API Kobelco Settings', 'last_sync_timestamp'), before)

    def test_paginated_success_preserves_mapping_and_deduplicates(self):
        serials = ('TEST-KOBELCO-13', 'TEST-KOBELCO-58')
        payloads = [
            {'Fleet': {'@version': '1', '@snapshotTime': '2026-11-20T06:00:00Z',
                       'Equipment': [equipment(serials[0])], 'Links': [{'rel': 'next', 'href': '/Fleet/2'}]}},
            {'Fleet': {'@version': '1', '@snapshotTime': '2026-11-20T06:00:00Z',
                       'Equipment': [equipment(serials[1])]}}
        ]
        bodies = [json.dumps(p) for p in payloads]
        self.get.side_effect = lambda *a, **k: Mock(status_code=200, text=bodies[1 if a[0].endswith('/2') else 0],
            json=lambda: payloads[1 if a[0].endswith('/2') else 0])
        first = self.scheduled()
        self.assertEqual((first['created'], first['pages']), (2, 2))
        settings = frappe.get_single('API Kobelco Settings')
        mapping = next(r for r in settings.machine_mappings if r.serial_number == serials[0])
        mapping.asset = self.assets[0]
        settings.save()
        before = frappe.get_all('Kobelco Results', filters={'serial_number': ['in', serials]}, fields=['*'], order_by='name')
        second = self.scheduled()
        self.assertEqual((second['created'], second['skipped']), (0, 2))
        after = frappe.get_all('Kobelco Results', filters={'serial_number': ['in', serials]}, fields=['*'], order_by='name')
        self.assertEqual(after, before)
        self.assertEqual(after[0].raw_response in bodies, True)
        self.assertEqual(frappe.get_single('API Kobelco Settings').last_sync_status, 'Success')
        self.assertEqual(frappe.db.get_value('Kobelco Machine Mapping', mapping.name, 'asset'), self.assets[0])
        self.assertTrue(self.api.sync_now()['ok'])  # manual path still works

    def test_api_failure_preserves_last_success_and_recovers(self):
        self.assertTrue(self.scheduled()['ok'])
        previous = frappe.get_single('API Kobelco Settings').last_successful_sync
        self.get.return_value = Mock(status_code=401, text='DO-NOT-LOG-CREDENTIAL')
        with self.assertLogs(frappe.logger('kobelco'), level='INFO') as logs:
            with self.assertRaisesRegex(self.api.KobelcoError, 'Authentication failed'):
                self.scheduled()
        self.assertIn('Authentication failed', '\n'.join(logs.output))
        self.assertNotIn('DO-NOT-LOG-CREDENTIAL', '\n'.join(logs.output))
        failed = frappe.get_single('API Kobelco Settings')
        self.assertEqual(failed.last_sync_status, 'Failed')
        self.assertIsNotNone(failed.last_sync_timestamp)
        self.assertNotIn('DO-NOT-LOG-CREDENTIAL', failed.last_sync_message)
        self.assertEqual(failed.last_successful_sync, previous)
        self.get.return_value = Mock(status_code=200, json=lambda: {'Equipment': [equipment('TEST-KOBELCO-13')]})
        self.assertTrue(self.scheduled()['ok'])
        self.assertEqual(frappe.get_single('API Kobelco Settings').last_sync_status, 'Success')

    def test_shared_lock_blocks_hourly_and_manual_without_http(self):
        # thread_local=False gives the contender a separate token in the same thread.
        lock = frappe.cache.lock(frappe.cache.make_key('kobelco_manual_sync'), timeout=30, thread_local=False)
        with lock:
            with self.assertRaisesRegex(self.api.KobelcoError, 'already running'):
                self.scheduled()
            manual = self.api.sync_now()
            self.assertFalse(manual['ok'])
            self.assertEqual(manual['diagnostic']['stage'], 'acquire_sync_lock')
            self.assertEqual(manual['diagnostic']['exception_class'], 'LockError')
        self.get.assert_not_called()
        self.assertEqual(frappe.get_single('API Kobelco Settings').last_sync_status, 'Failed')

    def test_unexpected_failure_is_sanitized_and_status_is_committed(self):
        with patch.object(self.api, 'sync_now', side_effect=RuntimeError('DO-NOT-LOG-CREDENTIAL')), \
                patch.object(frappe.db, 'rollback'), patch.object(frappe.db, 'commit') as commit:
            with self.assertRaises(self.api.KobelcoError) as caught:
                self.api.run_hourly_sync()
            self.assertNotIn('DO-NOT-LOG-CREDENTIAL', str(caught.exception))
            self.assertIsNone(caught.exception.__context__)
            self.assertEqual(frappe.get_single('API Kobelco Settings').last_sync_status, 'Failed')
            commit.assert_called_once()

    def test_native_executor_contains_failure_and_marks_job_failed(self):
        from frappe.core.doctype.scheduled_job_type.scheduled_job_type import ScheduledJobType
        job = ScheduledJobType({'doctype': 'Scheduled Job Type', 'method': 'engineering.controllers.kobelco.run_hourly_sync', 'frequency': 'Hourly'})
        self.get.return_value = Mock(status_code=503, text='DO-NOT-LOG-CREDENTIAL')
        original_rollback = frappe.db.rollback
        def rollback(*args, **kwargs):
            if kwargs.get('save_point'):
                return original_rollback(*args, **kwargs)
        with patch.object(frappe.db, 'commit'), patch.object(frappe.db, 'rollback', side_effect=rollback), \
                patch.object(job, 'log_status') as log_status:
            job.execute()  # must contain the exception, allowing other jobs to run
        self.assertEqual([call.args[0] for call in log_status.call_args_list], ['Start', 'Failed'])
        self.assertEqual(frappe.get_single('API Kobelco Settings').last_sync_status, 'Failed')
