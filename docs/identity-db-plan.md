# `identity` — Database Build Plan

**Status:** Original 34-revision chain executed and previously verified on a real server.
Authorized Catalog source increment adds revisions 0035-0037 with matching models and offline/
SQLite verification; live roundtrip of those three revisions remains a release gate.
**Date:** 2026-09-03

Tenant directory increment (2026-10-20): revisions `0067`–`0071` each add one
Tenant index for prefix lookup, status filtering and stable name/slug/created sorting.
Every revision has an inverse downgrade. Native MySQL 9.6 upgrade, downgrade to
`0066`, and re-upgrade verified on a disposable schema. Local Identity is at `0071`.
See [tenant management](tenant-management.md).
**Tree:** `dbs/identity/` · **Models:** `apis/identity/src/identity/models/` · **Seeds:** `seeds/`
**Schema reference:** [identity-schema.md](identity-schema.md) — field-level detail is there, not repeated here
**Phases mirror:** [org-model.md](org-model.md) §6.5

37 revisions, 36 materialized tables; original 11 phases plus the source increment. `language` and `plan` stay deferred.

This document is the working order of execution. §1 and §2 are decisions that shape every revision — settle them before writing revision `0001`, because changing them later means rewriting the chain.

---

## 1. DB-level conventions

Beyond CLAUDE.md §4, these are the decisions that only surface once you actually write DDL.

### 1.1 One revision per table

Rule 4.8 says one DDL statement per revision, because MySQL DDL is atomic per statement but not transactional across statements, and a half-applied multi-statement revision desynchronizes the schema from `alembic_version`.

`CREATE TABLE` with its foreign keys, unique constraints, and secondary indexes **declared inline is one statement.** So:

- **One revision per table**, everything inline.
- A later `ALTER` is its own revision, one `ALTER` per revision.
- Never two `CREATE TABLE`s in one revision, even for a parent and its child.

This is what makes rule 4.8 workable rather than producing 200 revisions.

### 1.2 Revision naming — zero-padded sequential

Each service has its own linear chain with no branching, so a counter is more readable than a hash:

```ini
# dbs/identity/alembic.ini
file_template = %%(rev)s_%%(slug)s
```

`revision` is set by hand: `0001`, `0002`, … Files read `0008_create_company.py`. A gap or a duplicate is immediately visible in a directory listing, which a hash chain never is.

### 1.3 Constraint naming convention

MySQL auto-names indexes and constraints unpredictably, and an auto-named constraint cannot be reliably dropped in `downgrade`. Set the convention **once** on the shared `MetaData` before any model is written:

```python
NAMING_CONVENTION = {
    "ix":  "ix_%(table_name)s_%(column_0_N_name)s",
    "uq":  "uq_%(table_name)s_%(column_0_N_name)s",
    "fk":  "fk_%(table_name)s_%(column_0_name)s",
    "pk":  "pk_%(table_name)s",
    "ck":  "ck_%(table_name)s_%(constraint_name)s",
}
```

Retrofitting this after revision `0010` means an `ALTER` per constraint across ten tables. It is the single cheapest thing to get right on day one.

**When the generated name exceeds 64 characters, shorten it by hand — do not let MySQL truncate it.** MySQL caps an identifier at 64 characters and rejects a longer one at migration time, with no way to shorten it afterwards. `uq_company_tax_registration_company_id_tax_system_jurisdiction_code_valid_from` is 78. Shorten in this order, stopping as soon as the name fits, and keep the `uq_`/`ix_` prefix and table name intact:

1. **Drop `company_id`** when it is the leading column — the table prefix already says the row is company-owned.
2. **Drop a `_code` suffix** — `jurisdiction_code` becomes `jurisdiction`.
3. **Collapse `valid_from, valid_to` to `validity`** — the pair is one window.

Applied to Phase 4: `uq_company_tax_registration_tax_system_jurisdiction_valid_from` (61) and `ix_company_tax_registration_jurisdiction_validity` (49). The name no longer lists every column, so **the columns are asserted in a test** rather than read off the name — `test_the_unique_key_is_named_within_mariadbs_identifier_limit`, plus one per table asserting every declared name on it fits.

### 1.4 `tenant_id` carries no foreign key

Deliberate, and the reasoning matters because it looks like an omission:

