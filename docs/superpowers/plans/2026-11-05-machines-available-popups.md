# Machines Available hourly breakdown popups

Specification: user request 2026-11-05. Extend only Engineering Machines Available. Preserve source dashboard, filters/matrix/export and shared CSS. LAB only; no commits/push/PR.

Architecture: lazy hour-specific backend endpoint, existing accessible historical MPP scope and document/list/field permission helpers. Filter PBM query by site, selected ADTs and strict overlapping timestamps; no hourly production reload. Group records per machine; reuse existing union-of-intervals downtime calculation. Client popup shows current cell counts, record details and per-machine unique minutes. Pointer hover previews; click/keyboard pins; dismissal invalidates pending responses. Fixed positioning tracks nested scroll, viewport and page visibility. No cross-hover data cache.

- [x] Write failing backend and browser tests for bounds/night rollover/scope, permissions/redaction, interval unions, hover/pin/dismissal/stale responses/scroll/mobile.
- [x] Implement endpoint, popup controller and scoped styles, retain matrix parity except accessibility/data attributes.
- [x] Run backend, JavaScript/browser regressions, review, build Engineering assets.
- [x] Clear LAB cache/reload only LAB web process if needed; validate actual API/native Desk hover/pin/Excel, remove temporary session.
- [x] Record evidence and blockers; no unrelated changes.

Completed validation:
- 54 Python/backend/Chromium tests passed, including source backend regressions, interval unions, boundary/subminute/night cases, historical MPP scope, inaccessible documents, redacted classification, canonical Asset ID collision, hover/pin/dismissal/stale responses and mobile placement.
- 18 Node tests passed, including source matrix markup parity excluding new accessibility/data attributes, source renderer regressions and escaped popup fields.
- Engineering build, JS syntax, Python compilation and git whitespace checks passed.
- LAB native Desk page verified through local HTTPS with real PBMs: all requested popup fields, hover/pin/switch/toggle/outside/Escape/close, night hour, scrolling, empty results, production/spare scopes, red highlighting, selected-filter Excel and mobile bounds. No JS errors.
- Backend live API verified against Koppie 2026-08-01 real overlapping PBM, all three historical MPP scopes and Guest denial. No source records were changed.
- Review found a display-label/Asset-ID collision; canonical ID lookup fixed and regression observed fail then pass. Review confirmed fix with no remaining material findings.
- Mobile popup is constrained to space above or below the selected row, preserving access to the tapped cell. Browser tests assert row non-overlap.
- Original dashboard JS/Python/CSS and shared Engineering stylesheet hashes unchanged.
- LAB cache cleared; no schema migration or web process restart needed. Temporary test session removed. No production changes, commits, pushes or PRs. No remaining blockers.

Changed files: machines_available.py (new endpoint), machines_available.js (popup/render interactions), machines_available.css (scoped popup styles), test_hour_breakdowns.py (new backend tests), test_machines_available.cjs (renderer regression/escaping), test_machines_available_browser.py (interaction tests), this plan/validation record.
Evidence: /tmp/machines-popup-tests.log, /tmp/machines-popup-js-tests.log, /tmp/machines-popup-build.log, /tmp/machines-popup-lab-desktop.png, /tmp/machines-popup-lab-mobile.png. Live check scripts: /tmp/verify_machines_popup_lab.py, /tmp/machines_popup_live_browser.py (require a temporary LAB session; removed after validation).
