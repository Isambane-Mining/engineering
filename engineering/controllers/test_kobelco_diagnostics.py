"""Reliability regressions on the private site; every vendor response is mocked."""
import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import frappe
from MySQLdb import OperationalError
from engineering.engineering.doctype.api_kobelco_settings import test_api_kobelco_settings as _integration

SECRET = "password=PRIVATE-PASSWORD Authorization: Basic PRIVATE-HEADER https://private.invalid/SECRET-PATH SQL-PARAMETER"


class TestKobelcoDiagnostics(unittest.TestCase):
    setUp = _integration.TestKobelcoIntegration.setUp
    _cleanup_isolated_transaction = _integration.TestKobelcoIntegration._cleanup_isolated_transaction

    def test_lock_timeout_has_code_stage_safe_error_log_and_preserves_success(self):
        before_logs = frappe.db.count('Error Log', {'method': 'Kobelco Sync Failure'})
        self.assertTrue(self.api.sync_now()['ok'])
        previous = frappe.get_single('API Kobelco Settings').last_successful_sync
        error = frappe.QueryTimeoutError(OperationalError(1205, SECRET))
        error.__cause__ = error.args[0]
        with patch.object(self.api, '_settings', side_effect=error), \
                self.assertLogs(frappe.logger('kobelco'), level='INFO') as logs:
            result = self.api._run(self.settings, store_results=True)
        self.assertFalse(result['ok'])
        diagnostic = result['diagnostic']
        self.assertEqual(diagnostic['stage'], 'lock_settings')
        self.assertEqual(diagnostic['exception_class'], 'QueryTimeoutError')
        self.assertEqual(diagnostic['database_error_code'], 1205)
        self.assertIn('lock-wait timeout', diagnostic['description'])
        self.assertIsNotNone(datetime.fromisoformat(diagnostic['attempt_timestamp_utc']).tzinfo)
        stored = frappe.get_all('Error Log', filters={'method': 'Kobelco Sync Failure'}, fields=['error'])
        self.assertTrue(stored)
        self.assertIn(diagnostic, [json.loads(row.error) for row in stored])
        for secret in ('PRIVATE-PASSWORD','PRIVATE-HEADER','SECRET-PATH','SQL-PARAMETER'):
            self.assertNotIn(secret, str(result) + str(stored) + str(logs.output) + str(frappe.debug_log))
        failed = frappe.get_single('API Kobelco Settings')
        self.assertEqual(failed.last_successful_sync, previous)
        self.assertEqual(failed.last_sync_status, 'Failed')
        self.assertIn('1205', failed.last_sync_message)
        self.assertTrue(self.api.sync_now()['ok'])
        recovered = frappe.get_single('API Kobelco Settings')
        self.assertEqual(recovered.last_sync_status, 'Success')
        self.assertNotIn('1205', recovered.last_sync_message)
        self.assertEqual(frappe.db.count('Error Log', {'method': 'Kobelco Sync Failure'}), before_logs + 1)

    def test_unexpected_errors_report_the_actual_processing_stage_without_raw_text(self):
        cases = [('_discover', 'update_mappings'), ('_store_snapshot', 'store_snapshots')]
        for function, stage in cases:
            with self.subTest(stage=stage), patch.object(self.api, function, side_effect=RuntimeError(SECRET)):
                result = self.api._run(self.settings, store_results=True)
            self.assertFalse(result['ok'])
            self.assertEqual(result['diagnostic']['stage'], stage)
            self.assertEqual(result['diagnostic']['exception_class'], 'RuntimeError')
            self.assertIsNone(result['diagnostic']['database_error_code'])
            self.assertNotIn('PRIVATE', str(result))

    def test_known_error_type_does_not_make_arbitrary_exception_text_safe(self):
        with patch.object(self.api, '_discover', side_effect=self.api.KobelcoError(SECRET)):
            result = self.api._run(self.settings, store_results=True)
        self.assertFalse(result['ok'])
        self.assertNotIn('PRIVATE', str(result))
        self.assertNotIn('https://', result['message'])
        self.assertEqual(result['diagnostic']['exception_class'], 'KobelcoError')

    def test_native_scheduled_job_and_error_logs_keep_only_safe_diagnostics(self):
        job = frappe.get_doc({'doctype': 'Scheduled Job Type',
                              'method': 'engineering.controllers.kobelco.run_hourly_sync',
                              'frequency': 'Hourly'}).insert(ignore_permissions=True)
        rollback = frappe.db.rollback
        def rollback_savepoint_only(*args, **kwargs):
            # The wrapper commits its status before native failure rollback. Keep
            # that boundary simulated so this test remains one rollback-only unit.
            if kwargs.get('save_point'):
                return rollback(*args, **kwargs)
        with patch.object(self.api, 'LAB_SITE', frappe.local.site), \
                patch.object(self.api, '_discover', side_effect=RuntimeError(SECRET)), \
                patch.object(frappe.db, 'commit'), \
                patch.object(frappe.db, 'rollback', side_effect=rollback_savepoint_only):
            job.execute()
        log = frappe.get_all('Scheduled Job Log', filters={'scheduled_job_type': job.name},
                             fields=['status', 'details', 'debug_log'])[0]
        self.assertEqual(log.status, 'Failed')
        self.assertEqual(json.loads(log.details)['stage'], 'update_mappings')
        self.assertNotIn('Traceback', log.details)
        self.assertIn('update_mappings', log.debug_log)
        self.assertIn('RuntimeError', log.debug_log)
        self.assertIn('attempt_timestamp_utc', log.debug_log)
        for token in ('PRIVATE-PASSWORD', 'PRIVATE-HEADER', 'SECRET-PATH', 'SQL-PARAMETER'):
            self.assertNotIn(token, log.details + log.debug_log)

    def test_worker_diagnostic_payload_has_no_original_exception_context(self):
        with patch.object(self.api, 'LAB_SITE', frappe.local.site), \
                patch.object(self.api, 'sync_now', side_effect=RuntimeError(SECRET)), \
                patch.object(frappe.db, 'rollback'), patch.object(frappe.db, 'commit'):
            with self.assertRaises(self.api.KobelcoError) as caught:
                self.api.run_hourly_sync()
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn('PRIVATE', str(caught.exception))
        payload = json.loads(frappe.debug_log[-1].split('Kobelco hourly sync: ', 1)[1])
        self.assertEqual(payload['diagnostic']['stage'], 'sync_dispatch')
        self.assertEqual(payload['diagnostic']['exception_class'], 'RuntimeError')


