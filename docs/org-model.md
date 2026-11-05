# Org & Access Model — `identity` Service

**Status:** Core model, scoped APIs and administration UI implemented; remaining open product questions retained below
**Date:** 2026-09-03
**Owned by:** `identity` service
**Related:** [tech-stack.md](tech-stack.md) — rules 4.3 (DB isolation), 4.9 (auth) · [fiscal-year.md](fiscal-year.md) — period control

---

## 1. Core structure

There is no single hierarchy. There are **two independent trees joined by assignment tables**:

- a **structural** tree — where things live: tenant → company → department
- an **identity** set — who exists: users, groups

Access belongs to neither. It is a property of the **(subject, role, scope)** triple that connects them. That indirection is the whole design; collapsing it is what makes org models rigid.

```
STRUCTURE                              IDENTITY
─────────                              ────────
Tenant ─────────────────────────────── User          (user belongs to TENANT,
  │  isolation boundary                  │            not to a company)
  │  subscription, plan, data domain     │
  │                                    UserGroup
  ├── Company  (legal entity)             │  collection of users
  │     tax reg, invoice series,          │
  │     currency, fiscal year             │
  │                                       │
  │     └── Department                    │
  │           cost centre,                │
  │           approval routing            │
  │                                       │
  └── Role  (named permission bundle)     │
        │                                 │
        └── Permission  (atomic, fixed catalogue in code)


                    JOINS
                    ─────
   Membership:      User × Company [× Department]     — org affiliation
   RoleAssignment:  (User | UserGroup) × Role × Scope — authorization
                                          Scope = Tenant | Company | Department
```

---

## 2. The three decisions that matter

### 2.1 Tenant ≠ Company

**Tenant** is the isolation and subscription boundary — the paying customer.
**Company** is a legal entity *inside* the tenant, owning its own tax registration, invoice number series, base currency, and fiscal calendar.

For a billing product this separation earns its keep immediately: group companies, subsidiaries, and separate books under one account are normal.

*If multi-company isn't needed at launch:* keep the table and give each tenant exactly one company row. Costs nothing now. Retrofitting it later means renumbering issued invoices.

### 2.2 Users attach to the tenant, not the company

One person routinely works across several companies in a group. A `user.company_id` column guarantees duplicate humans within a month.

Company and department affiliation goes in `membership`.

Company people administration uses a bounded projection of current affiliations:
`GET /v1/companies/{company_id}/users` and its lean detail require `user.read` at
that company. They expose tenant users' directory fields, never the tenant-wide
profile. Ended, inactive, future affiliations and other account classifications
are excluded. Tenant filtering and company object scope are both enforced.

`POST /v1/companies/{company_id}/users` requires company-scoped `user.invite` and
creates a new tenant-user invitation and current primary company affiliation in
one audited transaction. It never changes an existing account or assigns a role.
The company and account classification cannot be supplied in the body. Existing
account affiliation and account-wide profile/lifecycle changes remain separate
administrative operations. This completes the company-admin people workflow
without promoting a company grant into tenant authority (2026-10-24).

### 2.3 Role assignments are scoped

A role granted at tenant scope applies everywhere. At company scope, to that company and its departments. One table covers every real case without introducing new concepts:

| Need | Assignment |
|---|---|
| Priya is AP clerk for Company A only | `(user:priya, ap_clerk, company:A)` |
| Ravi is finance admin group-wide | `(user:ravi, finance_admin, tenant:T)` |
| Audit team gets read-only everywhere | `(group:audit, read_only, tenant:T)` |
| Sales head approves only Dept 12 | `(user:x, approver, department:12)` |

**Resolution rule:** effective permissions = union of all assignments whose scope is an *ancestor-or-self* of the resource's scope.

---

## 3. Entity reference

| Entity | Role in the model |
|---|---|
| **tenant** | Root isolation boundary. On every table, in every query |
| **company** | Legal entity under tenant. Owns invoice series, tax registration, currency |
| **department** | Under company. Cost centre and approval routing. Self-nesting |
| **user** | Under tenant. Credentials live in the configured sign-in provider — Identity's own `local_*` tables by default, or Authentik ([local-auth](local-auth.md)); profile and org data here |
| **user_group** | Tenant-scoped collection of users; a *subject* for role assignment |
| **role** | Named bundle of permissions. System roles + tenant-custom |
| **permission** | Atomic `resource.action` string. **Fixed catalogue in code, not user-editable data** |
| **user_type** | Kind of principal — see §3.1 |

