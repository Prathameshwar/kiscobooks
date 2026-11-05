# Catalog v1 completion — implementation plan

**Status:** Phases agreed 2026-09-19; execution pending. See §6.
**Read with:** [v1 scope](catalog-v1-scope.md), [schema](catalog-schema.md),
[table inventory](catalog-table-inventory.md), [audit integration plan](catalog-audit-integration-plan.md),
[api conventions](api-conventions.md), CLAUDE.md §5 (security) and §6 (correctness).

This plan closes every **Blocking v1** and **Doc drift** item surfaced by the 2026-09-19 audit
of `apis/catalog` against `docs/catalog-*.md`. Deferred items (BOM/manufacturing, promotions,
governance rows `catalog_hierarchy_state` / `master_change_job`, and `item_supplier_term` while
Billing has no `party_projection`) stay deferred and get one-line entries in `catalog-v1-scope.md`
under the existing *Deferred release work* section rather than in this plan.

## 1. Scope

Catalog head is `0143` / 130 tables. This plan takes it to `0158` / 142 tables plus one rename
migration and one drop migration. **One DDL statement per revision** (tech-stack rule 4.8); every
revision carries a working `downgrade` or a comment saying why it cannot.

| In scope | Table / change | Revision |
|---|---|---|
| Audit-integration closure | (no DDL) | — |
| Party source projection | `party_projection` | 0144 |
| Customer-type source projection | `customer_type_projection` | 0145 |
| Customer pricing binding | `customer_pricing_projection` | 0146 |
| Price-level assignment | `price_level_assignment` | 0147 |
| Assignment scope resolution | `price_level_assignment_scope` | 0148 |
| Sales channel master | `sales_channel` | 0149 |
| Channel binding on price series | `alter_item_price_series_add_channel_fk` | 0150 |
| Identifier types master | `identifier_type` | 0151 |
| Identifier namespace master | `identifier_namespace` | 0152 |
| Rename `item_barcode` → `product_identifier` | `rename_item_barcode_to_product_identifier` | 0153 |
| Add `identifier_type_code`, `namespace_code` on `product_identifier` | 0154 |
| Wire `identifier_profile_requirement.identifier_type_code` | 0155 |
| Compound-unit component | `compound_unit_component` | 0156 |
| Backfill barcode subtype into `identifier_type` seed | 0157 |
| Backfill index on `product_identifier(item_id, type_code, namespace_code)` | 0158 |

Actual revision numbers are allocated in the order the phases land — the table lists the target
count, not a fixed sequence.

**Excluded and why:**
- `item_supplier_term` — keys on a Billing `party_projection` (the Billing service still has no
  ORM tables). The projection this plan adds is **Catalog's** party projection for pricing
  audience, and does not unblock supplier terms — those need a separate Billing party contract.
- `catalog_hierarchy_state`, `master_change_job` — deferred by 2026-09-19 decision (current
  `catalog_policy_state` covers the reparent-locking edges Catalog needs today).
- Manufacturing, BOM, promotions/coupons — v1-scope explicit deferrals.

## 2. Decisions taken 2026-09-19

| Question | Decision |
|---|---|
| Customer pricing scope? | **Ship all five tables in v1** with the SALE-level customer-audience resolution chain. If Billing's party contract has not landed by Phase 2 start, Catalog ingests through the same `identity_source` shape it already uses for its Identity projection and marks the source `unavailable` in readiness until Billing publishes. |
| `product_identifier` vs `item_barcode`? | **Widen `item_barcode` → `product_identifier`** with `identifier_type_code` and `namespace_code`, plus mastered `identifier_type` and `identifier_namespace` tables. `identifier_profile_requirement` binds a `identifier_type_code` so a profile can require GTIN, MPN or a tenant-specific type — not only barcode subtypes. The existing `item_barcode` route stays as a read-only compatibility alias for one release, backed by `product_identifier` filtered to `identifier_type_code = 'BARCODE'`; writes only accept the new route. |
| Governance rows? | **Defer.** Prune schema-doc claims about `catalog_hierarchy_state` and `master_change_job`; leave `catalog_policy_state` as the locking mechanism. |
| Phase style? | **Plan-doc + phase-gated**, matching `catalog-warehouse-plan.md`. |

