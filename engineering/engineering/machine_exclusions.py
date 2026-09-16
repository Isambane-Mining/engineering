"""
Machines excluded specifically from Pre Use Hours and
Availability & Utilisation.

Asset master records remain active elsewhere in ERPNext.
"""

EXCLUDED_PRE_USE_AU_MACHINES = {
    "426-492",
    "426-492 GWAB",
    "IS127",
    "IS127 GWAB",
    "IS0126 KLP",
    "IS077KLP",
    "IS077 KLP",
}


def normalise_machine(value):
    if value is None:
        return ""

    return " ".join(
        str(value).strip().upper().split()
    )


def compact_machine(value):
    return normalise_machine(value).replace(" ", "")


EXCLUDED_PRE_USE_AU_COMPACT_KEYS = {
    compact_machine(value)
    for value in EXCLUDED_PRE_USE_AU_MACHINES
}


def is_pre_use_au_excluded(site, machine):
    """
    Global exclusions for Pre Use Hours and A&U.

    `site` remains in the signature for compatibility.
    """
    machine = normalise_machine(machine)

    if not machine:
        return False

    if machine in EXCLUDED_PRE_USE_AU_MACHINES:
        return True

    return (
        compact_machine(machine)
        in EXCLUDED_PRE_USE_AU_COMPACT_KEYS
    )


def filter_pre_use_au_machines(rows, site=None):
    filtered = []

    for row in rows or []:
        if isinstance(row, dict):
            machine = (
                row.get("fleet_number")
                or row.get("asset")
                or row.get("asset_name")
                or row.get("machine")
                or row.get("machine_name")
                or row.get("name")
            )
        else:
            machine = row

        if not is_pre_use_au_excluded(
            site,
            machine,
        ):
            filtered.append(row)

    return filtered
