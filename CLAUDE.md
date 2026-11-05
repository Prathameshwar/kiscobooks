# CLAUDE.md

Guidance for Claude Code in this repository.

## Repository and publishing

- Keep project files at their existing local paths.
- The current GitHub repository is `Prathameshwar/kiscobooks`, branch `main`. Publish the repository root to `origin/main`.
- When committing, stage only the task's files. Preserve concurrent staged and unstaged work from other agents and the user.
- Before publishing, fetch `origin/main` and check for remote changes. Push committed changes with `git push origin main`; never force push or publish unfinished unrelated edits.

## 1. What this is

A multi-tenant billing platform: eight Python microservices behind nginx, with Next.js web and React Native mobile clients. **Money correctness, tenant isolation, and auditability outrank delivery speed on every trade-off.**

The target services are Identity, Audit, Catalog, Accounting, Vouchers, Reports,
Notification and Design. Design owns document layout — templates, immutable layout
versions, routing rules, brand assets and print evidence — and renders nothing; its
renderer and object storage are open questions
([invoice-design](docs/invoice-design.md)).
Vouchers replaces the previously planned Billing and Payments APIs;
Vouchers has a verified Phase 1 common foundation and Reports a verified B09 foundation.
Phase 2 verifies ordinary money execution and financial statements/registers; its
[execution record](docs/voucher-phase2-execution.md) records verification and precise
coverage. Money admission defaults to disabled and release activation remains separate.
Payroll and related HR work are excluded.
[The Vouchers plan](docs/vouchers-plan.md) governs the revised document catalogue and
proposed posting boundary; its phases do not authorize implementation by themselves.

The architecture is decided. Don't propose alternative stacks, add a service, or change a datastore without raising it first.

