# Copyright (c) 2026, BuFf0k and contributors
# For license information, please see license.txt

"""Single source of SharePoint / Microsoft Graph credentials for Engineering Legals.

Every SharePoint integration (per-record upload, monthly folders, monthly
frequency sync, the one-off copy scripts) reads its configuration through
get_sharepoint_config() and its token through get_graph_access_token().

The client secret is never returned from get_sharepoint_config() and never
stored on an object or in a named local: Frappe's traceback-with-variables
dumps object attributes in full, which is how the old site_config secret
leaked into System Health.
"""

import requests

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
from frappe.utils.password import get_decrypted_password

DOCTYPE = "Engineering Legals SharePoint Config"
TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

# AADSTS codes that mean the stored secret itself is unusable.
_SECRET_ERROR_CODES = ("AADSTS7000222", "AADSTS7000215")


class SharePointAuthError(frappe.ValidationError):
	pass


class EngineeringLegalsSharePointConfig(Document):
	def validate(self):
		self.hostname = (
			(self.hostname or "").strip().replace("https://", "").replace("http://", "").rstrip("/")
		)
		self.site_path = (self.site_path or "").strip().strip("/")
		self.drive_name = (self.drive_name or "").strip() or "Documents"


def get_sharepoint_config() -> dict:
	"""Non-secret SharePoint settings. Throws if anything required is missing."""
	values = frappe.db.get_singles_dict(DOCTYPE)

	config = {
		"tenant_id": (values.get("tenant_id") or "").strip(),
		"client_id": (values.get("client_id") or "").strip(),
		"hostname": (values.get("hostname") or "").strip(),
		"site_path": (values.get("site_path") or "").strip().strip("/"),
		"drive_name": (values.get("drive_name") or "").strip() or "Documents",
	}

	missing = [key for key in ("tenant_id", "client_id", "hostname", "site_path") if not config[key]]
	if missing:
		frappe.throw(
			f"{DOCTYPE} is incomplete (missing: {', '.join(missing)}). "
			"Set it under Engineering > Settings > SharePoint Config."
		)

	return config


def get_graph_access_token(source: str) -> str:
	"""Client-credentials token for Microsoft Graph.

	On failure, records the Microsoft error on the config and raises
	SharePointAuthError with Microsoft's own explanation (AADSTS code).
	"""
	config = get_sharepoint_config()

	if not get_decrypted_password(DOCTYPE, DOCTYPE, "client_secret", raise_exception=False):
		message = f"No Client Secret is set on {DOCTYPE}."
		record_sharepoint_status(source, error=message)
		raise SharePointAuthError(message)

	response = requests.post(
		TOKEN_URL.format(tenant_id=config["tenant_id"]),
		data={
			"client_id": config["client_id"],
			"client_secret": get_decrypted_password(DOCTYPE, DOCTYPE, "client_secret"),
			"scope": "https://graph.microsoft.com/.default",
			"grant_type": "client_credentials",
		},
		timeout=30,
	)

	if response.ok and response.json().get("access_token"):
		return response.json()["access_token"]

	message = "Microsoft rejected the SharePoint credentials: " + describe_graph_error(response)
	if any(code in message for code in _SECRET_ERROR_CODES):
		message += f"\n\nCreate a new client secret in Azure and update it on {DOCTYPE}."

	record_sharepoint_status(source, error=message)
	raise SharePointAuthError(message)


def describe_graph_error(response) -> str:
	"""Readable error from a Microsoft identity / Graph response, without trace noise."""
	try:
		payload = response.json()
	except ValueError:
		return f"HTTP {response.status_code}: {(response.text or '').strip()[:500]}"

	# Identity platform: {"error": "...", "error_description": "AADSTS...: ... Trace ID: ..."}
	description = payload.get("error_description")
	if description:
		return f"HTTP {response.status_code}: {description.split(' Trace ID:')[0].strip()}"

	# Graph: {"error": {"code": "...", "message": "..."}}
	error = payload.get("error")
	if isinstance(error, dict):
		return f"HTTP {response.status_code}: {error.get('code')}: {error.get('message')}"

	return f"HTTP {response.status_code}: {str(payload)[:500]}"


def raise_for_graph_error(response):
	"""Drop-in for response.raise_for_status() that keeps Microsoft's explanation."""
	if not response.ok:
		raise requests.HTTPError(
			f"Graph request failed ({response.request.method} {response.url}): {describe_graph_error(response)}",
			response=response,
		)


def record_sharepoint_status(source: str, error: str | None = None):
	"""Store the latest SharePoint result on the config and commit it.

	Only call from background jobs or explicit actions (Test Connection) -
	never from inside a document save, since this commits.
	"""
	timestamp = now_datetime()
	values = {
		"last_status": "Error" if error else "Success",
		"last_status_on": timestamp,
		"last_status_source": source,
	}
	if error:
		values.update(last_error_on=timestamp, last_error_source=source, last_error=error[:5000])
	else:
		values["last_success_on"] = timestamp

	try:
		frappe.db.set_single_value(DOCTYPE, values)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"{DOCTYPE}: could not record status", message=frappe.get_traceback())


@frappe.whitelist()
def test_connection():
	"""Get a token and resolve the configured site and document library."""
	frappe.only_for("System Manager")

	source = "Test Connection"
	config = get_sharepoint_config()
	headers = {"Authorization": "Bearer " + get_graph_access_token(source)}

	site = requests.get(
		f"https://graph.microsoft.com/v1.0/sites/{config['hostname']}:/{config['site_path']}",
		headers=headers,
		timeout=30,
	)
	if not site.ok:
		message = f"Could not open SharePoint site '{config['site_path']}': " + describe_graph_error(site)
		record_sharepoint_status(source, error=message)
		frappe.throw(message)

	drives = requests.get(
		f"https://graph.microsoft.com/v1.0/sites/{site.json()['id']}/drives",
		headers=headers,
		timeout=30,
	)
	if not drives.ok:
		message = "Could not list document libraries: " + describe_graph_error(drives)
		record_sharepoint_status(source, error=message)
		frappe.throw(message)

	names = [d.get("name") for d in drives.json().get("value", [])]
	if config["drive_name"].lower() not in [(n or "").lower() for n in names]:
		message = (
			f"Document library '{config['drive_name']}' not found. Available: {', '.join(filter(None, names))}"
		)
		record_sharepoint_status(source, error=message)
		frappe.throw(message)

	record_sharepoint_status(source)
	return {"site": site.json().get("webUrl"), "drive_name": config["drive_name"]}
