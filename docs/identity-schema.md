# `identity` — Table & Field Reference

**Status:** Original schema implemented; authorized source-artifact increment added 2026-09-11.
**Date:** 2026-09-03

GSTR-1 increment (2026-11-02): revision 0097 adds
`company_gst_outward_profile`, scoped to company and its eligible Indian GSTIN.
It retains prior-financial-year aggregate turnover as DECIMAL(19,4), INR,
explicit Rule 14A applicability, effective whole-month boundaries, retained
reference and SHA-256 proof, and standard identity/audit fields. The scoped
registration/start tuple is unique. Overlaps are rejected under the company
lock; history permits only one exclusive close. Setup metadata and paginated
profile APIs enforce tax-registration management authority. Signed Accounting
context carries the dated profile; GSTR-1 requires a fresh profile for each GST
financial year. See [GSTR-1 delivery](gstr1-delivery.md).

GSTR-3B increment (2026-11-02): revision 0096 adds
company_gst_filing_preference. Standard Id/Tenant/Effective/Audit mixins supply
UUIDv7 id, tenant_id, valid_from/valid_to and actor/timestamp audit columns.
company_id references company; registration_id references
company_tax_registration; frequency is VARCHAR(10), MONTHLY or QRMP.
The tenant/company/registration/start tuple is unique and frequency has a
database check constraint. The owner API locks the active company, requires the
same-company eligible GST registration, refuses overlapping periods and permits
only one immutable-history close operation. Signed company context carries this
dated history. Native setup metadata provides current state/regime choices and
the tax-registration field schema to the Company configuration screen.
See [GSTR-3B delivery](gstr3b-delivery.md).

Tenant directory increment (2026-10-20): revisions `0067`–`0071` add indexes
`ix_tenant_name_id`, `ix_tenant_status_name_id`, `ix_tenant_created_id`,
`ix_tenant_status_created_id`, and `ix_tenant_status_slug_id`, matching Tenant's
model declarations. No field or lifecycle changes. See [tenant management](tenant-management.md).
**Service:** `apis/identity` · **Migrations:** `dbs/identity/` · **Seeds:** `seeds/`
**Related:** [org-model.md](org-model.md) §6 (inventory & phases) · [company.md](company.md) · [company-features.md](company-features.md) · [roles-permissions.md](roles-permissions.md) · [custom-fields.md](custom-fields.md) · [field-permissions.md](field-permissions.md)

The original inventory deferred language and plan. Language is now materialized
by revision `0072`; `0073` adds the timezone catalogue. Plan remains deferred.
This is the field-level reference; design rationale lives in the related docs.

## Regional reference tables (2026-10-20)

`language` reuses the shared ISO 639-1 model: `code CHAR(2)` primary key,
`iso3 CHAR(3)` unique, `name VARCHAR(128)`, nullable `native_name VARCHAR(128)`,
and non-null `is_active BOOL`. `timezone` has `code VARCHAR(64)` primary key,
`name VARCHAR(128)` and non-null `is_active BOOL`. Both are global reference
catalogues without tenant IDs; natural keys are an explicit reference exception.
Timezone is Identity's materialization of the pinned shared tzdata source.
Installation seeds preserve withdrawn rows as inactive. No reference CRUD is exposed.
Tenant creation/editing, onboarding and setup read bounded active choices from the
existing gated APIs and validate every selected code against local tables.

Decision amendment: materialize language and timezone for the user's requested
selectors; tenant/setup language selection stores a two-letter ISO code. Existing
stored settings are retained; UI translation remains separate.

---

## Local authentication provider (2026-10-31)

Revisions `0090`–`0095`, one `CREATE TABLE` each, add the tables of the local provider
([local-auth](local-auth.md) §5): `local_identity` (`seq` INT auto-increment primary key — the
account-review `provider_id` — a UUID `uid`, a 64-hex `sub`, unique case-insensitive `email` and
`username`, `status` `pending`/`active`/`disabled`, `email_verified_at`), `local_credential`
(argon2id `password_hash`, `failed_attempts`, `lock_ends_at`), `local_recovery_token`,
`local_signing_key` (RS256; the private JWK only as AES-256-GCM ciphertext bound to its `kid`),
`local_authorization` (a hashed request id that becomes a hashed one-use code) and
`local_refresh_token` (hashed, rotated through `family_id`). Every datetime is `DATETIME(6)`
named `*_at`. No password, code, token or private key is stored in the clear; tokens, codes and
request ids are kept only as their SHA-256.

## First-run installation control (2026-10-20)

Revision `0066` adds `platform_installation`, a singleton installation-control record
outside tenant business-data filtering. `id` is UUIDv7/BINARY(16); unique `key`
VARCHAR(16) is `platform`. Nullable `name` VARCHAR(200), `public_url` VARCHAR(2048),
`completed_at` DATETIME(6), `tenant_id`/`administrator_id` BINARY(16),
`administrator_subject` VARCHAR(64) and `request_hash` VARCHAR(64) hold completion
metadata. No passwords, access/refresh tokens or setup keys are stored in this table.
The application installation seed creates the row; setup locks it and commits its
completion alongside tenant/user/role and audit outbox records. No browser reset exists.
See [platform-setup.md](platform-setup.md) for boundaries and recovery.

## 0. Conventions

### 0.1 Types

| Concern | Type | Rule |
|---|---|---|
| Primary key | `BINARY(16)` | UUIDv7. Time-ordered, so it clusters well on InnoDB |
| Reference PK | `CHAR(2)` / `VARCHAR(6)` / `CHAR(3)` | Natural ISO code — the one UUIDv7 exception (CLAUDE.md §4) |
| Money | `DECIMAL(19,4)` | Always with a sibling currency column. Never `FLOAT` |
| Quantity | `DECIMAL(19,4)` | Same fixed scale as money. Never narrowed per column |
| Timestamp | `DATETIME(6)` | UTC. Suffix `_at`. Microsecond precision for event ordering |
| Business date | `DATE` | Suffix `_date` or `_on`. Never a datetime |
| Enum | `VARCHAR(n)` | App-validated. Never MySQL `ENUM` — altering one rebuilds the table |
| Boolean | `TINYINT(1)` | MariaDB has no native bool |
| Structured | `JSON` | Not indexable on MariaDB (rule 4.7) — see `custom_field_value_index` |
| Email | `VARCHAR(320)` | 64 local + `@` + 255 domain |

Charset `utf8mb4` / `utf8mb4_unicode_ci`, engine InnoDB, row format `DYNAMIC` throughout.

### 0.2 Column mixins

Defined once in `libs/platform` and composed, rather than restated per table. Field grids below list **only table-specific columns**; the mixins each table uses are named in its header.

**`Id`**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `id` | `BINARY(16)` | no | UUIDv7 primary key |

**`Tenant`** — every tenant-scoped table. Subject to the session-level filter (CLAUDE.md §5.3).

| Column | Type | Null | Purpose |
|---|---|---|---|
| `tenant_id` | `BINARY(16)` | no | Isolation boundary. First column of nearly every index |

**`SelfTenant`** — `tenant` only. Includes `Id`; adds no column. Its `id` **is** the tenant id, so the session filter matches it on `id` instead of on `tenant_id`. Without it, the one table that defines the isolation boundary would be the only table outside it.

**`Audit`** — who and when, on every mutable table.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `created_at` | `DATETIME(6)` | no | Row creation, UTC |
| `created_by` | `BINARY(16)` | yes | Actor `user_id`; null when written by `system` |
| `updated_at` | `DATETIME(6)` | no | Last mutation, UTC |
| `updated_by` | `BINARY(16)` | yes | Last mutating actor |

**`Deactivable`** — the `is_active` form of rule 4.12. Never combined with a `status` column.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `is_active` | `TINYINT(1)` | no | `false` = not selectable for new records. **Not** hidden from history |
| `deactivated_at` | `DATETIME(6)` | yes | When |
| `deactivated_by` | `BINARY(16)` | yes | By whom |

**`Effective`** — the date-validity form of rule 4.12, for anything affecting a computed amount.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `valid_from` | `DATE` | no | Inclusive start |
| `valid_to` | `DATE` | yes | Inclusive end; null = open-ended |

### 0.3 Tenant-filter exemptions

These tables sit outside the session filter and are **explicitly whitelisted** in the shared library (`TENANT_FILTER_EXEMPT`) — never exempt by accident of omission:

| Table | Why |
|---|---|
| `country` · `state` · `currency` · `language` | ISO reference data, no `tenant_id`, natural-code PK |
| `processed_message` | Infrastructure dedupe; a message may arrive before a tenant is resolved |
| `outbox` | `tenant_id` is nullable for platform-level events, and the poller reads across every tenant by design — it runs under `unfiltered()` |
| `local_identity` · `local_credential` · `local_recovery_token` · `local_signing_key` · `local_authorization` · `local_refresh_token` | Installation-global state of the local authentication provider: a sign-up exists before any tenant does. Reached only through `identity/local_auth` ([local-auth](local-auth.md) §5); no tenant-scoped route selects from them |

`tenant` is **not** on this list. It has no `tenant_id`, but it is filtered on `id` through the `SelfTenant` mixin — see §0.2.

Every other table is filtered. A new table without `tenant_id` is a review failure unless it is added to that whitelist deliberately, with its reason. `test_every_table_is_tenant_scoped_or_explicitly_exempt` and `test_exemption_list_matches_the_documented_set` in `libs/platform/tests/test_conventions.py` hold this list and this doc to each other.

