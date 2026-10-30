import re
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime, time_diff_in_hours, add_days


class WhatsAppBreakdownMessageLog(Document):
    def validate(self):
        parse_whatsapp_breakdown_message(self)


def parse_time_to_erp(value):
    if not value:
        return None

    value = str(value).strip().lower()
    value = value.replace(" ", "")

    match = re.search(r"(\d{1,2})[:hH]?(\d{2})", value)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if hour < 0 or hour > 23:
        return None

    if minute < 0 or minute > 59:
        return None

    return f"{hour:02d}:{minute:02d}:00"


def clean_line(line):
    return str(line or "").strip()


def is_review_only_message(text):
    text_lower = (text or "").lower().strip()

    if not text_lower:
        return True

    # Clear book-back messages must still be processed.
    if re.search(r"\b(book\s*back|bookback|booked back)\b", text_lower):
        return False

    # Clear book-down messages must still be processed.
    if re.search(r"\b(book\s*down|bookdown|booked down)\b", text_lower):
        return False

    review_phrases = [
        "incident report",
        "waiting for the incident report",
        "need an incident report",
        "standing till tomorrow",
        "will be standing",
        "remove",
        "add",
        "add is",
        "add machine",
        "add dozer",
        "from gwab list",
        "from the list",
        "to our list",
        "change the comment",
        "remove the comment",
        "please share km",
        "share km",
        "km readings",
        "can we please have hours",
        "please have hours",
        "which one",
        "working ?",
        "working?",
        "fixed?",
        "feedback",
        "who is attending",
        "who's attending",
        "offsite change",
        "off site change",
        "no breakdowns",
        "back to production",
        "power off",
        "electricity",
        "please note",
        "pls note",
        "please arrange",
        "arrange a diesel bowser",
        "must go to hino",
        "hino for service",
    ]

    for phrase in review_phrases:
        if phrase in text_lower:
            return True

    # Questions about a machine are review unless they are clear book-back/book-down.
    if "?" in text_lower:
        return True

    # Status report style line, for example:
    # ❌IS0611 *LHS No side mirror*
    # This is a status/list item, not necessarily a new breakdown booking.
    if re.search(r"^[✅❌🚫]\s*(is|ex)\s*\d{2,4}", text_lower, re.IGNORECASE):
        return True

    return False


def get_shift_from_datetime(dt):
    dt = get_datetime(dt or now_datetime())
    hour = dt.hour

    if 6 <= hour < 18:
        return "Day Shift"

    return "Night Shift"


def combine_date_and_time(base_dt, time_value):
    base_dt = get_datetime(base_dt or now_datetime())

    if not time_value:
        return base_dt

    time_text = str(time_value)
    hour, minute, second = [int(x) for x in time_text.split(":")]

    return base_dt.replace(hour=hour, minute=minute, second=second, microsecond=0)


def infer_site_from_group(group_name):
    group_name = (group_name or "").lower()

    site_map = {
        "kriel": "Kriel Rehabilitation",
        "krr": "Kriel Rehabilitation",
        "klip": "Klipfontein",
        "gwab": "Gwab",
        "koppie": "Koppie",
        "uit": "Uitgevallen",
        "bank": "Bankfontein",
        "bnk": "Bankfontein",
    }

    for key, site in site_map.items():
        if key in group_name:
            return site

    return None



def is_review_only_message(text):
    text = text or ""
    lower = text.lower().strip()

    # These are proper Book Back messages. Do not send them to review.
    if any(x in lower for x in [
        "book back",
        "bookback",
        "booked back",
        "please book back",
    ]):
        return False

    # These are proper Book Down messages. Do not send them to review.
    if any(x in lower for x in [
        "book down",
        "bookdown",
        "booked down",
        "stop:",
        "stopped",
    ]):
        return False

    review_phrases = [
        "incident report",
        "waiting for the incident report",
        "need an incident report",
        "write the incident report",
        "standing till tomorrow",
        "will be standing",
        "please remove",
        "pls remove",
        "remove the comment",
        "change the comment",
        "please add",
        "pls add",
        "from gwab list",
        "from the list",
        "to our list",
        "please share km",
        "share km",
        "km readings",
        "can we please have hours",
        "please have hours",
        "which one",
        "feedback",
        "who is attending",
        "who's attending",
        "offsite change",
        "off site change",
        "no breakdowns",
        "back to production",
        "power off",
        "electricity",
        "please note",
        "pls note",
        "please arrange",
        "arrange a diesel bowser",
        "must go to hino",
        "hino for service",
        "yes all",
        "moved this morning",
        "not on the report",
    ]

    if any(phrase in lower for phrase in review_phrases):
        return True

    if "?" in lower:
        return True

    if lower in ["yes", "no", "nope", "thanks", "ps"]:
        return True

    if re.match(r"^[✅❌🚫]\s*(is|ex)\s*0*\d{2,4}", lower, re.IGNORECASE):
        return True

    return False


