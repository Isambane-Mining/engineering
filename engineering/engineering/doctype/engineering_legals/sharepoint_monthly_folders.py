from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

import frappe
import requests

from engineering.engineering.doctype.engineering_legals_sharepoint_config.engineering_legals_sharepoint_config import (
    get_graph_access_token,
    get_sharepoint_config,
    raise_for_graph_error,
    record_sharepoint_status,
)


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

ROOT_FOLDER = "Isambane Mining"

SITES = [
    "klp",
    "gwab",
]

SUBFOLDERS = [
    "01. Automatic Fire Suppression",
    "02. Condition Monitoring",
    "03. Dynamic Brake Testing",
    "04. Earth Leakage Testing & CoC",
    "05. Equipment list",
    "06. FRCS Compliance",
    "07. Load Testing",
    "08. Maintenance Schedules",
    "09. PDS-MPI Maintenance",
    "10. Pressure Vessels",
]


class SharePointClient:
    def __init__(self, config):
        self.config = config
        self.headers = {}
        self.drive_id = None
        self.drive = None
        self.sharepoint_site = None

        self.refresh_token()
        self._load_site_and_drive()

    def __repr__(self):
        # Keep the bearer token in self.headers out of tracebacks.
        return f"<SharePointClient drive_id={self.drive_id}>"

    def refresh_token(self):
        self.headers = {
            "Authorization": "Bearer " + get_graph_access_token("Monthly folder job"),
            "Content-Type": "application/json",
        }

    def request(self, method, url, **kwargs):
        response = requests.request(
            method,
            url,
            headers=self.headers,
            timeout=30,
            **kwargs,
        )

        if response.status_code == 401:
            self.refresh_token()

            response = requests.request(
                method,
                url,
                headers=self.headers,
                timeout=30,
                **kwargs,
            )

        return response

    def _load_site_and_drive(self):
        response = self.request(
            "GET",
            (
                f"{GRAPH_BASE_URL}/sites/"
                f"{self.config['hostname']}:/{self.config['site_path']}"
            ),
        )

        raise_for_graph_error(response)
        self.sharepoint_site = response.json()

        response = self.request(
            "GET",
            (
                f"{GRAPH_BASE_URL}/sites/"
                f"{self.sharepoint_site['id']}/drives"
            ),
        )

        raise_for_graph_error(response)

        drives = response.json().get("value", [])

        for drive in drives:
            current_name = (drive.get("name") or "").strip()

            if (
                current_name.lower()
                == self.config["drive_name"].lower()
            ):
                self.drive = drive
                self.drive_id = drive["id"]
                break

        if not self.drive:
            available = []

            for drive in drives:
                if drive.get("name"):
                    available.append(drive["name"])

            frappe.throw(
                "SharePoint document library "
                f"'{self.config['drive_name']}' was not found. "
                "Available libraries: "
                + ", ".join(available)
            )

    def get_item_by_path(self, folder_path):
        encoded_path = quote(folder_path, safe="/")

        response = self.request(
            "GET",
            (
                f"{GRAPH_BASE_URL}/drives/{self.drive_id}"
                f"/root:/{encoded_path}"
            ),
        )

        if response.status_code == 404:
            return None

        raise_for_graph_error(response)
        return response.json()

    def ensure_folder(self, parent_path, folder_name):
        if parent_path:
            full_path = (
                parent_path.strip("/")
                + "/"
                + folder_name.strip("/")
            )
        else:
            full_path = folder_name.strip("/")

        existing = self.get_item_by_path(full_path)

        if existing:
            if not existing.get("folder"):
                frappe.throw(
                    "A file already exists where a folder "
                    f"is required: {full_path}"
                )

            return {
                "status": "existing",
                "path": full_path,
            }

        if parent_path:
            parent = self.get_item_by_path(parent_path)

            if not parent:
                frappe.throw(
                    "Parent folder does not exist: "
                    + parent_path
                )

            endpoint = (
                f"{GRAPH_BASE_URL}/drives/{self.drive_id}"
                f"/items/{parent['id']}/children"
            )
        else:
            endpoint = (
                f"{GRAPH_BASE_URL}/drives/{self.drive_id}"
                "/root/children"
            )

        response = self.request(
            "POST",
            endpoint,
            json={
                "name": folder_name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "fail",
            },
        )

        if response.status_code == 409:
            existing = self.get_item_by_path(full_path)

            if existing and existing.get("folder"):
                return {
                    "status": "existing",
                    "path": full_path,
                }

            frappe.throw(
                "SharePoint folder conflict: " + full_path
            )

        raise_for_graph_error(response)

        return {
            "status": "created",
            "path": full_path,
        }