| Doc | Governs |
|---|---|
| [docs/tech-stack.md](docs/tech-stack.md) | Stack, service boundaries, numbered rules 4.1–4.12, decision log |
| [docs/invoice-design.md](docs/invoice-design.md) | `design` service: document templates, layout versions, resolution order, brand assets, print evidence, canvas input rules and open renderer/storage questions |
| [docs/invoice-designer-production-plan.md](docs/invoice-designer-production-plan.md) | Proposed plan to make the designer voucher-type aware (product/account/mixed tables, per-kind bindings), renderer parity via a shared capability manifest, assets, preview and phases P0-P7; agreed 2026-11-03 (D1-D3 decided); §8 Purchase production readiness R1-R6 and D5 (one language per template) agreed 2026-11-04 |
| [docs/vouchers-plan.md](docs/vouchers-plan.md) | Voucher kinds/types, replacement of Billing/Payments, proposed Accounting posting boundary and delivery phases; payroll excluded |
| [docs/voucher-implementation-plan.md](docs/voucher-implementation-plan.md) | Detailed V0-V9 work packages, owner/dependency contracts, schema/API/worker/client delivery, decision gates, acceptance and rollout evidence |
| [docs/voucher-delivery-tracker.md](docs/voucher-delivery-tracker.md) | Reviewed batch order and prerequisites, decision/status/evidence ledger, all-kind coverage and separate activation checkpoints |
| [docs/voucher-batch-note.md](docs/voucher-batch-note.md) | Saved 45-batch scope/deliverables in eight delivery groups; 41 baseline, one conditional and three optional batches |
| [docs/voucher-phase5-execution.md](docs/voucher-phase5-execution.md) | Detailed B28-B36 implementation gates, owner boundaries and Phase 5 evidence |
| [docs/voucher-phase6-execution.md](docs/voucher-phase6-execution.md) | Detailed B37-B41 job-work/manufacturing gates, selected baseline and Phase 6 evidence |
| [docs/voucher-phase7-execution.md](docs/voucher-phase7-execution.md) | Selected B42-B44 banking/provider integration contract and independent activation evidence |
| [docs/voucher-phase8-execution.md](docs/voucher-phase8-execution.md) | B45 final native evidence, two-year rehearsal, recovery and staged C4 activation contract |
| [docs/voucher-implementation-todo.md](docs/voucher-implementation-todo.md) | Live batch and activation checklist; maintain alongside the delivery tracker's authoritative status/evidence record |
| [docs/voucher-account-recording-design.md](docs/voucher-account-recording-design.md) | Account source facts, register/ledger grains, balance definitions, daily/period summaries, atomic projection maintenance, rebuilds and BAL01-BAL20 |
| [docs/voucher-posting-reporting-design.md](docs/voucher-posting-reporting-design.md) | Required ledgers/TB/P&L/Income & Expense/Balance Sheet and registers; posting lineage, source snapshots, opening/earnings bridges, reconciliation and reporting acceptance checks |
| [docs/voucher-stock-recording-reporting-design.md](docs/voucher-stock-recording-reporting-design.md) | Stock capture/storage grains, guarded positions, immutable quantity/value/cost histories, repair/import contracts, item/group/expiry registers, B27a-e, INV01-INV24 and STK01-STK20 |
| [docs/voucher-data-model.md](docs/voucher-data-model.md) | Shared voucher header/revision/line and reusable detail tables; type-specific section requirements; no per-kind document tables |
| [docs/voucher-invoice-calculation.md](docs/voucher-invoice-calculation.md) | Common invoice modes and stacked quantity/line/invoice components, tax/payable/cost separation, source-linked returns, sales deals and CAL01-CAL28 |
| [docs/voucher-commercial-configuration.md](docs/voucher-commercial-configuration.md) | Tally-informed Sales/Purchase/type/class controls, native policy enforcement, manual/free/10+1 distinctions and scheme fulfillment/return rules |
| [docs/voucher-sales-configuration-plan.md](docs/voucher-sales-configuration-plan.md) | Current TallyPrime Sales configuration findings mapped to platform gaps, typed policy/API plan, delivery slices and acceptance gates; UI deferred |
| [docs/voucher-remaining-configuration-plan.md](docs/voucher-remaining-configuration-plan.md) | Detailed typed settings, applicability, owner boundaries and delivery slices for the other 21 voucher kinds and their order/quote/indent/challan/bank/job profiles; UI deferred |
| [docs/voucher-manufacturing-job-work-plan.md](docs/voucher-manufacturing-job-work-plan.md) | Focused BOM, manufacturing, output-cost, custody, job-work configuration and B37-B41 backend implementation contract; UI/payroll excluded |
| [docs/voucher-configuration-design.md](docs/voucher-configuration-design.md) | All-kind native settings registry, 22-kind configuration/capture/effect matrix, shared policy storage, effective-settings APIs, publication/entry enforcement and VCF01-VCF24 |
| [docs/voucher-import-plan.md](docs/voucher-import-plan.md) | Bulk import of Purchase, Sales, Credit/Debit Note, Payment, Receipt, Contra and Journal drafts: per-kind templates and duplicate/entitlement checks, staged dry-run validation, reviewed commit, result report |
| [docs/voucher-table-inventory.md](docs/voucher-table-inventory.md) | Candidate entry/support tables by owner, optional capabilities, existing Accounting and infrastructure reuse |
| [docs/voucher-extensibility.md](docs/voucher-extensibility.md) | Planned runtime voucher types and typed header/item-line custom fields reusing Identity/Catalog mechanisms |
| [docs/voucher-tax-recording.md](docs/voucher-tax-recording.md) | Planned India GST/state-VAT recording, statutory dates/documents, ITC/RCM, job work and return evidence |
| [docs/org-model.md](docs/org-model.md) | Tenant / company / department / user / role model, field lists |
| [docs/company.md](docs/company.md) | Company fields, tax system/regime, statutory IDs, licences, visibility |
| [docs/company-features.md](docs/company-features.md) | Per-company capability flags, dependencies, irreversibility ratchet |
| [docs/voucher-financial-year-design.md](docs/voucher-financial-year-design.md) | Required company-year readiness, effect dates and numbering, cross-year balances/bills/stock, close/reopen contracts, D12 and FY01-FY24 |
| [docs/fiscal-year.md](docs/fiscal-year.md) | Fiscal periods, close/lock lifecycle, posting rules, numbering |
| [docs/audit.md](docs/audit.md) | Audit trail, event shape, immutability, retention |
| [docs/identity-schema.md](docs/identity-schema.md) | `identity` tables and fields — types, keys, per-field purpose, column mixins |
| [docs/identity-db-plan.md](docs/identity-db-plan.md) | `identity` migration order — 34 revisions, DB conventions, per-phase exit tests |
| [docs/custom-fields.md](docs/custom-fields.md) | Runtime-configurable fields — types, validation, conditions, search |
| [docs/field-permissions.md](docs/field-permissions.md) | Field-level allow/deny on top of role permissions |
| [docs/roles-permissions.md](docs/roles-permissions.md) | Permission catalogue, preloaded system roles, separation of duties |
| [docs/notification.md](docs/notification.md) | Notification transport, Email / SMS / WhatsApp / Push delivery tables, receipts, consent, suppression |
| [docs/api-conventions.md](docs/api-conventions.md) | Standard CRUD and list contract: cursor paging, filtering, search, sorting, lean projections, query performance |
| [docs/design-system.md](docs/design-system.md) | `@janso/ui` — design tokens, the three themes, component catalogue, layout, display formatting |

