# Audit microservice implementation checklist

Status values: `[ ]` pending, `[~]` active, `[x]` complete, `[!]` externally blocked.

This checklist is the execution record for `docs/audit.md`. A phase is complete only when
its implementation, migration/model parity, tests, and relevant documentation are done.

## Activities completeness follow-up — 2026-10-30

- [x] Review seven producer contracts (1,120 declared routes), native recording,
      delivery, scope and activity projection; run affected producer tests.
- [x] Retain actor type, represented user and source in the lean Activities API;
      export OpenAPI and regenerate the Audit client (client version 0.2.44).
- [x] Expose Organisation activity only for current tenant activity grants, with
      independent audit-link authority and fresh rows/cursors on scope changes.
- [x] Guard all 16 Reports lifecycle actions against the publication contract;
      correct system attribution and report-export access categorization.
- [x] Native Audit suite: 218 passed / 13 infrastructure-dependent skipped;
      seven producer suites: 127 passed / 12 skipped. Console: 99 passed;
      browser: 4 passed over 48 layouts. Type/lint and generated-client checks pass.
- [!] Live VM and isolated broker/MySQL rehearsal not executed in this run.

See [review and reusable cases](activity-logging-completeness-review.md). The older
phase completion counts below are historical records, not the current test total.

## Implementation phases

- [x] Phase 0 — scaffold (`apis/audit`, `dbs/audit`), config (`AUDIT_*`), MySQL 9.6 conventions
- [x] Phase 1 — `audit_event` model: full §3 shape, composite PK `(occurred_at, id)`, nullable
      enrichment columns, tenant filter via `TenantMixin`
- [x] Phase 2 — migrations 0001 outbox / 0002 processed_message / 0003 audit_event
      (RANGE COLUMNS(occurred_at) monthly + `pmax`), one DDL per revision, downgrades present
- [x] Phase 3 — category taxonomy reconciled to the emit contract (`domain/categories`);
      parity test against `billing_platform.outbox._AUDIT_CATEGORIES`
- [x] Phase 4 — per-tenant hash chain (`domain/hash_chain`): deterministic canonical hashing,
      `verify_chain` break detection (tamper + sequence gap)
- [x] Phase 5 — envelope → event-fields mapping (`domain/ingest`), `extra="forbid"`, unknown
      category rejected, forward-compatible with enrichment fields
- [x] Phase 6 — ingestion consumer (`tasks/consume`): dedupe on `message_id`, single-writer
      sequence + chain assignment, idempotent redelivery; `run_consumer` is thin transport
- [x] Phase 7 — read surfaces (`api/routes`): audit trail (`audit.read`), security-gated
      (`audit.read_security`), activity feed (`activity.read`), detail (partition-pruned),
      export (`audit.export`) — the export itself staged as an `access` event on the outbox
- [x] Phase 8 — object-level scope on every surface (`api/auth` scoped grants): tenant-wide vs
      company/department, wrong-company → 403
- [x] Phase 9 — retention + partition arithmetic (`domain/retention`, `domain/partitions`):
      per-category floors, longest-lived basis for dropping, missing/expired planning
- [x] Phase 10 — maintenance jobs: partition create-ahead + expiry (`tasks/partitions`,
      privileged connection), chain verification (`tasks/verify`), scheduler (`tasks/scheduler`)
- [x] Phase 11 — tests: pure domain, consumer, verify, routes (auth/scope/isolation/export),
      DB isolation, migration shape + parity; MySQL smoke tool

## Mandatory close-out

- [x] `uv run pytest` — 86 passed, 2 skipped (containerised `@mysql` tests need Docker)
- [x] Coverage 92% overall; domain modules 98–100% (floor held)
- [x] `ruff check` clean; `mypy --strict` clean
- [x] MySQL 9.6 smoke: `upgrade head` → 4 tables + 5 partitions (incl. `pmax`) → `downgrade base`
      clean; `compare_metadata` reports **no drift** between models and the applied schema
- [x] Docs: `docs/audit.md` §3 categories reconciled, §7 open questions resolved, §8 decision log

## Deferred (documented in docs/audit.md §7–§8)

- [ ] **Integration-log surface** — distinct shape (delivery status, retries, response codes),
      schema underspecified; `audit_event` (trail + activity + export) ships first
- [ ] **Enriching `audit_payload`** on `libs/platform` with `source_service`, `actor_type`,
      `actor_ip`/`user_agent`, `api_client_id`, `company_id`, `department_id`, `request_id` —
      the columns already exist (nullable) and the consumer picks them up with no schema change
- [!] Live broker binding of `run_consumer` and Celery-Beat wiring of the maintenance jobs —
      deployment configuration, exercised in CI, not unit-testable here

## Decisions held throughout implementation

- MySQL 9.6, UUIDv7 `BINARY(16)`, UTC `DATETIME(6)`, InnoDB/utf8mb4; hashes `BINARY(32)`.
- Append-only by grant (INSERT + SELECT); no write API — events arrive over the broker only.
- Single chain writer (`consumer_prefetch=1`); per-tenant sequence + hash chain.
- Retention: security/money 7y, admin 3y, access/system 1y; expiry drops whole partitions.
- Tenant filtering, object-level scope, dedupe, and the outbox are mandatory on every path.
