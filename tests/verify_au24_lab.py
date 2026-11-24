"""Read-only LAB verification for AU24 shift-level calculations."""

import importlib
import json
import os
from unittest.mock import patch

import frappe


def close(actual, expected, field):
    if actual is None or expected is None:
        assert actual is expected, (field, actual, expected)
    else:
        assert abs(float(actual) - float(expected)) < 1e-6, (
            field, actual, expected
        )


def verify_totals(rows):
    fields = (
        "total_hours",
        "breakdown_hours",
        "planned_maintenance_hours",
        "working_hours",
        "availability_available",
        "use_of_availability_available",
        "utilisation_available",
    )

    atoms = [
        row for row in rows
        if row.get("is_atomic") and not row.get("is_total_row")
    ]
    assert atoms, "No atomic shift records returned."

    bottom = rows[-1]
    assert bottom.get("is_total_row"), "Bottom total row missing."

    for field in fields:
        close(
            bottom[field],
            sum(float(row[field] or 0) for row in atoms),
            field,
        )

    close(
        bottom["availability_percent"],
        bottom["availability_available"] / bottom["total_hours"] if bottom["total_hours"] else None,
        "bottom availability percentage",
    )
    close(
        bottom["use_of_availability_percent"],
        bottom["working_hours"] / bottom["use_of_availability_available"] if bottom["use_of_availability_available"] else None,
        "bottom Use of Availability percentage",
    )
    close(
        bottom["utilisation_percent"],
        bottom["working_hours"] / bottom["utilisation_available"] if bottom["utilisation_available"] else None,
        "bottom utilisation percentage",
    )

    parent_checks = 0

    for index, parent in enumerate(rows[:-1]):
        indent = int(parent.get("indent") or 0)
        if indent not in (0, 1, 2):
            continue

        descendants = []
        for child in rows[index + 1:]:
            child_indent = int(child.get("indent") or 0)
            if child.get("is_total_row") or child_indent <= indent:
                break
            if child.get("is_atomic"):
                descendants.append(child)

        if not descendants:
            continue

        for field in fields:
            close(
                parent[field],
                sum(float(row[field] or 0) for row in descendants),
                f"parent {indent} {field}",
            )

        parent_checks += 1

    return atoms, parent_checks


def main():
    frappe.init(
        site="juan.isambane.co.za",
        sites_path="/home/juan/juan-bench/sites",
    )
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.db.rollback()
    frappe.db.sql("START TRANSACTION READ ONLY")

    try:
        report = importlib.import_module(
            "engineering.engineering.report.availability_and_utilisation_engine_(24).availability_and_utilisation_engine_(24)"
        )

        formula = os.environ.get("AU24_FORMULA", "Industry Formula")

        filters = dict(
            from_date="2026-08-01",
            to_date="2026-08-07",
            sites=["Uitgevallen"],
            formula=formula,
            asset_ownership="Isambane & Excavo Assets",
            isambane_basis="100% A & U",
            machine_scope=os.environ.get("AU24_MACHINE_SCOPE", "All Machines"),
        )

        # Suppress only the original Engine's Error Log write during
        # read-only verification. Calculation behaviour remains unchanged.
        with patch.object(frappe, "log_error") as legacy_logs:
            columns, rows, message, chart, summary, skip_total = report.execute(filters)


        assert chart is None and summary is None and skip_total

        if formula == "Industry Formula":
            assert len(columns) == 12, f"Expected 12 Industry columns, got {len(columns)}"

            atoms, parent_checks = verify_totals(rows)

            assert all(row["total_hours"] == 12 for row in atoms), (
                "Expected every Uitgevallen shift to have a 12-hour base."
            )

            shifts = {row["shift"] for row in atoms}
            assert shifts == {"Day", "Night"}, shifts

            unique_shifts = {
                (row["site"], row["fleet_number"], row["shift_date"], row["shift"])
                for row in atoms
            }
            assert len(unique_shifts) == len(atoms), "Duplicate shift records detected."

            result = {
                "formula": formula,
                "columns": len(columns),
                "shift_rows": len(atoms),
                "machines": len({
                    (row["site"], row["fleet_number"], row["shift_date"])
                    for row in atoms
                }),
                "shifts": sorted(shifts),
                "shift_base_hours": sorted({row["total_hours"] for row in atoms}),
                "parent_totals_verified": parent_checks,
                "fleet_total": rows[-1],
            }

        else:
            assert len(columns) == 10, f"Expected 10 Isambane columns, got {len(columns)}"
            assert rows[-1].get("is_total_row")
            result = {
                "formula": formula,
                "columns": len(columns),
                "rows": len(rows),
                "fleet_total": rows[-1],
            }

        result["message"] = message
        print(json.dumps(result, indent=2, default=str))

    finally:
        frappe.db.rollback()
        frappe.destroy()


if __name__ == "__main__":
    main()
