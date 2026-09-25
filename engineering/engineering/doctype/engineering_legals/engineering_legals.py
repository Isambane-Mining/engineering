import os
import time
import mimetypes
from typing import Optional
from urllib.parse import quote

import requests
import frappe
from frappe.model.document import Document
from frappe.utils import now, getdate, cint


# Drive Team that will own all Engineering Legals links.
# This must match the Drive Team "Title" exactly.
ENGINEERING_DRIVE_TEAM_TITLE = "Engineering Legals"


NEW_SHAREPOINT_ROOT = "Isambane Mining"

NEW_SHAREPOINT_SITE_MAPPING = {
    "Gwab": "gwab",
    "Klipfontein": "klp",
}

NEW_SHAREPOINT_SECTION_MAPPING = {
    "Fire Suppression": ["01. Automatic Fire Suppression"],

    "Illumination Baseline": ["02. Condition Monitoring"],
    "Noise Level Baseline & Measurement": ["02. Condition Monitoring"],
    "NDT": ["02. Condition Monitoring"],
    "Machine NDT": ["02. Condition Monitoring"],

    "Brake Test": ["03. Dynamic Brake Testing"],
    "Brake Tester Calibration Certificate": [
        "03. Dynamic Brake Testing"
    ],
    "Brake Test Authorisations": [
        "03. Dynamic Brake Testing"
    ],

    "CoC for Containers, Offices, Workshops": [
        "04. Earth Leakage Testing & CoC"
    ],
    "Multi-meter Calibration Certificate": [
        "04. Earth Leakage Testing & CoC"
    ],
    "Authorised LV Person": [
        "04. Earth Leakage Testing & CoC"
    ],
    "Earth Leakage Testing": [
        "04. Earth Leakage Testing & CoC"
    ],

    "FRCS": ["06. FRCS Compliance"],

    "Lifting Equipment": ["07. Load Testing"],

    "Machine Service Records": [
        "08. Maintenance Schedules",
        "Maintenance-Services",
    ],
    "Service Schedule": [
        "08. Maintenance Schedules",
        "Maintenance-Services",
    ],
    "Wearcheck": [
        "08. Maintenance Schedules",
        "Maintenance-Services",
    ],
    "Brake Wear Measurements": [
        "08. Maintenance Schedules",
        "Maintenance-Services",
    ],
    "Tyre Inspection Report": [
        "08. Maintenance Schedules",
        "Tyre Surveys",
    ],
    "C-Track Inspection": [
        "08. Maintenance Schedules",
        "Track Surveys",
    ],
    "Track Surveys": [
        "02. Condition Monitoring",
        "Track Surveys",
    ],

    "PDS": ["09. PDS-MPI Maintenance"],

    "Pressure Vessels": ["10. Pressure Vessels"],
}


