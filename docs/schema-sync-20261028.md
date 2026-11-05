# Database, model and script synchronization — 2026-10-28

Authorized: keep the local databases, current models and setup/launch scripts in
sync. Preserve data, service ownership, runtime grants and migration history.

- [x] Inspect all eight live schemas, independent migration heads and model metadata.
- [x] Identify drift: Accounting 0212 -> 0216; Vouchers 0101 -> 0105.
- [x] Back up and rehearse the existing forward migrations in disposable schemas.
- [x] Drain affected managed processes, back up again, upgrade and retain row counts.
- [x] Restart affected services and repeat all eight schema comparisons.
- [x] Verify Windows scripts, runtime readiness and record the final evidence.

Six services were already aligned. The pending migrations create five opening
workflow tables and add three nullable columns; they do not rewrite existing
business rows. Read all eight revisions before application. No new migration,
schema reset, Alembic stamp, runtime DDL grant or financial admission change is
needed. Migration/seed/model repairs will be recorded if rehearsal identifies any.

Both live upgrades passed Alembic comparison and native metadata checks. The
affected managed APIs, Accounting reference worker and three previously running
delivery workers were restored. No admission flags or runtime database grants were
changed. Each rehearsal database was removed after successful verification; live
backups remain under ignored `.test_artifacts/schema-sync-upgrade-20261028/`.
Administrator credentials were supplied through a hidden prompt and child process
environments only; they were not saved in scripts or connection files.

Script finding: the shutdown regression expected 20 successfully stopped workers
after preserving one reused PID, but the current launcher has 24 definitions.
Updated the expectation to 23 and explicitly checked the three added stock/source
delivery workers. The PID-protection and continued-cleanup assertions remain.
All 63 Windows PowerShell files parsed; all 49 launcher tests passed. The schema
verifier's eight regression tests also passed. Final runtime health reports all
12 infrastructure/API components UP.

## Final verified state

| Service | Database / migration head | Model tables |
|---|---|---:|
| Identity | 0089 | 56 |
| Audit | 0003 | 3 |
| Catalog | 0210 | 182 |
| Notification | 0116 | 30 |
| Accounting | 0216 | 137 |
| Vouchers | 0105 | 71 |
| Reports | 0038 | 28 |
| Design | 0008 | 7 |

All **514** model tables align. All eight Alembic checks exited zero; missing/extra
tables and extended native differences are empty for every service. Original
Accounting rows: **14,361** across **134** tables; original Vouchers rows:
**59,528** across **69** tables. Before/after counts match table by table, including
existing stock, financial and retained import evidence.

The one-off rollout helper stalled while capturing output from detached process
hosts after the APIs started. Closed that completed helper, changed startup output
capture to dedicated files, and restored the three delivery workers separately.
No migration was repeated or reversed. Final independent schema and health checks
above establish the resulting state.

Evidence: `.test_artifacts/schema-sync-20261028-final/`,
`.test_artifacts/schema-sync-runtime-health-final.log`,
`.test_artifacts/schema-sync-script-validation-final.log`, and the private upgrade
backups/retention logs named above. Manual simplicity/security review confirmed
service-local schema ownership, independent forward chains, unchanged runtime
grants, retained data and verified process ownership. No new issue remains in
this synchronization task. No commit or publication was performed.
