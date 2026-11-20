# Kobelco diagnostics and isolated tests

Scope: branch juan; LAB implementation only; preserve all existing work. Do not change authentication, telemetry extraction, mappings, scheduling or historical rows.

- [ ] Require an explicitly designated isolated test site and a database distinct from live LAB. Guard both runner and fixture setup before writes. Mock HTTP process-wide, forbid unmocked requests, roll back test data and commits, keep scheduler disabled. Exercise the production LAB gate via test-only constant substitution rather than pretending the DB context is LAB.
- [ ] Test first: timeout with chained MariaDB code1205, safe class/stage/timestamp diagnostics, secret-free Error Log and scheduled output, preserved successful timestamp, recovery clearing failed status, test runner refusing LAB and separate Redis keys.
- [ ] Track actual processing stages; emit allowlisted descriptions and recognized SQL codes without exception text/locals. Persist explicit diagnostic-only Error Log documents and include structured diagnostics in scheduled result logging.
- [ ] Run mocked DB tests only on the private test DB/site; controller regressions separately. No live import verification. Compare live telemetry and mapping fingerprints read-only afterward.
- [ ] Document changed files, commands, diagnostics semantics and isolated test-site lifecycle.