class EngineeringLegals(Document):
    """Controller for Engineering Legals DocType."""

    def on_update(self):
        sync_engineering_legals_from_doc(self, "on_update")

    def on_trash(self):
        _engineering_legals_on_trash(self, "on_trash")

    def validate(self):
        """
        Server-side source of truth.
        - expiry_date is ALWAYS recalculated from start_date + section rules
        - invalid combinations are blocked
        - conditional fields are cleared when not relevant
        - expiry is never carried over and never user-editable
        """
        from frappe.utils import add_months

        # Always reset first (prevents stale carry-over)
        self.expiry_date = None

        # Core fields must exist (server enforcement)
        if not self.sections:
            frappe.throw("Section is required.")

        section = (self.sections or "").strip()

        # FLEET NUMBER REQUIREMENT RULE - START
        fleet_optional_sections = {
            "Brake Tester Calibration Certificate",
            "Brake Test Authorisations",
            "CoC for Containers, Offices, Workshops",
            "Multi-meter Calibration Certificate",
            "Authorised LV Person",
            "Earth Leakage Testing",
            "Pressure Vessels",
        }

        if (
            section not in fleet_optional_sections
            and not self.fleet_number
        ):
            frappe.throw(
                "Fleet Number is required for this Section."
            )
        # FLEET NUMBER REQUIREMENT RULE - END


        no_start_date_sections = {
            "Machine Service Records",
            "Service Schedule",
            "Wearcheck",
            "Brake Wear Measurements",
        }

        if section not in no_start_date_sections and not self.start_date:
            frappe.throw("Start Date is required.")

        if section == "Brake Test":
            if not self.vehicle_type:
                frappe.throw("Vehicle Type (LDV/TMM) is required for this Section.")

            months = 1 if self.vehicle_type == "TMM" else 3
            self.expiry_date = add_months(self.start_date, months)

        elif section == "PDS":
            if not self.vehicle_type:
                frappe.throw("Vehicle Type (LDV/TMM) is required for this Section.")

            months = 3 if self.vehicle_type == "TMM" else 4
            self.expiry_date = add_months(self.start_date, months)

        elif section == "FRCS":
            self.expiry_date = add_months(self.start_date, 3)

        elif section in (
            "Brake Tester Calibration Certificate",
            "Brake Test Authorisations",
            "Multi-meter Calibration Certificate",
            "Authorised LV Person",
            "Pressure Vessels",
        ):
            self.expiry_date = add_months(self.start_date, 12)

        elif section == "CoC for Containers, Offices, Workshops":
            self.expiry_date = add_months(self.start_date, 1)

        elif section == "Earth Leakage Testing":
            self.expiry_date = add_months(self.start_date, 3)

        # NEW LEGAL SECTIONS EXPIRY RULES - START
        elif section in (
            "Brake Tester Calibration Certificate",
            "Brake Test Authorisations",
            "Multi-meter Calibration Certificate",
            "Authorised LV Person",
            "Pressure Vessels",
        ):
            # Yearly validity
            self.expiry_date = add_months(self.start_date, 12)

        elif section == "CoC for Containers, Offices, Workshops":
            # Monthly validity
            self.expiry_date = add_months(self.start_date, 1)

        elif section == "Earth Leakage Testing":
            # Quarterly validity
            self.expiry_date = add_months(self.start_date, 3)
        # NEW LEGAL SECTIONS EXPIRY RULES - END

        elif section == "Lifting Equipment":
            if not self.lifting_type:
                frappe.throw("Lifting Type (Inspection/Certificate) is required for this Section.")

            months = 3 if self.lifting_type == "Inspection" else 12
            self.expiry_date = add_months(self.start_date, months)

        elif section in ("NDT", "Machine NDT"):
            self.expiry_date = add_months(self.start_date, 12)

        elif section == "C-Track Inspection":
            self.expiry_date = add_months(self.start_date, 1)

        elif section == "Fire Suppression":
            self.expiry_date = add_months(self.start_date, 3)

        elif section == "Tyre Inspection Report":
            self.expiry_date = add_months(self.start_date, 1)

        elif section == "Illumination Baseline":
            self.expiry_date = add_months(self.start_date, 24)

        elif section == "Noise Level Baseline & Measurement":
            self.expiry_date = add_months(self.start_date, 24)

        elif section == "Brake Wear Measurements":
            if not self.brake_wear_type:
                frappe.throw("Brake Wear Type (ADT/FEL) is required for this Section.")
            self.start_date = None
            self.expiry_date = None

        elif section in ("Machine Service Records", "Service Schedule", "Wearcheck"):
            self.expiry_date = None

        else:
            frappe.throw(f"Unknown Section: {section}")




        # Clear irrelevant fields so nothing stale gets saved (imports/API too)
        if section not in ("Brake Test", "PDS"):
            self.vehicle_type = None

        if section != "Lifting Equipment":
            self.lifting_type = None

        if section != "Brake Wear Measurements":
            self.brake_wear_type = None

        # -----------------------------
        # HSEC integration requirements
        # -----------------------------
        section = (self.sections or "").strip()

        # Always populate external qualification code from Sections
        self.hsec_qualification_id_external = section or None

        # Auto-send only for HSEC sections
        HSEC_SEND_SECTIONS = {"Brake Test", "FRCS"}
        self.hsec_send = 1 if section in HSEC_SEND_SECTIONS else 0

        if getattr(self, "hsec_send", 0):
            # Required by HSEC: Qualification_ID_External
            if not getattr(self, "hsec_qualification_id_external", None):
                frappe.throw("HSEC External Qualification Code is required when 'Send to HSEC' is enabled.")

            # Keep the original creation timestamp only once
            if not self.hsec_inserted_at:
                self.hsec_inserted_at = now()
        else:
            # Keep clean when not sending
            self.hsec_inserted_at = None


