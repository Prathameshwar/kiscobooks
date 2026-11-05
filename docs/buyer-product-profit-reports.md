# Buyer and product profit reports

## Plan agreed by the implementation request

These are two new cards under Analytics. Profit means commercial net sales
(excluding GST, after commercial reductions and credit notes) less verified actual
stock cost, before shared overheads. Do not allocate company P&L, imported YTD,
latest purchase prices or FX estimates to buyers/products. Unknown costs make the
affected profit unavailable, including totals; zero cost requires explicit evidence.

### 1. Party (buyer) wise profit

1. Define exact buyer aggregation and invoice breakdown over the frozen source.
   Test sales/returns, partial costs, currencies, comparisons and anonymous buyers.
2. Register the report, filters, scoped invoice drill-downs and private exports.
3. Add the Analytics card/workspace with period, comparison, buyer, currency and
   search filters; reuse compact progress, cancellation, refresh and export actions.
4. Verify native execution, permissions, actual export files and responsive UI.

### 2. Product wise profit

1. Reuse the same cost arithmetic for Products and Product groups views. Include
   ancestor groups, deduplicate memberships inside each group and compute summary
   totals from unique source lines. Unmapped lines remain explicit.
2. Add item/group filters using the retained inventory dimensions. Group names and
   hierarchy reflect that snapshot; overlapping group rows are not additive.
3. Register the report and add its Analytics card/workspace, group-to-product
   navigation and private exports.
4. Verify hierarchy, overlapping membership, returns, missing costs, currency,
   comparisons, filter behavior, native jobs, exports and responsive layouts.

### Final review and application

Review both reports end to end against the repository security and correctness
rules. Run affected backend/UI suites, type/lint and contract checks, fix findings,
then restart Reports API/workers and console. No database migrations, permission
additions, money writes or new dependencies are required. Previous Analytics work
is preserved. Commit/publication is outside this request.

## Execution and validation

Both report implementations are complete:

- `BUYER_PROFIT`: Buyers and Invoices and returns views; buyer/currency/search and
  comparative-date filters; invoice date, reference and account context; signed
  invoice drill-downs; private PDF/XLSX/CSV exports.
- `PRODUCT_PROFIT`: Products and Product groups views; product/group/buyer,
  currency/search and comparative-date filters; frozen inventory selectors and
  group-to-product drill-downs. Ancestor and overlapping membership is deduplicated
  per group. Summary totals count unique source lines, not group rows.
- Both use verified stock movement costs and reversal signs. Costs, profit and
  margins remain unavailable if any selected line lacks cost evidence. Currencies
  stay separate and margins recompute from aggregate operands. Comparisons preserve
  unavailable prior values. Services and unmapped lines remain explicit.
- Both inherit source preparation/recovery, compact progress and Stop, history,
  frozen display preferences, saved selections, scoped search/sort and top exports.

Final review fixed hidden period labels in the new report tables, search for
unidentified buyers, and the distinction between overlapping group rows and unique
summary totals. Invoice exports retain buyer/account and posting-date context.
The invoice PDF projection was reordered after visual review so sales, actual
cost and gross profit appear together in its first column band. The regression
checks the table headers rather than accepting matching words in the notes.
No new money writes, routes, permissions, database changes or dependencies.

## Validation and final review

- 43 calculation/regression tests passed; the new domain module has 99.16% branch
  and statement coverage (90% required).
- 46 native MySQL checks passed, including both new reports with actual matching
  invoice/stock/GL evidence, negative profit, group-to-product drill-downs,
  authorization, replay, retained history and all Analytics views. Actual private
  PDF/XLSX/CSV files were generated. Disposable-schema migration parity and
  downgrade/upgrade checks also passed.
- Shared Analytics/reference UI: 68 tests passed. After review, 28 UI/browser
  checks and 7 focused retained-view/filter checks passed. These runs overlap.
- Final native follow-up after the PDF fix: 6 passed, 15 deselected. Both new
  reports and all four views execute and export successfully; the first PDF table
  band contains net sales, cost and gross profit. Invoice context continues on a
  labelled second band with row numbers; no columns are discarded.
- Browser checks cover all 33 Analytics views at 1440, 390 and 320 pixels in both
  light and dark themes, including contained table scrolling. Representative
  screenshots and exported PDFs were inspected manually.
- Ruff, strict mypy for five affected source modules, console TypeScript, Reports
  OpenAPI drift and generated Reports client checks passed. No public API schema
  changes were required.

The `/simplify` and `/security-review` commands are unavailable in this session.
Equivalent manual reviews covered exact Decimal arithmetic, missing-cost and
currency boundaries, bounded source reads, tenant/company scope, current authority,
immutable results, signed drill-down filters, private artifacts and shared UI reuse.
No additional security findings remained. Financial checks use synthetic facts in
disposable schemas and do not certify live customer transactions.

