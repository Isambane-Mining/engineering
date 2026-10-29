# Engineering Legals Site Configuration Implementation Plan

**Goal:** Implement the approved Phase 1 design as code only, on LAB `juan`.
**Spec:** Approved investigation/design in the conversation and Phase 2 request.
**Architecture:** One server resolver supplies legacy and site rules, capture requirements,
expiry previews and immutable per-record provenance. Historical dates remain authoritative.
Reports and SharePoint use recorded reporting metadata, never recalculate expiry.
**Tech stack:** Existing Frappe Python/JSON DocTypes, Desk JS and Jinja portal.

## Global constraints

- No production access, migration, data seeding, activation, push, merge or deployment.
- Preserve all existing legal records and the unrelated custom_docperm.json diff.
- No SharePoint retry or historical site-policy changes.
- Default-off `engineering_legals_site_rules_enabled` configuration switch.
- No automatic seed patch: configuration creation requires separate approval.
- Work in the explicitly requested checkout/branch; keep changes uncommitted for review.

## Tasks

1. Write and run failing isolated rule/history tests; implement the shared resolver and
   parent/child schema with uniqueness, conditions, date arithmetic and safe fallback.
   Files: controllers/engineering_legals_rules.py, new DocType directories,
   tests/test_engineering_legals_site_rules.py.
2. Write failing controller/preview tests; integrate capture, historical preservation and
   server-managed snapshots; make Desk and supplier capture consume the shared preview.
   Files: Engineering Legals and supplier draft schemas/controllers, portal pages.
3. Write failing report/routing tests; integrate recorded category/counting/routing metadata
   while retaining legacy report shapes, history, API signatures and SharePoint selection.
   Files: monthly summary, legals report, SharePoint routing/folder helpers.
4. Run isolated Python and JS behavior tests, syntax/static checks and fresh code review.
   Add a lab migration/backup verification and rollback runbook; execute none of its DB steps.

## Interfaces

- `resolve_rule(values, configuration=None)` returns a normalized rule dictionary.
- `apply_document_rules(doc)` calculates new/changed documents and preserves historical
  expiry plus provenance on unrelated edits, using get_doc_before_save().
- `get_capture_preview(...)` authenticates Desk/supplier callers and returns requirements,
  section choices, normalized inputs and server expiry, preserving persisted history.
- `record_reporting_rule(record)` reads snapshot or historical section category/mode.
- `get_sharepoint_site_mapping()` and `get_record_sharepoint_parts(record)` preserve
  legacy routes unless an enabled, effective configuration supplies new routing.

## Review focus

- Forged posted expiry/snapshots must not become authoritative.
- Old imports and records without snapshots must work before schema activation.
- Inactive specific conditions must not fall through to generic active rules.
- Async previews must not overwrite values after a subsequent edit.
- Mixed historical/configured records must select exactly the records SharePoint consumes.

## Execution ledger

- Initial status: `juan`, HEAD cd3c8e1; only custom_docperm.json modified beforehand.
- Ruling: use current checkout as requested, no additional worktree or commits.
- Ruling: no seed patch is registered; schema-only migration must never create configuration records.
- Ruling: retain legacy reports' existing status/site scope; unrelated fixes remain out of scope.

- Task 1: complete — legacy/site resolver, validation and additive schema implemented.
- Task 2: complete — controller, Desk and portal share server calculations; history protected.
- Task 3: complete — recorded report modes/categories and SharePoint routes integrated.
- Task 4: complete — isolated regression suite, static validation and independent review.
- Final review: five code findings fixed with failing-then-passing regression tests:
  changed required fleet, no-expiry/date-filter ordering, stored draft ownership,
  persisted creation in preview, and edits during asynchronous Desk field application.
- Runbook review: maintenance browser acceptance now explicitly uses read-only transactions.
- Additional isolated coverage: Machine File stored dates, Machine Reliability calculations,
  LAB-only audit guard, baseline comparison and schema/index/disabled-empty acceptance check.
- Verification: 52 Python tests; Desk and portal JavaScript behavior suites; compilation,
  JSON/Jinja/JS syntax; Ruff correctness checks; new-file Ruff checks; whitespace checks.
- No migration, seed, activation, database connection, production credentials, notifications,
  live sync, commit, push, merge or deployment. custom_docperm.json checksum unchanged.
- Deferred integration verification: real Frappe schema/permissions/browser behavior, backup
  recovery and Graph delivery require the separately approved LAB migration/acceptance phase.
- Final error-path check: validation uses Frappe message logs so both clients receive actionable messages; covered by a failing-then-passing regression.

## Finalisation authorisation (29 October 2026)

The later user request authorises a dedicated feature branch, scoped commit, push
and draft PR, superseding the Phase 2 no-commit/no-push stop point above. Migration,
DB writes, seeding, activation, deployment and merge remain prohibited.

- MPP Child reviewed: retain its Production ownership/data; reuse Link Location.
- Both legal policy DocTypes retained; neither duplicates a site master.
- Review fixes cover direct Supplier controller scope, configured service history
  pagination, and explicit acceptance/preservation of missing attachment references.
- Stale generic backup instructions replaced with the reviewed operator gates.
