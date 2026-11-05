# Product configuration and numeric precision

**Status:** Company-only configuration, decision dated 2026-10-30.
Implementation and verification are tracked in [Product Configuration TODO](product-configuration-todo.md).

## Automatic starter and pricing options — 2026-11-04

New companies receive one published COMPANY configuration through Catalog's
verified enrollment worker, after the Default type/group and pricing masters.
The starter uses Simple authoring, disables the eight optional entry dimensions,
selects the Default type for goods and services, and clears optional profiles.
Sale and purchase prices are optional, MRP is disabled, and sale level coverage is
one. A dated company pricing policy selects PRICE1, the base-currency purchase
plan, explicit unit prices and an error for missing prices. No price amounts or
opening balances are invented.

The following native fields in `ProductPricingPolicy` use
`INHERIT | DISABLED | ENABLED`:

| Field | Controls | New-company setting |
| --- | --- | --- |
| `multiple_price_levels_mode` | Selling levels beyond PRICE1 | Disabled |
| `unit_prices_mode` | Separate prices for alternate units/packs | Disabled |
| `quantity_tiers_mode` | Quantity-slab pricing | Disabled |
| `channel_prices_mode` | Sales-channel-specific prices | Disabled |
| `additional_currencies_mode` | Prices outside the company currency | Disabled |
| `formula_prices_mode` | Supported reference-cost/MRP formulas | Disabled |

`sale_level_count` retains its required-coverage meaning; it does not authorize
additional levels. Multiple levels and foreign currencies also require their
company capabilities, and foreign currencies need an active allowance. Alternate
units must still satisfy product unit configuration. Unit derivation remains
controlled by `CompanyPricingPolicy`; these switches do not add currency conversion.

Draft creation/replacement, preview/publication, bulk price writers and regular
resolution use the applicable product configuration, including adoption pins.
Reference prices and guards enforce unit/currency controls. Historical records
remain readable. Publishing a later company revision does not rewrite old pins.
Only existing SKU/unit capabilities are controlled: batch/declaration pricing is
not implemented, and warehouse-specific pricing is excluded.

Migration 0216 defaults existing rows to INHERIT, preserving prior permitted
behavior. Only the new starter explicitly disables extra options. Its baseline
date is 1000-01-01 so a new company's earlier books date has defaults too; the
provisioner refuses to insert it over authored configuration, products or mode
settings. A company policy lock, one transaction and system audit evidence make
retries and concurrent setup safe. Rollback refuses to discard any non-INHERIT
setting. Apply 0216 before running the updated Catalog API or source worker.

The overview shows saved pricing options; the editor groups them with native
labels, capability-filtered choices and field permissions. Changes still follow
save draft → preview → publish. Product master pages remain deferred.
See the [delivery plan](product-configuration-starter-plan.md).

## Current ownership decision — 2026-10-30

Product configuration can be created, edited and published only for the company.
The console opens one company overview and a direct configuration form; there is
no type/group/family/SKU scope selection or scope creation step. Saving the first
draft atomically creates the singleton company owner when needed. Publication
retains its dated, versioned server review and explicit confirmation.

Current and proposed product defaults resolve only published COMPANY revisions.
`INHERIT` is presented as **Use system default** and means the native baseline.
Optional native type profile defaults are fallbacks; explicit company profile
choices and clearing take precedence for current/new configuration. Native type,
unit, goods/service, capability and structural requirements still constrain use.
Independent tax, pricing and operational policies retain their own ownership.

The consumer review binds new adoption evidence and saved pins to
`resolution_version=2`. Company VALUE/CLEAR choices therefore survive preview,
adoption, authoring defaults, readiness and activation. Existing rows retain
version 1 and their original ordering. The marker is server controlled and part
of the signed preview; unsupported versions fail closed. Publication also
validates the selected default goods/service type's native constraints.
Deploy Catalog migration 0214 before the matching API. Its additive column
defaults existing rows to 1 without rewriting history. Online rollback is allowed
only while all records are version 1; offline rollback is refused.

