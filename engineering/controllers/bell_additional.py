"""Additional Bell Equipment ISO 15143-3 telemetry."""

import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin, urlparse
import xml.etree.ElementTree as ET

import frappe
import requests


SETTINGS = "API Bell Settings"
FAULT_DOCTYPE = "Bell Equipment Fault Codes"
FUEL_DOCTYPE = "Bell Equipment Fuel Consumption"

TOKEN_HOST = "sso.bellequipment.com"
FLEET_HOST = "b-fleet03.bellequipment.com"


class BellAdditionalError(Exception):
    pass


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _timestamp(value):
    if not value:
        raise BellAdditionalError("Bell measurement timestamp is missing.")

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        raise BellAdditionalError("Bell returned an invalid timestamp.") from None


def _credentials(settings):
    token_url = settings.token_url
    fleet_url = settings.fleet_url

    if urlparse(token_url).hostname != TOKEN_HOST:
        raise BellAdditionalError("Invalid Bell authentication URL.")

    if urlparse(fleet_url).hostname != FLEET_HOST:
        raise BellAdditionalError("Invalid Bell Fleet URL.")

    response = requests.post(
        token_url,
        data={
            "grant_type": "password",
            "username": settings.username.strip(),
            "password": settings.get_password("password"),
            "scope": settings.scope or "ISO_Exports",
        },
        auth=(
            settings.client_id.strip(),
            settings.get_password("client_secret"),
        ),
        timeout=60,
        allow_redirects=False,
    )

    if response.status_code != 200:
        raise BellAdditionalError(
            f"Bell authentication failed (HTTP {response.status_code})."
        )

    token = response.json().get("access_token")
    if not token:
        raise BellAdditionalError("Bell did not return an access token.")

    return token


def _links(root):
    result = {}

    for node in root:
        if _tag(node) == "Links":
            values = {_tag(child): child.text for child in node}
            if values.get("rel") and values.get("href"):
                result[values["rel"]] = values["href"]

    return result


def _fetch_events(settings, token, pin, metric, event_tag, start, end):
    base = settings.fleet_url.rstrip("/")
    url = (
        f"{base}/Equipment/{quote(pin, safe='')}/"
        f"{metric}/{start}/{end}"
    )

    visited = set()
    events = []

    for _ in range(100):
        parsed = urlparse(url)

        if parsed.scheme != "https" or parsed.hostname != FLEET_HOST:
            raise BellAdditionalError("Bell pagination URL is not approved.")

        if url in visited:
            raise BellAdditionalError("Bell pagination loop detected.")

        visited.add(url)

        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/xml",
            },
            timeout=max(int(settings.timeout or 30), 60),
            allow_redirects=False,
        )

        if response.status_code != 200:
            raise BellAdditionalError(
                f"Bell {metric} request failed (HTTP {response.status_code})."
            )

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            raise BellAdditionalError(
                f"Bell returned invalid {metric} XML."
            ) from None

        for item in root:
            if _tag(item) == event_tag:
                events.append(
                    (
                        _timestamp(item.attrib.get("datetime")),
                        {
                            _tag(child): child.text
                            for child in item
                        },
                        ET.tostring(item, encoding="unicode"),
                    )
                )

        href = _links(root).get("next")
        if not href:
            return events

        url = urljoin(url, href)

    raise BellAdditionalError("Bell exceeded the 100-page safety limit.")


def _machine_mappings(settings):
    rows = [
        row for row in (settings.machine_mappings or [])
        if row.pin and row.asset
    ]

    if not rows:
        raise BellAdditionalError(
            "No mapped Bell machines found. Complete Asset Mapping first."
        )

    return rows


def _key(prefix, pin, values):
    raw = "|".join(str(value or "") for value in values)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{pin}-{digest}"


def _save_record(doctype, values):
    key = values["external_key"]
    existing = frappe.db.exists(doctype, key)

    if existing:
        doc = frappe.get_doc(doctype, existing)
        doc.update(values)
        doc.save(ignore_permissions=True)
        return "updated"

    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    return "created"


def _identity(mapping):
    return {
        "asset": mapping.asset,
        "equipment_id": mapping.equipment_id,
        "pin": mapping.pin,
        "serial_number": mapping.serial_number,
        "oem": mapping.oem or "BELL",
        "model": mapping.model,
    }


def _set_status(kind, success, message):
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    values = {
        f"last_{kind}_status": "Success" if success else "Failed",
        f"last_{kind}_message": message[:500],
    }

    if success:
        values[f"last_{kind}_sync"] = now

    frappe.db.set_single_value(SETTINGS, values)
    frappe.clear_document_cache(SETTINGS, SETTINGS)


def _set_machine_status(mapping, kind, success, message, checked_at):
    values = {
        f"{kind}_status": "Reporting" if success else "Not Reporting",
        f"{kind}_last_checked": checked_at.replace(tzinfo=None),
        f"{kind}_last_error": "" if success else str(message)[:500],
    }

    frappe.db.set_value(
        "Bell Machine Mapping",
        mapping.name,
        values,
        update_modified=False,
    )


