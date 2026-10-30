# Monthly TMM Assurance — Grant feedback implementation record

Extend the existing LAB page and saved action DocTypes. Preserve unrelated fixture, workspace and downtime-correction edits. No production connection, deployment, push or merge.

## Confirmed decision

The user clarified the earlier answer: **all distinct breakdown events overlapping the reporting calendar month**, including events started earlier and repaired/closed events. Select starts within the month, or earlier starts still open/resolved strictly after month start; start must be before the next month. Deduplicate stable names per reporting month. Outstanding-at-month-end selection is not used. Table status remains explicitly current.

## Completed implementation

- [x] Shared browser/PDF three-month grouped availability SVG, seven selectable groups, native styling, legend/axis/value labels and N/A versus zero. Original Daily Dashboard calculation/defaults/aggregation retained.
- [x] Canonical 16-category definition and mirrored PBM Select metadata; new-record/category-correction validation; unchanged historical blanks/unsupported values survive closure/unrelated edits. No Cylinders option, guessed FRCS expansion, automatic backfill or text inference.
- [x] Existing native PBM capture dropdown and WhatsApp Book Down path use the same controlled options. WhatsApp maintenance detection stays server-owned; planned maintenance and Book Back avoid unnecessary categorisation prompts. New insert uses ordinary PBM create permission.
- [x] Confirmed monthly population, stable-name deduplication, cancellation/planned-maintenance exclusion, A&U-excluded defects retained, current status, captured/fallback equipment grouping and explicit unmapped-group review.
- [x] Count Pareto top 10, complete categorised denominator, omitted counts, 80% reference and crossing set before the display limit. Canonical ties; full category view includes zero-count safety categories. Category and 80% record drilldowns plus unresolved review links share the same records.
- [x] Persistent actions retain scope, ownership/dates/statuses, dirty/conflict handling and stable child identities. New categories controlled; unchanged legacy labels preserved. Optional validated breakdown references and Add action from a record.
- [x] Full PDF uses shared SVG charts and all relevant groups' counts, full category breakdown, priority records, unresolved rows and saved actions. Compact category tables, repeated headings and explicit empty states.
- [x] Server scope/source/read/write/print/reference permission checks, including complete participating Asset access before a fleet measurement is generated.
- [x] Isolated Frappe schema/document/controller/Page/PDF tests, Chromium interaction checks, existing regressions, syntax/compilation/JSON/diff checks, visual inspection and exact LAB commands in docs/monthly-tmm-assurance.md.

## Review and verification ledger

Independent read-only review found one Important issue: permission-filtered Assets could silently alter the fleet denominator. A real Asset-specific User Permission test reproduced it before the fix. Completeness checks now refuse that scope before Engine access; the regression passes. No other Important/Critical findings were reported.

Actual PDF regression caught the initial availability SVG's percentage root sizing yielding a blank exported graph. Fixed intrinsic SVG dimensions for image export; text/pixel tests verify real rendered charts. The final compact test report is eight pages for seven groups.

A real controller persistence test exercises all 16 captured values, new blank rejection, and unchanged legacy blank/unsupported Select saves. Unrelated PBM workflow side effects are mocked only within that disposable test. Existing full-environment PBM tests were updated for the new requirement but not run against any working site.

Final result: 95 tests passed (17 unit/controller/presentation, 12 Frappe integration, 8 browser, 58 regressions), plus syntax/compilation/JSON/diff checks. Commands are recorded in the handover and `/tmp/monthly-tmm-assurance-validation/grant-*.log`.

## Rulings and limits

- User-specified existing LAB checkout retained; unrelated work was not reverted or committed.
- Updated population uses the recorded start/resolution interval against local calendar midnight boundaries, with one count per stable record per overlapping month. Earlier repaired/closed and open carry-ins are tested, including exact boundaries and year rollover. Availability functions and calls remain unchanged.
- A&U downtime exclusions do not remove records from the confirmed all-breakdowns count. Count fleet covers Site records; availability retains its explicitly labelled in-house ownership basis.
- Reopening history is not reconstructed: the selected monthly population uses recorded start/resolution intervals, not outstanding status at month-end. Stored Breakdown History is not immutable; overwritten closures/reopening gaps cannot be reconstructed reliably and are not invented.
- Source restrictions fail closed rather than produce unlabelled partial-fleet availability. This can deny the report to users who lack complete source access, without granting any new permissions.
- Cylinders treatment remains unconfirmed and unchanged. No category inference or historical data rewrite was added.
- Authenticated Desk and MariaDB activation checks remain after import into the configured LAB site. Browser checks here are an explicit harness with mocked controls/API; actual schema/controller/PDF tests use a guarded disposable SQLite site.

## Overlap clarification verification

New overlap and database tests failed against the raised-only implementation. The shared population helper and permission-filtered query were updated; the same helper results feed group counts, chart/80% records, drill-downs and PDF. The database regression checks that carried-in closed records appear in the complete report/PDF HTML while pre-month closures do not. Actual PDF export includes earlier-started repaired events and the updated population label. No availability formula, scheduler, schema or permission fixture was changed by this correction.

Latest overlap-correction verification: 95 tests passed (17 unit/controller/presentation, 12 Frappe integration, 8 Chromium harness, 58 existing regressions). Fresh logs: `/tmp/monthly-tmm-assurance-validation/overlap-*.log`. Actual exported PDF contains earlier-started repaired events and all seven group charts; charts were rendered and the updated detail page inspected. No additional schema reload or asset build is required for this Python-only population correction; reload supervised LAB web processes and clear the LAB site cache.
