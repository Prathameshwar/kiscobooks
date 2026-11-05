# Voucher types and typed custom fields

**Date:** 2026-10-10. **Status:** Backend custom-field foundation implemented; UI deferred.
**Read with:** [Vouchers](vouchers-plan.md), [custom fields](custom-fields.md),
[field permissions](field-permissions.md) and [Catalog metadata](catalog-field-metadata-options.md).
**Storage contract:** [Shared voucher tables](voucher-data-model.md) apply to every kind/type.
Header custom fields live on the revision; ITEM-line fields live on its common line. The
proposed `vouchers.voucher_item` metadata entity does not imply an independent voucher-kind table.

**Native behavior contract:** The [all-voucher configuration contract](voucher-configuration-design.md) defines the shared
settings registry, 22-kind capture/effect matrix, native policy storage and VCF01-VCF24.
Commercial controls are one family; descriptive custom attributes remain separate.

## 1. Extensible voucher types

The 22 non-payroll kinds are the initial catalogue, not a permanent limit on the product.
Authorized administrators can create additional company voucher types at runtime from a
supported kind/profile: Retail Sales, Export Sales, Subcontractor Payment or Repair Job Work,
for example. Creating such a type needs no deployment or per-type database migration.
Adding a genuinely new posting behavior requires a reviewed implementation of a new kind or
profile, with its own validation, permissions, tax treatment and tests. A name or script cannot
invent accounting or stock effects. Payroll and related HR work remain excluded.

Keep stable system kind/profile identifiers and protected system templates. Company types
have their own ID, company-unique code, name, base kind/profile, origin/template version,
versioned numbering configuration, allowed modes/classes, approval configuration, print
layout and field bindings. Cloning makes an explicit copy; later parent/template changes
never silently change an existing company's type. A template grants no action permission.
Clone/version the type's section configuration as well: required/optional/forbidden details,
supported entry modes and code-defined conditional requirements. No per-type table is created.
Required native sections and authorization cannot be weakened through layout or field bindings.

Issued/posted vouchers pin the type revision. Retire used types instead of deleting them;
historical documents remain readable. Changing the base kind of a used type requires a new
type, not reinterpretation of old vouchers. Administrators may tighten supported controls,
but cannot remove required native fields, bypass tax rules, or make a posting kind non-posting
through descriptive metadata. Type creation and use are separately authorized.

### 1.1 Commercial behavior controls

The [commercial configuration contract](voucher-commercial-configuration.md) adds versioned
company Sales/Purchase policies and narrower type/class rules for tax, discount scopes, charge
recipes, zero-valued items, manual bonus quantity and automatic deals. These are native
behavioral controls, separate from custom fields and layout. Classes supply permitted defaults;
they cannot enable a forbidden component or bypass product/actor/legal requirements.
Cloning copies explicit bindings/defaults, not permission or executable promotion support.
Publish only compatible rules and retain effective-policy evidence on documents/quotes.

## 2. Three distinct places for attributes

| Scope | Owner and proposed entity | Purpose |
|---|---|---|
| Item master | Existing Catalog `catalog.item` / `catalog.product_family` | Reusable product facts; retain Catalog's native attributes/options/variant model and existing custom fields |
| Voucher header | Vouchers; proposed `vouchers.voucher` | Extra document information such as an external job reference or inspection note |
| Voucher item line | Vouchers; proposed `vouchers.voucher_item` | Transaction-specific information such as a customer marking instruction on one line |

The two Vouchers entity keys are registered in Identity and projected to Vouchers.
Each item line has a stable local ID, even when the same SKU appears twice. Header fields
and line fields are independent. Product attributes may be displayed from a versioned item
snapshot; editing line custom fields never edits the Catalog item or its variants. Expose
master attributes and transaction fields in separate namespaces with explicit provenance.

Tax classification, stock ownership, job order, consumption, yield, scrap, quantities, price,
discount, cost and posting accounts remain native typed fields. Custom fields cannot calculate
prices/tax, allocate stock, select posting behavior or route approvals. A business attribute
that acquires one of those responsibilities must be promoted through a normal schema change.

## 3. Reuse the existing platform

Identity already authors typed definitions, layout and field policies; Catalog consumes local
projections and accepted validation contracts. `libs/platform` already supplies typed value
validation, condition evaluation, canonical values and merged field metadata. Reuse these
and `@janso/ui` forms instead of creating a separate voucher attribute engine.

