# Sales, Purchase and voucher commercial configuration

**Date:** 2026-10-10. **Status:** Required design; shared Vouchers configuration and invoice
capture/preview foundations exist, while the operational scheme engine and full Sales/Purchase
execution remain incomplete. **Scope:** Controlled taxes, discounts, charges, free quantities and
deals for company voucher types. Payroll remains excluded.

**Discount implementation checkpoint, 2026-10-11:** The common invoice policy now narrows
manual discount input kinds and net/gross bases, caps the number of discount components,
controls direct and indirect discount-on-discount dependencies, and limits the final
allocated commercial discount by invoice amount and by each line's pre-component net
base percentage. The company/type/class intersection is restrictive. Vouchers enforces
recipe choices at capture; Accounting repeats those checks and enforces monetary limits after its sole
calculator runs. Default serialization omits the new controls to preserve historical
policy hashes. This is an incremental B15 slice, not Catalog ceiling integration or
automatic scheme activation. Free/deal preview, goods posting and discounted source-linked
notes remain gated by their existing B16/B17/B24/B25 dependencies. The current console form
does not yet author invoice components.
**Read with:** [Invoice calculations](voucher-invoice-calculation.md),
[voucher types](voucher-extensibility.md), [product configuration](catalog-product-configuration.md),
[pricing](catalog-pricing-design.md), [promotions](catalog-promotions.md) and
[India tax recording](voucher-tax-recording.md).

This commercial family uses the [all-voucher configuration contract](voucher-configuration-design.md). Its shared registry,
policy storage, effective-settings API and stage enforcement also cover accounts/banking,
inventory, orders, scenarios and job work; do not implement a parallel resolver.

## 1. TallyPrime configuration findings

Reviewed official TallyHelp, not a running installation. Menu visibility varies by enabled
features, tax jurisdiction and release. The table distinguishes documented entry controls
from the stronger native policy/enforcement contract proposed for this platform.