def _run(kind):
    settings = frappe.get_single(SETTINGS)

    if not settings.enabled:
        return {"ok": False, "message": "Enable Bell API Settings first."}

    enabled_field = (
        "fault_codes_enabled"
        if kind == "fault_codes"
        else "fuel_consumption_enabled"
    )

    if not settings.get(enabled_field):
        return {"ok": False, "message": f"{kind} retrieval is disabled."}

    try:
        days = int(
            settings.get(
                "fault_codes_lookback_days"
                if kind == "fault_codes"
                else "fuel_consumption_lookback_days"
            ) or 30
        )

        if not 1 <= days <= 365:
            raise BellAdditionalError(
                "Lookback period must be between 1 and 365 days."
            )

        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(days=days)

        start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        mappings = _machine_mappings(settings)
        token = _credentials(settings)

        # Use existing Asset mappings. A failed machine must not block others.
        pending = []
        failures = []
        successful_machines = 0

        for mapping in mappings:
            try:
                if kind == "fault_codes":
                    events = _fetch_events(
                        settings, token, mapping.pin,
                        "CautionCodes", "CautionDescription",
                        start, end,
                    )
                else:
                    events = _fetch_events(
                        settings, token, mapping.pin,
                        "FuelUsedInThePreceding24Hours", "FuelUsedLast24",
                        start, end,
                    )

                successful_machines += 1

                for timestamp, data, raw_xml in events:
                    identity = _identity(mapping)

                    if kind == "fault_codes":
                        code = (data.get("Identifier") or "").strip()
                        description = data.get("Description") or ""

                        if not code:
                            raise BellAdditionalError(
                                "Fault without an identifier."
                            )

                        key = _key(
                            "FAULT", mapping.pin,
                            (code, timestamp.isoformat()),
                        )

                        values = {
                            **identity,
                            "external_key": key,
                            "fault_code": code,
                            "description": description,
                            "occurred_at": timestamp,
                            "retrieved_at": now.replace(tzinfo=None),
                            "query_start": start_dt.replace(tzinfo=None),
                            "query_end": now.replace(tzinfo=None),
                            "source_event_xml": raw_xml,
                            "source_checksum": hashlib.sha256(
                                raw_xml.encode("utf-8")
                            ).hexdigest(),
                        }
                        doctype = FAULT_DOCTYPE

                    else:
                        try:
                            consumed = float(data["FuelConsumed"])
                        except (ValueError, TypeError, KeyError):
                            raise BellAdditionalError(
                                "Invalid fuel consumption measurement."
                            ) from None

                        if consumed < 0:
                            raise BellAdditionalError(
                                "Negative fuel consumption measurement."
                            )

                        units = data.get("FuelUnits") or ""

                        # One record per machine and measurement timestamp.
                        key = _key(
                            "FUEL24", mapping.pin,
                            (timestamp.isoformat(),),
                        )

                        values = {
                            **identity,
                            "external_key": key,
                            "fuel_consumed": consumed,
                            "fuel_units": units,
                            "measurement_timestamp": timestamp,
                            "retrieved_at": now.replace(tzinfo=None),
                            "query_start": start_dt.replace(tzinfo=None),
                            "query_end": now.replace(tzinfo=None),
                            "source_event_xml": raw_xml,
                            "source_checksum": hashlib.sha256(
                                raw_xml.encode("utf-8")
                            ).hexdigest(),
                        }
                        doctype = FUEL_DOCTYPE

                    pending.append((doctype, values))

                _set_machine_status(mapping, kind, True, "", now)

            except Exception as error:
                _set_machine_status(mapping, kind, False, str(error), now)
                failures.append(
                    f"{mapping.equipment_id or mapping.pin}: "
                    f"{str(error)[:180]}"
                )

        if successful_machines == 0:
            raise BellAdditionalError(
                "All mapped machines failed. No records were imported. "
                + "; ".join(failures[:5])
            )

        frappe.db.savepoint("bell_additional_sync")

        try:
            created = 0
            updated = 0

            for doctype, values in pending:
                outcome = _save_record(doctype, values)
                created += outcome == "created"
                updated += outcome == "updated"

        except Exception:
            frappe.db.rollback(save_point="bell_additional_sync")
            raise

        label = "fault events" if kind == "fault_codes" else "fuel readings"
        message = (
            f"Retrieved {len(pending)} {label}. "
            f"{successful_machines}/{len(mappings)} machines successful. "
            f"{created} created; {updated} updated."
        )

        if failures:
            message += " Machine failures: " + "; ".join(failures[:5])

        _set_status(kind, not failures, message)

        return {
            "ok": not failures,
            "partial": bool(failures),
            "count": len(pending),
            "created": created,
            "updated": updated,
            "machines": successful_machines,
            "failed_machines": len(failures),
            "message": message,
        }

    except Exception as error:
        message = (
            str(error)
            if isinstance(error, BellAdditionalError)
            else f"Bell additional retrieval failed ({type(error).__name__})."
        )

        _set_status(kind, False, message)

        return {"ok": False, "message": message}


@frappe.whitelist(methods=["POST"])
def pull_fault_codes():
    frappe.has_permission(SETTINGS, "write", throw=True)
    return _run("fault_codes")


@frappe.whitelist(methods=["POST"])
def pull_fuel_consumption():
    frappe.has_permission(SETTINGS, "write", throw=True)
    return _run("fuel_consumption")
