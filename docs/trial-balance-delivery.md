# Trial Balance delivery

User authorization (2026-11-02): implement each phase of
[the agreed plan](trial-balance-implementation-plan.md) in order, then review and fix
findings. Closing balances is the default; Detailed shares the same frozen result.

## Status

- [x] Phase 1: contracts and baseline.
- [x] Phase 2: calculations and frozen hierarchy.
- [x] Phase 3: APIs, discovery and compatibility.
- [x] Phase 4: dedicated Trial Balance UI.
- [x] Phase 5: ledger drilldowns and real exports.
- [ ] Phase 6: review and Trial Balance fixes implemented; broader Reports release
  checks remain open (see final verification below).

## Contract decisions

- Version 6 isolates the new Trial Balance calculation and hierarchy. Existing
  v1 Trial Balance calculation and other statement behavior retain their contracts.
- Default/detailed views project one canonical frozen result; layout switching
  changes presentation only. Both use the same exact base-currency source.
- Actual native head/group ancestry is retained, with variable group depth.
  Parent columns aggregate descendant account debit and credit sides independently.
- The hierarchy index is a reconstructible Reports-local locator into immutable
  result batches. Scoped job/attempt/period/parent/sibling keys support bounded
  reads. No financial master balances are added.
- Zero-row suppression removes only rows with no opening, turnover or closing;
  zero-closing accounts with activity remain visible. Totals are leaf-only.
- Current hierarchy and All ledgers export settings are typed presentation options
  over the completed report, with the same full-company totals.

## Compact toolbar and layout review (2026-11-02)

User requested filters behind an icon, less vertical spacing, and export controls
beside Refresh accounting data. The completed presentation follows this order:
Refresh accounting data → Filters icon → Export hierarchy → split Export button.
Actions remain subject to the actor's existing report permissions.

- Filters start closed. The icon exposes financial-year/date controls, hierarchy
  presets, zero-row visibility and the comparative period when available. Closing
  and reopening the panel preserves selections and draft dates without preparing
  a report. The disclosure has an accessible name, expanded state and stable target.
- Closing balances remains the default. Its compact layout switch stays visible
  above the table with actual statement dates, currency, account count and the
  reconciliation status. Title/subtitle spacing is 4 px; the view/table gap is 12 px.
  Account labels have more room on desktop, rows are denser, and disclosures keep
  a 24 px minimum target. All styling remains in the shared token-based stylesheet.
- Export hierarchy offers Current hierarchy and All ledgers. PDF is the initial
  primary export; the arrow offers Excel, CSV and HTML. Selecting a format exports
  immediately and remembers it for the primary action. Disabled formats retain
  their capacity reasons while valid alternatives remain usable. Existing private
  download, PDF preview, polling, cancellation and retry actions remain available.
- Review fixed a submission gap: the split button and scope selector now disable
  immediately while awaiting the initial export job, preventing another selection
  before the server responds. The failing regression was reproduced before fixing it.
- Browser review also reproduced and fixed the first Debit subheading sticking
  horizontally in the detailed layout. Only the Account / group column stays fixed;
  numeric subheadings scroll with their corresponding balance columns. Header
  backgrounds now match consistently across both Debit and Credit subheadings.
- Shared UI version is 0.1.51. Workspace dependencies continue to use the existing
  workspace link; this presentation change requires no API, model or migration change.

Final verification: **61 Trial Balance tests + 32 related report tests passed**.
Dedicated Trial Balance coverage is **100% statements/functions/lines and 88.33%
branches**, above the configured floors. **175 shared control/token/theme tests
passed**, and Console TypeScript passed. Related ReportWorkspace tests emit two
React `act` warnings but have no failures.

Browser verification passed for 48 combinations: both layouts, filters open/closed,
four widths (1440/768/390/320) and three themes. An additional 200% zoom check passed.
Checks cover page overflow, compact spacing, grand totals, keyboard focus and
correct fixed account/scrolling numeric headings.
Screenshots include long account names and normal desktop/phone previews:
`.tools/trial-balance-review/trial-balance-toolbar-1440.png` and
`.tools/trial-balance-review/trial-balance-toolbar-390.png`. These use mounted React
fixtures with the real stylesheet; they do not certify an authenticated live journey.

