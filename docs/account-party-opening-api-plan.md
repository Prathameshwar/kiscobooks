# Account and party opening balances: API plan

Date: 2026-10-28. Implementation authorized by the subsequent request to proceed.
The three explicit financial policies were confirmed during implementation:
unknown-date on-account items, both reporting modes, and zero-reconciled clearing. See [delivery status](account-party-opening-api-delivery.md)
and [API behavior](account-party-opening-api.md). UI and installation activation
are deferred. Extend the existing Accounting opening and journal owners;
do not introduce editable balances on account/party masters or another posting engine.

## Research and existing foundations

Official concepts consulted:

- [TallyPrime ledgers](https://help.tallysolutions.com/ledgers-and-groups-in-tallyprime/):
  ledger classification and opening at books begin.
- [TallyPrime party setup](https://help.tallysolutions.com/set-up-party-ledger/):
  optional bill-wise maintenance and credit terms.
- [QuickBooks Online outstanding balances](https://quickbooks.intuit.com/learn-support/en-us/help-article/customer-statements/enter-outstanding-balances-customers-vendors/L90uWlIBd_US_en_US):
  recommends individual unpaid customer invoices/vendor bills over a generic opening;
  preserve their original document dates and omit previously settled documents.
- [QuickBooks Desktop account openings](https://quickbooks.intuit.com/learn-support/en-us/help-article/product-setup/enter-opening-balances-accounts-quickbooks-desktop/L4PfiNhRx_US_en_US):
  select a starting balance/date and prevent overlap with imported historical activity.
  Desktop and Online are distinct references, not one universal product contract.

Recommended adaptation: ledger-wise capture and bill-wise clarity, with company-wide
balanced, auditable financial effects. Historical outstanding documents become native
opening open items; they do not generate new commercial invoices, revenue, purchases,
tax or stock. Master creation and opening preparation/posting have distinct receipts.

Source inspection found:

- `schemas/subledger.py`: `OpeningCreate` already accepts a posting date, up to
  200 journal lines and 1,000 bill allocations. `OpeningBill` has line sequence,
  reference, amount, document date and due date.
- `tasks/openings.py`: enforces books-begin date, balanced journal validation, exact
  bill-to-party-line totals, duplicate bill checks and a single active opening batch.
- `api/subledger.py`: existing preview/create/read/void/finalize-zero opening routes,
  narrow first-time zero review/confirmation and ordinary subledger APIs.
- `tasks/subledger_posting.py`: posting creates dated open items, preserves customer
  versus supplier role and debt versus credit direction, and finalizes the batch.
  Ordinary posting requires a finalized financial opening. Corrections already have
  trading/period/dependency fences.
- `models/subledger.py`: opening batches, open items and allocation lineage already
  exist. One batch currently links one journal; bill base values are allocated from
  that journal line rather than captured independently for each historical bill.
- Existing financial-year/report contracts require once-only migration openings,
  honest mid-year history coverage and continuous annual carry without new postings.
- Bank reconciliation already has opening-item APIs; stock has its own opening
  coordinator and inventory-to-GL coverage. Reuse both boundaries.

These describe the inspected foundations before implementation. The completed
delivery and verification are recorded in account-party-opening-api-delivery.md.

## Proposed date and accounting rules

1. **Opening date:** company `books_begin_date`, shared by the initial financial
   cutover. It is not the account/party creation date or a free per-ledger posting
   date. Opening effect precedes ordinary activity on that business date.
2. **Coverage:** normally represents the previous day's closing balances. Store the
   covered-through date, source system/migration identity and originating fiscal
   year explicitly. Same-day historical documents currently pass the native API;
   retain compatibility initially, but require explicit coverage/overlap review.
   Phase 1 must settle any stricter same-day policy before changing validation.
3. **Historical bill date:** preserve the actual old document date; it may precede
   books begin, but cannot follow the supported cutover. Never substitute account
   creation date or today's date. Known documents require actual dates. The subsequently approved explicit
   ON_ACCOUNT alternative preserves unknown dates without fabricating invoice history.
4. **Due date:** can precede the opening date (already overdue) or follow it; cannot
   precede the document date under the current contract. Preserve supplied dates;
   any terms-derived date must be explicit in preview and frozen at commit.
5. **As-of date:** a read/report filter, separate from opening and bill dates.
   Outstanding balance and ageing use dated settlements, including cross-year
   allocations; future payments must not reduce an earlier as-of balance.
6. **New accounts after cutover:** normally start at zero; later receipts, liabilities,
   transfers and corrections use normal dated transactions. Master creation does
   not silently backdate a new opening or alter the company cutover.
7. **Next year:** carry existing facts and unsettled bills. Do not reset books begin,
   copy bills with new dates or post the prior closing balance again.
8. **Amounts:** positive exact decimal text plus explicit debit/credit or document
   direction, currency and base carrying value. No float, implicit zero, automatic
   present-day exchange rate, cross-role/currency netting or silent balancing plug.

Example: opening on 2026-04-01, customer invoice dated 2026-02-10, due 2026-03-12,
original amount 100,000, paid before cutover 40,000: import only the remaining
60,000 at cutover. Age from the historical dates. A payment posted on 2026-04-05
changes balances from that date; it does not rewrite the 2026-04-01 opening.

## Delivery phases and exit criteria

- [x] **1. Contract and policy audit.** Verify existing account kinds, party-role
  accounts, bill-wise policies, currencies, field permissions, opening/period gates,
  posting/adoption/reversal paths, import mechanisms and report classifications.
  Define typed readiness, capabilities, capture metadata, coverage modes and error
  codes. Decide same-day legacy document treatment, explicit on-account handling,
  mid-year YTD behavior and large-batch clearing policy. Exit: agreed contracts,
  compatibility matrix, acceptance fixtures and no unresolved financial policy
  being silently implemented.

- [x] **2. Durable company opening worksheet.** Extend/reuse the existing opening
  batch as the financial coordinator, with stable line/document keys, immutable
  revisions, expected versions, review hashes and resumable progress. Separate
  mutable preparation from native posted facts. Add bounded, paged account/party
  allocation reads and read-only readiness/preview. Preserve old API callers and
  existing finalized/zero/reversed batches. Exit: independent account entries join
  one company declaration; refresh/retry cannot create a second opening cycle.

- [x] **3. Party outstanding documents.** Add typed opening invoices/bills, credit
  notes, customer advances, supplier advances and unapplied credits, mapped to the
  correct existing party-role accounts and debt/credit directions. Preserve stable
  external identity, original date, due date, reference, outstanding transaction
  amount and base carrying value. For partially settled documents, distinguish
  original face amount from the imported remaining balance. Support separate
  historical carrying values per bill where FX rates differ; do not silently
  prorate all bills at one current rate. Bill-wise totals must reconcile to the
  corresponding control balance. Summary-only capture, if approved, creates an
  explicitly identified on-account item with disclosed unknown invoice detail,
  not invented bills or dates. Exit: ageing, outstanding selection and subsequent
  settlement work for customer/supplier roles, credits, advances and currencies
  without reposting old sales, purchase, tax or inventory effects.

- [x] **4. General accounts and opening bridges.** Cover cash, bank/overdraft,
  assets, accumulated depreciation, loans, liabilities, equity and tax-control
  accounts, respecting supported classifications and currency rules. Validate
  exceptional sides such as credit cash through explicit policy rather than
  assuming every balance has its normal side. Reconcile party-control accounts to
  Phase 3 and inventory GL to the stock opening's COMBINED/LINKED_GL treatment so
  neither posts twice. Reuse bank opening-reconciliation items for outstanding
  cheques/deposits without reposting cash. Fixed-asset or statutory subregister
  completeness is not inferred from a GL balance. Exit: no double-counted AR/AP,
  inventory, bank items, tax obligations or retained earnings.

- [x] **5. Native posting, completion and recovery.** Read-only preview validates
  the complete declaration, total debit=credit in base currency, native references,
  dates, rates, permissions, period locks and existing activity. Posting uses native
  journal commands with idempotency, company locks, audit/outbox and separate
  posting authority; saving a worksheet posts nothing. Preserve explicit narrow
  zero confirmation. If more than 200 lines are supported, add a bounded child-
  journal execution plan under one opening batch: each chunk must balance. The
  recommended option is an explicitly configured migration clearing account whose
  final net balance must be zero, subject to Phase 1 agreement. Never finalize the
  company after only the first chunk. Partial success retains receipts/effects and
  blocks ordinary posting until recovery/reconciliation completes. Exit: lost
  responses, simultaneous submits, failures and cancellation never duplicate money
  or claim already-posted effects were rolled back.

- [x] **6. Reconciliation, dates and statement coverage.** Expose declared/applied
  account balances, party debt/credit totals by role/currency, base-value bridges,
  bill coverage, bank reconciliation and inventory-opening coverage. Extend native
  source/report contracts to distinguish a start-of-year migration from a mid-year
  one. A YTD-summary mode requires typed provenance and separately disclosed
  imported nominal activity; a post-cutover-only view cannot claim a complete
  fiscal-year P&L. Exclude opening effects from ordinary turnover and never add
  imported earnings twice. Exit: TB, Balance Sheet, ledger, ageing and subsequent-
  year carry reconcile at one source snapshot with honest historical coverage.

- [x] **7. Bulk import, evidence and correction.** Add versioned JSON/CSV/TSV/XLSX
  templates with explicit bounds, dry-run validation, row issues, duplicate-source
  detection, reviewed commit, durable job history, resume and private exports.
  Reference resolution uses authorized native IDs or uniquely resolved company
  codes; ambiguous names never select an account or create a master silently.
  Keep immutable revision/posting/settlement lineage. Allow replacing unposted
  preparation; posted corrections follow native reversal/replacement and existing
  trading, settlement, period and stock-claim fences. Unsupported legacy adoption
  or restatement returns a specific blocker. Exit: cancel/retry preserves posted
  receipts, audit evidence and closed-period protections.

- [x] **8. Synchronization, native verification and two reviews.** Add required
  one-DDL-per-migration changes with matching models, schemas, factories, indexes,
  permission catalogue/system roles/seeds, event contracts, OpenAPI and TS clients.
  Verify upgrade/existing-company compatibility and MySQL-native concurrent flows.
  Cover positive and opposite-side balances, missing values, mixed roles/currencies,
  different bill FX carrying values, partial settlements, overdue/future due dates,
  same-day coverage, closed periods, mid-year/YTD, annual carry, import interruption,
  field denies/exports, cross-company references and stock/bank bridges. Run two
  reviews (correctness/security/recovery, then complete workflows/compatibility),
  fix findings after each and rerun affected checks. Exit: precise evidence and
  activation limits recorded; UI remains deferred.

## API surface to refine in Phase 1

Retain company scope under `/v1/companies/{company_id}` and extend the existing
`/opening-batches` family. Proposed additions cover readiness/capabilities, typed
worksheet revisions, validation/preview, execution progress, reconciliation,
account/party opening reads and migration import jobs. Names and schemas are not
final until compatibility review; preserve native journal lifecycle, `/open-items`,
allocations, ageing, zero confirmation and bank opening-item owners.

Reads expose server-evaluated actions and field sets for a later UI. Growing lists
use typed filters and signed keyset cursors; sensitive exports recheck current
authority and require expiring tickets. Money writes require idempotency keys;
state/version/hash conflicts are distinguishable from configuration, permission,
date, reconciliation and service-availability failures. No balance-overwrite route.

## Proposed decisions and boundaries

2026-10-28: recommend one books-begin cutover, bill-level party evidence, preserved
historical dates and base carrying values, balanced native effects, explicit zero,
and continuous yearly carry. These adapt the researched workflows to the repository's
existing financial invariants. Summary-only on-account behavior, same-day coverage,
mid-year reporting modes and temporary clearing for large execution are explicit
Phase 1 decisions. The subsequent implementation request authorizes the work;
the subsequent explicit answers authorize unknown-history on-account balances,
both reporting modes, and configured clearing with mandatory zero reconciliation.

UI, annual profit-transfer automation, statutory tax migration interpretations,
new asset-register engines and release activation are not implicitly authorized.
Tax/advance provenance gaps must fail closed or remain capability-gated until the
existing legal/accounting policy is resolved; do not invent a tax effect.
