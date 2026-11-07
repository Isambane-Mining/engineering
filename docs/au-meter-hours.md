# Recorded working hours in A&U summaries

The A&U Engine and Month End retain recorded work from shifts that pass the existing Pre-Use meter integrity rules, including shifts flagged `invalid_au`. Work/required/available hours use the same eligible rows. Breakdown downtime keeps its existing minute-based aggregation and eligibility. A&U flags, warning levels, problem-day counts and reasons remain available for investigation; Month End exposes dated shift reasons in its A&U Validation column.

Pre-Use rejection is unchanged: 12 hours per shift / 24 per day; Saturdays planned at 7 hours use 9 / 18, Saturdays planned at 9 use 12 / 24; unsupported Saturday configuration remains invalid. No records are corrected or rewritten. Manual A&U flag review does not determine recorded-work eligibility.

Percentages retain the existing available-hour formulas and 85%/100% target scaling. Reconciliation flags no longer erase defined percentages. A zero denominator produces N/A, including Sunday-only work against zero planned hours. No hours or denominator is invented to make a percentage available.

## EX015 evidence replay

The static fixture `tests/fixtures/ex015_october_2026.json` contains sanitized plan, meter and PBM inputs from the completed read-only production investigation. It has 62 planned shift slots and 39 recorded meter pairs. Tests recalculate flags and arithmetic rather than loading the former report's calculated totals.

| Metric | Before | Corrected |
| --- | ---: | ---: |
| Recorded work included | 271h | 314h |
| Required hours included | 432h | 466h |
| Mechanical downtime | 45h44m | 45h44m |
| Utilisation available hours | 413.834h | 446.834h |
| Availability available hours | 436.834h | 479.834h |
| A&U problem shifts | 5 | 5 |
| Availability, 100% basis | 101.119% | 102.969% |
| Utilisation, 100% basis | 65.485% | 70.272% |
| Availability, 85% basis | 85.951% | 87.524% |
| Utilisation, 85% basis | 55.662% | 59.731% |

The retained flagged work is 16 October Day 12h, 23 October Day 8h, 24 October Day 8h, 25 October Night 5h, and 28 October Day 10h: 43h. Sunday work stays recorded, with zero required hours and undefined standalone percentages.

## Verification

From this worktree, using the bench Python (no site initialization, database connection or HTTP):

```sh
PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1 FRAPPE_STREAM_LOGGING=1 /home/juan/juan-bench/env/bin/python tests/run_au_meter_hours_tests.py
node tests/test_au_month_end_formatter.cjs
```

The runner supplies the same no-site context as the existing Engineering Legals runner and runs all root Python tests plus its existing DocType/calculation modules: 70 tests pass, including 12 A&U regressions. Bare unittest discovery lacks the Frappe context required by unrelated legacy tests; use the guarded runner. The JavaScript test executes the actual Month End formatter and checks undefined versus real-zero percentages. JavaScript syntax checks, Python compilation and `git diff --check` also pass.

Downstream checks cover the shared daily and weekly dashboards, mixed production/spare Month End scopes, warning visibility, and Down Time hours/percentages/PBM. The HOD presentation availability-grid module passes all 10 existing tests against the corrected Engine.

Four pre-existing Short Haul rendering failures were reproduced identically with the baseline Engine and corrected Engine (7/11 pass in both runs):

- `TestShortHaul.test_no_short_haul_keeps_single_bar_and_small_value_hover`
- `TestShortHaul.test_stack_and_real_tooltip_values_are_not_capped`
- `TestShortHaul.test_uncapped_short_haul_component`
- `TestShortHaul.test_zero_denominator_retains_hours_without_inventing_percentage`

These exercise unchanged renderer HTML and are outside this calculation fix. They are not claimed passing.

The separately implemented **Actual Availability & Utilisation Engine** report does not consume the shared Engine and retains its legacy arithmetic/filter. It is unchanged and can still disagree. The ordinary Engine, Month End, and their shared downstream consumers receive this correction.

All verification uses local code and static evidence. The deployed production code has not been verified, changed or deployed. No site migrations, historical edits, production connections or database writes were performed during this implementation.