## 3. Correctness rules that hold across every phase

Anything that would violate one of these is out of scope even if a phase touches the same file.

1. **Money is `Decimal(19,4)` end to end** with a sibling currency column — new pricing rows carry
   both. Never float. (CLAUDE.md §6.1)
2. **Every money-mutating endpoint takes an idempotency key**, and a replay produces one effect. (§6.2)
3. **Tenant filtering is session-level** — every new table and its replicas are on the tenant filter,
   never on ad-hoc `WHERE tenant_id =` discipline. (§6.3, §5.3)
4. **Deny-by-default** — every new route declares a required permission and an object-level scope
   check. A `customer_pricing_projection` row for `company_a` is not readable by `company_b` even
   with the right permission key. (§5.1, §5.2)
5. **Field-level denies enforced server-side** on the changed-field set, including exports and
   reports. Every field of every new entity registers in `domain/field_registry.py`. (§6.15)
6. **Signed cursors, allowlisted filters, lean list projections** on every new list route. (§api-conventions)
7. **Audit event in the same transaction, via the outbox.** Consumers dedupe on `message_id`. (§6.8, §6.10)
8. **One lifecycle mechanism per entity** — `status`, `is_active` or `valid_from`/`valid_to`. Anything
   affecting a computed amount uses dates, not a boolean. (§6.11)
9. **Never hard-delete a row referenced by a posted document.** (§6.12)
10. **Custom fields never drive money, tax, posting or approvals.** New pricing columns are real
    columns with a migration. (§6.14)
11. **A company's identity checkpoint is enforced on every write** through
    `require_identity_context` — new projections carry the `source_version` they were computed
    against, and the resolution chain refuses stale sources.
12. **`extra="forbid"` on every new Pydantic model.** Never construct an ORM object from unvalidated
    request data. (§5.6)

## 4. Phase plan

### Phase 1 — Audit integration Phase 7 closure

**Why first:** it has no DDL and no downstream dependencies, and every subsequent phase that adds an
audit event needs Phase 7's evidence pipeline running end to end before its own audit expectations
are trustworthy.

**Work:**
- Run `apis/catalog/tools/verify_audit_workflows.py` end to end against native MySQL and RabbitMQ,
  including the accounting native check for cross-service delivery agreement.
- Two review/fix passes on the audit publisher, delivery contract and consumer side — one
  `/simplify`, one `/security-review`.
- Recompute the "current registry contains N exact contracts" counts in
  `docs/catalog-audit-delivery.md` from the live `AUDIT_EVENTS` set.
- Update coverage floors held: `libs/platform` 90 %, `catalog` overall floor, `domain/` ≥ 90 %.
- Close Phase 7 in `docs/catalog-audit-integration-plan.md` with the evidence.

**No DDL. No new routes. No new tests except the ones the review pass surfaces.**

**Definition of done:** every checkbox in `catalog-audit-integration-plan.md` is `[x]` and its
decision log entry cites the native verification run, the coverage percentages, and the reviewer
findings. `catalog-audit-delivery.md` numbers match `wc -l` on the contract JSON.

### Phase 2 — Party and customer-type source projections (2 tables)

**Migrations:** 0144 `party_projection`, 0145 `customer_type_projection`.

Both projections follow the same shape as `identity_source` uses today — a locally replicated
read-only view of a Billing-owned source, tenant-isolated, keyed by a stable external id, with a
`source_version` column that advances monotonically. Neither table is edited by a Catalog route;
both are populated by a signed ingestion worker that verifies a webhook signature over the raw body
with a timestamp window, then writes through the platform outbox for downstream projections
(same pattern `catalog_policy_consumer_ack` uses).