def _get_engineering_legals_path_parts(doc: Document):
    """
    Folder path format:
    <site>/<month>/<date>/<section>/<asset>
    """
    site = (doc.site or "Unknown Site").strip() or "Unknown Site"
    section = (doc.sections or "Unclassified").strip() or "Unclassified"
    asset = (doc.fleet_number or "No Fleet").strip() or "No Fleet"

    raw_date = getattr(doc, "start_date", None)
    if raw_date:
        dt = getdate(raw_date)
        month_folder = dt.strftime("%Y-%m")
        date_folder = dt.strftime("%Y-%m-%d")
    else:
        month_folder = "No Month"
        date_folder = "No Date"

    return {
        "site": site,
        "month": month_folder,
        "date": date_folder,
        "section": section,
        "asset": asset,
    }







def remove_drive_links_for_engineering_legals(doc: Document):
    """
    Deactivate Drive File link(s) created for this doc attachment.
    Safer than deleting: sets is_active=0.
    """

    if "drive" not in frappe.get_installed_apps():
        return

    file_url = getattr(doc, "attach_paper", None)
    if not file_url:
        return

    # Match the exact same URL format you used when creating the link
    public_url = file_url.replace("/private/files/", "/files/")
    absolute_url = frappe.utils.get_url(public_url)

    team = _get_default_drive_team()

    # Deactivate any matching Drive link rows (avoid brittle folder lookups)
    frappe.db.sql(
        """
        UPDATE `tabDrive File`
        SET is_active = 0
        WHERE team = %s
          AND is_link = 1
          AND is_active = 1
          AND path = %s
        """,
        (team, absolute_url),
    )

    frappe.db.commit()



def move_engineering_legal_file_to_folder(doc: Document):
    """Move the File linked in doc.attach_paper into the desired folder tree."""

    file_url = getattr(doc, "attach_paper", None)
    if not file_url:
        return

    parts = _get_engineering_legals_path_parts(doc)

    root_folder = "Home/Engineering Legals"
    target_folder_path = os.path.join(
        root_folder,
        parts["site"],
        parts["month"],
        parts["date"],
        parts["section"],
        parts["asset"],
    )

    target_folder_name = ensure_file_folder_tree(target_folder_path)

    file_doc = frappe.get_value(
        "File",
        {
            "file_url": file_url,
            "attached_to_doctype": doc.doctype,
            "attached_to_name": doc.name,
        },
        ["name", "folder"],
        as_dict=True,
    )

    if not file_doc:
        return

    file_name = file_doc.name

    # Keep the original privacy/file_url as-is.
    # Changing DB values alone does not move the physical file on disk.
    for attempt in range(2):
        fresh_file_doc = frappe.get_doc("File", file_name)
        fresh_file_doc.reload()

        if fresh_file_doc.folder == target_folder_name:
            return

        try:
            fresh_file_doc.db_set("folder", target_folder_name, update_modified=False)
            return
        except Exception:
            if attempt == 0:
                frappe.db.rollback()
                continue
            raise


def _safe_sharepoint_status_update(docname: str, values: dict):
    for attempt in range(3):
        try:
            frappe.db.sql(
                """
                UPDATE `tabEngineering Legals`
                SET
                    sharepoint_synced = %s,
                    sharepoint_synced_at = %s,
                    sharepoint_sync_error = %s
                WHERE name = %s
                """,
                (
                    values.get("sharepoint_synced"),
                    values.get("sharepoint_synced_at"),
                    values.get("sharepoint_sync_error"),
                    docname,
                ),
            )
            frappe.db.commit()
            return
        except Exception:
            frappe.db.rollback()
            if attempt < 2:
                time.sleep(0.5)
                continue

            frappe.log_error(
                title="Engineering Legals SharePoint status update failed",
                message=frappe.get_traceback(),
            )


