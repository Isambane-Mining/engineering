# LAB Fleet Health email boundary

`engineering.api.fleet_health_email.send_fleet_health_email` is an authenticated POST endpoint. It is disabled outside the actual Frappe site `juan.isambane.co.za`, including for Administrator. Only `erp.intelligence@isambane.co.za` and Administrator may call it.

The only recipient is `juan@isambane.co.za`. Recipient, CC, BCC, sender, account, header, and all other extra parameters are rejected, even if empty. The framework's exact `cmd` value is the only exception. This endpoint must never be registered as an MCP tool.

The caller supplies `subject`, `text`, `html`, and `attachments`. Each of exactly two attachments has exactly `filename`, `content_type`, and `content_base64`. The filenames must be a matching generated Koppie daily or seven-day weekly report pair, with `.pdf` and `.html` extensions and matching MIME types. Validation checks real dates, canonical Base64, a combined 10 MiB decoded limit, a corresponding encoded limit, PDF header/end markers, and passive self-contained UTF-8 HTML. Format checks do not establish provenance or provide a general PDF malware scanner: the authenticated service account remains the trusted report producer.

Frappe resolves the default outgoing Email Account. It must have email `juan@isambane.co.za`, OAuth authentication, a connected app, a Microsoft Outlook/Office 365 SMTP host, outgoing/default enabled, and no Always BCC. Passwordless/no-auth and Frappe Mail routes are rejected. The actual queue sender, account and recipient are checked before sending.

`frappe.sendmail` builds the queue; Frappe sends through its own OAuth transport. Success returns only `{"status":"sent","queue_id":"..."}` after both queue and sole recipient are Sent. Sent means the outgoing server accepted the message, not proof of inbox placement. Failed delivery queues are marked Error to stop background retries, and the endpoint returns a generic failure. If a connection times out after sending, reconcile the Email Queue before another manual attempt. No tokens/passwords or raw upstream diagnostics are returned to Node. A request-scoped traceback formatter redacts OAuth locals, a scoped Sentry hub suppresses delivery telemetry, and an Error Log before-insert hook discards delivery exception text/metadata. Other request contexts are unchanged.

## Offline tests

From `/home/juan/juan-bench/apps/engineering`:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/juan/juan-bench/env/bin/python -m unittest engineering.api.test_fleet_health_email engineering.api.test_fleet_health_privacy
```

These tests isolate DB/transport calls and never send email. Cross-repository verification also builds daily and partial weekly artifacts with the Node renderer, passes their payload through this endpoint and real LAB Frappe queue building, checks both attachment MIME parts and envelope, mocks the final transport, then rolls back the test queues.

## LAB operations

Pull the feature branch into the LAB `juan` checkout with `git pull --ff-only upstream codex/lab-fleet-health-mail`. Preserve unrelated pycache changes. Run `bench --site juan.isambane.co.za clear-cache` for the Error Log hook. No schema migration or asset build is needed. Reload only `juan-bench-web:juan-bench-frappe-web` using supervisor, then update the MCP LAB checkout from `codex/lab-frappe-mail` and restart only `isambane-erp-intelligence.service`.

Run both agent dry runs, then one forced daily test under the timer's `flock` lock. Verify the returned queue ID in the LAB Email Queue and its sole recipient before installing/enabling the two LAB timers. All changes are LAB-only; never run these operations against production.
