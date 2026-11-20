# Machines Available viewing options

Reference: /home/juan/machines_available_mobile_options.html, read 2026-11-05.
Implement prototype Month/Day/Heatmap navigation, KPI cards/calendar, hourly list and compact monthly heatmap within native Desk. No phone frame, demo sidebar or sample figures. Keep real Site/from/to/scope/unavailable filters and Excel API. Calendar/day order uses operational 06:00–06:00, unlike prototype's simulated calendar-day hours.

Design decisions: calendar default; active month selector covers selected filter range; full month slots always visible but out-of-range dates disabled/unknown. In-range inaccessible or pending data never synthesised. Monthly/daily KPIs aggregate completed recorded source cells only; zero valid observations shows unknown. Calendar shading uses available/fleet ratio (same 80/50/20 legend thresholds); hourly/heatmap retain existing utilised/available colours. Fleet size is historical MPP; variable monthly fleets labelled average. No calculation API duplication: existing get_analysis, get_hour_breakdowns and export_machine_excel remain authoritative.

- [x] Add failing renderer/aggregate, browser navigation/filter/popup/export and backend source-contract regressions.
- [x] Implement scoped prototype styles, renderers and state; preserve source matrix renderer regression contract.
- [x] Run regression suites/review, build Engineering assets.
- [x] Validate native LAB with real month/calendar/day/heatmap interactions and exports at mobile/desktop. Remove test session; confirm source/shared stylesheet hashes unchanged.
No production changes, commits, push or PR. Preserve unrelated dirty files.

Completed validation:
- 59 Python/backend/Chromium tests passed, including existing source, permissions, PBM interval/night/field-redaction regressions, full-month operational payload and historical MPP scope contracts, responsive view navigation/shared filters, heatmap-to-day selection, popup pin/toggle/dismissal, stale data and all-mode export wiring.
- 20 Node tests passed, including original matrix parity/colour regressions, safe popup rendering, month lengths/leap year/Monday alignment and recorded-only KPI aggregation, daily 24-hour order and red borders.
- Engineering build passed. JS syntax and Git whitespace checks passed.
- Live LAB native Desk validation against Koppie August 2026: 31-day calendar, KPI comparison against actual source response, 24-hour day navigation, 31×24 heatmap, real PBM popup/pinning/night rollover, All/Production/Spare scopes, selected-filter XLSX downloads from all three modes, 390px and 1440px layouts and scrolling. No JS errors.
- Mobile native Desk screenshot inspected. Scoped unavailable-selector override prevents shared dashboard CSS from spanning the entire mobile row. Daily popup placement preserves the selected row as a click target.
- Independent review found no material issues. Average fleet uses all selected dates' historical MPP fleet; activity KPIs use completed recorded hours, as labelled.
- Existing calculation/breakdown/export APIs unchanged; no new backend production code, schema migration, shared stylesheet edits or source-dashboard changes.
- LAB cache cleared. Temporary browser session removed. No production changes, commits, push or PR. No blockers.

Changed files under engineering/engineering/page/machines_available/: machines_available.js, machines_available.css, test_machines_available.cjs, test_machines_available_browser.py, test_view_data_contract.py (new); plus this plan/validation record.
Evidence: /tmp/machines-views-tests.log, /tmp/machines-views-js.log, /tmp/machines-views-build.log, /tmp/machines-views-live.log, /tmp/machines-views-lab-{calendar,day,heatmap}-{390,1440}.png, /tmp/machines-views-lab-calendar-mobile-clean.png. Native LAB validation script: /tmp/machines_views_live_lab.py (temporary session removed after checks).
