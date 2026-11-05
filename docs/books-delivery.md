# Native Books workspace delivery

Approved scope: research, plan, implement, review and fix the nine Books entries other
than Day Book. Day Book is a read-only visual and interaction reference for this work.
The existing versioned Reports definitions remain the financial authority.

## Product references and adopted patterns

- TallyPrime Cash/Bank Book: daily chronological receipts/payments, opening and closing
  balance, account selection, period selection, drill-down, negative-balance visibility.
  <https://help.tallysolutions.com/cash-bank-book-tally/>
- TallyPrime Sales/Purchase Registers: periodic summary, voucher drill-down, configurable
  periods and columnar views. <https://help.tallysolutions.com/how-to-work-with-sales-register-in-tallyprime/>
  and <https://help.tallysolutions.com/track-purchases/>
- TallyPrime Payment/Receipt Registers: monthly-to-voucher drill-down, columnar views,
  tender/bank references and exception visibility.
  <https://help.tallysolutions.com/knowledgebase/payments-and-receipts-tally/>
- TallyPrime ledgers: account and party histories remain grounded in ledger postings and
  bill-wise party balances. <https://help.tallysolutions.com/ledgers-and-groups-in-tallyprime/>
  and <https://help.tallysolutions.com/set-up-party-ledger/>
- QuickBooks: customizable transaction detail, account/customer/vendor grouping, visible
  columns and transaction drill-through; inventory valuation detail shows movements and
  their quantity/value/cost effects.
  <https://quickbooks.intuit.com/learn-support/en-us/help-article/report-management/use-reports-see-sales-inventory-status/L7ocoLmqP_US_en_US>

## Shared implementation rules

- Use immutable, verified report generations and the existing native definitions. Do not
  recalculate financial truth in the browser.
- Reuse the Day Book information hierarchy: breadcrumb/header, snapshot freshness,
  compact filter surface, summary strip, responsive report surface, retained results while
  refreshing, cursor paging, private export and drill-down.
- Build each summary from the complete frozen result on the Reports worker, not from the
  visible page. Preserve exact decimal strings and separate currencies rather than adding
  unlike amounts in the browser.
- Discover parameters, views, columns, limits and formats from each versioned definition;
  do not hard-code a second report contract in the client.
- Keep exact server-provided decimal strings and company display configuration.
- Saved view preferences contain filters only and are scoped to actor, company and book.
- Permission-gate source refresh, export, and reference lookups. Never expose source data
  outside the authenticated tenant/company authority.

## Per-book quick plans

### Cash Book

1. Select an optional cash account and period/currency basis.
2. Show opening/running/closing balance columns with debit receipts and credit payments.
3. Highlight negative visible balances and retain full journal drill-down.
4. Support frozen export, saved filters and snapshot refresh.

### Bank Book

1. Select an optional bank account and period/currency basis.
2. Show chronological debit/credit movements and running balance.
3. Preserve bank-account drill-down; direct reconciliation remains the separate native
   Bank Reconciliation report rather than being duplicated here.
4. Support frozen export, saved filters and snapshot refresh.

### Sales Book

1. Support posting/document-date basis, customer, account, currency and invoice filters.
2. Show commercial total, tax, rounding and payable with invoice/journal drill-down.
3. Provide compact/detail definition views and frozen exports.

### Purchase Book

1. Support posting/document-date basis, supplier, account, currency and invoice filters.
2. Show commercial total, charged tax, supplier difference and payable.
3. Preserve component/tax/settlement/GL drill-down supplied by the native definition.

### Payment Book

1. Support period, account/party/role and currency basis.
2. Show payment voucher, tender mode, instrument/reference, recognition and amount.
3. Preserve journal-entry drill-down and exports; post-dated/exception behavior remains
   represented by the server's recognition fields, never inferred by the UI.

### Receipt Book

