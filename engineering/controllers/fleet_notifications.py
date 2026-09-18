# Copyright (c) 2026, buff0k and contributors
# For license information, please see license.txt

import frappe

from engineering.controllers.fleet_compliance import bulk_drivers, compute_all, get_expiring_threshold_days
from engineering.controllers.notifications import _get_outgoing_email_account
from engineering.engineering.doctype.fleet_management_settings.fleet_management_settings import (
	get_reportable_asset_names,
)

ATTENTION_STATUSES = ["Attention Required", "Non-Compliant"]

# Used as the by_location_lines key for content that has no Location at all
# (e.g. an unregistered Asset with a blank Location) — it can never be
# routed to a Location-specific recipient, only to a blank-Location
# (company-wide) one.
NO_LOCATION = ""


def _get_current_allocations():
	"""Base (real, stored) fields only — compliance is computed fresh per
	row via fleet_compliance.compute_all, never read from a cached column.
	Scoped to get_reportable_asset_names() — Reporting Scope's included
	Companies/Suppliers — same as every other Fleet report/dashboard/export."""
	asset_names = get_reportable_asset_names()

	if not asset_names:
		return []

	return frappe.get_all(
		"Vehicle Allocation",
		filters={"docstatus": 1, "status": "Current", "asset": ["in", list(asset_names)]},
		fields=["name", "asset", "asset_name", "location", "required_licence_type", "is_temp", "valid_from"],
	)


def _recipients_by_scope(recipients):
	"""Split Fleet Notification Recipient rows into a Location-specific map
	and a catch-all (blank-Location) list. Each of the three fleet
	notifications (Weekly Compliance Digest, Terminated Driver Alert,
	Temporary Loan Digest) has its own separate Recipients table on Fleet
	Management Settings — pass in whichever one is relevant, not a shared
	list with opt-in flags. The same person can be added to more than one
	table if they need more than one notification."""
	specific = {}
	catch_all = []

	for row in recipients or []:
		email = frappe.db.get_value("User", row.user, "email") or row.user

		if not email:
			continue

		location = (row.location or "").strip()

		if location:
			specific.setdefault(location, []).append(email)
		else:
			catch_all.append(email)

	def _dedupe(emails):
		seen = set()
		out = []

		for e in emails:
			key = e.lower()

			if key in seen:
				continue

			seen.add(key)
			out.append(e)

		return out

	return {loc: _dedupe(emails) for loc, emails in specific.items()}, _dedupe(catch_all)


def _send_location_grouped(*, by_location_lines, recipients, subject_prefix, log_label, dry_run):
	"""Shared sender for every Location-scoped fleet notification (Weekly
	Compliance Digest, Terminated Driver Alert, Temporary Loan Digest) —
	`recipients` is that specific notification's own Recipients table.

	by_location_lines: {location_or_NO_LOCATION: [pre-formatted line, ...]}
	— only keys with actual content should be present.

	A recipient with a specific Location gets one email scoped to just
	that Location. A recipient with a blank Location gets a single
	company-wide email covering every Location's content (including the
	NO_LOCATION bucket, which can never reach a Location-specific
	recipient since it isn't tied to one) — "no Location set" means
	"across the whole company", not "nothing"."""
	specific_recipients, catch_all_recipients = _recipients_by_scope(recipients)

	payloads = {}

	for location, lines in by_location_lines.items():
		if location == NO_LOCATION or not lines:
			continue

		recips = specific_recipients.get(location, [])

		if not recips:
			continue

		payloads[location] = {
			"recipients": recips,
			"subject": f"{subject_prefix} — {location} ({len(lines)})",
			"message": "<br>".join(["Hi Team", "", f"Location: {location}", ""] + lines),
		}

	if catch_all_recipients:
		combined_lines = []
		total = 0

		for location in sorted(by_location_lines, key=lambda k: (k == NO_LOCATION, k)):
			lines = by_location_lines.get(location) or []

			if not lines:
				continue

			combined_lines.append(f"<b>{location or 'Unassigned'}</b>")
			combined_lines.extend(lines)
			combined_lines.append("")
			total += len(lines)

		if combined_lines:
			payloads["All Locations"] = {
				"recipients": catch_all_recipients,
				"subject": f"{subject_prefix} — All Locations ({total})",
				"message": "<br>".join(["Hi Team", ""] + combined_lines),
			}

	if dry_run:
		return payloads

	email_account = _get_outgoing_email_account(match_by_doctype="Vehicle Allocation")

	if not email_account or not getattr(email_account, "email_id", None):
		frappe.log_error(
			f"No outgoing Email Account configured/enabled. Skipping {log_label}.",
			log_label,
		)
		return payloads

	for key, payload in payloads.items():
		if not payload["recipients"]:
			continue

		try:
			frappe.sendmail(
				recipients=payload["recipients"],
				sender=email_account.email_id,
				subject=payload["subject"],
				message=payload["message"],
				now=True,
			)
		except Exception:
			frappe.log_error(f"Failed to send {log_label} for {key}", log_label)

	return payloads


