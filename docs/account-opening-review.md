# Account opening creation review — 2026-11-02

1. Reproduce account creation, simple / bill-wise transitions, locked capture and uncertain-request recovery defects with failing UI tests.
2. Fix retained amounts and unfinished-bill handling, allow an explicit reset of an unavailable opening, and retry the original accounting creation request without rebuilding it from changed capture metadata. Keep native field authority, exact amounts, company books-begin dates and posting boundaries.
3. Review general, cash, party and foreign-currency behavior; verify account / Party / quick-account creation and worksheet integration, native backend regressions, responsive layout and types. Record final findings and evidence.

The existing account, opening evidence, migration and API contracts remain applicable. No automatic activation, balancing adjustment or posting is part of this review.

All three phases completed.

The five initial regressions failed before the implementation changes: loss of the pending balance when switching mode, hiding an unfinished bill, inability to clear an unavailable opening, missing confirmation for clearing bills, and rebuilding an uncertain creation instead of retaining its original request. A subsequent browser regression reproduced four-line step labels on a narrow account card before the responsive fix.

Fixes:

- Bill-wise to balance-only switching retains the exact pending amount and historical foreign carrying value. Saved allocations remain available when switching back. An unfinished bill must be added, updated or cancelled before changing mode.
- Entered openings can be cleared even when capture access becomes unavailable. Clearing bill evidence requires confirmation with initial focus on keeping the opening. Clearing remains disabled during pending or uncertain creation.
- Account, Party, quick supplier and quick expense creation retry the retained original body and idempotency key before rebuilding validation from current opening metadata. Response verification and current company/creation authority remain required. Definitive validation failures and explicit resets use fresh keys.
- Account creation progress stacks on narrow screens so its labels remain readable. The three primary opening controls remain compact. Shared UI version is 0.1.54; the offline frozen workspace install passed with the existing lockfile.

Verification:

- 435 unique Console checks passed: 343 broader creation, account, Party, worksheet and product regression checks; three additional conditional-input checks; 87 shared-command consumer checks for Design, voucher types and product workflows; two browser tests. The instrumented broader run required a 15-second test timeout for two existing tax/default UI scenarios; both passed without changing their assertions.
- 9 shared Stepper/layout checks passed. Console and shared UI TypeScript checks passed.
- 42 Accounting domain/API/guard checks passed, covering atomic creation, exact evidence, rollback, wrong-company/tenant access, retained replay, locked periods and immutable opening evidence. This run used the fixture's default SQLite database; it did not apply migrations or modify the live database.
- Reviewed opening input/capture/command coverage: 99.53% lines/statements, 98.08% functions and 92.83% branches. The final conditional-input run covers MasterOpeningStep at 100% lines, 96.15% functions and 85.71% branches. The combined scoped report is in `.tools/account-opening-reviewed-coverage/`.
- Browser checks cover 36 layout combinations: account balance-only and Party balance-only/bill-wise at 1440, 768, 390 and 320 pixels in light, dark and ledger themes, plus keyboard focus and 200% zoom. Screenshots in `.tools/account-opening-review/` and `.tools/master-opening-review/`; desktop and 320-pixel screens were visually reviewed.
- Whitespace checks passed. Existing unrelated workspace changes were preserved.

Final simplify/security review: consolidated retry state in the existing command hook and retained one shared opening editor. No additional findings after the fixes. Exact decimal strings, explicit Dr/Cr, books-begin date validation, native field/finance authority, company-scoped receipt verification, atomic evidence creation and the explicit company opening review/posting boundary remain intact. No API, database model, migration or script changes are required by these fixes.
