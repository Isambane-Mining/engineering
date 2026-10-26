# Optional problem categories

LAB report: https://juan.isambane.co.za/app/reliability-engineering

Plant Breakdown or Maintenance has an optional Select field `problem_category`, immediately after `breakdown_reason`. Its default is blank. It has no mandatory dependency, custom validation or client requirement. Existing integrations can omit it. Existing `failure_classification`, workflows, signature permissions and downtime calculations are unchanged.

The ten choices are Brakes, Steering, Engine / Starting, Hydraulics, Electrical, Cooling, Transmission / Drivetrain, Tyres / Wheels, Air Conditioning and Other. Leave it blank if unsure. No migration populates historical records.

Machine Reliability uses a matching manual category as a direct complaint, even without a keyword. Blank categories use the existing reason/resolution keyword matching. A different manual category prevents category keywords in its reason from redefining the complaint; resolution matches still show additional work. Extra keywords retain the existing OR search behavior and may find complaints in other categories. Each source record contributes once. Planned maintenance and resolution-only work never create confirmed failure intervals.

Other finds explicit manual choices or its configured terms; it is not an automatic remainder of all unclassified faults. Category names stay aligned with the dropdown; keywords and test mappings remain editable. The migration retains edited terms for surviving categories and merges retired/custom terms and test mappings into Other. Other permits longer merged lists so previously valid settings are not rejected; keywords remain limited to 100 characters each, and the nine named systems retain their 100-keyword limit.

## Files for this change

- `engineering/engineering/doctype/plant_breakdown_or_maintenance/plant_breakdown_or_maintenance.json`
- `engineering/engineering/doctype/plant_breakdown_or_maintenance/test_problem_category.py`
- `engineering/engineering/doctype/machine_reliability_settings/machine_reliability_settings.py` and `.json`
- `engineering/engineering/doctype/machine_reliability_category/machine_reliability_category.json`
- `engineering/engineering/page/machine_reliability/calculations.py`, `machine_reliability.py` and `test_problem_categories.py`
- `engineering/public/js/machine_reliability_dashboard.js`
- `engineering/patches/simplify_machine_reliability_categories.py`, `test_simplify_machine_reliability_categories.py` and `engineering/patches.txt`
- `tests/ui/problem_categories.cy.js`
- `docs/machine-reliability.md` and this document

Tests use transaction savepoints for document inserts, category changes and historical record saves; no test records are retained. They cover blank/omitted/cleared values, all ten options, live API classification, precedence, extra words, resolution-only work, maintenance exclusions, interval validation, settings migration and permissions.

## LAB verification

- 55 Python tests passed, including real document saves and live report queries in rolled-back transactions.
- 2 live Cypress browser tests passed: existing form metadata/optional control and dashboard category, steering, extra-word, timeline-detail and brake-result checks.
- LAB migration, category patch log, frontend build, JavaScript syntax and Git whitespace checks passed.
- Source audit confirmed all 10,727 historical breakdown records unchanged and every new category field blank after migration and test rollback.

## Optional tyre damage classification

Problem Subcategory is an optional blank-default Select, shown under Tyres / Wheels, with Tyre Damage as its one choice. The Daily A&U Engine tyre KPI requires this explicit category/subcategory pair on a Breakdown record. Neither classification is mandatory, and historical records are not backfilled. Machine Reliability continues using its existing main-category and historical keyword rules.
