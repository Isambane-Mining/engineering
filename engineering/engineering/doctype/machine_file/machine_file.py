from datetime import date as _mf_period_date
import re as _mf_period_re

import frappe

from frappe.model.document import Document
from frappe.utils import (
    add_days,
    add_months,
    getdate,
    now_datetime,
)


INDEX_TEMPLATE = [
    {
        "index_no": "1",
        "description": "Machine Registration & Movement",
        "frequency": "",
        "source_candidates": ["Asset Movement"],
    },
    {
        "index_no": "2",
        "description": "Equipment Technical Information as per TMM COP16 & Vision Diagram",
        "frequency": "",
        "source_candidates": [],
    },
    {
        "index_no": "3",
        "description": "FRC Checklist",
        "frequency": "Quarterly",
        "source_candidates": [],
    },
    {
        "index_no": "4",
        "description": "Noise Level Baseline and Periodical Measurement Report (VOHE)",
        "frequency": "Periodical",
        "source_candidates": [],
    },
    {
        "index_no": "5",
        "description": "Illumination Baseline and Periodical Measurements Report (VOHE)",
        "frequency": "Periodical",
        "source_candidates": [],
    },
    {
        "index_no": "6",
        "description": "PDS Installation COC",
        "frequency": "",
        "source_candidates": [],
    },
    {
        "index_no": "7",
        "description": "PDS Inspection Report",
        "frequency": "Inspection",
        "source_candidates": [],
    },
    {
        "index_no": "8",
        "description": "Fire Suppression Issues Base Risk Assessment (IBRA) and Installation Certificate",
        "frequency": "",
        "source_candidates": [],
    },
    {
        "index_no": "9",
        "description": "Brake Test Report",
        "frequency": "250 Hours / After Brake Work",
        "source_candidates": [],
    },
    {
        "index_no": "10",
        "description": "C Track Inspection Report",
        "frequency": "",
        "source_candidates": [],
    },
    {
        "index_no": "11",
        "description": "Breakdown Log Sheet",
        "frequency": "Continuous",
        "source_candidates": [
            "Plant Breakdown or Maintenance",
        ],
    },
    {
        "index_no": "12",
        "description": "Service Record / Job Card",
        "frequency": "Every Service",
        "source_candidates": [
            "Job Card",
        ],
    },
    {
        "index_no": "12.1",
        "description": "Brake Wear Measurements",
        "frequency": "Every Service",
        "source_candidates": [],
    },
    {
        "index_no": "13",
        "description": "Tyre Inspection Report and Survey",
        "frequency": "Inspection",
        "source_candidates": [],
    },
    {
        "index_no": "14",
        "description": "Machine Support Post or Locking Pin",
        "frequency": "6 Months NDT",
        "source_candidates": [],
    },
    {
        "index_no": "15",
        "description": "Pre-use Checklist",
        "frequency": "Refer to Pre-use File",
        "source_candidates": [
            "Pre Use Inspection",
            "Pre Use Checklist",
            "Pre-Use Inspection",
            "Pre Use",
        ],
    },
    {
        "index_no": "16",
        "description": "Maintenance Inspection",
        "frequency": "Inspection",
        "source_candidates": [],
    },
    {
        "index_no": "17",
        "description": "PR's",
        "frequency": "",
        "source_candidates": [
            "Purchase Requisition",
        ],
    },
    {
        "index_no": "18",
        "description": "Wear Check Job Cards",
        "frequency": "",
        "source_candidates": [],
    },
    {
        "index_no": "19",
        "description": "Component Replacement Reports & Warranty",
        "frequency": "",
        "source_candidates": [],
    },
    {
        "index_no": "20",
        "description": "Aircon & Heater Repairs",
        "frequency": "",
        "source_candidates": [],
    },
]


class MachineFile(Document):

    def validate(self):
        self.set_asset_details()
        self.ensure_index()

    def set_asset_details(self):
        if not self.machine:
            return

        asset = frappe.db.get_value(
            "Asset",
            self.machine,
            [
                "asset_name",
                "asset_category",
                "location",
                "item_code",
            ],
            as_dict=True,
        )

        if not asset:
            return

        self.machine_name = asset.asset_name
        self.machine_category = asset.asset_category
        self.site = asset.location
        self.item_code = asset.item_code
        self.serial_no = ""

    def ensure_index(self):
        existing = {
            str(row.index_no): row
            for row in (self.index_items or [])
            if row.index_no
        }

        ordered_rows = []

        for item in INDEX_TEMPLATE:
            row = existing.get(item["index_no"])

            if not row:
                row = self.append("index_items", {})

            row.index_no = item["index_no"]
            row.description = item["description"]
            row.frequency = item["frequency"]

            ordered_rows.append(row)

        # Remove anything not part of the official index.
        allowed = {
            item["index_no"]
            for item in INDEX_TEMPLATE
        }

        for row in list(self.index_items or []):
            if str(row.index_no) not in allowed:
                self.remove(row)


def _doctype_exists(doctype):
    return bool(frappe.db.exists("DocType", doctype))


def _find_asset_field(doctype):
    if not _doctype_exists(doctype):
        return None

    meta = frappe.get_meta(doctype)

    fieldnames = {
        df.fieldname
        for df in meta.fields
    }

    preferred = [
        "asset",
        "asset_name",
        "fleet_number",
        "machine",
        "machine_number",
        "equipment",
        "asset_number",
    ]

    for fieldname in preferred:
        if fieldname in fieldnames:
            return fieldname

    for df in meta.fields:
        if (
            df.fieldtype == "Link"
            and df.options == "Asset"
        ):
            return df.fieldname

    return None


def _find_date_field(doctype):
    meta = frappe.get_meta(doctype)

    fieldnames = {
        df.fieldname
        for df in meta.fields
    }

    preferred = [
        "posting_date",
        "date",
        "report_date",
        "inspection_date",
        "service_date",
        "transaction_date",
        "report_datetime",
        "breakdown_start_datetime",
        "creation",
        "modified",
    ]

    for fieldname in preferred:
        if (
            fieldname in fieldnames
            or fieldname in ("creation", "modified")
        ):
            return fieldname

    return "modified"


def _machine_records(
    doctype,
    machine,
    asset_field=None,
):
    if not doctype or not _doctype_exists(doctype):
        return 0, None

    asset_field = (
        asset_field
        or _find_asset_field(doctype)
    )

    if not asset_field:
        return 0, None

    filters = {
        asset_field: machine
    }

    count = frappe.db.count(
        doctype,
        filters=filters,
    )

    if not count:
        return 0, None

    date_field = _find_date_field(doctype)

    rows = frappe.get_all(
        doctype,
        filters=filters,
        fields=[date_field],
        order_by=f"{date_field} desc",
        limit=1,
    )

    last_date = None

    if rows:
        value = rows[0].get(date_field)

        if value:
            last_date = getdate(value)

    return count, last_date


def _find_source(item, machine):
    first_compatible = None

    for doctype in item.get(
        "source_candidates",
        [],
    ):
        # ASSET MOVEMENT SPECIAL COUNT
        if doctype == "Asset Movement":
            count, last_date = _asset_movement_records(
                machine
            )

            return (
                "Asset Movement",
                "",
                count,
                last_date,
            )

        if not _doctype_exists(doctype):
            continue

        asset_field = _find_asset_field(
            doctype
        )

        if not asset_field:
            continue

        if first_compatible is None:
            first_compatible = (
                doctype,
                asset_field,
            )

        count, last_date = _machine_records(
            doctype,
            machine,
            asset_field,
        )

        if count:
            return (
                doctype,
                asset_field,
                count,
                last_date,
            )

    if first_compatible:
        return (
            first_compatible[0],
            first_compatible[1],
            0,
            None,
        )

    return "", "", 0, None


def _manual_documents(
    doc,
    index_no,
):
    rows = [
        row
        for row in (doc.documents or [])
        if str(
            row.index_no or ""
        ).strip() == str(index_no)
    ]

    if not rows:
        return 0, None, None

    def row_date(row):
        if row.document_date:
            return getdate(
                row.document_date
            )

        return getdate(
            "1900-01-01"
        )

    rows = sorted(
        rows,
        key=row_date,
        reverse=True,
    )

    latest = rows[0]

    document_date = (
        getdate(latest.document_date)
        if latest.document_date
        else None
    )

    expiry_date = (
        getdate(latest.expiry_date)
        if latest.expiry_date
        else None
    )

    return (
        len(rows),
        document_date,
        expiry_date,
    )


def _calculate_next_due(
    template,
    last_date,
    explicit_expiry,
):
    if explicit_expiry:
        return explicit_expiry

    if not last_date:
        return None

    frequency = (
        template.get(
            "frequency",
            "",
        )
        or ""
    ).lower()

    if "quarter" in frequency:
        return add_months(
            last_date,
            3,
        )

    if "6 month" in frequency:
        return add_months(
            last_date,
            6,
        )

    return None


def _status_for_row(
    source_count,
    manual_count,
    next_due,
):
    today = getdate()

    if next_due:
        if next_due < today:
            return "Overdue"

        if next_due <= add_days(
            today,
            30,
        ):
            return "Due Soon"

        return "Current"

    if source_count:
        return "ERP Records"

    if manual_count:
        return "Current"

    return "Missing"


def _refresh_doc(doc):
    doc.set_asset_details()
    doc.ensure_index()

    template_map = {
        item["index_no"]: item
        for item in INDEX_TEMPLATE
    }

    for row in doc.index_items:
        template = template_map.get(
            str(row.index_no)
        )

        if not template:
            continue

        (
            source_doctype,
            source_asset_field,
            source_count,
            source_date,
        ) = _find_source(
            template,
            doc.machine,
        )

        (
            manual_count,
            manual_date,
            explicit_expiry,
        ) = _manual_documents(
            doc,
            row.index_no,
        )

        row.source_doctype = (
            source_doctype
        )

        row.source_asset_field = (
            source_asset_field
        )

        row.record_count = (
            source_count
            + manual_count
        )

        dates = [
            value
            for value in [
                source_date,
                manual_date,
            ]
            if value
        ]

        last_date = (
            max(dates)
            if dates
            else None
        )

        row.last_record_date = (
            last_date
        )

        next_due = _calculate_next_due(
            template,
            last_date,
            explicit_expiry,
        )

        row.next_due_date = (
            next_due
        )

        row.status = _status_for_row(
            source_count,
            manual_count,
            next_due,
        )

    doc.last_refreshed = now_datetime()




