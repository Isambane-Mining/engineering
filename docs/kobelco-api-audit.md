# Kobelco raw API audit — 19 November 2026

Completed on branch `juan`, LAB `juan.isambane.co.za`. Existing unrelated uncommitted work, credentials, mappings, MPI and WearCheck were preserved. No commits, pushes, production changes, scheduled syncs or remote writes occurred.

## Evidence and findings before repair

Inspected the two existing Results, their saved machine JSON and a fresh authenticated, read-only GET of the configured `/Fleet/1`. The response was HTTP 200 JSON, with a `Fleet` envelope and two `Equipment` objects. Authentication used the encrypted Settings password without logging credentials or the configured URL.

The pre-change findings and exact proposed historical corrections were reported before applying changes to existing Results. Original rows were backed up locally with mode 0600. Schema expansion was checked to leave every pre-existing field value unchanged before the historical repair.

Every one of the **40 observed leaf paths** is listed below. All **33 populated machine paths** now have typed Results fields; Fleet version and snapshot time also have typed fields. Five namespace/link paths remain in the complete original JSON because they describe transport metadata, not machine telemetry. New/unrecognized future API properties will also remain in that JSON; this audit establishes complete typed coverage of this response, not undocumented future schemas.

The previous implementation already stored operating/idle hours, cumulative fuel consumed and its unit, remaining fuel/DEF percentages, engine running state, GPS latitude/longitude and machine identifiers. It missed these populated values:

| Measurement | LY02510013 | LY02510058 |
|---|---:|---:|
| PTO hours | 9157 | 7694 |
| Load count | 292 | 333 |
| Fuel consumed in last 24 hours (litre) | 165 | 235 |
| Fuel tank capacity (litre) | 960 | 960 |
| Altitude (metre) | 1627 | 1631 |
| Engine number (text) | 00638737 | 640619 |
| Telematics unit installed (UTC) | 2023-08-31 00:00 | 2025-04-19 00:00 |

The original parser looked for `datetime` and `_fleet_timestamp`, while the actual response uses `@datetime` and `@snapshotTime`. All ten independent measurement-group source timestamps had therefore been lost from the typed fields, although the saved machine JSON retained them. Fuel tank capacity shares the FuelRemaining timestamp; altitude shares Location's timestamp. Engine numbers are strings to preserve leading zeros.

## Field-by-field comparison

Paths below are relative to `Fleet`; `Equipment[]` and `Links[]` refer to each array element. “Previously present” means a typed value existed, not merely the property being in saved JSON. All machine paths remain in `raw_json`, and all paths remain in `raw_response` for new imports.

| Raw JSON path | Results field | Before this audit |
|---|---|---|
| `@snapshotTime` | `fleet_snapshot_timestamp / snapshot_timestamp` | Fleet snapshot timestamp missing |
| `@version` | `fleet_version` | Missing typed field |
| `@xmlns` | `raw_response` | Not retained in original Fleet envelope; now preserved as raw JSON |
| `@xmlns:xsd` | `raw_response` | Not retained in original Fleet envelope; now preserved as raw JSON |
| `@xmlns:xsi` | `raw_response` | Not retained in original Fleet envelope; now preserved as raw JSON |
| `Equipment[].CumulativeIdleHours.@datetime` | `idle_hours_timestamp` | Typed source timestamp empty |
| `Equipment[].CumulativeIdleHours.Hour` | `idle_hours` | Previously present |
| `Equipment[].CumulativeLoadCount.@datetime` | `load_count_timestamp` | Typed source timestamp empty |
| `Equipment[].CumulativeLoadCount.Count` | `load_count` | Missing typed field |
| `Equipment[].CumulativeOperatingHours.@datetime` | `operating_hours_timestamp` | Typed source timestamp empty |
| `Equipment[].CumulativeOperatingHours.Hour` | `operating_hours` | Previously present |
| `Equipment[].CumulativePowerTakeOffHours.@datetime` | `pto_hours_timestamp` | Typed source timestamp empty |
| `Equipment[].CumulativePowerTakeOffHours.Hour` | `pto_hours` | Missing typed field |
| `Equipment[].DEFRemaining.@datetime` | `def_remaining_timestamp` | Typed source timestamp empty |
| `Equipment[].DEFRemaining.Percent` | `def_remaining` | Previously present |
| `Equipment[].EngineStatus.@datetime` | `engine_status_timestamp` | Typed source timestamp empty |
| `Equipment[].EngineStatus.EngineNumber` | `engine_number` | Missing typed field |
| `Equipment[].EngineStatus.Running` | `engine_status` | Previously present |
| `Equipment[].EquipmentHeader.Model` | `model` | Previously present |
| `Equipment[].EquipmentHeader.OEMName` | `oem` | Previously present |
| `Equipment[].EquipmentHeader.PIN` | `pin` | Previously present |
| `Equipment[].EquipmentHeader.SerialNumber` | `serial_number` | Previously present |
| `Equipment[].EquipmentHeader.UnitInstallDateTime` | `unit_install_timestamp` | Missing typed field |
| `Equipment[].FuelRemaining.@datetime` | `fuel_remaining_timestamp` | Typed source timestamp empty |
| `Equipment[].FuelRemaining.FuelTankCapacity` | `fuel_tank_capacity` | Missing typed field |
| `Equipment[].FuelRemaining.FuelTankCapacityUnits` | `fuel_tank_capacity_units` | Missing typed field |
| `Equipment[].FuelRemaining.Percent` | `fuel_remaining` | Previously present |
| `Equipment[].FuelUsed.@datetime` | `fuel_consumption_timestamp` | Typed source timestamp empty |
| `Equipment[].FuelUsed.FuelConsumed` | `fuel_consumption` | Previously present |
| `Equipment[].FuelUsed.FuelUnits` | `fuel_units` | Previously present |
| `Equipment[].FuelUsedLast24.@datetime` | `fuel_used_last24_timestamp` | Typed source timestamp empty |
| `Equipment[].FuelUsedLast24.FuelConsumed` | `fuel_used_last24` | Missing typed field |
| `Equipment[].FuelUsedLast24.FuelUnits` | `fuel_used_last24_units` | Missing typed field |
| `Equipment[].Location.@datetime` | `location_timestamp` | Typed source timestamp empty |
| `Equipment[].Location.Altitude` | `altitude` | Missing typed field |
| `Equipment[].Location.AltitudeUnits` | `altitude_units` | Missing typed field |
| `Equipment[].Location.Latitude` | `latitude` | Previously present |
| `Equipment[].Location.Longitude` | `longitude` | Previously present |
| `Links[].href` | `raw_response` | Not retained in original Fleet envelope; now preserved as raw JSON |
| `Links[].rel` | `raw_response` | Not retained in original Fleet envelope; now preserved as raw JSON |

