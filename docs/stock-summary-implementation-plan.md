# Stock Summary implementation plan

Requested 2026-11-01: provide a proper Stock Summary reached from
`/reports/inventory`, borrowing the look, feel and useful interactions of Day Book.
This document is a proposal. No application code, database, configuration, source
snapshot or release flag is changed by this planning task.

Implementation authorization: on 2026-11-01 the user approved phase-wise delivery
of this plan, all phases without interruptions, followed by final review/fixes.
Current progress and agreed initial delivery boundaries are recorded in
[stock-summary-delivery](stock-summary-delivery.md).

## 1. What the current link opens

The Stock summary card opens `/reports/workspace?report=STOCK_SUMMARY`. That URL
selects a definition inside the general Reports workspace. It currently presents
the full report selector, manual source selection, technical parameter labels,
Create report, and company-wide recent report/export histories. It does not open
a dedicated Stock Summary experience or prepare a stock result automatically.

The calculation is already implemented: `STOCK_SUMMARY` version 2 aggregates
verified position evidence into item/ownership/custody rows. It returns opening,
inward, outward, closing physical quantity, eligible/reserved/available quantities,
carrying value and capability statuses. It supports item, location hierarchy,
group and ownership filters, zero-stock items with proven coverage, signed item
ledger drilldowns and the existing report export engine.

Its required date is `as_of`, which must match the inventory snapshot date.
Opening and turnover currently come from the owner's snapshot coverage window;
there is no arbitrary From date parameter for this definition. The user interface
must not present these numbers as movement for an independently chosen period.

The live company has no complete inventory source: the preceding Books review
confirmed zero inventory records even after a successful source refresh. Financial
snapshot readiness does not prove stock readiness. Existing calculations/export
fixtures pass, but a UI redesign alone cannot make the live report work.

References:

- [Current workspace route](../mfes/apps/console/app/reports/workspace/page.tsx)
  and [generic report screen](../mfes/apps/console/app/components/ReportWorkspace.tsx).
- [Inventory registration](../apis/reports/src/reports/tasks/inventory_catalog.py),
  [calculations](../apis/reports/src/reports/domain/reporting/inventory.py) and
  [parameter schemas](../apis/reports/src/reports/schemas/inventory.py).
- [Day Book delivery](day-book-delivery.md) and
  [live Books print/export review](books-print-export-review.md).
- [Inventory consumer implementation](reports-framework/inventory-implementation.md),
  [inventory review](reports-framework/inventory-final-review.md),
  [stock source/reporting design](voucher-stock-recording-reporting-design.md) and
  [native stock delivery](stock-posting-delivery.md).

## 2. Proposed experience

Keep the existing card and bookmarked URL working. For `STOCK_SUMMARY`, render a
dedicated Console Stock Summary workspace; other report codes keep their existing
routes. Breadcrumbs become **Reports > Inventory > Stock Summary**, with a clear
return to Inventory reports. Do not introduce another Stock Summary menu/card.

Borrow Day Book's shared page header, scope/freshness row, compact filters,
summary strip, report surface, saved-view/column drawers, responsive behavior,
progress and recovery states, and private Print/PDF/export workflow. Stock-specific
labels and calculations remain domain-specific. Reuse shared UI components/styles;
do not copy Day Book's entire component or financial/voucher activity controls.

Conceptual page layout:

```text
Reports > Inventory > Stock Summary
Stock Summary                         Export v   Print / PDF
Company · financial year
As of [date] · movement since [coverage start] · freshness
                                            Refresh

As of [date]   Warehouse [All]   Item group [All]
Search items [code or name]       More filters   Apply   Saved views

Items in result | Closing quantity by unit | Available by unit | Owned stock value

Product / Unit / Ownership & custody
Opening | Inward | Outward | Closing | Available | Stock value | Details

Applied scope and period · full-result count             Previous / Next
```

Warehouse and item/group controls use searchable, permission-scoped master
lookups. Advanced filters cover individual item, ownership, supported custody/
disposition, zero/nonzero stock and inactive items. Add a filter only with its
matching server contract and capability; unsupported reservation/batch fields
must not appear as functioning controls.

Search applies to the entire frozen result through a bounded server query/run
parameter, not just the currently displayed 50 rows. Search, scope, dates, sorting
and views must also bind totals, pagination, drilldowns and exports.

The first valid source/date/default selection prepares automatically. Later
filter changes remain pending until Apply; retain previous rows and show their
applied scope. Refresh obtains the newest compatible source and prepares again,
with abortable progress and retry that preserves command identity. No automatic
retry loop or false zero-stock screen when data is missing.

Default As of to the latest verified inventory date compatible with the selected
company/year, displaying that actual date and freshness. Do not substitute a
financial snapshot date or silently label an older cut as today's stock. A
historical date needs its compatible retained source; unavailable dates explain
what must be prepared. Eligibility at a new business-day boundary also needs
the correct evaluation date and owner policies, even when no movement occurred.

