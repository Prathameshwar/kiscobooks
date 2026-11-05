# Simple products by default: revised API-only delivery plan

Status: phases approved for implementation on 2026-10-28. Delivery and review
evidence are maintained in [the TODO](simple-product-api-todo.md); implemented
contracts are in [the API reference](simple-product-api.md). UI implementation is
explicitly deferred until the API acceptance checks are complete.

## 1. Required outcome

- New companies resolve `product_family_sku_enabled=false` without manual setup.
- Simple mode exposes one product, one code/name input, one detail resource and
  one edit operation. No family/default-SKU pair is required in the public form contract.
- Enabling the company setting makes the existing advanced family/SKU flow available.
- Internal ProductFamily + Item storage remains. Product ID equals Item.id, so
  invoices, pricing, batches, serials, warehouses and openings retain their references.
- Inventory profiles are independent of this setting. Turning advanced authoring
  off must not turn off batches, ordinary attributes, stock or warehouse features.

## 2. Findings that revise the earlier plan

| Inspected implementation | Consequence for delivery |
|---|---|
| `models/configuration.py`, `tasks/configuration.py` | Product defaults use drafts, immutable dated releases and monotonically advancing effective dates. A current authoring switch should not be placed inside these historical releases. |
| `tasks/product_requirements.py`, `tasks/product_choices.py` | Existing items can use pinned configuration. Advanced authoring must check the live company switch separately; old pins must not bypass it. |
| `tasks/products.py` | Creation already writes a family, default item and initial setup in one idempotent transaction. Reuse its mutation logic, not a second HTTP call or nested idempotent command. |
| `tasks/product_commands.py`, `tasks/product_attributes.py` | Groups, manufacturers, categories and ordinary attribute declarations use family ownership. Do not prohibit all family routes in simple mode. |
| `tasks/attribute_forms.py` | Attribute editing and variant hints share permission calculations. Add distinct capability decisions so ordinary values remain editable with variants disabled. |
| `tasks/product_creation_review.py` | Reviewed configuration has an explicit fingerprint field list. Live authoring-mode freshness needs its own check; a boolean alone in a response will not enforce stale submissions. |
| `tasks/bulk_registry.py`, `tasks/bulk_matching.py` | Bulk creation targets ProductFamily, updates target either owner, and target matching assumes code/version conventions. Simple import needs an adapter and matching changes, not only a new HTTP endpoint. |
| `models/projections.py` | Catalog's company projection has no company creation timestamp. Absence of configuration cannot distinguish an old company from a new one. |
| Accounting `tasks/stock_effects.py`, `tasks/stock_openings.py`, `tests/test_stock_openings.py` | Native opening execution and posted-GL opening selection exist in the working tree. Verify current behavior instead of relying on the older wizard's unavailable-opening statement. |
| `tasks/product_definition_reads.py` | Child resources retain family or item ownership and field-level membership checks. A product facade must preserve those checks. |

## 3. Selected design and compatibility rules

### Company authority

Add one Catalog-owned current company authoring configuration, using a dedicated
company-scoped singleton table, following the current-control pattern used for
warehouse configuration. It is presented under Product Configuration, but is not
another Identity feature flag or a type/group/SKU override.

Proposed table: `company_product_authoring_configuration`, with tenant/company
unique key, ID, strict boolean, row_version and standard audit fields. Reads use
false when no row exists, without mutating on GET. First write uses the existing
company policy lock and safe insert pattern. Register native metadata, permissions
and audit contracts alongside the model/migration.

Use existing `product_configuration.read/manage` authority for reads/preview and
edits respectively, subject to field policy. This is an immediate authoring control,
not publication of a dated default revision; document this distinction explicitly.
No historical config, accepted adoption or operational source snapshot is rewritten.

### Compatibility and mode transitions

- Prepare an explicit pre-rollout company inventory using the existing authorized
  Identity company-list/export mechanism, and seed true for those existing companies.
  Include Catalog's retained company IDs as a reconciliation check. If an authoritative
  roster is unavailable, report the migration limitation; do not guess age from
  projection arrival, absence of config, UUID time or presence of products alone.
- Roll out readers and additive product APIs before enforcing new mode gates.
  Keep the public mode-transition write disabled until Phase 4 installs every
  structural guard. Install/reconcile the compatibility seed before declaring
  the false fallback live; activate the complete API behavior at Phase 7.
  Coordinate the cutoff with company creation so companies cannot fall between steps.
- False to true preserves all IDs and existing settings. Do not add a variant,
  mutate an inventory profile or require reactivation merely to enable authoring.
- True to false is allowed only when all retained families have exactly one default
  item, SIMPLE structure and no axes/variant keys. Draft and discontinued records,
  explicit advanced configuration and pending bulk jobs must be checked. A stale
  job cannot apply incompatible work after a mode change.
