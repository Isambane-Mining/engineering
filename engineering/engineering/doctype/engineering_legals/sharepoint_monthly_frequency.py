from __future__ import annotations

import mimetypes
import os
from datetime import datetime
from urllib.parse import quote

import frappe
import requests
from frappe.utils import get_first_day, getdate, nowdate

from engineering.engineering.report.engineering_legals_monthly_summary.engineering_legals_monthly_summary import (
    execute as execute_monthly_summary,
)

from engineering.engineering.doctype.engineering_legals.engineering_legals import (
    NEW_SHAREPOINT_ROOT,
    NEW_SHAREPOINT_SECTION_MAPPING,
    NEW_SHAREPOINT_SITE_MAPPING,
    _ensure_sharepoint_folder,
    _get_graph_access_token,
    _get_sharepoint_drive_id,
    _get_sharepoint_settings,
    _get_sharepoint_site_id,
    _graph_request,
    _sanitize_sharepoint_part,
)


# These documents must remain visible in every monthly folder
# from their Start Date month through their Expiry Date month.
RECURRING_UNTIL_EXPIRY_SECTIONS = {
    "Fire Suppression",
    "Illumination Baseline",
    "Noise Level Baseline & Measurement",
    "NDT",
    "Machine NDT",
    "Brake Test",
    "FRCS",
    "Lifting Equipment",

    # These will begin working automatically once the exact ERP
    # section records and expiry rules are added.
    "Brake Tester Calibration Certificate",
    "Brake Test Authorisations",
    "CoC for Containers, Offices, Workshops",
    "Multi-meter Calibration Certificate",
    "Authorised LV Person",
    "Earth Leakage Testing",
    "Load Test Certificate",
    "Pressure Vessels",
}


def _month_start(value):
    if not value:
        return None

    return getdate(get_first_day(getdate(value)))


def _target_month(year=None, month=None):
    if year is None or month is None:
        selected = getdate(nowdate())
        year = selected.year
        month = selected.month

    year = int(year)
    month = int(month)

    if month < 1 or month > 12:
        frappe.throw("Month must be between 1 and 12.")

    sharepoint_month_names = {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "June",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
    }

    month_date = getdate(f"{year:04d}-{month:02d}-01")
    month_name = sharepoint_month_names[month]
    month_folder = f"{month:02d}.{month_name}-{year % 100:02d}"

    return month_date, month_folder


def _get_attachment_file(doc):
    file_url = getattr(doc, "attach_paper", None)

    if not file_url:
        return None

    file_row = frappe.get_value(
        "File",
        {
            "attached_to_doctype": doc.doctype,
            "attached_to_name": doc.name,
            "file_url": file_url,
            "is_folder": 0,
        },
        "name",
    )

    if not file_row:
        file_row = frappe.get_value(
            "File",
            {
                "file_url": file_url,
                "is_folder": 0,
            },
            "name",
        )

    if not file_row:
        return None

    return frappe.get_doc("File", file_row)


def _build_filename(doc, file_doc):
    raw_date = getattr(doc, "start_date", None)

    if raw_date:
        date_part = getdate(raw_date).strftime("%Y-%m-%d")
    else:
        date_part = "No-Date"

    original_ext = os.path.splitext(
        file_doc.file_name or ""
    )[1] or ".pdf"

    return _sanitize_sharepoint_part(
        f"{(doc.fleet_number or 'No Fleet').strip()}-"
        f"{(doc.sections or 'Unclassified').strip()}-"
        f"{date_part}{original_ext}"
    )



def _build_collision_filename(base_filename, docname):
    """
    Return a stable unique filename when multiple Engineering Legals
    records would otherwise resolve to the same SharePoint destination.

    The original/base filename remains unchanged for the first record.
    Additional records receive a short deterministic suffix based on
    their Engineering Legals document name.
    """
    import hashlib

    stem, extension = os.path.splitext(base_filename)

    suffix = hashlib.sha1(
        (docname or "").encode("utf-8")
    ).hexdigest()[:10]

    return _sanitize_sharepoint_part(
        f"{stem}__{suffix}{extension}"
    )


def _sharepoint_item_exists(
    drive_id,
    folder_parts,
    filename,
    token,
):
    full_path = "/".join(
        [*folder_parts, filename]
    )

    encoded_path = quote(full_path, safe="/")

    url = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
        f"/root:/{encoded_path}"
    )

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )

    if response.status_code == 404:
        return False

    if response.status_code == 401:
        return False

    response.raise_for_status()
    return True


