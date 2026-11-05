# RF2: durable execution and bounded results

The v2 path now admits an idempotent job and outbox message in one transaction. A separate
dispatcher publishes confirmed, durable, JSON-only Celery tasks containing three IDs. Short,
bulk and render queues are distinct; prefetch is one. The reference calculator runs in the
worker process after its database transaction closes. The legacy worker no longer holds the
company mutex while completing independent runs.

Four additive tables (revisions 0017–0020) retain tenant quotas, immutable job requests,
attempt history and immutable result batches. Admission allows 20 queued jobs per tenant;
claims allow two calculations and one export per tenant. A short tenant lock serializes
admission/claims, but individual batch publications lock only their job. A lease lasts 60
seconds, each replacement increments the attempt, and publication requires the current
unexpired attempt. Batches have at most 200 rows and 1 MiB. COMPLETE results are frozen;
partial rows remain inaccessible. Export jobs reference a completed parent and fail independently.

Cancellation fences publication. Transient dependency failures retry with bounded delay and
at most three attempts. Repair requeues committed work whose delivery was lost, without
duplicating a pending outbox record, and recovers failures between failure recording and retry.
Neither this repair nor result retention deletes completed evidence.

Workers use a separate, company-scoped service credential to obtain a signed, request-bound
Identity proof, valid for at most 30 seconds. Identity resolves current company/user status,
dated role grants and both Reports/Accounting field policies. Workers verify this authority
before calculation and publication. Gateway contexts now include both policy namespaces;
reads also enforce current permissions and actor binding. The Identity authorization resolver
requires its existing Catalog-source bootstrap/generation record. Private credentials are
deployment configuration, never retained in job payloads.

## Operation at this phase

Default `REPORTS_FRAMEWORK_ENABLED=false`. The enabled reference path is limited to 20,000
facts; this is not the million-line engine. RF3/RF4 must pass their capacity gates before
larger workloads are admitted. Discovery exposes no new export formats yet.

- Configure `REPORTS_JOB_BROKER_URL`, `REPORTS_JOB_QUEUE_NAMESPACE` (default `reports`), and
  `REPORTS_AUTHORITY_SOURCES` (origin, key_id, secret and explicit tenant/company scopes).
- Configure matching `IDENTITY_REPORT_AUTHORITY_CREDENTIALS` separately from owner feed keys.
- Dispatcher: `python -m reports.tasks.job_dispatcher --env-file <private-file>`.
- Worker: add `--worker short --pool prefork --concurrency 2`; use separate workers for
  `bulk` and `render`. The launcher limits concurrency to 1–8.
- Windows local development uses `--pool solo`; production uses prefork. Solo does not
  enforce prefork hard time/memory recycling limits. RF6 adds render-specific supervision;
  the current reference task has 55/60-second soft/hard limits and 512 MiB recycling.

## Verification

- SQLite job/recovery tests prove replay, gaps, stale attempts, three-attempt exhaustion,
  cancellation, tenant quotas/isolation, rollback with no audit effect, broker failure and
  outbox repair. Frozen parent results survive failed export jobs.
- Native MySQL runs the full Reports suite, scoped FK/index/model parity and complete
  downgrade/upgrade. A held lock on one same-company job does not block another job's claim.
- Live RabbitMQ confirms outbox delivery into the selected Celery lane; duplicate sweeps
  produce no second publish. Existing signed Audit broker integration also passes.
- Native Identity checks exercise signed authority, revocation and both field-policy
  namespaces in isolated schemas. Gateway/session/impersonation regressions: 17 passed.
- OpenAPI and both generated Reports/Identity clients are synchronized. API client tests:
  8 passed; TypeScript checking passes. Reports and Identity strict mypy pass.

Local command logs: `.test_artifacts/reports-framework/rf2-{reports-native,identity-native,tests}.log`.
The tests preserve v1 behavior; the new v2 console and complete export routes belong to RF5–RF7.