- Reject incompatible downgrade with 409 and authorized bounded blocker details.
  Do not merge/delete records, clear axes or rewrite settings automatically.
- Keep legacy family/item reads and ordinary writes available. Legacy family CREATE
  still creates one SIMPLE family/default item, preserving the existing wizard during
  the API-first rollout. Gate axis declaration and sibling creation, including initial
  setup and bulk, rather than banning all family endpoints.
- If an explicit variant requirement conflicts with simple mode, reject the attempted
  incompatible configuration/creation or downgrade with a clear reason. Do not
  silently weaken the requirement or make historical stock reads fail.

## 4. Implementation phases

### Phase 1 - Live company control and compatibility migration

Deliver:

1. Singleton model, migration, factories, native field metadata, audit registration
   and company-scoped access using existing primitives. One DDL statement per revision;
   keep any data backfill separate, explicit, resumable and reviewed.
2. `GET /v1/companies/{company_id}/product-configuration/authoring`: flag,
   configuration version, policy generation and permitted current capabilities,
   available before type/kind/product selection.
3. Define preview and idempotent PATCH contracts on that resource: expected
   version/generation, desired boolean and change reason. Implement shared access,
   version and blocker-check helpers; expose the public transition write in Phase 4.
   Preview provides a signed bounded decision; commit revalidates under the same
   company lock. Preview is not authorization.
4. Explicit legacy-company seed/cutover process and tests for companies with no
   Catalog configuration, delayed projections and creation around the cutoff.
5. Live-control capability metadata separate from dated EffectiveConfiguration.
   Preserve the existing configuration fingerprint contract for legacy clients;
   new product requests carry authoring-version evidence separately.

Exit: defaults, compatibility, read-only GET, audit rollback, stale preview,
permission denial, tenant isolation and concurrent first-write tests pass. The
existing UI/API workflows remain usable. No variant gates are activated prematurely.

### Phase 2 - One-product read and metadata contracts

Deliver:

1. Add `GET /products` and `GET /products/{item_id}` under the company prefix.
   One directory row per item, canonical product code from Item.sku and name from
   Item.name; permitted family descriptive fields join into the same resource.
2. A single-product field-set/option contract built from existing native metadata.
   Explicitly map each public field to its underlying permission checks. No new
   authorization entity named `catalog.product` merely to rename the presentation.
3. Return an opaque revision token covering item/family ownership and versions,
   and separate live authoring-control evidence. Tokens never confer permission.
   Child operations can keep their existing native expected-version rules.
4. Namespace family/item custom fields by their existing definition/owner identity
   inside one product form contract. Never merge same-named JSON keys destructively.
5. Return bounded links/action hints for existing tax, pricing, units, profiles,
   tracking, stock and opening operations. Avoid embedding every child collection.
6. Preserve cursor/search/filter/sort conventions. Authorize both sides of joined
   fields, bind cursors to the correct policy/query context and avoid N+1 reads.
   Product reads remain usable in advanced mode; they do not replace existing APIs.

Exit: product projection, hidden fields, mixed-owner custom fields, cursor
invalidation, bounded queries and cross-company ownership tests pass.

### Phase 3 - Atomic simple create and edit

Deliver:

1. `POST /products` accepts one code/name, kind, required published type, base unit,
   operation flags and applicable existing setup fields. Retain required custom
   fields and type requirements; simple does not mean optional business validation.
2. Refactor the shared mutation layer out of the existing product command only as
   needed. Legacy and new transports reuse the same native checks and transaction.
   Keep legacy operation names, request fingerprints and receipt rendering stable.
3. Allocate a stable internal family code from server-generated identity, satisfying
   existing 30-character/uniqueness rules. Set initial family name from product name.
   Persist generated IDs once; exclude regenerated values from retry fingerprints.
4. Reuse accepted-default, initial group/unit/barcode/attribute/tax/price handlers.
   A failure rolls back family, item, children, custom claims and audit together.
5. `PATCH /products/{item_id}` checks the single-default-item/SIMPLE precondition,
   aggregate revision and current authority, then updates mapped fields atomically.
   Synchronize product name and internal family label for simple edits, subject to
   both native field policies. Generated values must not bypass native write denies.
6. Return one product resource and existing setup-result references. Never return
   a second editable family identity as a required part of this flow.
7. Support simple standalone creation in either mode. Aggregate simple edits reject
   a shared/variant family; advanced edits continue through existing explicit APIs.
   Preserve active/discontinued editing restrictions and draft activation lifecycle.

Exit: rollback, code conflicts, replay after policy changes, regenerated-ID safety,
no-op edits, two-owner stale writes and active-product restrictions pass. Existing
creation and activation suites remain green without weakening assertions.

### Phase 4 - Structure enforcement and ordinary attributes

Deliver:

