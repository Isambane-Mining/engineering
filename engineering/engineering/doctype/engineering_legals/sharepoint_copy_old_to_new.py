from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import quote

import frappe
import requests

from engineering.engineering.doctype.engineering_legals_sharepoint_config.engineering_legals_sharepoint_config import (
    get_graph_access_token,
    get_sharepoint_config,
    raise_for_graph_error,
)


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
NEW_ROOT_FOLDER = "Isambane Mining"

SITE_MAPPING = {
    "Gwab": "gwab",
    "Klipfontein": "klp",
}

FOLDER_MAPPING = {
    "Fire Suppression": "01. Automatic Fire Suppression",

    "Illumination Baseline": "02. Condition Monitoring",
    "Noise Level Baseline & Measurement": "02. Condition Monitoring",
    "Non-Destructive Testing Report (NDT)": "02. Condition Monitoring",
    "Machine NDT": "02. Condition Monitoring",

    "Brake Test": "03. Dynamic Brake Testing",
    "FRCS": "06. FRCS Compliance",
    "Lifting Equipment": "07. Load Testing",
    "Machine Service Records": "08. Maintenance Schedules",
    "Tyre Inspection Report": "08. Maintenance Schedules",
    "C-Track Inspection": "08. Maintenance Schedules",
    "PDS": "09. PDS-MPI Maintenance",
}

MAINTENANCE_SUBFOLDER_MAPPING = {
    "Machine Service Records": "Maintenance-Services",
    "Tyre Inspection Report": "Tyre Surveys",
    "C-Track Inspection": "Track Surveys",
}


class SharePointClient:
    def __init__(self, config):
        self.config = config
        self.headers = {}
        self.drive = None
        self.drive_id = None
        self.site = None

        self.refresh_token()
        self.load_site_and_drive()

    def __repr__(self):
        # Keep the bearer token in self.headers out of tracebacks.
        return f"<SharePointClient drive_id={self.drive_id}>"

    def refresh_token(self):
        self.headers = {
            "Authorization": "Bearer " + get_graph_access_token("Old-to-new folder copy"),
            "Content-Type": "application/json",
        }

    def request(self, method, url, **kwargs):
        response = requests.request(
            method,
            url,
            headers=self.headers,
            timeout=60,
            **kwargs,
        )

        if response.status_code == 401:
            self.refresh_token()

            response = requests.request(
                method,
                url,
                headers=self.headers,
                timeout=60,
                **kwargs,
            )

        return response

    def load_site_and_drive(self):
        response = self.request(
            "GET",
            (
                f"{GRAPH_BASE_URL}/sites/"
                f"{self.config['hostname']}:/{self.config['site_path']}"
            ),
        )

        raise_for_graph_error(response)
        self.site = response.json()

        response = self.request(
            "GET",
            f"{GRAPH_BASE_URL}/sites/{self.site['id']}/drives",
        )

        raise_for_graph_error(response)

        for drive in response.json().get("value", []):
            drive_name = (drive.get("name") or "").strip()

            if (
                drive_name.lower()
                == self.config["drive_name"].lower()
            ):
                self.drive = drive
                self.drive_id = drive["id"]
                break

        if not self.drive:
            frappe.throw(
                "SharePoint document library not found: "
                + self.config["drive_name"]
            )

    def get_item_by_path(self, path):
        encoded_path = quote(path.strip("/"), safe="/")

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

    def list_children(self, item_id):
        items = []
        url = (
            f"{GRAPH_BASE_URL}/drives/{self.drive_id}"
            f"/items/{item_id}/children?$top=200"
        )

        while url:
            response = self.request("GET", url)
            raise_for_graph_error(response)

            data = response.json()
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")

        return items

    def ensure_folder(self, parent_path, folder_name):
        if parent_path:
            full_path = (
                parent_path.rstrip("/")
                + "/"
                + folder_name
            )
        else:
            full_path = folder_name

        existing = self.get_item_by_path(full_path)

        if existing:
            if not existing.get("folder"):
                frappe.throw(
                    "A file exists where a folder is required: "
                    + full_path
                )

            return existing

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

            if existing:
                return existing

        raise_for_graph_error(response)
        return response.json()

    def copy_item(self, item_id, destination_folder_id):
        endpoint = (
            f"{GRAPH_BASE_URL}/drives/{self.drive_id}"
            f"/items/{item_id}/copy"
            "?@microsoft.graph.conflictBehavior=fail"
        )

        response = self.request(
            "POST",
            endpoint,
            json={
                "parentReference": {
                    "driveId": self.drive_id,
                    "id": destination_folder_id,
                }
            },
        )

        if response.status_code not in (200, 201, 202):
            raise_for_graph_error(response)

        return response.headers.get("Location")