1. **Ordering.** `outbox` ships in Phase 0, four phases before `tenant` exists. An FK would force `tenant` first, and `tenant` cannot be tested for isolation before the outbox writer exists ([org-model.md](org-model.md) §6.5).
2. **The enforcement is elsewhere.** Isolation is the session-level filter (CLAUDE.md §5.3) plus a two-tenant test per table. An FK proves the tenant *exists*; it does nothing about querying the wrong one, which is the actual risk.
3. A tenant is never hard-deleted, so cascade semantics are moot.
4. It keeps future partitioning by `tenant_id` open.

**Compensating control:** one test per tenant-scoped table asserting every `tenant_id` resolves to a real `tenant` row, run against the seeded fixture set. Cheap, and it catches the only thing the FK would have.

### 1.5 `*_by` columns carry no foreign key

`created_by`, `updated_by`, `deactivated_by`, `enabled_by`, `granted_by`, `revoked_by`, `closed_by` — all `BINARY(16) NULL`, no constraint.

The blocker is circular: `company` is Phase 3 and `user` is Phase 5, but `company.created_by` references a user while `user.default_company_id` references a company. One direction must give. `*_by` gives, because it is metadata on roughly sixty columns, while `user.default_company_id` is a real relationship worth constraining.

Nullable because system and migration writes have no actor. Users are anonymized rather than deleted (CLAUDE.md invariant 12), so a dangling reference is not a scenario.

`user.default_company_id`, `user.reporting_manager_id`, `company.parent_company_id`, `department.parent_id`, `department.head_user_id` **do** carry FKs.

### 1.6 Charset, engine, row format

`ENGINE=InnoDB`, `DEFAULT CHARSET=utf8mb4`, `COLLATE=utf8mb4_unicode_ci`, `ROW_FORMAT=DYNAMIC` — set explicitly on every `CREATE TABLE`, never inherited from the server default. A server rebuilt with a different default silently changes collation, and collation changes comparison semantics on every `VARCHAR` key.

**Index key length check.** `utf8mb4` is 4 bytes per character; InnoDB `DYNAMIC` caps a key at 3072 bytes. The widest composite uniques in the inventory:

| Constraint | Bytes | |
|---|---|---|
| `uq_user_tenant_id_email` — `BINARY(16)` + `VARCHAR(320)` | 1296 | ok |
| `uq_field_config_...` — 16 + 16 + `VARCHAR(80)` + `VARCHAR(120)` | 832 | ok |
| `uq_field_policy_...` — 48 + 16 + 320 + 480 + 40 + 48 + 16 | 968 | ok |

All clear, but the check is part of reviewing any revision that adds a `VARCHAR` to a composite key.

### 1.7 Index rule: `tenant_id` leads

Every query on a tenant-scoped table is filtered by `tenant_id` because the session filter injects it. So `tenant_id` is the **first column of every composite index** on those tables. An index that omits it is unusable by the filtered query and will be silently ignored by the optimizer.

**Two exceptions, both narrow, and each stated in a comment where it is taken.**

1. **An index supporting a foreign key must begin with the FK's own columns.** InnoDB requires a supporting index on the referencing side, and if none begins with those columns it *creates one*, named after the constraint. That index is invisible in the model and reads as autogenerate drift forever. So `ix_company_address_company_id_type` leads with `company_id`, not `tenant_id`.
2. **An index may lead with a column that functionally determines `tenant_id`.** `company_id` is one: a company belongs to exactly one tenant, so a scan of `(company_id, …)` is already tenant-confined and §1.7's concern — an index the filtered query cannot use — does not arise. This does not weaken isolation, which the session filter enforces regardless of which index is chosen.

Where the two agree, as they do on `company_address`, there is no tension to resolve.

**Unique constraints are not indexes for this purpose, and stay minimal.** `uq_company_feature_company_id_feature_key` deliberately omits `tenant_id`: prefixing it would let the same `(company_id, feature_key)` pair insert twice under a mismatched `tenant_id` — a *weaker* constraint, not a stronger one. Add `tenant_id` to a unique key only when it is genuinely part of the scope being made unique, as in `uq_company_tenant_id_code`, where two tenants must both be free to call their company `MAIN`.

---

## 2. The MySQL trap that changes five tables

**In MySQL, `NULL` values are distinct in a `UNIQUE` index.** Two rows with `NULL` in the same nullable column of a unique key are both accepted.

Five tables in the inventory use `NULL` in a unique key to mean "applies to everything":

