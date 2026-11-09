import frappe
from collections import defaultdict
from frappe.utils import nowdate



def get_deviation_recipient_emails(site):
    """Return configured Pre-Use Deviation recipients for one site."""
    settings = frappe.get_single("Pre Use Deviation Settings")
    recipients = []
    seen = set()

    for row in settings.get("recipients_per_site") or []:
        if (row.location or "").strip() != (site or "").strip():
            continue

        user = (row.user or "").strip()
        if not user:
            continue

        email = frappe.db.get_value("User", user, "email") or user
        email = (email or "").strip()

        if not email or email.lower() in seen:
            continue

        seen.add(email.lower())
        recipients.append(email)

    return recipients


def send_open_deviation_emails():
    deviations = frappe.get_all(
        "Pre Use Deviation",
        filters={"action_status": "Open"},
        fields=[
            "name",
            "site",
            "report_datetime",
            "deviation_details",
            "fleet_number",
            "machine_type",
            "machine_model",
            "pre_use_no",
            "reported_by_name_and_surname",
            "action_status",
        ],
        order_by="site asc, report_datetime asc",
    )

    if not deviations:
        frappe.log_error("No open deviations found", "Open Deviation Email Job")
        return

    grouped = defaultdict(list)
    for row in deviations:
        site = row.get("site")
        if site:
            grouped[site].append(row)

    for site, rows in grouped.items():
        recipients = get_deviation_recipient_emails(site)
        if not recipients:
            continue

        frappe.sendmail(
            recipients=list(set(recipients)),
            subject=f"Open Pre Use Deviations - {site} - {nowdate()}",
            message=build_email_table(site, rows),
        )


def build_email_table(site, rows):
    html_rows = ""

    for d in rows:
        html_rows += f"""
        <tr>
            <td>{d.get('name', '')}</td>
            <td>{d.get('pre_use_no', '')}</td>
            <td>{d.get('report_datetime', '')}</td>
            <td>{d.get('fleet_number', '')}</td>
            <td>{d.get('machine_type', '')}</td>
            <td>{d.get('machine_model', '')}</td>
            <td>{d.get('reported_by_name_and_surname', '')}</td>
            <td>{d.get('deviation_details', '')}</td>
            <td>{d.get('action_status', '')}</td>
        </tr>
        """

    return f"""
    <p>Good day,</p>
    <p>Please find below all <b>Open Pre Use Deviations</b> for <b>{site}</b>.</p>

    <table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse; width:100%;">
        <thead>
            <tr>
                <th>ID</th>
                <th>Pre-Use No.</th>
                <th>Reported At</th>
                <th>Fleet Number</th>
                <th>Machine Type</th>
                <th>Machine Model</th>
                <th>Reported By</th>
                <th>Deviation Details</th>
                <th>Action Status</th>
            </tr>
        </thead>
        <tbody>
            {html_rows}
        </tbody>
    </table>

    <p>Regards<br>Isambane System</p>
    """