def parse_whatsapp_breakdown_message(doc):
    raw_message = clean_line(doc.raw_message)

    if not raw_message:
        doc.status = "Needs Review"
        doc.error_message = "Raw Message is empty."
        return

    if not doc.message_datetime:
        doc.message_datetime = now_datetime()

    if not doc.target_shift:
        doc.target_shift = get_shift_from_datetime(doc.message_datetime)

    if not doc.target_site:
        doc.target_site = infer_site_from_group(doc.group_name)

    text = raw_message.strip()

    # Allow manual test format:
    # Group Name: Kriel Control Room Room
    # Raw Message: IS570 Faulty emergency stop button
    manual_group_match = re.search(r"^group name\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if manual_group_match and not doc.group_name:
        doc.group_name = manual_group_match.group(1).strip()

    manual_raw_match = re.search(r"^raw message\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if manual_raw_match:
        text = manual_raw_match.group(1).strip()

    text_lower = text.lower()

    doc.detected_plant_no = None
    doc.detected_action = None
    doc.detected_start_time = None
    doc.detected_book_back_time = None
    doc.detected_hours = None
    doc.detected_reason = None
    doc.detected_resolution = None
    doc.error_message = None

    plant_match = re.search(r"\b(IS|EX)\s*0*(\d{2,4})\b", text, re.IGNORECASE)
    if plant_match:
        prefix = plant_match.group(1).upper()
        number = plant_match.group(2)
        doc.detected_plant_no = f"{prefix}{number}"
    else:
        doc.detected_action = "Unknown"
        doc.status = "Needs Review"
        doc.error_message = "Could not detect plant number like IS570 or EX230."
        return

    if is_review_only_message(text):
        doc.detected_action = "Unknown"
        doc.status = "Needs Review"
        doc.error_message = "Message mentions a machine, but is not a clear Book Down or Book Back message."
        return

    start_match = re.search(
        r"\b(stop|start|stopped|breakdown start|bd start|booked down|book down|down)\b\s*[:@\-]?\s*(\d{1,2}[:hH]?\d{2})",
        text,
        re.IGNORECASE,
    )
    if start_match:
        doc.detected_start_time = parse_time_to_erp(start_match.group(2))

    book_back_match = re.search(
        r"\b(book\s*back|bookback|booked back|back|return|returned)\b\s*[:@\-]?\s*(\d{1,2}[:hH]?\d{2})",
        text,
        re.IGNORECASE,
    )
    if book_back_match:
        doc.detected_book_back_time = parse_time_to_erp(book_back_match.group(2))

    hours_match = re.search(
        r"\b(smr|hrs|hours|hour)\b\s*[:\-]?\s*(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if hours_match:
        doc.detected_hours = float(hours_match.group(2))

    if doc.detected_book_back_time or "book back" in text_lower or "bookback" in text_lower:
        doc.detected_action = "Book Back"
    else:
        doc.detected_action = "Book Down"

    lines = [clean_line(line) for line in text.splitlines() if clean_line(line)]

    if doc.detected_action == "Book Down":
        reason = re.sub(r"\b(IS|EX)\s*0*\d{2,4}\b", "", text, flags=re.IGNORECASE).strip()
        reason = re.sub(r"^[:\-\s]+", "", reason).strip()

        if reason:
            doc.detected_reason = reason
            doc.status = "Parsed"
        else:
            doc.status = "Needs Review"
            doc.error_message = "Book Down detected, but no breakdown reason found."

    elif doc.detected_action == "Book Back":
        resolution_lines = []

        for line in lines:
            line_lower = line.lower()

            if line_lower.strip() in ["edited", "(edited)"]:
                continue

            if re.fullmatch(r"(IS|EX)\s*0*\d{2,4}", line, flags=re.IGNORECASE):
                continue

            if re.search(r"^(stop|start|stopped|breakdown start|bd start|booked down|book down|down)\b\s*[:@\-]?\s*\d{1,2}[:hH]?\d{2}", line_lower):
                continue

            if re.search(r"^(please\s+)?(book\s*back|bookback|booked back|back|return|returned)\b", line_lower):
                continue

            if re.search(r"^(smr|hrs|hours|hour)\b\s*[:\-]?\s*\d+(?:\.\d+)?\s*$", line_lower):
                continue

            resolution_lines.append(line)

        if resolution_lines:
            doc.detected_resolution = "\n".join(resolution_lines).strip()

        doc.status = "Parsed"

    else:
        doc.status = "Needs Review"
        doc.error_message = "Could not detect action."


@frappe.whitelist()
def create_or_update_breakdown(log_name, problem_category=None):
    log = frappe.get_doc("WhatsApp Breakdown Message Log", log_name)
    log.check_permission("read")

    if log.status not in ["Parsed", "Created Breakdown", "Updated Breakdown"]:
        frappe.throw(f"Message must be Parsed before creating/updating breakdown. Current status: {log.status}")

    if not log.detected_plant_no:
        frappe.throw("Detected Plant No is missing.")

    if not log.detected_action:
        frappe.throw("Detected Action is missing.")

    if not log.target_site:
        frappe.throw("Site is missing on the WhatsApp log. Please select Site first.")

    if not log.target_shift:
        log.target_shift = get_shift_from_datetime(log.message_datetime)

    if log.detected_action == "Book Down":
        return create_breakdown_from_log(log, problem_category=problem_category)

    if log.detected_action == "Book Back":
        return update_breakdown_from_log(log)

    frappe.throw(f"Unsupported action: {log.detected_action}")


@frappe.whitelist()
def requires_breakdown_category(log_name):
    """Let capture UI reuse the server's existing maintenance determination."""
    log = frappe.get_doc('WhatsApp Breakdown Message Log', log_name)
    log.check_permission('read')
    return log.detected_action == 'Book Down' and get_downtime_type_from_log(log) == 'Breakdown'


def get_downtime_type_from_log(log):
    text = f"{log.raw_message or ''} {log.detected_reason or ''} {log.detected_resolution or ''}".lower()

    planned_words = [
        "service",
        "servicing",
        "maintenance",
        "planned maintenance",
        "pm",
    ]

    for word in planned_words:
        if word in text:
            return "Planned Maintenance"

    return "Breakdown"


def create_breakdown_from_log(log, problem_category=None):
    start_dt = combine_date_and_time(
        log.message_datetime,
        log.detected_start_time,
    )

    breakdown = frappe.new_doc("Plant Breakdown or Maintenance")
    breakdown.location = log.target_site
    breakdown.shift = log.target_shift
    breakdown.downtime_type = get_downtime_type_from_log(log)
    if breakdown.downtime_type == 'Breakdown':
        from engineering.engineering.problem_categories import validate_problem_category
        try:
            validate_problem_category(problem_category, is_new=True)
        except ValueError as exc:
            frappe.throw(str(exc))
        breakdown.problem_category = problem_category
    breakdown.asset_name = log.detected_plant_no
    breakdown.breakdown_start_datetime = start_dt
    breakdown.breakdown_reason = log.detected_reason or log.raw_message
    breakdown.open_closed = "Open"

    if log.detected_hours:
        breakdown.hours_breakdown_starts = log.detected_hours
    else:
        breakdown.hours_breakdown_starts = 0

    breakdown.insert()

    log.linked_breakdown = breakdown.name
    log.status = "Created Breakdown"
    log.error_message = None
    log.save(ignore_permissions=True)

    frappe.db.commit()

    return {
        "status": "Created Breakdown",
        "breakdown": breakdown.name,
    }


def update_breakdown_from_log(log):
    filters = {
        "asset_name": log.detected_plant_no,
        "open_closed": "Open",
        "location": log.target_site,
    }

    open_records = frappe.get_all(
        "Plant Breakdown or Maintenance",
        filters=filters,
        fields=["name", "breakdown_start_datetime"],
        order_by="creation desc",
        limit=2,
    )

    if not open_records:
        log.status = "Needs Review"
        log.error_message = f"No open breakdown found for {log.detected_plant_no} at {log.target_site}."
        log.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw(log.error_message)

    if len(open_records) > 1:
        log.status = "Needs Review"
        log.error_message = f"More than one open breakdown found for {log.detected_plant_no} at {log.target_site}."
        log.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw(log.error_message)

    breakdown = frappe.get_doc("Plant Breakdown or Maintenance", open_records[0].name)

    start_dt = None
    if log.detected_start_time:
        start_dt = combine_date_and_time(log.message_datetime, log.detected_start_time)
        breakdown.breakdown_start_datetime = start_dt
    elif breakdown.breakdown_start_datetime:
        start_dt = get_datetime(breakdown.breakdown_start_datetime)

    resolved_dt = None
    if log.detected_book_back_time:
        resolved_dt = combine_date_and_time(log.message_datetime, log.detected_book_back_time)

        if start_dt and resolved_dt < start_dt:
            resolved_dt = add_days(resolved_dt, 1)

        breakdown.resolved_datetime = resolved_dt

    if log.detected_hours:
        breakdown.hours_breakdown_starts = log.detected_hours

    if log.detected_resolution:
        breakdown.resolution_summary = log.detected_resolution

    if start_dt and resolved_dt:
        breakdown.breakdown_hours = time_diff_in_hours(resolved_dt, start_dt)

    breakdown.open_closed = "Closed"
    breakdown.save(ignore_permissions=True)

    log.linked_breakdown = breakdown.name
    log.status = "Updated Breakdown"
    log.error_message = None
    log.save(ignore_permissions=True)

    frappe.db.commit()

    return {
        "status": "Updated Breakdown",
        "breakdown": breakdown.name,
    }
