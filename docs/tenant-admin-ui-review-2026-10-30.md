# Tenant administrator UI review, 30 October 2026

The reviewed UI still needs fixes. The [findings CSV](tenant-admin-ui-review-findings-2026-10-30.csv) records **12 bugs and 8 implementation/UX gaps**, with severity, complexity, reproduction steps, source locations, evidence and a suggested delivery order. The main visual defects are the phone designer layout, inconsistent lookup/text/date heights, default fieldset styling in Receipt/Payment, and crowded voucher action buttons. Other confirmed defects concern mode-dependent controls, navigation, invoice formatting, validation and Audit feedback.

This was a review of the paths used by changes #1–18. Application code was not changed, business records were not saved or posted, invitations were not sent, and no role updates were applied. Existing concurrent printing, company-settings and shared-component work was preserved. Several findings predate this batch but are exposed by its new routes; the CSV identifies that attribution instead of claiming every finding is a newly introduced regression.

## Bugs

| ID | Severity / complexity | Finding |
|---|---|---|
| B01 | High / High | At 390px the designer's fixed side panels crowd out the canvas and clip or overlap toolbar/property controls. |
| B02 | Medium / Low | Purchase lookups measure 42.1875px high, text inputs 36px and date inputs 38px. Mixed controls also differ in report settings. |
| B03 | Medium / Low | Receipt/Payment account groups use browser-default groove borders and padding; fields stack across the full desktop width and action buttons touch. |
| B04 | Medium / Low | An explicitly account-only Receipt permits Add item and creates an item line that the native owner rejects in ACCOUNTS mode. |
| B05 | Medium / Low | Purchase/money review Back links go to opening stock. |
| B06 | Medium / Medium | Open customer ledger opens party configuration, without a transaction ledger. |
| B07 | Medium / Low | Invoice preview presents raw four-place amounts without company display precision or currency. |
| B08 | Medium / Medium | Purchase client validation leaves focus on Save and renders a global status message without field error association or an invalid-field marker. |
| B09 | Low / Low | Native voucher history prints `DRAFT ? SUBMITTED`; issue-number text uses the same separator. |
| B10 | Medium / Low | A failed Audit/activity read still has a No events pager caption, implying a successful empty result. |
| B11 | Low / Low | The Audit security-exclusion chip exposes the operator `never`. |
| B12 | Low / Low | Initial and draft voucher workflow buttons lack consistent spacing/wrapping. |

## Gaps

| ID | Severity / complexity | Missing behavior |
|---|---|---|
| G01 | High / High | Saved-draft directory, discoverable reopen/edit workflow and a canonical continuation after Save. Voucher drafts currently renders another entry/import surface. |
| G02 | High / Medium | A readable saved transaction summary before financial review/approval. The current detail page requires Refresh and then shows status/actions/history without supplier, dates, references or captured amounts/lines. |
| G03 | Medium / Medium | Report source choices need readable dates, coverage and compatibility. A READY financial source does not establish inventory report readiness. |
| G04 | Medium / Low | Repeated report/export history labels need time, period/parameters and readable run identity. |
| G05 | High / High | Goods and tax-bearing Purchase workflows remain outside the implemented untaxed account slice. Country plus configured tax type must determine supported native behavior. |
| G06 | High / High | Physical count with calculated stock difference remains an unfinished menu destination. Native cutoff and surplus valuation decisions remain open. |
| G07 | Medium / Medium | Real invitation delivery and recipient acceptance remain unconfigured and untested. |
| G08 | Low / Low | Report/book entry should load the chosen native workspace with clear loading/retry states, instead of requiring another manual Load action. |

G05–G07 are known unfinished prerequisites/workflows, not regressions attributed to the working untaxed form, count placeholder or invitation controls.

## Suggested delivery order

1. Fix shared control heights, money grouping/action CSS, mode-compatible item controls, safe Back navigation, money display and misleading Audit/history text. These are Low complexity changes. Verify native date controls, selected/disabled lookups, multi-selection wrapping, keyboard focus and all three rounding profiles.
2. Add the readable voucher summary and field-associated validation; connect customer-ledger navigation; improve report source/history/entry continuity. These are mostly Medium changes and should retain native scope, refusal and version checks.
3. **High complexity: designer responsiveness.** First agree a compact toolbar and collapsible palette/inspector layout. Then preserve desktop geometry, keyboard/focus behavior and native restore/Undo while testing 1440, 768 and 390px. The review records the layout defect; it does not change the editor.
4. **High complexity: saved draft discovery/edit.** Plan native scoped list/detail/edit contracts, readable capture and metadata, expected-version conflicts, retry/uncertain-save behavior and canonical routing. Verify drafts can be found and reopened without duplicate creation.
5. **High complexity: statutory/goods Purchase and physical counts.** Complete the existing owner/release plans first. India with GST uses the supported GST profile; other countries/types use their configured supported workflow. Count cutoff and surplus valuation need their governing decisions before implementation.
6. Configure invitation delivery when provider/mailbox prerequisites exist, then test recipient acceptance.

## Review coverage and evidence

The [execution CSV](tenant-admin-ui-review-execution-2026-10-30.csv) retains screen captures, browser interactions, initial interrupted attempts, corrected harness probes and focused component assertions. Its rows are evidence entries, **not a count of unique accepted features**. Browser PASS means the named capture/interaction completed; a separate finding can still identify a defect in that captured state.

