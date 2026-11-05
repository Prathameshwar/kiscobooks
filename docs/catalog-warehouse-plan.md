# Stock-location definitions — implementation plan (C7.08–C7.11)

**Status:** Phases agreed 2026-09-17; **all six phases complete** (schema head 0143). See §6.
**Design contract:** [stores, godowns and stock-location configuration](catalog-warehouses.md).
**Read with:** [inventory integration contract](catalog-inventory-integration.md),
[schema](catalog-schema.md) §*Shared configuration*, [table inventory](catalog-table-inventory.md) §5,
[api conventions](api-conventions.md).

This document is the execution record for the warehouse area. It exists because the previous
205-task ledger was removed on 2026-09-13; per-phase closure evidence is recorded here.

## 1. Scope

Catalog-owned location **definitions** only. Billing owns stock, availability, transfers,
transit movement, counts, damage and the product ledger ([integration contract](catalog-inventory-integration.md) §2).

| In scope | Table | Revision |
|---|---|---|
| Location master | `warehouse` | 0132 |
| Company location configuration | `company_warehouse_configuration` | 0133 |
| Operation-policy revisions | `warehouse_operation_policy_revision` | 0134 |
| Non-stockholding grouping | `warehouse_group` | 0135 |
| Dated group hierarchy | `warehouse_group_parent` | 0136 |
| Dated primary-group membership | `warehouse_group_assignment` | 0137 |
| Bins inside a warehouse | `warehouse_bin` | 0138 |
| SKU location-selection mode | `item_warehouse_policy` | 0139 |
| Restrictive SKU/location/operation grants | `item_warehouse_permission` | 0140 |
| Per-location replenishment targets | `item_replenishment_policy` | 0141 |
| Published release manifest | `catalog_policy_release` | 0142 |
| Trusted consumer acknowledgement | `catalog_policy_consumer_ack` | 0143 |

Catalog schema head is 0131 / 118 tables; this takes it to 0143 / 130. **One DDL statement per
revision** (tech-stack rule 4.8); any follow-on index or check constraint takes its own revision
above 0143. Every revision carries a working `downgrade`.

**Excluded and why:**

- `item_supplier_term` — keys on a Billing `party_projection` that does not exist (`apis/billing/`
  is empty). Supplier terms cannot be defined against an invented party. Stays open in
  [table inventory](catalog-table-inventory.md) §5.
