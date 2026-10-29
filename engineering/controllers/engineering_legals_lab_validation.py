"""Non-whitelisted, read-only LAB audit commands. Run only after separate approval.

No document saves, SQL writes, network requests or job execution. The manifest is
private (0600), contains historical data and must not be committed to Git.
"""

import hashlib
import json
import os
from pathlib import Path

import frappe
from frappe.utils import cint

LAB_SITE = "juan.isambane.co.za"


def _guard():
    if getattr(frappe.local, "site", None) != LAB_SITE:
        raise frappe.PermissionError(f"This audit is restricted to LAB {LAB_SITE}.")


def read_state():
    _guard()
    records = frappe.get_all(
        "Engineering Legals", fields=["*"], order_by="name", limit_page_length=0
    )
    urls = sorted({record.attach_paper for record in records if record.attach_paper})
    files = frappe.get_all(
        "File",
        filters={"is_folder": 0},
        or_filters=[
            ["attached_to_doctype", "=", "Engineering Legals"],
            ["file_url", "in", urls or ["__NO_LEGAL_ATTACHMENTS__"]],
        ],
        fields=["*"],
        order_by="name",
        limit_page_length=0,
    )
    hashes = {}
    for file in files:
        if (file.file_url or "").startswith(("http://", "https://")):
            hashes[file.name] = (
                "remote:" + file.file_url
            )  # Preserve reference; never fetch external content.
            continue
        document = frappe.get_doc("File", file.name)
        document.validate_file_path()
        try:
            with open(document.get_full_path(), "rb") as stream:
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            hashes[file.name] = digest.hexdigest()
        except FileNotFoundError:
            # Preserve the File row and URL. Permission/path errors still fail closed.
            hashes[file.name] = "missing:ENOENT"
    return {"records": records, "files": files, "content_hashes": hashes}


def _canonical(state):
    return json.loads(json.dumps(state, sort_keys=True, default=str))


def capture_snapshot(output_path, expected_count=3283, allow_missing_files=False):
    _guard()
    state = _canonical(read_state())
    missing_files = sum(
        value == "missing:ENOENT" for value in state["content_hashes"].values()
    )
    if missing_files and not cint(allow_missing_files):
        raise frappe.ValidationError(
            "Missing attachment files require explicit acceptance before capturing a baseline."
        )
    if len(state["records"]) != int(expected_count):
        raise frappe.ValidationError(
            "Engineering Legals count differs from the approved baseline; investigate before migration."
        )
    manifest = dict(site=LAB_SITE, version=1, **state)
    descriptor = os.open(Path(output_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return {
        "ok": True,
        "records": len(state["records"]),
        "files": len(state["files"]),
        "missing_files": missing_files,
        "remote_files": sum(
            value.startswith("remote:") for value in state["content_hashes"].values()
        ),
        "manifest": str(output_path),
    }


def verify_snapshot(input_path):
    _guard()
    baseline = json.loads(Path(input_path).read_text())
    if baseline.get("site") != LAB_SITE or baseline.get("version") != 1:
        raise frappe.ValidationError("Invalid LAB baseline manifest.")
    current = _canonical(read_state())
    for collection in ("records", "files"):
        expected = baseline[collection]
        # Additive schema fields are allowed; every pre-existing field must match.
        fields = set().union(*(row.keys() for row in expected))
        projected = [
            {field: row.get(field) for field in fields} for row in current[collection]
        ]
        if projected != expected:
            raise frappe.ValidationError(
                f"Historical {collection} changed; keep LAB paused and investigate."
            )
    if current["content_hashes"] != baseline["content_hashes"]:
        raise frappe.ValidationError(
            "Attachment bytes changed; keep LAB paused and investigate."
        )
    return {
        "ok": True,
        "records": len(current["records"]),
        "files": len(current["files"]),
        "message": "All historical fields, attachment references and local attachment bytes match.",
    }


def verify_installation():
    """Post-migration acceptance only: additive schema present, rules still off/empty."""
    _guard()
    parent_name = "Engineering Legals Site Configuration"
    child_name = "Engineering Legals Site Section Rule"
    if cint(frappe.conf.get("engineering_legals_site_rules_enabled")):
        raise frappe.ValidationError(
            "Site rules must remain disabled during migration acceptance."
        )
    if not all(frappe.db.table_exists(name) for name in (parent_name, child_name)):
        raise frappe.ValidationError("Site configuration schema is not installed.")
    parent, child = frappe.get_meta(parent_name), frappe.get_meta(child_name)
    site = parent.get_field("site")
    if (
        parent.autoname != "field:site"
        or not site
        or site.options != "Location"
        or not site.unique
    ):
        raise frappe.ValidationError(
            "Parent Site link/naming/uniqueness metadata is incorrect."
        )
    if not child.istable:
        raise frappe.ValidationError("Section Rule must be a child table.")
    indexes = frappe.db.sql(
        "SHOW INDEX FROM `tabEngineering Legals Site Configuration`", as_dict=True
    )
    if not any(
        row["Column_name"] == "site" and row["Non_unique"] == 0 for row in indexes
    ):
        raise frappe.ValidationError("The database unique Site index is missing.")
    if not frappe.get_meta("Engineering Legals").has_field("expiry_rule_snapshot"):
        raise frappe.ValidationError(
            "Engineering Legals policy audit columns are missing."
        )
    if frappe.db.count(parent_name) or frappe.db.count(child_name):
        raise frappe.ValidationError(
            "Unexpected site configurations/rules: migration must not seed data."
        )
    return {
        "ok": True,
        "site_configurations": 0,
        "section_rules": 0,
        "rollout_enabled": False,
    }
