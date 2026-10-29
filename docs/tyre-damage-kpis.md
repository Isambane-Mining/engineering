# Daily Engine tyre damage KPIs

LAB: https://juan.isambane.co.za/app/daily-availability-and-utilization-dashboard

Both dashboard tabs reuse the same compact grey Tyre Damages cards and occurrence query. The two larger performance cards, existing graphs, colours and calculations are unchanged. Cards say **Classified tyre damage breakdowns**, to distinguish explicit classification from historical text estimates.

## Classification

Plant Breakdown or Maintenance retains its optional, blank-default Problem Category. A new optional, blank-default **Problem Subcategory** Select offers **Tyre Damage**, shown when Problem Category is **Tyres / Wheels**. Neither field is mandatory, and existing records are never automatically classified. Clearing either field remains supported.

The KPI requires both values, plus `downtime_type = Breakdown` and a non-cancelled record. A subcategory left on a different parent category does not qualify. Count unique record names, never keyword occurrences or standing hours. There is no free-text matcher or historical estimate in this KPI. Routine maintenance is not inferred as damage from text. Operators must explicitly select Tyre Damage for damage events.

The existing Machine Reliability Settings remain the central source of the ten main categories and editable keywords. Its Tyres / Wheels category is reused; Machine Reliability's historical keyword fallback, additional searches and direct-complaint/repair distinction are unchanged. The single subcategory is a standard optional Select rather than a second category settings system.

## Existing scope and access

- Apply the dashboard's inclusive start/end dates to the breakdown start date, historical record site and historical asset category (Engine category fallback when missing).
- Restrict to machines/dates in the existing Engine roster, retaining its ownership and production/spare restrictions and individual Asset selection.
- Use Frappe `get_list` for record/User Permissions. Without breakdown read access, display unavailable (`—`). A limit of 20,000 qualifying records prevents silently truncated counts.
- Both tabs use the same counts. Hours per Asset shows one category total; choosing a machine restricts it to that machine, retaining existing chart behavior.

## LAB data

At investigation, all 10,727 existing LAB breakdown records had a blank Problem Category. July 1–31, 2026, combined production/spare and Isambane & Excavo ownership, therefore produces **ADT 0 / Dozer 0** for Klipfontein and Koppie. These are classified counts; older keyword estimates (11 and 4) are no longer used. No historical records are imported or backfilled.

## Validation

Transaction-only tests cover saving omitted/blank subcategory, explicit classification, clearing it, wrong parent category, planned maintenance exclusion and historical damage text without classification. Other tests cover unique counts, ADT/Dozer separation, permitted historical scope, selected Asset, live dashboard filters and both tabs. Existing graph and original KPI markup are compared unchanged. Browser checks cover both tabs, optional field visibility and responsive card sizes.

The LAB migration adds the optional schema field. Frontend assets are rebuilt. Unrelated pre-existing Short Haul graph test failures documented in the prior implementation are outside this classification change.

Final verification: **51 Python tests passed**, covering tyre classification/counting/rendering, ownership, optional document saves and Machine Reliability/category regressions. **5 Cypress tests passed** across tyre KPI and problem category specs. Desktop/tablet/mobile widths 1440, 1280, 768 and 375 pixels passed; desktop/mobile screenshots were inspected. LAB migration, frontend build, Python compilation, JavaScript syntax and Git whitespace checks passed. A before/after digest of the 10,727 source records matched, and all new subcategories remained blank after transaction-only tests.

Files updated for this simplification:

- Plant Breakdown or Maintenance JSON and its optional-category save tests.
- Machine Reliability Settings Python (shared category/subcategory constants).
- `tyre_damage.py` and `test_tyre_damage.py` (structured query, counts, labels and tests).
- `tests/ui/tyre_damage.cy.js` and `tests/ui/problem_categories.cy.js`.
- This document and `docs/problem-categories.md`.

Existing working dashboard integration, shared hours renderer and card CSS are reused without changes in this iteration. No production access, commit, push or merge.

## Controller review

Classification, permitted queries and unique counting now live in `engineering/controllers/tyre_damage.py`. The page's `tyre_damage.py` retains HTML rendering and re-exports the existing helper names for import compatibility. Dashboard HTTP endpoints, response shapes and permissions are unchanged.

The isolated dashboard tests now provide deterministic Engine rows, MPP shift hours, report date, permission results and classified breakdowns. They exercise the real aggregation and HTML rendering, including production/spare filtering and nonzero counts. This replaces missing live-site fixtures; production calculations are unchanged. All nine tyre tests pass offline. The broader review and its pre-existing test failures are recorded in `docs/eben-controller-review.md`; the earlier deployment results above are historical, not actions taken for this review.
