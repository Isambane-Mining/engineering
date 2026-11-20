> **Current status — final formula/visual refinements complete:** corrected daily Industry MAX/MIN denominator, 12-column layout, Day/Night colours and concise popups implemented and verified on actual LAB after explicit user-approved LAB-only reload. See **Final formula/visual acceptance** at the end. Earlier checkpoints are historical.

# AU24 implementation checkpoint — 18 November 2026

## Branch / baseline
- Working on `juan`; latest local commit `1012a0173036f23da3c7f94e5fe54e8609719842`.
- Read-only `git ls-remote upstream refs/heads/juan` reports the same commit. Cached upstream/juan is older; no fetch/merge performed.
- Unrelated dirty files inspected and preserved. Original Engine must remain untouched.

## Approach / stage
- Inspection complete. Original Engine's `apply_au_percentage_basis` multiplies percentage values by 0.85 for 85% basis and 1.0 for 100%, then rounds to 3 percentage decimals. Hours are unchanged.
- Reuse original shift/source pipeline and this exact scaling function for Isambane, including weighted totals.
- Industry will expose Availability, Use of Availability and Utilisation together; two formula choices only.
- Standard Frappe DataTable inline filters will be reused. Their visible row set will drive a read-only canonical-controller total endpoint, so bottom totals always match visible machines.

## Completed
- Inspected request, working tree, commits, original Engine, Frappe Query Report and DataTable filtering implementation.

## Outstanding
- Implement dynamic columns, Industry additional ratio, Isambane basis, inline filters/totals and updated formula dialog.
- Focused syntax / calculation / one LAB report verification.

## Files modified in this task
- AU24_CODEX_HANDOFF.md (this checkpoint).

## Incomplete functions / errors
- None changed yet. No errors.

## Tests executed
- None yet; inspection only.

## Next Bash commands
```bash
cd /home/juan/juan-bench/apps/engineering
git status --short --branch
git diff -- 'engineering/engineering/report/availability_and_utilisation_engine_(24)'
```
No commits, pushes, merges, deployment, business-record population or service restarts authorised.

## Stage 1 implementation complete (verification pending)
- Canonical controller now has two formulas and ten relevant columns per formula; Site retained internally only.
- Industry computes all three ratios and daily anomaly flags, including zero-available-hour inconsistencies.
- Added validated `isambane_basis` (default 100%, preserving existing report default); forwards selection into original Engine, and reuses original basis scaling/rounding for machine and weighted total percentages.
- Added permission-checked, read-only `get_filtered_total` endpoint. No records are changed.
- UI uses standard inline-filter inputs/matching and keeps total last. Multi-column matching intersects sets to avoid installed DataTable's empty-result restart bug; percentage searches use displayed percentage units.
- Formula dialog now documents both final formulas, Industry's extra ratio, and selected Isambane basis.
- Existing styling preserved with dynamic widths and visible search row.

### Files modified in this task
- `engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).py`
- `engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js`
- `AU24_CODEX_HANDOFF.md`

### Checks so far
- Python AST syntax: PASS.
- JavaScript `node --check`: PASS.
- Remaining: requested calculation examples, one LAB run, focused column/filter check.
- No intentionally partial functions. Browser behaviour not verified yet.

## Stage 2 verification and documentation
### Completed requirements
- Removed table Site column; Site filter/internal grouping unchanged.
- Two Formula options only; ten relevant columns each.
- Industry has all three distinct ratios (Availability / Use of Availability / Utilisation).
- Isambane exposes both original Engine percentage bases; exact existing scaling/rounding helpers reused. Default remains prior 100% behaviour.
- Standard visible column searches support Asset, Asset Type and numeric operators; percentage searches use display units. Weighted total stays last and represents the exact visible machines, including empty results.
- Formula help and targets updated, visual improvements retained.
- Original Engine/controller and original Startup/Fatigue records unchanged; no duplicate report folder or helper controller introduced.

