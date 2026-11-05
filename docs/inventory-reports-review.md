# Inventory reports sequential review

Execution evidence for [the authorized plan](inventory-reports-delivery-plan.md).
The record covers each report's plan, implementation, correctness review, UI/UX
review and real report/export journey. Final live passes use the same report order.

## 1. Stock Summary — complete

Preserved the reviewed Stock Summary calculations and source contracts. Reused
its existing page through the shared inventory workspace, with per-report
configuration for subsequent reports. Corrected the empty-selection heading so
stock results are not presented as a transaction list. Inventory default columns
apply only to inventory workspaces; existing Books retain their tested defaults.

Verification: 15 Stock Summary UI tests, 33 existing Native Book regressions,
12 Stock Summary calculation/API tests and focused application/test TypeScript
all pass. The empty-state test failed before its correction. Security and
correctness review retained tenant/company/actor/field authority, exact quantities,
unknown reservation behavior, immutable sources and private artifacts.

Live source preparation certifies 8 records and 3 actual zero-stock items. CSV,
Excel, PDF and HTML contain all 3 rows (621 / 7,388 / 33,489 / 2,134,632 bytes);
protected PDF preview matches the download. Light/Dark/Ledger at widths 1440 and
390 pass; menu/drawer leave row height unchanged. An expired QA browser session
was renewed using Windows-protected credentials, then the layout checks passed.
No live operational stock or financial records were fabricated.

## 2. Item Stock Ledger

Plan: dedicated item/period/warehouse/lot controls, exact per-position opening and
running quantity/value, recorded voucher references, retained-source batch lookup,
report-specific history, configured display and signed scope-preserving navigation.

Implemented the dedicated workspace, full-result opening/closing totals by unit,
owner and custody, readable transaction/opening labels, and signed frozen item,
warehouse, group and lot selectors. Corrected previous-month snapshot defaults
and From-date bounds. Running balances are counted once per position. Three UI
cases, calculation metrics, scoped selectors and six native MySQL run/export
cases pass. The initial live run encountered mixed running implementation
versions during staged changes; the final live pass passed after a synchronized
service/worker restart.

## 3. Warehouse Stock

Implemented calendar, warehouse/item selection, complete-result item/warehouse
search, essential columns and full-result totals. Parent selection includes each
descendant position once; units and third-party stock remain separate. The
dedicated UI case, warehouse metric regression and six native MySQL cases pass.

## 4. Stock Valuation

Implemented owned-position valuation, optional cost details and separate control
reconciliation rows. Totals exclude repeated cost detail and GL rows. Native
Accounting publishes reconciled residual FIFO layers or moving-average pools
where one physical position owns the complete pool; ambiguous allocations remain
unavailable. Added full-result source-grain search and corrected filtered GL
reconciliation scope. Four-format exports, details, permissions and the native
producer tests pass; the producer test failed before the cost-detail correction.

## 5. Batch Summary

Implemented frozen batch selection, balances and optional batch/serial history,
with current-position totals separated from audit rows. Lot drill-down now uses
the actual row lot even when the parent report has no explicit lot filter.
Search includes item, batch and warehouse labels. The UI case, physical/history
metric and drill regression, and native run/export cases pass. Unsupported serial
history coverage is explained instead of being treated as complete.

## 6. Stock Expiry

Implemented expired, near-expiry and required-but-missing expiry exceptions,
bounded days-ahead controls, complete-result search and recorded owned exposure.
Urgent dates sort first with stable position identity. Physical stock stays
visible even when expiry/holds make it ineligible. UI, exception metrics, date
boundaries and native run/export cases pass.

## 7. Stock Reorder

Implemented native Catalog company/warehouse replenishment bands with verified
effective fixed ordering-unit conversion to base quantities. Replenishment uses
an explicitly shown AVAILABLE or ELIGIBLE basis; eligible excludes reservations
and the page says so. Minimum, multiple and maximum orders are enforced, with
remaining target shortfall exposed. Company/warehouse bands can overlap, so
their quantities are not presented as additive totals. Unverified reservations
or orders cannot become zero. The report requires the existing
`item_warehouse_policy.read` permission. Positive scoped constraints, UI, native
Catalog definitions and native Reports exports pass. The live review found that
the worker authority allowlist omitted the newly required policy permission;
corrected the shared Identity/Reports contract. Five signed Identity authority
tests pass, including company-scoped grant and revocation. The configuration-empty
state now directs users to replenishment settings rather than implying a shortage.