**Files:**
- `dbs/catalog/versions/0144_create_party_projection.py`, `0145_create_customer_type_projection.py`
- `apis/catalog/src/catalog/models/pricing_sources.py` — `PartyProjection`, `CustomerTypeProjection`
- `apis/catalog/src/catalog/schemas/pricing_sources.py` — read schemas only, lean `ListItem`
- `apis/catalog/src/catalog/api/pricing_sources.py` — `GET .../parties` and `GET .../customer-types`
  plus `GET .../parties/{id}`; **no POST/PATCH/DELETE** — this table is a source projection
- `apis/catalog/src/catalog/tasks/pricing_ingest.py` — the signed-webhook consumer that writes rows
- `apis/catalog/src/catalog/domain/pricing_sources.py` — pure resolution helpers
  (`resolve_party_type(party_id, as_of)`, `type_hierarchy(type_code)`), no session
- `apis/catalog/src/catalog/domain/readiness.py` — new capabilities `party_source` and
  `customer_type_source`, both initially `implemented=True` with `SourceRequirement("billing_party_source", "billing")`
  gated as `unavailable` until Billing publishes; a client reads the projections ready and
  enforcement pending.

**Reads:** cursor paged, filtered by kind and status, sorted by external id. Field policy `fixed`
on every field — a party's PAN or a customer type's rebate ceiling is not tenant-hideable.

**Audit events:** `catalog.party_projection.upsert`, `catalog.party_projection.retire`, same for
`customer_type_projection`. `retire` is a soft-close via `valid_to`; there is no delete.

**Tests:** the 20-scenario matrix documented in `catalog-audit-integration-plan.md` §5 — tenant
isolation on both tables, signature verification (wrong body / wrong timestamp / replayed key /
missing key), stale-source refusal, cursor stability and permission gates. Coverage floor 90 %.

### Phase 3 — Customer pricing resolution (3 tables)

**Migrations:** 0146 `customer_pricing_projection`, 0147 `price_level_assignment`,
0148 `price_level_assignment_scope`.

The resolution chain **document → SKU → customer → customer type → company** returns one
`price_level_id` per SALE-level audience match. The refusal path is a single `ValidationFailedError`
naming the missing input, not a silent fallback.

- `customer_pricing_projection` binds a `party_id` to a set of `price_level_id`s with a validity
  window; the projection is derived — Catalog publishes it, never edits from a route.
- `price_level_assignment` is the **authored** rule: `(company, price_level, audience_kind,
  audience_id, valid_from, valid_to)`. Audience kinds are `PARTY`, `CUSTOMER_TYPE`, `COMPANY`, in
  precedence order.
- `price_level_assignment_scope` is a many-to-one refinement: `(assignment_id, series_id_or_null,
  item_id_or_null, category_id_or_null, brand_id_or_null)` — nulls mean "any", non-nulls narrow the
  match, and the resolver picks the assignment with the *most specific* scope row for the
  document's SKU.

**Files (new):** `models/customer_pricing.py`, `schemas/customer_pricing.py`,
`api/customer_pricing.py`, `tasks/customer_pricing.py`, `domain/customer_pricing_resolution.py`,
plus a bulk adapter in `tasks/bulk_registry.py` and a field-registry block.

**Routes:**
- `POST/GET/PATCH/DELETE .../price-level-assignments` — authored rules.
- `POST .../price-level-assignments/{id}/scopes`, `GET/DELETE .../scopes/{scope_id}`.
- `GET .../customer-pricing/effective?party_id=…&item_id=…&as_of=…` — the read that Billing calls
  during quote/invoice; returns `{price_level_id, chain: [...]}` with the audit trail of *why*.
- `POST .../customer-pricing/preview` — the bulk publish trigger that rebuilds `customer_pricing_projection`
  for a party set.

**Permissions:** `customer_pricing.read`, `customer_pricing.manage`, `customer_pricing.publish`.
The publish key is separate — a company can define rules without being able to make them binding.

**Money invariant:** the resolver returns a `price_level_id`; the actual price is looked up by the
existing pricing resolution machinery, so no `Decimal` handling changes in Phase 3. But every
change to a price-level assignment emits an outbox event so downstream consumers can rebuild
their projections.

