# MPI Phase 2

Implementation plan: expand the explicit Results field mapping and schema; restrict driver/VIN/sensors
to elevated read permissions; make request serialization match the working urllib reference; report the
two endpoint outcomes independently; separate background-owned mapping/status updates from user saves;
add offline mocked Python and form tests and run them. No migrations, restarts, commits or pushes.

## Request diagnosis

Read-only LAB checks on 2026-11-19 used the saved encrypted credentials internally, without printing
credentials or response bodies. The user-provided reference was a form-urlencoded urllib POST and
a urllib GET with an explicit Basic header. Side-by-side checks found:

| Endpoint | requests defaults | urllib reference |
|---|---|---|
| Vehicle list | HTTP 200, 142 records | HTTP 200, 142 records |
| Status, same IMEI | HTTP 200, code 0 | HTTP 200, code 0 |

The original client and required-field parser also succeeded on one record. A current authentication or
HTTP-library failure was not reproduced. No claim is made that requests itself caused the earlier failure.
Locally there are no proxy environment variables or netrc files. Observable request defaults differ:
requests advertises compression and its own User-Agent/keep-alive; urllib requests identity encoding
and closes the connection. Basic auth also differs for non-Latin-1 credentials (requests uses Latin-1;
the supplied urllib reference uses UTF-8). The client will explicitly use the reference form encoding,
UTF-8 Basic encoding, identity response encoding, urllib User-Agent and connection-close behavior.
Environment-derived proxies/netrc authentication are disabled for this fixed verified HTTPS origin;
TLS verification remains enabled and redirects remain disabled. This is deterministic compatibility
hardening, not evidence that a specific header caused a reproduced failure.

## Data and permissions

Each IMEI retains one result. Vehicle-list coordinates are separate from status coordinates. Record
metadata and all listed nested status members have individual fields; sensors_status and zone_data are
structured JSON values, not an entire response. The existing zone text field remains a scalar display
and retains its Data type, avoiding an unsafe JSON conversion of existing plain-text zone values.
Only allowlisted endpoint fields are persisted.
The API's epoch times are retained as returned, alongside the existing derived site-local position time.
Moving/parking are seconds per the API documentation. Other numeric values retain API units.
Null optional scalar values are preserved in a structured missing-fields list so Frappe numeric zero
defaults cannot be mistaken for measured zero. Missing activity fields reject the snapshot; omitted
optional metadata preserves previous values and explicit null clears it. Older position snapshots
cannot replace newer ones. Empty sensor arrays explicitly clear previous sensor values.

Driver name, phone, VIN, info and sensor data use permission level 1. Only System Manager,
Engineering Manager and Fleet Manager have level-1 read access. Other existing readers retain
vehicle/activity access. No body, remote error message or exception text is logged or reported.

## Settings concurrency

Sync status writes use update_modified=False and update only background-owned status fields.
Discovery writes child rows directly under the singleton lock; it never saves the entire settings form.
User saves merge current server-owned telemetry and discovered rows with the submitted Asset choices.
Normal timestamp conflict detection for simultaneous user edits stays enabled.
Refresh Sync Status updates only read-only status fields in the browser, without reload_doc or overwriting
unsaved credentials, configuration or mapping selections. Results remain accessed through Frappe permissions.

## Deferred activation

The new schema requires a separately authorized LAB migration. No schema/data activation is performed
in this task. Review the changed JSON and run `bench --site juan.isambane.co.za migrate` only when approved.
Then validate the form, restricted fields, repeated syncs and edited mapping preservation on LAB.
API references: https://docs.pilot-gps.com/7.7/vehicle_status_print.html and
https://docs.pilot-gps.com/list_of_objects.html.

## Validation

Offline tests (all HTTP and DB boundaries mocked; no real credentials):
```bash
env/bin/python -m unittest engineering.tests.test_mpi engineering.tests.test_mpi_phase2 -q
node apps/engineering/engineering/tests/test_mpi_settings_form.cjs
```
Run from the bench directory. Read-only checks of the updated client also returned HTTP 200 / 142
vehicles for the list and HTTP 200 / code 0 / one record for status. Only HTTP codes, record counts,
API numeric codes and mapping counts were printed. No sync or result persistence was invoked.