## 8. Stock Ageing

Implemented receipt/manufacture date basis, ordered age bands, unknown/assumed
history and separate unit/owner/custody band totals. Native remaining receipt
origins now reconcile to physical stock under the posting fence; transfers keep
their original receipt date and unknown opening history stays unknown. The
native origin test failed before publication was added, then passed. UI, exact
age boundaries and Reports cases pass. A transient MySQL connection interruption
after the phase tests was followed by a passing final native suite.

## 9. Stock Movement

Implemented selected-period opening/inward/outward/closing, separate action
categories, full-result item search and genuine-consumption inactivity. Unknown
inactivity displays explicitly when retained history is insufficient. Item drill
now retains the requested From date. Unit totals use selected-period movements,
not repeated running balances. UI, period/drill metrics and native cases pass.

## 10. Stock Group Summary

Implemented group search/selection and group-to-item navigation. Overall totals
use the union of selected physical positions rather than adding overlapping
ancestor/child group rows. Ungrouped stock remains identifiable. UI, the overlap
regression, authority and native run/export cases pass.

## Combined review

- 199 UI/navigation checks: inventory workspaces, shared Books behavior, reference
  controls, report proxy, workspace, landing cards and report page authorization.
- 184 Reporting calculation/API/export/authority regressions pass.
- 81 disposable MySQL checks pass, including all ten run/page/drill/authority
  paths and CSV, Excel, HTML and PDF exports; migration/model/index parity and
  downgrade/upgrade also pass.
- Native Accounting source tests and Catalog source tests pass; strict affected
  Python and application/test TypeScript checks pass.
- Reporting contract 0.10.0 and its four consumers' lockfiles are synchronized.
  Retained 0.9.0 and earlier committed source hashes remain explicitly readable.
  Reports OpenAPI and API client 0.2.50 are synchronized.
- Manual equivalents of CLAUDE.md §5/§6, simplify and security review: no new
  datastore or operational posting path; exact Decimal quantities/costs, bounded
  source leases, signed cursors, company/tenant/actor authority and private
  exports preserved. The slash commands are unavailable in this environment.

## Final live review

All ten reports pass actual protected CSV, Excel, HTML and PDF exports (40 files),
and each PDF preview matches its download. The live browser card-to-report loop
passes calendars, completed report history, private saved-view create/restore/delete,
Columns menus, available row detail drawers and all three themes at 1440/390 pixels.
No browser exceptions or horizontal page overflow were found. Result-area visual
inspection passes for all ten reports in Light, Dark and Ledger at desktop/mobile
widths. The final live journey also verifies invalid snapshot date guards,
full-result search, warehouse drill/return with column restoration, changed-filter
saved-view restoration/deletion, retained snapshot discovery and completed history.
Stock Group Summary's search label now correctly says Search groups.

| Report | Live rows | CSV / Excel / HTML / PDF |
|---|---:|---|
| Stock Summary | 3 | Pass |
| Item Stock Ledger | 0 | Pass |
| Warehouse Stock | 0 | Pass |
| Stock Valuation | 0 | Pass |
| Batch Summary | 0 | Pass |
| Stock Expiry | 0 | Pass |
| Stock Reorder | 0 | Pass |
| Stock Ageing | 0 | Pass |
| Stock Movement | 3 | Pass |
| Stock Group Summary | 0 | Pass |

Final fixes also corrected a Windows file-encoding fault in the shared workspace;
the source is valid UTF-8, Next compiles and 60 affected workspace/Books tests pass.
Managed services/workers were restarted with the synchronized source contract.
Elevated launchers were stopped cooperatively only after verifying workspace,
exact process start time and listener ancestry.

Operational data in the live company remains unchanged. Positive stock, cost,
receipt-age, replenishment, scope and export cases use disposable native schemas;
the live company's genuine zero stock is not replaced with QA postings. Unknown
reservations, order coverage and inactivity are shown explicitly. Replenishment
ordering units currently require verified effective fixed conversion; unsupported
measured conversions do not produce invented quantities.