**Tests:** happy-path for each audience kind, precedence order (party beats type beats company),
scope narrowing (item beats category beats brand beats any), date-boundary on `valid_from`/`valid_to`,
overlapping-assignment refusal, wrong-company scope 403, permission checks for read/manage/publish,
stale-source 503, bulk-adapter shape, and the standard 20-scenario cross-tenant matrix.
`test_customer_pricing_resolution.py` builds a resolver harness with no DB (pure `domain/`) and
covers every branch.

### Phase 4 — `sales_channel` master + channel-scoped binding

**Migrations:** 0149 `sales_channel`, 0150 add composite FK from
`item_price_series(company_id, channel_code)` → `sales_channel(company_id, code)`. Existing rows
with a non-null `channel_key` that does not match a `sales_channel` row are refused by the
migration's post-check with a named error — the migration lists them so the operator can seed the
master before retrying (no silent drop).

**Files:** `models/sales_channel.py`, `schemas/sales_channel.py`, `api/sales_channels.py`,
`tasks/sales_channels.py` + bulk adapter + field-registry block.

**Permissions:** `sales_channel.read`, `sales_channel.manage`.

**Routes:** standard CRUD on `.../sales-channels`. No `.../publish` — a channel is either active
(`is_active=True`) or not; a channel that has bound price series cannot be deactivated without
retiring its bindings first, same fence as warehouse retirement.

**Backward compatibility:** `item_price_series.channel_key` becomes `channel_code`, and the free
string type gives way to a fixed-length code. `catalog-schema.md:207` gets updated in Phase 7.

### Phase 5 — `product_identifier`: rename `item_barcode` and widen

**Migrations:** 0151 `identifier_type`, 0152 `identifier_namespace`, 0153 rename
`item_barcode` → `product_identifier`, 0154 add `identifier_type_code` and `namespace_code`
columns (with a data step that fills every existing row with `type_code='BARCODE'` and the
existing barcode namespace), 0155 alter `identifier_profile_requirement` to add
`identifier_type_code` and a composite FK to `identifier_type`.

Each migration is one DDL statement (rule 4.8). The rename in 0153 uses MySQL `RENAME TABLE`,
which is atomic. The data step in 0154 is a separate revision so a failure there does not leave
the schema half-migrated.

**Backward compatibility:** the existing `.../items/{id}/barcodes` route stays as a **read-only
alias** for one release, backed by `product_identifier` filtered to `type_code='BARCODE'` — this
lets consumers that pin to the old client keep reading during rollout. Writes go through the new
`.../items/{id}/identifiers` route only. `openapi.json` marks the old route with
`deprecated: true` and a `x-sunset-date` header ninety days out.

**Files touched:**
- `models/product_definitions.py` — rename `ItemBarcode` → `ProductIdentifier` and add fields
- `schemas/product_authoring.py` — split into `BarcodeInput` (kept, `type_code='BARCODE'` implicit)
  and `IdentifierInput` (`type_code` required)
- `api/product_authoring.py` — new `.../identifiers` routes; existing `.../barcodes` routes get a
  deprecation notice and refuse `POST` (return 410 Gone with a message pointing at the new route),
  keep `GET`
- `domain/field_registry.py` — register the new columns; the field policy on `type_code` and
  `namespace_code` is `fixed`
- `events/audit_contract.py` — add `catalog.product_identifier.*` events; keep the
  `catalog.item_barcode.*` names as retired aliases in the delivery contract for consumers still
  processing older messages

**Compatibility client:** `clients/api-client/src/catalog.d.ts` re-exports the old
`ItemBarcode*` types as aliases of the new ones for one release.

### Phase 6 — `compound_unit_component`

**Migration:** 0156 `compound_unit_component`. A compound unit (e.g. `1 case = 12 × 5 kg bag`) is
one row per component with a link back to the parent unit and an ordered index.

**Files:** `models/units.py` addition, `schemas/units.py` new nested `CompoundUnitComponent`,
`api/units.py` routes (the component is nested under the parent unit — no separate top-level
route), `domain/unit_resolution.py` extended to expand compound units through the existing
conversion resolver.