Only Stock Summary runs/exports appear in its optional History drawer. Saved
views are personal and company/actor/report scoped. Source UUIDs, versions,
classification dates and verification evidence belong in Source details.

## 3. Quantity and value contract

| Measure | Meaning and required behavior |
|---|---|
| Opening quantity | Quantity immediately before the displayed movement window; label its actual source start. |
| Inward / outward | Genuine stock quantity legs in that window, including applicable returns, adjustments and reversals. Internal transfers remain distinct from sales/purchases and cancel in complete-company physical totals. |
| Closing quantity | Physical quantity at the selected snapshot date; opening + inward - outward must reconcile for the declared scope/grain. |
| Eligible quantity | Stock that can be issued under the pinned ownership, custody, disposition and expiry policies. Held/damaged/expired stock remains physical stock. |
| Reserved quantity | Verified outstanding reservation quantity; unknown reservation coverage is unavailable, never zero. |
| Available quantity | Sum of eligible unreserved quantity at the supported position/allocation grain. Do not subtract all reservations from one aggregated item total. Displayed availability is not a posting guarantee. |
| Stock value | Owner-proven residual carrying value under the existing warehouse FIFO/moving-average policy, in company currency. Exclude third-party stock from owned asset totals. |

Rows separate item, base unit, ownership and custody. Owned local, transit/external
and third-party stock must not be silently merged. Quantity totals are per unit
and scope: `70 PCS + 15 KG` is two totals, not `85`. Item count is distinct items,
not the number of ownership/custody rows. Group memberships and parent warehouse
filters must not double count leaf positions or overlapping classifications.

Summary cards are calculated over the complete authorized frozen result, not the
visible page. Show unknown/unavailable quantities or value explicitly. A valid,
complete source may prove zero stock; absence of evidence may not.

For cost: reuse residual warehouse pool/layer evidence. Historical bin movement
values cannot establish a current residual bin asset. Bin/partial-location value
is unavailable unless the owner proves an allocation at that requested grain.
Stock Summary must not infer cost from selling price or recompute FIFO/MVA in
the browser. Stock-only activity must not create dummy financial journals.

Recommended first delivery is **As-of Stock Summary**, with its actual movement
window clearly displayed. A user-selectable From/To mode is a separate extension:
it requires complete historical movements, supported opening reconstruction,
historical source/valuation/classification semantics and a versioned parameter
contract. Reusing the existing period movement calculation is preferable to
building another engine, but only after those requirements are verified.

## 4. Complete source delivery is part of the implementation

This plan includes closing the live inventory source gap, rather than stopping
at a new screen. Reuse Accounting's native stock records and the trusted inventory
publication adapter, Catalog's authenticated definition/snapshot contracts, and
Reports' signed source-generation transport.

1. Capture a consistent owner stock generation, exact as-of/business timezone,
   coverage start and retained Catalog item/unit/group/warehouse/policy versions.
   External owner calls occur outside Accounting money transactions.
2. Produce complete typed item, location, group and position evidence, with
   supported reservation/eligibility facts, native movement identities and exact
   residual warehouse valuation/control evidence. Include zero/closed positions
   needed by retained history; do not publish only the latest voucher's movements.
3. Build bounded pages in a restartable, fenced job. Publish the single complete
   coverage record and matching records atomically through the existing adapter/
   source publication boundary. An unfinished batch is not complete company stock.
4. Reconcile identities/counts, quantities, movement/opening bridges, cost pools
   and supported GL controls before readiness. Preserve old frozen cuts and
   never rewrite committed movement history.
5. Expose server-authoritative stock readiness, snapshot date, coverage and
   reservation/valuation capabilities to discovery. Select a source compatible
   with the chosen date; never rely only on a financial READY flag or a positive
   inventory record count.

Any additional staging schema/migration or shared contract is designed with its
matched model/API/client/consumer changes in the relevant phase. No new service,
cross-service SQL, public balance overwrite, fabricated coverage or posting
activation is proposed.

## 5. Access, drilldowns and exports

Access is based on effective company-scoped grants and fields, not role names.
Tenant/company administrators still require the selected company's authority.
Reuse `report.read`, `report.export`, existing item/warehouse permissions and
the established financial input authority for value-bearing output.

The current inventory reports conservatively require complete input/financial
authority. Quantity-only and partial-warehouse access are target extensions,
not features that a client can enable by hiding a value column:

- Full-authority actors receive the complete authorized quantities/value view.
- A quantity-only view requires a server-enforced projection and matching
  authority proof. Denied value, unit cost, totals, drilldowns and exports must
  remain inaccessible. Until implemented, the current stricter denial remains.
- Restricted warehouse output must label its scope and filter rows, totals,
  master search and downstream links on the server. It may not claim complete
  company stock. Count/blind-count restrictions must remain effective.
- Export and source-refresh actions use their own effective grants; current
  authority is checked again at work, paging, drilldown and download.

Clicking a product opens its stock ledger from the same frozen source and scope,
then permitted movement/voucher detail, with Back to Stock Summary restoring
filters/page. Warehouse/batch breakdowns use registered, signed drilldowns and
existing report calculations when supported. No unscoped client-generated links.

