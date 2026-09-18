# Copyright (c) 2026, buff0k and contributors
# For license information, please see license.txt

"""Shared presentation helpers for every Fleet Management notification
email, mirroring the pattern already established in ir/industrial_relations/
email_style.py — Frappe ships a complete transactional-email design
(frappe/templates/emails/standard.html + email.bundle.scss: a rounded white
card, an optional masthead, a bold title row with a coloured status dot)
that only activates when frappe.sendmail(header=[title, indicator_colour])
is actually passed. None of the Fleet notifications did, so every one of
them rendered as bare, unstyled `<br>`-joined text outside that card.

EMAIL_STYLE_BLOCK layers a small, consistent table treatment on top. Frappe
runs every email through Premailer at send time
(frappe.email.email_body.inline_style_in_html), which inlines any <style>
block present in the message body — so this is written as normal CSS, not
hand-rolled inline `style=` attributes on every cell."""

from urllib.parse import quote

import frappe
from frappe.utils import escape_html, get_url

FLEET_ACCENT = "#1565c0"

# Maps to Frappe's own .indicator-{colour} classes (email.bundle.scss) — the
# same dot frappe/hrms use on their own transactional emails.
INDICATOR_BY_SEVERITY = {
	"urgent": "red",  # Non-Compliant, a terminated driver still allocated
	"attention": "orange",  # Expiring/Attention Required, pending termination
	"info": "blue",  # administrative — temporary loans, unregistered assets
}

# Same colour meaning as fleet_compliance.py's _STATUS_COLOURS, kept as
# plain hex here (not CSS custom properties) since email clients can't
# resolve var(--...) the way the desk UI can.
STATUS_COLOURS = {
	"Valid": "#2e7d32",
	"On File": "#2e7d32",
	"Closed": "#2e7d32",
	"Compliant": "#2e7d32",
	"Expiring": "#e65100",
	"Incomplete": "#e65100",
	"Open": "#e65100",
	"Attention Required": "#e65100",
	"Pending Termination": "#e65100",
	"Expired": "#c62828",
	"Outstanding": "#c62828",
	"Non-Compliant": "#c62828",
	"Terminated": "#c62828",
}

EMAIL_STYLE_BLOCK = f"""
<style>
  .fleet-email-intro {{ margin: 0 0 16px; color: #525252; }}
  .fleet-email-section-title {{
    margin: 20px 0 8px;
    font-size: 13px;
    font-weight: 600;
    color: #212121;
  }}
  .fleet-email-table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    margin-bottom: 8px;
  }}
  .fleet-email-table th {{
    text-align: left;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.01em;
    color: #525252;
    background-color: #f5f5f5;
    padding: 8px 10px;
    border-bottom: 2px solid {FLEET_ACCENT};
  }}
  .fleet-email-table td {{
    padding: 8px 10px;
    font-size: 13px;
    line-height: 1.45;
    vertical-align: top;
    border-bottom: 1px solid #ededed;
    word-wrap: break-word;
  }}
  .fleet-email-table tbody tr:last-child td {{ border-bottom: none; }}
  .fleet-email-table tbody tr:nth-child(even) td {{ background-color: #fafafa; }}
  .fleet-email-badge {{
    display: inline-block;
    padding: 1px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    color: #ffffff;
    white-space: nowrap;
  }}
  .fleet-email-empty {{
    padding: 16px;
    color: #999999;
    font-size: 13px;
    text-align: center;
    background-color: #f8f8f8;
    border-radius: 8px;
  }}
  .fleet-email-signoff {{ margin-top: 20px; color: #525252; }}
</style>
"""


def email_header(title, severity="info"):
	"""The (title, indicator_colour) pair frappe.sendmail(header=...)
	expects — this is what actually turns on Frappe's rounded-card email
	chrome."""
	return [title, INDICATOR_BY_SEVERITY.get(severity, "blue")]


def intro(text):
	return f'<p class="fleet-email-intro">{text}</p>'


def section_title(text):
	return f'<div class="fleet-email-section-title">{escape_html(text)}</div>'


def empty_state(message):
	return f'<div class="fleet-email-empty">{escape_html(message)}</div>'


def signoff():
	return '<p class="fleet-email-signoff">Kind regards,<br>Fleet Management</p>'


def status_badge(status):
	"""A small coloured pill matching the status colours used in the Fleet
	Compliance desk views — status text stays exactly as computed
	(Expiring/Expired/Outstanding/etc.), just with a matching colour."""
	colour = STATUS_COLOURS.get(status, "#757575")
	return f'<span class="fleet-email-badge" style="background-color:{colour};">{escape_html(status or "—")}</span>'


def record_link(doctype, name, label=None):
	"""A link to a Vehicle Allocation / Vehicle Licence (or any doctype)
	record — returns plain escaped text if name is falsy, since a row may
	have nothing to link to yet (e.g. no Vehicle Licence captured). The
	record name is URL-quoted since these names routinely contain spaces
	(e.g. "IS872 - 2026-09-11") — matching the same quote() convention
	already used for record links elsewhere in this app (see
	vehicle_licence_expiration.py's record_url)."""
	if not name:
		return escape_html(label or "—")

	url = get_url(f"/app/{frappe.scrub(doctype).replace('_', '-')}/{quote(name)}")
	return f'<a href="{url}">{escape_html(label or name)}</a>'


def render_table(headers, rows_of_cells):
	"""headers: [str, ...]; rows_of_cells: [[cell_html, ...], ...] — cells
	are HTML, already escaped/linked by the caller (matches
	fleet_compliance._render_table's calling convention, for consistency
	with the desk-side compliance panels)."""
	head = "".join(f"<th>{escape_html(h)}</th>" for h in headers)
	body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows_of_cells)

	return f'<table class="fleet-email-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
