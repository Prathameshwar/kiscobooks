# Financial-year start and balance-continuity delivery

Date: 2026-10-26. Scope: the approved six-phase UI/API plan for starting the next
financial year in the same company and reviewing balances carried by retained history.

## TODO

- [x] Phase 1: inspect existing calendar, readiness, selection and report contracts.
- [x] Phase 1: record the workflow, ownership and acceptance cases below.
- [x] Phase 2: company-scoped next-year preview and affected API checks.
- [x] Phase 3: guided generation/readiness/open/select UI, navigation and recovery tests.
- [x] Phase 4: selected-year defaults and explicit custom dates in both report interfaces.
- [x] Phase 5: verified continuity report, search, paging, drilldowns and exports.
- [x] Phase 6: OpenAPI/client/documentation synchronization and affected checks.
- [x] Review 1: accounting, authorization, scope, concurrency and recovery; fix findings.
- [x] Review 2: navigation, accessibility, messages, responsive layouts and themes; fix findings.
- [x] Isolated two-year rehearsal and final evidence record.

## Agreed implementation contract

Accounting owns the immutable calendar, next-year preview and individual audited
generation/period commands. Reports owns reconciled immutable source generations,
continuity calculations, row tokens and exports. Console composes these capabilities;
it does not invent balances, posting dates or authority.

The journey is Review next year → Generate or reuse → Check prerequisites → explicitly
open selected future periods → explicitly Use this year. An existing source year is
company scoped; absent selection falls back to the latest readable company year. The
generic generator remains available for earlier/missing years. An old year need not be
closed. Selection is browser display/filter context, never a document posting date.

Every generation and transition retains its idempotency key across unconfirmed results.
Opening several periods is a recoverable sequence of existing individual commands, not
a cross-service transaction. Refresh shows completed steps; a failed step never causes
closed/locked periods to reopen. New-year prerequisite results do not certify tax,
numbering or every voucher producer. Existing release activation gates remain intact.

Continuity compares the previous calendar year's final day with the next year's opening
before its first movement, using one source generation, exact Decimal arithmetic and
the same frozen classifications. The generation must cover the original books and both
calendars. Account/bill/advance identity and original due dates survive year boundaries.
Prior accumulated earnings and current-year profit remain separately derived. No annual
opening journal, account copy, balance overwrite or profit-transfer journal is created.

Report defaults follow the selected year. Explicit custom dates are preserved; changing
the company discards the previous company's report state. Retained report parameters and
results remain unchanged when another year is selected or older history is adjusted.

## Acceptance and review evidence

Required cases: fresh and existing target years; incomplete books/calendar/openings;
inactive companies; read-only and denied fields; wrong-company source/target/snapshot;
double submission, lost response, interrupted multi-period operation and stale versions;
custom report dates and company/year switching; prior closing equals next opening;
cross-year bill allocation/advance continuity; next-year P&L excludes previous activity;
separate accumulated earnings; incomplete coverage; immutable previous report runs;
bounded pagination and signed drilldowns/exports; keyboard and all three themes.

Evidence and findings will be recorded here as each phase finishes. Concurrent unrelated
workspace edits are preserved. Application schema changes, if required, ship with matching
models/migrations/scripts; API changes ship with OpenAPI and generated clients.

### Phase 2 evidence

Added a read-only next-preview API with explicit source-year object scope, frozen
calendar derivation, target reuse, overlap/calendar/configuration blockers and permission
hints. The original missing-endpoint regression failed first. Accounting: 19 fiscal/API
checks passed initially; one new field-policy fixture used the wrong wire shape and was
corrected, then that check passed separately (20 total). Ruff and strict mypy passed.
Accounting OpenAPI and generated TypeScript contracts have been refreshed.

### Phase 3 progress

The original-year suggestion regression failed first with 2026 instead of the requested
2027; the generator now uses the API proposal. The guided flow opens explicitly selected
future periods, preserves confirmed steps and retry identities, and requires explicit
year selection. Its first verification passed 105 Console tests across workflow, existing
fiscal UI and company request policy. Navigation and final review remain in progress.

### Phases 4–5 evidence

Both report interfaces follow selected/previous financial-year presets and retain explicit
custom dates across year changes and browser reloads. The initial date-hook tests passed
four cases; both existing interfaces passed their initial 22 checks. Report labels explain
prior accumulated versus current-year earnings.