| Table | Nullable column in a `UNIQUE` | What breaks |
|---|---|---|
| `role` | `tenant_id` (null = system role) | Two system roles with the same `key` both insert |
| `role_assignment` | `scope_id` (null = tenant scope) | Duplicate tenant-scope assignments of the same role |
| `field_policy` | `scope_id` (null = tenant scope) | Duplicate, and possibly contradictory, tenant-scope policies |
| `field_config` | `company_id` (null = tenant-wide) | **Two tenant-wide configs for one field.** The resolver picks arbitrarily |
| `custom_field_definition` | `company_id` (null = all companies) | Two tenant-wide definitions with the same `key` |

Every one of these is a correctness bug that a unique constraint was supposed to prevent, and none of them fails a naive test — you have to insert the duplicate deliberately to see it.

### Decision: a zero-UUID sentinel, not `NULL`

Those columns are `NOT NULL` and store `0x00000000000000000000000000000000` to mean "all". Named `SCOPE_ALL` in `libs/platform`; never exposed by an API, which continues to accept and return `null`.

Why this over the alternatives:

- **Generated column + unique on `COALESCE(...)`** — MySQL supports it, but CLAUDE.md §2 warns that `--autogenerate` does not see generated columns, so every future revision on those five tables becomes hand-written and easy to get wrong.
- **Partial / filtered unique index** — MySQL does not have them.
- **Application check under `SELECT ... FOR UPDATE`** — racy without the constraint, and it moves an integrity guarantee out of the database.

Cost accepted: `company_id = 0x00...` is a magic value at the SQL level. Mitigated by the named constant, a mapper-level translation, and a test per affected table asserting the duplicate is rejected.

`outbox.tenant_id` stays genuinely nullable — it is not part of any unique key.

---

## 3. Phase D0 — scaffolding, before revision `0001`

No tables. Ends with an empty chain that runs clean up and down.

| Deliverable | Detail |
|---|---|
| `dbs/identity/` tree | `alembic.ini` (§1.2 `file_template`), `env.py`, `versions/` |
| `env.py` path wiring | Imports `identity` models for autogenerate. **All path wiring lives here and nowhere else** (CLAUDE.md §4) |
| Async engine | `asyncmy`, `READ COMMITTED`, per-service DB grant — `identity` credentials reach no other schema |
| `MetaData` + naming convention | §1.3, in `libs/platform` |
| Base + mixins | `Id`, `Tenant`, `Audit`, `Deactivable`, `Effective` ([identity-schema.md](identity-schema.md) §0.2) |
| Type decorators | `UUIDv7` → `BINARY(16)`; `Money` and `Quantity` → `DECIMAL(19,4)` returning `Decimal`; `UtcDateTime` → `DATETIME(6)` |
| `SCOPE_ALL` constant | §2 |
| Testcontainers fixture | MySQL **9.6**, matching production. Never SQLite — collation, `DECIMAL` truncation and `NULL`-in-`UNIQUE` all differ |
| Migration round-trip test | `upgrade head` then `downgrade base` on an empty container, asserting a clean schema both ways |

**Exit:** `alembic upgrade head` and `downgrade base` both succeed on a fresh container. The `Money` type test asserts a value round-trips as `Decimal`, not `float`.

That last test is worth writing before any table exists. `asyncmy` returning `float` for a `DECIMAL` is silent, and it is easier to catch on one column now than to find in `billing` later.

---

## 4. Revisions, phase by phase

Order within a phase is dependency order — a table's FK targets must already exist.

### Phase 0 — platform mechanism

| Rev | Table | Note |
|---|---|---|
| `0001` | `outbox` | `INDEX (published_at, available_at)` is the poller's only query. `tenant_id` nullable, no FK |
| `0002` | `processed_message` | **PK `(consumer_name, message_id)`** — composite, not `message_id` alone |
| `0003` | `idempotency_key` | `UNIQUE (tenant_id, endpoint, key_value)`; `request_hash` present from the start |

**Exit:** outbox writer commits an event in the same transaction as a dummy row and a rollback leaves neither. Redelivery of one `message_id` to two consumer names processes twice; to one name, once.

### Phase 1 — reference tables

| Rev | Table | Note |
|---|---|---|
| `0004` | `currency` | No FK. First, because `country` points at it |
| `0005` | `country` | FK → `currency.code` |
| `0006` | `state` | FK → `country.code`, plus **`UNIQUE (country_code, code)`** — the composite FK target |

