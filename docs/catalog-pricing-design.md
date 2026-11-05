# Product, unit, batch and cost-aware pricing design

**Product Configuration delivery, 2026-11-04:** Six explicit company configuration
controls now gate existing multiple selling levels, alternate-unit prices,
quantity tiers, channels, additional currencies and formulas. New companies start
with all six disabled and one level; migration 0216 preserves legacy behavior with
INHERIT. These controls apply through the product's effective/adopted configuration.
See [the implemented contract](catalog-product-configuration.md#automatic-starter-and-pricing-options--2026-11-04).
Initial batch pricing is implemented by the
[Simple batch-entry slice](simple-product-batch-opening-plan.md): verified LOT scopes,
per-batch sale/purchase rates and Accounting-owned initial physical MRP. Wider
physical-declaration allocation and downstream voucher UI work remain planned.

**Pricing scope decision, 2026-11-04:** Warehouse/godown/store-specific regular pricing
is excluded from the plan. Price definitions, configuration, imports and resolution
have no location override or location-ranking dimension. Stock locations, warehouse
valuation pools, tax context and physical allocation retain their separate rules.
Sales channels remain a commercial pricing dimension, not a warehouse selector.

**Ownership amendment, 2026-10-10:** [Vouchers](vouchers-plan.md) replaces planned Billing
and Payments APIs. Retained Billing references map document/basket preparation to Vouchers,
party sources to Accounting, and authoritative cost/allocation/posting to Accounting's
existing financial and proposed stock extension. Catalog keeps price definitions. Preview
does not reserve stock or authorize posting; legacy wire names need explicit compatibility work.

**V1.3 implemented slice:** [native company/SKU API and storage](catalog-v13-api.md).
Company levels/defaults, explicit unit prices, tiers, purchase references, estimates, product
MRP and supported formula/guard definitions are implemented. Wider customer/physical-source
selection and Billing consumer-release gates below remain future scope.

**2026-10-12 channel repair checkpoint:** Catalog's price-series API now accepts a reviewed
sales-channel code and resolution prefers an exact channel price before the generic series.
A generated non-null channel scope key in migration 0172 permits distinct channel series
without nullable-unique duplicates; active channel and company scope are checked. This is a
local source/API slice with focused tests and isolated MySQL 9.6 migration, parity,
multi-channel resolution and downgrade/re-upgrade evidence. Downstream
Vouchers/Accounting pricing activation, physical declarations and issue-time price guards
remain future owner work.

Referenced channel codes and active state are retained for historical price resolution;
Catalog refuses renaming or deactivating a channel used by a price series.

**Status:** Revised Catalog design, 2026-09-11; implementation pending.
**Scope:** Catalog price/configuration masters, policies, publication and read-only references.
Billing owns parties, physical lots/units/declarations, actual purchase/cost facts, allocations,
basket calculations, approvals and posting. No Billing source implementation is added here.
**Read with:** [Tables](catalog-table-inventory.md),
[schema](catalog-schema.md), [configuration](catalog-product-configuration.md),
[bulk/pricing](catalog-bulk-pricing.md), [promotions](catalog-promotions.md) and
[stock integration](catalog-inventory-integration.md).

## 1. Research baseline and design consequence

TallyPrime documents dated standard buying/selling rates and customer price levels; it also
distinguishes purchase expenses, actual/billed quantities and stock costing/reporting.
[Buying and selling prices](https://help.tallysolutions.com/selling-buying-prices/),
[additional purchase costs](https://help.tallysolutions.com/tally-prime/purchase-process/additional-cost-of-purchase/),
[stock query](https://help.tallysolutions.com/stock-query-tally/).

Use those business distinctions, while making source ownership, unit/currency/tax basis,
configuration dependencies and immutable history explicit. This is a design based on public
documentation, not inspection of TallyPrime source or a blanket claim of superiority.

There must not be a flat product row containing purchase_price, cost_price, mrp, sale_price_1,
sale_price_2, sale_price_3 with no unit/date/provenance. Use a small set of native price concepts,
typed scopes and history. Do not build an arbitrary money-field/EAV or executable formula engine.

## 2. Price and cost vocabulary

| Concept | Owner and authority | Meaning |
|---|---|---|
| Standard purchase rate | Catalog purchase price book | Expected future buying rate; not an actual purchase or valuation |
| Supplier quoted/gross rate | Catalog purchase price and purchase_price_term | Dated quote/reference amount before a declared unconditional trade discount |
| Supplier net reference rate | Catalog purchase price | Derived after the quoted trade discount on a declared tax basis; not the final invoice cost |
| Actual purchase price | Billing posted purchase evidence | What the transaction recorded, including original units, discounts, currency and tax treatment |
| Last purchase/last sale rate | Billing transaction history | Dated observation with supplier/customer/location provenance; no automatic Catalog overwrite or fallback |
| Standard/planning cost | Catalog item_reference_cost | Explicit estimate used for planning or an explicitly estimated pricing policy |
| Replacement estimate | Catalog item_reference_cost | Dated expected replenishment cost; not inventory carrying value |
| Service cost estimate | Catalog item_reference_cost | Optional estimated cost per service unit; never creates stock or a stock valuation |
| Actual landed/receipt cost | Billing receipt/cost evidence | Supported allocation of net purchase consideration, capitalizable charges and nonrecoverable tax |
| Inventory carrying/allocated cost | Billing valuation and selected issue allocations | Actual applicable FIFO/specific/weighted-average evidence; not necessarily the latest purchase rate |
| Product/pack MRP | Catalog item_mrp | Dated product declaration/default for the declared jurisdiction and pack |
| Physical stock MRP/declaration | Billing source, read-only Catalog projection | Declaration attached to actual stock/pack units; old stock is not relabelled by a new product default |
| Recommended retail/list price | Catalog price_plan with purpose REFERENCE_RETAIL | Optional commercial reference/MSRP; not a statutory maximum or automatic selling price |
| Regular selling prices | Catalog SALE price books | PRICE1/PRICE2/PRICE3 and further levels, units, audiences, channels and permitted stock scopes |
| Minimum selling price | Catalog commercial_guard_rule | Explicit fixed floor and/or cost-based restriction, enforced on the actual sale result by Billing |
| Maximum selling price | Catalog guard plus applicable physical declaration/jurisdiction rules | A business maximum and legal/declared restrictions have distinct provenance and override rules |
| Actual net realized sale price | Billing sale/credit allocations | Final consideration after benefits, with tax separated; not a Catalog master value |

A product can have many purchase/selling rates and many receipts into one manufacturer batch.
Therefore no scalar batch purchase_cost or average_cost is authoritative by itself. Billing
retains receipt layers and allocation evidence; a displayed batch average is labelled derived.

## 3. Native price dimensions and persistence

A rate is an amount in one currency, per an exact positive quantity of one pinned unit/pack
revision, with explicit tax basis, validity, source and purpose. Its scope is an SKU, verified
lot or verified stock-price declaration. It may additionally select an audience/channel.
Omitted scope means the documented default, never an arbitrary best price.

Current implementation and retained planning dimensions:

| Dimension | Current status |
|---|---|
| Product/SKU | Implemented price owner; each variant can have its own rates |
| Unit/pack | Implemented explicit rates or configured exact base derivation |
| Price level | Implemented; additional levels require company capability |
| Customer/customer type | Implemented level selection from verified projections; live Accounting handoff remains pending |
| Sales channel | Implemented exact-channel then generic selection |
| Quantity slab | Implemented tier selection using the original billed quantity |
| Effective dates | Implemented dated price history |
| Currency | Implemented separate books; no implicit FX conversion |
| Batch/lot | Planned verified stock-specific price scope; not implemented in the current API |
| Physical stock-price declaration | Planned declaration-specific scope; not implemented in the current API |

Bins and individual serials/IMEIs have no separate ordinary price master. Product/pack
MRP is a separate dated declaration; actual stock cost belongs to Accounting valuation.

| New Catalog table | Purpose and constraint |
|---|---|
| product_pricing_policy | Typed child of a Product Configuration revision: price requirements, source/derivation modes and referenced defaults; no second price-amount authority |
| item_price_scope | Stable SKU/LOT/STOCK_DECLARATION scope; exact item and matching local projection FKs; company/subject uniqueness and immutable subject identity |
| purchase_price_term | Typed optional purchase-price child recording gross quote and unconditional trade discount; published net price is deterministically validated, never independently editable |
| item_reference_cost | Dated STANDARD_ESTIMATE/REPLACEMENT_ESTIMATE/SERVICE_ESTIMATE per SKU/unit/currency/basis, source evidence and numeric revision; explicitly non-actual |
| item_price_formula | One typed recipe per derived item_price: allowed source, markup/margin/reduction and output basis; no recursion, SQL or user expression |
| commercial_guard_rule | Dated fixed floor/ceiling or minimum-margin/markup rule; typed commercial scope and optional SKU/lot/declaration price scope; explicit basis, severity and source requirements |
| inventory_lot_projection | Minimal Billing lot identity/item/manufacturer/date/status/source version; no stock quantity, cost or editable physical master |
| stock_price_declaration_projection | Minimal immutable Billing declaration/pack/lot linkage, MRP/currency/jurisdiction/tax basis and source version; no custody or valuation authority |

Existing tables are extended rather than cloned for every price kind:

- price_plan has purpose SALE, PURCHASE or REFERENCE_RETAIL. SALE requires its price level;
  PURCHASE and REFERENCE_RETAIL reject customer sale-level semantics. Published plan terms stay
  immutable. A reference retail price is never an automatic replacement for missing sale coverage.
- item_price_series references item_price_scope, unit revision, audience and optional channel
  context. SKU remains explicit for company ownership checks. Stable normalized scope
  keys prevent nullable-uniqueness races. Fixed native ranking replaces arbitrary price priority.
- item_price has a tagged fixed amount/volume tiers OR one typed formula, not conflicting
  simultaneous authorities. Zero has explicit free/zero-price semantics; null is not zero.
- purchase_price_term uses NONE/PERCENT/FIXED_PER_BASIS trade discount only, on the quote's
  compatible unit/currency/tax basis. Terms reconcile to the published net reference amount.
  Settlement discounts, retrospective rebates and supplier incentive settlement remain Billing
  purchase workflow extensions; they do not silently reduce a Catalog reference rate.
- item_mrp gains explicit jurisdiction, declaration/source evidence, unit/basis and numeric policy.
  It is not a second sell-price book. Physical declarations continue to belong to Billing.
- item_commercial_policy retains participation/free-sale policy; fixed minimum-price authority
  moves to commercial_guard_rule. Do not retain two independently writable min-price fields.
  discount_ceiling continues to own combined-discount percentage ceilings.
- item_price_numeric_revision validates entered Catalog rates/reference costs/fixed guards at
  their shared SKU/unit/currency precision. Billing cost allocation is not rounded to a user's
  selling-price entry precision. Physical declarations are validated by their authoritative source.

Protect purchase/reference-cost administration separately from selling-price read. No anonymous
catalogue endpoint can enumerate supplier costs or customer-specific prices.

## 4. Units and price derivation

Unit conversion does not automatically imply price conversion. Permit these explicit policies
per sale/purchase role:

- EXPLICIT_ONLY: require a price for the selected unit/pack. This is the safe default.
- EXACT_BASE_DERIVATION: exact compatible base-unit conversion is allowed if no applicable
  explicit unit rate exists; include the source price and unit revisions in the result.

For example, a piece may sell for 80 and a box of 12 for 900. The box price is valid and does not
become 960 merely because the quantity conversion is 12. Purchase can independently be quoted
per carton; a quantity entered in cartons may be billed by measured weight only through the
declared measured-unit contract. Nominal catch-weight ratios cannot determine actual charges.

Keep quantity unit, pricing unit, price-basis quantity, actual physical quantity and billed
quantity distinct. Per-100/per-1000 prices preserve amount/basis and use exact intermediate
arithmetic. Compound display does not create another underlying stock unit. Tier quantities
use compatible billed quantity for the original SKU line before lot splitting; paid versus
reward quantity is explicit. No cross-line/basket aggregation unless its separate contract exists.

Direct entered prices must satisfy the configured grid. Computed/formula prices have an explicit
rounding stage and result provenance. Minimum-derived rates round upward to the permitted step,
maximum-derived rates downward; this rate-grid rule does not override company monetary-total
or tax rounding. Exact final consideration still must pass the guard after
discount/tax allocation. A guard never silently rewrites an accepted price to fit its limits.

MRP conversion between packs is permitted only when the declaration/jurisdiction contract
allows it. A sealed-pack declaration cannot automatically become a lawful loose-unit price.

## 5. Product, batch and physical declaration behavior

Product-level defaults may be inherited by a lot, but each fact has a different authority:

| Scope | Catalog configuration/pricing | Billing facts |
|---|---|---|
| SKU | Product defaults, unit prices, sale levels, purchase references, floors and estimated costs | Actual receipts, costs and sold amounts |
| Lot/batch | Explicit lot selling/purchase-reference rates or narrower business guards against a verified lot reference | Manufacturer batch identity, expiry, actual receipt cost layers and stock |
| Stock price declaration | Optional declaration-specific sale rate/formula/guard against a verified reference | Actual printed/declaration MRP and the stock quantities/units to which it applies |
| Physical serial/unit | Identifier requirements only; ordinary rates inherit supported scopes | Actual unit identity, declared pack, custody and specific cost; exceptional transaction price needs Billing approval |

The same manufacturer batch may contain packs with different valid declarations. Do not invent
a new manufacturing batch or overwrite one lot-level MRP to distinguish them. Billing must
preserve a declaration/allocation subdivision or unit mapping so quantities cannot merge
across different declared prices. Catalog's projection does not establish available stock.

Stock-declaration scope also works for goods without batch tracking: the source identifies
the relevant physical pack/receipt allocation without inventing a manufacturer lot. A lot
reference is required only when that declared stock actually belongs to a tracked lot.

Product MRP history provides current/future defaults. For existing allocated stock, its pinned
physical declaration remains authoritative. A subsequent product declaration of 120 cannot
make a pack still labelled 100 eligible for 120. Relevant stricter business/jurisdiction caps
still apply; product defaults cannot relax a physical maximum. Corrections/relabeling require
the owner workflow, evidence and supported jurisdiction rules, not a Catalog price PATCH.

Example: same SKU/batch, declaration A has MRP 100 and B has MRP 120. At a regular MRP-less-10%
policy, the allocation prices are 90 and 108. A sale using both must retain distinct priced
allocations; a merged display is allowed only when exact allocation evidence remains available.
Never choose a customer-supplied cheaper batch ID without authorized, verified allocation.

If lot pricing is disabled, ordinary prices use SKU scope. Physical MRP, expiry and cost remain
enforced when applicable. If lot pricing is OPTIONAL, explicit absence may inherit SKU rates.
If REQUIRED, missing lot/declaration coverage is an error. Stale/unknown/denied references never
mean 'no override'. Disabling a used mode does not erase old rates/declarations or reinterpret stock.

## 6. Deterministic resolution and external computation

For SALE:

1. Validate company/actor/customer/source readiness, product configuration, date and units.
   Resolve the authorized customer price level, then exact currency book.
   REQUIRED lot/declaration mode removes ineligible SKU-only candidates before ranking.
2. Rank eligible candidates lexicographically: customer audience > channel > standard; within
   customer audience, exact channel > any channel; then declaration > lot > SKU; then exact
   requested pricing unit > permitted base derivation.
   Every dimension is explicit; equal-rank overlapping candidates fail publication/resolution.
3. In OPTIONAL mode a customer-specific SKU rate can beat a generic lot rate. It still must
   satisfy the actual allocation's MRP/floor restrictions. In REQUIRED mode only the required
   stock-specific candidates compete; a generic/customer SKU fallback cannot bypass the rule.
4. Apply the selected volume tier using the original compatible billed SKU-line quantity.
   Split allocations do not silently reset quantity slabs. Required lot-specific price coverage
   is validated for every allocation.
5. Resolve fixed rate or typed formula, retain source revisions and distinguish complete regular
   price from a definition awaiting allocation/cost/tax context.
6. Billing selects actual eligible allocations, evaluates any allocation-dependent source,
   computes benefits/tax with its sole basket evaluator and enforces all final guards. Changed
   allocation, price source, cost or declaration invalidates an affected accepted quote/approval.

For PURCHASE: use the configured purchase book/currency, supplier audience > standard, then
the same enabled stock/unit specificity. Supplier identity comes from Billing. Return
gross quote, unconditional discount and net reference with provenance. A purchasing actor can
record the actual invoice through Billing without silently changing future reference prices.

REFERENCE_RETAIL is queried explicitly for comparison/authoring. No last-purchase/last-sale
fallback and no implicit FX conversion. Missing currency or authoritative facts is explicit.

Catalog's /prices/resolve is a regular-definition/reference resolver, not an executable basket
quote or stock reservation. When runtime facts are necessary, return NEEDS_ALLOCATION,
NEEDS_COST or NEEDS_TAX_CONTEXT, required source contracts and no fabricated final amount.
Untrusted callers cannot submit cost/availability/MRP as authoritative overrides. Catalog can
resolve static or verified published-reference recipes; Billing evaluates actual-cost recipes
from local authoritative allocations without a synchronous Catalog call inside posting.

## 7. Formula pricing and commercial guards

Offer only these native recipes when configured:

| Recipe | Source and calculation |
|---|---|
| MRP_LESS_PERCENT | Applicable declared MRP and a bounded reduction; convert tax basis only with the required adapter context |
| REFERENCE_COST_PLUS_MARKUP | Explicit estimate multiplied by (1 + markup) |
| REFERENCE_COST_TARGET_MARGIN | Explicit estimate divided by (1 - target margin) |
| ALLOCATED_COST_PLUS_MARKUP | Actual selected Billing cost multiplied by (1 + markup) |
| ALLOCATED_COST_TARGET_MARGIN | Actual selected Billing cost divided by (1 - target margin) |

No price-to-price recursion or arbitrary formula strings. Store either an explicitly LIVE_SOURCE
recipe evaluated at the transaction's effective context or a reviewed SNAPSHOT publication as a
fixed price with source evidence. Changing an estimate does not alter a snapshot price. Live
source revisions are returned, acknowledged and pinned by the consumer; incomplete releases
cannot produce a final rate. Price-requiredness is satisfied by a valid executable definition,
not necessarily by a non-null scalar amount.

Markup and margin are different. With cost 80, markup 25% gives 100; margin 25% gives
106.666..., rounded at the declared output boundary. Margin must be below 100%; zero/negative
denominators, missing cost and nonrepresentable results fail. A standard estimate cannot satisfy
a guard explicitly requiring actual allocated cost.

Effective floor is the greatest applicable fixed/cost-derived floor; ceiling is the least
applicable business/declaration/jurisdiction maximum. Inherited mandatory restrictions cannot
be relaxed by a lot or SKU override. Fixed amount guards require SKU/stock scope and compatible
unit/currency; group/company rules may inherit dimensionless margin/markup/discount requirements.
An empty permitted range is a configuration/quote error, never silent clamping.

Check floors and margins on allocated net selling consideration excluding tax, after every
applicable scheme/coupon/manual benefit. MRP checks use the jurisdiction's required comparable
basis. Gifts use their explicit promotion/free-sale contract, not arbitrary zero-price entry;
ordinary paid-line guards cannot be bypassed by labelling a line 'gift'. A contractual regular
MRP reduction is a base-price recipe, not a second automatic promotion; display and stacking
must not accidentally award the same intended reduction twice.

Each business rule declares BLOCK or REQUIRE_APPROVAL, allowed actor roles and source
requirements through native policy. Approval workflow/consumption lives in Billing and binds
the exact quote/allocations/revisions; non-overridable jurisdiction restrictions stay blocking.
Cost-denied callers receive an authorized outcome without cost values, implied minimums or
margin percentages; privileged margin preview is rate-limited/audited and not a public oracle.

## 8. Actual-cost integration and source safety

Actual cost remains Billing evidence, including actual versus billed quantities, receipt layers,
supported landed charges, cost allocation, write-downs, reversals and late-cost corrections.
Catalog never imports, edits or caches a scalar actual_cost as pricing truth.

Illustration only, with the stated components approved by Billing's accounting policy:
100 billed units at 80 = 8,000; unconditional trade discount 800; allocated freight 400;
nonrecoverable tax 100; 110 units actually received including 10 free.
Total inventory cost = 7,700; derived receipt cost = 70 per physical unit. Recoverable tax,
if any, is separate. Expected purchase rate 80, net reference 72 and actual cost 70 differ.

FIFO may later issue older layers at a different cost; weighted average uses its costing scope;
a particular serial may have a specific cost. Repeated receipts into one batch do not collapse
these facts into a rewritten batch purchase price. Transfers carry cost; approved freight and
impairment create separate evidence. A low historical or standard cost never replaces a missing
actual-cost source. Cross-currency cost comparisons require Billing's authoritative transaction
FX snapshot and explicit conversion evidence, not a guessed rate or different-currency price book.
Service margins use declared estimates or a separately implemented actual
service-cost source, never fictitious inventory layers.

Returns/reprints use original price/declaration/unit/numeric/tax/benefit/cost evidence. They do
not reprice at today's price level, MRP, last purchase rate or altered configuration.

### Optional manufacturing estimate source

[BOM phase M2](catalog-manufacturing-design.md#6-cost-estimates-and-relationship-to-prices)
can publish a reviewed complete manufacturing estimate as a new STANDARD_ESTIMATE in
item_reference_cost. Preserve output/run-size/unit/currency/date and every component/route/source
revision. Setup costs can make the estimate quantity-dependent; the adopted basis must remain
visible. Missing material or protected cost makes the estimate incomplete, not zero.

Costing a stocked subassembly reference and its exploded inputs together is prohibited. Co-product
allocation must reconcile to total estimated cost. A refresh creates a new estimate and requires
explicit reference-cost adoption; no automatic selling-price, MRP or actual-cost replacement.
Billing's manufactured receipt/layer/WIP/variance valuation remains its independent actual-cost source.

## 9. Configuration controls and presets

`product_pricing_policy` is a typed Product Configuration child. Current defaults
come from the company configuration; existing products retain their adoption pins,
including historical resolution where applicable. Native type, unit and capability
constraints still apply. Enabling an option permits its use without making every
price field mandatory. Field read authority remains field policy.

The wider design families below include future stock/declaration and transaction
work. The implemented controls and new-company defaults are listed in
[Product Configuration](catalog-product-configuration.md#automatic-starter-and-pricing-options--2026-11-04).

| Control family | Choices and validation |
|---|---|
| Purchase references | Disabled/optional/required when purchasable; supplier-specific rates optional; no supplier master creation |
| Sale levels | Baseline PRICE1 or enabled multiple levels; required coverage declared per supported currency/unit/audience |
| Unit pricing | Explicit prices or permitted exact base derivation; independent sale/purchase modes |
| Stock-specific pricing | Disabled/optional/required lot/declaration coverage; requires verified source and runtime allocation support |
| Product MRP | Not applicable/optional/required; jurisdiction/pack/basis required when applicable |
| Physical declaration | Source requirement and stock identification contract; disabling lot-price overrides never disables declaration checks |
| Reference cost | Disabled/optional/required for chosen formula; estimate kind, unit/currency and freshness/validity |
| Price method | Fixed/volume tier or supported typed recipe; source dependencies and output rounding explicit |
| Floors/ceilings/margin | Optional business guards plus mandatory inherited restrictions; explicit cost basis and blocking/approval behavior |
| Quantity/rate precision | Existing 0-4 entry scales, exact increments, basis quantity and unit rules |
| Manual override/free sale | Explicit authority and transaction approval contract; non-overridable caps retained |
| Publication/change mode | Future defaults, reviewed existing-SKU adoption, fixed snapshot or live-source revision; no historical rewrite |

Example presets are combinations of these same controls, not separate engines:
service/hour (no stock/MRP); simple retail goods (PRICE1 and optional product MRP); wholesale
(multiple levels, case prices and supplier references); batch-controlled retail (physical MRP,
expiry and optional lot prices); serial-controlled equipment (device profile and actual cost
when available); measured bulk goods (kg/litre pricing and exact actual measures).

Do not allow an enabled actual-cost recipe without Billing support, a service batch policy,
a REQUIRED physical declaration without stock identity, or required sale coverage when selling
is disabled. Draft/activation validate definition coverage; quote/post validate allocated facts.
Old documents retain original configuration. Disabling features never clears their values.

## 10. APIs, imports and phase integration

Catalog adds scoped price-scope/reference-cost/guard/recipe administration and role-aware
configuration metadata. Existing prices/imports publish these native structures. Price matrix
reads expose only authorized purposes/levels/units and distinguish reference versus actual
facts. There is no Catalog actual-cost, batch creation, purchase posting or invoice endpoint.

Import templates include Products, Units/Packs, Purchase References/Terms, Sale Prices/Tiers,
MRP, Reference Costs and Guards. Lot/declaration overrides must resolve exact existing external
IDs or scoped verified aliases. No creating a physical lot from a price worksheet. Formula
changes, percentage updates and copied prices have frozen inputs/versions and previewed
rounding/guard effects. Publication may be pending consumer acknowledgement. No automatic
propagation of a new product MRP into old stock or copying of last actual cost into a master.

| Phase | Addition |
|---|---|
| C0/C1 | Price vocabulary, ownership, exact comparisons/rounding and deterministic scope order |
| C5 | Minimal lot/declaration projections and readiness; no actual-cost source ownership |
| C6/C7 | Typed pricing configuration, verified scopes and conditional activation rules |
| C8 | Purchase terms, reference costs/list prices, unit/lot/declaration rates, formulas and guards |
| C9 | Comparable tax/MRP basis and explicit missing transaction-tax context |
| C10 | Reviewed multi-sheet prices/terms/cost estimates/MRP/guards imports |
| P0/P1/P5 | Base-price recipe versus benefit distinction and correct definition publication |
| C15 | Source/precision/permission/override/history and actual-consumer integration matrix |

Mandatory examples: independent piece/box prices; per-1000 micro rates; goods/service presets;
supplier gross/net versus actual landed cost; 100 billed/110 received; same batch with two
declarations; mixed-declaration sale allocations; audience versus stock scope precedence;
quantity slabs preserved after splitting; missing actual cost; margin versus markup;
post-discount floor violation; floor above MRP; stale source; unauthorized cheaper lot;
disabled configuration; historical return; and current-authority bulk retry.

## Decision log

2026-11-04: Catalog 0221 extends price scope to a verified Accounting batch.
Resolution requires `lot_id` for products that selected batch pricing and never
falls back to a different lot. Accounting 0235 owns the immutable initial physical
MRP; its declared unit/currency and tax basis are retained. Warehouse pricing remains
excluded. See the batch-entry delivery record above.

- 2026-11-04: Product Configuration controls existing levels, units, tiers,
  channels, currencies and formulas. New-company starters disable all six extra
  options; existing revisions inherit their previous permitted behavior.

- 2026-11-04: Removed warehouse/godown/store-specific regular pricing from the plan,
  including series context, configuration and selection precedence. Retained sales
  channels, stock-location controls and warehouse valuation as separate concerns.

- 2026-10-30: Removed the product creation "Tax and price source / reason" note
  from native price drafts, published prices and tax assignments, including bulk
  adjustment input. Columns are dropped by Catalog 0211-0213. Price source IDs,
  versions, dates and audit evidence remain automatic; reference-cost, MRP and
  guard evidence and official statutory documents retain their separate contracts.

- 2026-10-12: Repaired the previously inert sales-channel price field with exact-then-generic
  selection and normalized uniqueness. Retained the generic default for old series; deferred
  FMCG posting and stock-price declaration activation to the existing owner gates.

- 2026-10-10: Adopted the Vouchers/Accounting owner mapping for earlier Billing dependencies.
  Catalog definitions stay local; party and authoritative cost facts come from Accounting.

- 2026-09-11: Added optional BOM-estimate provenance and reviewed standard-reference adoption;
  retained sole Billing authority over actual manufactured cost and posting.

- 2026-09-11: Separated purchase references, quoted discounts, MRP/MSRP, regular selling prices,
  estimates and actual cost. Added typed unit/lot/declaration scopes, recipes and commercial guards.
- 2026-09-11: Preserved Catalog-only implementation: physical declarations, receipt/allocated
  cost, stock selection, actual purchase/sale values and approval/posting remain Billing-owned.

Decision 2026-09-12: V1.3 implements the native company/SKU subset using 17 tables (0083-0099); see its API decision log for bootstrap, exact basis, live references and unavailable external-source boundaries. No actual-cost or allocation producer is implied.

Decision 2026-09-13 (price-level lifecycle): retirement is rejected when any price plan or
company default/fallback policy references the level, including historical policies. Retirement
has no effective date, so allowing it would break historical resolution. Unreferenced levels
may retire; referenced levels may still be renamed. The baseline level remains non-retirable.