TYPE/GROUP/FAMILY/SKU authoring, editing, publication, filters and ownership option
sources are permanently retired. Compatibility company-scope APIs remain closed
to those owners. Old owner rows/columns and published revisions remain only to
support immutable provenance and existing product adoption pins. Internal pinned
resolution preserves version 1's original ordering; public current/default inspection
never selects those layers. Existing products require supported, reviewed adoption
to accept the current company configuration, with no automatic history rewriting.

The older hierarchy descriptions below document the historical contract and do
not authorize new non-company configuration. The current decision supersedes them.
See the [implementation plan](company-only-product-configuration-plan.md) and
[review results](company-only-product-configuration-review.md).
**Read with:** [Product rules](catalog-product-design.md), [schema](catalog-schema.md),
[company formats](company.md) and [company capabilities](company-features.md).
**Location controls:** [Stores/godowns, Main and stock operations](catalog-warehouses.md).
**Complete pricing controls:** [Purchase/MRP/selling/unit/batch/reference-cost model](catalog-pricing-design.md).
**Planned voucher integration:** [Sales/Purchase commercial policies](voucher-commercial-configuration.md)
further restrict allowed discount/charge/free/deal behavior at transaction execution. They
reuse this configuration's product/numeric/price guards; no voucher class may widen them.
This reference adds no implemented Catalog setting or automatic scheme runtime.

**Implementation boundary:** Catalog owns this native configuration. Billing owns operational
stock controls/approvals, counts/damage/ledger and transaction enforcement under the
[inventory integration contract](catalog-inventory-integration.md). Required source support is
an external dependency; this Catalog scope does not add another API's migrations.

## 1. Requirement and ownership

Provide explicit quantity and price decimal controls, and a native **Product Configuration**
API for company defaults, reusable type/group profiles and permitted product overrides.
It controls supported options, defaults, requiredness and safe adoption on existing products.
It does not duplicate Identity capability flags, field layout or permissions.
Existing /catalog-defaults and group-default routes are adapters to these same configuration
revisions/native default-profile children, not separately writable sources of the same settings.

| Layer | Owner and responsibility |
|---|---|
| Company capability | Identity: whether inventory, batches, serials, multiple price levels or coupons are available at all |
| Product configuration | Catalog: allowed/required options, defaults and reusable numeric/profile references |
| Activated product configuration | Catalog: pinned SKU/unit/profile decisions, with permitted future revisions |
| Transaction enforcement | Billing: local complete configuration, actual stock/cost, quote/post/return validation and snapshots |
| Field policy/layout | Existing Identity/platform mechanism: caller authority and presentation metadata, independent of feature behavior |

Effective use requires **implemented support AND enabled company capability (where applicable)
AND applicable product configuration AND valid transaction context AND actor permission**.
A product override cannot switch on a disabled company capability or bypass a hard requirement.
Custom fields remain descriptive; none of these settings are stored as custom values.

## 2. Numeric controls are separate

The existing platform stores every money/quantity value as DECIMAL(19,4). Keep that convention;
configuring two decimals does not change a column to DECIMAL(19,2). Allowed precision here is 0–4.
A later need for more stored precision requires a separately reviewed platform-wide contract.

| Control | Authoritative setting | Meaning |
|---|---|---|
| Quantity decimal places | unit_of_measure.decimal_places; stricter item_unit_revision.quantity_decimal_places | Accepted entered quantity for the selected unit; 0 means whole units |
| Quantity increment | Unit and item-unit revision constraints | Accepted quantity must be an exact multiple; scale alone does not enforce increments such as 0.25 |
| Fractional pack entry | Native product/unit option plus conversion revision | May accept half a box only when permitted and the resulting base quantity is valid |
| Price decimal places | item_price_numeric_revision.price_decimal_places | Accepted stored rate amount for a SKU/unit/currency; independent of invoice-total precision |
| Price increment | Optional item_price_numeric_revision.price_increment | Exact allowed step for entered prices, distinct from minimum sale price or discount ceiling |
| Price basis quantity | item_price.price_basis_quantity with declared pricing unit | Rate per 1, 100, 1,000 or another positive exact quantity; all tiers inherit this basis |
| Monetary total scale | Existing Identity company.amount_precision and supported currency/tax context | Rounding boundary for computed line/tax/document amounts, not rate-entry scale |
| Quantity presentation default | Existing Identity company.quantity_precision | Presentation preference, not permission to round stock or reject a valid finer product quantity |
| Rounding mode | Existing Identity company.rounding_mode and supported tax adapter | Supported half_up/half_even/down semantics at named boundaries; no arbitrary per-product override |
| Tax/discount percentages | Dedicated typed rate contracts | Dimensionless rates, not money; never inherit price/quantity decimal settings |
| Cost/unit estimates | Billing valuation history and exact calculation | Derive average/per-unit cost at adequate precision; stored layer quantity/value stays authoritative |

