"""Add verified classification keywords without replacing custom settings."""
import frappe
from engineering.controllers.failure_classification import terms

KEYWORDS = {'Mechanical': 'bearing seized|shaft fractured|coupling sheared|tensioner seized|pulley misaligned|idler bearing collapsed|gear teeth stripped|chain snapped|keyway worn', 'Hydraulic': 'boom cylinder|stick cylinder|bucket cylinder|pilot pressure|valve spool|swivel joint|hydraulic motor|swing motor|joystick pilot valve|lift cylinder', 'Electrical': 'starter will not engage|alternator not charging|battery will not hold charge|isolator switch|main fuse|relay contacts|ignition switch|harness insulation|earth connection|starter cable', 'Engine': 'cylinder head gasket|piston crown|piston rings|crankshaft bearing|connecting rod|camshaft lobe|valve clearance|turbocharger shaft|cylinder liner|rocker arm|low compression', 'Transmission / Drivetrain': 'differential crown wheel|differential pinion|diff lock|planetary gears|axle shaft|prop shaft|clutch pack|torque converter|transmission pressure|transfer case|gear selector|hub reduction', 'Braking System': 'brake pads|brake hose|master cylinder|brake charging pump|park brake|park brake lining|brake warning pressure switch|brake pack|brake booster|brake cooling|emergency braking', 'Steering System': 'steering pump|orbitrol valve|steering rod|tie rod|kingpin|articulation pin|articulation bearing|steering accumulator|steering cylinder', 'Cooling System': 'radiator core|water pump impeller|thermostat|viscous fan clutch|fan drive belt|expansion tank|coolant warning|charge air cooler|coolant pipe|coolant manifold|radiator mounting', 'Fuel System': 'fuel lift pump|rail pressure|injector stuck|fuel rail|tank pickup|leak-off line|filler neck|fuel cap seal|fuel heater|water in fuel|fuel cooler', 'Lubrication System': 'oil pump|oil filter|oil gallery|oil cooler|sump gasket|crank oil seal|automatic grease pump|grease line|grease nipple|grease reservoir|lubrication cycle|turbo oil feed|turbo return line', 'Undercarriage / Suspension': 'track chain|track shoe|track pin|track bush|carrier roller|bottom roller|idler bearing|sprocket teeth|track adjuster|recoil spring|track guard|track frame|equalizer bar|bogey pivot|leaf spring|shock absorber|walking beam|suspension pivot', 'Tyres / Wheels': 'tyre punctured|tyre sidewall|tyre burst|tyre tread separation|valve stem|bead not seating|rim cracked|lock ring|studs sheared|wheel bearing|dual tyre|tread chunking|shoulder tear|carcass bulging|inflation hose|wheel assembly|tyre casing|tubeless rim|tyre inner liner', 'Structural': 'chassis cracked|boom weld|stick side plate|bucket shell|dump body floor|tailgate frame|blade mounting|ripper frame|rear frame|cradle mount|counterweight bolts|cab support|handrail mounting|access ladder|tower weld|cross member|platform bracket|a-frame|tow hitch|rops member', 'Pneumatic / Air System': 'air compressor|air dryer|air receiver|air hose|air solenoid|air relief valve|air bag|control air line|compressor belt|compressor intake|unloader valve|pneumatic lock|air line lubricator', 'Electronic / Control System': 'ecu communications|controller not commanding shifts|display screen|can communication|speed sensor|position sensor|throttle position|transducer reading|boom angle sensor|joystick module|gateway offline|gps position|payload reading|tilt angle|controller plug|termination resistor|encoder pulses|diagnostic port', 'Air Conditioning / Cab': 'compressor clutch|condenser core|evaporator icing|refrigerant hose|expansion valve|blower motor|cab filter|heater core|fan resistor|cab temperature|cab door latch|cab door hinges|windscreen|seat slide|cab mount|demister outlet|wiper linkage|screen washer|cab pressuriser|cab duct|visor bracket|cab light|window glass', 'Safety Systems': 'reverse alarm|fire sensor|emergency stop|seat belt|seatbelt|person detection|rotating beacon|emergency steering alarm|overspeed shutdown|fire suppression|operator presence safety circuit|raised body alarm|body lock sensor|safety work light|lockout mechanism', 'Attachments / Implements': 'bucket tooth|side cutter|bucket pivot pin|quick hitch|cutting edge bolt|tilt link|ripper shank|ripper tip|moldboard cutting edge|circle gear|scarifier tine|hammer tool|hammer bushing|fork tine|grapple jaw|grapple pivot|heel plate|bucket corner|breaker attachment hose|drill bit|drill rod|spray bar', 'Pump / Fluid Transfer Systems': 'transfer pump|spray pump|fuel transfer pump|dewatering pump|suction strainer|discharge hose|suction hose|drive coupling|check valve|foot valve|wear ring|pump bearing|spray nozzle|discharge valve|meter stopped|priming pipe|hose reel', 'Tipping / Body Hoist Systems': 'hoist cylinder|hoist pressure hose|tip body hinge|body raised sensor|tailgate latch|tailgate hinge|lift control valve|body stop|tip command lever|safety prop|body floor|tailgate chain|hinge bracket|hoist relief valve|body lock'}


def execute():
    settings = frappe.get_doc("Machine Reliability Settings")
    rows = {row.category: row for row in settings.categories if row.category}

    missing = set(KEYWORDS) - set(rows)
    if missing:
        frappe.throw(f"Missing Failure Classifications: {sorted(missing)}")

    changed = False

    for category, phrases in KEYWORDS.items():
        row = rows[category]
        existing = terms(row.keywords)
        combined = list(existing)

        for keyword in phrases.split("|"):
            normalized = keyword.strip().casefold()
            if normalized and normalized not in combined:
                combined.append(normalized)

        if combined != existing:
            row.keywords = "\n".join(combined)
            changed = True


    inspections = {
        "Lubrication System": ["Wearcheck"],
        "Safety Systems": ["PDS", "Fire Suppression", "FRCS"],
    }

    for category, sections in inspections.items():
        row = rows[category]
        existing = [
            x.strip() for x in (row.test_sections or "").splitlines()
            if x.strip()
        ]
        for section in sections:
            if not frappe.db.exists("Engineering Legals Sections", section):
                frappe.throw(f"Missing inspection section: {section}")
            if section not in existing:
                existing.append(section)
                changed = True
        row.test_sections = "\n".join(existing)

    if changed:
        settings.save(ignore_permissions=True)