**One statement shape the filter cannot reach, and it raises.** `with_loader_criteria` attaches to the ORM entities in a statement's columns clause. `select(func.count()).select_from(Invoice)` has none, so the criteria is silently dropped and the count returns every tenant's rows. The library raises `UnfilterableStatementError` on that shape rather than allowing it; the fix is to name the column — `select(func.count(Invoice.id))`. Joins and `EXISTS` subqueries are reached and are unaffected. This matters because every paginated list endpoint needs a total, which is exactly where the entity-less form gets written.

### 0.4 Numeric scale and display config

**Storage scale is fixed at four decimals for every amount and every quantity, in every service and every replica.** It is not a per-column choice. MariaDB rounds to a narrower target scale on insert without raising, so one `DECIMAL(19,2)` column downstream loses data silently and surfaces later as a subledger that will not tie.

`company.amount_precision` and `company.quantity_precision` (0–4) are **presentation/rounding configuration, not storage scale**. amount_precision rounds monetary totals under rounding_mode; quantity_precision supplies a presentation default and never rounds stock conversions. A company at amount_precision=2 stores 1234.5000 and shows 1,234.50. Both remain [IMM]. The planned [Product Configuration](catalog-product-configuration.md) owns separate quantity/rate entry precision and preserves exact transaction values; it adds no duplicate writable Identity precision fields.

**Amount and date display formats are server-resolved config, never client locale defaults.** `identity` exposes the resolved config — user preference over company default over tenant default — and one shared formatter per platform consumes it (`libs/platform` for Python; the generated client package for web and mobile), against a shared fixture set including a non-`en` locale. Three independent format calls produce three renderings of the same invoice; this is what prevents that. Full contract in [company.md](company.md) §4.5.

### 0.5 Notation

**`[IMM]`** = immutable once the company has any posted document ([company.md](company.md) §5.2).
**`[CODE]`** = value comes from a code-defined catalogue in `libs/platform`, not user data.

---

## 1. Reference tables

Seeded from `libs/platform` static data ([tech-stack.md](tech-stack.md) § *Reference tables*). No `tenant_id`, no `Audit` mixin — content changes by seed, not by user.

### 1.1 `country`

**Purpose:** ISO 3166-1 country list. Selects the jurisdiction profile that drives which statutory IDs and licences a company must supply.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `code` | `CHAR(2)` | no | **PK.** ISO 3166-1 alpha-2 — `IN`, `GB`, `AE` |
| `iso3` | `CHAR(3)` | no | Alpha-3, for interchange formats that require it |
| `numeric_code` | `CHAR(3)` | no | ISO numeric, used by some banking formats |
| `name` | `VARCHAR(100)` | no | Common name — "India" |
| `official_name` | `VARCHAR(200)` | no | Legal name, for printed documents |
| `default_currency_code` | `CHAR(3)` | no | Pre-selects currency on company creation |
| `phone_prefix` | `VARCHAR(8)` | no | Dial code, for phone input |
| `subdivision_label` | `VARCHAR(60)` | no | UI label for its subdivisions — "State", "Province", "Emirate" |
| `is_active` | `TINYINT(1)` | no | Selectable for new records |

**Keys:** PK `code` · FK `default_currency_code` → `currency.code`

### 1.2 `state`

**Purpose:** ISO 3166-2 subdivisions. Required for tax place-of-supply, and carries the GST state code.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `code` | `VARCHAR(6)` | no | **PK.** ISO 3166-2 — `IN-MH`, `US-CA` |
| `country_code` | `CHAR(2)` | no | Owning country |
| `name` | `VARCHAR(100)` | no | "Maharashtra" |
| `subdivision_type` | `VARCHAR(60)` | no | "state", "union territory", "metropolitan collectivity with special status" |
| `tax_jurisdiction_code` | `VARCHAR(8)` | yes | GST state code — Maharashtra `27`. Prefixes every GSTIN issued there |
| `is_active` | `TINYINT(1)` | no | Selectable for new records |

**Keys:** PK `code` · FK `country_code` → `country.code` · **UNIQUE `(country_code, code)`**

> The unique key exists solely to be the target of the composite FK on `company` and `company_address`, which is what makes `country_code='IN'` with `state_code='US-CA'` unrepresentable rather than merely unlikely.

### 1.3 `currency`

**Purpose:** ISO 4217 currencies plus the presentation metadata needed to print an amount.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `code` | `CHAR(3)` | no | **PK.** ISO 4217 alpha — `INR`, `USD` |
| `numeric_code` | `CHAR(3)` | no | ISO numeric |
| `name` | `VARCHAR(100)` | no | "Indian Rupee" |
| `symbol` | `VARCHAR(8)` | no | `₹`. Multi-byte, hence the length |
| `minor_unit` | `TINYINT` | no | Decimal places for **display** — JPY 0, INR 2, KWD 3. Storage is always `DECIMAL(19,4)` |
| `major_unit_name` | `VARCHAR(40)` | no | "Rupees" — for amount-in-words |
| `minor_unit_name` | `VARCHAR(40)` | yes | "Paisa" |
| `minor_unit_name_plural` | `VARCHAR(40)` | yes | "Paise" |
| `is_active` | `TINYINT(1)` | no | Selectable for new records |

**Keys:** PK `code`

> `minor_unit` governs rounding and display only. It never changes storage precision — a JPY amount is still `DECIMAL(19,4)`, it just renders with no decimals.

### 1.4 `language` — *deferred*

**Purpose:** BCP-47 language list, for the locale dropdown once multi-language labels are built.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `code` | `VARCHAR(8)` | no | **PK.** BCP-47 — `en`, `en-IN`, `hi` |
| `name` | `VARCHAR(100)` | no | English name |
| `native_name` | `VARCHAR(100)` | no | Endonym, for the picker |
| `is_rtl` | `TINYINT(1)` | no | Right-to-left layout |
| `is_active` | `TINYINT(1)` | no | Selectable |

Not built in phase 1. `locale` stays a validated BCP-47 string until [custom-fields.md](custom-fields.md) §13's multi-language question is settled.

---

## 2. Platform mechanism

Defined by `libs/platform` but **physically present in every service database**, so they need migrations in `dbs/identity/` like anything else.

### 2.1 `outbox`

**Purpose:** Guarantees an event and its business change commit atomically. The mechanism behind CLAUDE.md invariants 8 and 10 — publishing after commit loses events RabbitMQ cannot replay.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `id` | `BINARY(16)` | no | PK |
| `tenant_id` | `BINARY(16)` | yes | Null for platform-level events |
| `aggregate_type` | `VARCHAR(80)` | no | `company`, `user`, `role_assignment` |
| `aggregate_id` | `BINARY(16)` | no | The row that changed |
| `event_type` | `VARCHAR(120)` | no | `company.created`, `role_assignment.changed` |
| `payload` | `JSON` | no | Event body. Versioned by `schema_version` |
| `schema_version` | `SMALLINT` | no | Lets consumers handle an evolving payload |
| `message_id` | `BINARY(16)` | no | Dedupe key consumers store in `processed_message` |
| `trace_id` | `VARCHAR(32)` | yes | Ties the event to the originating request (audit.md §1) |
| `occurred_at` | `DATETIME(6)` | no | When the business change happened, not when published |
| `available_at` | `DATETIME(6)` | no | Earliest publish attempt. Backoff sets it forward |
| `published_at` | `DATETIME(6)` | yes | Null = pending. The poller's queue |
| `attempt_count` | `SMALLINT` | no | Retry counter; drives backoff and DLX routing |
| `last_error` | `TEXT` | yes | Truncated. Diagnostics only — never surfaced to a client (CLAUDE.md §5.8) |

**Keys:** PK `id` · INDEX `(published_at, available_at)` — the poller's only query · INDEX `(aggregate_type, aggregate_id)` · UNIQUE `(message_id)`

> Published rows are **not deleted inline.** A retention job archives them after a window, so a consumer bug is diagnosable and a lost event is republishable. Deleting on publish makes the outbox unauditable.

### 2.2 `processed_message`

**Purpose:** Consumer-side dedupe. Redelivery must produce one effect (rule 4.4).

| Column | Type | Null | Purpose |
|---|---|---|---|
| `consumer_name` | `VARCHAR(120)` | no | Logical consumer — several consume the same message |
| `message_id` | `BINARY(16)` | no | From the producer's outbox row |
| `processed_at` | `DATETIME(6)` | no | For retention pruning |

**Keys:** **PK `(consumer_name, message_id)`**

> The PK must be composite. Keying on `message_id` alone means the second consumer of a fanout event silently skips it — a data-loss bug that only appears once a second consumer is added.

No `tenant_id`: dedupe is an infrastructure concern and the message may be pre-tenant-resolution. Whitelisted in §0.3.

### 2.3 `idempotency_key`

**Purpose:** A replayed request produces one effect and returns the original response (CLAUDE.md invariant 2).

| Column | Type | Null | Purpose |
|---|---|---|---|
| `id` | `BINARY(16)` | no | PK |
| `tenant_id` | `BINARY(16)` | no | Scoping |
| `key_value` | `VARCHAR(255)` | no | Client-supplied `Idempotency-Key` header |
| `endpoint` | `VARCHAR(200)` | no | Method + route. Scopes the key so one value can't collide across endpoints |
| `request_hash` | `CHAR(64)` | no | SHA-256 of the canonicalized body |
| `state` | `VARCHAR(20)` | no | `in_progress` \| `completed` \| `failed` |
| `response_status` | `SMALLINT` | yes | Replayed on a repeat |
| `response_body` | `JSON` | yes | Replayed on a repeat |
| `locked_at` | `DATETIME(6)` | yes | Concurrent-request guard |
| `completed_at` | `DATETIME(6)` | yes | When the effect landed |
| `expires_at` | `DATETIME(6)` | no | Retention horizon — 24h typical |