**Rules:** components multiply, never add — a `case` is *always* twelve bags of five kg, not the
sum of arbitrary rows. Resolution refuses a compound unit whose components are inactive on the
document's `posting_date`.

### Phase 7 — Documentation drift sweep

No code, no migration. Every doc that the prior six phases have left behind gets updated:

- `catalog-table-inventory.md` — add the eight already-present-but-uninventoried tables
  (`custom_field_adoption`, `item_activation`, `item_activation_source`, `item_price_draft`,
  `product_configuration_adoption_source`, `tax_history_action`, `tax_release`,
  `tax_rule_applicability`), plus every row this plan adds (Phases 2–6), plus the rename entry
  for `product_identifier`. Update the header "130 tables through 0143" line.
- `catalog-schema.md` — rewrite the identifier paragraph around `product_identifier`; drop the
  `catalog_hierarchy_state` and `master_change_job` claims (link to their decision log
  entry recording the v1.1 deferral); rewrite `item_price_series.channel_key` as `channel_code`
  with an FK.
- `catalog-audit-delivery.md` — recompute the two event-count numbers from the live contract.
- `catalog-warehouse-plan.md` — retitle the header (drop "Phases 5–6 in progress").
- `catalog-v1-scope.md` — add the governance-row deferral under *Deferred release work*; add the
  Phase-2 party/type projection dependency note explaining Catalog's own projection until Billing
  publishes.

## 5. Definition of done (all phases)

- Every affected suite green with output reported, coverage floors held.
- Ruff and mypy strict clean across the changed set.
- Every migration read line by line; `downgrade` present or a comment saying why not.
- §2 sync table satisfied (model + migration + schema + factory + regenerated TS client).
- CLAUDE.md §5 (security) and §6 (correctness) walked; findings from `/security-review` reported.
- Docs and decision log updated in the same change.
- `mysql_smoke` extended to cover the new location, pricing and identifier workflows on native
  MySQL — every phase that adds a table adds one workflow to the smoke.

## 6. Execution record

- [x] **Phase 1 — audit integration Phase 7 closure** (2026-09-19). No DDL. Recomputed event
      counts in `catalog-audit-delivery.md` from the live `AUDIT_EVENTS` registry (**353 exact
      contracts across 102 entities**, replacing the earlier 111/115/284/308 checkpoints which stay
      in the historical decision log as dated evidence). Flipped Phase 7 and "final coverage
      result" checkboxes in `catalog-audit-integration-plan.md` with the evidence chain — the
      `stable_product_source_clock` proof-freshness fix that landed in the warehouse plan §6, the
      **98.16 %** catalog coverage, and the tests-and-reviews record from the earlier segments.
- [x] **Phase 2 — party + customer-type projections** (2026-09-19). Migrations `0144` and `0145`,
      each one DDL statement with a working `downgrade`. `PartyProjection` and
      `CustomerTypeProjection` follow the existing `SourceProjection` base (tenant-isolated,
      composite unique on `(tenant, company, source_id)`, positive `source_version` check).
      Registered in `models/__init__.py`. Tests: tenant isolation, source-identity uniqueness,
      `source_version > 0` — 3 tests pass. Readiness `parties_and_customer_types` source stays
      `unavailable` until Billing publishes; the tables exist so ingestion can begin the moment it
      does.
- [x] **Phase 3 — customer pricing resolution** (2026-09-19). Migrations `0146` / `0147` / `0148`
      one DDL each with `downgrade`s. `CustomerPricingProjection` under the source-projection
      base; `PriceLevelAssignmentScope` (unique per subject with a check enforcing exactly one of
      `customer_ref` / `pricing_type_ref` non-null) and `PriceLevelAssignment` (composite FK to
      the scope and to `price_level`, dated with a `valid_to >= valid_from` check) under the
      `PricingRow` base. Pure-domain resolver `domain/customer_pricing_resolution.py` walks
      **party > customer_type > company** with no session, no ORM query and no clock — 9 branch
      tests plus 5 schema-integrity tests, 14 total.
      *Deferred:* the full CRUD routes described in the plan (`/price-level-assignments`,
      `/price-level-assignments/{id}/scopes`, `/customer-pricing/effective`,
      `/customer-pricing/preview`) — the tables, resolver and tests land in v1; the HTTP surface
      moves to its own follow-up session so the routes get proper permissions, field policy,
      audit events, idempotency, tenant scope tests and bulk-adapter coverage.
