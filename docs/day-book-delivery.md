# Day Book workspace delivery

Approved scope: direct Books → Day Book navigation, professional responsive report UI,
typed filters, full-result totals/counts, voucher/accounting views, drill-through,
saved views, export/print, tests and final review. User authorized all phases without
intermediate confirmation on 2026-11-01. No publication requested.

## Todo

- [x] Phase 1: inspect report/source contracts and agree row/count/amount semantics.
- [x] Phase 2: direct navigation and shared responsive styling.
- [x] Phase 3: quick/advanced filters, URL state and personal saved views.
- [x] Phase 4: frozen posted voucher/accounting results, live document activity and summaries.
- [x] Phase 5: drill-through, permission-aware creation, export and report printing.
- [x] Phase 6: affected unit/integration tests, browser/accessibility/theme review and fixes.

Each phase includes review and fixes. Evidence and remaining limitations are recorded below.

## Follow-up UI and experience review

Requested 2026-11-01 after the six delivery phases:

- [x] Review initial load, report refresh, pagination, source preparation and export progress.
- [x] Fix confusing empty/error states, recovery actions and retained-result messaging.
- [x] Inspect spacing, alignment, long content, keyboard focus and responsive layouts in all themes.
- [x] Run regression tests and browser checks; record findings and fixes.

### Findings and fixes

- Added one accessible progress announcement for source discovery, report generation,
  refresh, page loading, source preparation and each export format. Existing results stay
  visible during updates; export preparation does not mark the report as loading again.
- Cold loads show placeholders and pending results instead of a false ready screen or zero
  count. Failures and disabled workers have an unavailable state; completed empty reports
  retain their separate empty state. Every path into posted generation respects worker
  availability, including scope changes. Live voucher activity remains available.
- Failed pages retry that page; failed exports retry that export, preserving the command
  identity after an uncertain submission. Recovery retains the current rows and totals.
  Reset filters now clears and applies the filters, including empty-state recovery.
- Status and transaction-currency chips expose active filters when mobile controls are
  collapsed. Long mobile voucher numbers wrap inside their entries instead of being clipped.
- Desktop filter controls share a measured baseline and height. Advanced mobile filters
  scroll with a visible action footer at 320px and 390px. New conditions receive focus;
  removing a condition focuses the next/previous value or Add condition. Escape closes
  the drawer and restores the opener, including at the eight-condition limit.
- Native date controls follow the selected theme, fixing low-contrast calendar icons in
  dark mode. The browser review checks their computed native color scheme.
- Reviewed all three themes, narrow and desktop layouts, retained-result messages and
  reduced-motion behavior. The existing shared reduced-motion rule ends animations after
  one near-instant iteration; no additional animation override was necessary.
- Manual simplify/security review covered operation guards, exact retry payloads and
  idempotency behavior, stale-request cancellation, scoped styles, escaped text and
  accessibility announcements. This follow-up changes no backend authority or money logic.

### Follow-up verification

- Console regressions: 128 passed across six affected suites (34 Day Book tests, including
  nine new regressions; 94 related navigation, report, reference and download checks).
  Shared style checks: 2 passed. Bugs were reproduced with failing tests/browser assertions
  before their fixes. UI test readiness now waits for settled React effects.
- Browser review: 33 checks passed, including 15 viewport/theme combinations from 320px
  to 1440px, long-content bounds, loading and queued reports, export progress, errors,
  aligned controls, mobile drawer scrolling, focus restoration and reduced motion.
  Dark-theme native date controls were checked at every viewport. No JavaScript errors.
- Authenticated local posted-report and live-voucher checks passed with no browser errors.
  The earlier full CSV/Excel/PDF download and print-preview evidence remains applicable;
  this follow-up did not change artifact delivery or financial calculation.
- Console TypeScript passed after the final component changes. Shared UI is 0.1.47;
  lockfile refresh passed and its workspace links required no change.
- Evidence: `.tools/day-book-ux-final-unit.log`, `day-book-ux-related.log`,
  `day-book-ux-style.log`, `day-book-ux-tsc-final.log`, `day-book-ux-browser-final.log`,
  `day-book-ux-live.log`, and `.tools/day-book-review/review.json` with screenshots.
  Authenticated follow-up evidence remains under ignored
  `.test_artifacts/tenant-admin-20261029/live/` (`day-book-live-*` screenshots and
  `live-documents.json`).
- No follow-up UI review tasks remain open. Existing runtime/capacity limits below apply.

## Export reuse follow-up

The subsequent PDF/Excel/CSV delivery reuses the existing report engine and centralizes
browser export options, status tracking and private links across three report screens.
All formats and both Day Book views were verified through actual authenticated downloads;
format limits, permissions and known-job retry recovery were reviewed and fixed.
See [the completed export plan and evidence](report-export-delivery.md).

## Decisions

- Posted book uses a new versioned `DAY_BOOK_ACTIVITY` definition in the existing Reports
  framework and Celery worker. Existing DAY_BOOK definitions/runtimes remain readable.
  Calculation uses verified, bounded Accounting source generations and exact Decimal
  arithmetic. The ordinary user sees freshness, not source UUIDs or execution controls.
