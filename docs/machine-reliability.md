# Machine Reliability (Phase 1)

LAB: https://juan.isambane.co.za/app/reliability-engineering
Legacy entry: /app/machine-reliability redirects to the first tab.
Settings: /app/machine-reliability-settings

Read-only analysis of existing Plant Breakdown or Maintenance and Engineering Legals records. No AI, document extraction, outside API or duplicate failure records.

## Configuration

System Manager, Engineering Manager and Engineering Area Manager can edit Machine Reliability Settings. The ten broad categories match the optional Problem Category dropdown on Plant Breakdown or Maintenance. Each category contains editable comma/newline-separated words or phrases and exact Engineering Legals test-section names (one per line). Category names stay fixed; migrations preserve keyword edits for retained categories and merge retired category terms/test mappings into Other. User keywords extend the selected category using OR. All Problems without extra words includes all breakdown/maintenance text.

Matching is case-insensitive and uses word boundaries; whitespace and hyphens between phrase words are equivalent. When a category is selected, a matching manual Problem Category identifies the direct complaint. Blank historical categories use the existing text rules. A different manual category suppresses category-keyword matches in the reason; configured matches in its resolution remain additional work. User-entered extra words can still extend direct-complaint searching to other categories. Records are processed once, so manual and text matches never add duplicate records. Matches in the complaint take precedence over resolution-only matches. Keyword search cannot establish a diagnosis, test outcome or accident cause. Broad words and negated statements can still match; inspect the displayed matched terms and source text.

## Scope and calculations

- Dates are inclusive calendar dates, using breakdown start or legal document start date. Missing dates cannot be included. Events must start inside the period; earlier ongoing breakdowns are not added to this event-cohort report.
- Site uses the historical event field, including machines that have since moved. Category uses current Asset metadata. Fleet lookup uses the same dates/site/category and permitted historical records.
- The API requires read access to breakdowns, Engineering Legals and Asset. Source queries use Frappe get_list and assigned Location scope. Only identity/category metadata for Assets linked to already permitted events is read separately, to avoid current-location permissions rewriting historical scope. Source document access is still checked when opening its form.
- Problem count is unique matching breakdown/maintenance records. Manual-category complaints and direct keyword complaints on Breakdown records are failures; resolution-only matches and Planned Maintenance records never create failure intervals. Orange markers include planned work and resolution-only repair work.
- Frequency uses consecutive direct failures per Asset ID within the period. Both meter readings must be positive and finite, strictly increasing, and their delta cannot exceed elapsed calendar hours. Missing/zero/decreasing/unchanged/implausible gaps are excluded and flagged. The next comparison uses the immediate predecessor, never bridges an invalid reading. Machine comparison averages are weighted only by that machine's valid intervals. The overview average uses all valid intervals across machines, never cross-machine subtraction.
- Average standing time is the arithmetic mean of valid completed direct breakdown record durations. Overlapping records remain in this average and are flagged. Reversed or incomplete intervals are excluded; valid zero-duration records remain eligible. Source exclude_from_au flags are shown; raw source timestamps, not stored breakdown_hours, determine this report's durations.
- Unique standing time is separate: merge valid completed direct intervals per machine, clipped to the selected dates. Unassigned records cannot contribute unique machine time. It describes the event cohort above, not all downtime overlapping the window.
- Top 10 all faults bypasses problem matching only; it retains dates/site/category/fleet and Breakdown type. Top 10 selected problem uses direct Breakdown complaints only.
- Tests use the configured section mapping. Services always use dated Machine Service Records for the selected machines, independently of problem text. Schedules do not establish completed services. Legal document fields do not establish pass/fail, detailed repairs or meter readings. Those values remain unavailable. Hour-mode timeline lists events without readings separately by date.

## Limits and verification

The retained detailed-record APIs use server-side pagination (50 rows by default, maximum 100). Each source query is bounded at 20,000 rows and rejects larger scopes before calculating totals; date ranges are limited to five years. Charts show up to 1,000 events/intervals/machines and disclose truncation; all accepted source records contribute to summaries. Narrow filters for complete chart coverage. Queries have date/site indexes.

Run on LAB:

```
bench --site juan.isambane.co.za run-tests --module engineering.engineering.page.machine_reliability.test_calculations
bench --site juan.isambane.co.za run-tests --module engineering.engineering.page.machine_reliability.test_machine_reliability
bench build --app engineering
```

