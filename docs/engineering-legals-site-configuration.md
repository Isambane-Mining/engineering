# Engineering Legals Site Configuration — LAB review and migration runbook

Phase 2 implementation was code-only. This finalisation prepares a feature branch and
draft PR; migration, seeding, activation and deployment remain separately gated.

## Site structure decision (LAB read-only inspection, 29 October 2026)

Reuse the existing **Location** master, as both Engineering Legals.site and
MPP Child.site already do. Do not link legal configuration to an MPP Child row.

MPP Child belongs to the Production app and is a child table of
`Define Monthly Production.define`. Its fields are `site` (Link Location),
`monthly_production_plan` (Link Monthly Production Planning), `start_date` and
`end_date`, plus a Section Break. Its controller is empty; the parent client
filters plans by Location and fetches their dates. Production auto-sync owns
monthly row membership and removal. These rows are production-plan assignments,
not unique or durable site identities.

LAB has 18 MPP Child rows across four parents and six sites, three rows per site:
Bankfontein, Gwab, Klipfontein, Koppie, Kriel Rehabilitation and Uitgevallen. All
links resolve to Location. Plot 22 has an existing legal record and Location but
no MPP Child row. Selecting sites from MPP Child would therefore duplicate choices,
omit valid legal sites and introduce a dependency on Production plan lifecycle
and access. No MPP Child, parent, Production source or existing site data is changed.

The two new DocTypes serve distinct purposes; neither is a redundant site master.
No existing or newly created structure needs deletion.

| DocType | Fields and ownership |
| --- | --- |
| Engineering Legals Site Configuration | `site`: required unique Link Location, name from site; `enabled`: Check default 0; `effective_from`: Date required when enabled; `section_rules`: Table Engineering Legals Site Section Rule; `sharepoint_site_code`: optional safe folder code; `notes`: Small Text. System/Engineering Managers manage it; deletion disabled. |
| Engineering Legals Site Section Rule | Child only: `section`: required Link Engineering Legals Sections; `vehicle_type`: blank/LDV/TMM; `lifting_type`: blank/Inspection/Certificate; `active`: Check default 1; `no_expiry`: Check default 0; `expiry_value`: positive whole Int; `expiry_unit`: Days/Months/Years; `fleet_required`: Check; `start_date_policy`: Required/Optional/Clear; `brake_wear_required`: Check; `report_category`: existing ten monthly categories or Other; `counting_mode`: Active Until Expiry/Saved In Month; `sharepoint_subfolder`: optional safe folder. |

Engineering Legals adds only three hidden server-managed provenance fields:
`site_configuration`, `expiry_rule_source`, `expiry_rule_snapshot`. The existing
supplier draft gains `brake_wear_type`. No historical data is backfilled.

## Behavior

The global site-config key `engineering_legals_site_rules_enabled` defaults to off.
When off, when a site has no parent, when its parent is disabled, or when the document
predates Effective From, the server uses the previous server expiry rules. Invalid
enabled configurations fail explicitly; arbitrary DB errors are not swallowed.

Each enabled parent is unique by Location and owns section/vehicle/lifting rules.
The most specific match wins. Duplicate/equally specific overlapping rules are invalid;
an inactive specific rule blocks its combination even if a generic active rule exists.
Days use calendar days; Months/Years use Frappe calendar-month clipping.

Unrelated Engineering Legals saves restore stored expiry and provenance from the
pre-save document. Desk refresh never recalculates locally. Intentional changes to
site, section, start date or equipment conditions resolve a fresh policy. Snapshots
are server-managed and are not copied to a new document. Reports and SharePoint
read recorded category/counting/routing metadata, retaining legacy aliases and paths.
A new no-expiry record supersedes older alerts for that fleet/section without hiding
history or changing monthly membership. HSEC flags and payloads are unchanged.

No seed patch is registered. No configuration records are created during migration.
SharePoint retry filtering and existing report historical/current-site policies are unchanged.

## Checks safe to run now (no site, database, mail or HTTP)

