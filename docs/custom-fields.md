# Custom Fields

**Status:** Shared mechanism and Identity/Catalog/Vouchers backend support implemented; other consumers remain planned
**Date:** 2026-09-15
**Master:** `identity` · **Machinery:** `libs/platform` · **Consumers:** every service
**Related:** [tech-stack.md](tech-stack.md) rules 4.7 (JSON), 4.12 (lifecycle) · [org-model.md](org-model.md) §4.4 · [audit.md](audit.md) · [fiscal-year.md](fiscal-year.md) §7 (sequences)

Supersedes the sketch in [org-model.md](org-model.md) §4.4.

---

## 1. Goal and boundary

An admin adds fields to an entity — say two extra fields on `item`, for one company only — with **no migration, no deploy, no code change**.

### Achievable at runtime, by configuration

Adding, reordering, relabelling, deactivating fields · all data types in §4 · required, regex, min/max, length, precision, uniqueness · static dropdowns · cascading dropdowns over registered sources · conditional show/hide · per-company scoping and overrides · auto-numbering with prefix, padding, and reset cycle.

### Deliberately requires a code change

| Change | Why it must be code |
|---|---|
| A genuinely new **data type** | Needs storage, coercion, validation, and a renderer in both clients |
| A new **dynamic option source** | An admin-supplied query or URL would be SQL injection and SSRF. Sources are whitelisted resolvers — see §4.3 |
| A new **entity type** accepting custom fields | The owning service must register it and declare which native fields conditions may reference |

This mirrors an existing rule: **permissions are code, roles are data** (CLAUDE.md invariant 13). Here, *types, sources, and entities are code; fields are data.*

---

## 2. Where it lives

Definitions are read on the **write path** of every service — an incoming `item` cannot be validated without them. Per [tech-stack.md](tech-stack.md) § *Reference data ownership*, that means they must be local to the service doing the write, never fetched synchronously.

Identity owns authored definitions, layouts and field policies. Its authenticated Catalog
snapshot/change contract supplies company-scoped local projections. Catalog checks source
freshness and actor authority before using them; product writes do not call Identity.

New product definitions have `requires_adoption=true`. A company continues using its last
accepted validation contract while a new candidate synchronizes. An administrator reviews
the affected products, resolves reported issues, and adopts that exact candidate. A signed,
actor-bound review token expires after 15 minutes and is invalidated by changed definitions,
values, row versions or uniqueness state. The Console also compares Identity and Catalog
source definition digests before offering adoption. Layout and access policies remain live;
a layout cannot lower a definition's requiredness. Existing unflagged definitions retain
legacy immediate resolution for compatibility.

`libs/platform` supplies pure typed validation, condition evaluation, metadata resolution
and canonical value rules. Each owner implements its storage, transaction, option lookup,
authorization and sequence adapters. The shared `@janso/ui` renderer supplies presentation.

### Vouchers consumer (implemented 2026-10-10; reviewed 2026-10-11)

[Voucher extensibility](voucher-extensibility.md) adds typed custom fields to voucher headers
and individual item lines, independently of existing Catalog item-master attributes. Entity
keys `vouchers.voucher` and `vouchers.voucher_item` are accepted by Identity definition
administration and projected to Vouchers. The backend uses the 12 existing data types,
shared validation/metadata, local accepted contracts, adoption, field policies and
same-transaction indexes/claims/sequences. Vouchers owns native
versioned type/profile bindings, values and historical snapshots; Identity owns definitions.
Bindings cannot weaken validation or access rules. Neither tax/stock behavior nor job-work
ownership/deadlines may be implemented as custom fields. The
[2026-10-11 review](voucher-custom-attribute-review.md) records the saved-revision metadata
read and conditional-field fix; UI remains deferred.

---

## 3. Tables

All in the master (`identity`) and mirrored to replicas.

```
custom_field_definition
  id, tenant_id
  company_id                NULL = applies to every company in the tenant
  entity_type               key into the code-defined entity registry (§4.4)
  key                       stable identifier; IMMUTABLE after create
  label, help_text, placeholder
  data_type                 see §4
  display_order, display_group
  is_active                 (rule 4.12 — this entity uses is_active, not status)
  is_searchable             drives projection into the index table (§7)
  is_immutable_after_create
  validation      (JSON)    §5
  options         (JSON)    static select choices
  option_source_key         dynamic_select only — registered resolver key
  depends_on_key            cascading parent field
  visibility      (JSON)    condition rule tree, §6
  sequence_config (JSON)    auto_number only
  default_value
  created_at/by, updated_at/by

  UNIQUE (tenant_id, company_id, entity_type, key)
```