def _upload_to_month(
    doc,
    month_folder,
    drive_id,
    token,
    dry_run,
    filename_override=None,
):
    site = (getattr(doc, "site", None) or "").strip()
    section = (getattr(doc, "sections", None) or "").strip()

    new_site = NEW_SHAREPOINT_SITE_MAPPING.get(site)
    category_parts = NEW_SHAREPOINT_SECTION_MAPPING.get(section)

    if not new_site:
        return {
            "status": "skipped",
            "reason": f"Site not configured: {site}",
        }

    if not category_parts:
        return {
            "status": "skipped",
            "reason": f"Section not mapped: {section}",
        }

    folder_parts = [
        NEW_SHAREPOINT_ROOT,
        month_folder,
        new_site,
        *category_parts,
    ]

    file_doc = _get_attachment_file(doc)

    if not file_doc:
        return {
            "status": "skipped",
            "reason": "Attachment File row not found",
        }

    filename = (
        filename_override
        or _build_filename(doc, file_doc)
    )

    destination = "/".join(
        [*folder_parts, filename]
    )

    if dry_run:
        return {
            "status": "planned",
            "destination": destination,
        }

    parent_item_id = _ensure_sharepoint_folder(
        drive_id,
        folder_parts,
        token,
    )

    if _sharepoint_item_exists(
        drive_id,
        folder_parts,
        filename,
        token,
    ):
        return {
            "status": "existing",
            "destination": destination,
        }

    content = file_doc.get_content()

    if content is None:
        return {
            "status": "failed",
            "reason": "Could not read attachment content",
        }

    if isinstance(content, str):
        data = content.encode("utf-8")
    else:
        data = content

    encoded_filename = quote(filename)

    upload_url = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
        f"/items/{parent_item_id}:/{encoded_filename}:/content"
    )

    mime_type = (
        mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )

    _graph_request(
        "PUT",
        upload_url,
        token,
        data=data,
        headers={"Content-Type": mime_type},
    )

    return {
        "status": "uploaded",
        "destination": destination,
    }