```bash
cd /home/juan/juan-bench/apps/engineering
PYTHONDONTWRITEBYTECODE=1 ../../env/bin/python tests/run_engineering_legals_tests.py
node tests/test_engineering_legals_desk.cjs
node tests/test_engineering_legals_portal.cjs
git diff --check
```

The Python runner blocks Frappe site initialization/connection, DB, email, enqueueing
and requests HTTP. Tests replace only their explicit external boundaries with fixtures.
JavaScript tests execute the real form scripts in a controlled DOM/Desk environment.
They are not a substitute for post-migration browser/schema integration testing.

## Migration gate — not executed or authorized by this PR

Do not run `bench migrate`, create configuration records or enable rules as part of
PR preparation. The new tables are not installed on LAB. This is a draft code review,
not a deployment clearance. Full cross-app migration and browser/permission checks
must first pass on a disposable restored clone with external integrations isolated.

The earlier generic backup/pause examples have been withdrawn: plain `bench backup`
prunes existing archives even with explicit output paths, and stopping Supervisor
workers alone does not stop the six-hour backup cron or independent writers. The
LAB operator's separately prepared, approval-gated backup package is at
`/home/juan/juan-bench/legals-backup-final-20261029/RUNBOOK.md` (private host artifact,
not part of this repository or a portable clone runtime).

Before any separately approved migration:

1. Review all installed apps, pending patches, fixture imports and hooks, including
   ZA Local's metadata refresh. The unrelated `custom_docperm.json` working-tree
   edit is excluded from this PR and must be assessed separately before a LAB migrate.
   The earlier frozen source manifests/clone source archive predate final PR fixes;
   preserve them and capture a separately reviewed new source snapshot for this
   commit before the rehearsal. Do not replace the accepted historical-data baseline.
2. Record prior LAB service states; independently hold the exact LAB-only backup
   cron, imports and every other DB/file writer. The three MyISAM tables require
   quiescence throughout capture and verification. Do not stop other benches,
   shared MariaDB/Redis or global cron, or take a global SQL read lock.
3. Create a fresh complete DB/public/private/config backup into a new private
   directory outside cron retention, using the reviewed no-pruning procedure.
   Verify gzip/tar integrity, complete present-file inventories/content, configuration
   copies and archive SHA256 hashes. Never overwrite/delete existing archives.
   Restore prior service states on success, failure and interruption; retain an
   independent recovery session for host loss or SIGKILL.
4. Preserve the accepted baseline of 3,283 legal rows, historical dates (858 null),
   5,467 related File rows and all present-file hashes. The 1,253 existing legal
   records with missing attachments (1,079 URLs) are accepted historical conditions,
   not files to recover or references to delete. The standalone private V2 baseline
   remains the authoritative sealed comparison for this LAB investigation.
5. The repository LAB-only audit helper can also capture an explicitly accepted
   missing-file baseline using `allow_missing_files=True`; default capture rejects
   missing files until accepted. It stores an explicit `missing:ENOENT` availability
   marker with unchanged File rows/URLs. Verification rejects new loss, changed
   bytes/references or even newly recovered files until reviewed. Permission/path
   errors still fail. Manifests are private 0600 artifacts and must never enter Git.
6. Restore into a separate DB, files, copied code/environment and site config. Do
   not expose original configuration credentials to the clone. Enforce network
   isolation, private DB/Redis sockets, no workers/web/scheduler, disabled events,
   mail/webhooks/notifications/server scripts/SharePoint secrets, and tested enqueue
   and outbound-call guards before app initialization. A mute flag alone is not enough.
7. Compare real fixed-date report outputs, recorded routes and permissions before
   and after the isolated cross-app migration; do not invoke Graph, HSEC or mail.
   Verify unique Location metadata/index, the two additive tables, zero parent/child
   records, and rollout off. Never regenerate a baseline merely to make a mismatch pass.
8. Obtain separate approval for LAB migration after restore/rehearsal evidence is
   reviewed. Configuration creation and rule activation are later approval gates.

No seeding patch, data backfill or automatic activation is registered. Existing
records retain their dates and provenance; expiry is recalculated only for new
records or intentional policy-driving input changes. Additive migration does not
require rewriting historical records.

