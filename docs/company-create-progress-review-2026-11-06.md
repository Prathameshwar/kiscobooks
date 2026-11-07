# Company creation progress review — 2026-11-06

Status: implemented in the local workspace; not deployed.

Company creation previously showed task badges and text, with no animated activity
while saving or preparing the company. Profit and loss already had an indeterminate
bar, live status and stage labels. That treatment is now shared as
`PreparationProgress` in UI 0.1.70, with its styles centralized in `data.css`.
Profit and loss, Balance Sheet and the native financial workspace use the same
component; report Stop controls and their existing calculations remain intact.

## Resulting behavior

- **Saving:** pressing Create immediately shows “Saving your company” with activity
  feedback. Opening is offered only after the save is confirmed. Duplicate creation
  submissions remain blocked.
- **Checking:** the first setup read has an activity indicator while the company
  is already saved.
- **Preparing:** the current running server step supplies the operation label.
  The ready-step count comes from the verified, company-scoped setup response.
  Neither a percentage nor a completion time is fabricated.
- **Waiting or review needed:** existing warning and retry controls remain visible;
  the activity bar stops. A transient read failure also stops the bar until a fresh
  response is available. Setup retry uses the shared button's loading state.
- **Opening:** opening the saved company shows activity. The user can still choose
  **Open while setup continues** or **Leave for now**, and automatic opening still
  follows confirmed preparation. Opening balances retain their separate decision.

The wizard focuses changed activity headings and scrolls the preparation panel
into view. The initial short-screen check reproduced a hidden bar at 320 × 390px;
the corrected check passes with the progress and footer action visible. Readiness
pages do not request automatic scrolling, and subsequent status updates do not
repeatedly move the reader's scroll position.

## Validation and review

The new regression assertions first failed against the old implementation for the
missing saving/checking/preparation progressbars. The activity-heading focus
regression also failed before the focus change. Final unit and typecheck results
are recorded below.

**257 unit tests passed:** 44 Company wizard, 18 automatic readiness, 10 Profit
and loss, 12 Balance Sheet, 33 native books, 69 Trial Balance, 32 finance workspace,
7 finance final review, 15 WizardLayout, 14 shared controls and 3 preparation
progress tests. Console and shared UI TypeScript checks and task-file
`git diff --check` passed.

Broader verification found two existing source-rebuild assertions expecting
`could not be verified after rebuilding`. The source owner now reports
`Accounting source rebuild did not complete` for their fixtures. The Trial Balance
failure reproduced with the new shared component export removed and with its
application/source files unmodified. Both stale message assertions were corrected;
bounded-rebuild counts and retained-result checks are preserved. Their suites now
pass. A pre-existing, non-fatal React `act` warning remains in Trial Balance's
export-layout test.

**384 Chromium layout checks passed:** eight saving, checking, running, waiting,
review-needed, opening and report states; 320, 390, 768 and 1440px widths;
390 and 844px heights; all three themes; normal and reduced motion. They check
activity state, indeterminate accessibility, animation preferences, horizontal
bounds, progress visibility and the enabled Open company action in the footer.
The static browser harness renders the real shared components and saved setup
fixtures, with the same scroll operations verified by unit tests. It does not
submit live company creation or financial commands. Evidence and screenshots are
in the ignored `.tools/company-progress-review/` directory.

The normal Vitest entry point is blocked by this workstation's esbuild subprocess
restriction (`spawn EPERM`); the local TypeScript runner executes the affected
Vitest suites. Manual simplification and repository security/correctness review
found no further issue. The `/simplify` and `/security-review` slash commands are
unavailable here. The UI changes add no API, polling timer, dependency, permission,
tenant-scope rule, financial command or change to the durable creation request.
Auth and Console retain workspace links to UI, so lockfile resolutions do not change.
