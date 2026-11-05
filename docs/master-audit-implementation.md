# Master audit implementation

Authorised 2026-10-29 following the master audit review. Existing unrelated workspace edits remain in place.

1. Complete producer contracts and safe evidence: register bank actions, validate dynamic emitters, retain safe opening money/reference evidence and normalize Notification mutation evidence without breaking historical reads. Add regression tests before fixes.
2. Protect logs and preserve correlation: generate bounded request/trace IDs at trusted boundaries, establish audit context consistently, remove sensitive query/referrer values from access logs, and log safe rejection metadata. Test redaction, attribution and rollback behaviour.
3. Complete local delivery and operations: configure explicit source credentials from each producer contract, include every publisher in managed startup, report worker/backlog health and provide bounded recovery. Validate existing evidence before replay; retain historical privacy cutoffs and message identities.
4. Complete Console history/activity: generate subject choices from producer contracts, add permission-scoped activity and master history entry points, and display actor/reference evidence. Regenerate API artifacts if contracts change. Run affected backend/UI/script checks and database/model verification, then manually review security and correctness invariants and fix findings.

No schema change was required. Audit remains broker-fed; infrastructure logs remain outside Audit. No publishing or commit is included in this task.

## Execution and final review

All four phases implemented. The source contracts, generated Accounting evidence matrix,
Console subject/resource identities, shared library version 0.44.2 and all eight service
lockfiles/environments are synchronized.

The final review also corrected the consumer's combined route limit, false historical-held
counts during concurrent publishing, bank evidence that previously manufactured a status,
historical primitive evidence rendering, and the distinction between absent and recorded-null
before/after values. Stale manufacturing-readiness and permission-catalogue test expectations
were reconciled with existing implementation/docs; no permission or role was widened.

Authorization, company/tenant isolation, impersonation attribution, field-policy projection,
secret/PII redaction, atomic emission, idempotency and immutable evidence were reviewed manually.
The `/simplify` and `/security-review` commands are not available in this session; their review
checks were performed directly. No remaining blocking finding was identified in the changed paths.

### Local delivery result

- All eight issuers configured with exact, independent signing contracts and managed workers.
- Reviewed eligible events delivered: Catalog 1,931; Accounting 647; Vouchers 43,186;
  Identity 530 recovered pending events. All source outboxes have zero eligible pending/exhausted events.
- Broker: one audit consumer, zero queued messages and zero dead letters after recovery.
- Audit contains 50,611 events with 50,611 distinct message IDs; verification found zero broken tenant chains.
- The 37 Identity events before the existing privacy cutoff remain held. Retained event payloads,
  original message IDs and source timestamps were not rewritten to manufacture historical evidence.
- Windows delivery health reports UP. nginx configuration was validated and started with query/referrer-safe logs.

Reports, Notification, Design and Audit export had no local pending events; real RabbitMQ
verification exercised authenticated delivery for all eight issuers in isolated test queues.

### Validation

- Console: 399 tests across 17 affected audit, activity, master, tracking and proxy suites passed.
- Live RabbitMQ: 11 tests passed, including every issuer, confirms, dedupe, rejection and reconnect.
- Shared library: 1,154 passed; package coverage 93.88% (90% floor).
- Audit: 192 passed, 13 skipped; package coverage 92.28% (90% floor).
  Skips require a container runtime or explicit live-broker settings; the separate live-broker run passed.
- Accounting banking/evidence: 11 passed; opening/contract checks: 30 passed, one native-Decimal case skipped.
- Catalog API/correlation/evidence: 15 passed. Identity gateway/history: 8 passed.
  Notification control/evidence: 8 passed, one container-dependent check skipped.
- Ruff, strict mypy and Console TypeScript checks cover the changed paths.
- Windows worker/startup/shutdown/configuration and launcher readiness: 46 tests passed.
- Native MySQL schema verification: all eight databases aligned, all 518 tables matched,
  no missing/extra tables or native differences, all Alembic checks passed.

### Operator commands

Run these from the original workspace root; private values are never command arguments:

```powershell
# Idempotent local credential/route synchronization; preserves existing cutoffs.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File start/win/audit-prepare.ps1

# Check source contracts, backlogs and existing broker queues.
apis/audit/.venv/Scripts/python.exe apis/audit/tools/delivery_state.py --preflight --broker

# Preview a bounded set of reviewed pending IDs; add --apply only after reviewing.
apis/audit/.venv/Scripts/python.exe apis/audit/tools/delivery_state.py --service identity --retry <message-uuid>

# Verify generated Console subjects and owner resource identities.
apis/audit/.venv/Scripts/python.exe start/win/audit-contracts.py --check-console
```

Normal `start-services.ps1` starts every configured audit publisher after the consumer;
`status.ps1` includes a separate Audit delivery health row. Publishers emit safe stalled-outbox
warnings every 60 seconds when eligible events are exhausted or older than five minutes.
Historical held rows do not trigger those warnings. Delivery checks report unhealthy consumers,
dead letters, stopped workers and material queue backlogs independently of read-API database readiness.
Infrastructure alert routing, OTel/Grafana exports and the deferred integration-log surface retain
their documented scope; no direct HTTP audit-write endpoint was added.