def _clear_sharepoint_sync_status(docname: str):
    _safe_sharepoint_status_update(
        docname,
        {
            "sharepoint_synced": 0,
            "sharepoint_synced_at": None,
            "sharepoint_sync_error": None,
        },
    )


def _mark_sharepoint_sync_success(docname: str):
    _safe_sharepoint_status_update(
        docname,
        {
            "sharepoint_synced": 1,
            "sharepoint_synced_at": now(),
            "sharepoint_sync_error": None,
        },
    )


def _mark_sharepoint_sync_failure(docname: str, error_message: str):
    _safe_sharepoint_status_update(
        docname,
        {
            "sharepoint_synced": 0,
            "sharepoint_synced_at": None,
            "sharepoint_sync_error": (error_message or "")[:1400],
        },
    )



def _sanitize_sharepoint_part(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "Unknown"

    for ch in ['"', '*', ':', '<', '>', '?', '/', '\\', '|']:
        value = value.replace(ch, "-")

    return value.strip().rstrip(".") or "Unknown"


def _get_sharepoint_settings() -> dict:
    settings = {
        "tenant_id": frappe.conf.get("ms_graph_tenant_id"),
        "client_id": frappe.conf.get("ms_graph_client_id"),
        "client_secret": frappe.conf.get("ms_graph_client_secret"),
        "hostname": frappe.conf.get("sharepoint_hostname"),
        "site_path": frappe.conf.get("sharepoint_site_path"),
        "drive_name": frappe.conf.get("sharepoint_drive_name") or "Documents",
        "root_folder": frappe.conf.get("sharepoint_root_folder") or "Engineering Legals",
    }

    missing = [k for k, v in settings.items() if not v and k not in ("drive_name", "root_folder")]
    if missing:
        frappe.throw("Missing SharePoint/Graph settings in site_config: " + ", ".join(missing))

    return settings


def _get_graph_access_token(settings: dict) -> str:
    token_url = f"https://login.microsoftonline.com/{settings['tenant_id']}/oauth2/v2.0/token"

    response = requests.post(
        token_url,
        data={
            "client_id": settings["client_id"],
            "client_secret": settings["client_secret"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )

    if not response.ok:
        frappe.throw(f"Graph token request failed: {response.status_code} - {response.text}")

    return response.json()["access_token"]


def _graph_request(method: str, url: str, token: str, **kwargs):
    headers = kwargs.pop("headers", {}) or {}
    headers["Authorization"] = f"Bearer {token}"

    response = requests.request(method, url, headers=headers, timeout=60, **kwargs)

    if not response.ok:

        # SharePoint item/folder already exists.
        # Treat as non-fatal so uploads do not fail.
        if response.status_code == 409:
            try:
                return response.json()
            except Exception:
                return {
                    "status_code": 409,
                    "text": response.text,
                }

        frappe.throw(f"Graph request failed: {response.status_code} - {response.text}")

    if response.text:
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type.lower():
            return response.json()

    return None


def _get_sharepoint_site_id(settings: dict, token: str) -> str:
    site_path = settings["site_path"].lstrip("/")
    url = f"https://graph.microsoft.com/v1.0/sites/{settings['hostname']}:/{site_path}"
    data = _graph_request("GET", url, token)
    return data["id"]


def _get_sharepoint_drive_id(settings: dict, site_id: str, token: str) -> str:
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    data = _graph_request("GET", url, token)

    target_name = (settings["drive_name"] or "").strip().lower()

    for row in data.get("value", []):
        if (row.get("name") or "").strip().lower() == target_name:
            return row["id"]

    available = ", ".join([row.get("name") or "" for row in data.get("value", [])])
    frappe.throw(
        f"SharePoint document library '{settings['drive_name']}' not found. Available: {available}"
    )


def _get_sharepoint_folder_parts(doc: Document, settings: dict) -> list[str]:
    """Return the existing/legacy SharePoint folder path."""
    site = (doc.site or "Unknown Site").strip() or "Unknown Site"
    section = (doc.sections or "Unclassified").strip() or "Unclassified"

    raw_date = getattr(doc, "start_date", None)
    if raw_date:
        dt = getdate(raw_date)
        year_folder = dt.strftime("%Y")
        month_folder = dt.strftime("%B %Y")
    else:
        year_folder = "No Year"
        month_folder = "No Month"

    return [
        _sanitize_sharepoint_part(site),
        _sanitize_sharepoint_part(year_folder),
        _sanitize_sharepoint_part(section),
        _sanitize_sharepoint_part(month_folder),
    ]


def _get_new_sharepoint_folder_parts(doc: Document) -> Optional[list[str]]:
    """
    Return the new monthly SharePoint path.

    Only sites and sections configured in the new structure are uploaded
    here. All records still upload to the legacy path as well.
    """
    site = (getattr(doc, "site", None) or "").strip()
    section = (getattr(doc, "sections", None) or "").strip()

    new_site = NEW_SHAREPOINT_SITE_MAPPING.get(site)
    category_parts = NEW_SHAREPOINT_SECTION_MAPPING.get(section)

    if not new_site or not category_parts:
        return None

    raw_date = getattr(doc, "start_date", None)

    if not raw_date:
        raw_date = getattr(doc, "creation", None)

    if raw_date:
        month_folder = getdate(raw_date).strftime("%m.%b-%y").replace(".Jun-", ".June-")
    else:
        month_folder = "No-Month"

    return [
        NEW_SHAREPOINT_ROOT,
        month_folder,
        new_site,
        *category_parts,
    ]

def _ensure_sharepoint_folder(drive_id: str, folder_parts: list[str], token: str):
    parent_item_id = "root"

    for folder_name in folder_parts:
        encoded_name = quote(folder_name)
        lookup_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{parent_item_id}:/{encoded_name}"

        response = requests.get(
            lookup_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

        if response.status_code == 200:
            parent_item_id = response.json()["id"]
            continue

        if response.status_code != 404:
            frappe.throw(f"Graph folder lookup failed: {response.status_code} - {response.text}")

        create_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{parent_item_id}/children"
        payload = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "replace",
        }
        created = _graph_request("POST", create_url, token, json=payload)
        parent_item_id = created["id"]

    return parent_item_id


def upload_engineering_legals_to_sharepoint(doc: Document, source_file_doc: Optional[Document] = None):
    file_doc = source_file_doc

    if not file_doc:
        file_url = getattr(doc, "attach_paper", None)
        if not file_url:
            return

        file_row = frappe.get_value(
            "File",
            {
                "attached_to_doctype": doc.doctype,
                "attached_to_name": doc.name,
                "file_url": file_url,
                "is_folder": 0,
            },
            ["name", "file_name"],
            as_dict=True,
        )

        if not file_row:
            return

        file_doc = frappe.get_doc("File", file_row.name)

    content = file_doc.get_content()
    if content is None:
        frappe.throw(f"Could not read attached file content: {file_doc.file_url}")

    if isinstance(content, str):
        data = content.encode("utf-8")
    else:
        data = content

    settings = _get_sharepoint_settings()
    token = _get_graph_access_token(settings)
    site_id = _get_sharepoint_site_id(settings, token)
    drive_id = _get_sharepoint_drive_id(settings, site_id, token)

    folder_parts = _get_sharepoint_folder_parts(doc, settings)
    parent_item_id = _ensure_sharepoint_folder(drive_id, folder_parts, token)

    raw_date = getattr(doc, "start_date", None)
    if raw_date:
        date_part = getdate(raw_date).strftime("%Y-%m-%d")
    else:
        date_part = "No-Date"

    original_ext = os.path.splitext(file_doc.file_name or "")[1] or ".pdf"

    filename = _sanitize_sharepoint_part(
        f"{(doc.fleet_number or 'No Fleet').strip()}-{(doc.sections or 'Unclassified').strip()}-{date_part}{original_ext}"
    )
    encoded_filename = quote(filename)

    upload_url = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
        f"/items/{parent_item_id}:/{encoded_filename}:/content"
    )
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # Upload to the existing legacy SharePoint folder.
    _graph_request(
        "PUT",
        upload_url,
        token,
        data=data,
        headers={"Content-Type": mime_type},
    )

    # Also upload Gwab and Klipfontein records into the new monthly
    # Isambane Mining folder structure.
    new_folder_parts = _get_new_sharepoint_folder_parts(doc)

    if new_folder_parts:
        new_parent_item_id = _ensure_sharepoint_folder(
            drive_id,
            new_folder_parts,
            token,
        )

        new_upload_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/items/{new_parent_item_id}:/{encoded_filename}:/content"
        )

        _graph_request(
            "PUT",
            new_upload_url,
            token,
            data=data,
            headers={"Content-Type": mime_type},
        )




def ensure_file_folder_tree(path: str) -> str:
    """
    Ensure that a nested folder path like
    'Home/Engineering Legals/GWAB/NDT/EX014'
    exists in the File DocType.

    Returns the File.name of the deepest folder.
    """

    parts = path.split("/")
    if not parts or parts[0] != "Home":
        raise ValueError("Folder path must start with 'Home'")

    parent_name = "Home"

    # Walk through Engineering Legals / Site / Section / Fleet
    for part in parts[1:]:
        if not part:
            continue

        folder_name = f"{parent_name}/{part}"

        existing = frappe.get_value(
            "File",
            {"name": folder_name, "is_folder": 1},
            "name",
        )

        if existing:
            parent_name = existing
            continue

        # Create new folder
        folder_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": part,
                "is_folder": 1,
                "folder": parent_name,
            }
        )
        folder_doc.insert(ignore_permissions=True)
        parent_name = folder_doc.name

    return parent_name


