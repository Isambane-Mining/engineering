# LAB failure-classification integration and activation

Goal: integrate the prepared juan classification change into the newer running LAB checkout, keeping its unrelated code and data.

Authorization: latest user request permits in-place integration and LAB activation. No commits or pushes are needed. Keep the running branch and the prepared juan worktree. Never access production or drop the retired columns/backfill breakdowns.

1. Snapshot tracked/untracked source in both checkouts and record hashes. Compare per-file juan deltas with the running checkout and merge only the requested classification changes; resolve overlaps manually.
2. Add regression coverage for TMM classification counts/Pareto/export details/action links and WhatsApp optional Link capture. Replace every runtime dependency on the old fields; keep historical blank values supported. Use the existing master for filter/action choices.
3. Locate the supplied PDF; if absent, report that limitation and retain existing keywords with the prepared migration's safe alias mapping. Never invent PDF-derived phrases.
4. Run controller, classification, TMM, WhatsApp and import regressions on combined code. Review targeted changes and confirm unrelated source hashes remain unchanged.
5. Back up the named LAB database before migration, retain a full PBM source-row checksum baseline and schema-column list. Run LAB-only migration, frontend build and cache clearing. Refresh only the LAB web process.
6. Verify the migrated settings/form, rollback-only document saves, count/drill-down agreement, Dozer cards, reliability reports, TMM/API/export/browser interactions and historical-row checksums. Re-scan runtime references; document actual evidence and any PDF blocker.

Completed: in-place integration, 80 offline + 12 SQLite + 20 LAB backend tests, 8 fixture-browser + 15 live browser tests, verified backup, successful migration retry, build/cache/web refresh, live PDF and complete historical-row audit. PDF keyword seeding remains blocked by the unavailable attachment. No commits or pushes.