### Focused verification executed
- `node --check` on canonical JS: PASS.
- Python AST syntax on canonical controller: PASS.
- `/tmp/au24_refinement_check.py`: PASS. Industry example: 20h available, A=83.333333%, Use=75%, U=62.5%. Original Engine Isambane example required=12h/PBM=2h/work=9h: 100% basis A=83.333%, U=90%; 85% basis A=70.833%, U=76.5%; hours unchanged.
- Same script: both dynamic ten-column schemas verified, no Site/irrelevant columns; one actual LAB report run for Uitgevallen 1–7 Aug 2026: 27 machines plus one total. A=0.8930731922398589, Use=0.3927444717080805, U=0.3507495590828924 (decimal ratios).
- `/tmp/au24_refinement_browser.cjs`: focused browser check PASS, reusing the saved real LAB run for table rendering instead of more source queries. Live `get_filtered_total` endpoint used. IS56 search selects five machines; >98 availability narrows to IS564/IS565. Their weighted total reconciles; empty multi-column intersection produces only the total with zero hours and dash ratios. Both formula options, ten Industry columns, first-column search enabled and 390px page width verified.
- Inspected `/tmp/au24-refined-desktop.png`, `/tmp/au24-refined-formula.png`, `/tmp/au24-refined-mobile.png`.
- Initial browser check had a fixture expectation error (assumed IS314; actual real fleet is IS0314) and did not intercept query-string report URLs. Corrected the check to use actual IS56 fleet data and route pattern; no product error caused that initial timeout.

### Additional exact files modified
- `engineering/engineering/report/availability_and_utilisation_engine_(24)/README.md`: aligned existing documentation with final requirements; preserved other content.
- `tests/test_au24_engine.py`: surgically migrated existing over-100% example from removed standalone formula into the Industry Use column; other existing uncommitted tests preserved. This test was not separately executed; requested examples were checked through the script above.

### Outstanding / limitations
- No core requirement intentionally left partial.
- No broad regression suite, second live Isambane dataset run, service reload, deployment, commit, push or merge performed.
- Older broad/browser helper assertions may still reference the superseded 15-column or third-formula layout; do not interpret those as the current specification. Updating/running broad suites was outside the requested minimal check cycle.
- Column totals require the read-only LAB endpoint to be reachable. On failure the previous rows/totals are retained and a message explains filtering was not applied.
- Final syntax, protected-file and working-tree checks/temporary-session cleanup still pending at this checkpoint.

## Final checkpoint — ready for review
- Final canonical JavaScript syntax and Python/controller/test syntax: PASS.
- `git diff --check` on all task files: PASS.
- `git diff --exit-code HEAD` for original Engine folder and original Startup/Fatigue DocType: PASS (unchanged).
- Confirmed no duplicate `_24` report folder or `calculations.py`.
- Temporary browser session removed.
- Branch remains `juan`, HEAD remains `1012a0173036f23da3c7f94e5fe54e8609719842`. No commits/push/merge/deploy/restart performed.
- Exactly five task files were touched: canonical `.py`, canonical `.js`, existing report `README.md`, existing `tests/test_au24_engine.py`, and this root checkpoint. All other dirty files are pre-existing and were left alone.
- Core requested implementation is complete. No partially implemented function remains. Manual review is next; broader suites and additional live-data scenarios were deliberately not run.

## Exact recommended next Bash commands (review only)
```bash
cd /home/juan/juan-bench/apps/engineering
cat AU24_CODEX_HANDOFF.md
git status --short --branch
git log -1 --oneline
git diff -- 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).py' 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js' 'engineering/engineering/report/availability_and_utilisation_engine_(24)/README.md' tests/test_au24_engine.py
```

Open the existing LAB report for manual review:
`https://juan.isambane.co.za/app/query-report/Availability%20and%20Utilisation%20Engine%20(24)`

Suggested review: Industry / Uitgevallen / 1–7 August 2026, then Asset column search
`IS56` and Availability column search `>98`. Expected visible machines: IS564 and
IS565, with a weighted bottom Total / Average row. Then switch Formula to Isambane
and inspect the two basis options. Do not commit, push, merge, deploy or restart
services until separately approved.

Optional focused checks only if you change code during review:
```bash
cd /home/juan/juan-bench/apps/engineering
node --check 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js'
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests /home/juan/juan-bench/env/bin/python -B -m unittest test_au24_engine.Engine24Tests
```
The calculation/one-LAB-run script and focused browser script used this session
remain at `/tmp/au24_refinement_check.py` and `/tmp/au24_refinement_browser.cjs`;
actual LAB result fixture is `/tmp/au24_refinement_lab.json`. The temporary browser
authentication file was removed, so the browser script needs a new temporary LAB
session if explicitly reused. These `/tmp` artifacts are not repository files.