Then the seed: `seeds/reference/` — idempotent upsert on the natural key, run before any FK-bearing migration in a fresh environment.

**Exit:** inserting `country_code='IN'` with `state_code='US-CA'` is rejected by the database, not by validation. The three tables are proven absent from the session tenant filter via the §0.3 whitelist, with a test that a query returns rows with no tenant in context.

### Phase 2 — tenant

| Rev | Table | Note |
|---|---|---|
| `0007` | `tenant` | `UNIQUE (slug)`. No `tenant_id` — it is the tenant |

**Exit:** two-tenant isolation test pattern established here and reused verbatim for every later table.

### Phase 3 — company core

| Rev | Table | Note |
|---|---|---|
| `0008` | `company` | The largest table. **Composite FK `(country_code, state_code)`**; `print_template_id` is `BINARY(16)` with no FK — the target lives outside `identity` |
| `0009` | `company_address` | Composite FK too |
| `0010` | `company_feature` | `UNIQUE (company_id, feature_key)` |

No migration for `FIELD_REGISTRY` — it is code ([identity-schema.md](identity-schema.md) §6.2).

**Exit:** `amount_precision`, `quantity_precision`, `base_currency`, `state_code`, `code`, fiscal start and `rounding_mode` all reject a change once `first_posted_at` is set, **for every actor including platform admin**. Feature dependency resolution and the `locks_on` ratchet tested. `GET /entities/identity.company/field-set` returns registry-only output and the web form renders from it.

> **The `field-set` endpoint is deferred to the API phase**, along with `company`'s Pydantic schemas and the regenerated TS client: `identity` has no FastAPI app yet, so there is nothing for a route to hang from. The two `domain/` halves of this exit criterion are done and tested with no database at all — `company_immutability` and `company_features`, each asserted to take no actor parameter. `JURISDICTION_PROFILES` ([company.md](company.md) §3) is deferred to Phase 4, which is where the profile is first read; `cash_receipt_limit`'s "lowerable, never raisable" rule ([company.md](company.md) §5.5) waits on it.

### Phase 4 — statutory and licences

| Rev | Table | Note |
|---|---|---|
| `0011` | `company_tax_registration` | `UNIQUE (company_id, tax_system, jurisdiction_code, valid_from)` — named `uq_company_tax_registration_tax_system_jurisdiction_valid_from` under §1.3; FK → `company_address` |
| `0012` | `company_statutory_id` | `value` nullable — restricted kinds store only `value_last4`. **`value_last4` is NOT NULL**, see below |
| `0013` | `company_licence` | `INDEX (valid_to)` for the expiry sweep |

**Exit:** `posting_date` resolution returns the registration valid on that date; overlaps rejected at write; **a gap returns `None` and never falls back**. A full AADHAAR submitted to the API is proven absent from the table, the logs, the response, and an export.

**Status: done, with the API halves deferred.** Resolution, overlap rejection and the gap rule are tested with no database at all (`libs/platform/tests/test_statutory.py`), and the seam between each table and the resolver is tested against persisted rows so a column renamed on one side cannot leave both suites green. The AADHAAR criterion is met **at the table** — `test_a_restricted_identifier_is_stored_without_its_full_value` reads the column back, and `test_the_full_restricted_number_is_absent_from_every_column` asserts it across the whole row rather than the one column it belongs in. The **logs, response and export** thirds are deferred with the rest of the API surface: there is no route to submit to and no logging middleware to redact yet. They belong to the API phase and to the export path in `reports`, and the single chokepoint they will both go through — `prepare_statutory_value` — is at 100% coverage now.

Two decisions taken here that the schema doc did not anticipate:

- **`company_statutory_id.value_last4` is NOT NULL for every kind**, not only restricted ones ([identity-schema.md](identity-schema.md) §3.7 said nullable). It is the last column of `uq_company_statutory_id_company_id_kind_value_last4`, and MySQL treats NULLs inside a unique key as distinct (§2) — left NULL for unrestricted kinds, a company could store the same PAN twice and the key would enforce nothing for exactly the kinds that print on invoices.
- **`company_tax_registration.jurisdiction_code` carries no foreign key.** It holds a *state* code in India and a *country* code in the UK, and no single target covers both. The compensating control is `assert_jurisdiction_code_allowed`, which **fails closed**: an empty subdivision set refuses every Indian code rather than skipping the check.

