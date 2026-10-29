# LAB Fleet Health email boundary

`engineering.api.fleet_health_email.send_fleet_health_email` is an authenticated POST endpoint. It is disabled outside the actual Frappe site `juan.isambane.co.za`, including for Administrator. Only `erp.intelligence@isambane.co.za` and Administrator may call it.

The only recipient is `juan@isambane.co.za`. Recipient, CC, BCC, sender, account, header, and all other extra parameters are rejected, even if empty. The framework's exact `cmd` value is the only exception. This endpoint must never be registered as an MCP tool.

The caller supplies `subject`, `text`, `html`, and `attachments`. Each of exactly two attachments has exactly `filename`, `content_type`, and `content_base64`. The filenames must be a matching generated Koppie daily or seven-day weekly report pair, with `.pdf` and `.html` extensions and matching MIME types. Validation checks real dates, canonical Base64, a combined 10 MiB decoded limit, a corresponding encoded limit, PDF header/end markers, and passive self-contained UTF-8 HTML. Format checks do not establish provenance or provide a general PDF malware scanner: the authenticated service account remains the trusted report producer.

Frappe resolves the default outgoing Email Account. It must have email `juan@isambane.co.za`, OAuth authentication, a connected app, a Microsoft Outlook/Office 365 SMTP host, outgoing/default enabled, and no Always BCC. Passwordless/no-auth and Frappe Mail routes are rejected. The actual queue sender, account and recipient are checked before sending.

`frappe.sendmail` builds the queue; Frappe sends through its native OAuth protocol. Success returns only `{"status":"sent","queue_id":"..."}` after both queue and sole recipient are Sent. Sent means the outgoing server accepted the message, not proof of inbox placement. Failed delivery queues are marked Error before the framework commits their diagnostics, preventing background retries. The endpoint returns a generic failure. If a connection times out after sending, reconcile the Email Queue before another manual attempt.

The public POST endpoint delegates to `engineering.controllers.fleet_health_email`; delivery protection lives in `engineering.controllers.fleet_health_privacy`. The old privacy module re-exports its existing public helpers. No global Error Log hook is registered. A request-local account and Connected App suppress native token-refresh diagnostics, while an SMTP subclass uses the native XOAUTH2 primitive without its raw-error logger. It preserves TLS/SSL and closes connections safely, including repeated after-response cleanup. Optional IMAP sent-folder copies remain best effort, using the same private OAuth protection. Cached accounts and framework classes are never modified.

Native queue processing commits Sending before any token refresh, which can itself commit. A queue-instance status wrapper replaces raw errors and marks Error before a failure commit. Request-scoped traceback redaction, Sentry event suppression and removal of delivery message-log entries prevent diagnostics escaping through those channels. Validation, permission and delivery errors skip native Error Log snapshots, which could otherwise store confidential request arguments. These protections apply to this endpoint; other email and Error Log behavior is unchanged.

## Offline tests

From `/home/juan/juan-bench/apps/engineering`:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/juan/juan-bench/env/bin/python tests/run_controller_regressions.py
```

This runner blocks site initialization, database access, real email, HTTP and queue scheduling. Synthetic transport tests exercise token refresh failures, SMTP and IMAP OAuth, queue failure commits, Sentry isolation, HTTP message logs, Error Log snapshot suppression and cleanup failures. No email is sent. Earlier deployment verification described in repository history is separate from this offline controller review.

## LAB operations

Deployment requires separate approval. This controller review does not migrate, update the running LAB checkout, clear caches, restart services, enable timers or send live email. A later approved LAB deployment must invalidate cached hooks and restart the relevant Python processes so the removed Error Log hook is no longer cached. No schema change is included. Live delivery acceptance must be verified separately with the authorized recipient.