# MACHINE FILE MOVEMENT DETAIL START

def _machine_file_asset_movement_config():
    if not frappe.db.exists(
        "DocType",
        "Asset Movement"
    ):
        return None

    if not frappe.db.exists(
        "DocType",
        "Asset Movement Item"
    ):
        return None

    parent_meta = frappe.get_meta(
        "Asset Movement"
    )

    child_meta = frappe.get_meta(
        "Asset Movement Item"
    )

    # Find the child table field on Asset Movement.
    child_table_field = None

    for df in parent_meta.fields:
        if (
            df.fieldtype == "Table"
            and df.options == "Asset Movement Item"
        ):
            child_table_field = df.fieldname
            break

    # Find the Asset field on Asset Movement Item.
    asset_field = None

    preferred_asset_fields = [
        "asset",
        "asset_name",
        "machine",
        "fleet_number",
    ]

    child_fieldnames = {
        df.fieldname
        for df in child_meta.fields
    }

    for fieldname in preferred_asset_fields:
        if fieldname in child_fieldnames:
            asset_field = fieldname
            break

    if not asset_field:
        for df in child_meta.fields:
            if (
                df.fieldtype == "Link"
                and df.options == "Asset"
            ):
                asset_field = df.fieldname
                break

    def first_existing(candidates):
        for fieldname in candidates:
            if fieldname in child_fieldnames:
                return fieldname

        return None

    source_location_field = first_existing([
        "source_location",
        "from_location",
        "current_location",
    ])

    target_location_field = first_existing([
        "target_location",
        "to_location",
        "new_location",
    ])

    from_employee_field = first_existing([
        "from_employee",
        "source_employee",
    ])

    to_employee_field = first_existing([
        "to_employee",
        "target_employee",
    ])

    return {
        "child_table_field": child_table_field,
        "asset_field": asset_field,
        "source_location_field": source_location_field,
        "target_location_field": target_location_field,
        "from_employee_field": from_employee_field,
        "to_employee_field": to_employee_field,
    }


def _asset_movement_records(machine):
    config = _machine_file_asset_movement_config()

    if not config:
        return 0, None

    asset_field = config.get(
        "asset_field"
    )

    if not asset_field:
        return 0, None

    child_rows = frappe.get_all(
        "Asset Movement Item",
        filters={
            asset_field: machine,
        },
        fields=[
            "parent",
        ],
        limit_page_length=5000,
    )

    parent_names = list({
        row.parent
        for row in child_rows
        if row.parent
    })

    if not parent_names:
        return 0, None

    parent_meta = frappe.get_meta(
        "Asset Movement"
    )

    parent_fieldnames = {
        df.fieldname
        for df in parent_meta.fields
    }

    date_field = None

    for candidate in [
        "transaction_date",
        "posting_date",
        "movement_date",
        "date",
    ]:
        if candidate in parent_fieldnames:
            date_field = candidate
            break

    fields = [
        "name",
        "docstatus",
        "creation",
    ]

    if date_field:
        fields.append(date_field)

    parents = frappe.get_all(
        "Asset Movement",
        filters={
            "name": ["in", parent_names],
            "docstatus": ["<", 2],
        },
        fields=fields,
        limit_page_length=5000,
    )

    if not parents:
        return 0, None

    dates = []

    for row in parents:
        value = (
            row.get(date_field)
            if date_field
            else row.creation
        )

        if value:
            dates.append(
                getdate(value)
            )

    last_date = (
        max(dates)
        if dates
        else None
    )

    return len(parents), last_date


@frappe.whitelist()
def get_machine_registration_movement(name):
    doc = frappe.get_doc(
        "Machine File",
        name
    )

    doc.check_permission("read")

    machine = doc.machine

    config = _machine_file_asset_movement_config()

    if not config:
        return {
            "machine": machine,
            "rows": [],
            "can_create": False,
            "error": (
                "Asset Movement configuration "
                "could not be found."
            ),
        }

    asset_field = config.get(
        "asset_field"
    )

    child_table_field = config.get(
        "child_table_field"
    )

    if not asset_field:
        return {
            "machine": machine,
            "rows": [],
            "can_create": False,
            "error": (
                "Asset field could not be found "
                "on Asset Movement Item."
            ),
        }

    child_meta = frappe.get_meta(
        "Asset Movement Item"
    )

    child_fieldnames = {
        df.fieldname
        for df in child_meta.fields
    }

    child_fields = [
        "parent",
        "idx",
    ]

    for fieldname in [
        asset_field,
        config.get(
            "source_location_field"
        ),
        config.get(
            "target_location_field"
        ),
        config.get(
            "from_employee_field"
        ),
        config.get(
            "to_employee_field"
        ),
    ]:
        if (
            fieldname
            and fieldname in child_fieldnames
            and fieldname not in child_fields
        ):
            child_fields.append(
                fieldname
            )

    child_rows = frappe.get_all(
        "Asset Movement Item",
        filters={
            asset_field: machine,
        },
        fields=child_fields,
        order_by="parent desc, idx asc",
        limit_page_length=5000,
    )

    parent_names = list({
        row.parent
        for row in child_rows
        if row.parent
    })

    if not parent_names:
        return {
            "machine": machine,
            "rows": [],
            "can_create": frappe.has_permission(
                "Asset Movement",
                "create"
            ),
            "child_table_field": child_table_field,
            "asset_field": asset_field,
        }

    parent_meta = frappe.get_meta(
        "Asset Movement"
    )

    parent_fieldnames = {
        df.fieldname
        for df in parent_meta.fields
    }

    parent_fields = [
        "name",
        "docstatus",
        "creation",
        "modified",
    ]

    optional_parent_fields = [
        "transaction_date",
        "posting_date",
        "movement_date",
        "date",
        "purpose",
        "company",
        "reference_doctype",
        "reference_name",
        "remarks",
    ]

    for fieldname in optional_parent_fields:
        if (
            fieldname in parent_fieldnames
            and fieldname not in parent_fields
        ):
            parent_fields.append(
                fieldname
            )

    parent_rows = _mf_readable_records(
        "Asset Movement",
        filters={
            "name": ["in", parent_names],
        },
        fields=parent_fields,
        limit_page_length=5000,
    )

    parent_map = {
        row.name: row
        for row in parent_rows
    }

    files = _mf_readable_records(
        "File",
        filters={
            "attached_to_doctype": "Asset Movement",
            "attached_to_name": [
                "in",
                parent_names,
            ],
            "is_folder": 0,
        },
        fields=[
            "name",
            "file_name",
            "file_url",
            "attached_to_name",
            "is_private",
        ],
        order_by="creation asc",
        limit_page_length=5000,
    )

    file_map = {}

    for file_row in files:
        file_map.setdefault(
            file_row.attached_to_name,
            []
        ).append({
            "name": file_row.name,
            "file_name": (
                file_row.file_name
                or file_row.name
            ),
            "file_url": file_row.file_url,
        })

    result = []

    status_map = {
        0: "Draft",
        1: "Submitted",
        2: "Cancelled",
    }

    source_field = config.get(
        "source_location_field"
    )

    target_field = config.get(
        "target_location_field"
    )

    from_employee_field = config.get(
        "from_employee_field"
    )

    to_employee_field = config.get(
        "to_employee_field"
    )

    for child in child_rows:
        parent = parent_map.get(
            child.parent
        )

        if not parent:
            continue

        movement_date = None

        for fieldname in [
            "transaction_date",
            "posting_date",
            "movement_date",
            "date",
            "creation",
        ]:
            value = parent.get(
                fieldname
            )

            if value:
                movement_date = str(
                    value
                )
                break

        result.append({
            "name": parent.name,
            "date": movement_date,
            "purpose": (
                parent.get("purpose")
                or ""
            ),
            "from_location": (
                child.get(source_field)
                if source_field
                else ""
            ),
            "to_location": (
                child.get(target_field)
                if target_field
                else ""
            ),
            "from_employee": (
                child.get(from_employee_field)
                if from_employee_field
                else ""
            ),
            "to_employee": (
                child.get(to_employee_field)
                if to_employee_field
                else ""
            ),
            "status": status_map.get(
                parent.docstatus,
                "Unknown"
            ),
            "docstatus": parent.docstatus,
            "remarks": (
                parent.get("remarks")
                or ""
            ),
            "attachments": file_map.get(
                parent.name,
                []
            ),
        })

    result.sort(
        key=lambda row: (
            row.get("date") or ""
        ),
        reverse=True,
    )

    return {
        "machine": machine,
        "rows": result,
        "can_create": frappe.has_permission(
            "Asset Movement",
            "create"
        ),
        "child_table_field": child_table_field,
        "asset_field": asset_field,
    }

# MACHINE FILE MOVEMENT DETAIL END




@frappe.whitelist()
def get_machine_file_dashboard(name):
    doc = frappe.get_doc(
        "Machine File",
        name,
    )

    doc.check_permission("read")

    rows = []

    for row in doc.index_items:
        rows.append({
            "index_no": row.index_no,
            "description": row.description,
            "frequency": row.frequency,
            "source_doctype": (
                row.source_doctype
            ),
            "source_asset_field": (
                row.source_asset_field
            ),
            "status": (
                row.status
                or "Missing"
            ),
            "record_count": (
                row.record_count
                or 0
            ),
            "last_record_date": (
                row.last_record_date
            ),
            "next_due_date": (
                row.next_due_date
            ),
        })

    return {
        "name": doc.name,
        "machine": doc.machine,
        "machine_name": (
            doc.machine_name
        ),
        "site": doc.site,
        "machine_category": (
            doc.machine_category
        ),
        "last_refreshed": (
            doc.last_refreshed
        ),
        "rows": rows,
    }


