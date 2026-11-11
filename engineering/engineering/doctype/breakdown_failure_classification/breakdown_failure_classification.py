import frappe
from frappe.model.document import Document
from engineering.controllers.failure_classification import (
    clear_configuration_cache, validate_matching_configuration,
)


class BreakdownFailureClassification(Document):
    def validate(self):
        try:
            validate_matching_configuration(self)
        except ValueError as exc:
            frappe.throw(str(exc))

    def on_update(self):
        clear_configuration_cache()

    def on_trash(self):
        clear_configuration_cache()

    def after_rename(self, *args, **kwargs):
        clear_configuration_cache()