**Keys:** PK `id` · **UNIQUE `(tenant_id, endpoint, key_value)`** · INDEX `(expires_at)`

> `request_hash` is the field people omit. Same key with a *different* body is a client bug, and it must return **422**, not silently replay the first response — otherwise a mobile client that mutates a payload between retries gets the wrong answer and never knows.

---

## 3. Tenant & structure

### 3.1 `tenant`

*Mixins: `Id`, `Audit`.* No `tenant_id` — it **is** the tenant.

**Purpose:** Root isolation and subscription boundary. The paying customer.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `name` | `VARCHAR(200)` | no | Display name |
| `slug` | `VARCHAR(63)` | no | Subdomain / URL segment. DNS-label constrained |
| `status` | `VARCHAR(20)` | no | `active` \| `suspended` \| `closed` (rule 4.12 — no `is_active` here) |
| `plan_id` | `BINARY(16)` | yes | Nullable until `plan` is built |
| `primary_contact_email` | `VARCHAR(320)` | no | Billing and incident contact |
| `default_country_code` | `CHAR(2)` | no | Pre-selects on company creation |
| `default_state_code` | `VARCHAR(6)` | yes | Selected tenant state; NULL for existing tenants or no subdivision |
| `default_currency_code` | `CHAR(3)` | no | Pre-selects on company creation |
| `default_locale` | `VARCHAR(8)` | no | BCP-47 |
| `default_timezone` | `VARCHAR(64)` | no | IANA — `Asia/Kolkata` |
| `trial_ends_on` | `DATE` | yes | Null = not a trial |
| `suspended_at` | `DATETIME(6)` | yes | Set on suspension |
| `suspended_reason` | `VARCHAR(500)` | yes | Shown to tenant admins |

**Keys:** PK `id` · UNIQUE `(slug)` · FKs to `country`, `currency`

*Mechanism note:* filtered on `id` via the `SelfTenant` mixin (§0.2), so provisioning a tenant and any platform-admin listing run under `unfiltered()` — the same audited escape hatch as every other cross-tenant operation. `plan_id` carries no FK while `plan` is deferred (§3.2).

> `slug` is immutable after creation — it appears in URLs, webhook targets, and saved bookmarks. Renaming it silently breaks integrations.

### 3.2 Platform pricing catalog; tenant plan assignment remains deferred

The global fee catalog is implemented as `platform_price` and immutable
`platform_price_revision`, revisions 0084–0085. See [platform pricing](platform-pricing.md)
for fields, units, conversion, defaults and lifecycle. It does not assign `tenant.plan_id`
or create tenant billing contracts. The original future tenant tier below stays deferred.

**Purpose:** Subscription tier. Deferred pending the open question of whether we bill our own tenants in this system.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `code` | `VARCHAR(40)` | no | `starter`, `growth` — stable identifier |
| `name` | `VARCHAR(100)` | no | Display |
| `max_companies` | `INT` | yes | Null = unlimited |
| `max_users` | `INT` | yes | Null = unlimited |

*Mixins: `Id`, `Audit`, `Deactivable`.* No `tenant_id` — plans are platform-level.

### 3.3 `company`

*Mixins: `Id`, `Tenant`, `Audit`.*

**Purpose:** The legal entity that issues documents. Owns its tax registrations, invoice series, base currency, and fiscal calendar. Not the same thing as a tenant ([org-model.md](org-model.md) §2.1).

**Identity**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `parent_company_id` | `BINARY(16)` | yes | Group hierarchy; self-referencing |
| `code` | `VARCHAR(20)` | no | **`[IMM]`** Short code, embedded in document numbers |
| `legal_name` | `VARCHAR(255)` | no | Registered name, for statutory output |
| `trade_name` | `VARCHAR(255)` | yes | Trading-as name, printed on invoices |
| `display_name` | `VARCHAR(120)` | no | UI and company switcher |
| `entity_type` | `VARCHAR(30)` | no | `pvt_ltd` \| `llp` \| `partnership` \| `sole_prop` \| `public` \| `trust` \| `branch` |
| `incorporation_date` | `DATE` | yes | Registration date |
| `country_code` | `CHAR(2)` | no | **`[IMM]`** Selects the jurisdiction profile |
| `state_code` | `VARCHAR(6)` | no | **`[IMM]`** Home state. Drives place of supply on every line |
| `status` | `VARCHAR(20)` | no | `active` \| `suspended` \| `closed` |
| `first_posted_at` | `DATETIME(6)` | yes | Set once by the first posting, never cleared. **Gates every `[IMM]` field** |

**Financial — all `[IMM]`**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `base_currency` | `CHAR(3)` | no | Ledger currency. Changing it reinterprets every stored amount |
| `reporting_currency` | `CHAR(3)` | yes | Presentation translation; null = same as base |
| `fiscal_year_start_month` | `TINYINT` | no | 1–12. Source for `fiscal_year` generation |
| `fiscal_year_start_day` | `TINYINT` | no | 1–31 |
| `books_begin_date` | `DATE` | no | Earliest postable date. May be after the FY start on migration |
| `amount_precision` | `TINYINT` | no | 0–4. **Display and rounding scale for amounts — not storage scale** (§0.4) |
| `quantity_precision` | `TINYINT` | no | 0–4. Default quantity presentation; native unit precision governs input, exact stock is never rounded to this default |
| `rounding_mode` | `VARCHAR(20)` | no | `half_up` \| `half_even` \| `down`. `Decimal` context, not float |

**Tax posture** — defaults only; authoritative values are per-registration (§3.6)

| Column | Type | Null | Purpose |
|---|---|---|---|
| `default_tax_system` | `VARCHAR(20)` | no | **`[CODE]`** Form default. **Never read by a posting path** |
| `tax_treatment_default` | `VARCHAR(12)` | no | `inclusive` \| `exclusive` |

**Commercial defaults**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `default_payment_terms_days` | `SMALLINT` | no | Seeds invoice due dates |
| `credit_limit_default` | `DECIMAL(19,4)` | yes | Default customer credit ceiling |
| `cash_receipt_limit` | `DECIMAL(19,4)` | yes | Statutory cap (₹2,00,000 in India). Lowerable, never raisable above the profile |
| `backdated_posting_limit_days` | `SMALLINT` | yes | Rejects implausible back-dating even in an open period ([fiscal-year.md](fiscal-year.md) §6.3) |

**Business nature**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `industry_code` | `VARCHAR(20)` | yes | NIC / NAICS |
| `business_category_code` | `VARCHAR(32)` | yes | FK to seeded `business_category.code`; unclassified by default |
| `store_format_code` | `VARCHAR(32)` | yes | FK to seeded `store_format.code`; unspecified by default |
| `business_nature` | `VARCHAR(20)` | yes | `trading` \| `manufacturing` \| `service` \| `distribution` \| `retail` |

**Locale & presentation**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `timezone` | `VARCHAR(64)` | no | IANA. Governs document date defaulting |
| `locale` | `VARCHAR(8)` | no | BCP-47 |
| `date_format` | `VARCHAR(20)` | no | Display pattern for `_date` fields |
| `datetime_format` | `VARCHAR(30)` | no | Display pattern for `_at` fields |
| `digit_grouping` | `VARCHAR(10)` | no | `indian` (12,34,567) \| `western` (1,234,567) |
| `decimal_separator` | `VARCHAR(2)` | no | `.` or `,` |
| `thousands_separator` | `VARCHAR(2)` | no | `,`, `.`, space, or empty |
| `negative_format` | `VARCHAR(15)` | no | `minus` \| `parentheses` |
| `show_amount_in_words` | `TINYINT(1)` | no | Prints the words line on documents |
| `currency_symbol_position` | `VARCHAR(10)` | no | `prefix` \| `suffix` |
| `currency_symbol_override` | `VARCHAR(8)` | yes | Legacy stationery — "Rs." instead of "₹" |

**Documents & branding**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `logo_url` | `VARCHAR(500)` | yes | Signed-URL object key (CLAUDE.md §5.14) |
| `signature_url` | `VARCHAR(500)` | yes | Authorised-signatory image |
| `brand_color` | `CHAR(7)` | yes | Hex |
| `print_template_id` | `BINARY(16)` | yes | Document layout selection |
| `terms_and_conditions` | `TEXT` | yes | Printed block |
| `declaration_text` | `TEXT` | yes | "We declare that this invoice shows…" |
| `jurisdiction_text` | `VARCHAR(200)` | yes | "Subject to Mumbai jurisdiction" |
| `signatory_name` | `VARCHAR(150)` | yes | Printed name |
| `signatory_designation` | `VARCHAR(100)` | yes | Printed designation |
| `dsc_thumbprint` | `VARCHAR(64)` | yes | Certificate **thumbprint only**. Never a key or PFX (CLAUDE.md §5.9) |

**Visibility** ([company.md](company.md) §6)

| Column | Type | Null | Purpose |
|---|---|---|---|
| `visibility` | `VARCHAR(10)` | no | `listed` \| `unlisted`. **A display preference, not access control** |
| `requires_step_up` | `TINYINT(1)` | no | Demands fresh authentication before opening |
| `visibility_changed_at` | `DATETIME(6)` | yes | Audit support |
| `visibility_changed_by` | `BINARY(16)` | yes | Audit support |

**Extensibility**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `custom_fields` | `JSON` | yes | Values keyed by definition `key` ([custom-fields.md](custom-fields.md) §3) |

**Keys:** PK `pk_company` · UNIQUE `uq_company_tenant_id_code (tenant_id, code)` · INDEX `ix_company_tenant_id` · INDEX `ix_company_tenant_id_status` · FK `fk_company_parent_company_id` → `company.id` · FK `fk_company_country_code`, `fk_company_base_currency`, `fk_company_reporting_currency` · **FK `fk_company_country_code_state_code (country_code, state_code)` → `state (country_code, code)`** · FK-supporting indexes `ix_company_country_code_state_code`, `ix_company_base_currency`, `ix_company_reporting_currency`, `ix_company_parent_company_id`

