# Purchase UI delivery todo

Updated: 2026-10-31. Scope: Purchase UI first, followed by separately agreed API,
end-to-end and print work. Owner: the current user/agent conversation.

The user approved the five-phase sequence and explicitly requires a review and
fixes after each phase, followed by confirmation before starting the next phase.
Phase 5 was authorized by the user's “proceed as best fit and complete the next phase.” Keep this file and
the [blueprint](purchase-ui-blueprint.md) current together.

Current authorization: the user asked to complete **all remaining work except API
integration and print**. Continue the remaining UI completion passes below without
an additional phase confirmation. Server persistence/approval/execution and secure
file transport remain dependencies of the excluded API integration; do not relabel
local simulations as those completed capabilities.

## Phase status

| Phase | Deliverable | Status | Next authorization |
|---|---|---|---|
| P1 | Blueprint, layouts, interaction contract, examples and acceptance matrix | Complete; reviewed and fixed | P2 authorized |
| P2 | Core Purchase entry: header, supplier, mode-aware grid and totals | Complete; reviewed and fixed | P3 authorized |
| P3 | Purchase details: components, tax, receipt references, settlement and attachments | Complete; reviewed and fixed | P4 authorized |
| P4 | Workflow states: draft editing, review, rejection correction and recovery | Complete; reviewed and fixed | P5 authorized |
| P5 | Visual/usability refinement, accessibility, responsive and scale verification | Complete; reviewed and fixed | Remaining UI passes authorized |
| P6A | Remaining UI gaps and full-console build blockers; review and fix | Complete; reviewed and fixed | Authorized with all non-API/non-print work |
| P6B | Native browser zoom, Firefox/WebKit/mobile and accessibility verification; review and fix | Complete; reviewed and fixed | Authorized |
| P6C | Complete UI workflow regression, production build and final readiness reconciliation | Complete; reviewed and fixed | API integration and print excluded |

## Remaining UI completion passes

- [x] P6A: compare the implemented UI against the blueprint; close independent UI gaps. Desktop Net amount now agrees with compact cards, preserves editable account bases and suppresses stale net values during invalid numeric entry.
- [x] P6A: reproduce console type/build blockers and add regression coverage. Accept the supported stock-adjustment kind; give the Activity page the required Next props object. Preserve company/kind checks and all concurrent edits.
- [x] P6B: run native browser zoom with measured zoom evidence rather than viewport-equivalent coverage alone. Both Chromium channels pass 100/200/400% in all themes, including whole-sheet scrolling and full-field visibility.
- [x] P6B: test Firefox and WebKit with phone/tablet profiles; distinguish emulation from physical devices. All four browsers pass the five interaction sequences.
- [x] P6B: verify browser accessibility output: four actual Chromium AX-tree checks plus 74 axe/visual cases. NVDA is not installed; human NVDA/VoiceOver and physical Safari/iOS acceptance remain external release checks. No OS speech session is claimed.
- [x] P6C: complete the UI scenario, navigation/recovery, permission and attachment-state regression matrix. Final console run: 178 tests in 18 files, native exit 0; shared UI: 606 tests in 8 files, exit 0.
- [x] P6C: run the full-console typecheck and production build; finish review fixes. Normal Next CLI checks pass; review build output is isolated and source configuration is restored.
- [x] Update the readiness report and pending list so completed UI work and excluded API/print dependencies are explicit.

## P1: blueprint

- [x] Read repository instructions and governing invoice/configuration/design docs.
- [x] Inspect current Purchase capture, draft editing, workflow and Sales entry primitives.
- [x] Define the information hierarchy and desktop, tablet and mobile behavior.
- [x] Define separate supplier invoice, internal document, posting and supply dates.
- [x] Specify Items, Accounts/Services and Mixed layouts without destructive conversion.
- [x] Specify supplier, numeric entry, tax, receipt, components and settlement behavior.
- [x] Define the fixture-only boundary and honest save/status presentation.
- [x] Record policy controls, field access and future integration dependencies.
- [x] Produce desktop previews in light/dark/ledger and a mobile preview.
- [x] Validate representative examples and all blueprint links/artifacts.
- [x] Complete simplification, correctness and security review; fix findings.
- [x] Record actual verification output and remaining limitations.
- [x] Prepare the P1 handoff and request for P2 confirmation; subsequently authorized.

## P2: core entry (complete)

- [x] Confirm authorization for this phase.
- [x] Build a clearly identified Purchase UI preview using synthetic fixture adapters.
- [x] Reuse ConsoleShell, shared EntryGrid, numeric controls and centralized entry styles.
- [x] Define typed Purchase UI policy/draft state; keep it separate from the service contract.
- [x] Automatically resolve fixture configuration and useful defaults.
- [x] Implement supplier selection, ambiguous payable selection, dates and invoice identity.
- [x] Preserve user input through date/type/supplier/mode changes; review impacted facts.
- [x] Implement item, account/service and mixed rows; row details and row actions.
- [x] Implement provisional totals, inline errors, focus navigation and keyboard shortcuts.
- [x] Add rendering, validation, pending, failure, read-only and reducer tests.
- [x] Review the actual rendered workspace; fix findings; record evidence.
- [x] List every pending phase and request P3 confirmation.