> **`custom_field_override` is superseded by `field_config`** — see [identity-schema.md](identity-schema.md) §6.2 for the authoritative definition.
>
> It did what its name says: let one tenant-wide custom field be required in Company A and optional in Company B without duplicating the definition. It was then generalized, because a tenant admin configuring a form does not think in terms of "custom" versus "native" — they want to hide `company.industry_code`, rename `trade_name`, and add a field, in one screen. The client renders **one merged, ordered field set**, so there is one table configuring it, with a `field_source` discriminator.
>
> What that adds beyond this doc: a code-defined `FIELD_REGISTRY` of native fields per entity, marking each `hideable` / `renameable` / `required`; requiredness that may only tighten; and the five-step resolver that keeps tenant **layout** (step 3) strictly separate from per-actor **access** (step 5).

```
custom_field_value_index
  tenant_id, company_id, entity_type, entity_id, definition_id
  value_text, value_number, value_date, value_bool
  PRIMARY KEY (entity_type, entity_id, definition_id)
  INDEX (definition_id, value_text)
  INDEX (definition_id, value_number)
  INDEX (definition_id, value_date)
```

Lives in the **entity's own service**, not `identity`. Written only for `is_searchable` definitions. See §7.

```
custom_field_sequence
  id, tenant_id, company_id, definition_id, cycle_key, next_value
  UNIQUE (definition_id, company_id, cycle_key)
```

`auto_number` state. Lives in the entity's service. `cycle_key` is `''`, a `fiscal_year_id`, `'2026'`, or `'2026-09'` depending on `reset`.

**Values themselves live in the entity's `custom_fields` JSON column** — one read, no join, for the common display path.

---

## 4. Data types

### 4.1 Scalar

`text` · `long_text` · `integer` · `decimal` · `boolean` · `date` · `datetime` · `currency_amount`

`decimal` and `currency_amount` are stored as strings in JSON and coerced to `Decimal` — never through `float` (invariant 1). `currency_amount` carries a sibling currency key.

`date` and `datetime` are distinct: business dates never become datetimes (CLAUDE.md §4).

### 4.2 Static select

`select` / `multi_select`, choices in `options`:

```json
{"choices": [
  {"value": "raw", "label": "Raw material"},
  {"value": "fg",  "label": "Finished goods", "is_active": true}
]}
```

Choices deactivate rather than delete — a value already stored on an item must still render (rule 4.12).

### 4.3 Dynamic select

`dynamic_select`, bound to a **registered resolver**, never a URL or query:

```python
@option_source("catalog.item_category")
def item_categories(ctx: SourceContext) -> list[Option]:
    # ctx carries tenant_id, company_id, actor, parent_value
    ...
```

The definition stores `option_source_key`. Admins pick from the registered list; they cannot type a query, an endpoint, or a table name. **This is the security boundary of the whole feature** — see §9.

`depends_on_key` gives cascading dropdowns (State → City): the child's resolver receives the parent's value in `ctx.parent_value`.

Cross-service sources are resolved from the local replica or a cached projection — never a synchronous call inside a write transaction (invariant 7).

### 4.4 Entity registry

Code-defined, contributed by the owning service:

```python
register_entity(
    "catalog.item",
    native_fields_for_conditions=["item_type", "is_taxable", "uom"],
)
```

`native_fields_for_conditions` is the whitelist of the entity's own columns that a visibility rule may reference (§6). Anything not listed is unreachable, so conditions cannot be used to probe fields the admin shouldn't see.

### 4.5 Auto-number

The only stateful type. Reuses the document-sequence pattern from [fiscal-year.md](fiscal-year.md) §7.

```json
{"prefix": "IT-", "padding": 5, "start": 1, "reset": "calendar_year"}
```

`reset` ∈ `never | fiscal_year | calendar_year | month`. Yields `IT-00042`.

Rules:

- Allocated **on create only**, inside the entity's transaction, via `SELECT ... FOR UPDATE` on the `custom_field_sequence` row. `READ COMMITTED` (rule 4.2) makes this safe without gap locks.
- **Always read-only to users.** Never accepts input, never subject to `required` validation, never editable — so `is_immutable_after_create` is implied and forced.
- **Not gap-free.** Allocation and entity creation roll back together. Deletion, abandoned committed records and explicit resets can still leave gaps; this is not statutory numbering. If gap-free numbering is ever needed, that is an invoice-series requirement and belongs in `document_sequence`, not here.
- Deactivating a definition does **not** reset its sequence. Reactivation continues where it stopped.