The broader Reports release checks recorded below remain open. This UI review
does not change their status.

## Phase evidence

### Phase 1

- Confirmed current source head/group/parent and account facts, native aggregate
  reuse, result-batch storage, existing permission checks and export pipeline.
- Reproduced the stale discovery assertion before fixing it: `44 != 39` in
  `test_discovery_has_typed_parameters_and_only_ready_capabilities` (1 failed).
  Replaced the stale literal count with unique code and registered-catalogue checks;
  typed parameter and disabled-admission assertions remain in that test.
- Source/worker readiness will be checked using private local configuration without
  exposing credentials or writing financial data. Fixture readiness alone is not
  evidence that a live report source is complete.
- Baseline: 98 existing backend checks passed; corrected discovery/API suite:
  4 passed. Console baseline: 43 passed across three suites. The company's absent
  GST registrations are explicitly accounted for in discovery expectations.

### Phase 2

- Added Trial Balance version 6 and default/detailed projections while retaining
  version 5 and the existing v1 calculations. Reference/native hierarchy parity,
  independent gross-side totals, ancestry failures and exact strings are covered.
- Added `report_hierarchy_node` and migration `0042`: one CREATE TABLE with scoped
  job/attempt/batch references and parent/ordinal paging index; downgrade drops
  this reconstructible locator table. Read the generated statement line by line.
- Locators are created in the result-batch transaction, verified against its
  immutable rows and fenced by the worker attempt. No amounts are duplicated.
- Targeted backend suites: 98 passed. New domain/native modules: Ruff and strict
  mypy passed. Native MySQL: 11 passed; schema/model/index/FK parity and complete
  downgrade/upgrade passed through head 0042 using the existing loopback test
  helper. Its runner dropped only its randomly named disposable schema.
- Local service credentials cannot create disposable schemas; configured root
  credentials were unavailable. Started the repository's separate loopback test
  MySQL on 13396 rather than modifying live database permissions.

### Phase 3

- Added typed, parent/period/zero-filter bound hierarchy paging with checksummed
  frozen batches, live company/actor/field authorization and private caching headers.
- Discovery selects version 6 once; explicit legacy version 5 results remain readable.
  New Trial Balance calculations reject filtered partial result queries.
- Hierarchy publication requires a complete locator count before job completion.
- API/discovery tests: 7 passed, including signed account navigation, bounded
  cursors, legacy reads and populated two-tenant isolation with immutable ancestry.
- OpenAPI and the Reports TypeScript client were regenerated.

## Review and limitations

### Phases 4 and 5

- The existing Finance Trial Balance URL now opens the dedicated two-layout
  workspace. Closing balances remains the default. Hierarchy presets and manual
  disclosures reuse the completed result; root totals remain independent of paging.
- Branch loading follows visible expanded nodes with 50 siblings per page and a
  1,000-row memory bound, including reservations for pending reads. All groups opens subgroup ancestry; Ledgers also opens
  terminal groups. Quiet filtering preserves zero-closing accounts with activity.
- Scoped session storage retains only report IDs, presentation, cursors and scroll.
  Signed ledger navigation carries a validated local return URL. The generic ledger
  workspace resumes the child run; Back restores Trial Balance choices.
- Both views export through existing private jobs. Current hierarchy and All ledgers
  stream the complete source, including off-page accounts and full leaf-side totals.
  CSV/XLSX identify row kind, level, code and parent; Excel also carries outline levels.
  PDF/HTML use company presentation and grouped opening/movement/closing headers.
- UI checks: 56 Trial Balance tests and 32 shared workspace/navigation/page tests
  passed. Browser layout: one check passed over 24 combinations (two layouts,
  three themes and four widths), plus 200% zoom and disclosure/region keyboard
  focus. Screenshots are in `.tools/trial-balance-review/`. The fixtures contain
  expanded account ancestry and a long account name; mobile field widths and the
  visually hidden caption were corrected and rerun successfully. The browser test
  uses actual shared CSS and captured React markup; interactive lifecycle behavior
  is covered by the unit suite rather than an authenticated live browser journey.
