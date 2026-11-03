# Monthly TMM Assurance

Current implementation: MPP reporting periods, approved stored A&U calculation,
count-based breakdown Pareto, saved corrective actions, and a six-slide editable
PowerPoint export. Source calculations/rendering/API code remains consolidated in
`engineering/engineering/page/monthly_tmm_assurance/monthly_tmm_assurance.py`.

## Reporting periods

The Reporting Month is the **month of the MPP end date**. The default remains the
previous completed month; its preceding two labels are also displayed across
year boundaries. Action scope keys remain Site / Reporting Month / Group, so
existing saved actions retain their identities.

The report resolves each label from the selected site's non-cancelled Monthly
Production Planning records (`location`, `prod_month_start_date`,
`prod_month_end_date`, `docstatus`). Dates are inclusive. No dates are hard-coded.

- Identical MPP intervals are deduplicated and flagged with a visible warning.
  A shift is never multiplied by the number of plans.
- Different intervals with the same end-month label, inverted/missing start
  dates, and overlapping intervals are conflicts.
- Missing/conflicting historical periods display N/A and a warning, without
  querying substitute calendar dates.
- A missing/conflicting selected period prevents report/export generation with
  an explicit error. Existing filter/save protections remain in place.
- Gaps are not filled. Every displayed period shows its actual dates.

The supplied 2026 example resolves August 20 July–23 August, September
24 August–20 September, October 21 September–18 October **only if these plans
exist in ERP**. October then excludes 19–31 October. These example dates occur in
tests and documentation, not runtime period resolution.

## Availability source — intentionally different from the previous dashboard

For each equipment group and resolved period:

```
availability percentage = 85 × SUM(shift_available_hours)
                             / SUM(shift_required_hours)
```

Values come directly from stored **Availability and Utilisation** records:
`location`, `shift_date`, `asset_category`, `shift_required_hours`,
`shift_available_hours`, `docstatus`, `invalid_pre_use_hours`.

The site and inclusive MPP dates select the records, equivalent to a site/date
EXISTS join with MPP. Cancelled records and `invalid_pre_use_hours = 1` are
excluded. Null invalid flags are not treated as invalid. Identity deduplication
also prevents repeated source rows from contributing twice.

The ratio uses full stored precision. Scaling is applied exactly once. Stored
percentages are not read, machine percentages are not averaged, and no 85% cap
is imposed. Zero required hours and missing groups are N/A; valid zero available
hours with positive required hours is 0%. All-null available hours is N/A.

**This is not the Daily A&U Engine Dashboard calculation.** It has no dashboard
ownership, submitted-Asset/fleet, production/swing or additional synthesized
shift filters. The existing dashboard and A&U engines are unchanged. Source
record permissions still apply; partial source access fails closed instead of
presenting a partial fleet total.

Explicit mappings, with no inferred aliases:

| Stored category | Equipment group |
| --- | --- |
| ADT | ADTs |
| Excavator | Excavators |
| Drills | Drills |
| Grader | Graders |
| Loader | FELs |
| Dozer | Dozers |
| Service Truck, TLB, Water Bowser, Diesel Bowsers | Ancillary |

Unsupported/blank availability categories are flagged on the page and in the
presentation's factual data notes; they are not reassigned to Ancillary.

Regression example: required 18,240, available displayed 14,766.53, approved
availability 68.81%. Query/calculation keeps the available-hours precision;
rounding occurs only for display; availability labels show two decimal places.

## Breakdown population and corrective actions

Pareto uses the **selected MPP period**. One distinct Plant Breakdown or
Maintenance name counts once per overlapping period, including earlier starts,
open records, and repaired/closed records. Cancelled and Planned Maintenance
records remain excluded; legacy blank downtime type remains eligible.

The interval is `[MPP start 00:00, day after MPP end 00:00)`. An earlier record
must remain open or resolve strictly after period start. A start within the
period counts even for an instantaneous record. Ending exactly at period start
or beginning after the last included day does not count.

