# Analytics reports delivery

Authorized 2026-11-02: implement the five agreed business reports, one at a time,
with review and fixes. Existing project paths and unrelated work are preserved.

The 2026-11-03 completion pass covers all eight reports on the Analytics page,
including the three accounting controls. Its plans, fixes, calculation version 3
and verification are recorded in [analytics-completion-review.md](analytics-completion-review.md).

The subsequent addition of Party (buyer) wise profit and Product wise profit,
including product groups, is recorded in
[buyer-product-profit-reports.md](buyer-product-profit-reports.md). Analytics now
contains seven business reports and three accounting controls.

## Agreed loop

For each report: (1) define measures and boundaries; (2) verify source evidence;
(3) implement calculations and frozen execution; (4) implement the shared page;
(5) reconcile, test native/API/UI/export behaviour, review and fix findings.

| Order | Report | Status |
|---|---|---|
| 1 | Sales performance | Implemented and reviewed |
| 2 | Profit and margin analysis | Implemented and reviewed |
| 3 | Customer insights | Implemented and reviewed |
| 4 | Expense and profit leakage | Implemented and reviewed |
| 5 | Cash and working capital | Implemented and reviewed |

## Shared decisions

- Reuse the existing Reports registry, immutable source cuts, job/authority
  lifecycle, result search, drill-down, private PDF/XLSX/CSV/HTML artifacts and
  Console report workspace. Keep accounting controls in their existing section.
- Posted transactions govern all business periods. Comparison dates are explicit
  and retain their own values. Exact Decimal arithmetic; ratios recompute from
  operands. Undefined ratios and missing evidence remain unavailable.
- Invoice analytics is grouped by original document currency. GL profitability
  and cash movements use the company base currency. No invented FX conversion or
  addition of currencies. Inventory quantity remains separated by base unit.
- Sales commercial values already reflect discounts and returns. Diagnostic
  discounts/returns are never subtracted again from company profit.
- Product joins require the accepted invoice supply's common item-line identity
  and the retained stock movement's line identity, voucher and item evidence.
  Existing owner storage already retains these identities. Add optional typed
  feed fields; legacy facts stay readable and missing historical links remain
  explicit. No database schema change is needed for this transport extension.
- Native financial aggregates reuse daily projections; bounded invoice/history
  components pin company, epoch and sequence. No owner database access from Reports.
- Customer activity is based on recorded history, not predicted churn/lifetime
  value. First observed is not claimed to be first ever. Anonymous sales remain
  separate. Inactivity and exception thresholds are visible parameters.
- Cash movements, outstanding obligations and owned stock tied up are separate.
  Snapshot dates/completeness are explicit; due dates are not collection promises.
- All input permissions and field denies are enforced by the existing complete-
  input authority. Bank/stock views require their additional source grants.

## Verification and findings

Record each completed phase, native/API/UI checks, export/browser evidence,
security/simplification findings and remaining live-data limits here.

The 2026-11-02 final review and fixes are recorded in
[analytics-reports-final-review.md](analytics-reports-final-review.md). The review
covers each native report view, exact monetary reconciliation, retained history,
permissions, shared workspaces and actual private exports. New runs use
calculation version 2; existing frozen results remain unchanged.

### Analytics landing page — 2026-11-02

The Analytics menu opens `/reports/analytics` through the existing category route.
Its Business analytics section contains Sales performance, Profit and margin
analysis, Customer insights, Expense and profit leakage, and Cash and working
capital. Each card opens its own report workspace; the page shares report search,
responsive cards, breadcrumbs and category navigation with the other report menus.

Review found that loading or an unavailable Reports service hid all five business
cards. They now remain visible as disabled previews during loading and server
failure, with the existing retry action. A successful company catalogue still
hides excluded analytics reports; 401/403 responses keep protected cards hidden.
Unavailable previews never receive report links or expose financial values.
Legacy catalogue assertions were updated for the five analytics reports and two
GST returns already present in the workspace. This landing-page work does not
complete the wider report verification interrupted by the Python process stop.

Landing-page verification: 55 tests passed across the Analytics catalogue,
report-card connection, reports hub and reports page suites. Console application
and affected test types passed. Manual permission and simplification review found
no additional issues: previews contain no navigable report link, 401/403 responses
hide protected cards, and changing company clears previous catalogue availability.
