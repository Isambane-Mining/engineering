# Machines Available implementation plan

Goal: reproduce the machine availability tab as an independent Engineering Desk Page.
Specification: user request dated 2026-11-05. Existing source is the reference for UI and API behaviour.
Architecture: copy only the matrix renderer and machine filter controller; call existing permission-checked is_production defaults, analysis and Excel APIs. Keep copied CSS scoped to this page and leave source dashboard untouched.
Constraints: preserve unrelated changes; LAB only (juan.isambane.co.za); no commits, push or PR; no calculation duplication or shared stylesheet edits.

- [x] Add failing renderer parity, filter/controller/browser and backend Excel/permission tests.
- [x] Add native Page metadata, isolated JS/CSS, package marker, and workspace shortcut/link.
- [x] Run backend and JS/browser regressions; build Engineering assets.
- [x] Reload only Page on LAB and append navigation without overwriting unrelated live workspace changes; clear LAB cache.
- [x] Verify native loader, live API/filter scopes/export and browser route; report evidence and blockers.

Review focus: unknown/pending values, month boundaries, unavailable range including zero, stale responses after invalid filters/errors, denied source permissions, export selected filters, CSS leakage into existing dashboard.

Validation completed:
- 43 Python tests passed (new backend and Chromium fixture tests plus existing source backend regressions).
- 17 Node tests passed (new matrix/interval parity tests plus source renderer regressions).
- Engineering asset build passed; JS syntax and git diff whitespace checks passed.
- LAB Page and workspace activated with targeted document updates. Existing workspace rows/content preserved. No schema changes or broad migrations required.
- Live Chromium through local LAB HTTPS verified native Desk route, real Frappe controls, 24 cells, All/Production/Spare API scopes, unavailable filter, Excel download/filter metadata, desktop/mobile, and absence of other tabs/summary assets.
- Live API exports passed for every scope with Koppie 2026-08-01. LAB has plans through August; later dates correctly report no accessible plan.
- Source dashboard JS/Python/CSS and shared Engineering CSS hashes remain unchanged.
- Independent review found an initialization race; added a failing regression and fixed refresh after defaults resolve. Final suite includes this test.
- No production changes, commits, push or PR. No remaining implementation blockers.

LAB evidence: /tmp/machines-available-tests.log, /tmp/machines-available-js-tests.log, /tmp/machines-available-build.log, /tmp/machines-available-lab-desktop.png, /tmp/machines-available-lab-mobile.png, /tmp/machines-available-lab.xlsx. Pre-activation Page/workspace snapshot: /tmp/machines-available-lab-before.json. Temporary browser session removed after checks.