> Every FK gets a **declared** supporting index, because InnoDB otherwise invents one named after the constraint — invisible in the model and permanent autogenerate drift. `fk_company_country_code` needs none of its own: `ix_company_country_code_state_code` has `country_code` as its leftmost prefix and serves both.

> `fk_company_parent_company_id` proves the parent row exists; it **cannot** prove the parent is in the same tenant. That check is `domain/`'s, and a test asserts the database's silence so it is not later mistaken for redundant. `print_template_id` carries no FK at all — templates live outside `identity`, and a cross-service foreign key is what the architecture forbids.

> `first_posted_at` is the whole enforcement mechanism for `[IMM]`. It is set inside the first posting's transaction by any service that posts, arriving via the company replica — so it must be part of the `company.updated` event, not a local-only column.

### 3.4 `company_feature`

*Mixins: `Id`, `Tenant`, `Audit`.*

**Purpose:** Per-company capability toggles ([company-features.md](company-features.md)). Rows rather than booleans on `company`, so each carries its own actor, audit event, and irreversibility lock.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | Owner |
| `feature_key` | `VARCHAR(60)` | no | **`[CODE]`** From the `FEATURES` catalogue |
| `is_enabled` | `TINYINT(1)` | no | Current state. Absent row = disabled |
| `enabled_at` | `DATETIME(6)` | yes | When switched on |
| `enabled_by` | `BINARY(16)` | yes | Who switched it on |
| `disabled_at` | `DATETIME(6)` | yes | When switched off |
| `disabled_by` | `BINARY(16)` | yes | Who switched it off |
| `locked_at` | `DATETIME(6)` | yes | Set by the first dependent write. Non-null = **permanently enabled** |
| `lock_reason` | `VARCHAR(120)` | yes | The `locks_on` event, for the rejection message |

**Keys:** PK `pk_company_feature` · UNIQUE `uq_company_feature_company_id_feature_key (company_id, feature_key)` · INDEX `ix_company_feature_tenant_id` · FK `fk_company_feature_company_id`

> The unique key **deliberately omits `tenant_id`** ([identity-db-plan.md](identity-db-plan.md) §1.7). `company_id` already determines the tenant, so prefixing it would let the same pair insert twice under a mismatched `tenant_id` — a weaker constraint. `feature_key` carries no FK: features are code, not data, and validation is `billing_platform.features`' job.

### 3.5 `company_address`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** Multiple addresses per company — a company genuinely has registered, billing, shipping, and branch addresses at different places.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | Owner |
| `type` | `VARCHAR(20)` | no | `registered` \| `billing` \| `shipping` \| `branch` |
| `label` | `VARCHAR(100)` | yes | User-facing name — "Andheri Warehouse" |
| `line1` | `VARCHAR(255)` | no | |
| `line2` | `VARCHAR(255)` | yes | |
| `city` | `VARCHAR(100)` | no | |
| `state_code` | `VARCHAR(6)` | no | FK; drives place of supply on shipping addresses |
| `postal_code` | `VARCHAR(20)` | no | Validated per jurisdiction profile |
| `country_code` | `CHAR(2)` | no | FK |
| `is_primary` | `TINYINT(1)` | no | One per `type` — enforced in `domain/`, **not** by a key |

**Keys:** PK `pk_company_address` · INDEX `ix_company_address_company_id_type (company_id, type)` · INDEX `ix_company_address_tenant_id` · INDEX `ix_company_address_country_code_state_code` · FK `fk_company_address_company_id` · FK `fk_company_address_country_code` · **FK `fk_company_address_country_code_state_code (country_code, state_code)` → `state (country_code, code)`**

> `ix_company_address_company_id_type` leads with `company_id` rather than `tenant_id`, which is one of the two exceptions to [identity-db-plan.md](identity-db-plan.md) §1.7: it supports `fk_company_address_company_id` and so must begin with that column, and `company_id` functionally determines `tenant_id` anyway. `ix_company_address_country_code_state_code` also serves `fk_company_address_country_code`, whose columns are its leftmost prefix.

> **"One per `type`" has no unique key** because it needs one restricted to `is_primary = 1`, and MariaDB has no partial unique index. The rule lives in `domain/`; the schema is deliberately silent, and a test asserts that silence so the missing constraint is not later read as an oversight.

> `company.state_code` is **not** derived from the primary registered address, deliberately ([org-model.md](org-model.md) §6.2) — flipping `is_primary` here must never retroactively change the tax treatment of issued invoices.

### 3.6 `company_tax_registration`

*Mixins: `Id`, `Tenant`, `Audit`, `Effective`.* Uses `Effective`, **not** `Deactivable` — an old GSTIN must stay resolvable for invoices issued under it.

**Purpose:** The registrations a company invoices under. Resolved by the document's `posting_date` ([company.md](company.md) §2.3).

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | Owner |
| `tax_system` | `VARCHAR(20)` | no | **`[CODE]`** `gst_in` \| `vat_gb` \| … Immutable after create |
| `regime` | `VARCHAR(30)` | no | **`[CODE]`** `regular` \| `composition` \| `flat_rate` \| … Drives whether tax may be charged |
| `registration_class` | `VARCHAR(20)` | no | **`[CODE]`** `supplier` \| `isd` \| `tds_deductor` \| `tcs_collector`. Derived from `regime` by the catalogue and set in `domain/` on create, never by the client; read-only in the API. Groups overlap and the unique key |
| `number` | `VARCHAR(40)` | no | GSTIN / VAT number. Validated against the profile regex |
| `jurisdiction_code` | `VARCHAR(6)` | no | State or country this registration covers. **No FK** — a *state* code in India, a *country* code in the UK, and no single target covers both |
| `legal_name_on_registration` | `VARCHAR(255)` | yes | May differ from `company.legal_name`; prints as registered |
| `registered_address_id` | `BINARY(16)` | yes | FK → `company_address` |
| `is_primary` | `TINYINT(1)` | no | Default for the jurisdiction |
| `verified_at` | `DATETIME(6)` | yes | Verification timestamp |
| `verified_by` | `BINARY(16)` | yes | Actor |
| `verification_reference` | `VARCHAR(120)` | yes | Gateway/portal reference |

**Keys:** PK `id` · UNIQUE `(company_id, tax_system, registration_class, jurisdiction_code, valid_from)`, named `uq_company_tax_registration_class_jurisdiction_valid_from` (revision 0063; was `uq_company_tax_registration_tax_system_jurisdiction_valid_from` without the class) · INDEX `(company_id, jurisdiction_code, valid_from, valid_to)`, named `ix_company_tax_registration_jurisdiction_validity` — the resolution query

> Both names are shortened under [identity-db-plan.md](identity-db-plan.md) §1.3: the generated ones are 78 and 74 characters and MariaDB caps an identifier at 64. **The name therefore no longer lists every column** — read the columns from the table above, or from the test that asserts them.

> Two rules enforced in `domain/`, not by constraints: **overlapping validity for the same `(tax_system, jurisdiction_code)` is rejected** at write time, and **a gap returns `None`** rather than falling back to the nearest row. A company may genuinely be unregistered for a stretch.

> A third rule replaces the missing FK on `jurisdiction_code`: `assert_jurisdiction_code_allowed` requires a subdivision code where the profile registers per state and the country code where it registers per country, and **fails closed** — an empty subdivision set refuses every code rather than skipping the check.

### 3.7 `company_statutory_id`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** Statutory identifiers — PAN, TAN, CIN, EIN, Udyam, IEC, PF, ESI, professional tax. Rows rather than columns, because the set is jurisdiction-specific.

> **`is_active` *and* `valid_to` is one lifecycle mechanism, not two** (rule 4.12, at its most easily misread). An identifier does not affect a computed amount — it prints — so the boolean is the right mechanism, and `valid_to` is the expiry printed on the certificate. The proof is the **absence of `valid_from`**: with no start date there is no window, so `valid_to` cannot be read as the date-validity form. A superseded identifier is deactivated, never deleted, and keeps its `value` (invariant 12).

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | Owner |
| `kind` | `VARCHAR(40)` | no | **`[CODE]`** From the jurisdiction profile |
| `value` | `VARCHAR(60)` | yes | Full value. **Null for restricted kinds** |
| `value_last4` | `VARCHAR(4)` | **no** | Populated for **every** kind — see below |
| `holder_name` | `VARCHAR(150)` | yes | For proprietor-held IDs |
| `issued_on` | `DATE` | yes | |
| `valid_to` | `DATE` | yes | Expiry where applicable |
| `verified_at` | `DATETIME(6)` | yes | |
| `verified_by` | `BINARY(16)` | yes | |
| `verification_reference` | `VARCHAR(120)` | yes | Proof of verification without holding the number |

**Keys:** PK `id` · UNIQUE `(company_id, kind, value_last4)` · INDEX `(company_id, kind)`

> **`value_last4` is NOT NULL, and populated for unrestricted kinds too** — corrected here in Phase 4. It is the last column of the unique key, and MariaDB treats NULLs inside a unique key as distinct ([identity-db-plan.md](identity-db-plan.md) §2): left NULL for unrestricted kinds, a company could store the same PAN twice and the key would enforce nothing for exactly the identifiers that print on invoices. The known cost of keying on the last four is narrow and accepted — two *different* values of **one** kind that happen to end the same way are falsely rejected. `kind` is in the key, so a PAN and a TAN sharing their last four both insert.