## P3: purchase details (complete)

- [x] Confirm authorization for this phase.
- [x] Add scoped discount/charge editors, clear bases and treatment explanations.
- [x] Add supplied tax evidence and supplier-versus-recipient tax summaries.
- [x] Add direct/reference/deferred receipt intent and partial-source allocation UI.
- [x] Add batch/expiry/serial/location detail where fixture policy requires it.
- [x] Add credit terms, eligible advances and payment instructions with residual totals.
- [x] Add supplier declared total/difference and explicit supported resolution states.
- [x] Add attachment selection/removal/local preview with type/size and error states.
- [x] Add typed custom fields from the fixture field-set; no financial behavior from them.
- [x] Test components, allocation boundaries, panel focus, permissions and recovery.
- [x] Review and fix; record evidence; list pending work and request P4 confirmation.

## P4: workflow states (complete)

- [x] Confirm authorization for this phase.
- [x] Implement create, edit/resume and read-only review from a single draft representation.
- [x] Model submitted/approved/rejected states and a visible rejected-correction path.
- [x] Preserve supplier/source snapshots and distinguish current-master changes.
- [x] Implement same-tab/cancellable-history and native unload guards; browser coverage limits are recorded below.
- [x] Simulate validation refusal, stale revision, failed save and uncertain-save recovery.
- [x] Retry an uncertain command with unchanged body/key in the adapter contract.
- [x] Prevent company changes from reusing prior-company rows, selections or responses.
- [x] Keep demo save/submit separate from actual persisted/posted claims.
- [x] Test lifecycle actions, permission restrictions and stale async response handling.
- [x] Review and fix; record evidence; list pending work and request P5 confirmation.

## P5: quality gate (complete within the synthetic UI scope)

- [x] Confirm authorization for this phase.
- [x] Inspect light/dark/ledger at desktop, tablet, mobile, 320px and 200% layout equivalent; native toolbar zoom remains release acceptance.
- [x] Verify keyboard-only entry, accessible labels/roles, focus and non-color error cues; human screen-reader acceptance remains below.
- [x] Exercise 1, 50 and 200 lines, long descriptions and the actual Supplier control with a delayed fixture loader.
- [x] Verify configured number/review-date formats and multilingual labels; native date presentation follows the browser.
- [x] Exercise PU01-PU09 and the supported synthetic permission/error matrix; owner policy remains separate.
- [x] Measure interactions on the available Windows machine; record browser, compiled component build, fixture sizes and review budget.
- [x] Run affected UI suites/typechecks and manual simplify/security/correctness reviews; record the independent full-console build blocker.
- [x] Fix review findings and repeat affected checks.
- [x] Write the [UI-readiness report](purchase-ui-readiness.md) with residual gaps; do not claim API/print readiness.
- [x] Request confirmation for the next separately scoped API/effective-policy stage in the P5 handoff.

## Later stages: pending, outside these UI phases

API planning is now requested and recorded in the [API phase plan](purchase-api-plan.md)
and [API checklist](purchase-api-todo.md). Implementation remains pending separate
phase authorization; the completed UI phases and print exclusion are unchanged.

- [ ] Agree the Purchase API/effective-policy contract and supported profile matrix.
- [ ] Integrate real scoped suppliers, registrations, payable accounts, items and sources.
- [ ] Complete supplier identity/duplicate checks and authoritative calculation acceptance.
- [ ] Verify actual draft/revision/approval/correction/recovery end to end.
- [ ] Complete goods receipt/valuation/payable/tax/report reconciliation and release gates.
- [ ] Integrate secure attachment upload/download with owner evidence.
- [ ] Agree print layouts, titles, numbering, legal evidence and immutable print snapshots.
- [ ] Verify print/PDF, pagination, copies, locale and denied-field behavior.
- [x] Complete native browser zoom at 100/200/400% in Edge/Chrome, all themes.
- [x] Complete available Edge/Chrome/Firefox/WebKit coverage and resolve stock/Next page type blockers; full application build passes.
- [ ] External release acceptance: human NVDA/VoiceOver session on supported assistive technology.
- [ ] External release acceptance: physical Safari/iOS and the team's supported hardware, beyond the completed Windows engine/viewport profiles.

## Review ledger

### P1, 2026-10-31

Artifacts: [blueprint](purchase-ui-blueprint.md),
[design previews and reproduction](testing/purchase-ui/README.md),
[examples](testing/purchase-ui/examples.json),
[browser results](testing/purchase-ui/render-review.json).

| Finding | Fix / result |
|---|---|
| P1-R01: mobile composition shortened product names and lost pack/A4 detail | Preserve the complete product/pack descriptions; visually rechecked |
| P1-R02: mobile shell lacked the financial year/currency context | Add compact year/currency alongside company; visually rechecked |
| P1-R03: Preview draft and Review bill did not distinguish save simulation | Use Save demo draft with persistent not-saved notice; document the explicit simulated result |
| P1-R04: narrow quantity headers and undersized labels weakened scanning | Label Receipt qty and Billed qty explicitly; increase grid headers to the existing 11px overline scale; mobile primary actions are 44px tall |
| P1-R05: example totals called every pre-tax base taxable, including NON_GST | Rename the fixture field to pre_supplier_tax_total; legal classification remains owner evidence |
| P1-R06: Edge timed out capturing a standalone SVG | Render the same SVG inside a minimal local HTML host; all four screenshots now pass |

