# Kobelco integration — embedded mapping revision, 19 November 2026

**Latest state:** see [the raw API audit](kobelco-api-audit.md) for subsequent real-data findings, added telemetry, timestamp corrections, preservation of original Fleet JSON and current test results. The blank-credential/no-live-call statements below describe the earlier UI revision only; user-configured credentials and real mappings/results are now preserved.

Implemented and activated in LAB (`juan.isambane.co.za`), branch `juan`. No commits, pushes, branches or production operations.

## Final structure and UI

- **API Kobelco Settings** has exactly two native Frappe tabs:
  - **API Configuration:** Enabled, Base URL, Username, secure Password, inline Test Connection and Fetch Fleet buttons, and last sync timestamp/status/message. Last successful sync remains stored for audit but is hidden to keep this tab compact.
  - **Machine Mapping:** one editable native child-table grid, `machine_mappings`, using **Kobelco Machine Mapping**. Fields are Serial Number, PIN, OEM, Model, Asset, Mapping Status and Last Seen. Users select an existing Asset inline. Native orange/green status indicators distinguish unmapped/mapped rows.
- **Kobelco Results** remains a separate telemetry-history DocType, accessible through the Engineering workspace. Its Machine Mapping action opens the Settings mapping tab.
- The Engineering workspace Kobelco card now contains Settings and Results only.

The direct reference was API Wearcheck Settings JSON, JavaScript and its Wearcheck Unmapped child table. WearCheck has no custom Settings CSS or active JavaScript layout code. Both forms use Frappe's native Tab Break, Table, grid and form spacing implementation. Existing Engineering CSS was inspected; no custom CSS, embedded styles or CSS-in-JavaScript was added.

Username and password have no prepopulated values. The username Data field has an empty default; browser autocomplete is disabled on the username and password controls. Password remains a Frappe Password field using encrypted storage. LAB remains disabled with no saved Kobelco credentials.

## Mapping and telemetry behavior

Fetch Fleet merges discovery into the child table and saves Settings once. It identifies machines by serial/PIN, retains child-row identities, manually chosen Assets, and machines absent from a later response. It updates only discovery fields. Settings is reloaded with a database lock after HTTP so choices saved during the request are preserved; normal parent modified checks protect stale saves.

Serial, PIN and Asset uniqueness is enforced in parent validation and database unique indexes. Existing machine identifiers cannot be edited; discovery may fill a previously missing PIN. Removing discovered rows is blocked; clearing Asset marks the machine Unmapped. No model matching or Asset creation occurs.

Saving the parent updates the local Asset/mapping links on historical results. Results' telemetry measurements, source timestamps, availability flags, raw JSON, read-only behavior and snapshot deduplication are unchanged. Its internal `mapping` field is now hidden Data containing the child-row ID, rather than a Link to the removed master DocType. The API client, Basic Authentication, pagination and read-only HTTP behavior were unchanged.

Mapping inherits the existing Settings permissions: System Manager, Engineering Manager and Engineering Area Manager can configure and map. Engineering User, Production and Procurement roles retain Results read access, but no longer have the standalone mapping editing permission. The child DocType has no independent permissions or form/list navigation.

## Deleted DocType and data checks

Removed **Kobelco Asset Mapping**, its five source files, standalone form/list scripts, permissions, workspace link and standalone-mapping test assumptions. No separate Kobelco unmapped DocType existed.

Before removal, LAB had **0 legacy mappings and 0 Results**. The guard was checked before deleting source or schema. The migration refuses to run when any legacy mapping records exist, before schema changes or deletion, and checks again before removal. The empty legacy database table and DocType metadata were removed. No machine data was discarded.

## Migration instructions

A pre-model-sync patch is registered in `engineering/patches.txt`:

```sh
cd /home/juan/juan-bench
bench --site juan.isambane.co.za run-patch engineering.patches.embed_kobelco_machine_mapping
bench --site juan.isambane.co.za clear-cache
```