Artifacts: `.tools/dimension-profit/native/` and
`.tools/analytics-completion/browser/`. Logs: `.tools/dimension-profit-*.log`.
The console, Reports API and report execution/render workers were restarted with
the final definitions. The Reports readiness endpoint returns ready, all six
reporting/source workers are running, and `/reports/analytics` returns the expected
sign-in redirect for an unauthenticated request.

## Backend review follow-up

Plan: (1) reproduce drill-down scope, comparison-source selection, export filter
context and decimal-context findings; (2) fix them using the existing source and
rendering contracts; (3) run domain/native/export regressions, lint and typing;
(4) review scope/security and restart Reports API/workers. Existing unrelated
Accounting/Catalog/Vouchers edits remain untouched.

Findings and fixes:

1. Invoice/buyer drill-downs could widen a reference-filtered selection to every
   invoice for the buyer. Single-invoice selections now retain that invoice ID;
   multi-invoice reference subsets do not offer a broader sales-register link.
   Whole-buyer searches and comparative dates remain supported. Private subset
   evidence stays inside the frozen result and is not exposed in row responses.
2. Source reads used the interval spanning both comparison periods, including
   unselected intervening invoices. Ordinary analytics now query the union of
   the actual periods; customer-history reads still include their full history.
3. Line matching inherited the caller's Decimal precision before aggregate
   calculation began. It now uses the same explicit 48-digit context as totals.
4. Presentation exports omitted buyer/product/group/currency filter context.
   These selections now retain names and IDs from the frozen source, including
   empty results, and appear in PDF/Excel/HTML metadata. The CSV row contract is
   unchanged.
5. A missing prior product/group row could be reported as zero profit while
   earlier invoices lacked product identity. Missing baselines and derived changes
   now remain unavailable in that currency instead of inventing a zero baseline.

The two definitions are version 2; frozen version-1 results remain readable.
No migrations, new dependencies or public API schema changes were needed.

Follow-up verification: 66 shared/domain checks passed, followed by 23 focused
checks after the additional comparison fix, with 100% coverage of the profit
domain module. The native suite passed 30 checks and exposed two missing buyer
labels on empty reports; a scoped frozen-party lookup fixed them. All three final
native regressions passed, including real PDF downloads with the retained filter
names/IDs. The targeted console suite passed 21 tests. Runs overlap.

Ruff, strict mypy, OpenAPI drift and whitespace checks passed. The manual security
and simplification review found no remaining issues: source reads retain tenant,
company and sequence scope; drill-downs retain current authority; export text uses
the existing escaped/private rendering path. No unrelated owner-service edits
were changed.

Applied the backend follow-up by restarting Reports API and the reporting
execution/render workers. API readiness is healthy and all six reporting/source
workers are running with the final definitions.

## UI review follow-up — 2026-11-03

Review phases: reproduce comparison/context/detail issues; fix the shared UI with
profit-specific labels; verify interactions, exports and responsive layouts;
review scope and restart the console to apply the changes.

Findings and fixes:

1. Summary cards iterated only current-period currencies, hiding currencies that
   occurred solely in the comparison period. Cards now retain both sets of
   currencies, explicitly identifying absent current activity without inventing
   zero values. Missing cost evidence still displays as unavailable.
2. Comparison dates and frozen dimension selections were absent beside the
   figures. The summary now displays the completed run's comparison dates and
   buyer/product/group/currency selections. Editing filters does not relabel old
   results. Compact wrapping chips display names, with full retained references
   available as titles.
3. The invoice view labelled buyers as accounts, and product selection used a
   generic item label. Profit workspaces now use Buyer, Product, Product group,
   Actual cost and Gross margin consistently.
4. Row details rendered unregistered comparison fields as raw strings and nulls
   as dashes. Profit detail metadata now applies frozen money/percentage
   formatting, meaningful document/count labels and explicit unavailable values.

Regression tests reproduced the first three visible issues before the fixes.
Interaction coverage also verifies all four views preserve their export view,
automatically download completed PDFs and retain the download link at the top.
The browser matrix includes long applied names, unavailable comparison costs
and a comparison-only currency at desktop and narrow mobile widths.

Manual simplification and security/correctness review: no new dependencies,
requests, permissions, source calculations or public API changes. Applied labels
use escaped React text from the frozen result; detail formatting uses the run's
display configuration. Existing reference ownership, access revocation and
private export flows remain covered by the shared regression suites.

Verification: 77 distinct UI checks passed across the two runs (54 initially,
then 33 with 10 overlapping checks). The browser check covers all 33 Analytics
views at 1440, 390 and 320 pixels in light/dark themes; desktop and mobile profit
screenshots were also inspected. TypeScript and whitespace checks passed. The
console was restarted successfully on port 4320 to apply this UI-only follow-up.