1. Mirror Payment Book with receipt-specific copy and semantics.
2. Show tender and instrument references with exact amount and currency.
3. Preserve journal-entry drill-down, saved filters and exports.

### Account Ledger

1. Require or allow the definition's account filter and support group/period/currency.
2. Show opening context, debit, credit and running balance in posting order.
3. Provide retained row and journal drill-down with frozen exports.

### Party Ledger

1. Filter by customer/supplier party, role, account, period and currency.
2. Show chronological debits, credits and running balance.
3. Keep outstanding-bill drill-down available alongside journal detail.

### Stock Ledger

1. Require an item and support warehouse, batch, ownership and period filters.
2. Show inward/outward quantity, running quantity, value delta and value balance.
3. Keep inventory evidence distinct from the financial snapshot and validate it server-side.
4. Support frozen exports and retained row detail.

## Delivery loop

- [x] Research TallyPrime and QuickBooks patterns for all nine books.
- [x] Decide the book-specific scope and improvements above.
- [x] Record quick plans before application changes.
- [x] Implement the shared native workspace and all nine configurations.
- [x] Run unit, type, report-contract, accessibility and responsive review.
- [x] Fix findings and record final evidence.

## Review evidence and fixes

- Console strict TypeScript check passed.
- The final Books UI/end-to-end selection passed 80 tests across native Books, Books routing,
  shared export behavior and the private download proxy. The existing Reports renderer and
  artifact suite passed 15 tests.
- 67 focused Books, native workspace, Reports workspace, financial-report and navigation
  tests passed. The shared responsive Day Book style contract used by these workspaces also
  passed its 2 tests.
- Route coverage opened all nine native book routes and retained company-scoped permission
  denial. Dedicated coverage verified definition-owned filters, exact formatted balances,
  cursor paging, actor/company/book-scoped saved views, permission-gated actions and private
  export delivery.
- Review fixed UTC-derived default dates, incomplete saved-view validation, first-page-only
  source discovery, a refresh action that could retain an older snapshot, missing local date
  and transaction-currency validation, and non-actionable server-issued drill-downs.
- The final implementation uses the existing Day Book responsive classes and design tokens;
  it does not modify Day Book code or CSS. Tables remain horizontally scrollable and
  keyboard-focusable on narrow screens, while filters use the established responsive grid.
- Manual security/accounting review found no client-side recalculation, cross-company
  reference path, arbitrary export download, floating-point money conversion or unbounded
  result request. Server definitions, signed cursors/drill-downs and verified generations
  remain authoritative.

## Per-book review and export fixes

| Book | Primary surface | More filters | Reviewed result/export focus |
|---|---|---|---|
| Cash Book | Period, Cash account | cash ledger group, party/role, currency, comparison, journal | debit/credit/running balance; negative values retain accounting format |
| Bank Book | Period, Bank account | bank ledger group, party/role, currency, comparison, journal | bank movements/running book balance; reconciliation remains separate |
| Sales Book | Period, date basis, Customer | customer account, sales group, role, currency, comparison, invoice | commercial/tax/payable and invoice/journal drill-down |
| Purchase Book | Period, date basis, Supplier | supplier account, purchase group, role, currency, comparison, invoice | commercial/charged-tax/payable and supplier detail |
| Payment Book | Period, Paying cash or bank account, Paid party | payment group, role, currency, comparison, journal | tender mode, instrument/reference, recognition and amount |
| Receipt Book | Period, Receiving cash or bank account, Received from party | receipt group, role, currency, comparison, journal | tender mode, instrument/reference, recognition and amount |
| Account Ledger | Period, Ledger account | ledger group, party/role, currency, comparison, journal | chronological debit/credit/running balance |
| Party Ledger | Period, Customer or supplier, Party role | party account/group, currency, comparison, journal | party movement/running balance and bill/journal drill-down |
| Stock Ledger | Period, Stock item | item group, warehouse, batch/lot, ownership, inactive items | inward/outward, quantity balance, value delta/value balance |