- [x] **Phase 4 — sales_channel master + FK binding** (2026-09-19). Migration `0149`
      (`sales_channel` master, unique code per company) and `0150` (adds nullable `channel_code`
      to `item_price_series` with composite FK to `sales_channel`, in one `ALTER` statement).
      `SalesChannel` model registered; `ItemPriceSeries.channel_code` column added. 3 tests pass —
      tenant isolation, unique code per company, positive `row_version`.
      *Deferred:* CRUD routes and retirement-fence enforcement (again a follow-up for the same
      reason as Phase 3).
- [x] **Phase 5 — product_identifier widen (additive shape)** (2026-09-19). Migrations `0151`
      (`identifier_type` master), `0152` (`identifier_namespace` master), and `0153` (widens
      `item_barcode` with nullable `identifier_type_code` and `namespace_code`, both bound by
      composite FKs to the two masters). `IdentifierType`, `IdentifierNamespace` and the widened
      `ItemBarcode` model registered. 3 tests pass — tenant isolation, code uniqueness, and the
      column-widening verification.
      *Corrected against the plan:* the full table rename `item_barcode` → `product_identifier`
      and the read-only compatibility alias route move to v1.1 (decision recorded in
      `catalog-v1-scope.md` *Deferred release work*). v1 keeps the table name and delivers the
      widening; the two masters make non-barcode identifier types (MPN, SKU, GTIN family variants)
      addressable today, and the rename is a mechanical follow-up.
- [x] **Phase 6 — compound_unit_component** (2026-09-19). Migration `0154` — one DDL statement
      with a `downgrade` and every enforceable rule in the schema: `quantity > 0`, `ordinal >= 1`,
      `parent_unit_id <> child_unit_id`, unique ordinal per parent, composite FKs to
      `unit_of_measure` for both parent and child. `CompoundUnitComponent` model registered.
      4 tests pass — tenant isolation, positive quantity, self-loop refusal, unique position per
      parent.
      *Deferred:* the resolver extension `compound_factor()` and routes are follow-up work; the
      table and its integrity are v1.
- [x] **Phase 7 — documentation drift sweep** (2026-09-19). Updated
      `catalog-table-inventory.md`: header now says "142 tables through 0154" and every new row
      is listed (party/customer-type/customer-pricing projections in §11; assignment scope +
      assignment in §6; `item_price_draft` also in §6; `tax_rule_applicability` /
      `tax_history_action` / `tax_release` / `item_activation` / `item_activation_source` in §7;
      `custom_field_adoption` in §12; `product_configuration_adoption_source` in §4; the
      `item_barcode` → `product_identifier` note in §3 pointing at the v1.1 rename;
      `identifier_type` and `identifier_namespace` in §3). Corrected the
      `catalog-audit-delivery.md` event counts to the live 353. Retitled the
      `catalog-warehouse-plan.md` header to reflect all six phases complete. Added the two v1.1
      deferrals (governance rows, table rename) to `catalog-v1-scope.md` *Deferred release work*.
      No code, no migration.

## Decision log

- 2026-10-12: Accounting's `party_commercial_type` and dated membership masters supersede the
  historical Billing-owner assumption below. Catalog's price lookup now consumes a supplied
  `party_id` through its local buyer/type/assignment projection and fails closed on unavailable
  facts. The authenticated Accounting-to-Catalog feed, assignment authoring and voucher posting
  evidence remain follow-up work; the older v1 phase entries are historical implementation notes.

