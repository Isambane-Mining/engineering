# Monthly TMM Assurance Implementation Plan

**Goal:** Build the approved monthly Desk page in LAB, using Daily A&U Engine Dashboard's backend unchanged.

**Architecture:** A native Page loads three completed calendar months; availability uses `fetch_grouped_data` with the dashboard's defaults (85% basis, combined production/swing fleet, in-house ownership). Group totals use `au_engine.build_summary_row` then `apply_au_percentage_basis`, never average percentages. Saved actions use a site/month/group parent and child rows with normal Frappe permissions, optimistic concurrency and immutable identity. Server SVG images are shared by browser/PDF and embedded in the PDF without JavaScript.

**Constraints:** Work only in this LAB app. Preserve existing fixture changes. No deployment, production access, scheduler, emails, push or merge. User has approved the layout and directed implementation; no further design approval needed.

- [x] Write failing tests for month rollover, aggregation, missing/zero and downtime clipping/deduplication; implement data helpers and API.
- [x] Add actions schema/controller and tests for persistence, conflicts, site and role permissions, including direct document saves.
- [x] Implement native Page with two filters, row selection, editable actions, dirty-state protection and stale response protection.
- [x] Render complete PDF with all groups and saved actions; verify embedded chart output with wkhtmltopdf and raster inspection.
- [x] Run isolated Frappe integration tests, browser checks and regression checks; document calculation trace, validation and exact LAB commands.

**Review focus:** cross-year dates; zero versus unknown; overlapping records/cause attribution; concurrency and filter changes; site access on API/PDF/direct writes; all PDF groups independent of UI selection.

## Validation ledger

- Calculation helpers: 7/7 passed. Real Frappe schema/document/Page/PDF tests: 9/9 passed. Chromium harness: 6/6 passed. Existing isolated regressions: 58/58 passed.
- Review: independent reviewer found a source-record permission bypass in raw Engine SQL. Reproduced with a real A&U-specific User Permission; added scope identity permission checks before Engine execution; regression now passes.
- Async Frappe set_value restoration: reproduced failure, awaited control updates, browser regression now passes.
- Ruling: use the user-specified existing LAB checkout instead of creating a different worktree; preserve unrelated fixture and concurrent downtime-dashboard edits.
- Ruling: fail closed on incomplete source record access, rather than intersecting generated Engine rows with stored A&U records: Engine rows are generated from planning and Pre-Use and may exist without a stored A&U row.
- Ruling: union overlapping downtime before cause measurement; use combined recorded categories for shared intervals and retain Uncategorised. This avoids duplicate time; it intentionally need not reconcile legacy duplicate/blank-reason Engine PBM totals.
- Authenticated configured-LAB smoke check remains after targeted imports. No working-site migration or production connection was performed.