# Active continuation: expandable tree and formula presentation — 18 November 2026

## Inspection / approach
- Branch still `juan`, HEAD `1012a01`; previous AU24 and unrelated dirty work preserved.
- Original Engine hierarchy is category → date → machine → shift, category priority ADT/Dozer/Excavator then alphabetical, dates/machines/shifts sorted. Original JS uses `initial_depth: 0` and Frappe's standard tree controls.
- Important original Industry contract: calculations are daily; shift children are source detail only. Keep one 24-hour base per machine/day, never one per shift. Shift calculated cells will be neutral dashes with a clear source-detail explanation; machine/day row holds the actual calculation. Isambane shift calculations remain the actual original Engine values.
- Reuse original `build_tree_rows` for hierarchy/order and original Engine summary helpers for Isambane. Industry parent totals aggregate atomic machine-days only.
- Tree search selects atomic machine-days (Industry) or shifts (Isambane), then rebuilds all matching ancestors/subtotals and bottom total. Collapsing rows changes disclosure only, not selected data.

## Outstanding at start
- Tree rows, source shift detail, tree-aware column search, two available-hours dialogs, reordered/highlighted columns.
- Focused syntax/calculation/LAB/tree/filter/desktop/mobile verification.

## Tree stage 1 — implementation complete, focused verification pending
- Reused original Engine `build_tree_rows` for exact hierarchy/order. Site/fleet keys keep identical labels at separate sites distinct internally.
- Isambane maps actual original Engine shift values and recomputes category/date/machine/bottom summaries from integrity-aware source shifts; original scaling/rounding helpers remain in use.
- Industry retains unchanged `calculate_day` and `total_row`; its atomic data is now retained per machine/day. Shift raw work and PBM detail use the original shift-clock helper only, without configuration access. Calculated shift cells intentionally remain dashes like the original Industry drill-down.
- Added permission-checked `get_filtered_tree`; tree searches rebuild only matching atomic rows and their ancestors. Standard expand/collapse acts on the trimmed tree, so excluded children cannot reappear.
- Added both available-hours formula dialogs with equations, variables, examples and selected basis. Working Hours moved alongside raw inputs; calculated hours have green/purple backgrounds and Use of Availability has a distinct subtle blue-green background.
- Python/JavaScript syntax PASS. Actual calculations, one LAB run, tree interaction/filtering and responsive checks remain pending.
- Files so far this continuation: canonical report `.py`, canonical report `.js`, root handoff. Original Engine and configurations untouched.

## Tree stage 2 — calculations and preview verified
- Python/JS syntax passed.
- `/tmp/au24_tree_check.py` passed: Industry worked example; Isambane worked example at each basis; source shift and parent subtotals; correct column order.
- One actual fresh-process LAB report run: Uitgevallen 1–7 August 2026, Industry. 616 tree rows = 6 categories + 42 category/dates + 189 machine-days + 378 Day/Night details + one bottom total. 27 unique machines. Unique machine/day identity checked; every parent subtotal reconciles to atomic days. All bottom underlying hours and all three ratios match the saved pre-tree report within 1e-8.
- Industry example: raw breakdown=3h, raw maintenance=1h, work=15h, available=20h; A=83.333333%, Use=75%, U=62.5%. Day/Night source rows do not get a second 24h base.
- Isambane example: required=12h, PBM=2h, work=9h; both available-hour values=10. 100% basis: A=.83333/U=.9. 85% basis: A=.70833/U=.765. All hierarchy levels and bottom reconcile, hours unchanged.
- `/tmp/au24_tree_browser.cjs` focused preview passed: progressive category/date/machine expansion to Day/Night; collapse; both extra formula buttons; live explanation updates on basis changes; Industry raw shift work reconciles to parent; IS56 selects 35 atomic machine-days with valid ancestors; >98 search uses displayed percent units; collapse/expand cannot resurrect filtered fleets; empty intersection keeps one zero-hours/dash total; highlighted Isambane source shift values; 390px viewport has no document overflow.
- Rendering uses the saved actual LAB Industry result and the explicitly synthetic worked-example Isambane result; no extra live report-data cycles were run. `/tmp/au24-tree-desktop.png`, `...-filtered.png`, `...-hours.png`, `...-isambane.png`, `...-mobile.png` inspected. Isambane/mobile screenshots show the formula popup because of Bootstrap hide-transition timing in the check; DOM calculations/colour classes and responsive width assertions passed.