---

## 5. Validation

```json
{
  "required": true,
  "min": "0", "max": "9999",
  "min_length": 3, "max_length": 64,
  "regex": "^[A-Z]{2}-\\d{4}$",
  "regex_message": "Must look like AB-1234",
  "decimal_places": 2,
  "unique_within": "company"
}
```

`unique_within` ∈ `none | company | tenant`, enforced through transactional `custom_field_unique_claim` records in Catalog — which is why a unique custom field must also be `is_searchable`. Reject the combination at definition time if it isn't.

`regex_message` matters: a raw pattern in an error message is unusable to an end user.

### Validation pipeline

Order is not arbitrary — steps 2–4 are what make conditional fields safe.

1. Resolve tenant/company definitions, accepted product contracts, feature gates and layout.
2. Apply defaults on create before evaluating conditions. JSON-encoded defaults retain their
   declared scalar/list/object type; legacy unquoted text remains readable. Defaults do not
   silently populate existing products during readiness checks or adoption.
3. Enforce readable dependencies and field write policies; evaluate visibility against the
   combined native/custom values. Reject changed values for conditionally hidden or retired fields.
4. Require visible mandatory values. Layout requiredness can strengthen this requirement.
5. Validate exact types, bounds, regex and option membership. An unchanged saved retired
   choice or retired field is preserved; new retired selections are rejected.
6. Persist values, unique claims, prepared scalar/member index generations, row version and
   audit/outbox together. Auto-number allocation belongs to this same transaction.

Activation independently validates the stored family and item contracts. Active products
accept descriptive changes (item name; family name/description/model code; authorized custom
values). Structural changes remain governed by their dedicated commands and lifecycle rules.

---

## 6. Conditional show/hide

A **declarative rule tree**, not an expression string. No `eval`, no interpreter, no admin-authored code.

```json
{"op": "and", "rules": [
  {"field": "item_type", "cmp": "eq", "value": "service"},
  {"op": "or", "rules": [
    {"field": "cf_hsn", "cmp": "not_empty"},
    {"field": "cf_sac", "cmp": "not_empty"}
  ]}
]}
```

