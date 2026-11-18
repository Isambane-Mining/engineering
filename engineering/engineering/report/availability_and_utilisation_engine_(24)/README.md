# Availability and Utilisation Engine (24)

The confirmed final calculation rules supersede the earlier configuration-driven
24-hour Isambane proposal. The original Availability and Utilisation Engine and
the original startup/fatigue DocType remain unchanged. There is one report folder,
`availability_and_utilisation_engine_(24)`. All Python logic is in its report
controller; no separate calculation module or duplicate DocType is required.

## Formula choices and Use of Availability

There are two Formula options: Industry Formula and Isambane Formula.
Use of Availability is an additional Industry column, not a standalone formula.
Its own available-hours denominator is MAX(24 − raw breakdown − raw planned maintenance, MIN(working hours, 24)), calculated independently for each machine/day. Industry's
separate Utilisation column continues to divide working hours by the 24-hour base.

Ratios above 1 are preserved and flagged in amber. Daily anomalies propagate to
machine and total rows even when aggregation hides an inconsistent day. Zero
denominators display a neutral dash for Use of Availability. Totals divide summed
working hours by the sum of the daily Use of Availability denominators; they never average daily ratios. No separate Use of Availability target is
invented.

## Industry Formula

Each dated production-planning day has a fixed 24-hour base (06:00–06:00).
Availability available hours = max(24 − raw breakdown − raw maintenance, 0).
Availability ratio = availability available hours / 24.
Use of Availability available hours = max(24 − raw breakdown − raw maintenance, min(working hours, 24)). Calculate this MAX/MIN per machine/day before aggregation.
Use of Availability ratio = working hours / its own available hours.
Utilisation available hours = 24; utilisation ratio = recorded working hours / 24.

Raw PBM duration is clipped to the reporting day, without startup/fatigue
exclusions or merging away overlaps between raw records. Non-cancelled PBM,
exclude_from_au and existing asset/report filters remain applicable. Working hours
use recorded nonnegative Pre-Use meter differences with the existing last-reading
per machine/shift selection; no legacy 18-hour integrity threshold is used here.
Neither the new configuration DocType nor a holiday calendar is read by this path.
Reference targets are availability 0.85 and utilisation 0.75.

## Isambane Formula

The service calls the unchanged original Engine get_data Isambane path, then
the original build_tree_rows hierarchy and build_summary_row for its valid underlying shifts. This preserves:

- Original Required Hours, per-shift exceptions and Pre-Use status exceptions.
- Original PBM downtime exclusions for startup/fatigue and Sunday handling.
- Original Pre-Use integrity filtering and zero-required-hours behaviour.
- Shift availability available = max(working, max(required − PBM downtime, 0)).
- Shift utilisation available = max(required − PBM downtime, min(working, required)).

MAX/MIN is applied by Engine at shift level, not recalculated on period totals.
The Isambane Calculation Basis filter offers 85% A & U and 100% A & U.
The default remains 100% to preserve the report's prior default. The selected basis
uses the original Engine's percentage multiplier (0.85 or 1.0), including its
3-percentage-decimal rounding, after weighted aggregation. Underlying hours do not
change. Reference targets remain 0.85 for both metrics, independently of the basis.

Industry shows twelve relevant columns, including both separate utilisation denominators; Isambane retains ten. The base column is Required Hours (h)
for Isambane and Total Hours (24h) for Industry. Industry places Use of Availability directly after Utilisation;
Isambane shows Utilisation Available Hours in its calculation section. Site, row numbers, Safety
Meeting, Fatigue and Tramming columns are omitted; Site remains a report filter
and internal grouping key.

## Ratios, display and totals

The existing availability_percent/utilisation_percent result fields now contain
**decimal ratios**, e.g. 0.85. Only the JavaScript display argument is multiplied
by 100 for Frappe's Percent formatter. Exported raw report values remain ratios.
Undefined denominators display neutral dashes. No upper percentage cap is added.

Category, date, machine/day and bottom totals sum underlying atomic hours, then divide summed available
hours by summed base/Required Hours and summed work by summed utilisation available.
There are no average-of-machine percentages, KPI cards or totals above the table.
Formula-specific reference targets are shown beside the selected formula and in
the View Formula dialog. Standard column searches are visible below the headings.
Percentage searches use displayed units (e.g. >85 means >85%, not >0.85). A
permission-checked read-only endpoint recalculates the bottom weighted total for
the exact selected underlying dataset; the total remains last even when no records match.
The screenshot-approved filter card, separate configuration button, wrapped headers
and green/purple percentage styling are preserved.

