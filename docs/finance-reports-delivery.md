# Remaining Finance reports - delivery plan

Authorized 2026-11-03: choose at most two useful views per remaining `/reports/finance`
report, write its phases, implement, review and fix, then continue without an approval
pause. Trial Balance, Profit and Loss and Balance Sheet are already delivered.
Scope follows `reportSectionsFor('finance')`: 19 remaining reports. Tax, inventory
and analytics reports retain their separate workspaces.

## View decisions and report-specific acceptance

| Order | Report | Recommended views | Contract and review focus |
|---:|---|---|---|
| 1 | Income and expenditure | Statement | Income, expenditure, surplus/deficit; imported YTD disclosed; no trading gross profit. |
| 2 | Account ledger | Transactions | Opening, posted debit/credit and running balance; account and currency scope; journal drilldown. |
| 3 | Day book | Posted journal entries | Posting date, voucher number/kind, account and debit/credit; no cross-account running balance. |
| 4 | Party ledger | Transactions | Party/role/account scope, opening and running balances, bills and journal links. |
| 5 | Cash book | Cash transactions | Cash classification; receipts/payments and running balance. |
| 6 | Bank book | Bank transactions | Bank classification; book movement, not bank statement certification. |
| 7 | Account summary | Period movement | Day/month grain selector; opening, debit, credit, net and closing; period drilldown. |
| 8 | Outstanding bills | Bill detail; balances by party | Due dates, original/allocated/remaining, currency basis; debt and credits separate. |
| 9 | Advances | Unapplied credits; balances by party | Remaining credit, not income; account labels and original/remaining values. |
| 10 | Receivables/payables ageing | Ageing matrix | Current/1-30/31-60/61-90/over-90/unknown; debt separate from credits. |
| 11 | Payment register | Payment detail | Tender grain, signed reversals, paying account, mode/reference; no duplicated voucher sums. |
| 12 | Receipt register | Receipt detail | Tender grain, signed reversals, receiving account, mode/reference. |
| 13 | Bank balance agreement | Balance agreement | Required bank and statement balance; difference is diagnostic, not finalisation. |
| 14 | Finalised bank reconciliation | Session evidence | Required session, bank, currency; frozen opening/closing and matched/residual detail. |
| 15 | Unmatched bank transactions | Unmatched worklist | Bank/book side, date, status, amount, matched amount, residual and age. |
| 16 | Sales register | Invoice register | Customer, posting/document dates, original/reduction direction, tax/payable and invoice drilldowns. |
| 17 | Purchase register | Supplier invoice register | Supplier, invoice/date basis, charged tax and supplier difference, reductions. |
| 18 | Invoice component register | Components and allocations | Row type and purpose, component and allocation amounts kept distinct. |
| 19 | Invoice settlement register | Settlement history | Allocation and reversal dates, as-of activity and amount; retained invoice links. |

## Phases applied to each report, in the order above

1. Confirm the row's financial contract against the existing engine/schema and choose
   the columns and primary filters listed above. Preserve exact decimal amounts,
   currencies, source dates and permission checks. Record the selected view in the
   server definition so downloads use the same presentation.
2. Implement the report-specific workspace configuration and route. Reuse the native
   report engine for verified source preparation, typed reference filters, bounded
   paging, saved filters and history. Keep dates/amounts on the completed report
   while replacement work runs. Show compact progress and Stop near the top.
3. Complete the selected report's signed drilldowns, full-result PDF/Excel/CSV exports,
   automatic download and prominent download/preview recovery links. Required bank,
   session or party selectors must be completed before launching dependent work.
4. Run its contract/UI regression cases and relevant engine/export cases. Review empty,
   failure, cancellation, stale result, permission, currency and responsive states;
   fix findings before marking that report complete and proceeding to the next.

Shared lifecycle changes introduced for the first report are regression-tested for
existing book, inventory, tax and analytics consumers. No posting, matching,
reconciliation finalisation or statutory filing is performed by these reports.

## Official product references and decision log