# MACHINE FILE ASSET REGISTER SYNC
def _sync_machine_files_from_assets():
    """
    Ensure every submitted Asset has one Machine File.

    Existing Machine Files are left in place.
    New Machine Files are created only when missing.
    """

    assets = frappe.get_all(
        "Asset",
        filters={
            "docstatus": 1,
            "asset_category": ["not in", ["Cellular Telephone", "Lifting Equipment"]],
        },
        fields=[
            "name",
            "asset_name",
            "asset_category",
            "location",
        ],
        order_by="asset_category asc, name asc",
    )

    created = 0
    existing = 0
    failed = []

    for asset in assets:
        existing_name = frappe.db.exists(
            "Machine File",
            {
                "machine": asset.name,
            },
        )

        if existing_name:
            existing += 1
            continue

        try:
            doc = frappe.new_doc(
                "Machine File"
            )

            doc.machine = asset.name

            # validate() on Machine File automatically
            # fetches Site, Category and machine details
            # and builds the complete index.
            doc.insert(
                ignore_permissions=True
            )

            created += 1

        except Exception as exc:
            failed.append({
                "machine": asset.name,
                "error": str(exc),
            })

            frappe.log_error(
                title=(
                    "Machine File Sync Failed "
                    f"- {asset.name}"
                ),
                message=frappe.get_traceback(),
            )

    frappe.db.commit()

    return {
        "total_assets": len(assets),
        "created": created,
        "existing": existing,
        "failed_count": len(failed),
        "failed": failed[:20],
    }


@frappe.whitelist()
def sync_machine_files():
    """
    Desk button used to add newly-created Assets
    to the Machine File register.
    """

    roles = frappe.get_roles(
        frappe.session.user
    )

    if "System Manager" not in roles:
        frappe.throw(
            "Only a System Manager can sync the Machine File register."
        )

    return _sync_machine_files_from_assets()



# MACHINE FILE GROUPED REGISTER START
@frappe.whitelist()
def get_machine_file_register(site=None, machine_category=None, machine=None):
    """
    Machine File grouped register.

    IMPORTANT:
    Only Assets with docstatus = 1 (Submitted)
    are displayed.
    """

    if not frappe.has_permission("Machine File", "read"):
        frappe.throw(
            "You do not have permission to read Machine File."
        )

    asset_filters = {
        "docstatus": 1,
        "asset_category": ["not in", ["Cellular Telephone", "Lifting Equipment"]],
    }

    if site:
        asset_filters["location"] = site

    if machine_category:
        asset_filters["asset_category"] = machine_category

    if machine:
        asset_filters["name"] = machine

    submitted_assets = _mf_readable_records(
        "Asset",
        filters=asset_filters,
        fields=[
            "name",
            "asset_name",
            "item_code",
            "location",
            "asset_category",
        ],
        order_by="asset_category asc, name asc",
        limit_page_length=5000,
    )

    if not submitted_assets:
        return []

    asset_map = {
        row.name: row
        for row in submitted_assets
    }

    machine_names = list(asset_map.keys())

    machine_files = _mf_readable_records(
        "Machine File",
        filters={
            "machine": ["in", machine_names],
        },
        fields=[
            "name",
            "machine",
        ],
        limit_page_length=5000,
    )

    file_map = {
        row.machine: row.name
        for row in machine_files
    }

    rows = []

    for asset in submitted_assets:
        machine_file_name = file_map.get(
            asset.name
        )

        # Only show machines that have a Machine File.
        if not machine_file_name:
            continue

        rows.append({
            "name": machine_file_name,
            "machine": asset.name,
            "machine_name": asset.asset_name,
            "item_code": asset.item_code,
            "site": asset.location,
            "machine_category": asset.asset_category,
        })

    return rows
# MACHINE FILE GROUPED REGISTER END



# MACHINE FILE GENERIC SECTION DETAIL START

def _machine_file_attached_files(doctype, names):
    if not names:
        return {}

    rows = _mf_readable_records(
        "File",
        filters={
            "attached_to_doctype": doctype,
            "attached_to_name": ["in", names],
            "is_folder": 0,
        },
        fields=[
            "name",
            "file_name",
            "file_url",
            "attached_to_name",
        ],
        order_by="creation asc",
        limit_page_length=5000,
    )

    result = {}

    for row in rows:
        result.setdefault(
            row.attached_to_name,
            []
        ).append({
            "name": row.name,
            "file_name": (
                row.file_name
                or row.name
            ),
            "file_url": row.file_url,
        })

    return result


def _machine_file_source_records(
    doctype,
    asset_field,
    machine,
):
    if (
        not doctype
        or not asset_field
        or not frappe.db.exists(
            "DocType",
            doctype
        )
    ):
        return []

    meta = frappe.get_meta(
        doctype
    )

    fieldnames = {
        df.fieldname
        for df in meta.fields
    }

    date_field = _find_date_field(
        doctype
    )

    fields = [
        "name",
        "creation",
        "modified",
    ]

    if date_field not in fields:
        fields.append(
            date_field
        )

    if "docstatus" not in fields:
        fields.append(
            "docstatus"
        )

    optional_fields = [
        "status",
        "workflow_state",
        "purpose",
        "remarks",
        "description",
    ]

    for fieldname in optional_fields:
        if (
            fieldname in fieldnames
            and fieldname not in fields
        ):
            fields.append(
                fieldname
            )

    rows = _mf_readable_records(
        doctype,
        filters={
            asset_field: machine,
        },
        fields=fields,
        order_by=f"{date_field} desc",
        limit_page_length=5000,
    )

    names = [
        row.name
        for row in rows
    ]

    attachments = (
        _machine_file_attached_files(
            doctype,
            names,
        )
    )

    status_map = {
        0: "Draft",
        1: "Submitted",
        2: "Cancelled",
    }

    result = []

    for row in rows:
        record_date = (
            row.get(date_field)
            or row.creation
        )

        display_status = (
            row.get("status")
            or row.get("workflow_state")
            or status_map.get(
                row.docstatus,
                ""
            )
        )

        result.append({
            "name": row.name,
            "date": (
                str(record_date)
                if record_date
                else ""
            ),
            "status": display_status,
            "purpose": (
                row.get("purpose")
                or ""
            ),
            "remarks": (
                row.get("remarks")
                or row.get("description")
                or ""
            ),
            "attachments": (
                attachments.get(
                    row.name,
                    []
                )
            ),
        })

    return result


@frappe.whitelist()
def get_machine_file_section_details(
    name,
    index_no,
):
    doc = frappe.get_doc(
        "Machine File",
        name
    )

    doc.check_permission(
        "read"
    )

    index_no = str(
        index_no or ""
    ).strip()

    index_row = None

    for row in doc.index_items or []:
        if str(
            row.index_no or ""
        ).strip() == index_no:
            index_row = row
            break

    if not index_row:
        frappe.throw(
            f"Machine File section {index_no} was not found."
        )

    template = None

    for item in INDEX_TEMPLATE:
        if str(
            item.get("index_no")
        ) == index_no:
            template = item
            break

    # -----------------------------------------------------
    # Documents uploaded directly into Machine File
    # -----------------------------------------------------
    manual_documents = []

    for row in doc.documents or []:
        if str(
            row.index_no or ""
        ).strip() != index_no:
            continue

        manual_documents.append({
            "row_name": row.name,
            "document_type": (
                row.document_type
                or index_row.description
            ),
            "document_date": (
                str(row.document_date)
                if row.document_date
                else ""
            ),
            "expiry_date": (
                str(row.expiry_date)
                if row.expiry_date
                else ""
            ),
            "attachment": (
                row.attachment
                or ""
            ),
            "notes": (
                row.notes
                or ""
            ),
        })

    # -----------------------------------------------------
    # Section 1 has special Asset Movement logic
    # -----------------------------------------------------
    movement = None

    if index_no == "1":
        movement = (
            get_machine_registration_movement(
                name
            )
        )

    # -----------------------------------------------------
    # Resolve ERP source for all other sections
    # -----------------------------------------------------
    source_doctype = (
        index_row.source_doctype
        or ""
    )

    source_asset_field = (
        index_row.source_asset_field
        or ""
    )

    if (
        index_no != "1"
        and template
        and (
            not source_doctype
            or not source_asset_field
        )
    ):
        (
            resolved_doctype,
            resolved_asset_field,
            _count,
            _last_date,
        ) = _find_source(
            template,
            doc.machine,
        )

        source_doctype = (
            source_doctype
            or resolved_doctype
            or ""
        )

        source_asset_field = (
            source_asset_field
            or resolved_asset_field
            or ""
        )

    source_records = []

    if (
        index_no != "1"
        and source_doctype
        and source_asset_field
    ):
        source_records = (
            _machine_file_source_records(
                source_doctype,
                source_asset_field,
                doc.machine,
            )
        )

    can_add_document = (
        doc.has_permission(
            "write"
        )
    )

    can_create_source = False

    if (
        source_doctype
        and frappe.db.exists(
            "DocType",
            source_doctype
        )
    ):
        can_create_source = (
            frappe.has_permission(
                source_doctype,
                "create"
            )
        )

    return {
        "index_no": index_no,
        "description": (
            index_row.description
            or ""
        ),
        "frequency": (
            index_row.frequency
            or ""
        ),
        "machine": doc.machine,
        "machine_name": (
            doc.machine_name
            or ""
        ),
        "site": (
            doc.site
            or ""
        ),
        "source_doctype": (
            source_doctype
        ),
        "source_asset_field": (
            source_asset_field
        ),
        "source_records": (
            source_records
        ),
        "manual_documents": (
            manual_documents
        ),
        "movement": movement,
        "can_add_document": (
            can_add_document
        ),
        "can_create_source": (
            can_create_source
        ),
    }

# MACHINE FILE GENERIC SECTION DETAIL END



# MACHINE FILE ENGINEERING LEGALS LINK START

import os
import re