The §1.4 compensating control (`tenant_id` has no FK, so one test per tenant-scoped table asserts every value resolves to a real `tenant`) was present only on `company`. It is now on all six.

### Phase 5 — user and authorization

| Rev | Table | Note |
|---|---|---|
| `0014` | `user` | `UNIQUE (tenant_id, email)`, `UNIQUE (authentik_sub)`. `default_department_id` added **without** FK — target is Phase 6 |
| `0015` | `user_identity` | `UNIQUE (provider, provider_sub)` |
| `0016` | `role` | `tenant_id` uses `SCOPE_ALL`, not `NULL` (§2). `UNIQUE (tenant_id, key)` |
| `0017` | `role_permission` | `permission_key` is `VARCHAR`, **no FK** — permissions are code |
| `0018` | `role_assignment` | `scope_id` uses `SCOPE_ALL`. `INDEX (tenant_id, subject_type, subject_id)` is the hot path |

Then the seed: `seeds/roles/` — the twelve system roles, idempotent upsert on `(SCOPE_ALL, key)`.

**Exit:** per endpoint — 401 unauthenticated, 403 permitted-but-wrong-company, 422 invalid. All three escalation guards tested. Boot **fails** on a seeded `permission_key` absent from the code catalogue. The session filter's `role` exception (`tenant_id = :current OR tenant_id = SCOPE_ALL`) has its own test proving system roles are visible and another tenant's roles are not.

### Phase 6 — structure and groups

| Rev | Table | Note |
|---|---|---|
| `0019` | `department` | Self FK; `INDEX (tenant_id, path)` |
| `0020` | *ALTER* | Add FK `user.default_department_id` → `department.id`. The one deferred constraint, resolved |
| `0021` | `user_group` | Flat — no `parent_id` |
| `0022` | `user_group_member` | `INDEX (user_id)` — resolution reads this direction |
| `0023` | `membership` | Separate from `role_assignment` by design |

**Exit:** ancestor-or-self scope resolution correct at all three scopes. `path` maintained correctly across a reparent. A user with a membership and no role assignment can reach nothing.

### Phase 7 — remaining children

| Rev | Table |
|---|---|
| `0024` | `company_contact` |
| `0025` | `company_bank_account` |
| `0026` | `company_document` |
| `0027` | `user_notification_preference` |
| `0028` | `user_api_token` |

**Exit:** `account_number` and `iban` proven redacted in logs. A raw token is proven never stored — only `token_hash` and `token_prefix`. A token's `scopes` cannot widen the user's resolved permissions.

### Phase 8 — impersonation and visibility

| Rev | Table | Note |
|---|---|---|
| `0029` | `impersonation_session` | `INDEX (ended_at, expires_at)` for the sweeper |

**Exit:** start and end both emit audit events. An expired session is refused even if `ended_at` is still null. An `unlisted` company still appears in audit rows and in a tenant-wide report for an authorized reader.

### Phase 9 — field policy

| Rev | Table | Note |
|---|---|---|
| `0030` | `field_policy` | `scope_id` uses `SCOPE_ALL` (§2) |

**Exit:** `assert_fields_writable` operates on the **diff against current state**, not on payload presence — sending an unchanged value for a denied field is allowed; changing it is not. Read-denies hold in exports and reports.

### Phase 10 — extensibility

| Rev | Table | Note |
|---|---|---|
| `0031` | `custom_field_definition` | `company_id` uses `SCOPE_ALL` |
| `0032` | `field_config` | `company_id` uses `SCOPE_ALL`; FK → `custom_field_definition` |
| `0033` | `custom_field_value_index` | **PK `(entity_type, entity_id, definition_id)`** — natural key, no surrogate |
| `0034` | `custom_field_sequence` | `UNIQUE (definition_id, company_id, cycle_key)` |

**Exit:** a non-`hideable` field rejects `is_visible = false`; requiredness cannot be loosened; an unknown `field_key` **fails the boot**. A hidden field is still accepted by the API and still present in exports. Rule-tree fixtures green in Python and both clients. Custom-field values proven unreadable by any pricing, tax, posting or approval path (CLAUDE.md invariant 14).

---

## 5. Seeds

In `seeds/`, never in a migration (CLAUDE.md §2). Idempotent upsert on the natural key, re-runnable on every deploy.

