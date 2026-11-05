"""Backfill missing WearCheck machine identifiers into API Wearcheck Settings.

Runs once after model sync through patches.txt. Existing rows and mappings
are preserved; new rows have only JSON Value populated.
"""

import frappe

from engineering.controllers.importer import ensure_machine_mapping_rows


def execute():
    machines = frappe.db.sql(
        """
        SELECT DISTINCT machine
        FROM `tabWearCheck Results`
        WHERE machine IS NOT NULL AND TRIM(machine) != ''
        ORDER BY machine
        """,
        as_dict=True,
    )
    ensure_machine_mapping_rows(row.machine for row in machines)