## Missing values, original JSON and timestamps

- Missing numeric measurements remain Python `None`, SQL `NULL` and JSON `null`. A genuine reported zero remains 0 with its availability flag set. This applies both to database writes and Frappe document serialization; Frappe's default optional numeric coercion would otherwise convert missing values to zero. A scoped DocType schema hook keeps only the 12 Kobelco measurement columns nullable, without changing their numeric types or existing values.
- Both machines genuinely report **DEF 0%**. Those zeros were preserved. A stopped engine is also preserved separately from an unknown engine state.
- `raw_json` preserves the individual machine JSON used for its existing checksum and deduplication. `raw_response` stores the exact original response text for that machine's Fleet page, including envelope attributes, every machine, source timestamps, namespaces and advertised links. The parser never injects internal timestamps into the source dictionaries. Pagination retains the originating page for each machine.
- Original source timestamps, installation date, Fleet snapshot time and fetch time are stored as UTC. Offset-bearing source timestamps normalize to UTC. No timezone is guessed for values that already explicitly declare `Z`.
- Results forms and lists display timestamps in **Africa/Johannesburg** using a shared formatter. The site's existing **Asia/Kolkata** timezone remains unchanged. Field labels are timezone-neutral because standard Data Export retains UTC values; exports and direct API/database access must be interpreted as UTC. Field help and the form introduction explicitly state the display timezone.
- When the original Fleet snapshot is unavailable, `snapshot_time_basis` explicitly identifies a fallback to the latest source measurement. An installation date alone never becomes a measurement snapshot.
- The response declares EngineStatus at **2026-11-19 21:45 UTC**, later than the actual Fleet snapshot **12:06:25 UTC**. These supplied times are retained and flagged in `source_time_warning`; they are not silently corrected. This discrepancy needs vendor confirmation. Other cumulative/fuel source times are 2026-11-18 22:00 UTC, and Location is 2026-11-17 22:00 UTC, demonstrating why individual timestamps matter.

## Existing Results: recoverable corrections applied

Exactly two historical LAB rows were repaired, using only each row's own saved machine JSON. New telemetry, units and individual source timestamps were recovered. Their original local `fetched_at` values, 17:29 Asia/Kolkata, were converted to **11:59 UTC**, which displays **13:59 Johannesburg**, retaining microseconds.

Verified unchanged against the backup: record names, snapshot checksums, original `raw_json`, serial/PIN/OEM/model, Asset and mapping links/status, creation/modification audit fields, and every previously stored measurement including DEF zero. A repeated repair preview reports zero candidates. Test inserts and mutations were rolled back.

Historical complete Fleet envelopes and original Fleet snapshot timestamps were never saved by the old importer and **cannot be reconstructed** from its machine JSON. These fields remain empty on those two rows. Their fallback snapshot basis and the source-time anomaly are explicit. The separate live audit response is not attached retroactively to old snapshots. Future imports retain their complete original response.

