# Sales and Purchase: entry modes, calculation and posting

**Date:** 2026-10-10. **Status:** Requested plan refinement; detailed implementation remains V0/V3/V4 work.
**Scope:** Sales/Purchase with inventory, accounts-only entry and supported mixed goods/services;
charges, discounts, tax, payment modes, advances and outstanding balances, including stacked
quantity/line/invoice components on purchases and purchase returns. Payroll stays excluded.
**Read with:** [Vouchers plan](vouchers-plan.md), [shared data model](voucher-data-model.md),
[settlement review](tally-settlement-functional-review.md), [India tax plan](voucher-tax-recording.md),
[Catalog pricing](catalog-pricing-design.md) and [promotion contract](catalog-promotions.md).
**Configuration:** [Sales/Purchase commercial controls](voucher-commercial-configuration.md)
govern which modes, component scopes, free quantities and deal mechanics each type can use.

Implemented ordinary-invoice preview guard (2026-10-31): proposed advance allocations plus tender
instructions cannot exceed the exact calculated payable. Equality is permitted.
This validation does not reduce commercial/tax totals or claim settlements executed;
Accounting still validates actual balances and effects when posting.
Financial notes keep their existing original-invoice entitlement and settlement
validation at preparation; this guard does not change that contract.

The request is interpreted as supporting both inventory-linked invoices and accounting-only
invoices. Item display, physical execution, ledger posting and payment are separate decisions.
This document strengthens the existing common model; it does not create Sales/Purchase tables.

## 1. TallyPrime functional baseline