# ----------------------------------------------------------------------
# Frappe Drive integration
# ----------------------------------------------------------------------


def create_drive_link_for_engineering_legals(doc: Document):
    """
    Create / update a Drive File *link* for this Engineering Legals document.

       Drive folder structure:
        Home / Engineering Legals / <Site> / <Section> / <Fleet Number> /


    Inside that folder we create a Drive File with:
        is_group = 0 (file)
        is_link  = 1 (link entity)
        path     = File.file_url (ERPNext file URL)
    """

    # If Drive app is not installed, do nothing
    if "drive" not in frappe.get_installed_apps():
        return

    # No attachment? Nothing to sync.
    file_url = getattr(doc, "attach_paper", None)
    if not file_url:
        return

    # Always work with the PUBLIC url form for Drive
    public_url = file_url.replace("/private/files/", "/files/")

    # Find the File record for this attachment (should already use /files/ after move)
    file_row = frappe.db.get_value(
        "File",
        {"file_url": public_url},
        ["name", "file_name", "file_size", "file_type", "file_url"],
        as_dict=True,
    )
    if not file_row:
        return

    team = _get_default_drive_team()
    home = _get_drive_home_folder(team)

    # Build folder path: Engineering Legals / <Site> / <Month> / <Date> / <Section> / <Asset>
    parts = _get_engineering_legals_path_parts(doc)

    root_title = "Engineering Legals"
    root_folder = _get_or_create_drive_folder(root_title, home, team)
    site_folder = _get_or_create_drive_folder(parts["site"], root_folder, team)
    month_folder = _get_or_create_drive_folder(parts["month"], site_folder, team)
    date_folder = _get_or_create_drive_folder(parts["date"], month_folder, team)
    section_folder = _get_or_create_drive_folder(parts["section"], date_folder, team)
    asset_folder = _get_or_create_drive_folder(parts["asset"], section_folder, team)


    # Avoid creating duplicate links for the same file & folder
    public_url = file_row.file_url.replace("/private/files/", "/files/")
    # Drive links work best with an ABSOLUTE URL
    absolute_url = frappe.utils.get_url(public_url)



    existing = frappe.db.exists(
        "Drive File",
        {
            "team": team,
            "parent_entity": asset_folder,
            "is_link": 1,
            "path": absolute_url,
            "is_active": 1,
        },
    )

    if existing:
        return


    # Finally, create the Drive File link (always using PUBLIC url)
    public_url = file_row.file_url.replace("/private/files/", "/files/")

    link_doc = frappe.get_doc(
        {
            "doctype": "Drive File",
            "title": file_row.file_name or "Attachment",
            "team": team,
            "parent_entity": asset_folder,
            "is_group": 0,   # file
            "is_link": 1,    # link entity
            "is_active": 1,
            "is_private": 0,  # visible to team
            "path": absolute_url,  # ABSOLUTE url so Drive can open it
            "file_size": file_row.file_size or 0,

            # Better MIME detection (File.file_type is often blank / not a real MIME)
            "mime_type": (mimetypes.guess_type(file_row.file_name or "")[0] or (file_row.file_type or "")),
        }
    )



    link_doc.insert(ignore_permissions=True)


