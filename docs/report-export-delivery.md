# Report export reuse and delivery

Requested 2026-11-01: Day Book must export PDF, Excel and CSV, reusing existing
implementation and centralizing missing mechanisms for other reports.

## Plan and todo

- [x] Phase 1: inspect available report renderers, job APIs, private downloads and consumers.
- [x] Phase 2: centralize browser export tracking, format availability/limits and download links;
  reuse these in Day Book and existing report workspaces.
- [x] Phase 3: verify all formats and both Day Book views, progress/recovery, permissions and
  actual downloads; review and fix findings.

## Decisions

- Reuse the Reports framework's existing CSV/XLSX/PDF writers, Celery export jobs and
  private artifact storage. Reuse the console's streaming `/api/report-download` route.
  There is no second renderer or browser-side reconstruction of financial rows.
- Export all matching rows from the completed report, using its frozen filters, currency,
  display configuration and current view. Pagination does not limit the exported rows.
- PDF is the printable presentation. Excel is a real `.xlsx` workbook, with exact-value
  policy and an About sheet. CSV is UTF-8 with canonical dates and decimal values.
- Server-advertised format and capacity limits remain authoritative. Show PDF/Excel/CSV
  explicitly, with a reason when a format is unavailable or the completed result is too large.
  Do not silently truncate a report or export only its visible page.
- Posted book is a verified snapshot and supports exports. All vouchers is live document
  activity; its UI must explain how to reach the exportable posted report.
- Keep report-specific filters/calculations in their owners. Reuse the browser mechanism
  for tracking export jobs, capacity decisions and private download/preview links across
  Day Book, the generic report workspace and opening-balance continuity reports.

## Verification and review

- Reused existing server writers/jobs/private storage and the streaming download route.
  No new renderer, service, migration, storage adapter or API schema was introduced.
- Central browser mechanism: `mfes/apps/console/app/lib/report-exports.ts`, used by Day Book,
  all nine native Books, FrameworkReports and opening-balance continuity. Shared UI
  Menu/Button/Notice primitives
  supply export presentation; no duplicate styles or app-specific export component were added.
- Reviewed and fixed missing-format visibility, complete-result row/cell limits, incompatible
  views, document-part limits, private single-PDF preview eligibility and download-link encoding.
- Pinned-query Books supply their verified full-result summary count to the shared capacity
  check because their materialized-row count is intentionally zero.
- Completed export links now disappear when export permission is removed. Generic report
  screens also abort status tracking after revocation. Server access checks remain authoritative.
- Status polling is sequential and abortable. Navigation/company changes cannot apply late
  status responses; timers are cleaned up. After a status-read failure, retry resumes the known job rather than submitting a
  duplicate file job. Uncertain initial submissions retain their original idempotency key.
- UI tests wait for asynchronous effects while local services share the runner's CPU;
  report and renderer timeouts in the application were not increased.
- Manual simplify/security review covered field/current-access enforcement in reused APIs,
  report/view binding, exact decimal policies, spreadsheet text safety, private streaming,
  encoded links, status-job identity and stale-request cancellation. No financial calculation,
  authorization policy or credentials were added to the browser.

## Final verification

Native Books follow-up (2026-11-01): the same mechanism now serves Cash, Bank, Sales,
Purchase, Payment, Receipt, Account Ledger, Party Ledger and Stock Ledger. A parameterized
workspace test prepares CSV, XLSX and a private single-PDF print preview for every route.
The focused console selection passed 57 tests, strict TypeScript passed, and the existing
Reports artifact/renderer suite passed 15 tests. Split PDF ZIP delivery remains an export
choice; the dedicated Print / PDF action always requests a previewable single PDF.

- Console: 116 tests passed across five affected suites: Day Book 41, report workspace 22,
  balance continuity 13, shared export mechanisms 14 and private download route 26.
  The initial 115-test run passed; the final Day Book run adds the verified known-job retry
  regression. Missing-format, capacity, permission and duplicate-job bugs were reproduced
  with failing tests before fixes.
- Reports API/renderer checks: 27 passed. The six Day Book cases cover PDF/XLSX/CSV in both
  voucher and accounting views, full-result row counts, exact debit/credit totals, idempotent
  export submission and current-access denial. The strengthened six-view/format checks passed
  again, including exported job counts and actual Excel worksheet row counts.
- Browser regression: 33 checks passed across the existing 15 viewport/theme combinations,
  progress/failure states, filters, retained results, drawer focus/scrolling and reduced motion.
  No JavaScript errors. Console TypeScript and Ruff passed; whitespace checks are clean.
- Authenticated local UI: all six real downloads passed, with correct MIME types, filename
  extensions and file signatures. Both PDF previews returned the same authorized private
  route in inline mode. Each downloaded CSV/Excel/PDF was independently opened; Excel/CSV
  row counts agree and both PDFs contain Day Book. The existing QA period is empty;
  the nonempty API fixtures verify four voucher activity rows/eight accounting lines and
  exact 460.0000 debit/credit totals through the same writers.
- Private evidence: `.test_artifacts/report-export-20261101/exports.json`,
  `file-validation.json`, six downloaded artifacts and authenticated screenshots.
  Runner logs: `.tools/report-export-ui-final.log`, `report-export-daybook-final.log`,
  `report-export-api.log`, `report-export-views-final.log`, `report-export-tsc-final.log`,
  `report-export-ruff.log`, `report-export-browser.log` and `report-export-live-final.log`.
- Review complete; no pending implementation task remains. Existing deployment admission,
  private-storage requirements and published renderer/capacity limits still apply. Live
  All vouchers remains document activity; exportable accounting reports are in Posted book.

## Live all-books follow-up decision (2026-11-01)

All ten Books entries were audited. Nine passed 27 real PDF/Excel/CSV downloads, private
inline preview and independent file/header/row-count validation. The shared Native Books
consumer now prepares initial reports automatically within the selected snapshot's
available history, waits for required references, preserves manually chosen periods and
aborts requests on exit. Print/export continues through the existing frozen jobs and
owned artifacts; no renderer or financial algorithm was replaced.

Stock Ledger's PDF/Excel/CSV exports pass with genuine complete API fixtures. The live
company is blocked: even after a successful source refresh, Accounting supplies zero
inventory reporting records. The workspace explicitly describes this dependency and
does not create a false empty result. Complete stock source coverage remains pending
upstream. Full evidence and the current delivery boundary are recorded in
[books-print-export-review](books-print-export-review.md).