> **AADHAAR and SSN-class identifiers: `value` stays NULL.** The API accepts a full number, derives `value_last4`, records `verification_reference`, and discards the rest — never persisted, logged, returned, or exported (CLAUDE.md §5.10, [company.md](company.md) §4.3). PAN, TAN, CIN, EIN and GSTIN are *business* identifiers, printed on invoices, and are stored in full.

### 3.8 `company_licence`

*Mixins: `Id`, `Tenant`, `Audit`, `Effective`.*

**Purpose:** Trading licences that gate posting and print on documents — drug licences, FSSAI, LUT.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | Owner |
| `kind` | `VARCHAR(40)` | no | **`[CODE]`** `drug_licence_20b` \| `fssai` \| `lut` \| … |
| `number` | `VARCHAR(60)` | no | Prints on documents that legally require it |
| `issuing_authority` | `VARCHAR(200)` | yes | |
| `premises_address_id` | `BINARY(16)` | yes | Licences are usually per premises |
| `issued_on` | `DATE` | yes | |
| `renewal_reminder_days` | `SMALLINT` | yes | Lead time for the Celery Beat reminder |
| `document_url` | `VARCHAR(500)` | yes | Scanned licence, signed URL |
| `is_primary` | `TINYINT(1)` | no | Default for the kind |

**Keys:** PK `id` · UNIQUE `(company_id, kind, number, valid_from)` · INDEX `(company_id, kind, valid_from, valid_to)` · INDEX `(valid_to)` — the expiry-reminder sweep

> Resolved by `posting_date`, like tax registration. An expired licence **rejects** posting a document containing a gated item — not a warning ([company.md](company.md) §4.4). The gate **fails closed**: a gate no licence kind in the jurisdiction declares is a refusal, not permission, so a jurisdiction with no licences at all cannot post a gated line.

> Unlike tax registration, two licences of one kind valid at once is normal — a licence is per premises — so `resolve_licence` *chooses* (primary first, then the most recent start) rather than treating two matches as ambiguous. A renewal is a **new row with the same number**, which is why `valid_from` is in the unique key; editing the old row would change what an already-posted invoice printed.

> `INDEX (valid_to)` is the one index here that leads with neither `tenant_id` nor `company_id`, because the Beat sweep asks "what expires soon" across every tenant. It runs under `unfiltered()` by construction and that job is its **only** reader — a request path issuing this query is the cross-tenant read the session filter exists to prevent.

### 3.9 `company_contact`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** Named contacts per function, for statutory correspondence and support routing.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | Owner |
| `type` | `VARCHAR(20)` | no | `primary` \| `finance` \| `support` \| `statutory` |
| `name` | `VARCHAR(150)` | no | |
| `designation` | `VARCHAR(100)` | yes | |
| `email` | `VARCHAR(320)` | yes | |
| `phone_country_code` | `VARCHAR(8)` | yes | |
| `phone` | `VARCHAR(20)` | yes | |
| `is_primary` | `TINYINT(1)` | no | One per `type` |

**Keys:** PK `id` · INDEX `(company_id, type)`

### 3.10 `company_bank_account`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** Collection accounts, printed on invoices. One per currency is normal.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | Owner |
| `label` | `VARCHAR(100)` | no | "HDFC Current — INR" |
| `account_name` | `VARCHAR(200)` | no | Beneficiary name |
| `account_number` | `VARCHAR(60)` | yes | **Log-redaction target** (CLAUDE.md §5.11) |
| `iban` | `VARCHAR(34)` | yes | **Redaction target** |
| `swift` | `VARCHAR(11)` | yes | |
| `ifsc` | `VARCHAR(11)` | yes | India |
| `bank_name` | `VARCHAR(200)` | no | |
| `branch` | `VARCHAR(200)` | yes | |
| `currency_code` | `CHAR(3)` | no | FK |
| `is_primary` | `TINYINT(1)` | no | One per currency |

**Keys:** PK `id` · INDEX `(company_id, currency_code)` · FK `currency_code`

### 3.11 `company_document`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** Stored certificates and proofs — incorporation, registration certificates, board resolutions.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | Owner |
| `type` | `VARCHAR(40)` | no | `incorporation` \| `gst_certificate` \| `board_resolution` \| … |
| `title` | `VARCHAR(200)` | no | Display |
| `number` | `VARCHAR(60)` | yes | Document reference |
| `file_url` | `VARCHAR(500)` | no | Object key; served via signed expiring URL |
| `file_size_bytes` | `BIGINT` | yes | |
| `content_type` | `VARCHAR(100)` | yes | Validated on upload, not trusted from the client |
| `issued_on` | `DATE` | yes | |
| `expires_on` | `DATE` | yes | Drives a reminder where relevant |

**Keys:** PK `id` · INDEX `(company_id, type)` · INDEX `(expires_on)`

### 3.12 `department`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** Structure below a company — a role-assignment scope and a default cost centre. **Not** an approval chain ([org-model.md](org-model.md) §5.4).

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | Owner |
| `parent_id` | `BINARY(16)` | yes | Self-nesting; null = top level |
| `code` | `VARCHAR(20)` | no | Short reference |
| `name` | `VARCHAR(150)` | no | Display |
| `cost_centre_code` | `VARCHAR(30)` | yes | Default allocation target |
| `head_user_id` | `BINARY(16)` | yes | Department head, for routing |
| `path` | `VARCHAR(500)` | no | Materialized ancestor path — makes scope resolution one indexed `LIKE` instead of recursion |

**Keys:** PK `id` · UNIQUE `(company_id, code)` · INDEX `(tenant_id, path)` · FK `parent_id` → `department.id`

> `path` is maintained on insert and on reparent. Without it, ancestor-or-self scope resolution ([org-model.md](org-model.md) §2.3) is a recursive CTE on every permission check — the hottest query in the system.

---

## 4. Identity

### 4.1 `user`

*Mixins: `Id`, `Tenant`, `Audit`.*

**Purpose:** A principal within one tenant. Credentials live in Authentik; profile, org data, and preferences live here.

**Link & type**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `authentik_sub` | `VARCHAR(64)` | yes | OIDC subject. Null while `invited` and not yet activated |
| `user_type` | `VARCHAR(30)` | no | `platform_admin` \| `tenant_user` \| `customer_portal_user` \| `service_account`. **Never used for authorization** |
| `status` | `VARCHAR(20)` | no | `invited` \| `active` \| `suspended` \| `deactivated` |

**Name**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `salutation` | `VARCHAR(20)` | yes | |
| `first_name` | `VARCHAR(100)` | no | |
| `middle_name` | `VARCHAR(100)` | yes | |
| `last_name` | `VARCHAR(100)` | yes | Nullable — mononymous names are real |
| `display_name` | `VARCHAR(200)` | no | Rendered everywhere; derived on create, then user-editable |

**Contact**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `email` | `VARCHAR(320)` | no | Login identifier and notification target |
| `email_verified_at` | `DATETIME(6)` | yes | Mirror of Authentik state; a cache, not source of truth |
| `phone_country_code` | `VARCHAR(8)` | yes | |
| `phone` | `VARCHAR(20)` | yes | |
| `phone_verified_at` | `DATETIME(6)` | yes | |

**Org**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `employee_code` | `VARCHAR(40)` | yes | HR reference; survives anonymization |
| `job_title` | `VARCHAR(120)` | yes | |
| `reporting_manager_id` | `BINARY(16)` | yes | Self-referencing |
| `default_company_id` | `BINARY(16)` | yes | Company the app opens on |
| `default_department_id` | `BINARY(16)` | yes | |
| `date_of_joining` | `DATE` | yes | |
| `date_of_exit` | `DATE` | yes | |

**Preferences**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `locale` | `VARCHAR(8)` | yes | Overrides company default |
| `timezone` | `VARCHAR(64)` | yes | Governs displayed timestamps |
| `date_format` | `VARCHAR(20)` | yes | Overrides company |
| `datetime_format` | `VARCHAR(30)` | yes | Overrides company |
| `digit_grouping` | `VARCHAR(10)` | yes | Overrides company |
| `currency_display` | `VARCHAR(20)` | yes | Symbol vs code |
| `theme` | `VARCHAR(20)` | yes | |
| `landing_page` | `VARCHAR(100)` | yes | |

> A user may override **presentation** — date pattern, grouping, symbol form. A user may **not** override `amount_precision`, `quantity_precision`, or `rounding_mode`: those change computed totals, so they are company-level and `[IMM]` after posting (§0.4). Two users must never see different totals for the same document.

**Lifecycle**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `invited_by` | `BINARY(16)` | yes | |
| `invited_at` | `DATETIME(6)` | yes | |
| `activated_at` | `DATETIME(6)` | yes | First successful login |
| `last_active_at` | `DATETIME(6)` | yes | Written asynchronously — never on the request path |
| `deactivated_at` | `DATETIME(6)` | yes | |
| `deactivated_by` | `BINARY(16)` | yes | |
| `deactivation_reason` | `VARCHAR(500)` | yes | |
| `anonymized_at` | `DATETIME(6)` | yes | Set when PII is tombstoned |

**Legal**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `terms_accepted_at` | `DATETIME(6)` | yes | |
| `terms_version` | `VARCHAR(20)` | yes | Which version was accepted |
| `privacy_accepted_at` | `DATETIME(6)` | yes | |

**Extensibility**

| Column | Type | Null | Purpose |
|---|---|---|---|
| `custom_fields` | `JSON` | yes | |

**Keys:** PK `id` · **UNIQUE `(tenant_id, email)`** · **UNIQUE `(authentik_sub)`** · INDEX `(tenant_id, status)` · FK `reporting_manager_id`, `default_company_id`, `default_department_id`

