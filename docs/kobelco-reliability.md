# Kobelco reliability: safe diagnostics and isolated tests

Implemented on branch `juan`, LAB only, 20 November 2026. No live API imports were triggered for validation. Authentication, Asset mapping logic, telemetry extraction, hourly registration/frequency and snapshot history are unchanged. Existing unrelated work, MPI and WearCheck were not edited. No commits or pushes.

## Root changes

Previously `_run()` discarded unexpected exception details, while `run_hourly_sync()` raised only the generic replacement. The failed setup verification also overlapped a test transaction against live LAB Settings, producing competing DB/Redis lock acquisition. The exact original DB exception was not retained; the new diagnostics make future failures distinguishable without exposing raw exception text.

Failures now carry structured metadata:

```json
{
  "stage": "lock_settings",
  "exception_class": "QueryTimeoutError",
  "database_error_code": 1205,
  "description": "Database lock-wait timeout.",
  "attempt_timestamp_utc": "2026-11-20T10:00:00+00:00"
}
```

Stages identify lock acquisition/savepoint creation, client initialization, fleet retrieval, telemetry normalization, Settings locking, mapping update, Settings save, snapshot storage and monitoring updates. The scheduled boundary additionally identifies Settings lookup, sync dispatch and commit failure.

Recognized database codes are recovered from exception causes/wrapped driver exceptions, not parsed from raw error messages. Codes 1205, 1213, 1062, 2002, 2003, 2006 and 2013 have fixed descriptions. Both mysqlclient (`MySQLdb`) and PyMySQL exceptions are supported. Unknown errors retain their exception class and stage with a fixed safe description; unknown codes remain null. Only explicitly safe Kobelco messages or strictly formatted HTTP status codes may appear as descriptions.

The same diagnostic is written to the rotating Kobelco log, the scheduler's Debug Log, Last Sync Message and an Error Log titled **Kobelco Sync Failure**. Error Log records are constructed directly with only diagnostic JSON, avoiding automatic request/job metadata, headers, URLs, external error reporting and traceback locals.

Frappe normally places a contextual traceback into a failed Scheduled Job Log's Details. A narrowly scoped `on_change` handler replaces that Details value with diagnostic JSON within the same log transaction. It applies only to Failed records for `engineering.controllers.kobelco.run_hourly_sync` in LAB. Other jobs and production records are left alone. This changes diagnostic storage, not scheduling or execution frequency. Old job logs are not rewritten.

Failure preserves Last Successful Sync. A subsequent successful sync restores Success and replaces Last Sync Message; previous Error Logs remain historical evidence. The shared Redis lock key and timing remain unchanged.

## Secondary failures and limits

Rollback and logging failures cannot propagate the original exception/context. An uncertain connection is closed and discarded. When possible, a new connection is opened without elevating the current user, allowing monitoring and native failure logging to continue; the old connection is never committed.

If database reconnection also fails, only safe file/debug diagnostics can remain available. Database-backed Last Sync/Error Log updates cannot be guaranteed during a database outage, and a native Scheduled Job Log may remain Start until service is restored. If the file logger is also unavailable, logging is best-effort; its failure never leaks the original error or commits uncertain import work. No automatic API retry or historical rewrite was added.

## Test isolation

The old runner defaulted to live LAB. It now defaults exclusively to **kobelco-test.localhost**, database **kobelco_test**, and refuses every other site before opening a DB connection. Fixtures independently enforce the designated site/database, `allow_tests`, an explicit `kobelco_isolated_tests` marker, and both scheduler-disable/pause flags before their first write. Direct fixture invocation against LAB is rejected too.

No live Settings, credentials, Assets or Results were copied. A private, socket-only MariaDB instance was provisioned under `/tmp/kobelco-test-db-p0ycuxv3`, with its own Frappe/ERPNext test site. Only the three tested Engineering Kobelco schemas and their required roles/module metadata were prepared; unrelated Engineering fixtures/patches were not imported. Test scheduling is disabled. The live LAB database account lacked database-creation privileges, so no LAB/production database administration was performed.

Normal tests use mocked API responses. The runner blocks unmocked HTTP, background enqueues, commits and unplanned reconnections. Tests that verify a transaction boundary explicitly mock that boundary. Scheduler tests substitute only the wrapper's LAB-site constant; they never rename the actual connection/site/database, so live worker Redis keys and caches are not reused. Frappe Redis keys are namespaced by database; `kobelco_test` is distinct from live `juan`.

