# MPI multi-vehicle history implementation plan

Goal: select several saved MPI vehicle mappings on one manual request, sharing its existing 1–7 completed UTC day range.

Approach: extend MPI History Import with an MPI History Vehicle child table. Keep the legacy IMEI field optional for previously saved single-vehicle requests. Snapshot selected plate/Asset display values; validate every selection against saved settings when saving/queuing. Freeze selections once queued. One parent job processes batches of five vehicles sequentially, retaining the existing per-vehicle Redis lock, endpoint/day transactions and IMEI history keys. A failed vehicle cannot stop subsequent vehicles. Per-vehicle status/outcomes are persisted independently without changing the parent's form revision.

Bounds: at most 500 vehicles, five per batch, 2000 records per endpoint/day and 20000 per vehicle. Queue timeout scales by selected count using the existing 1800-second allowance per vehicle. This deliberately permits fleet jobs to run longer while bounding both work and memory. Only one job is enqueued; batches do not enqueue further jobs. Date and HTTP timeout limits remain unchanged.

Selection: a permission-checked settings method exposes IMEI, plate and Asset only. Add Selected Vehicles uses a searchable multi-select; Add All Mapped Vehicles includes saved mapping rows with a confirmed Asset link and skips already selected rows. Individually selected known vehicles may have no Asset, preserving existing single-vehicle behavior. Duplicate, malformed, unknown and ambiguous mapping IMEIs are rejected server-side. Mapping changes do not rewrite saved display values on queued requests or historical Asset links.

Work:
- [ ] Add mocked failing tests for selection validation, parent/child progress, partial failure, legacy requests, one queued job and repeated imports across vehicles.
- [ ] Add child schema and extend parent model/controller; keep parser and current snapshot behavior unchanged.
- [ ] Add selected/all actions and refresh child status by saved row identity, preserving unsaved selection/date edits.
- [ ] Run all offline MPI Python/form tests, syntax/schema checks, inspect focused diff and compare pre-existing dirty files with initial hashes.

No migrations, restarts, live imports, commits or pushes. Schema activation and schema-backed validation remain pending explicit activation.
