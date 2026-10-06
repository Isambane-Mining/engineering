# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

"""Format-specific PDF parsing for Fleet Card Transaction Import - turns
either known statement shape into a list of plain row dicts, the shared
contract the rest of the import pipeline (engineering.controllers.
fleet_card_import) works with:

	{
		"card_identifier": "2008327433",   # full card number (NedBank) or
		                                    # last-4-digit suffix (Standard
		                                    # Bank, which masks the rest)
		"registration_number": "JNV 452MP" or None,
		"driver_name_raw": "JOHAN VENTER" or None,
		"transaction_type": "Fuel" | "Fuel & Oil" | "Toll" | "Other",
		"transaction_datetime": "2026-09-12 09:04:00",
		"merchant": "B P CHARLES STR MTR W/SHOP",
		"town": "PRETORIA" or "",
		"litres": 62.5 or None,
		"odometer": 85100 or None,
		"amount": 4789.10,
		"vat_amount": 169.08 or None,
		"document_number": "192000" or None,
	}

Both formats are real bank exports, not something either bank designed for
machine parsing - space-joined text extraction (pdfplumber) loses the
original column boundaries, so merchant/town are a best-effort split (last
whitespace-separated word before the transaction-type keyword is taken as
the town, everything before that as the merchant) rather than an exact
field-by-field read. card/vehicle identity, amount, date and transaction
type - the fields that matter for matching and accounting - come from
unambiguous fixed tokens in each line and are not approximate.

NedBank's "VEHICLE AUDIT TRAIL AND CALCULATED VAT" section gives the full
card number but only a lump monthly VAT figure (on the "Trans. Total"/
"*** Total" summary lines, never per-row) - vat_amount is therefore always
None for a NedBank-sourced row except where a row happens to carry its own
(Toll rows do; Fuel & Oil rows don't in the samples seen). Standard Bank's
"Extended Vehicle Transaction Report" masks the card to its last 4 digits
(printed as "NUMBER: ******9911") but gives the full registration number -
matching a Standard Bank row to a Fleet Card goes via registration_number,
not card_identifier (see resolve_fleet_card() in fleet_card_import.py)."""

from __future__ import annotations

import io
import re

import frappe

NEDBANK_SECTION_MARKER = "VEHICLE AUDIT TRAIL AND CALCULATED VAT"
STANDARD_BANK_MARKER = "Standard Bank Extended Vehicle Transaction Report"

_NEDBANK_SKIP_LINE = re.compile(
	r"^(TXR\d|VEHICLE AUDIT TRAIL|BRANCH NAME|COST CENTRE|\d+/\d+ CARD DETAILS"
	r"|VEH/CARD DETAILS|\S*CARD DETAILS\b.*VAT CALC\.?$|\*{3,} END OF REPORT \*{3,}$|\d+ \d+ .+\(PTY\) LTD$)"
)
_NEDBANK_SUMMARY_LINE = re.compile(r"\b(Trans\. Total|Service Fees|Tran\. Fees|Finance charges|\*\*\* Total)\b")
_NEDBANK_CARD_NO = re.compile(r"^Card No\.\s*:\s*(\d+)")
_NEDBANK_REG_NO = re.compile(r"^Reg\.\s*No\.\s*:\s*(.+)$")
_NEDBANK_DRIVER = re.compile(r"^Driver\s*:\s*(.+)$")
_NEDBANK_VEH_MAKE = re.compile(r"^Veh\s*Make\s*:\s*(.+)$")
_NEDBANK_ROW = re.compile(
	r"^(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})\s+(.+?)\s+(Fuel\s*&\s*Oil|Toll)\s+(\S+)\s+"
	r"(\d+,\d{2})(?:\s+(\d+,\d{2}))?$"
)

_SB_HEADER_REG_NO = re.compile(r"REG\.\s*NO\s*:\s*(\S+)")
_SB_HEADER_DRIVER = re.compile(r"DRIVER\s*:\s*([A-Z][A-Z .'-]+?)\s{2,}")
_SB_HEADER_CARD_SUFFIX = re.compile(r"NUMBER:\s*\*+(\d{3,6})")
#  Head: date, batch, micro, voucher, typ, then "<merchant blob> <odometer>
#  [<fuel_span>]" up to the literal "FUEL" keyword. Tail: "<litres>
#  [<l/100k>] <amount> <interest> [<warning words>]". Odometer and L/100K
#  are both blank (shown as a single "0") on some vehicles and populated
#  with a second number on others, depending on whether that vehicle's own
#  odometer tracking is active - split on the "FUEL" anchor and parse each
#  side by position (amount/odometer are always second-to-last/first of
#  their own run) rather than a single fixed-arity regex, since the
#  optional extra column shifts everything after it by one position.
_SB_FUEL_HEAD = re.compile(r"^(\d{8})\s+(\d+)\s+(\d+)\s+(\S+)\s+([A-Z])\s+(.+?)\s+FUEL\s+(.+)$")
_SB_FUEL_HEAD_BLOB = re.compile(r"^(.*\D)\s+(\d+)(?:\s+(\d+))?$")
_SB_FUEL_TAIL = re.compile(r"^((?:[\d.]+\s+)*[\d.]+)(?:\s+(.*))?$")
_SB_TOLL_ROW = re.compile(r"^(\d{8})\s+[A-Z]\s+0\s+TOLL FEES\s+([\d.]+)\s+([\d.]+)$")
_SB_TIME_LINE = re.compile(r"^(\d{2}:\d{2}:\d{2})\b")
_SB_FUEL_BF = re.compile(r"\bFUEL B/F\b")