Verification:

- `python docs/testing/purchase-ui/blueprints.py`: nine exact-decimal examples,
  four well-formed SVGs, 28 linked-file checks and no scripted/external SVG content.
  Includes item quantity/rate, discount/charge/tax/total, recipient-tax separation,
  source-receipt residual and advance/payment residual checks.
- `node docs/testing/purchase-ui/render.cjs`: four Edge renders at desktop
  1440x1080 and mobile 390x1400; text bounds, text overlap and text contrast checks pass.
  Browser version and individual results are recorded in the linked JSON.
- Visually inspected all three desktop palettes and the mobile composition after
  fixes. No remaining blocking composition finding identified.
- Manual simplification review: reuse existing controls/styles; one fixture source,
  no duplicated Sales business logic; simplify SVG content verification.
- Manual scoped CLAUDE.md sections 5/6 review: synthetic data only; no permissions,
  service calls, tenant access, persistence, number allocation, posting, tax rules
  or secret material added. Read-denied data, company switching and uncertain-save
  obligations are explicit future UI acceptance cases. No P1 security issue found.
- `/simplify` and `/security-review` are not callable tools/skills in this session;
  the scoped manual reviews above were performed, not those unavailable commands.
- Python AST parsing and `node --check` passed for the artifact scripts. Task-file
  whitespace checks passed. A workspace-wide `git diff --check` also reported
  existing trailing whitespace in unrelated `apis/catalog/openapi.json` changes;
  that file was not edited for this task.
- Application unit suites/typechecks were not rerun: this phase changes design
  documents, fixtures and artifact-generation/review scripts, not application code.

Limits: SVG checks are not application keyboard, accessibility, responsive CSS,
backend, legal tax or print certification. P2-P5 retain those applicable UI gates;
API/end-to-end/print stages remain separate. No backend batch or activation status
changes. Stop here and obtain the user's confirmation before P2.

Later phases must append their own findings, fixes, actual checks and known limits.

### P2, 2026-10-31

User authorization: “yes proceed next”. Implemented the authenticated
`/vouchers/new/purchase-preview` route and typed synthetic Purchase workspace.
The live `/vouchers/new/purchase` account-bill path retains its API behavior.

Delivered: supplier lookup and unambiguous payable default; explicit ambiguous
account selection and setup-needed states; supplier invoice identity and both
dates; Items / Accounts-services / Mixed entry; retained incompatible rows;
separate receipt/billed quantity with an explanation for differences; manual
rates with four-place display; line base/discount entry; row add/insert/duplicate/
move/remove/undo; keyboard shortcuts; description/reason drawer; exact provisional
commercial totals and conditional supplied tax evidence; validation navigation;
review dialog; clearly simulated draft action with pending/failure/retry states;
read-only permission behavior; reload/company-change dirty guard. The complete
navigation/lifecycle/recovery contract remains P4.

| Finding | Fix / result |
|---|---|
| P2-R01: raw decimal spellings invalidated evidence without changing values | Normalize signature inputs with shared exact-decimal formatting; failing regression reproduced, then passed |
| P2-R02: absolutely positioned hidden labels widened the mobile document | Position the workspace scroller relatively; browser overflow regression and unit assertion pass |
| P2-R03: intrinsic input widths hid most numeric columns on desktop | Use shared column-width tokens; desktop fixture now shows both quantities, rate, discount and base without horizontal scrolling |
| P2-R04: narrow controls clipped pack descriptions and primary actions wrapped poorly | Widen subject column, retain full labels, add scroll guidance, use two action columns with 44px targets |
| P2-R05: numeric component-local invalid text could survive replacement | Explicitly remount the grid for a confirmed example replacement; reset regression passes |
| P2-R06: invalid setup focused a disabled payable control | Focus the actionable supplier lookup; failing regression reproduced, then passed |
| P2-R07: quantity issue navigation opened a panel without reaching its reason field | Focus the named reason editor; unit test verifies correction and demo completion |
| P2-R08: demo completion could imply persistence or clear a dirty guard | Keep explicit Demo draft only / Not saved language and retain dirty state after the demo action |
| P2-R09: sample INR amounts could acquire another company's currency symbol | Keep fixture currency explicit while preserving separators, locale and date preferences; alternate-format test passes |
| P2-R10: row deletion lacked recovery | Restore only the removed row, preserving subsequent header/row edits; undo test passes |
| P2-R11: isolated harness missed the app root/base styles and native dark-control scheme | Load actual root styles and ThemeProvider; re-capture actual-component screenshots |

Verification:

- Console: **104 tests passed in 9 files**: `purchase-workspace` (25),
  `purchase-preview-route` (4), `purchase-entry-contract` (20),
  `purchase-entry-form` (5), `purchase-entry-save` (3),
  `purchase-validation` (1), `money-entry-route` (9),
  `sales-entry-page` (15) and `sales-line-grid` (22).
