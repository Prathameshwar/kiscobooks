# Advanced product creation: continuation review

Reviewed 2026-11-05. The user authorized uninterrupted phase-wise work and two
review/fix passes. This record does not mark Phase 6 or Phase 7 complete.

## Implemented in this continuation

- Every SKU setup now creates the dated BASE binding before optional alternates,
  barcode, tax and prices. Quantity and price defaults are fetched for that
  SKU's selected unit. The BASE binding starts on the books-begin date when a
  reviewed opening precedes product creation. Seven alternate bindings are
  allowed alongside BASE, respecting the native eight-binding setup limit.
- The Advanced options response carries the signed company context's
  books-begin date when available. The opening editor defaults to that date,
  validates it before the first write, and hides opening when finance context
  is unavailable or books begin in the future. Current source versions are
  checked during progress; changed setup requires a new review.
- The wizard captures a configured SKU barcode and named batch selling prices.
  Pinned Product Type attribute members are exposed through native options;
  required non-axis values are captured per SKU and declared in the submitted
  family definition. Variant axis choices are narrowed to the pinned set.
  Serial count compares quantities numerically so exact decimal strings such
  as `2.0000` agree with two physical units. The final review exposes entered
  profile, SKU, unit, tax, price and opening details. Validation links select
  the affected step and SKU.
- A submitted definition remains immutable. Recovery checks the current
  creation receipt, locks completed SKU setup and saved opening decisions,
  keeps command bodies/keys for uncertain work, and rekeys only definitively
  editable unfinished commands. Saved session commands are constrained to the
  same company and creation path.

## Review pass 1: correctness and security

1. The original UI omitted the BASE unit binding. Native readiness and price
   creation require it. Fixed with a dated BASE binding and a per-unit native
   quantity rule; reserved `BASE` as a code and reduced the alternate limit.
2. Editing after partial effects could replace reviewed work and clear every
   command key. Fixed with receipt-aware edits, completed-step locks and
   selective command replacement.
3. A saved opening could become hidden when configuration changed. Fixed with
   an explicit removal action for still-editable openings.
4. Storage recovery accepted arbitrary command paths. Restricted stored
   commands to the original company, creation and supported SKU actions.

## Review pass 2: UX and native owner boundaries

1. Books-begin date was user-entered without a known company date, leaving a
   late, uneditable native rejection. Fixed by returning the signed date in
   Advanced options and validating it before submission.
2. Batch sale prices were omitted despite the native batch schema accepting
   named levels. Added per-batch fields and exact strings in the opening body.
3. A padded decimal serial quantity was rejected by string comparison. Fixed
   numeric count comparison; the owner still validates exact quantities.
4. A required barcode had no field. Added capture and a clear action when
   changed configuration disables a saved barcode.
5. The original final review and error summary did not expose enough details
   or take a user to the affected SKU. Expanded both and added field focus.
6. A pinned Product Type could require non-axis typed attributes that the
   wizard could not declare, blocking definition creation. Added scoped
   attribute members to options, a per-SKU typed editor, and required family
   declarations; authored axes are restricted to permitted members. A follow-up
   review found that malformed typed values could still reach submit, so the
   client now checks native text, integer, decimal, date and unit rules before
   building the immutable command.
7. The final end-to-end pass found that losing a session receipt during recovery
   could start a second product definition. Submit now requires the matching
   saved intent and refreshes the native creation status before accepting edits.
   The final review also exposes named batch selling prices that were previously
   hidden behind the opening summary.
8. Published Product Types can be shared by goods and services (`BOTH`). The
   Advanced options response previously rejected that native value. Its schema,
   OpenAPI contract and Catalog client now accept it, with an API regression.

## Verification and remaining gates

### Focused UI review, 2026-11-05

Phone widths previously hid every step label, leaving only numbers. The shared
wizard CSS now keeps all four labels visible and wraps them within the step
buttons. SKU selectors now use pressed buttons instead of incomplete tab
semantics, so ordinary keyboard navigation matches the controls. Narrow
section headers and variant axes wrap; field children shrink inside their grid;
long review values wrap within cards. Required-attribute cards have consistent
spacing, and paired unit inputs each show their shared validation error. The
browser layout regression asserts visible step labels at four widths in three
themes, but could not run in this workspace because the UI runner and workspace
dependencies are absent. Syntax and CSS diff checks passed.

- Ten changed TypeScript source files and the new regression test parsed with
  an offline TypeScript compiler. Pure Advanced product libraries typechecked.
  Targeted Node smoke checks passed for dated BASE/barcode setup, padded serial
  count, and completed-setup edit rejection. Python files compiled and the
  OpenAPI JSON parsed. `git diff --check` found no whitespace errors.
- Backend pytest cannot start: `pytest_asyncio` is absent. Console Vitest,
  TypeScript app typecheck, generated-client check and browser layout tests
  cannot run: pnpm and workspace dependencies are absent. Offline npm install
  also lacks `yargs-parser`. These gates must be run before release.
- Native whole-draft preview is still absent; current validation and option
  refresh do not replace owner validation. The published
  inventory/warranty/return/handling terms still need readable
  summaries. Owner calculated opening carrying value is not previewed before
  posting. Do not enable or publish this flow as complete until these are
  implemented and the Phase 7 cross-service scenario matrix passes.
