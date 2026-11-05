# Report-by-report API review

Authorized 2026-10-22: review and update all 27 registered reports in registry order,
using the closest Tally/QuickBooks concepts. API work includes report-specific columns,
calculation filters, result search/filter/sort capabilities and signed next-level links.
The user authorized uninterrupted implementation; this phase record implements that scope.

## Phases

1. Establish official product references and a 27-report acceptance matrix. Add a bounded
   asynchronous result-query contract with explicit report allowlists, exact sorting,
   immutable parent provenance and ordinary signed ordinal paging. Financial calculations
   and presentation selection are separate: browsing must never recalculate running balances
   or disguise a subset as a reconciled full-company statement.
2. Review each report in registry order. Correct its exposed fields and add executable
   drilldowns to a filtered report, journal entries, invoice components/tax/settlement/GL
   or frozen row detail. Preserve generation, date basis, currency basis and authority.
3. Synchronize OpenAPI/client contracts, run per-report and native regression checks,
   verify migration/runtime compatibility and installed package, then final money/security
   review. New browsing UI, production activation and publishing are outside this task.
   Existing console row-link handling and its proxy allowlist were updated for compatibility.

## Result navigation decision

Growing source queries retain their indexed native access paths. New result search/filter/
sort runs as a bounded worker job against an immutable completed parent, through
`POST /report-runs/{id}/queries`. Selected results use indexed ordinal batches and normal
cursor paging, export the same selection, and retain original row ordinals and financial
evidence. Unsupported fields/values/sorts are rejected; no arbitrary SQL or field/operator
language is introduced. Prefix search uses only each report's declared readable identifiers
and labels. Work is bounded by source rows, result rows, bytes, time and process memory.

## Review ledger

The following registry order is the acceptance order. Findings, references, implementation
and verification are recorded as each report is completed.

| # | API code | Closest concept | Review and changes |
|---:|---|---|---|
| 1 | SOURCE_RECONCILIATION | Control totals / source integrity diagnostic | Reviewed; Source count and GL debit/credit controls; typed count/amount selection and frozen row detail. |
| 2 | ACCOUNT_LEDGER | Tally Ledger Vouchers / QuickBooks General Ledger | Reviewed; Opening account labels, voucher kind and original running balances; journal and frozen detail links. |
| 3 | DAY_BOOK | Tally Day Book / QuickBooks Journal | Reviewed; Entry-only journal grain; voucher-kind/date/amount selection; journal detail. |
| 4 | PARTY_LEDGER | Customer/vendor transaction detail | Reviewed; Party/account/role labels; journal and bill-wise outstanding links. |
| 5 | CASH_BOOK | Cash ledger / cash account register | Reviewed; Cash account classification and opening carry retained; journal links. |
| 6 | BANK_BOOK | Bank ledger / bank account register | Reviewed; Bank account classification and opening carry retained; journal links. |
| 7 | BALANCE_SHEET | Balance Sheet | Reviewed; Account/group labels, earnings bridges and company controls; account ledger links. |
| 8 | INCOME_EXPENSE | Income and Expenditure | Reviewed; Income/expense nature and NET_SURPLUS_DEFICIT; no trading gross-profit row; account links. |
| 9 | PROFIT_LOSS | Profit & Loss | Reviewed; Direct/indirect accounting retained with gross/net profit; account/group labels and ledger links. |
| 10 | TRIAL_BALANCE | Trial Balance | Reviewed; Opening, turnover and split closing balances plus control difference; account ledger links. |
| 11 | ACCOUNT_SUMMARY | Ledger monthly/day summary | Reviewed; Day/month account and descendant-group summaries with quiet-period carry; period-limited account/group links; unused journal filter rejected. |
| 12 | OUTSTANDING_BILLS | Bills Receivable/Payable / open invoices | Reviewed; Bill/account labels, original/allocated/remaining amounts and due-date aging; ledger and party bills. |
| 13 | ADVANCES | Unapplied customer/vendor credits | Reviewed; Explicit unapplied credit direction, original/remaining amounts and labels; ledger and bill links. |
| 14 | AGING | Receivables/Payables Aging | Reviewed; Debt/credit separation and original due-date buckets; uppercase money fields sortable; ledger/bill links. |
| 15 | BANK_RECONCILIATION | Bank reconciliation balance comparison | Reviewed; Instrument references/states plus book/statement controls retained; journal links; diagnostic does not certify statement coverage. |
| 16 | BANK_RECONCILIATION_EVIDENCE | Finalized reconciliation report | Reviewed; Finalized session membership, side/amount/matching/residual and session balances; removed never-populated columns; journal links. |
| 17 | BANK_RECONCILIATION_WORKLIST | Unmatched bank transactions | Reviewed; Bank/book dates, source identifiers, status and age_days; removed unused date columns; journal links. |
| 18 | PAYMENT_REGISTER | Payment vouchers / vendor payment detail | Reviewed; Tender/account labels, modes and references; no multiplication of voucher totals; journal links. |
| 19 | RECEIPT_REGISTER | Receipt vouchers / customer receipt detail | Reviewed; Tender/account labels, modes and references, split-tender/reversal semantics retained; journal links. |
| 20 | SALES_REGISTER | Sales Register / sales transaction detail | Reviewed; Invoice/party labels, original/reduction direction, tax/rounding/supplier difference; journal/component/tax/settlement/GL links. |
| 21 | PURCHASE_REGISTER | Purchase Register / purchases by vendor | Reviewed; Supplier invoice labels and original/reduction direction; native-currency totals; journal/component/tax/settlement/GL links. |
| 22 | INVOICE_COMPONENT_REGISTER | Invoice item/charge/allocation detail | Reviewed; Separate component/allocation amounts plus purpose/scope/effect/basis; invoice and journal links. |
| 23 | INVOICE_TAX_REGISTER | Invoice tax detail | Reviewed; Component taxable basis, percentage, supplier charge, treatment/credit state and tax-point date; invoice/journal links. |
| 24 | INVOICE_CREDIT_REGISTER | Input-tax-credit positions and events | Reviewed; Separate as-of credit positions and dated events; pending/eligible/claimed/suspended/blocked states retained; invoice links. |
| 25 | INVOICE_SETTLEMENT_REGISTER | Invoice payment/settlement history | Reviewed; Allocation identity, original posting/reversal dates and as-of activity; invoice/journal links. |
| 26 | INVOICE_GL_BRIDGE | Transaction journal / invoice posting detail | Reviewed; Actual GL account code/name and line currency; exact signed debits; invoice and journal links. |
| 27 | TAX_GL_BRIDGE | Tax-to-ledger reconciliation detail | Reviewed; Tax purpose/component and actual GL account/currency; tax-point/posting distinction preserved; invoice/journal links. |

