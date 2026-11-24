import re

import frappe
from frappe.model.document import Document

from engineering.controllers.kobelco_client import NUMERIC_FIELDS


class KobelcoResults(Document):
    def validate(self):
        if not self.flags.kobelco_import:
            frappe.throw("Kobelco Results are read-only. Use Sync Now to import telemetry.")

    def get_valid_dict(self, *args, **kwargs):
        values = super().get_valid_dict(*args, **kwargs)
        # Frappe normally coerces optional Float/Int values to 0 during DB writes
        # and serialization. Keep missing telemetry NULL in both DB and API JSON.
        for field in NUMERIC_FIELDS:
            if field in values and not self.get(field + "_available"):
                values[field] = None
        return values


def on_doctype_update():
    """Keep only Kobelco measurement columns nullable, including after migrations.

    Frappe creates numeric columns NOT NULL DEFAULT 0 regardless of `reqd`.
    Alter nullability/defaults without changing any stored measurement values.
    """
    if not frappe.db.table_exists("Kobelco Results"):
        return
    columns = {row.Field: row for row in frappe.db.sql("SHOW COLUMNS FROM `tabKobelco Results`", as_dict=True)}
    changes = []
    for field in NUMERIC_FIELDS:
        column = columns.get(field)
        if not column or (column.Null == "YES" and column.Default in (None, "NULL")):
            continue
        if not re.fullmatch(r"[a-z0-9(), ]+", column.Type):
            raise frappe.ValidationError("Unexpected Kobelco measurement column type.")
        changes.append(f"MODIFY COLUMN `{field}` {column.Type} NULL DEFAULT NULL")
    if changes:
        frappe.db.sql_ddl("ALTER TABLE `tabKobelco Results` " + ", ".join(changes))
