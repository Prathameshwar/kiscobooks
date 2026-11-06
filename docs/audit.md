# Audit Service

**Status:** Core (`audit_event`) modelled and implemented — schema/partitioning, ingestion consumer, hash chain, read surfaces, and maintenance jobs. Integration-log surface deferred (see §7 / decision log).
**Date:** 2026-09-03 (implementation 2026-09-11)
**Owned by:** `audit` service
**Related:** [tech-stack.md](tech-stack.md) rules 4.4 (outbox), 4.5 (ledger), 4.12 (lifecycle) · [org-model.md](org-model.md) · [fiscal-year.md](fiscal-year.md)

---

## 1. Scope

`audit` owns three tenant-visible historical read surfaces, all fed from the same event stream:

| Surface | Audience | Purpose |
|---|---|---|
| **Audit trail** | Auditors, compliance, tenant admins | Who did what to which entity, when, with before/after values |
| **Activity feed** | End users | Friendlier projection of the same data — "Priya approved INV-1042" |
| **Integration log** | Tenant admins, support | Inbound/outbound webhook deliveries, API errors, export jobs |

Activity implementation clarification (2026-10-30): `/v1/activity` projects the
recorded actor type, actor reference, represented-user reference and authenticated
source service alongside action, subject, timestamp, category and company. It
does not return changed values, free-text context, IP/user-agent or hash evidence.
Historical absent metadata remains null; the UI does not invent a system actor.
The query loads only its projection and keyset sort fields.

Console defaults to Company activity. A current **tenant-scoped** `activity.read`
grant also exposes Organisation activity (the existing native tenant-wide query),
including business events without a company and across tenant companies.
Company-scoped grants cannot open this view. Organisation subject-history links
require tenant-scoped `audit.read` independently; company events retain their
recorded company in the link. Security events remain excluded from both activity
views, and platform notification evidence remains on its authorized platform
surface. See [completeness review](activity-logging-completeness-review.md).

### Explicitly out of scope

**Application logs, metrics, and traces do not belong here.** They are infrastructure concerns, handled by the OpenTelemetry → Grafana stack already in [tech-stack.md](tech-stack.md):

- Structured JSON logs to stdout → collected by the platform → Loki
- Metrics via the OTel SDK → Prometheus
- Traces via OTel → Tempo

Two reasons this is not a service:

1. **A log-receiving service cannot log the failures that matter.** A process that dies mid-request cannot POST its own death, and when the log service is down every other service either blocks or silently discards. Logging must not have a runtime dependency.
2. **It would be reimplementing Prometheus and Tempo, worse.** There is no version of a Python ingestion service that beats purpose-built time-series infrastructure.

**The bridge between the two:** every audit row stores the `trace_id` of the request that produced it. From an audit entry you jump straight to the trace in Tempo and the logs in Loki. That gives you the correlation without collapsing the concerns.

Implementation clarification (2026-10-22): the OpenTelemetry/Grafana flow above is the
architecture target. The current audit pipeline is a custom signed JSON event contract,
transactional outbox, RabbitMQ ingestion, and MySQL hash chain. It does not implement
OTel SDK instrumentation/export, W3C `traceparent` propagation, or an OTel/CloudEvents
audit schema. Current correlation uses bounded `X-Trace-Id` and request identifiers;
sanitized structured failure logs use the shared stdout logging helper. See the
[platform review](platform-audit-review.md) for implemented coverage and limitations.

---

## 2. Ingestion

### 2.1 Audit events are emitted in the same transaction as the change

The one rule that makes audit trustworthy. An audit event is written to the **emitting service's outbox**, in the same database transaction as the business change it records ([tech-stack.md](tech-stack.md) rule 4.4). The outbox poller publishes it; `audit` consumes it.

```
billing tx: ── write invoice row ──┐
                                   ├── COMMIT
            ── write outbox row ───┘
                                        │
                          poller ───► RabbitMQ ───► audit consumer ───► audit_event
```

Why not a direct call or a fire-and-forget publish:

- **Direct HTTP call to `audit`** — either it blocks the business transaction (audit outage stops invoicing) or it's best-effort (changes exist with no audit trail, which is precisely what an auditor looks for).
- **Publish after commit** — a crash between commit and publish loses the audit record permanently. RabbitMQ has no replay ([tech-stack.md](tech-stack.md) rule 4.5), so it is unrecoverable.

