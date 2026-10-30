# Monthly TMM Assurance — Grant feedback, LAB handover

Route: `/app/monthly-tmm-assurance` in the Engineering workspace. This extends the existing page and persistent action DocTypes.

## Confirmed population and counting unit

The user clarified **all breakdown events overlapping the reporting month**, including repaired/closed events and events carried in from earlier months. This supersedes the earlier raised-in-month interpretation; it is not an outstanding-only population.

- One count is one **Plant Breakdown or Maintenance record**, identified by its stable `name`. The ERP has one Problem Category and description per breakdown record; it does not identify individual faults within a multi-fault description.
- Eligibility uses the recorded **`breakdown_start_datetime` / `resolved_datetime` interval**, not database creation time. The calendar month runs from its first day 00:00 inclusive to the next month 00:00 exclusive. Include starts within that month, plus earlier starts that remain open or resolve strictly after month start. Exclude earlier events ending exactly at month start and events starting at next month start. Each stable record counts once **per month it overlaps**, regardless of duration, shift/hourly entries or duplicate rows. Instantaneous events recorded within the month also count once.
- Cancelled records (`docstatus == 2`) and Planned Maintenance are excluded. Legacy blank downtime types retain the established breakdown interpretation. `exclude_from_au` does **not** remove a record from defect counts: it governs measured downtime, not this confirmed all-breakdowns population.
- Open and repaired/closed records are both included when eligible. The recorded resolution date determines whether an earlier event continued into the month. Missing Pre-Use, non-production shifts and absence of planning do not affect counts. Table status is explicitly **current**; no month-end outstanding status is substituted for interval selection.
- `Breakdown History` overwrites its start/closure rows rather than keeping an immutable reopening event stream. It is not suitable for reliably reconstructing all historical open states; selection uses the recorded start/resolution interval and does not invent historical reopening gaps. Changes that overwrote an earlier closure cannot be reconstructed reliably from this source.
- Count group uses the PBM's captured equipment category, falling back to permission-visible Asset category when missing. A machine need not still be at the Site today. Count population covers the Site's breakdown records; the availability graph separately retains the approved in-house fleet basis. Unmappable equipment groups appear in a separate review section and are not silently discarded.

## Availability calculation remains unchanged

The source is **Daily A&U Engine Dashboard**, with **85% A & U**, **Production + Swing/Spare Machines**, **Isambane & Excavo Assets**.

`daily_availability_and_utilization_dashboard.fetch_grouped_data` calls `availability_and_utilisation_engine.get_data` at the 100% basis, rebuilds shift/category summaries and applies the selected percentage basis. Monthly Assurance takes the shift rows (`indent == 3`, no formula rows), groups using the dashboard's `CATEGORY_MAP`, calls the Engine's `build_summary_row` on the hour fields and `apply_au_percentage_basis(..., '85% A & U')`. No machine percentages or three-month values are averaged.

The Engine's available hours are `max(work_hours, max(required_hours - pbm_total_downtime, 0))`. Its summary aggregates valid shift available/required hours with its existing invalid Pre-Use/A&U exclusions, rounding and 85% scaling. No valid required-hour denominator produces **N/A**; a genuine zero produces **0.0%**. Existing above-100% values remain visible.

Sources remain Monthly Production Planning/children and exceptions, Asset, Pre-Use Hours/Pre-use Assets, Plant Breakdown or Maintenance, stored A&U shifts, Startup and Fatigue spesification, machine exclusions and invalid shift exclusions. The Engine and existing dashboard were not changed.

| Group | Dashboard categories |
|---|---|
| ADTs | ADT and dashboard aliases |
| Excavators | Excavator and dashboard aliases |
| Drills | Drills |
| Graders | Grader |
| FELs | Loader |
| Dozers | Dozer and dashboard aliases |
| Ancillary | Service Truck, TLB, Water Bowser, Diesel Bowsers |

The main table is replaced by three individual adjacent monthly bars per group, with month legend, values and percent axis. Reporting month defaults to the previous completed month and has two preceding months. Submission remains due on the third day of the following month. Only Site and Reporting Month are report filters. Selecting an equipment group changes its counts, details and actions.

## Canonical categories and capture

`engineering/engineering/problem_categories.py` is the canonical definition for validation, report counting and action selection. The PBM Select metadata mirrors it; a regression test enforces equality. Native capture and the WhatsApp log picker read that metadata.

Existing categories: Brakes; Steering; Engine / Starting; Hydraulics; Electrical; Cooling; Transmission / Drivetrain; Tyres / Wheels; Air Conditioning; Other.

Added individually: **FRCS; Stop Blocks; Machine Locks; Bowl Lock Pins; Brake Test; Steps / Handrail**. Brakes and Brake Test remain separate. FRCS has no invented expansion. Cylinders was not added or automatically mapped.