Fixtures create their own minimal real Asset rows for Link/permission checks and roll back Settings, encrypted credentials, mappings and snapshots. Frappe's Error Log is MyISAM and does not roll back; fixtures and runner explicitly remove only the Error Log IDs they created. Test logs go to the isolated site's log directory, not the live LAB site's Kobelco log. Frappe's bench-wide log mirror may contain isolated-test entries.

Do not run the old LAB-based test workflow. Live worker verification is a separate operational activity; none was requested or triggered for these changes.

## Running tests

From `apps/engineering`, with the isolated site's database running:

```sh
/home/juan/juan-bench/env/bin/python tests/run_kobelco_tests.py
/home/juan/juan-bench/env/bin/python tests/run_controller_regressions.py
node tests/test_kobelco_telemetry_format.cjs
```

This command is deliberately refused and exits before connecting:

```sh
/home/juan/juan-bench/env/bin/python tests/run_kobelco_tests.py --site juan.isambane.co.za
```

The local private MariaDB instance is temporary and is stopped after validation. To reuse its retained data while `/tmp` still exists, start it in a separate terminal:

```sh
/usr/sbin/mariadbd --no-defaults \
  --datadir=/tmp/kobelco-test-db-p0ycuxv3/data \
  --socket=/tmp/kobelco-test-db-p0ycuxv3/mysql.sock \
  --pid-file=/tmp/kobelco-test-db-p0ycuxv3/server.pid \
  --log-error=/tmp/kobelco-test-db-p0ycuxv3/server.log \
  --skip-networking --innodb-buffer-pool-size=64M
```

For a durable new isolated environment, provision a dedicated test database/site using appropriate test-server administration credentials. Do not restore LAB data or point it at database `juan`. First-time provisioning on that test server follows:

```sh
# Run only if this designated test site/database does not already exist.
bench new-site kobelco-test.localhost --db-name kobelco_test --install-app erpnext
bench --site kobelco-test.localhost set-config allow_tests 1
bench --site kobelco-test.localhost set-config kobelco_isolated_tests 1
bench --site kobelco-test.localhost set-config disable_scheduler 1
bench --site kobelco-test.localhost set-config pause_scheduler 1
bench --site kobelco-test.localhost execute engineering.tests.kobelco_test_support.prepare_site
```

`prepare_site` is guarded and was validated on the private test site. It is an explicit provisioning action, never an automatic test-fixture schema migration. The runner has no fallback to LAB if the test database is unavailable.

## Validation

- **61 Kobelco tests passed** on the isolated database with mocked HTTP, including timeout1205, both drivers, safe stage/class/timestamp reporting, secret-bearing exceptions, native Scheduled Job Log filtering, preserved last success, recovery clearing failure status, lock namespace isolation, LAB refusal and secondary rollback/logging failure/reconnection behavior.
- **91 controller regressions passed**, without DB/HTTP/background work.
- **Eight telemetry formatting checks passed**; telemetry implementation was not changed.
- Modified Python parsing and `git diff --check` passed.
- Post-test private-site checks found zero test Settings, encrypted credentials, Assets, mappings, Results or owned Error Logs.
- Read-only LAB comparison confirmed original historical Results unchanged, mapping identities/Asset links unchanged, enabled/base URL/username unchanged and no test rows in LAB.
- No live worker verification/import was triggered. The LAB web process was gracefully reloaded to load manual-request diagnostics. No hourly job re-registration, scheduler configuration change or production operation was performed.

## Files changed

Modified existing files (including previously uncommitted Kobelco files):

- `engineering/controllers/kobelco.py`
- `engineering/hooks.py` — scoped Scheduled Job Log diagnostic handler only; hourly hook unchanged
- `engineering/controllers/test_kobelco.py`
- `engineering/controllers/test_kobelco_scheduler.py`
- `engineering/engineering/doctype/api_kobelco_settings/test_api_kobelco_settings.py`
- `tests/run_kobelco_tests.py`
- `docs/kobelco-hourly-sync.md` — points to the replacement test workflow

Added:

- `engineering/controllers/test_kobelco_diagnostics.py`
- `engineering/tests/kobelco_test_support.py`
- `docs/superpowers/plans/2026-11-20-kobelco-reliability.md`
- `docs/kobelco-reliability.md`

The new isolated site configuration/data are local test infrastructure outside the app repository. They contain no copied live Kobelco credentials and must not be committed.