**Docs win over code.** Code contradicting a doc is the thing that's wrong. If a doc is wrong, fix it and its decision log in the same change.

**Don't silently answer an open question.** Each doc ends with unresolved items. If a task depends on one, ask.

---

## 2. How to work

**Phase plans.** Anything crossing more than one service, one migration, or ~100 lines: write the phases first and get them agreed. Each phase ends with tests green and the repo working — never a migration without its matching model. Report progress per phase, not per file.

**Review after the last phase.** Walk §5 and §6, run `/simplify`, and run `/security-review` for anything touching auth, permissions, tenant scoping, money movement, or audit. Report findings including "nothing." Don't skip it for mechanical-looking changes — that's where these invariants actually break.

**Keep these in sync.** A change on the left isn't done until the right is done, in the same change.

| Changed | Also update |
|---|---|
| SQLAlchemy model | Migration, Pydantic schema, test factory, regenerated TS client |
| Route or response model | OpenAPI → `clients/api-client` → its consumers in web and mobile |
| Event payload | Every consumer, replica tables, version handling |
| Permission key | Code catalogue, system roles, seeds — [roles-permissions](docs/roles-permissions.md) §2, §6 |
| Shared library | Version bump, every consuming service's lockfile |
| A documented decision | The doc **and** its decision log |

**Migrations.** Never change a model without a migration, or accept a generated migration without reading it line by line — `alembic --autogenerate` misses generated columns, index renames, `VARCHAR` length, partitioning, and collation on MySQL. **One DDL statement per revision** (rule 4.8): MySQL DDL is atomic per statement but not transactional across statements, so a multi-statement failure desyncs the schema from Alembic's version table. Every migration needs a working `downgrade` or a comment saying why not. Seed data lives in `seeds/`, never in migrations.

---

## 3. Shared library

`libs/platform` holds **mechanism**; services hold **domain and policy**. That line is what stops this becoming a distributed monolith.

**In:** SQLAlchemy base/session including the tenant filter · `assert_postable()` and the `fiscal_period` replica · audit emission · outbox writer and poller · JWT validation and permission resolution · RabbitMQ publisher/consumer with `message_id` dedupe · provider-webhook verification and replay-protection primitives · money and `Decimal` helpers · ISO country/currency/language data · OTel and logging setup · error envelope · versioned signed cursor codec, page envelope and safe list-query primitives · base config · test helpers.

**Out:** domain logic belonging to one service · another service's ORM models · anything that would make two services deploy together.

**Write the same non-trivial thing twice and stop — move it here.** Two copies of tenant filtering is how they drift apart.

