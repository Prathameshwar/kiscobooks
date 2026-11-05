# Analytics reports final review

Requested 2026-11-02: review all five reports, focusing on data accuracy, and fix findings.

## Reviewed measures and fixes

| Report | Accuracy checks and resulting behaviour |
|---|---|
| Sales performance | Posting dates govern periods. Commercial sales exclude tax and subtract returns once; discounts are already included. Currency groups remain separate. Product and category searches now match displayed line labels, without filtering invoice headers first. These searches narrow the breakdown; invoice totals and trends retain the full applied period and currency. |
| Profit and margin analysis | Company totals reconcile to the native posted P&L, including direct costs, operating expenses and other income. Product costs require matching voucher/common-line identities, dated owned-stock movements and matching currency. Missing costs remain unavailable. Searches now find verified item names and displayed unmapped labels. Company P&L totals retain the full period. |
| Customer insights | Activity and repeat purchases use retained identified-customer history, with explicit inactivity thresholds and first-observed dates. Returns without retained purchases now remain in customer rows and net sales. Their purchase dates, recency and inactivity remain unknown. Anonymous transactions remain separately disclosed. |
| Expense and profit leakage | Expenses reconcile to the posted P&L. Returns, discounts and stock losses are diagnostics and are not deducted from profit again. Group searches now match group names and retain every account in that group. Diagnostic searches match displayed reduction labels. Missing stock history or a period beyond stock coverage produces an explicit unavailable notice. |
| Cash and working capital | Opening cash plus recorded receipts minus payments plus opening adjustments equals closing cash. Transfers are netted per journal. Outstanding debts and unapplied credits remain separate and reconcile to the party ledger. Owned stock requires a matching date and company base currency, including empty snapshots. Slow-stock status requires known old origins and complete history with no company-wide sale or consumption in the selected window. |

New runs use calculation version 2. Previously frozen runs retain their original
calculation and source evidence.

## Presentation review

The shared workspace keeps bill references, debt/credit direction, stock status,
quantity, unit and cash movement visible by default; additional columns remain
selectable. Customer insights displays recorded net sales. Cash insights displays
opening balance and opening adjustments alongside the existing closing balance,
receipts and payments. Charts name their actual measure and disclose the latest
24 intervals without promising a view that does not exist.

Report source authority, private artifact delivery, actor/company isolation,
field denies, comparison drill-down periods, source bounds and exact Decimal
calculations remain enforced. The manual security and simplification review found
no additional issue requiring a permission or schema change.

## Verification

181 distinct backend cases passed across the full suite and targeted reruns.
The full native suite completed with 175 passes and one incorrect fixture
expectation: it expected net party balance 80 as gross receivables. The fixture
allocates only 50 of a receipt of 120 against an invoice of 200, so the correct
gross debt is 150 and unapplied credit is 70. The targeted cash check and the
subsequent five-report native/export suite passed with that corrected expectation.
Five additional stock-age/cash comparison cases passed. The selected native
suites also cover ledger, invoice, statement, allocation, source-cut, drill-down,
authority, export and registry regressions.

Combined statement/branch coverage is 97.33% across the six Analytics domain
modules; every module exceeds 90%, and cash/common calculations reach 100%.
The Console application passes the scoped TypeScript check and 108 relevant
Analytics, catalogue, report and shared-book UI tests. Ruff and strict mypy pass
for all 11 Analytics backend modules. Generated API clients are current.

All five reports completed in the authenticated running company. The live Cash
report downloaded a valid PDF. That company's selected retained period has no
posted financial activity; populated arithmetic is independently checked using
verified native MySQL source fixtures. For those fixtures, all five reports
produce actual private PDF/XLSX/CSV files with posting basis, exact summaries and
interpretation notes. The native runs verify replay, ownership, denied downloads
and valid file formats. Migration/model/index parity and a downgrade/upgrade
round trip also pass in disposable schemas.

The browser checks the authorized live catalogue and all five workspaces against
these populated native results, comparing the downloaded file bytes. Date inputs,
stable-height row action drawers, desktop/mobile widths and Light/Dark/Ledger
themes pass without page errors or document-level horizontal overflow. The test
fixtures configure the actual private export directory before capturing export
capabilities; Print remains disabled when that configuration is absent.

Evidence is local under `.test_artifacts/analytics-reports-review/`, including
native files, export review, coverage, UI logs and separate live/fixture browser
records. Credentials remain protected and are not published.

## Data limits

These reports describe recorded transactions. They do not estimate exchange
rates, missing historical product costs, first-ever purchase dates, future cash
collections or customer churn. Missing stock links, incomplete stock coverage and
unknown due dates stay explicit. Row search and report parameters retain their
documented scope; a filtered breakdown does not redefine company P&L or cash
totals.