The continuity report compares complete consecutive calendars using one verified source,
retained Decimal balances and original bills/advances. Initial domain/registry checks:
83 passed. Native-query reference parity and the scoped API/search/signed bill drilldown/
CSV-export checks passed separately. Console initially passed eight continuity cases;
search timing and duplicate alert semantics were exposed and corrected before review.

### Review 1 — complete

Money/security review has checked retained-history semantics, incomplete source coverage,
calendar consistency, input/field/object scope, revoked authority, idempotent recovery,
signed child actions and export ownership. Fixes include rejecting monthly grain for the
full-year continuity contract and ignoring superseded/aborted row requests. The review
also found a source calendar whose start could disagree with the company anchor while
its end appeared valid. Preview now checks the complete source span; the regression passes
on both SQLite and MySQL. Frozen continuity refuses the same malformed prior calendar.
No unresolved scope, money, audit or retry findings remain in this delivery.

The repository requests `/simplify` and `/security-review`. Neither command is exposed
by the available tools in this session (capability lookup returned no matching tool), so
equivalent manual reviews of CLAUDE.md sections 5–6 and affected code were completed.

### Review 2 — complete

UX findings fixed: result source captions use the completed run's source rather than the
next source selection; refresh success uses an informational notice; source lists expose
bounded older-snapshot loading; export buttons enforce both row and cell limits; drilldown
exports do not borrow continuity limits; exports offer cancel/retry; next-year permission
messages state both required permissions. Regression checks cover these findings and
breadcrumb discard confirmation. Periods use the existing responsive paired grid, and
the reason control respects denied write access. Back-link labels follow the actual
return destination. Real components passed 12 Edge checks: both pages in light, dark and
ledger themes at 1440 px and 390 px, with no document overflow or page errors. Keyboard
validation focuses the reason field; kebab actions open and Escape closes the menu.
Screenshots were inspected. Preview-only fixture corrections supplied the application's
shared root/background classes and complete frozen display settings. No application CSS
was added. No unresolved UI findings remain in this delivery.

### Phase 6 and final verification

- Console: 169 tests passed across fiscal UI, readiness, reports, request policy and
  navigation. Subsequent layout/return-label fixes passed the affected 23 workflow cases
  and the final 13 continuity cases. Console TypeScript checking passed.
- Reports: 119 statement/registry/native/drilldown/retained-runtime checks passed;
  the final 9 continuity domain cases also passed, including frozen calendar rejection.
- Accounting: 21 cases passed in the expanded fiscal batch; the remaining rehearsal
  assertion initially used an unfilterable test count. It was corrected to count the ORM
  ID under tenant scope, and the case passed separately. Domain/API Ruff and strict mypy
  checks passed. Reports Ruff and strict mypy checks passed.
- Native MySQL: Accounting's original 20 fiscal/preview cases passed, Reports' two
  native continuity/scope/search/signed-drilldown/CSV cases passed, then two final Accounting
  calendar/two-year cases passed. Tests used random `*_test_<uuid>` schemas on the separate
  loopback server at port 13396, with migrations applied first and FK checks retained.
  Only task-owned schemas were removed, and the disposable server was stopped afterward.
- Two-year rehearsal: both years are posting-ready concurrently; exactly two fiscal years,
  24 periods, one original zero-opening batch and zero annual journals remain. Separate
  financial-source cases retain the same carried bill, its due date, advances and earnings;
  a later next-year allocation changes the existing bill rather than recreating it.
- Accounting/Reports OpenAPI checks and generated client checks passed. API client bumped
  to 0.2.30; its eight transport tests and TypeScript check passed. Workspace lock verification
  passed; directory-based dependency resolution required no lock content change.
- Live read-only schema comparison found zero model/schema differences in Accounting and
  Reports, at migration heads 0167 and 0038. No DDL, model or seed changes were required.
- Reviewed Accounting and Reports were gracefully reloaded through the existing managed
  launcher. All 12 infrastructure/API readiness checks reported UP. Whitespace check passed.

### Where the user opens the workflow

Company settings → Financial years → **Start next financial year**. The year-list kebab
can start from a specific source year. Year details and readiness cards link to
**Review opening balances**. Source refresh/run/export actions honor existing permissions
and deployment activation; the UI gives a clear handoff when these are unavailable.
Deferred producer/stock/tax gates remain unchanged. No real company was transitioned.
