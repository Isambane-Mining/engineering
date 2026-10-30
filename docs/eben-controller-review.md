# Eben's Engineering controller review

## Scope

The feature branch starts at Engineering `juan` commit `cd3c8e10cde860310404cf48b228c2930ec0e13b`. It excludes Engineering Legals PR #138 and all permission fixtures. Implementation and offline tests run in an isolated worktree, leaving the running LAB checkout unchanged. No database records, credentials, attachments, services or deployments are changed.

Fleet Health email validation and delivery orchestration move to `controllers/fleet_health_email.py`. Privacy moves to `controllers/fleet_health_privacy.py`. Existing API imports and the authenticated POST method retain their paths and contracts. Controllers are not whitelisted. LAB site, user, recipient, account and attachment restrictions remain intact.

The global Error Log hook is removed. Delivery-specific protections cover native OAuth refresh, SMTP/IMAP authentication, Error Log snapshots, Sentry, HTTP message logs and Email Queue failure commits. Native queue processing claims Sending before refreshing tokens. No framework class or cached account is patched. See `lab-fleet-health-email.md` for details.

The WhatsApp after-insert hook referenced the deleted `whatsapp_breakdown_import` controller. Repository imports, hooks, scheduler entries and call sites were checked before removing that obsolete registration. The separate manual WhatsApp chat importer and Asset Movement hooks remain unchanged. No file is deleted.

Tyre classification, queries and unique counting move to `controllers/tyre_damage.py`; the page retains rendering and re-exports the old helper names. HTTP methods and permission-aware queries remain unchanged. Four formerly site-dependent dashboard tests receive explicit Engine, MPP hours, date, Asset and classified breakdown fixtures; the real aggregation and renderer still run.

## Verification

From the feature worktree, using the installed bench Python:

```bash
/home/juan/juan-bench/env/bin/python -B tests/run_controller_regressions.py
```

**81 tests pass**, including all nine tyre tests, API compatibility, validation, scoped privacy, token-refresh failures, native XOAUTH2 wire format, SSL/TLS, best-effort sent copies, queue commit ordering, cleanup failures and adjacent calculation/ownership regressions. This runner blocks site initialization, database access, HTTP, SMTP connections and background scheduling unless a test supplies an explicit synthetic fixture.

The broader audit is deliberately opt-in:

```bash
/home/juan/juan-bench/env/bin/python -B tests/run_controller_regressions.py --extended
```

It runs **108 tests: 90 pass, five fail and 13 error**. Four failures also reproduce on the untouched base and concern existing Short Haul graph markup/percentages:

- `test_no_short_haul_keeps_single_bar_and_small_value_hover`
- `test_stack_and_real_tooltip_values_are_not_capped`
- `test_uncapped_short_haul_component`
- `test_zero_denominator_retains_hours_without_inventing_percentage`

The remaining one failure and 13 errors are Machine Reliability/category API tests that require site settings, database or real user permissions and hit the offline database guard. No live-site tests, document-save tests, migrations, browser sessions or real email deliveries are run for this review.

The protected Legals checkout separately passes its existing **58 Python tests and both JavaScript suites**. It remains on its existing branch and its unrelated permission fixture retains the same SHA-256. Changed Python files compile in memory; Ruff checks the moved controller/API implementations, delivery tests and offline runner. Git whitespace checks pass. No JavaScript source is changed.

## Production commits reviewed individually

Current company `main`/`juan` was inspected at `769e07885ce9db53a7af3172f1581a14fb2f6d22`, using a separate detached worktree. Neither old commit is applied:

| Commit | Finding | Decision |
| --- | --- | --- |
| `ff766b94caf7feb95c10e0d5d568a32875847757` | Removes an old hourly productivity API override. Current hooks already contain only the independent PDF override. The obsolete controller/API is gone. | Already satisfied; no PR. |
| `9c8f5974c02b47c68a02a43f882bdb4f744f0f8c` | Adds validation/tests/docs for the old `get_dashboard` API. Current Summary uses `get_defaults`/`get_summary`, with a shared frontend and separate Analysis page. | Superseded; no PR. |

Current Summary and Analysis pass **70 isolated Python tests and 34 JavaScript tests**, with live database/transport access blocked. The old branch is not merged and the original Production checkout, including its unrelated permission fixture and node_modules symlink change, is untouched.

## Remaining limits

The private transport intentionally relies on installed Frappe's native OAuth primitives and queue ordering. Rerun these tests when upgrading Frappe. Optional IMAP copy failures remain best effort, consistent with native behavior, without retaining sensitive upstream diagnostics. SMTP acceptance is not proof of inbox delivery. A later approved deployment needs hook-cache invalidation and process reload, followed by authorized LAB acceptance checks; this PR does not execute those actions.

## PR #137 integration and privacy compatibility decision

PR #137 is `juan` into `main`; PR #139 contains the controller review commit `3e78953e81b805e852eff6bf992d2374ff4b82e4` against `juan`. Integrating that exact commit by fast-forward preserves its history without pulling in Legals PR #138 or permission work. No change is merged into `main`.

The privacy API file is intentionally retained as an eight-line compatibility shim. Searches of Engineering, the installed bench apps and the available MCP release source found no new runtime consumers after the controller moves. The old import path was used by the email module and the removed Error Log hook, however, and cached hooks or out-of-repository Python consumers may still resolve it. Deleting the file would break those imports; there is no HTTP endpoint to remove because its helpers were never whitelisted. The shim contains no business logic, credential access or hook registration. A regression verifies that reloading it neither installs formatters nor creates a Sentry hub or loads an account. Actual delivery protection remains in the controller, imported directly by email business logic.

The integration adds one additional privacy fix: unexpected exceptions before private delivery also become generic ValidationErrors with `skip_error_log`, suppressing confidential request snapshots and upstream exception chaining. Known validation and permission exceptions keep their existing messages and types. A synthetic regression first reproduced the unhandled failure, then passed after this fix. The relevant tests, protected Legals suites, compilation, targeted lint and final change scope are rechecked before pushing `juan`. The original LAB worktree is not switched or deployed. PR #139 becomes superseded once its exact commit is included in `juan`.