1. Revalidate the live switch inside the mutation transaction in axis declaration
   and create_variant handlers, using the existing company policy lock. Cover
   native routes, initial setup and bulk invocation of those handlers.
2. Update current capability/form metadata, including can_create_variant, without
   disabling ordinary attribute declaration/value editing. Add product-scoped
   adapters for family-owned declarations/groups/categories/manufacturers where
   the simple client would otherwise need an editable family identity.
3. Adapters resolve product-to-family internally and reuse native owner/version,
   field-policy, date and lifecycle checks; no alternate business implementation.
4. Expose mode preview/PATCH only together with the completed structural guards.
   Check downgrade compatibility under the same lock, including pending advanced
   work and conflicting explicit policies. Scope blocker disclosures to authority.
5. Verify changes in mode do not invalidate historical pinned configuration or
   disable native units, price, tax, tracking/profile and warehouse operations.

Exit: direct/bulk bypass and downgrade/variant race tests pass; ordinary attributes
remain usable with the flag false. Existing advanced cases still pass with it true.

### Phase 5 - Simple bulk/import and stale-work protection

Deliver:

1. Add explicit simple product CREATE/UPDATE bulk operations using the same schemas
   and mutation functions as Phase 3. Preserve existing resource/action names.
2. Extend metadata, matchers, AUTO behavior and reference results so product code
   targets Item.sku and successful creation resolves to Item.id, not family ID.
   Account for aggregate version evidence instead of assuming one row_version.
3. Keep simple templates to one identity input. Permit existing authorized setup
   fields without requiring a family/default-item payload in each row.
4. Pin/recheck authoring-mode version in preview/commit/worker stages. Invalidate
   incompatible stale advanced jobs; never silently downgrade a prepared variant.
   Completed-command replays retain existing idempotency semantics and authority checks.
5. Verify dependent rows can refer to a newly created product and that rollback,
   chunking, bounded command counts and custom-field claims remain correct.

Exit: simple and legacy imports, mode change after preview, queue races, duplicate
matching, worker replay and dependent-reference tests pass.

### Phase 6 - Stock, opening and integration regression

Deliver verification first; production changes only for demonstrated contract gaps:

| Feature | Required result in simple and advanced mode |
|---|---|
| Product selection/voucher sources | Product ID is the same item_id; no family-to-item ambiguity or new replicated inventory identity. |
| Inventory/tracking profiles | Stock/non-stock, lot/serial/expiry requirements and activation pins remain authoritative. |
| Ordinary attributes/custom fields | Independent of variants, preserving type requirements and native field permissions. |
| Warehouses/bins | Existing location policies, defaults and operation restrictions still resolve by item/date. |
| Units/barcodes/pricing/tax | Existing exact decimal, conversion, publication and dated-rule behavior is preserved. |
| Opening stock | Existing OPENING execution accepts that item_id, required warehouse/lot/serial evidence and native opening date/value rules. |

Exercise both native COMBINED and LINKED_GL opening modes, posted-GL remaining-value
claims, duplicate opening protection, books-begin date restrictions, tracking inputs,
reconciliation and reversals against the available implementation. Confirm separate
permissions remain required. A Catalog product save does not post an opening or
write balances; partial opening failure cannot imply product-creation rollback.

The working tree includes concurrent stock changes. Record the revision/state
actually verified and reconcile stale documentation with the stock work owner;
do not replace unfinished work or claim deployment/activation from local code alone.

Exit: available Accounting/Vouchers integration contracts and affected stock/opening
suites pass, with any external release dependency explicitly recorded.

### Phase 7 - API completion and UI handoff

1. Update governing product/configuration/schema/import/API docs and decision logs.
2. Export OpenAPI, audit/field contracts and regenerate API-client types per phase;
   finish with consistency checks. Generated clients are API deliverables, not UI work.
3. Run affected Catalog suites plus relevant Accounting/Vouchers and Identity
   compatibility tests. Validate migration/backfill rehearsal and rollout ordering.
4. Complete repository-required simplification/security review, particularly native
   field aliases, company scoping, receipts, blocker disclosures and stock authority.
5. Publish an API acceptance checklist and example create/read/edit/config/import
   requests, including capabilities for one product card and opening selection.

Exit: no unresolved API correctness or contract dependency needed by the planned
UI. UI implementation starts only after this checkpoint is accepted.

## 5. Scope and review decisions

This is API-only delivery. No React screens, navigation, cards, wizard or
opening UI changes belong in these phases. No commits or publication are requested.

The live singleton setting, additive /products facade, compatibility roster and
blocking downgrade rules are the revised recommended design. Agree phases before
implementation as required by CLAUDE.md. If the compatibility roster or a governing
open design question cannot be resolved, complete independent work and report the
specific decision needed; do not silently substitute a different rollout policy.