ENGINEERING_LEGALS_MACHINE_FILE_MAP = {
    # 2. Equipment Technical Information
    "2": [
        "Equipment List",
        "Equipment Technical Information",
    ],

    # 3. FRC Checklist
    "3": [
        "FRCS",
        "FRCS Compliance",
        "FRC",
        "FRC Compliance",
        "FRC Checklist",
    ],

    # 4. Noise Level / VOHE
    "4": [
        "Noise Level Baseline & Measurement",
        "Noise Level Baseline and Measurement",
        "Noise Level Baseline",
        "Noise Level Measurement",
    ],

    # 7. PDS Inspection
    "7": [
        "PDS-MPI Maintenance",
        "PDS MPI Maintenance",
        "PDS Inspection",
        "PDS Inspection Report",
    ],

    # 8. Fire Suppression
    "8": [
        "Automatic Fire Suppression",
        "Fire Suppression",
        "Fire Suppression Inspection",
    ],

    # 9. Brake Test Report
    "9": [
        "Brake Test",
        "Brake Test Report",
        "Dynamic Brake Testing",
        "Dynamic Brake Test",
    ],

    # 12. Service Record / Job Card
    "12": [
        "Machine Service Records",
        "Machine Service Record",
        "Service Records",
        "Service Record",
        "Service Record / Job Card",
    ],

    # 13. Tyre Inspection Report and Survey
    "13": [
        "Tyre Inspection Report",
        "Tyre Inspection",
        "Tyre Survey",
        "Tyre Inspection Report and Survey",
    ],

    # 16. Maintenance Inspection
    "16": [
        "Condition Monitoring",
        "Maintenance Schedules",
        "Maintenance Schedule",
        "Maintenance Inspection",
    ],

    # 21. Pressure Vessel
    "21": [
        "Pressure Vessels",
        "Pressure Vessel",
    ],
}