def _month_folder_name(year, month_number):
    return datetime(
        int(year),
        int(month_number),
        1,
    ).strftime("%m.%b-%y").replace(".Jun-", ".June-")


def _old_month_folder_name(year, month_number):
    return datetime(
        int(year),
        int(month_number),
        1,
    ).strftime("%B %Y")


def _destination_path(
    year,
    month_number,
    old_site,
    old_section,
):
    month_folder = _month_folder_name(
        year,
        month_number,
    )

    new_site = SITE_MAPPING[old_site]
    new_category = FOLDER_MAPPING[old_section]

    path = (
        f"{NEW_ROOT_FOLDER}/"
        f"{month_folder}/"
        f"{new_site}/"
        f"{new_category}"
    )

    maintenance_subfolder = (
        MAINTENANCE_SUBFOLDER_MAPPING.get(old_section)
    )

    if maintenance_subfolder:
        path += "/" + maintenance_subfolder

    return path


def _ensure_destination_tree(
    client,
    year,
    month_number,
    old_site,
    old_section,
):
    month_folder = _month_folder_name(
        year,
        month_number,
    )

    new_site = SITE_MAPPING[old_site]
    new_category = FOLDER_MAPPING[old_section]

    client.ensure_folder("", NEW_ROOT_FOLDER)

    month_path = f"{NEW_ROOT_FOLDER}/{month_folder}"
    client.ensure_folder(
        NEW_ROOT_FOLDER,
        month_folder,
    )

    site_path = f"{month_path}/{new_site}"
    client.ensure_folder(
        month_path,
        new_site,
    )

    category_path = f"{site_path}/{new_category}"
    client.ensure_folder(
        site_path,
        new_category,
    )

    maintenance_subfolder = (
        MAINTENANCE_SUBFOLDER_MAPPING.get(old_section)
    )

    if maintenance_subfolder:
        client.ensure_folder(
            category_path,
            maintenance_subfolder,
        )


def _copy_folder_contents_recursive(
    client,
    source_folder,
    destination_path,
    dry_run,
    results,
):
    destination_folder = client.get_item_by_path(
        destination_path
    )

    if not destination_folder:
        frappe.throw(
            "Destination folder not found: "
            + destination_path
        )

    children = client.list_children(
        source_folder["id"]
    )

    for child in children:
        child_name = child.get("name") or "Unnamed"

        destination_item_path = (
            destination_path.rstrip("/")
            + "/"
            + child_name
        )

        existing = client.get_item_by_path(
            destination_item_path
        )

        source_web_url = child.get("webUrl")
        destination_web_url = (
            destination_folder.get("webUrl")
        )

        if existing:
            results["skipped_existing"].append({
                "name": child_name,
                "source": source_web_url,
                "destination": destination_item_path,
            })

            print(
                "SKIP EXISTS:",
                destination_item_path,
            )
            continue

        if child.get("folder"):
            if dry_run:
                results["planned"].append({
                    "type": "folder",
                    "source": source_web_url,
                    "destination": destination_item_path,
                })

                print(
                    "PLAN FOLDER COPY:",
                    destination_item_path,
                )
                continue

            monitor_url = client.copy_item(
                child["id"],
                destination_folder["id"],
            )

            results["copied"].append({
                "type": "folder",
                "name": child_name,
                "source": source_web_url,
                "destination": destination_web_url,
                "monitor_url": monitor_url,
            })

            print(
                "COPY QUEUED:",
                destination_item_path,
            )

            time.sleep(0.3)
            continue

        if dry_run:
            results["planned"].append({
                "type": "file",
                "source": source_web_url,
                "destination": destination_item_path,
            })

            print(
                "PLAN FILE COPY:",
                destination_item_path,
            )
            continue

        monitor_url = client.copy_item(
            child["id"],
            destination_folder["id"],
        )

        results["copied"].append({
            "type": "file",
            "name": child_name,
            "source": source_web_url,
            "destination": destination_web_url,
            "monitor_url": monitor_url,
        })

        print(
            "COPY QUEUED:",
            destination_item_path,
        )

        time.sleep(0.3)