> Email is deliberately **not** globally unique — the same address may exist in two tenants as different people-in-context. That single constraint is what stands between this model and a global `principal` ([org-model.md](org-model.md) §4.3), so changing it is a much larger decision than it looks.
>
> **Deactivation anonymizes, never deletes** (CLAUDE.md invariant 12). A user who posted an invoice is referenced from the ledger forever. Replace name, email, and phone with a tombstone; preserve `id` and `employee_code`; stamp `anonymized_at`.
>
> **Do not store what Authentik owns:** password hashes, MFA secrets, session state, recovery codes.

### 4.2 `user_identity`

*Mixins: `Id`, `Tenant`, `Audit`.*

**Purpose:** Additional IdP links, so a user can sign in via more than one provider.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `user_id` | `BINARY(16)` | no | Owner |
| `provider` | `VARCHAR(40)` | no | `authentik` \| `google` \| `microsoft` |
| `provider_sub` | `VARCHAR(255)` | no | Subject at that provider |
| `linked_at` | `DATETIME(6)` | no | |
| `last_login_at` | `DATETIME(6)` | yes | Mirror; a cache |

**Keys:** PK `id` · UNIQUE `(provider, provider_sub)` · INDEX `(user_id)`

### 4.3 `user_notification_preference`

*Mixins: `Id`, `Tenant`.*

**Purpose:** Per-channel, per-event opt-in. Consumed by `notification`.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `user_id` | `BINARY(16)` | no | Owner |
| `channel` | `VARCHAR(20)` | no | `email` \| `sms` \| `whatsapp` \| `push` \| `in_app` |
| `event_key` | `VARCHAR(120)` | no | **`[CODE]`** From the notifiable-event catalogue |
| `is_enabled` | `TINYINT(1)` | no | Absent row = the event's default |

**Keys:** PK `id` · UNIQUE `(user_id, channel, event_key)`

### 4.4 `user_api_token`

*Mixins: `Id`, `Tenant`, `Audit`.*

**Purpose:** Programmatic credentials for `service_account` users.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `user_id` | `BINARY(16)` | no | Owner |
| `name` | `VARCHAR(120)` | no | Human label — "Nightly stock sync" |
| `token_prefix` | `VARCHAR(12)` | no | First chars, shown in the UI for identification |
| `token_hash` | `CHAR(64)` | no | SHA-256. **The token itself is shown once and never stored** |
| `scopes` | `JSON` | yes | Narrowing within the user's permissions; never widening |
| `last_used_at` | `DATETIME(6)` | yes | Written asynchronously |
| `last_used_ip` | `VARCHAR(45)` | yes | IPv6-capable |
| `expires_at` | `DATETIME(6)` | yes | Null = non-expiring (discouraged) |
| `revoked_at` | `DATETIME(6)` | yes | Revocation is immediate, not TTL-based |
| `revoked_by` | `BINARY(16)` | yes | |

**Keys:** PK `id` · UNIQUE `(token_hash)` · INDEX `(user_id)`

> Lifecycle is `revoked_at` + `expires_at` — **not** `is_active` (rule 4.12). `scopes` may only subtract from the user's resolved permissions; a token that widens them is a privilege-escalation path around [roles-permissions.md](roles-permissions.md) §1.5.

### 4.5 `user_group`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** A named set of users that can be the *subject* of a role assignment — "Audit Team" gets read-only everywhere, once.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `code` | `VARCHAR(40)` | no | Stable reference |
| `name` | `VARCHAR(150)` | no | Display |
| `description` | `VARCHAR(500)` | yes | |

**Keys:** PK `id` · UNIQUE `(tenant_id, code)`

> Groups are **flat** — no `parent_id`. Nesting was rejected: compose via multiple role assignments instead, which keeps resolution one join deep.

### 4.6 `user_group_member`

*Mixins: `Id`, `Tenant`, `Audit`.*

**Purpose:** Group membership.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `user_group_id` | `BINARY(16)` | no | |
| `user_id` | `BINARY(16)` | no | |
| `added_by` | `BINARY(16)` | yes | |

**Keys:** PK `id` · UNIQUE `(user_group_id, user_id)` · INDEX `(user_id)` — permission resolution walks this direction

### 4.7 `membership`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** Org affiliation — which company and department a user belongs to. **Not authorization.** A membership may exist with no system access at all.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `user_id` | `BINARY(16)` | no | |
| `company_id` | `BINARY(16)` | no | |
| `department_id` | `BINARY(16)` | yes | Null = company-level affiliation |
| `is_primary` | `TINYINT(1)` | no | Drives default company on login |
| `started_on` | `DATE` | yes | |
| `ended_on` | `DATE` | yes | Ended affiliations stay for history |
| `department_scope_key` | `BINARY(16)` generated stored | yes | Null department normalized to the zero UUID for uniqueness |
| `primary_user_id` | `BINARY(16)` generated stored | yes | User ID only while active and primary; otherwise null |

**Keys:** PK `id` · UNIQUE `(user_id, company_id, department_id)` · INDEX `(company_id)`

> Kept separate from `role_assignment` because the lifecycles differ — HR changes versus security changes — and different people should review each. Merging them is the most common shortcut in org models and it makes access review impossible.

### 4.8 `impersonation_session`

*Mixins: `Id`, `Tenant`, `Audit`.*

**Purpose:** Time-bound support access, audited at both ends (CLAUDE.md §5.5). A table rather than a Redis TTL, so a session left open by a crashed process is still discoverable and closable.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `actor_user_id` | `BINARY(16)` | no | Who is impersonating |
| `target_user_id` | `BINARY(16)` | no | Who is being impersonated |
| `reason` | `VARCHAR(500)` | no | Mandatory. Surfaced to the tenant |
| `ticket_reference` | `VARCHAR(120)` | yes | Support ticket link |
| `started_at` | `DATETIME(6)` | no | |
| `expires_at` | `DATETIME(6)` | no | Hard ceiling, enforced server-side |
| `ended_at` | `DATETIME(6)` | yes | Null = active |
| `ended_reason` | `VARCHAR(40)` | yes | `manual` \| `expired` \| `revoked` |
| `actor_ip` | `VARCHAR(45)` | yes | |

**Keys:** PK `id` · INDEX `(target_user_id, ended_at)` · INDEX `(ended_at, expires_at)` — the sweeper

> Every audit row written during the session carries `on_behalf_of_user_id` ([audit.md](audit.md) §3), which is what makes impersonation visible to the tenant afterwards.

---

## 5. Authorization

### 5.1 `role`

*Mixins: `Id`, `Audit`, `Deactivable`.* `tenant_id` is **nullable** here — see below.

**Purpose:** A named permission bundle. System roles are shipped and read-only; tenant roles are clones a tenant may edit ([roles-permissions.md](roles-permissions.md)).

| Column | Type | Null | Purpose |
|---|---|---|---|
| `tenant_id` | `BINARY(16)` | **yes** | **Null = system role**, shared across all tenants |
| `key` | `VARCHAR(60)` | no | Stable identifier — `billing_clerk`. **Never renamed** |
| `name` | `VARCHAR(150)` | no | Display; may change |
| `description` | `VARCHAR(500)` | yes | Shown in the assignment UI |
| `is_system` | `TINYINT(1)` | no | Redundant with `tenant_id IS NULL`, kept for query clarity and to make the read-only check explicit |
| `cloned_from_role_id` | `BINARY(16)` | yes | Set when a tenant clones a system role |
| `scope_hint` | `VARCHAR(20)` | yes | `platform` \| `tenant` \| `company` \| `department`. UI guidance only, not enforcement |

**Keys:** PK `id` · UNIQUE `(tenant_id, key)` · INDEX `(is_system)`

> `tenant_id IS NULL` breaks the session-level tenant filter's usual shape, so the filter must be written as `tenant_id = :current OR tenant_id IS NULL` **for this table only**. That exception is explicit in the shared library and needs its own test — a naive filter hides every system role.

### 5.2 `role_permission`

*Mixins: `Id`, `Audit`.*

**Purpose:** Which permission keys a role grants.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `role_id` | `BINARY(16)` | no | |
| `permission_key` | `VARCHAR(80)` | no | **`[CODE]`** `invoice.post`, `period.close`. Plain string, **no FK** |

**Keys:** PK `id` · UNIQUE `(role_id, permission_key)`

> There is **no `permission` table.** Permissions are a fixed catalogue in code ([roles-permissions.md](roles-permissions.md) §2); a table would make them user-editable data and nothing could be statically checked. Startup asserts every stored `permission_key` exists in the catalogue and **fails the boot** if not — silent drift means a role that grants nothing.

### 5.3 `role_assignment`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`, `Effective`.*

**Purpose:** The `(subject, role, scope)` triple that is the whole authorization model. Resolution is the union of all assignments whose scope is an **ancestor-or-self** of the target object's scope.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `subject_type` | `VARCHAR(12)` | no | `user` \| `user_group` |
| `subject_id` | `BINARY(16)` | no | The user or group |
| `role_id` | `BINARY(16)` | no | What is granted |
| `scope_type` | `VARCHAR(12)` | no | `tenant` \| `company` \| `department` |
| `scope_id` | `BINARY(16)` | yes | Null when `scope_type = tenant` |
| `granted_by` | `BINARY(16)` | yes | Who granted it — escalation-guard evidence |
| `grant_reason` | `VARCHAR(500)` | yes | Why, for access review |

**Keys:** PK `id` · UNIQUE `(subject_type, subject_id, role_id, scope_type, scope_id)` · INDEX `(tenant_id, subject_type, subject_id)` — the resolution query · INDEX `(role_id)`