### 3.1 On `user_type`

Keep it as a **small closed enum** on the user record describing *what kind of principal this is*:

`platform_admin` · `tenant_user` · `customer_portal_user` · `service_account`

It determines which app surface and which auth flow the principal gets. It **must not be used for authorization** — that is roles' job.

Left loose, `user_type` grows into a shadow role system that contradicts the real one. It is worth having only because a customer-portal user (the person being billed) genuinely is a different kind of principal from a tenant employee, with a different login surface.

---

## 4. Tables

### 4.1 Core skeleton

Minimal column set; timestamps and audit columns omitted.

```
tenant            (id, name, status, plan_id)

company           (id, tenant_id, legal_name, tax_registration, base_currency,
                   fiscal_year_start, invoice_series_prefix)

department        (id, tenant_id, company_id, parent_id, name, cost_centre_code)

user              (id, tenant_id, authentik_sub, email, user_type, status)

user_group        (id, tenant_id, name)
user_group_member (user_group_id, user_id)

membership        (id, tenant_id, user_id, company_id, department_id, is_primary)

role              (id, tenant_id NULL=system, key, name)
role_permission   (role_id, permission_key)

role_assignment   (id, tenant_id, subject_type, subject_id, role_id,
                   scope_type, scope_id)
```

Notes:

- `department.parent_id` gives nested departments at no extra cost.
- `role.tenant_id IS NULL` marks a system role shared across all tenants. The preloaded set and the full permission catalogue are in [roles-permissions.md](roles-permissions.md).
- `role_assignment.subject_type` ∈ {`user`, `user_group`}; `scope_type` ∈ {`tenant`, `company`, `department`}.
- **`membership` and `role_assignment` stay separate.** Membership is org affiliation (org chart, default cost centre, approval routing) and can exist with no system access at all. Role assignment is authorization. Different lifecycles — HR changes vs security changes — and different reviewers.

---

### 4.2 Company — extended fields

> **Superseded by [company.md](company.md)** — the full design, covering tax system vs regime, jurisdiction profiles, statutory IDs, licences, the immutable-after-posting rule, and visibility. The list below is retained as the summary shape; `company.md` is authoritative where they differ.

```
company
  id, tenant_id, parent_company_id          -- parent enables group hierarchy
  code                                      -- short unique code; used in numbering
  legal_name, trade_name, display_name
  entity_type            -- pvt_ltd | llp | partnership | sole_prop | public | trust | branch
  registration_number    -- CIN / company-house number
  incorporation_date
  status                 -- active | suspended | closed

  -- financial
  base_currency, reporting_currency
  fiscal_year_start_month, fiscal_year_start_day
  books_begin_date                          -- earliest postable date
  amount_precision, rounding_mode

  -- invoicing defaults
  default_payment_terms_days
  tax_treatment_default  -- inclusive | exclusive
  invoice_series_prefix

  -- locale
  timezone, locale, date_format, number_format

  -- branding
  logo_url, signature_url, brand_color

  -- compliance
  einvoicing_enabled, withholding_tax_applicable

  -- extensibility
  custom_fields (JSON)
```

Anything that can legitimately occur more than once goes to a child table. Flattening these into the parent is the most common modelling mistake here — a company can hold several tax registrations (one per state under Indian GST), several bank accounts (one per currency), and several addresses.

