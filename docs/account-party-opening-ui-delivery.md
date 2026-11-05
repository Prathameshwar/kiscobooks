# Account and party opening UI

Delivered 2026-10-28 at `/accounting/opening`, following the
[UI plan](account-party-opening-ui-plan.md) and completed
[API contract](account-party-opening-api.md).

## Delivered behavior

- Masters has an Account and party openings card. Ledger, party and supplier
  directories and details link to the workspace using current company authority.
  Account/party links preserve the selected context and return destination.
- Balances and bills uses three steps: account category/group, paged alphabetical
  account openings, and source settings/review/posting. Edited rows are validated
  before the third step. The company supplies books begin and base currency.
  Search and pagination retain the worksheet's exact decimal edits.
- Party documents support invoices, supplier bills, credits, advances and explicitly
  unknown-date on-account evidence. Remaining amounts, optional original face values
  and historical base carrying values are checked without JavaScript money floats.
- Optional YTD evidence, same-day overlap review, credit-cash explanations and a
  configured migration clearing account are available under the typed API contract.
- A successful server preview precedes save/replace. Automatic mode fills source
  settings and discloses an equity offset for any difference. An explicit final
  confirmation saves, prepares bounded native drafts and posts them, retaining
  exact request keys on uncertain retries. Manual mode retains the individual
  actions. Finalization follows reconciled native confirmations; posted balances
  are never overwritten.
- Imports provide a metadata-derived CSV template, bounded CSV/TSV/XLSX/JSON upload,
  staging, durable job history, validation issues, source and bill review, commit,
  resumable preparation, cancellation and private report downloads.
- History uses signed cursor paging for retained company openings, captured entries
  and immutable revisions. It exposes bill dates, historical carrying values and
  posting lineage, with ticketed evidence exports. Closed/replaced preparations are
  reachable after reload. Earlier setup openings are explained without an overwrite.
- Correction preparation retains native close/replacement fences. Posted records
  remain subject to the existing native reversal and dependent-transaction rules;
  this UI never changes a posted balance directly.

## Existing design and access

The implementation reuses shared Tabs, Stepper, Cards, form controls, entity search,
file upload, tables, paging, review lists, confirmation dialogs and display formatters.
The compact account choices and editable grid use shared token-based opening styles.
Light, dark and ledger themes retain the responsive layout and keyboard navigation.

Finance read access opens the workspace. Finance management access permits capture,
import preparation and completion; native journal posting additionally requires journal
posting and period access. Export access remains separate. Server field metadata,
company ownership and current authority remain authoritative. No grants or financial
admission switches were broadened for this UI.

The proxy permits a fixed Accounting surface, checks normalized paths and typed
queries, preserves idempotency keys, and carries private download headers. Worksheet
and upload contents are not placed in browser storage. Unsaved edits and uncertain
commands prevent accidental section/company changes; retries retain the exact body/key.

## Two reviews and fixes

Review 1 covered financial intent, field policy, source privacy and safe retries.
Fixed a collision between financial and stock OpenAPI schema names, custom table-cell
rendering, the existing-opening loading race, nested document-edit loss and confirmation
retry handling. Existing stock client schema names are preserved.

Review 2 exercised complete browser workflows, imports, history and compatibility.
Added the private staged-declaration read needed for meaningful import review, retained
job selection across validation/commit, protected in-progress journal selection, made
action reasons visible before confirmation, preserved closed-opening navigation and
explained legacy setup records. Money display uses the existing exact-text formatters.

Manual reviews followed CLAUDE.md sections 5 and 6; the named slash commands were not
available as executable tools. All identified findings were fixed and checked.

## Verification

- **243 Console tests passed**, covering the new UI, proxy and validation together
  with account/party pages, existing accounting editors, Masters and stock history.
- Console TypeScript checking passed. Generated API client **0.2.41** is current;
  its TypeScript check and **8 transport tests** passed.
- Accounting strict mypy and Ruff passed for the affected API/schema/read modules.
  Existing opening and ledger domain checks: **51 passed**.
- Native MySQL import-review workflow passed, including current field denial,
  cross-company refusal, reviewed commit/replay, cancellation and private history.
  Disposable upgrade/downgrade/re-upgrade through 0222 and model parity passed.
- Browser checks: six sections at 1440px and 390px in all three themes (**36 checks**),
  plus two complete fixture workflows: on-account edit/preview/save/prepare/post/
  reconcile/finalize, and retained import validation/review/commit. No browser errors
  or page/card horizontal overflow were found. Shared tables scroll internally.
- Live tenant3 sign-in and `/accounting/opening` service/metadata reads passed.
  Its selected company grants read-only access; management controls were correctly
  disabled. Accounting was refreshed and readiness passed after the read endpoint
  addition. No additional migration was needed for the UI.

Full financial UI workflows used isolated browser fixtures; native integration tests
used disposable MySQL and existing Identity authority/confirmation test doubles. No
real company opening was captured, posted, reversed or finalized for UI verification.
Concurrent Sales and stock UI edits were preserved. No commit or publication was requested.

## Review hardening, 2026-10-29

The approved follow-up adds pinned edit baselines, immutable revision reads and
explicit new/replacement selection. Conflicts retain local edits until explicit
discard; a reload never silently authorizes overwriting another controller's work.
Existing worksheets respect fiscal readiness and period authority. Outstanding
documents use opening-specific capture metadata derived from native field rules,
reject duplicate references/source
keys and cannot silently change ledger, side or currency after document capture.

Posting and completion now exposes scoped correction preflight, prepared-intent
cancellation, retained reversal discovery, separately reviewed reversal posting
and cancellation of interrupted reversals. Cancellation remains possible when
books prevent posting. Remaining drafts, posted counts and confirmation requirements
are explicit. Bank opening items have a direct company-scoped handoff at
`/accounting/bank-reconciliation`, reusing the existing bank owner without requiring
report access or posting the bank balance again.

The [implementation record](account-opening-review-implementation.md) contains
the new tests, native verification, browser checks and review limits.

## Automatic completion decision, 2026-11-04

The user requested that opening be completed on `/accounting/opening` without another
step elsewhere. Automatic review now sets up missing fixed starter accounts through
the existing initialization command. Its final confirmation covers prepare, post,
native confirmation, reconciliation and finalize. Ledger and outstanding agreement,
exact totals, zero clearing, revision identity and native completion receipts are
verified before success is displayed. Reconciliation differences stop completion and
remain visible on this page; confirmations continue polling automatically.

Lost setup, posting and finalization responses retain their exact body/key. A saved
or partially posted declaration can resume from this page after explicit confirmation,
without reposting confirmed journals. The completed view removes the action-reason and
finalize controls. Manual mode retains individual commands and all native permission,
period, company and revision checks. Final review evidence is recorded in the
[three-step delivery plan](account-party-opening-three-step-plan.md).

## Focused UI refinement, 2026-11-04

The focused visual review corrected mobile account fields that extended beyond
their rows, even when the page itself reported no overflow. Account search stays
usable at narrow widths, all three steps remain aligned, and keyboard navigation
focuses the newly opened step. Primary forward actions are distinct; inapplicable
navigation buttons are omitted. Automatic source details are expandable, with
reporting choices and review checks visible. Balance and completion metrics are
easier to scan, and readonly values use a quieter surface. Native posting,
confirmation and retry behavior remains the same.

Styles are scoped in the shared opening stylesheet, using existing design tokens
in UI version 0.1.66. See the three-step plan for desktop/mobile/theme verification.