---

## 4. Layout and conventions

```
apis/{identity,audit,catalog,accounting,vouchers,reports,notification,design}/
  src/<name>/{api,domain,models,schemas,events,tasks}/   tests/
dbs/<service>/                      alembic.ini, env.py, versions/ — one tree per service
libs/platform/                      shared Python library
mfes/                               web micro-frontends
start/win/                          local run scripts
docs/   seeds/
```

`api/` routes stay thin — validate, call domain, return. `domain/` holds business rules and imports no framework.

**Migrations live in `dbs/<service>/`, models live in `apis/<service>/src/<name>/models/`.** Each service migrates independently — never one shared revision chain, which would couple services' migration history and invite the cross-service foreign keys the architecture forbids. `dbs/<service>/env.py` imports that service's models for autogenerate; keep the path wiring in `env.py` only.

- Python 3.12, `uv`, Ruff, **mypy strict** — no new `type: ignore` without a reason comment
- Table names **singular**, snake_case. IDs are **UUIDv7 as `BINARY(16)`** — except the four ISO reference tables (`country`, `state`, `currency`, `language`), which use their natural code as PK and carry no `tenant_id` ([tech-stack](docs/tech-stack.md) § *Reference tables*)
- Timestamps UTC, suffixed `_at`. Business dates suffixed `_date`, never datetimes
- Enums are `VARCHAR` + app validation, never MySQL `ENUM` (altering one rebuilds the table)
- Money is `DECIMAL(19,4)` with a sibling currency column. Never `FLOAT`
- **Quantities are `DECIMAL(19,4)` too.** Four decimals is the fixed *storage* scale for every amount and quantity column in every service and replica — never narrowed per column, since MySQL narrows to a smaller scale without erroring
- **Amount and date display formats come from config, never from client locale defaults.** `company.amount_precision` / `quantity_precision` / `rounding_mode` / `date_format` are display and rounding scale only; one shared formatter per platform reads the resolved display config ([company](docs/company.md) §4.5)
- `async def` by default; CPU-bound work goes to Celery, never inline (rule 4.10)

**CRUD and lists.** Every resource follows [api-conventions.md](docs/api-conventions.md). Growing lists use signed keyset cursors (`limit` default 50, maximum 200), typed allowlisted filters, resource-specific indexed search, allowlisted stable sorting with `id` as tie-breaker, and a dedicated lean `ListItem` schema. Never return the detail model, arbitrary client-selected fields, unused JSON/BLOB/TEXT columns, an unconditional exact count, or an unbounded/deep-offset query. Fields denied for read are also forbidden in filters, search and sorting.

**Web and micro-frontends (`mfes/`).** One pnpm workspace: shared design system and reusable components in `mfes/packages/ui` (`@janso/ui`); each MFE in `mfes/apps/<name>`.
- **CSS is centralized, never duplicated per app.** Design tokens and component styles live in `packages/ui/src/styles/` — `tokens.css` is the single source of truth for palette, type scale, spacing, radius and gradients; everything visual keys off those CSS custom properties. Style through tokens and shared classes, never ad-hoc per-component stylesheets or hardcoded colours/sizes inline.
- **Reusable components live in `@janso/ui`, not inside an app.** Framework primitives (`Button`, `TextField`, …) and the brand lockup/logomark are shared. An MFE holds only its own layout and screens; the moment a second MFE needs a piece, it moves to `@janso/ui` — the same mechanism-vs-policy line as `libs/platform`.
- **Every shared component and every page ships unit tests** (Vitest + React Testing Library), same as the backend (§7): rendering, each conditional branch, form validation/success/failure/pending states, and accessibility (labels, roles, focus). No UI ships without them.
- Logomarks are self-contained SVGs that carry their own colour, with `useId()`-namespaced gradient ids so two instances on one page never cross-paint.

---

## 5. Security — non-negotiable

Assume every implementation is hostile-facing. These are not situational.

**Authorization**