- Actual PDF, XLSX, CSV and HTML download bytes were
  validated for both views; the 206-account branch paginated without loss or duplicate
  ordinals, quiet filtering retained its active account and unchanged full totals.
- Reproduced and fixed invalid mutation of the frozen export-options schema and
  loss of prior financial rows after a failed replacement hierarchy read.

### Phase 6 review and fixes

- Walked CLAUDE.md sections 5 and 6. `/simplify` and `/security-review` are not
  callable capabilities in this session, so performed their manual equivalents:
  arithmetic/coverage, frozen ancestry, input bounds, tenant/company/actor scope,
  field denial, attempt fencing, private artifacts, cancellation and retry identity.
- Fixed per-locator repeated job reads using scoped per-flush job/batch caches.
  The 206-sibling regression originally counted 234 job SELECTs; it now stays below
  80 while retaining checks for every locator and immutable financial batch.
- Failed calculation/root/presentation reads retain the previous completed result.
  Saved expired branch cursors restart at the first page of the same report. Expired
  signed ledger mappings refresh their branch without changing totals. Discovery
  outages now have a working Retry. Legacy runs remain visible until a new v6 result
  is ready, and older deployments cannot accept unsupported v6 preparation.
- History now pages through actor-owned runs with Older reports, so completed
  legacy Trial Balances beyond the first 20 reports remain reachable. Its regression
  first failed with a missing control, then passed without an additional calculation.
- The generic retained ledger workspace resets on actor changes; the regression
  first failed by retaining its component state. The corrected route includes actor
  and run in its key, with validated Trial Balance return navigation.
- Export overrides reject more than 2,000 raw nodes before deduplication. The
  regression first failed because a 2,001-entry list was silently reduced to one.
- Added frozen display-rounding residuals from all account leaves. Exact six-column
  values and financial controls remain unchanged. UI cells expose exact amounts;
  rows/totals disclose differences from rounded ledger sums. Real HTML exports in
  both layouts prove a 0.0060 exact total and a 0.0100 display residual.
- Native publication parity caught missing empty residual fields in reference rows
  and evidence. Both paths now have the same empty-field contract. After fixing
  this, domain/native-statement suites passed 18 checks; native MySQL statements
  passed 9, including full migration downgrade/upgrade and model/index/FK parity.
  The preceding native Trial Balance/API/export run passed its other 24 checks.
- The affected backend run passed 224 checks and skipped 2 environment-specific
  cases; its one parity failure was reproduced and fixed, then rerun in the green
  18-check suite above. The earlier affected run passed 223 and skipped 2 before
  the rounding addition. New domain coverage: 95.51% (9 tests), above the 90% floor.
- Trial Balance UI coverage: 100% statements/lines/functions and 87.69% branches.
  Shared UI: 2,306 tests passed; shared UI and Console TypeScript passed. Reports
  Ruff and strict mypy passed (172 source files). OpenAPI/generated Reports client
  freshness and client TypeScript passed; client transport tests: 8 passed.
  Shared versions are UI 0.1.50 and API client 0.2.57, with corresponding lock state.
- Reproduced a stale Balance Continuity fixture requesting only one month; corrected
  it to a complete financial year. The isolated regression passed. Full coverage
  also exposed the existing audit fixture stripping `gst.` from declared actions;
  preserving the action namespace made all 20 audit contract cases pass.
- The generic navigation regression still expected v6 Trial Balance to accept a
  partial result-query run. It now proves the intended 422 rejection, reads the
  dedicated hierarchy and continues checking signed next-level navigation.
- Final backend rerun: **56 passed in 206.37s**, covering all four Trial Balance
  modules, native statements, audit contracts and both corrected Trial Balance
  generic-navigation cases. Final Console rerun: **50 Trial Balance tests** and
  **32 shared workspace/navigation/page tests passed**; TypeScript passed. Ruff,
  strict mypy (172 files), OpenAPI/client freshness, client TypeScript and all
  8 client transport tests passed. The new backend modules/tests also passed
  Ruff's formatting check (14 files).
