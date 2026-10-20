import frappe
from frappe import _
from frappe.utils import getdate

from engineering.engineering.report.down_time.down_time import get_data
from engineering.engineering.page.downtime_correction_dashboard.downtime_correction_dashboard import (
    check_site_access,
)


VERIFICATION_ROLES = {
    "Engineering": (
        "Engineering Manager",
        "Engineering Foreman",
    ),
    "Production": (
        "Production Manager",
        "Production Foreman",
    ),
}


def check_verification_permission(department, site):
    if department not in VERIFICATION_ROLES:
        frappe.throw(_("Invalid verification department."))

    user = frappe.session.user

    if user == "Guest":
        frappe.throw(
            _("Please log in to verify downtime."),
            frappe.PermissionError,
        )

    user_roles = set(frappe.get_roles(user))

    engineering_roles = set(VERIFICATION_ROLES["Engineering"])
    production_roles = set(VERIFICATION_ROLES["Production"])

    # Ordinary verification users may act for one department only.
    if (
        user != "Administrator"
        and user_roles & engineering_roles
        and user_roles & production_roles
    ):
        frappe.throw(
            _("Conflicting downtime verification roles are assigned."),
            frappe.PermissionError,
        )

    matched = [
        role for role in VERIFICATION_ROLES[department]
        if role in user_roles
    ]

    if not matched:
        frappe.throw(
            _("You do not have permission to verify {0} downtime.").format(
                department
            ),
            frappe.PermissionError,
        )

    # Preserve the existing administrative site-access policy.
    if (
        user != "Administrator"
        and "System Manager" not in user_roles
    ):
        allowed_sites = set(
            frappe.get_all(
                "User Permission",
                filters={
                    "user": user,
                    "allow": "Location",
                },
                pluck="for_value",
            )
        )

        if site not in allowed_sites:
            frappe.throw(
                _("You do not have permission to verify downtime at this site."),
                frappe.PermissionError,
            )

    check_site_access(site)

    return matched[0]


def get_scope(report_date, site, shift):
    if not site or not frappe.db.exists("Location", site):
        frappe.throw(_("Please select a valid Site."))

    if not report_date:
        frappe.throw(_("Please select a report date."))

    date = getdate(report_date)

    if date > getdate(frappe.utils.today()):
        frappe.throw(_("Future report dates cannot be verified."))

    shift = shift or ""

    if shift not in ("", "Day Shift", "Night Shift"):
        frappe.throw(_("Invalid report shift."))

    return date, site, shift, shift or "All Shifts"


def get_required_records(report_date, site, shift):
    # Deliberately exclude the Asset Category filter.
    # Every applicable downtime record must count toward completion.
    rows = get_data({
        "report_date": report_date,
        "site": site,
        "shift": shift,
    })

    return {
        str(row["breakdown_docname"]): row
        for row in rows
        if row.get("breakdown_docname")
    }


def get_parent(site, report_date, report_shift):
    names = frappe.get_all(
        "Mechanical Downtime sign-off",
        filters={
            "site": site,
            "report_date": report_date,
            "report_shift": report_shift,
        },
        pluck="name",
        limit_page_length=2,
    )

    if len(names) > 1:
        frappe.throw(_("Multiple downtime sign-offs found for this period."))

    if not names:
        return None

    return frappe.get_doc("Mechanical Downtime sign-off", names[0])


def get_verified_ids(parent, department):
    if not parent:
        return set()

    return {
        row.downtime_record
        for row in parent.get("downtime_verifications") or []
        if row.department == department
        and row.verification_status == "Verified"
    }


def build_summary(parent, required):
    result = {}

    for department in ("Production", "Engineering"):
        verified_ids = get_verified_ids(parent, department)
        completed = len(set(required) & verified_ids)
        total = len(required)

        result[department] = {
            "verified": completed,
            "total": total,
            "outstanding": total - completed,
            "status": "Closed" if total > 0 and completed == total else "Open",
        }

    result["overall_status"] = (
        "Closed"
        if result["Production"]["status"] == "Closed"
        and result["Engineering"]["status"] == "Closed"
        else "Open"
    )

    return result