- One activity row per source voucher (or standalone journal) and posting day. Multiple
  events on one day remain separately identifiable in expanded details. Events on later
  days, including reversals, keep their actual daily totals. Accounting view uses journal
  lines. Distinct voucher, daily activity row, journal and line counts are separate.
- Party/account filters select whole matching journals before voucher grouping; complete
  entries remain in totals. All filters apply before pagination. Summaries are retained
  in the completed job evidence, covering all matched results.
- Posting date determines posted-book inclusion; live document activity uses document
  date. Both are explicitly labelled. Selecting an older financial year defaults to that
  year's last day, rather than silently selecting today's date outside it.
- Base currency is the default. Transaction currency requires an explicit currency and
  selects only that currency's entries; mixed-currency journals can appear unbalanced in
  that view. Both the UI and export context identify this scope.
  No aggregate combines unrelated currencies or document values across voucher kinds.
- All vouchers is explicitly live, sourced from the Vouchers service with its own current
  permissions, current revision, filters, cursor and opt-in summary. It is not a frozen GL
  snapshot and offers no invented debit/credit totals. This distinction is necessary
  because Accounting snapshots do not contain drafts or unexecuted documents.
- Saved views are personal browser preferences scoped by actor and company; no report
  rows or credentials are stored. URL filters and report IDs support return navigation.
- Exports and printing use the authorized completed report and existing private report
  artifact pipeline. Report printing is separate from individual voucher designer layouts.
- Styles live in the shared UI package and use design tokens in all three themes.

## Review evidence

- Direct-route regression was verified failing before implementation, then passing.
- UI/route unit tests: 255 passed across ten affected suites, including parameter-bound retained runs, exact page
  restoration, explicit Apply, retries, permission-gated actions and safe back navigation.
- Browser review: 15 viewport/theme combinations (320–1440px, light/dark/ledger), no
  document overflow or JavaScript errors. Compact desktop filters and mobile disclosure
  were added after visual inspection. Expand/collapse, drawer Escape, accounting mode
  and live scope were exercised. Fixture browser evidence: `.tools/day-book-review/`.
  The final run passed 20 checks, including the drawer's fully opaque settled state.
- Shared Day Book style checks: 2 passed; console TypeScript check passed.
- Vouchers API tests: 23 passed, including current-revision counts, keyset cursors,
  literal wildcard search, field denies and company/tenant isolation.
- Reports domain/API/worker/export checks: 33 passed, plus 84 existing framework
  regression tests. New domain coverage is 98.26% (90% required).
- Disposable native MySQL verification: 30 Reports and 17 Vouchers tests passed after
  full fresh migrations. The existing local databases needed no migration.
- Ruff and strict mypy passed for the changed Python modules. OpenAPI/client freshness
  and report presentation bundle checks passed.
- Local QA source/authority credentials were configured for exactly the authenticated
  QA company, using existing owner and worker contracts. Existing local databases were
  already at migration heads. No financial posting flag changed. Private environment
  backups and live browser evidence: `.test_artifacts/day-book-delivery/` (ignored).
- Authenticated local browser: direct navigation, completed verified report, actual private
  CSV/Excel/PDF downloads, authorized inline PDF preview, and completed live-document
  query passed with no JavaScript errors. Evidence: `delivery.json` and
  `live-documents.json` in that private directory. The QA date had no matching documents;
  nonempty amounts, lineage, multiple posting days and pagination were verified by the
  native integration tests and browser fixtures.

## Final review and fixes

- Reviewed the security and accounting invariants in CLAUDE.md sections 5 and 6.
  `/simplify` and `/security-review` commands were unavailable in this session, so their
  review was performed manually: authority and field-deny enforcement, company/tenant
  isolation, exact arithmetic, posting dates, cursor ownership, stale request cancellation,
  retained-run/filter binding, escaped output and private download authorization.
- Fixed direct card navigation, newest-first date grouping, ledger-name searches when
  particulars show a party, daily attribution of later postings, and misleading grouped
  count labels. Added verified full-result context/totals to Excel and PDF output.
- Fixed stale export download notices after failure, PDF preview delivery, terminal
  quarantined-source recovery, type-filter resolution from URLs, revision-field read
  denies, and refresh cancellation. Regression tests cover the fixes.
- Visual fixes include aligned filter fields, persistent period preset selection, tighter
  desktop spacing, mobile filter disclosure and touch targets, themed drawer surfaces,
  accessible table captions, and frozen report formatting in the kind breakdown.
- No outstanding defect found in the delivered scope. The runtime/capacity constraints
  below remain explicit; production credentials and deployment are environment setup.

## Runtime and capacity

- Requires existing Reports framework, versioned owner sources, fresh Identity authority,
  private artifact storage and report worker lanes. Local credentials are scoped to the QA
  company; production must provision its own identities and allowed company scopes.
- This definition uses the existing bounded materialized reference worker. Its configured
  source-fact/result/export limits apply; capacity failures never publish partial totals.
- CSV retains canonical values and all standard result columns. Excel adds an About sheet
  with context and summary. PDF is the printable company report. Live document activity
  has status counts; export/print belong to the verified Posted book snapshot.
- Saved views are personal browser preferences, not shared or server-backed records.
