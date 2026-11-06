# A&U recorded meter hours implementation plan

Goal: retain integrity-valid recorded work in Engine and Month End totals while preserving investigative A&U flags. User specification: the eight requirements in the EX015 follow-up; expected October work is 314h.

Architecture: use the shared Engine summary eligibility rule for work, required and available hours, with Pre-Use integrity as the exclusion boundary. Preserve physical PBM handling and existing availability/ utilisation formulas. Keep A&U validation flags advisory for aggregation; display them and reasons in Month End. Undefined percentages use N/A when their denominator is zero.

Constraints: isolated branch/worktree; no deployment, site changes, migrations, production connections, historical edits or unrelated changes. Tests use static sanitized evidence from the completed read-only investigation and in-memory data boundaries. The running bench checkout stays unchanged.

Review focus: Saturday 7/9 configurations and invalid configuration; shift/day limits and valid sibling shifts; Sunday work with zero required hours; unchanged PBM minute totals; aggregation of flagged rows across machine/date/category/scope and downstream percentage consumers.

- [x] Add regression fixtures and tests for all five EX015 flagged shifts, full October 314h, retained 45h44m PBM, required hours 466h, 12h/24h and Saturday 9h/18h and 12h/24h rejection, zero denominators, flags/reasons, Month End scopes, daily/weekly downstream summaries.
- [x] Run regressions against baseline and confirm failures are excluded work/required hours and missing Month End visibility.
- [x] Make minimal shared Engine eligibility and validation percentage changes; expose Month End validation status/details; correct Engine help text describing exclusions.
- [x] Run regression suite, existing database-free tests, JavaScript syntax, Python compilation and diff validation. Inspect downstream consumers for independent filters; report any unavailable checks.
- [x] Review and commit focused changes on fix/au-retain-valid-meter-hours. Leave worktree available; do not merge, push or deploy.

Verification: 70 guarded Python tests pass; Month End formatter regression passes; 10 HOD availability-grid tests pass; JS syntax, Python compilation and diff checks pass. Four unchanged Short Haul renderer failures reproduce with the baseline Engine; see docs/au-meter-hours.md for exact names.

Independent review found no aggregation defects. Fixed zero-denominator availability rendering with a failing-then-passing formatter test. Added mixed production/spare, warning and Down Time coverage identified during review.

Ruling: the independent Actual Availability & Utilisation Engine is not a downstream consumer and is left unchanged to avoid changing separate legacy arithmetic; it may continue to disagree until separately migrated.

Branch/worktree are preserved for review, without merge, push or deployment, as requested.
