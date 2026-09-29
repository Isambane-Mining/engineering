import frappe


ADD_BY_LOCATION = {
    "Gwab": [
        "arno@isambane.co.za",
        "grant.cummings@isambane.co.za",
        "richard@isambane.co.za",
        "vusi@isambane.co.za",
    ],
    "Klipfontein": [
        "arno@isambane.co.za",
        "grant.cummings@isambane.co.za",
        "vusi@isambane.co.za",
    ],
}

REMOVE_BY_LOCATION = {
    "Gwab": [
        "mandla@isambane.co.za",
    ],
}


def _norm(value):
    return str(value or "").strip().lower()


def _ensure_user(email):
    if frappe.db.exists("User", email):
        return

    first_name = (
        email.split("@", 1)[0]
        .replace(".", " ")
        .replace("_", " ")
        .replace("-", " ")
        .title()
    )

    user = frappe.new_doc("User")
    user.email = email
    user.first_name = first_name
    user.enabled = 1
    user.user_type = "Website User"
    user.send_welcome_email = 0

    user.flags.no_welcome_mail = True

    user.insert(ignore_permissions=True)


def execute():
    if not frappe.db.exists(
        "DocType",
        "Plant Breakdown Settings",
    ):
        return

    settings = frappe.get_single(
        "Plant Breakdown Settings"
    )

    changed = False

    # --------------------------------------------------------
    # Validate Locations
    # --------------------------------------------------------

    for location in ADD_BY_LOCATION:
        if not frappe.db.exists(
            "Location",
            location,
        ):
            frappe.throw(
                f"Location {location} does not exist."
            )

    # --------------------------------------------------------
    # Ensure recipient Users exist
    # --------------------------------------------------------

    all_emails = set()

    for emails in ADD_BY_LOCATION.values():
        all_emails.update(emails)

    for email in sorted(all_emails):
        _ensure_user(email)

    # --------------------------------------------------------
    # Remove Mandla from Gwab only
    # --------------------------------------------------------

    for location, emails in REMOVE_BY_LOCATION.items():

        remove_set = {
            _norm(email)
            for email in emails
        }

        for row in list(
            settings.get("recipients_per_site") or []
        ):
            if (
                _norm(row.location) == _norm(location)
                and _norm(row.user) in remove_set
            ):
                settings.remove(row)
                changed = True

    # --------------------------------------------------------
    # Add required recipients without duplicates
    # --------------------------------------------------------

    for location, emails in ADD_BY_LOCATION.items():

        for email in emails:

            exists = False

            for row in (
                settings.get("recipients_per_site")
                or []
            ):
                if (
                    _norm(row.location)
                    == _norm(location)
                    and _norm(row.user)
                    == _norm(email)
                ):
                    exists = True
                    break

            if exists:
                continue

            settings.append(
                "recipients_per_site",
                {
                    "location": location,
                    "user": email,
                },
            )

            changed = True

    if changed:
        settings.save(
            ignore_permissions=True
        )