class TestKobelcoIsolation(unittest.TestCase):
    def test_fixture_refuses_live_lab_before_writes(self):
        from engineering.tests.kobelco_test_support import require_isolated_site
        fixture = _integration.TestKobelcoIntegration('test_password_is_encrypted_and_connection_test_does_not_import')
        with patch.object(frappe.local, 'site', 'juan.isambane.co.za'), \
                patch.object(frappe.db, 'savepoint', side_effect=AssertionError('Live test write attempted')):
            with self.assertRaisesRegex(RuntimeError, 'LAB is forbidden'):
                fixture.setUp()

    def test_test_lock_namespace_cannot_collide_with_live_lab(self):
        from engineering.tests.kobelco_test_support import require_isolated_site
        require_isolated_site()
        isolated = frappe.cache.make_key('kobelco_manual_sync')
        with patch.dict(frappe.local.conf, {'db_name': 'juan'}):
            live = frappe.cache.make_key('kobelco_manual_sync')
        self.assertNotEqual(isolated, live)

    def test_rollback_and_logging_failures_cannot_expose_context_or_commit_partial_work(self):
        from engineering.controllers import kobelco
        fake_db = Mock()
        fake_db.get_single_value.return_value = 1
        fake_db.rollback.side_effect = RuntimeError(SECRET)
        fake_db.close.side_effect = RuntimeError(SECRET)
        with patch.object(frappe.local, 'db', fake_db), \
                patch.object(kobelco, 'LAB_SITE', frappe.local.site), \
                patch.object(kobelco, 'sync_now', side_effect=RuntimeError(SECRET)), \
                patch.object(frappe, 'logger', side_effect=RuntimeError(SECRET)):
            with self.assertRaises(kobelco.KobelcoError) as caught:
                kobelco.run_hourly_sync()
            self.assertNotIn('PRIVATE', str(caught.exception))
            self.assertIsNone(caught.exception.__context__)
            self.assertIsNone(frappe.local.db)
        fake_db.commit.assert_not_called()
        fake_db.close.assert_called_once()

    def test_import_rollback_failure_detaches_connection_before_returning(self):
        from engineering.controllers import kobelco
        fake_db = Mock()
        fake_db.rollback.side_effect = RuntimeError(SECRET)
        with patch.object(frappe.local, 'db', fake_db), \
                patch.object(kobelco, 'KobelcoClient') as client:
            client.return_value.fetch_fleet.side_effect = RuntimeError(SECRET)
            result = kobelco._run(Mock(), store_results=True)
            self.assertFalse(result['ok'])
            self.assertEqual(result['diagnostic']['stage'], 'fetch_fleet')
            self.assertNotIn('PRIVATE', str(result))
            self.assertIsNone(frappe.local.db)
        fake_db.commit.assert_not_called()

    def test_rollback_failure_can_restore_a_fresh_safe_connection_for_monitoring(self):
        from engineering.controllers import kobelco
        old, fresh = Mock(), Mock()
        old.rollback.side_effect = RuntimeError(SECRET)
        def reconnect(*, set_admin_as_user):
            self.assertFalse(set_admin_as_user)
            frappe.local.db = fresh
        with patch.object(frappe.local, 'db', old), patch.object(frappe, 'connect', side_effect=reconnect):
            self.assertTrue(kobelco._safe_rollback())
            self.assertIs(frappe.local.db, fresh)
        old.close.assert_called_once()
        old.commit.assert_not_called()
        fresh.connect.assert_called_once()

    def test_database_codes_are_retained_for_both_supported_mariadb_drivers(self):
        from engineering.controllers import kobelco
        from pymysql.err import OperationalError as PyMySQLError
        for driver in (OperationalError, PyMySQLError):
            with self.subTest(driver=driver.__module__):
                error = frappe.QueryTimeoutError(driver(1205, SECRET))
                diagnostic = kobelco._diagnostic(error, 'lock_settings', '2026-11-20T10:00:00+00:00')
                self.assertEqual(diagnostic['database_error_code'], 1205)
                self.assertNotIn('PRIVATE', str(diagnostic))

    def test_native_log_filter_does_not_change_other_jobs(self):
        from engineering.controllers import kobelco
        doc = Mock(status='Failed', scheduled_job_type='unrelated-job', details='original traceback')
        with patch.object(kobelco, 'LAB_SITE', frappe.local.site), \
                patch.object(frappe.db, 'get_value', return_value='frappe.email.queue.flush'), \
                patch.object(frappe.db, 'set_value', side_effect=AssertionError('Unrelated log changed')):
            kobelco.sanitize_scheduled_job_log(doc)
        self.assertEqual(doc.details, 'original traceback')

    def test_actual_lab_gate_skips_the_isolated_test_site(self):
        from engineering.controllers import kobelco
        from engineering.tests.kobelco_test_support import require_isolated_site
        require_isolated_site()
        with patch.object(frappe.db, 'get_single_value', side_effect=AssertionError('Settings must not be read')):
            self.assertEqual(kobelco.run_hourly_sync()['skipped'], 'not_lab')