1. **Deny by default.** Every route declares a required permission. A route without one must be explicitly marked public, with a comment saying why.
2. **Endpoint permission is not enough — check object-level scope.** A user holding `company:A` must not reach `company:B`'s invoice even with the right permission key. Resolve the actor's scope against the object being touched, every time. This is the most likely real vulnerability in this system.
3. **Tenant filtering is session-level**, in the shared library — never per-query discipline. One forgotten `WHERE` is a cross-tenant breach. (rule 4.9)
4. JWT carries `tenant_id`, `user_id`, `user_type` — **never the permission set**. Permissions resolve server-side from cache so revocation takes effect on the cache TTL, not the token TTL.
5. Impersonation is time-bound and audited at start and end.

**Input and output**

6. Pydantic models use `extra="forbid"`. Never construct an ORM object from unvalidated request data — no mass assignment.
7. Raw SQL is parameterized, always. Never format values into SQL. This matters most in `reports`, which will legitimately use raw aggregates.
8. Error responses return the error envelope only — no stack traces, no SQL, no internal identifiers.

**Secrets and sensitive data**

9. No secrets in the repo, in code, or in test fixtures. Environment or secret manager only.
10. **Never store raw card data or full national identity numbers.** Tokenize cards at the gateway; future Vouchers payment adapters keep only the gateway token and last four digits. AADHAAR/SSN-class identifiers follow the same rule — last four plus a verification reference, never the full value ([company](docs/company.md) §4.3). Business identifiers (PAN, TAN, CIN, EIN, GSTIN) are stored in full.
11. Redact from logs: tokens, card numbers, bank accounts, passwords, full tax IDs. Audit rows store references, never PII (§6.9).

**External surface**

12. **Verify the signature on every inbound gateway or notification-provider webhook**, using the raw body and a timestamp window to reject replays. An unverified webhook is an unauthenticated state change. Notification callbacks are the service's only unauthenticated HTTP ingress; they are not a general send API ([notification](docs/notification.md) §2).
13. Rate limit auth and money-mutating endpoints, at nginx and in-app.
14. Report and invoice downloads use signed, expiring URLs. No public object storage.
15. Pin dependency versions. No new dependency without a stated reason.

---

## 6. Correctness invariants

Walk these before declaring done. References are to the docs.

1. Money is `Decimal` end to end, with currency alongside. Never float. (4.1)
2. Every money-mutating endpoint takes an idempotency key, and a replay produces one effect. (4.3)
3. Every financial write calls `assert_postable(company_id, posting_date, actor)`. ([fiscal-year](docs/fiscal-year.md) §4.2)
4. `posting_date` determines the period — never `created_at` or `document_date`. (§4.1)
5. Posted documents in closed periods are never edited. Corrections are reversing entries in an open period. (§4.4)
6. Invoice numbers are allocated on posting only, never to drafts, keyed `(company, series, fiscal_year)`. (§7)
7. No synchronous cross-service call inside a money transaction — replicate locally. (tech-stack § *Reference data ownership*)
8. Every state change emits an audit event **in the same transaction**, via the outbox. ([audit](docs/audit.md) §2.1)
9. Audit rows hold `actor_user_id`, never denormalized PII. (audit §5.2)
10. Publishing goes through the outbox, never directly after commit. Consumers dedupe on `message_id`. (4.4)
11. One lifecycle mechanism per entity — `status` **or** `is_active` **or** `valid_from`/`valid_to`. Anything affecting a computed amount uses dates, not a boolean. (4.12)
12. Never hard-delete a row referenced by a posted document. Anonymize users; never delete them.
13. Permissions are code (a fixed catalogue); roles are data. ([org-model](docs/org-model.md) §5.3)
14. **Domain logic never reads a custom field.** Store, validate, display, report — never price, tax, post, or route approvals from one. If it drives money, promote it to a real column with a migration. ([custom-fields](docs/custom-fields.md) §11)
15. Field-level denies are enforced **server-side on the changed-field set**, never by the UI alone, and read-denies must hold in exports and reports too. ([field-permissions](docs/field-permissions.md) §6) **Tenant field config is layout, not authorization** — a hidden field is still accepted by the API and still present in exports; blocking a field is `field_policy`'s job. Clients render forms from the `field-set` endpoint and never hardcode a field list. ([identity-schema](docs/identity-schema.md) §6.2)
16. A company's currency, state, fiscal start, precision, rounding, and code are **immutable once anything is posted** — enforced in `domain/`, for every actor, not as a permission. The same ratchet applies to any feature flag that has shaped posted data. ([company](docs/company.md) §5.2, [company-features](docs/company-features.md) §4)
17. Tax regime and licences resolve by the document's `posting_date`, never by the company's current value. Company `visibility` is a display preference — it never removes audit rows or hides data from an authorized reader. ([company](docs/company.md) §2.3, §6.4)