- Operators: `and`, `or`, `not`
- Comparisons: `eq`, `ne`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`, `empty`, `not_empty`, `matches`
- `field` may reference another custom field's `key`, or a native field from the entity's whitelist (§4.4). Nothing else resolves.
- Depth capped; cycles rejected at definition-save time.

**The tree is evaluated by the server and the shared TypeScript web renderer.** Clients use it to show and hide; the server uses it to decide what is required and what is permitted (§5, steps 2–4). Client-side evaluation is presentation, never enforcement.

**Two implementations will drift.** Mitigation: one JSON fixture set of rule-tree cases with expected outcomes, executed by the Python and shared TypeScript suites. Adding a comparison operator means adding fixtures, which fail in whichever runtime hasn't implemented it.

---

## 7. Storage and search

Two representations, written together:

| | Purpose | Cost |
|---|---|---|
| `custom_fields` JSON on the entity | Display and API reads — arrives with the record, no join | None |
| `custom_field_value_index` rows | Filtering, sorting, uniqueness | One row per searchable field per record |

MariaDB's `JSON` is not natively indexable (rule 4.7). The documented workaround — promote to an indexed generated column — is a **migration**, which defeats the entire purpose. Hence the index table: it delivers indexed search with no schema change, ever.

- Only `is_searchable` definitions produce index rows.
- Product adoption prepares claims and searchable generations atomically. Ordinary writes refuse an unprepared searchable contract. The existing index rebuild worker supports bounded chunks and retained-generation cleanup.
- Filtered list queries join the index table; unfiltered reads never touch it.
- Write amplification is proportional to searchable fields only. Keep `is_searchable` off by default and make the admin opt in — the field count grows quietly otherwise.

---

## 8. Client contract

Identity administration:

- `GET/POST /v1/custom-field-definitions`; filter GET by `entity_type` and `company_id`.
- `GET/PUT /v1/custom-field-definitions/{id}`. Product PUT requires the current `expected_digest`.
- `GET /v1/entities/{entity}/custom-field-contract?company_id=...` exposes registered native
  fields and closed option sources; generated from Catalog's owner registry.
- `GET /v1/entities/{entity}/field-config` and `PUT .../field-config/{field_key}` support
  product `company_id`; `field-policies` supports product definitions and company listing.

Catalog uses `/v1/companies/{company}` as its prefix:

- `GET /entities/{entity}/field-set?operation=create|update`; update can include `object_id`.
  Metadata includes `source_version` and `adoption_version`, authorized fields and stored
  retired values as readonly descriptors. Object metadata honors item/family lifecycle.
- `GET /option-sources/{source}` supplies bounded, authorized dynamic choices. Cascading
  requests include `parent_id`; the server validates the parent/source relationship.
- `POST /entities/{entity}/custom-field-adoption/preview` returns definitions, source digests,
  eligibility and owner/key issues without stored values.
- `POST /entities/{entity}/custom-field-adoption` accepts `preview_token` and requires an
  `Idempotency-Key`. Current actor permissions are rechecked on receipt replay.
- Existing product-family/item create and PATCH APIs accept the `custom_fields` map. PATCH
  supplies `expected_version` and an idempotency key, and sends only changed custom values.

`entity` is `catalog.product_family` or `catalog.item`. The Console page is
`/products/custom-fields`. It manages definitions, reviews adoption and edits saved values.
`CustomFields` and `CustomFieldEditor` live in `@janso/ui`; consumers never hard-code custom
keys. Definition/layout/policy authorization stays on the server. The editor authors a
single visibility condition and preserves existing compound trees; the API accepts the full
bounded tree. Mobile consumption is not implemented by this change.

---

## 9. Security

This feature takes admin-authored configuration and executes it against the database, so it is the largest new attack surface in the system.

1. **Option sources are code-registered resolvers.** No admin-supplied SQL, table name, endpoint, or URL — that would be injection and SSRF in one field.
2. **Conditions are a data structure, never an expression string.** No `eval`, no template engine, no arbitrary comparison functions.
3. **Admin-authored regex is a ReDoS vector.** The shared v1 validator accepts only bounded literals, character classes, anchors and fixed repetitions. It rejects groups, alternatives, backreferences and variable quantifiers, caps pattern/input sizes, and validates at definition ingest. General regex support is unavailable; adding it requires a bounded-time engine and review. `(a+)+$` is rejected.
4. **Definition writes need their own permission** — `custom_field.manage`, at company scope. Editing definitions is an administrative act, not a data edit.
5. **Server-side revalidation of everything.** Option membership, visibility, required — all recomputed server-side. The client payload is a hint.
6. **Custom fields obey tenant and company scoping like any other data**, through the session-level filter (invariant 3). A definition scoped to Company A must not resolve for Company B.
7. **No PII shortcuts.** A custom field holding personal data is still subject to erasure. Do not use custom fields to stash data that native columns deliberately don't hold.

---

## 10. Audit

- **Value changes** appear in the audit event's `changes` JSON exactly like native fields, keyed by definition `key`.
- **Definition changes** are `admin`-category audit events in their own right — who added a field, changed a validation rule, or deactivated one.
- Auto-number allocations are recorded on the create event.

---

## 11. Governance — the rule that keeps this maintainable

**Domain logic must never read a custom field.**

Custom fields may be stored, validated, displayed, exported, and reported on. They must not be read by pricing, tax calculation, posting, approval routing, or any ledger path.

The moment a custom field drives money, three things become true at once: it needs a migration-backed column for indexing, it needs a real test suite, and it can no longer be deactivated by an admin without breaking the books. At that point it is a native field wearing a costume — promote it properly, with a migration, a model change, and a backfill.

Anything else, and every calculation in the system implicitly depends on runtime configuration nobody reviewed.

---

## 12. Limitations, stated plainly

- Searchable fields require transactional scalar/member index maintenance. Member filters use correlated EXISTS, which does not multiply entity rows.
- Sorting across a mix of custom and native fields needs the join and will not use a covering index.
- Auto-number is not gap-free and cannot be made so without becoming `document_sequence`.
- Python and TypeScript execute the same fixture file at `libs/platform/tests/fixtures/custom-field-conditions.json`; server validation remains authoritative.
- No cross-entity conditions — a rule on `item` cannot reference a field on `invoice`.
- No computed or formula fields. A field whose value derives from others is domain logic (§11).

---

## 13. Open questions

- [ ] Do custom fields need to appear on printed documents (invoice PDFs)? If yes, templates need a generic block and the PDF layer needs the definitions
- [ ] Should `reports` expose custom fields as report columns automatically, or only `is_searchable` ones?
- [x] Field-level permissions — **resolved: see [field-permissions.md](field-permissions.md).** All custom fields are protectable by default, referenced as `custom_field:<key>`; no per-field registration needed since they are already admin-defined data
- [x] Shared v1 safety caps: 128 effective definitions, 4096 long-text characters, 512 indexed scalar characters after normalization, 200 static choices, 100 selected members and 1024 index rows per owner update across active/building generations. These are input safety bounds, not measured production workload targets.
- [ ] Multi-language labels — is `label` per-locale, or single-language for v1?
- [x] Multi-select uses one member row per selection/generation; has-any/has-all compile to EXISTS. No joined aggregate value or duplicate-producing list join.

## 14. Product rollout and operational bounds

1. Create/adopt an optional contract first when existing products need values. Populate values
   through versioned product PATCH or the existing reviewed bulk `UPDATE` workflow, whose
   bounded worker checkpoints and receipts reuse native commands. Defaults never replace
   explicit backfill decisions. Auto-number fields allocate only on new product creation.
2. Propose tightened validation, requiredness or uniqueness; review all affected owners.
   Adoption checks at most 1000 owners and refuses larger populations without partial
   approval. Issues are reported up to 200 entries; any issue blocks commit. Tenant-wide
   uniqueness scans all companies, needs tenant-wide permissions and readable affected fields,
   and serializes claim writers through the tenant contract row.
3. Adopt the reviewed result. The transaction prepares unique claims and scalar/member indexes,
   saves the accepted contract and increments policy generation. Pending index build/cleanup
   must finish first. Used types, sequences and uniqueness comparison semantics cannot change
   through adoption. Historical claims are retained to prevent accidental reuse.

Identity migration `0058` and Catalog migrations `0129`/`0130` add the adoption flag and
accepted contract storage. Each revision contains one DDL operation; downgrade is blocked
where it would discard accepted contracts. Apply them before exposing the new routes/source
payload. No business database migration is performed by this implementation task.

The Console server needs the existing `AUTH_URL`, `NEXTAUTH_SECRET`, `IDENTITY_URL`, plus
`CATALOG_GATEWAY_URL` pointing to the configured gateway base that accepts Catalog `/v1/...`
paths and validates bearer tokens. Never point it at a direct actor-header-only API. The
proxy accepts only listed methods/routes, uses same-origin requests and server-held tokens,
forwards company step-up proof, refuses redirects and retains idempotency keys for retries.
Absent configuration returns 503. No browser token or operator-supplied target URL is used.

Refresh contracts with the owner tools `apis/catalog/tools/export_field_contract.py` and
both services' `tools/export_openapi.py`, then run the API client generator for `catalog`
and `identity`. `billing-platform` is 0.24.0; its consuming lockfiles were refreshed.

Verification uses synthetic ASGI/SQLite and component/proxy tests. Live MySQL locking,
broker synchronization and browser sessions against a deployed gateway still require the
integration environment. The 1000-owner adoption cap is a safety bound, not a performance
claim. A larger resumable adoption workflow is outside this bounded implementation.

## Decision log

- 2026-10-11: Updated the stale Vouchers planning status after verifying the existing
  Identity/Vouchers backend. Saved voucher revisions now expose their pinned field metadata;
  custom-to-custom conditions and field-set disclosure honor current read denies. See the
  [review](voucher-custom-attribute-review.md). The 2026-10-10 entry describes the earlier
  planning change, not today's implementation state.

- 2026-10-10: Corrected the stale unimplemented status to reflect existing Identity/Catalog
  support. User requested voucher and item custom attributes; added the planned Vouchers
  header/item-line consumer and runtime type bindings, reusing existing machinery. No registry
  or API support was implemented by this planning change.

- 2026-09-11: Added shared validation/layout/query mechanisms and Catalog value stores with
  same-transaction claims/sequences. Corrected the earlier claim that rollback necessarily
  consumes a number; no gap-free guarantee was introduced. Adopted bounded linear regex and
  typed EXISTS membership, and recorded input caps. Source/API/rebuild integration remains open.

- 2026-09-15: Implemented product definition administration, accepted-contract adoption,
  stored readiness validation, active descriptive maintenance, shared forms and two review/fix
  passes. See `product-configuration-todo.md` and the retained verification artifacts.