This targeted LAB patch has already run successfully. A forced second run also passed, validating idempotence. It loads the new child/settings/results schemas, removes only obsolete standalone mapping navigation, and deletes the guarded empty legacy DocType/table. Remaining workspace rows and their order are preserved. Unrelated pending LAB patches/fixtures were not applied. During a normal future migration, the pre-model-sync registration runs the same guard automatically.

If the patch reports existing legacy mapping data, stop and export/review those records before proceeding. It deliberately does not silently migrate or discard existing mappings.

The LAB web process on port 8007 was gracefully reloaded to pick up the Python controller changes. Reload the Settings page to refresh browser metadata.

## Tests and verification

```sh
# From apps/engineering
/home/juan/juan-bench/env/bin/python tests/run_kobelco_tests.py
/home/juan/juan-bench/env/bin/python tests/run_controller_regressions.py
KOBELCO_BROWSER_AUTH_FILE=/path/to/temporary-lab-session.json node tests/verify_kobelco_browser.cjs
```

- **30 Kobelco tests passed**, including mocked HTTP/authentication, secure password storage, child discovery and identity, duplicate prevention, preserving manual Assets during refresh and while HTTP is pending, results creation/deduplication/relinking, malformed data rollback, disabled/unauthorized access, mapping permissions, and the migration guard refusing existing data before changes.
- **91 existing controller regression tests passed.**
- **LAB browser validation passed:** exactly two native tabs, blank username/password, secure Password type, inline API buttons, disabled Fetch Fleet while disabled, real inline Asset autocomplete/selection, derived Mapping Status, Results-to-mapping-tab navigation, and workspace links. No browser JavaScript errors occurred.
- Guarded scoped migration and forced repeat both passed. Python parsing, JavaScript syntax, JSON parsing and `git diff --check` passed.
- Independent review found no important defects; inherited Settings permissions are documented above.

All temporary settings, encrypted test credentials, child rows and snapshots were rolled back. Browser sample rows existed only in the browser and were discarded without saving. The temporary browser session was removed. No real vendor API calls were made. Real connection verification still needs the user's vendor credentials.

WearCheck/MPI files and unrelated existing work were preserved. Only Kobelco workspace navigation and this patch's registration changed shared files; their existing unrelated content was retained.

## Changed files in this revision

Modified:

- `docs/kobelco-integration.md`
- `docs/superpowers/plans/2026-11-19-kobelco.md`
- `engineering/controllers/kobelco.py`
- `engineering/controllers/test_kobelco.py`
- `engineering/engineering/doctype/api_kobelco_settings/api_kobelco_settings.js`
- `engineering/engineering/doctype/api_kobelco_settings/api_kobelco_settings.json`
- `engineering/engineering/doctype/api_kobelco_settings/api_kobelco_settings.py`
- `engineering/engineering/doctype/api_kobelco_settings/test_api_kobelco_settings.py`
- `engineering/engineering/doctype/kobelco_results/kobelco_results.js`
- `engineering/engineering/doctype/kobelco_results/kobelco_results.json`
- `engineering/engineering/doctype/kobelco_results/kobelco_results_list.js`
- `tests/verify_kobelco_browser.cjs`
- `engineering/engineering/workspace/engineering/engineering.json`
- `engineering/patches.txt`

Added:

- `engineering/engineering/doctype/kobelco_machine_mapping/__init__.py`
- `engineering/engineering/doctype/kobelco_machine_mapping/kobelco_machine_mapping.json`
- `engineering/engineering/doctype/kobelco_machine_mapping/kobelco_machine_mapping.py`
- `engineering/patches/embed_kobelco_machine_mapping.py`

Deleted:

- `engineering/engineering/doctype/kobelco_asset_mapping/__init__.py`
- `engineering/engineering/doctype/kobelco_asset_mapping/kobelco_asset_mapping.js`
- `engineering/engineering/doctype/kobelco_asset_mapping/kobelco_asset_mapping.json`
- `engineering/engineering/doctype/kobelco_asset_mapping/kobelco_asset_mapping.py`
- `engineering/engineering/doctype/kobelco_asset_mapping/kobelco_asset_mapping_list.js`