Review fixes shared by all nine books:

- The final UI workflow review fixed retained-result view integrity (changing a view no
  longer relabels rows from the previous calculation), locked conflicting actions while a
  latest-snapshot refresh is in progress, kept the report accessible while an export runs,
  and added in-place recovery when initial definition/source discovery fails.
- First-load and first-run states now use the report loading surface instead of briefly
  presenting a false empty book. Split-PDF controls stay out of the normal layout and appear
  only when they can rescue a result that is too large for one printable PDF.
- Saved views stop at the documented 20-view limit with an actionable message instead of
  silently discarding the oldest saved view.
- Added a Day Book-style opening summary strip with book-specific measures: receipts,
  payments and closing balance for Cash/Bank; net commercial, tax and payable for
  Sales/Purchase; voucher, tender and amount counts for Payment/Receipt; debit, credit and
  closing balance for Account/Party ledgers; and inward, outward and closing quantity for
  Stock. Opening rows affect closing position but not activity, comparative rows are
  excluded, returns reduce register totals, and multi-currency results remain visibly
  uncombined.
- Summary-domain tests cover ledger, register, tender and stock rules at 96% branch-aware
  coverage. Native materialized and pinned-query integration tests verify that the complete
  frozen result carries the summary evidence consumed by the workspace.
- Replaced schema/storage labels such as `Account Id`, `Group Id`, `Party Id` and `Item Id`
  with contextual accounting language. Retained identifier columns are hidden initially and,
  when deliberately enabled, are labelled as audit references rather than master names.
- Reduced the main filter surface to each book's period and defining selector(s). Remaining
  controls use the established responsive More filters drawer with active-filter count,
  Reset advanced and Apply filters actions.
- Consolidated choose/save/delete view controls behind one accessible Saved views book icon
  beside the filter actions. The drawer stays out of the ordinary layout; choosing a saved
  view closes it and immediately prepares the matching frozen result.
- Export menus now use human format names, current server-advertised formats, permission
  gates, retained-view binding, private downloads and single-PDF print preview. PDF, real
  Excel and CSV always stay visible; unavailable formats explain the server capability or
  complete-result capacity that blocks them.
- Print / PDF always prepares one printable PDF and offers the authorized inline preview.
  Large printable exports can separately use split PDF ZIP delivery when advertised; Excel
  and CSV remain single files. The split request is explicitly bound to `PACKAGE` delivery.
- Export status polling is sequential and abortable. The completed book stays visible during
  preparation, stale download links are removed before a new attempt, failed polling resumes
  the known export, and an uncertain initial submission retries with the same idempotency key.
- Streamed ledger books use their verified full-result summary count for row/cell/part checks
  instead of the materialized-row counter, which is intentionally zero for pinned queries.
- A parameterized test runs, exports CSV and Excel, and prepares a private printable PDF for
  every book through its own authoritative report code.
  Backend calculation/export review ran 113 tests: 111 passed, one skipped, and one unrelated
  existing `BALANCE_CONTINUITY` test failed because its fixture supplies a one-month range to
  a report that requires a complete financial year. All nine Books paths in that selection
  passed.

## Live print/export follow-up decision (2026-11-01)

The disabled Print / PDF investigation found that initial report preparation required
Apply and defaulted before the selected snapshot's available history. The workspace now
initializes within verified coverage and prepares automatically once required filters
and scoped references are ready. Manual dates remain explicit and server verified.
Source discovery validates the selected snapshot and refresh updates its history hint.

Nine Books routes, including Day Book, passed real PDF/Excel/CSV downloads and private
print preview. Stock Ledger requires a stock item and genuine complete inventory source;
a fresh READY source still contains zero inventory records. Its consumer/writers pass
with complete nonempty fixtures, but live printing remains blocked by the upstream
source boundary. The UI now names that dependency instead of leaving only an unexplained
disabled action. See [the review and per-book evidence](books-print-export-review.md).
