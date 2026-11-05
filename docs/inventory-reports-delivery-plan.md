# Inventory reports: sequential delivery and review

Authorized 2026-11-01: the user requested a plan, implementation, correctness
review, UI/UX review and final end-to-end review for each of the ten inventory
reports, completed one at a time without intermediate approval stops.

## Shared delivery rules

Keep `/reports/inventory` and all existing report bookmarks. Use the Stock Summary
and Day Book workspace, shared UI components/styles, frozen source references,
registered report jobs, signed drilldowns and private export pipeline. Each report
gets its own title, purpose, essential columns, filters, full-result metrics,
empty/error/recovery states, private saved views and report-specific history.
Refresh and Refresh stock data share the export/print action row. As-of is a
calendar tied to retained verified snapshots; period reports additionally select
a From date inside the actual retained movement window.

Search applies before totals/paging/exports. Default columns emphasize business
information; technical references and optional detail remain under Columns/Source
details. Row actions use a portalled kebab and details drawer. Drilldowns retain
source/scope and restore the parent's page, filters, view and columns. All themes,
mobile scrolling, keyboard/focus behavior and actual files are reviewed.

Keep Decimal arithmetic, item units, ownership/custody, actor/company authority
and field denial server-side. Never combine incompatible units or count detail
and control rows twice. Missing reservations, origin dates, cost allocation or
order coverage remain unavailable; reporting never posts stock/money or activates
an operational subsystem. Existing strict complete-input authority remains in force.

Native source enhancements may read existing Accounting receipt-origin balances,
cost layers/pools and unit movements under the existing owner fence. Catalog may
publish configured replenishment definitions through its existing immutable master
lease. No new service/table or cross-service database query is planned. Preserve
retained immutable cuts and explicitly version changed report/source contracts.

## Reference review

Official TallyPrime guidance retrieved for this review:

- [Stock Summary FAQs](https://help.tallysolutions.com/stock-summary-faq-tally/):
  item/group stock views, quantities and values, configuration and drilldowns.
- [Godown Summary](https://help.tallysolutions.com/godown-summary-tally/):
  location stock visibility and item drilldowns.
- [Batch Summary](https://help.tallysolutions.com/batch-summary/):
  batch balances, dates and traceability.
- [Stock Ageing Analysis](https://help.tallysolutions.com/stock-ageing-analysis-report-tally/):
  configurable age bands and tracing remaining stock to receipt origins.

These inform report purpose/navigation. The platform retains its own immutable
cost policy and source/authority contracts; alternate valuation simulations and
editing vouchers from reports are outside this reporting task. QuickBooks official
guidance was not successfully retrieved, so no unverified comparison is relied on.

## Report-by-report plan and acceptance

| Order | Report | Implementation/correction plan | Required acceptance |
|---:|---|---|---|
| 1 | Stock summary | Retain reviewed item balances; audit search, zero items, default columns, summary quantities/value, calendar, saved views and drill return. Establish the shared inventory workspace for subsequent reports. | 100 + 40 - 25 = 115; reservations reduce availability only; mixed units/owners separate; real refresh and four exports agree. |
| 2 | Item stock ledger | Dedicated item/period/warehouse/lot selection, exact opening and running balances, source vouchers and value movements; essential dates/inward/outward/balance columns. | A later From date changes opening; transactions reconcile to closing; no running balance across distinct positions; warehouse/lot scope and return navigation hold. |
| 3 | Warehouse stock | Dedicated location/item/group report, leaf-location rows and full-selection totals; exclude location/control duplication. | Parent location includes descendants once; transfer moves stock between locations without increasing company stock; unit-separated totals agree. |
| 4 | Stock valuation | Dedicated owned-stock values, costing method and unit costs, optional owner layer/pool evidence; separately labelled GL control rows and reconciliation status. | Position totals exclude layer/control duplicates and third-party stock; unknown allocation stays unavailable; explicit source cost details reconcile. |
| 5 | Batch summary | Dedicated lot/item/date report and optional movement/serial history; distinguish current positions from trace rows, preserve batch scope. | Current quantities count once; history units never inflate stock; dates/serials are readable; retained lot lookup uses the source snapshot. |
| 6 | Stock expiry | Dedicated upcoming-day window and expired inclusion, quantity/value exposure, known/unknown expiry statuses and focused default columns. | Expiry-day/minimum-life rules hold; unknown required dates appear as exceptions; held/expired quantities remain physical stock. |
| 7 | Stock reorder | Dedicated configured product replenishment report; explicit quantity basis and reservation/order coverage. Respect targets, minimum/multiple/maximum order constraints if native definitions supply them. | Available basis refuses unverified reservations; an explicitly selected eligible-stock basis excludes reservations and says so; unknown orders never become zero; no policy means a clear configuration-empty state. |
| 8 | Stock ageing | Dedicated receipt/manufacture age basis and ordered age bands; publish native residual origin cohorts, with unknown/assumed provenance separated. | Residual origin quantities sum to physical stock; transfer preserves receipt age; missing manufacture/history is unknown, not today's age; bucket boundaries are exact. |
| 9 | Stock movement | Dedicated period flow report, action categories and nonmoving filters; distinguish receipts/returns/transfers from consumption and costs from quantities. | Requested window changes opening/turnover; genuine last sale/consumption drives inactivity; insufficient history remains unknown; transfers are not sales. |
| 10 | Stock group summary | Dedicated group/unit/ownership/custody rollups, exact full-result summary without adding overlapping group rows, group-to-item navigation. | Ancestor/leaf memberships deduplicate; group rows are non-additive across overlapping groups; item drill never broadens the selected group. |

For each row: record the concrete findings, implement and run affected tests,
review correctness/security, inspect UI/styles/UX, then exercise Inventory card →
report → filters/rows/details/drill/back/history → CSV/Excel/HTML/PDF/preview.
Positive source cases run against disposable native schemas; the live company's
actual zero stock must remain zero. No synthetic operational postings are made in
the live company to make screenshots appear populated.

## Progress

| Report | Plan | Implementation/tests | Correctness review | UI/UX review | End-to-end review |
|---|---|---|---|---|---|
| Stock summary | Done | Done | Done | Done | Done |
| Item stock ledger | Done | Done | Done | Done | Done |
| Warehouse stock | Done | Done | Done | Done | Done |
| Stock valuation | Done | Done | Done | Done | Done |
| Batch summary | Done | Done | Done | Done | Done |
| Stock expiry | Done | Done | Done | Done | Done |
| Stock reorder | Done | Done | Done | Done | Done |
| Stock ageing | Done | Done | Done | Done | Done |
| Stock movement | Done | Done | Done | Done | Done |
| Stock group summary | Done | Done | Done | Done | Done |

## Decision log

- 2026-11-01: the user explicitly authorized the complete sequential loop,
  including plans, implementations and three review/fix passes. Routine report
  presentation choices follow that authorization; no extra approval pause is needed.
- 2026-11-01: source audit confirms retained calculations for all ten reports,
  but nine generic workspaces, incomplete native origins/cost detail and omitted
  Catalog replenishment definitions. These gaps are included in this delivery.
- 2026-11-01: quantity-only/partial-authority projections, arbitrary historical
  snapshot reconstruction, posting activation and publication remain separate.
- 2026-11-01: all ten final live export and UI journeys pass. Result tables and
  empty states pass Light/Dark/Ledger at desktop/mobile widths. The final search,
  snapshot calendar, warehouse drill/return, saved-view and history journey passes.
  Detailed findings and verification are recorded in
  [inventory-reports-review.md](inventory-reports-review.md).