@frappe.whitelist()
def get_downtime_verification_summary(
    report_date,
    site,
    shift="",
    department="Engineering",
):
    report_date, site, shift, report_shift = get_scope(
        report_date, site, shift
    )

    check_verification_permission(department, site)

    required = get_required_records(report_date, site, shift)
    parent = get_parent(site, report_date, report_shift)

    # Existing historical sign-offs must not be silently converted.
    legacy = bool(
        parent and int(parent.get("verification_workflow_version") or 0) == 0
    )

    if legacy:
        return {
            "historical_workflow": True,
            "department": department,
            "summary": None,
            "outstanding_records": [],
            "message": _(
                "This period uses the previous electronic sign-off workflow."
            ),
        }

    summary = build_summary(parent, required)

    summary["stored_status"] = parent.status if parent else "Open"
    summary["status_outdated"] = bool(
        parent and parent.status != summary["overall_status"]
    )

    verified_ids = get_verified_ids(parent, department)

    outstanding_records = [
        {
            "downtime_record": record_id,
            "plant_no": row.get("plant_no"),
            "breakdown_reason": row.get("breakdown_reason"),
        }
        for record_id, row in required.items()
        if record_id not in verified_ids
    ]

    all_records = []

    for record_id, row in required.items():
        item = dict(row)
        item["downtime_record"] = record_id
        item["verification_status"] = (
            "Verified" if record_id in verified_ids
            else "Not Verified"
        )
        all_records.append(item)

    return {
        "summary": summary,
        "outstanding_records": outstanding_records,
        "all_records": all_records,
        "historical_workflow": False,
        "department": department,
    }


@frappe.whitelist(methods=["POST"])
def submit_downtime_verifications(
    report_date,
    site,
    shift,
    department,
    verifications,
):
    import hashlib

    report_date, site, shift, report_shift = get_scope(
        report_date, site, shift
    )
    role = check_verification_permission(department, site)

    if isinstance(verifications, str):
        verifications = frappe.parse_json(verifications)

    if not isinstance(verifications, list) or not verifications:
        frappe.throw(_("Select at least one downtime record."))

    if len(verifications) > 1000:
        frappe.throw(_("Too many verification entries."))

    identity = f"{site}|{report_date}|{report_shift}"
    lock_name = "dt-signoff:" + hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:40]

    acquired = frappe.db.sql(
        "SELECT GET_LOCK(%s, %s)",
        (lock_name, 15),
    )

    if not acquired or acquired[0][0] != 1:
        frappe.throw(
            _("Another user is processing this sign-off. Try again.")
        )

    try:
        result = _submit_downtime_verifications(
            report_date,
            site,
            shift,
            report_shift,
            department,
            role,
            verifications,
        )
        frappe.db.commit()
        return result
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.db.sql(
            "SELECT RELEASE_LOCK(%s)",
            (lock_name,),
        )


def _submit_downtime_verifications(
    report_date,
    site,
    shift,
    report_shift,
    department,
    role,
    verifications,
):
    from frappe.utils import now_datetime

    required = get_required_records(report_date, site, shift)

    if not required:
        frappe.throw(_("No downtime records found for this period."))

    seen = set()
    prepared = []

    for item in verifications:
        if not isinstance(item, dict):
            frappe.throw(_("Invalid verification entry."))

        record_id = str(item.get("downtime_record") or "").strip()
        status = str(item.get("verification_status") or "").strip()
        comments = str(item.get("comments") or "").strip()

        if record_id not in required:
            frappe.throw(
                _("Downtime record is outside the selected reporting period.")
            )

        if record_id in seen:
            frappe.throw(_("Duplicate downtime record in submission."))

        if status not in ("Verified", "Not Verified"):
            frappe.throw(_("Invalid verification status."))

        if len(comments) > 1000:
            frappe.throw(_("Verification comment is too long."))

        seen.add(record_id)
        prepared.append((record_id, status, comments))

    parent = get_parent(site, report_date, report_shift)

    if parent:
        version = int(parent.get("verification_workflow_version") or 0)

        if version != 1:
            frappe.throw(
                _(
                    "This period uses the previous sign-off workflow. "
                    "Existing approvals must not be converted automatically."
                )
            )
    else:
        parent = frappe.new_doc("Mechanical Downtime sign-off")
        parent.site = site
        parent.report_date = report_date
        parent.report_shift = report_shift
        parent.status = "Open"
        parent.verification_workflow_version = 1

        flag = "_mechanical_dt_verification_create"
        previous_flag = frappe.flags.get(flag)

        try:
            parent.set_new_name()
            frappe.flags[flag] = parent.name
            parent.insert(ignore_permissions=True)
        finally:
            if previous_flag is None:
                frappe.flags.pop(flag, None)
            else:
                frappe.flags[flag] = previous_flag

    already_verified = get_verified_ids(parent, department)

    # The server determines the full outstanding set under the
    # submission lock. A client cannot submit a partial batch.
    outstanding_ids = set(required) - already_verified
    submitted_ids = {record_id for record_id, _, _ in prepared}

    if not outstanding_ids:
        frappe.throw(
            _("All downtime records are already verified for this department.")
        )

    if submitted_ids != outstanding_ids:
        frappe.throw(
            _(
                "Every outstanding downtime record must have a "
                "Verified or Not Verified decision. Refresh the "
                "report and try again."
            )
        )

    for record_id, status, comments in prepared:
        if record_id in already_verified:
            frappe.throw(
                _("Downtime record {0} is already verified.").format(
                    record_id
                )
            )

        parent.append("downtime_verifications", {
            "downtime_record": record_id,
            "department": department,
            "verification_status": status,
            "verified_by": frappe.session.user,
            "verified_on": now_datetime(),
            "verification_role": role,
            "comments": comments,
        })

    summary = reconcile_verification_status(parent, required)

    flag = "_mechanical_dt_verification_append"
    previous_flag = frappe.flags.get(flag)

    try:
        frappe.flags[flag] = (parent.name, department)
        parent.save(ignore_permissions=True)
    finally:
        if previous_flag is None:
            frappe.flags.pop(flag, None)
        else:
            frappe.flags[flag] = previous_flag

    return {
        "message": _("Downtime verification submitted."),
        "summary": summary,
        "department": department,
        "submitted": len(prepared),
    }