### Important outstanding LAB worker dependency
- The existing LAB web worker has a cached previous controller. Live request to the new `get_filtered_tree` returned HTTP 417 / missing method. The source imports/runs correctly in a fresh LAB Python process.
- No worker restart, module hot reload, deployment or cache invalidation was performed, per the user's restrictions.
- To finish source/UI verification safely, the browser check intercepted only the new method and used `/tmp/au24_tree_preview_bridge.py` to execute that exact canonical controller endpoint in a fresh, permission-checked, read-only LAB process. This is a temporary test bridge, not application code or a deployed workaround.
- Consequently the SOURCE implementation and preview are verified; normal live Desk tree loading/search still needs the approved LAB worker reload and one live acceptance check afterwards. Do not claim the running cached worker is updated.
- On endpoint failure the previous tree/totals remain displayed and a message explains that the search was not applied.

## Tree final handoff
### Completed
- Expandable original category/date/machine/shift hierarchy and ordering; standard Frappe tree controls.
- Weighted category/date/machine and bottom summaries from atomic source data, without parent/child duplication.
- Industry daily calculations retained unchanged; source shifts stay visible beneath daily calculations with explanatory tooltips/dashes. Isambane actual shift calculations and both percentage bases preserved.
- Working Hours reordered to column six, Site remains internal/filter-only, both formula choices and basis selector retained.
- Added Availability Available Hours and Utilisation Available Hours buttons with dynamic, formula-specific equations, variables, examples and basis information. Existing View Formula kept.
- Calculated hours/percentages highlighted, Use of Availability distinguished, raw inputs neutral, >100 warnings/progress indicators/sticky headings/responsive controls retained.
- Atomic column matching, matching ancestor/subtotal rebuilding, no orphan children, no filtered-child resurrection, empty-match total retained. Edits typed while an earlier filter request is pending are preserved.

### Exact files modified in THIS tree continuation
1. `engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).py`
2. `engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js`
3. `engineering/engineering/report/availability_and_utilisation_engine_(24)/README.md`
4. `AU24_CODEX_HANDOFF.md`
Previous uncommitted AU24 changes and all unrelated work were preserved. No Python helper file, duplicate report folder or DocType was added.

### Final validation
- Canonical Python/JavaScript syntax PASS; task-scoped `git diff --check` PASS.
- AST comparison against pre-tree source: `calculate_day`, `total_row`, `ratio`, `read_assets`, `read_sources`, `read_preuse` and `get_site_configurations` unchanged.
- Original Engine and Startup/Fatigue source folders unchanged against HEAD.
- Focused calculations, one actual LAB report, parent reconciliation, progressive expansion, search/totals and responsive preview results are recorded above.
- No extensive regression suite. No changes to business/configuration records. Temporary browser authentication session cleaned up at the end.

### Outstanding / incomplete
- **Running LAB worker reload and one live Desk acceptance check remain outstanding.** The cached worker does not expose new `get_filtered_tree` (observed HTTP 417 / method missing), despite fresh-process import/execution succeeding. Do not mistake the preview bridge for deployment.
- No intentionally partial product functions remain. Normal live use must wait for that approved worker reload; source and preview verification are complete.
- Industry shift calculation cells are deliberately dashes because its approved denominator is daily, matching the original Engine's Industry drill-down design. Managers see raw source shift inputs and the actual calculated machine/day row directly above. A new per-shift Industry formula was not invented.

### Exact next Bash commands — review only
```bash
cd /home/juan/juan-bench/apps/engineering
cat AU24_CODEX_HANDOFF.md
git status --short --branch
git log -1 --oneline
git diff -- 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).py' 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js' 'engineering/engineering/report/availability_and_utilisation_engine_(24)/README.md'
node --check 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js'
```
The current branch is `juan`; latest commit remains `1012a0173036f23da3c7f94e5fe54e8609719842`.
No commit, push, merge, deployment, service restart or module hot reload was performed.
Do not run a blanket `bench restart`. The LAB-specific worker/service and its safe
reload command must be confirmed and authorised before live acceptance.

After the approved LAB-only reload, open:
`https://juan.isambane.co.za/app/query-report/Availability%20and%20Utilisation%20Engine%20(24)`

