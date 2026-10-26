# Machine Reliability implementation plan

Approved scope: user prompt and in-chat investigation, including the two standing-time and per-machine adjustments. LAB only; existing juan branch; no production deployment.

1. Implement and test pure keyword matching, recorded durations, unique downtime and per-Asset failure gaps in page/machine_reliability/calculations.py.
2. Add editable Single Machine Reliability Settings with category child rows, seeded keywords and inspection mappings. Never create breakdowns or rewrite source data.
3. Add permission-aware live-data APIs, historical-site fleet lookup, bounded queries, exact summaries, paginated tables and explicit chart limits.
4. Build responsive Desk Page with three tabs, interactive date/hour timelines, per-machine comparison and source links; add Engineering navigation.
5. Validate calculation and API tests, permission isolation, migration, assets, live responses and browser interactions on LAB.

Decisions: average standing time = arithmetic mean of valid completed direct Breakdown record durations; overlap remains included and flagged. Unique downtime is a separate merged, window-clipped metric. Never bridge invalid meter readings or mix Assets. Additional keywords extend category words (OR). Services are contextual records for the filtered machines; tests use configured section mappings. All-fault Top 10 bypasses problem matching only. Missing legal meter/detail fields remain unavailable.

Progress: implementation complete on LAB juan branch. No worktree per explicit user instruction. No unrelated files changed.

Verification: 7 calculation tests, 11 live API/settings/permission tests, 14 existing reliability regressions; LAB migration and Engineering build; browser suite covers 4 scenarios. Independent review corrected historical Asset-transfer scoping, unassigned records, nullable fleet lookup and disclosed machine cap. A real restricted-user regression failed before the historical-site fix and passed afterward. Original source counts remain 10,727 PBM and 3,283 Engineering Legals records.

LAB navigation was updated additively because migrate preserves the customized Workspace; its legacy invalid link was retained. All existing live links were preserved, and the report link was verified idempotent. The developer-mode auto-export was restored to the original repository file plus the focused report link/card count change.

No commit, push or production deployment was performed. Remaining source limitations (missing legal meter readings/test outcomes, keyword ambiguity and invalid source meters) are disclosed in the interface and report documentation.
