# Availability and Utilisation Engine (24)

The confirmed final calculation rules supersede the earlier configuration-driven
24-hour Isambane proposal. The original Availability and Utilisation Engine and
both configuration DocTypes remain unchanged. The existing Frappe entry wrapper
is unchanged; its canonical service and calculation module implement this update.

## Industry Formula

Each dated production-planning day has a fixed 24-hour base (06:00–06:00).
Availability available hours = max(24 − raw breakdown − raw maintenance, 0).
Availability ratio = availability available hours / 24.
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
build_summary_row for each machine's underlying shift rows. This preserves:

- Original Required Hours, per-shift exceptions and Pre-Use status exceptions.
- Original PBM downtime exclusions for startup/fatigue and Sunday handling.
- Original Pre-Use integrity filtering and zero-required-hours behaviour.
- Shift availability available = max(working, max(required − PBM downtime, 0)).
- Shift utilisation available = max(required − PBM downtime, min(working, required)).

MAX/MIN is applied by Engine at shift level, not recalculated on period totals.
The old percentage-basis multiplier is explicitly disabled (100% basis). Targets
remain references, never multipliers. Reference targets are 0.85 for both metrics.

The base column displays Required Hours (h) for Isambane and Total Hours (24h) for
Industry. Safety Meeting, Fatigue and Tramming remain visible; Industry shows zero,
while Isambane shows dashes because these are not additional separate deductions.

## Ratios, display and totals

The existing availability_percent/utilisation_percent result fields now contain
**decimal ratios**, e.g. 0.85. Only the JavaScript display argument is multiplied
by 100 for Frappe's Percent formatter. Exported raw report values remain ratios.
Undefined denominators display neutral dashes. No upper percentage cap is added.

Machine-period and bottom totals sum underlying hours, then divide summed available
hours by summed base/Required Hours and summed work by summed utilisation available.
There are no average-of-machine percentages, KPI cards or totals above the table.
Formula-specific reference targets are shown in explanatory text below the table.
The screenshot-approved filter card, separate configuration button, wrapped headers
and green/purple percentage styling are preserved.

## Configuration dialog

The read-only configuration dialog uses the existing
`Startup and Fatigue spesification` DocType.

It displays Site, Shift, Day Type, Startup and Fatigue.
Day and Night configurations are shown separately.
No duplicate configuration DocType is required.

Isambane calculations continue to use the original Engine's
established startup/fatigue overlap exclusions.

## Minimal verification

From the Engineering app directory, run only the two calculation examples:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests ../../env/bin/python -B -m unittest test_au24_engine.Engine24Tests

From bench sites, one read-only LAB report call (default Isambane):

    PYTHONDONTWRITEBYTECODE=1 ../env/bin/python -B ../apps/engineering/tests/verify_au24_lab.py

The LAB helper creates no records, reloads no metadata and uses a read-only
transaction. AU24_FORMULA can explicitly select Industry for a later run.
The browser and broader regression helpers have been aligned to the new ratio
contract, but are not part of this requested minimal verification cycle.

No deployment, cache invalidation or worker restart is part of this source change.
Existing web workers may require their normal reload when deployment is approved.