def _za_decimal(value: str) -> float:
	"""South African comma-decimal ("4789,10") -> float. Thousands are
	never grouped in either source export (confirmed against real values
	up to 5 digits before the comma), so a bare comma always means decimal
	point here, never thousands."""
	return float(value.replace(",", "."))


def sniff_format(first_page_text: str) -> str | None:
	"""Which known shape, from the FIRST page alone - both formats repeat
	enough of their own section headers on every later page that one page
	is always enough to tell them apart (see NedBank's own COMMUNICATION
	SCHEDULE first page, which doesn't carry the audit-trail marker itself
	but is still unambiguous: no Standard Bank statement ever starts any
	other way)."""
	if STANDARD_BANK_MARKER in first_page_text:
		return "Standard Bank"
	# NedBank's own first page is a different section (COMMUNICATION
	# SCHEDULE) - its own audit-trail marker only shows up a few pages in,
	# so sniffing needs a second, NedBank-specific first-page fingerprint.
	if "NEDBANK" in first_page_text.upper() and "COMMUNICATION SCHEDULE" in first_page_text.upper():
		return "NedBank"
	return None


def detect_and_parse(content: bytes, filename: str) -> tuple[str, list[dict]]:
	import pdfplumber

	with io.BytesIO(content) as buf, pdfplumber.open(buf) as pdf:
		pages_text = [page.extract_text() or "" for page in pdf.pages]

	if not pages_text:
		frappe.throw(frappe._("The attached file has no readable pages."))

	fmt = sniff_format(pages_text[0])
	if fmt is None:
		frappe.throw(
			frappe._(
				"Could not recognise {0} as a NedBank or Standard Bank Fleet Card statement."
			).format(filename)
		)

	if fmt == "NedBank":
		return fmt, parse_nedbank(pages_text)
	return fmt, parse_standard_bank(pages_text)