**Planned tax-date amendment:** Invariant 17 describes the current implementation. The
[India voucher tax plan](docs/voucher-tax-recording.md#3-native-tax-facts-and-dates) requires
a versioned statutory-date resolution contract before new tax profiles are enabled. Do not
silently change existing callers or assume a GL posting date always equals legal time of
supply. Invariant 4 continues to govern fiscal posting; historical snapshots stay immutable.

---

## 7. Testing — mandatory

**No change ships without unit tests — APIs and UI equally, fixes as much as features.** Run the affected suites for every change, including one-line ones, and report the output. Tests are done when green, not when written.

- **Bug fix: write the failing test first**, confirm it fails for the stated reason, then fix. A fix without a regression test is the same bug with a shorter memory.
- **Refactor:** existing tests pass untouched. Needing to change a test means the behaviour changed — say so.

**Backend** — `pytest`, `pytest-asyncio`, `httpx.AsyncClient`. MySQL and RabbitMQ via testcontainers; never mock at the driver level on integration paths.

Per endpoint: happy path against the response schema · unauthenticated → 401 · authenticated but unpermitted → 403 · **wrong-company object access → 403** (§5.2) · invalid input → 422 · idempotency replay → one effect.

Per invariant: **cross-tenant isolation test for every new table** — seed two tenants, query as one, assert the other's rows are absent (the highest-value test here) · money paths assert the returned **type** is `Decimal`, since driver float coercion is silent · posting into a `CLOSED` period is rejected · consumer redelivery yields one effect · a rolled-back transaction leaves no audit row · domain rules tested with no database at all.

**Web** (Vitest + React Testing Library) and **mobile** (Jest `jest-expo` + React Native Testing Library). Playwright for E2E only — never a substitute for unit tests.

Every branch of conditional rendering · every form's validation, success, failure, and pending states · money and date formatting including a non-`en` locale · permission-gated UI present for a permitted role and absent otherwise · 401/403/422/500 each producing the intended state rather than a blank screen · mocked `api-client`, never a live service.

Mobile also: offline and network-failure recovery · **retries reuse the same idempotency key** — this is the mobile path to double-charging someone · token refresh and expiry.

**Coverage:** 90% floor on `libs/platform` and every `domain/`; overall must not decrease. A met percentage doesn't make anything above optional.

```
uv run pytest --cov            # per service
pnpm --filter web test
pnpm --filter mobile test
```

CI runs all three and blocks merge. Run them locally first — CI is the backstop, not the first check.

---

## 8. Definition of done

- [ ] Tests written for every API and UI change, including fixes; regression test present for bug fixes
- [ ] All affected suites run and green, output reported; coverage floors held
- [ ] Ruff and mypy strict clean
- [ ] Migration read line by line; `downgrade` present or justified
- [ ] §2 sync table satisfied
- [ ] §5 security and §6 invariants walked
- [ ] Review pass run, findings reported
- [ ] Docs and decision log updated if a decision changed

Report faithfully: failing tests get shown with output, skipped or blocked work gets named. Don't call work complete until this list actually is. When you hit an unresolved design question, finish everything that doesn't depend on it, then ask.