Product numeric defaults are distinct from company display fields. There is no second writable
amount_precision or rounding_mode in Catalog. Company financial-format immutability remains.
Do not add independent tax/discount/FX precision knobs through a product option; their own
native adapters/amount contracts govern them.

### Quantity validation and display

- Validate entered quantity against the selected unit, SKU binding and transaction role.
  More restrictive product precision cannot exceed its unit's precision; serial base quantity
  must be integer regardless of display settings.
- Check all applicable increments exactly. Combining increments means satisfying their
  intersection, not choosing the smaller number; 0.20 and 0.25 require multiples of 1.00.
- Validate every compound component before conversion, then validate the exact base result.
  Secondary measured quantities have their own declared unit precision/increment.
- Reject nonzero excess digits, negative values where disallowed, NaN/infinity and overflow.
  Numerically equal trailing zeros are harmless: 1.2300 satisfies two decimal places.
- Quantity conversion never rounds away stock. A smaller base unit can represent finer
  measurements; it does not justify accepting an unrepresentable amount in the entered unit.
- API/export round-trip values retain their exact decimal representation and applicable
  precision metadata. A transaction line must show enough digits to reproduce its quantity;
  a coarser company presentation default must not conceal a nonzero quantity or rate.
  Aggregate display can be rounded only with an explicit distinction from the exact value.
- Use decimal strings in JSON for money/quantity and a declared import numeric convention;
  never infer whether 1,250 means a decimal value or a grouped integer, or pass binary floats
  through a rounding helper to hide lost precision.
- Keep minimum order quantity, quantity increment, reorder level and quantity decimal places
  as different fields. For example, increments of 0.25 hours with minimum 1 hour.

### Price basis, calculation and rounding

A declared price is **amount in currency per price_basis_quantity of pricing unit**.
A request must provide/resolve that basis, never rely on a formatter to guess it.
Validate the entered amount against its price-entry revision before persistence.

Compute regular line consideration as:

```text
exact_pricing_quantity × price_amount / price_basis_quantity
```

Keep adequate Decimal precision through conversion, tier selection and this division; do not
round a derived per-base-unit rate to four decimals before multiplying. Tier thresholds use
their declared quantity/unit basis; changing the rate denominator never changes a customer's tier.

Example: 0.0120 per 1,000 pieces represents an effective rate of 0.000012 per piece without
storing that six-place rate in a four-place amount column. Store 0.0120, 1000.0000, unit and
revision. A request for 0.000012 per 1 piece is rejected under the current storage contract.
Small resulting line amounts still follow the explicit line-total rounding policy; a positive
charge that would round to zero is blocked unless the native small-charge/free-sale policy allows it.

Example without tax/discount: quantity 1.250 kg × price 19.8765 per kg = 24.845625.
At company amount_precision=2 and half_up, the line amount is 24.85, persisted as 24.8500.
The stored quantity is 1.2500 and the stored price remains 19.8765. Formatting the rate to
19.88 before multiplication would change the calculation and is forbidden.

Apply benefits/tax using the [promotion calculation contract](catalog-promotions.md), with
explicit allocation and rounding stages. Rounded line/component amounts reconcile to document
totals; represent any permitted document/cash round-off separately with an account/reason.
Cash settlement rounding is not a product price setting. Never hide a balancing adjustment in quantity.

Reuse platform Decimal helpers, adding strict exact-scale/increment validators. The current
quantize_storage helper rounds to four places, so it cannot serve as validation for quantity or
entered price. Validate first; use explicit rounding only at approved computed-amount boundaries.
Default Decimal context precision is insufficient for some products/divisions near numeric limits;
set a tested bounded context, reject overflow and test residual allocation.

## 3. Product Configuration ownership and related controls