| Seed | Phase | Content |
|---|---|---|
| `seeds/reference/` | 1 | `currency`, `country`, `state` from `libs/platform` static data |
| `seeds/roles/` | 5 | Twelve system roles + `role_permission`, keyed `(SCOPE_ALL, key)` |

Role keys are immutable once shipped; a rename is a new role plus a migration of assignments. A seeded `permission_key` not in the code catalogue is a **boot failure**, not a warning ([roles-permissions.md](roles-permissions.md) §6).

---

## 6. Per-revision review checklist

Every revision, before it lands. This is CLAUDE.md §8 narrowed to DDL.

- [ ] One DDL statement (§1.1)
- [ ] Read line by line — `--autogenerate` misses `VARCHAR` length, index renames, collation, partitioning, generated columns
- [ ] `ENGINE`, `CHARSET`, `COLLATE`, `ROW_FORMAT` explicit (§1.6)
- [ ] Composite index keys under 3072 bytes (§1.6)
- [ ] `tenant_id` leads every composite index on a tenant-scoped table (§1.7)
- [ ] No `NULL` inside a `UNIQUE` key — `SCOPE_ALL` instead (§2)
- [ ] Money **and quantity** columns are `DECIMAL(19,4)`, each money column with its currency sibling
- [ ] Timestamps `DATETIME(6)` suffixed `_at`; business dates `DATE` suffixed `_date` / `_on`
- [ ] Enums are `VARCHAR`, never MySQL `ENUM`
- [ ] `downgrade` present and **executed** in the round-trip test, or a comment saying why not
- [ ] Model, Pydantic schema, test factory and regenerated TS client updated in the same change (CLAUDE.md §2)
- [ ] Two-tenant isolation test added for the new table
- [ ] No seed data in the revision

---

## 7. What is not in this plan

- **`language` and `plan`** — deferred. `tenant.plan_id` stays nullable, unconstrained.
- **`fiscal_year` / `fiscal_period`** — owned by `billing`. `identity` holds only the calendar *configuration* on `company` ([fiscal-year.md](fiscal-year.md) §1.1).
- **`document_sequence`** — `billing`.
- **Partitioning** — `outbox` and `impersonation_session` are the first candidates, but not before real volume. Partitioning by `tenant_id` stays open because §1.4 declined the FK.
- **The `audit` service's tables** — separate database, separate chain, Phase 2 of the service build order.

---

## 8. Open questions

- [x] **`department.path` separator and depth cap — RESOLVED.** Materialized path of
  UUID-hex segments, `/`-delimited with a leading and trailing slash
  (`/<id>/<id>/`), so descendant lookup is an indexed `LIKE '/a/b/%'` and
  ancestor-or-self is a prefix test. **Depth capped at 6 levels**, enforced in
  `identity/domain/department_tree` (`MAX_DEPTH`) on create and reparent — a cost-centre
  tree deeper than that is past what the structure models, and it bounds both the
  `VARCHAR(500)` key and the reparent rewrite. (Decided during execution; org-model §5
  keeps departments a structure, not an approval chain.)
- [ ] Retention windows for `outbox`, `processed_message`, `idempotency_key` — drives whether they need partitioning at `CREATE` time rather than an `ALTER` later
- [x] **Does `field_config` need company scope at launch — RESOLVED: tenant-only.** The
  `company_id` column stores the `SCOPE_ALL` sentinel and structurally supports company
  overrides, but only `field_config.manage` at tenant scope is granted at launch, so all
  field layout is tenant-wide. Company-scoped overrides need only a future permission
  grant, not a migration. (Decided during execution.)
- [ ] Is `plan` in scope for v1 — unblocks `tenant.plan_id`'s FK

### Decision log (execution)

- **2026-09-11** — Executed phases D0–P10 (all 34 revisions) plus the deferred API layer
  for phases 2–6. Resolved the two schema-shaping open questions above. Added
  `AuthenticationRequiredError` (401) to `libs/platform` (v0.2.0) so the HTTP boundary can
  distinguish "who are you" (401) from "you may not" (403). Phase-5 test
  `test_default_department_id_carries_no_foreign_key_yet` was rewritten (→
  `..._now_carries_the_deferred_foreign_key`) because revision 0020 adds that FK, exactly
  as its docstring predicted. `custom_field_value_index.value_date` (DATETIME(6), a
  polymorphic value column) is exempted from the `_date`→DATE naming check, documented in
  the revision and the test.