The primary sweep covered 23 route states at desktop 1440px, tablet 768px and phone 390px, plus configured Receipt/Purchase forms, Payment probes, profile-specific overview screens and a retained designer. Additional checks covered native saved voucher/history, customer-link destination, report sources/history, enabled opening-entry controls, historical restore/Undo, an operator's unchanged role-catalogue preview, and a simulated overview failure followed by real Retry recovery.

Final collection contains **53 completed browser cases, 132 layout-capture entries and 164 passing component assertions**, plus preserved initial attempts and corrected harness probes. All three Payment forms were inspected: the final Services and Distribution native reads each found one active Payment type, and both UI rechecks passed. No missing-Payment-configuration application gap is reported.

Existing focused component/contract suites passed **164 tests**: 156 across overview, books/reports, report references, money/Purchase forms, openings, Items and session failures; 8 covering version/native designer restore. Passing suites do not establish that these visual defects are absent.

| Earlier work | UI review scope and limit |
|---|---|
| #1 | Real provider sign-in and company selection used throughout; no synthetic login token. |
| #2 | Public unavailable/access recovery views rendered at all three widths with expected 503/403 responses. Overview source failure was browser-simulated and recovered with a real native read. |
| #3, #8 | Audit/activity failure/filter/pager presentation inspected. Their retained-tenant reads returned 503 during the sweep, so populated pagination was not newly accepted. Previous native race/pagination evidence is separate. |
| #4 | Product attributes and retained editor reviewed; native historical Restore and Undo performed locally without Save/Publish. Designer readonly/failure contracts have focused tests. |
| #5, #6 | Three configured profiles reused; Sales entry, SKU configuration and configured money display reviewed. No new invoice, approval, statutory or posting execution. |
| #7 | Items, Accounts, Parties and stock destinations inspected. This review does not repeat all 115 earlier record-link checks. |
| #9–#11 | Report/book hubs, Cash book entry, native workspace controls, source/history presentation and typed-reference styles inspected. No new report job/export was created. |
| #12, #13 | Native ordinary-money and untaxed account-Purchase forms, saved detail navigation, history and validation reviewed. Submitted retained invoices remained unchanged. |
| #14 | Live scoped overview, customer lookup/destination and failure/Retry inspected; no nonzero posted activity was created. |
| #15 | Stock view and offered adjustment placeholder inspected; physical counts remain pending. |
| #16 | Invite-user and notification settings inspected; no delivery attempt. |
| #17 | Responsive controls, alignment, enabled/disabled states, fieldsets, action spacing and selected new workflows inspected. This does not certify every populated business combination. |
| #18 | New evidence and findings recorded independently; older acceptance ledgers were not rewritten. |

Invoice-preview display was checked using the actual readable retained voucher plus **browser-only DRAFT/preview responses**, separately labelled in the CSV. This demonstrates presentation behavior, not a new native invoice calculation or acceptance. Missing-supplier validation failed locally before a business write. Opening Add account balance and editor Restore/Undo changed only local UI state.

The initial Sales document-width measurement was investigated rather than accepted as a clipping defect. At 768/390px the actual main scroll area remained exactly 768/390px, the line grid scrolled by 530/908px, and the final check found no external visible overflow. Horizontal line scrolling is intentional; no confirmed Sales clipped-line bug is listed.

The initial development server produced slow compilation, webpack runtime errors and interrupted requests. Only its launcher-managed Console process was restarted. Earlier results remain in separate attempt artifacts. Two Payment probes read options before async loading completed; a later native-read/UI recheck is recorded separately. A Purchase probe initially waited for button onClick on a native form-submit button; the corrected probe waited for form onSubmit and reproduced B08. One company-selection assertion ran at phone width and was corrected to use the desktop selection surface. These are harness/environment events, not application findings.

The review is not blanket end-to-end acceptance of financial posting, India GST, inventory execution, nonzero report reconciliation or real mail delivery. Those remain governed by their existing owner/prerequisite plans and acceptance evidence.

## Reuse

Run from the original workspace with managed local services and the retained fixture manifest/protected credentials available. Run phases sequentially to avoid competing development compilation. `QA_REVIEW_DATE` can select a valid company document date; the default is the current UTC date. The harness supports `QA_OUTPUT`, `QA_CONSOLE_URL`, `QA_AUTH_URL` and `QA_BROWSER`.

```powershell
$env:QA_UI_REVIEW_PART='screens'
node docs/testing/tenant-admin/review-ui.cjs
$env:QA_UI_REVIEW_PART='remaining'
node docs/testing/tenant-admin/review-ui.cjs
$env:QA_UI_REVIEW_PART='final-checks'
node docs/testing/tenant-admin/review-ui.cjs
$env:QA_UI_REVIEW_PART='payment-recheck'
node docs/testing/tenant-admin/review-ui.cjs
python -B docs/testing/tenant-admin/collect_ui_review.py
```

The collector uses the retained local artifact directory for this dated report. Screenshots, protected credentials and fixture-state artifacts remain ignored. The reviewer should inspect screenshots as well as geometry: overflow-hidden editor panels can be unusable even when document width appears correct. No application fix or publication was performed in this review.

## Review todo

- [x] Inspect changed/reused surfaces and preserve concurrent edits.
- [x] Run browser review at desktop/tablet/phone widths and across configured profiles.
- [x] Reproduce navigation, mode-control, formatting, validation and failure-state findings.
- [x] Run focused component suites and review screenshots/source attribution.
- [x] Record reusable probes, findings and separate execution evidence.
- [ ] Implement the agreed UI fixes and rerun their affected probes.
- [ ] Complete owner-gated statutory, stock and invitation acceptance.
