# Simple product creation progress

Local implementation only. No VM update.

- [x] Phase 1: Add regression coverage for prominent pending, waiting, recovery and completion feedback. Existing flow failed to expose the progress region before implementation.
- [x] Phase 2: Add a shared progress panel style and connect Simple creation to verified native stages.
- [x] Phase 3: Run affected checks and review accessibility, responsive CSS, recovery and monetary boundaries (limitations below).

Progress must follow server evidence. Do not simulate percentages or mark opening stock posted before confirmation. Keep existing save, polling, retry and idempotency behavior.

## Result

- Progress appears below the page header immediately after submission and scrolls into view once when work starts.
- Shared opt-in panel adds a spinner, animated indeterminate bar, numbered milestones, current-stage emphasis and completed checkmarks. Mobile milestones stack, and reduced-motion preferences stop animation.
- Uses native CREATE, pricing, ACTIVATE, batch/serial and stock steps. Optional stock stages follow captured details or server evidence. Unknown stages show verification without inferred completion.
- Automatic stock/pricing waits explain that work resumes automatically. Saved, failure and correction states stop animation and explain the existing next action.
- Confirmed completion gets a success panel with retained navigation and focus. Opening stock is reported posted only from the server flag.
- Shared UI version: 0.1.73. Existing workspace link dependencies require no lockfile version change.

## Verification and final review

- New Simple progress and submission/recovery integration tests: **22 passed**.
- Shared progress component and CSS contract tests: **6 passed**. Existing compact progress tests remain green.
- Console TypeScript check: **passed**. Task diff whitespace check: **passed**.
- Existing Simple creation suite: **41 passed, 7 failed**, matching failures recorded before this task. Those tests still assume purchase reference prices provide opening valuation or omit required opening unit cost. No pricing behavior was changed to mask those failures.
- Manual simplification and security/invariant review: no new findings. No request, company scope, money calculation, opening submission, retry, storage or idempotency logic changed. Panel stage lists remain outside the progressbar accessibility subtree.
- Live browser geometry/visual verification remains blocked by this workstation's browser process restrictions. CSS contracts and DOM tests do not substitute for visual verification.
- Local implementation finished; no VM update, deployment, commit or publication performed.