API integration tests read LAB history and temporarily create a user and Location permission inside a rolled-back transaction with welcome emails disabled. They test a moved machine, site isolation, unassigned records, pagination, extra terms and source limits. Browser tests are tests/ui/machine_reliability.cy.js; use the dedicated config with RELIABILITY_SESSION_FILE pointing to a private temporary LAB session JSON. Do not commit session credentials. The Cypress launcher needs ELECTRON_RUN_AS_NODE unset when run from an Electron host.

## Changed files

- `engineering/engineering/page/machine_reliability/`: `__init__.py`, `machine_reliability.json`, `machine_reliability.js`, `machine_reliability.py`, `calculations.py`, `test_calculations.py`, `test_machine_reliability.py`.
- `engineering/engineering/doctype/machine_reliability_settings/`: `__init__.py`, `machine_reliability_settings.json`, `machine_reliability_settings.py`.
- `engineering/engineering/doctype/machine_reliability_category/`: `__init__.py`, `machine_reliability_category.json`, `machine_reliability_category.py`.
- `engineering/patches/seed_machine_reliability_settings.py` and `engineering/patches.txt`.
- `engineering/engineering/workspace/engineering/engineering.json`.
- `engineering/public/css/engineering.css`.
- `tests/ui/machine_reliability.config.cjs` and `tests/ui/machine_reliability.cy.js`.
- `docs/machine-reliability.md` and `docs/superpowers/plans/2026-10-21-machine-reliability.md`.

## Current layout

Reliability Engineering has one main tab navigation with three peer views: Machine Reliability (default), Breakdown Analysis and Problem Machines. The Reliability Engineering heading stays above the tabs. Machine Reliability remains a single Overview dashboard inside its tab. It retains all seven filters, six compact KPI cards, the interactive date/machine-hour timeline, source-record dialogs, and data-quality checks. Events without machine-hour readings remain available in the timeline's expandable list. Breakdown Analysis and Problem Machines reuse the existing report implementations without nested tabs. Each dashboard keeps its own filters and results when switching tabs; unchanged Problem Machines results keep their existing chart mounted.


Detailed Records markup, tab handlers, table pagination state and unused table renderers/styles have been removed from the frontend. Shared table styling is retained for the timeline's list of events without readings. Shared backend calculations and APIs, including detailed records and frequency projections, remain unchanged for compatibility and tests. No calculation, keyword or permission rule changed.

The known IS545 difference between the original export (23 complaints, 18 usable gaps, average 18.22 hours) and LAB (7 qualifying direct breakdowns, 4 usable gaps, average 32.25 hours) is caused by incomplete LAB history. No calculations were altered and no missing records were imported.

## Combined report changes

- `engineering/engineering/page/reliability_engineering/reliability_engineering.js`: coordinator and optional mount for the existing analysis.
- `engineering/engineering/page/machine_reliability/machine_reliability.js`: legacy route redirect.
- `engineering/engineering/page/reliability_engineering/reliability_engineering.js`: existing Machine Reliability implementation as a reusable dashboard.
- `engineering/public/css/engineering.css`: outer tabs and responsive spacing.
- `engineering/engineering/workspace/engineering/engineering.json`: single combined report entry.
- `tests/ui/machine_reliability.cy.js`, `tests/ui/problem_machines.cy.js`: combined entry, independent filters, redirects, access, timeline and responsive checks.
- `docs/machine-reliability.md`: entry point and integration notes.

Initial integration verification: 39 Python tests and 12 Cypress browser tests passed on LAB; frontend build and LAB migration passed. Existing backend source and calculation tests are unchanged.

Pre-existing Reliability Analysis limitation: passing a blank Asset value can return zero records; selecting an asset returns data. The backend distinguishes a blank string from an omitted/null filter. This existing behavior was preserved during integration.


## Three main tabs update

Only these files changed for the layout update:

- `engineering/engineering/page/reliability_engineering/reliability_engineering.js`: three peer panels, shared heading, keyboard navigation and chart retention on return.
- `engineering/public/css/engineering.css`: one tab style and responsive layout; unused nested-tab styles removed.
- `tests/ui/machine_reliability.cy.js` and `tests/ui/problem_machines.cy.js`: direct navigation, independent filter persistence, chart retention, keyboard and responsive checks.
- `docs/machine-reliability.md`: current layout notes.

The URL and all backend APIs, calculations, keyword matching and permissions are unchanged. The old Machine Reliability URL still opens the default tab.
