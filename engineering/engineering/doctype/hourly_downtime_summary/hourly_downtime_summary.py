# Copyright (c) 2026, Isambane Mining (Pty) Ltd
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document
from frappe.utils import now_datetime
from datetime import timedelta


SITE_CHANNELS = {
    "Koppie": "Isambane Mining-kop-hourly-downtime-reporting",
    "Kriel Rehabilitation": "Isambane Mining-krl-hourly-downtime-reporting",
    "Klipfontein": "Isambane Mining-klp-hourly-downtime-reporting",
    "Gwab": "Isambane Mining-gwb-hourly-downtime-reporting",
    "Bankfontein": "Isambane Mining-bnk-hourly-downtime-reporting",
    "Uitgevallen": "Isambane Mining-uit-hourly-downtime-reporting",
}


class HourlyDowntimeSummary(Document):
    def validate(self):
        if self.summary_message:
            self.summary_message = self.summary_message.strip()


def get_completed_hour_slot():
    now = now_datetime()

    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    previous_hour_start = current_hour_start - timedelta(hours=1)

    period_date = previous_hour_start.date()
    report_date = period_date

    if previous_hour_start.hour < 6:
        report_date -= timedelta(days=1)

    start_text = previous_hour_start.strftime("%H:00")
    end_text = (
        "24:00"
        if current_hour_start.hour == 0
        else current_hour_start.strftime("%H:00")
    )

    return report_date, f"{start_text}-{end_text}", period_date


def create_koppie_hourly_downtime_summary():
    return create_hourly_downtime_summary("Koppie")


def create_all_hourly_downtime_summaries():
    created = []

    for site in SITE_CHANNELS:
        try:
            created.append(create_hourly_downtime_summary(site))
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Hourly Downtime Summary failed for {site}"
            )

    return created

def create_hourly_downtime_summary(site):
    report_date, hour_slot, period_date = get_completed_hour_slot()
    channel_id = SITE_CHANNELS.get(site)

    if not channel_id:
        frappe.throw(f"No Raven channel configured for site: {site}")

    filters = {
        "report_date": str(period_date),
        "hour_slot": hour_slot,
        "site": site,
    }

    from engineering.engineering.report.hourly_downtime_report.hourly_downtime_report import execute

    columns, data = execute(filters)

    summary_message = build_summary_message(
        site=site,
        report_date=report_date,
        hour_slot=hour_slot,
        data=data,
    )

    doc = frappe.get_doc({
        "doctype": "Hourly Downtime Summary",
        "site": site,
        "report_date": report_date,
        "hour_slot": hour_slot,
        "channel_id": channel_id,
        "summary_message": summary_message,
        "report_data_json": json.dumps(data, default=str),
        "sent_to_raven": 0,
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


def build_summary_message(
    site,
    report_date,
    hour_slot,
    data,
):
    open_rows = [
        row for row in data
        if row.get("status_key") == "open"
    ]
    closed_rows = [
        row for row in data
        if row.get("status_key") == "closed"
    ]
    breakdown_rows = open_rows + closed_rows

    total = len(data)
    open_count = len(open_rows)
    closed_count = len(closed_rows)
    available_count = total - open_count

    lines = [
        f"{site.upper()} HOURLY BREAKDOWN REPORT",
        str(report_date),
        hour_slot.replace("-", " TO "),
        "",
    ]

    if not breakdown_rows:
        lines.extend([
            "No breakdown events for this hour.",
            "",
            f"Open at Hour End: {open_count}",
            f"Closed During Hour: {closed_count}",
            f"Available at Hour End: {available_count}",
            f"Fleet Total: {total}",
        ])
        return "\n".join(lines)

    grouped = {}

    for row in breakdown_rows:
        category = (
            row.get("category_group")
            or row.get("asset_category")
            or "OTHER"
        )
        grouped.setdefault(category, []).append(row)

    category_order = [
        "ADT",
        "Excavator",
        "Dozer",
        "Water Bowser",
        "Diesel Bowser",
        "Service Truck",
        "FEL",
        "Grader",
    ]

    for category in category_order:
        rows = grouped.get(category) or []

        if not rows:
            continue

        lines.append(category.upper())

        for row in rows:
            plant_no = row.get("plant_no") or "-"
            reason = row.get("reason") or "-"
            status = str(
                row.get("status_key") or ""
            ).upper()
            hours = float(row.get("open_hours") or 0)

            lines.append(
                f"{plant_no} - {status} - "
                f"{hours:.2f} HRS - "
                f"{str(reason).upper()}"
            )

        lines.append("")

    lines.extend([
        f"Open at Hour End: {open_count}",
        f"Closed During Hour: {closed_count}",
        f"Available at Hour End: {available_count}",
        f"Fleet Total: {total}",
    ])

    return "\n".join(lines)