Use a fixed typed option catalogue, not arbitrary JSON switches or a general EAV rules engine.
For optional capabilities/metadata use DISABLED, OPTIONAL or REQUIRED; INHERIT means an
explicit fallback at scopes that permit inheritance. OPTIONAL has an explicit default_enabled
where activation is a choice. A field requirement and a selected tracking mode remain distinct.

The matrix below includes controls owned by related native APIs and external consumers.
It is an ownership design, not the payload of one configuration endpoint. The implemented
configuration fields are listed in the corrected contract below; complete route contracts are
in [the configuration API guide](catalog-v12-api.md).

| Configuration area | Related controls | Hard boundary |
|---|---|---|
| Product identity | Allowed GOODS/SERVICE kinds, simple/variant mode, SKU/barcode code policies and attribute-set requirements | One primary group/default General and base UOM remain native obligations |
| Classification | Group/type defaults; category, brand, manufacturer/site and native-attribute requiredness | Categories never become implicit tax ancestry |
| Units and quantities | Unit/profile defaults, decimal places, increments, alternate/compound/measured entry, fractional packs and min/max transaction quantities | Exact unit compatibility, integer serialized base units and storage bounds |
| Price entry | Price precision/increment defaults, price-basis quantity/unit, existing price-policy/profile references | Same SKU/unit/currency policy across price levels; no alternate price calculator |
| Price purposes | Purchase references, quoted trade-discount terms, SALE levels and separately labelled REFERENCE_RETAIL | Actual purchase/sale/cost history remains Billing-owned |
| Pricing scope and method | Explicit versus base-derived unit rates, optional/required lot/declaration scopes, fixed/tier/native recipe | Required sources must exist; no caller-invented lot/cost/MRP or recursive formula |
| MRP and cost inputs | Product declaration defaults, physical declaration requirement, optional standard/replacement/service estimates | Existing physical declarations cannot be relabelled by a product default; actual allocated cost is external |
| Commercial guards | Fixed minimum/maximum, minimum margin/markup, cost source and blocking/approval requirement | Strongest applicable floor/ceiling survives narrower overrides; post-benefit enforcement belongs to Billing |
| Inventory/tracking | Stock/nonstock defaults, batch/expiry/serial mode, IMEI identifier requirements and warehouse/profile defaults | Services reject inventory; expiry requires batch; IMEI requires the serial/identifier profile |
| Stores/godowns | Built-in Main, multi_godown capability view, sale/purchase/return/opening defaults and optional SKU location restrictions | One warehouse authority; each operation must pass its location flags and actor scope; Main always exists |
| Purchase/sale behavior | Existing buy/sell eligibility and allowed unit bindings; transaction-role quantity bounds | Returns/corrections remain available under their native historical obligations |
| Tax and commercial policy | Required classification, inherit/explicit-tax mode, zero-price/free-sale, floor/discount/MRP profile references | Tax obligations and restrictive company/group guards cannot be disabled |
| Promotions | Participation/exclusion, coupon eligibility and allowed manual-discount policy references | Company capability, the sole promotion evaluator and all combined guards still apply |
| Operational policies | Warranty/return/handling profiles, replenishment enablement/defaults, reorder/MOQ/multiple references | Do not reinterpret existing stock or invent forecast/settlement behavior |
| Optional manufacturing definitions | BOM participation/requiredness, alternative/multi-level/phantom/recipe/secondary-output/substitution options, route/quality definitions and estimate-source policy | Proposed bom_definitions capability must exist; goods outputs only; no production/WIP/actual-cost execution implied |

Barcode is a product/pack identifier; serial/IMEI identify a physical instance. A product-level
IMEI setting expresses the required instance identifier profile, not an array of devices on SKU.
Do not invent Identity feature flags for every field. Baseline product options need no separate
feature flag; optional company capabilities use the existing fixed catalogue.

Expose effective_enabled, requiredness, allowed values, editable/locked state, source revision,
dependency/readiness reasons and actor-authorized metadata. Layout visibility remains in field_config.
A disabled option rejects new incompatible writes; it does not erase historical values.
An unsatisfiable required-field/policy combination must fail validation or explain the missing
authorized system default, rather than quietly weakening requiredness.

