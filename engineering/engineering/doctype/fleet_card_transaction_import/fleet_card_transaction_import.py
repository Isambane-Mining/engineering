# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

"""Fleet Card statement import - accepts either known statement shape
(NedBank's "Vehicle Audit Trail", Standard Bank's "Extended Vehicle
Transaction Report") through one doctype. Which shape a given file is gets
sniffed from its own content the moment it's parsed (see
engineering.controllers.fleet_card_import_parsers' detect_and_parse/
sniff_format) and recorded on this doc's own detected_format field.

See engineering.controllers.fleet_card_import's module docstring for the
full narrative on *why* the pipeline is shaped the way it is (background
job, before_submit guard, etc. - deliberately modelled on, but simplified
from, is_attendance's Clocking Import) - that module is what actually
drives every method below; this file only owns doctype registration and
handing the attached file to the right parser."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils.file_manager import get_file

from engineering.controllers import fleet_card_import
from engineering.controllers.fleet_card_import_parsers import detect_and_parse


class FleetCardTransactionImport(Document):
	def validate(self):
		fleet_card_import.validate_import(self)

	def before_submit(self):
		fleet_card_import.before_submit_guard(self)

	@frappe.whitelist()
	def queue_import(self):
		fleet_card_import.queue_import(self)

	def on_cancel(self):
		fleet_card_import.cancel_import(self)

	def parse_file(self) -> list[dict]:
		"""Cached per in-memory Document instance - validate() and
		queue_import() can both run against the same loaded doc within one
		request, and re-reading/re-decoding a 100+ page PDF twice is pure
		waste since the attached file can't change in between."""
		cached = getattr(self, "_parsed_rows_cache", None)
		if cached is not None:
			return cached

		filename, content = get_file(self.file)
		detected_format, rows = detect_and_parse(content, filename)
		self.detected_format = detected_format
		self._parsed_rows_cache = rows
		return rows
