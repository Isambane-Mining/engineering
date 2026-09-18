# Copyright (c) 2026, buff0k and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import escape_html

from engineering.controllers.fleet_compliance import bulk_drivers, compute_all, get_expiring_threshold_days
from engineering.controllers.fleet_email_style import (
	EMAIL_STYLE_BLOCK,
	email_header,
	intro,
	record_link,
	render_table,
	section_title,
	signoff,
	status_badge,
)
from engineering.controllers.notifications import _get_outgoing_email_account
from engineering.engineering.doctype.fleet_management_settings.fleet_management_settings import (
	get_reportable_asset_names,
)

ATTENTION_STATUSES = ["Attention Required", "Non-Compliant"]

# Used as a row's "location" value for content that has no Location at all
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


def _send_location_grouped(*, tables, recipients, subject_prefix, intro_text, severity, log_label, dry_run):
	"""Shared sender for every Location-scoped fleet notification (Weekly
	Compliance Digest, Terminated Driver Alert, Temporary Loan Digest) —
	`recipients` is that specific notification's own Recipients table.

	tables: [{"title": str | None, "headers": [str, ...], "rows": [{"location":
	str, "cells": [html, ...]}, ...]}, ...] — one entry per logical
	category (e.g. weekly digest has "Compliance Issues" and "Unregistered
	Assets" as two separate tables, since their columns differ; the other
	two notifications each have just one). `cells` line up with `headers`
	and never include a Location cell — that's injected here, and only for
	the "All Locations" catch-all email; a Location-scoped recipient's
	email only ever contains their own Location's rows, so a repeated
	Location column there would just be noise.

	A recipient with a specific Location gets one email containing every
	table's rows for just that Location (no separate table per Location —
	one consolidated table per category, exactly like the catch-all case,
	just pre-filtered). A recipient with a blank Location gets a single
	company-wide email covering every Location's rows in one table per
	category, with a Location column so they can still tell them apart —
	"no Location set" means "across the whole company", not "nothing"."""
	specific_recipients, catch_all_recipients = _recipients_by_scope(recipients)

	locations_present = {
		(row["location"] or "").strip() for table in tables for row in table["rows"]
	} - {NO_LOCATION}

	payloads = {}

	for location in locations_present:
		recips = specific_recipients.get(location, [])

		if not recips:
			continue

		blocks = []
		count = 0

		for table in tables:
			rows_here = [row["cells"] for row in table["rows"] if (row["location"] or "").strip() == location]

			if not rows_here:
				continue

			if table.get("title"):
				blocks.append(section_title(table["title"]))

			blocks.append(render_table(table["headers"], rows_here))
			count += len(rows_here)

		if not blocks:
			continue

		payloads[location] = {
			"recipients": recips,
			"subject": f"{subject_prefix} — {location} ({count})",
			"message": (
				EMAIL_STYLE_BLOCK
				+ intro(f"{intro_text} Location: <b>{escape_html(location)}</b>.")
				+ "".join(blocks)
				+ signoff()
			),
		}

	if catch_all_recipients:
		combined_blocks = []
		total = 0

		for table in tables:
			if not table["rows"]:
				continue

			rows_sorted = sorted(table["rows"], key=lambda row: (row["location"] or "").strip())
			rows_here = [
				[escape_html((row["location"] or "").strip() or "Unassigned"), *row["cells"]] for row in rows_sorted
			]

			if table.get("title"):
				combined_blocks.append(section_title(table["title"]))

			combined_blocks.append(render_table(["Location", *table["headers"]], rows_here))
			total += len(rows_here)

		if combined_blocks:
			payloads["All Locations"] = {
				"recipients": catch_all_recipients,
				"subject": f"{subject_prefix} — All Locations ({total})",
				"message": EMAIL_STYLE_BLOCK + intro(f"{intro_text} Covering every Location.") + "".join(combined_blocks) + signoff(),
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
				header=email_header(subject_prefix, severity),
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


def _issue_cell(label, status, doctype=None, name=None):
	"""One line inside a "Issues" table cell — the label links to the
	backing record (Vehicle Licence / Employee Induction Record) when one
	exists, plain text otherwise, followed by a coloured status badge."""
	return f"{record_link(doctype, name, label=label)} {status_badge(status)}"


def _addendum_cell(status, url):
	label = "Company Vehicle Undertaking"
	text = f'<a href="{url}">{label}</a>' if url else escape_html(label)
	return f"{text} {status_badge(status)}"


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

	issue_rows = []

	for r in flagged:
		issues = []

		if r["vehicle_licence_status"] in ("Expiring", "Expired", "Incomplete", "Outstanding"):
			issues.append(
				_issue_cell(
					"Vehicle Licence", r["vehicle_licence_status"], "Vehicle Licence", r.get("vehicle_licence_source")
				)
			)

		if r["driver_licence_status"] in ("Expiring", "Expired", "Incomplete", "Outstanding"):
			issues.append(
				_issue_cell(
					"Driver Licence",
					r["driver_licence_status"],
					"Employee Induction Record",
					r.get("driver_licence_source"),
				)
			)

		if r["addendum_status"] == "Outstanding":
			issues.append(_addendum_cell(r["addendum_status"], r.get("addendum_url")))

		driver_display = escape_html(", ".join(d.driver_name or d.driver for d in r["driver_rows"]) or "no driver")

		issue_rows.append(
			{
				"location": (r.get("location") or "").strip(),
				"cells": [
					record_link("Vehicle Allocation", r["name"], label=r["asset_name"] or r["asset"]),
					driver_display,
					"<br>".join(issues) or status_badge(r["overall_status"]),
				],
			}
		)

	unregistered_rows = [
		{
			"location": (u.get("location") or "").strip(),
			"cells": [record_link("Asset", u.asset, label=u.asset_name or u.asset), escape_html(u.asset_category or "—")],
		}
		for u in unregistered
	]

	tables = [
		{"title": "Compliance Issues", "headers": ["Asset", "Driver(s)", "Issues"], "rows": issue_rows},
		{
			"title": "Unregistered Assets (no Vehicle Allocation yet)",
			"headers": ["Asset", "Category"],
			"rows": unregistered_rows,
		},
	]

	return _send_location_grouped(
		tables=tables,
		recipients=settings.get("weekly_digest_recipients"),
		subject_prefix="Fleet Compliance Weekly Digest",
		intro_text="The following need attention this week.",
		severity="attention",
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

	rows = []

	if statuses:
		current_allocations = _get_current_allocations()
		drivers_by_parent = bulk_drivers([row.name for row in current_allocations])

		for row in current_allocations:
			driver_rows = drivers_by_parent.get(row.name, [])
			flagged_drivers = [
				f"{escape_html(d.driver_name or d.driver)} {status_badge(statuses[d.driver])}"
				for d in driver_rows
				if d.driver in statuses
			]

			if not flagged_drivers:
				continue

			rows.append(
				{
					"location": (row.get("location") or "").strip(),
					"cells": [
						record_link("Vehicle Allocation", row.name, label=row.asset_name or row.asset),
						"<br>".join(flagged_drivers),
					],
				}
			)

	tables = [{"title": None, "headers": ["Asset", "Driver(s)"], "rows": rows}]

	return _send_location_grouped(
		tables=tables,
		recipients=settings.get("terminated_driver_alert_recipients"),
		subject_prefix="Fleet Terminated Driver Alert",
		intro_text="The following allocated vehicles have a Terminated or Pending Termination driver.",
		severity="urgent",
		log_label="Fleet Terminated Driver Alert",
		dry_run=dry_run,
	)


def send_temporary_loan_digest(dry_run: bool = False):
	"""Daily: a summary of every active ("Is Temporary Loan") Vehicle
	Allocation, grouped by Location."""
	settings = frappe.get_single("Fleet Management Settings")
	current_allocations = [row for row in _get_current_allocations() if row.is_temp]
	drivers_by_parent = bulk_drivers([row.name for row in current_allocations])

	rows = []

	for row in current_allocations:
		driver_rows = drivers_by_parent.get(row.name, [])
		driver_display = escape_html(", ".join(d.driver_name or d.driver for d in driver_rows) or "no driver")
		rows.append(
			{
				"location": (row.get("location") or "").strip(),
				"cells": [
					record_link("Vehicle Allocation", row.name, label=row.asset_name or row.asset),
					driver_display,
					escape_html(str(row.valid_from or "—")),
				],
			}
		)

	tables = [{"title": None, "headers": ["Asset", "Driver(s)", "Since"], "rows": rows}]

	return _send_location_grouped(
		tables=tables,
		recipients=settings.get("temporary_loan_digest_recipients"),
		subject_prefix="Fleet Temporary Loan Digest",
		intro_text="The following are active Temporary Loan allocations.",
		severity="info",
		log_label="Fleet Temporary Loan Digest",
		dry_run=dry_run,
	)