Identity's definition entity allowlist, native-field registry, projection contracts,
permissions and generated clients support the two Vouchers entities.
Vouchers owns company/type/profile bindings that select header/line fields and may tighten
their applicability/requiredness. Identity remains the definition/policy authority. A binding
cannot weaken the accepted definition or an access deny. Exact binding precedence is a V1
contract: resolve entity/company definitions, then type/profile restrictions, then live actor
access; reject incompatible configurations before publishing a type revision.

The existing 12 data types are the starting contract:

| Data type | Example or use |
|---|---|
| `text` | Short external reference |
| `long_text` | Detailed descriptive instructions |
| `integer` | Descriptive whole-number measurement |
| `decimal` | Descriptive decimal measurement, stored without float conversion |
| `boolean` | An informational yes/no answer |
| `date` | An informational business date |
| `datetime` | An informational timestamp |
| `currency_amount` | A descriptive amount with currency; never an invoice total or posting input |
| `select` | One configured choice |
| `multi_select` | Several configured choices |
| `dynamic_select` | A choice from an authorized, registered option source |
| `auto_number` | A generated auxiliary reference, separate from statutory voucher numbering |

Definitions retain a stable `cf_` key, labels/help, data type, scope, default, requiredness,
min/max, length/precision, bounded regex, choices/source, conditional display, searchability,
immutability and supported uniqueness rules. No administrator-supplied SQL, arbitrary URLs,
executable formulas or new data types. Display conditions are layout, never authorization.
Registered dynamic sources use local, scoped data and cannot leak denied fields.

Store validated values in `custom_fields` JSON on header and item-line revisions, not dynamic
SQL columns. Reuse the current caps (128 definitions per entity, 4,096-character long text,
200 choices) and define aggregate voucher/line/payload bounds before release. A per-line cap
alone does not bound a whole voucher. Decimal/currency serialization and date handling follow
the shared validators, with errors identifying the exact line and field.

## 4. History, conversion and querying

- Issued/posted revisions pin accepted definition and type/binding versions plus the evidence
  required to reproduce historical labels/options/values. A current label change does not
  rewrite an issued document. Live read-denies still apply to historical access and printing.
- Reuse reviewed definition adoption for drafts and active types. Changing a used field's
  data type or weakening a shared contract in place is prohibited; create a new key and an
  explicit reviewed mapping where needed. Deactivation does not erase historical values.
- Indent -> order/issue, quote -> order -> challan -> invoice, returns and job-work conversions copy only explicitly
  mapped, compatible fields. Revalidate target requiredness and write permissions. Preserve
  source revision/line references; do not blindly copy auto-numbers or uniqueness claims.
  Conversion cannot silently coerce incompatible data or lose required evidence.
- Vouchers owns its value indexes, uniqueness claims and auxiliary sequences. Commit them
  with the document revision and outbox in one local transaction; retries do not allocate
  twice. Line ownership and the current-versus-historical uniqueness scope must be explicit.
- Filtering/sorting uses authorized typed indexes with readiness tracking, as in Catalog.
  Do not fall back to unbounded JSON scans. Read-denies cover metadata, queries, print/export,
  reports and related-object option lookups, not just the edit form. Audit events identify
  changed fields/revisions without dumping arbitrary custom-field values into logs.
- Posting snapshots carry custom fields as evidence only. Accounting does not derive tax,
  money, stock, custody or approval decisions from those values.

## 5. Planned API and delivery

Use existing Identity definition/policy administration and company-scoped Vouchers surfaces:

| Proposed surface | Purpose |
|---|---|
| `/voucher-types`, `/{id}/revisions`, `/{id}/clone` | Create, version, clone and retire derived types |
| `/voucher-types/{id}/field-bindings` | Bind accepted header/item definitions to a type revision |
| `/voucher-types/{id}/configuration-bindings`, `/{id}/effective-configuration` | Bind native policy revisions and resolve context/stage controls, provenance and readiness under the common configuration contract |
| `/voucher-types/{id}/field-set` | Metadata for a new voucher before it has an ID |
| `/vouchers/{id}/field-set` | Header metadata for the current draft or historical revision |
| `/vouchers/{id}/items/{line_id}/field-set` | Per-line metadata and access for the selected item/context |

The type `field-set` and revision-pinned `/vouchers/{id}/field-set` are implemented.
The other paths remain proposals where not delivered. No single "custom columns" API
may bypass definition validation, object scope or the native transaction schema.