> `Effective` (`valid_from`/`valid_to`) covers **temporary elevation** — a year-end auditor whose access expires on a date rather than by someone remembering to revoke it.
>
> Three escalation guards enforced in `domain/` ([roles-permissions.md](roles-permissions.md) §1.5): you cannot grant a permission you do not hold, cannot modify your own assignments (directly or via a group you belong to), and cannot grant at a scope broader than your own. Every write here is a `security`-category audit event.

### 5.4 `field_policy`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** Allow/deny a *specific field* within an already-permitted update ([field-permissions.md](field-permissions.md)). Narrows; never widens.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `subject_type` | `VARCHAR(12)` | no | `role` \| `user_group` \| `user` |
| `subject_id` | `BINARY(16)` | no | |
| `entity_type` | `VARCHAR(80)` | no | **`[CODE]`** `billing.invoice` |
| `field_key` | `VARCHAR(120)` | no | **`[CODE]`** Registered field name, or `custom_field:<key>` |
| `access` | `VARCHAR(10)` | no | `read` \| `write` |
| `effect` | `VARCHAR(10)` | no | `deny` \| `allow` |
| `scope_type` | `VARCHAR(12)` | no | `tenant` \| `company` \| `department` |
| `scope_id` | `BINARY(16)` | yes | Null at tenant scope |
| `condition` | `JSON` | yes | Optional rule tree; defeats cache-time resolution, so keep rare |
| `reason` | `VARCHAR(500)` | yes | **Surfaced in the 403 and the audit event** |

**Keys:** PK `id` · UNIQUE `(subject_type, subject_id, entity_type, field_key, access, scope_type, scope_id)` · INDEX `(tenant_id, subject_type, subject_id)`

> Default is **allow** — the deliberate deviation from deny-by-default, because the endpoint permission is the gate and this only subtracts. Deny wins at equal specificity; a more specific scope overrides a broader one. Attach to **roles**, not users, as standard practice.

---

## 6. Extensibility

Master copies live here; every other service holds a read-only replica ([custom-fields.md](custom-fields.md) §2).

### 6.1 `custom_field_definition`

*Mixins: `Id`, `Tenant`, `Audit`, `Deactivable`.*

**Purpose:** An admin-defined field on an entity, with no migration and no deploy.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | yes | **Null = every company in the tenant** |
| `entity_type` | `VARCHAR(80)` | no | **`[CODE]`** From the entity registry — `catalog.item` |
| `key` | `VARCHAR(60)` | no | Stable identifier. **Immutable after create** |
| `label` | `VARCHAR(150)` | no | Form label |
| `help_text` | `VARCHAR(500)` | yes | |
| `placeholder` | `VARCHAR(150)` | yes | |
| `data_type` | `VARCHAR(30)` | no | **`[CODE]`** `text` \| `integer` \| `decimal` \| `date` \| `datetime` \| `boolean` \| `currency_amount` \| `select` \| `multi_select` \| `dynamic_select` \| `auto_number` |
| `display_order` | `SMALLINT` | no | Within its group |
| `display_group` | `VARCHAR(100)` | yes | Form section heading |
| `is_searchable` | `TINYINT(1)` | no | Projects into `custom_field_value_index`. **Off by default** |
| `requires_adoption` | `TINYINT(1)` | no | Default 0 for legacy rows; new Catalog product definitions use 1 and need company review/adoption. Migration 0058. |
| `is_immutable_after_create` | `TINYINT(1)` | no | Set-once fields |
| `requires_feature` | `VARCHAR(60)` | yes | **`[CODE]`** Resolves out of the set when the feature is off |
| `validation` | `JSON` | yes | `required`, `min`/`max`, `regex`, `decimal_places`, `unique_within` |
| `options` | `JSON` | yes | Static select choices |
| `option_source_key` | `VARCHAR(80)` | yes | **`[CODE]`** Registered resolver. **Never a URL or query** |
| `depends_on_key` | `VARCHAR(60)` | yes | Parent field for cascading selects |
| `visibility` | `JSON` | yes | Conditional show/hide rule tree |
| `sequence_config` | `JSON` | yes | `auto_number` prefix, padding, reset cycle |
| `default_value` | `VARCHAR(500)` | yes | |

**Keys:** PK `id` · UNIQUE `(tenant_id, company_id, entity_type, key)` · INDEX `(tenant_id, entity_type, is_active)` — the resolution query

> `option_source_key` is the security boundary of the whole feature. Admin-supplied SQL or URLs would be injection and SSRF in one column, so sources are code-registered resolvers only. Admin-authored `regex` is a ReDoS vector: complexity-check at save time, cap input length, match under timeout.

### 6.2 `field_config`

*Mixins: `Id`, `Tenant`, `Audit`.* **Supersedes `custom_field_override`** — same table generalized to cover native fields as well as custom ones.

**Purpose:** A tenant admin's per-scope override of how a field appears on a form — show/hide, require, reorder, relabel. Covers **both** native columns (`company.industry_code`) and custom definitions, because the client renders one merged field set and needs one place to configure it.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | yes | **Null = tenant-wide default.** A company row overrides the tenant row |
| `entity_type` | `VARCHAR(80)` | no | **`[CODE]`** From the entity registry — `identity.company` |
| `field_source` | `VARCHAR(10)` | no | `native` \| `custom`. Makes the discriminator queryable |
| `field_key` | `VARCHAR(120)` | no | Native registry key, or the custom definition's `key` |
| `definition_id` | `BINARY(16)` | yes | FK → `custom_field_definition`. **Non-null iff `field_source = custom`** |
| `is_visible` | `TINYINT(1)` | yes | Null = inherit. `false` hides it from **new** forms only |
| `is_required` | `TINYINT(1)` | yes | Null = inherit. **May only tighten** — see below |
| `display_order` | `SMALLINT` | yes | Null = inherit registry / definition order |
| `display_group` | `VARCHAR(100)` | yes | Null = inherit. Moves a field to another form section |
| `label_override` | `VARCHAR(150)` | yes | Null = inherit. Only where the registry marks the field `renameable` |
| `help_text_override` | `VARCHAR(500)` | yes | Null = inherit |
| `default_value` | `VARCHAR(500)` | yes | Prefill for new records |

**Keys:** PK `id` · **UNIQUE `(tenant_id, company_id, entity_type, field_key)`** · INDEX `(tenant_id, entity_type)` — the resolution query · FK `definition_id`

Four rules, all enforced in `domain/` at write time on the config row — not at render time:

1. **Requiredness tightens only.** Optional → required is allowed. Required → optional is **rejected**: `FIELD_REGISTRY[key].required` is the floor. Loosening it would let an admin switch off form enforcement of a `NOT NULL` column, and every create would 500 at the database instead of returning 422.
2. **`is_visible = false` is rejected for a non-`hideable` field.** The registry marks `hideable=False` on anything `NOT NULL`, anything `[IMM]`, anything that prints on a statutory document, and anything that drives money — `base_currency`, `state_code`, `legal_name`, `amount_precision`.
3. **`label_override` is rejected unless `renameable`.** Relabelling `state_code` to something local is fine; relabelling `pan` is not, because it appears in statutory output under its legal name.
4. **An unknown `field_key` fails the boot check** — same rule as `role_permission.permission_key` (§5.2). A config row pointing at a column that was renamed or dropped silently removes the field from every form.

> **Hiding is layout, not authorization.** A hidden field is absent from the *form*; the API still accepts it, and imports and integrations legitimately set fields the UI does not show. To genuinely block a field, use `field_policy` (§5.4), which is enforced server-side on the changed-field set and holds in exports and reports (CLAUDE.md invariant 15). This is the same distinction as `company.visibility` ([company.md](company.md) §6): a display preference is never a security boundary.
>
> **Hiding never hides history.** A field hidden after it has data still renders read-only on existing records and still appears in exports — same rule as disabling a feature ([company-features.md](company-features.md) §4). Otherwise hiding becomes a silent data-loss and audit-gap mechanism. Read-*denies* from `field_policy` do suppress exports; layout hiding does not. Keeping those two apart is the point of having two tables.

#### The native field registry — code, no table

`field_config` overrides entries in a **fixed catalogue in `libs/platform`**, alongside the permission and feature catalogues:

```python
FIELD_REGISTRY = {
    "identity.company": {
        "legal_name":      Field(required=True, hideable=False, reason="statutory output"),
        "base_currency":   Field(required=True, hideable=False, reason="immutable; money"),
        "state_code":      Field(required=True, hideable=False, reason="place of supply"),
        "amount_precision":Field(required=True, hideable=False, reason="immutable; rounding"),
        "trade_name":      Field(hideable=True, renameable=True),
        "industry_code":   Field(hideable=True, renameable=True, group="business"),
        "business_nature": Field(hideable=True, group="business"),
        "credit_limit_default": Field(hideable=True, requires_feature="credit_limits"),
        ...
    },
    "identity.user":       {...},
    "identity.department": {...},
}
```

There is deliberately **no `field` table.** Native fields are model columns; a table would let an admin invent one, and nothing could be statically checked. Boot asserts every registry key resolves to a real column on the entity's model and **fails** if not.

#### Resolution — one endpoint, five ordered steps

```
GET /entities/{entity_type}/field-set?company_id=...
```

1. Start from `FIELD_REGISTRY[entity_type]`.
2. **Drop** fields whose `requires_feature` is disabled for the company ([company-features.md](company-features.md) §6.1).
3. Apply `field_config` — company row over tenant row.
4. **Merge in** `custom_field_definition` for the entity, with their own `field_config` rows applied.
5. Apply **`field_policy`** for *this actor* — read/write denies, last.

Steps 3 and 5 must stay separate and in that order. Step 3 is per **tenant** and is form layout; step 5 is per **actor** and is access control. Merging them means a tenant admin editing a form could change who can see a field — the one failure mode this whole design exists to avoid. Steps 1–4 are cacheable per `(tenant, company, entity)`; step 5 is per actor.

