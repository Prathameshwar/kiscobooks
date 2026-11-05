# Tech Stack — Billing Platform

**Status:** Agreed
**Date:** 2026-09-03
**Scope:** Microservice backend with web and mobile clients.

**Architecture revision, 2026-10-10:** The user replaced the planned Billing and Payments
APIs with one Vouchers API. Accounting retains its implemented ledger/fiscal authority.
The [Vouchers plan](vouchers-plan.md) defines 22 accounting, inventory, order and general
kinds; payroll and related work are excluded. Its stock-posting boundary and phase details
are proposals to finalize before implementation. This revision supersedes older service
ownership/build-order statements, including historical decision-log entries below.
Indents, Purchase Orders, Sales Orders, Quotations and Delivery Challans are explicit core coverage.
Indents/orders/quotations have no actual stock/account-balance effects. Requisition, Quotation
and Delivery Challan are required profiles within the 22-kind catalogue, not extra posting engines.
Job work in both directions is included later scope. Company-created voucher types and typed
header/item-line custom fields reuse the [existing customization design](voucher-extensibility.md).
[India GST and state-VAT recording](voucher-tax-recording.md) adds native statutory facts,
separate tax dates, eligibility and reporting; supported VAT states remain to be selected.
All kinds/company types use the [shared voucher data model](voucher-data-model.md): one
header/revision/line core plus reusable typed details for accounts, inventory, charges/tax,
advances and tenders. Each type declares required/optional/forbidden sections. Creating a
voucher type does not create document tables; Accounting remains the effect authority.
The [voucher table inventory](voucher-table-inventory.md) distinguishes proposed document
tables from reused infrastructure/masters and authoritative Accounting effects.
The [Tally functional review](tally-voucher-functional-review.md) adds Journal/Stock Journal/
banking behavior and shared dimension/instrument/reconciliation design gates; documented
Tally features do not imply implementation or full feature-parity scope.
The [settlement review](tally-settlement-functional-review.md) adds Payment/Receipt purposes,
bill adjustment and advance/refund lifecycles using the same document and allocation boundaries.
The [invoice calculation contract](voucher-invoice-calculation.md) specifies Sales/Purchase
entry modes and separates commercial total, statutory tax, landed cost and payment settlement.
The [order/fulfillment review](tally-order-fulfillment-review.md) adds non-posting indents,
shared quantity/date schedules, guarded conversion and separate movement/billing progress.
The [implementation roadmap](voucher-implementation-plan.md) consolidates these contracts into
owner-specific work packages, decision gates, release dependencies and acceptance evidence.
The [delivery tracker](voucher-delivery-tracker.md) records reviewed batch prerequisites,
kind/profile coverage and the evidence needed before verification and activation.

---

## 1. Stack

| Layer | Choice |
|---|---|
| **Service framework** | Python 3.12 + FastAPI |
| **Validation / schemas** | Pydantic v2 |
| **ORM / migrations** | SQLAlchemy 2.0 + Alembic |
| **Database** | MySQL 9.6 — one database per service, InnoDB, `utf8mb4` |
| **DB driver** | `asyncmy` (`mysql+asyncmy://`) |
| **Ingress / gateway** | nginx — `ingress-nginx` on K8s; plain nginx in compose for local dev |
| **Async messaging** | RabbitMQ (`aio-pika` for consumers) |
| **Background & scheduled jobs** | Celery, RabbitMQ broker, Celery Beat for schedules |
| **Cache** | Redis (cache only — not a broker) |
| **Auth / IdP** | `AUTH_PROVIDER`, chosen per installation: **local** (default; Identity is the OIDC provider, [local-auth](local-auth.md)) or Authentik (Django-based OIDC provider + dedicated PostgreSQL) |
| **Token validation in services** | `joserfc` (`billing_platform.oidc`) — JWKS, RS256; the same verifier for either provider |
| **Web frontend** | Next.js (React + TypeScript), `next-auth` generic OIDC provider |
| **Mobile** | React Native (Expo, TypeScript), `expo-auth-session` |
| **API contract → clients** | FastAPI-generated OpenAPI → generated TypeScript client |
| **Monorepo / packaging** | pnpm workspaces (frontend), uv (Python) |
| **Lint / format / types** | Ruff + mypy (strict) |
| **Backend tests** | pytest + pytest-asyncio + httpx; MySQL/RabbitMQ via testcontainers |
| **Web tests** | Vitest + React Testing Library (Playwright for E2E only) |
| **Mobile tests** | Jest (`jest-expo`) + React Native Testing Library |
| **Containers** | Docker |
| **Orchestration** | Kubernetes + Helm |
| **CI/CD** | GitHub Actions |
| **Observability** | OpenTelemetry → Grafana stack (Loki / Tempo / Prometheus) |

### Runtime components

Backend services are Python. Two non-Python components remain by necessity:

- **Authentik's PostgreSQL** — Authentik does not support MySQL/MariaDB. Treated as a vendored appliance database: no application code touches it, no migrations of ours run against it.
- **Authentik Go outposts** — only if the reverse-proxy feature is enabled. Not needed: Identity validates the JWTs (through `billing_platform.oidc`) and hands every other service a signed actor context.

---

## 2. Service boundaries

Eight target services. Identity, Audit, Catalog, Accounting and Notification exist;
Vouchers has its Phase 1 common foundation; Reports has its B09 export/projection/run
foundation; Design owns document layout (2026-10-25 decision below). Financial voucher
execution and statement calculations remain later batches. There is no separate Billing or
Payments API.

| # | Service | Owns | Why it's a separate boundary |
|---|---|---|---|
| 1 | **identity** | Tenants, companies, departments, users, groups, roles; thin layer over Authentik. Model: [org-model.md](org-model.md) | Authority and company configuration shared by the business services |
| 2 | **audit** | Audit trail, activity feed, integration log. Design: [audit.md](audit.md) | Append-only, multi-year retention, largest table in the system, its own access control. Insert-only DB grant makes tampering impossible rather than merely forbidden |
| 3 | **catalog** | Products, units, locations, price/tax definitions and optional BOM/promotion definitions | Definition publication is separate from physical or financial posting |
| 4 | **accounting** | Parties/accounts, journals, fiscal controls, openings, settlements, credit and tax; proposed stock/custody/value posting extensions | Authoritative posting effects remain together; existing financial implementation is reused |
| 5 | **vouchers** | Voucher types, drafts/revisions, approvals, sales/purchases, receipts/payments, inventory/order/general document workflows, provider adapters and print artifacts | One transaction-document API; submitted effects are committed by Accounting through a reliable command/result contract |
| 6 | **reports** | Read models, aggregates, report definitions, generated artifacts | Analytical load uses its own projections; financial outputs reconcile to Accounting. See rule 4.11 |
| 7 | **notification** | Email / SMS / WhatsApp / Push delivery; templates, routing, attempts, receipts, consent projection and suppression. Design: [notification.md](notification.md) | Send commands arrive only through RabbitMQ. The sole unauthenticated HTTP ingress is provider-specific signed callback endpoints; there is no public or synchronous send API. Delivery state is operational evidence, not billing domain state |

| 8 | **design** | Document layout: templates, immutable layout versions, routing rules, brand assets, reusable blocks and print evidence. Design: [invoice-design.md](invoice-design.md) | Presentation is separated from document content: a template edit must not be able to change a figure, and its own database keeps the layout compiler away from money tables. It renders nothing — it answers "which layout" and records "what was printed" |