## Expandable tree and calculation visibility

The original Engine tree builder orders category → date → machine → shift.
Frappe's standard expand/collapse and tree-depth controls are used, initially
showing category rows. The first Asset column carries category/date/fleet/shift
labels; Site remains internal. Fleet labels shared by different sites retain
separate internal identities. Working Hours sits beside raw downtime inputs.

Industry's atomic calculation remains one 24-hour machine/day. Day/Night (or the
configured three-shift system) children show raw work and raw PBM clipped to the
original clock windows. They are source detail, as in the original Industry tree:
calculated hours/ratios and daily base are dashes on those children. The machine/day
row immediately above them displays the actual daily calculation. Never assign a
second 24-hour base or invent a shift percentage. Industry searches select complete
machine-days and show all their source shifts together.

Isambane shift children show the actual original Engine hours and basis-scaled
percentages. Parent and bottom summaries use original integrity-valid source
shifts once, including original Sunday handling. Integrity-excluded shifts remain
visible with an explanatory tooltip and are not counted in summaries.

Column matching acts on atomic machine-days (Industry) or source shifts
(Isambane), with searchable fleet/category/date context. `get_filtered_tree`
rebuilds just their ancestors and weighted subtotals. The filter updates the tree body while retaining the existing header/input DOM,
caret, keyboard focus, column widths and open/closed branch state. Editing keys
stay in search inputs, and unrelated branches are not automatically expanded.
Expand/collapse therefore cannot resurrect excluded children. Clearing searches restores the full tree.
Collapsing a selected branch is disclosure only; its underlying data remains in
the totals. Parents and source-detail children are never counted a second time.

Availability calculated hours/percentages are green; utilisation hours/percentages
are purple; Industry Use of Availability has a distinct subtle blue-green fill.
Both available-hours buttons have short formula-specific equations and variable
keys; Isambane shows its selected basis. The View Formula dialog retains worked examples.
Day shift rows have a light-blue background and Night shift rows a light-grey
background across all cells, with calculated-cell highlights preserved. They update with filter changes.

See the latest section of root `AU24_CODEX_HANDOFF.md` for focused verification and
the latest live LAB acceptance results. The specifically authorised LAB-only web
group reload resolved the cached controller; no production service was restarted.

## Configuration dialog

The read-only configuration dialog uses the existing
`Startup and Fatigue spesification` DocType.

It displays Site, Shift, Day Type, Startup and Fatigue.
Day and Night configurations are shown separately.
No duplicate configuration DocType is required.

Isambane calculations continue to use the original Engine's
established startup/fatigue overlap exclusions.

## Minimal verification

For optional later checks from the Engineering app directory, run the focused calculation examples:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests ../../env/bin/python -B -m unittest test_au24_engine.Engine24Tests

From bench sites, one read-only LAB report call (default Isambane):

    PYTHONDONTWRITEBYTECODE=1 ../env/bin/python -B ../apps/engineering/tests/verify_au24_lab.py

The LAB helper creates no records, reloads no metadata and uses a read-only
transaction. AU24_FORMULA can explicitly select Industry for a later run.
Older browser/regression helpers may still assert the superseded 15-column or third-formula layout. They are not part of this minimal verification cycle; inspect their expectations before using them. See `AU24_CODEX_HANDOFF.md` for the exact checks executed for the final refinements.

No deployment, cache invalidation or worker restart is part of this source change.
Existing web workers may require their normal reload when deployment is approved.

## Industry shift-level calculation

Industry calculations are performed independently for each scheduled shift.
The shift base comes from the site's configured shift timings: 12 hours for
2x12Hour and 8 hours for 3x8Hour.

Availability Available Hours = Shift Hours - Breakdown - Planned Maintenance.
Use of Availability Available Hours = MAX(Availability Available Hours,
MIN(Working Hours, Shift Hours)).
Utilisation Available Hours = Shift Hours.

Category, date, machine and fleet totals sum the underlying shift hours and
denominators before calculating percentages. Shift rows are the atomic records.