def _mf_legal_normalise(value):
    value = str(
        value or ""
    ).strip()

    # Strip report numbering such as:
    # 01. Automatic Fire Suppression
    value = re.sub(
        r"^\s*\d+\s*[\.\-\)]\s*",
        "",
        value,
    )

    value = value.replace(
        "–",
        "-"
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.casefold().strip()


def _mf_find_field(
    meta,
    candidates,
    labels=None,
):
    labels = labels or []

    field_map = {
        df.fieldname: df
        for df in meta.fields
    }

    for fieldname in candidates:
        if fieldname in field_map:
            return fieldname

    wanted_labels = {
        _mf_legal_normalise(
            label
        )
        for label in labels
    }

    if wanted_labels:
        for df in meta.fields:
            if (
                _mf_legal_normalise(
                    df.label
                )
                in wanted_labels
            ):
                return df.fieldname

    return None


def _mf_engineering_legals_config():
    if not frappe.db.exists(
        "DocType",
        "Engineering Legals"
    ):
        return None

    meta = frappe.get_meta(
        "Engineering Legals"
    )

    return {
        "section_field": _mf_find_field(
            meta,
            [
                "sections",
                "section",
                "legal_section",
                "legal_category",
            ],
            [
                "Sections",
                "Section",
                "Legal Category",
            ],
        ),

        "site_field": _mf_find_field(
            meta,
            [
                "site",
                "location",
            ],
            [
                "Site",
                "Location",
            ],
        ),

        "fleet_field": _mf_find_field(
            meta,
            [
                "fleet_number",
                "element_number",
                "asset",
                "machine",
                "plant_number",
                "equipment",
            ],
            [
                "Fleet Number",
                "Element Number",
                "Plant Number",
                "Asset",
                "Machine",
            ],
        ),

        "attachment_field": _mf_find_field(
            meta,
            [
                "attach_paper",
                "attachment",
                "attach_document",
                "document",
            ],
            [
                "Attach Paper",
                "Attachment",
                "Document",
            ],
        ),

        "start_date_field": _mf_find_field(
            meta,
            [
                "document_start_date",
                "start_date",
                "document_date",
                "inspection_date",
            ],
            [
                "Document Start Date",
                "Start Date",
                "Document Date",
            ],
        ),

        "expiry_date_field": _mf_find_field(
            meta,
            [
                "expiry_date",
                "expiration_date",
                "valid_until",
                "next_due_date",
            ],
            [
                "Expiry Date",
                "Expiration Date",
                "Valid Until",
                "Next Due Date",
            ],
        ),
    }


def _mf_engineering_legal_allowed_section(
    index_no,
    section_value,
):
    allowed = (
        ENGINEERING_LEGALS_MACHINE_FILE_MAP
        .get(
            str(index_no),
            [],
        )
    )

    actual = _mf_legal_normalise(
        section_value
    )

    return any(
        actual
        == _mf_legal_normalise(
            expected
        )
        for expected in allowed
    )


def _mf_engineering_legal_status(
    expiry_date,
):
    if not expiry_date:
        return "Submitted"

    expiry_date = getdate(
        expiry_date
    )

    today = getdate()

    if expiry_date < today:
        return "Overdue"

    if expiry_date <= add_days(
        today,
        30,
    ):
        return "Due Soon"

    return "Current"


def _mf_engineering_legals_files(
    names,
):
    result = {}

    if not names:
        return result

    files = _mf_readable_records(
        "File",
        filters={
            "attached_to_doctype":
                "Engineering Legals",

            "attached_to_name": [
                "in",
                names,
            ],

            "is_folder": 0,
        },
        fields=[
            "name",
            "file_name",
            "file_url",
            "attached_to_name",
        ],
        order_by="creation asc",
        limit_page_length=5000,
    )

    for file_row in files:
        result.setdefault(
            file_row.attached_to_name,
            []
        ).append({
            "name":
                file_row.name,

            "file_name":
                file_row.file_name
                or file_row.name,

            "file_url":
                file_row.file_url,
        })

    return result


def _mf_get_engineering_legals(
    machine,
    site,
    index_no,
    respect_permissions=False,
):
    index_no = str(
        index_no
    )

    if (
        index_no
        not in
        ENGINEERING_LEGALS_MACHINE_FILE_MAP
    ):
        return []

    config = (
        _mf_engineering_legals_config()
    )

    if not config:
        return []

    section_field = config.get(
        "section_field"
    )

    fleet_field = config.get(
        "fleet_field"
    )

    site_field = config.get(
        "site_field"
    )

    attachment_field = config.get(
        "attachment_field"
    )

    start_field = config.get(
        "start_date_field"
    )

    expiry_field = config.get(
        "expiry_date_field"
    )

    if (
        not section_field
        or not fleet_field
    ):
        return []

    meta = frappe.get_meta(
        "Engineering Legals"
    )

    meta_fields = {
        df.fieldname
        for df in meta.fields
    }

    fields = [
        "name",
        "docstatus",
        "creation",
        "modified",
        section_field,
        fleet_field,
    ]

    for fieldname in [
        site_field,
        attachment_field,
        start_field,
        expiry_field,
    ]:
        if (
            fieldname
            and fieldname
            in meta_fields
            and fieldname
            not in fields
        ):
            fields.append(
                fieldname
            )

    #
    # Engineering Legals may be either a submittable
    # or normal saved DocType.
    #
    # If submittable:
    #     only Submitted records (docstatus = 1)
    #
    # If not submittable:
    #     saved records have docstatus = 0
    #
    filters = {
        fleet_field: machine,
    }

    if meta.is_submittable:
        filters["docstatus"] = 1
    else:
        filters["docstatus"] = ["<", 2]

    # Legal history follows the machine across site transfers.
    # Fleet Number and Sections determine the matching records.

    query = _mf_readable_records if respect_permissions else frappe.get_all
    rows = query(
        "Engineering Legals",
        filters=filters,
        fields=fields,
        order_by=(
            f"{start_field} desc"
            if start_field
            else "modified desc"
        ),
        limit_page_length=5000,
    )

    rows = [
        row
        for row in rows
        if _mf_engineering_legal_allowed_section(
            index_no,
            row.get(
                section_field
            ),
        )
    ]

    file_map = (
        _mf_engineering_legals_files(
            [
                row.name
                for row in rows
            ]
        )
    )

    result = []

    for row in rows:
        start_date = (
            row.get(
                start_field
            )
            if start_field
            else None
        )

        expiry_date = (
            row.get(
                expiry_field
            )
            if expiry_field
            else None
        )

        section = (
            row.get(
                section_field
            )
            or ""
        )

        attachments = list(
            file_map.get(
                row.name,
                []
            )
        )

        direct_attachment = (
            row.get(
                attachment_field
            )
            if attachment_field
            else None
        )

        if direct_attachment:
            direct_url = str(
                direct_attachment
            )

            if not any(
                file_row.get(
                    "file_url"
                )
                == direct_url
                for file_row
                in attachments
            ):
                attachments.insert(
                    0,
                    {
                        "name":
                            direct_url,

                        "file_name":
                            os.path.basename(
                                direct_url
                            )
                            or "Attachment",

                        "file_url":
                            direct_url,
                    },
                )

        status = (
            _mf_engineering_legal_status(
                expiry_date
            )
        )

        details = []

        if expiry_date:
            details.append(
                "Expiry: "
                + str(
                    getdate(
                        expiry_date
                    )
                )
            )

        result.append({
            "name":
                row.name,

            "section":
                section,

            "date":
                (
                    str(start_date)
                    if start_date
                    else str(
                        row.creation
                    )
                ),

            "start_date":
                (
                    str(
                        getdate(
                            start_date
                        )
                    )
                    if start_date
                    else ""
                ),

            "expiry_date":
                (
                    str(
                        getdate(
                            expiry_date
                        )
                    )
                    if expiry_date
                    else ""
                ),

            "status":
                status,

            # Generic expanded Machine File
            # table already understands these.
            "purpose":
                section,

            "remarks":
                " | ".join(
                    details
                ),

            "attachments":
                attachments,
        })

    return result


def _mf_add_pressure_vessel_index():
    if any(
        str(
            item.get(
                "index_no"
            )
        )
        == "21"
        for item in INDEX_TEMPLATE
    ):
        return

    INDEX_TEMPLATE.append({
        "index_no": "21",

        "description":
            "Pressure Vessel Inspection / Certificate",

        "frequency":
            "As per Legal Expiry",

        "source_candidates": [],
    })


_mf_add_pressure_vessel_index()


def _mf_apply_legals_to_machine_file(
    doc,
):
    doc.ensure_index()

    for row in (
        doc.index_items
        or []
    ):
        index_no = str(
            row.index_no
            or ""
        )

        if (
            index_no
            not in
            ENGINEERING_LEGALS_MACHINE_FILE_MAP
        ):
            continue

        records = (
            _mf_get_engineering_legals(
                doc.machine,
                doc.site,
                index_no,
            )
        )

        if not records:
            continue

        #
        # _refresh_doc has already reset
        # the normal Machine File counts.
        #
        row.record_count = (
            int(
                row.record_count
                or 0
            )
            + len(
                records
            )
        )

        date_values = []

        if row.last_record_date:
            date_values.append(
                getdate(
                    row.last_record_date
                )
            )

        for record in records:
            if record.get(
                "start_date"
            ):
                date_values.append(
                    getdate(
                        record[
                            "start_date"
                        ]
                    )
                )

        if date_values:
            row.last_record_date = max(
                date_values
            )

        #
        # Latest legal record controls
        # the legal status/due date.
        #
        latest = records[0]

        expiry = latest.get(
            "expiry_date"
        )

        if expiry:
            row.next_due_date = getdate(
                expiry
            )

            row.status = (
                _mf_engineering_legal_status(
                    expiry
                )
            )

        else:
            row.status = (
                "ERP Records"
            )


#
# Preserve existing section-detail method and enhance it.
#
if (
    "get_machine_file_section_details"
    in globals()
    and "_mf_original_section_details"
    not in globals()
):
    _mf_original_section_details = (
        get_machine_file_section_details
    )


if "_mf_original_section_details" in globals():

    @frappe.whitelist()
    def get_machine_file_section_details(
        name,
        index_no,
    ):
        data = (
            _mf_original_section_details(
                name,
                index_no,
            )
        )

        index_no = str(
            index_no
            or ""
        )

        if (
            index_no
            not in
            ENGINEERING_LEGALS_MACHINE_FILE_MAP
        ):
            return data

        doc = frappe.get_doc(
            "Machine File",
            name
        )

        records = (
            _mf_get_engineering_legals(
                doc.machine,
                doc.site,
                index_no,
                respect_permissions=True,
            )
        )

        if not records:
            return data

        #
        # Feed Engineering Legals into the
        # existing ERP-record renderer.
        #
        existing_records = (
            data.get(
                "source_records"
            )
            or []
        )

        data[
            "source_records"
        ] = (
            records
            + existing_records
        )

        data[
            "source_doctype"
        ] = "Engineering Legals"

        #
        # Deliberately blank so the existing
        # "View ERP Records" button doesn't
        # open every legal category.
        #
        data[
            "source_asset_field"
        ] = ""

        data[
            "engineering_legals_mapped"
        ] = True

        return data


#
# Replace only the refresh endpoint.
#
@frappe.whitelist()
def refresh_machine_file(name):
    doc = frappe.get_doc(
        "Machine File",
        name,
    )

    doc.check_permission(
        "write"
    )

    _refresh_doc(
        doc
    )

    _mf_apply_legals_to_machine_file(
        doc
    )

    doc.save(
        ignore_permissions=True
    )

    return {
        "name":
            doc.name,

        "machine":
            doc.machine,

        "last_refreshed":
            doc.last_refreshed,
    }


@frappe.whitelist(methods=["POST"])
def sync_engineering_legals_to_machine_files():
    """
    Refresh all current Machine Files and link
    submitted Engineering Legals records.
    """

    frappe.only_for("System Manager")

    names = frappe.get_all(
        "Machine File",
        pluck="name",
        order_by="name asc",
    )

    updated = 0
    failed = []

    for name in names:
        try:
            doc = frappe.get_doc(
                "Machine File",
                name,
            )

            _refresh_doc(
                doc
            )

            _mf_apply_legals_to_machine_file(
                doc
            )

            doc.save(
                ignore_permissions=True
            )

            updated += 1

        except Exception:
            failed.append(
                name
            )

            frappe.log_error(
                title=(
                    "Machine File Engineering "
                    f"Legals Sync - {name}"
                ),
                message=(
                    frappe.get_traceback()
                ),
            )

    frappe.db.commit()

    return {
        "total_machine_files":
            len(names),

        "updated":
            updated,

        "failed_count":
            len(failed),

        "failed":
            failed[:25],
    }


@frappe.whitelist()
def engineering_legals_mapping_diagnostic(
    machine=None,
):

    frappe.only_for("System Manager")
    config = (
        _mf_engineering_legals_config()
    )

    result = {
        "doctype_exists":
            bool(
                frappe.db.exists(
                    "DocType",
                    "Engineering Legals"
                )
            ),

        "config":
            config,

        "mapping":
            ENGINEERING_LEGALS_MACHINE_FILE_MAP,

        "machine":
            machine,

        "sections":
            {},
    }

    if machine:
        machine_file_name = (
            frappe.db.get_value(
                "Machine File",
                {
                    "machine":
                        machine
                },
                "name",
            )
        )

        if machine_file_name:
            mf = frappe.get_doc(
                "Machine File",
                machine_file_name,
            )

            mf.check_permission("read")

            for index_no in (
                ENGINEERING_LEGALS_MACHINE_FILE_MAP
            ):
                records = (
                    _mf_get_engineering_legals(
                        mf.machine,
                        mf.site,
                        index_no,
                    )
                )

                result[
                    "sections"
                ][
                    index_no
                ] = {
                    "count":
                        len(records),

                    "records":
                        records[:10],
                }

    return result

# MACHINE FILE ENGINEERING LEGALS LINK END


# MACHINE FILE AUTHENTICATED ATTACHMENT START


# MACHINE FILE AUTHENTICATED ATTACHMENT END


# MACHINE FILE INLINE ATTACHMENT VIEW V2 START

@frappe.whitelist()
def open_machine_file_attachment(file_url):
    """
    Open Machine File / Engineering Legals attachments
    inside the browser.

    PDFs are displayed using the browser PDF viewer.
    Other supported file types use inline Content-Disposition.
    """

    import mimetypes
    import os

    file_url = str(
        file_url or ""
    ).strip()

    if not file_url:
        frappe.throw(
            "Attachment URL is required."
        )

    file_name = frappe.db.get_value(
        "File",
        {
            "file_url": file_url
        },
        "name",
    )

    if not file_name:
        frappe.throw(
            f"File record not found for {file_url}"
        )

    file_doc = frappe.get_doc(
        "File",
        file_name
    )

    file_doc.check_permission("read")
    if file_doc.attached_to_doctype and file_doc.attached_to_name:
        try:
            attached_doc = frappe.get_doc(
                file_doc.attached_to_doctype, file_doc.attached_to_name
            )
        except frappe.DoesNotExistError:
            frappe.throw("Attachment source is unavailable.", frappe.PermissionError)
        attached_doc.check_permission("read")

    # -----------------------------------------------------
    # PHYSICAL FILE
    # -----------------------------------------------------

    full_path = file_doc.get_full_path()

    if not os.path.isfile(
        full_path
    ):
        frappe.throw(
            "The attachment exists in ERP but "
            "the physical file is missing."
        )

    content = file_doc.get_content()

    if not content:
        frappe.throw(
            "The attachment is empty."
        )

    filename = (
        file_doc.file_name
        or os.path.basename(
            full_path
        )
        or "attachment"
    )

    content_type = (
        mimetypes.guess_type(
            filename
        )[0]
        or "application/octet-stream"
    )

    extension = (
        os.path.splitext(
            filename
        )[1]
        .lower()
    )

    # -----------------------------------------------------
    # PDF
    #
    # Frappe's PDF response uses:
    # Content-Disposition: inline
    #
    # This opens Chrome/Edge's PDF viewer instead of
    # downloading immediately.
    # -----------------------------------------------------

    if extension == ".pdf":

        frappe.local.response[
            "filename"
        ] = filename

        frappe.local.response[
            "filecontent"
        ] = content

        frappe.local.response[
            "type"
        ] = "pdf"

        return

    # -----------------------------------------------------
    # IMAGES / OTHER BROWSER-SUPPORTED FILE TYPES
    # -----------------------------------------------------

    frappe.local.response[
        "filename"
    ] = filename

    frappe.local.response[
        "filecontent"
    ] = content

    frappe.local.response[
        "content_type"
    ] = content_type

    frappe.local.response[
        "display_content_as"
    ] = "attachment"

    frappe.local.response[
        "type"
    ] = "download"


# MACHINE FILE INLINE ATTACHMENT VIEW V2 END



# MACHINE FILE BREAKDOWN REASONS START

@frappe.whitelist()
def get_machine_breakdown_log_summary(name):
    """
    Return the same PBM breakdown-detail calculation used by
    Availability & Utilisation Month End.

    Section 11 must show:
        Start
        Resolved
        Total Time
        Start-up + Fatigue
        Sunday Hours
        A&U Time
        Reason
    """

    from frappe.utils import getdate

    from engineering.engineering.report.availability_and_utilisation_month_end_report import (
        availability_and_utilisation_month_end_report as month_end,
    )

    doc = frappe.get_doc(
        "Machine File",
        name,
    )

    doc.check_permission(
        "read"
    )

    machine = (
        doc.machine
        or ""
    )

    site = (
        doc.site
        or ""
    )

    if not machine:
        return {
            "machine": "",
            "rows": [],
            "totals": {
                "total_minutes": 0,
                "startup_fatigue_minutes": 0,
                "sunday_minutes": 0,
                "au_minutes": 0,
            },
        }

    # ---------------------------------------------------------
    # Determine complete PBM date range for this machine.
    #
    # Keep this aligned with the canonical Month End helper,
    # which trusts PBM records from 2026-01-01 onward.
    # ---------------------------------------------------------

    conditions = [
        "asset_name = %(machine)s",
        "breakdown_start_datetime IS NOT NULL",
        "IFNULL(breakdown_reason, '') != ''",
        "IFNULL(exclude_from_au, 0) = 0",
        (
            "breakdown_start_datetime >= "
            "'2026-01-01 00:00:00'"
        ),
    ]

    values = {
        "machine": machine,
    }

    if site:
        conditions.append(
            "location = %(site)s"
        )

        values["site"] = site

    permitted_filters = {"asset_name": machine}
    if site:
        permitted_filters["location"] = site
    permitted_names = _mf_readable_records(
        "Plant Breakdown or Maintenance",
        filters=permitted_filters,
        pluck="name",
        limit_page_length=0,
    )
    if not permitted_names:
        return {
            "machine": machine, "site": site, "rows": [],
            "totals": {key: 0 for key in (
                "total_minutes", "startup_fatigue_minutes",
                "sunday_minutes", "au_minutes",
            )},
        }
    conditions.append("name IN %(permitted_names)s")
    values["permitted_names"] = tuple(permitted_names)

    bounds = frappe.db.sql(
        f"""
        SELECT
            MIN(
                DATE(
                    breakdown_start_datetime
                )
            ) AS from_date,

            MAX(
                DATE(
                    COALESCE(
                        resolved_datetime,
                        NOW()
                    )
                )
            ) AS to_date

        FROM `tabPlant Breakdown or Maintenance`

        WHERE {" AND ".join(conditions)}
        """,
        values,
        as_dict=True,
    )

    bounds = (
        bounds[0]
        if bounds
        else frappe._dict()
    )

    from_date = bounds.get(
        "from_date"
    )

    to_date = bounds.get(
        "to_date"
    )

    if not from_date or not to_date:
        return {
            "machine": machine,
            "site": site,
            "rows": [],
            "totals": {
                "total_minutes": 0,
                "startup_fatigue_minutes": 0,
                "sunday_minutes": 0,
                "au_minutes": 0,
            },
        }

    # ---------------------------------------------------------
    # IMPORTANT:
    # Reuse the exact Month End/A&U helper.
    #
    # Do not create a second downtime formula here.
    # ---------------------------------------------------------

    filters = frappe._dict({
        "from_date": str(
            from_date
        ),
        "to_date": str(
            to_date
        ),
        "location": site,
    })

    detail_map = (
        month_end
        .get_plant_breakdown_reason_details(
            filters,
            [machine],
            allowed_names=permitted_names,
        )
    )

    details = (
        detail_map.get(
            machine
        )
        or []
    )

    # The Month End report already has a cleanup routine
    # for duplicate/grouped reason segments.
    if hasattr(
        month_end,
        "clean_reason_details"
    ):
        try:
            details = (
                month_end
                .clean_reason_details(
                    details
                )
            )
        except Exception:
            pass

    rows = []

    totals = {
        "total_minutes": 0,
        "startup_fatigue_minutes": 0,
        "sunday_minutes": 0,
        "au_minutes": 0,
    }

    def minute_value(value):
        try:
            return int(
                round(
                    float(
                        value or 0
                    )
                )
            )
        except Exception:
            return 0

    for detail in details:

        total_minutes = minute_value(
            detail.get(
                "total_minutes"
            )
        )

        startup_minutes = minute_value(
            detail.get(
                "startup_fatigue_minutes"
            )
        )

        sunday_minutes = minute_value(
            detail.get(
                "sunday_minutes"
            )
        )

        au_minutes = minute_value(
            detail.get(
                "au_minutes"
            )
        )

        start_datetime = detail.get(
            "start_datetime"
        )

        resolved_datetime = detail.get(
            "resolved_datetime"
        )

        rows.append({
            "date": (
                str(
                    detail.get("date")
                )
                if detail.get("date")
                else ""
            ),

            "start_datetime": (
                str(start_datetime)
                if start_datetime
                else ""
            ),

            "resolved_datetime": (
                str(resolved_datetime)
                if resolved_datetime
                else ""
            ),

            "total_minutes":
                total_minutes,

            "startup_fatigue_minutes":
                startup_minutes,

            "sunday_minutes":
                sunday_minutes,

            "au_minutes":
                au_minutes,

            "reason": (
                detail.get(
                    "reason"
                )
                or ""
            ),
        })

        totals[
            "total_minutes"
        ] += total_minutes

        totals[
            "startup_fatigue_minutes"
        ] += startup_minutes

        totals[
            "sunday_minutes"
        ] += sunday_minutes

        totals[
            "au_minutes"
        ] += au_minutes

    rows.sort(
        key=lambda row: (
            row.get(
                "start_datetime"
            )
            or ""
        )
    )

    return {
        "machine": machine,
        "site": site,
        "from_date": str(
            getdate(
                from_date
            )
        ),
        "to_date": str(
            getdate(
                to_date
            )
        ),
        "rows": rows,
        "totals": totals,
    }

# MACHINE FILE BREAKDOWN REASONS END



# MACHINE FILE FREQUENCY DOCUMENT SAVE START

def _mf_document_frequency_months(
    index_no,
    frequency,
):
    """
    Return a calendar-month interval only where the
    Machine File frequency clearly defines one.

    Event-based frequencies intentionally return None.
    """

    import re

    index_no = str(
        index_no or ""
    ).strip()

    frequency = str(
        frequency or ""
    ).strip()

    value = frequency.casefold()

    # Quarterly
    if "quarter" in value:
        return 3

    # 6 Months NDT, 12 Months, etc.
    match = re.search(
        r"(\d+)\s*months?",
        value,
    )

    if match:
        return int(
            match.group(1)
        )

    # Annual / yearly
    if (
        "annual" in value
        or "yearly" in value
    ):
        return 12

    # Pressure Vessel section:
    # follow existing Engineering Legals 12-month rule.
    if index_no == "21":
        return 12

    return None


def _mf_get_index_frequency(
    doc,
    index_no,
):
    index_no = str(
        index_no or ""
    ).strip()

    for row in (
        doc.index_items
        or []
    ):
        if str(
            row.index_no or ""
        ).strip() == index_no:
            return (
                row.frequency
                or ""
            )

    return ""


def _mf_document_status(
    expiry_date,
):
    from frappe.utils import (
        add_days,
        getdate,
        today,
    )

    if not expiry_date:
        return "Current"

    expiry = getdate(
        expiry_date
    )

    current = getdate(
        today()
    )

    if expiry < current:
        return "Overdue"

    if expiry <= add_days(
        current,
        30,
    ):
        return "Due Soon"

    return "Current"


def _mf_update_manual_section_status(
    doc,
    index_no,
):
    """
    Make sure a manually saved document immediately updates
    Records / Last Record / Next Due / Status.

    The normal Machine File refresh remains the main source
    for ERP-linked counts.
    """

    from frappe.utils import getdate

    index_no = str(
        index_no or ""
    ).strip()

    documents = [
        row
        for row in (
            doc.documents
            or []
        )
        if str(
            row.index_no
            or ""
        ).strip() == index_no
    ]

    if not documents:
        return

    index_row = None

    for row in (
        doc.index_items
        or []
    ):
        if str(
            row.index_no
            or ""
        ).strip() == index_no:
            index_row = row
            break

    if not index_row:
        return

    #
    # Do not reduce an ERP-derived count.
    #
    index_row.record_count = max(
        int(
            index_row.record_count
            or 0
        ),
        len(documents),
    )

    dated = [
        row
        for row in documents
        if row.document_date
    ]

    if dated:
        latest = max(
            dated,
            key=lambda row:
                getdate(
                    row.document_date
                ),
        )

        latest_date = getdate(
            latest.document_date
        )

        if (
            not index_row.last_record_date
            or latest_date
            > getdate(
                index_row.last_record_date
            )
        ):
            index_row.last_record_date = (
                latest_date
            )

        expiry = getattr(
            latest,
            "expiry_date",
            None,
        )

        if expiry:
            index_row.next_due_date = (
                getdate(
                    expiry
                )
            )

            index_row.status = (
                _mf_document_status(
                    expiry
                )
            )

        elif (
            index_row.status
            in (
                "",
                None,
                "Missing",
            )
        ):
            index_row.status = "Current"

    elif (
        index_row.status
        in (
            "",
            None,
            "Missing",
        )
    ):
        index_row.status = "Current"


@frappe.whitelist()
def save_machine_file_document(
    name,
    index_no,
    document_type,
    document_date,
    attachment,
    notes=None,
    next_due_date=None,
):
    """
    Central Machine File document save.

    Frequency behaviour:
      Quarterly       -> +3 months
      N Months        -> +N months
      Annual/Yearly   -> +12 months
      Pressure Vessel -> +12 months

    Event-based frequencies such as:
      Continuous
      Every Service
      Inspection
      250 Hours / After Brake Work

    do not receive an invented calendar expiry.
    The user may enter Next Due where applicable.
    """

    from frappe.utils import (
        add_months,
        getdate,
    )

    name = str(
        name or ""
    ).strip()

    index_no = str(
        index_no or ""
    ).strip()

    document_type = str(
        document_type or ""
    ).strip()

    attachment = str(
        attachment or ""
    ).strip()

    notes = str(
        notes or ""
    ).strip()

    if not name:
        frappe.throw(
            "Machine File is required."
        )

    if not index_no:
        frappe.throw(
            "Machine File Index No. is required."
        )

    if not document_type:
        frappe.throw(
            "Document / Report is required."
        )

    if not document_date:
        frappe.throw(
            "Document Start Date is required."
        )

    if not attachment:
        frappe.throw(
            "Attachment is required."
        )

    doc = frappe.get_doc(
        "Machine File",
        name,
    )

    doc.check_permission(
        "write"
    )

    start_date = getdate(
        document_date
    )

    frequency = (
        _mf_get_index_frequency(
            doc,
            index_no,
        )
    )

    months = (
        _mf_document_frequency_months(
            index_no,
            frequency,
        )
    )

    #
    # Fixed date frequency always controls Next Due.
    #
    if months:
        expiry_date = add_months(
            start_date,
            months,
        )

    elif next_due_date:
        expiry_date = getdate(
            next_due_date
        )

    else:
        expiry_date = None

    #
    # Validate hidden child table before appending.
    #
    parent_meta = frappe.get_meta(
        "Machine File"
    )

    documents_field = (
        parent_meta.get_field(
            "documents"
        )
    )

    if (
        not documents_field
        or documents_field.fieldtype
        != "Table"
    ):
        frappe.throw(
            "Machine File documents table was not found."
        )

    child_meta = frappe.get_meta(
        documents_field.options
    )

    child_fields = {
        df.fieldname
        for df in child_meta.fields
    }

    values = {}

    if "index_no" in child_fields:
        values["index_no"] = (
            index_no
        )

    if "document_type" in child_fields:
        values["document_type"] = (
            document_type
        )

    if "document_date" in child_fields:
        values["document_date"] = (
            start_date
        )

    if "expiry_date" in child_fields:
        values["expiry_date"] = (
            expiry_date
        )

    if "attachment" in child_fields:
        values["attachment"] = (
            attachment
        )

    if "notes" in child_fields:
        values["notes"] = (
            notes
        )

    row = doc.append(
        "documents",
        values,
    )

    doc.save()

    #
    # Attach the uploaded File record to Machine File
    # where the upload is not already attached elsewhere.
    #
    file_name = frappe.db.get_value(
        "File",
        {
            "file_url": attachment
        },
        "name",
    )

    if file_name:
        file_doc = frappe.get_doc(
            "File",
            file_name,
        )

        if not file_doc.attached_to_name:

            updates = {
                "attached_to_doctype":
                    "Machine File",

                "attached_to_name":
                    doc.name,
            }

            file_meta = frappe.get_meta(
                "File"
            )

            if file_meta.has_field(
                "attached_to_field"
            ):
                updates[
                    "attached_to_field"
                ] = "documents"

            frappe.db.set_value(
                "File",
                file_name,
                updates,
                update_modified=False,
            )

    #
    # Run normal Machine File source refresh first.
    #
    try:
        if (
            "refresh_machine_file"
            in globals()
        ):
            refresh_machine_file(
                doc.name
            )
    except Exception:
        frappe.log_error(
            title=(
                "Machine File Document "
                "Refresh Warning"
            ),
            message=(
                frappe.get_traceback()
            ),
        )

    #
    # Reload and guarantee the manual document is reflected.
    #
    doc = frappe.get_doc(
        "Machine File",
        doc.name,
    )

    _mf_update_manual_section_status(
        doc,
        index_no,
    )

    doc.save(
        ignore_permissions=True
    )

    frappe.db.commit()

    index_row = None

    for item in (
        doc.index_items
        or []
    ):
        if str(
            item.index_no
            or ""
        ).strip() == index_no:
            index_row = item
            break

    return {
        "machine_file":
            doc.name,

        "row_name":
            row.name,

        "index_no":
            index_no,

        "frequency":
            frequency,

        "document_date":
            str(
                start_date
            ),

        "next_due_date":
            (
                str(
                    expiry_date
                )
                if expiry_date
                else ""
            ),

        "status":
            (
                index_row.status
                if index_row
                else _mf_document_status(
                    expiry_date
                )
            ),

        "record_count":
            (
                index_row.record_count
                if index_row
                else 1
            ),

        "last_record_date":
            (
                str(
                    index_row
                    .last_record_date
                )
                if (
                    index_row
                    and index_row
                    .last_record_date
                )
                else ""
            ),
    }

# MACHINE FILE FREQUENCY DOCUMENT SAVE END



# MACHINE FILE LIVE LEGALS MAPPING FIX START

#
# Exact Engineering Legals names currently used in ERP.
#
# Machine File:
#
# 5 = Illumination Baseline and Periodical
#     Measurements Report (VOHE)
#
# 7 = PDS Inspection Report
#

ENGINEERING_LEGALS_MACHINE_FILE_MAP["5"] = [
    "Illumination Baseline",
    "Illumination Baseline & Measurement",
    "Illumination Baseline and Measurement",
    "Illumination Measurement",
]

ENGINEERING_LEGALS_MACHINE_FILE_MAP["7"] = [
    "PDS",
    "PDS Inspection",
    "PDS Inspection Report",
    "PDS-MPI Maintenance",
    "PDS MPI Maintenance",
    "PDS Installation",
]

# MACHINE FILE LIVE LEGALS MAPPING FIX END



# MACHINE FILE LDV SUPPLIER GROUPING START

@frappe.whitelist()
def get_ldv_supplier_groups(machines=None):
    """
    Return supplier information for the LDVs already displayed
    in the Machine File fleet list.

    The displayed Machine File list remains the authority for
    which assets are included, so submitted-only filtering
    already applied by the list is preserved.
    """

    import json

    if not machines:
        return {
            "supplier_field": "",
            "rows": [],
        }

    if isinstance(
        machines,
        str,
    ):
        try:
            machines = json.loads(
                machines
            )
        except Exception:
            machines = [
                item.strip()
                for item in machines.split(",")
                if item.strip()
            ]

    machines = [
        str(machine).strip()
        for machine in (
            machines or []
        )
        if str(machine).strip()
    ]

    if not machines:
        return {
            "supplier_field": "",
            "rows": [],
        }

    meta = frappe.get_meta(
        "Asset"
    )

    fields_by_name = {
        df.fieldname: df
        for df in meta.fields
    }

    # -----------------------------------------------------
    # Detect the actual Supplier field used on Asset.
    # -----------------------------------------------------

    supplier_field = None

    candidates = [
        "supplier",
        "custom_supplier",
        "asset_supplier",
        "equipment_supplier",
        "machine_supplier",
        "custom_asset_supplier",
        "custom_equipment_supplier",
        "custom_machine_supplier",
        "supplier_name",
    ]

    for candidate in candidates:

        if candidate in fields_by_name:
            supplier_field = (
                candidate
            )
            break


    # Prefer a Link -> Supplier if exact candidate
    # names were not found.
    if not supplier_field:

        for df in meta.fields:

            if (
                df.fieldtype == "Link"
                and df.options == "Supplier"
            ):
                supplier_field = (
                    df.fieldname
                )
                break


    # Last safe fallback: a field whose label
    # explicitly contains Supplier.
    if not supplier_field:

        for df in meta.fields:

            label = str(
                df.label or ""
            ).strip().lower()

            if (
                "supplier" in label
                and df.fieldtype
                in (
                    "Link",
                    "Data",
                    "Select",
                )
            ):
                supplier_field = (
                    df.fieldname
                )
                break


    if not supplier_field:

        return {
            "supplier_field": "",
            "error":
                "No supplier field was found on Asset.",
            "rows": [],
        }


    fields = [
        "name",
        "asset_name",
        "item_name",
        "location",
        supplier_field,
    ]


    rows = _mf_readable_records(
        "Asset",
        filters={
            "name": [
                "in",
                machines,
            ]
        },
        fields=fields,
        limit_page_length=5000,
    )


    by_machine = {
        row.name: row
        for row in rows
    }


    result = []

    for machine in machines:

        row = by_machine.get(
            machine
        )

        if not row:
            continue


        supplier = str(
            row.get(
                supplier_field
            )
            or ""
        ).strip()


        # Assets without an external supplier are treated
        # as Isambane-owned for this LDV fleet grouping.
        if not supplier:
            supplier = "Isambane"


        result.append({
            "machine":
                machine,

            "supplier":
                supplier,

            "model":
                row.item_name
                or "",

            "location":
                row.location
                or "",
        })


    return {
        "supplier_field":
            supplier_field,

        "rows":
            result,
    }

# MACHINE FILE LDV SUPPLIER GROUPING END





# MACHINE FILE LDV SUPPLIER GROUPING V2 START

@frappe.whitelist()
def get_ldv_supplier_groups_v2(machines=None):
    """
    Resolve supplier/owner for the LDVs already shown by the
    Machine File fleet register.

    The existing submitted-only fleet list remains authoritative.
    """

    import json

    if isinstance(machines, str):
        try:
            machines = json.loads(machines)
        except Exception:
            machines = [
                value.strip()
                for value in machines.split(",")
                if value.strip()
            ]

    machines = [
        str(value or "").strip()
        for value in (machines or [])
        if str(value or "").strip()
    ]

    if not machines:
        return {
            "field": "",
            "rows": [],
        }


    meta = frappe.get_meta(
        "Asset"
    )

    field_map = {
        df.fieldname: df
        for df in meta.fields
    }


    # -----------------------------------------------------
    # Find all Assets by either Asset.name OR asset_name.
    # This protects us if the fleet number is stored in
    # asset_name rather than document name.
    # -----------------------------------------------------

    asset_names = set()


    direct = _mf_readable_records(
        "Asset",
        filters={
            "name": [
                "in",
                machines,
            ]
        },
        pluck="name",
        limit_page_length=5000,
    )

    asset_names.update(
        direct
    )


    if "asset_name" in field_map:

        by_asset_name = _mf_readable_records(
            "Asset",
            filters={
                "asset_name": [
                    "in",
                    machines,
                ]
            },
            pluck="name",
            limit_page_length=5000,
        )

        asset_names.update(
            by_asset_name
        )


    if not asset_names:

        return {
            "field": "",
            "error":
                "No matching Asset records found.",
            "rows": [],
        }


    # -----------------------------------------------------
    # Detect actual supplier / owner field.
    # Score the strongest fields first.
    # -----------------------------------------------------

    candidates = []


    for df in meta.fields:

        fieldname = str(
            df.fieldname or ""
        ).lower()

        label = str(
            df.label or ""
        ).lower()

        score = 0


        if (
            df.fieldtype == "Link"
            and df.options == "Supplier"
        ):
            score += 100


        if "supplier" in fieldname:
            score += 80

        if "supplier" in label:
            score += 80


        if "vendor" in fieldname:
            score += 60

        if "vendor" in label:
            score += 60


        if "owner" in fieldname:
            score += 50

        if "owner" in label:
            score += 50


        if "contractor" in fieldname:
            score += 40

        if "contractor" in label:
            score += 40


        if (
            "company" in fieldname
            or "company" in label
        ):
            score += 10


        if (
            score
            and df.fieldtype
            in (
                "Link",
                "Data",
                "Select",
            )
        ):
            candidates.append(
                (
                    score,
                    df.fieldname,
                    df.label,
                )
            )


    candidates.sort(
        reverse=True
    )


    base_fields = [
        "name",
        "asset_name",
        "item_name",
        "location",
    ]


    selected_field = None
    selected_rows = None
    selected_score = -1


    for _priority, fieldname, _label in candidates:

        fields = list(
            base_fields
        )

        if fieldname not in fields:
            fields.append(
                fieldname
            )


        rows = _mf_readable_records(
            "Asset",
            filters={
                "name": [
                    "in",
                    list(asset_names),
                ]
            },
            fields=fields,
            limit_page_length=5000,
        )


        non_empty = sum(
            1
            for row in rows
            if str(
                row.get(fieldname)
                or ""
            ).strip()
        )


        distinct = {
            str(
                row.get(fieldname)
                or ""
            ).strip()
            for row in rows
            if str(
                row.get(fieldname)
                or ""
            ).strip()
        }


        #
        # Non-empty values matter most.
        # Distinct suppliers increase confidence.
        #
        data_score = (
            non_empty * 10
            + len(distinct)
        )


        if data_score > selected_score:

            selected_score = (
                data_score
            )

            selected_field = (
                fieldname
            )

            selected_rows = (
                rows
            )


    # -----------------------------------------------------
    # If there is no supplier-style field with data,
    # return a useful diagnostic instead of silently failing.
    # -----------------------------------------------------

    if not selected_field:

        return {
            "field": "",
            "error":
                "No Supplier/Owner field detected on Asset.",
            "candidate_fields": [
                {
                    "fieldname": item[1],
                    "label": item[2],
                    "priority": item[0],
                }
                for item in candidates
            ],
            "rows": [],
        }


    rows_by_machine = {}


    for row in selected_rows or []:

        keys = {
            str(
                row.name or ""
            ).strip(),

            str(
                row.asset_name or ""
            ).strip(),
        }

        for key in keys:

            if key:
                rows_by_machine[
                    key
                ] = row


    result = []


    for machine in machines:

        asset = rows_by_machine.get(
            machine
        )

        if not asset:
            continue


        supplier = str(
            asset.get(
                selected_field
            )
            or ""
        ).strip()


        #
        # Blank owner/supplier means company-owned.
        #
        if not supplier:
            supplier = "Isambane"


        result.append({
            "machine":
                machine,

            "supplier":
                supplier,

            "model":
                asset.item_name
                or "",

            "location":
                asset.location
                or "",
        })


    return {
        "field":
            selected_field,

        "rows":
            result,

        "candidate_fields": [
            {
                "fieldname": item[1],
                "label": item[2],
                "priority": item[0],
            }
            for item in candidates
        ],
    }

# MACHINE FILE LDV SUPPLIER GROUPING V2 END




# MACHINE FILE ASSET OWNER SUPPLIER FIX START

@frappe.whitelist()
def get_machine_supplier_details(machines=None):
    """
    Return the actual Asset ownership/supplier information.

    Rules:
        Asset Owner = Supplier
            -> use Asset.supplier

        Asset Owner = Company
            -> use Asset.company

        Otherwise
            -> show captured Supplier first,
               then Company,
               otherwise blank.

    Never automatically label everything as Isambane.
    """

    import json

    if isinstance(
        machines,
        str,
    ):
        try:
            machines = json.loads(
                machines
            )
        except Exception:
            machines = [
                item.strip()
                for item in machines.split(",")
                if item.strip()
            ]

    machines = [
        str(machine or "").strip()
        for machine in (
            machines or []
        )
        if str(machine or "").strip()
    ]

    if not machines:
        return {
            "rows": []
        }


    meta = frappe.get_meta(
        "Asset"
    )

    fields = {
        df.fieldname
        for df in meta.fields
    }


    query_fields = [
        "name",
        "asset_name",
        "item_name",
        "location",
    ]


    for fieldname in [
        "asset_owner",
        "supplier",
        "company",
    ]:
        if (
            fieldname in fields
            and fieldname
            not in query_fields
        ):
            query_fields.append(
                fieldname
            )


    #
    # Some sites use Asset.name as fleet number,
    # others may use asset_name.
    #
    names = set()


    names.update(
        _mf_readable_records(
            "Asset",
            filters={
                "name": [
                    "in",
                    machines,
                ]
            },
            pluck="name",
            limit_page_length=5000,
        )
    )


    if "asset_name" in fields:

        names.update(
            _mf_readable_records(
                "Asset",
                filters={
                    "asset_name": [
                        "in",
                        machines,
                    ]
                },
                pluck="name",
                limit_page_length=5000,
            )
        )


    if not names:
        return {
            "rows": []
        }


    assets = _mf_readable_records(
        "Asset",
        filters={
            "name": [
                "in",
                list(names),
            ]
        },
        fields=query_fields,
        limit_page_length=5000,
    )


    by_machine = {}


    for asset in assets:

        for key in [
            asset.name,
            asset.get(
                "asset_name"
            ),
        ]:

            key = str(
                key or ""
            ).strip()

            if key:
                by_machine[
                    key
                ] = asset


    output = []


    for machine in machines:

        asset = by_machine.get(
            machine
        )

        if not asset:
            continue


        owner = str(
            asset.get(
                "asset_owner"
            )
            or ""
        ).strip()


        supplier = str(
            asset.get(
                "supplier"
            )
            or ""
        ).strip()


        company = str(
            asset.get(
                "company"
            )
            or ""
        ).strip()


        owner_lower = (
            owner.lower()
        )


        display_supplier = ""


        if (
            owner_lower
            == "supplier"
        ):

            display_supplier = (
                supplier
            )


        elif (
            owner_lower
            == "company"
        ):

            display_supplier = (
                company
            )


        else:

            #
            # Respect actual captured data.
            #
            display_supplier = (
                supplier
                or company
                or ""
            )


        output.append({

            "machine":
                machine,

            "asset_owner":
                owner,

            "supplier":
                supplier,

            "company":
                company,

            "display_supplier":
                display_supplier,

            "model":
                asset.get(
                    "item_name"
                )
                or "",

            "location":
                asset.get(
                    "location"
                )
                or "",

        })


    return {
        "rows":
            output
    }

# MACHINE FILE ASSET OWNER SUPPLIER FIX END


# Read-only Machine File period views.
def _mf_parse_period(value):
    value = frappe.parse_json(value) if isinstance(value, str) else value
    value = value or {}
    if not isinstance(value, dict):
        frappe.throw("Invalid Machine File period.")
    dates = []
    for key in ("from_date", "to_date"):
        raw = value.get(key)
        if raw and not _mf_period_re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw)):
            frappe.throw("Period dates must use YYYY-MM-DD.")
        try:
            dates.append(_mf_period_date.fromisoformat(raw) if raw else None)
        except (ValueError, TypeError):
            frappe.throw("Invalid period date.")
    start, end = dates
    if start and end and start > end:
        frappe.throw("From Date cannot be after To Date.")
    months = value.get("months") or []
    if not isinstance(months, list):
        frappe.throw("Months must be a list.")
    for month in months:
        if not isinstance(month, str) or not _mf_period_re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            frappe.throw("Invalid selected month.")
        if not 1 <= int(month[:4]) <= 9999:
            frappe.throw("Invalid selected year.")
    return start, end, set(months)