- Shared UI: **416 tests passed in 5 files**: entry grid (56), numeric fields
  (29), contrast (308), tokens (21) and class coverage (2).
- Purchase-scoped TypeScript source/route/tests and transitive dependencies pass:
  `node docs/testing/purchase-ui/interactive/typecheck.cjs`.
- Whole-console `pnpm.cmd --filter @janso/console typecheck` remains blocked by
  an unrelated existing TS2322 at `app/vouchers/new/[kind]/page.tsx:61`:
  `PHYSICAL_STOCK` is passed to `VoucherEntry.initialKind`, whose declared union
  is `PURCHASE | RECEIPT | PAYMENT`. Those ongoing stock changes were preserved.
  The complete console build is therefore not claimed green.
- [Browser results](testing/purchase-ui/phase2/review.json): six actual-component
  renders / eight screenshots; desktop 1440x1000 in light/dark/ledger, tablet
  1024x900, mobile 390x844 and an empty desktop state. No page overflow/runtime
  errors; mobile primary actions meet 44px; review returns focus; financial edits
  remove stale supplied totals; the demo action explicitly reports no persistence.
  This is a local component harness, not an authenticated service E2E run.
- Visually reviewed desktop light/dark/ledger and mobile after fixes. Theme values
  remain centralized; existing Sales styling is unchanged by opt-in workspace rules.
- Documentation/artifact check passes: nine exact-decimal examples, four SVGs
  and 38 repository evidence links. Interactive CJS scripts pass `node --check`;
  new source/test/harness whitespace and tracked task-file diff checks pass.
- Manual simplification review: reuse EntryGrid/SearchSelect/numeric formatting,
  exact-decimal math, overlay focus handling and existing unsaved-change events;
  keep one Purchase draft reducer; do not copy Sales tax/business rules.
- Manual CLAUDE.md sections 5/6 security/correctness review: route permission and
  wrong-company denial tests pass; company-keyed workspace remount; no service
  client, financial write, persistent browser storage, tax-rate inference, number
  allocation, attachment upload, secrets or audit mutations. No additional issue
  found within P2 scope. `/simplify` and `/security-review` remain unavailable as
  callable tools; these were manual equivalent reviews.

All pending work is listed above: **P3** details/components/tax/receipt/tracking/
settlement/attachments/custom fields; **P4** full lifecycle and recovery;
**P5** final responsive/accessibility/locale/scale gate; then separately authorized
**API integration, end-to-end effects/reconciliation and print/PDF** work.
Stop after P2 and request user confirmation before P3.

### P3, 2026-10-31

User authorization: “proceed as best fit and complete next phase.” The existing
authenticated `/vouchers/new/purchase-preview` now includes six progressive detail
panels and five synthetic examples. The live Purchase API screen is unchanged.

Delivered:

- Ordered document discounts and supplier/additional charges, fixed/percentage
  amounts, explicit eligible line bases and treatment selectors.
- Read-only supplied tax recipe/source/classification; supplier tax enters the
  bill once; recipient liability and additional cost stay separate.
- Direct/reference/deferred receipt intent; scoped partial existing receipt
  selection and aggregate residual checks; no second receipt or on-hand claim.
- Item-required location, batch, expiry and serial capture, with retained inactive
  facts and duplicate serial validation within and across rows of the same item.
- Calendar credit terms/due date, supplier/currency-scoped advance proposals,
  method/currency-matched payment account, overpayment validation and projected
  remainder while keeping the full supplier bill total.
- Original supplier total and signed difference; entry correction or a matching
  revised supplier total with original/reason retained; no balancing plug.
- Local supporting files with count/size/type/signature checks, pending/failure/
  retry/removal, decoded raster preview and cleanup; PDF guidance without embedding.
- Purchase notes and typed descriptive custom fields using shared field controls.
- Apply/Cancel drawers with local staging, dirty Escape/discard confirmation,
  validation/focus navigation and read-only/availability fixture policy.

| Finding | Fix / result |
|---|---|
| P3-R01: repeated item serials could pass when split across rows | Track serials by item across directly received rows; failing regression reproduced, then passed |
| P3-R02: individually valid amounts could overflow the document's DECIMAL(19,4) range | Guard aggregate base/total range and withhold usable totals; failing regression reproduced, then passed |
| P3-R03: custom-field validation left focus on Apply | Resolve the shared control through its configured label; focus regression passes |
| P3-R04: a corrupt raster preview fell through to PDF guidance | Show explicit Image preview unavailable guidance; failing decode regression reproduced, then passed; object URLs still revoke |
| P3-R05: display order could show a charge before a newly added discount although discounts calculate first | Share one ordering helper between calculation and editor; failing order regression reproduced, then passed |
| P3-R06: revised supplier total could be accepted without its original declared amount | Require the original before recording a revision; failing regression reproduced, then passed |
| P3-R07: shared stacked-field margins shifted paired treatment controls by 16px | Reuse the shared form-grid spacing reset; browser regression reproduced and alignment checked after fixing |
| P3-R08: screenshots caught the drawer enter animation, leaving a translucent sheet | Wait for animation completion, disable animations during capture and capture panels at viewport size |

