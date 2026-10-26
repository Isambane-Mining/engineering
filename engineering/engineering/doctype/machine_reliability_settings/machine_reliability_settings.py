import frappe
from frappe.model.document import Document
from engineering.engineering.page.machine_reliability.machine_reliability import terms


TYRES_WHEELS_CATEGORY = 'Tyres / Wheels'
TYRE_DAMAGE_SUBCATEGORY = 'Tyre Damage'


DEFAULT_CATEGORIES = [
    ('Brakes', 'brake, brakes, braking, park brake, parking brake, handbrake, retarder', 'Brake Test\nBrake Wear Measurements'),
    ('Steering', 'steer, steering, hard steering, heavy steering, no steering, power steering, steering wheel, steering pump, steering cylinder, tie rod', ''),
    ('Engine / Starting', 'engine, starting, starter, crank, cranking, no start, not start, wont start, won’t start', ''),
    ('Hydraulics', 'hydraulic, hydraulics, hydraulic leak, hydraulic pump, hydraulic hose', ''),
    ('Electrical', 'electrical, wiring, alternator, battery, batteries, fuse, fuses, short circuit', 'Illumination Baseline'),
    ('Cooling', 'coolant, radiator, overheating, overheat, water pump, cooling', ''),
    ('Transmission / Drivetrain', 'transmission, gearbox, drivetrain, drive shaft, driveshaft, differential, prop shaft, propshaft, final drive', ''),
    (TYRES_WHEELS_CATEGORY, 'tyre, tyres, tire, tires, wheel, wheels, puncture, rim, rims', 'Tyre Inspection Report'),
    ('Air Conditioning', 'aircon, air con, air conditioning, air conditioner', ''),
    ('Other', 'other, miscellaneous, unknown fault, oil leak, oil leaks, oil leaking, lubrication, lubricate, grease, low oil pressure, pds, proximity, collision warning, fire suppression, seat belt, seatbelt, emergency stop', 'Wearcheck\nPDS\nFire Suppression\nFRCS'),
]
PROBLEM_CATEGORIES = tuple(category for category, _, _ in DEFAULT_CATEGORIES)


class MachineReliabilitySettings(Document):
    def validate(self):
        seen = set()
        for row in self.categories:
            label = (row.category or '').strip()
            if not label or label.casefold() in seen:
                frappe.throw('Problem category names must be present and unique.')
            seen.add(label.casefold())
            words = terms(row.keywords)
            # Other retains merged historical/custom lists without discarding
            # configured terms. Keep the existing limit for the named systems.
            if not words or any(len(w) > 100 for w in words):
                frappe.throw('Each category needs keywords, up to 100 characters each.')
            if label != 'Other' and len(words) > 100:
                frappe.throw('Use at most 100 keywords per category. Other may retain longer merged lists.')
            row.category, row.keywords = label, '\n'.join(words)
            for section in (row.test_sections or '').splitlines():
                section = section.strip()
                if section and (section == 'Machine Service Records' or not frappe.db.exists('Engineering Legals Sections', section)):
                    frappe.throw('Choose existing test / inspection sections; services are counted separately.')

        if {row.category for row in self.categories} != set(PROBLEM_CATEGORIES):
            frappe.throw('Keep the ten standard Problem Categories. You can edit their keywords and test sections.')