def _get_default_drive_team() -> str:
    """
    Always use the specific Drive Team configured for Engineering Legals.

    We look it up by Drive Team *Title* so we don't accidentally use
    someone else's personal team.
    """
    team = frappe.db.get_value(
        "Drive Team",
        {"title": ENGINEERING_DRIVE_TEAM_TITLE},
        "name",
    )

    if not team:
        frappe.throw(
            f"Drive Team '{ENGINEERING_DRIVE_TEAM_TITLE}' not found. "
            "Please create it in Drive > Drive Team or update ENGINEERING_DRIVE_TEAM_TITLE "
            "in engineering_legals.py."
        )

    return team



def _get_drive_home_folder(team: str) -> str:
    """
    Get the 'Home' folder for this team in Drive.
    """
    home = frappe.db.get_value(
        "Drive File",
        {
            "title": "Home",
            "is_group": 1,
            "team": team,
            "is_active": 1,
        },
        "name",
    )
    if home:
        return home

    # Fallback: create a Home folder if missing
    home_doc = frappe.get_doc(
        {
            "doctype": "Drive File",
            "title": "Home",
            "parent_entity": None,
            "is_group": 1,
            "is_link": 0,
            "is_active": 1,
            "team": team,
            "owner": frappe.session.user,
            "is_private": 0,
        }
    )
    home_doc.insert(ignore_permissions=True)
    return home_doc.name


