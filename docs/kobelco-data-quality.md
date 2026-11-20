# Kobelco data-quality investigation — 19 November 2026

Investigated the two existing LAB Results on branch `juan`. Findings were reported before adding regression coverage. No extraction or timezone defect was reproduced in the three reported cases. No runtime code, schema, historical telemetry, original JSON or Asset mapping was changed. No vendor calls, production operations, commits or pushes were performed.

## Missing Fleet metadata

Both historical Results contain their original individual machine JSON in `raw_json`, but have no retained complete Fleet envelope in `raw_response`. Neither machine object contains Fleet API version or Fleet snapshot time. Consequently `fleet_version` and `fleet_snapshot_timestamp` are correctly empty for these rows.

The separately retained later audit response has `Fleet.@version = "1"` and `Fleet.@snapshotTime = "2026-11-19T12:06:25Z"`. That response was captured after the historical imports; it cannot prove the original envelope metadata. It was not used to fill historical gaps.

The current client reads those envelope attributes from each machine's originating page, and the sync controller stores them on new Results. Regression coverage confirms that metadata from one page cannot populate missing metadata on another page. Existing deduplication leaves historical rows unchanged when the same machine observation is returned again.

## Future Engine Status and Snapshot times

Both saved machine objects explicitly contain:

```json
"EngineStatus": {
  "@datetime": "2026-11-19T21:45:00Z",
  "Running": "false"
}
```

The database stores `engine_status_timestamp = 2026-11-19 21:45:00` UTC and the form displays `2026-11-19 23:45:00` in Africa/Johannesburg. The source explicitly declares UTC (`Z`); the future time is not introduced by a local-to-UTC conversion. It is later than the historical UTC fetch times, approximately 11:59, and was still future-dated at investigation time, approximately 13:34 UTC.

Both historical rows have `snapshot_time_basis = "Latest source measurement"`. Without the original Fleet timestamp, the existing documented fallback selects the latest individual measurement time, which is EngineStatus at 21:45 UTC. Thus the generic `snapshot_timestamp` is derived, not a recovered original Fleet snapshot. The existing source-time warning identifies the anomaly.

When an actual Fleet timestamp is supplied, the parser keeps it as the snapshot, retains the later EngineStatus timestamp separately and flags the discrepancy. Regression coverage checks both paths. No timestamp was clamped to fetch time, shifted to a speculative timezone or otherwise changed. Kobelco needs to confirm why its source timestamp is future-dated.

## PTO versus operating hours

| Serial | Saved `CumulativeOperatingHours.Hour` | Saved `CumulativePowerTakeOffHours.Hour` | Stored operating / PTO |
|---|---:|---:|---:|
| LY02510013 | `"9157"` | `"9157"` | 9157 / 9157 |
| LY02510058 | `"7694"` | `"7694"` | 7694 / 7694 |

The equality exists in the original source fields. Both source groups also declare `@datetime = "2026-11-18T22:00:00Z"`. The parser reads PTO and operating hours independently. A regression test uses deliberately different values and timestamps to prove this; removing PTO leaves it missing rather than copying operating hours. Equality alone does not establish a defect or justify changing the measurements. The equipment-specific meaning of Kobelco's PTO counter requires vendor confirmation if unexpected.

## Verification and scope

An independent read-only comparison, without calling the integration normalizer, checked all 33 retained machine JSON leaf paths against their database columns on both Results: **66 comparisons passed**. It also checked numeric availability flags, the shared fuel-capacity timestamp, snapshot basis/fallback and original JSON checksums. No mismatches were found.

A complete pre/post comparison of all Results and child mapping fields passed after the tests. This includes the source JSON strings, timestamps, existing measurements, Asset links and audit fields. No historical repair was executed during this investigation.

Validation:

- `tests/run_kobelco_tests.py`: **40 tests passed**, including three new focused regression tests.
- `tests/test_kobelco_telemetry_format.cjs`: **eight checks passed**, including two new checks for the exact suspect timestamp, in ISO UTC and database formats.
- `git diff --check`: passed.

Only these files were edited during this investigation:

- `engineering/controllers/test_kobelco.py`
- `tests/test_kobelco_telemetry_format.cjs`
- `docs/kobelco-data-quality.md` (this report)

MPI, WearCheck and unrelated uncommitted work were not edited. No migration or web-process reload is needed because runtime code and schema are unchanged. Findings establish agreement with the retained API data; they do not independently validate the accuracy of the vendor's physical measurements or clock.