The existing PBM dropdown remains the capture interface. New Breakdown records require a valid category in both native metadata and server validation. Explicit corrections require controlled values. Unchanged legacy blanks/unsupported values can survive unrelated edits and closure. A narrowly scoped Select-validation override permits that unchanged legacy category while validating all other Select fields normally. No historical records were backfilled or reclassified.

The existing WhatsApp Message Log Create/Update button now requests the same controlled category for Book Down and passes the explicit selection to new-record validation. Book Back does not request recategorisation. New creation uses normal PBM insert permissions; the entrypoint checks log read permission. No duplicate capture panel, new hooks, scheduler or messaging was added.

Existing Machine Reliability keyword defaults are preserved. Its settings can explicitly configure additional controlled categories without inventing keywords or changing historical classifications. The Monthly report never uses keyword inference.

## Count Pareto and 80% details

- Counts deduplicate record identity, not elapsed hours, snapshots, shifts or days. Blank and unsupported Problem Category values are unresolved categorisation and excluded from the Pareto denominator, with their original values available for review.
- Sort descending by count; ties follow canonical category order. Top 10 is the default. Omitted-category and record counts are explicit; they are not merged into Other. Cumulative percentages always use the full categorised denominator, so the visible line may stop below 100%.
- The 80% reference is on the cumulative axis. Priority is the smallest leading set reaching/exceeding 80%, including the crossing category, calculated before limiting the chart. Additional priority categories beyond 10 are identified and exposed by Show all categories.
- The full category list includes all 16 categories, including zero-count safety categories. Each category can show its original records. “Breakdowns contributing to the first 80%” expands to Category, Machine, original linked Reference, Reported Date, Description and current Status. Unresolved categorisation has its own permission-filtered review list and original-record links.
- Completeness reconciles `categorised + unresolved = group total`. Original editing workflows and existing permissions perform corrections; this report does not automatically change categories.

## Persistent corrective actions

The existing Site / Reporting Month / Equipment Group parent identity, normal Frappe saves, optimistic version conflict handling and dirty protection remain. Save saves every dirty group; row changes retain drafts; filter changes ask before discarding; browser close/refresh warns. PDF saves pending actions first and stops on failure.

The existing `cause` field is retained and relabelled **Category**, preserving all saved data. New actions select canonical categories. Unchanged legacy action labels remain selectable for review and survive saves using stable child row names. New arbitrary values are rejected. Actions outside the priority set remain accessible.

A new optional child Link field **`breakdown_reference`** points to Plant Breakdown or Maintenance. “Add action” on a breakdown row fills its reference/category without duplicating its description. Reference validation checks read permission and matching Site/equipment group. Unknown or foreign action-row identities are rejected.

## Permissions and PDF

All report/PDF endpoints validate the action scope and Location read permission. Source read permissions and record-level checks apply. The reused Engine performs raw SQL, so completeness checks refuse a report if source restrictions hide participating data, including submitted in-house Assets, rather than presenting a partial-fleet percentage as complete. New action writes use normal Frappe create/write permissions; direct Desk/REST saves validate scope/category/reference too. No existing permission fixtures were changed by this feature.

PDF uses shared server-generated SVG images, not browser chart JavaScript. It includes Site, period, due date, confirmed population and unit, three-month availability, and each relevant group's top-10 Pareto, full category counts, 80% records, unresolved records and saved actions. It is independent of current selection. Tables repeat headings and rows avoid splitting. The full category count table uses two columns of categories to keep the report compact. Empty states are explicit.

## Files affected

- `engineering/engineering/page/monthly_tmm_assurance/`: Page JS/JSON/API, shared SVG/PDF rendering, date/group helpers, confirmed population/count/priority helpers and tests.
- `engineering/engineering/problem_categories.py`: canonical category tuple and legacy-compatible policy.
- `engineering/engineering/doctype/plant_breakdown_or_maintenance/`: Select options, server category validation and updated tests.
- `engineering/engineering/doctype/machine_reliability_settings/machine_reliability_settings.py`: canonical re-export and compatible explicit configuration validation.
- `engineering/engineering/doctype/whatsapp_breakdown_message_log/`: category prompt/pass-through on the existing create path.
- `engineering/engineering/doctype/monthly_tmm_assurance_action/`: retained action fields plus optional breakdown reference.
- `engineering/engineering/doctype/monthly_tmm_assurance_actions/`: immutable scope, controlled new categories, legacy preservation and reference checks.
- `tests/test_monthly_tmm_assurance_browser.py`: browser interactions and screenshots.
- `engineering/engineering/workspace/engineering/engineering.json`: original feature's workspace shortcut retained.
- This handover and `docs/superpowers/plans/2026-10-30-monthly-tmm-grant-feedback.md`.