| Capability | Documented behavior | Official source |
|---|---|---|
| Entry modes | Item Invoice for item/quantity/rate entry; Accounting Invoice for ledger amounts; As Voucher exposes debit/credit entry | [Sales modes](https://help.tallysolutions.com/sales-of-goods-services/), [Purchase entry](https://help.tallysolutions.com/tally-prime/purchase-process/purchase-goods-and-services-tally/) |
| Account allocation | Common sales/purchase account or item-specific accounts; cash/bank or party ledger depending on settlement | [Sales modes](https://help.tallysolutions.com/sales-of-goods-services/) |
| Discounts and charges | Item/document discounts, additional ledgers and configurable calculation bases; purchase discount can be shown separately or netted into item value | [Sales charges/discounts](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/), [Purchase discounts](https://help.tallysolutions.com/tally-prime/purchase-process/purchase-goods-and-services-tally/) |
| Actual/billed quantities | Free quantities can differ from quantities charged to the party | [Sales quantities](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/) |
| Tax-inclusive entry | Inclusive rates and supported tax/slab configurations expose the derived tax breakdown | [Inclusive rates and tax analysis](https://help.tallysolutions.com/sales-with-cess-tally/) |
| Charge tax treatment | Expense ledgers can be taxable themselves or contribute to another supply's assessable value; composite-supply handling is explicit | [Expense tax setup](https://help.tallysolutions.com/set-up-expense-ledgers-for-gst/), [composite supply](https://help.tallysolutions.com/composite-supply-gst/) |
| Purchase costing | Additional purchase cost can be allocated by quantity or value | [Additional purchase cost](https://help.tallysolutions.com/additional-cost-of-purchase/) |
| Multiple tax bases | GST classifications include cess valuation and per-unit rate inputs; applicability still depends on the dated legal profile | [GST classification](https://help.tallysolutions.com/india-gst-create-use-and-update-gst-classifications-tally/) |
| Purchase returns | Debit Note entry supports purchase returns and adjustments; the purchaser's accounting document must be distinguished from the supplier's statutory tax document | [Purchase returns](https://help.tallysolutions.com/purchase-returns-tally/) |
| Split settlement | POS supports multiple payment modes; this is a POS capability, not proof of identical fields in every invoice mode | [POS payments](https://help.tallysolutions.com/point-of-sale-tally/) |
| Rounding | Invoice or ledger rounding has a configured method/limit and a visible difference | [Rounding](https://help.tallysolutions.com/round-off-invoice-and-ledger-values/) |
| Billing versus movement | Orders, delivery tracking and invoicing can be linked; billing before delivery is distinguishable from physical dispatch | [Order/delivery/invoice tracking](https://help.tallysolutions.com/sales-order-tally/) |

Reviewed official documentation, not a running Tally installation. Configuration and release
differences exist, including purchase discount entry formats. We adopt the required business
capabilities below without claiming that Tally exposes our exact schema, controls or UI.

## 2. Entry and effect matrix for this platform

| Mode/profile | Commercial entry | Physical quantity | Accounting and settlement |
|---|---|---|---|
| Accounts-only invoice | Native account/service amounts and tax classification; no dummy SKU | None | Revenue/expense/asset, tax and party/cash effects as applicable |
| Item invoice: direct execution | Goods item, billed quantity, price and stock allocations | Execute supported dispatch/receipt once | Invoice effects plus required stock-value/COGS/clearing effects under the recognition policy |
| Item invoice: movement already recorded | Item lines with exact Delivery/Receipt Note or challan allocations | Reference existing movement; no second issue/receipt | Billing and valuation/clearing reconciliation; payment handled independently |
| Item invoice: movement deferred | Billed goods with an explicit supported pending-fulfillment profile | No current movement; later execution links the invoice | Recognize only permitted financial/tax effects; do not fabricate stock or completion |
| Mixed goods/services | Item and/or account lines permitted by the implemented mixed profile | Only eligible goods execute/reference movements | Each line retains its own commercial/tax classification and account distribution |
| As Voucher presentation | Explicit account allocations with supported item detail | Same execution rules as the selected business profile | Must reproduce the same validated invoice calculation and balanced posting |

Use native inventory intent such as NONE, EXECUTE, REFERENCE_EXISTING or DEFERRED, bound to
line/quantity allocations and supported profile rules. These are proposed contract names.
No unrestricted `affects_stock=false` switch on an ordinary goods line. Partial execution or
reference requires explicit non-overlapping quantity slices and remaining-quantity guards.
An accounts-only entry still needs HSN/SAC, supply facts and other statutory details where
applicable; if its document profile requires item/quantity evidence, that profile must expose it.
Fixed assets/service expenses do not become saleable inventory merely because they are purchased.

Pure movement remains the Receipt/Delivery/Material/Stock workflows. All **posted** Sales and
Purchase profiles have their appropriate financial effects; draft/optional status is not a
way to record a real taxable supply without the required document and statutory workflow.

## 3. Common sections and input ownership

| Section | Native input/evidence | Calculation responsibility |
|---|---|---|
| Header/parties | Company, registrations, customer/supplier, bill-to/ship-to, currency, document/posting/tax dates, terms and references | Pin relevant master/rule versions; supplier invoice number/date distinct from internal voucher number |
| Item/account line | SKU or account, goods/service nature, quantity/unit or amount, price source/basis, inclusive/exclusive basis, account distribution | Resolve commercial amount; retain tax classification even without stock |
| Physical allocation | Actual quantity, location, owner, batch/serial, execute/reference/deferred intent, movement source | Reconcile physical and billed quantities without forcing equality for free/measured quantities |
| Discount components | Trade/promotion/manual/settlement purpose, fixed/percentage, target lines, eligible basis, stage and approval | Apply once, preserve each benefit and allocated amounts |
| Charges | Freight, packing, insurance, handling or other supported purpose; amount/rate, basis, account, supplier/source and treatments | Separate invoice-payable, taxable-value and inventory-cost effects |
| Tax context/components | Rate/classification source, taxable base, component, exemption/RCM/credit treatment, declared versus calculated values | Jurisdiction adapter determines lawful base, rates, tax point and component amounts |
| Rounding/adjustment | Typed purpose, method, increment, account, tolerance and reason | Explicit difference; cannot force balance by changing a tax value arbitrarily |
| Advances/credits | Existing source open items, requested amounts and financial/tax adjustment links | Check eligible available balance; no new money created |
| Tenders | Mode, amount/currency, cash/bank/clearing account, instrument/provider reference, date and recognized state | Separate requested, accepted/recognized and cleared amounts |
| Outstanding/installments | Due dates and proposed remaining bill references | Derive remaining debt from recognized effects; retain invoice gross independently |

Retain supplier-declared quantities, rates, discounts, tax and total alongside calculated
values when they differ. Explain tolerances and require an authorized supported resolution;
never overwrite source evidence to make a supplier invoice agree with our result. Duplicate
supplier-invoice checks use an explicit scoped identity rule, not the internal voucher number.
Price overrides require provenance and permission. Hidden purchase costs stay protected in
previews and explanations under the existing Catalog/Accounting field policies.

## 4. Discounts and charges: one calculation authority

Represent each applied discount as a shared CHARGE/ADJUSTMENT line with typed
`voucher_charge_detail` and target `voucher_charge_allocation` rows. The same structure
supports a single-item discount and an invoice discount across eligible lines. Item-level
discount input in the UI is normalized into that representation; an item detail's discount
summary is derived, not a second editable amount. Promotion award/approval evidence links
to the component; existing promotion evaluation remains the single benefit engine.

A component retains purpose, effect (ADD/DEDUCT), input kind, rate or fixed amount, currency,
NET_EXCL_TAX/GROSS_INCL_TAX basis, stage, eligible source/target IDs, policy version, accepted
result and rounding evidence. If percentage and amount are both displayed, declare which is
input and which is derived; do not accept inconsistent authorities. No arbitrary executable
formula or negative balancing amount is supplied through a custom field.

Resolve the Catalog regular price first, then existing product/scheme, basket/coupon and
authorized manual stages. Preserve the published stacking rules and total discount/MRP/floor
guards; do not create another invoice-discount engine. Sequential percentages apply to their
defined remaining basis: 10% then 5% is 14.5% of the original amount, not 15%. Fixed amounts
declare per-unit, line or document scope. A discount on charges includes only named eligible
charges at a supported calculation stage; document row order alone cannot change the result.
Purchase trade terms stay distinct from sales promotions and later settlement discounts.
Baseline price/manual-discount entry must work without unimplemented campaign/coupon runtime;
advanced promotion capabilities retain their existing separate delivery gates.

For each charge or discount, resolve three independent policy decisions:

| Decision | Required distinction |
|---|---|
| Commercial | Charged/allowed by this invoice's counterparty, versus another party's existing cost; which amount changes this invoice's payable? |
| Tax | Independently taxable supply, apportioned into eligible supply bases, qualifying reduction, or a supported non-tax adjustment? |
| Inventory valuation | Capitalizable input cost/discount, period expense, or no stock-value effect? Which owned receipts/items receive it? |

These are validated policy results, not three free user switches. A transporter's separately
booked bill may increase eligible landed cost without increasing the goods supplier's bill
or posting freight twice. An assessable-value allocation and a landed-cost allocation may
use different target sets/bases. `voucher_charge_allocation` therefore needs a native
allocation purpose, source amount and target; accounting consumers must not sum those views
as independent charges. The original component is counted once in the commercial total.

Default document discount apportionment follows the existing eligible-net-value and stable
largest-remainder policy. Charge allocation can use approved value, compatible quantity,
or a supported measured/manual basis; compare quantities only in compatible units. Each
allocation reconciles to its source; reject zero-denominator, excessive-discount and ineligible
target cases. Quantity-based allocation across kilograms and pieces cannot just sum the numbers.

### 4.1 Required component scopes and amount bases

Purchase and purchase-return profiles must support multiple components at each supported
scope; a single `discount_percent`, `tax_rate` or `additional_charge` column is insufficient.
The same common calculator serves Sales and financial-only notes where their profile permits.

| Scope/input | Required behavior | Example |
|---|---|---|
| Quantity-based discount or charge | Amount per declared quantity denominator and unit; explicit billed, actual, accepted, returned or measured quantity basis as permitted | Packing 2 per billed piece; freight 50 per 100 kg |
| Item/account line | Fixed amount or percentage of a named eligible base; several components can target one line | Trade discount, additional discount and handling on one purchase line |
| Selected lines | Explicit eligible target set frozen in the revision, with shared components allocated only across that set | Discount on one product group, excluding services and already-discounted items |
| Whole invoice | Fixed or percentage discount/charge on eligible bases, allocated to underlying lines for tax, cost and return traceability | Supplier invoice discount and invoice freight |
| Tax component | Percentage of a statutory value, amount per statutory quantity, or an explicitly implemented combined/slab recipe | Separate central/state components; quantity-based levy only when the applicable rule requires it |

Scope, calculation basis and allocation basis are different fields. A fixed invoice freight
amount allocated by weight is not a per-kilogram freight rate. Quantity thresholds that select
a percentage/slab are also distinct from an amount per unit. Freeze units, conversion factors,
denominator, eligible quantity and measurement evidence; do not substitute actual receipt
quantity for billed quantity. Free units, packs, partial receipts and services require explicit
bases; a service without quantity cannot silently default to one unit. Unsupported slab or
measured-basis recipes remain blocked until implemented and verified.

### 4.2 Component dependencies, storage and explanations

Each component has a stable logical key and revision-specific identity. Persist native scope,
purpose, ADD/DEDUCT direction, input kind, input rate/amount, unit/denominator, currency,
inclusive/exclusive basis, eligible targets, basis recipe/version and dependency references.
Store the accepted basis quantity/value, calculated amount, rounding stage/residual, source
evidence, posting mapping and applicable commercial/tax/cost treatment alongside the inputs.
Dependencies and allocations use validated scoped references; custom attributes may describe
a component but cannot define its financial behavior.

Use a bounded, acyclic dependency graph of supported recipes. Two percentages on the original
base are parallel; the second percentage on the first result is sequential. Thus 10% and 5%
can yield either 15% or 14.5% only when the declared bases justify that result. A discount can
include named charges, and a charge can include named discounted bases. Tax-on-tax requires
explicit legal-profile support. Reject cycles, self-inclusion through invoice totals, invalid
or cross-revision references, excessive reductions and component/allocation fan-out beyond
reviewed D07 limits. Display order has no calculation authority.

Keep repeated discounts/charges in `voucher_charge_detail` and purpose-tagged target rows in
`voucher_charge_allocation`; keep tax facts in `voucher_tax_component`. D07 must normalize
multi-target basis/dependency membership and source-return references, reusing shared tables
where appropriate; any necessary shared supporting relation belongs in the reviewed manifest.
Do not add purchase-specific tables or hide relational claims in free-form JSON. Native typed
rules are extensible, but new executable recipes require implementation/versioning, not just
the creation of a company voucher type or custom field.

Preview, approval, supplier comparison, posting and reprint must explain the same component
sequence and totals. Preserve the supplier's declared components and totals separately from
calculated results. Differences need classified, authorized resolution under the selected
policy; never insert a fabricated tax/discount or change stock cost merely to force agreement.
Reports expose source/component/allocation grains without adding commercial, tax-base and
cost allocations together as if they were three charges.

### 4.3 Sales deals and configuration eligibility

Apply the [commercial policy contract](voucher-commercial-configuration.md) before offering or
calculating a component. Sales and Purchase policies, type/class restrictions, product guards
and actor authority constrain the same common pipeline in UI, API and import. Manual entry of
paid/free quantities and automatic scheme entitlement are separate capabilities. Use existing
Catalog definitions and one evaluator; a price-tier discount, reward and manually entered
discount cannot each repeat the same benefit. Supported automatic 10+1 produces disjoint paid/
reward units with pinned rule evidence, while manual terms retain reason/source authority.
Policy retirement preserves original return/reprint evidence; new effects still require live
authorization. CAL17-CAL28 supplement CAL01-CAL16 for these controls and sales/free-stock cases.

## 5. Tax, calculation order and rounding

Treat the pipeline as a versioned dependency sequence, not a universal spreadsheet formula:

1. Resolve profile, currency/units, price basis, party/registration/supply context and dated
   rules. Distinguish actual and billed quantities and freeze input/master evidence.
2. Normalize supported inclusive/exclusive prices; derive base amounts with the jurisdiction
   adapter. Resolve approved discount/charge dependencies and promotion eligibility once.
3. Calculate and allocate commercial discounts/charges in their declared stages. Keep the
   legally taxable base separate from commercial net: not every discount reduces tax.
4. Apply the supported supply classification and tax rules per line/allocation. Composite/mixed
   supply treatment cannot be inferred merely from mixing goods and services on one screen.
   Preserve CGST/SGST/UTGST/IGST/cess or the selected VAT components and recoverability separately.
5. Reconcile line results and tax components into invoice total, then apply supported invoice
   rounding/other typed adjustments at their declared stage. Any tax-affecting adjustment must
   feed the appropriate tax calculation; it cannot be disguised as post-tax rounding.
6. Determine party settlement obligation, including any applicable statutory additions or
   deductions through typed postings. Apply eligible existing advances/credits and recognized
   new tenders once; derive remaining open items and due dates.
7. Produce linked commercial, tax, settlement, stock-value and ledger previews. Accounting
   revalidates the approved result and commits all promised effects in its guarded transaction.

Inclusive tax is extracted from the price, not added again. A gross discount over several tax
rates needs a supported inversion/allocation rule. Slabs, quantity cess and compounding cannot
be reduced to one header `tax_percentage`. Unimplemented combinations fail with a precise reason.
For an inclusive line, a percentage discount declared on `GROSS_INCL_TAX` uses the actual entered
gross consideration, including supplier-charged fixed cess and its explicit price-rounding bridge.
It then allocates the gross discount back to net/tax per line; the fixed cess remains a fixed
quantity levy unless its statutory rule says otherwise. A price cannot be marked tax-inclusive
when every resolved tax component is payable only by the recipient under reverse charge.
Catalog's `INCLUSIVE`/`EXCLUSIVE` price-plan result maps to the invoice line's
`GROSS_INCL_TAX`/`NET_EXCL_TAX` basis when that price is selected. Do not infer the invoice basis
from an item's MRP: the same item can have an inclusive retail MRP and an exclusive wholesale
selling price. The line basis and selected price evidence must be preserved together by future
price-to-voucher integration.
The current native invoice tax resolver supports ordinary services and untaxed account lines;
tax-bearing goods still require a goods statutory resolver and selected-price evidence before
an inclusive item price can be posted through the full voucher flow.
India's [CGST Rule 35](https://cbic-gst.gov.in/valuation-rules.html) governs the extraction of
GST from an inclusive value.
Rate or taxable-value overrides retain the original result, accepted value, reason and authority;
permission alone cannot override a statutory prohibition. Free quantity/value does not imply
zero taxable value or zero inventory cost.

For India, inclusions and discount exclusions depend on the applicable version of the valuation
rules; see [CBIC section 15](https://taxinformation.cbic.gov.in/content-page/explore-act/1000284/1000001).
This plan does not hard-code an old post-supply-discount condition or treat Tally's configurable
ledger order as law. GST/state-VAT scope, tax dates, RCM and ITC remain governed by the tax plan.

Use exact decimal arithmetic and existing storage limits; apply explicit rate, line, tax,
currency and invoice rounding stages. A rounding increment is not the same as display precision.
Record residual allocation deterministically; line/charge/tax summaries must reproduce the
accepted total exactly. Rounding an invoice does not silently change a statutory tax component.
Snapshot engine/policy versions, input digest, component results, rounding and approval evidence.
Reprints/returns use that snapshot, not today's item price or tax configuration.

Invoice-level tax entry is an input convenience: normalize it into eligible supply/component
allocations, preserving the entered header amount and allocation evidence. A derived header
tax summary is not an additional tax to add to already-taxed lines. Mixed rates, exemptions,
registrations and recovery treatments remain distinct; never average them into one tax rate.
Validate the permitted combination (for example, central plus state/UT components versus
integrated tax) and any applicable cess through the effective profile. GST, state VAT and
quantity levies cannot be freely stacked by selecting account names. Tax on an independent
service charge versus a charge included in goods' assessable value must follow its resolved
treatment, without taxing both representations. Withholding remains a separate tax/settlement
classification, not an ordinary trade discount.

### 5.1 Purchase-return component and adjustment contract

1. Select original invoice revisions, lines, component allocations and executed receipt slices.
   A partial or consolidated return preserves those source identities individually, including
   their currency, unit, tax profile, supplier and registration compatibility. Do not rerun
   today's price, promotion threshold, invoice discount or tax setup on the smaller return.
2. Track financial quantity/value claims separately from physical returned quantity. An
   amount-only allowance changes no stock; returning free units does not automatically create
   a priced supplier credit. Each original component has an explicit return treatment:
   proportional, approved fixed/full entitlement, nonreturnable, or reviewed manual allocation.
   Shipping already consumed need not be refundable; the decision and supplier evidence persist.
3. Bound cumulative returned quantities, commercial amounts and component/tax adjustments by
   the compatible source entitlements, accounting for earlier notes, cancellations and reversals.
   Claims on a shared source must be reserved/consumed atomically by the accepted effect owner
   under D01/D04; Vouchers links alone cannot enforce money or stock caps. Replays do not consume
   entitlement twice. The final eligible allocation receives the deterministic remaining minor
   units; legitimate nonrefundable balances are not forced to zero when all goods are returned.
4. Preserve the original statutory base/component history and apply the dated adjustment rules
   and required evidence for the return event. A purchaser's commercial Debit Note/return advice,
   Rejections Out movement and supplier statutory credit note are separate evidence/effects.
   Do not infer an ITC reversal or tax refund solely from a stock return. Link the supplier note
   to the already-recorded commercial adjustment and record only an explained additional delta
   where needed; never recognize the same credit twice. Missing legacy component detail needs
   a reviewed opening/source allocation, not invented historical tax precision.
5. New return freight, restocking fees and negotiated extra allowances are new identified
   components with their own dated treatment and evidence, separate from reversal of original
   components. Supplier-credit caps apply to the original allocations; separately authorized
   new adjustments retain their own limits and reason. Refund payment/bill adjustment is a
   linked settlement action; approving a purchase return does not imply cash was received.
6. Reverse/remove stock value using the selected Accounting cost policy and original quantity/
   cost lineage, retaining immutable value legs. Supplier credit may differ from carrying value
   because of landed costs, later cost adjustments or consumed stock; post an explained cost/
   expense/variance bridge. Never equate tax-inclusive credit to stock value or rewrite old
   layers. Financial-only adjustments can affect remaining inventory or expense/COGS without
   inventing a physical return. Closed-period and cross-year rules still apply.

Unpaid supplier credit reduces the compatible payable; excess credit remains an identifiable
supplier debit balance/receivable or unapplied credit under the open-item policy until settled.
The stock ledger, purchase-return register, tax register and party ledger must reconcile through
the same source allocations, with explicit timing differences for evidence still pending.

## 6. Payment mode, credit terms and recognition

Cash, bank transfer, UPI, card and cheque are tender modes with supported mode-specific fields;
credit is an unpaid-balance/terms condition. An invoice may have existing advance adjustment,
several recognized tenders and an unpaid remainder simultaneously. Keep amounts in separate
totals: entered commercial amount, discounts, charges, taxable bases, tax, invoice total,
party obligation, applied existing credit, recognized settlement and remaining outstanding.
Withholding/TCS and other statutory adjustments need their own classification/recognition
stage so they are not counted in both invoice total and settlement a second time.

An accepted card collection can, under its approved profile, settle the customer through a
card-clearing receivable before the provider credits the bank. Later net bank settlement and
merchant fee clear that receivable; the fee does not reopen the customer invoice. A pending
payment request is not an accepted collection. Cheques and failed/returned instruments follow
their own recognition/correction policy; storing a reference alone proves no settlement.
For cash tendered above the payable, distinguish applied cash from change returned; a genuine
overpayment retained as credit must be explicitly classified rather than called change.

Select one effect owner: the invoice's combined Accounting posting or a linked Receipt/Payment.
Provider callbacks, printed receipts and later bank reconciliation reference that same money
effect. Never settle it once from invoice tenders and again from a Receipt or bank import.

## 7. Worked invoice and purchase-cost examples

Illustrative INR amounts, not prescribed tax rates. Assume two independent taxable supplies,
tax-exclusive prices, a permitted document discount and a permitted charge allocation by net
value. Assume the selected policy rounds these allocated bases and tax components to paise.
This assumption must be validated by the actual tax profile, not applied to all freight/services.

| Calculation | Goods A | Service B | Total |
|---|---:|---:|---:|
| Entered amount | 1,000.00 | 500.00 | 1,500.00 |
| Line discount | -100.00 | 0.00 | -100.00 |
| Document discount 140, allocated by remaining value | -90.00 | -50.00 | -140.00 |
| Net commercial lines | 810.00 | 450.00 | 1,260.00 |
| Charge 100, allocated by net value | 64.29 | 35.71 | 100.00 |
| Taxable base under the assumed profile | 874.29 | 485.71 | 1,360.00 |
| Illustrative tax: 5% / 18% | 43.71 | 87.43 | 131.14 |
| Invoice before rounding | 918.00 | 573.14 | 1,491.14 |

An explicit -0.14 invoice-rounding entry makes invoice total **1,491.00**. Applying an existing
advance of 300, recognized cash of 200 and recognized card collection of 400 leaves **591.00**
outstanding. Invoice total remains 1,491.00. The card-clearing amount may await bank settlement.
Only Goods A needs physical execution/reference; Service B has no fictitious stock movement.
Any required tax-on-advance adjustment remains a separately linked tax event.

Purchase costing is a different reconciliation. Reuse the existing pricing-plan illustration:
100 billed units at 80 = 8,000; trade discount 800; eligible freight 400; nonrecoverable tax
100; actual receipt 110 units including 10 free. Eligible cost is **7,700**, or **70 per actual
unit**, while recoverable tax is separate. The goods supplier's payable includes only amounts
that supplier charges; a different freight supplier has its own payable/payment source. Later
cost adjustments allocate against receipt layers and any already-issued stock under the
Accounting valuation policy. They never overwrite the original price or receipt snapshot.

### 7.1 Stacked purchase components and repeated partial returns

Illustrative INR fixture, not a prescribed tax treatment: actual equals billed quantity,
prices exclude tax, all shown discounts/charges affect the assumed taxable base, both lines
are independent supplies, and component taxes round half-up to paise. Packing and freight
are assumed assessable and proportionally returnable. Actual profiles must validate each
assumption, including rounding and adjustment eligibility.

| Calculation in declared dependency order | Goods A: 10 at 100 | Goods B: 5 at 100 | Total |
|---|---:|---:|---:|
| Entered amount | 1,000.00 | 500.00 | 1,500.00 |
| A trade discount 10% of entered amount | -100.00 | 0.00 | -100.00 |
| A further discount 10% of remaining 900 | -90.00 | 0.00 | -90.00 |
| A quantity discount 1 per billed piece | -10.00 | 0.00 | -10.00 |
| B fixed line discount | 0.00 | -100.00 | -100.00 |
| Remaining line bases | 800.00 | 400.00 | 1,200.00 |
| Invoice discount 10%, allocated by those bases | -80.00 | -40.00 | -120.00 |
| A packing 2 per billed piece; B fixed handling 10 | 20.00 | 10.00 | 30.00 |
| Invoice freight 111, allocated by preceding 740:370 bases | 74.00 | 37.00 | 111.00 |
| Taxable base under the assumed profile | 814.00 | 407.00 | 1,221.00 |
| Illustrative central tax: 9% / 2.5% | 73.26 | 10.18 | 83.44 |
| Illustrative state tax: 9% / 2.5% | 73.26 | 10.18 | 83.44 |
| Supplier invoice total | 960.52 | 427.36 | **1,387.88** |

Returning two A pieces claims 20% of A's original allocations: gross 200, discounts
20 + 18 + 2 + 16, packing 4 and freight 14.80, giving base **162.80**. Under this fixture's permitted
source-allocation rounding, central/state tax is 14.65 each and credit is **192.10**. Five
such returns consume A completely: the first four credits are 192.10 and the last is **192.12**,
with 14.66 of each tax component on that final return. Total A credit is exactly **960.52**;
B remains **427.36**. Do not recalculate an invoice discount threshold on each return.
If freight is nonreturnable or statutory rounding differs, use that explicit supported policy
and its reconciliation instead; this fixture is not a blanket rule for supplier tax notes.

### 7.2 Configured sales deal with discounts and charges

Illustrative same-SKU 10+1: actual quantity 11, billed quantity 10, rate 100 and cost 60 per
physical unit. Assume the selected commercial policy explicitly allows the deal to combine
with a 10% line discount, then a 5% bill discount on the remaining paid consideration, plus
a fixed assessable packing charge of 20. Assume a supported tax-exclusive profile with 9%
central and 9% state components, and both discounts qualify to reduce the taxable base.

| Result | Amount/quantity |
|---|---:|
| Paid amount: 10 x 100 | 1,000.00 |
| Line discount | -100.00 |
| Bill discount: 5% of 900 | -45.00 |
| Packing | 20.00 |
| Taxable base under the assumed profile | 875.00 |
| Central tax / state tax | 78.75 / 78.75 |
| Invoice total | **1,032.50** |
| Actual stock issued / total cost | **11 / 660.00** |

The reward's regular-price comparison value of 100 is informational: it is not deducted from
1,000 again and is not a second expense in addition to the all-unit cost of 660. If the type
forbids a bill discount with this scheme, the attempted combination is rejected; an explicit
re-quote may select another permitted combination, but the server cannot silently remove it.
Actual tax classification and account mapping remain profile requirements, not fixture defaults.

## 8. Schema/API integration and acceptance gates

Reuse `voucher`/`voucher_revision`/`voucher_line` plus existing proposed typed account, item,
inventory, charge/allocation, tax/withholding, bill-allocation and tender sections. Components
are shared across both kinds and company types. Additional native fields/refinements do not
require new per-kind tables or changing the 51-candidate baseline.

Expose one typed invoice preview through the common voucher API: normalized line/component
results, eligible/blocked allocations, source tax differences, tax breakdown, recognized versus
pending settlement, remaining debt and proposed stock/accounting effects. Explanations must
respect field permissions. Caller-supplied totals are consistency assertions, not independent
posting authority. Preview/approval pins the input digest and calculation revisions; any change
to the bill requires revalidation and, where required, renewed approval. For non-stock invoices,
the same charge/tax/settlement sections work without dummy inventory rows.

The current [Accounting tax input](../apis/accounting/src/accounting/schemas/voucher_tax.py)
has a narrower source-document taxable-value/withholding shape. V0 must version/extend its
contract for these line/component allocations; a single aggregate taxable value cannot prove
multi-rate invoice compatibility. Catalog prices/definitions and existing Accounting tax/open-
item primitives remain foundations, not an implemented invoice calculator or stock posting API.
V3 can deliver account/service posting and item-mode preparation; stock-bearing invoice posting
stays disabled until the V4 quantity/value contract and relevant acceptance cases pass.

Acceptance cases before enabling the respective V3/V4 profiles:

- Accounts-only Sales/Purchase, mixed goods/services and direct/linked/deferred item invoices
  yield the required effects exactly once, including partial fulfillment and actual/billed differences.
- Fixed/percentage discounts at line and document level reconcile; stacking, charges-in-basis,
  promotion replay, excessive discount, mixed-unit allocation and rounding residuals are checked.
- Inclusive/exclusive and mixed-rate invoices reproduce bases/components; test supported cess,
  nil/exempt/RCM classifications, declared supplier differences and prohibited overrides.
- Advance + split tender + credit remainder reconcile; pending references, change, provider fees,
  withholding and duplicate callbacks do not create false or duplicate settlement.
- Purchase payable, tax recoverability and landed cost reconcile independently, including
  third-party charges, free receipt units, late costs and already-issued stock.
- Returns/corrections use original discount, charge, tax, tender and movement allocations;
  a returned item is not refunded twice and an invoice correction does not repeat stock movement.

These are design acceptance cases, not tests run in Tally or implementation claims.

### 8.1 Required component acceptance matrix

The following are future implementation checks within the existing batches, not additional
voucher kinds, parent batches or a claim that the calculation engine already exists.

| Check | Required evidence | Batch scope |
|---|---|---|
| CAL01 | Multiple fixed/percentage/per-quantity components at line, selected-line and document scopes; accounts-only mode requires no dummy SKU | B15/B17 |
| CAL02 | Sequential versus common-original-base discounts, named charge inclusion, deterministic evaluation independent of display order | B15 |
| CAL03 | Actual/billed/free/accepted/returned and measured quantity distinctions; pack/per-100 conversions; incompatible units and absent measurements rejected | B15/B24/B25 |
| CAL04 | Fixed invoice allocation versus per-unit amount calculation; eligible/excluded targets, zero denominator, excess discount and stable residual checks | B15 |
| CAL05 | Multiple tax components, quantity/value and implemented combined/slab bases; incompatible tax combinations and unsupported recipes blocked | B16 |
| CAL06 | Header entry and line tax results reconcile once across mixed rates/exemptions; independent taxed service charge versus assessable charge allocation | B15/B16/B18 |
| CAL07 | Inclusive/exclusive entry, gross discount inversion, tax-on-tax only when supported, statutory versus invoice rounding and immutable rate versions | B15/B16 |
| CAL08 | Supplier-declared/component differences, authorized resolution and old aggregate tax-reader compatibility without manufactured balancing tax | B16/B17 |
| CAL09 | Payable, recoverable/pending/nonrecoverable tax, landed cost and third-party freight reconcile without duplicate liabilities or capitalization | B17/B22/B24 |
| CAL10 | Multi-source partial returns retain original component allocations; five-return fixture exactly exhausts refundable A amounts with final residual | B17/B25 |
| CAL11 | Physical free-quantity return, financial-only allowance and full/partial/nonrefundable charge entitlements are distinct; no duplicate stock movement | B17/B25 |
| CAL12 | Concurrent/replayed/cancelled source claims enforce cumulative quantity/value/tax limits; approved extra return fees have separate identities and limits | B17/B25 |
| CAL13 | Commercial return advice, supplier tax note, ITC adjustment and refund are linked without duplicate credit; overpaid supplier balances remain traceable | B16/B17/B25 |
| CAL14 | Carrying-value versus supplier-credit bridge, late costs, already-issued stock and closed/cross-year corrections preserve immutable quantity/value history | B22/B24/B25/B26 |
| CAL15 | Native scoped component/dependency/allocation references, bounded graph, cycle rejection, field permissions and revision-bound approval/reprint | B02/B04/B15/B17 |
| CAL16 | Purchase/return and tax registers drill into components; financial/stock reports reconcile without multiplied totals; full invoice/return rehearsal | B18/B27/B45 |
| CAL17 | Company Sales/Purchase policies and type/class/product restrictions intersect; defaults never widen authority; reject conflicts and cross-company policy references | B02/B05/B06/B15 |
| CAL18 | Same-item manual 10+1 retains 10 paid/1 reward/11 actual, explicit term authority and all-unit cost; Purchase free receipt does not consume a sales scheme | B15/B24 |
| CAL19 | Automatic 10+1 at paid quantities 9/10/19/20 yields 0/1/1/2 rewards before caps; units, serial integers, stacking, concurrency and repeat limits are enforced | B15/B24 |
| CAL20 | Cross-item reward uses a distinct eligible ITEM/tracking allocation; missing gift, unsupported tax allocation and implicit substitution block acceptance | B15/B16/B24 |
| CAL21 | Ordinary zero-price, sample/gift and paid-supply reward purposes are distinct; mandatory tax and stock cost cannot be disabled with UI/free-item flags | B06/B16/B24 |
| CAL22 | Scheme, regular-price reduction and manual/bill discounts combine only under explicit stack permission; worked 1032.50 invoice costs 660 for 11 physical units without duplicate benefit | B15/B24 |
| CAL23 | Required/default charges, tax profiles and override/approval limits apply to API/import/UI equally; hiding a field cannot authorize or remove a financial effect | B06/B08/B15/B16 |
| CAL24 | Policy publication/stop versus posting races, stale projections and changed quote digests cannot bypass controls; history/reprint keeps accepted revisions | B06/B07/B15/B24 |
| CAL25 | Disabled new promotion entry still permits separately authorized original-allocation returns; no automatic gift-list-price recovery, repeated award or coupon restoration | B17/B25 |
| CAL26 | Source-scoped rewards survive lot splits, order/challan conversion and partial billing/fulfillment without duplicate award; unimplemented deferred gifts or cumulative schemes rejected | B24/B29/B30 |
| CAL27 | Effective-policy discovery exposes only implemented compatible mechanics and masked explanations; manual free terms do not imply automatic scheme/coupon runtime readiness | B06/B08/B15/B24 |
| CAL28 | Reports distinguish paid/reward/actual quantities, monetary versus informational benefits, all-unit COGS and returns; sales/purchase policy and scheme replay rehearsal | B18/B27/B45 |

## Decision log

- 2026-11-03 (owner decision D02, B24): a purchased goods line's landed cost (`stock_cost`) is its commercial
  value after discounts and the supplier charges apportioned to it, plus GST that cannot be claimed; claimable GST
  is recoverable tax and rounding is never capitalised. A charge on goods carries no separate account and is spread
  over goods lines only, by value ([purchase-product-review](purchase-product-review.md#owner-decisions-2026-11-03)).

- 2026-10-31: Purchase API review found that preview bounded tenders but omitted
  advance allocations from the over-settlement guard. Require exact advance plus
  tender totals at or below calculated payable for Sales/Purchase; financial notes
  retain their original-component preparation guards. No change to balance authority.

- 2026-10-10: Added Sales/Purchase native configuration and Tally research via the commercial
  configuration contract. Extended acceptance to CAL01-CAL28 for manual/automatic 10+1,
  independent samples/gifts, restricted stacking, API/import enforcement and source-linked
  returns/fulfillment. Added a controlled sales-deal fixture; runtime remains future work.

- 2026-10-10: Required repeated quantity, line, selected-line and invoice discounts/charges/
  taxes for Purchase and purchase returns. Added native component dependencies, header-tax
  normalization, original-allocation return caps and independent supplier-credit/tax/cost
  bridges, a stacked purchase/partial-return fixture and CAL01-CAL16. Existing D02/D04/D05/
  D07/D09 gates and 45 batches remain; no costing or statutory rule was silently selected.

- 2026-10-10: User requested deeper Sales/Purchase coverage with inventory or accounting-only
  posting and proper charges, tax, discounts and payment modes. Added sourced Tally capabilities,
  an effect matrix, one component calculation authority, independent commercial/tax/valuation
  allocations, split settlement and worked reconciliations. Shared tables and owner boundaries
  remain; implementation and unsupported tax/stock combinations require explicit contracts.