## Authorized Catalog source increment (2026-09-11)

| Revision | Table | Purpose |
|---|---|---|
| 0035 | catalog_source_generation | Tenant-wide monotonic generation and serialization lock shared by participating native writes and snapshot creation. |
| 0036 | catalog_source_snapshot | Immutable company-scoped manifest, request identity, source version and freshness lease; unique tenant/company/request. |
| 0037 | catalog_source_page | Bounded immutable snapshot pages with content digests and same-company composite foreign key. |

Every revision contains one CREATE and one DROP; no seeds or source business tables are copied.
Models, source API and publication remain Identity-owned. Each new table has non-vacuous
two-tenant isolation tests. Snapshot read/signing verifies persisted structure, identity and scope.
See [source operations](catalog-source-operations.md).

Decision 2026-09-11: user authorized these minimal source artifacts to unblock Catalog. Original
historical live migration evidence does not imply these new revisions were applied to a live server.

- **2026-09-11** ? Added revisions 0038?0042: three seeded reference tables, one company
  ALTER with optional category/store-format FKs and the parent composite key, and a tenant-scoped
  role binding table. Each revision has one DDL per direction. Seeds run after migration;
  existing classifications default to null/empty. See [company-classification.md](company-classification.md).

- **2026-09-11** ? Explicit Alembic configuration URLs now override the application
  environment URL, so disposable migration tests cannot accidentally inherit that target.

- **2026-09-11** ? `identity.install` now applies migrations then atomically loads all
  Identity default catalogues. Online/Store roles and Online store format are seeded values;
  no new DDL revision is required. Installation is safe to rerun.

- **2026-09-11** ? Added the Salesperson system role through the existing installation/role
  seed. It uses existing permission keys and tables, so no DDL migration is required.


## 2026-09-12 bug-fix migrations

0043 adds generated affiliation and active-primary uniqueness keys. 0044?0046 add
owner keys to users, departments and company addresses. 0047?0050 add composite owner
FKs and the default-department/default-company check. Run the read-only integrity
inventory before deploying these revisions. Duplicate/invalid historical data blocks
migration rather than being rewritten. See [implementation and validation](identity-bug-fix-results-2026-09-12.md).


## Identity gap migrations (2026-09-12)

| Revision | Contract |
| --- | --- |
| 0051 | Nullable UTC `user.tokens_valid_after_at`; direct sessions/proofs reject earlier authentication. |
| 0052 | `user_invitation` durable pending/accepted/cancelled/expired workflow, one pending invitation per tenant user. |
| 0053 | `user_notification_preference.source_version` for ordered consumer projection. |
| 0054 | Bank ciphertext, key ID and account/IBAN last-four fields; legacy plaintext cleared by audited rotation. |
| 0055 | `posting_reservation` durable company/operation freeze, scoped actor FK, terminal status/history. |
| 0056 | Binary collation for custom text indexes; case folding follows the field contract. |
| 0057 | Company document storage state, SHA-256, immutable Blob snapshot, upload expiry/finalization times and composite tenant/company ownership. |

Each revision performs one DDL per direction. Data-protection guards reject downgrades
that would lose encrypted bank details, posting history or Azure references. Models,
factories and generated clients change together. Real MySQL 9.6 migration/drift/race
verification through 0057 passed (483 checks). See [operations](identity-gap-operations.md)
for deployment, recovery and explicit live dependency gates.

Decision: Azure Blob was selected by the user on 2026-09-12; old document keys remain
legacy until a reviewed verified import. API tokens use explicit permission-key/company
scope objects and live owner-authority intersection, resolving the earlier token-shape question.


## Tax registration class migrations (2026-10-05)

[tax-accounting-plan](tax-accounting-plan.md) Phase 1 follow-up; [company](company.md) §4.2.

| Revision | Contract |
| --- | --- |
| 0060 | `company_tax_registration.registration_class VARCHAR(20) NOT NULL DEFAULT 'supplier'` (instant add). |
| 0061 | Data-only backfill from the `billing_platform.tax.REGIMES` catalogue (`isd`, `tds_deductor`, `ecommerce_operator` → `tcs_collector`); parameterized `UPDATE`s, no DDL; no downgrade needed (derived values, idempotent). |
| 0062 | Drop the `'supplier'` default so no insert classifies a row by omission; `domain/` sets the class on create. |
| 0063 | Swap the unique key atomically to `uq_company_tax_registration_class_jurisdiction_valid_from (company_id, tax_system, registration_class, jurisdiction_code, valid_from)`; downgrade refuses while same-day rows of different classes exist. |