```
company_address           (id, company_id, type, line1, line2, city, state,
                           state_code, postal_code, country_code, is_primary)
                           -- type: registered | billing | shipping | branch

company_tax_registration  (id, company_id, tax_system, regime, number,
                           jurisdiction_code, valid_from, valid_to, is_primary)
                           -- tax_system: gst_in | vat_gb | vat_ae | sales_tax_us | ...
                           -- regime:     regular | composition | flat_rate | ...
                           -- see company.md §2 — system and regime are two axes

company_statutory_id      (id, company_id, kind, value, value_last4,
                           issued_on, valid_to, verified_at)
                           -- kind: pan | tan | cin | ein | udyam | iec | aadhaar
                           -- AADHAAR/SSN store last4 only — company.md §4.3

company_licence           (id, company_id, kind, number, issuing_authority,
                           premises_address_id, valid_from, valid_to)
                           -- kind: drug_licence_20b | fssai | lut | ...
                           -- gates posting and prints on documents — company.md §4.4

company_contact           (id, company_id, type, name, designation, email, phone)
                           -- type: primary | finance | support | statutory

company_bank_account      (id, company_id, label, account_name, account_number,
                           iban, swift, ifsc, bank_name, branch, currency, is_primary)

company_document          (id, company_id, type, file_url, number,
                           issued_on, expires_on)
```

### 4.3 User — extended fields

```
user
  id, tenant_id
  authentik_sub                             -- unique; link to IdP
  user_type, status                         -- invited | active | suspended | deactivated

  -- name
  salutation, first_name, middle_name, last_name, display_name

  -- contact
  email, email_verified_at
  phone_country_code, phone, phone_verified_at

  -- org
  employee_code, job_title, reporting_manager_id
  default_company_id, default_department_id
  date_of_joining, date_of_exit

  -- preferences
  locale, timezone, date_format, number_format, currency_display
  theme, landing_page

  -- lifecycle
  invited_by, invited_at, activated_at, last_active_at
  deactivated_at, deactivated_by, deactivation_reason

  -- legal
  terms_accepted_at, terms_version, privacy_accepted_at

  -- extensibility
  custom_fields (JSON)
```

**Uniqueness (per §7, resolved):** users are tenant-scoped.