Verification:

- Console: **136 tests passed in 11 files**, using `--maxWorkers=1 --minWorkers=1`:
  Purchase workspace (25), details (15), panels (17), preview route (4), entry
  contract (20), entry form (5), entry save (3), purchase validation (1), money
  entry route (9), Sales entry page (15) and Sales line grid (22).
  An earlier concurrent run exposed a timing-sensitive focus assertion in the
  unchanged live Purchase validation test; it passed alone and in the complete
  serialized run. No live-entry code/test was modified for that timing behavior.
- Shared UI: **491 tests passed in 6 files**: FileUpload (75), EntryGrid (56),
  numeric fields (29), contrast (308), tokens (21), class coverage (2).
- Purchase-scoped TypeScript source/route/tests and transitive dependencies pass
  via `node docs/testing/purchase-ui/interactive/typecheck.cjs`.
- Whole-console typecheck remains blocked by the pre-existing TS2322 at
  `app/vouchers/new/[kind]/page.tsx:61`: `PHYSICAL_STOCK` is not in
  `VoucherEntry.initialKind`. The unrelated stock work is preserved; a green full
  console build is not claimed.
- [Browser results](testing/purchase-ui/phase3/review.json): **17 renders/screenshots**
  in Edge, desktop 1440x1000/light/dark/ledger, tablet 1024x900, mobile 390x844,
  empty state, six desktop panels and five mobile panels. No document/dialog
  overflow or runtime errors; 44px mobile primary targets, paired treatment
  alignment, dirty cancellation/focus restoration, receipt residual, full-bill/
  settlement separation, read-only recipient tax, honest local-file state and
  actual raster decoding checked. This is an actual-component harness, not an
  authenticated API E2E test. P2 screenshots were retained separately.
- Visually reviewed the workspace palettes, all six desktop panels and mobile
  details; fixed spacing/capture findings and refreshed P3 evidence.
- Static check: nine exact-decimal examples, four SVGs and 59 repository evidence
  links pass. CJS syntax/Python AST and whitespace across 31 scoped source/test/
  document/harness files pass, as do tracked task-file diff checks. The 17 panel
  tests were rerun after the final paired-field spacing fix and pass. Reproduction instructions
  and bounded fixture decisions are synchronized with the blueprint/design system.
- Manual simplification review: shared Drawer/Modal, numeric entry, CustomFields,
  FileUpload and form-grid spacing; one component-order helper and one Purchase
  draft reducer. No copied Sales calculation or new dependency/app stylesheet.
- Manual CLAUDE.md sections 5/6 security/correctness review: synthetic sources
  scope receipt/advance/payment proposals; read-only fixtures stay disabled;
  exact decimal arithmetic and aggregate limits; source receipt is never received
  twice; no payment, posting, service request, browser persistence, numbering or
  audit mutation; custom fields do not change finance. Files stay in memory, MIME/
  extension/signature checks are basic local checks, no active PDF embed, URLs
  revoke and async results cannot restore a discarded selection. No further
  blocking issue found within P3 scope. `/simplify` and `/security-review` remain
  unavailable; these were manual equivalent reviews, not those commands.

Limits: supplied example recipes are not statutory/effective owner policy or
accepted Accounting calculations. Attachments are not uploaded, stored or scanned;
PDFs are not rendered inline. P3 provides panel transaction behavior, not the full
P4 lifecycle/recovery contract. The P5 accessibility/zoom/locale/scale matrix is
still pending. No production or API/print readiness is claimed.

Pending, in order: **P4** create/edit/resume/read-only workflow, submitted/approved/
rejected correction, navigation guards, stale/failed/uncertain command recovery and
company isolation; **P5** final visual/usability, keyboard/screen-reader, zoom,
locale and 1/50/200-line quality gate. Then separately authorized **API integration,
end-to-end financial/stock/tax/report reconciliation, secure attachment transport,
and print/PDF**. Detailed checklists for all of these remain above.

**Stop after P3 and obtain the user's confirmation before starting P4.**

### P4, 2026-10-31

User authorization: the subsequent “proceed as best fit and complete next phase.”
The authenticated `/vouchers/new/purchase-preview` now runs a scoped in-memory
workflow through the same Purchase editor. No live Purchase service behavior changes.

Delivered:

- New draft, save/revise/resume in this tab and explicit tab-data disposal.
- Exact saved-revision review before demo submission; submitted/approved read-only
  views and rejection reason with a separate, reasoned correction and lineage.
- Preserved supplier/item/receipt labels, current-master comparison and updated
  snapshots when selections change.
- Field validation refusal/focus, known failure with retained editable input,
  permission refusal with frozen editors, stale comparison and explicit replacement
  or copy to a separate new bill, failed latest-read verification/retry.
- Pending duplicate protection and uncertain-response recovery with the same body
  and command key; unverified results never replace visible inputs.
- Same-tab leave confirmation, cancellable browser Back, native unload/company
  guard, and company/year remount with late-response isolation. Open panels and raw
  invalid numeric editors must first be resolved; unconfirmed commands must recover.

