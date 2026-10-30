from frappe.model.document import Document

from engineering.controllers.engineering_legals_rules import validate_configuration


class EngineeringLegalsSiteConfiguration(Document):
    def validate(self):
        validate_configuration(self)