# These three are registered directly against Frappe's own native
# scheduler buckets (scheduler_events["weekly"] / ["daily"] in hooks.py) —
# "Weekly" fires once, Sundays at 00:00 server time; "Daily" fires once, at
# 00:00 server time; both cron-driven and deduplicated by Frappe's own
# Scheduled Job Type (via last_execution), so there is no custom day/hour
# field or dedup cache to maintain here. Each gate only ever decides
# whether the notification is enabled at all — never when it runs.
def send_weekly_fleet_digest_gate():
	if not frappe.db.exists("DocType", "Fleet Management Settings"):
		return

	if not frappe.db.get_single_value("Fleet Management Settings", "send_weekly_digest"):
		return

	return send_weekly_fleet_digest(dry_run=False)


def send_terminated_driver_alert_gate():
	if not frappe.db.exists("DocType", "Fleet Management Settings"):
		return

	if not frappe.db.get_single_value("Fleet Management Settings", "send_terminated_driver_alert"):
		return

	return send_terminated_driver_alert(dry_run=False)


def send_temporary_loan_digest_gate():
	if not frappe.db.exists("DocType", "Fleet Management Settings"):
		return

	if not frappe.db.get_single_value("Fleet Management Settings", "send_temporary_loan_digest"):
		return

	return send_temporary_loan_digest(dry_run=False)


def _get_unregistered_assets():
	asset_names = get_reportable_asset_names()

	if not asset_names:
		return []

	return frappe.db.sql(
		"""
		select a.name as asset, a.asset_name as asset_name, a.asset_category as asset_category, a.location as location
		from `tabAsset` a
		left join `tabVehicle Allocation` v on v.asset = a.name and v.docstatus = 1 and v.status = 'Current'
		where a.name in %(asset_names)s and v.name is null
		order by a.name
		""",
		{"asset_names": list(asset_names)},
		as_dict=True,
	)


def send_weekly_fleet_digest(dry_run: bool = False):
	"""Group currently-open Vehicle Allocations needing attention — and
	unregistered public-road Assets — by Location and email the configured
	recipients for that Location. Compliance is computed fresh here (not
	read from any stored field). dry_run=True returns payloads instead of
	sending."""
	settings = frappe.get_single("Fleet Management Settings")
	threshold_days = get_expiring_threshold_days()

	flagged = []
	current_allocations = _get_current_allocations()
	drivers_by_parent = bulk_drivers([row.name for row in current_allocations])

	for row in current_allocations:
		driver_rows = drivers_by_parent.get(row.name, [])
		compliance = compute_all(
			row.asset,
			[d.driver for d in driver_rows],
			row.required_licence_type,
			threshold_days,
		)

		if compliance["overall_status"] in ATTENTION_STATUSES:
			flagged.append({**row, **compliance, "driver_rows": driver_rows})

	unregistered = _get_unregistered_assets()

	by_location_lines = {}

	for r in flagged:
		location = (r.get("location") or "").strip()
		issues = []

		if r["vehicle_licence_status"] in ("Expiring", "Expired", "Incomplete", "Outstanding"):
			issues.append(f"Vehicle Licence {r['vehicle_licence_status']}")

		if r["driver_licence_status"] in ("Expiring", "Expired", "Incomplete", "Outstanding"):
			issues.append(f"Driver Licence {r['driver_licence_status']}")

		if r["addendum_status"] == "Outstanding":
			issues.append("Company Vehicle Undertaking Outstanding")

		driver_display = ", ".join(d.driver_name or d.driver for d in r["driver_rows"]) or "no driver"

		by_location_lines.setdefault(location, []).append(
			f"- {r['asset_name'] or r['asset']} — {driver_display}: {', '.join(issues) or r['overall_status']}"
		)

	if unregistered:
		by_unregistered_location = {}

		for u in unregistered:
			location = (u.get("location") or "").strip()
			by_unregistered_location.setdefault(location, []).append(u)

		for location, assets in by_unregistered_location.items():
			lines = by_location_lines.setdefault(location, [])
			lines.append("")
			lines.append("Unregistered public-road Assets (no Vehicle Allocation yet):")

			for u in assets:
				lines.append(f"- {u.asset_name or u.asset} ({u.asset_category})")

	return _send_location_grouped(
		by_location_lines=by_location_lines,
		recipients=settings.get("weekly_digest_recipients"),
		subject_prefix="Fleet Compliance Weekly Digest",
		log_label="Fleet Compliance Weekly Digest",
		dry_run=dry_run,
	)


