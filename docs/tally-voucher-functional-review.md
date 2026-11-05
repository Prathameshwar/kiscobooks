# TallyPrime: Journal, Stock Journal and banking capabilities

**Reviewed:** 2026-10-10, using official TallyHelp documentation.
**Status:** Functional research and proposed plan refinements, not an implemented feature list.
**Scope:** Accounting Journal, Stock Journal and bank-related transactions; payroll/HR excluded.
**Read with:** [Vouchers plan](vouchers-plan.md), [shared data model](voucher-data-model.md),
[table inventory](voucher-table-inventory.md) and [India tax recording](voucher-tax-recording.md).
**Follow-up:** [Payment, Receipt, bill adjustment and advances](tally-settlement-functional-review.md)
examines settlement reference modes, unused credits, refunds and tax-aware advance matching.

This reviews published behavior, not Tally's private database or a tested installation.
Release/configuration differences matter: the banking guides include features added in
Releases 6.0 and 7.1. Legacy references below are explicitly identified. Full Tally parity
is not selected simply by documenting a capability; implementation boundaries remain V0 gates.

## 1. Accounting Journal

Journal is a general ledger-entry document. It supports multiple debit and credit accounts,
dates and narration, and is commonly used for depreciation and accounting adjustments.
Tally also permits cash/bank entries through Journal; describing it as intrinsically
non-cash would be incorrect. Payment/Receipt/Contra offer more specific entry workflows.
See [accounting entry](https://help.tallysolutions.com/accounting-entry-tally/).

| Capability | Functional meaning |
|---|---|
| Compound ledger entry | Several accounts on either side of one balanced transaction |
| Accrual/adjustment | Record an expense payable, provision, depreciation or account reclassification |
| Party/bill detail | Preserve the party and bill purpose instead of reducing the entry to ledger totals |
| Cost allocation | Attribute income/expense to departments, projects or other cost centres |
| Foreign currency | Keep transaction currency/rate and record supported exchange differences |
| Statutory adjustment | Use a tax-specific adjustment purpose and details where supported |
| Review | Inspect the journal register, Day Book and affected ledger entries |

The party detail uses bill references such as new reference, against reference and on-account;
these express creation, settlement or an unassigned amount, rather than a single generic
reference string. See [receivable/payable tracking](https://help.tallysolutions.com/receivables-payables-tracking-methods/).
Cost centres support hierarchy, parallel cost categories and percentage-based allocation
classes; the same expense can be analysed by both department and project. See
[cost-centre allocation](https://help.tallysolutions.com/cost-centre-or-profit-centre-tally/).
Foreign-exchange gains/losses can be accounted for through Journal and supported classes;
see [multi-currency accounting](https://help.tallysolutions.com/multi-currency-accounting-made-simple-with-tallyprime/).
Tally's GST reverse-charge workflow also uses statutory Journal adjustments; see
[RCM recording](https://help.tallysolutions.com/india-gst-inward-supply-rcm-tally/).

Illustrative accounting example: accrued rent of INR 10,000 debits Rent Expense and credits
Rent Payable. A subsequent Payment settles that payable; booking the expense again would
duplicate it. This example explains the intended platform behavior, not a Tally UI sequence.

**Platform implications:** retain common account/bill/tax sections and balanced Accounting
posting. Make cash/bank eligibility an explicit supported profile rule, with the same bank
allocation requirements as other money vouchers. An ordinary Journal must not bypass
receivable, tax, period or approval rules. Statutory adjustments follow our separate India
tax contract; selecting a tax ledger alone is insufficient evidence of a valid adjustment.

**Inventory qualification:** the official but legacy
[TDL voucher reference](https://help.tallysolutions.com/article/DeveloperReference/tdlreference/voucher_and_invoice_customisation.htm)
describes inventory allocations in Journal/Payment/Receipt when ledger configuration permits.
That is not proof of current-release compatibility in every configuration. Our initial
ordinary manual Journal profile remains accounts-only; enabling an inventory-capable Journal
would require current-release verification and an explicit platform posting contract.

## 2. Stock Journal

Stock Journal records source and destination inventory legs. It supports a warehouse
transfer or a transformation in which the consumed and produced items differ. Tally documents
one-to-many and many-to-one location transfers and additional-cost tracking; see the
[inventory/manufacturing FAQ](https://help.tallysolutions.com/tally-prime/inventory/inventory-and-manufacturing-faq/).

| Capability | Functional meaning |
|---|---|
| Warehouse transfer | Decrease quantity at the source and increase it at the destination |
| Consumption/production | Record component issues and resulting finished items with quantities and values |
| Manufacturing mode | Use a product's selected BOM to populate expected component requirements |
| Multiple BOMs | Choose an applicable component recipe for the same product |
| Multiple outputs | Record main output, co-products, by-products and scrap with cost distribution |
| Additional costs | Allocate production-related costs into output valuation |
| Loss/damage | Record an outward-only damaged-stock adjustment where appropriate |
| Batch/unit context | Retain applicable batch, location and unit details; review stock availability |

Manufacturing is a Stock Journal mode, not another independent voucher base kind. Tally's
guide also describes optional manufacturing requisitions and a damaged-stock entry with
no destination output. See
[manufacturing and stock adjustments](https://help.tallysolutions.com/tally-prime/inventory/manage-inventory-in-manufacturing-tally/).

Tally's job costing links projects/cost centres and locations, with Stock Journal classes
for transfer or consumption and project profitability analysis. See
[job costing](https://help.tallysolutions.com/job-costing-tally/).
Job costing and subcontract job work are related but distinct requirements: a project cost
allocation does not identify legal ownership or custody of a principal's materials. Our
required Material In/Out and job-order workflows remain necessary for subcontracting.

**Platform implications:** separate TRANSFER, CONSUMPTION/PRODUCTION and approved LOSS
profiles rather than interpreting every two-sided entry as a transfer. Preserve source-to-output
links, owner/custodian, lots/serials, stock unit conversions and cost provenance. Transfers
conserve the same item's quantity across locations; transformations reconcile quantities
according to their BOM/yield/loss rules, not by equating unlike units or item quantities.
An outward-only loss requires a supported reason and authorization. Physical Stock remains
the protected count-and-delta workflow, not an interchangeable way to enter a guessed loss.

Do not interpret an additional-cost allocation as proof that an expense, payable or bank
payment was posted. Define whether a cost is already booked and being capitalized or requires
a new authorized financial effect; prevent duplicate expense recognition. Stock values may
affect financial reporting even where no sales/purchase invoice is created. Our Accounting
stock/value recognition policy is an explicit design choice, not a claimed copy of Tally's
internal accounting. Applicable tax/challan requirements follow the India tax plan.

## 3. Bank vouchers and supporting workflows

Bank Payment and Bank Receipt are uses/derived types of Payment and Receipt. Contra handles
transfers among the company's own cash/bank accounts, including deposits and withdrawals.
Journal may also contain bank entries. A transfer changes the affected account balances;
it does not become income or expense merely because funds moved. See
[Contra and Journal entry](https://help.tallysolutions.com/accounting-entry-tally/).

| Capability | What the user can record or do | Official guide |
|---|---|---|
| Payment/Receipt entry modes | Enter several counterpart allocations using a simplified or debit/credit presentation | [Payments and receipts](https://help.tallysolutions.com/knowledgebase/payments-and-receipts-tally/) |
| Bill/advance allocation | Split settlement across bills or retain an on-account amount | [Bill tracking](https://help.tallysolutions.com/receivables-payables-tracking-methods/) |
| Bank allocations | Split transaction modes/amounts and retain instrument number/date and payee/payer bank details; ledger-wise allocations are supported | [Payments and receipts](https://help.tallysolutions.com/knowledgebase/payments-and-receipts-tally/) |
| Bank status | Track allocation status, including on hold, processed and reconciled, and display a consolidated voucher status | [Payments and receipts](https://help.tallysolutions.com/knowledgebase/payments-and-receipts-tally/) |
| Cheque control | Configure cheque ranges and bank print formats; monitor printing/use/cancellation | [Cheque management](https://help.tallysolutions.com/banking-cheque-printing-tally/) |
| Post-dated cheques | Distinguish receipt/issue and cheque dates, manage pending instruments and their later accounting treatment | [Post-dated cheques](https://help.tallysolutions.com/post-dated-cheque-managment-tally/) |
| Cash/bank paperwork | Produce deposit slips and payment advice, with relevant instrument details | [Banking utilities](https://help.tallysolutions.com/banking/) |
| Manual reconciliation | Record bank dates and reconcile/unreconcile book transactions | [Manual reconciliation](https://help.tallysolutions.com/manual-bank-reconciliation/) |
| Statement matching | Use exact/potential matches, one-to-one, one-to-many, many-to-one and partial matches; correct/unlink matches | [Auto reconciliation](https://help.tallysolutions.com/auto-bank-reconciliation/) |
| Opening reconciliation | Set a reconciliation cutoff and bring forward earlier uncleared transactions | [Bank reconciliation setup](https://help.tallysolutions.com/bank-recon-setup/) |
| Statement-created entries | Create single, multiple or consolidated vouchers; the batch workflow produces optional vouchers for review | [Auto-create vouchers](https://help.tallysolutions.com/auto-create-vouchers/) |
| Bank execution | Use supported e-payment or Connected Banking facilities separately from recording the accounting voucher | [Banking utilities](https://help.tallysolutions.com/banking/) |

The simplified entry mode is a presentation choice; our posting remains double-entry.
Likewise, recording a bank reference, printing a cheque, submitting a payment and reconciling
a bank statement are distinct events. The current guides permit altering book entries during
reconciliation; our posted Accounting effects instead use linked authorized corrections.
We adopt the functional need to correct a mismatch, not an in-place mutation of posted money.

Illustrative platform scenarios:

- Pay supplier invoices of INR 6,000 and INR 4,000 using one bank instrument: one INR 10,000
  bank effect, two bill allocations, with any unused advance tracked separately.
- Match an INR 9,990 bank receipt against an INR 10,000 customer collection and a separately
  evidenced INR 10 bank charge. Reconciliation does not silently write off the difference.
- Import an uncleared cheque from before the migration cutoff into opening reconciliation
  evidence. Do not post the opening bank balance a second time.

## 4. Gaps and refinements for our common model

These are design findings, not assertions that the current APIs implement the capabilities.
No per-kind document tables are required. The existing 51-table inventory remains a baseline;
the following normalization candidates are outside that count until scope/ownership is finalized.

| Finding | Proposed shared representation and ownership | Delivery implication |
|---|---|---|
| Cost centres/projects are native accounting dimensions | Consider `voucher_dimension_allocation`, referencing the relevant account allocation; Accounting owns dimension definitions and posted journal allocations, with read-only Vouchers snapshots | Resolve in V0; ordinary cost allocation fits V2, manufacturing/project costing V8; no payroll |
| One header party is insufficient for multi-party entry | Bind bill/tender distributions to scoped account/party allocations; allow an optional primary party only for presentation | Review existing Accounting source-document constraints before claiming support for one atomic multi-party payment |
| A tender may serve several counterpart allocations | Make the tender-to-account/bill relationship explicit; consider `voucher_tender_allocation` where many-to-many distribution is needed | V2 schema/cardinality decision; no duplicate cash effect per distribution |
| Bank/instrument state outlives the issued revision | Retain immutable tender input; record instrument/processing/reconciliation events through operations or a shared instrument lifecycle | V2 mode semantics; V7 provider/reconciliation extensions; separate booking, execution and clearing dates |
| Cheque ranges, leaves and cash denominations need native structure if offered | Consider shared `bank_cheque_book`, `bank_cheque_leaf`, and `voucher_cash_denomination`; reuse company bank masters rather than copying them | Optional detailed banking scope, master ownership and numbering/void rules need selection |
| Imported bank entries and opening BRS differ from financial postings | Extend reconciliation batch/line/match structures with source, cutoff, opening-origin and amount allocation | Optional V7; import deduplication, partial matches and audited unlinking; no opening balance posted twice |
| Auto-created vouchers require a review/posting boundary | Retain statement provenance on common drafts and pass the normal approval, tax and Accounting command checks | Optional V7; no blanket auto-post just because a row is imported |
| Additional inventory costs can duplicate expense recognition | Reuse charge/allocation and process details with source cost references; Accounting controls capitalization/variance | V4/V8 valuation contract, including an explicit unsupported-case rejection |
| Cash/bank Journal support differs from accounts-only stock policy | Correct the non-cash description; declare supported Journal profiles and required bank details | V2; inventory-capable Journal remains a separately verified profile, not automatic parity |

Dimension allocations must partition the source amount within each required category.
Parallel department/project analyses are not summed into a second expense. These are native
facts, not descriptive custom attributes; typed header/item customization remains unchanged.
For company bank/cheque master ownership, check Identity's existing bank capabilities and
Accounting's account references before selecting an owner; no duplicate editable master.

Accounting's existing [source document model](../apis/accounting/src/accounting/models/subledger.py)
has one party/account and a unique journal reference. Its general journal lines can identify
parties, but this does not establish atomic multi-party document/settlement support. V0 must
design that command and source-evidence mapping; do not split a promised atomic voucher into
independent postings without changing the contract explicitly.

## 5. Functional acceptance examples

Before advertising the selected capabilities, verify these against our implemented contracts:

1. A compound Journal balances, retains bill/cost allocation, and rejects forbidden inventory
   or unsupported tax adjustments. A permitted bank Journal requires bank allocation details.
2. Parallel project/department allocation preserves one financial expense; each required
   allocation category reconciles independently to the original amount.
3. A transfer moves the same item between locations once, including several source/destination
   allocations; a replay changes neither quantity nor value again.
4. A manufacturing entry pins the selected BOM/version, records consumption and several
   outputs, and reconciles additional cost, scrap and loss according to the selected policy.
5. An outward-only loss requires approval; a cost already booked is not booked again when
   allocated into output value. Job-work goods retain their owner through these operations.
6. Split payment instruments and multiple bills retain distinct references and remaining
   amounts. A failed/pending instrument follows its explicit recognition policy rather than
   being marked cleared by the overall voucher status.
7. Post-dated instruments retain their dates, evidence and cancellation history; any later
   financial posting rechecks period/approval guards. Printing alone changes no balance.
8. Reconciliation supports partial and grouped matches, duplicate imports, opening uncleared
   entries and audited unmatching. Differences require their own authorized financial action.

These are proposed future acceptance cases, not tests run in Tally or the current services.

## Decision log

- 2026-10-10: Linked the follow-up settlement review requested by the user; Payment/Receipt
  purposes and bill/advance histories are shared capabilities, not additional base kinds.
- 2026-10-10: User requested feature-level review of Tally accounting journals, stock journals
  and bank vouchers. Recorded official capabilities and release qualifications, corrected the
  Journal non-cash assumption, and identified shared dimension, instrument and reconciliation
  design gaps. Preserved common voucher tables, Accounting authority, India tax controls and
  payroll exclusion. No application implementation or full banking/feature parity is claimed.
