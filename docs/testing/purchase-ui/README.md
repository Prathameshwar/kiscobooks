# Purchase UI review artifacts

The Phase 1 files below are static design references and synthetic examples. They do not replace
the running Purchase screen or demonstrate API, interaction, print or financial
readiness. See the [blueprint](../../purchase-ui-blueprint.md) and
[todo/review ledger](../../purchase-ui-todo.md).

- [Desktop light](desktop-light.png), [dark](desktop-dark.png), [ledger](desktop-ledger.png).
- [Mobile light](mobile-light.png).
- Editable vector references: the corresponding `.svg` files.
- [Examples](examples.json): nine exact-decimal UI scenarios; tax is supplied fixture evidence.
- [Browser check results](render-review.json): text bounds/contrast on the static references.

Reproduce from the existing repository root:

```powershell
python docs/testing/purchase-ui/blueprints.py
node docs/testing/purchase-ui/render.cjs
```

The generator uses Python's standard library and reads colours from the shared
theme files. The renderer uses the already installed
`.tools/ui-review-runner/node_modules/playwright` and Microsoft Edge. It adds no
dependency and makes no service call. It hosts each SVG in a minimal local HTML
document for screenshots; direct standalone-SVG screenshots timed out in Edge.

The automated checks validate fixture arithmetic, documentation links, SVG
structure, text inside the canvas, text overlap and text contrast at its background. They do
not establish WCAG conformance, keyboard interaction, responsive CSS or final app
performance. Those checks belong to the later interactive phases.

## Phase 2 interactive workspace

The application preview is `/vouchers/new/purchase-preview`, under the existing
authenticated ConsoleShell, selected company and year. It uses synthetic INR
suppliers/items and makes no service requests or persistent saves. The old live
account-purchase entry continues to use its existing API contract.

The [Phase 2 screenshots/results](phase2/review.json) come from the **actual React
workspace** in an isolated component harness. They do not include authenticated
API or ConsoleShell end-to-end verification. Route permissions have separate unit
tests. Start the existing-tooling harness from the repository root:

```powershell
node docs/testing/purchase-ui/interactive/start.cjs
# In a second terminal, while the harness is running:
node docs/testing/purchase-ui/interactive/review.cjs
node docs/testing/purchase-ui/interactive/typecheck.cjs
```

The harness binds only to `127.0.0.1:4417`. It needs the existing console Vite and
React dependencies, the existing Playwright installation and Microsoft Edge; it
adds no dependency. Stop its process after reviewing.

Screenshots: [desktop light](phase2/desktop-light.png),
[dark](phase2/desktop-dark.png), [ledger](phase2/desktop-ledger.png),
[tablet](phase2/tablet-light.png), [mobile](phase2/mobile-light.png),
[empty state](phase2/empty-light.png), [review](phase2/review-light.png),
[edited calculation](phase2/edited-light.png).

Checks cover page overflow, runtime errors, mobile primary action sizes, review
focus return, stale-total invalidation and the explicit demo-only result. Full
keyboard/screen-reader, 200% zoom, 200-line performance and the complete scenario
matrix remain the P5 gate. The scoped TypeScript command checks Purchase source,
route, tests and transitive dependencies; it does not substitute for the complete
console typecheck/build.

## Phase 3 purchase details

The same authenticated preview now contains six Purchase detail panels. Synthetic
scenarios cover goods with an advance, partial existing receipt, recipient tax,
an untaxed account expense and required batch/serial tracking. Select a scenario
and use Load example bill; replacing edited entries requires confirmation.

With the harness above running:

```powershell
node docs/testing/purchase-ui/interactive/phase3-review.cjs
node docs/testing/purchase-ui/interactive/typecheck.cjs
```

[P3 browser results](phase3/review.json) record 17 renders/screenshots, including
the three desktop themes, tablet, mobile and empty state, six desktop panels and
five mobile panels. Captures wait for drawer entry animation to finish; panels
use viewport screenshots so fixed overlays are represented accurately.

- Workspace: [light](phase3/desktop-light.png), [dark](phase3/desktop-dark.png),
  [ledger](phase3/desktop-ledger.png), [tablet](phase3/tablet-light.png),
  [mobile](phase3/mobile-light.png), [empty](phase3/empty-light.png).
- Desktop panels: [discounts/charges](phase3/components-light.png),
  [recipient tax](phase3/tax-recipient-dark.png), [partial receipt](phase3/receipt-light.png),
  [tracking](phase3/tracking-light.png), [payment/terms](phase3/settlement-ledger.png),
  [supplier comparison/files](phase3/evidence-light.png).
- Mobile panels: [components](phase3/components-mobile.png),
  [receipt](phase3/receipt-mobile.png), [tracking/dark](phase3/tracking-mobile-dark.png),
  [settlement](phase3/settlement-mobile.png), [evidence](phase3/evidence-mobile.png).