def copy_old_documents_to_new(
    year=2026,
    dry_run=True,
):
    """
    Copy documents from the old Engineering Legals paths
    into the new Isambane Mining folder structure.

    Old source format:
        Site/Year/Section/Month Year

    New destination format:
        Isambane Mining/Mon-YY/site/category

    The source is never moved, renamed or deleted.

    Dry-run:
        copy_old_documents_to_new(
            year=2026,
            dry_run=True,
        )

    Actual copy:
        copy_old_documents_to_new(
            year=2026,
            dry_run=False,
        )
    """

    if isinstance(dry_run, str):
        dry_run = dry_run.lower() in (
            "1",
            "true",
            "yes",
            "y",
        )

    year = int(year)

    client = SharePointClient(
        get_sharepoint_config()
    )

    results = {
        "year": year,
        "dry_run": dry_run,
        "source_folders_found": [],
        "source_folders_missing": [],
        "planned": [],
        "copied": [],
        "skipped_existing": [],
    }

    for month_number in range(1, 13):
        old_month_name = _old_month_folder_name(
            year,
            month_number,
        )

        for old_site in SITE_MAPPING:
            for old_section in FOLDER_MAPPING:
                old_path = (
                    f"{old_site}/"
                    f"{year}/"
                    f"{old_section}/"
                    f"{old_month_name}"
                )

                source_folder = client.get_item_by_path(
                    old_path
                )

                if not source_folder:
                    results[
                        "source_folders_missing"
                    ].append(old_path)

                    print(
                        "SOURCE MISSING:",
                        old_path,
                    )
                    continue

                results[
                    "source_folders_found"
                ].append(old_path)

                destination_path = _destination_path(
                    year=year,
                    month_number=month_number,
                    old_site=old_site,
                    old_section=old_section,
                )

                print()
                print("SOURCE      :", old_path)
                print("DESTINATION :", destination_path)

                _ensure_destination_tree(
                    client=client,
                    year=year,
                    month_number=month_number,
                    old_site=old_site,
                    old_section=old_section,
                )

                _copy_folder_contents_recursive(
                    client=client,
                    source_folder=source_folder,
                    destination_path=destination_path,
                    dry_run=dry_run,
                    results=results,
                )

    results["source_found_count"] = len(
        results["source_folders_found"]
    )

    results["source_missing_count"] = len(
        results["source_folders_missing"]
    )

    results["planned_count"] = len(
        results["planned"]
    )

    results["copied_count"] = len(
        results["copied"]
    )

    results["skipped_existing_count"] = len(
        results["skipped_existing"]
    )

    print()
    print("=== MIGRATION SUMMARY ===")
    print("Dry run:", results["dry_run"])
    print(
        "Source folders found:",
        results["source_found_count"],
    )
    print(
        "Source folders missing:",
        results["source_missing_count"],
    )
    print(
        "Planned copies:",
        results["planned_count"],
    )
    print(
        "Queued copies:",
        results["copied_count"],
    )
    print(
        "Skipped existing:",
        results["skipped_existing_count"],
    )
    print("Old source folders were not changed.")

    return results