def _parse_month(month=None, year=None):
    current_date = frappe.utils.now_datetime()

    selected_year = int(
        year or current_date.year
    )

    if month is None:
        selected_month = int(current_date.month)
    elif isinstance(month, int):
        selected_month = month
    elif str(month).isdigit():
        selected_month = int(month)
    else:
        try:
            selected_month = datetime.strptime(
                str(month).strip(),
                "%B",
            ).month
        except ValueError:
            try:
                selected_month = datetime.strptime(
                    str(month).strip(),
                    "%b",
                ).month
            except ValueError:
                frappe.throw(
                    f"Invalid month: {month}"
                )

    if selected_month < 1 or selected_month > 12:
        frappe.throw(
            f"Invalid month number: {selected_month}"
        )

    month_folder = datetime(
        selected_year,
        selected_month,
        1,
    ).strftime("%m.%b-%y").replace(".Jun-", ".June-")

    return selected_year, selected_month, month_folder


def ensure_month_folders(
    year=None,
    month=None,
):
    """
    Create this SharePoint structure:

    Isambane Mining
        Mon-YY
            klp
                10 standard folders
            gwab
                10 standard folders

    Examples:
        ensure_month_folders()
        ensure_month_folders(year=2027, month=1)
        ensure_month_folders(year=2027, month="January")
    """

    selected_year, selected_month, month_folder = (
        _parse_month(
            month=month,
            year=year,
        )
    )

    config = get_sharepoint_config()
    client = SharePointClient(config)

    created_paths = []
    existing_paths = []

    def ensure(parent_path, folder_name):
        result = client.ensure_folder(
            parent_path=parent_path,
            folder_name=folder_name,
        )

        if result["status"] == "created":
            created_paths.append(result["path"])

            frappe.logger("engineering_legals").info(
                "Created SharePoint folder: "
                + result["path"]
            )
        else:
            existing_paths.append(result["path"])

    ensure("", ROOT_FOLDER)

    month_path = (
        ROOT_FOLDER + "/" + month_folder
    )

    ensure(ROOT_FOLDER, month_folder)

    for site_name in SITES:
        site_path = (
            month_path + "/" + site_name
        )

        ensure(month_path, site_name)

        for subfolder_name in SUBFOLDERS:
            ensure(site_path, subfolder_name)

    result = {
        "year": selected_year,
        "month": selected_month,
        "month_folder": month_folder,
        "root_folder": ROOT_FOLDER,
        "sites": SITES,
        "created_count": len(created_paths),
        "existing_count": len(existing_paths),
        "created_paths": created_paths,
        "existing_paths": existing_paths,
        "sharepoint_site": (
            client.sharepoint_site.get("webUrl")
        ),
        "document_library": client.drive.get("webUrl"),
    }

    frappe.logger("engineering_legals").info(
        "SharePoint monthly folder check completed: "
        + frappe.as_json(result)
    )

    return result


def ensure_all_months_for_year(year=None):
    """
    Create January through December for a selected year.

    Existing folders and files are left unchanged.

    Example:
        ensure_all_months_for_year(year=2026)
    """

    selected_year = int(
        year or frappe.utils.now_datetime().year
    )

    summary = {
        "year": selected_year,
        "months": [],
        "created_count": 0,
        "existing_count": 0,
    }

    for month_number in range(1, 13):
        result = ensure_month_folders(
            year=selected_year,
            month=month_number,
        )

        summary["months"].append(
            result["month_folder"]
        )

        summary["created_count"] += (
            result["created_count"]
        )

        summary["existing_count"] += (
            result["existing_count"]
        )

    return summary


def create_current_month_sharepoint_folders():
    """
    Scheduler entry point.

    Runs daily and ensures the current month's folder exists.
    Existing SharePoint folders and files are not overwritten.
    """

    source = "Monthly folder job"

    try:
        result = ensure_month_folders()
        record_sharepoint_status(source)

        frappe.logger("engineering_legals").info(
            "Scheduled SharePoint folder task completed. "
            f"Folder={result['month_folder']}, "
            f"Created={result['created_count']}, "
            f"Existing={result['existing_count']}"
        )

    except Exception as e:
        record_sharepoint_status(source, error=str(e) or type(e).__name__)
        frappe.log_error(
            title=(
                "Engineering Legals SharePoint "
                "Monthly Folder Error"
            ),
            message=frappe.get_traceback(),
        )

        raise
