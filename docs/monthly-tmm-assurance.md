# Monthly TMM Assurance

Native Desk page: `/app/monthly-tmm-assurance`. Site and reporting-month filters
only; the default is the previous completed month. Submission is due on the 3rd
of the following month. There are no scheduler/email jobs.

## Reporting periods and availability

Resolve each of the three labels from that site's Monthly Production Planning
(MPP) end-date month. Display the actual inclusive plan start/end dates. Missing
plans give N/A; missing/conflicting selected plans block the report/export.
Identical duplicate intervals are warned about and deduplicated; conflicting or
overlapping periods are rejected. Calendar dates are never substituted.

Availability remains **85 × SUM(shift_available_hours) /
SUM(shift_required_hours)** from stored Availability and Utilisation rows by
location and inclusive shift_date. Apply scaling once, using unrounded sums.
Exclude cancelled rows and invalid_pre_use_hours = 1. Deduplicate by row name.
Zero denominator is N/A; genuine zero availability stays zero; there is no cap.
This stored-data calculation intentionally does not apply the dashboard's
ownership/fleet filters. Existing A&U engines are unchanged.

Explicit mappings:

| Stored category | Page group |
|---|---|
| ADT | ADTs |
| Excavator | Excavators |
| Drills | Drills |
| Grader | Graders |
| Loader | FELs |
| Dozer | Dozers |
| Diesel Bowsers | Diesel bowsers |
| Water Bowser | Water bowsers |
| TLB | TLBs |
| Service Truck | Service trucks |

Unsupported categories are flagged. Support categories are calculated separately;
there is no combined Ancillary availability. Existing Ancillary action scopes
remain separately accessible through **Historical Ancillary actions**; they are
never copied to the four new scopes.

## Planning-adjusted breakdown hours

The source is `Plant Breakdown or Maintenance` (PBM), not hourly entries or stored
elapsed `breakdown_hours`. Include carried-in and repaired/closed events.
Deduplicate by PBM name. Exclude cancelled records, `exclude_from_au`, and event
types other than Breakdown (blank legacy event type remains eligible). Planned
Maintenance is not a Failure Classification and stays outside this Pareto.

Preserve the approved TMM **midnight** boundary convention: MPP start at 00:00
through the day after the inclusive MPP end at 00:00. Clip the recorded interval
to those boundaries and to `frappe.utils.now_datetime()` (site-local time).
Never count future/negative time. A missing/open resolution uses the earlier of
period end and current site time. Invalid/missing starts, reversed timestamps or
timezone-bearing source timestamps remain explicit review records with unknown
hours (N/A), never manufactured zero hours. Invalid timestamps cannot be reliably
assigned to a month, so the site's timestamp-review records remain visible.

For each clipped PBM call the existing authoritative
`availability_and_utilisation_month_end_report.get_required_downtime_minutes_for_breakdown`.
It reads producing MPP plans and their Monthly Production Days, uses Engine
shift systems/required hours (including shifts spanning midnight), subtracts
configured Startup and Fatigue specification windows, caps overlap at required
shift hours and skips shifts without required hours. Divide its returned whole
required-downtime minutes by 60. Do not independently round hours or substitute
elapsed time when planning gives zero. Elapsed clipped hours remain supporting
ERP detail only. No trust-date, fleet-ownership or free-text-diagnosis filters
are added to TMM's population.

Each distinct PBM contributes once; repeated query/hourly entries cannot allocate
its full time again. Separate PBM records remain separate events, as in the
canonical per-breakdown helper; no arbitrary reallocation between classifications
is performed. The helper's established per-record minute precision is retained.

## Pareto and component review

Use the latest selected MPP period. Sort classifications by adjusted hours,
then canonical master order for ties. Percentages use **all classified hours**,
not the displayed top ten. Highlight the first 80% set including its crossing
classification. All classifications and records remain accessible in the page;
additional priority classifications are included in presentation continuations.

Missing/unsupported classifications retain their associated known hours in a
separate review total, excluded from the classified denominator. Timestamp-review
records have unknown hours. Page, drill-down, PDF and presentation consume the
same measured records and totals.

Component matching is entirely local and deterministic, in
`engineering/controllers/failure_classification.py`. It reuses Machine Reliability
Settings' configured classification keywords and the same whole-phrase matcher.
The existing twenty masters remain authoritative; no master or historical
complaint is inferred, renamed or backfilled.

Maintain explicit stable labels/aliases in `SUBCATEGORY_PHRASES`, spelling and
abbreviation rules in `DESCRIPTION_SYNONYMS`, and reviewed manual mappings in
`APPROVED_SUBCATEGORY_MAPPINGS`, keyed by `(recorded classification, normalized
reason)`. These are reviewable source configuration, with no external services,
fuzzy technical-name substitution or new mapping DocType. Existing approved
mappings take precedence. Additional approved phrases can be maintained in
Machine Reliability Settings; their capitalized phrase is the stable display
label unless an explicit label/alias is supplied in the shared controller.

Specific contained phrases suppress generic matches. Multiple components,
conflicting classifications, vague symptoms and absent vocabulary return Review.
Original `breakdown_reason` and Failure Classification stay unchanged. Examples:
tyre puncher/tyer puncture → Tyre puncture; batery faulty → Battery fault;
head light not working/headlight faulty → Lighting fault. “No power”, “does not
start” and “oil leak” do not establish a component diagnosis.

For each priority classification show up to three matched subcategories ranked
by distinct PBM count, then case-insensitive stable label. Display adjusted hours
as well. Each PBM receives at most one subcategory allocation. Unmatched records
and known hours remain accessible in review details.

## Exports, actions and access

Primary download is an editable `.pptx`, using the bundled design-only template:

1. Prime movers availability: ADTs, Excavators, Dozers, Drills.
2. Support availability: Diesel bowsers, Water bowsers, TLBs, Service trucks.
3. ADT Pareto, with priority component continuations.
4. Excavator Pareto, with priority component continuations.
5. Dozer Pareto, with priority component continuations.

Charts, embedded workbooks, text and component tables are editable. Top-ten charts
retain the full-population denominator. Each continuation holds at most two
priority classifications; missing component matches are explicit. Site/month/MPP
dates appear on every slide. No FEL/combined Ancillary availability slide, raw
breakdown lists, action tables or unrelated sections are exported. Empty groups
retain an explicit empty Pareto slide. Legacy PDF remains available and includes
all relevant page groups and saved actions.

Read/site permissions are checked server-side. Stored A&U, MPP and PBM sources fail closed on partial record access before
raw canonical helper queries. Startup/Fatigue specifications are internal
calculation configuration, read through the unchanged canonical helper; users
do not need configuration-editing roles to read their authorised site report. Export checks print permission before generating content. Action saves
retain normal Frappe create/write/site checks, immutable scope, child validation
and optimistic concurrency. Filter changes and refresh protect unsaved actions.
No broad permission changes were introduced. CSS is loaded as native Page CSS.

## Validation and LAB activation

Tests live beside the Page (`test_downtime_hours.py`, `test_mpp_presentation.py`,
existing integration tests), plus the shared classification and browser suites.
Integration tests use only a disposable SQLite site; MariaDB-specific planning
readers are adapted to fixture plans while the real Month End helper executes.

The action group's Select options changed. On LAB, reload the parent action
DocType, clear the site cache, and restart the LAB web process through the
operator's normal service mechanism. Page CSS is read by Frappe's page loader;
there is no asset-bundle build requirement or data backfill for this change.
Do not run a blanket migration merely for TMM, because unrelated pending patches
must be reviewed separately. Historical records and retired columns stay intact.