def _get_or_create_drive_folder(title: str, parent_entity: Optional[str], team: str) -> str:
    """
    Find a Drive folder (Drive File with is_group=1) by title under parent_entity.
    If missing, create it and return its name.
    """
    existing = frappe.db.get_value(
        "Drive File",
        {
            "title": title,
            "parent_entity": parent_entity,
            "is_group": 1,
            "is_active": 1,
            "team": team,
        },
        "name",
    )
    if existing:
        return existing

    folder = frappe.get_doc(
        {
            "doctype": "Drive File",
            "title": title,
            "parent_entity": parent_entity,
            "is_group": 1,
            "is_link": 0,
            "is_active": 1,
            "team": team,
            "owner": frappe.session.user,
            "is_private": 0,
        }
    )
    folder.insert(ignore_permissions=True)
    return folder.name

# -------------------------------------------------------------------
# Module-level doc_event hooks (required if hooks.py points to
# engineering.engineering.doctype.engineering_legals.engineering_legals.on_update)
# -------------------------------------------------------------------

def sync_engineering_legals_from_file(file_doc, method=None):
    try:
        if getattr(file_doc, "is_folder", 0):
            return

        if getattr(file_doc, "attached_to_doctype", None) != "Engineering Legals":
            return

        attached_name = getattr(file_doc, "attached_to_name", None)
        if not attached_name:
            return

        if str(attached_name).startswith("new-engineering-legals-"):
            return

        if not frappe.db.exists("Engineering Legals", attached_name):
            return

        _clear_sharepoint_sync_status(attached_name)

        doc = frappe.get_doc("Engineering Legals", attached_name)

        if getattr(file_doc, "file_url", None) and doc.attach_paper != file_doc.file_url:
            doc.db_set("attach_paper", file_doc.file_url, update_modified=False)
            doc.reload()

        upload_engineering_legals_to_sharepoint(doc, source_file_doc=file_doc)
        move_engineering_legal_file_to_folder(doc)
        _mark_sharepoint_sync_success(attached_name)

    except Exception:
        attached_name = getattr(file_doc, "attached_to_name", None)
        if attached_name and frappe.db.exists("Engineering Legals", attached_name):
            _mark_sharepoint_sync_failure(attached_name, frappe.get_traceback())

        frappe.log_error(
            title="Engineering Legals file-trigger sync failed",
            message=frappe.get_traceback(),
        )

        if getattr(file_doc, "attached_to_doctype", None) != "Engineering Legals":
            return

        attached_name = getattr(file_doc, "attached_to_name", None)
        if not attached_name:
            return

        if str(attached_name).startswith("new-engineering-legals-"):
            return

        if not frappe.db.exists("Engineering Legals", attached_name):
            return

        doc = frappe.get_doc("Engineering Legals", attached_name)

        if getattr(file_doc, "file_url", None) and doc.attach_paper != file_doc.file_url:
            doc.db_set("attach_paper", file_doc.file_url, update_modified=False)
            doc.reload()

        upload_engineering_legals_to_sharepoint(doc, source_file_doc=file_doc)
        move_engineering_legal_file_to_folder(doc)

    except Exception:
        frappe.log_error(
            title="Engineering Legals file-trigger sync failed",
            message=frappe.get_traceback(),
        )

