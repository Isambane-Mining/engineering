# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

"""Shared plumbing behind the "Fleet Card Transaction Import" doctype -
card resolution, Issues tracking, bulk Fleet Card Transaction creation, and
the Draft -> Missing Information -> Pending Import -> Importing ->
Partially Imported / Completed / Error async-submit lifecycle. Deliberately
modelled on is_attendance.controllers.clocking_import (the existing
reference pattern for this app) but simplified: that module's
auto-requeue-after-partial-fix and cross-document resync machinery exists
for ITS use case (large, frequent, often-concurrent unattended uploads
sharing the same unresolved employee codes) - a Fleet Card statement is a
manual, one-at-a-time, monthly upload, so resolving an Issue here just
means clicking "Start Import" again yourself; nothing propagates
automatically to other documents.

Format-specific PDF parsing lives separately in
engineering.controllers.fleet_card_import_parsers - this module doesn't
know or care which bank's statement produced the rows it's handling, only
their shared contract (see that module's own docstring for the exact row
shape)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime
from frappe.utils.file_manager import get_file

IMPORT_JOB_TIMEOUT = 30 * 60  # a 100+ page statement needs more than a web request allows, not an hour
RUN_IMPORT_JOB_PATH = "engineering.controllers.fleet_card_import.run_import_job"
STALL_THRESHOLD_MINUTES = IMPORT_JOB_TIMEOUT // 60 + 10
MAX_STALL_RECOVERY_ATTEMPTS = 3


def _normalize_card_number(value: str | None) -> str:
	"""Digits only, leading zeros stripped - the same physical card prints
	with a different number of leading zeros across this app's own two
	NedBank report sections (confirmed on real statements: "0008327445" on
	one page, "8327445" on another, for the same card), so comparison must
	tolerate that rather than require an exact string match."""
	if not value:
		return ""
	return "".join(ch for ch in value if ch.isdigit()).lstrip("0")


def resolve_fleet_card(row: dict, overrides: dict[str, str]) -> str | None:
	"""Which Fleet Card a parsed row belongs to. A manual Issue override
	(from a previous pass through this same document's Issues table) wins
	outright. Otherwise: NedBank rows carry the full card number, matched
	directly; Standard Bank masks everything but the last few digits, so
	those rows match via registration_number instead (unambiguous - a
	Fleet Card is issued against exactly one vehicle), with the masked
	suffix only as a tie-break if more than one submitted Fleet Card
	exists for that vehicle."""
	identifier = row.get("card_identifier")
	registration_number = row.get("registration_number")

	override_key = identifier or registration_number
	if override_key and overrides.get(override_key):
		return overrides[override_key]

	if registration_number:
		candidates = frappe.get_all(
			"Fleet Card",
			filters={"registration_number": registration_number, "docstatus": 1},
			fields=["name", "card_number"],
			order_by="issue_date desc",
		)
		if len(candidates) == 1:
			return candidates[0].name
		if len(candidates) > 1 and identifier:
			for candidate in candidates:
				if _normalize_card_number(candidate.card_number).endswith(_normalize_card_number(identifier)):
					return candidate.name
		if candidates:
			return candidates[0].name

	if identifier and len(identifier) >= 6:
		# Only a full (not masked-suffix) card number is specific enough
		# to match on its own, without a registration number to confirm it.
		normalized = _normalize_card_number(identifier)
		for candidate in frappe.get_all(
			"Fleet Card", filters={"docstatus": 1}, fields=["name", "card_number"], order_by="issue_date desc"
		):
			if _normalize_card_number(candidate.card_number) == normalized:
				return candidate.name

	return None


def rebuild_issues(doc, rows: list[dict]) -> None:
	overrides = {}
	for row in doc.issues:
		key = row.card_identifier
		if key and row.fleet_card:
			overrides[key] = row.fleet_card

	grouped: dict[str, dict] = {}
	for row in rows:
		key = row.get("card_identifier") or row.get("registration_number")
		if not key or resolve_fleet_card(row, overrides):
			continue
		entry = grouped.setdefault(
			key,
			{
				"card_identifier": row.get("card_identifier"),
				"registration_number": None,
				"count": 0,
				"first_seen": row["transaction_datetime"],
			},
		)
		entry["count"] += 1
		if row["transaction_datetime"] < entry["first_seen"]:
			entry["first_seen"] = row["transaction_datetime"]
		# A card's very first row or two (before its own Reg. No. label
		# line is reached) can carry no registration_number yet - prefer
		# any row in the group that actually has one, for a useful Issues
		# table, rather than whichever row happened to be seen first.
		if not entry["registration_number"] and row.get("registration_number"):
			entry["registration_number"] = row["registration_number"]

	previous_fleet_card_by_key = {row.card_identifier: row.fleet_card for row in doc.issues if row.fleet_card}

	doc.issues = []
	for key, entry in sorted(grouped.items()):
		doc.append(
			"issues",
			{
				"card_identifier": entry["card_identifier"],
				"registration_number": entry["registration_number"],
				"occurrence_count": entry["count"],
				"first_seen": entry["first_seen"],
				"fleet_card": previous_fleet_card_by_key.get(entry["card_identifier"]),
			},
		)


def refresh_readiness(doc, rows: list[dict]) -> bool:
	"""Rebuild the Issues table and row counts. Returns whether every row
	resolves (drives Pending Import/Completed, same as validate_import()
	below); resolvable_count (how many rows resolve right now, which may be
	fewer than all of them) is what lets queue_import() start a *partial*
	pass on a file that isn't fully resolved yet."""
	overrides = {row.card_identifier: row.fleet_card for row in doc.issues if row.fleet_card}

	rebuild_issues(doc, rows)

	resolvable = sum(1 for row in rows if resolve_fleet_card(row, overrides))

	doc.total_rows = len(rows)
	doc.unresolved_count = len(doc.issues)
	doc.unmatched_cards = ", ".join(sorted({i.card_identifier or i.registration_number or "" for i in doc.issues}))
	doc.resolvable_count = resolvable

	return not doc.issues


def validate_import(doc) -> None:
	if not doc.file:
		doc.issues = []
		doc.total_rows = 0
		doc.unresolved_count = 0
		doc.unmatched_cards = ""
		doc.status = "Not Parsed"
		return

	if doc.flags.get("_fleet_card_import_pipeline_active"):
		return

	rows = doc.parse_file()
	ready = refresh_readiness(doc, rows)
	doc.status = "Pending Import" if ready else "Missing Information"


def before_submit_guard(doc) -> None:
	if doc.status != "Completed":
		frappe.throw(
			_(
				'Run the import first ("Start Import") and wait for it to complete - this document '
				'can only be submitted once its Status is "Completed", not from here directly.'
			)
		)


def queue_import(doc) -> None:
	if doc.docstatus != 0:
		frappe.throw(_("This import has already been submitted."))

	if not doc.file:
		frappe.throw(_("Attach a file first."))

	rows = doc.parse_file()
	ready = refresh_readiness(doc, rows)

	if not ready and not doc.resolvable_count:
		frappe.throw(
			_(
				"None of the {0} card(s) in this file match a known Fleet Card yet - {1} unresolved. "
				"Resolve at least one in the Issues table first."
			).format(len(doc.issues), len(doc.issues))
		)

	doc.status = "Importing"
	doc.stall_recovery_attempts = 0
	doc.flags._fleet_card_import_pipeline_active = True
	doc.save()

	frappe.enqueue(
		RUN_IMPORT_JOB_PATH,
		queue="long",
		timeout=IMPORT_JOB_TIMEOUT,
		job_name=f"fleet_card_transaction_import_{doc.name}",
		docname=doc.name,
		enqueue_after_commit=True,
	)


def create_transactions(doc, rows: list[dict]) -> tuple[int, int, int]:
	"""Bulk-create Fleet Card Transactions for every row that doesn't
	already exist (idempotent - dedup key is fleet_card+transaction_datetime
	+amount, which is as unique as either source statement itself gets:
	neither prints a global transaction id that survives both formats).
	Returns (created, skipped, skipped_unresolved)."""
	overrides = {row.card_identifier: row.fleet_card for row in doc.issues if row.fleet_card}

	created = 0
	skipped = 0
	skipped_unresolved = 0

	for row in rows:
		fleet_card = resolve_fleet_card(row, overrides)
		if not fleet_card:
			skipped_unresolved += 1
			continue

		dedup_filters = {
			"fleet_card": fleet_card,
			"transaction_datetime": row["transaction_datetime"],
			"amount": row["amount"],
		}
		if frappe.db.exists("Fleet Card Transaction", dedup_filters):
			skipped += 1
			continue

		txn = frappe.get_doc(
			{
				"doctype": "Fleet Card Transaction",
				"fleet_card": fleet_card,
				"driver": _resolve_driver(row.get("driver_name_raw")),
				"transaction_type": row["transaction_type"],
				"transaction_datetime": row["transaction_datetime"],
				"merchant": row.get("merchant"),
				"town": row.get("town"),
				"litres": row.get("litres"),
				"odometer": row.get("odometer"),
				"amount": row["amount"],
				"vat_amount": row.get("vat_amount"),
				"document_number": row.get("document_number"),
				"source_reference": doc.name,
			}
		)
		txn.insert(ignore_permissions=True)
		txn.submit()
		doc.append("created_transactions", {"transaction": txn.name})
		created += 1

	return created, skipped, skipped_unresolved


def _resolve_driver(driver_name_raw: str | None) -> str | None:
	"""Best-effort only - an exact, case-insensitive match against
	Employee.employee_name. No fuzzy matching (unlike Clocking Import's
	employee resolution): a wrong silent match here would misattribute a
	real transaction to the wrong person, which is worse than leaving it
	blank for a human to fill in on the created Fleet Card Transaction."""
	if not driver_name_raw:
		return None

	match = frappe.db.get_value("Employee", {"employee_name": driver_name_raw, "status": "Active"}, "name")
	return match or None


def run_import_job(docname: str) -> None:
	doc = frappe.get_doc("Fleet Card Transaction Import", docname)
	doc.flags._fleet_card_import_pipeline_active = True

	try:
		rows = doc.parse_file()
		created, skipped, skipped_unresolved = create_transactions(doc, rows)

		fully_done = not doc.issues

		log_lines = [
			f"Detected format: {doc.detected_format}",
			f"Rows in file: {len(rows)}",
			f"Transactions created: {created}",
			f"Rows already imported (skipped): {skipped}",
		]
		if skipped_unresolved:
			log_lines.append(f"Rows still blocked (unresolved card): {skipped_unresolved}")
		doc.import_log = "\n".join(log_lines)

		if fully_done:
			doc.status = "Completed"
			doc.save(ignore_permissions=True)
			doc.submit()
		else:
			doc.status = "Partially Imported"
			doc.save(ignore_permissions=True)
			frappe.db.commit()
	except Exception as error:
		frappe.db.rollback()

		if isinstance(error, (frappe.QueryDeadlockError, frappe.QueryTimeoutError)):
			raise frappe.RetryBackgroundJobError from error

		doc.reload()
		doc.flags._fleet_card_import_pipeline_active = True
		doc.status = "Error"
		doc.import_log = frappe.get_traceback()
		doc.save(ignore_permissions=True)
		frappe.db.commit()


def recover_stalled_imports() -> dict:
	"""Scheduled watchdog (see hooks.py scheduler_events) - same reasoning
	as is_attendance's recover_stalled_imports(): a document still at
	"Importing" well past IMPORT_JOB_TIMEOUT cannot possibly be legitimate
	work still in progress (RQ itself kills anything running longer), so
	it's re-queued; a document that stalls MAX_STALL_RECOVERY_ATTEMPTS
	times in a row is flipped to "Error" instead, for a person to look at."""
	threshold = add_to_date(now_datetime(), minutes=-STALL_THRESHOLD_MINUTES, as_string=False)

	recovered = []
	escalated = []

	stalled = frappe.get_all(
		"Fleet Card Transaction Import",
		filters={"status": "Importing", "modified": ["<", threshold]},
		fields=["name", "stall_recovery_attempts"],
	)

	for row in stalled:
		attempts = row.stall_recovery_attempts or 0

		if attempts >= MAX_STALL_RECOVERY_ATTEMPTS:
			existing_log = frappe.db.get_value("Fleet Card Transaction Import", row.name, "import_log") or ""
			frappe.db.set_value(
				"Fleet Card Transaction Import",
				row.name,
				{
					"status": "Error",
					"import_log": (
						existing_log
						+ f"\n\n{now_datetime()}: auto-recovery gave up after {attempts} stalled attempt(s) "
						'in a row - needs a person to look at this. Fix whatever\'s blocking it, then '
						'click "Start Import" to retry.'
					),
				},
			)
			frappe.db.commit()
			escalated.append(row.name)
			continue

		frappe.db.set_value("Fleet Card Transaction Import", row.name, "stall_recovery_attempts", attempts + 1)
		frappe.db.commit()

		frappe.enqueue(
			RUN_IMPORT_JOB_PATH,
			queue="long",
			timeout=IMPORT_JOB_TIMEOUT,
			job_name=f"fleet_card_transaction_import_stall_recovery_{row.name}_{frappe.generate_hash(length=8)}",
			docname=row.name,
		)
		recovered.append(row.name)

	return {"recovered": recovered, "escalated": escalated}


def cancel_import(doc) -> None:
	for row in doc.created_transactions or []:
		if not row.transaction or not frappe.db.exists("Fleet Card Transaction", row.transaction):
			continue
		txn = frappe.get_doc("Fleet Card Transaction", row.transaction)
		if txn.docstatus == 1:
			txn.cancel()
		frappe.delete_doc("Fleet Card Transaction", row.transaction, ignore_permissions=True, force=True)
