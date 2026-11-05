# Catalog product and inventory design

Current Simple Product delivery (2026-11-04): see [ready on Save](simple-product-ready-plan.md). Catalog owns creation progress, product definitions, GST and prices; Vouchers numbers and posts the opening through Accounting. Local Catalog head is 0218 (183 tables); Accounting head is 0232 (147 tables). Older proposal status below is historical.

**Ownership amendment, 2026-10-10:** [Vouchers](vouchers-plan.md) replaces the planned
Billing/Payments APIs. In the retained design below, Billing document/workflow duties map
to Vouchers; party sources and authoritative money/stock/value effects map to Accounting
(stock posting is proposed, not implemented). Catalog retains definitions. This amendment
supersedes older ownership text; historical wire identifiers are not renamed. Payroll/HR is excluded.

**Status:** Revised implementation proposal, 2026-09-11. API, database and backend workers only.
**Read with:** [Schema and endpoints](catalog-schema.md).
**Bulk workflows and price levels:** [Detailed contract](catalog-bulk-pricing.md).
**Schemes, coupons and discounts:** [Promotion design](catalog-promotions.md).
**Product controls and decimals:** [Product Configuration](catalog-product-configuration.md).
**Complete commercial model:** [Purchase/MRP/selling/unit/batch prices, cost sources and guards](catalog-pricing-design.md).
**Stores and godowns:** [Main, location policies, stock and transfers](catalog-warehouses.md).

**Scope correction:** Catalog-only implementation. Billing owns party/customer source and all
physical stock, transfer/damage/count/adjustment, ledger, coupon-runtime and sale/credit execution.
Those rules below are integration requirements, not Catalog source APIs or migrations.
See [inventory integration](catalog-inventory-integration.md) and [Catalog table inventory](catalog-table-inventory.md).

## 1. Design baseline

Use company-owned product families and sellable/purchasable SKUs. A simple product has
one default SKU; a variant product has explicitly created SKUs. Prices, barcodes, packs
and inventory policies attach to the SKU; tax may inherit through the explicit hierarchy
below. Other master defaults are copied or resolved through a recorded revision; changing a master never silently changes a
posted transaction. Company-to-company reuse is an explicit copy with source reference,
not a cross-company FK or automatic propagation.

| Owner | Authoritative data |
|---|---|
| Identity | Company, departments, capabilities, actors, grants, custom-field definitions, field configuration and policies |
| Catalog | Groups/categories/types, families/SKUs, brands/manufacturers, native attributes, units/packs, product identifiers, warehouses/bins, profiles, prices, tax and promotion/program definitions |
| Billing | Parties/pricing types; physical stock/custody, reservations, valuation/ledger; one promotion evaluator, coupon issuance/usage and bounded sales/credit posting |
| libs/platform | Auth/scope, DB sessions, Decimal/conversion primitives, metadata/custom-field engine, policy enforcement, idempotency, audit, events, projection and list mechanisms |

Opening stock is included through a required Billing inventory phase. Storing an editable
opening_quantity/current_stock on item would lose allocation and accounting history.
No eighth service, cross-service FK, or remote call inside a posting transaction is introduced.
Catalog master storage can precede Billing; customer-type pricing requires Billing's party
source, and stock capability requires its inventory phases. Billing is the recommended
commercial-party owner. Catalog consumes native dated memberships and owns type/customer-to-
price-level assignments. Identity continues to own users and access control.

## 2. Product shape and conditional requirements

A family has code, name, goods/service kind, product type, primary group, category memberships,
optional brand/model and approved manufacturers, description and lifecycle. An item has its own SKU, display name, family, unit profile,
buy/sell eligibility and lifecycle. Code uniqueness is within company; codes and external
identifiers preserve leading zeros. Groups and category schemes have bounded acyclic trees. Tags and descriptions
are descriptive; they cannot determine prices, tax, stock control or permissions.

Drafts may omit activation requirements. Activation validates the full native/custom-field
contract and company capabilities. One lifecycle per entity: draft / active / discontinued
for families/items; discontinued records remain readable and valid on returns/history.

| Field or capability | Goods, inventory tracked | Goods, not inventory tracked | Service |
|---|---|---|---|
| Company, SKU, name, kind, type, primary group | Required; type/group may use explicit Default masters | Required; same defaults | Required; compatible service defaults |
| Base/billing unit and quantity increment | Required | Required | Required; e.g. hour, visit, job |
| Sellable / purchasable | At least one true | At least one true | At least one true |
| Inventory profile | Required | Absent | Forbidden |
| Valuation and stock account mapping | Required before stock posting | Absent | Forbidden |
| Sales/purchase unit | Defaults to base; explicit allowed conversion | Same | Compatible billing unit only |
| Classification and tax treatment | Required when applicable to jurisdiction/direction | Same | Service classification when applicable |
| Sales price | Required to resolve a priced sale; creation may precede price setup | Same | Same |
| Opening stock | Optional document | Forbidden | Forbidden |
| Batch, expiry, serial/IMEI tracking | Optional; dependencies below | Forbidden | Forbidden |
| Barcode/product code | Optional, pack-specific allowed | Optional | Optional internal lookup code |
| Replenishment, warehouse/bin | Enabled as needed | Forbidden | Forbidden |
| Weight/dimensions, shelf life | Optional, typed with units | Optional where meaningful | Forbidden as physical stock fields |
| Warranty/service duration | Optional duration and start trigger | Optional | Optional duration; no inventory implication |