def _mf_period_matches(value, period):
    start, end, months = period
    if not (start or end or months):
        return True
    if not value:
        return False
    day = getdate(value)
    return (not start or day >= start) and (not end or day <= end) and (
        not months or day.strftime("%Y-%m") in months
    )


def _mf_period_legal_matches(row, period):
    from calendar import monthrange

    start, end, months = period
    if not (start or end or months):
        return True

    document_start = row.get("start_date")
    document_end = row.get("expiry_date")
    if not document_start or not document_end:
        return _mf_period_matches(document_start, period)

    first = getdate(document_start)
    last = getdate(document_end)
    if last < first:
        return False

    lower = max(first, start) if start else first
    upper = min(last, end) if end else last
    if lower > upper:
        return False
    if not months:
        return True

    for month in months:
        year, number = map(int, month.split("-"))
        month_start = _mf_period_date(year, number, 1)
        month_end = _mf_period_date(year, number, monthrange(year, number)[1])
        if lower <= month_end and upper >= month_start:
            return True
    return False


def _mf_period_filter_rows(rows, period, field="date"):
    return [row for row in rows or [] if _mf_period_matches(row.get(field), period)]


def _mf_period_filter_breakdown(data, period):
    # The canonical A&U helper returns segments per reporting day (06:00-06:00).
    # Filter those segments, retaining its duration calculations unchanged.
    data["rows"] = _mf_period_filter_rows(data.get("rows"), period)
    data["totals"] = {
        key: sum(row.get(key, 0) or 0 for row in data["rows"])
        for key in ("total_minutes", "startup_fatigue_minutes", "sunday_minutes", "au_minutes")
    }
    days = [row["date"] for row in data["rows"] if row.get("date")]
    data["from_date"] = min(days) if days else None
    data["to_date"] = max(days) if days else None
    return data


