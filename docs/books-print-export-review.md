# Books print and export follow-up

Requested 2026-11-01: resolve disabled Print / PDF actions for every book and
verify actual print/export functionality one book at a time, including Day Book.

## Delivery sequence

1. Audit report readiness, advertised formats, protected export APIs and live
   behavior for all ten Books routes.
2. Fix the shared preparation/export flow and any book-specific findings using
   the existing Reports jobs, frozen results, PDF/Excel/CSV renderers and private
   download route. Verify each book before moving to the next.
3. Review real downloaded files, print previews, filters, full-result coverage,
   limits, permission/revocation behavior and failure/retry handling. Run affected
   UI/API/rendering checks and record per-book evidence.

No alternate renderer, browser reconstruction of accounting rows, new service or
storage migration is planned. Existing export admission, capacity, company scope
and field-read enforcement remain authoritative.

## Status

- [x] Audit all ten books and identify the live disabled-control causes.
- [x] Complete shared preparation fixes and explain required selections/source blockers.
- [x] Verify live PDF print preview and PDF/Excel/CSV downloads for nine books.
- [x] Verify Stock Ledger PDF/Excel/CSV using complete, nonempty API fixtures.
- [x] Review permissions, failure/retry behavior and full-result coverage.
- [x] Complete tests and final simplification/security review.
- [ ] Live Stock Ledger print/export: requires genuine complete inventory source
  coverage from Accounting. A fresh READY snapshot still has zero inventory records.

## Findings and decisions (2026-11-01)

The non-Day-Book workspaces initially waited for Apply and defaulted to the financial
year start, 2026-04-01. This company's verified history starts on 2026-10-31. Applying
the original defaults produced `REPORT_VERIFICATION_FAILED`, so there was no completed
run to export. Cash Book succeeded immediately when its period was within coverage.

The shared workspace now reads the selected READY generation's existing detail API,
initializes the period within its available history, and prepares the initial run once
required parameters and retained references are verified. Explicitly edited dates are
preserved for owner-side historical/YTD verification. A failed automatic run is not
repeated, and leaving the workspace aborts the active request. Refresh updates the
history hint without replacing user filters. Export writers and financial calculations
are unchanged.

The final delayed-reference regression found that a boolean readiness flag could still
describe the previous empty selection when a new item was chosen. Readiness now records
the verified identifier and must match the submitted filter; an automatic run waits
until that exact reference finishes verification.

Stock Ledger additionally requires a selected stock item and complete inventory
evidence. The protected refresh request and source worker completed successfully, but
the refreshed manifest still reports `inventory_report_record: 0`. The UI now explains
this dependency and disables preparation rather than claiming an empty stock book.
Selecting a verified item automatically prepares a ledger when its source is available.
The existing PDF/Excel/CSV machinery passes with nonempty, complete stock fixtures.

The complete inventory source producer is a separate delivery boundary documented in
[inventory-final-review](reports-framework/inventory-final-review.md#remaining-delivery-boundary)
and [the native stock decision](voucher-stock-recording-reporting-design.md#native-stock-implementation-decision---2026-10-28).
Refreshing financial data cannot manufacture that missing coverage. No stock balances,
opening quantities, coverage records or release gates were invented or changed.

## Per-book verification

| Book | Live PDF and private print preview | Live Excel / CSV | Retained rows |
|---|---|---|---|
| Day Book | Passed | Passed | 0 |
| Cash Book | Passed | Passed | 1 opening row |
| Bank Book | Passed | Passed | 0 |
| Sales Book | Passed | Passed | 0 |
| Purchase Book | Passed | Passed | 0 |
| Payment Book | Passed | Passed | 0 |
| Receipt Book | Passed | Passed | 0 |
| Account Ledger | Passed | Passed | 12 opening rows |
| Party Ledger | Passed | Passed | 0 |
| Stock Ledger | Pending complete owner source; API fixtures passed | Same | No live result admitted |

All 27 live files were downloaded through the authenticated private route. PDFs have
the correct signature, company, report title and period; inline preview returns identical
bytes. CSV/Excel headers and row counts agree; Excel ZIP integrity and the provenance
worksheet pass. Desktop (1440) and mobile (390) screenshots were inspected, with no
horizontal page overflow. The live period has no posted transaction activity; nonempty
API fixtures verify retained rows, exact amounts and stock movements.

## Checks and evidence

- Console: 167 tests across seven affected suites; Native Books includes 33 tests.
  New regressions first failed for automatic preparation, required-item guidance,
  refreshed-history guidance and missing inventory evidence. Strict TypeScript passes.
- Reports: 82 unique checks passed, one MySQL-only check skipped: 25 renderer/
  presentation/identity/Day Book cases, 27 frozen-export/private-download/inventory
  cases, two Stock Ledger scope/paging cases and 28 ledger/invoice/tender cases.
  These cover nonempty data, current-access revocation, full-result exports, capacity
  rejection, retry/storage failure and owned artifact publication. The broader native
  gate initially had two stale Payment/Receipt evidence assertions: rows matched,
  but expected evidence omitted the existing book summary. Exact 40.0000/150.0000
  summary/count expectations were added; all ten native bank/tender cases then passed.
  Strict TypeScript, changed-test Ruff/format checks and whitespace checks pass.
- Manual simplification and security/invariant review: no unresolved issue in this
  change. Existing scoped APIs, field authorization, retained-view binding, exact
  decimals, private download tokens, current authority and capacity limits remain
  authoritative. Source history is advisory; manually selected dates still reach
  server verification. No schema/API contract or financial posting policy changed.
- Private evidence: `.test_artifacts/books-print-review/exports.json`,
  `file-validation.json`, `stock-source-review.json`, downloaded files and screenshots;
  final UI log: `.test_artifacts/books-ui-final.log`. Credentials are stored only in
  ignored Windows-protected QA storage.

The Books consumer changes are complete. Live Stock Ledger printing/export remains
pending the genuine upstream inventory source delivery; it is not certified as passed.