These are conceptual equivalents, not claims of statutory output or product feature parity.
Existing complete-company authority, accrual basis and owner-committed evidence remain required.

## Official reference concepts

Public TallyHelp articles were inspected on 2026-10-22. QuickBooks names in the matrix
are conceptual equivalents; this review does not claim QuickBooks output certification.

- Reports 2-6 and 11: [Ledger Vouchers](https://help.tallysolutions.com/ledger-vouchers/),
  [Day Book](https://help.tallysolutions.com/day-book-tally/), and
  [Cash/Bank Book](https://help.tallysolutions.com/cash-bank-book-tally/): selected periods,
  debit/credit entries, running balances, monthly summary and voucher/bill drilldowns.
- Reports 7-10: [Balance Sheet](https://help.tallysolutions.com/balance-sheet-tally/),
  [Profit and Loss](https://help.tallysolutions.com/profit-and-loss-statement-tally/) and
  [Trial Balance](https://help.tallysolutions.com/trial-balance-tally/): classified account
  balances, comparisons and ledger drilldowns. Income/Expenditure uses surplus/deficit wording
  while retaining this platform's accrual calculation.
- Reports 12-14: [Outstandings](https://help.tallysolutions.com/outstandings-tally/):
  bill-wise receivables/payables, unapplied credits and due-date aging.
- Reports 15-19: [Bank Reconciliation](https://help.tallysolutions.com/bank-reconciliation-tally/)
  and Day Book/Ledger Vouchers: instrument/statement details, unmatched activity and vouchers.
  Source reconciliation (#1) and finalized owner-session evidence remain platform diagnostics.
- Reports 20-22 and 25-26: [Sales Register](https://help.tallysolutions.com/how-to-work-with-sales-register-in-tallyprime/)
  and [Purchases](https://help.tallysolutions.com/purchase/): period -> invoice -> components,
  settlement and accounting-entry detail. Purchase returns retain DEBIT_NOTE reduction semantics.
- Reports 23-24 and 27: [GST reports](https://help.tallysolutions.com/tally-prime/taxation-compliance/india-gst/gst-reports/):
  tax detail and reconciliation concepts. This API exposes owner-recorded tax/credit facts;
  it does not add statutory return filing or infer unrecorded ITC eligibility.

## Implementation and resource limits

All 27 definitions advertise `navigation`: typed filter fields, prefix-search labels,
allowlisted sort fields (maximum three), nulls last and original-balance semantics.
`q` searches a field prefix, case-insensitively (minimum two characters). Filters are ANDed;
text/UUID/boolean comparisons are exact, dates accept `_from`/`_to`, amounts/integers accept
`_min`/`_max`. Amounts use Decimal comparisons; financial values remain decimal strings.
Sort uses ascending original ordinal to resolve ties. Unknown fields, duplicate sort keys,
nonfinite amounts and reversed ranges are rejected. No source entry is rewritten.

Result selection is a BULK-lane worker over the parent's frozen result, capped by configured
`bulk_result_limit` (default 1,000,000 scanned/selected rows), 32 MiB selected canonical JSON (before provenance fields),
configured bulk time limit (default 600 seconds), and the existing 512 MiB process memory cap.
An over-limit selection is blocked with `REPORT_CAPACITY_EXCEEDED`; it is never truncated.
Selected exports are labelled "Selected rows". Their reconciliation evidence belongs to the
full parent, not a falsely complete-company subset. The result retains the immediate parent's
source ordinal, query, attempt and evidence hash. Further selections refer to their immediate
parent; provenance forms a chain.

Native ledger row-detail links contain a signed cursor before the selected row, so HTTP reads
seek one row rather than traverse earlier pages. Tokens are bound to company, tenant, actor,
permission context, parent run and attempt; current authority is always rechecked. Materialized
row detail reads the indexed ordinal batch and checks its hash/count. Legacy pinned runtime v1
remains packaged unchanged; new ledgers use runtime v2. Unsupported historical calculations
still require a fresh run for new selection requests; completed reads/exports retain their versions.

Apply additive Reports migration `0036` before deploying: one scoped journal index, with matching
model and reversible downgrade. Existing source/ledger projections remain version 4. This adds
no owner mutation, schema copy, arbitrary SQL or production admission change.

## Final review and validation

Per-report tests exercise populated source data for every report, all advertised ascending/
descending sort fields, exact filters, prefix search, API query publication/paging, frozen row
links and each available next-level mapping. Separate tests cover unchanged running balances,
Decimal ties/ranges, permission revocation, token tampering, bounded failures, selected HTML
export and cursor-based comparative detail. Native regression and migration checks cover
SQLite and disposable loopback MySQL; final results are recorded below.

Simplification review: report row grains and navigation allowlists share one registry spec;
filter constants compile once per worker scan; views project canonical rows. Retained runtime
v2 is an intentional frozen copy, not a dependency on mutable live handlers. Named slash-command
tools `/simplify` and `/security-review` are not available in this environment, so equivalent
manual reviews were performed against CLAUDE.md sections 5 and 6.

Security/money review: fixed unbounded native row-detail traversal, strengthened full-definition
parent identity checking, aligned document-date journal links to actual posting dates, corrected
GL account/currency labels, and separated surplus/deficit from trading profit presentation.
Current company/read/field authority, immutable attempts, private exports and exact money
arithmetic remain enforced. The console proxy allowlist now admits and tests the result-query
and signed row-detail routes.
No unresolved correctness/security finding was found in reviewed scope.
Production load/soak and release activation are outside this local API task.


Verified checkpoints:

- All 27 API query/drilldown cases passed in registry order; strengthened nonempty fixture,
  filter/search/sort cases passed in subsequent focused runs.
- Disposable MySQL gates: 139 tests passed, then 151 tests passed after populated fixtures,
  export/security additions; each included model/index parity and full base -> 0036 -> base -> 0036.
- Console compatibility: 39 tests passed (workspace, GET detail, proxy allowlist and downloads),
  full console TypeScript check passed. API client: 8 tests and TypeScript check passed.
- Ruff/mypy and OpenAPI/client freshness checks passed. Installed wheel check passed with
  27 definitions, new navigation and both packaged ledger runtimes.

Final MySQL gate: 106 tests passed, including all 27 populated API loops, wrong-company/
cross-tenant and field-deny checks, token tampering, exact sorting, selected exports, native
invoice parity, and the journal index access regression. Model/index parity and complete
migration downgrade/upgrade passed again. Disposable test schemas were removed by the helper;
the temporary loopback server was stopped. Subsequent canonical UUID-filter and console
formatting checks passed (8 focused backend tests, 14 console tests); final package reinstalled
successfully.

Full service regression: **498 passed, 6 skipped**. The skipped checks require native MySQL
or live broker conditions; the relevant native checks ran separately on disposable MySQL.
The full command's whole-service coverage assertion failed at **85.47%**. A focused append
command also initially failed its whole-service assertion because its data was being collected
alongside the full run; all 126 tests in that command passed. The checks were then run sequentially,
with the existing coverage policy measured over `domain/` as in earlier framework gates.
Final focused tests: **103 passed**, with **94.89% domain branch/statement coverage**,
above the previous **93.49%** and mandatory **90%** domain floor. New navigation is **99.51%**,
drilldowns **98.90%**, invoice registers **97.18%**. The whole-service measurement remains below
its default 90% assertion; subprocess-only renderer/worker code and retained runtime helpers
are material uncovered areas. No test or coverage exclusion was added to conceal those gaps.

Final per-report suite: **106 passed, 1 skipped** (the MySQL-only journal index test,
which passed in the native gate). A final bank-row review also added the selected account
identifier to each instrument row so advertised account filters include instruments; its
focused bank/native parity results are recorded below.