@frappe.whitelist()
def get_period_view(name, period=None):

    selected = _mf_parse_period(period)
    doc = frappe.get_doc("Machine File", name)
    doc.check_permission("read")
    sections = {}
    summary = []
    movement = None
    breakdown = None

    for index in doc.index_items or []:
        number = str(index.index_no)
        data = get_machine_file_section_details(name, number)
        data["source_records"] = [
            row for row in data.get("source_records") or []
            if (
                _mf_period_legal_matches(row, selected)
                if "start_date" in row
                else _mf_period_matches(row.get("date"), selected)
            )
        ]
        data["manual_documents"] = _mf_period_filter_rows(
            data.get("manual_documents"), selected, "document_date"
        )
        records = list(data["source_records"])
        if number == "1":
            movement = data.get("movement") or get_machine_registration_movement(name)
            movement["rows"] = _mf_period_filter_rows(movement.get("rows"), selected)
            data["movement"] = movement
            records = list(movement["rows"])
        elif number == "11":
            breakdown = _mf_period_filter_breakdown(get_machine_breakdown_log_summary(name), selected)
            records = list(breakdown["rows"])

        documents = data["manual_documents"]
        dates = [getdate(r["date"]) for r in records if r.get("date")]
        dates += [getdate(r["document_date"]) for r in documents if r.get("document_date")]
        count = len(records) + len(documents)
        status = "ERP Records" if count else "No records in period"
        due = None
        legal_records = [r for r in records if "start_date" in r]
        if legal_records:
            latest = max(legal_records, key=lambda r: r.get("start_date") or r.get("date") or "")
            due = latest.get("expiry_date") or None
            status = _mf_engineering_legal_status(due) if due else "ERP Records"
        elif documents:
            latest = max(documents, key=lambda r: r.get("document_date") or "")
            due = latest.get("expiry_date") or None
            if due:
                status = _mf_engineering_legal_status(due)
        summary.append({
            "index_no": number, "description": index.description,
            "frequency": index.frequency, "source_doctype": data.get("source_doctype"),
            "source_asset_field": data.get("source_asset_field"),
            "record_count": count, "last_record_date": max(dates) if dates else None,
            "next_due_date": due, "status": status,
        })
        data["period_filtered"] = True
        sections[number] = data
    return {"rows": summary, "sections": sections, "movement": movement, "breakdown": breakdown}


def _mf_readable_records(doctype, **kwargs):
    """Read source rows using the current user's configured permissions."""
    if not frappe.has_permission(doctype, "read"):
        return []
    rows = frappe.get_list(doctype, **kwargs)
    result = []
    for row in rows:
        name = row if isinstance(row, str) else row.get("name")
        if not name:
            continue
        try:
            doc = frappe.get_doc(doctype, name)
        except frappe.DoesNotExistError:
            continue
        if doc.has_permission("read"):
            result.append(row)
    return result