- Sibling pages replace the prior page through Next/Previous controls, with a
  bounded 100-cursor window and First accounts recovery. This implements progressive
  access without accumulating every visited financial row in browser memory.
- No unresolved arithmetic, tenant isolation, field-permission or artifact-access
  defect remains from the manual review. Release evidence is separate below.

### Follow-up filter and hierarchy review (2026-11-02)

The user requested a final review of filters and expand/collapse. Rechecked the
financial-year/date inputs, current/comparative selection, quiet-row filtering,
all four expansion presets, manual disclosures, sibling pages, layout switching,
retained totals and matching export settings.

Two asynchronous defects reproduced with failing regressions before fixes:

- Collapsing an unloaded branch left its request pending. Immediately reopening
  it could wait for that old request. Collapse and preset/page changes now cancel
  pending child reads and release their reservations. Cleanup from an obsolete
  request cannot remove a newer request's reservation.
- During a period/filter refresh, an unloaded branch could start another read
  using the previous presentation. Child loading now pauses during the refresh;
  committing the new root cancels previous branch reads. Hierarchy/filter controls
  are disabled while that operation is pending, and the account region reports
  its busy state. The layout switch remains independent.

Added independent, balanced UI fixtures with two heads, nested groups, sibling
accounts, a quiet account, a clearing account with movement and zero closing,
and distinct comparative amounts. Both layouts now prove each expansion preset,
independent branch collapse, retained child collapse choices after reopening a
parent, zero filtering, period switching, page replacement/return, layout changes
on page 2 and unchanged full totals. Export payloads retain the chosen period,
layout, hierarchy and disclosure settings.

Native-query API fixtures also prove a quiet nested group is removed, a zero-closing
account with 7.0000 debit and credit movement remains, all pages share the full
summary, and filtering evaluates each frozen period independently. Streaming export
checks exercise both scopes and every preset across periods and quiet settings,
including ancestry across batch boundaries and unchanged six-column controls.

Final follow-up results:

- Trial Balance UI: **56 passed**; coverage **100% statements/functions/lines,
  87.69% branches**. Console TypeScript passed.
- Backend domain/native/API: **16 passed**. Actual exports and streaming/filter
  checks: **18 passed** (34 backend checks total).
- Shared workspace/navigation/page checks: **32 passed**. Browser layout: **1
  passed**, covering both layouts, three themes, four widths, keyboard focus and
  200% zoom. It uses captured React markup and actual shared CSS; interactive
  behavior is tested in React unit tests.
- Reports Ruff, formatting checks and strict mypy (172 source files) passed.
- Manual simplification/security review of these fixes found no remaining filter
  or disclosure defect. Scope checks, exact amounts and private storage remain
  covered by the focused suites.

This follow-up did not rerun or clear the broader Reports failures/coverage gate
recorded below. The later schema synchronization below records the separately
authorized application of migration 0042 and Reports restart.

### Schema synchronization and runtime restart (2026-11-02)

- Initial read-only live checks: framework, exports and source versions are enabled;
  native query admission remains disabled. The live Reports schema is at 0041 and
  lacks the new hierarchy table. Runtime credentials have no CREATE grant.
- The user subsequently authorized database/script/model synchronization and supplied
  migration credentials. Reports was backed up and restored in a disposable schema;
  the 0041 -> 0042 rehearsal passed native/Alembic parity and row retention. The live
  forward migration then created the hierarchy locator table. All 4,477 rows across
  the 30 original application tables retained their counts, and runtime grants
  remained unchanged.
- The owned Reports API and five workers were stopped and restarted through the
  existing launcher helpers. Workers used its 15-second, ownership-checked stop
  fallback. Reports liveness/readiness return HTTP 200 and all five workers are
  running. The Accounting snapshot publisher and other services were preserved.
- The final read-only comparison passes for all eight services and 537 model tables;
  Reports model/migration/readiness/database heads agree at 0042 with 31 model tables.
  No model repair, applied-history edit, stamp or additional migration was needed.
- Additional native MySQL checks: 20 passed, with full migration downgrade/upgrade
  and model/index/FK parity. Schema-verifier regressions: 8 passed. The separate
  native server and generated rehearsal schemas were cleaned up. No financial
  postings or admission changes were made.