def reconcile_verification_status(parent, required):
    """Calculate the status from the complete set of downtime records."""
    if int(parent.get("verification_workflow_version") or 0) != 1:
        frappe.throw(
            _("Historical sign-offs cannot use verification reconciliation.")
        )

    summary = build_summary(parent, required)
    parent.status = summary["overall_status"]

    return summary


def reconcile_signoffs_after_breakdown_change(doc, previous=None):
    """Refresh existing version-1 sign-offs affected by a breakdown change.

    No verification history is added, removed or edited. Historical
    workflow-0 documents remain untouched.
    """
    from datetime import timedelta
    from frappe.utils import get_datetime

    # Only changes affecting breakdown membership require reconciliation.
    def membership_signature(record):
        if record is None:
            return None

        start = (
            record.get("breakdown_start_datetime")
            or record.get("creation")
        )

        return (
            record.get("location") or "",
            str(start or ""),
            str(record.get("resolved_datetime") or ""),
        )

    if (
        previous is not None
        and membership_signature(doc) == membership_signature(previous)
    ):
        return 0

    affected_sites = set()
    starts = []
    resolved_ends = []
    has_open_interval = False

    for record in (doc, previous):
        if not record:
            continue

        site = record.get("location")
        if site:
            affected_sites.add(site)

        start = (
            record.get("breakdown_start_datetime")
            or record.get("creation")
        )
        if start:
            starts.append(get_datetime(start))

        resolved = record.get("resolved_datetime")

        if resolved:
            resolved_ends.append(get_datetime(resolved))
        else:
            has_open_interval = True

    if not affected_sites:
        return 0

    # Include the preceding calendar date because a Night Shift
    # extends into the following morning.
    earliest_date = (
        min(starts).date() - timedelta(days=1)
        if starts else None
    )

    # An open breakdown can affect later shifts indefinitely.
    # Bound only when both previous and current intervals are closed.
    latest_date = (
        max(resolved_ends).date()
        if resolved_ends and not has_open_interval
        else None
    )

    updated = 0

    for site in sorted(affected_sites):
        filters = {
            "site": site,
            "verification_workflow_version": 1,
        }
        if earliest_date and latest_date:
            filters["report_date"] = [
                "between",
                [earliest_date, latest_date],
            ]
        elif earliest_date:
            filters["report_date"] = [">=", earliest_date]

        signoffs = frappe.get_all(
            "Mechanical Downtime sign-off",
            filters=filters,
            fields=["name", "report_date", "report_shift", "status"],
            order_by="report_date asc",
        )

        for signoff in signoffs:
            shift = (
                ""
                if signoff.report_shift == "All Shifts"
                else signoff.report_shift
            )

            required = get_required_records(
                signoff.report_date,
                site,
                shift,
            )

            parent = frappe.get_doc(
                "Mechanical Downtime sign-off",
                signoff.name,
            )

            expected = build_summary(
                parent,
                required,
            )["overall_status"]

            if signoff.status == expected:
                continue

            # Only update the calculated field. This deliberately
            # does not alter any historical verification entries.
            frappe.db.set_value(
                "Mechanical Downtime sign-off",
                signoff.name,
                "status",
                expected,
                update_modified=False,
            )
            updated += 1

    return updated