Print/PDF prepares an actual single printable PDF with private inline preview.
Excel and CSV use the existing asynchronous export/artifact engine, complete
filtered rows and server-advertised capacity. PDF includes company/date/scope,
unit-separated totals, continuation headers and provenance. Excel includes its
report/provenance sheets; CSV preserves exact values and spreadsheet text safety.
Show progress, meaningful disabled reasons, retry, and separate split-PDF export
only when the supported result exceeds single-file capacity.

## 6. Delivery phases and exit criteria

| Phase | Work | Required exit evidence |
|---|---|---|
| 1. Contracts and source audit | Confirm current native/source gaps; freeze as-of/window, row grain, value allocation, capability and authority decisions. Define reusable Day Book presentation pieces. | Reviewed contracts and fixture truth table; every unsupported case has an explicit state. No activation implied. |
| 2. Inventory source producer | Implement complete fenced Accounting/Catalog evidence and readiness through existing transports; integrate real nonempty local owner data. | Nonempty and genuinely empty company snapshots reconcile; partial/torn/stale/replayed builds fail safely; historical cuts survive. Live inventory coverage is proven. |
| 3. Stock Summary API | Reuse/extend current calculations, typed readiness, full-result metrics, supported search/filter/sort/views and frozen pagination. Synchronize any changed contracts/clients. | Independent exact quantity/value fixtures and full-result search/paging pass; unsupported dates/capabilities fail clearly; strict bounds/index plans verified. |
| 4. Dedicated page | Existing URL/card renders Stock Summary; implement Day Book-style layout, automatic preparation, quick/advanced filters, totals, columns, saved views, source/status/history drawers and responsive recovery. | UI branch/accessibility tests; retained results, exact-reference verification, company/year changes, themes and narrow layouts pass. |
| 5. Access, drilldowns, print/export | Deliver the agreed authority projection/scope behavior, signed ledger/breakdowns and actual PDF/Excel/CSV files with private preview. | Wrong tenant/company, restricted warehouse, denied cost/field and revocation tests; all formats agree with full filtered results and preserve parent context. |
| 6. Final review and readiness | Review calculations, source completeness, performance, permissions, error/retry behavior and the whole Inventory-to-ledger journey. | Nonempty live browser evidence, real file opening/row-count checks, affected tests/coverage/type/lint/native-schema checks and final simplification/security review pass. |

Each phase includes its own tests and review; the repository remains working at
each boundary. Implementation begins only after this plan is agreed. Existing
posting/release activation remains separately governed.

## 7. Acceptance scenarios

- Opening 100, inward 40, outward 25 gives closing 115; summaries and exported
  rows agree independently of pagination. Selecting a shorter supported period
  must change opening/turnover correctly, rather than only changing its caption.
- A source-confirmed product with no positions appears as zero when requested;
  no inventory source shows a preparation blocker and never an empty result.
- Held/expired stock changes eligibility, not physical quantity. Unknown
  reservations/valuation never become zero or an invented availability/value.
- Internal transfer changes warehouse balances without inventing company sales;
  returns/reversals retain signed source lineage. Owned transit/third-party
  quantities and owned stock values remain distinct.
- Mixed units, parent locations, overlapping groups, warehouse/bin cost pools,
  zero quantity with remaining value, backdated changes and year rollover reconcile.
- Search finds an item beyond page one; row count, summary, drilldowns and all
  exports describe the same applied scope. Clear/reset restores the valid defaults.
- Scope/field/cost revocation cannot be bypassed through a saved view, summary
  card, source details, cached result, filter/sort, child report or existing download.
- Slow or failed discovery, verification, calculation, paging and export retain
  truthful state, accessible recovery and the correct idempotency identity.
- Desktop and mobile in all three themes remain readable; wide tables scroll
  within their report region; keyboard/focus/drawer and reduced-motion checks pass.

## 8. Decisions to agree before implementation

Recommended scope: complete source producer plus dedicated As-of Stock Summary,
full-result search/totals, supported drilldowns, PDF/Excel/CSV and access review.
Confirm the delivery timing of arbitrary From/To reporting and quantity-only/
restricted-warehouse authority in Phase 1; do not claim these capabilities before
their server/source contracts exist. Use existing costing and expiry policies.
Any unresolved residual value allocation or unsupported historical source date
stays explicitly unavailable pending a reviewed owner contract.

## Decision log

- 2026-11-01: user authorized all implementation phases and final review. Delivered
  the recommended complete-source As-of scope; see [delivery](stock-summary-delivery.md).
  Subsequent UI steering selected kebab row actions, essential default columns,
  a shared refresh/export action row and a calendar tied to verified snapshot dates.
- 2026-11-01: user requested a plan only. Reviewed the current route/screen,
  existing inventory consumers, live source evidence and Day Book interactions.
  Proposed reuse of the existing report engine with complete owner source
  delivery and a dedicated Stock Summary surface. No application implementation
  or activation authorized by this document.