Use Industry / Uitgevallen / 1–7 August 2026. Expand ADT → 2026-08-01 → EX217:
Day work 8h plus Night work 7h reconciles to 15h; machine/day base remains 24h.
Search Asset `IS56` (35 atomic machine-days), then Availability `>98`; verify the
filtered branch totals, expand/collapse and clear both searches. Inspect Isambane
at both bases and both available-hours dialogs, then review mobile layout.

Temporary check artifacts (not repository files):
- `/tmp/au24_tree_check.py` — requested examples + one real LAB run and reconciliation.
- `/tmp/au24_tree_lab.json` — saved actual LAB tree result.
- `/tmp/au24_tree_browser.cjs` — focused preview (requires a new temporary auth session).
- `/tmp/au24_tree_preview_bridge.py` — fresh-process read-only preview bridge only.
- `/tmp/au24-tree-desktop.png`, `/tmp/au24-tree-filtered.png`, `/tmp/au24-tree-hours.png`.

## Active fix: live LAB tree, stable filtering and exact popups
- Branch `juan`, HEAD `1012a01`, unrelated dirty files preserved.
- Root causes confirmed: LAB Gunicorn (`--preload`) still caches the older controller; both canonical methods exist and are whitelisted in a fresh import. Previous filter implementation replaced the header/input DOM on every search and allowed DataTable's keyboard navigation to receive input-editing keys.
- Implemented body-only tree data replacement, preserving the existing header/input nodes, caret and tree disclosure state. New/previously collapsed branches do not auto-expand. Header editing keys stay in the input; input events support paste/mobile; duplicate keydown/input requests are suppressed.
- Industry columns now end Availability / Utilisation / Use of Availability, with Use immediately after Utilisation. Working Hours remains next to raw inputs.
- Available-hours popups use WH, ReqH and applicable adjusted Downtime, and exact 12h required / 11h work / 1h downtime examples yielding 11h for both Isambane calculations. Industry retains raw downtime and 24h utilisation available hours.
- Python syntax/import/canonical path/whitelist/order check and JS syntax: PASS.
- Operator sudo policy explicitly permits `sudo -n /usr/bin/supervisorctl restart juan-bench-web:`. Supervisor configuration scopes that group to the LAB web server (127.0.0.1:8007) and LAB Socket.IO (9007). Nginx maps only juan.isambane.co.za and this bench contains only that site. Production services have separate prod-bench groups.
- Next: requested approved-mechanism LAB-only web group reload, then one actual LAB browser report with expansion/filter/popup/subtotal checks. No preview interception or bridge will be used.

## Live LAB final acceptance — authoritative current checkpoint
### Completed fixes
- Flat live results/missing-method errors resolved by reloading the stale preloaded LAB web service through the existing operator-permitted command.
- Category → Date → Machine → Day/Night arrows verified in the actual LAB browser, with original Engine hierarchy and no duplicate daily denominator.
- Search now updates only the tree body. It retains the same header and input DOM nodes, keyboard focus/caret, scroll position and existing open/closed branch state. Input editing keys no longer bubble to DataTable cell navigation. Input events support paste/mobile; duplicate input/keydown requests are suppressed.
- Relevant parents/subtotals and weighted bottom total are rebuilt from atomic data; unrelated branches do not auto-expand.
- Industry columns now place Utilisation immediately before Use of Availability; Working Hours remains beside raw inputs.
- Both Isambane hours popups use exact WH/ReqH/Downtime formulas and 12h required / 11h work / 1h downtime examples yielding 11h for both available-hours values. Industry raw-downtime versus Isambane adjusted-downtime distinction retained; no extra deductions.

### Approved LAB-only service action performed
```bash
sudo -n /usr/bin/supervisorctl restart juan-bench-web:
```
- Exact command explicitly permitted by the host's NOPASSWD operator policy and within the user's requested LAB reload scope.
- Confirmed Supervisor symlink `/etc/supervisor/conf.d/juan-bench.conf` → this bench's config.
- Group contains only `juan-bench-frappe-web` (127.0.0.1:8007, --preload) and `juan-bench-node-socketio` (9007).
- Nginx maps this bench to juan.isambane.co.za; this bench has only that site. Production is a separate `prod-bench` service group and was not restarted. No workers, Redis, database or other benches restarted.
- Command completed successfully: both LAB web group processes stopped and started. No schema/configuration/business-record changes or deployment performed.

