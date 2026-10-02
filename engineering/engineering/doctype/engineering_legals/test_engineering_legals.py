from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from engineering.engineering.doctype.engineering_legals.engineering_legals import (
    EngineeringLegals,
)


class TestEngineeringLegals(TestCase):
    def _doc(self, section):
        return SimpleNamespace(
            sections=section,
            site="Koppie",
            fleet_number="TEST-ASSET",
            attach_paper="/private/files/test.pdf",
            start_date="2026-10-01",
            expiry_date=None,
            vehicle_type=None,
            lifting_type=None,
            brake_wear_type=None,
            hsec_send=0,
            hsec_qualification_id_external=None,
        )

    def test_saved_in_month_sections_do_not_require_expiry(self):
        for section in (
            "Equipment Technical Information",
            "Maintenance Inspections",
            "PDS Installation",
        ):
            doc = self._doc(section)
            with patch(
                "engineering.engineering.doctype.engineering_legals.engineering_legals.frappe.throw",
                side_effect=ValueError,
            ):
                EngineeringLegals.validate(doc)
            self.assertIsNone(doc.expiry_date)

    def test_unknown_section_still_rejected(self):
        doc = self._doc("Definitely Unknown Section")

        with patch(
            "engineering.engineering.doctype.engineering_legals.engineering_legals.frappe.throw",
            side_effect=ValueError,
        ):
            with self.assertRaises(ValueError):
                EngineeringLegals.validate(doc)