| V1 step | Required evidence |
|---|---|
| V1a: types/revisions/templates | Company isolation, clone provenance, retirement, immutable historical kind, no permission escalation |
| V1b: definitions/bindings/forms | Both entities registered end to end; every supported type validated; item master/header/line separation; requiredness and field-denial cases |
| V1c: storage/adoption/query | Atomic claims/sequences/indexes, bounded input, reviewed schema adoption, historical snapshots, conversion mappings and generated-client parity |

Later document phases must exercise their own conversions and types against this foundation,
including Job Work In/Out Orders and Material In/Out. An inspection note can be custom;
stock ownership, statutory job-work deadlines and service-tax classification cannot.

## Decision log

- 2026-10-11: Reviewed the implemented Identity definitions and Vouchers header/item-line
  projections, JSON values, accepted snapshots, typed indexes, claims, sequences and field
  metadata. Fixed custom-to-custom condition resolution while keeping read-denied parents
  unavailable, and exposed pinned metadata for saved revisions under live field policies.
  See [custom-attribute review](voucher-custom-attribute-review.md).

- 2026-10-10: Extended explicit custom-field copy/revalidation rules to indent-to-order/issue
  conversion. Approval quantities, schedules and fulfillment behavior remain native fields,
  never configurable financial logic embedded in custom attributes.
- 2026-10-10: User selected common voucher base/detail tables. Bound runtime types to shared
  section configuration; header/ITEM-line custom fields reuse common revision/line storage.
  Cloning a type copies configuration, not a schema or a new physical document table.
- 2026-10-10: User required future company-created voucher types and typed custom attributes
  on vouchers and items. Reuse Identity/Catalog/platform mechanisms for item masters, voucher
  headers and individual item lines. The initial 22 kinds do not cap future implemented kinds;
  runtime types cannot introduce executable financial behavior. Vouchers support is planned.

### Sales commercial-configuration review - 2026-10-10

The [commercial configuration contract](voucher-commercial-configuration.md) now requires native company Sales/Purchase
policy revisions, restrictive type/class bindings and disjoint paid/reward source evidence.
D07 finalizes shared policy/benefit relations; no per-type table or custom-field posting logic.
CAL17-CAL28 remain future implementation checks.

### All-voucher configuration review - 2026-10-10

Bound type/class creation and native policy surfaces to the common configuration registry.
VCF01-VCF24 cover all kinds/profiles; custom-field administration cannot add executable behavior.

- 2026-10-30: The Console now has a voucher type directory at `/masters/voucher-types` (list with
  kind/status filters and the service's code-prefix search, create, duplicate, change entry rules,
  retire). It uses only the existing `vouchers` routes — `GET /voucher-types[/{id}]`,
  `GET /voucher-capabilities`, `POST /voucher-types`, `/{id}/revisions`, `/{id}/retire` — and the
  browser proxy allows those three writes, by POST only. Reading needs `vouchers.read`; creating,
  duplicating, revising and retiring also need `vouchers.type.manage`.
  - **A save is a new revision.** The form sends the policy as it was read with only the base entry
    controls changed (entry modes and default, required/forbidden sections, line/party/date limits,
    approval and required details, party roles, default narration), at the `row_version` it was read
    at, so a concurrent revision is a conflict rather than an overwrite. The typed sub-policies
    (stock, financial, invoice, order, money, manufacturing, job process, sales workflow, commercial
    attribution, counter, notification) are passed through untouched and are **not** editable there.
    A v2 policy stores only supplied keys, so a key it lacks is added only when the form moves it off
    the service's default.
  - **Retiring is permanent** — the service has no reinstate — and needs a typed word. A retired type
    keeps its record; the service refuses to revise it or use it for a new voucher, so the Console
    offers nothing to change on one. A duplicate carries `derived_from_revision_id`, the original's
    kind and profile (which cannot be changed) **and the original's policy**: sent without it, the
    service intersects the original with the *default* policy and the copy comes back with approval,
    starting mode and narration reset (an items-only original cannot be copied at all).
  - **Kind-aware and not a reason.** The rules form offers a kind only the sections the service lists
    for it (`planned_sections` of `GET /voucher-capabilities`), starts a kind with no item entry only in
    Accounts, and refuses what `validate_policy` always refuses — required items with no lines, required
    parties with no parties, forbidden references with a required supplier reference. The service
    accepts a `reason` on revise and retire but records it nowhere, so the Console does not ask for one.
    A revision supersedes the earlier one for live use: drafts still open on it are asked to adopt the
    current configuration (`voucher type revision is retired or superseded`); issued vouchers keep theirs.
  - **Not built:** editing the typed sub-policies, binding field definitions, classes, series or
    templates to a type, and a revision history list (the service lists no revisions by type).