Warehouse configuration exposes independent allow_sale_issue and allow_purchase_receipt flags,
plus transfer/return/opening/adjustment controls. Multi-location enablement reuses Identity's
multi_godown flag; Product Configuration does not maintain another writable copy. All activity
defaults initially use Main. Default changes never move stock; actual allocation and acknowledged
location policy govern reserve/post. The warehouse companion defines these APIs and lifecycle rules.

## 4. Default inheritance and safe changes

Current default selection is **company product default > native/unit baseline**, within all applicable
hard constraints. A company configuration can provide dimension-specific quantity defaults;
a universal three-place default must not make a piece unit fractional. Explicit incompatible
overrides fail; derived defaults report the unit/kind constraint that narrows them.

Three change types use different behavior:

1. **Future-product defaults:** a new configuration/profile revision changes subsequent
   activation only. Active SKUs retain pinned structural/numeric unit profiles. The API explicitly
   states that existing products have not adopted the new default.
2. **Apply to draft products:** preview a frozen selection and proposed effective configuration;
   validate permissions, references, values and row/source versions. Commit through ordinary
   adoption handlers or bulk jobs. Active structural adoption remains unsupported; it requires
   a separate history-aware replacement workflow. No silent propagation or data clearing.
3. **Live commercial restrictions:** dated price/participation/commercial policies affect future
   transactions only, through complete releases and Billing's activation acknowledgement.
   Company capability changes use Identity's use/disable handshake; stopping an offer uses its
   separate Billing control. A Catalog configuration publish cannot claim an immediate remote stop.

Base unit, variant axes, activated tracking and base quantity granularity remain structural.
Changing them on an active SKU uses the already-defined replacement/migration workflow;
zero current stock does not prove there is no history, reservation or pending document.
New alternate packs need explicit new revisions and exact base compatibility.

Price-entry precision can change through an effective revision for **future price publications**.
It does not round existing price rows to the new scale; already published prices retain their
numeric revision and remain addressable. Explicitly replacing current prices needs a reviewed
price-history change. Rounding a future price is an explicit previewed operation, not an import side effect.
Returns/reprints use original quantity, price basis, numeric/config/rounding revisions and allocations.

A DISABLED structural option cannot be forced onto active products that use it. Reject that
existing-product adoption; permit an explicitly future-products-only default where valid.
Neither a bulk import nor administrator privilege bypasses these locks.

## 5. Implemented storage and APIs

Configuration uses seven existing native tables: `product_configuration_scope`,
`product_configuration_draft`, `product_configuration_revision`, `product_entry_option_policy`,
`product_numeric_default`, `product_pricing_policy` and `catalog_default_profile`. Scope ownership
is COMPANY for authoring; retired TYPE/GROUP/FAMILY/SKU references remain as historical provenance. Child rows belong to
exactly one draft or revision. Published revisions are immutable and dated; scope and draft
versions enforce concurrency. No new storage is needed for these corrections.

`product_configuration_adoption` and its source rows pin the reviewed SKU configuration.
`item_unit_revision` owns accepted quantity rules; `item_price_numeric_revision` owns accepted
price precision/increment. Price basis remains on its declared price history. Reusable profile
values remain in their authoritative native masters and revisions.

Use [the configuration/authoring API guide](catalog-v12-api.md) for exact routes, partial PATCH,
protected explanations and explicit default acceptance. Price histories and numeric revisions
are documented in [pricing](catalog-v13-api.md); final activation is in
[tax and activation](catalog-v14-api.md). The generated OpenAPI and TypeScript client carry the
request/response types. Read/manage/publish/adopt permissions and underlying field/reference
permissions apply together; configuration authority does not grant Identity administration.

## 6. Verification and runtime boundaries

The [task checklist](product-configuration-todo.md) records regression and contract checks.
Verification covers exact unit grids, separate rate precision, goods/service applicability,
dated ownership, nested PATCH, protected references, source metadata, stale acceptance,
publication/adoption concurrency and activation compatibility. Bulk adoption uses the same
native eligibility and commit rules as individual adoption.

Catalog publication does not move stock, rewrite published prices, change company display
precision or acknowledge a Billing release. Billing quote/post/return and stock obligations
remain governed by the external integration contract and original stored revisions.

## Decision log