- Private backup/retention evidence:
  `.test_artifacts/trial-balance-schema-sync-20261102-42ba92a521194cae95f984f9a629fbb6/`.
  Final credential-free schema reports: `.tools/trial-balance-review/schema-final/`.
  See [the synchronization record](local-schema-sync.md) for all service heads.

The separate loopback MySQL helper started for these checks has been stopped;
its disposable schemas were removed by the guarded runner. Live services and
financial data were preserved. Publication was not requested.

## Final verification and open release checks

The full Reports suite completed in three isolated SQLite test processes: 1,081
passed, 19 failed and 7 skipped (1,107 collected). The two audit namespace failures
and two Trial Balance partial-query expectation failures were addressed above and
passed in the final 56-check focused rerun. The earlier interrupted monolithic attempt
is not a completed suite result.

Fifteen cases outside the focused Trial Balance suites remain unresolved:

- `test_foundation.py::test_full_api_run_pages_download_and_idempotency`: the fixture
  assumes every business table is populated by a basic source run, including GST
  review tables; its table-count assertion fails.
- `test_report_navigation.py::test_each_report_declares_search_filters_sorts_and_detail_link`:
  DAY_BOOK_ACTIVITY, GSTR3B and GSTR1 lack the generic `row_detail` mapping assumed
  by this test.
- `test_each_report_rows_have_valid_filters_sort_and_executable_mappings`:
  BALANCE_CONTINUITY requires a complete financial year; GSTR3B/GSTR1 require captured
  `_gst_context`; the five analytics adapters require verified native inputs.
- `test_each_report_api_query_and_next_level_links`: BALANCE_CONTINUITY is blocked
  by its one-month fixture, and GSTR3B/GSTR1 return 403 for missing GST registration.

These are observed failures, not a verified before-change comparison. Unrelated
production contracts were not relaxed to satisfy these generic fixture assumptions.
Before-change full-service coverage evidence was unavailable, so the overall
coverage ratchet cannot be asserted.

Combined full-service coverage is **87.08%**, below the configured 90% gate. Several supervised
PDF/worker child modules have no measured parent-process coverage despite successful
artifact checks. This measurement limitation does not waive the gate. New Trial
Balance domain coverage meets its 90% floor, and the dedicated UI meets its configured
statement/function/line and branch thresholds. Phase 6 remains open for the broader
suite and coverage gate. Migration 0042 and the Reports runtime restart are now
complete, as recorded above; an authenticated live Trial Balance journey is separate
from these schema/readiness checks.

Combined coverage data is `apis/reports/.coverage-trial-full`; the standalone JSON
is `.tools/trial-balance-review/reports-coverage.json`. Screenshot evidence is under
`.tools/trial-balance-review/`. Coverage 7.16 automatically consumes suffix data
when reporting, so the original chunk files no longer remain after the combined
report. The saved full-run aggregate remains available.

Reproduction commands, run from their respective package directories:

```powershell
# apis/reports: focused final backend checks
.venv/Scripts/python.exe -m pytest tests/test_trial_balance_domain.py tests/test_trial_balance_native.py tests/test_trial_balance_api.py tests/test_trial_balance_exports.py tests/test_native_statements.py tests/test_activity_audit_contract.py 'tests/test_report_navigation.py::test_each_report_api_query_and_next_level_links[TRIAL_BALANCE0]' 'tests/test_report_navigation.py::test_each_report_api_query_and_next_level_links[TRIAL_BALANCE1]' -q
.venv/Scripts/python.exe -m ruff check src
.venv/Scripts/python.exe -m mypy src/reports
.venv/Scripts/python.exe tools/export_openapi.py --check

# mfes/apps/console: dedicated UI coverage and types
pnpm.cmd exec vitest run tests/trial-balance.test.tsx --coverage --coverage.include=app/components/TrialBalanceWorkspace.tsx --coverage.include=app/lib/trial-balance.ts
pnpm.cmd exec tsc --noEmit
```

Partial coverage processes used `--cov-fail-under=0` to collect their separate data,
then the combined report was checked with `--fail-under=90`; that final gate failed.
The configured floor was not changed.
