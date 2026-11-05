# TallyPrime: Payment, Receipt, bill adjustment and advances

**Reviewed:** 2026-10-10, against official TallyHelp and relevant existing Accounting code.
**Status:** Functional research and proposed Vouchers refinements; no implementation claimed.
**Scope:** Customer/supplier and other non-payroll money transactions. Payroll/HR remain excluded.
**Read with:** [Vouchers plan](vouchers-plan.md), [shared data model](voucher-data-model.md),
[bank/journal review](tally-voucher-functional-review.md) and [India tax plan](voucher-tax-recording.md).

## 1. Voucher kind, transaction purpose and allocation are different

Payment and Receipt are base voucher kinds. An advance is a purpose of either kind;
bill adjustment identifies how amounts are applied to outstanding references. Tally's
Settle Bills action prepares a Payment or Receipt from selected outstanding bills, rather
than introducing a separate base kind. Full/partial and repeated settlement are supported.
See [settling outstanding dues](https://help.tallysolutions.com/manage-outstanding-payables-tally/).

| Business action | Voucher/workflow | Meaning for our model |
|---|---|---|
| Pay a supplier bill | Payment with bill allocation | New outflow and settlement of existing debt |
| Collect a customer bill | Receipt with bill allocation | New inflow and settlement of existing debt |
| Pay a direct expense / receive other income | Payment / Receipt with account allocations | May book a new expense/income rather than settle an invoice |
| Receive customer advance | Receipt with advance purpose | Money received before the related invoice; preserve unapplied credit |
| Pay supplier advance | Payment with advance purpose | Money paid before the related bill; preserve unapplied credit |
| Apply existing advance | Bill allocation in a later Sales/Purchase or supported adjustment workflow | Consume existing available value without receiving/paying it again |
| Refund customer advance | Payment with refund purpose | New outflow linked to the remaining refundable advance |
| Receive supplier advance refund | Receipt with refund purpose | New inflow linked to the remaining recoverable advance |
| Retain return credit for later business | Supported Credit/Debit Note and allocation workflow | Credit availability changes; no cash refund merely because a note exists |

The advance/refund/return rows are supported by the current Tally guides cited in section 4.
The rightmost column is our proposed effect model, not Tally's private storage architecture.
Company types such as Bank Payment, Advance Receipt or Supplier Advance reuse the same base
tables and supported profiles. These names do not add new predefined voucher kinds to our 22.

## 2. Payment and Receipt entry capabilities

Tally supports cash/bank transactions in simplified or debit/credit entry modes, multiple
counterpart ledger allocations and bank-instrument details. Bills can be selected before
entering the amount, or allocated after the amount is entered. Pending bills can be sorted;
due-date ordering supports automatic application to older dues. Formal receipts and transaction
registers support acknowledgement and review. See
[Payment and Receipt entry](https://help.tallysolutions.com/knowledgebase/payments-and-receipts-tally/).

For our platform, the shared entry must keep these responsibilities separate:

| Section | Required facts when applicable |
|---|---|
| Money | Cash/bank account, tender amount/currency, mode, instrument/reference and recognition evidence |
| Counterpart | Party/role/account or expense/income account, business purpose and amount |
| Bills | Target references, allocation amount, resulting remainder and allocation business date |
| Terms | Bill date, due date or installment schedule; frozen terms rather than today's master defaults |
| Adjustments | Explicit discount, withholding, fee, write-off or FX purpose, account and source evidence |
| Advance | Original source, party/role, intended order/supply if known, available amount and tax classification |
| Audit | Actor, approval, immutable source revision, operation identity and Accounting result IDs |

The amount reducing a party balance can differ from the bank amount. Tally documents receipts
with a separate discount ledger; see
[receipts and settlement discounts](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/).
Our discount, withholding and write-off profiles must explicitly reconcile the difference;
they cannot be a generic override of the outstanding amount. Bank fees do not automatically
reduce the customer's debt. Tax or withholding eligibility follows its own supported rules.

## 3. Bill-wise reference semantics

Tally supports party-total tracking and bill-wise tracking. The latter exposes references,
due dates, ageing and settlement history. Its current tracking guide lists New Ref, Against
Ref and On Account, including New Ref/On Account for advances. See
[outstanding tracking methods](https://help.tallysolutions.com/receivables-payables-tracking-methods/).
The current sales guide also explicitly documents an Advance reference option. See
[advance receipt entry](https://help.tallysolutions.com/sales-receipts-additional-charges-discounts-free-items/).
Do not claim that all releases/configurations expose exactly the same reference menu.

| Reference concept | Meaning |
|---|---|
| New Ref | Establish a separately tracked outstanding reference |
| Agst Ref / Against Ref | Apply an amount against an existing reference |
| Advance | Explicitly identify a payment/receipt preceding the related bill, where that option is exposed |
| On Account | Record a party amount without selecting a particular bill |

Our native design separates **reference mode** from **business purpose**. An ADVANCE purpose
may create a named reference or remain on-account; an unidentified on-account receipt is not
automatically a taxable advance. Preserve source labels on imports, but normalize their meaning
through a versioned adapter rather than copying one release's UI enum into every API.

One money entry may settle several bills, and one bill may be settled over several entries.
An excess payment/receipt remains explicitly unapplied; partial settlement leaves the remainder
open. Tally's report-based settlement workflow supports these partial payments; see
[outstanding settlement](https://help.tallysolutions.com/manage-outstanding-payables-tally/).

For our product, later assignment of an existing on-account credit is an allocation operation,
not another Receipt/Payment. Ordinary allocation within the same accounting scope creates no
new cash or revenue/expense. A necessary FX difference or account reclassification is an
explicit additional financial effect, never silently folded into a no-money adjustment.
Automatic bill selection is a visible proposal with a saved rule/order; authoritative balances
must be checked again when Accounting commits it.

## 4. Advance lifecycle in current TallyPrime

| Stage | Documented behavior | Official guide |
|---|---|---|
| Receive advance | Receipt with Nature of Receipt set to Advance Receipt and supply/tax details | [GST advances received, Release 3.0+](https://help.tallysolutions.com/india-gst-advance-receipts-tally/) |
| Pay an RCM advance | Payment with a specific Advance Payment Under Reverse Charge nature | [GST advances paid, Release 3.0+](https://help.tallysolutions.com/india-gst-advance-payments-gst-reverse-charge-tally/) |
| Adjust received advance | Sales invoice supports manual selection/amount or configured automatic adjustment | [Adjust advances received](https://help.tallysolutions.com/adjust-advance-received/) |
| Adjust paid advance | Purchase supports equivalent manual/automatic adjustment and remaining-advance reporting | [Adjust advances paid](https://help.tallysolutions.com/adjust-advances-under-gst/) |
| Refund received advance | Payment with Refund of Advance Receipt purpose | [Reverse advances received](https://help.tallysolutions.com/reverse-advance-received-gst/) |
| Recover paid advance | Receipt with Refund of Advance Payment purpose | [Reverse advances paid](https://help.tallysolutions.com/reverse-advances-under-gst/) |
| Return after advance application | Supported Credit/Debit Note flow can restore availability for future invoices, including fully used references | [Customer return credit](https://help.tallysolutions.com/reverse-advance-received-gst/), [supplier return credit](https://help.tallysolutions.com/reverse-advances-under-gst/) |
| Migrate outstanding advances | Separate opening advance evidence records registration, party, place of supply, original date, rate and unadjusted amount | [Opening advances received](https://help.tallysolutions.com/opening-balance-for-unadjusted-advances-gst/), [opening advances paid](https://help.tallysolutions.com/opening-balance-for-unadjusted-advances-under-gst/) |

The GST adjustment guides describe automatic selection by GST rate and place of supply in
FIFO order. This differs from ordinary bill settlement ordered by due date. Manual adjustment
allows selecting several advances and changing amounts. See
[advance matching](https://help.tallysolutions.com/adjust-advance-received/).
Our eligible-candidate filter must additionally enforce company, party/role, currency,
registration, tax treatment and source availability; FIFO never overrides an incompatibility.
An RCM-specific Payment nature must not become the default for every supplier advance.

**Financial application and tax adjustment are separate allocations.** Store the gross amount
applied to the bill, and separately the applicable advance taxable base/components and their
recognition/adjustment events. An advance can have no tax effect, a tax effect already recorded,
or an amount still needing statutory review; a single `adjusted` boolean cannot express this.
Opening tax-advance evidence must reconcile to an imported Accounting opening credit, not
create a second cash receipt or blindly duplicate the opening ledger amount.

Tally's legacy Release 2.1-and-earlier article contains historical turnover-based explanations.
Even current entry guides describe tax-ledger/configuration choices; these are product
workflows, not authority to choose the legal tax point. Our India tax plan governs dated rules,
goods/service treatment, RCM, statutory receipt/refund evidence and credit eligibility.
The GST Portal separately explains taxable service advances and later invoice adjustment;
same-return invoice reporting must not cause duplicate advance tax. See
[GST Portal advance reporting](https://tutorial.gst.gov.in/userguide/returns/GSTR_1.htm).
No generic VAT rule is inferred from Tally's GCC VAT guides; India state VAT remains profile-specific.

## 5. Worked examples for our model

Amounts below illustrate money/allocation behavior only; taxes are omitted.

| Event | New money effect | Outstanding result |
|---|---|---|
| Customer pays INR 30,000 before invoicing | Receipt +30,000 | Unapplied advance 30,000 |
| Sales invoice INR 50,000 applies that advance | None from advance application | Invoice remainder 20,000; advance remainder zero |
| Customer pays INR 12,000 later | Receipt +12,000 | Invoice remainder 8,000 |
| Collect INR 7,900 and authorize INR 100 settlement discount | Receipt +7,900; separate discount effect 100 | Invoice settled; total cash received is 49,900 |
| Supplier receives INR 20,000 advance, later bills INR 12,000 | Payment -20,000; no new cash at bill adjustment | Unapplied supplier advance 8,000 |
| Supplier refunds INR 3,000 of that remainder | Receipt +3,000 | Supplier advance available 5,000 |

If a return reinstates INR 5,000 previously applied from an advance, record a linked return
credit/reinstatement event. Do not rewrite the original receipt from 30,000 to 35,000. A later
refund and a later invoice application compete for that same available credit and must not
both consume it. A return credit is not automatically cash, a new sales advance or a tax reversal.

## 6. Reuse and implementation gaps

Accounting already has [allocation inputs](../apis/accounting/src/accounting/schemas/subledger.py)
and [allocation/reversal commands](../apis/accounting/src/accounting/tasks/allocations.py).
The commands operate on debt/credit open items of the same company, party, role, account and
currency, enforce dated history, and can generate realized FX for different carrying rates.
These are reusable primitives, not proof that Vouchers' multi-line atomic orchestration exists.

| Requirement | Shared representation / implementation gate |
|---|---|
| Reference and purpose distinction | Extend `voucher_bill_allocation` inputs with normalized reference mode, purpose, scoped account allocation, source/target IDs, amount and dates |
| New credit vs existing credit | Posting creates the actual open item; allocation consumes it. Vouchers stores requests/results rather than authoritative remaining balances |
| Late allocation/reallocation | Use dated `voucher_operation` evidence and Accounting allocation/reversal IDs; preserve the original issued voucher revision |
| Pure bill adjustment | Provide an allocation command/workflow without a fabricated zero-value cash voucher or an unconditional new base kind |
| Settlement differences | Use native ACCOUNT/ADJUSTMENT lines, withholding detail and supported posting profiles; explicit cash-versus-party reconciliation |
| Named advances and on-account amounts | Retain source identity even if the UI omits a bill name; classify known advance, unidentified receipt and refundable deposit separately |
| Automatic allocation | Persist proposed matches, policy version, deterministic tie-breaks and acceptance; recheck available amounts at commit |
| Partial refunds and returns | Link original open items/allocations and return-credit provenance; enforce refund-plus-use bounds in the authoritative transaction |
| Tax-aware advance matching | Reuse tax context/components and tax events/allocations; preserve amount-level links between financial use and statutory adjustment |
| Opening migration | Link opening financial credit and tax-advance evidence with original dates and already-recognized tax; no duplicate money effect |
| Multiple bills/parties or control accounts | Finalize one atomic Accounting command where promised; cross-role, cross-party, cross-account or cross-currency netting is not supported merely by the existing pair-allocation API |
| Outstanding views | Distinguish gross bills, allocated amounts, unapplied credits/advances, refunds, due dates and net party balance; bank reconciliation is a separate view |

These refinements reuse the 51-candidate baseline and the additional shared banking candidates
already identified. They do not require per-kind payment/receipt/advance tables or a second
mutable advance-balance table. Exact columns, master classifications and bulk command semantics
remain V0 design work. V2 covers money/settlement, V3 invoice application and relevant tax
profiles, and V6 reconciled reporting. No new implementation phase or payroll scope is added.

## 7. Acceptance cases for later implementation

1. Settle two bills with one payment, and one bill with several payments; retain exact remainders.
2. Record an excess/on-account receipt, then allocate it later without a second cash posting.
3. Apply several advances to one invoice and one advance across invoices; reject concurrent overuse.
4. Separate bank amount from approved discount/withholding; retain the unpaid balance when no
   adjustment is authorized. Do not silently clear a bank fee or short payment.
5. Reverse a mistaken allocation and apply the credit elsewhere, retaining dates and history;
   enforce period controls and realized-FX reversal rules where applicable.
6. Apply/refund/reinstate advances partially; reject double consumption and unauthorized cross-party netting.
7. Reconcile financial and tax portions across partial invoices, rate/registration mismatches,
   same/later return periods, returns and refunds under the selected jurisdiction rules.
8. Import opening financial/tax advance evidence once; changing the setup cutoff creates no money.

These are proposed acceptance scenarios, not tests run in Tally or new application tests.

## Decision log

- 2026-10-10: User requested TallyPrime Payment, Receipt, bill-adjustment and advance research.
  Distinguished kinds, purposes and reference modes; added current advance/refund/return and
  opening workflows, due-date versus tax-aware FIFO matching, native settlement differences,
  and separate financial/tax allocations. Existing Accounting allocation/reversal is reused;
  cross-scope/bulk orchestration remains a contract gate. No implementation or new base kinds.