**Current integration direction:** Catalog publishes product/SKU, unit/pack, price/tax,
tracking and warehouse definitions. Accounting supplies authoritative commercial parties
and dated classifications. Vouchers owns transaction documents and workflow orchestration.
The proposed posting boundary keeps physical lots/units, inventory movements/reservations,
valuation and corresponding financial effects together in Accounting. Promotion definitions
remain Catalog-owned; if enabled later, live holds/redemption must share the authoritative
posting transaction with their money/stock effects. No inventory or promotion execution is
claimed by this plan. See [Vouchers ownership and phases](vouchers-plan.md#3-service-ownership).

**Two different records, both called an "audit trail":**

- The **ledger** in `accounting` is the *financial* record — what the money did. Append-only, source of truth for statutory reports (rule 4.5).
- The **audit trail** in `audit` is the *actional* record — who did what, when, from where. Compliance and forensics ([audit.md](audit.md)).

Neither substitutes for the other, and neither lives in the other's database.

### Build order

Dependency order for the revised plan; this is not a claim that existing services were
built in this order. Notification is already available for invitation and document delivery.

```
0. shared platform library
1. identity      (everything will depend on it)
2. audit         (establishes the durable evidence pattern)
3. catalog       (product, price, tax and location definitions)
4. accounting    (masters and authoritative financial posting; already implemented)
5. notification  (existing event-driven delivery and provider callbacks)
6. vouchers      (V0-V6 core; Accounting stock in V4; optional gateway V7; included job work V8)
7. reports       (V9.1 foundation alongside Vouchers V1; exports with V3/V4/V8; final V9 hardening)
```

**`audit` goes early deliberately.** Retrofitting audit emission means revisiting every write
path. Identity alone supplies enough events to exercise the common emission pattern before
voucher workflows are built.

The list names dependency foundations, not isolated service completion. Required Reports
exports and statutory documents ship with the transaction profiles that depend on them;
Vouchers does not wait until after all job work to start Reports. Optional V7 gateway work
is independent of required V8 job work. See the implementation roadmap's release graph.

**Step 0 is not optional.** Before the first service, build one shared Python package holding: JWT/JWKS validation, the outbox implementation and publisher, SQLAlchemy session and engine setup, OpenTelemetry wiring, RabbitMQ connection management, and base Pydantic config. Six services each hand-rolling token validation is the concrete failure mode of this architecture, and consolidating later is far harder than factoring out now.

### What deliberately does *not* get its own service

This is where the service count inflates without anyone deciding to inflate it.

- **PDF / document generation** → a Celery worker inside the service that owns the data (rule 4.10). CPU-bound work, not a bounded context.
- **Tax calculation** → product tax definitions live in `catalog`; accounting tax and authoritative tax posting live in `accounting`. `libs/platform` supplies the calculation mechanism for previews and posting against versioned local facts. Vouchers carries the document inputs and displays the result; preview is not posting authority. See [tax-accounting-plan](tax-accounting-plan.md).
- **Payment gateways** → isolated adapters/workers and signed callbacks within `vouchers`, with a separate intent/attempt lifecycle. Payment and Receipt vouchers reuse Accounting's settlement authority; there is no standalone Payments service. Payroll and related HR capabilities are out of scope.
- **API gateway** → nginx config, not code.
- **Application logs, metrics, traces** → infrastructure, not a service. Structured JSON to stdout → Loki; OTel SDK → Prometheus and Tempo. A log-receiving service cannot capture the failures that matter most (a process that dies mid-request cannot report its own death), and when it is down every caller either blocks or discards silently. Logging must have no runtime dependency. See [audit.md](audit.md) §1 — audit rows carry `trace_id`, which gives correlation without merging the concerns.

### Reference data ownership

Country, currency, language, exchange rates, and fiscal calendars are read by nearly every service. **None of them justifies a reference-data service** — that would put a synchronous network call on the hot path of every write, for data that changes yearly, and would make posting an invoice fail because an unrelated service is down.

Three tiers, by how the data behaves:

| Tier | Examples | Lives in | Why |
|---|---|---|---|
| **Immutable global** | `country`, `state`, `currency`, `language`, timezone | **Shared platform library** as source of truth, **materialized into a small table in each service DB** | ISO 3166-1 / 3166-2 / 4217 / 639 change roughly yearly. See § *Reference tables* below — the library owns the data, the table exists so it can be joined, FK'd, and served to a dropdown |
| **Tenant / company config** | Enabled currencies, default language, fiscal-year start | **`identity`** (on `tenant` / `company`) | It is org configuration, and `identity` already owns those records |
| **Financial control and dated posting facts** | `fiscal_year` / `fiscal_period`, selected FX evidence, effective tax rates | **`accounting`** owns fiscal/financial state; Catalog owns product tax definitions replicated locally for posting | Must be readable inside the posting transaction, with no remote call, and reproducible for closed periods |

**The governing rule:** reference data read on a transactional write path must be local to the service doing the write. A money transaction never makes a synchronous cross-service call to validate or convert.

Accounting publishes committed financial/period events; Vouchers and Reports may keep
read-only projections. A projection permits previews and reporting, never a late posting
into a closed period. Accounting checks its current authoritative period under the posting
lock. Catalog/Identity facts needed by that transaction are replicated or supplied through
bounded, versioned authority contracts before it starts.

### Reference tables — natural keys, not UUIDs

Tier 1 defaults are **defined in `libs/platform` as static versioned data** and
materialized by seeds. For Country, State, Currency and Language, Identity also
owns platform-operator overrides and additions (decision 2026-10-21 below).
The service table remains a local projection: no cross-service FK or financial
write-time network hop.

The table exists because three things need it and static data alone cannot provide them:

1. **Referential integrity.** `company.base_currency` should be unable to hold `XYZ`. A Pydantic enum check is bypassed by any direct write, a migration, or a data fix.
2. **Joins.** Listing companies with their country and state names should not mean N lookups in Python, and `reports` needs to group and sort by them in SQL.
3. **A queryable dropdown.** Country and state are *selected*, so the client needs a searchable, paginated, localizable endpoint — not a hardcoded list per client.

**These four tables use their natural code as the primary key** — `CHAR(2)`, `VARCHAR(6)`, `CHAR(3)`, `VARCHAR(8)` — and are **the one deliberate exception to the UUIDv7 rule** (§4). Justification:

- ISO codes are already stable, globally unique identifiers. A surrogate UUID adds a join to learn something the code already tells you.
- `WHERE country_code = 'IN'` is readable in a query log and a data fix; `WHERE country_id = 0x0192...` is not.
- Codes are identical in every environment. Surrogate ids seeded per environment differ, so a fixture, a support script, or a replicated row means something different in staging than in production.
- ISO does not recycle codes. Retired codes stay retired, so a stored value never silently changes meaning.

They also carry **no `tenant_id`** and are exempt from the session-level tenant filter — the one exempt category, whitelisted explicitly in the shared library rather than by omission.

Codes are **never renamed**. Names, translations, and flags may change; the code is permanent because entity rows point at it.

Tax rules are the same shape: `catalog` owns product definitions and `accounting` holds
the local effective-rate copy used at authoritative posting time.

### Isolation rule

MySQL treats "schema" and "database" as the same thing. When service databases share an
instance, grants must prevent Vouchers from reading Accounting tables directly or Reports
from bypassing owner APIs.

**Each service gets its own DB user, granted access only to its own database.** That grant is what enforces the boundary — not convention.

---

## 3. Frontend strategy

One TypeScript monorepo containing web, mobile, and shared packages.

**Share business logic, not UI components.** The generated API client, domain types, validation schemas, and calculation rules (invoice totals, tax, proration) live in a shared package used by both clients. Written once, tested once.

**Do not share UI components.** Web and mobile get layouts native to their platform. Forcing shared components via React Native Web makes both worse.

The OpenAPI spec is derived from Pydantic models rather than maintained alongside them, so the generated client cannot drift from the server. Regenerate it in CI and fail the build on uncommitted diffs.

---

## 4. Non-negotiable implementation rules

These are cheap now and expensive to retrofit.

### 4.1 Money

- `DECIMAL(19,4)` for all monetary columns. Never `FLOAT`/`DOUBLE`.
- Store currency code alongside every amount.
- Verify `asyncmy` returns `decimal.Decimal`, not `float` — MySQL-family drivers have historically been sloppy here. Write a test that asserts the type.
- Set an explicit `decimal.Context` at app startup with the rounding mode your jurisdiction requires (`ROUND_HALF_EVEN` unless specified otherwise). Do not rely on defaults.

### 4.2 Transaction isolation

MySQL/InnoDB defaults to `REPEATABLE READ`. Under it, InnoDB takes gap locks on range scans, which causes deadlocks on concurrent inserts into the same index range — exactly what a batch invoice run does.

**Set `READ COMMITTED` globally** unless there is a specific reason otherwise.

### 4.3 Idempotency

Every money/stock-mutating voucher operation requires an idempotency key. HTTP retries,
broker redelivery and provider callbacks must also deduplicate by stable business source
identity, so changing a request key cannot create another posting or charge.

### 4.4 Transactional outbox

A RabbitMQ publish is not part of the database transaction. Commit an invoice, crash before the publish, and the event is lost permanently — RabbitMQ has no replay.

1. Write the domain row and an `outbox` row in the **same transaction**.
2. A Celery Beat task polls unpublished outbox rows, publishes to RabbitMQ, marks them sent.
3. Consumers dedupe on the outbox row's UUID (`message_id`) — the poller is at-least-once.

Shared code, roughly 60 lines. Non-optional for anything touching money.

### 4.5 Audit trail lives in the database

RabbitMQ deletes messages once acked. There is no event log to replay and no long retention.

**The append-only ledger table in MySQL is the source of truth for audit**, not the broker. Reconciliation and auditors query rows, not a message stream.

### 4.6 Messaging topology

- Topic exchanges for committed posting results and document-delivery events. A draft-created
  event must never trigger a second independent financial posting.
- **Every consumer queue gets a dead-letter exchange from day one.**
- Enable publisher confirms.

### 4.7 JSON columns

MySQL's `JSON` is a native binary type, but a JSON *path* still cannot be indexed directly — indexing needs a generated column over the path. Keep raw payloads (gateway webhooks, tax-rule metadata) in a `JSON` column for audit, and promote any field you filter on to an indexed generated column:

```sql
gateway_txn_id VARCHAR(64) AS (JSON_UNQUOTE(JSON_EXTRACT(payload, '$.id'))) STORED,
INDEX idx_gateway_txn (gateway_txn_id)
```

### 4.8 Migrations

MySQL DDL is atomic per statement but not transactional across statements. A multi-statement migration that dies partway leaves the schema half-applied and Alembic's version table out of sync with reality.

**One DDL statement per Alembic revision**, so a failure is unambiguous about where it stopped.

### 4.9 Auth

- One Authentik application + provider pair **per client**, not one shared.
- Mobile is a **public client** — no client secret, PKCE mandatory.
- Web (with a Next.js backend) can be a confidential client.
- Roles never travel in the token; permissions resolve server-side from Identity's own data (CLAUDE.md §5.4). An `org_id` claim, where the provider issues one, only binds a token to a tenant — the local provider issues none. Do not call the provider per request.
- Tenant scoping is enforced in the application layer (MySQL has no row-level security).

Service-side validation:

```python
from authlib.jose import jwt
# cache the JWKS; refresh on unknown `kid`
claims = jwt.decode(token, jwks, claims_options={
    "iss": {"essential": True, "value": f"{AUTHENTIK_URL}/application/o/<slug>/"},
    "aud": {"essential": True, "value": CLIENT_ID},
})
claims.validate()
```

### 4.10 CPU-bound work

FastAPI's async handles I/O-heavy paths well but blocks on CPU work. **Invoice PDF rendering and month-end aggregation go to Celery workers from day one** — not retrofitted later.

### 4.11 Reports read model

`reports` owns a **denormalized read model in its own database**, built by consuming RabbitMQ events (CQRS). It does not query other services' databases — rule 4.3's grants forbid it — and it does not fan out API calls per report.

Three consequences to build for:

**Backfill is mandatory.** The outbox/event contract must provide a consistent owner export
and checkpointed catch-up path; the broker alone is not a replay archive. Reports consumes
owner export endpoints or immutable owner-produced artifacts, not cross-database grants.

**Separate the consistency paths.** The read model is eventually consistent — correct for operational dashboards, wrong for anything statutory. A VAT return or revenue-recognition report that doesn't tie to the penny is worse than no report.

- *Analytics / dashboards* → query the read model. Surface the projection lag in the response.
- *Financial / statutory reports* → reconcile to Accounting's authoritative ledger export
  at an explicit `as_of` checkpoint. Scenario, optional and memorandum documents are excluded.

Required outputs are account ledgers, trial balance, P&L/Income & Expense, Balance Sheet and
incremental party/tax/stock/job-work registers. See the
[posting/reporting design](voucher-posting-reporting-design.md) for the catalogue, source
coverage and acceptance checks. Initial financial events are not a complete report feed.
A run pins both business dates and committed source manifests, plus formula/classification/
rule versions, history coverage, scope, reconciliation and artifact hashes. Owner snapshot
barriers must prevent missing or half effects during backfill/catch-up. Period locks alone
do not freeze reports; late data creates a new run. Complete financial outputs require
authorized access to every contributing input and source reconciliation.
The [stock recording/reporting design](voucher-stock-recording-reporting-design.md) specifies
inventory feeds and current/item/group/location/expiry/age/value outputs. Accounting serves
guarded operational availability; Reports uses declared snapshots and date evaluation.
Expiry depends on time as well as events; Catalog holds definitions, not editable balances.

**Report generation is async.** Large exports are CPU-bound and slow. `POST /reports` returns `202` with a job id; a Celery worker generates the artifact; the client polls or receives a notification event. Mobile clients cannot hold a request open for a month-end export.

### 4.12 Lifecycle columns

Pick **exactly one** mechanism per entity. Never two on the same table.

| Mechanism | Use when | Entities |
|---|---|---|
| `status` enum | The entity has a multi-state lifecycle with meaningful transitions | `tenant`, `user`, `company`, `fiscal_year`, `fiscal_period`, invoices, payments |
| `is_active` boolean | Binary question: may this be chosen for new records or not | `role`, `user_group`, `department`, `custom_field_definition`, price plans, notification templates |
| `valid_from` / `valid_to` | The value affects a computed financial figure | Tax rates, tax registrations, exchange rates, price lists |

Four rules:

**Never `status` and `is_active` together.** `status = suspended` with `is_active = true` has no defined meaning, and both will end up being written by different code paths.

**`is_active = false` means "not selectable for new records" — not "hidden".** It must not filter the entity out of historical data. Deactivating a department cannot break invoices already posted against it, and the department must still render on those invoices and in reports.

**Anything affecting a computed amount needs date validity, not a boolean.** A flag cannot express "this tax rate applied last year, a different one applies now" — and once a period is locked, recomputing it with today's rate is a correctness bug, not a rounding difference. This is the single most common modelling error in billing systems.

**Never hard-delete anything referenced by a posted document.** Pair `is_active` with `deactivated_at` and `deactivated_by`.

---

## 5. Decision log

Recorded so later stages don't relitigate settled ground.

### Python over Java/Spring Boot
**Chosen** for single-runtime consistency and team familiarity.

What Java would have given us: more turnkey plumbing (Spring Cloud Gateway, Spring Security OIDC, Spring Batch are config-level concerns rather than assembled pieces), and compiler-enforced types across service boundaries — mypy strict covers most but not all of this during cross-service refactors.

What it would *not* have given us: better money precision or transactional integrity. `decimal.Decimal` is arbitrary-precision with explicit rounding contexts, and SQLAlchemy 2.0 handles transaction scoping fine. This was not a real differentiator.

Mitigation for the async/CPU gap: rule 4.10.

### MySQL 9.6 over PostgreSQL
**Chosen** by preference. Exact-decimal support is equivalent (`DECIMAL` vs `NUMERIC`).

Real costs accepted:
- DDL is atomic **per statement** but not transactional across statements → a
  multi-statement migration can still half-apply → rule 4.8 (one DDL per revision) stands
- JSON is a native type, but path filtering still needs an indexed generated column
  (no `JSONB` + GIN equivalent) → rule 4.7 stands
- No row-level security → app-layer tenant scoping
- No partial indexes (functional indexes exist; partial do not)

**Datastore decision reversed — see the decision log below (2026-09-11):** the target
and available engine is **MySQL 9.6**, not MariaDB 11.4. The schema, the numbered rules,
and the invariants are engine-neutral in every respect that matters here (NULL-in-UNIQUE
distinctness, `DECIMAL` truncation, `utf8mb4_unicode_ci`, `ROW_FORMAT=DYNAMIC`,
`SELECT … FOR UPDATE`), which is why the reversal is a configuration and documentation
change, not a schema rewrite. Two genuine differences to keep in mind: MySQL's `JSON` is
a native binary type (MariaDB's is a `LONGTEXT` alias), and MySQL 8+/9 runs
`STRICT_TRANS_TABLES` by default, so an over-long value **raises** rather than truncating
silently — a safety improvement over the behaviour §5 was guarding against.

### Authentik over Keycloak
**Chosen** for Python/single-runtime consistency.

Cost: Authentik requires PostgreSQL, reintroducing a second database engine. Accepted as an appliance concern (see §1).

Keycloak runs on MySQL/MariaDB and would have kept one engine, at the cost of a JVM in the stack. Trade was: avoid a second runtime > avoid a second engine.

### nginx over Traefik
**Chosen.** Deployed as `ingress-nginx`, which provides the same dynamic service discovery via Ingress resources — so no capability lost on Kubernetes. Local dev uses a static nginx config, which is fine since the service list is fixed.

A gateway *is* required: single entry point for web and mobile, TLS/CORS/rate-limiting terminated once rather than per service.

### RabbitMQ over Kafka
**Chosen.** Also consolidates — it serves as the Celery broker, so Redis reverts to cache-only. Net component count unchanged.

Lost: event replay, long retention, event sourcing → rule 4.5.
Gained: publisher confirms, per-queue DLX, per-message retry. Kafka's partition-offset model makes "retry this one poisoned message" awkward, which matters for payment webhook processing.

Consequences to watch:
- The outbox pattern (4.4) becomes mandatory rather than merely advisable, because lost events are unrecoverable.
- `reports` cannot rebuild its read model from the event stream, so batch backfill is a first-class requirement (4.11) rather than a convenience.

### `reports` as a service from day one
**Chosen**, against an initial recommendation to defer it until a read replica or event consumer was needed.

Rationale for including it: analytical query load genuinely does not belong on billing's transactional database, and the boundary follows a real difference in access pattern rather than a guess about future scale.

Cost accepted: it is the only service needing two data paths (event-driven projections plus batch backfill), and the only one where eventual consistency is a correctness question rather than a latency one. Both are handled by rule 4.11.

### Reference data as tables, not library enums alone
**Revised 2026-09-03.** The original decision was "static versioned data, no table, no FK, no join" for `country`, `currency`, and `language`.

**What changed:** country and state must be *selected from a list* on company creation, and `state` was added. Three needs the library-only form cannot meet: FK integrity (a currency code that cannot be invalid), SQL joins for listing and reporting, and a searchable endpoint for the dropdowns. State also carries real domain data — the GST state code that prefixes every Indian GSTIN.

**Resolution, not reversal:** the library remains the source of truth and is still read on write paths with no hop. The table is a per-service materialized projection seeded from it — the same shape as a tier-3 replica. The governing rule (*reference data on a write path is local to the writing service*) is unchanged.

**Cost accepted:** four extra tables per service DB, a seed step that must run before the first FK-bearing migration, and one deliberate exception to UUIDv7 primary keys (§4).

### Reference column widths follow ISO, and a country with no derivable value is excluded
**Added 2026-09-03**, on generating the committed datasets ([identity-schema.md](identity-schema.md) §1.1–§1.2).

**Widened:** `state.subdivision_type` and `country.subdivision_label` from `VARCHAR(40)` to `VARCHAR(60)`. ISO 3166-2 carries "Metropolitan collectivity with special status" at 45 characters. MySQL's default `STRICT_TRANS_TABLES` *raises* on an over-long value (MariaDB's default truncated silently), but the generator refuses to write any value wider than its column regardless — that guard is what found this one, and it holds on either engine. The rule going forward: widen the column, never truncate reference data.

**Excluded:** a country the authoritative databases cannot fully supply is left out of the dataset and logged, rather than seeded with a guessed value — a wrong dial code or currency in a table other tables hold foreign keys to is worse than an absent country. Ten are currently excluded: `BV`, `GS`, `HM`, `PN`, `TF`, `UM` have no dial code; `AQ`, `CW`, `SX`, `ZW` have no current ISO currency in the bundled `iso-codes` edition, which predates `XCG` (Caribbean guilder, 2025) and `ZWG` (Zimbabwe Gold, 2024).

**Consequence to watch:** a company cannot be registered in an excluded country. `CW`, `SX` and `ZW` are inhabited and will need an amendment — either a `pycountry` bump that carries the new codes, or curated rows with their real ISO numeric codes. Not guessed here.

### `tenant` is inside the session filter, and unfilterable statements raise
**Added 2026-09-03**, on writing the `tenant` table (revision `0007`).

**`tenant` is filtered, not exempt.** It has no `tenant_id` — its `id` *is* one — so the `TenantMixin` form cannot apply. The alternative was to put it on the exemption whitelist and rely on route-level object checks. Rejected: rule 4.9 and CLAUDE.md §5.3 make isolation session-level precisely so that no route can forget it, and leaving *the table that defines the boundary* to per-route discipline inverts that. A second mixin, `SelfTenant`, filters it on `id` from the same ambient tenant. Cost accepted: provisioning a tenant and any platform-admin listing must run under `unfiltered()`.

**An unreachable statement raises rather than running.** `with_loader_criteria` attaches to the ORM entities in a statement's columns clause. `select(func.count()).select_from(Invoice)` has none, so the criteria was dropped without complaint and the count crossed every tenant. Found by a test written for `tenant` that expected `1` and got `2`. The library now refuses that shape with a message naming the fix (`select(func.count(Invoice.id))`); joins and `EXISTS` subqueries are reached and unaffected.

**The general rule this settles:** a session-level filter that *silently* does not apply is worse than no filter, because it reads as protection. Where the mechanism cannot prove it applied — including a statement shape the library cannot inspect — it denies.

### Feature flags and tax systems are code catalogues in `libs/platform`, validated at import
**Added 2026-09-03**, on writing `company` and `company_feature` (revisions `0008`–`0010`).

**Catalogues, not tables.** `FEATURES` and `TAX_SYSTEMS` are fixed dicts in `libs/platform`, the same tier as the permission catalogue (invariant 13). A `feature` table would let a tenant invent a flag no code implements — which then reads as "not enabled yet" forever — and a `tax_system` table would let one name a regime no posting path can honour. Both are claims that code exists to honour them, so both are code.

**Validated at import time.** `features._validate_catalogue()` runs on module load and raises for an unknown dependency, an unknown tax system, a dependency cycle, a dependency gated more narrowly than its dependent, and two features sharing a `locks_on` event. A malformed entry fails the boot, not the first request that touches it — every one of those failures is otherwise silent until a specific enable is attempted.

**The mechanism/policy line.** The library holds the *graph*: dependencies, tax gates, which event locks which flag. Anything that reads a `company_feature` row — its `locked_at`, its actor, its audit event — is `identity`'s `domain/`. Same split as CLAUDE.md §3.

### Domain immutability takes no actor, and the module is the proof
**Added 2026-09-03**, alongside the above.

Ten `company` columns freeze once `first_posted_at` is set, and a feature locks permanently once its `locks_on` event fires. Both are invariant 16, and both are enforced by modules that have **no actor parameter at all** — not "check that the actor is not permitted", but nothing to check an actor against. Tested by asserting the signatures, which is the only way to prove "no role lifts it, including platform admin" without enumerating every role. The status is part of the message: 422, never 403, because 403 invites someone to go looking for an actor for whom it is allowed.

**Enforced on the diff, not the payload.** `changed_fields(current, incoming)` compares values, so a client PUTting an unchanged company back is not editing anything. Rejecting on payload presence would make every full update impossible after the first posting, and clients would work around it with partial payloads — which is how a field ends up cleared by accident. Field policy uses the same rule ([field-permissions.md](field-permissions.md) §6).

### Date-effective resolution helpers take rows, never a `company_id`
**Added 2026-09-03**, on writing `company_tax_registration`, `company_statutory_id` and `company_licence` (revisions `0011`–`0013`).

`resolve_tax_registration`, `resolve_licence`, `assert_no_overlap` and `assert_company_can_issue` all take the **rows** and return or refuse. The sketches in [company.md](company.md) §4.2 and §4.4 took a `company_id`, which cannot work: the caller is `billing`, inside a money transaction, and a helper that accepted an id would have to query for itself. From inside `libs/platform` that is either a second data path with no tenant scope of its own or a synchronous cross-service call in a posting transaction — invariant 7 and CLAUDE.md §5.3 respectively. Taking rows keeps the library **mechanism** (the date arithmetic, which every service must agree on) and leaves loading them to the service that owns its own replica.

Asserted structurally, the same way domain immutability is: no rule in `identity/domain/` accepts `session`, `db`, `connection` or `engine`, and the tests check the signatures rather than trusting the import list.

### The licence gate fails closed
**Added 2026-09-03**, alongside the above.

`assert_company_can_issue` refuses a `line_gates` entry that **no licence kind in the jurisdiction declares**. The tempting reading is that an unknown gate is not this jurisdiction's concern and should pass; that makes the UK profile — which declares no licences at all — able to post every gated line freely, and a scheduled drug sold with no licence is not a configuration gap, it is the outcome the gate exists to prevent. Every gate on the document is checked, not only the first.

**`document_kind` was dropped from the signature.** The gate is decided entirely by the gates the lines carry, so a document kind was a second input that could only ever agree redundantly or disagree — and disagreeing permissively is the same failure. Its write-side counterpart is that a licence the profile marks `has_expiry` must carry `valid_to`: left open-ended it satisfies every gate forever.

### `company_statutory_id.value_last4` is NOT NULL for every kind
**Added 2026-09-03**, alongside the above. Corrects [identity-schema.md](identity-schema.md) §3.7, which had it nullable and populated only for restricted kinds.

It is the last column of `uq_company_statutory_id_company_id_kind_value_last4`, and MySQL treats NULLs inside a unique key as **distinct**. Left NULL for unrestricted kinds, a company could store the same PAN twice and the key would enforce nothing for exactly the identifiers that print on invoices. The key is on `value_last4` rather than `value` for the mirror-image reason: for a restricted kind `value` is NULL, so keying on it would let the same AADHAAR be added repeatedly with no way to notice. The accepted cost is narrow — two *different* values of one kind that happen to end the same four characters are falsely rejected.

### Notification sends are event-driven; provider callbacks terminate in `notification`

**Chosen:** producers request Email, SMS, WhatsApp and Push delivery by publishing through their transactional outbox. `notification` consumes those requests and never exposes a public or synchronous "send now" API.

Delivery providers still need to report acceptance, delivery, failure, bounce and read state. Those callbacks terminate at provider-specific endpoints owned by `notification`, behind nginx rate limits. Each adapter verifies the signature over the raw request body, enforces the provider timestamp/replay window where available, and commits the encrypted callback to the deduplicated `provider_event` inbox before returning success. An asynchronous normalizer then writes `delivery_event`, advances the current `notification_delivery` projection without state regression, and emits audit/outbox rows in its own transaction. This short durable-inbox path keeps provider retries from becoming a load amplifier.

Rejected alternatives:

- **No callback ingress:** leaves accepted messages permanently indistinguishable from delivered, bounced or read messages, and makes suppression unreliable.
- **A generic callback endpoint:** encourages weak lowest-common-denominator verification. Each provider has its own signature scheme and parser.
- **Callbacks handled by producer services:** couples billing and identity to notification vendors and duplicates receipt logic.

The complete table and retention design is [notification.md](notification.md).

### `audit` as a service — yes; telemetry and logs — no
**Chosen** after these three were initially proposed together as one service.

`audit` earns a service: it is a compliance artifact, not an ops artifact. Multi-year statutory retention, tenant-facing queries, separate access control, append-only with tamper-evidence, and the largest table in the system. Loki is the wrong home — it is ops log storage with a retention window, not a queryable compliance store.

Telemetry and logs do not, for the reasons in § *What deliberately does not get its own service*: a logging path must not have a runtime dependency, and the alternative is reimplementing Prometheus and Tempo in Python.

The distinguishing question, when this comes up again for something else: **is it read by tenants as product data, or by engineers as operational data?** Product data gets a service. Operational data gets infrastructure. Tenant-facing API history, webhook deliveries, and integration errors are product data, which is why they sit in `audit` (see [audit.md](audit.md) §1) rather than in Loki.

### Datastore reversed: MySQL 9.6, not MariaDB 11.4
**Reversed 2026-09-11.** The original decision (above) was MariaDB 11.4 over MySQL 8.4.
The deployed and available engine is **MySQL 9.6**, so that is now the platform datastore.

Why the reversal is cheap: the schema and the numbered rules were already engine-neutral
in every respect the design depends on — `DECIMAL(19,4)` truncation, NULL-in-UNIQUE
distinctness (the `SCOPE_ALL` sentinel design), `utf8mb4_unicode_ci`,
`ROW_FORMAT=DYNAMIC`, `ENGINE=InnoDB`, `SELECT … FOR UPDATE`, session-level tenant
filtering (no engine has usable RLS here). The full `identity` 34-revision chain was
verified to apply and reverse on MySQL 9.6.

Three engine differences now recorded rather than assumed:
1. **DDL atomicity** — MySQL DDL is atomic per statement but not transactional across
   statements, so rule 4.8 (one DDL per revision) still stands, for the same reason.
2. **JSON** — native binary type (not a `LONGTEXT` alias); path filtering still needs a
   generated column, so rule 4.7 stands.
3. **Strict mode** — `STRICT_TRANS_TABLES` is on by default, so an over-long value
   *raises* instead of truncating silently. A safety improvement; the "never truncate
   reference data" guard is kept regardless.

One cosmetic note: integer *display widths* (`TINYINT(1)`, `SMALLINT(n)`) are deprecated
in MySQL 8.0.19+; existing columns keep working and emit a deprecation warning only. Not
worth a schema-churning migration to strip.

Remaining sweep (mechanical, tracked): the testcontainers image and the DB-marker name
across every service's `conftest`, and prose "MariaDB" references in per-revision
docstrings and the other service docs, are updated engine-by-engine as each service is
touched. `identity` is done; `notification` and `libs/platform` test fixtures follow.

---

### Catalog and inventory design proposal

**Proposed 2026-09-11.** The user expanded Catalog planning to goods/services, units,
tracking, opening stock, replenishment and richer pricing/tax. The detailed
[product design](catalog-product-design.md) keeps definitions in Catalog and stock/financial
effects in Billing, with the required cross-service work explicit. Adoption and schema
contracts are recorded in [Catalog schema](catalog-schema.md); the agreed service count
and datastore remain unchanged.

**Consolidated 2026-09-11.** Recommended Billing ownership for company-scoped commercial
parties and native customer pricing types. Minimal source APIs now precede Catalog pricing;
shared jobs precede bulk workflows. Identity users/access roles remain separate from customer
pricing classification. This is proposed implementation ownership, not a completed service.

**Promotions extension 2026-09-11.** Added schemes, coupons and discounts through P0–P5.
Catalog authors finite native definitions; Billing owns one evaluator and all live usage.
The minimum actual sales/credit posting path is now included for redemption and returns;
full order/payment automation remains separate. Shared libraries retain mechanisms only.

## 6. Open items

- [ ] Recurring document scheduling/subscriptions — separate future scope; do not add a service or a scheduler implicitly to the voucher core.
- [ ] Payment gateway/banking selection — drives optional Vouchers adapters and callback certification, not a Payments service.
- [ ] Additional jurisdictions beyond the selected India GST scope and supported document profiles.
- [ ] Finalize the Vouchers/Accounting command contract, stock valuation/recognition policy and included job-work/manufacturing delivery details in [V0](vouchers-plan.md#5-delivery-phases-and-acceptance-gates).
- [ ] Finalize [voucher type/header/item customization](voucher-extensibility.md) contracts and [India tax](voucher-tax-recording.md) date/registration compatibility, statutory integrations and first VAT state/commodity coverage.
- [ ] Managed vs self-hosted MySQL and RabbitMQ
- [x] Planning catalogue and financial/operational consistency requirements recorded in [posting/reporting design](voucher-posting-reporting-design.md); implementation, selected statutory formats and D11 contracts remain open

### 2026-09-11 Catalog foundation implementation decisions

- billing-platform 0.5.0 adds opt-in guarded sessions, same-company object access, atomic
  insert claims, detached scoped service signatures, confirmed broker transport and shared
  custom-field validation/layout/query mechanisms. Catalog opts into guarded sessions;
  existing services retain their established factory defaults and regression coverage.
- Shared language data is explicitly registered/materialized by Catalog. It does not silently
  add an unmigrated language table to Identity's metadata or revision chain.
  Amendment (2026-10-20): Identity explicitly materializes that shared language
  shape in `0072`, plus its IANA timezone projection in `0073`, for regional
  selectors requested by the user. Identity seeds timezone rows from the shared
  pinned tzdata dependency; global reference data remains local to writes.
- Optional aio-pika transport supports persistent messages, confirms and commit-before-ACK;
  mock transport tests do not constitute a verified RabbitMQ deployment.
- Pinned tzdata 2026.3 supplies IANA ZoneInfo data on Windows for promotion-definition timezone
  validation ([official package](https://pypi.org/project/tzdata/)). All consuming lockfiles are
  synchronized. This does not select a company's timezone or a supported tax jurisdiction.


### 2026-09-12 Identity gap implementation decisions

- User selected private Azure Blob documents. Identity uses managed/environment identity,
  create-only upload SAS, checksum validation and immutable snapshot downloads.
- Shared billing-platform 0.17.0 provides tested signed actor/broker mechanisms, bounded
  per-process rate limiting, AES-GCM and request-scoped real/effective audit attribution.
  All consuming Python lockfiles are synchronized.
- The separate Identity posting client supplies Billing's reservation/terminal HTTP
  adapter. Actual Billing posting remains an external integration gate; no new service
  or money-transaction owner is introduced. See [Identity operations](identity-gap-operations.md).

### Accounting finance ownership - 2026-09-15

The approved [Accounting finance contract](accounting-finance-contract.md) supersedes
older Billing ownership statements for ledger/fiscal controls and commercial party
accounting. The existing Accounting service owns journals, periods, entered openings,
open items, settlement allocations, credit controls and overdue charges. Identity owns
company configuration and first-posting reservations. Billing and Payments remain
future source consumers; this increment creates neither service and defers their UI.

### Tax ownership widened to Accounting - 2026-10-05

Tax is no longer an invoice-only concern. `catalog` keeps product tax definitions
(HSN/SAC classification, rules, dated rates and bindings). `accounting` owns tax accounts
and profiles (already implemented), account-level tax defaults for non-product vouchers,
TDS/TCS withholding masters, and tax on journals, expenses and payments. The calculation
(place of supply, component amounts, rounding, regime refusal) is shared mechanism in
`libs/platform`, so Billing and Accounting compute identically. Accounting reads Catalog
rules from a replica fed by outbox events — never a synchronous call inside a posting.
Reverse-charge *applicability* is a dated fact on the Catalog rule and on the Accounting
account default; the posting service decides RCM per document. Plan:
[tax-accounting-plan](tax-accounting-plan.md).

### Vouchers replaces planned Billing and Payments APIs - 2026-10-10

The user selected one Vouchers API for transaction documents and explicitly excluded payroll
and related work. The target seven services now include Accounting and Vouchers instead of
Billing and Payments. The [new plan](vouchers-plan.md) enumerates 22 base kinds, with a proposed
18-kind core and four later job-work kinds; manufacturing is a Stock Journal mode. The user's
subsequent confirmation makes job work included scope, superseding the initial optional split.
The user also required orders, quotations and challans. Quotation derives from the non-posting
Sales Order profile; Delivery Challan uses the Delivery Note movement workflow. Orders and
quotations never alter actual stock/account balances, and printing a challan never moves stock.
Accounting remains the ledger/fiscal/party authority. Co-locating stock/value posting there
is the proposed consistency boundary, to finalize in V0. Vouchers owns document workflows
and provider adapters; no cross-database atomicity is assumed. Historical Billing/Payments
references below or in older plans do not authorize creating those services. Existing package,
event and service identifiers require explicit compatibility work and are not renamed here.

### Voucher extensibility, job work and India tax recording - 2026-10-10

The user required additional company-created types, typed voucher/item attributes, job works
and proper GST/VAT recording, then confirmed India as the jurisdiction. Added the
[extensibility contract](voucher-extensibility.md) and [tax recording plan](voucher-tax-recording.md).
Identity remains the field-definition/policy authority; Vouchers owns header/line values and
type bindings; Catalog owns item masters; Accounting owns tax/ledger effects. Job work is
included later scope. India GST is first; VAT needs verified state-specific profiles. Statutory
tax dates must be separated from GL posting periods through versioned compatibility work.
Existing GST calculation and custom-field code are reused without claiming the planned
Vouchers, compliance or India VAT functionality is already implemented. Payroll stays excluded.

### Shared base tables across voucher kinds - 2026-10-10

The user selected common voucher base tables with type-dependent details, including complex
invoices combining account/item lines, charges, tax entry, advances and payment references.
The [data model](voucher-data-model.md) uses a common header/revision/line core with reusable
typed components and section rules. It does not create separate Sales/Purchase/Payment/Job-work
document table families. Type configuration stays data; domain validation remains code, and
Accounting keeps authoritative journal/stock/tax/settlement effects in its own database.
The subsequent requested table inventory lists shared and conditional structures by owner;
optional gateway/import/scheduling tables are candidates, not newly committed release scope.

### Journal, Stock Journal and bank functionality review - 2026-10-10

At the user's request, reviewed official TallyPrime behavior for accounting journals, stock
journals and bank vouchers. Corrected the blanket non-cash Journal description and recorded
bank allocations, cost-centre/project analysis, transfer/manufacturing/loss profiles and
instrument/reconciliation workflows. The [review](tally-voucher-functional-review.md) separates
verified product behavior from platform choices and lists further shared schema candidates.
These require V0 ownership/contracts and selected phase scope; the prior table count remains
a baseline. Common voucher tables, Accounting effect authority and payroll exclusion persist.

### Payment, Receipt and advance settlement review - 2026-10-10

The user's follow-up requested bill-adjustment and advance functionality. The
[review](tally-settlement-functional-review.md) separates money posting, bill-reference
allocation and statutory advance adjustment. Existing Accounting allocation/reversal commands
are reusable; bulk/multi-party atomicity, supported refund/difference profiles and tax mappings
remain contract work. No new base kinds, per-kind tables or mutable advance-balance authority
are introduced by this documentation update.

### Sales/Purchase calculation and posting - 2026-10-10

The user required inventory-linked and accounting-only invoices with proper charges, discounts,
tax and payment handling. The [invoice contract](voucher-invoice-calculation.md) keeps common
voucher tables and a single calculation pipeline, reusing Catalog policies and Accounting
effects. Discount components have one authority; payable, tax-base and cost distributions
are purpose-tagged. Item display does not imply stock execution, and recognized settlement is
separate from later bank clearance. V0/V3/V4 contract and acceptance gates remain before release.

### Indent, order, quotation and challan review - 2026-10-10

The user requested TallyPrime's procurement/order/movement functionality. The
[review](tally-order-fulfillment-review.md) distinguishes its optional manufacturing
requisition from our required general non-posting indent workflow. Plain requisitions join
V5; BOM assistance remains V8. Shared fulfillment schedules and bounded source allocations
support partial/consolidated conversion and separate delivery/billing/closure progress.
The 22-kind catalogue and common voucher tables remain; the schedule candidate is outside
the prior 51-table baseline until V0 normalization. No application implementation is claimed.

### Consolidated voucher implementation roadmap - 2026-10-10

The user requested implementation detail after the Tally-based research. The
[roadmap](voucher-implementation-plan.md) defines owner-scoped schema/API/worker/client
packages, command/result and failure contracts, policy decision gates, 28 acceptance cases
and staged activation/recovery. It retains V0-V9 and starts Reports/statutory work alongside
dependent transactions; optional V7 does not block required V8. No new service boundary,
stack, local path, application code or deployment is changed by this planning revision.

### Voucher batch-readiness review - 2026-10-10

The user requested a plan review before implementation in batches/phases. The
[delivery tracker](voucher-delivery-tracker.md) records eight corrected planning findings,
45 batches over the existing 38 work packages, all 22 kinds and activation/evidence gates.
Foundation item/type data precedes customization; allocation/instrument support precedes
complete settlements; stock-period and costing support precede executable stock; Reports
arrives incrementally. Stock-only effects retain first-use/period protection without a dummy
journal. Open business decisions remain explicit; no application implementation is claimed.

### Voucher financial-reporting review - 2026-10-10

The user requested explicit report readiness. The
[posting/reporting design](voucher-posting-reporting-design.md) adds ledgers, TB, P&L/Income
& Expense, Balance Sheet and incremental registers; source completeness, committed snapshot
barriers, native classification, opening/earnings and GL/subledger/stock/tax reconciliation.
D11 and RPT01-RPT20 make these contracts reviewable within the existing 45 parent batches.
B14a-d deliver core statements; later transaction phases extend their evidence. Period
locking alone is not report reproducibility, and annual-close automation remains deferred.

### Voucher stock reporting and balances review - 2026-10-10

The user required current product stock, item/group registers and expiring-stock reports.
The stock design defines canonical owner/custody/location/lot positions, quantity and value
histories, eligibility, lot-date/hold/reservation changes and residual receipt-age allocation.
Dated classification and compatible-unit rollups prevent false group totals. B27a-e and
INV01-INV24 fit the existing 45 parents/gates; later B32/B40 add demand and job-work facts.
Required inventory reports use one Accounting source and shared Reports runs. No stock
service, application implementation or unselected company policy is introduced.

### Financial-year planning decision - 2026-10-10

The required [company financial-year plan](voucher-financial-year-design.md) keeps one
company and continuous source history, with explicit posting/statutory dates and number
identities, next-year readiness, close evidence and controlled reopen/report invalidation.
D12/FY01-FY24 extend existing batches. Annual earnings transfers remain deferred; no annual
company split, balance import or second ledger is required for normal continuation.

### Account-recording review - 2026-10-10

The [account recording/maintenance design](voucher-account-recording-design.md) records
required native GL/source lineage, explicit register grains and derived balance definitions.
Reports maintains complete line facts and optional summaries through atomic checkpoints and
verified generation cutover. Owner balances remain authoritative for financial decisions.
BAL01-BAL20/RF33-RF40 extend existing gates and 45 batches; no architecture/service change.

### Stock capture/storage review - 2026-10-10

The [stock storage design](voucher-stock-recording-reporting-design.md#31-what-an-execution-captures)
now specifies exact execution data, normalized stock grains, immutable value history and
atomic guarded balances. Operational repair and Reports rebuilds are distinct. RF41-RF48
and STK01-STK20 extend existing gates/batches without adding a service or duplicate stock owner.


### 2026-10-10 - B09 financial owner export and Reports foundation

Accounting captures each committed root transaction into immutable scoped change/fact rows,
allocating its sequence under the same company fence used by frozen export materialization.
Reports stages signed pages, atomically applies complete verified bundles, catches up through
an explicit end barrier and switches a reconciled immutable generation. No cross-service SQL,
financial balance authority or new statement calculation is introduced. Native journal-line
and DAY/MONTH gross account projections use DECIMAL(19,4), with original currency/FX evidence.

Shared platform 0.29.0 generalizes requester-bound owner signing; reporting-contract 0.1.0 is
consumed by Accounting and Reports. Definition/run/output hashes and live input permissions
freeze diagnostic output without pretending fiscal locks alone freeze a report. Initial
coverage is retained owner ledger from books-begin, capped at 100,000 facts; missing YTD or
classification history is not synthesized. B14 and later producer batches extend the
capability. [B09 execution/evidence](voucher-b09-execution.md) records limits, tests, migration
heads and the separate known failure in parallel sequence work.

### 2026-10-13 - Voucher notification integration

Vouchers writes optional share/automatic send commands to its outbox; Accounting
publishes party-contact snapshots. Notification authenticates each broker source
against an explicit route, broker user and tenant/company grant and owns all delivery
evidence. Contact projection is monotonic by Accounting setup generation. Terminal
voucher state fences late commands. Provider dispatch is opt-in and unknown sends
remain in reconciliation rather than being retried blindly. The
[voucher notification execution record](voucher-notification-execution.md) lists
the separate attachment and live certification gates.


### 2026-10-21 ? managed reference catalogs

User-authorized CRUD extends the static-default decision for Country, State,
Language and Currency. The shared library still supplies committed ISO defaults;
Identity owns authenticated platform-operator additions and overrides. Per-service
`reference_revision` records preserve operator rows through seed reruns, including
archived rows. Codes, state parents/tax jurisdictions, currency financial/display
identifiers and ISO identifiers are permanent. Storage remains DECIMAL(19,4).

Identity writes immutable `reference_change` entries in the same transaction as
the materialization, provenance revision and audit outbox. This journal is the
reference-delivery outbox; there is no extra unpublished RabbitMQ event. UUIDv7
entries are committed under the installation lock, with a persisted monotonic
ordering guard for differing owner clocks. Scoped HMAC read/ack workers deliver
100 changes per page to Catalog and Accounting, commit native rows/version state
with their checkpoint, then acknowledge. Ack retries recover a crash after local
commit. Duplicate versions must match; out-of-order changes roll back.

Install canonical seeds in each consumer first, then replay the retained journal
from the beginning on bootstrap or rebuild. New custom selections wait for both
required acknowledgements. Existing configuration/history remains local and
readable; no synchronous financial-write calls are introduced. Other services
consume financial/company snapshots rather than these management tables.

The three UUID-keyed management tables are explicitly global tenant-filter
exceptions: they hold ISO configuration or scoped service checkpoints, never
tenant data. Operator identity and live configuration permissions gate every
public management route; fresh verified authentication gates writes. Delete
archives and checks active tenant/company/address/currency dependencies; it
never removes referenced historical rows.

Accepted costs: provenance tables in three databases, the Identity journal, two
independent worker credentials and service-local DML grants. No new service or
datastore. Extra languages provide reference choices, not UI translations; extra
countries do not enable tax profiles.

Decision 2026-10-21: reuse the existing Redis client for non-personal reference
dropdown projections. Identity owns a transactionally rotated global generation
(revision 0080); versioned database-specific keys expire with a bounded TTL.
READ COMMITTED loads recheck the generation before populating. Redis failure
falls back to DB reads; permissions and write-time/financial validations remain
live. No new datastore, service or dependencies. See [reference-cache.md](reference-cache.md).

Decision 2026-10-25: document layout is the eighth service, `design` (row 8 above,
[invoice-design.md](invoice-design.md)). The code existed in the tree without a doc,
decision entry, migration tree, permission keys or audit emission; this records the
boundary rather than inventing it. It owns `invoice_template`, its immutable layout
versions, routing rules, brand assets, reusable blocks and render snapshots in its own
`design` database, on port 8014 behind `/design/` with its own `/_design_authorize`
subrequest. It verifies the gateway-signed actor context only — Identity signs company
context for the accounting, vouchers and reports routes alone — and checks every route's
permission against the object's own company scope. It accepts no client-supplied compiled
HTML or CSS and no client-supplied asset storage path, and emits `design.*` audit events
through its own outbox; `audit` accepts `design` as an issuer. It renders nothing: the
renderer and object storage remain open questions (invoice-design.md §9). No new datastore
technology and no new dependency beyond the shared library.

### 2026-10-31 - Local authentication provider; `AUTH_PROVIDER` is `local` or `authentik`

Decision: credentials may be owned by Identity itself. `AUTH_PROVIDER=local` (the default) makes
Identity an OpenID Connect provider for the first-party clients — sign-up with manual review,
sign-in, refresh, password change and operator-issued recovery links — and `authentik` keeps every
Authentik flow unchanged. The setting is permanent, per installation, and read by Identity and the
Auth app. Details, tables and security controls: [local-auth](local-auth.md).

Why: the Authentik VM was a hard prerequisite for any sign-in, including local development and CI,
and an installation that does not want to run a second identity system and its PostgreSQL had no
option. This **supersedes, for `local` only,** the 2026-10-20 decision that Authentik owns
credentials ([account-registration](account-registration.md)); with `authentik` that decision is
unchanged.

What does not change: services still verify RS256 JWTs through `billing_platform.oidc` (the verifier
gained one rule — plain HTTP is accepted for loopback hosts only, so a development machine needs no
certificate); permissions still resolve server-side and never travel in the token; tenant isolation
is unchanged. The six `local_*` tables are installation-global because a sign-up exists before any
tenant does, and are whitelisted in `TENANT_FILTER_EXEMPT` with that reason.

Two choices differ from the plan that was agreed first. **No Authlib:** the provider is a narrow
profile — authorization code with PKCE (S256), confidential clients, refresh rotation, revocation —
so it is written directly on `joserfc`, which keeps the whole protocol readable in one review and
adds no dependency or framework glue. **One new dependency, `argon2-cffi`**, for argon2id password
hashing (OWASP's first choice; the stdlib offers only scrypt). Multi-factor authentication, social
login, SAML and email recovery (SMTP is still deferred) are out of scope; step-up means entering the
password again.

Rule 4.10 says CPU-bound work goes to Celery. **One deliberate exception:** argon2id password
hashing runs in a small bounded thread pool inside the request (`local_auth/offload.py`: 4 workers,
8 waiting, then 429, never more than half the database pool). It is on the sign-in path, where a broker round-trip would add latency and a
new way to fail for nothing, and argon2-cffi releases the GIL, so the pool is genuinely parallel;
what rule 4.10 protects — the event loop — is protected. It must never be run inline.

Open: `user.authentik_sub` keeps its name and holds the active provider's subject (a rename to
`idp_sub` is a separate migration); the provider is chosen per installation and credentials are not
migrated between providers. Existing *accounts* are the exception that matters: an installation that
already has people (the platform administrator above all) cannot sign in after the switch, so
`local_auth.cli adopt-users` re-points each named `user` row at a new local account and issues a link
to choose a password ([local-auth](local-auth.md) §9).


### 2026-10-31 ? Local sign-in accepts username or email

Local authentication accepts either the account username or email with its password. Both
resolve to one local identity, account throttle and credential lockout; the OIDC subject and
tenant linkage stay unchanged. The internal login payload uses `identifier`, with the previous
`email` field retained as a mutually exclusive compatibility alias. No public API, database
schema or Authentik flow changes. Contract: [local-auth](local-auth.md);
verification: [username login](local-auth-username-login.md).

### 2026-11-01 - Versioned company display projection cache

Identity reuses its existing Redis client for the authorized, per-user response of the
company display-config endpoint. Live authorization and field-policy resolution precede
every lookup. Keys include committed company/user row versions and the access fingerprint;
Redis failure falls back to the authoritative database resolver. No financial/configuration
write path consumes the entry, and no new datastore, service, migration or dependency is
introduced. Contract and operations: [company-display-cache](company-display-cache.md).
Conditional field policy is evaluated from live company columns before a cache read;
output denials remain enforced independently of Redis contents. Step-up continues to
read its live flag, and source reloads refresh any preloaded ORM identities.
