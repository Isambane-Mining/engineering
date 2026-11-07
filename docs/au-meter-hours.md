# Recorded working hours in A&U summaries

The A&U Engine and Month End retain recorded work from shifts that pass the existing Pre-Use meter integrity rules, including shifts flagged `invalid_au`. Work, required hours and available hours use the same eligible shifts. Mechanical downtime keeps its existing minute-based aggregation. A&U flags, warning levels, problem-day counts and reasons remain available; Month End exposes dated shift reasons in its A&U Validation column.

Pre-Use integrity validation is unchanged: 12 hours per shift / 24 per day; Saturdays planned at 7 hours use 9 / 18; Saturdays planned at 9 use 12 / 24. Unsupported Saturday configurations remain invalid. No historical readings are corrected or rewritten. Work-plus-downtime reconciliation flags do not discard an entire shift's recorded hours.

Percentages retain the existing available-hour formulas and 85%/100% target scaling. Defined percentages stay visible alongside flags; a zero denominator produces N/A, including Sunday work against zero required hours.

## EX015 October evidence replay

`tests/data/ex015_october_2026.json` contains sanitized plan, meter and PBM inputs from the earlier read-only investigation: 62 planned shift slots and 39 recorded meter pairs. It is ordinary test data, not a Frappe fixture. Tests recalculate flags and totals from those inputs.

| Metric | Before | Corrected |
| --- | ---: | ---: |
| Working hours | 271h | 314h |
| Required hours | 432h | 466h |
| Mechanical downtime | 45h44m | 45h44m |
| A&U problem shifts | 5 | 5 |
| Availability, 100% basis | 101.119% | 102.969% |
| Utilisation, 100% basis | 65.485% | 70.272% |
| Availability, 85% basis | 85.951% | 87.524% |
| Utilisation, 85% basis | 55.662% | 59.731% |

The retained flagged work is 16 October Day 12h, 23 October Day 8h, 24 October Day 8h, 25 October Night 5h, and 28 October Day 10h: 43h. Sunday work stays recorded without inventing a percentage denominator.

## CSS and regression checks

Engine presentation is in `engineering/public/css/engineering.css`, already loaded through `app_include_css`. The two injected stylesheets, static inline styles and cursor/opacity styling were replaced by scoped rules and state classes. Shared table/filter rules follow Frappe's body route, so they stop applying when navigating to another report. Dialog classes remain usable outside the report wrapper. Existing Dozer and Machines Available stylesheet rules are preserved.

From the app root with the bench environment and its existing Playwright/Chromium installation:

```sh
PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1 FRAPPE_STREAM_LOGGING=1 /home/juan/juan-bench/env/bin/python tests/run_au_meter_hours_tests.py
node tests/test_au_month_end_formatter.cjs
```

The focused suite has 12 arithmetic/report regressions and four browser/CSS checks. Coverage includes all five flagged shifts, full-month totals, weekday/Saturday integrity rejection, Sunday zero denominators, warnings, mixed production/spare scopes, daily/weekly/Down Time consumers, actual formatter highlights, dialogs and navigation to another report. Tests block site initialization, database access, email, queues and HTTP. Month End's formatter test separately verifies N/A versus a measured zero. Changed Python compiles and both report scripts pass JavaScript syntax validation.

## LAB dependency and acceptance

LAB lacked the existing upstream `is_production` standard child DocType `Excluded Production Machine` and the `excluded_production_machines` Table field in Monthly Production Planning. These were introduced by approved upstream commit `ae9d998` and are still present at `19d2c5e`. The installed LAB app checkout predated that schema addition; no patch registration creates it.

After a verified backup, only those two DocTypes were synchronized from the exact upstream source definitions using Frappe's standard reload operation. No replacement/custom DocType, exclusion bypass, full-site migration, data-conversion patch, backfill or production change was used. The related dependency source files remain LAB-only changes in the separate `is_production` checkout and are not part of this Engineering PR.

A same-driver SHA-256 audit confirmed all eight existing planning source tables unchanged, including 103 planning documents and 153,836 production-area rows. Permission semantics and the patch log also match the backup; standard reload regenerated permission-row IDs and modification timestamps. No exclusion data was invented.

The corrected `juan` code was then executed against LAB database `juan` using the dedicated SELECT-only account and a READ ONLY transaction. For the available EX015/Koppie period, 1–31 August 2026, Engine and Month End match: 1 working hour, 448 required hours and 398.367 mechanical downtime hours. Only SELECT/SHOW statements were issued during acceptance. The October 314h / five-flag verification comes from the separate static evidence replay, not fabricated LAB October records.

The independent legacy Actual Availability & Utilisation Engine does not consume this shared Engine and retains its separate arithmetic. It is unchanged. Production has not been deployed or modified.