| Requirement | TallyPrime configuration or behavior | Primary source |
|---|---|---|
| Item discount | Invoice F12 enables cash/trade-discount entry; an item discount can retain the entered rate while reducing its amount | [Discounts and free items](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/) |
| Bill discount | A discount ledger applies a percentage or amount to the invoice's item total | [Discounts and free items](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/) |
| Including charges in a discount basis | Invoice F12 has a current-subtotal calculation option | [Discounts and free items](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/) |
| Extra charges | Additional ledgers record freight, packing and similar amounts; optional cost-centre allocations provide analysis | [Sales charges](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/) |
| Same-item free quantity | Company F11 enables separate actual/billed quantities; movement uses actual quantity and the amount uses billed quantity | [Free quantities](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/) |
| Separate free item | The Sales voucher type permits zero-valued entries; a reward item can carry quantity without a selling amount | [Zero-valued entries](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/) |
| Customer prices and quantity slabs | Company multiple-price-level support, customer price-level selection and dated price lists supply quantity-range rates/discounts | [Buying and selling prices](https://help.tallysolutions.com/selling-buying-prices/) |
| Reusable invoice defaults | Voucher classes restrict party groups and supply account allocations, additional charge/tax entries and rounding defaults | [Voucher classes](https://help.tallysolutions.com/accounting-entry-tally/) |
| Inclusive tax and slab calculation | Stock/ledger tax settings, invoice controls and classes support inclusive entry and applicable item-price/MRP slabs | [Sales tax configuration](https://help.tallysolutions.com/sales-with-cess-tally/) |
| Multiple tax components | GST classifications preserve applicable component rates and cess value/quantity inputs | [GST classifications](https://help.tallysolutions.com/india-gst-create-use-and-update-gst-classifications-tally/) |
| Purchase terms and free receipts | Purchase entry supports supplier discounts, additional ledgers and actual/billed differences; eligible purchase costs can be allocated by quantity or value | [Purchase entry](https://help.tallysolutions.com/tally-prime/purchase-process/purchase-goods-and-services-tally/), [purchase costing](https://help.tallysolutions.com/additional-cost-of-purchase/) |

These sources establish how to record free goods and quantity pricing. They do not establish
that every arbitrary combination of automatic 10+1 selection, cross-item offers, coupons,
quota reservation and return recovery is native TallyPrime behavior. Our automatic schemes
use the existing Catalog promotion design and its required runtime; no TDL/add-on capability
is assumed. Configurable ledger order is also not a substitute for dated statutory rules.

## 2. Configuration ownership and effective permission

Each company needs separately editable **Sales** and **Purchase** commercial policies, with
type/class refinements for such documents as Retail Sales, Wholesale Sales, Service Sales,
Purchase Invoice and source-linked Credit/Debit Notes. These are native Vouchers policies.
They reference the existing Identity capabilities and Catalog pricing/product/promotion
revisions, rather than copying those authorities or creating a feature flag for every field.

Existing Catalog [pricing schemas](../apis/catalog/src/catalog/schemas/pricing.py) include
native discount-ceiling and `free_sale_allowed` controls, while its
[promotion schemas](../apis/catalog/src/catalog/schemas/promotions.py) explicitly describe
definition validation without basket/coupon execution. Reuse those inputs and the
[company capability contract](company-features.md); a newly added voucher policy is not proof
that an automatic offer, tax recipe or stock effect has been implemented.

| Layer | Responsibility and constraint |
|---|---|
| Implemented kind/profile and tax adapter | Define executable recipes, supported tax cases and stock/account effects; configuration cannot add code |
| Identity company capability | Gate inventory, price levels and implemented promotion/coupon capabilities; retain existing first-use rules |
| Company Sales/Purchase policy | Select allowed modes/components, limits, defaults, reasons and override/approval rules independently by direction |
| Voucher type revision | Narrow its base kind/profile and company policy, bind required/optional/forbidden sections and allowed commercial mechanics |
| Voucher class revision | Supply compatible account, charge, discount and rounding defaults; cannot widen type permissions or legal scope |
| Catalog product/pricing/promotion revisions | Supply prices, units, participation, free-sale eligibility, tax classification, floors, ceilings and native deal definitions |
| Transaction context and actor | Validate customer/supplier, registration/date, currency, location, channel, actual quantities/stock, access and required approval |
| User form/print preference | Control presentation only; hiding a field neither removes a required effect nor grants permission to enter it |

Effective capability is the intersection of implemented support and all applicable enabled
policies, product restrictions, context and actor authority. A deny wins. Tax obligations,
stock tracking, hard floors/ceilings and field denies cannot be relaxed by a lower layer.
Resolve defaults by explicit company -> type -> class precedence only within permitted values;
a document override needs the native override permission. Product tax/price sources retain
their own resolver; class defaults cannot override a SKU's statutory facts. Reject conflicting
requirements and empty allowed sets when publishing, instead of silently selecting a winner.

Separate **availability**, **default value**, **requiredness**, **edit permission** and
**approval threshold**. A rule marked mandatory cannot simply be removed from the form.
Do not make a blanket `allow_discount` or `allow_free` the authority for every mechanic.

## 3. Required commercial controls

Names below describe typed policy responsibilities; final fields/normalization are D06/D07
work. New optional mechanics start unavailable until configured and verified. Templates may
offer defaults, but adopting a template must show the resulting enabled behavior.

| Control family | Required configurable details |
|---|---|
| Entry and quantity | Account/item/mixed modes; actual/billed separation; allowed difference reasons; permitted units and measurement sources; no stock mode for services |
| Regular price | Allowed price levels/books and source policies; tax-inclusive/exclusive entry; permitted rate overrides with reason/approval; preserve original quantity-tier basis |
| Discounts | Enable line, selected-line and bill scopes separately; fixed/percentage/per-unit inputs; repeated stages, approved bases and charge inclusion; eligible/excluded items; aggregate ceilings and override authority |
| Charges | Allowed shared charge definitions/accounts; fixed/percentage/per-quantity bases; target scopes, required/default components, limits and editability; commercial/tax/cost treatment references |
| Tax | Allowed jurisdiction/profile and registration context; supported components/slabs/inclusive entry; rate/base overrides only where legally permitted with evidence; a tax-display preference cannot disable tax |
| Free quantity with paid goods | Whether a declared manual bonus quantity or supported automatic scheme is allowed; reason, source, maximum quantity/value and approval; actual-versus-billed difference alone is insufficient evidence |
| Independent free item/sample | Separate authorization for an uncharged item, sample or gift; native purpose and tax/accounting treatment; reject accidental blank rates or arbitrary zero-price bypass |
| Deals | Enabled same-item/cross-item mechanics, published rule references, buy/reward pools, thresholds, repeat caps, dates, price levels, locations/channels and customer eligibility |
| Combining benefits | Versioned compatible combinations, stages/priority, exclusivity and manual-discount interaction; reward units cannot qualify themselves for more rewards |
| Coupons and campaigns | Enable only when separately delivered; valid program/rule scope, holds/limits and suspension; not a prerequisite for ordinary manual discounts or manually evidenced bonus quantities |
| Returns | Original paid/reward/component allocation, refund and gift-return rules, nonreturnable charges, source caps and approved recovery terms; do not inherit today's deal as a new award |
| Rounding and output | Existing numeric/statutory rounding policies, bill-rounding bounds, display of paid/free/actual quantity and benefit breakdown; printing must reproduce stored facts |

Tax treatment is resolved, not an arbitrary user checkbox. For example, whether freight is
part of a supply's assessable value is governed by the supported tax profile. A company may
restrict which valid profiles users can select, but cannot waive a mandatory tax by disabling
tax entry. Likewise, disabling new discounts must not prevent an authorized source-linked
return from reversing an old discount. Such correction authority is a separate policy.

Sales and Purchase must remain distinct: supplier-declared free quantities and trade terms
can be recorded with provenance under Purchase controls. They do not consume a sales campaign
or justify enabling a procurement rebate/automatic supplier scheme engine. The latter remains
outside the existing sales-promotion runtime scope until separately designed and implemented.

## 4. Free quantities and 10+1 deals

### 4.1 Manual recording versus automatic entitlement

A same-item **10+1** deal means 10 paid units plus 1 reward unit: actual quantity 11, billed
quantity 10. At 100 per paid unit, the entered commercial amount is 1,000 before other
components. Stock dispatch is 11 and its cost covers all 11. The bonus must not additionally
deduct 100 from that already-normalized 1,000 amount. Preserve any regular-price benefit
comparison separately from posting amounts; do not recognize a second promotion expense.

Manual entry records an authorized supplier/customer term and explicit paid/reward quantities;
it claims no automatic entitlement or campaign redemption. The absence of an automatic scheme
engine must not require users to fabricate a promotion ID to record supported manual terms.
An automatic award instead requires a published rule, the single evaluator, current eligibility
and atomic entitlement/stock/financial enforcement. Users cannot label an ordinary sale as a
manual gift to evade a restricted automatic scheme or commercial limit.

For an uncapped same-item 10+1 recipe on **paid** qualifying quantity, rewards are
`floor(paid_quantity / 10) * 1`: 9 -> 0, 10 -> 1, 19 -> 1, 20 -> 2. Caps and compatible units
apply before acceptance. Quantity 10 must be labelled as paid or actual input; never infer
which the user intended. The recipe above is not applied to total quantity including rewards.
No fractions of a serial unit, recursive rewards, implicit substitutes or double awards after
splitting a line across lots/warehouses are allowed. Remainders do not carry across invoices
unless a separate cumulative-scheme contract is implemented; that runtime is not in this scope.

### 4.2 Same-item and different-item storage

Use common ITEM lines/details and inventory allocations. Persist native quantity role,
benefit source/manual reason, qualifying and reward line/unit links, policy/rule revisions
and exact benefit allocations. The same SKU may be displayed as one actual/billed row or as
paid/reward rows, but normalize to one canonical set of disjoint units. A different reward
SKU requires its own ITEM line and valid stock/tracking allocations. A derived free-quantity
summary is not a second editable quantity or another stock movement.

Zero commercial consideration is not zero inventory cost or automatically zero taxable value.
Samples/gifts and a multi-item supply for one consideration need separate native tax purposes.
[CBIC Circular 92/11/2019](https://cbic-gst.gov.in/pdf/circular-cgst-92.pdf) distinguishes these
cases; use it as classification evidence and validate the effective law/notifications at tax
profile release. Do not hard-code universal gift ITC, exemption or mixed-supply treatment from
an invoice label. Cross-item rewards require supported supply/consideration allocation first.

If a later bill discount applies to a deal, use the approved eligible base and stacking policy;
do not discount a reward's zero commercial amount again. Native price-floor/MRP/aggregate
benefit checks still inspect the combined result, including benefits attributed to free units.

### 4.3 Fulfillment, returns and reporting

Freeze deal groups before physical lot splitting. For order/challan/partial-invoice workflows,
retain source-scoped paid and reward entitlements and consumed quantities across conversions;
do not recalculate 10+1 on each child or award the same reward twice. Pin the supported award
scope (invoice or linked order) and trigger (billing or fulfillment); require qualifying paid
units at that trigger before releasing rewards. Manual bonus quantity may be evidenced first,
but actual stock execution still validates availability. A missing reward requires explicit
re-quote/approval or a tracked deferred reward only when that workflow is supported.

Returns use original disjoint paid/reward and component allocations. Under the existing default,
refund original net-paid allocation without silently repricing retained goods or charging the
reward's list price. A returned reward reverses its actual stock/cost and supported original tax
allocation, but does not automatically refund a list price never charged. Keep outstanding reward
evidence; a different disclosed gift-recovery policy needs its own supported rules/approval.
Free commercial presentation does not erase statutory consideration allocation where required.

Reports retain paid, reward and actual quantity; regular-price comparison, applied monetary
discounts, charges, tax and net consideration; all-unit COGS; manual versus scheme source and
returned/outstanding rewards. Do not sum the informational reward value with applied monetary
discounts twice. Scheme redemption counters and promotional expense are not interchangeable.

## 5. Revision lifecycle, APIs and shared storage

Vouchers owns native versioned company Sales/Purchase policies and type/class bindings;
Identity owns capabilities/access, Catalog owns master definitions, and Accounting owns
accepted posting/redemption/quantity/value effects. Reuse `voucher_type_revision`,
`voucher_type_section`, `voucher_class` and common component/item/source-allocation structures.
D07 must finalize shared company-policy storage and any typed benefit-membership relations
before migrations, outside the unchanged 51 numbered candidate baseline where needed. Never
create one configuration or invoice table per voucher kind, scheme or company-defined type.

Provide scoped draft/read/validate/publish/history operations, expected-version edits, impact
preview and an effective-policy response with source revisions and allowed/required/editable
controls. Reuse the common voucher preview/command contract and metadata-driven forms. Reject
forbidden fields/mechanics in API/import/automation as well as the UI. An unsupported declared
mechanic produces a reason, not a silently stripped charge, ignored tax or newly enabled gift.

Publish immutable revisions with audit and consumer-readiness acknowledgment. Documents and
quotes pin policy, Catalog source generations, rule/engine revisions and approval digests.
Changes that affect a draft require revalidation/re-approval; historical posting/reprint/return
keeps original calculation evidence. Live access, statutory readiness and stop/suspension
checks still apply at commit. Publication, posting and disabling/suspension races need owner
fences; stale projections must not authorize a newly forbidden free issue. This is future
execution work, not proof supplied by the existing Catalog configuration endpoints.

## 6. Delivery and verification

Keep the existing 45 parents. B02 resolves D01/D04/D06/D07 contracts; B05/B06 implement native
policies/type/class binding and B08 exposes effective controls. B15/B16 implement calculation,
tax and deal preview; B17 covers accounts/service restrictions; B24/B25 implement actual free
goods, deal consumption and source-linked returns; B18/B27/B45 reconcile and verify them.
Order-scoped entitlement is B29/B30 integration, not an implicit invoice-only feature.

Automatic same-item 10+1 is required supported-scheme work in the applicable B15/B24 slices,
with Catalog publication/projection and Accounting runtime prerequisites explicitly evidenced.
Cross-item mechanics activate only with their verified tax/stock/allocation slice. Campaigns,
coupons, gift choices and limits retain the existing separate promotion delivery gates; do not
claim those ready from a manual 10+1 invoice or a definition validator. Ordinary invoices may
release with these mechanics unavailable and must expose that supported-profile limitation.

[CAL17-CAL28](voucher-invoice-calculation.md#81-required-component-acceptance-matrix) cover
configuration inheritance/denial, manual/automatic deals, quantity conservation, stacking,
tax distinctions, policy races, returns, partial fulfillment and reporting. D06 still owns
business-specific thresholds/overrides; D05/D09 owns legal scope. No thresholds, costing
method or company capability were activated by this review.

## Decision log

- 2026-10-10: User requested Tally-informed Sales/Purchase/voucher controls for item/bill
  taxes, discounts, charges, free goods and 10+1 deals. Recorded sourced settings, independent
  native policies, restrictive effective controls, manual versus automatic awards, shared
  paid/reward storage, statutory classification and immutable return/fulfillment evidence.
  Extended existing batches and CAL coverage; no application code or live settings changed.

### All-voucher configuration review - 2026-10-10

Integrated the commercial family into the all-kind framework and shared native policy
storage. Existing CAL01-CAL28 and manual/automatic deal distinctions remain authoritative.

### Sales implementation planning - 2026-10-11

The [Sales configuration implementation plan](voucher-sales-configuration-plan.md) maps
TallyPrime type, class, entry and statutory controls to the implemented shared foundation and
remaining B15-B45 execution gates. The status line above now distinguishes implemented
configuration/capture foundations from the incomplete commercial and scheme runtime.

### Manual-discount control implementation - 2026-10-11

Added restrictive typed recipe, compounding and final allocation limits to the shared
invoice policy, with producer and Accounting owner enforcement. Kept automatic schemes
unavailable: stored Catalog promotion facts and a same-item evaluator are not a published,
acknowledged release or an executable free-goods posting path. Future Catalog ceilings must
be checked against the combined manual and promotional benefit; the local policy ceiling
does not stand in for that Catalog authority.

### Two-pass invoice execution review - 2026-10-11

Pass 1 found that a manually captured free/scheme line could leave draft even though
Accounting refuses every free-purpose invoice preview. Submission now rejects those
lines until the Catalog, tax, stock and Accounting execution path is published; draft
capture remains available for planning. Pass 2 found that an ordinary invoice could
leave draft without any calculation acceptance. The shared stage validator now requires
an accepted calculation hash for submission and later transitions. Accounting still
recalculates and matches that hash before posting; hash presence alone is not proof of
the owner's current preview, because draft input and the acceptance command can carry
a caller-provided hash. This is a remaining approval-provenance gate for a subsequent
execution slice.
