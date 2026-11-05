# Purchase UI readiness review

Reviewed: 2026-10-31. P1–P5 implement the Purchase preview; P6 completes the
remaining UI gaps, browser coverage and build review requested by the user.
It is a synthetic UI workspace. API integration and print are explicitly excluded;
production persistence, financial execution and printing are not certified here.

## What is ready

The authenticated `/vouchers/new/purchase-preview` route contains the shared
Purchase editor and workflow preview. Desktop keeps dense keyboard grid entry;
compact containers use labelled line cards and a full-screen staged line editor.
Apply changes one line; dirty dismissal offers keep/discard. Duplicate, insert,
move, remove and undo use the same draft reducer. Full product descriptions remain
available, including long Hindi/French labels. A sticky invoice/line-count strip
and bill-total actions preserve document context while scrolling.

Supplier/payable resolution, separate invoice/posting dates, Items/Accounts/Mixed
modes, exact-decimal provisional calculations, six detail panels, review and
simulated lifecycle/recovery remain available. Example controls are collapsed in
the workflow workspace. Supplied duplicate candidates show references and block
continuation without inventing an override or a successful live duplicate check.
Supplied cost-read denial withholds the entire financial editor and review.

New quality fixes include named keyboard-scrollable overlay bodies, labelled
empty lookup results, valid document/action group semantics, correctly labelled
grid controls, compact footer alignment, 44px narrow-screen primary actions and
stable formatting context during unrelated edits. Invalid desktop numeric text
survives resizing. After correcting it, the user explicitly chooses line cards;
the grid cannot disappear in the middle of a correction. Invalid numbers also
prevent changing a mobile line's type until corrected.
The retained grid keeps its focused field, and switching restores the last edited
line's card rather than jumping to the first line.

P6 aligns desktop Net amount with mobile line totals: after line discount and
before bill adjustments/tax. Account base amounts remain editable; invalid numeric
text suppresses the corresponding derived net amount. At high zoom or in a short
landscape viewport, Purchase dialogs scroll as one sheet. The shared overlay also
reveals the whole focused field when native focus scrolling exposes only its caret.

## Acceptance evidence

| Gate | Verified result |
|---|---|
| Visual/reflow | [34 Edge cases](testing/purchase-ui/phase5/audit.json) plus [40 P6 cases](testing/purchase-ui/phase6/audit.json): all themes, desktop/tablet/phone/320px/landscape, locale labels, panels and lifecycle states; Firefox/WebKit plus actual Edge/Chrome 100/200/400% zoom. No page/dialog horizontal overflow or runtime errors. |
| Accessibility | axe-core 4.10.3: zero automated violations in all 74 cases. [Four actual browser AX-tree checks](testing/purchase-ui/phase6/accessibility.json) verify required/invalid/focused properties, named dialogs and denied financial data withholding. Remaining gradient/icon incomplete results are explained below. |
| Keyboard entry | [Four-browser interaction checks](testing/purchase-ui/phase6/behavior.json): enter a blank supplier/account bill entirely by keyboard and save to the tab adapter; staged mobile editing, error focus, whole-field visibility, scrollable review body, focus trap and Escape. |
| Navigation/recovery | Actual Back cancellation and native reload dismissal preserve dirty input in both browsers. Existing tests cover refused/failed/stale/uncertain commands, immutable correction lineage, exact retry body/key and late prior-company responses. |
| Lookup | The actual Supplier control runs against an injected delayed fixture loader: cancellation, newer-query protection, explicit failure, keyboard retry and recovery. No live supplier API was introduced. |
| Formatting | `de-DE`, comma decimals, dot grouping, suffix currency and `dd.MM.yyyy` review dates; canonical decimal strings remain unchanged by formatting. Native date controls retain browser date presentation. Labels are not translated. |
| Tests | P6 final reruns: 178 console tests in 18 files and 606 shared UI tests in 8 files pass. They cover current Purchase, existing live Purchase capture, workflow/recovery, navigation, route/type ownership, Activity permissions, overlays, numeric entry, lookup, attachments and contrast. Earlier P5's broader Sales checks remain recorded in its ledger. |
| Full application build | Next 15.5.25 production build passes compilation, lint/type validation, static generation and tracing. P6 resolves the supported `PHYSICAL_STOCK` prop contract and Activity's optional props-object incompatibility. [Final verification](testing/purchase-ui/phase6/verification.json) records the build, source/bundle hashes, tests and typechecks. |
| Review | Manual simplification and CLAUDE.md sections 5/6 correctness/security review completed. No unresolved blocking finding within the supported synthetic UI matrix. |

Automated accessibility checks supplement the keyboard and visual review. The
remaining `color-contrast` incomplete results concern gradient action backgrounds
and decorative disclosure glyphs; the shared 308-test contrast suite checks both
action-gradient stops across all themes, and disclosure buttons have explicit
accessible names. See the [P5 review](testing/purchase-ui/phase5/incomplete-review.json)
and [P6 review](testing/purchase-ui/phase6/incomplete-review.json).
This does not constitute WCAG certification or a human screen-reader session.

P6 extends the original 200% layout-equivalent evidence with actual Chromium
browser zoom at 100%, 200% and 400% in isolated Edge/Chrome profiles. Recorded
viewport widths, outer-window size, DPR, CSS zoom and visual-viewport scale verify
native layout zoom without viewport emulation, CSS zoom or pinch zoom. Short
Purchase dialogs scroll as one sheet so header/footer chrome cannot crush their
fields. Browser-surface screenshots preserve physical pixels at native zoom.