Unrelated changes to `engineering/fixtures/custom_docperm.json` and `downtime_correction_dashboard.py` were preserved.

## Verification and limitations

**Final result: 95 tests passed** (17 calculation/controller/presentation, 12 Frappe integration, 8 Chromium, 58 existing regressions). JavaScript syntax, Python compilation, changed JSON parsing and `git diff --check` also passed.

Validation uses the disposable SQLite Frappe site `/tmp/production-summary-validation-tmm/sites/summary-test.local`, with isolated Redis on port 16879. No existing working-bench site credentials or database were used.

- Calculation/presentation tests cover unchanged availability math, rollover, N/A/zero, overlap boundaries, repaired/closed carry-ins, earlier open events, one count per overlapping month across a year boundary, cancellation/deduplication, canonical options, unresolved denominators, ties, zero counts and priority sets exceeding 10.
- Real Frappe tests cover schema imports/Page asset loading; typed PBM controller insert/save and Select validation for all 16 values and legacy closure; count selection; read-only/Site/source/Asset restrictions; persistence/conflicts; old action labels; optional references and foreign-child rejection.
- Actual Frappe/wkhtmltopdf export is rendered and inspected. The eight-page compact fixture PDF contains seven group charts and their saved actions, full counts and priority records. Extracted text and rendered blue/orange pixels verify every chart.
- Chromium checks use the actual page JS and native Desk CSS, with mocked controls/API. They cover the seven selectable groups, two filters, dirty drafts/filter cancellation/async controls, conflicts, export-after-save, stale responses, priority details, category inspection, safety-category action creation, unresolved review and legacy action options. Screenshots were visually compared with the reference.
- Existing isolated Engineering regression suite is included. The older full-environment PBM test module was updated for the new policy but was not run against the working site.
- Full authenticated Desk verification on a configured LAB site and MariaDB activation remain after import; the browser harness is not claimed as authenticated verification. A framework permission-path deprecation warning does not fail the tests.

Re-run from the app root:

```bash
/home/juan/juan-bench/env/bin/python -m unittest engineering.engineering.page.monthly_tmm_assurance.test_grant_feedback engineering.engineering.page.monthly_tmm_assurance.test_monthly_tmm_assurance -v
TMM_TEST_SITES=/tmp/production-summary-validation-tmm/sites /home/juan/juan-bench/env/bin/python -m unittest engineering.engineering.page.monthly_tmm_assurance.test_integration -v
/home/juan/juan-bench/env/bin/python tests/test_monthly_tmm_assurance_browser.py
/home/juan/juan-bench/env/bin/python tests/run_engineering_legals_tests.py
git diff --check
```

Artifacts with test-only fixtures: `/tmp/monthly-tmm-assurance-validation/report.pdf`, `pdf-availability.png`, `pdf-pareto-actions.png`, `page-desktop.png`, `page-mobile.png`; logs use `grant-*.log` in the same directory.

## Exact LAB activation commands

Set `LAB_SITE` to the actual LAB site first. These targeted imports avoid a full migrate importing unrelated pending permission fixtures. No activation commands were run on the existing bench site.

```bash
cd /home/juan/juan-bench
export LAB_SITE='YOUR-LAB-SITE-NAME'
bench --site "$LAB_SITE" reload-doc engineering doctype plant_breakdown_or_maintenance
bench --site "$LAB_SITE" reload-doc engineering doctype monthly_tmm_assurance_action
bench --site "$LAB_SITE" clear-cache
```

On a supervised **dedicated LAB bench**, reload the changed Python modules:

```bash
bench restart --web
```

For a `bench start` development session, its development process reload/restart handles Python changes. Refresh Desk after cache clearing so PBM/WhatsApp metadata and the standard Page scripts reload. No asset bundle build is required; no bundled asset or hook changed. The parent action schema, Page registration and workspace remain those of the existing implementation.

The clarified overlap population is implemented consistently in counts, 80% details, review/drill-down lists and PDF. Availability calculation functions and dashboard calls were not changed. No schema change was needed for this population correction; its updated Python modules require the LAB web reload described above. No unresolved population or category decision blocks this version. Cylinders treatment remains unconfirmed and unchanged. No production access, deployment, push, merge, backfill, scheduler job or email sending was performed.

Latest overlap-correction verification: 95 tests passed (17 unit/controller/presentation, 12 Frappe integration, 8 Chromium harness, 58 existing regressions). Fresh logs: `/tmp/monthly-tmm-assurance-validation/overlap-*.log`. Actual exported PDF contains earlier-started repaired events and all seven group charts; charts were rendered and the updated detail page inspected. No additional schema reload or asset build is required for this Python-only population correction; reload supervised LAB web processes and clear the LAB site cache.
