# Stock Summary delivery

User approved all phases of [the plan](stock-summary-implementation-plan.md) on
2026-11-01, with uninterrupted implementation and final review/fixes. No commit
or publication requested.

## Phase decisions

Initial delivery is As-of Stock Summary over complete company source evidence,
using existing strict input/financial authority and supported item/warehouse
filters. Arbitrary period reporting and quantity-only/restricted-authority
projections remain separately versioned extensions as stated in the agreed plan.
Native stock currently supports company-owned warehouse/transit stock and
warehouse FIFO/moving-average pools. Unsupported source ownership/custody or
residual bin allocation is not fabricated.

Complete source preparation reuses the Accounting reporting snapshot worker and
committed inventory publication adapter. Catalog supplies bounded, scoped,
policy-fenced immutable master pages. Stock refresh requests a fresh complete
source; a movement-only incremental handoff cannot certify inventory coverage.

## Checklist

- [x] Phase 1: source/contract audit and As-of/authority decisions.
- [x] Phase 2: complete Catalog/Accounting inventory source and live readiness.
- [x] Phase 3: typed Stock Summary search/filters/full-result totals.
- [x] Phase 4: dedicated Day Book-style page, filters, saved views and recovery.
- [x] Phase 5: permissions, frozen drilldowns, actual PDF/Excel/CSV downloads.
- [x] Phase 6: live evidence, affected/native tests and review/fixes.

## Evidence and final review

The existing Inventory report card opens the dedicated workspace at
`/reports/workspace?report=STOCK_SUMMARY`. It automatically prepares a report
from a verified complete source. Refresh stock data builds a fresh owner source;
Refresh rereads prepared data. Both actions share the Export / Print-PDF toolbar.

The As-of field uses the shared native calendar input. Only a matching verified
snapshot can run; unsupported dates show an inline explanation and disable Apply.
Load snapshot dates discovers retained cuts. Search, item/warehouse/group,
ownership/custody, inactive and zero-stock filters, stable sorting, saved views,
column selection, report history and frozen warehouse/ledger navigation are wired.
Full-selection totals separate base units, ownership and custody. Reservations
without owner coverage and ambiguous residual bin values remain unavailable.

Default table columns are Item name, Unit, Opening, Inward, Outward, Closing stock
and Stock value. All other authorized columns remain selectable. Row actions use
the shared portalled kebab menu; detail opens in a drawer without changing row height.

Live QA evidence is retained privately in `.test_artifacts/stock-summary-review/`:

- A fresh source certifies 8 inventory records and produces 3 stock item rows.
  The existing company has zero physical stock; its verified catalog items appear
  as zero. No operational stock or financial balances were invented for this check.
- CSV has 3 data rows; Excel opens with report/provenance sheets; PDF opens with
  company, As-of date, movement window, owned value and unit-separated totals.
  PDF preview returns the same bytes as the protected download. HTML also opens.
- Actual CSV / XLSX / PDF / HTML exports completed: 621 / 7,390 / 33,484 /
  2,134,632 bytes. The PDF's three column bands repeat all three rows.
- Positive native receipt evidence was verified in a migrated disposable MySQL
  schema: quantity 2, carrying value 12.50, committed movement handoff, stable
  publication identities, failed-source rollback and stale-coverage invalidation.
- Live kebab and detail drawer preserve the row's 60.5-pixel height. Columns can
  be selected/unselected. Desktop 1440 and mobile 390 fit in Light, Dark and Ledger.

Verification: 12 native Accounting tests; 5 Catalog source/fence tests; 188 selected
inventory/rendering reporting tests (the final lease-test correction was rerun
separately); 8 Stock Summary UI tests, 33 native-book regressions, 60 proxy tests,
10 reference tests and 22 general report-workspace tests. Changed backend modules
pass Ruff and strict mypy; console TypeScript and Reports OpenAPI/client checks pass.

See [final review](stock-summary-review.md) for fixes, scope and access checks.
Local private credentials are scoped to the existing QA tenant/company. Other
companies require their own explicit owner scopes and complete source readiness.

## Follow-up final review results

The final requested review fixes terminal-source recovery, usable-cut selection,
parent page/column restoration, selected-view preservation, detail formatting and
saved-view reselection. See the follow-up section of the review for specifics.

- 14 Stock Summary tests and 33 Native Book tests pass after the final fixes;
  60 proxy, 10 reference and 22 report-workspace regressions also pass.
- 100 selected reporting checks pass, including exact opening/receipt/issue
  reconciliation, reservations, valuation and ledger agreement. Ruff passes for
  the added calculation test. No production calculation change was required.
- A new live fresh snapshot certifies 8 records and 3 zero-stock item rows.
  Frozen source recomputation also produces 3 rows and confirms the running
  definition matches the current implementation.
- Actual CSV / XLSX / PDF / HTML downloads contain all 3 rows and are respectively
  621 / 7,388 / 33,490 / 2,134,632 bytes. Protected PDF preview matches the download.
  The browser reports no page errors.
- Light, Dark and Ledger desktop/mobile checks pass at widths 1440 and 390;
  row/menu/drawer height remains 60.5 pixels. Detail dates, quantities and money
  now use the company formats.
- The live user journey passes calendar guards, item search, warehouse navigation
  and parent columns, saved-view restore/deletion, snapshot-date discovery and
  completed report history restoration, with no browser page errors.

Full console TypeScript validation currently finds six errors in unrelated
purchase quick-create tests changed concurrently. The application and affected
stock/book/reference tests pass separately, preserving those unrelated edits.