def sync_engineering_legals_from_doc(doc, method=None):
    try:
        if not getattr(doc, "attach_paper", None):
            return

        _clear_sharepoint_sync_status(doc.name)

        frappe.enqueue(
            "engineering.engineering.doctype.engineering_legals.engineering_legals.run_engineering_legals_sharepoint_sync",
            queue="short",
            timeout=300,
            enqueue_after_commit=True,
            docname=doc.name,
        )

    except Exception:
        frappe.log_error(
            title="Engineering Legals doc-trigger enqueue failed",
            message=frappe.get_traceback(),
        )




def run_engineering_legals_sharepoint_sync(docname: str):
    try:
        if not docname:
            return

        if not frappe.db.exists("Engineering Legals", docname):
            return

        doc = frappe.get_doc("Engineering Legals", docname)

        if not getattr(doc, "attach_paper", None):
            _mark_sharepoint_sync_failure(docname, "Attach Paper is empty.")
            return

        file_row = frappe.get_value(
            "File",
            {
                "attached_to_doctype": doc.doctype,
                "attached_to_name": doc.name,
                "is_folder": 0,
            },
            ["name"],
            as_dict=True,
            order_by="creation desc",
        )

        if not file_row:
            _mark_sharepoint_sync_failure(docname, "No File row found for attached document.")
            return

        file_doc = frappe.get_doc("File", file_row.name)

        if getattr(file_doc, "file_url", None) and doc.attach_paper != file_doc.file_url:
            doc.db_set("attach_paper", file_doc.file_url, update_modified=False)
            doc.reload()

        upload_engineering_legals_to_sharepoint(doc, source_file_doc=file_doc)
        _mark_sharepoint_sync_success(docname)

        try:
            move_engineering_legal_file_to_folder(doc)
        except Exception:
            frappe.log_error(
                title="Engineering Legals file move warning",
                message=frappe.get_traceback(),
            )

    except Exception:
        _mark_sharepoint_sync_failure(docname, frappe.get_traceback())
        frappe.log_error(
            title="Engineering Legals background SharePoint sync failed",
            message=frappe.get_traceback(),
        )







def queue_unsynced_engineering_legals():
    rows = frappe.get_all(
        "Engineering Legals",
        filters={
            "attach_paper": ["is", "set"],
            "sharepoint_synced": 0,
            "docstatus": ["<", 2],
        },
        pluck="name",
        order_by="modified asc",
        limit_page_length=200,
    )

    for name in rows:
        frappe.enqueue(
            "engineering.engineering.doctype.engineering_legals.engineering_legals.run_engineering_legals_sharepoint_sync",
            queue="short",
            timeout=300,
            enqueue_after_commit=False,
            docname=name,
        )







def _engineering_legals_on_trash(doc, method=None):
    pass