The outbox resolves both: completeness is guaranteed by the transaction, decoupling by the async delivery. Emission belongs in the shared platform library so every service does it identically.

### 2.2 `occurred_at` is the source timestamp

Set by the emitting service at the moment of the change — never the consumer's receipt time. Replica lag and redelivery would otherwise reorder history.

Consumers dedupe on the outbox `message_id`, since delivery is at-least-once.

---

## 3. Event shape

```
audit_event
  id, tenant_id
  occurred_at                    -- source timestamp; partition key
  sequence                       -- per-tenant monotonic, assigned by the consumer

  -- actor
  actor_type                     -- user | service_account | system
  actor_user_id                  -- reference only, never denormalized PII (§5.2)
  on_behalf_of_user_id           -- impersonation: support acting as a tenant user
  actor_ip, actor_user_agent, api_client_id

  -- scope
  company_id, department_id

  -- what happened
  category                       -- data | security | financial | admin | access
  action                         -- created | updated | deleted | approved | posted |
                                 -- closed | locked | logged_in | exported | ...
  entity_type, entity_id
  changes (JSON)                 -- changed fields only: {field: {from, to}}
  context (JSON)                 -- action-specific extras

  -- correlation
  source_service
  trace_id, request_id
  message_id                     -- outbox id; dedupe key

  -- integrity
  prev_hash, row_hash            -- see §4.2
```

### Categories

Reconciled to the **emit contract** in `billing_platform.outbox.audit_payload`, which two
services already publish through — that contract is operative and this draft's original
list (`data`/`financial`) had drifted from it (see decision log).

| Category | Examples | Retention |
|---|---|---|
| `security` | Login, role assignment, permission change, impersonation, token issue/revoke | 7 years |
| `money` | Posting, period close/lock, invoice-number allocation, credit note (was `financial`) | 7 years |
| `admin` | Company config, custom field definitions, tenant settings | 3 years |
| `access` | Sensitive reads and exports — see §5.3 | 1 year |
| `system` | System-originated changes, projections, background jobs (was the `data` bucket) | 1 year |

---

## 4. Immutability

### 4.1 Enforced by grant, not convention

The runtime database user holds **`INSERT` and `SELECT` only on `audit_event`**. No `UPDATE`, no `DELETE` on evidence. Outbox and inbox infrastructure have separate grants for their required operations. Per-service grants are already the isolation mechanism ([tech-stack.md](tech-stack.md) § Isolation rule), so this costs nothing extra and makes tampering impossible through the application, not merely forbidden.

Retention deletion runs as a separate privileged job dropping whole partitions (§6) — never row-level deletes.

### 4.2 Hash chain

