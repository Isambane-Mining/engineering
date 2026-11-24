# MPI Phase 3 history implementation

Goal: manually import one mapped vehicle's trips, stops, parkings, idle periods, geozone visits and
daily distance summaries without changing MPI Results snapshots or saving raw endpoint responses.

Architecture: `MPI History Import` is the saved manual request and execution status. `MPI Activity History`
holds allowlisted normalized events and per-day distance summaries. A separate history controller reuses
the existing authenticated MPI client. Nothing is scheduled; no workspace/dashboard changes are needed.

Plan:
1. Inspect proven endpoint row schemas and activity report template names using read-only LAB calls.
2. Write mocked regressions for request parameters, parser shapes, dates, deduplication and permissions;
   observe failures before implementation.
3. Add history controller, two DocTypes, and manual Import History action. Keep snapshot behavior unchanged.
4. Run all MPI mocked tests, form tests and static checks, obtain a focused code review, and verify unrelated
   changed files against their initial hashes. Do not migrate, restart, commit or push.

## Contract

- One known settings mapping/IMEI per request; write access to settings and the request is required to queue.
- Date fields refer to inclusive UTC calendar dates, at most seven completed days. Future/current UTC days,
  invalid/reversed ranges and fractional or timezone-ambiguous inputs are rejected. Split into canonical
  daily half-open windows; pass `stop = exclusive_end - 1` to the API so adjacent requests share no second.
- Import endpoint calls are sequential: `run` with zones=0, `runstops`, `get_idle`, `ag_geozones`, `distance`.
  Only an explicitly requested optional activity report adds `reports_list` and `get_report`.
- No zones_mileage, geofencelist, get_status_and_distance, fuel/driver/device/admin calls or data storage.
- Use only existing snapshot agentid for the optional report's veh_id; never fetch/store driver/device data.
- Request/worker timeouts are inherited 5/20 seconds and 1800 seconds; cap rows at 2000 per endpoint/day and
  20000 per import. Redis lock per vehicle prevents overlapping workers from racing deterministic keys.
- Stable history keys use IMEI, kind and source start; geozones add name/group; reports add template ID.
  End corrections upsert the existing event. Daily summaries use IMEI and canonical UTC day.
- Source timestamps are UTC epoch seconds with explicit UTC ISO display fields. Intersecting source events
  retain their original bounds; events starting exactly at a window's exclusive end are omitted.
- Only typed, explicit activity fields are saved. Omitted optional metrics are identified in missing_fields,
  avoiding false zero measurements from Frappe numeric coercion. No addresses, sensors or response blobs.
- Each endpoint/day is parsed and saved atomically. A failed endpoint rolls back its batch, records a safe
  local error, and allows other endpoints/days to continue. Partial status and per-endpoint counts are visible.
- The history worker does not save settings or update current MPI Results/mapping links. History records
  resolve the selected Asset when imported; historical Asset links are not silently rewritten later.
- Normal user permission checks and request revision checks apply. Parameters cannot change after queuing;
  rerunning the same request is allowed and idempotent. Create another request to change the date range.

## Report shape

The audited activity report is not a `{code,data}` envelope: its root contains success, headers, data,
aggr and other presentation keys. Only the data subtree is considered, restricted to the requested
vehicle. Inspect template names and row keys first; reject unrecognized templates/shapes. Map only
row ts, te, length with matching agentid, discarding fn, nested data and presentation/fuel metadata.
Never map positional display columns or persist arbitrary report header/row fields.

LAB template-name inspection identified Mileage report, Trips and parkings, and Geozones report as
activity templates. Only Mileage report's returned row schema was verified; the other templates are
deliberately not imported. Its observed rows contain agentid, data, fn, length, te and ts. Grouping keys
are presentation labels, so identity is validated on each row. Open geozone visits have a null te.

## Activation and verification

No schema activation or live import is performed here. After review and a separately authorized migration,
open `/app/mpi-history-import`, create a request with a saved mapping IMEI and completed UTC dates, save,
and select Import History. Refresh Import Status to see counts without losing user edits. Open
`/app/mpi-activity-history` for records. Reimport the same/overlapping days to verify stable record counts.
An optional activity report needs an existing MPI Results agentid, populated by the existing snapshot sync.

Offline tests will mock all HTTP and database boundaries. Existing MPI Phase 1/2 tests and their form
refresh test must remain green. No real credentials appear in fixtures.

Verified on branch `juan`: 54 mocked Python tests and both Node form tests passed. Python syntax,
DocType JSON field/order consistency, JavaScript syntax and `git diff --check` passed. Baseline SHA-256
comparison confirmed all 72 pre-existing modified/untracked files were preserved except the intended
MPI settings JavaScript addition. Existing history Asset links are also preserved on explicit reimports;
previously unlinked history may acquire the selected mapping's Asset.

Reproduce the offline tests from `apps/engineering`:

```bash
/home/juan/juan-bench/env/bin/python -B -m unittest engineering.tests.test_mpi engineering.tests.test_mpi_phase2 engineering.tests.test_mpi_history
node engineering/tests/test_mpi_settings_form.cjs
node engineering/tests/test_mpi_history_form.cjs
```

Schema-backed validation and a live import remain pending activation. No migrations, restarts, commits,
pushes or live history imports were performed.
