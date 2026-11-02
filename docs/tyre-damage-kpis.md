# Daily Engine tyre / wheel breakdown KPI

The activated LAB implementation counts unique, non-cancelled Plant Breakdown or Maintenance records with downtime type Breakdown and `failure_classification = Tyres / Wheels`. All classified tyre/wheel faults count, including rims, studs and bearings. There is no text-derived tyre estimate or damage-only subcategory requirement.

Both tabs use the existing permission-aware occurrence query and the same Engine roster, selected date/site, historical record category, ownership, production/spare and individual Asset restrictions. The drill-down calls that same controller and returns the same unique names. Its full-list link opens those original names. No duplicate ERP records are created.

Only the ADT tyre / wheel card renders. The shared machine `CATEGORIES` still includes ADT and Dozer for calculations and average rows; `TYRE_CARD_CATEGORIES` controls card visibility and the drill-down. Dozer retains its two availability/utilisation cards, hours cards, charts and rows. Shared HTML/export renderers cannot emit a Dozer tyre card.

See [migration and verification](failure-classification-migration.md). Activated on LAB on 2 November 2026. July 2026 ADT counts and drill-down totals are both zero at Klipfontein and Koppie because historical classifications remain blank.
