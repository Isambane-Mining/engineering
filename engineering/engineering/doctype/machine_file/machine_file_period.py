"""Read-only Machine File period views; saved summaries are never changed."""
from datetime import date
import re

import frappe
from frappe.utils import getdate


def parse_period(value):
    value = frappe.parse_json(value) if isinstance(value, str) else value
    value = value or {}
    if not isinstance(value, dict):
        frappe.throw("Invalid Machine File period.")
    dates = []
    for key in ("from_date", "to_date"):
        raw = value.get(key)
        if raw and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw)):
            frappe.throw("Period dates must use YYYY-MM-DD.")
        try:
            dates.append(date.fromisoformat(raw) if raw else None)
        except (ValueError, TypeError):
            frappe.throw("Invalid period date.")
    start, end = dates
    if start and end and start > end:
        frappe.throw("From Date cannot be after To Date.")
    months = value.get("months") or []
    if not isinstance(months, list):
        frappe.throw("Months must be a list.")
    for month in months:
        if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            frappe.throw("Invalid selected month.")
    return start, end, set(months)


def matches(value, period):
    start, end, months = period
    if not (start or end or months):
        return True
    if not value:
        return False
    day = getdate(value)
    return (not start or day >= start) and (not end or day <= end) and (
        not months or day.strftime("%Y-%m") in months
    )


def filter_rows(rows, period, field="date"):
    return [row for row in rows or [] if matches(row.get(field), period)]


def filter_breakdown(data, period):
    # The canonical A&U helper returns segments per reporting day (06:00-06:00).
    # Filter those segments, retaining its duration calculations unchanged.
    data["rows"] = filter_rows(data.get("rows"), period)
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
    from engineering.engineering.doctype.machine_file import machine_file as mf

    selected = parse_period(period)
    doc = frappe.get_doc("Machine File", name)
    doc.check_permission("read")
    sections = {}
    summary = []
    movement = None
    breakdown = None

    for index in doc.index_items or []:
        number = str(index.index_no)
        data = mf.get_machine_file_section_details(name, number)
        data["source_records"] = [
            row for row in data.get("source_records") or []
            if matches(row.get("start_date") if "start_date" in row else row.get("date"), selected)
        ]
        data["manual_documents"] = filter_rows(
            data.get("manual_documents"), selected, "document_date"
        )
        records = list(data["source_records"])
        if number == "1":
            movement = data.get("movement") or mf.get_machine_registration_movement(name)
            movement["rows"] = filter_rows(movement.get("rows"), selected)
            data["movement"] = movement
            records = list(movement["rows"])
        elif number == "11":
            breakdown = filter_breakdown(mf.get_machine_breakdown_log_summary(name), selected)
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
            status = mf._mf_engineering_legal_status(due) if due else "ERP Records"
        elif documents:
            latest = max(documents, key=lambda r: r.get("document_date") or "")
            due = latest.get("expiry_date") or None
            if due:
                status = mf._mf_engineering_legal_status(due)
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