Firefox 157.0 and WebKit 27.2 also run the actual components with desktop, tablet,
phone and 320px profiles. These are Windows engine/viewport checks, not physical
Safari/iOS devices. All four browsers are checked for keyboard entry, supplier
lookup recovery, draft departure protection, mobile editing, scroll and focus.
Browser protections still depend on cancellable navigation and unload activation.

P6 records browser-exposed accessibility trees as semantic evidence. NVDA is not
installed in this environment; no human NVDA/VoiceOver session or WCAG
certification is claimed. Physical Safari/iOS and human assistive-technology
acceptance remain external release checks, not unfinished UI implementation.

## Scenario coverage

| Blueprint case | Fixture and expected result |
|---|---|
| PU01 | `untaxed`: account expense without stock quantities; supplied no-tax recipe. |
| PU02 | `goods`: two goods lines, discounts, freight and supplied tax; full bill 5,723, advance 1,000, projected remaining 4,723. |
| PU03 | `mixed`: goods and service rows preserve their own fields and one summary. |
| PU04 | `receipt`: six billed against twelve available; residual six; no second-receipt claim. |
| PU05 | `bundle`: 11 received / 10 billed with an explicit paid-bundle reason; price follows billed quantity. |
| PU06 | `mismatch`: declared 5,800 versus calculated 5,723; signed difference and blocking evidence-panel review. |
| PU07 | Harness `duplicate`: supplied existing reference, visible candidate and blocking check; no live policy/override inferred. |
| PU08 | `recipient`: service supplier payable excludes recipient tax liability. |
| PU09 | `goods` settlement panel: advance and proposed payment keep full bill total; excess settlement refused. |

Additional unit/browser coverage includes empty/missing/ambiguous supplier setup,
restricted costs, incomplete required tracking, receipt over-claim, incompatible
mode, absent supplied tax evidence, submitted/approved review, rejected correction,
write refusal, failed/latest-read failure/stale/uncertain saves and company/year
isolation. Evidence panels preserve local-file and supplier-revision distinctions.

## Scale and environment

Machine: Windows 11 Enterprise 10.0.26100, Intel Core Ultra 7 165H, 63.45 GiB visible
RAM. Browser review uses Edge 156.0.4314.50 and Chrome 156.0.8078.48. Performance uses
Edge, Node 24.13.1, React 19.3.0 and a Vite 5.4.21 production build of the actual
components at 1440x1000. It is not the Next application bundle or a low-end-device
benchmark. The final JS bundle is approximately 399.25 kB (123.07 kB gzip), excluding font
and CSS; the final bundle hash, load timings and all samples are recorded in
[performance.json](testing/purchase-ui/phase5/performance.json).

Fixtures contain 1, 50 and 200 lines. Measure filling the final line's rate through
two animation frames, including automation, scrolling and rendering. Keep the first
edit separate and record twelve warm edits. The local review gate is warm p95 at
or below 250 ms; this is a review budget, not a product service-level guarantee.
No virtualization or new application dependency was needed. See the result file
for actual medians, p95 and input counts rather than treating this machine's
results as universal.

| Lines | Ready including initial load | Warm median edit | Warm p95 edit |
|---|---|---|---|
| 1 | 3,092.2 ms | 34.8 ms | 50.8 ms |
| 50 | 1,384.1 ms | 50.1 ms | 66.8 ms |
| 200 | 1,898.7 ms | 96.7 ms | 166.8 ms |

The first navigation pays initial asset/font loading; later sizes reuse the
browser asset cache. Compare warm edit samples separately from initial load.

## Remaining work and next gate

The subsequent API planning request is captured in the
[detailed API phase plan](purchase-api-plan.md) and [API checklist](purchase-api-todo.md).
This is planning authorization; API implementation has not started.

1. Agree and implement the Purchase API/effective-policy mapping: scoped masters,
   registrations, payable/source selection, field-set/read/write permissions,
   duplicate identity and authoritative tax/calculation evidence. The current
   presentation state must not be sent directly as an API payload.
2. Integrate durable draft/revision/approval/correction and exact command recovery;
   replace tab-only storage and verify historical snapshots/conflicts against owners.
3. Verify authenticated end-to-end purchase execution: receipts, stock valuation,
   payable, recipient/supplier tax, advances/payment and report reconciliation,
   including failed/replayed commands and release activation gates.
4. Integrate secure attachment upload/download and server validation. Current
   attachments remain local and disappear on leave/reload.
5. Define immutable print data, layouts, legal titles/numbering, PDF/pagination,
   copies, locale and denied-field behavior, then test printing end to end.
6. Obtain physical Safari/iOS and human assistive-technology release acceptance
   on the team's supported devices. Native browser zoom and the available
   Edge/Chrome/Firefox/WebKit matrix are covered by P6.

The user authorized all remaining UI passes and explicitly excluded API integration
and print. Items 1–5 stay outside this completed UI scope; they require later
authorization. Keep the [delivery todo](purchase-ui-todo.md) as the phase ledger.

Later authorization, 2026-10-31: the user authorized all Purchase API phases.
The production account-Purchase route now uses the connected controller; private
VM-disk supporting files have an implemented native transport. The completed UI
baseline above remains historical evidence. Current API implementation, limits and
remaining release checks are tracked in [the API todo](purchase-api-todo.md) and
[API evidence](purchase-api-progress.md). Print remains excluded.