Chain-shape and offline (`--sql`) rendering checked; the MySQL round-trip/drift tests were
skipped where no container runtime was available and must run before deployment.


## First-run setup increment ? 2026-10-20

Revision `0066` performs one `CREATE TABLE platform_installation` statement; its
explicit downgrade drops only that table. The installation seed runs after migrations,
never inside DDL or API startup. This is platform control metadata, deliberately outside
TenantMixin, with no general HTTP CRUD/reset surface. Existing tenants disable first-run
provisioning. Completion serializes on this pre-seeded row and commits with the created
user/tenant/role and transactional outbox evidence. See [platform-setup.md](platform-setup.md).

## Regional reference increment (2026-10-20)

Revision `0072` creates the shared `language` shape and `0073` creates `timezone`.
Each revision contains one atomic CREATE and one inverse DROP, with InnoDB,
utf8mb4_unicode_ci and DYNAMIC row format. No content is placed in migrations.
Identity installation seeds ISO language and pinned IANA timezone data in its
default transaction; withdrawn codes remain inactive. Tables have natural keys
and no tenant scope. APIs bound each active list to 1,000 choices and reject
unsupported codes on setup, provisioning and tenant default updates.

Decision: the user requested database/API-bound regional selectors. Materialize
these catalogues in Identity and use them across tenant administration and setup.

## Tenant default state (2026-10-21)

Revisions 0074?0076 add `tenant.default_state_code VARCHAR(6) NULL`, an explicit
`(default_country_code, default_state_code)` index and the composite foreign key
into the existing state table. Each revision issues one DDL per direction and
has its inverse. Existing rows retain NULL. Reference content remains in the
re-runnable installation seed. Use migration credentials; the runtime user has
no ALTER permission. No sequence or table is added for generated workspace IDs.

Decision: the user requested Country and State only during tenant creation.
Persist that state rather than collecting a value that would be discarded.

## Reference choice cache generation (2026-10-21)

Revision 0080 creates `reference_cache_generation` with UUIDv7 id/token and unique
global key, one CREATE statement and one inverse DROP. No seed data is in DDL.
Identity installation seeds its initial row; reference writes rotate its token
atomically. Country/state/currency/language/timezone/provenance/checkpoint data
are preserved. Rollback restores the previous token. Cached choice projections
expire via Redis TTL; permission checks and financial validation do not use them.

Decision: shared reference dropdowns may use Redis; the committed database token
provides invalidation across API processes, seed runs and service acknowledgements.

## Public account review (2026-10-21)

Revisions 0081 and 0082 each create one table with inline keys and an inverse DROP:
`account_review` and `account_review_command`. Models, factories, strict schemas and
generated clients accompany them. Deploy both before enabling the provider adapter;
run the existing system-role seed to add the two platform-only permissions without
replacing tenant assignments. A focused native round-trip test returns to 0080,
checks both tables absent and reapplies head. Older irreversible revisions are
outside this downgrade boundary.
Revision 0083 adds the tenant/created_at/id index needed for the default directory
sort without a status filter, as one CREATE INDEX with an inverse DROP INDEX.
Revisions 0086 and 0087 each add one nullable VARCHAR(200) workspace column to
the review projection and command, respectively. Each has one DDL statement and
an inverse downgrade. Deploy both with the matching model and generated client
before enabling automatic tenant creation on approval.

Decision: retain bounded searchable registration metadata and durable intent in
Identity; Authentik remains the credential and activation authority.

## Platform fees and pricing (2026-10-23)

0084 creates global `platform_price`; 0085 creates immutable `platform_price_revision`.
Each revision has one CREATE TABLE with inline constraints/indexes and one inverse DROP.
Deploy both, then run Identity installation to insert the nine default commercial offerings.
Repeat installation preserves administrator edits and deleted codes. Neither migration
contains seed data or assigns tenant plans. See [pricing decisions and fields](platform-pricing.md).
Native verification upgrades from an empty MySQL 9.6 schema, reinstalls, compares schema,
and exercises only the reversible 0085→0083→0085 boundary. Earlier deliberate irreversible
migrations are preserved.