- `item_inventory_profile` — already migrated (`models/tax.py`); part of C7.10 is done.
- Manufacturing `allow_production_issue`/`allow_production_receipt` and `bom_location_default` —
  optional M0–M4 branch ([design](catalog-warehouses.md#optional-manufacturing-location-policies)).
- Everything in the design contract §4 and the external rows of its §6 table: those are Billing
  contract references, and the scenarios there are Billing's acceptance tests, not Catalog's.

## 2. Decisions taken 2026-09-17

| Question | Decision |
|---|---|
| Release/acknowledgement (C5.06–C5.09) | **In scope, Phase 6.** Without a trusted acknowledgement Catalog cannot report a policy as applied ([design](catalog-warehouses.md) §5), and non-Main deactivation has no fence. Ack ingestion is testable now with a signed source event; Billing need not exist. |
| Company activity-default history | **Current-state pointers plus audited change history**, not dated revision rows. A default is resolution convenience evaluated at operation time, not a term that prices or posts; a dated default would silently change resolution on a boundary crossing. Design contract §6 corrected accordingly. |
| v1 scope | **Definitions are v1.** [catalog-v1-scope.md](catalog-v1-scope.md) updated; operational multi-store enforcement stays deferred pending Billing. |

## 3. Cross-cutting rules for every phase

- Deny by default: every route declares a permission from the fixed catalogue, plus an
  object-level company/scope check against the addressed row. Endpoint permission alone is not
  a scope check ([CLAUDE.md](../CLAUDE.md) §5.2).
- Same-company composite foreign keys (`tenant_id, company_id, id`) for every local reference;
  session-level tenant filtering stays in `libs/platform`.
- `master_constraints()` (`models/commercial.py:27`) for each code/name master; `row_version`
  with `expected_version` optimistic concurrency; `Idempotency-Key` on every write.
- Lists: signed keyset cursors (50 default / 200 max), typed allowlisted filters, resource-specific
  indexed search, allowlisted sorting with `id` tie-breaker, dedicated lean `ListItem` schema.
  Read-denied fields are excluded from filters, search, sorting and exports.
- Audit event in the same transaction via the outbox, for every state change, holding
  `actor_user_id` and references only.
- Each phase ends with tests green and the repo working: model, migration, Pydantic schema, test
  factory, field-registry entry and field-policy map land together. No table without its
  two-tenant isolation test.
- Quantities `DECIMAL(19,4)`; `Decimal` asserted as the returned type on every quantity path.
- Enums are `VARCHAR` + app validation (`kind`, `selection_mode`, `delivery_state`).

## 4. Phases

### Phase 1 — Permissions, feature gate, honest readiness

No tables. Shared-library first so later phases have real keys to declare.

**Changes**

- `libs/platform/src/billing_platform/permissions.py`: add 12 keys —
  `warehouse.read|manage|publish|deactivate`, `warehouse_group.read|manage|move`,
  `warehouse_bin.read|manage`, `item_warehouse_policy.read|manage`, `catalog.release.read`.
  Add `item_warehouse_policy` to `_CATALOG_RESOURCES` so bulk job authority can carry it.
  Per-location replenishment is governed by `item_warehouse_policy.manage`: both are per-SKU
  per-location definitions maintained by the same role, and splitting them adds a key with no
  separation-of-duties reason. Ack ingestion gets no key — it is source-only.
- `apis/identity/src/identity/domain/system_roles.py` + `seeds/`: grant the manage/publish/
  deactivate/move set to the company administrator, read-only to the tenant auditor. The boot
  check (`assert_known_permission`) turns a missed seed into a boot failure, not a silent 403.
- `libs/platform` version 0.25.0 → 0.26.0; refresh every consuming service's lockfile.
- `apis/catalog/src/catalog/domain/readiness.py`: add
  `Capability("stock_location_definitions", "C7")` with `implemented=False`, and a
  `SourceRequirement` row for the Billing warehouse guard. Today the registry lists no warehouse
  capability at all, so a client cannot discover the gap.
- New `apis/catalog/src/catalog/domain/warehouses.py` (pure, no framework): resolves the
  three company modes of [design](catalog-warehouses.md) §1 — inventory off → Main metadata only;
  inventory on + `multi_godown` off → Main exclusively, another id **rejected, never mapped**;
  multi_godown on → additional locations. `multi_godown` already exists in
  `libs/platform/src/billing_platform/features.py:60` (`requires=("inventory",)`,
  `locks_on="godown_movement"`); no Identity feature change.

**Exit:** `libs/platform` and Identity suites green with a test per new key; seed/role tests assert
every key is granted somewhere; mode resolver unit-tested with no database; Catalog behaviour
unchanged; coverage floors held.

### Phase 2 — Location master, Main + transit bootstrap, company configuration

**Tables:** `warehouse` (0132), `company_warehouse_configuration` (0133).

**Model** (`models/warehouses.py`)

- `warehouse`: `ClassificationMaster` base + `master_constraints("warehouse")`;
  `kind` in `STORE|GODOWN|INTERNAL_TRANSIT`, optional department reference, timezone,
  address and tax-location facts (country/state to the ISO reference tables), `is_system`.
- `company_warehouse_configuration`: company-PK singleton; `main_warehouse_id` immutable after
  insert; `default_sale_warehouse_id`, `default_purchase_warehouse_id`,
  `default_customer_return_warehouse_id`, `default_opening_warehouse_id`; `source_version`;
  `row_version`. Unique Main enforced in the schema, not only in code.

**Commands** (`tasks/warehouse_bootstrap.py`, `tasks/warehouses.py`)

- `bootstrap()` modelled on `tasks/pricing_foundation.py:135`: MAIN, INTERNAL_TRANSIT and the
  configuration row in **one transaction under the `catalog_policy_state` company lock**
  (`tasks/policy_state.py`), idempotent, with catch-up for companies created before this ships.
  Every warehouse command calls it first, exactly as `create_level` does. Readiness for the
  capability stays false until the row set is complete.
- MAIN and INTERNAL_TRANSIT are reserved from create, identity update, deactivate, reassignment
  and import; the display label stays editable. Transit is never selectable or defaultable.
- Additional-location create requires `multi_godown`; the empty master alone is not financial use,
  so creation does not trip the ratchet.

**API** (`api/warehouses.py`, registered in `api/routes.py`)

`POST|GET /companies/{company_id}/warehouses`, `GET|PATCH /warehouses/{warehouse_id}`,
`POST /warehouses/{warehouse_id}/deactivate` (fenced in Phase 6),
`GET|PATCH /companies/{company_id}/warehouse-configuration`. Field-registry entries in
`domain/field_registry.py`; read/manage maps in `tasks/field_context.py`.

**Exit tests** — concurrent bootstrap creates exactly one Main (mandated, [design](catalog-warehouses.md) §7);
tenant isolation on both tables; 401 / 403-unpermitted / **403 wrong-company object** / 422;
idempotency replay yields one effect; reserved-kind mutation and delete refused; inventory-off
create refused; multi_godown-off second location refused and *not* silently mapped to Main;
audit row present on success and absent after rollback; `Decimal` typing where applicable.

### Phase 3 — Operation-policy revisions and activity defaults

**Table:** `warehouse_operation_policy_revision` (0134).

- Eight typed booleans exactly as [design](catalog-warehouses.md) §2 names them: `allow_sale_issue`,
  `allow_purchase_receipt`, `allow_transfer_in`, `allow_transfer_out`,
  `allow_customer_return_receipt`, `allow_supplier_return_issue`, `allow_opening_stock`,
  `allow_adjustment`. No JSON operation keys. Revision number + UTC validity window, immutable
  once published, following the `inventory_templates.py` revision pattern (unique
  `(tenant, company, id)`, unique `(tenant, company, warehouse_id, revision)`, composite FK).
- New ordinary locations inherit a reviewed template; permissions are never inferred from a name.
- `domain/warehouse_resolution.py` (pure): authorized explicit allocation > SKU activity default >
  company activity default > built-in Main. A configured-but-inactive, denied, stale or
  operation-disabled default is an **error**, not permission to fall through. An activity blocked
  even at Main resolves to *no eligible location* — never a re-enabled flag or an unrelated store.
  With `multi_godown` off, all four defaults must be Main.
- Operation kind comes from the domain handler; a caller cannot relabel a sale issue as an
  adjustment or a purchase as an opening. Flags grant no permission by themselves.
- `preview` / `publish` with delivery state `PENDING|APPLIED|REJECTED`; `APPLIED` becomes reachable
  only through the Phase 6 acknowledgement.
- Company defaults change through a typed audited action, not a bare PATCH of pointer columns;
  a default change moves no stock and touches no quantity.

**API:** `GET /warehouses/{warehouse_id}/operation-policy` (current + history),
`POST /warehouses/{warehouse_id}/operation-policy/preview|publish`,
`POST /companies/{company_id}/warehouse-configuration/defaults`.

**Exit tests** — sale-only and purchase-only flags independent in both directions;
purchase-disabled does not disable transfer-in or customer return; zero-price gift still needs
sale issue; every resolver branch including each error branch; blocked-at-Main reports no eligible
location; revision immutability and preserved history; multi_godown-off forces Main defaults;
default change emits audit and moves nothing; PENDING is what a fresh publish reports.

### Phase 4 — Groups and bins

**Tables:** `warehouse_group` (0135), `warehouse_group_parent` (0136),
`warehouse_group_assignment` (0137), `warehouse_bin` (0138).

Direct reuse of the `ItemGroup` / `ItemGroupParent` dated-hierarchy machinery
(`models/classification.py`, `tasks/classification.py`): unique on
`(tenant, company, group_id, valid_from)`, two composite FKs, descendant index, bounded cycle and
depth rejection, `warehouse_group.move` for reviewed reparenting, and `catalog_policy_state`
generation bumped so a new descendant invalidates a stale preview.

- Groups are non-stockholding, cannot be selected as a stock location, and **confer no access to
  member stores** — the real privilege-escalation risk in this area.
- One dated primary group per warehouse; rollups deduplicate authorized members and preserve
  historical membership across reparenting.
- Main remains a physical warehouse regardless of group assignment.
- `warehouse_bin` is parent-scoped (`master_constraints("warehouse_bin", parent="warehouse_id")`),
  subordinate to warehouse permissions; bins are not a substitute for groups or vice versa.

**API:** `api/warehouse_groups.py` — group CRUD, `POST /warehouse-groups/{id}/move`,
`PUT /warehouses/{id}/primary-group`, `GET /warehouse-groups/{id}/members`; bins under
`api/warehouses.py` as `POST|GET /warehouses/{warehouse_id}/bins`, `GET|PATCH /warehouse-bins/{id}`.

**Exit tests** — cycle and depth rejection; dated reparent preserves historical rollups;
group membership grants no store access; two primary groups on one date rejected; bin code unique
within its warehouse and repeatable across warehouses; group cannot be used as a stock location;
tenant isolation on all four tables; generation bump invalidates a stale preview.

### Phase 5 — SKU location policies and replenishment

**Tables:** `item_warehouse_policy` (0139), `item_warehouse_permission` (0140),
`item_replenishment_policy` (0141) in `models/warehouse_policies.py`.

- `selection_mode` in `ALLOW_ALL_ACTIVE|ALLOW_LIST` with explicit membership and per-operation
  restrictions. `domain/warehouse_policy_composition.py` (pure) enforces that a product
  restriction **narrows, never widens** the location's own policy, and that a missing row means
  the documented company baseline — not a guessed deny and not a caller-supplied authorization
  claim.
- Per-location minimum / reorder / target / MOQ / order multiple as `DECIMAL(19,4)`, validated
  against the existing unit-grid rules (`tasks/product_quantity.py`, `tasks/unit_consistency.py`).
  Services and non-stock goods are rejected: Main's existence grants no allocation.
- Optional role-specific SKU activity defaults, subject to the same resolver errors as Phase 3.

**API:** `GET|PUT /items/{item_id}/warehouse-policy`,
`GET|PUT /items/{item_id}/replenishment-policy`.

**Exit tests** — narrowing-only composition proved against a permissive company policy, in both
orders; a widening attempt rejected; missing-row baseline; service SKU rejected; unit-grid
exactness with `Decimal` type assertions; wrong-company item 403; a policy row referencing a
location blocks that location's deactivation; restricted actor cannot enumerate other stores
through the policy read.

### Phase 6 — Release/acknowledgement, deactivation fence, bulk, verification

**Tables:** `catalog_policy_release` (0142), `catalog_policy_consumer_ack` (0143), per the
column contract in [schema](catalog-schema.md) lines 103–104.

- `catalog_policy_release`: company, revision, effective date, `published_at`, bounded dependency
  manifest. Only a validated complete release is consumable for its effective interval.
  Publication compares `catalog_policy_state` as well as reviewed dependency versions.
- `catalog_policy_consumer_ack`: company, trusted consumer, release/aggregate and source-event
  identity, acknowledged/enforced version, applied/rejected result, safe reason.
  **Idempotent source-only ingestion** through the consumer worker with `message_id` dedupe —
  no public write route; scoped read under `catalog.release.read`. An older acknowledgement cannot
  regress current enforcement.
- Delivery state resolves from the ack: no ack → `PENDING`; enforced version matched → `APPLIED`;
  consumer rejection → `REJECTED` with its safe reason.

**Deactivation fence** (`tasks/warehouses.py`, [design](catalog-warehouses.md) §5) — Catalog-side
preconditions: not Main, not transit; no company or SKU default, bin, group assignment or product
policy depending on it. The stock/value/holds/pending-document half is checked in Billing under
its location guards; Catalog acknowledges deactivation **only after the coordinated fence**.
Until a trusted consumer exists, deactivation returns an explicit pending state — it never infers
safety from a displayed zero quantity.

**C7.11 rejection guards** — warehouse and product PATCH, and every Catalog import path, reject
on-hand, opening stock, physical lot/serial, transfer, count and adjustment fields with 422 rather
than ignoring them. Tested per surface, since a silently dropped quantity field is the failure mode.

**C10.09 bulk adapters** (`tasks/bulk_registry.py`) — warehouse, group, group parent, assignment,
bin, operation policy, item warehouse policy and replenishment policy CREATE/UPDATE through the
same native commands, with templates and field-policy maps. Explicitly reject stock balances,
counts, transfers, Main mutation and party creation. Bulk uses exact scoped codes/IDs; an omitted
location uses the same resolver as the API.

**Readiness** — flip `stock_location_definitions` to `implemented=True`; the Billing warehouse-guard
source requirement stays `unavailable`, so a client sees definitions ready and enforcement pending.

**Verification (definition of done)**

- Full Catalog suite plus `libs/platform` and Identity suites, output reported; coverage floors
  held (90% on `libs/platform` and every `domain/`; overall not decreased).
- Ruff clean; mypy strict clean, no new `type: ignore` without a reason comment.
- Every one of revisions 0132–0143 read line by line against its model, with `downgrade` present;
  `VARCHAR` lengths, generated columns, index names and `DECIMAL(19,4)` scale checked by hand,
  since autogenerate misses them on MySQL.
- `tools/mysql_smoke` run against native MySQL (testcontainers Docker is unavailable here, so the
  live-MySQL suites skip; the smoke run is the substitute and its result is reported as such).
- Two-tenant isolation test present for all 12 new tables.
- OpenAPI export → `clients/api-client` regeneration → TypeScript typecheck of its consumers.
- `/simplify`, and `/security-review` because this touches permissions, tenant scoping and
  object-level scope. Findings reported including "nothing".

**Doc sync**

| Doc | Update |
|---|---|
| [catalog-warehouses.md](catalog-warehouses.md) | Status line, §6 activity-default correction, release row, §7 pointer here, decision log |
| [catalog-v1-scope.md](catalog-v1-scope.md) | Definitions listed as included; deferred section narrowed to operational enforcement |
| [catalog-table-inventory.md](catalog-table-inventory.md) | Stale head/count line (says 57 tables at 0059); mark `item_supplier_term` blocked |
| [catalog-schema.md](catalog-schema.md) | Stale head/count line (says 114 tables at 0116) |
| New `docs/catalog-warehouse-api.md` | Route registry in the style of the other `catalog-*-api.md` files |
| `apis/catalog/README.md` | Link the new route registry |
| This document | Per-phase closure evidence as each phase lands |

## 5. Sequencing and risk

Phases are strictly ordered: 1 gates every route's permission; 2 creates the identity every later
row references; 3 needs the configuration row; 4 and 5 are independent of each other and could run
in parallel if useful; 6 needs all of them.

| Risk | Handling |
|---|---|
| Bootstrap race creating two Mains | Company lock via `catalog_policy_state`, unique Main constraint in the schema, mandated concurrency test |
| Group membership leaking store access | Groups carry no scope; explicit negative test in Phase 4 |
| Fallback chain quietly re-enabling a blocked activity | Configured-but-invalid default is an error; *no eligible location* is a first-class outcome |
| Product policy widening a location's capability | Composition is narrowing-only, unit-tested with no database |
| Claiming a policy is enforced in another database | `PENDING` until a trusted ack; deactivation fenced |
| Catch-up for pre-existing companies missed | `bootstrap()` runs from every warehouse command, with a test seeded from a company that has no configuration row |

## 6. Progress and closure evidence

- [x] **Phase 1 — permissions, feature gate, honest readiness.** 12 keys in
      `libs/platform/src/billing_platform/permissions.py` with `item_warehouse_policy` in
      `_CATALOG_RESOURCES`; role grants in `identity/domain/system_roles.py` (all 12 to
      `company_admin`, the 5 reads to `tenant_auditor`, `warehouse.read` to `salesperson`,
      `billing_clerk` and `viewer`); `catalog/domain/warehouses.py` mode resolver;
      `readiness.py` capability `stock_location_definitions` (false) and the Billing
      `warehouse_stock_and_location_guards` source requirement; shared library 0.26.0 with six
      lockfiles. Tests: `libs/platform/tests/test_permissions.py` 33 passed,
      `apis/identity` role suites 46 passed (`tests/test_warehouse_roles.py` new),
      `apis/catalog/tests/test_warehouse_modes.py` + `test_api.py` 21 passed. Ruff and mypy
      strict clean on every touched module.
      *Carried:* `test_salesperson_role.py` was already red at `2d091fd` — it pinned 27 keys
      while the committed role held 28 (`product_configuration.read` added without updating the
      test). Fixed alongside the new `warehouse.read`, and the grant count is now derived from
      the role so it cannot drift again.
- [x] **Phase 2 — location master, Main + transit bootstrap, company configuration.**
      `0132_create_warehouse.py` and `0133_create_company_warehouse_configuration.py`, both with a
      working `downgrade`; `models/warehouses.py`, `tasks/warehouses.py` (bootstrap, catch-up and
      the command handlers), `tasks/warehouse_policy.py` (default-pointer and dependency checks),
      `schemas/warehouses.py`, `api/warehouses.py`; field-registry entries and read/manage maps for
      both tables. Tests: `test_warehouse_api.py` 11, `test_warehouse_storage.py` 7,
      `test_warehouse_concurrency.py` 3 — the mandated concurrent bootstrap creates exactly one
      Main; tenant isolation on both tables; 401 / 403-unpermitted / 403 wrong-company /
      404-alien-tenant / 422; replay yields one effect; reserved kind and code refused whatever
      wrote the row, including a direct write the API never saw; inventory-off and second-location
      creates refused rather than mapped to Main; audit event present on success and absent after
      rollback.
      *Plan corrected against the implementation:* provisioning is
      `POST /companies/{company_id}/warehouse-configuration/bootstrap` returning the standard
      `CommandOutput` with 201, not a `PATCH` — it creates rows, so it is a command with an
      idempotency key, and `PATCH` on a singleton nobody may edit field-by-field would have been a
      lie. There is therefore no `PATCH /warehouse-configuration`: the only writable part of that
      row is the four activity defaults, and Phase 3's typed action owns them. Bootstrap-on-update
      was dropped as dead code — every warehouse command already runs the catch-up first, so a
      second call site could never be reached. `POST /warehouses/{id}/activate` was added
      alongside `deactivate` for parity with every other master.
- [x] **Phase 3 — operation-policy revisions and activity defaults.**
      `0134_create_warehouse_operation_policy_revision.py` (`downgrade` present); the eight typed
      booleans as columns, no JSON operation keys; `tasks/warehouse_operations.py`,
      `domain/warehouse_resolution.py` (pure, no framework); the four routes below; audit contract
      regenerated (`contracts/audit-events.json` and the console entity list now carry
      `catalog.warehouse_operation_policy_revision`). Tests: `test_warehouse_operations.py` 10 and
      `test_warehouse_resolution.py` 36 — a publish supersedes rather than rewrites and the trail
      keeps what the superseded revision allowed, with the two windows meeting at one instant; a
      proposal that changes nothing writes nothing and does not move the generation; a publish
      against a stale generation or an unseen Identity checkpoint is refused; transit custody's
      policy is reserved (preview `publishable: false`, publish 409); a new location inherits
      Main's reviewed policy on create without its creator holding `warehouse.publish`, and the
      retained create receipt replays to one revision; an activity default may only point at a
      location allowed to serve *that* operation, defaults move no revisions, and with
      `multi_godown` off only Main is accepted; every resolver branch including each error branch
      and *no eligible location*; a read-denied flag is absent from the view, the history and the
      preview diff and 403s the publish; a write-denied flag 403s the publish and writes nothing;
      tenant isolation with one company id present in two tenants. Ruff and mypy strict clean on
      every touched module.
      *Plan corrected against the implementation:* there are no drafts. A publish inserts a
      revision that is already in force and closes its predecessor's window in the same
      transaction, so "immutable once published" is structural rather than a rule something has to
      remember — no route can rewrite one, and there is no update route to omit. `preview` is a
      `POST` with the proposal in the body: eight booleans and a reviewer's intent do not belong in
      an access log, and it stays outside the idempotency-key path because it writes nothing.
      `delivery_state` is computed, not stored, and reads `PENDING` for every revision until the
      Phase 6 acknowledgement exists.
      *Contract change:* `GET /companies/{company_id}/warehouse-configuration` now reports the live
      Identity checkpoint as `source_version` — the meaning it carries on every other Catalog read
      — and the stored provisioning checkpoint as `provisioned_source_version`. The defaults action
      compares the echoed `expected_source_version` against the live checkpoint, so projecting the
      stored column under that name made the action unreachable for any client that read its
      expectations from this endpoint once Identity advanced.
- [x] **Phase 4 — groups, dated membership and bins.** `0135_create_warehouse_group.py`,
      `0136_create_warehouse_group_parent.py`, `0137_create_warehouse_group_assignment.py`,
      `0138_create_warehouse_bin.py` — one DDL statement each, every `downgrade` present;
      `models/warehouse_groups.py`, `tasks/warehouse_groups.py` (the two specs and the dated
      member rollup), `schemas/warehouse_groups.py`, `api/warehouse_groups.py` (17 routes);
      `assert_groupable()` in `tasks/warehouse_policy.py`; four field-registry entries with their
      read/manage maps; audit contract regenerated with 14 new event names across the four
      entities plus `catalog.warehouse.assign`. The item-group machinery was generalized rather
      than copied: `DatedEdge` now describes any dated relation a master appends to, so a group's
      parent link and a location's primary group append through the same `move_edge` — which is
      why "who was under this group in March" answers the same way for both.
      Tests: `test_warehouse_groups.py` 9 passed; re-run together with `test_warehouse_api.py`,
      `test_warehouse_storage.py`, `test_warehouse_operations.py`, `test_classification_api.py`,
      `test_classification_storage.py`, `test_field_registry.py` and `test_audit_contract.py`, 64
      passed; `test_api.py` 6 passed. Covered: a dated cycle and a ninth level are refused and the
      rejected create leaves neither a group nor an interval nor a moved generation; a group whose
      opening interval is missing is refused rather than read as unparented; a reparent effective
      later leaves March's rollup answering March — members, children and the parent history each
      answer per date, and the superseded interval is still there, closed the day before its
      successor; the rollup needs `warehouse_group.read` **and** `warehouse.read`, a read-deny on a
      membership field blocks it server-side, a group detail carries no scope, permission or
      location field at all, and grouping a location needs authority over the location *and* over
      the grouping — each alone is 403; one primary group per date — a same-day second interval, a
      past date and an append reaching back into closed history are all 409, the unique
      `(warehouse_id, valid_from)` key holds against a direct write, re-assigning the group already
      in force writes nothing, a stale version or generation is 409, transit custody and a retired
      group are refused, and a group with members keeps its identity and its lifecycle; `A1` twice
      in one godown is 409 while `A1` in another godown is a different bin, a bin never changes
      parent, and a location's bins are retired before the location; a group id is not a location
      id at any of the five routes that take one; tenant isolation on all four tables with one
      company id present in two tenants. Ruff and mypy strict clean on every touched module.
      *Plan corrected against the implementation:* the reviewed reparent is
      `POST /warehouse-groups/{id}/reparent`, not `/move` — it moves the group's parent link, and
      `move` reads like the group itself relocates somewhere, which is exactly the "a group is a
      place" confusion this table exists to avoid. Bins are flat at `POST|GET /warehouse-bins` and
      `GET|PATCH /warehouse-bins/{id}` rather than nested under `/warehouses/{id}/bins`: the parent
      travels in the body, where the idempotency payload already covers it, the same shape as every
      other parent-scoped master; `activate` and `deactivate` were added for both new masters, since
      `MasterUpdate` cannot set `is_active`. There is no `warehouse.move` permission and a
      membership is not a rename, so grouping a location is the `assign` action, authorized by
      `warehouse.manage` over the location and `warehouse_group.manage` over the grouping, and it
      bumps the location's `row_version` even though no column on it changes.
      *Defect found while generalizing:* `move_edge` treated the last interval as the one in force.
      For a hierarchy those are the same thing, but a membership can be **cleared** — the open
      interval closes and nothing opens — and that location could then never be grouped again: the
      same group replayed as an unchanged no-op, a different one hit the "history is never
      rewritten" refusal. It now distinguishes the last interval from the last *open* one, so a
      cleared location has history and no group and may be assigned one again.
      `test_a_location_has_one_primary_group_on_any_date` pins both halves.
- [x] **Phase 5 — product location policies and replenishment bands.**
      `0139_create_item_warehouse_policy.py`, `0140_create_item_warehouse_permission.py`,
      `0141_create_item_replenishment_policy.py` — one DDL statement each, every `downgrade`
      present; `models/warehouse_policies.py`, `domain/warehouse_policy_composition.py` (pure,
      no framework, no database), `tasks/warehouse_policies.py`, `schemas/warehouse_policies.py`,
      `api/warehouse_policies.py` (the four routes below); three field-registry entries with their
      read/manage maps; audit contract regenerated for the three entities.
      A restriction's foreign key points at `item_warehouse_policy`'s scoped item key rather than
      at `item`, so "a stored per-location permission without a selection mode" is impossible in
      the schema instead of being a rule the writer has to keep. The product-wide band uses the nil
      UUID as `scope_warehouse_id` with a check tying it to a `NULL` `warehouse_id`, because MySQL
      counts NULLs in a unique index as distinct and "one product-wide band per product" would
      otherwise not be a constraint at all.
      Tests: `test_warehouse_composition.py` 17 passed (no database) and
      `test_warehouse_policies.py` 9 passed; re-run with the other warehouse suites plus
      `test_audit_contract.py`, `test_api.py` and `test_migrations.py`, 128 passed, 1 skipped.
      Covered: narrowing composes in **both orders** over HTTP — a product narrowed against a
      permissive location, then a narrower *location* revision published under it, and
      `effective_operations` shrinks while the stored product rows keep `row_version == 1`, so the
      intersection is computed and never stored; a widening attempt is 409 with nothing written,
      and the narrowed restatement of the same call is accepted; the missing row reads as the
      documented baseline rather than a 404 or a guessed deny; a SERVICE and a NON_STOCK goods
      product are refused at both endpoints with their own messages, and the baseline read still
      answers for them; a product activity default must point at a location that serves *that*
      operation (409), must be inside the product's own membership (422), and transit custody is
      never a default (422); a location still stocking a product cannot be retired — the default
      pointer and the membership each refuse separately, and retiring the membership clears the
      fence; bands are stated whole, land on the product's unit grid, keep `Decimal` in storage,
      and an off-grid, float, inverted or unsatisfiable band is refused at review time rather than
      on a purchase order; 401 unauthenticated on all four routes, 403 unpermitted, reader GET 200
      with PUT 403, an actor holding `item_warehouse_policy.read` but **not** `warehouse.read`
      cannot enumerate a company's locations through a product (403), wrong-company item 403,
      alien-tenant 404, unknown item 404, unknown location 404, stale generation 409, query
      parameters and nine malformed bodies 422; tenant isolation on all three tables; a read-denied
      `warehouse_id` omits entries whole, a read-denied location flag withholds
      `effective_operations`, and a write-deny on `selection_mode` is a 403 that leaves the stored
      row and its memberships untouched. Ruff and mypy strict clean on every touched module.
      *Plan corrected against the implementation:* the "optional role-specific SKU activity
      defaults" became plain product activity defaults — four nullable pointers on
      `item_warehouse_policy`, one per activity, resolved by the Phase 3 resolver. Roles are data
      and permissions are code (CLAUDE.md §6.13); a default keyed by role would have made a role
      row a term in *where stock moves*, and nothing in [catalog-warehouses](catalog-warehouses.md)
      §3's precedence chain has a level for it. The path parameter is `{object_id}`, not
      `{item_id}`: the shared command wrapper takes the object under change by that name, and a
      second spelling for the same thing at these two routes only would have needed a per-route
      adapter. Column names are spelled `safety_quantity` / `reorder_quantity` /
      `target_quantity` / `min_order_quantity` / `max_order_quantity` in full, per the platform
      convention rather than [schema](catalog-schema.md)'s `_qty` shorthand — that line and the
      stale "dated activity-default references" on `company_warehouse_configuration` are corrected
      in the same change.
- [x] **Phase 6 — policy releases, acknowledgements, the coordinated deactivation fence, bulk
      adapters and verification.**
      `0142_create_catalog_policy_release.py`, `0143_create_catalog_policy_consumer_ack.py` — one
      DDL statement each, both `downgrade`s present; `models/releases.py`,
      `domain/policy_release.py` (pure — no session, ORM, clock or quantity), `tasks/releases.py`,
      `tasks/acknowledgements.py`, `tasks/acknowledgement_worker.py`, `schemas/releases.py`,
      `schemas/acknowledgements.py`, `api/releases.py` (`GET|POST /policy-releases` and
      `GET /policy-releases/{object_id}`); `domain/stock_facts.py` behind the two places a new field
      name can enter Catalog (C7.11); eight bulk adapters in `tasks/bulk_registry.py` (C10.09);
      `events/audit_policy.py`'s `SOURCE_ENTITIES` and `events/evidence.py`'s `source_change` for an
      ingestion trail that has no actor to name; `domain/readiness.py` flipping
      `stock_location_definitions` to `implemented=True` while
      `SourceRequirement("warehouse_stock_and_location_guards", "billing")` stays unavailable, so a
      client reads definitions ready and enforcement pending.
      Publishing costs `warehouse.publish` on top of `warehouse.manage`; both reads cost
      `catalog.release.read`. The manifest is Catalog's, never the caller's — the body carries the
      date, the reason and the previewed expectations, and nothing that could narrow what the
      release covers — and every configured activity default is re-resolved through the chain a
      document uses, so a release cannot deliver a default that would fail weeks later in another
      service. No route writes an acknowledgement: those rows arrive only from a signed source
      event, `consumer` comes from the worker's verified source key rather than from the payload,
      and the platform inbox dedupes on `message_id`. Every field of both entities is registered
      `fixed` — a tenant field policy able to hide a release's digest or an acknowledgement's result
      would leave a reader unable to tell an enforced policy from a refused one, and the retirement
      fence reads the same row.
      Covered: a release delivers Catalog's own manifest and refuses a body that tries to state one;
      it takes force on its date and in the reviewed order, so a scheduled release is in the history
      and is not yet what a consumer should enforce; republishing an unchanged policy on the same
      date writes nothing, while a *rejected* predecessor is republishable because a refusal can be
      about transient consumer state; delivery is `PENDING` until Billing says it enforces that
      revision and `REJECTED` on a single veto; an acknowledgement naming a release, location or
      operation-policy revision Catalog never published is refused rather than stored; an older
      claim never regresses enforcement, and at one revision a claim may only weaken. The fence
      needs both halves — `warehouse.deactivate` (403), a published release (409), a clearance at
      all (503 naming `warehouse_stock_and_location_guards`), a refusal carrying its closed reason
      code (409 with `STOCK_ON_HAND`), a clearance about *that* location, and one granted against
      the release now in force, so retiring a location invalidates the clearances granted under the
      previous manifest. 401 unauthenticated on all three routes; 403 for `item.read` and for
      `warehouse.read` alone; reader GET 200 with POST 403; publish refused when either
      `warehouse.manage` or `warehouse.publish` is missing; wrong-company 403 both ways round;
      alien-tenant 404; unknown release 404; a `limit` or `as_of` query parameter 422; a command
      without an idempotency key 422; eight malformed bodies 422; a stale generation 409 with
      nothing written; tenant isolation on both tables with one company id present in two tenants.
      The reserved-fact refusal names the phrase rather than answering a boolean, matches whole word
      sequences only (`exception_handler` is not `on_hand`), names every offending import column at
      once, refuses a file by column before a row is interpreted, and holds on the product and
      classification custom-field create *and* edit paths and on a staged bulk record. A whole
      location network — groups, a location, a bin, a membership and a reparenting — imports through
      the dated native commands; a location policy and a product's stocking rules import by their
      own codes with no generation, source version or revision number anywhere in the file; a header
      naming a quantity, count sheet, transfer or trading party is refused at staging before a
      reviewer sees a plan; and a publish key withheld after staging fails that row, not the policy.
      Ruff and mypy strict clean on every touched module.
      *Plan corrected against the implementation:* the publication body is `PolicyReleaseInput`, not
      `ReleaseInput` — that name already belongs to the tax-governance publication body, and two
      different bodies competing for one name in the published OpenAPI document is a contract
      defect, not a naming preference. Releases are a company sub-collection at
      `/v1/companies/{company_id}/policy-releases` rather than anything nested under a location: a
      release is about the whole set, and hanging it off one location would have implied a location
      can be delivered on its own. The plan's "explicit pending state" for a fenced deactivation is
      **503 `source_unavailable`**, not a 409 — no clearance, a clearance about an older release and
      a clearance about an older operation policy all mean the next thing that has to happen is a
      consumer speaking again, and telling the caller to fix it would be telling them to fix
      something they do not control. Only a consumer's refusal is a 409, and it carries the closed
      reason code the caller can act on.
      *Defects found while implementing this phase:* the audit evidence for a release rendered every
      changed field as a bare `{"changed": True}` marker, because the evidence builder inferred "no
      prior state" from the audited action being named `create` — and a release's action is
      `publish`. It now derives that from an empty `before` (`creating=not before`), so the values
      an auditor reads a release *for* are in the trail. A bulk record's report carried no column
      name when the refusal came from `domain/` rather than from Pydantic: `RowFailureError.fields()`
      now also reads `PlatformError.extra["fields"]`, so a reviewer holding a five-thousand-row file
      is not left with `invalid_record` and no column. `WarehouseUpdate` rejected a patch that named
      only a state, because the country/state pairing rule sat on the update model; the rule moved to
      `LocatedFacts`, which the create and the stored-values merge share, so an update is still held
      to it — including clearing a country while a state remains — with the stored values in hand.
      Two more were found by the MySQL smoke and are not Catalog behaviour at all: the new tests'
      `emitted()` helpers scoped their outbox reads with `tenant_scope` alone, and `outbox` is
      deliberately exempt from the session filter (the poller reads across tenants), so on a shared
      database they collected every tenant's rows — SQLite-per-test hid it, and all six reads now
      state `tenant_id`; and `tools/mysql_smoke`'s reversibility roundtrip had been unrunnable since
      `0131` landed, since that revision refuses `downgrade` on purpose, so it now unwinds to a named
      floor above it and replays, which still exercises every one of 0132–0143 on the real engine.
      Two were gaps in this change's own verification rather than in its behaviour. The
      registry-against-real-columns check is driven by a hand-listed set of models, and the five
      entities Phases 5 and 6 registered — the three product-policy tables and the two release
      tables — were never added to it, so those entities' field names were the only ones in Catalog
      not being checked against a real column; supplying them made the check pass, which says the
      registry was right and only unverified. And `bulk_factories.run` gained a `version` parameter
      that it forwarded on every call, which silently overrode a test that patches `proofs` with a
      pinned checkpoint — it now forwards `version` and `denied` only when a caller states them, so
      a test still decides its own defaults.
      One pre-existing defect at HEAD was fixed in passing: `configure_family` let an empty option
      list be declared under an existing SKU selection, stranding that selection and reporting it
      later as a shape complaint instead of the conflict it is.
      *One pre-existing failure at HEAD is left in place:*
      `test_product_configuration_fail_closed::test_effective_sources_fail_closed_for_wrong_owners_and_broken_history`
      fails identically on a clean extraction of `2d091fd`. That commit widened
      `permitted_family_states` so item-level structural authoring is allowed under an `ACTIVE`
      family, and the assertion row expecting a barcode add to be refused there dates from
      `c752190`, when it was not. The behaviour reads deliberate — a draft SKU under a live family
      has to be completable — so the stale row is the thing to change, but that is a
      product-authoring call and is left for its owner. *Also fixed while closing this phase:* the
      `stable_product_source_clock` fixture pinned `catalog.tasks.actor_authorization.utcnow`
      but not `tests.test_actor_authorization.utcnow`, which is what its `proof()` helper reads to
      stamp `generated_at`. `validate_proof` compares `generated_at` to the pinned `now` with a +5 s
      freshness guard, so once real time advanced 5 s past fixture setup — trivial in a
      six-hour full run with coverage — every fresh call to `proof()` produced a proof that
      validated as future-dated and rejected as `IdentitySourceUnavailableError`. All four tests
      pass in isolation and were flagged in the earlier mixed-state run under different scheduling.
      Pinning `test_actor_authorization.utcnow` to the same `instant` closes it at the source.

## Decision log

- 2026-09-17: Agreed the six phases above; included `catalog_policy_release` /
  `catalog_policy_consumer_ack` so publication and deactivation have a real acknowledgement;
  chose current-state company defaults with audited history over dated revision rows; excluded
  `item_supplier_term` while Billing has no party projection.
- 2026-09-17: Provisioning is a command (`POST …/warehouse-configuration/bootstrap`, 201), and the
  configuration singleton has no `PATCH`. Its only writable part is the four activity defaults, and
  those change through the typed audited action so each pointer is checked against its own
  operation.
- 2026-09-17: An operation policy is published straight into force, never drafted. The revision's
  window is server-assigned and the predecessor is closed in the same transaction, which is what
  makes immutability structural instead of enforced by convention.
- 2026-09-17: A location's primary group changes through an `assign` action authorized by
  `warehouse.manage` **and** `warehouse_group.manage`, not a `warehouse.move` permission — there is
  none, and inventing one would have implied a location can be relocated. The group's own parent
  link moves through `POST /warehouse-groups/{id}/reparent`, and bins are flat at
  `/warehouse-bins` with the parent location in the body, like every other parent-scoped master.
- 2026-09-17: A product's activity defaults are four nullable pointers on its policy row, not
  role-specific ones. Permissions are code and roles are data; a default keyed by role would let a
  role row decide where stock moves, and §3's precedence chain — document choice, product default,
  company default — has no level for it.
- 2026-09-17: `source_version` on the configuration read is the live Identity checkpoint, matching
  every other Catalog read that hands back expectations; the provisioning checkpoint is reported
  separately as `provisioned_source_version`. Reporting the stored value under the expectation's
  name left the defaults action unsatisfiable once Identity moved.
- 2026-09-18: A location's `country_code` / `state_code` pair is validated in
  `tasks/reference_locations.py` against the ISO tables, not left to the composite foreign key. On
  MySQL a composite FK with a NULL member is not enforced, so an unknown `country_code` was accepted
  whenever `state_code` was NULL — the constraint stays for the paired case, and the application
  check covers the unpaired one. Identity's `company` and `company_address` carry the same shape and
  the same exposure; it is recorded here rather than changed, because fixing another service's
  validation inside this change would put a Catalog phase in the way of Identity's own review.
- 2026-09-18: An ISO code Catalog cannot use is **422**, not 409. A code that is unknown or inactive
  is a bad value in the request, not a conflict with stored state, and the caller fixes it the same
  way whichever it turns out to be.
- 2026-09-18: The country/state pairing rule lives on `LocatedFacts`, shared by `WarehouseCreate`
  and the stored-values merge, rather than on each request model. On the update path the rule needs
  the row's current values to be answerable at all — a patch naming only a state is valid if the
  stored country matches it — so the model that sees both is the only place it can be enforced
  without either rejecting valid patches or letting a country be cleared out from under a state.
- 2026-09-18: The policy publication body is `PolicyReleaseInput`. `ReleaseInput` was already the
  tax-governance publication body, and two unrelated request shapes competing for one schema name in
  the published OpenAPI document is a generated-client defect, not a style question.
- 2026-09-19: `stable_product_source_clock` pins `tests.test_actor_authorization.utcnow` in
  addition to `catalog.tasks.actor_authorization.utcnow`, so a proof minted by the shared `proof()`
  helper stamps `generated_at` from the same pinned instant `validate_proof` reads it against. The
  +5 s freshness guard used to fire once real time drifted past the fixture setup — a five-second
  drift is unremarkable in a six-hour full run with coverage — and the drift was silent because
  the two `utcnow` symbols live in different modules with the same name.
- 2026-09-18: `tools/mysql_smoke` covers the location definitions end to end, and its reversibility
  roundtrip unwinds to a named floor (`0131`) instead of `base`. `0131` refuses `downgrade` on
  purpose — the check constraint it replaced cannot be restored without deciding what happens to the
  measurements written under the new one — so an unconditional walk to `base` had been unrunnable
  since that revision landed. Stopping above it keeps every later revision's `downgrade` exercised
  on the real engine, which is the only place MySQL's DDL behaviour is observable at all.