| Finding | Fix / result |
|---|---|
| P4-R01: submit/correct adapter transitions could accept a body different from the saved original | Require exact saved content before transition; both failing regressions reproduced, then passed |
| P4-R02: a changed supplier could inherit the previous supplier snapshot; selected supplier/review could show today's label | Refresh changed selections, preserve unchanged snapshots and show historical labels in selected controls/review; failing regressions reproduced, then passed |
| P4-R03: result verification accepted an arbitrary positive revision on create | Require revision 1 for new/correction and exact next revision for edits; failing regression reproduced, then passed |
| P4-R04: Finish the current action notice could remain after recovery or numeric correction | Clear it when the blocker resolves; both failing regressions reproduced, then passed |
| P4-R05: mobile leave-dialog actions were 36px tall | Restrict a token-based 44px minimum to marked workflow dialog footers; browser measurement failed before fixing and passes afterward |
| P4-R06: review's close icon looked active during a pending submission | Use shared Modal busy state for review/correction, aligning close, scrim and Escape with pending actions; failing regression reproduced, then passed |

Verification:

- Broad serialized console regression run: **180 tests passed in 17 files**.
  Includes P2/P3 Purchase, live Purchase, Sales, route access, command recovery and
  company-change mechanisms. After the final review fixes and two additional
  regressions, **43 tests passed in 4 focused files**: workflow UI (21), workflow
  model (13), draft navigation (4), preview route (5). The unaffected suites from
  the broader run were not repeated. These runs cover 182 distinct current tests.
- Shared UI: **416 tests passed in 5 files**: EntryGrid (56), numeric fields (29),
  contrast (308), tokens (21), class coverage (2). Class coverage was rerun after
  the final dialog marker/CSS addition: **2 passed**. P4 does not change FileUpload.
- Purchase source/route/tests and transitive dependencies pass the scoped
  `node docs/testing/purchase-ui/interactive/typecheck.cjs` check.
- Whole-console `pnpm.cmd --filter @janso/console typecheck` still reports the
  existing TS2322 at `app/vouchers/new/[kind]/page.tsx:61`: `PHYSICAL_STOCK` is
  outside `VoucherEntry.initialKind`. The concurrent stock changes are preserved;
  the complete console build is not claimed green.
- [P4 browser results](testing/purchase-ui/phase4/review.json): **15 renders/screenshots**
  in Edge 156.0.4314.50. Desktop 1440x1000 light/dark/ledger, tablet 1024x900,
  mobile 390x844 and empty state, review/submission, frozen submitted/approved,
  rejection/correction, uncertain recovery, stale comparison, master-name changes,
  leave cancellation/focus restoration and real same-document browser Back.
  No page/dialog overflow or runtime errors; mobile footer and leave-dialog
  actions meet 44px. Captures were refreshed after the dialog-size fix.
- Visually inspected desktop palettes, submission review, stale comparison,
  historical labels and mobile leave/recovery views. The browser surface is a
  local actual-component harness, not an authenticated service E2E test.
- Documentation verifier passes nine exact-decimal examples, four SVGs and 77
  repository evidence links; the one reviewed WHATWG browser-contract link is
  explicitly allowed without fetching or embedding external content in SVGs.
  CJS syntax, Python AST, 40 scoped source/test/document/harness text-file whitespace,
  15 browser artifact records and tracked task-file diff checks pass.
- Manual simplification review: one controlled editor/reducer, existing command
  retry hook, shared unsaved-change event and overlays; no duplicated lifecycle
  transport, new dependency, global overlay change or per-app stylesheet.
- Manual CLAUDE.md sections 5/6 security/correctness review: scoped synthetic
  commands and result verification; company/year isolation; immutable rejected
  original; exact-decimal draft facts; no actual service/network financial write,
  persistent browser draft storage, number allocation, approval, posting, payment,
  audit mutation or file transport. Grants control fixture UI only; actual server
  authorization remains required in integration. No further blocking P4 finding.
  `/simplify` and `/security-review` are unavailable; these are manual equivalents.

Limits: this is a UI workflow simulation. All saved drafts/files are lost on leaving
or reload. Native navigation protections depend on browser cancellation support;
cross-browser/back-forward-cache coverage remains P5. The comparison fixture shows
invoice/notes changed by the simulated editor; a production API conflict diff needs
the real revision contract. No production, end-to-end, legal tax or print readiness
is claimed.

Pending, in order: **P5** final visual/usability fixes, complete keyboard/screen-reader
and focus checks, 200% zoom, light/dark/ledger across sizes, company formatting and
non-English display, 1/50/200 lines, long descriptions/delayed lookups, permission/
error matrix and interaction measurements/readiness report. Then separately scoped
**API/effective-policy integration, durable drafts/approval/recovery, end-to-end
financial/stock/tax/report reconciliation, secure attachment upload/download and
print/PDF layouts/pagination/copies/locale/permissions**. Full pending checklists
remain above.

**Stop after P4 and obtain the user's confirmation before starting P5.**

### P5, 2026-10-31

