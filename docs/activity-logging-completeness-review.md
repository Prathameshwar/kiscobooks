# Activities logging completeness review — 2026-10-30

Activities reads the native immutable audit stream. It does not rely on browser
click logging: owners stage evidence in the transaction that changes business
state; confirmed outbox delivery and authenticated ingestion produce the feed.

## Findings and fixes

1. **Actor/source projection was incomplete.** Activities discarded recorded
   `actor_type`, `on_behalf_of_user_id` and `source_service`. The response and
   generated client now retain them. The UI shows source and represented-user
   references, distinguishes system/service-account actors, and labels missing
   historical attribution **Not recorded** rather than guessing **System**.
2. **Tenant-wide business history was unreachable from the feed UI.** The native
   endpoint already supported a tenant query, but Console always sent company ID.
   Authorized users now have Company/Organisation view links. Only an active
   tenant-scoped activity grant permits the organisation view; a flat permission,
   expired grant or company grant cannot widen it. Tenant-scoped audit authority
   is checked separately for organisation history links. Company events retain
   their recorded company, and switching scopes resets rows/cursors and aborts
   the old request.
3. **Reports had no publication-contract guard.** Its helper could stage an
   unknown action that the publisher would never select. It now validates before
   adding an outbox row. All 16 current literal caller actions match the declared
   contract. Report exports use `access`; background work records actor `system`
   and source `reports`. Existing stored evidence is not rewritten.
4. **Activities loaded the wider audit-list model.** Its native query now loads
   only activity projection fields plus sequence for allowed keyset ordering.

The suspected cursor-query-binding gap was disproved: binding already existed.
New native regressions confirm rejection when sort, limit or company changes;
a tenant feed walks all eligible rows once without leaking another tenant or
security events. Source timestamps remain the timeline ordering; no ingestion-time
rewrite, inferred actor identity or duplicate browser audit record was introduced.

## Coverage and practical limits

Reviewed seven producer contracts: Identity 117, Catalog 441, Accounting 387,
Vouchers 57, Reports 16, Notification 84, Design 18; Audit adds its export route.
This is **1,120 business-source routes plus one Audit route**, including declared
lifecycle vocabularies. Static inventory found 680 decorated POST/PUT/PATCH/DELETE
handler definitions, including read-like POST commands and delegated handlers.
These counts are inventory, **not proof that every handler branch ran** or that
every declared event corresponds to an implemented user workflow.

Owner tests verify transaction/outbox evidence and declared publication routes.
Catalog tests include a real API write through the confirmed publisher adapter,
authenticated Audit consumption, redelivery dedupe and chain verification using
isolated SQLite and a mocked broker exchange. Vouchers/Accounting tests also
exercise native owner evidence entering Audit. Reporting tests cover every
declared lifecycle action plus the rejected undeclared action. Native feed tests
exercise scoped API reads and complete page walks of ingested rows.

Security activities are intentionally outside Activities and need the separate
security-audit authority. Platform notification history remains segregated.
Integration/application diagnostics are separate documented surfaces; ordinary
page views and failed validation attempts are not invented as business mutations.
Nullable historical metadata stays unknown. Concurrent local-auth workflows are
still being edited separately and are not declared fully validated by this review.

Live VM delivery and real broker/MySQL rehearsal were **not executed**. This
review cannot certify current deployed worker health, retained outbox backlogs or
the delivery of old historical events. Existing startup preparation and delivery
inventory/retry tools remain the operational checks; no application database was
manipulated and no retained event was edited or replayed by this task.

## Validation

| Suite | Passed | Skipped |
|---|---:|---:|
| Audit, full suite | 218 | 13 |
| Catalog producer evidence/defaults | 24 | 0 |
| Accounting producer evidence/financial contracts | 23 | 10 |
| Reports lifecycle/API/jobs/export/execution/recovery | 53 | 1 |
| Notification mutation contract | 2 | 0 |
| Vouchers contract/broker checks | 2 | 1 |
| Design isolation/evidence | 13 | 0 |
| Identity audit delivery/context/platform evidence | 10 | 0 |
| Console affected UI/API/scope/evidence suites | 99 | 0 |
| Edge component-layout tests | 4 | 0 |

The four browser tests cover **48 layouts**: hub, audit, Company activity,
Organisation activity × 1440/768/390/320 × light/dark/ledger. Actual rendered
components and shared CSS were checked for overflow, controls, focus and evidence
layout; screenshots were reviewed. UI interaction and permission branches run in
React Testing Library. Browser/API fixtures do not claim live tenant login.

Console and API-client TypeScript pass. Audit/Reports changed source files pass
strict mypy and Ruff; Audit OpenAPI and generated client checks pass. Fail-first
evidence records three missing-provenance cases, six inaccessible/unsafe scope
cases and 17 report-contract/attribution failures before the fixes.

## Reuse

Results are in [findings/cases CSV](testing/tenant-admin/activity-logging-completeness-results.csv)
and [service coverage CSV](testing/tenant-admin/activity-logging-service-coverage.csv).
Run each Python suite from its service folder with that service's interpreter:

```powershell
# From apis/audit
.venv/Scripts/python.exe -m pytest -q
# From apis/reports
.venv/Scripts/python.exe -m pytest tests/test_activity_audit_contract.py tests/test_framework_api.py tests/test_framework_jobs.py tests/test_framework_exports.py tests/test_framework_execution.py tests/test_framework_recovery.py -q
```

From `mfes/apps/console`:

```powershell
pnpm.cmd exec vitest run tests/activity-api.test.ts tests/activity-feed.test.tsx tests/activity-page.test.tsx tests/audit-page.test.tsx tests/logs-and-activities-page.test.tsx tests/audit-api.test.ts tests/audit-proxy.test.ts tests/audit-events.test.tsx tests/audit-event-evidence.test.tsx tests/platform-audit-events.test.tsx tests/logs-and-activities-navigation.test.tsx --maxWorkers=2 --minWorkers=1
$env:QA_LOGS_BROWSER = '1'
pnpm.cmd exec vitest run tests/logs-and-activities-layout.browser.test.tsx --maxWorkers=1 --minWorkers=1
Remove-Item Env:QA_LOGS_BROWSER
pnpm.cmd exec tsc --noEmit
```

The existing `start/win/audit-contracts.py` reads the eight native contracts without
printing credentials. Operational live checks should use the existing approved
audit preparation/worker and delivery-state tools with the private environment
directory; isolate MySQL/broker rehearsal as their documented tools require.

## Final review

Walked CLAUDE.md §§5–6 and reviewed the final diff. No unresolved implementation
finding in the reviewed changes. Permission checks fail closed and no grants are
created or broadened. History query scope is validated server-side before mounting
reads; native services still authorize every page independently. Source provenance
comes from recorded authenticated evidence; no PII lookup, new data storage,
business rule, money value or hash-chain rewrite was added. Shared controls/styles
are reused. API-client 0.2.44 remains an unchanged workspace link in consuming locks.
Original paths, file line endings and concurrent local-auth changes are preserved.

`/simplify` and `/security-review` are unavailable here; manual simplification and
security/correctness reviews were completed instead. The live checks and concurrent
local-auth limits above remain explicit follow-up verification, not passing results.