Checks cover document/dialog overflow, runtime errors, mobile primary targets,
dirty Escape/discard and focus restoration, unchanged bill after cancellation,
partial-source residual, full bill versus proposed settlement, read-only recipient
tax, honest local-file state and decoded raster preview. Component/model unit tests
cover validation, exact arithmetic, scoped eligibility, required tracking, custom
fields, file failure/pending/discard and read-only policy behavior.

The browser surface remains an isolated actual-component harness, not an
authenticated API E2E run. Files never upload or persist; PDF preview is descriptive
guidance only. Tax rates/treatments and availability are supplied fixtures. Final
screen-reader/keyboard matrix, zoom, locale and 200-line scale checks remain P5.

## Phase 4 purchase workflow

The authenticated preview now supports new bills, tab draft save/resume, submitted
and approved read-only examples, rejection corrections, historical master labels,
and validation/known-failure/permission/stale/uncertain outcomes. Open **Explore
workflow examples** to select a state or the next simulated command outcome. Demo
save/submit uses an injected memory adapter and never persists, posts or pays.
Leaving/reloading loses all tab drafts and selected files; **Discard tab drafts**
explicitly releases them. Create, edit and submit actions use existing scoped grants.

With the same harness running:

```powershell
node docs/testing/purchase-ui/interactive/phase4-review.cjs
node docs/testing/purchase-ui/interactive/typecheck.cjs
# Manual workflow harness, independent of application authentication:
# http://127.0.0.1:4417/?workflow=DRAFT&theme=dark
# ?workflow=NEW&blank or ?workflow=REJECTED or ?workflow=MASTER_CHANGED
```

[P4 results](phase4/review.json) record 15 renders/screenshots:

- New workspace: [light](phase4/new-light.png), [dark](phase4/new-dark.png),
  [ledger](phase4/new-ledger.png), [tablet](phase4/new-tablet.png),
  [mobile](phase4/new-mobile.png), [empty](phase4/empty-light.png).
- Review/state: [submission review](phase4/review-light.png),
  [submitted](phase4/submitted-dark.png), [approved](phase4/approved-ledger.png),
  [rejected/mobile](phase4/rejected-mobile.png),
  [correction reason](phase4/correction-light.png).
- Recovery: [unconfirmed/mobile](phase4/uncertain-mobile.png),
  [stale revision comparison](phase4/stale-light.png),
  [historical master names](phase4/master-changed-light.png),
  [leave confirmation/mobile](phase4/leave-mobile.png).

Checks cover document/dialog overflow, runtime errors, mobile footer/dialog action
targets, read-only editors, full-bill versus settlement review, correction reason
focus and lineage, uncertainty freezing/recovery, retained stale entries, canceled
leave with focus restoration, and real same-document browser Back cancellation.
Full-page captures place the sticky footer at the viewport boundary and can cover
rows there; dialogs use viewport captures. The browser version is in the JSON.

Unit tests cover exact draft/revision contracts, duplicate pending commands,
same-key recovery after lost or unverified responses, field refusal focus, write
denial, failed latest-read verification/retry, explicit stale replacement, no
submission without calculation evidence, saved-label refresh/preservation, local
file copy/disposal, and late prior-company response/year isolation.

These are component/model/route checks, not authenticated API end-to-end evidence.
The comprehensive P5 accessibility/zoom/locale/scale gate and broader navigation
browser matrix remain pending. Server authorization, durable command recovery,
secure files, real approval/posting/reconciliation and print remain later work.

## Phase 5 quality review

Current result: [UI-readiness report](../../purchase-ui-readiness.md),
[phase ledger](../../purchase-ui-todo.md), [34 visual/a11y cases](phase5/audit.json),
[Edge/Chrome interactions](phase5/behavior.json),
[1/50/200-line measurements](phase5/performance.json) and
[reviewed audit limitations](phase5/incomplete-review.json).

Representative final views: [desktop light](phase5/desktop-light-lines.png),
[dark](phase5/desktop-dark-lines.png), [ledger](phase5/desktop-ledger-lines.png),
[mobile line cards](phase5/mobile-light-lines.png),
[mobile line editor](phase5/line-editor-mobile.png),
[long multilingual/comma-decimal editor](phase5/line-editor-long-locale.png),
[compact 200% layout](phase5/reflow-200-dark.png),
[supplier mismatch](phase5/supplier-mismatch.png) and
[supplied duplicate warning](phase5/suspected-duplicate.png).

The harness has additional query fixtures: `?workflow=NEW&lines=200`,
`&scenario=mixed`, `&scenario=bundle`, `&scenario=mismatch`,
`&scenario=duplicate`, `&slowlookup`, `&restricted`, `&long&locale`.
The delayed loader searches the actual Supplier control, not a separate demo
widget. Its `error` query produces a retryable lookup failure. None calls a service.

Reproduce using the installed app dependencies and existing Playwright runner.
axe-core is a pinned **local review tool**, not an application dependency:

```powershell
New-Item -ItemType Directory -Path .tools/purchase-ui-audit -Force
Invoke-WebRequest 'https://unpkg.com/axe-core@4.10.3/axe.min.js' -OutFile .tools/purchase-ui-audit/axe-4.10.3.min.js
Get-FileHash .tools/purchase-ui-audit/axe-4.10.3.min.js -Algorithm SHA256
# Expected: 880970c081707360e64f34cea25ff91892f5bc95675b0776925b9709dd8a68bb
node docs/testing/purchase-ui/interactive/production.cjs
# In another terminal, with the compiled review server running:
$env:PURCHASE_REVIEW_URL = 'http://127.0.0.1:4418'
node docs/testing/purchase-ui/interactive/phase5-audit.cjs
node docs/testing/purchase-ui/interactive/phase5-behavior.cjs
# Run measurements after other test/browser work has finished:
node docs/testing/purchase-ui/interactive/phase5-performance.cjs
node docs/testing/purchase-ui/interactive/typecheck.cjs
```

The production harness binds to localhost 4418 and writes only to the ignored
`.tools/purchase-ui-production` folder. It builds the actual React components with
Vite; it is not a full Next application build. Stop the server after review.
Behavior checks need the installed Edge and Chrome channels. The audit verifies
the axe hash before use and records incomplete results as well as violations.
Its remaining gradient/icon contrast items are reviewed against the existing
shared contrast suite; zero violations alone is not a conformance certificate.

The 200% check uses 720x500 CSS pixels at DPR 2, plus 320px reflow; native toolbar
zoom and human NVDA/VoiceOver acceptance remain release checks. Primary references:
[W3C reflow guidance](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) and
[axe 4.10.3 API](https://github.com/dequelabs/axe-core/blob/v4.10.3/doc/API.md).
Production API/effective-policy, durable workflows, financial E2E, secure files and
print remain pending with separate authorization.

## Phase 6 remaining UI completion

The user authorized all remaining UI phases and excluded API integration and
print. P6 supersedes the historical pending zoom/browser/build notes above.
See the [current readiness report](../../purchase-ui-readiness.md) and
[delivery checklist](../../purchase-ui-todo.md).

Evidence: [Firefox/WebKit and native zoom matrix](phase6/audit.json),
[four-browser interactions](phase6/behavior.json),
[actual browser accessibility trees](phase6/accessibility.json) and
[final verification record](phase6/verification.json).

Representative views: [desktop discounted net amounts](phase5/desktop-light-lines.png),
[Firefox phone](phase6/firefox-phone.png),
[WebKit narrow locale](phase6/webkit-narrow-ledger.png),
[native 400% dark drawer with a fully visible focused field](phase6/msedge-zoom-400-dark.png).
Native zoom images preserve physical browser pixels; their dimensions differ
from ordinary CSS-pixel review screenshots.

Browser tooling uses local Playwright 1.64.1 with matching Firefox/WebKit builds;
these add no application dependency. Install them with the existing runner:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH="$PWD/.tools/purchase-ui-browsers"
node .tools/ui-review-runner/node_modules/playwright/cli.js install firefox webkit
```

Start `production.cjs` in a separate terminal, then run:

```powershell
node docs/testing/purchase-ui/interactive/phase6-audit.cjs
$env:PURCHASE_REVIEW_BROWSERS='msedge,chrome,firefox,webkit'
$env:PURCHASE_REVIEW_OUTPUT='../phase6'
node docs/testing/purchase-ui/interactive/phase5-behavior.cjs
node docs/testing/purchase-ui/interactive/phase6-accessibility.cjs
node docs/testing/purchase-ui/interactive/application-build.cjs
```

The full Next build uses the normal application configuration, checks and CLI.
Its local preload changes only the review output directory and two-worker count
in the CLI and webpack workers. Build output stays in the ignored
`mfes/apps/console/.next/purchase-review` folder. The wrapper restores only verified
Next-generated TypeScript include/reference changes and preserves unexpected
concurrent configuration edits. It does not bypass lint, types or route validation.

P6 checks native 100/200/400% zoom in isolated Edge/Chrome profiles, short-sheet
scrolling, whole-field focus visibility, and browser AX required/invalid/focused
properties. Completed theme/drawer animations are audited; gradient contrast
incomplete results still use the shared contrast suite. Tooling references:
[Playwright browser versions](https://playwright.dev/docs/browsers) and
[Chromium zoom preferences](https://raw.githubusercontent.com/chromium/chromium/main/chrome/browser/ui/zoom/chrome_zoom_level_prefs.cc).

Windows WebKit/phone profiles are not physical iOS/Safari tests. Browser AX trees
and automated audits are not a human NVDA/VoiceOver session. Physical-device and
human assistive-technology acceptance remain external release checks. Production
data, durable command recovery, real effects/reconciliation, secure uploads and
print remain the explicitly excluded API/print scope.