def sync_active_legals_for_month(
    year=None,
    month=None,
    dry_run=True,
):
    """
    Synchronize the exact Engineering Legals records represented by the
    Engineering Legals Monthly Summary into the corresponding SharePoint
    month.

    The monthly dashboard is the source of truth:
      Dashboard record_names_json == SharePoint expected records.

    This includes both:
      - active_until_expiry categories
      - saved_in_month categories

    When multiple ERP records resolve to the same legacy/base filename,
    the first record keeps the base filename and the additional records
    receive deterministic suffixes so the SharePoint file count can
    reconcile to the ERP dashboard record count.
    """
    if isinstance(dry_run, str):
        dry_run = dry_run.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

    selected_month, month_folder = _target_month(
        year=year,
        month=month,
    )

    # LAB must be able to perform a complete planning/dry-run without
    # SharePoint credentials.
    drive_id = None
    token = None

    if not dry_run:
        settings = _get_sharepoint_settings()
        token = _get_graph_access_token(settings)

        site_id = _get_sharepoint_site_id(
            settings,
            token,
        )

        drive_id = _get_sharepoint_drive_id(
            settings,
            site_id,
            token,
        )

    month_label = selected_month.strftime("%b")
    selected_records = []

    results = {
        "month": month_folder,
        "dry_run": dry_run,
        "checked": 0,
        "active": 0,
        "selected": 0,
        "planned": 0,
        "uploaded": 0,
        "existing": 0,
        "skipped": 0,
        "failed": 0,
        "collisions_resolved": 0,
        "details": [],
    }

    # --------------------------------------------------------
    # 1. Ask the dashboard for the exact records it counts.
    # --------------------------------------------------------

    for site in NEW_SHAREPOINT_SITE_MAPPING.keys():

        report_result = execute_monthly_summary({
            "site": site,
            "month": month_label,
            "year": selected_month.year,
        })

        report_rows = report_result[1] or []

        for report_row in report_rows:

            if report_row.get("is_total"):
                continue

            category = (
                report_row.get("category")
                or ""
            ).strip()

            record_names = frappe.parse_json(
                report_row.get("record_names_json")
                or "[]"
            ) or []

            for docname in record_names:

                results["checked"] += 1
                results["active"] += 1
                results["selected"] += 1

                try:
                    doc = frappe.get_doc(
                        "Engineering Legals",
                        docname,
                    )

                    file_doc = _get_attachment_file(doc)

                    if not file_doc:
                        results["skipped"] += 1

                        results["details"].append({
                            "name": docname,
                            "site": site,
                            "category": category,
                            "section": doc.sections,
                            "status": "skipped",
                            "reason": (
                                "Attachment File row not found"
                            ),
                        })

                        continue

                    new_site = NEW_SHAREPOINT_SITE_MAPPING.get(
                        (doc.site or "").strip()
                    )

                    category_parts = (
                        NEW_SHAREPOINT_SECTION_MAPPING.get(
                            (doc.sections or "").strip()
                        )
                    )

                    if not new_site:
                        results["skipped"] += 1

                        results["details"].append({
                            "name": docname,
                            "site": site,
                            "category": category,
                            "section": doc.sections,
                            "status": "skipped",
                            "reason": (
                                f"Site not configured: {doc.site}"
                            ),
                        })

                        continue

                    if not category_parts:
                        results["skipped"] += 1

                        results["details"].append({
                            "name": docname,
                            "site": site,
                            "category": category,
                            "section": doc.sections,
                            "status": "skipped",
                            "reason": (
                                f"Section not mapped: {doc.sections}"
                            ),
                        })

                        continue

                    base_filename = _build_filename(
                        doc,
                        file_doc,
                    )

                    folder_parts = [
                        NEW_SHAREPOINT_ROOT,
                        month_folder,
                        new_site,
                        *category_parts,
                    ]

                    selected_records.append({
                        "doc": doc,
                        "file_doc": file_doc,
                        "site": site,
                        "category": category,
                        "folder_parts": folder_parts,
                        "base_filename": base_filename,
                    })

                except Exception:

                    results["failed"] += 1

                    error = frappe.get_traceback()

                    results["details"].append({
                        "name": docname,
                        "site": site,
                        "category": category,
                        "status": "failed",
                        "reason": error,
                    })

                    frappe.log_error(
                        error,
                        "Engineering Legals monthly selection",
                    )

    # --------------------------------------------------------
    # 2. Detect records which would collapse onto one file.
    # --------------------------------------------------------

    grouped = {}

    for entry in selected_records:

        collision_key = (
            tuple(entry["folder_parts"]),
            entry["base_filename"].lower(),
        )

        grouped.setdefault(
            collision_key,
            [],
        ).append(entry)

    for entries in grouped.values():

        entries.sort(
            key=lambda item: item["doc"].name
        )

        for index, entry in enumerate(entries):

            if index == 0:
                entry["filename"] = (
                    entry["base_filename"]
                )
            else:
                entry["filename"] = (
                    _build_collision_filename(
                        entry["base_filename"],
                        entry["doc"].name,
                    )
                )

                results["collisions_resolved"] += 1

    # --------------------------------------------------------
    # 3. Plan or upload the exact selected records.
    # --------------------------------------------------------

    for entry in selected_records:

        doc = entry["doc"]

        try:
            outcome = _upload_to_month(
                doc=doc,
                month_folder=month_folder,
                drive_id=drive_id,
                token=token,
                dry_run=dry_run,
                filename_override=entry["filename"],
            )

            status = (
                outcome.get("status")
                or "failed"
            )

            if status in results:
                results[status] += 1
            else:
                results["failed"] += 1

            results["details"].append({
                "name": doc.name,
                "site": doc.site,
                "category": entry["category"],
                "section": doc.sections,
                "start_date": doc.start_date,
                "expiry_date": doc.expiry_date,
                "filename": entry["filename"],
                **outcome,
            })

            print(
                status.upper(),
                doc.name,
                outcome.get("destination")
                or outcome.get("reason")
                or "",
            )

        except Exception:

            results["failed"] += 1

            error = frappe.get_traceback()

            results["details"].append({
                "name": doc.name,
                "site": doc.site,
                "category": entry["category"],
                "status": "failed",
                "reason": error,
            })

            frappe.log_error(
                error,
                "Engineering Legals monthly SharePoint sync",
            )

            print(
                "FAILED",
                doc.name,
            )

    print()
    print("=== MONTHLY SHAREPOINT RECONCILIATION SUMMARY ===")
    print("Month:", results["month"])
    print("Dry run:", results["dry_run"])
    print("Dashboard selected:", results["selected"])
    print("Planned:", results["planned"])
    print("Uploaded:", results["uploaded"])
    print("Already existing:", results["existing"])
    print("Skipped:", results["skipped"])
    print("Failed:", results["failed"])
    print(
        "Filename collisions resolved:",
        results["collisions_resolved"],
    )

    return results


def run_current_month_frequency_sync():
    """
    Scheduled task.

    Runs for the current month and synchronizes the exact records
    represented by the Engineering Legals Monthly Summary.
    """
    return sync_active_legals_for_month(
        dry_run=False,
    )