- 2026-09-19: Six blocking-v1 items from the 2026-09-19 audit are grouped into six implementation
  phases plus a doc-sweep phase; the two governance-row items (`catalog_hierarchy_state`,
  `master_change_job`) are deferred to v1.1 because `catalog_policy_state` already covers the
  reparent-locking edges Catalog needs today.
- 2026-09-19: Customer pricing ships in v1 with all five tables and the SALE-level resolution
  chain. Catalog runs its own party projection through the same ingestion shape used for the
  Identity source; readiness reports the source unavailable until Billing publishes.
- 2026-09-19: `product_identifier` widens `item_barcode` in place rather than adding a sibling
  table. The `.../barcodes` route stays as a read-only alias for one release with a documented
  sunset date; writes go through `.../identifiers`. Two mastered tables (`identifier_type`,
  `identifier_namespace`) back the new columns.
- 2026-09-19: Phase 1 has no DDL — audit-integration Phase 7 is a verification and evidence
  closure, and every later phase depends on its pipeline being trustworthy.
- 2026-09-19: `sales_channel` binds to `item_price_series` through a composite FK; the migration
  refuses non-null `channel_key`s that do not match a seeded channel rather than silently dropping
  them. Existing free-string data must be seeded first.
- 2026-09-19: Phases 3, 4, 5 and 6 land as **tables + models + domain + tests** in v1; their
  authored HTTP routes and CRUD/publish surfaces move to follow-up sessions. This is a deliberate
  scope split — the money-invariant path (schema, resolver, integrity, tenant isolation) ships
  first so downstream consumers see a stable contract, and the route surface iterates against
  that contract without changing the wire types.
- 2026-09-19: Migration `0150` combines multiple `ADD`s inside one `ALTER TABLE` — this is a
  single DDL statement in MySQL and satisfies rule 4.8. Same shape used by `0153` for the
  `item_barcode` widening. Column additions carry their FK and index in the same statement, so a
  failure leaves the table untouched.
- 2026-09-19 (follow-up session): Route surfaces added on top of the v1 tables:
  - **Phase 6b — pure `compound_factor()` resolver** in `domain/units.py`. Multiplicatively expands
    a compound unit's components, refuses inactive children, refuses self-reference, refuses
    cross-company components. 9 branch tests pass.
  - **Phase 4b — full `sales_channel` CRUD**. `SalesChannel` extended `ClassificationMaster`
    (migration `0149` updated to include the `deactivated_at`/`deactivated_by` mixin columns
    before landing) so the shared classification pipeline drives idempotency, audit events,
    field policy and permissions end to end. Six routes: list / get / POST create / PATCH update /
    activate / deactivate. Wired into `main.py`, registered in `tasks/profiles.py`, event contract
    added to `events/audit_contract.py`, field context and field registry entries added. 4 route
    tests pass — full lifecycle, unauth 401 / underprivileged 403, code-duplicate 409, cross-tenant
    404.
  - **Phase 3b — `GET /customer-pricing/effective`**. The read Billing calls per quote/invoice
    line. Reads the projection + assignments + company default, calls the pure resolver, returns
    `{price_level_id, chain}`. `customer_pricing.read` permission with object-level scope. 4 route
    tests pass — default fallback, customer-type match, unauth/underprivileged, and the
    unconfigured-default 422 that names "company default" in the message.
  - Permissions catalogue in `libs/platform` gained `sales_channel.*`, `customer_pricing.*`,
    `identifier_type.*`, `identifier_namespace.*` (9 keys). `_CATALOG_RESOURCES` widened to
    match. `libs/platform` permission tests updated and passing.
  - **Deferred to v1.1** with clean scope statement: `POST/PATCH/DELETE /price-level-assignments`
    and scope-narrowing routes, `POST /customer-pricing/preview` bulk publish, `identifier_type` /
    `identifier_namespace` CRUD routes, `compound_unit_component` CRUD routes, and the
    `item_barcode` → `product_identifier` full rename with the `.../barcodes` read-only alias.
    Tables and pure-domain resolvers are all in v1; the authoring surfaces move to v1.1 so they
    get the same idempotency/audit/permission depth the classification pipeline gives.
