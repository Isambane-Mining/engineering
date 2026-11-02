# Failure classification replaces problem categories

The optional `failure_classification` Link to Breakdown Failure Classification is now the sole explicit classification source in this `juan` worktree. The two old standard Select definitions are removed. Their physical database columns and source values are retained; no backfill or inference occurs.

See [migration and verification](failure-classification-migration.md) for the 20 master names, legacy settings mapping, accepted historical gaps and activation status. Machine Reliability uses explicit classification first and keyword fallback for unclassified history. Resolution-only matches remain additional repair work.

Activated on LAB on 2 November 2026. Both retired form controls are absent; database columns and historical records remain unchanged. See the linked verification notes.