Authorized by the user's next-phase instruction. Current result and limitations:
[Purchase UI readiness](purchase-ui-readiness.md),
[visual/a11y results](testing/purchase-ui/phase5/audit.json),
[keyboard/navigation results](testing/purchase-ui/phase5/behavior.json),
[scale measurements](testing/purchase-ui/phase5/performance.json).
Earlier pending statements above record each historical handoff; this entry is
the current UI phase status.

| Finding | Fix / verification |
|---|---|
| P5-R01: compact Purchase still depended on horizontal line-grid editing | Labelled native line lists and staged full-screen line editor; Apply, validation focus, keep/discard, exact locale parsing, read-only review, row actions and undo tested. |
| P5-R02: example controls and stacked fields used too much mobile space | Move scenario controls into the existing collapsed workflow examples, use shared form-grid rhythm, compact status padding and a sticky invoice/line-count strip. |
| P5-R03: narrow review/save actions wrapped onto separate rows | Increase only the Purchase container selector specificity. Failing 720x500 geometry check reproduced; alignment and 44px targets now pass. |
| P5-R04: read-only overlay bodies could not be scrolled by keyboard | Add a named focusable shared overlay body region and visible inset focus; failing Modal/Drawer regressions pass. Update the intentional Tab-cycle contract. |
| P5-R05: empty portalled lookup results lacked a landmark | Add a named search region around the existing listbox; failing shared regression and actual empty-validation axe check pass. |
| P5-R06: unrelated invoice edits broadcast formatting to every grid cell | Memoize resolved display configuration; controlled-workflow regression failed at three broadcasts versus one, then passed. |
| P5-R07: an invalid numeric correction could unmount during responsive switching | Retain the grid across resize and correction until explicit Use line cards; failing regression reproduced, then passed with retained value and restored focus in unit/Edge/Chrome checks. |
| P5-R08: changing a mobile mixed-line kind could discard invalid numeric text | Disable kind changes with an explanation until the number is corrected; failing regression reproduced, then passed. |
| P5-R09: mobile list semantics and generic anchor labels produced a11y findings | Use native UL/LI, keep Add outside the list, name document/action groups and label actual controls rather than generic spans. Failing regressions and manual incomplete-audit review now pass. |
| P5-R10: remaining matrix lacked mixed/bundle/mismatch and supplied duplicate/cost-denial views | Add bounded examples, visible reference-based duplicate refusal, full financial-surface withholding for supplied cost denial, and delayed Supplier loader injection. Test positive, denied, stale-query and error-focus behavior without declaring production policy resolved. |
| P5-R11: restricted-cost page lacked H1; 720px tax drawer Done was 36px | Add a cost-free page heading and extend scoped narrow dialog actions through 48rem. Failing unit/browser checks now pass. |
| P5-R12: final resize review found focus jumped to the first cell/line | Keep focus on the mounted invalid field and restore the last edited line's card after an explicit switch. A failing second-line regression reproduced the jump; unit and browser checks cover the fix. |

Verification:

- **200 distinct console tests in 20 affected files passed.** Broad runs covered
  Purchase model/core/panels/workflow/route/navigation, existing live Purchase,
  Sales, money entry and company-change/command recovery. Final affected reruns:
  **45 tests in three files** after the last semantic changes (25 core, 18 mobile,
  two quality regressions); the final focus refinement also reruns the 20 mobile/
  quality tests and both browser behavior sequences. Existing money-entry tests emit React `act` warnings;
  their eight assertions pass. These warnings are not browser runtime failures.
- **581 shared UI tests in ten files passed:** 416 grid/numeric/contrast/token/
  class-coverage checks and 165 Modal/Drawer/ConfirmDialog/SearchSelect/overlay
  access checks. Shared UI is now 0.1.43; workspace links do not change.
- Scoped Purchase source, preview route, tests, harness and transitive dependencies
  typecheck; shared UI typecheck passes. Whole-console typecheck still fails only
  at the existing `PHYSICAL_STOCK` TS2322 route mismatch, preserved for its owner.
- Production **component harness** builds successfully with Vite 5.4.21 / React
  19.3.0. [34 Edge captures](testing/purchase-ui/phase5/audit.json) have zero axe
  violations, page/dialog horizontal overflow or runtime errors. Both generic
  ARIA issues and the initial list/scroll findings were fixed. Only reviewed
  gradient/icon contrast items remain incomplete; they are not silently waived.
- [Edge/Chrome behavior evidence](testing/purchase-ui/phase5/behavior.json)
  verifies keyboard-only blank-bill capture/save to the tab adapter, real Back
  and native reload dismissal, delayed lookup cancellation/failure/retry,
  responsive raw-text preservation, staged mobile edits and focus/scroll/trap.
- [Scale results](testing/purchase-ui/phase5/performance.json) record the actual
  Windows machine/build/browser and 1/50/200-line last-rate-edit samples against
  the local warm-p95 250ms review budget. Cold/load timings are separate; no
  full-application or low-end-device speed claim is made.
- Documentation verification passes nine exact-decimal examples, four SVGs and
  106 repository evidence links; three reviewed primary-contract URLs are
  explicitly allowed. CJS syntax, Python syntax, 50 scoped text-file whitespace,
  final screenshot/browser records and tracked task-file diff checks pass.