`failure_classification` and the existing master remain authoritative. No old
category fields, free-text inference or historical backfill are introduced.
Counts, full category views, 80% details, drill-downs and exports share the same
population. Missing/unsupported classifications remain visible for review and
are excluded from the existing classified-Pareto percentage denominator.

Cause counts descend; the cumulative percentage ends at 100% when classified
records exist. The page retains all seven groups, records, unresolved details,
full category tables and corrective-action tables. Saved-action concurrency,
server-side Site permissions, read/write/print checks and unsaved-change
protections remain intact.

## Download Presentation

The primary action calls `download_presentation(site, reporting_month)` and
returns an actual `.pptx`, with exactly these six slides for the selected Site:

1. Seven-group availability for three MPP periods, with dates and 85% basis.
2. Concise categorisation completeness counts and factual planning/data notes.
3. ADT Pareto.
4. Excavator Pareto.
5. Grader Pareto.
6. Ancillary Pareto.

`monthly_tmm_template.pptx` is a sanitised design-only derivative of
`/home/juan/Grant_Report_Fixed.pptx`. It retains the original theme, categorisation
slide artwork and black Pareto title bands. All historical figures, original
note text, slide images, notes and preview thumbnail were removed. The flattened
availability footer is recreated with editable shapes and current period text.
No deployment depends on the original file in `/home/juan`.

Charts are native editable PowerPoint charts with embedded data workbooks. Each
Pareto contains all positive classified categories, count bars, a 0–100%
secondary axis, cumulative line and an 80% reference. A missing classified
population produces an explicit empty state; it does not invent bars.

Only aggregate figures are exported. There are no individual breakdown lists,
unresolved-record lists, full category tables, saved-action tables or extra group
slides. The exporter enforces source/Site read access and scope print permission
before constructing the deck. Unsaved actions must save successfully before the
page starts downloading. The existing PDF API remains for compatibility; it is
not the primary page action and now uses the same MPP/stored-data source.

## Validation and current LAB data limitation

Checks cover stored-hour weighting, a single multiplier, values over 85/100,
zero/missing/invalid/cancelled data, explicit category mapping, MPP duplicates,
conflicts, adjacency, year rollover, overlap boundaries/deduplication, action
persistence/concurrency, permissions, exports and unsaved-change protection.
The six-slide PPTX is inspected structurally and rendered with LibreOffice for
visual/data verification. LibreOffice is a temporary test tool, not a runtime
dependency. Runtime export uses `python-pptx` (declared in `pyproject.toml`).

On **3 November 2026**, read-only SELECTs on LAB found August plans for Gwab and
Klipfontein but no September/October plans for those sites. Consequently the
supplied October total is verified with fixtures, not claimed as a reproduced
live LAB figure. A real August Klipfontein deck was generated read-only, and its
Python availability results matched independent SQL sums. No MPP/A&U records or
historical breakdowns were changed to make the example pass.

Artifacts and fresh logs: `/tmp/tmm-mpp-presentation/`.

## Exact LAB activation

`python-pptx 1.0.2` is already installed in the LAB bench environment. No schema
change, migration or asset bundle build is required for this change. Standard
Page JS and the packaged design-only template load from the app files.

```bash
cd /home/juan/juan-bench
bench --site juan.isambane.co.za clear-cache
sudo supervisorctl restart juan-bench-web:juan-bench-frappe-web
```

Refresh Desk after the web process is ready. For a future bench missing the new
runtime dependency, install it into that bench's environment first:

```bash
/home/juan/juan-bench/env/bin/pip install 'python-pptx>=1.0,<2'
```

These activation commands were **not run** during this update: live verification
was restricted to SELECTs. No scheduler, email, commit, push, merge or production
change was introduced. The missing LAB plans must be resolved through the normal
planning workflow before September/October reports can be produced there.