### Files changed in this fix
1. Canonical AU24 `.js`: stable filtering and exact popup presentation/examples.
2. Canonical AU24 `.py`: Industry column order only; every existing calculation/source/tree/permission function is AST-identical to the pre-fix snapshot.
3. Existing report `README.md`: current column/filter and activation notes.
4. Root `AU24_CODEX_HANDOFF.md`.
All earlier/unrelated uncommitted files preserved. Original Engine and Startup/Fatigue source unchanged against HEAD.

### Focused verification results
- JS syntax: PASS. Python syntax/import: PASS.
- Fresh import resolved the exact canonical path; both `get_filtered_total` and `get_filtered_tree` exist and are whitelisted.
- Actual site calls to BOTH methods: PASS. One atomic Industry machine-day returns 24h from total endpoint and six hierarchy rows/24h from tree endpoint.
- Successful focused browser workflow `/tmp/au24_live_acceptance.cjs`: PASS, exit 0. Exactly one real report call in that workflow: Industry / Uitgevallen / 1–7 August 2026, 616 tree rows, 189 atomic machine-days, 27 fleets. No Playwright routing/interception, fixtures, report-code injection or preview bridge.
- Expanded ADT/date/EX217 to Day and Night. 8h + 7h = 15h work; daily base stays 24h, source shifts do not get another daily base.
- Full weighted hours reconcile with atomic rows, and Use of Availability divides summed work by summed available hours.
- Typed partial `IS5`, then continued `6` in the SAME input. Matching atomic days narrowed 49 → 35. ArrowLeft moved caret inside input without cell navigation. Header/input element identities, focus, caret and scroll all preserved.
- Added Availability `>85` search using display percentage units: 26 atomic machine-days; weighted total reconciles. Only the previously opened ADT/2026-08-01 branches remain open.
- Both available-hours popup buttons checked for Industry and Isambane; formula selection changed presentation without running another source report, and both exact 11h examples checked. Zero browser page errors.
- Initial browser navigation attempts entered the Desk launcher before it finished loading and left the report hidden. Diagnosed via screenshot/DOM; fixed the CHECK to navigate directly to the report URL with filters. No product CSS workaround or synthetic preview was used. Those diagnostic attempts loaded the same report before the successful final pass; no broad regression/browser suite was run.
- Inspected actual screenshots: `/tmp/au24-live-fixed-desktop.png`, `/tmp/au24-live-isambane-availability.png`, `/tmp/au24-live-isambane-utilisation.png` (also both Industry popup screenshots).
- Original Engine/Startup-Fatigue source diff check PASS; all calculation/source/tree/permission function AST comparisons PASS; task-scoped whitespace check PASS.

### Remaining problems / limits
- No outstanding missing methods, worker-cache dependency, tree expansion or stable-filter issue found in the completed actual LAB acceptance.
- Per the minimal test limit, the final live report dataset was Industry. Isambane popup presentation was checked live without a second source-data report; its unchanged tree and basis calculations retain the earlier focused source/preview verification.
- No broad regressions or additional live periods/basis datasets run. User manual review remains next.
- No intentionally partial product function remains.

### Exact next Bash commands — review only
```bash
cd /home/juan/juan-bench/apps/engineering
git status --short --branch
git log -1 --oneline
git diff -- 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).py' 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js' 'engineering/engineering/report/availability_and_utilisation_engine_(24)/README.md'
sudo -n /usr/bin/supervisorctl status | rg '^juan-bench-web:'
```
Open the actual LAB report for manual review:
`https://juan.isambane.co.za/app/query-report/Availability%20and%20Utilisation%20Engine%20(24)?from_date=2026-08-01&to_date=2026-08-07&sites=%5B%22Uitgevallen%22%5D&formula=Industry%20Formula`
No further restart is required for the current Python source. Do not commit, push,
merge or deploy until the user's review. Branch remains `juan`, HEAD `1012a01`.

Final service check: LAB web/Socket.IO RUNNING (PIDs 2436190/2436191);
production web/Socket.IO RUNNING with unchanged long uptime (PIDs
1208122/1208123, over 1 day 19 hours). Temporary acceptance session removed.
Final task-scoped whitespace check passed; working branch and unrelated dirty
files remain unchanged.

