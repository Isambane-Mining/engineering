# Failure classification — LAB activation, 2 November 2026

Activated on `juan.isambane.co.za` in the existing running checkout `/home/juan/juan-bench/apps/engineering`. The prepared `juan` worktree changes were integrated in place with the newer LAB TMM Assurance, WhatsApp capture and site-specific Engineering Legals code. The running branch remains `feat/engineering-legals-site-configuration`. No checkout replacement, branch switch, reset, stash, commit, push or production operation was performed.

## Result

- The optional `failure_classification` Link is the only captured classification. The two former standard Select fields and their dependencies are removed from source and form metadata. Their physical database columns and every historical value remain untouched.
- Machine Reliability, its Reliability Engineering embedded view, queries and displayed details use the Link. Explicit classification takes precedence over complaint keywords; resolution-only matching remains additional repair work. Historical blank classifications retain keyword fallback. Existing interval/downtime calculations and permissions remain intact.
- Machine Reliability Settings now links to Breakdown Failure Classification masters. There are 20 active master/settings rows. Nine retained existing keyword rules and applicable inspection mappings; new keyword lists are blank. Legacy Other remains an inactive review row with its original keywords and inspection links. Ambiguous mappings are not guessed.
- ADT tyre/wheel cards and drill-down count unique non-cancelled Breakdown records with `failure_classification = Tyres / Wheels`, including rims, studs and bearings. Original roster, date/site/category, ownership, production/spare, Asset and permission rules are retained. Dozer tyre cards are removed from the shared renderer; Dozer hours/A&U cards, graphs and rows remain.
- Monthly TMM Assurance uses the Link in record population, classification counts, Pareto, details, action choices and PDF export. Its existing population windows, availability calculation, ownership, grouping and permissions are retained. Current TMM calculations/rendering helpers are consolidated in its main Page module.
- WhatsApp capture accepts an optional explicit master Link, validates supplied values and passes them to real PBM creation. It does not infer classification from message text. Planned-maintenance and book-back behavior remains intact.
- A pre-existing stale chart resize listener found during browser testing was fixed by destroying the prior Breakdown Analysis trend chart before replacing its SVG. Filters and calculations are unchanged; chart identity/filter retention tests pass.

## PDF keyword deployment

All 20 Failure Classifications have verified keywords saved on LAB.
The Machine Reliability API returns all 20 populated classifications.

The 20 classifications are already seeded in production.
No additional keyword-seeding patch is required.
The classification migration preserves existing custom keywords
and inspection links.

Inspection mappings:
- Wearcheck: Lubrication System
- PDS, Fire Suppression, FRCS: Safety Systems

Legacy Other remains inactive with its original keywords and inspection links.
No historical breakdown backfill is performed.

## Safety and activation

Source snapshots, starting hashes and dirty diffs for both checkouts are retained in `/home/juan/lab-classification-integration-20261102`. Unrelated navigation, custom permission fixtures and downtime-correction files match their starting hashes. The newer LAB features were retained rather than replacing LAB with the older juan checkout.

A full LAB database/config backup was completed **before migration**:

- `lab-before-classification.sql.gz` (about 1.2 GB compressed), protected in the snapshot directory.
- `lab-site-config-backup.json`, protected in the same directory.
- Gzip integrity check passed; SHA-256 is recorded in `database-backup.sha256`.

Only `engineering.patches.use_failure_classification` was pending. The first migration completed model/patch updates but lost a DB connection during fixture synchronization. A fresh connection was healthy; the idempotent migration retry completed successfully. The LAB app frontend build and cache clear passed. Only the LAB web master bound to `127.0.0.1:8007` was refreshed; no database/shared server was restarted.

## Actual verification

- **80 offline backend/controller regressions passed.**
- **12 disposable SQLite integration tests passed**, including permissions, saves, Link choices and PDF generation.
- **20 real LAB transaction-only tests passed**, including saving all 20 classifications, blank/cleared choices, existing record saves, site permissions, reliability APIs, real WhatsApp record creation, and a positive tyre KPI/drill-down identity check. All source writes were rolled back; temporary capture commits were suppressed.
- **8 TMM fixture-browser tests passed**, including actions, draft retention, conflict handling, drill-downs, exports and responsive layout.
- **15 live Cypress tests passed** across Machine Reliability, all three Reliability Engineering tabs, dashboard tyre cards/drill-downs, retired form controls, settings choices and TMM desktop/mobile views.
- Clean-process imports passed in forward and reverse order. Changed Python files compile; changed JavaScript parses; Git whitespace checks pass.
- A broader app compilation encountered the unchanged pre-existing `engineering/tyre_site_performance.py`, which contains JavaScript syntax. It was confirmed unchanged and left outside this task; it does not affect the verified report paths.

Live sample, **1–31 July 2026**, combined production/spare and existing in-house ownership scope:

| Site | ADT tyre/wheel count | Drill-down records |
| --- | ---: | ---: |
| Klipfontein | 0 | 0 |
| Koppie | 0 | 0 |

Historical classifications remain blank, so zero classified tyre counts are expected. No estimates are substituted.

IS545, 30 May–12 September 2026, Braking System: **7 direct complaints, 4 valid intervals, average 32.25 machine hours**, unchanged.

Live Koppie July TMM: seven groups and 20 master choices; record counts ADTs 154, Excavators 38, Drills 0, Graders 4, FELs 0, Dozers 22, Ancillary 22. Actual authorized live data exported successfully to a 200,199-byte PDF. The HTML/PDF and `activation-audit.json` are in the protected snapshot directory.

A SHA-256 comparison of every column in all **10,727** historical PBM records matches the pre-migration baseline. Both old physical columns are still present; neither old field is present in form metadata.

Final installed-app source scan: old field-name references remain only in migration metadata cleanup and tests asserting that the fields are absent. There are no remaining runtime queries, validators, forms, report/export accesses or capture writes using them. LAB stored Client Scripts, Server Scripts, SQL Reports, Custom Field dependencies and Property Setters showed no additional old-field dependencies.

## LAB pages

- https://juan.isambane.co.za/app/reliability-engineering
- https://juan.isambane.co.za/app/daily-availability-and-utilization-dashboard
- https://juan.isambane.co.za/app/monthly-tmm-assurance
- https://juan.isambane.co.za/app/machine-reliability-settings

The only remaining feature blocker is the inaccessible classification PDF for keyword seeding. Production remains untouched.
