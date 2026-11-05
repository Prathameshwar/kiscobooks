# Three-step account opening workflow

Requested 2026-11-04: choose Buyers, Suppliers, or one Other Accounts group; enter openings in an alphabetical, searchable, paged grid; validate edited rows before reviewing automatic or manual preparation and posting.

## Delivery phases

1. Add account selection and a paged editing grid. Retain edits across filters/pages, use exact decimal strings, preserve existing bill and foreign-currency detail, and obey capture permissions. Add regression tests for the step gate and list requests.
2. Move source settings into the third step. Default automatic source values without inventing accounting facts. Provide an explicit prepare-and-post action through the existing versioned, idempotent commands, with visible partial progress and recovery. Manual mode retains editable settings and the existing posting controls.
3. Verify workflow regressions, permissions, stale versions, uncertain retries, and responsive layouts. Update the workflow documentation and record review results.

## Confirmed accounting decisions

Final review requested 2026-11-04: automatic mode must complete the financial opening
on this page. The confirmed action now covers preparation, posting, waiting for native
confirmation, reconciliation and finalization. Extend the regression tests first, then
implement guarded completion and recovery, and verify the final UI and documentation.
Success means the server returned FINALIZED for the reviewed revision; posted journals
alone are partial progress. Manual mode retains its separate lifecycle controls.

- The user confirmed that every account uses the company books-begin date. Row dates are automatically populated and read-only.
- The user confirmed that the difference posts to a configured opening-balance offset account. The UI adds a disclosed, exact-decimal equity entry to the declaration before preview. The backend still receives and validates an explicitly balanced declaration. Migration clearing remains separate and must end at zero.

Chart v5 adds OPENING_BALANCE_OFFSET (Capital/equity) and MIGRATION_CLEARING (Current Assets). Existing initialization safely catches up missing defaults, retaining the existing conflict and permission rules. Manual mode can select a different eligible offset for the worksheet. No schema migration or new posting endpoint is needed.

## Verification and review

The row/date/offset decisions above are implemented without changing the ledger API
or adding a database column. Source settings use the existing declaration; the offset
is a normal, explicitly disclosed balanced entry with immutable revision evidence.

The implementation uses current company ownership checks, existing server field
permissions, exact decimal strings/BigInt arithmetic, optimistic versions and native
idempotent commands. It stops when the declaration changes, permissions deny a command,
or preparation makes no progress. Confirmed partial posting remains visible; an
uncertain mutation must be replayed before continuing. No financial data is written to
browser storage. Finalization still requires confirmed reconciliation.

Manual simplicity and security review covered CLAUDE.md sections 5 and 6. Findings
fixed during review: retaining the original automation review reason and edit baseline,
blocking navigation during automation, rechecking the configured equity account before
preview, preserving a group label when revisiting selection, and retaining historical
bill detail when a grid amount changes. Review slash commands are not installed here.

Browser evidence is local and ignored under `.tools/opening-review/`: 1440px and 390px,
light/dark/ledger, selection/grid/review screenshots, pagination edit retention,
validation, exact disclosed offset, manual toggle, no page overflow or runtime errors.
These checks use mocked company data and do not post into a live company.

Completed checks: 22 targeted Accounting tests passed (17 bootstrap/template checks
plus five stock/tax/default-count integrations); Ruff and strict mypy passed for the
changed backend sources. Console TypeScript passed. The 184-test opening run had
183 passes and one five-second timing failure under host load; the complete 30-test
workspace suite subsequently passed with a 15-second per-test allowance, with all
assertions retained. New group revisit coverage is recorded in the final UI results.

Final UI evidence: 203 distinct affected tests passed across the opening and saved
master-opening suites, including all 30 workspace tests, nine new step/automation
checks, exact-offset tests and default-account validation. Timing-sensitive integration
runs used a 15-second per-test allowance on this busy workspace. The final six browser
runs also exercised Other Accounts group selection and label retention on revisiting
step one. No further simplicity/security findings remain. Native MySQL/RabbitMQ and
live-company posting were not exercised for this UI/default-seed change.

## Final completion review, 2026-11-04

The final user instruction extends automatic posting through reconciliation and
finalization, with no separate completion action on another screen. Explicit preview
can initialize missing fixed starter opening accounts using existing company-scoped
bootstrap authority. Reads, paging and mode switches remain free of mutations.

Regression review covered delayed confirmations, ledger/document/clearing mismatch,
large aggregate exact totals, interrupted setup/post/finalize requests, saved-receipt
agreement with the approved preview, paused/reloaded completion, StrictMode and
unmount safety. The server still rechecks money permissions, company ownership,
period openness, revision identity and reconciliation inside its native commands.
No new endpoint, role, migration or financial posting engine was introduced.

Manual simplicity and security review (the slash commands are unavailable) found and
fixed premature success after journal posting, a setup navigation detour, stale
completion instructions, missing disclosure text, and missing preview/receipt
agreement before automatic posting. Finalized receipts and reconciliation must be
verified before displaying success; partial progress is retained on this page.

Final verification: 63 distinct affected Console tests passed across targeted runs
(30 workspace, 23 step/automation, seven worksheet and three default-account tests).
The final regression also retains the same preparation request after an unverifiable
receipt. Console TypeScript and the touched-file whitespace check passed. Four
existing Accounting lifecycle cases passed in 101.51 seconds using the default
isolated SQLite harness and existing authority/confirmation test doubles: post,
confirm, reconcile, finalize and trade; both large-opening modes; and unknown-date
on-account settlement. This rerun does not claim MySQL/RabbitMQ coverage.

All six browser combinations (1440px/390px, light/dark/ledger) completed the real UI
against isolated fixtures with exactly one journal post and one finalization, no
runtime errors and no page overflow. Completion screenshots are in the ignored
`.tools/opening-review/` folder. No live company opening was posted or finalized.
No unresolved findings remain from the final simplicity/security review.

## Focused visual and usability review, 2026-11-04

The user requested a professional, polished interface. Review phases: inspect the
selection, entry, review and completion screens; refine the layout and primary
actions using shared design tokens; verify keyboard use, mobile field bounds and
the entire confirmed workflow in light, dark and ledger themes. Keep the approved
accounting and posting behavior intact. The review prioritizes readable mobile
inputs, compact generated details, clear balance totals and a concise completion view.

Completed refinements: full-width mobile amount/date controls; a search field that
does not shrink beside the date hint; aligned three-step navigation with a primary
Next action; heading focus on step changes; automatic source details in a disclosure;
visible reporting and review choices; compact balance/completion metrics; and quieter
readonly styling. Manual source controls expand by default. The financial command
sequence, explicit posting review, exact values and permission gates are preserved.

Verification: 55 affected Console tests passed (24 step/automation, 30 workspace and
one browser layout regression), plus 56 shared token/theme/setup tests. One search
test exceeded its short async lookup allowance during a concurrent browser run; the
complete 24-test suite passed on rerun with its assertions unchanged. TypeScript and
the touched-file whitespace check passed. Shared UI is 0.1.66; refreshing the pnpm
workspace lockfile required no linked-consumer resolution changes.

The committed browser regression checks actual control bounds and full amount
visibility at 320/390/768/1440px in all themes, plus 200% zoom. The interactive fixture
run completed selection, search/paging, editing, review, manual toggle and automatic
finalization in all 12 size/theme combinations, with no runtime errors or page
overflow. Screenshots remain under `.tools/opening-review/`. Simplicity/security
review found no remaining issues; changes are scoped to presentation and step focus.