def parse_nedbank(pages_text: list[str]) -> list[dict]:
	"""Only pages belonging to the "VEHICLE AUDIT TRAIL AND CALCULATED
	VAT" section carry per-transaction rows (the "EXPENSE SUMMARY PER
	VEHICLE" pages earlier in the same file are a monthly total per
	vehicle, not individual transactions, and are skipped entirely) -
	filtered by content, not page position, since where that section
	falls varies by report. current card/registration/driver is carried
	across pages within the section (a card's rows routinely spill onto a
	continuation page that doesn't repeat "Card No. :")."""
	rows: list[dict] = []
	current_card = None
	current_reg = None
	current_driver = None

	for page_text in pages_text:
		if NEDBANK_SECTION_MARKER not in page_text:
			continue

		for line in page_text.splitlines():
			line = line.strip()
			if not line or _NEDBANK_SKIP_LINE.match(line) or _NEDBANK_SUMMARY_LINE.search(line):
				continue

			m = _NEDBANK_CARD_NO.match(line)
			if m:
				current_card = m.group(1)
				# A new card block always starts its own fresh Reg. No./
				# Driver label lines a line or two later - reset both so
				# this card's own early rows (this line's and the next
				# one or two) never carry the PREVIOUS card's values
				# forward in between.
				current_reg = None
				current_driver = None
				remainder = line[m.end() :].strip()
				# Statement prints "2008327433( )" right after the number -
				# a fixed decoration, not part of either the card number or
				# the row that follows it on the same line.
				remainder = re.sub(r"^\(\s*\)\s*", "", remainder)
				_append_nedbank_row(rows, remainder, current_card, current_reg, current_driver)
				continue

			m = _NEDBANK_REG_NO.match(line)
			if m:
				rest = m.group(1)
				# The label's own value and the row data are both on this
				# line, space-joined with no fixed boundary - the row
				# itself always starts at the DD/MM/YYYY date, so split
				# there. A card with fewer real transactions than label
				# lines (Card No./Reg. No./Driver/Veh Make always print,
				# whether or not a row happens to land on each one) can
				# leave this label's "remainder" holding unrelated text
				# from whatever comes next in the file instead of a real
				# row - only trust it, for both the label value and the
				# row, when a clean date boundary is actually found.
				date_split = re.search(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\b", rest)
				if date_split:
					current_reg = rest[: date_split.start()].strip()
					_append_nedbank_row(rows, rest[date_split.start() :], current_card, current_reg, current_driver)
				continue

			m = _NEDBANK_DRIVER.match(line)
			if m:
				rest = m.group(1)
				date_split = re.search(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\b", rest)
				if date_split:
					current_driver = rest[: date_split.start()].strip()
					_append_nedbank_row(rows, rest[date_split.start() :], current_card, current_reg, current_driver)
				continue

			m = _NEDBANK_VEH_MAKE.match(line)
			if m:
				rest = m.group(1)
				date_split = re.search(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\b", rest)
				remainder = rest[date_split.start() :] if date_split else ""
				_append_nedbank_row(rows, remainder, current_card, current_reg, current_driver)
				continue

			# A plain continuation row - no label prefix.
			_append_nedbank_row(rows, line, current_card, current_reg, current_driver)

	return rows


def _append_nedbank_row(rows, remainder, card, reg, driver):
	remainder = (remainder or "").strip()
	if not remainder or not card:
		return

	m = _NEDBANK_ROW.match(remainder)
	if not m:
		return

	date_str, time_str, merchant_blob, tran_type, doc_no, amt1, amt2 = m.groups()
	merchant_blob = merchant_blob.strip()
	parts = merchant_blob.rsplit(" ", 1)
	merchant, town = (parts[0], parts[1]) if len(parts) == 2 else (merchant_blob, "")

	day, month, year = date_str.split("/")
	tran_type_norm = "Fuel & Oil" if "Fuel" in tran_type else "Toll"

	rows.append(
		{
			"card_identifier": card,
			"registration_number": reg,
			"driver_name_raw": driver,
			"transaction_type": tran_type_norm,
			"transaction_datetime": f"{year}-{month}-{day} {time_str}:00",
			"merchant": merchant,
			"town": town,
			"litres": None,
			"odometer": None,
			"amount": _za_decimal(amt1),
			"vat_amount": _za_decimal(amt2) if amt2 else None,
			"document_number": doc_no,
		}
	)


def parse_standard_bank(pages_text: list[str]) -> list[dict]:
	"""Every page of a vehicle's 3-page block repeats the same header
	(registration/driver/masked card suffix), including the two pages that
	carry no transaction rows at all - re-extracting the header from every
	page and filtering transaction rows by content (not by assuming a
	fixed page role) tolerates the one real exception seen in practice: a
	lump "TOLL FEES" total for the period that lands on the *second* page
	of a vehicle's block, after the fuel rows on page 1 end."""
	rows: list[dict] = []

	for page_text in pages_text:
		reg_match = _SB_HEADER_REG_NO.search(page_text)
		driver_match = _SB_HEADER_DRIVER.search(page_text)
		card_match = _SB_HEADER_CARD_SUFFIX.search(page_text)

		reg = reg_match.group(1) if reg_match else None
		driver = driver_match.group(1).strip() if driver_match else None
		card_suffix = card_match.group(1) if card_match else None

		if not reg:
			continue

		lines = page_text.splitlines()
		i = 0
		while i < len(lines):
			line = lines[i].strip()

			if _SB_FUEL_BF.search(line):
				i += 1
				continue

			m = _SB_FUEL_HEAD.match(line)
			if m:
				date_str, _batch, _micro, voucher, _typ, head_rest, tail = m.groups()

				head_m = _SB_FUEL_HEAD_BLOB.match(head_rest.strip())
				if not head_m:
					i += 1
					continue
				merchant_blob, odometer, _fuel_span = head_m.groups()

				tail_m = _SB_FUEL_TAIL.match(tail.strip())
				if not tail_m:
					i += 1
					continue
				numbers = tail_m.group(1).split()
				litres = float(numbers[0])
				# Second-to-last of the run is always Amount (the last is
				# Interest, discarded - a finance charge, not VAT), whether
				# or not the optional Fillup L/100K column sits between
				# Litres and Amount - see the module docstring note above.
				amount = float(numbers[-2]) if len(numbers) >= 2 else float(numbers[0])

				time_str = "00:00:00"
				if i + 1 < len(lines):
					tm = _SB_TIME_LINE.match(lines[i + 1].strip())
					if tm:
						time_str = tm.group(1)
						i += 1

				merchant_blob = merchant_blob.strip()
				parts = merchant_blob.rsplit(" ", 1)
				merchant, town = (parts[0], parts[1]) if len(parts) == 2 else (merchant_blob, "")

				rows.append(
					{
						"card_identifier": card_suffix,
						"registration_number": reg,
						"driver_name_raw": driver,
						"transaction_type": "Fuel",
						"transaction_datetime": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str}",
						"merchant": merchant,
						"town": town,
						"litres": litres,
						"odometer": int(odometer) if odometer and odometer != "0" else None,
						"amount": amount,
						"vat_amount": None,
						"document_number": voucher,
					}
				)
				i += 1
				continue

			m = _SB_TOLL_ROW.match(line)
			if m:
				date_str, amount, _interest = m.groups()
				rows.append(
					{
						"card_identifier": card_suffix,
						"registration_number": reg,
						"driver_name_raw": driver,
						"transaction_type": "Toll",
						"transaction_datetime": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 00:00:00",
						"merchant": "",
						"town": "",
						"litres": None,
						"odometer": None,
						"amount": float(amount),
						"vat_amount": None,
						"document_number": None,
					}
				)

			i += 1

	return rows
