# Kobelco hourly LAB synchronisation plan

**Goal:** Run existing Kobelco sync hourly, only on juan.isambane.co.za and only while enabled.

**Architecture:** Add one hourly hook and a non-whitelisted wrapper calling existing sync_now. Keep the shared site Redis lock, API pagination, mapping merge, telemetry hashing and append-only results. Use native Scheduled Job Log for every hourly invocation and a sanitized rotating Kobelco log for all sync/discovery outcomes. Commit attempt status before returning a sanitized failure to Frappe's isolated scheduled-job executor so its rollback cannot erase the failed attempt or the last successful time. No new DocTypes or API endpoints.

**Constraints:** Branch juan; preserve existing changes. No MPI/WearCheck modifications, production operations, commits, pushes, dashboards, automatic Asset creation or historical telemetry rewrites. Existing enabled LAB credentials remain untouched. Registration targets only the single new LAB Scheduled Job Type; avoid full migrate/sync_jobs because unrelated pending migrations/jobs must remain untouched.

- [x] Write failing tests for guards/registration, success, paginated fleet, preservation/dedup, failure/recovery, unexpected safe errors, shared lock contention and native worker outcome containment.
- [x] Implement wrapper, shared attempt logging and hourly registration; run focused tests until green.
- [x] Run Kobelco suite, existing controller regressions and syntax/diff checks.
- [x] Register only new LAB job using Frappe insert_single_event; verify create_log, Hourly frequency, stopped flag, schedule due calculation, scheduler process lock and workers.
- [x] Verify an actual isolated LAB worker execution and record outcome without rewriting historical results; provide exact activation/verification commands and all changed files.
