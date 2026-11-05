# Account entries, registers, ledgers and maintained balances

**Date:** 2026-10-10. **Status:** Required design, with ordinary-money implementation.
The ordinary-money recording/reporting slice is implemented in
[Phase 2](voucher-phase2-execution.md), with completed verification and explicit coverage limits.
Later invoice, tax, stock and WIP extensions below retain their batch gates.
This specifies how account activity is captured, read and maintained, extending D01/D04/D07/
D11/D12 and AC26 without adding another service, ledger authority or parent batch.

Read with [posting/reporting](voucher-posting-reporting-design.md), [financial years](voucher-financial-year-design.md),
[shared tables](voucher-table-inventory.md), [finance contract](accounting-finance-contract.md),
[implementation](voucher-implementation-plan.md), [tracker](voucher-delivery-tracker.md) and
[todo](voucher-implementation-todo.md). Payroll remains excluded.

The [stock capture/storage contract](voucher-stock-recording-reporting-design.md#32-storage-grain-relationships-and-constraints)
specifies immutable value legs and quantity/unit/origin/source allocations behind stock/WIP
control balances. Reuse the report generation mechanism here, while Accounting operational
stock repair additionally fences live writers. STK checks extend the corresponding BAL bridges.

## 1. Review findings and existing capability

TallyPrime provides period-based ledger vouchers, running balances and bill-wise drill-down,
cash/bank daily and monthly views, and transaction registers. These are useful functional
references; they do not specify our storage design or override our append-only posting rules.
[Ledger vouchers](https://help.tallysolutions.com/ledger-vouchers/),
[cash/bank books](https://help.tallysolutions.com/tally-prime/accounting-financial-reports/cash-bank-book-tally/),
[account books and registers](https://help.tallysolutions.com/tally-prime/accounting-financial-reports/accounting-financial-reports-tally/).

| Inspected source | Current evidence | Required extension |
|---|---|---|
| [Ledger models](../apis/accounting/src/accounting/models/ledger.py) | Company-scoped journals and sequenced account lines; original/base money, party/role, fiscal period and reversal/source references | Preserve this canonical GL; add native source-distribution/dimension/commit evidence where the voucher/report contracts require it |
| [Ledger reads](../apis/accounting/src/accounting/tasks/ledger_reads.py), [schemas](../apis/accounting/src/accounting/schemas/ledger.py) | POSTED-only sums through an as-of date, optional account/party and BASE/ORIGINAL currency selection; protected aggregate inputs | Current debit/credit values are cumulative through that date, not period turnover. No role filter, opening/window/running balance or frozen-source token is provided |
| [Ledger API](../apis/accounting/src/accounting/api/ledger.py) | Journal/line lists and exports plus `/ledger/balance` | Generic export pages are not yet a complete snapshot/catch-up feed or an account ledger with stable running pagination |
| [Posting owner](../apis/accounting/src/accounting/tasks/journal_posting.py) | Company lock, fiscal/current-authority checks, atomic posted journal, subledger hooks and financial outbox | Extend complete effects and source lineage in the owner transaction; preserve every existing writer/recovery path |
| [Subledger reads](../apis/accounting/src/accounting/tasks/subledger_reads.py), [reconciliation](../apis/accounting/src/accounting/tasks/reconciliation.py) | Dated item/allocation balances, overdue buckets and party-control checks in base/original currency | Versioned reversal/lifecycle evidence, stable report snapshots, role-aware multi-account party statements and complete export coverage |
| [Financial event v1](../apis/accounting/src/accounting/events/financial_contract.py) | Journal-posted and period-changed payloads | PostedLine does not carry line sequence/narration; no complete allocation, source-distribution, classification or producer snapshot stream. Add compatible versions/exports; never infer missing fields |

RF33-RF40 track the capture/maintenance gaps. Existing balance-query behavior remains a
compatibility contract, not an implementation of all planned views. No installed company
balances or production data were examined.

## 2. One set of books, several views

| Concept | Source and grain | Maintenance rule |
|---|---|---|
| Account master | Accounting account identity, group/head, kind, currency and policy | Holds definitions, not an editable opening/current balance |
| General ledger entry | One committed `journal_line` in its posted journal | Append-only financial fact; no extra posting into a separate account-ledger table |
| Account ledger | Authorized lines for one account at dates/source snapshot | Opening, debit/credit movement and running/closing balances derived from GL |
| Account/group balances | Sum of relevant leaf-account GL facts | Derived, currency/scoping/date-aware; groups never receive separate postings |
| Party/bill/advance subledger | Open items plus dated allocations/reversals | Gross debt and unapplied credit are distinct; reconcile signed net to GL |
| Voucher register/day book | Document revision/execution or journal, with explicit row grain | Operational state and actual effect state remain separate; not another financial write |
| Cash/bank book | Actual GL lines on selected cash/bank accounts | Include every posting kind that affects the account; payment mode text alone is insufficient |
| Tax register | Native tax event/components/credit/settlement facts | Explain timing/eligibility differences to GL; not reconstructed solely from tax-account net |

An account ID identifies the ledger; it does not need a physical table per account, group,
voucher type or year. Shared report projections may repeat immutable source facts for reads,
but cannot accept independent monetary edits. Account names, custom fields or report layouts
cannot decide posting side, eligibility or classification. Renaming/deactivating an account
does not remove its history. Pin hierarchy/classification revisions for reproducible grouping.

## 3. Facts captured when a voucher posts

For each accepted effect bundle retain:

- Tenant/company; source service/type/ID; voucher ID and exact revision/hash; operation and
  effect IDs; authorized actor/approval evidence; journal ID and internal/statutory references.
- Document and posting dates, actual fiscal period, committed visibility/order evidence,
  narration and source reference. Stock and legal tax dates remain separately associated.
- Per journal line: stable ID, sequence, account, side, original currency/amount, recorded
  FX rate, base currency/amount, component, party/role when required and line description.
- Native amount-level source distributions connecting item/account/charge/discount/tax/
  rounding/tender/settlement input to its output lines. A voucher line can yield many entries;
  a consolidated entry can have many contributing lines. Distribution totals reconcile to
  their named output component; custom attributes are not a substitute for these fields.
- Native department/cost-centre/project or other dimensions only for the selected supported
  scope. Allocations partition a line within each dimension category; parallel categories
  must never be summed together. Missing supported dimensions use explicit unassigned scope.
- Open-item identity/direction, bill/advance reference, document/due dates, installments and
  party-role-account-currency; allocation and unallocation dates/amounts, including separate
  debt/credit base carrying amounts and linked realized-FX journals when applicable.
- Source links for original/reversal/replacement, opening provenance, associated bank
  instrument/tender and applicable tax/stock facts, plus transactional outbox/audit evidence.

Create the journal, required related facts, source receipt and outbox atomically in Accounting.
Reports failure cannot roll back or hide a committed owner posting. Document completion waits
for a durable owner result; an acknowledgement delay never authorizes another post. Source
identity must prevent duplication even with a different HTTP idempotency key or event ID.

Amounts use Decimal with the existing storage/rounding contract. Journal header debit/credit
must equal the sums of actual lines and each other; header equality alone is insufficient.
Base-only FX lines can have zero original amount under the existing special contract and
must not disappear. Drafts, previews, rejected commands, orders and scenarios add no actual GL.
Allocation-only adjustment adds settlement history without inventing a cash or journal effect.

Party-control entries must create or link reconciled subledger facts, or an explicitly
supported base-only FX effect. A manual Journal cannot bypass party/source-only restrictions
and leave an unexplained GL balance with no corresponding bill/advance detail.

## 4. Balance definitions and running ledgers

At a complete source snapshot W and for the same account/currency/scope:

```text
opening(S, W) = sum(posted debit - credit where posting_date < S, visible at W)
period_debit(S, E, W) = sum(posted debits dated S through E, visible at W)
period_credit(S, E, W) = sum(posted credits dated S through E, visible at W)
closing(E, W) = opening + period_debit - period_credit
running(i) = opening + sum(debit - credit through ordered row i)
closing_debit = max(closing, 0); closing_credit = max(-closing, 0)
```

Keep both gross debit and gross credit even when the same account appears on both sides of
one journal. An optional voucher-grouped ledger row may combine its lines for presentation,
but retains both sides, count and drill-down; it must not turn gross turnover into net change.

Use the contracted deterministic order `(posting_date, owner_commit_order, journal_id,
line_sequence, line_id)` at W. This is an accounting display order, not an assertion about
the time a physical payment happened. Cursor/run identity binds filters, dates, order,
currency, generation and permission scope; carry the prefix balance across pages without
trusting a client-supplied amount. An arbitrary sort cannot display a chronological running
balance without an explicit different meaning. Starting a fresh run may change row positions.

Distinguish these response measures:

| Measure | Meaning |
|---|---|
| As-of book balance | Posted activity through the explicit business date and source snapshot |
| Current balance | As-of the company's current business date/timezone; excludes later-dated postings |
| All-posted balance | Includes authorized future-dated postings only when explicitly requested and labelled |
| Available credit / spendable bank balance | Separate owner policy or bank evidence; cannot be equated with GL net balance |
| Outstanding bills | Debt and unapplied credits at the allocation-date cutoff; not just the party account net |
| Period turnover | Gross debits/credits inside the requested window, not the current API's cumulative totals |

A movement filter (voucher type, narration, debit-only, reference search) returns filtered
movement totals. It must either omit the full-ledger running balance or explicitly show the
full-ledger balance-at-row and separate filtered totals. Never take a full opening and only
some movements and label the result the account closing balance. Authorization filters are
not optional: full totals require access to all their inputs; denied balances cannot leak
through visible rows, cursors, counterpart detail or subtraction.

Daily/monthly summaries provide opening, gross turnover and closing, including a zero-movement
period with unchanged carry. Turnover adds across periods; closing balances do not. Group
debit/credit sums retain each leaf account's balance side and count each leaf once. A group
with debit 100 and credit 70 may show net debit 30, but its gross balance-side columns remain
100 and 70. Customer/supplier roles cannot be silently netted across accounts.

Daily negative-cash exceptions use actual CASH account balances, not all credit bank balances;
an authorized bank overdraft is a different account/policy. If intraday extrema are displayed,
label the deterministic ledger order used; it cannot establish physical cash timing from
date-only evidence. These diagnostics do not select a new posting prohibition or overdraft limit.

Original-currency balances partition by currency; base totals use stored base amounts, not
today's FX rate. Exact wider intermediate accumulators and bounded response/aggregate values
must avoid overflow or float conversion when many valid individual postings are summed.
Any new wider persisted summary type needs an explicit repository-contract decision under
D07; never silently widen/narrow journal money or truncate a cumulative total.

## 5. Shared records and summary storage

Physical names below are candidates under D07. Reuse existing reporting infrastructure and
owner facts; these are outside the 51 numbered Vouchers candidates.

| Record / owner | Grain and retained content | Required or conditional |
|---|---|---|
| Existing `journal` / `journal_line`, Accounting | Canonical committed entries and native scope/source references | Required; no replacement GL |
| Existing `source_document`, `open_item`, `allocation`, opening and tax records, Accounting | Source effects and subledger evidence; compatible lifecycle history extension as required | Reuse/extend |
| `journal_line_source_allocation` or shared effect distribution, Accounting | Exact source revision/line/component to output line, amounts and rule version | Required lineage capability; reuse the common native distribution design |
| `report_ledger_fact`, Reports | Unique `(tenant, company, generation, owner, journal_line_id)` plus source hash, order, dates, currency/side/amounts and authorized source references | Required line-grain read capability; may share the existing planned owner-fact projection |
| `report_account_day_total`, Reports | `(tenant, company, generation, account, posting_date, basis, currency)`; gross debit, gross credit, line count, source coverage | Conditional accelerator; start with account-wide grain and use facts for other filters |
| Existing candidate `report_account_period_total`, Reports | Same scope plus actual fiscal period; derived daily/line totals | Optional monthly accelerator; never added to daily totals for the same coverage |
| `report_projection_generation`, Reports, or extended `report_checkpoint` | Definition/schema version, owner manifests, verified checkpoints, BUILDING/READY/ACTIVE/FAILED state, cutover/reconciliation evidence | Required generation/control capability; no duplicate checkpoint engine |
| Existing candidates `report_run`, `report_artifact`, `report_reconciliation` | Fixed scope/snapshot/output, protected artifact and discrepancies with source IDs | Reuse; retain frozen versions |

Native unique constraints and scoped keys enforce the declared grain. Optional dimension,
party or registration summaries need their own approved grain/index/security contract before
use; do not create every Cartesian combination or mix an ALL bucket with its component rows.
Keep owner-issued immutable IDs as joins, not voucher numbers or mutable account labels.

Do not persist a mutable running balance on every journal line. Daily aggregates store
movements, with closing derived from prefix totals; a backdated posting changes the affected
day and later prefixes, not the immutable entries. Any carry/prefix cache records its covered
interval and source watermark. Readers select exactly one nonoverlapping coverage path.

Current Accounting direct sums remain the correctness baseline. An Accounting-owned balance
accelerator is optional only after a demonstrated need and D07/D11 review; if used for posting
or credit checks, every contributing owner write must maintain it under the same transaction/
locks and fail closed on stale coverage. Reports projections can never authorize spending,
credit, allocations or financial posting. There is no user-facing set-balance endpoint.

## 6. Projection maintenance, late entries and recovery

1. Obtain an owner-consistent snapshot and a catch-up boundary under D01/D11. Generic list
   exports, maximum UUID/timestamp or a merely allocated sequence do not prove completeness.
2. Build a new generation from full authoritative exports, verifying counts, journal-line
   sums, source hashes and company/currency control totals. Never copy unexplained old totals.
3. Apply each complete owner effect bundle in one Reports transaction: dedupe receipt,
   immutable facts, selected daily/period deltas and checkpoint advancement succeed together.
   A changed message ID carrying an existing effect must not add its amount again. Same source
   identity with a different immutable monetary payload is quarantined, never an overwrite.
4. Version nonmonetary lifecycle/classification and allocation reversal facts without losing
   what an earlier snapshot knew. Existing mutable reversal fields need sufficient versioned
   owner exports/history for frozen as-known runs; current rows alone cannot reconstruct them.
5. A late posting uses its original approved posting date. Update its day's movement and
   invalidate affected later prefix/carry caches; do not subtract a reversal from the original
   date. Allocation-only events refresh outstanding/aging views without changing GL totals.
6. Reconcile the complete shadow generation with owner totals at the same boundary, then
   switch the active pointer atomically after catch-up. Existing readers pin their generation;
   a run cannot mix pages or totals from old and new builds. Retain required frozen source/
   artifact evidence before retiring old projections under the retention policy.
7. Recovery resumes durable checkpoints and resolves owner receipts. Missing/incompatible
   bundles, stale required streams or reconciliation differences block COMPLETE status; show
   lag/affected scope explicitly. Catch-up after an outage must not depend on broker retention.

Keep query execution bounded and indexed by company/account/date/order and selected basis.
Measure large-account pagination, daily aggregation and rebuild throughput in B45, with target
volumes/latency fixed in B01/B03. Do not preselect an unmeasured performance promise. Add
monitoring for last verified source boundary, oldest pending effect, conflicting duplicates,
reconciliation difference, generation lag and failed rebuild/recovery.

## 7. Registers and APIs without double counting

| Required view | Row grain and reconciliation |
|---|---|
| Account ledger / daily-monthly account summary | Journal line, optional explicitly grouped voucher row; all totals reconcile to the selected account GL |
| Group ledger/summary and TB | Authorized descendant leaf accounts/lines once; retain gross sides, hierarchy version and opening/movement/closing |
| Day book and Journal/Contra/Payment/Receipt registers | Declared document execution/journal grain; internal transfers are not sales/expenses and aggregate cash+bank net may be zero |
| Sales/Purchase/Credit Note/Debit Note registers | One declared document revision/execution with child detail; commercial net, charges, discounts, taxes, gross and settlement are distinct measures |
| Cash/bank books | All actual cash/bank GL movements; daily/monthly/period detail, selected instrument references and negative cash exceptions |
| Party statement / bill adjustment / advance registers | Account-role-currency items and allocation history, gross outstanding/unapplied credit, due-date aging and GL bridge |
| Tax/withholding registers | Native event/component and settlement grain, registration/date basis and tax-to-GL differences |
| Reversal/opening/numbering/reconciliation registers | Original and correction provenance, once-only imports, issued/void number and mismatch evidence |

Invoice registers must aggregate each child relation to its intended parent grain before
joining. Joining two item rows, two tax components and two bill schedules directly produces
eight combinations: it cannot multiply a single 1,180 invoice into an apparent 9,440 sale.
Likewise, invoice totals repeated beside each allocation or bank instrument are not additive.
Subtotals identify which columns are additive; drill-down changes grain explicitly. Tally's
columnar sales-register functionality motivates the view, not a separate posting table.
[Sales register](https://help.tallysolutions.com/how-to-work-with-sales-register-in-tallyprime/).

Posted documents plus their linked reversals remain visible; cancelled-before-posting entries
can appear in an operational register with zero financial effect. When grouping Vouchers and
legacy Accounting sources, use source identity/receipt mappings so the document and its journal
do not become two sales. A standalone Accounting journal remains visible without a Vouchers row.

Extend existing company-scoped Accounting reads additively for authoritative period balance
preview/control exports where needed. Keep `/ledger/balance` cumulative debit/credit semantics.
Use the planned Reports catalogue/run/status/rows/drill-down/export API for ACCOUNT_LEDGER,
ACCOUNT_SUMMARY, GROUP_LEDGER, DAY_BOOK and existing statement/register kinds. Return requested
dates, currency basis, source/generation/run token, history coverage, gross totals, balance side,
scope/completeness and freshness. UI/posting previews may display owner balances; report lag
is explicit, with wait/retry for a requested owner receipt rather than guessed immediate freshness.

Recheck company/field/row permission on totals, counterpart details, filters, cursor use and
downloads. Restrict reference/narration access and protected bank data. Custom attributes may
filter/display permitted rows, but cannot supply financial amounts or bypass native controls.

## 8. Reconciliation and financial-year continuity

At the same business date and source coverage: source journals balance; line sums equal
headers; facts equal owner exports; day totals equal line facts; period totals equal their
days; ledger closing equals opening plus movement; TB leaf totals reconcile; P&L/Balance
Sheet bridges follow the existing reporting contract. Compare both base and relevant original
currency balances, including zero-original/base-only FX entries.

Customer debt minus unapplied credit matches the signed receivable account; supplier debt
has the opposite GL sign. Reconcile per account/party/role/currency before authorized grouping.
Bank book versus bank statement/clearance, tax events versus filed returns, and owned stock/
WIP versus control accounts retain explained timing and recognition bridges. A mismatch must
not be repaired by editing a report total or inserting an automatic suspense journal.

FY opening is prior closing at the same snapshot. Keep original bill/advance due dates and
stock/job references; no annual balance copy. New-year P&L and unclosed-earnings presentation
remain separate from raw GL carry. Authorized prior-year adjustments invalidate later derived
balances for new runs; frozen outputs remain unchanged. Ordinary next-year readiness does not
require deferred annual profit-transfer automation. Apply D12 and the FY acceptance matrix.

## 9. Batch scope and required acceptance

Retain 45 parents, 38 packages, twelve decision gates and existing B14a-d/B27a-e. D11 now
explicitly includes fact/summary grains, generation lifecycle, additive balance-read contract
and register aggregation; D07 defines exact reusable schema, D04 subledger semantics and
D12 cross-year behavior. No business costing/tax/dimension policy is silently selected.

| Batch | Additional scope |
|---|---|
| B01-B03 | Record current balance semantics/feed gaps; define native source distributions, row grains, source order, snapshot/generation and sizing contracts |
| B07/B10 | Complete source-linked owner posting and authoritative balance reads; preserve atomicity and legacy writers |
| B09 | Complete financial/subledger feeds, line facts, selected day/period summaries, atomic checkpoints, rebuild generations and reconciliation |
| B11-B13 | Dated item/allocation/instrument evidence; no GL delta for pure bill adjustment |
| B14a | Account/group ledgers, daily/monthly summaries, running pagination, register grains and TB controls |
| B14b/c/d | Statement/carry compatibility, party/advance/aging and cash/bank/detail/reconciliation extensions |
| B18/B27/B40 | Invoice/tax, stock/value and WIP source bridges with fanout-safe registers |
| B45 | Backfill/rebuild equivalence, projection cutover/recovery/load, late entries and permission-safe exports |

The following BAL checks extend AC26 and existing RPT/FY checks. They are future implementation
tests; documentation arithmetic is not evidence that these APIs/projections exist.

| Check | Required assertion | Batch |
|---|---|---|
| BAL01 | Every actual account entry has exact source/line/component/party/currency lineage and reconciled journal totals | B07/B10/B18 |
| BAL02 | Draft/preview/order/scenario/rejected operations have zero actual balance effect; delayed acknowledgement cannot hide a committed journal | B07/B09/B35 |
| BAL03 | Retry, duplicate/new-message-ID delivery and crash produce one immutable fact and one aggregate delta | B09/B45 |
| BAL04 | Opening + gross debit - gross credit equals closing; same-account opposite sides retain both gross movements | B14a |
| BAL05 | Ordered pagination and zero-activity periods retain correct prefixes; arbitrary sorting/filtering cannot mislabel running/closing balances | B14a |
| BAL06 | Company-current and all-posted views distinguish future dates; ledger and statutory dates retain their own meaning | B10/B14a |
| BAL07 | Daily/period/fact totals agree with exact Decimal handling; unsupported cumulative overflow fails explicitly | B09/B14a/B45 |
| BAL08 | Period closing amounts are not summed as turnover; group leaves count once and abnormal debit/credit sides remain visible | B14a |
| BAL09 | Original currencies remain separate; stored base carrying values and base-only FX reconcile | B11/B14d |
| BAL10 | Allocations/unallocations change bill balances by date without duplicate GL; customer/supplier roles and gross credits remain separate | B11/B14d |
| BAL11 | Late entries/reversals invalidate correct day/prefix/carry scope; old frozen generation/run remains reproducible | B09/B14/B45 |
| BAL12 | New generation snapshot plus catch-up has complete bundles; crash/cutover never mixes versions or loses/duplicates a commit | B09/B45 |
| BAL13 | Source identity with conflicting money, missing stream or reconciliation difference blocks COMPLETE and exposes repair evidence | B09/B45 |
| BAL14 | Register child joins do not multiply documents; legacy journal/voucher mappings and installment/tender repeats count once | B14a/B18 |
| BAL15 | Cash/bank includes all relevant account postings, separates book/clearance balances and preserves zero-net Contra turnover | B12/B14d |
| BAL16 | Reparented/renamed/inactive accounts preserve source history and pinned grouping/classification | B09/B14a-c |
| BAL17 | Full/partial totals, counterpart rows, filters, cursor/rebuild/download routes cannot leak denied account/party/company values | All report batches |
| BAL18 | Existing balance endpoint retains cumulative semantics; new period/read tokens and stale-after-post behavior are explicit | B09/B10/B14a |
| BAL19 | FY and migration openings count once; current P&L/prior earnings and older unsettled bills remain correct | B14b-d/B45 |
| BAL20 | Owner, facts, summaries, ledgers, registers and subledgers reconcile after rebuild at supported load; no balance-overwrite repair | B14/B18/B27/B40/B45 |

### Worked recording and maintenance fixture

Illustrative INR base-currency data, without selecting a general statutory rate policy:
opening Bank Dr 10,000 / Capital Cr 10,000; service sale Customer Dr 1,180 / Revenue Cr 1,000 /
Output tax Cr 180; receipt Bank Dr 500 / Customer Cr 500 allocated to that bill; credit note
Revenue Dr 100 / Output tax Dr 18 / Customer Cr 118, also allocated. Add Expense Dr 200 /
Bank Cr 200; supplier bill Expense Dr 500 / Supplier Cr 500; Contra Cash Dr 1,000 / Bank Cr
1,000. A separate arithmetic case Bank Dr 50 / Bank Cr 50 checks preservation of both sides
if that entry profile permits it; it is not evidence of an external collection/payment.

Closing balances: Bank 9,300 Dr, Cash 1,000 Dr, Customer 562 Dr, Expense 700 Dr; Capital
10,000 Cr, Supplier 500 Cr, Revenue 900 Cr, Output tax 162 Cr. TB sides are 11,562. Profit is
200 and assets 10,862 equal liabilities 662 + capital 10,000 + profit 200. Bank opening 10,000
plus period debit 550 minus credit 1,250 equals 9,300; netting same-account entries would hide
50 on each turnover side. Sales gross is 1,180, credit-note gross 118, net commercial gross
1,062 and receipt 500 leaves receivable 562; these distinct measures must not be added together.

With the May run frozen, a June reversal of the 200 expense affects June Bank/Expense only.
A later authorized May Expense Dr 30 / Bank Cr 30 changes a new May run to Bank 9,270,
Expense 730, profit 170 and assets 10,832; the original May artifact remains unchanged.
Rebuilt day/period totals must equal the same source snapshot, including gross turnover.

## Decision log

- 2026-10-10: User requested review of account registers, ledgers and balance capture and
  maintenance. Added exact fact/summary/register grains, current API gaps, source lineage,
  atomic projection updates, generation/rebuild contracts and BAL01-BAL20 under existing
  gates/batches. No new ledger authority, per-account/year tables or editable master balance.
  RF33-RF40 record planning corrections; all implementation tasks remain unverified.

### Stock capture/storage review - 2026-10-10

Recorded stock-value lineage and the stronger guard required to repair operational
stock state; common report generation does not grant stock posting or repair authority.