- Visual inspection covered final desktop palettes, mobile cards and editor,
  long multilingual/locale editor and the 200% layout-equivalent composition.
  The native toolbar zoom and human screen-reader limits remain explicit below.
- Manual simplification review retains one draft/reducer, shared numeric controls,
  overlays, menu and lookup; responsive measurement reads the centralized CSS
  marker. No parallel lifecycle transport, app stylesheet or application dependency.
- Manual CLAUDE.md sections 5/6 review: exact decimal strings/BigInt calculations;
  local staged edits; supplied-result identity binding; company/year remount;
  no new financial API, allocation, posting, approval, payment, audit write,
  browser draft persistence or attachment transport. UI cost hiding is not server
  authorization. Real field-read-denied data must never be delivered by owners.
  `/simplify` and `/security-review` are unavailable; these are manual equivalents.

**P1-P5 complete for the supported synthetic UI workspace.** Pending: API/effective
policy and scoped masters/field authorization/duplicate/calculation contracts;
durable draft/revision/approval/correction/recovery; authenticated financial/stock/
tax/report E2E and activation; secure attachments; immutable print/PDF layouts,
pagination/copies/locale/permissions; native toolbar zoom and NVDA/VoiceOver user
acceptance; remaining browser/device matrix; independent stock build fix. See the
full checklists above and readiness report for practical limits.

The later user instruction authorizes the P6 UI completion passes below. Purchase
API/effective-policy integration and print still require separate authorization.

## P6: remaining UI completion review

| Finding | Fix / verification |
|---|---|
| P6-R01: desktop's final amount was gross while compact cards showed net | Show discounted pre-tax Net amount in every grid mode. Preserve editable account bases and test recalculation after edits. |
| P6-R02: a derived net could remain stale beside invalid typed numeric text | Hide that line's net while numeric problems remain. A failing invalid-rate regression now passes. |
| P6-R03: actual 400% zoom squeezed a drawer body to 24 CSS pixels | Short Purchase dialogs scroll as one sheet. Native zoom regression reproduced before the fix; fields retain their height and actions remain keyboard reachable. |
| P6-R04: WebKit revealed only a field's caret, clipping its bottom below pinned actions | Shared overlay checks the focused field after native scrolling and reveals its entire box only if clipped. It ignores detached targets and portalled controls outside its body. Failing unit/browser regressions pass. |
| P6-R05: supported stock-adjustment route failed the console typecheck | Add PHYSICAL_STOCK to the existing initial-kind contract. Verify company/kind discovery, including wrong-company and wrong-kind refusal. No new API integration. |
| P6-R06: generated Next page validation rejected Activity's optional props object | Require the framework-supplied props object while keeping searchParams optional. Type regression and all Activity scope/permission tests pass. |
| P6-R07: review tooling needed trustworthy final-state and native-zoom evidence | Audit completed animations, compare each browser's own baseline, capture native physical browser frames directly, and preserve the application build output/configuration across CLI and webpack workers. No checks are disabled. |

Manual simplification/security review: no new transport, persisted financial
state, permission broadening, number allocation, tax authority or file upload.
Net amounts reuse the existing exact decimal calculation and display formatters.
The focus fix changes scrolling only, preserves focus and runs only for the active,
connected descendant of the overlay body. Supplied financial read denial remains
withheld in actual browser accessibility trees. No unresolved implementation
finding remains in the verified synthetic UI scope. Missing physical-device and
human assistive-technology acceptance stays explicit in the readiness report.

Final evidence: [verification record](testing/purchase-ui/phase6/verification.json),
[74-case browser coverage](purchase-ui-readiness.md#acceptance-evidence),
[four-browser interactions](testing/purchase-ui/phase6/behavior.json),
[native zoom/engine audit](testing/purchase-ui/phase6/audit.json),
[browser accessibility](testing/purchase-ui/phase6/accessibility.json) and
[production build output](testing/purchase-ui/phase6/build-output.txt).
The final component asset/hash and 1/50/200-line samples are in
[performance.json](testing/purchase-ui/phase5/performance.json); warm p95 values
are 50.8/66.8/166.8 ms against the local 250 ms review budget.

**All authorized UI phases are complete and reviewed.** Current pending work is
the excluded API/print checklist and external human/device release acceptance
above. The production Purchase route remains separate from the authenticated
synthetic `/vouchers/new/purchase-preview` workspace. Nothing was committed or
published as part of these UI passes.

Later authorization, 2026-10-31: Purchase API phases were authorized together.
Their current progress and pending owner integrations are maintained in the
[API todo](purchase-api-todo.md), separate from this completed UI baseline.

2026-11-02, supplier balance (PUI-D05): done on the live page. One figure (Cr/Dr, To pay/To receive)
under the Supplier field, read once per supplier choice, in the background, never blocking entry.
Tests: `purchase-supplier-balance*.test.ts(x)` (read and proof rules, view, page behaviour with a held
and a refused read), the proxy rule in `purchase-wire-policy.test.ts`, the stylesheet guard. Pending:
bill-wise overdue beside the figure, the same line on Sales, and a run against the live services.