## Final formula and visual refinements — implementation checkpoint
- Branch `juan`, HEAD `1012a01`; previous/unrelated dirty work preserved.
- Industry now stores `use_of_availability_available = MAX(24 - raw BD - raw PM, MIN(Working Hours, 24))` per machine/day, includes it in summed hour fields, and divides summed work by the summed daily denominator for all subtotals, period and bottom totals. Net availability and fixed-24 utilisation remain separate and unchanged.
- Industry now has 12 columns, showing Net Availability hours, Use of Availability denominator and Utilisation denominator separately. Use of Availability % remains directly after Utilisation %. Isambane retains ten columns.
- Day/Night row backgrounds use original Engine colours (#eaf4ff/#f3f4f6), scoped to indent-3 shift rows only; green/purple/blue inner calculated highlights retained.
- Both available-hours popups shortened to the requested equations and simple variable keys; Industry utilisation popup distinctly shows MAX/MIN Use of Availability and fixed-24 Utilisation. Main View Formula help updated to the new calculation and daily aggregation.
- Existing over-100% test assertion updated to 25/24 with the new 24h MAX/MIN denominator, retaining anomaly flags and unrelated tests.

### Files modified this continuation
- Canonical AU24 `.py` and `.js`.
- Existing report `README.md`.
- Existing `tests/test_au24_engine.py` (targeted denominator expectation only).
- `AU24_CODEX_HANDOFF.md`.

### Checks completed
- Python/JavaScript syntax PASS.
- `/tmp/au24_final_formula_check.py` PASS: Industry day with BD=3, PM=1, WH=22 gives net=20, Use denominator=22, A=20/24, Use=100%, U=22/24. Adding a second day WH=1/no downtime produces weighted Use=23/46=50%, correctly different from 23/44 using net hours. Above-100% ratio and zero-denominator handling retained.
- Isambane example ReqH=12, WH=11, downtime=1: both available hours=11. 100% basis A=.91667, U=1; 85% basis A=.77917, U=.85. Hours unchanged.
- AST comparison PASS: all Isambane mapping/calculation path, tree builder, source readers, configuration and filtered endpoint functions unchanged. Industry=12 columns, Isambane=10.

### Pending
- Check running LAB controller version with a read-only non-report call.
- If still preloaded with the previous formula, stop before restarting and obtain explicit user approval as the latest request requires. Prior reload permission is not treated as approval for another restart.
- After approval if necessary: one actual LAB report, shift colours/popups/tree searches/weighted totals. Do not use a preview bridge to claim live acceptance.

### Running-worker check and approval request
- Read-only actual LAB call to existing `get_filtered_total` with BD=3, PM=1, WH=22 returned Use ratio=1.1 and no `use_of_availability_available`. The fresh source correctly returns ratio=1.0 and denominator=22. This proves the preloaded running worker still has the previous formula.
- No report query or restart was used for that check.
- Explicit approval requested through the user-input tool for:
  `sudo -n /usr/bin/supervisorctl restart juan-bench-web:`
- Reason: Gunicorn --preload holds the prior controller; loading the new denominator and 12-column schema requires replacing the LAB web processes. Only the previously confirmed LAB web/Socket.IO group is targeted. No production, workers, Redis or database restart.
- Latest attachment explicitly says to wait for approval before another restart; no new restart has been performed. Live report/colour/popup/filter verification remains pending that response.

Explicit user approval received: **Approve LAB-only reload and finish verification**.
Proceeding with only `sudo -n /usr/bin/supervisorctl restart juan-bench-web:`;
then one actual LAB report acceptance workflow, with no preview interception.

## Final formula/visual acceptance — authoritative current checkpoint
### Completed work
- Daily Industry Use of Availability denominator is `MAX(24 - raw BD - raw PM, MIN(WH, 24))`. All weighted parent, period and bottom results sum stored daily denominators and work; MAX/MIN is never reapplied to period totals.
- Availability remains Net Available Hours / 24, and Utilisation remains WH / 24. Raw downtime selection/clipping/overlap rules unchanged. Above-100% values are preserved/flagged and zero denominators remain neutral dashes.
- Twelve Industry columns in the exact requested order, including both utilisation available-hour values. Use of Availability % directly follows Utilisation %. Working Hours stays alongside raw inputs. Isambane has ten columns and unchanged original Engine calculations/basis handling.
- Day rows use #eaf4ff and Night rows #f3f4f6 across the entire shift row. Parents are unmarked; inner green/purple/blue highlights remain intact.
- Both available-hours dialogs are concise and formula-specific, with simple variable keys and correct distinction between Industry raw downtime and Isambane adjusted PBM downtime. Industry utilisation dialog shows Use MAX/MIN separately from fixed-24 Utilisation. View Formula explanation also matches the final denominator.
- Existing tree/filter implementation preserved; no flat-table rewrite, new report folder or helper controller.

### Approval and service action
- User explicitly approved: “Approve LAB-only reload and finish verification”.
- Executed only `sudo -n /usr/bin/supervisorctl restart juan-bench-web:`; command completed successfully for LAB web and LAB Socket.IO.
- No production, background-worker, Redis or database service restarted. No schema/configuration/business data populated or modified. No deployment, commit, push or merge.

### Focused checks and results
- Canonical Python/JS syntax and modified test syntax: PASS; task-scoped whitespace check: PASS.
- `/tmp/au24_final_formula_check.py`: PASS, Industry example and weighted daily-denominator counterexample; over-100% and zero handling; one Isambane example at each 100%/85% basis. Isambane hours remain 11 at both bases.
- AST comparison: original Isambane path/mapping, tree builder, source readers, configuration and filtered endpoints unchanged. Original Engine and Startup/Fatigue source diff check: PASS.
- `/tmp/au24_final_live_check.cjs`: complete actual LAB workflow PASS, exit 0, one actual report call in that successful workflow, zero page errors, no preview bridge/interception/fixtures.
- Real report: Industry / Uitgevallen / 1–7 August 2026; 616 tree rows / 189 atomic machine-days / 27 fleets. Every daily denominator and all category/date/machine/bottom weighted totals reconciled. Bottom work=1591h, Use denominator=4050.98h, Use ratio=0.3927444717080805.
- This real period has no machine-days where work exceeds net hours below 24, so the MAX/MIN floor produces the same denominator as net hours for these records. The synthetic worked example explicitly verifies the newly changed branch. An initial browser-check assumption that the real period must contain such a record was removed; it was a CHECK assumption, not a calculation defect. That preliminary attempt also read the same report; no extensive regression/browser suite was run.
- Verified all 12 cells of Day/Night rows have the correct background; parent unmarked; calculation highlights match green/purple/blue. All exact column fieldnames/order checked.
- Tree search IS56 selects 35 atomic machine-days; Availability >85 narrows to 26. Input node/focus/scroll stay stable; only prior ADT/date paths stay expanded. Filtered denominator and weighted ratio reconcile.
- Both short popups checked for Industry and Isambane without a second formula-data query; inspected actual screenshots `/tmp/au24-final-day-night.png`, `/tmp/au24-final-industry-utilisation.png`, `/tmp/au24-final-isambane-availability.png` (other popup/filtered images also saved).

### Exact files changed this continuation
1. `engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).py`
2. `engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js`
3. `engineering/engineering/report/availability_and_utilisation_engine_(24)/README.md`
4. `tests/test_au24_engine.py` — existing above-100% assertion updated for the new denominator; other pre-existing changes preserved. No full suite run.
5. `AU24_CODEX_HANDOFF.md`.

### Outstanding work
- No intentionally incomplete implementation or live worker dependency remains.
- User manual review is next. Broad regressions, extra periods and extra live Isambane datasets were deliberately not run.
- Current branch `juan`; HEAD remains `1012a0173036f23da3c7f94e5fe54e8609719842`.

### Exact Bash continuation commands — review only
```bash
cd /home/juan/juan-bench/apps/engineering
git status --short --branch
git log -1 --oneline
git diff -- 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).py' 'engineering/engineering/report/availability_and_utilisation_engine_(24)/availability_and_utilisation_engine_(24).js' 'engineering/engineering/report/availability_and_utilisation_engine_(24)/README.md' tests/test_au24_engine.py
```
Open actual LAB:
`https://juan.isambane.co.za/app/query-report/Availability%20and%20Utilisation%20Engine%20(24)?from_date=2026-08-01&to_date=2026-08-07&sites=%5B%22Uitgevallen%22%5D&formula=Industry%20Formula`
No further reload is needed for the current Python source. Do not commit, push,
merge, deploy or run more tests unless requested or subsequent edits require them.
