# Notification microservice implementation checklist

Status values: `[ ]` pending, `[~]` active, `[x]` complete, `[!]` externally blocked.

This checklist is the execution record for `docs/notification.md`. A phase is only
complete when its implementation, migration/model parity, tests, and relevant
documentation are complete.

The follow-up review found unresolved bugs after NR0–NR5. Current one-at-a-time fixes
and final verification are tracked in [notification-review-fixes-todo.md](notification-review-fixes-todo.md).

## Implementation phases

- [x] Phase 0 — architecture, MySQL schema, API/list conventions, and provider choices
- [x] Phase 1 — shared platform pagination, callback security, and event primitives
- [x] Phase 2 — service skeleton, configuration, health/readiness, outbox/inbox foundation
- [x] Phase 3 — permission catalogue and notification event contracts
- [x] Phase 4 — provider-account CRUD/list + **sender-identity API** complete (`api/management`)
- [x] Phase 5 — send-time consent/suppression/preference/endpoint resolution (`domain/planning`, `domain/policy`) + suppression/consent management APIs + the **preference projection consumer** (`tasks/project`: version-ordered, idempotent) complete (its live-broker binding is thin transport)
- [x] Phase 6 — routing/template policy + **management APIs** complete: template/variant/version (immutable, content-hash unique) / activation (overlap-locked) / provider-template-binding / routing-rule (`api/management`)
- [x] Phase 7 — **send-command consumer built** (`tasks/consume`): §5 ten-gate planning, delivery + encrypted-content creation, idempotent on source `message_id`; request list complete
- [x] Phase 8 — delivery attempts, per-channel callback capture, delivery timeline, **and the async normalizer** (`tasks/normalize`: `provider_event` → `delivery_event`, no-regression via `should_advance`) (0019–0021)
- [x] Phase 9 — attachment registration + **scan gate** complete (`domain/attachments`, `api/management`): only a ``clean`` attachment attaches to a delivery; filename encrypted; live malware-scanner integration is the external hook
- [~] Phase 10 — SES send adapter + callback status normalization (`providers/normalize`) + HMAC signature path complete; **SNS X.509 (RSA) verification is the live hook** (needs the AWS signing cert) and live certification is external
- [~] Phase 11 — Twilio send adapter + callback status normalization + **`X-Twilio-Signature` verifier** (`providers/verify.verify_twilio`, SHA-1 over url+params, fixture-tested end to end) complete; only live-account certification is external
- [~] Phase 12 — Meta WhatsApp send adapter + callback status normalization + **`X-Hub-Signature-256` verifier** (HMAC-SHA256, tested) complete; only live-account certification is external
- [x] Phase 13 — Firebase Cloud Messaging push adapter and response normalization
- [~] Phase 14 — CRUD/list, authorization, **and the MySQL 9.6 test harness + two-tenant isolation** complete; live MySQL `EXPLAIN`/canary certification requires the deployment database
- [x] Phase 15 — operations runbook + **scheduled jobs** complete (`tasks/maintenance`, `tasks/scheduler`): retention crypto-purge, stuck-`sending` detection, unmatched-event reconciliation, due-retry surfacing, and normalizer, tied into one tested `run_maintenance_once` pass (the interval loop is thin transport)
- [~] Phase 16 — implemented slice locally verified; remaining phases above block release

## Mandatory close-out

- [x] Review pass 1 — fixed startup factory, ambiguous-send handling, verifier configuration, formatting, and migration parity coverage
- [x] Review pass 2 — 16 tests, lint, compilation, schema inventory and field/nullability parity clean
- [x] Final test and lint evidence recorded (type checker is not installed in this workspace)
- [x] External credential-dependent checks identified in `docs/notification-operations.md`

## Decisions held throughout implementation

- MySQL 9.6, UUIDv7 stored as `BINARY(16)`, UTC `DATETIME(6)`, InnoDB/utf8mb4.
- Email, SMS, WhatsApp, and push are explicit channels; transport is not left open-ended.
- Provider network calls never run inside a database transaction.
- Provider callbacks are verified, durably captured, acknowledged quickly, then normalized async.
- Tenant filtering, permission checks, idempotency, outbox/inbox, and secret references are mandatory.
- List APIs use cursor pagination, typed filters, allowlisted search/sort, lean projections, and indexes.
- Shared mechanisms live in `libs/platform`; notification policy lives in `apis/notification`.

## Voucher integration addendum (2026-10-13)

- [x] Source-scoped signed Voucher and Accounting ingress, party endpoint
  projection, company-fenced voucher evidence, terminal-state cancellation.
- [x] Opt-in SES/Twilio/Meta/FCM dispatch runner and retryable-failure backoff;
  ambiguous sends stay in reconciliation.
- [ ] External voucher artifact handoff and statutory invoice certification;
  current send commands contain template variables only.
- [!] Live provider callbacks, MySQL migration and canary verification need
  deployment credentials/infrastructure before channel activation.

## Remediation & Cross-Service Enhancement Plan (2026-10-15)

Tracked in detail in [`docs/notification-remediation-plan.md`](notification-remediation-plan.md).

- [x] **Phase NR0** — Test harness restoration, typed test fixes (mypy 25 errors), and reproduction fixtures
- [x] **Phase NR1** — Dispatcher & worker resilience: B01 busy-loop fix, B03 scheduled send fix, B04 retry exhaustion fix, G01 finalization timestamps/outbox
- [x] **Phase NR2** — Provider adapters & webhooks: B02 payload extraction (Twilio/Meta/SES), B07 SES HTML body support, B08 WhatsApp parameter fix
- [x] **Phase NR3** — Governance, concurrency & API: B05 activation locking, B06 route validation/specificity, G02 manual retry API, G06 legacy loop deprecation
- [x] **Phase NR4** — Producer service integrations: G03 voucher payload/artifacts (enriched variables), identity/accounting backlog tracked
- [x] **Phase NR5** — End-to-end multi-tenant validation, type checking, and OpenAPI client regeneration