Each row stores `prev_hash` (the previous row's `row_hash` for that tenant) and `row_hash` = hash over the row's content plus `prev_hash`. Any retroactive edit breaks the chain from that point on and is detectable by a verification job.

**This is cheap only because `audit` has a single writer** — one consumer assigns `sequence` and computes the chain. Scaling to multiple concurrent consumers per tenant would require partitioned chains or a sequencer. Decide before scaling out; retrofitting a chain over existing rows is worthless, since the unchained history can't be verified.

Run chain verification as a scheduled job and alert on breaks.

---

## 5. Access and privacy

### 5.1 Permissions

Defined in `identity`'s catalogue ([org-model.md](org-model.md) §5.3), assigned at company or tenant scope:

```
audit.read              -- read the audit trail for the granted scope
audit.read_security     -- security-category events (separately gated)
audit.export            -- bulk export
activity.read           -- the friendly activity feed
```

Tenant admins see their own tenant only. Platform admins have no blanket tenant
business audit access; support uses time-bound, audited impersonation.

### 5.1.1 Platform administrative history

`GET /v1/platform-events` and `GET /v1/platform-events/{event_id}` provide administrative
evidence in the operator's **operating tenant**. Identity verifies the configured OIDC
operator and current grants, then signs the existing actor context with a platform
history purpose marker. Audit verifies that context, rejects impersonation, and applies
session-level tenant isolation plus exact Identity event/entity families:

| Existing tenant-scoped permission | Evidence family |
|---|---|
| `platform.account.read` | Account access, imports, drift, reconciliation and decisions |
| `platform.tenant.read` | Tenant access, provisioning, metadata/lifecycle changes and invitation handoff |
| `platform.config.manage` | Installation completion, platform details and reference catalog changes |

No ordinary `audit.read`/`audit.read_security` grant is added. Business-company and
department evidence is excluded; clients cannot select another tenant. Security events
within the authorized family are included. There is no platform export or write route.
List filters are bounded category, exact subject type/UUID and UTC time range; pagination
uses signed keyset cursors bound to query, actor, tenant and current grants. Detail requires
the exact `occurred_at` partition timestamp. Values are conservatively projected to safe
state/reference facts and changed-field markers; free-text reason/context and network
identifiers are withheld, including from legacy evidence. Restricted output is not a
complete payload for independently recomputing stored chain hashes.

### 5.2 PII and erasure

Audit is immutable; erasure requests are not optional. These reconcile only if audit rows never contain PII directly.

**Store `actor_user_id` as a reference. Never denormalize name, email, or phone into the row.** Display names are resolved at read time from `identity`. When a user is anonymized ([org-model.md](org-model.md) §4.3), the audit trail keeps its referential integrity — "user 4f2c approved INV-1042" stays true and verifiable — while the PII is gone from the one place it lived.

Denormalizing the actor's email for display convenience would make the hash chain and the erasure requirement mutually exclusive.

### 5.3 Auditing reads

Do not audit ordinary reads — the volume dwarfs everything else and the signal is near zero. Audit these specifically:

- Viewing bank account details, tax registrations, or payment instruments
- Any bulk export or report download
- Impersonation sessions (start and end)
- Permission and role changes (a write, but the highest-value one)

**Exports are audited, including audit exports.** A read of the audit trail that produces a file is itself an `access` event.

---

## 6. Volume and retention

`audit_event` will be the largest table in the system by an order of magnitude — it grows with activity, not with customers.

- **Own database, own service.** Never co-located with transactional data.
- **RANGE partition on `occurred_at`, monthly.** Create partitions ahead via Celery Beat, the same way fiscal periods are generated ([fiscal-year.md](fiscal-year.md) §6).
- **MariaDB gotcha:** every unique key on a partitioned table must include the partition column. The primary key is therefore `(occurred_at, id)`, not `id`. This constrains the schema and cannot be changed later without a full rebuild — get it right in the first migration.
- Retention uses `money`, `security`, `admin`, `access`, and `system` (?7); a mixed-category monthly partition retains the longest applicable floor.
- Expiry drops partitions. Archive to object storage before dropping if the retention policy requires recoverability.

---

## 7. Open questions

- [x] **Retention period per category — RESOLVED (defaults, revisable per jurisdiction):** `security` and `money` 7 years; `admin` 3 years; `access` and `system` 1 year. Encoded in `domain/retention.RETENTION` and applied by the partition-drop job. Jurisdiction rules may extend these.
- [x] **Tamper-evidence — RESOLVED: treated as a requirement.** The per-tenant hash chain is always written and a verification job (`domain/hash_chain` + `tasks/verify`) checks it; whether a break pages someone or files a report is ops-config on the alert, not a code toggle.
- [x] **Activity feed push vs poll — RESOLVED: polling.** The feed is a keyset-paginated read of the same `audit_event` rows (no websocket/push infra in v1). Real-time push can be added later without a schema change.
- [~] **Webhook/integration-log surface — DECISION: lives in `audit` (per the doc's assumption), implementation deferred.** Its schema is not specified here and it is a distinct shape from `audit_event` (delivery status, retries, response codes). `audit` v1 delivers the fully-specified `audit_event` (audit trail + activity feed + export); the integration-log table + read is a documented follow-up.
- 2026-11-05 schema sync review: the deferred integration-log handlers are kept
  on an unmounted router. Hiding routes from OpenAPI does not disable HTTP;
  leaving them on the mounted router would access a table intentionally absent
  from the v1 Alembic metadata and migration chain. The model remains a draft
  until the schema and ingestion contract are decided together.
- [x] **Retention vs erasure — CONFIRMED sufficient.** §5.2 (actor as `actor_user_id` reference, PII resolved at read time, anonymized in `identity`) preserves the *fact* of actions and the chain while removing PII. That is the intended reconciliation.
- [x] **Write API — RESOLVED: no.** Events arrive over the broker only (like `notification`'s send path). There is no general write endpoint; a client-side action needs an owning service to emit it.

## 8. Decision log

- **2026-11-05 — Audit schema sync review.** The integration-log model remains
  an unshipped draft under §7; no Alembic table is added before its schema and
  ingestion contract are decided. Its handlers now live on an unmounted router,
  because `include_in_schema=False` hides documentation but still serves HTTP.
  The active Audit API therefore accesses only migrated tables.

- **2026-10-30 — Activity provenance and authorized organisation view.** Retain
  actor type, represented-user and source metadata in the lean activity response;
  reuse existing tenant/company native query authority for the two Console views.
  Scope changes discard client rows/cursors and abandoned requests. Reporting's
  audit helper rejects undeclared lifecycle actions before staging, records system
  work as `system`, and classifies report exports as `access`. Existing evidence is
  unchanged. Findings and verification are in the completeness review above.

- **2026-10-29 - Bounded cursor binding for broad administrators.** Audit and
  activity pagination embed a SHA-256 digest of the canonical binding facts,
  rather than the entire permission/policy payload. The binding includes surface,
  tenant, effective and real actor, impersonation, restricted audit scope, current
  grants, field policies and query parameters except the cursor itself. The shared
  signed codec, expiry, size limit and authorization on every read are retained.
  Cursors issued before this binding revision return 422; reload the first page.
  The retained three-company QA tenant returned two distinct pages on both
  surfaces with 378-character cursors, and cross-company replay returned 422.
  See [batch execution](tenant-admin-foundation-fixes-2026-10-29.md).

- **2026-10-29 - Master delivery, evidence and history consistency.** Registered all
  native banking actions, retained safe opening amounts/currencies/references and
  normalized new and historical Notification evidence. Shared request middleware
  supplies bounded correlation to every API; gateway and API access logs exclude
  sensitive query values. Publishers warn on stalled eligible outboxes while retaining
  historical privacy cutoffs. The single consumer accepts a bounded union of up to
  4,096 routes; each signing key remains limited to 1,024 routes and prefetch stays one.
  Local preparation/startup covers all eight issuers, and delivery health includes
  workers, outboxes and broker queues. Console activity uses the existing scoped API;
  master history and generated subject choices reuse central audit reads. Historical
  primitive evidence remains readable without implying missing before/after values
  were recorded. See [implementation and operations](master-audit-implementation.md).

- **2026-10-22 - Platform administration coverage.** Added operating-tenant evidence
  for tenant changes, account imports/drift and invitation handoff, and admitted the
  already-emitted setup completion route to Identity's exact publisher contract.
  Platform history reuses existing administrative grants, configured-operator verification,
  session isolation and signed pagination. UI history reads the generated Audit client;
  mutations emit in the owning transaction. Private free text remains outside immutable
  platform evidence. Deferred integration-log routes remain outside the published OpenAPI
  contract. OTel remains an infrastructure target. [Review and rollout](platform-audit-review.md).

- **2026-09-11 — Implemented the `audit_event` core.** Scaffolded the service (own DB, own alembic chain), the ingestion consumer (dedupe on `message_id`, per-tenant monotonic `sequence`, hash chain), the three read permissions' surfaces (audit trail, activity feed, security-gated, export — the export itself audited), and the partition-create/retention-drop/chain-verify jobs. MySQL 9.6 per the platform datastore reversal (tech-stack.md).
- **Category set reconciled to the emit contract** (`admin, security, access, money, system`) — the draft's `data`/`financial` had drifted from `billing_platform.outbox.audit_payload`, which identity and notification already publish. §3 updated.
- **Event shape vs emit contract:** `audit_event` carries the full §3 shape, but `audit_payload` today populates only `action, category, entity_type, entity_id, actor_user_id, on_behalf_of_user_id, changes, reason`. The richer columns (`source_service, actor_type, actor_ip, actor_user_agent, api_client_id, company_id, department_id, request_id`) are **nullable** and stay null until the emit contract is enriched — a follow-up on `libs/platform`, tracked here.

- **2026-09-17 - Accounting integration and authenticated reads.** New Accounting actions are
  canonical full event names. An immutable, issuer/schema-bound compatibility manifest accepts
  the original short verbs without rewriting signed bodies or historical evidence. The
  [accepted contract](accounting-audit-contract.md) defines safe before/after fields, exact
  Decimal strings, per-page export access events and sensitive detail access. Correlation and
  original/effective actors now flow through the outbox; authenticated issuer sets source service.
  This supersedes the September 11 note that all richer provenance was still unpopulated.
- **2026-09-17 - Current read authority applies to historical evidence.** Identity resolves
  Accounting field policies and company step-up scope for the gateway's signed Audit actor.
  Conditional denies are conservative; missing policy context withholds Accounting field
  evidence. Legacy Accounting free-text metadata/reasons cannot bypass the projection. Stored
  hashes remain unchanged; restricted API output alone cannot independently verify the chain.
  Actor names are optional, uncached Identity reads and never enter stored Audit rows.
- **2026-09-17 - Runtime and console.** Three separate workers deliver Accounting and Audit
  export events, with confirmed publication, exact-ID recovery and authenticated dead-letter
  inspection. The existing console now uses the generated Audit client, on-demand detail and
  server-authorized JSON export. [Operations](accounting-audit-operations.md) and
  [review/fix passes](accounting-audit-integration-review.md) record rollout and verification.
- **2026-09-17 - Final review hardening.** Chain verification paginates by sequence plus
  the physical `(occurred_at, id)` row key, detecting duplicate sequences across page boundaries.
  Authenticated ingress validates the existing column lengths and finite JSON before database
  access, dead-lettering those permanent payload defects while preserving database-outage retry.
  Unexpected HTTP failures use a generic error envelope with explicit `Cache-Control: no-store`.
  The [final review](accounting-audit-integration-review.md) records regression-first fixes and
  native MySQL/RabbitMQ/browser verification.

- **2026-09-17 - Catalog integration.** Catalog uses the existing authenticated outbox path,
  with exact entity/route binding, current historical field policies (including custom-field
  marker keys), and conservative protection of legacy aggregate evidence. Safe values retain
  exact Decimal strings and currency/unit references; report downloads emit access events.
  The gateway resolves Catalog actors through Identity and replaces incoming actor headers.
  Catalog joins the shared worker/status/recovery tools and existing Audit console. See the
  [Catalog contract](catalog-audit-contract.md) and [operations](catalog-audit-operations.md).

- **2026-10-11 - Voucher integration review.** Reconciled the Vouchers publisher's exact
  route list with its posting emitter, classified new voucher/operation evidence as `money`
  for financial retention, and applied current field policies and metadata projection to
  voucher detail/export reads. The [integration review](voucher-audit-integration-review.md)
  records rollout requirements and the reference-only evidence boundary.

- **2026-10-13 - Counter drawer authority.** Added counter master, operator-roster,
  session and cash-event routes to the Vouchers publisher's exact event allowlist.
  Operator assignment/revocation events carry security category, company and actor
  references, the changed status and a reason on status changes. The cash drawer's
  financial source remains its posted voucher; session and cash-event evidence uses
  financial retention, while recording custody rather than another ledger posting.

- **2026-10-25 - Design (document layout) becomes an issuer.** `design` joins the exact
  issuer set in `audit/domain/source_contract.py`, so a `design.*` event must carry
  `entity_type` equal to its event's entity prefix like every other service's. Its routes
  are `design.<entity>.{create,update}` for the six layout entities plus
  `design.invoice_template.publish`, `.archive`, `design.invoice_template_version.publish`
  and `.deactivate` on assignments, assets and components
  ([invoice-design.md](invoice-design.md) §7). Layout changes are `admin`; a render
  snapshot is `access`, because a print is a read of a document that happened — it records
  which immutable template version produced an artifact, never another ledger posting. A
  layout tree is deliberately absent from every payload: it is large, already versioned
  immutably, and the auditable fact is which version became live. Design events need an
  `AUDIT_SOURCE_CREDENTIALS` entry for the `design` issuer before ingestion accepts them.

- **2026-11-03 - Local startup contract refresh.** An already configured Windows audit
  pipeline refreshes its explicit native event allowlists before starting delivery
  workers. A private runtime fingerprint forces reload on first use, contract changes,
  and interrupted reloads; unchanged workers are reused. Publishers stop before the
  consumer, which starts before publishers. Signing identities, privacy cutoffs and
  immutable evidence remain intact. Health names unconfigured/stalled issuers and
  startup names the unhealthy component. See [startup repair](audit-startup-fix.md).