Tax-exempt/zero-rated items have explicit treatment, not a missing mapping. Zero-priced
items require an explicit free-of-charge policy; negative prices are rejected. Credit notes
and returns reverse a transaction; they do not create negative-price products.

Structural fields (kind, base unit, variant dimensions and tracking mode) freeze on
activation, before downstream services can consume the item. Safe descriptive edits use
row versions. A pack-ratio change creates a new pack revision; tracking or base-unit
changes require an explicit migration/replacement SKU, not ordinary PATCH.

Product Configuration adds typed company/type/group/family defaults and permitted SKU overrides.
It composes with Identity capabilities and field permissions; it cannot bypass either. Default
changes affect future activation, while existing-SKU adoption uses an explicit reviewed workflow.
The [configuration contract](catalog-product-configuration.md) defines required/optional/disabled
options, pinned profiles and numeric rules; generic custom fields never control these decisions.

### Master hierarchy and inheritance

Groups and categories are separate concepts: TallyPrime also uses stock categories for
classification across stock groups. Our cardinality and inheritance rules below are explicit
platform decisions. [TallyPrime stock classification](https://help.tallysolutions.com/knowledgebase/manage-stock-item-tally/).

| Master | Purpose and relationship | Defaults / control |
|---|---|---|
| Item group / subgroup | One primary hierarchy, e.g. Electronics > Phones > Smartphones; subgroup is the same entity with a parent, not a separate table | Tax/commercial defaults and group-level analysis; bounded depth 8, no cycles or cross-company parent |
| Category scheme / category | Independent trees such as Usage > Office or Season > Summer; multiple memberships, optional one primary within each scheme | Search/reporting/merchandising; no implicit tax or price inheritance |
| Product kind | GOODS or SERVICE | Fixed code-owned behavior; cannot be extended into arbitrary tenant-defined financial behavior |
| Product type | Smartphone, apparel, consumable, consulting; one kind and a versioned native requirements template | Attribute set, allowed unit dimensions, supported tracking/stock modes and defaults; cannot weaken company or native invariants |
| Product family / model | Shared product identity and variant axes; optional model/catalogue number | One primary group at a time; SKUs share this group; model is not a duplicate SKU master |
| Brand / series | Commercial identity, optional sub-brand and product series | Separate from manufacturer and category; primary brand on family, optional governed associations |
| Manufacturer / site | Actual producer/OEM/contract manufacturer and production site | Many manufacturers may serve one brand/product; approved sources on product, actual source on lot |
| Attribute set / option lists | Reusable native specification such as size/colour/material/grade or voltage/capacity | Type/family requirements; reuse typed attribute options instead of unrelated size/colour tables |
| Unit / pack type | UOM, package form (box, bottle, strip, bag), SKU pack revision | Pack type is a label/shape; actual conversion remains SKU-specific |
| Tax classification / category / rule | Official classification, native tax applicability category and dated component rules | Separate from merchandising category; goods/service/jurisdiction validation |
| Commercial masters | Price level, currency price plan, channel, customer-pricing-type assignment and discount policy | At least three configurable levels when enabled; customer/supplier memberships come from their authoritative party owner |
| Operational profiles | Tracking/device, warranty, return, handling, replenishment | Versioned typed rules; supported capabilities only; snapshot required obligations |
| Location and stock controls | Warehouse/bin, fixed stock dispositions, adjustment/return reasons | Catalog owns locations; Billing owns operational disposition/reason semantics and account mappings |
| Product relationships | Alternative/substitute, accessory, replacement/supersession | Typed, directional relations; no automatic substitution or transfer of stock/serial identity |

A family has exactly one active primary-group assignment at a date; verified company
enrollment provisions a real Default type and group for simple setups. Existing General
and custom masters are retained. Groups can contain subgroups and direct families. Categories are
assigned separately through scheme-qualified links; adding a Summer category never changes
a tax outcome. A category may explicitly target a promotion under its declared frozen/live
population policy. Category joins must not multiply SKU rows or reporting totals.

Product types are editable business masters backed by supported code-defined validators.
A type revision may require IMEI tracking for a device or an attribute set for clothing.
Apply it when creating/activating a family/SKU and store the selected revision. Changing the
template does not retroactively mutate active products. Require a validated migration for
existing products; no arbitrary expressions, SQL or tenant-invented stock modes.

Brand ownership/licensing is not inferred from manufacturer. Optional brand-owner, importer,
marketer and supplier references use the party-owner contract; financial/tax/legal party data
is not duplicated in Catalog. Product-approved manufacturers/sites are many-to-many, while
the actual lot producer is recorded once for traceability. Manufacturer changes must not
reassign old serial-number namespaces.

### Group-level tax resolution

Use this precedence independently for the classification, tax-treatment and rule-selection
bundles, within the same jurisdiction, sale/purchase direction and posting date:

**SKU override > family override > nearest subgroup > ancestor groups > company Catalog tax default.**

Each dated binding has INHERIT, OVERRIDE or REQUIRE_EXPLICIT mode. An absent binding inherits;
OVERRIDE must contain a complete valid bundle. REQUIRE_EXPLICIT stops ancestor fallback and
blocks use until a lower-level explicit binding supplies that bundle. Zero-rated/exempt is
an explicit treatment, never a missing value or a shortcut for inheritance.

Keep classification + code system together, treatment + exemption evidence together, and the
rule-selection context together. Allow a SKU-specific classification with a group-inherited
rate rule, but validate the resolved combination against the supported jurisdiction adapter.
Never merge unrelated fragments into an invalid tax configuration. Item-specific mandatory
classification cannot be bypassed by a broadly configured group.

The company fallback is an explicit Catalog tax-policy record. It is NOT Identity's
company.default_tax_system, which only supplies creation-form defaults. Categories, tags,
brands, manufacturer and product type do not silently become competing tax sources.

Return effective values, inherited/overridden status, source owner/binding revision and
source path per bundle. Group changes take effect by date; a SKU override remains until
explicitly reset to inheritance. Resolve the dated group membership and ancestry, not
today's tree, when preparing a historical transaction. Posted documents retain snapshots.

Example using illustrative rule names: Electronics supplies Rule A; Phones supplies Rule B;
a family without an override uses B; one SKU explicitly using Rule C stays on C after Phones
changes to Rule D next month. Another SKU may supply its own classification while inheriting
B/D. These rule names are not statutory rate recommendations.

A tax override needs tax-management authority plus resource/field scope; ordinary group
rename permission cannot change tax. Missing jurisdiction context, blocked inheritance,
ambiguous dates or incompatible bundles produce explicit errors.

### What else may inherit

| Setting | Resolution |
|---|---|
| Tax bundles | Live, effective-dated hierarchy above; native jurisdiction validation always wins |
| Discount ceilings | Effective company/group/family/SKU guardrails combine restrictively; use the smallest allowed maximum discount |
| Absolute prices and MRP | Explicit SKU/pack/currency histories; never infer one amount for a mixed-unit group |
| Unit, attribute, tracking, warranty and return profiles | Type/group creation defaults: explicit request > nearest group default > type template > company default; conflicting mandatory requirements fail activation |
| Reorder quantities | Explicit SKU/location values; group may default lead time/profile, but cannot copy a quantity across incompatible base units |
| Accounting assignments | Billing-owned dated mappings by SKU > family > nearest group > company; validate accounts locally at posting |
| Custom values and field permissions | Existing Identity/shared resolution only; group membership neither grants access nor copies arbitrary custom values |

For warranty/return/handling profiles, define native supported terms (duration/start trigger,
return window/eligible condition, storage constraints) and versioned attachments. General
handling metadata is included; hazardous/cold-chain compliance must not be advertised until
its dedicated validation/execution exists. Return operations enforce the selected native
return policy; warranty claim/service workflows remain a separately bounded extension.

### Master governance

Every configurable master has a stable code, scoped uniqueness, name/optional aliases,
lifecycle, version, audit and usage references. Use code registries for product kind,
calculation kinds, movement types and stock dispositions; master creation never invents
executable behavior. Share CRUD/lookup/import mechanics, while keeping typed service-owned
tables and domain validation.

- Group moves and family reassignment are effective-dated actions with subtree cycle/depth
  checks, previewed tax/default changes, required override permissions and reason.
- Large changes use prepare/validate/publish jobs. Bind publication to reviewed input versions
  and a company policy generation; a new concurrent descendant/override invalidates the preview.
  Ordinary moves apply today/future; historical corrections retain prior releases and use
  a separately controlled action.
- Publish a dependency manifest for hierarchy/bindings/assignments. Billing activates the
  required release only after its local dependencies are complete; no half-old/half-new tax tree.
- Deactivate blocks new assignments and preserves existing/history references. Reject
  deactivation with active dependants unless an explicit reassignment plan is applied.
  Tax bindings do not disappear merely because a display master was deactivated.
- Duplicate cleanup preserves aliases and historical IDs. Merge/reparent never cascades
  destructive updates into posted documents; cross-company copying uses explicit ID mapping.
- Imports use scoped stable source keys, dry-run validation and dependency order. Resolve
  names only through explicit mappings, not fuzzy guesses. Provide usage and change-impact APIs.
- All masters have backend metadata and native field policies. Descriptive custom values
  additionally cover groups, categories, product types, brands and manufacturers through
  explicit Identity registrations; they do not inherit into SKU calculations.

## 3. Units, conversions and packs

Borrow TallyPrime's distinction between simple units, compound units with a fixed
relationship, and alternate units whose relationship can depend on the item or actual
transaction. These are distinct concepts in its [stock-item documentation](https://help.tallysolutions.com/stock-items-faq/).
The following precision and persistence rules are this platform's design.

| Concept | Example | Contract |
|---|---|---|
| Simple unit | piece, kg, litre, hour, job | Code, symbol, dimension, allowed decimal places (0–4), quantity increment; optional jurisdiction UQC mapping |
| Fixed dimensional conversion | 1 kg = 1,000 g | Same dimension; positive reduced integer numerator/denominator to a canonical unit |
| Item pack / alternate sale unit | 1 box = 12 pieces for SKU A; 24 for SKU B | SKU-specific pack revision; purchase/sales eligibility, exact base ratio, optional barcode, dimensions and weight |
| Compound entry | 2 boxes + 3 pieces = 27 pieces for a 12-pack | Structured components converted and summed; 2.3 boxes never means this |
| Measured dual quantity | 1 sack nominally 50 kg, actual 49.6 kg | Retain both entered counts and measured base weight; nominal ratio is not authoritative |
| Service unit conversion | 90 minutes = 1.5 hours | Only declared compatible units; job-to-hour requires explicit service-specific commercial mapping |

One stock base unit per SKU. Normalize fixed conversions directly to base/canonical units,
avoiding ambiguous chains and cycles. Never globally convert count to mass or litres to kg;
item-specific measured relationships require explicit profiles and measurements.

Use integer ratios, Decimal arithmetic and sufficient intermediate precision. Persist
quantities as DECIMAL(19,4); validate unit precision, increment, range and exact
representability before SQL. Reject conversion residues rather than silently rounding stock.
For finer measurements choose a smaller base unit. Serialized stock requires integer
base quantities and one physical unit per base count.

Quantity precision and increments belong to the selected unit revision. Price precision belongs
to a dated SKU/unit/currency entry policy, separate from company amount precision. Preserve a
price's explicit basis quantity (per 1/100/1,000 units); never round the derived unit rate before
multiplication. Company quantity presentation must not hide a valid finer transaction quantity.

Every document line snapshots entered quantity/unit, base quantity, pack/conversion ID and
revision, exact ratio or actual dual quantities, price basis and rounding. A later pack change
cannot alter an earlier invoice or stock balance. Pricing may use either declared quantity
basis for measured goods; valuation uses the stock base quantity. Repacking changes packaging
evidence where needed; it does not create or destroy base stock.

## 4. Native attributes, variants and custom fields

| Mechanism | Purpose | Storage and behavior |
|---|---|---|
| Native attribute | Size, colour, grade, model/capacity, other supported product characteristics | Catalog-owned typed definitions/options and item values; explicit variant-axis flag |
| SKU variant | A specific purchasable/sellable combination | One SKU per exact family axis combination; unique canonical combination; no automatic Cartesian explosion |
| Custom field | Tenant-specific descriptive information | Identity-defined types/policies; values validated/indexed by shared machinery; no money or stock decisions |

A family declares its axes and allowed typed options. Each variant must supply exactly one
value per axis; retired options remain readable. Variant prices are selected by SKU, not
an arbitrary attribute expression. Changing axes after activation requires a new family
version/replacement, with an explicit mapping for migration.

Keep tax classification, conversion, warranty duration, lot/serial requirements, price basis
and reorder thresholds native. Adding a tenant custom field called cf_tax_rate cannot make
it participate in calculations. Native attribute extensibility also does not permit executable
tenant expressions or arbitrary price formulas.

Custom values are supported on catalog.product_family, catalog.item, catalog.item_group,
catalog.item_category, catalog.product_type, catalog.brand, catalog.manufacturer,
catalog.price_plan, catalog.tax_rule, catalog.campaign and catalog.promotion. Native metadata/
policies additionally cover units, packs, stock profiles, prices/tax histories, coupon programs,
limits, holds, approvals and sale/credit actions. Warehouse and physical-instance custom fields are later registrations,
not implicitly supported by having a generic JSON engine.

## 5. Barcodes, batches, expiry and physical identifiers

**Product identifiers:** multiple codes per SKU/pack: internal barcode, validated GTIN where
applicable, manufacturer part number and scoped supplier code. Global-standard codes resolve
uniquely inside the company; supplier codes resolve within supplier namespace. A barcode is
a string, not an integer. A SKU code and a physical serial are different namespaces.
Deactivated codes retain historical ownership and cannot silently move to a different product.

**Scanning:** return the matched SKU, pack revision and parsed tracking information with
structured errors for unknown or ambiguous codes. GS1 uses separate identifiers for GTIN
(01), lot (10), expiry (17), and serial (21); support these through an explicit parser contract,
not by treating the entire payload as an ordinary SKU barcode.
[GS1 identifier registry](https://ref.gs1.org/ai/?lang=en).
No fetching URLs embedded in scanned codes.

**Tracking profile:** independently enable lot tracking and serial tracking; both may coexist.
Expiry requires lot tracking under the existing company feature dependency. Define expiry
requiredness, manufacturing-date requiredness, default shelf life, saleable-life minimum,
issue selection (FIFO/FEFO) and permissioned override rules. FEFO selects by expiry;
it is not a costing method. Missing mandatory tracking data blocks posting.

**Lot:** company + SKU + manufacturer/source namespace + batch code, optional manufacture,
expiry and best-before dates, supplier/manufacturer reference and quality hold. Repeated
receipts can reference the same lot; conflicting dates require an audited correction action.
Warehouse, quantity and value belong to allocations/movements, not the lot header.
Expiry precedes neither manufacture nor best-before when supplied. Shelf-life defaults are
explicitly derived and recorded; they are not evidence of a manufacturer's date.

**Physical unit:** one serialized unit belonging to one SKU, optionally one lot. It owns
a collection of identifiers, e.g. SERIAL plus IMEI slot 1 plus IMEI slot 2. Identifier count,
required types, namespace and slot uniqueness come from a native device profile. Do not put
imei1/imei2 columns or an unvalidated array on the product. Multi-SIM equipment can require
multiple device identities; the model accommodates different profiles.
[GSMA multi-SIM requirements](https://www.gsma.com/get-involved/working-groups/gsma_resources/ts-37-requirements-for-multi-sim-devices/).

Enforce type-specific checksum/format validation. An IMEI cannot identify two units within
one company; serial uniqueness is manufacturer/SKU-scoped as declared by the profile.
No global cross-tenant uniqueness query that reveals another tenant's inventory.
Preserve original and canonical identifier forms; restrict identifier search/export and logs.

One unit has one current custody/stock position. Opening/receipt allocates it once; issue,
transfer and return move the same unit. Re-receiving a returned unit retains identity.
Allocations must contain exactly the serialized base quantity, with no duplicated IDs.
Expired, recalled, quarantined or damaged stock remains visible but cannot be allocated
as saleable stock. Overrides, where allowed, require a dedicated permission and reason.

## 6. Warehouses, opening stock and inventory integrity

Catalog owns warehouse and optional bin masters, including company/department scope.
Create a real default warehouse even when multi_godown is off. Billing projects these masters
and owns stock at SKU + location + lot + condition + ownership dimensions. Company-owned
stock is the first supported ownership mode; consignment cannot be enabled until its custody
and accounting rules are implemented.

Opening stock is a draft/validated/posted/cancelled document with business date, source import
reference and lines. Each line specifies SKU, location, entered/base quantity, cost/value and
currency, tracking allocations, and any measured quantity. Batch dates and serial identifiers
can be entered through these API allocations. Validation returns line-level errors before posting.

Posting must:

1. Check the books-begin/cutover date, fiscal period, permissions and feature/profile revisions.
2. Reconcile line totals with lot/serial allocations; reject negative opening quantity and
   nonzero value with zero quantity. Free stock needs explicit zero-cost justification.
3. The proposed Accounting owner creates append-only stock movements and required financial
   effects under the Vouchers command contract; persist valuation, supplied currency/FX,
   unit/profile snapshots, audit and outbox. If the asset opening is already posted through
   Accounting's entered-opening workflow, link/reconcile it rather than post it again.
4. Link stock and financial openings through one reconciliation batch with explicit provenance:
   either the authorized combined opening supplies the asset value or it matches existing
   financial opening facts. Never count both. A stock-only reconciliation still needs source,
   valuation and first-use guards; no dummy second journal is created.
5. Deduplicate retries by idempotency key and source-system/document/line identity.
   A fresh request key must not permit importing the same opening document twice.

An initial books-begin opening and a later inventory cutover are distinct document reasons.
A cutover requires a reconciled accounting adjustment at its authorized date. They are not
ordinary item edits. Year rollover carries stock forward; it does not re-post opening stock.

Posted corrections use linked reversals/adjustments in an open period. If units were consumed
or sold, reversing an opening is rejected or replaced by a controlled adjustment with cost
recalculation. A posted opening cannot be overwritten by re-import.

The separately owned Billing inventory kernel must support receipts, issues, returns, transfers,
adjustments, reservations and opening documents. Actual sales/credits and coupon execution are
also Billing work, outside this Catalog implementation. The integration contract specifies
explicit discrepancies, transfer charges, damage custody/write-down/disposal and physical counts.
Unadjusted transfer legs preserve company quantity/value; approved charges/losses are separate effects. Reserve and issue lock the same stock scope,
preventing concurrent overselling. Negative stock is disabled in the initial implementation.

Valuation is selected explicitly: FIFO or moving weighted average; specific identification
is available for serialized stock with per-unit cost. Implement every offered method before
exposing it. Freeze method once posting begins. Cost layers, landed-cost/valuation adjustments
and rounding residuals belong to Billing; cost is not the catalog sale price. The activated
inventory profile pins its requested valuation method; Billing additionally records first use.
Backdated stock writes that would reorder existing valuation require a controlled revaluation
workflow; reject them until that workflow is available.

Product stock ledger reads and physical count/adjustment/damage documents belong to Billing;
Catalog publishes exact unit/profile/location rules and preserves source history. Warehouse groups
organize physical stores without holding stock or expanding actor access.

The [stock recording/reporting design](voucher-stock-recording-reporting-design.md) makes
current/item/group/location/batch/expiry/age/value reports explicit. Dated classification,
receipt-origin, lot correction and hold histories must be recorded from first execution;
valuation layers alone cannot reconstruct remaining-stock age under moving average.

## 7. Minimum stock, replenishment and supplier terms

TallyPrime distinguishes reorder level from minimum order quantity. Keep that distinction
in this design. [TallyPrime reorder documentation](https://help.tallysolutions.com/tally-prime/inventory/reorder-stock-items-reorder-status-and-reorder-quantity/).

Maintain a company default profile with explicit per-warehouse overrides:

- Safety/minimum stock, reorder point, target/maximum stock and lead-time days.
- Minimum/maximum order quantity, order multiple and purchase pack.
- Preferred supplier, supplier SKU, supplier-specific lead time and order constraints,
  using an explicit party reference/projection contract.
- Optional minimum sales quantity and sales increment, independent of reorder settings.

All thresholds use base quantity; expose converted purchase quantities separately.
Validate 0 <= safety_stock <= reorder_point <= target_stock; maximum order may be absent.
An override is explicit, not a null that unpredictably inherits a changing default.

saleable_on_hand excludes blocked/expired/non-owned stock; available subtracts reservations
against those included saleable buckets. Reservations that became expired/blocked are flagged
for reassignment, not subtracted twice. projected_available additionally includes confirmed
incoming supply and subtracts outstanding demand not already reserved, within an explicit
lead-time horizon. Return the contributing quantities,
as_of and projection freshness. If supply/demand producers are absent, expose unavailable
inputs; do not imply zero incoming is a verified fact.

Suggestions declare their basis: available stock by default, or projected stock only with
complete supply/demand inputs. At/below reorder point, suggest enough to reach target, subject to MOQ,
order multiple, max order, conversion and lead time. Explicitly report over-target rounding
or incompatible constraints. No automatic purchase order is implied. Consumption forecasting
is a future extension; deterministic thresholds are included now.

### Store/godown policy

Every company has a real built-in Main warehouse, including metadata-only service companies.
Inventory enabled with multi_godown disabled uses Main exclusively. Enabling multi_godown permits
additional stores/godowns with independent sale-issue, purchase-receipt, transfer, return and
opening controls. Main remains the system fallback; activity defaults can differ when enabled.

Billing holds stock/reservations/cost by actual location; company totals never satisfy a shortage
at a selected store. Product allowlists only restrict location policy and actor scope. Transfers
preserve quantity/value/lot/serial identity, using explicit immediate or dispatch/receive mode.
The [warehouse contract](catalog-warehouses.md) defines transit accounting, default resolution,
acknowledged policy changes and deactivation checks. No default/flag change moves or erases stock.

## 8. Enterprise pricing

A company may enable multi_price_levels: Price 1, Price 2 and Price 3 are named master rows,
with more allowed. Customer pricing types A/B/C can map to those levels; a customer-specific
level assignment overrides its type. Ordinary callers cannot select a cheaper level themselves.
The full selection/fallback/import contract is in [bulk operations and customer price levels](catalog-bulk-pricing.md).

A price level is currency-independent. Its sale price plans specify currency and tax basis;
effective series specify SKU/unit and context. Resolve permissioned explicit level override
> customer assignment > pricing-type assignment > company default, then find that level's
currency plan. Within that plan use customer > channel > standard SKU price.
Within audience precedence, enabled declaration/lot/SKU and unit specificity follow
the fixed pricing-companion order; REQUIRED stock scope filters candidates before ranking.
Purchase books and reference retail are separate purposes. Cost estimates, physical declarations,
typed recipes and minimum/maximum guards follow that same companion, not scalar item price fields.
Equal-rank matches fail; missing price coverage defaults to ERROR, with one explicitly configured
same-currency fallback level optionally allowed. Zero is not missing. Quantity tiers are separate.

- Volume tiers use quantity intervals [minimum, maximum); one selected tier prices the whole
  line. Progressive/slab charging is a separate future calculation type and rejected initially.
- Effective dates follow the repository's inclusive date contract; lock a stable series row
  before inserting or replacing any range, including its first row.
- Customer/type/supplier targets use native references and locally validated dated memberships.
  Billing supplies the authoritative customer/type source through its own API plan. Catalog C5
  consumes it before C8 enables customer pricing; supplier references use that same party source.
- Unit/pack and currency match explicitly; no hidden FX fallback. Foreign-currency prices
  require the company capability. Each conversion and discount basis is recorded.
- Minimum sale price / allowed discount and dated MRP limits are native policies. MRP may
  be pack/lot-specific where relevant. Margin checks require authoritative current cost in
  Billing; a stale catalog cost projection cannot guarantee a margin.
- Price resolution returns amount/currency, level/assignment, unit basis, tax basis, tier, source IDs/versions
  and applied policy context. Billing snapshots these when posting. Changes never reprice
  existing documents. Purchase prices, stock cost and sale prices remain separate concepts.
- Automatic discounts, schemes, gifts, bundles and coupons use one native promotion model;
  Billing evaluates them after regular-price selection. Combined benefits obey restrictive
  ceilings/floors and explicit stacking. Manual discounts use the same allocation/guard path.
  See the [promotion contract](catalog-promotions.md) for limits, approvals, tax and returns.

### Schemes, coupons and promotional stock

Catalog owns campaign/promotion/coupon-program definitions; Billing owns code issuance,
live quotas, holds and redemptions. A code activates a benefit, never replaces price-level
selection. The default is one offer; permitted stacking is explicit and deterministic.
Buy 10/get 2 means 10 paid plus 2 reward units. Gifts use ordinary stock/lot/serial/expiry
rules and cost posting. Services can receive a benefit without acquiring stock behavior.
Use original allocated benefits for returns, not today's rules. Posted usage and history
survive campaign revisions; the P0–P5 workstream includes actual sale/credit integration.

### Bulk import and update

Use versioned CSV/XLSX templates or JSON batches with explicit CREATE_ONLY, UPDATE_ONLY or
UPSERT intent. Stage, validate, preview and then commit reviewed changes through the same
domain/policy handlers as ordinary APIs. Group/unit/brand references and custom fields must
resolve; dependency errors are reported before writes. Opening stock has its own Billing flow.

Bulk update accepts a file or an authorized filter plus typed action. Preview freezes exact
IDs/versions and before/after changes; commit rejects intervening edits. Blank/omitted means
unchanged; clears/removals are explicit. Percentage price changes create effective history
from the reviewed baseline. Selected price levels for a SKU can commit together.

Small same-service batches offer bounded atomic mode; large jobs commit per change set with
explicit partial results, safe retry and stop/continue policy. Cancellation does not undo prior
commits. See the [workflow and API contract](catalog-bulk-pricing.md) for modes, errors and examples.

## 9. Tax and commercial history

Native classification/treatment/rule bindings are effective-dated at company, group, family
or SKU scope, by jurisdiction and sale/purchase direction. Resolve them through section 2's
hierarchy and record source provenance. Support goods/service classification (such as HSN/SAC for a supported GST module),
tax category, taxable/exempt/zero-rated/out-of-scope treatment and exemption reason/reference.
Names of treatments do not imply identical legal semantics across jurisdictions.

Tax rules have typed applicability, dated components, percentage or supported per-unit fixed
amount, currency/unit for fixed amounts, rounding order and explicit component dependency.
Reject dependency cycles and unimplemented calculation kinds. Include reverse-charge
applicability and relevant tax-inclusive basis as native data, gated by company capabilities.

Catalog owns definitions. Billing evaluates them using posting date, seller/buyer registration,
place of supply, ship-from/to and transaction type, and snapshots resolved classification,
rules, component bases/rates/amounts, exemption evidence and rounding. Missing context is an
error. A numeric rate alone is insufficient to determine a tax liability.

No jurisdiction or statutory rate is invented by this plan. Implement a jurisdiction adapter
and source dated seed data from that jurisdiction's official authority before enabling it.
Changes create effective history with versioned supersession; published values remain
addressable, and corrections never mutate a posted document's snapshots.

## 10. Delivery bounds

Included: group/subgroup and category schemes, product types, brands/manufacturers/sites,
typed reusable profiles and master governance, goods/services, variants and native attributes, exact/compound/measured units,
packs/barcodes, batch/expiry/serial identifier profile definitions, location and replenishment
policies, at least three customer price levels and external-customer mappings, quantity/context
pricing, Catalog bulk import/update, tax definitions, custom fields and field policies, and native
scheme/promotion/coupon-program definitions. Actual lots/units, stock, counts/damage/adjustments,
product ledger, manual-discount approvals and sales/credit/redemption posting belong to Billing.

Optional planned extension: [BOM/manufacturing definitions](catalog-manufacturing-design.md)
cover real-SKU outputs, make/buy profiles, alternative/multi-level/phantom structures, exact
inputs/yield/batches, substitutions, routes, quality specifications and reproducible estimates.
M0-M4 adds 20 tables and 40 tasks. Goods/service identity, unit conversion and sales bundles
remain distinct. Manufacturing orders, consumption/output, WIP and actual costs remain external.

Explicit further extension points: sales kits, production execution/rework/disassembly,
consignment ownership, rental/assets,
subscription renewals/proration, contract-agreement pricing, forecast replenishment, stored-value
gift cards, loyalty/wallet/cashback, cumulative rebates and purchase-side supplier schemes. Do not expose
their feature flags or accept pretend configuration before their API/DB rules exist.

Jurisdiction selection, source contract versions and workload targets are deployment inputs.
Billing party/fiscal/stock/runtime sources are explicitly named external dependencies. Their
absence blocks dependent Catalog features; it does not authorize implementing them in Catalog.

## Decision log

- 2026-11-04: Removed warehouse/location-specific regular pricing from the design.
  Price selection retains audience, stock scope and unit specificity; stock and
  replenishment location controls keep their own rules.

- 2026-10-10: Added the detailed stock-reporting contract and clarified initial stock's
  reconciliation to already-posted financial openings. Receipt-origin age is independent
  from costing; product definitions still do not store physical quantities or lot balances.

- 2026-10-10: Superseded Billing/Payments ownership with the Vouchers/Accounting mapping
  at the top of this document; Catalog retains definitions. Payroll/HR is excluded.

- 2026-10-05: Tax publication hardening (tax-accounting Phase 2). Supersession never shortens a
  definition already in force; split GST components share rounding; goods HSN excludes chapter 99;
  company and BOTH-group defaults are kept per product kind; previews authorize first and are
  rate-limited. Releases too large for the 256-product synchronous preview publish against a
  chunked background impact review bound to the policy generation (see the tax API).

- 2026-09-14: Category schemes gain native required membership and an impact-reviewed policy
  transition. Active-family categories gain strictly future-dated reviewed replacements;
  existing membership history and activation pins remain. Current scheme policies apply to
  readiness; category axes remain independent of price/tax inheritance. Ambiguous bulk category
  codes require IDs/external keys. See the classification API for limits and migration safeguards.


- 2026-09-11: Moved BOM definitions from an unspecified extension point to optional M0-M4
  design. Kept production execution, actual manufacturing cost and physical genealogy outside Catalog.

- 2026-09-11: Expanded commercial definitions for independent unit prices, purchase terms,
  multiple declarations per lot, estimated versus actual cost, native recipes and final-price guards.

- 2026-09-11: User restricted implementation to Catalog. Physical/financial rules are retained
  as external integration contracts; customer source and stock ledger never become Catalog masters.

- 2026-09-11: Added the always-present Main and concrete multi-store/godown stock controls;
  purchase/sale flags, activity defaults, transfers and safe operational policy changes are native.
- 2026-09-11: Added native Product Configuration, independent quantity/price precision and
  exact rate-basis rules, with safe defaults/adoption and no loss of existing tracking/history.
- 2026-09-11: Replaced blanket promotion deferral with native schemes, coupons and discount
  contracts in P0–P5. Added Billing's sole evaluator/usage authority and bounded sale/credit
  integration; category targeting is explicit and does not change tax inheritance.
- 2026-09-11: Consolidated ownership and sequencing: Billing party APIs precede pricing,
  shared jobs precede bulk workflows, and Catalog delivery precedes stock posting. Pinned
  activated valuation profiles and separated unsupported agreement pricing from customer exceptions.
- 2026-09-11: Specified optional multi_price_levels with at least three levels, native
  customer-type/individual assignments, and concrete bulk import/update semantics.
- 2026-09-11: Added primary groups/subgroups, parallel category schemes, native product-type
  templates, reusable masters and explicit dated tax/default inheritance after the user's
  master-data review. Expanded custom-field registrations and safe master-change contracts.
- 2026-09-11: Replaced the earlier simple-master assumptions with this richer baseline at
  the user's request. Goods/services, conversion, tracking and opening stock are included.
- 2026-09-11: Kept company ownership; added families/SKUs rather than cross-company shared
  mutable masters. Native commercial/stock behavior remains distinct from custom metadata.
- 2026-09-11: Proposed Catalog master ownership plus Billing inventory/valuation ownership,
  with the required Billing phases visible in the plan. This is a design proposal, not
  evidence of implemented APIs, migrations, tax compliance or stock posting.


## Draft product delivery increment (2026-09-12)

V1.2 starts with a simple family and its single default SKU created atomically. Routes use
`product-families` and `items`; existing `item.create/read/update` permissions govern both,
with separate native/custom field policies. Product type revisions must already be published.
Kind and base-unit dimension must match the revision. Existing brands/series are scoped and
active. No implicit product type, unit or group is created.

Current delivery includes explicit variant creation, dated group/category assignments, SKU
unit revisions, configuration adoption and activation. A nullable unique `default_slot` is 1
for the default SKU and NULL for explicit variants; initial family creation remains SIMPLE.
SKU code, name, sellable/purchasable and positive exact minimum sale quantity are native.
Structural and descriptive PATCH currently require a DRAFT family/SKU. Active-family category
maintenance uses the reviewed, future-dated replacement command. An active family accepts
new DRAFT variants and SKU-level authoring of those drafts (the SKU itself must be DRAFT).
Other active-product maintenance and discontinuation commands remain undelivered lifecycle work.
Kind/type and base-unit identity remain immutable through these draft PATCH routes.
The original paired product tables are migrations 0062-0063; later native authoring extends
through 0082 and activation is documented separately below. Custom JSON remains descriptive.


Decision 2026-09-12 (V1.2): implemented native configuration and product authoring through
migration 0082. See [V1.2 routes and constraints](catalog-v12-api.md). Earlier checkpoints
above remain historical; activation is documented in [V1.4 contracts](catalog-v14-api.md).

Decision 2026-09-13 (product integrity): family/default-SKU attribute replacement requires
both expected versions. Closed option lists cannot be bypassed with scalar values. Unit and
minimum-sale grids validate all affected current/future intervals; alternate bindings alone
do not constitute compound entry. Active descendants block group moves until their adoption
history can be migrated. Detailed command semantics are in [the authoring API](catalog-v12-api.md).

Decision 2026-09-13 (unit integrity): a shared declared canonical root governs SKU fixed
ratios. Adding a declaration validates retained SKU history; undeclared containers retain
product-specific pack sizes. Product and bulk preview ratio values are exact integer strings,
with legacy integer requests preserved. Serial base rules remain whole-count throughout
scheduled revisions; quantity and pricing consumers reject invalid existing rules.
Measured entry requires distinct unit identities without a shared canonical relation and an
actual base measurement. Measured mode cannot override a declared fixed conversion.
Composed arithmetic uses unbounded rational intermediates, followed by exact DECIMAL(19,4)
and target-grid validation. These corrections add no physical stock or active-product
migration workflow; the [unit API](catalog-unit-api.md) records the implemented limits.

Decision 2026-09-14 (Product Tax integrity): classifications cover complete binding intervals,
and rule applicability is native HSN/SAC exact/prefix data frozen once used. Used or legacy
rules needing changed applicability require replacement rules. GST splits/ceilings and
compensation-cess definitions are validated across dated supply contexts. Reviewed coordinated
changes and future withdrawals retain all source records and predecessor evidence. Activation
checks known future tax boundaries. Tax categories, rules and classifications participate in
native options, aliases, external keys and usage. See [the tax API](catalog-v14-api.md) for the
review bounds, migration/downgrade constraints and Billing responsibility boundary.

Decision 2026-10-06 (sibling authoring): the line listing "sibling authoring after family
activation" as undelivered was stale. Since 2d091fd an ACTIVE family accepts new DRAFT
variants and SKU-level authoring of those drafts, matching
[catalog-attributes-api](catalog-attributes-api.md); an ACTIVE SKU, a DISCONTINUED family or an
exhausted `row_version` still returns 409.
## Simple product authoring - decision 2026-10-28

Users may author a single product without separate family/SKU inputs through the
[simple product API](simple-product-api.md). Storage remains one ProductFamily and
its default Item. Company mode controls variant authoring; inventory profiles,
ordinary specifications and operational item identity remain independent. This
decision extends authoring and presentation without introducing a second product
table or changing stock ownership.

## Company starter masters - decision 2026-10-30

Every active, enrolled company receives one ProductType and one ItemGroup initially
named `Default`, code `DEFAULT`, with BOTH kind compatibility. Catalog's authenticated
Identity source refresh owns provisioning for new and existing enrolled companies,
including companies created through APIs. This is asynchronous provisioning after
company creation; it does not couple Identity's company transaction to Catalog.

A newly created type receives a published, validated baseline: NON_STOCK, NONE
tracking, supported unit dimensions, optional variants, and no required brand,
manufacturer or expiry. STOCK is admitted only when the current verified company
snapshot enables inventory. The group receives a root hierarchy edge. This creates
one type and one group, with their supporting revision and hierarchy records.
Later feature changes and product configuration adoption use ordinary reviewed type
publication; provisioning never broadens an existing published policy automatically.

Provisioning reuses the DEFAULT code even after a rename, or an existing named
Default with an alternative code. It preserves General/custom records and existing
published revisions. Inactive, incompatible or unpublished existing defaults require
review. The company policy lock prevents duplicate concurrent creation, and native
system outbox evidence commits atomically with the defaults. No existing products
are reassigned. The wizard verifies the pair and a published type revision through
bounded, scoped reads. See [the implementation review](company-product-defaults-review-2026-10-30.md).