- `UNIQUE (tenant_id, email)` — the same address may exist in different tenants, as different people-in-context
- `UNIQUE (authentik_sub)` — one provider identity maps to exactly one user row (the column holds the active provider's subject, whichever it is)
- `tenant_id` is `NOT NULL` on every user

Deliberately **not** globally unique on `email`. That constraint is what would have to change if a global `principal` is ever introduced, so it is the only thing standing between the current model and that one.

```
user_notification_preference (user_id, channel, event_key, enabled)
                              -- channel: email | sms | whatsapp | push | in_app

user_identity                (user_id, provider, provider_sub)   -- multiple IdP links

user_api_token               (id, user_id, name, token_hash, scopes,
                              last_used_at, expires_at, revoked_at)
                              -- for user_type = service_account
```

**Do not store what Authentik owns:** password hashes, MFA secrets, session state, recovery codes. If the admin UI needs `mfa_enabled` or `last_login_at`, mirror them read-only via webhook and treat them as a cache — never as source of truth.

**Deactivation must anonymize, not delete.** A user who approved or issued invoices is referenced from the ledger forever, so the row cannot go away. Support replacing name, email, and phone with a tombstone while preserving `id` and `employee_code`. Deleting the row breaks referential integrity in `billing`; leaving PII in place breaks erasure requests.

### 4.4 Custom fields

> **Superseded by [custom-fields.md](custom-fields.md)** — the full design, covering data types, dynamic dropdowns, auto-numbering, validation, conditional visibility, and indexed search. The sketch below is the storage shape only.

The field lists above will never be complete, so make extension a first-class feature rather than a schema migration each time.

```
custom_field_definition (id, tenant_id, entity_type, key, label, data_type,
                         is_required, options_json, display_order, is_active)
                         -- entity_type: company | user | department | ...
                         -- data_type: text | number | date | bool | enum | reference
```

Values live in the entity's `custom_fields` JSON column. Definitions drive validation (built into the Pydantic model at request time) and form rendering in both clients.

Chosen over EAV: no join per field, no type-coercion table, and values arrive with the record. Per [tech-stack.md](tech-stack.md) rule 4.7, promote any custom field that needs filtering or sorting to an indexed generated column.

### 4.5 Lifecycle columns

Per [tech-stack.md](tech-stack.md) rule 4.12 — one mechanism per entity, never two.

| Entity | Mechanism |
|---|---|
| `tenant`, `user`, `company` | `status` enum (already defined above) |
| `department`, `role`, `user_group`, `custom_field_definition` | `is_active` + `deactivated_at`, `deactivated_by` |
| `membership` | `is_active` — ended affiliations stay for history |
| `role_assignment` | `is_active` + optional `valid_from` / `valid_to` for temporary elevation |
| `company_tax_registration` | `valid_from` / `valid_to` — **not** `is_active`; an old GSTIN must still be resolvable for invoices issued under it |
| `company_bank_account`, `company_address`, `company_contact` | `is_active` |
| `user_api_token` | `revoked_at` + `expires_at` (already defined) |

Deactivating a department or role must not hide it from historical records — invoices posted to a closed department still render that department.

### 4.6 Which company a session opens

A person may work in several companies, so every client has to answer "which one am I in". **The answer is resolved server-side**, by `GET /v1/session`, in four rules in this order:

| # | Rule | `selected_source` |
|---|---|---|
| 1 | the company named on the request (`?company_id=`) — an explicit switch | `explicit` |
| 2 | `user.default_company_id` — what this person chose for themselves | `default` |
| 3 | the company of their **primary** membership (`membership.is_primary`) | `membership` |
| 4 | the first company they can open, ordered by `code` | `first` |
|   | nothing matched | `none` |

The source is returned rather than inferred, because a client that showed a stored default and a first-readable fallback the same way would be claiming a preference nobody set.

- Rules 2–4 **fall through** when a candidate no longer exists, is not `active`, or is no longer readable: a stale default must not dead-end a session.
- They do **not** fall through when the candidate demands step-up (`company.requires_step_up`). That company is a valid selection whose details simply need a fresh proof, so the response withholds `company`, names it in `selected_company_id` and sets `step_up_required`. Quietly opening a *different* company instead is a wrong answer to "open my default".
- Rule 1 never falls through. An explicit switch that cannot be honoured is refused, so a caller learns their switch did not happen.
- Every candidate is checked with `company.read` at that company's own scope ([CLAUDE.md](../CLAUDE.md) §5.2). A membership is **affiliation, not authorization** (§2.3): rule 3 chooses *among* companies the actor may already open, and never grants one.

**The switcher's own list is `GET /v1/session/companies`** — an authenticated self-read, derived from the actor's grants (a company-scoped grant, a department-scoped grant's company, or every company for a tenant-scoped one). It needs no permission key: `GET /v1/companies` requires `company.read`, which the seeded clerk, approver and controller roles do not hold, and asking that endpoint "where may I work" is what left those roles with an empty switcher. It carries `id`, `code`, `display_name`, `requires_step_up` and `is_default` — nothing that describes a company — and field-policy read denies still apply.

**`default_company_id` is a self-write** on `PATCH /v1/session/preferences`. It confers no access, and it is validated against the same rule the chain applies, so a stored default is always one the chain will honour. Replacing it clears a `default_department_id` that belonged to the old company.

---

## 5. Traps

### 5.1 Tenant filtering must be enforced structurally

MariaDB has no row-level security ([tech-stack.md](tech-stack.md) rule 4.9), so `tenant_id` on every table is only as good as every query remembering to filter on it.

**Put the filter in the shared platform library as a SQLAlchemy session-level default**, not in per-query discipline. One forgotten `WHERE` clause is a cross-tenant data leak, and it will not show up in tests that use a single tenant's fixtures.

### 5.2 Do not put the permission set in the JWT

It is unbounded in size, and worse, a revoked role stays live for the token's lifetime.

- **In the token:** `tenant_id`, `user_id`, `user_type` — stable, small, needed on every request.
- **Resolved per request:** effective permissions, from a Redis cache keyed by user, invalidated on a `role_assignment.changed` event.

This refines rule 4.9 in tech-stack.md, which said to read roles from the token — that holds only while roles are few and unscoped.

### 5.3 Permissions are code, roles are data

Tenants may compose custom roles. They may not invent permissions. Once permission keys become user-editable rows, nothing in the codebase can be statically checked against them.

### 5.4 A department is not an approval chain

Approval routing will want amount thresholds, multi-step sequences, and delegation. Keep that as its own concern inside `billing`, referencing departments. Do not grow it into the org tree.

---

## 6. Table inventory & build order

`identity` is the **first API**, per [tech-stack.md](tech-stack.md) § *Build order*. Nothing else can be built first: every other service's tenant filter, permission check, and company reference resolves against what `identity` owns.

**But `libs/platform` comes before it and is not an API.** `identity`'s very first migration cannot be tested for cross-tenant isolation (CLAUDE.md §7) until the session-level tenant filter exists, and its first write cannot emit an audit event until the outbox writer exists. Phase 0 below is that minimum slice.

### 6.1 Reference tables — seeded, no `tenant_id`, code as PK

Per [tech-stack.md](tech-stack.md) § *Reference tables*. Present in **every** service DB, seeded from `libs/platform`.

```
country   (code CHAR(2) PK, iso3 CHAR(3), numeric_code, name, official_name,
           default_currency_code, phone_prefix, subdivision_label, is_active)
           -- subdivision_label: "State" | "Province" | "Emirate" | "County"

state     (code VARCHAR(6) PK,           -- ISO 3166-2, e.g. IN-MH, US-CA
           country_code CHAR(2) FK → country.code,
           name, subdivision_type,
           tax_jurisdiction_code,        -- GST state code: MH = 27. Prefixes every GSTIN
           is_active,
           UNIQUE (country_code, code))  -- supports the composite FK below

currency  (code CHAR(3) PK, numeric_code, name, symbol,
           minor_unit,                   -- JPY 0, most 2, KWD 3 — display & rounding
           is_active)

language  (code CHAR(2) PK, iso3 CHAR(3) UNIQUE, name, native_name, is_active)
timezone  (code VARCHAR(64) PK, name, is_active)
```

**`state.tax_jurisdiction_code` is the reason `state` is a table and not a string.** Maharashtra is `27`, and `27` is the first two digits of every Maharashtra GSTIN. Validating that a registration's GSTIN prefix matches its state is a real check that needs real data ([company.md](company.md) §4.2).

Regional selector amendment (2026-10-20): Identity materializes the existing shared
ISO language dataset and pinned IANA timezone catalogue. Tenant/setup language
choices store ISO 639-1 codes; timezone values store IANA identifiers. Translation
of UI labels remains deferred ([custom-fields.md](custom-fields.md) §13).

### 6.2 Company, country, state and currency

Answering the selection requirement directly:

```
company
  country_code  CHAR(2)    FK → country.code       [immutable after posting]
  state_code    VARCHAR(6) FK → state.code         [immutable after posting]
  base_currency CHAR(3)    FK → currency.code      [immutable after posting]

  FOREIGN KEY (country_code, state_code) REFERENCES state (country_code, code)
```

Three things worth being explicit about:

**The composite FK is the point.** A plain FK on each column separately permits `country_code = 'IN'` with `state_code = 'US-CA'`. The composite version makes that unrepresentable in the database, not merely unlikely. Same pattern on `company_address`.

**`company.state_code` is deliberately denormalized from the registered address.** It could be derived by joining to the primary `company_address`, and it must not be: place-of-supply resolution runs on **every invoice line**, deciding intra-state versus inter-state GST. That cannot depend on which address row currently carries `is_primary`, because flipping a flag on an address row would retrospectively change the tax treatment of issued invoices.

**Therefore `state_code` is immutable after first posting**, joining the [company.md](company.md) §5.2 list for exactly the same reason as `base_currency`: changing it flips every invoice between intra-state and inter-state. That is a new company, not a settings edit.

### 6.3 Full inventory — 35 tables

| # | Table | Group | Phase |
|---|---|---|---|
| 1 | `country` | Reference | 1 |
| 2 | `state` | Reference | 1 |
| 3 | `currency` | Reference | 1 |
| 4 | `language` | Reference | materialized in Identity by 0072 |
| 5 | `outbox` | Platform mechanism | 0 |
| 6 | `processed_message` | Platform mechanism | 0 |
| 7 | `idempotency_key` | Platform mechanism | 0 |
| 8 | `tenant` | Tenant & structure | 2 |
| 9 | `plan` | Tenant & structure | *deferred* |
| 10 | `company` | Tenant & structure | 3 |
| 11 | `company_address` | Tenant & structure | 3 |
| 12 | `company_tax_registration` | Tenant & structure | 4 |
| 13 | `company_statutory_id` | Tenant & structure | 4 |
| 14 | `company_licence` | Tenant & structure | 4 |
| 15 | `company_contact` | Tenant & structure | 7 |
| 16 | `company_bank_account` | Tenant & structure | 7 |
| 17 | `company_document` | Tenant & structure | 7 |
| 18 | `department` | Tenant & structure | 6 |
| 18a | `company_feature` | Tenant & structure | 3 |
| 19 | `user` | Identity | 5 |
| 20 | `user_identity` | Identity | 5 |
| 21 | `user_notification_preference` | Identity | 7 |
| 22 | `user_api_token` | Identity | 7 |
| 23 | `user_group` | Identity | 6 |
| 24 | `user_group_member` | Identity | 6 |
| 25 | `membership` | Identity | 6 |
| 26 | `impersonation_session` | Identity | 8 |
| 27 | `role` | Authorization | 5 |
| 28 | `role_permission` | Authorization | 5 |
| 29 | `role_assignment` | Authorization | 5 |
| 30 | `field_policy` | Authorization | 9 |
| 31 | `custom_field_definition` | Extensibility | 10 |
| 32 | `field_config` | Extensibility | 10 |
| 33 | `custom_field_value_index` | Extensibility | 10 |
| 34 | `custom_field_sequence` | Extensibility | 10 |

Notes on the four that are not obvious:

- **`outbox`, `processed_message`, `idempotency_key`** are defined by `libs/platform` but are real tables in each service's own database, so they need migrations in `dbs/identity/` like anything else.
- **`impersonation_session`** is a table rather than a Redis key so that a session left open by a crashed process is still discoverable and closable. CLAUDE.md §5.5 requires impersonation be time-bound and audited at both ends; a TTL that evaporates has no end event.
- **`custom_field_value_index` and `custom_field_sequence`** live in the entity's own service ([custom-fields.md](custom-fields.md) §3). `identity` needs its own copies because it owns entities that take custom fields — `company`, `user`, `department`.
- **`field_config`** supersedes the narrower `custom_field_override`: one table configures show/hide, requiredness, order and label for **native** columns as well as custom definitions, because the client renders one merged field set ([identity-schema.md](identity-schema.md) §6.2). The native fields it overrides are a **code catalogue**, not a table.
- **`plan`** is deferred pending the open question of whether we bill our own tenants in this system or externally. `tenant.plan_id` stays nullable until then.
- **Step-up sessions** ([company.md](company.md) §6.3) are Redis with a TTL, not a table — a lapsed step-up needs no closing event, only re-challenge.

### 6.4 Start with these ten

34 tables is four to six weeks before anything is demonstrable. It is not the first milestone. **This subset is:**

```
country · state · currency          -- selection works
outbox                              -- audit and events work from the first write
tenant · company                    -- core columns only; children come later
user
role · role_permission · role_assignment
```

Ten tables gets a working, secured, testable service: a tenant exists, it has a company with a valid country/state/currency, a user can authenticate against Authentik, and permissions resolve server-side. Every subsequent phase layers onto a green suite rather than extending an unfinished one.

Deliberately **not** in the first ten: `membership` (authorization works without org affiliation — §4.1 keeps them separate for exactly this reason), the company child tables, custom fields, and field policies.

### 6.5 Phase sequence

| Phase | Deliverable | Ends when |
|---|---|---|
| **0** | `libs/platform` minimum: base model, UUIDv7, session-level tenant filter, `Decimal` helpers, error envelope, outbox writer, test helpers, **field-registry types + boot validation** | Tenant filter has a two-tenant isolation test; 90% coverage floor met; a registry key naming a non-existent column fails the boot |
| **1** | Reference tables + seeds + lookup endpoints | Composite `(country, state)` FK proven to reject a mismatched pair |
| **2** | `tenant` + tenant provisioning | Cross-tenant isolation test |
| **3** | `company` core + `company_address` + `company_feature` + §5.2 immutability guard + **`FIELD_REGISTRY["identity.company"]` and the `field-set` endpoint, registry-only** | Currency/fiscal/state change after a simulated posting is rejected for **every** actor; feature dependency and ratchet tested; the web company form renders from `field-set`, not a hardcoded list |
| **4** | Tax registration, statutory IDs, licences | `posting_date` resolution; overlap rejected; AADHAAR full value proven never persisted, logged, or returned |
| **5** | `user`, `user_identity`, roles, assignments, Authentik/JWKS validation, Redis permission resolution | 401 / 403 / wrong-company-403 per endpoint; escalation guards tested |
| **6** | `department`, `user_group`, `membership`, scope resolution | Ancestor-or-self resolution tested at all three scopes |
| **7** | Remaining child tables | Redaction of bank details in logs verified |
| **8** | Impersonation + company visibility + step-up | Unlisted company still present in audit and in an authorized tenant-wide report |
| **9** | `field_policy` + `assert_fields_writable` | Diff-against-current-state, not payload presence |
| **10** | `field_config` (native-field show/hide, require, reorder, relabel) + custom fields + the merged `field-set` resolver | Non-`hideable` field rejects `is_visible = false`; requiredness cannot be loosened; a hidden field is still accepted by the API and still present in exports; rule-tree fixtures green in Python and both clients |

Phases 3 and 5 are the ones to slow down on. Phase 3 holds the irreversible-field guard; Phase 5 holds every authorization decision the other six services will trust.

**Why the `field-set` endpoint appears in Phase 3 and not Phase 10.** Tenant-configurable fields mean no client may hardcode a form. If the company form is built against a hardcoded field list in Phase 3 and switched to a resolver in Phase 10, it gets built twice — and the second build is the one that has to handle ordering, grouping, conditional visibility and relabelling retrofitted into finished components. So the **contract** ships in Phase 3 returning registry-only output with no overrides; Phase 10 only adds `field_config` and custom definitions to what it merges. The client code does not change.

---

## 7. Open questions

- [x] **Can one human belong to multiple tenants?** **Resolved 2026-09-03: no.** A `user` row is tenant-scoped — an accountant serving three client tenants is three user rows with three logins. Chosen for isolation simplicity: there is no join to traverse and no path by which one login resolves to two tenants. Accepted cost: no single sign-on across tenants, and no "all my tenants" view. The rejected alternative was a global `principal` with per-tenant user records. Revisiting means adding `principal` and touching every auth resolution path — see §4.3 for the constraint that keeps that door open.
- [ ] Multi-company needed at launch, or one company per tenant to start? (§2.1)
- [ ] Are nested departments needed, or is one flat level per company enough?
- [ ] Tenant-custom roles at launch, or system roles only for v1? (System roles are defined — see [roles-permissions.md](roles-permissions.md) §4. Custom roles need the clone-a-system-role flow in §1.2)
- [ ] Can user groups nest? Recommend no — flat groups, composed via multiple role assignments
- [ ] Invoice number series: per company (assumed here) or per company + fiscal year?
- [ ] Does `customer_portal_user` live in the same `user` table, or separately? Same table assumed; revisit if the portal grows its own profile requirements
- [x] **Initial permission catalogue** — **resolved: see [roles-permissions.md](roles-permissions.md) §2** for the `resource.action` list per service, and §4 for the preloaded system roles that bundle them

Decision 2026-10-21: tenant creation uses Country/State selectors with other
regional defaults resolved by Identity. The optional tenant default state is a
company-creation default, not a tax registration or company creation itself.
Workspace slugs are backend-generated from UUIDv7 and not shown as user inputs.

## Organisation administration delivery — 2026-10-24

The six core masters have administration entry points documented in
[organisation-access-delivery.md](organisation-access-delivery.md). Departments are
company-scoped; user groups remain tenant subjects. Department/group forms derive
their native fields from the strict API schemas. This does not register a new
custom-field or field-policy surface for these entities.

User details expose reviewed company/department affiliation add, end and primary
actions using the existing membership aggregate. A company administrator can manage
the affiliations of users already readable through that company's people projection;
tenant-wide profiles and groups retain tenant authority. Affiliation never grants a
role. Existing users outside that company are affiliated through tenant administration.
Ended associations remain retained; duplicate/recreation attempts report a conflict.

Decision log: reuse the existing nested-department and scoped-group mechanisms;
do not resolve the open launch-depth question or introduce tenant switching through
this UI work. Lean directory contracts and signed cursor bindings remain mandatory.
