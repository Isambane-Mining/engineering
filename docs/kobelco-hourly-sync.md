# Kobelco hourly synchronisation — LAB, 20 November 2026

Implemented and activated on branch `juan`, only on `juan.isambane.co.za`.

## Behaviour

The Engineering hourly scheduler hook calls `engineering.controllers.kobelco.run_hourly_sync`. The wrapper checks the exact site name before accessing Settings or HTTP and returns immediately outside LAB. Within LAB it skips when API Kobelco Settings is disabled. Existing enabled credentials were retained; no credentials or production settings were changed.

The wrapper calls the existing `sync_now()` implementation. There is no second API import path. Existing Basic Authentication, read-only GET requests, advertised fleet pagination, preservation of manual Asset mappings, source-JSON snapshot hashing and deduplication remain in use. No Assets are created automatically. No historical measurement, timestamp, original JSON or checksum is overwritten. Mapping discovery fields may refresh normally.

The same site-scoped Redis lock is shared by scheduled sync, manual Sync Now and Fetch Fleet. Lock contention performs no API call, records the skipped attempt as a failure with a clear message and does not change the last successful time. Frappe additionally prevents enqueueing the same scheduled job while it is queued/running. No new DocTypes or schema migrations were added. Manual Sync Now remains available.

## Monitoring and errors

Every hourly scheduler invocation uses Frappe's existing Scheduled Job Log with logging enabled: Start followed by Complete or Failed. The sanitized result/counts are retained in its Debug Log. Disabled/non-LAB invocations are successful no-ops, not sync attempts, and do not overwrite the last actual sync status.

Every sync/discovery attempt writes Started and a success/failure/lock-contention outcome to the rotating `sites/juan.isambane.co.za/logs/kobelco.log` (also mirrored to the bench log). Only constructed status/count messages and sanitized errors are logged. Settings documents, credentials, configured URLs, API response bodies and original exception tracebacks are not logged by this integration.

Settings continues to show Last Sync Timestamp, Status and Message. Failed attempts preserve Last Successful Sync. The scheduled wrapper commits the completed attempt status before passing a sanitized error to Frappe's scheduled-job executor. Otherwise Frappe's automatic failure rollback would erase the failed attempt. Frappe contains that error within this job, records Failed, and continues other jobs. Unexpected exceptions are converted to a fixed safe message outside the original exception handler so native traceback-with-locals does not retain HTTP/settings frames.

Scheduled Job Logs have Frappe's normal retention policy; file logs rotate. They are operational history, not permanent archives. Settings timestamps retain the existing Frappe site-clock convention; telemetry timestamps remain UTC with the existing Johannesburg formatter.

## Activation commands

Already completed in LAB. These commands target only LAB and only the new scheduled job. Run from `/home/juan/juan-bench` if registration must be repeated:

```sh
bench --site juan.isambane.co.za clear-cache
bench --site juan.isambane.co.za execute frappe.core.doctype.scheduled_job_type.scheduled_job_type.insert_single_event \
  --args '["Hourly", "engineering.controllers.kobelco.run_hourly_sync"]'
bench --site juan.isambane.co.za enable-scheduler
bench --site juan.isambane.co.za scheduler resume
```

Keep **Enabled** checked in API Kobelco Settings with the existing valid credentials. To stop Kobelco alone, uncheck Enabled; do not disable the whole site's scheduler. Normal future Frappe migrations also register hooks, but no full migrate or global job sync was run for this change because unrelated pending work must remain untouched.

## Verification commands

```sh
bench --site juan.isambane.co.za scheduler status --verbose
bench --site juan.isambane.co.za execute frappe.utils.scheduler.is_schduler_process_running
bench --site juan.isambane.co.za execute frappe.client.get_list \
  --kwargs '{"doctype":"Scheduled Job Type","filters":{"method":"engineering.controllers.kobelco.run_hourly_sync"},"fields":["name","method","frequency","create_log","stopped","last_execution"]}'
```

Expected: scheduler enabled; process running; exactly one matching job; frequency Hourly; create_log 1; stopped 0. The LAB job created here is `864e6hud85`.

Inspect recent attempts:

```sh
bench --site juan.isambane.co.za execute frappe.client.get_list \
  --kwargs '{"doctype":"Scheduled Job Log","filters":{"scheduled_job_type":"864e6hud85"},"fields":["name","creation","status","debug_log"],"order_by":"creation desc","limit_page_length":5}'
tail -n 30 sites/juan.isambane.co.za/logs/kobelco.log
```

To run only this job immediately through Frappe's scheduled-job executor (synchronous CLI verification; does perform a real read-only vendor sync):

```sh
bench --site juan.isambane.co.za trigger-scheduler-event engineering.controllers.kobelco.run_hourly_sync
```

Inspect its Scheduled Job Log and Settings afterward; the native executor contains failures, so CLI exit success alone does not establish API sync success. Do not trigger all hourly events for a Kobelco check.

Frappe Hourly means the next site-clock hour, processed at the next scheduler tick, not exactly 3600 seconds after a manual run. LAB's existing system timezone is Asia/Kolkata, so its hourly boundaries correspond to Johannesburg minute 30. No global timezone was changed. The default queue's existing 300-second job timeout remains in effect; a very slow/large future fleet would fail rather than silently truncate pages. Current live fleet is two machines on one page.

## Verified results

- Scheduler enabled, not paused, not disabled and outside maintenance mode.
- Scheduler process lock held by the running scheduler; site active for hourly execution; two workers available.
- Registered exactly one new LAB Scheduled Job Type, Hourly, create_log 1, stopped 0, default queue. Other scheduled job registrations were not synchronized or removed.
- An actual queued LAB worker execution completed successfully: log `923im3p4pd`, two machines, one page, two new source snapshots, zero unmapped. The original two historical Results were verified unchanged; total Results became four.
- An initial verification was accidentally overlapped by a test rerun, resulting in lock contention and a Failed job log (`86es7b66tg`). The test process was stopped, its transaction rolled back, and the isolated worker retry succeeded. The failed attempt remained visible and preserved the previous successful time. Final tests were rerun separately.
- 48 Kobelco tests passed, including eight new scheduler tests: hourly registration/due time, disabled gate, non-LAB gate, multi-page success, mapping preservation/dedup and manual path, API failure/recovery, real shared Redis lock contention, safe unexpected errors and native worker failure containment.
- 91 existing controller regression tests and eight telemetry formatter checks passed. Python/JavaScript syntax and `git diff --check` passed.
- Temporary test credentials/rows were rolled back. Existing Asset links, historical JSON and measurements were preserved. No MPI/WearCheck edits, dashboards, production operations, commits or pushes.

The LAB web master on port 8007 was gracefully reloaded to load shared logging changes for manual requests. Workers load the scheduled module normally; no bench-wide service restart was needed.

## Changed files

- `engineering/hooks.py`: one hourly entry; existing hooks retained.
- `engineering/controllers/kobelco.py`: LAB wrapper, sanitized attempt logging and contention monitoring around the existing shared sync path.
- `engineering/controllers/test_kobelco_scheduler.py`: new scheduler tests.
- `tests/run_kobelco_tests.py`: includes the new tests.
- `docs/superpowers/plans/2026-11-20-kobelco-hourly.md`: implementation plan.
- `docs/kobelco-hourly-sync.md`: this operational record.