- 2026-11-04: Provision one minimal published company configuration during setup;
  add six explicit gates over existing pricing capabilities. Preserve legacy modes
  with INHERIT and existing adoption pins. Product master UI and batch pricing
  remain deferred; see [delivery evidence](product-configuration-starter-plan.md).

- 2026-11-04: Removed warehouse/location rate configuration from the pricing plan.
  Inventory location defaults, permissions and valuation remain separate controls.

- 2026-09-11: Added optional product_manufacturing_policy and BOM controls under M0-M4;
  [manufacturing design](catalog-manufacturing-design.md#7-configuration-and-lifecycle-controls)
  defines safe defaults, exact units, reviewed adoption and separate execution readiness.

- 2026-09-11: Added typed pricing purpose/scope/recipe/MRP/reference-cost/guard controls under
  product_pricing_policy. Product configuration cannot create actual cost or overwrite physical declarations.

- 2026-09-11: Clarified Catalog configuration ownership versus external Billing runtime/approval
  enforcement; source support and acknowledgement are prerequisites, not Catalog source work.

- 2026-09-11: Added always-present Main, multi-store/godown defaults and restrictive product/
  location controls, with independent sale/purchase flags and one authoritative warehouse model.
- 2026-09-11: Added the user's explicit quantity/price decimal controls and Product Configuration
  requirement. Kept fixed four-place storage, separate rate/amount/quantity semantics and native
  company capability/permission boundaries; introduced no new service or UI implementation.
- 2026-09-11: Made defaults, existing-product adoption and live commercial restrictions explicit.
  Pinned structural rules and price history retain original configuration/numeric provenance.


## Configuration publication contract

The [API guide](catalog-v12-api.md) documents implemented routes. Publication checks expected
draft version, company policy generation and current Identity version, then atomically creates
an immutable revision with native children, audit/outbox events and an idempotency receipt.
Creation defaults resolve at an explicit business date using bounded group ancestry and hard
restrictions. Hidden, stale or inconsistent sources cannot be skipped for a weaker fallback.
Compatibility reads use the same authority; there is no parallel defaults store.

### Revision and child ownership

A scope has one typed owner. COMPANY uses the company identity; TYPE and GROUP use explicit
same-company foreign keys and mutually exclusive fields. Unique normalized ownership is
DB-enforced, including the COMPANY case (nullable unique keys alone cannot enforce that).
A draft is editable with optimistic concurrency; its published form is a separate immutable
revision, referenced from the publication result. Child rows belong to exactly one draft or
one revision through checked local foreign keys and unique parent keys. Numeric defaults are
bounded by the seven native unit dimensions, not a generic per-field value table.

Effective selection uses business dates and stable scope locking. A later revision can replace
future creation defaults without rewriting earlier revision contents or any SKU adoption.
Preview must distinguish effective change for new products from explicit adoption of existing
ones. Publication is not a claim that an external Billing consumer has adopted the settings.

### Native controls in the core increment

- Entry option policies cover variant/barcode/brand/category/manufacturer requirements and
  unit-entry choices. Fixed DISABLED/OPTIONAL/REQUIRED/INHERIT modes and explicit optional
  defaults are validated together. Services cannot select physical tracking/handling options.
- Inventory, expiry and identifier requirements reference the implemented immutable profiles;
  profile values remain authoritative. Feature availability comes from the complete Identity
  snapshot, and unknown/missing required capability information fails closed.
- Quantity defaults have a dimension, accepted decimal places and exact positive increment.
  Selected units can only narrow defaults. Combining increments uses their intersection.
- Price defaults have independent rate decimal places, currency, optional increment and a
  positive exact basis quantity. They do not change company amount precision or rounding mode,
  create price amounts, or modify published numeric/price history.
- Pricing requiredness describes purchase references, sale levels and MRP; full native price
  scope/formula/guard APIs own their values. Extra sale levels remain dependent on
  the real `multi_price_levels` capability, provided by Identity.
- Profile/unit references are real company-owned active masters or published revisions and
  require their own read/field authority. Missing references cannot create implicit masters.

Decision: keep the company display precision, feature source and field policies in their
existing owners. Draft/configuration defaults are a separate native Catalog authority with
explicit source metadata and reviewed draft-SKU adoption. No inventory transaction or UI is added.


Decision 2026-09-12 (V1.2): implemented native configuration and product authoring through
migration 0082. See [V1.2 routes and constraints](catalog-v12-api.md). Earlier checkpoints
above remain historical; activation is documented in [V1.4 contracts](catalog-v14-api.md).

## Corrected configuration contract (2026-09-13)

| Settings | Meaning and applicability | Override and persistence |
|---|---|---|
| Variants, barcode, brand, category | Native entry choices for applicable goods/services | OPTIONAL defaults can be overridden; REQUIRED/DISABLED restrictions survive narrower scopes |
| Manufacturer | Goods-only entry choice | Shared defaults are inapplicable to services; explicit service overrides are rejected |
| Alternate, compound, measured units | Entry capabilities; measured conversion remains goods-only | Native unit/conversion validation is always authoritative |
| Quantity precision/increment | Dimension-specific authoring suggestions | Narrow to the selected unit's exact grid; accepted values become item-unit revisions |
| Price precision/increment/currency/basis | Authoring suggestions, independent of company display precision | Accepted values become price numeric revisions and declared price basis; never round saved prices |
| Type and reusable profiles | References to current authorized published definitions | INHERIT resumes ancestry, CLEAR removes a default, VALUE selects a native reference |
| Purchase/sale/MRP requirements | Required definition coverage; MRP applies to goods | Hard restrictions survive narrower scopes; sale levels require the actual capability |
| Adoption | Explicit reviewed application to a draft SKU | Existing active structural pins remain immutable; unsupported active adoption is rejected |

PATCH preserves omitted nested fields. Changing an option mode away from OPTIONAL clears its
obsolete default; changing a profile mode away from VALUE clears its obsolete reference.
Explicit contradictory pairs are rejected. Numeric dimension collections remain explicit
replacements (an empty collection resumes inherited defaults); each numeric setting is validated
as a complete precision/increment or precision/currency group.

Existing family/SKU lookups derive their primary group at the requested business date. An
explicit inconsistent group is rejected. Candidate previews without family/SKU identity may
select a proposed type/group. Published revisions and existing adoption pins are never rewritten.

Decision 2026-09-13: approved in-place corrections to editing, inheritance, default authoring,
preview explanations and truthful adoption boundaries, using the existing native authorities.

Selected inventory profiles require `inventory`, plus `batch_tracking` for lot tracking,
`serial_tracking` for serial/IMEI tracking, and `expiry_tracking` for required expiry. These
Identity capabilities are checked on draft selection, effective resolution, readiness and
activation. Creating reusable profile definitions alone does not enable a company capability.

Decision 2026-09-13 (tracking integrity): selected tracking profiles are constrained by each
current company capability, including activation under the normal company transaction lock.

### Sales commercial-configuration review - 2026-10-10

Linked planned Vouchers Sales/Purchase/type/class policies below existing capability and
product restrictions. Native free-sale/discount guards remain authoritative inputs; no
Catalog/Identity runtime setting or feature activation was changed.

### Product configuration console delivery - 2026-10-25

The user authorized the previously deferred console workflow. Reuse the native configuration
tables, dated immutable publication, protected reference validation and signed draft-SKU adoption.
The console now obtains typed controls and aggregate completeness from Catalog field metadata,
and scoped searchable choices from the configuration option endpoint. Hidden or protected
nondefault settings cannot be silently dropped when copying a published revision. Company
capabilities, existing active structural pins and price history remain authoritative.

The [UI/API delivery record](product-configuration-ui-api.md) records phases, checks and limits.

Decision 2026-10-29: configuration reference lookups for `items` reach the closed
configuration policy instead of ordinary item-route classification. Native company,
object and field checks remain authoritative; unsupported methods, sources and
query fields remain refused. Drafts may adopt permitted product defaults effective
today while preserving a future company-default revision. Publication, adoption
and activation remain separate reviews.
## Live product authoring control - 2026-10-28

Decision: add the Catalog-owned current `product_family_sku_enabled` company control
alongside dated configuration, with false as the new-company fallback. It is not
stored in immutable default releases or product adoption pins. Native configuration
permissions and field policies apply. See [simple product API](simple-product-api.md)
for preview/commit, compatibility seeding and guarded downgrade behavior.