**Both clients render from this response and never hardcode a field list** — the same contract as the display config ([company.md](company.md) §4.5).

### 6.3 `custom_field_value_index`

*Mixins: `Tenant`.* No `Id` — the natural key is the PK. No `Audit` — derived data.

**Purpose:** Indexed search over custom fields without a migration. MariaDB `JSON` is not natively indexable (rule 4.7), and the documented workaround is a generated column, which is a migration — defeating the point.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `entity_type` | `VARCHAR(80)` | no | |
| `entity_id` | `BINARY(16)` | no | The record holding the value |
| `definition_id` | `BINARY(16)` | no | Which field |
| `company_id` | `BINARY(16)` | no | Scoping and uniqueness checks |
| `value_text` | `VARCHAR(255)` | yes | Text and select values |
| `value_number` | `DECIMAL(19,4)` | yes | Integer, decimal, currency |
| `value_date` | `DATETIME(6)` | yes | Date and datetime |
| `value_bool` | `TINYINT(1)` | yes | Boolean |

**Keys:** **PK `(entity_type, entity_id, definition_id)`** · INDEX `(definition_id, value_text)` · INDEX `(definition_id, value_number)` · INDEX `(definition_id, value_date)`

> Written in the **same transaction** as the entity, only for `is_searchable` definitions. Flipping `is_searchable` on enqueues a backfill; off deletes the rows. `identity` needs its own copy because it owns entities that take custom fields — `company`, `user`, `department`.

### 6.4 `custom_field_sequence`

*Mixins: `Id`, `Tenant`.*

**Purpose:** Counter state for `auto_number` custom fields.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `company_id` | `BINARY(16)` | no | |
| `definition_id` | `BINARY(16)` | no | |
| `cycle_key` | `VARCHAR(40)` | no | `''` \| a `fiscal_year_id` \| `'2026'` \| `'2026-09'`, per the reset rule |
| `next_value` | `BIGINT` | no | Allocated via `SELECT … FOR UPDATE` inside the entity transaction |

**Keys:** PK `id` · UNIQUE `(definition_id, company_id, cycle_key)`

> **Not gap-free.** A rolled-back create consumes a number. Gap-free numbering is a statutory invoice requirement and belongs in `document_sequence` ([fiscal-year.md](fiscal-year.md) §7), never here.

---

## 7. Cross-cutting checks before any migration lands

- **Every table with `tenant_id` has a two-tenant isolation test** — seed two tenants, query as one, assert the other's rows are absent (CLAUDE.md §7). This is the highest-value test in the service.
- **One DDL statement per revision** (rule 4.8) — no transactional DDL on MariaDB, so a multi-statement failure desynchronizes the schema from Alembic's version table.
- **Every migration read line by line.** `--autogenerate` misses `VARCHAR` length changes, index renames, collation, and generated columns.
- **`downgrade` present, or a comment saying why not.**
- Reference and system-role content ships in `seeds/`, **never in a migration**.
- The six §0.3 exemptions are whitelisted explicitly; a new `tenant_id`-less table is a review failure otherwise.

---

## 8. Open questions

- [ ] `department.path` separator and depth cap — needed before the materialized path is written
- [ ] Does `customer_portal_user` belong in `user`, or does the portal need its own principal table once it grows a profile?
- [ ] `user_api_token.scopes` shape — permission-key list, or something coarser?
- [ ] Should `role.scope_hint` be enforced rather than advisory? Enforcing it prevents assigning `controller` at department scope, which is probably right
- [ ] `outbox` retention window and archive destination
- [ ] Is `plan` in scope for v1, or is tenant billing external? Blocks `plan_feature` ([company-features.md](company-features.md) §7)

## 9. Decision log

- 2026-10-05: `company_tax_registration.registration_class` added and included in the unique
  key (revisions 0060–0063), so registrations of different classes in one state may start on
  the same day. See [company](company.md) §4.2.

- 2026-09-11: Clarified planned Catalog quantity/rate precision versus Identity presentation/
  monetary rounding. No Identity column type, applied migration or post-use lock is changed.


## Catalog source artifact tables (authorized 2026-09-11)

Identity remains the only writer of company, feature, field and subject facts. These artifacts
support the independent Catalog consumer; they are not new source business masters.

| Table | Native fields and constraints |
|---|---|
| catalog_source_generation | Id/tenant; unique tenant; positive BIGINT version. The native-write/snapshot transaction locks and advances this row. |
| catalog_source_snapshot | Id/tenant/company, request_id, source_version, generated_at, expires_at, manifest JSON; tenant/company/request unique, scoped identity key and expiry index. The signed manifest declares every known stream including empty sets, counts and page hashes. |
| catalog_source_page | Id/tenant/company, snapshot_id, page_number, content_sha256, payload JSON; unique scoped snapshot/page; composite scoped FK to the immutable snapshot. |

Artifacts have bounded creation/retention and do not replace the original domain/audit history.
Minimal payload whitelists exclude profile PII and credentials. Versioned full facts/tombstones
use Identity's transactional outbox. Source contracts and lease policy live in
[catalog-source-operations.md](catalog-source-operations.md).

- 2026-09-11: Added `business_category`, `business_role`, `store_format` (global seeded
  reference tables without tenant CRUD), `company_business_role` (tenant-scoped binding),
  and nullable company classification FKs. These three global catalogues are additional
  explicit mixin exceptions. See [company-classification.md](company-classification.md).


### 2026-09-12 corrective contract changes

See [bug-fix results](identity-bug-fix-results-2026-09-12.md) for field-policy sparse
responses, strict query/PATCH validation, bounded child lists, readable preferences,
and the explicit idempotent assignment re-grant command. Revisions 0044?0050 enforce
owner agreement for user defaults/managers, department heads/parents, registration
addresses and memberships. A selected default department requires a default company.


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

Decision 2026-10-21: Identity creates workspace slugs from its UUIDv7 and saves
optional tenant default states, validated against active country/state references.
Revisions 0074?0076 add the nullable column, supporting index and composite FK
separately. Existing slugs and tenant defaults are preserved.


Decision 2026-10-21: Settings reference catalog management

Revisions 0077?0079 add `reference_revision`, `reference_sync_state` and
`reference_change`, one CREATE/DROP statement per revision. Country/State/
Currency/Language natural-key tables and existing FK/history rows stay intact.
Catalog 0179?0180 and Accounting 0153?0154 add independent provenance/checkpoint
tables. The nullable `cursor` identifier is quoted in MySQL DDL.

ReferenceRevision carries UUIDv7 id, kind/code, name/parent, active flag, seed or
operator source, custom-origin flag, optimistic version, change id, bounded JSON
payload and actor/timestamps. Unique kind/code prevents retired code reuse;
kind/name/code, kind/active/name/code and kind/parent/name/code indexes support
lean signed keyset directories with natural code tie-breakers. ReferenceSyncState
has unique service and its committed cursor. Immutable Identity ReferenceChange
stores id/kind/code/version/payload and drives bounded durable replication.

These tables have no tenant_id because they hold global platform reference facts;
the explicit shared tenant-filter exception list records that justification.
Global operations still require configured operator identity, live
platform.config.manage and fresh verified write authentication. Audit events
contain actor UUID, kind/code/version and a bounded reason, never names or secrets.

Decision 2026-10-21: Redis reference choices use Identity revision 0080,
`reference_cache_generation`. Its UUIDv7 `id`, unique `key VARCHAR(16)` (`global`)
and UUIDv7 `token` contain no tenant or personal information. Source ORM writes,
provenance changes and consumer checkpoints rotate the token in the same transaction.
Installation creates the initial row. It is explicitly exempt from tenant filtering.
Reads use the token in versioned, database-specific Redis keys with a bounded TTL;
READ COMMITTED loaders recheck the token before filling. Redis failure falls back
to live reads; authorization and all write-time validations remain database-backed.

Decision 2026-10-21: `account_review` and `account_review_command` store the
platform's public-registration review projection and durable decision intent.
Both have UUIDv7 IDs, operating-tenant isolation and actor/timestamps. The projection
has an immutable provider UUID/numeric ID, bounded name/username/email/region,
status, observed activation/verification, SHA-256 fingerprint, version and drift flag.
Indexes cover tenant/name/email/username/id, tenant/status/created_at/id, and
tenant/created_at/id for the default unfiltered chronological directory.
Commands hold actor, account, action, bounded reason, manual attestation, request
key/hash, expected fingerprint, delivery state/attempts and completion timestamp.
The composite owner foreign key protects tenant isolation; actor/request-key is
unique per tenant. No credential, password hash or arbitrary provider blob is stored.
See [account review](platform-account-review.md) for purpose, access and retention.

Decision 2026-10-27: `account_review.workspace_name` distinguishes a public workspace
request from an invitation signup (empty) and an earlier registration (NULL).
`account_review_command.workspace_name` freezes the reviewed choice. Revisions
0086–0087 add one nullable VARCHAR(200) column each; no credentials are stored.


## Catalog source enrollment (0088)

`catalog_source_enrollment` records explicit installation Catalog enrollment with UUIDv7 `id`,
`tenant_id`, `company_id`, `is_active` and standard audit columns. The composite foreign key targets
`company(tenant_id,id)`; the unique tenant/company pair prevents duplicate or reactivated tombstones.
The active/id index supports bounded discovery. Authorised company creation inserts it atomically;
Catalog has no enrollment write API. Signed discovery returns only active tenant/company scope IDs.
Disabled rows are preserved by the audited operator backfill. No user authority or credentials are
stored here. See [source operations](catalog-source-operations.md).