Local private evidence is under `/tmp/kobelco-raw-api-audit/`: original live `fleet-page-1.json`, `results-before.json`, `repair-preview.json` and `repair-applied.json` (0600 in a 0700 directory). This temporary location is not durable archival storage.

## Why only two machines?

The actual response advertises:

```json
[{"rel":"self","href":"/Fleet/1?perPage=100"},
 {"rel":"last","href":"/Fleet/1?perPage=100"}]
```

There is **no `next` link**, no fleet-total field, and no pagination/count response header. Both `self` and `last` point to page 1 with a page capacity of 100. The actual two serials are LY02510013 and LY02510058, both SK850LC. This is evidence that the server advertises a single page for this account, rather than the client stopping at a two-machine page limit. The existing client follows advertised next links and preserves the configured base path; its mocked pagination regression tests pass.

The response does **not** establish why only these machines are assigned/exposed. Account fleet assignment, API entitlement and device activation/coverage need confirmation from the Kobelco account/dealer using the expected serial list. They are investigation leads, not proven causes. No additional endpoint was invented, no other account was probed and no speculative `/Fleet/2` request was sent. The audit requested only the configured Fleet endpoint; advertised `self`/`last` links were inspected directly in its JSON.

## Migration and repair instructions

The targeted schema reload has already been applied and repeated successfully in LAB; all 12 measurement columns were verified nullable and both real Results remained present. The two historical repairs are also already applied. Reload Results in the browser for the updated fields and formatter.

For the same implementation in an explicitly authorized environment:

```sh
# Load Results fields and run the scoped nullable-column hook.
bench --site SITE reload-doc engineering doctype kobelco_results
bench --site SITE clear-cache

# Preview only. Set the verified timezone used by that site's legacy importer.
bench --site SITE execute engineering.controllers.kobelco_audit.repair_legacy_results \
  --kwargs '{"legacy_timezone":"Asia/Kolkata"}'
```

Back up and review the preview before applying to other data. Apply only with a verified legacy timezone and explicitly reviewed record names, using the same function with `apply: true` and `names: [...]`. It never calls the vendor API, and preserves identity/raw/audit fields. Do not blindly use Asia/Kolkata for another site's data. The function is not whitelisted for web requests and requires Settings write permission. No automatic historical rewrite was added to migrations. Full `bench migrate` was intentionally not run against unrelated pending patches/fixtures; the relevant Results schema reload and its repeat were verified independently.

## Validation

- 37 Kobelco Python tests passed against LAB with mocked HTTP and rolled-back test data: authentication/secure credentials, advertised pagination and path safety, actual response projection, independent timestamps, missing versus zero at database/API boundaries, exact response preservation, mapping/duplicate/unmapped behavior, read-only and permission guards, rollback behavior, historical preview/apply/idempotence and legacy mapping deletion guard.
- 91 existing controller regression tests passed.
- Six standalone JavaScript UTC/Johannesburg formatter checks passed, including date rollover and explicit offsets.
- Read-only LAB browser checks verify actual Results fields, Johannesburg form/list formatting while the system remains Asia/Kolkata, neutral export labels, engine leading zero, new metrics, genuine DEF zero and the source warning. No Settings reads, saves or vendor calls occur in that browser test.
- Scoped schema reload/repeat, nullable-column checks, Python/JavaScript/JSON syntax and `git diff --check` passed. The existing results count is two. Temporary browser authentication is removed after verification.

Commands from `apps/engineering`:

```sh
/home/juan/juan-bench/env/bin/python tests/run_kobelco_tests.py
/home/juan/juan-bench/env/bin/python tests/run_controller_regressions.py
node tests/test_kobelco_telemetry_format.cjs
KOBELCO_BROWSER_AUTH_FILE=/path/to/private-lab-session.json node tests/verify_kobelco_results_browser.cjs
```

## Files changed by this audit

Modified existing integration files (they were already uncommitted at the start):

- `engineering/controllers/kobelco_client.py`
- `engineering/controllers/kobelco.py`
- `engineering/controllers/test_kobelco.py`
- `engineering/engineering/doctype/kobelco_results/kobelco_results.py`
- `engineering/engineering/doctype/kobelco_results/kobelco_results.json`
- `engineering/engineering/doctype/kobelco_results/kobelco_results.js`
- `engineering/engineering/doctype/kobelco_results/kobelco_results_list.js`
- `engineering/engineering/doctype/api_kobelco_settings/test_api_kobelco_settings.py`
- `docs/kobelco-integration.md`

Added:

- `engineering/controllers/kobelco_audit.py`
- `engineering/controllers/fixtures/kobelco_fleet.json` (actual response fixture; no credentials)
- `engineering/public/js/kobelco_telemetry_format.js`
- `tests/test_kobelco_telemetry_format.cjs`
- `tests/verify_kobelco_results_browser.cjs`
- `docs/kobelco-api-audit.md`

No DocTypes were deleted during this audit. No hooks, workspace, permission fixtures, MPI or WearCheck files were changed during this audit.