Reviewed 2026-11-03: [Tally ledger vouchers](https://help.tallysolutions.com/ledger-vouchers/)
support transaction detail, running balances and bill drilldowns;
[Tally cash/bank books](https://help.tallysolutions.com/cash-bank-book-tally/)
support period movement;
[Zoho receivables](https://www.zoho.com/en-sg/books/help/reports/receivables.html)
distinguishes ageing summaries and transaction detail;
[QuickBooks reconciliation reports](https://quickbooks.intuit.com/learn-support/en-us/help-article/export-reports/view-print-export-reconciliation-report/L1yNaVaOG_US_en_US)
retain session balances and cleared/uncleared evidence. The choices above are our
implementation decisions using these concepts and the available verified source
contracts; they do not claim product parity.

## Execution ledger

All 19 reports and their 21 selected views have completed the four phases.
INCOME_EXPENSE and ACCOUNT_LEDGER established the shared lifecycle; the remaining
reports followed the ordered implementation and review loop below.

- DAY_BOOK: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- PARTY_LEDGER: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- CASH_BOOK: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- BANK_BOOK: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- ACCOUNT_SUMMARY: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- OUTSTANDING_BILLS: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- ADVANCES: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- AGING: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- PAYMENT_REGISTER: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- RECEIPT_REGISTER: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- BANK_RECONCILIATION: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- BANK_RECONCILIATION_EVIDENCE: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- BANK_RECONCILIATION_WORKLIST: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- SALES_REGISTER: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- PURCHASE_REGISTER: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

## Review findings and fixes

- Income/expenditure help and coverage notes now share a collapsed About row;
  Finance spacing is compact and does not repeat the long explanation in the header.
- Worker/catalog implementation mismatches have a distinct failure code. They no
  longer trigger a futile accounting-source refresh. Source verification failures
  get one automatic preparation/retry within the caller's existing permissions.
  Preparation tries an incremental refresh when a prior source exists, then one
  full rebuild if that refresh fails. Both paths require a verified READY snapshot;
  failed rebuilds stop with an actionable message. Requested dates are preserved.
- Day Book retains a whole-result count and debit/credit summary for export admission;
  it never invents a balance across unrelated accounts.
- Party-balance projections retain readable account codes/names and exact separate
  debt/credit totals. Bill references remain visible by default in the curated views.
- Finalised bank sessions have a scoped period/currency selector. The proxy admits
  bounded GET requests only; report workspaces cannot finalise or match bank records.
- Finance history authorization failures clear displayed financial data.
- The Reports Day Book card opens the Finance workspace; the Books entry retains its
  established route. Account-ledger drilldowns retain the Back to Trial Balance link.
- GSTR-1 and GSTR-3B remain visible when unavailable. A disabled card explains the
  GST setup/access requirement and links directly to the selected company's GST
  settings. Setup links stay on one line inside the card at 320/390/768/1440 px.
  The server's registration eligibility and permission checks remain authoritative.

- INVOICE_COMPONENT_REGISTER: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

- INVOICE_SETTLEMENT_REGISTER: selected view, route, primary filters and full-result export implemented; report-specific engine/contract and UI/export checks passed. Cross-report review and export pipeline checks passed.

## Final verification

- All 19 report pipeline tests passed: admission, worker calculation, all 21 view
  projections, signed drilldowns where present, and full CSV/PDF/XLSX downloads.
- The final backend contract, summary, framework-worker and presentation-capacity
  regression suite passed all 45 tests.
- Console TypeScript validation completed without diagnostics; focused Python Ruff
  and mypy checks passed.
- Browser checks passed for all views at desktop and 390/320 px, in light and dark
  themes, with open and closed filters. GST setup links also passed containment and
  single-line checks at 1440/768/390/320 px.
- Finance lifecycle and contract checks passed, including rejected refresh recovery,
  one rejected full rebuild, access revocation, preserved completed results, Stop,
  required bank inputs and pinned Day Book exports. Shared book, inventory, tax,
  analytics and ActionCard regressions were checked.
- Manual security/simplification review covered company/account/session scoping,
  permission revocation, bounded reads, verified snapshot publication and immutable
  exports. No posting or reconciliation write capability was added. The requested
  slash-command review tools were unavailable; the checks were performed directly.

Runtime diagnosis found a quarantined incremental accounting generation and mixed
API/worker implementation versions. The code now distinguishes deployment mismatch
from source verification failure and can automatically request a fully verified
rebuild. Tests verify that recovery; a new live accounting snapshot was not created
as part of the read-only diagnosis.

Reports API, dispatcher, short/bulk execution workers and renderer were restarted
together after validation. All APIs, infrastructure and audit delivery reported UP;
all six report/snapshot workers were running. The console development server was
also restarted and reported UP.