## Rollback

Before migration: revert only this project's reviewed files or apply its reverse diff.
Leave custom_docperm.json and all other unrelated changes intact. Keep the diff/backup
outside the checkout before reverting; no `git reset --hard` or blanket restore.

After additive migration, before rule activation: keep the rollout switch off. The
compatibility code can remain with its additive tables/columns; no data rollback or
table deletion is needed. Fix forward if the preservation check fails, with LAB paused.

After rules have been activated in a later phase: disable the global switch (or the
relevant parent), retain compatibility code and snapshots. Existing recorded dates and
routes still apply. Do not restore the original controller blindly: it rejects custom
sections and recalculates historical expiry on saves.

A full DB/files restore is a last resort requiring explicit approval: it discards all
post-backup work. Pause LAB, verify SHA256SUMS and archive integrity again, then use:

```bash
cd /home/juan/juan-bench
bench --site juan.isambane.co.za restore "$LEGALS_BACKUP/database.sql.gz" \
  --with-public-files "$LEGALS_BACKUP/public-files.tgz" \
  --with-private-files "$LEGALS_BACKUP/private-files.tgz"
bench --site juan.isambane.co.za clear-cache
```

Retain the site config/encryption key backup and align code/schema deliberately; do not
print secrets or copy configuration over the current site without comparing it. Verify
the historical manifest again before restoring LAB's prior service states.

## Changed files

Paths are relative to `apps/engineering`. The pre-existing permission fixture is excluded.

```text
docs/engineering-legals-site-configuration.md
docs/superpowers/plans/2026-10-28-engineering-legals-site-configuration.md
engineering/controllers/engineering_legals_lab_validation.py
engineering/controllers/engineering_legals_rules.py
engineering/engineering/doctype/engineering_legals/engineering_legals.js
engineering/engineering/doctype/engineering_legals/engineering_legals.json
engineering/engineering/doctype/engineering_legals/engineering_legals.py
engineering/engineering/doctype/engineering_legals/sharepoint_monthly_folders.py
engineering/engineering/doctype/engineering_legals/sharepoint_monthly_frequency.py
engineering/engineering/doctype/engineering_legals/test_engineering_legals.py
engineering/engineering/doctype/engineering_legals_site_configuration/__init__.py
engineering/engineering/doctype/engineering_legals_site_configuration/engineering_legals_site_configuration.js
engineering/engineering/doctype/engineering_legals_site_configuration/engineering_legals_site_configuration.json
engineering/engineering/doctype/engineering_legals_site_configuration/engineering_legals_site_configuration.py
engineering/engineering/doctype/engineering_legals_site_section_rule/__init__.py
engineering/engineering/doctype/engineering_legals_site_section_rule/engineering_legals_site_section_rule.json
engineering/engineering/doctype/engineering_legals_site_section_rule/engineering_legals_site_section_rule.py
engineering/engineering/doctype/engineering_legals_supplier_portal_draft/engineering_legals_supplier_portal_draft.json
engineering/engineering/doctype/engineering_legals_supplier_portal_draft/engineering_legals_supplier_portal_draft.py
engineering/engineering/report/engineering_legals_monthly_summary/engineering_legals_monthly_summary.py
engineering/engineering/report/engineering_legals_report/engineering_legals_report.js
engineering/engineering/report/engineering_legals_report/engineering_legals_report.py
engineering/engineering/report/engineering_legals_report/fetch_second_table.py
engineering/engineering/workspace/engineering/engineering.json
engineering/templates/pages/engineering_legals_list.py
engineering/templates/pages/engineering_legals_sup.html
engineering/templates/pages/engineering_legals_sup.py
engineering/templates/pages/engineering_legals_supplier_report.py
tests/run_engineering_legals_tests.py
tests/test_engineering_legals_desk.cjs
tests/test_engineering_legals_integrations.py
tests/test_engineering_legals_lab_validation.py
tests/test_engineering_legals_portal.cjs
tests/test_engineering_legals_reports.py
tests/test_engineering_legals_site_rules.py
```