def _get_terminated_or_pending_drivers():
	"""{employee: "Terminated" | "Pending Termination"} for every Employee
	whose status is Left (Terminated), or who has a Termination Form on
	file — Submitted counts as Terminated, Draft-only as Pending
	Termination. Defensive against ir not being installed."""
	statuses = {}

	for e in frappe.get_all("Employee", filters={"status": "Left"}, pluck="name"):
		statuses[e] = "Terminated"

	if not frappe.db.exists("DocType", "Termination Form"):
		return statuses

	for row in frappe.get_all(
		"Termination Form",
		filters={"docstatus": ["<", 2]},
		fields=["requested_for", "docstatus"],
		order_by="docstatus desc",
	):
		if not row.requested_for or statuses.get(row.requested_for) == "Terminated":
			continue

		statuses[row.requested_for] = "Terminated" if row.docstatus == 1 else "Pending Termination"

	return statuses


def send_terminated_driver_alert(dry_run: bool = False):
	"""Daily: flag every Current, submitted Vehicle Allocation that has a
	Driver who is Terminated (Employee status Left, or a Submitted
	Termination Form) or Pending Termination (a Draft Termination Form),
	grouped by Location."""
	settings = frappe.get_single("Fleet Management Settings")
	statuses = _get_terminated_or_pending_drivers()

	by_location_lines = {}

	if statuses:
		current_allocations = _get_current_allocations()
		drivers_by_parent = bulk_drivers([row.name for row in current_allocations])

		for row in current_allocations:
			driver_rows = drivers_by_parent.get(row.name, [])
			flagged_drivers = [
				f"{d.driver_name or d.driver} ({statuses[d.driver]})" for d in driver_rows if d.driver in statuses
			]

			if not flagged_drivers:
				continue

			location = (row.get("location") or "").strip()
			by_location_lines.setdefault(location, []).append(
				f"- {row.asset_name or row.asset} — {', '.join(flagged_drivers)}"
			)

	return _send_location_grouped(
		by_location_lines=by_location_lines,
		recipients=settings.get("terminated_driver_alert_recipients"),
		subject_prefix="Fleet Terminated Driver Alert",
		log_label="Fleet Terminated Driver Alert",
		dry_run=dry_run,
	)


def send_temporary_loan_digest(dry_run: bool = False):
	"""Daily: a summary of every active ("Is Temporary Loan") Vehicle
	Allocation, grouped by Location."""
	settings = frappe.get_single("Fleet Management Settings")
	current_allocations = [row for row in _get_current_allocations() if row.is_temp]
	drivers_by_parent = bulk_drivers([row.name for row in current_allocations])

	by_location_lines = {}

	for row in current_allocations:
		driver_rows = drivers_by_parent.get(row.name, [])
		driver_display = ", ".join(d.driver_name or d.driver for d in driver_rows) or "no driver"
		location = (row.get("location") or "").strip()
		by_location_lines.setdefault(location, []).append(
			f"- {row.asset_name or row.asset} — {driver_display} (since {row.valid_from})"
		)

	return _send_location_grouped(
		by_location_lines=by_location_lines,
		recipients=settings.get("temporary_loan_digest_recipients"),
		subject_prefix="Fleet Temporary Loan Digest",
		log_label="Fleet Temporary Loan Digest",
		dry_run=dry_run,
	)
