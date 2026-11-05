# Tenant administrator fixes and remaining work

User-approved delivery order: implement steps **1–3 together**, then **4–6 in the next batch**. Original acceptance evidence remains in [the findings CSV](tenant-admin-findings-2026-10-29.csv) and [grouped bugs/gaps](tenant-admin-bugs-and-gaps-2026-10-29.csv).

## Current batch: steps 1–3

- [x] Read repository rules and record existing unrelated changes; preserve local paths and user work.
- [x] **1. Testing/authentication foundation**
  - [x] Verify managed provider/tunnel readiness and prevent orphaned or silently dead forwarding processes during long tests. Pinned SSH supervisor installed; live owned-child interruption recovered both forwarding ports without replacing the supervisor.
  - [x] Preserve real sign-in, token expiry/refresh and authenticated-origin checks in reusable UI/HTTP tests. Auth UI 159 passed; Auth server 103 passed and one Redis prerequisite skip. Live ordinary concurrent refresh passed; naturally expired live exchange remains an explicit coverage gap.
  - [x] Correct stale report catalogue/version expectations, incomplete catalog model fixtures and accounting initialized-chart assumptions without weakening security assertions. Focused suites: Reports 4, Catalog 2, Accounting 4 passed; rollback now exercises an actual new installation and legacy-version transition.
- [x] **2. Session/service recovery**
  - [x] Add failing regressions for unavailable/malformed upstream session/display reads. Confirmed 10 failures against the original session reader.
  - [x] Return a safe recoverable UI state instead of unhandled server errors; preserve login, refresh, step-up, tenant and company boundaries. Final affected Console tests: 89 passed across eight files; encoded retry-path and invalid-formatting regressions included.
  - [x] Verify ordinary and concurrent session refresh behavior without exposing tokens or extending expiry checks. Four live requests authenticated; existing automated expiry/retry/idempotency/coordinator tests passed.
- [x] **3. Audit pagination/company refusal**
  - [x] Confirm broad-admin cursor regression fails, then bound audit/activity cursor binding without weakening scope/query/authority replay checks. Confirmed original size failures; 18 cursor/API boundary tests passed after digest binding.
  - [x] Add/refine regressions for inaccessible company selection and unchanged cookies; return an appropriate refusal rather than misleading 502. Original 502 regression reproduced; corrected 403 preserves both selection cookies.
- [x] Run affected unit suites, type/lint checks and focused UI/API rechecks using the retained QA tenant. Audit 205 passed/13 skipped; Console 89 passed; Auth UI 159 passed; Auth server 103 passed/1 skipped; Reports 4, Catalog 2, Accounting 4 and Pester 9 passed. Ruff, Audit mypy, Console TypeScript and syntax checks passed. Final retained-tenant live checks: 12 passed.
- [x] Perform simplification and security/invariant review; document findings and update an execution/result CSV. Named review commands unavailable; equivalent manual review identified and fixed encoded-path/formatting defects. No remaining issue identified within changed scope.
- [x] Batch implementation complete with affected checks passing and unavailable integration prerequisites recorded. Results: [CSV](tenant-admin-fixes-1-3-results-2026-10-29.csv); [execution and reuse note](tenant-admin-foundation-fixes-2026-10-29.md).

No direct application database manipulation, financial release activation, unrelated work staging, commit or publishing was performed in this batch.

## Steps 4–6: implemented; live posting remains gated

- [x] Preserve prior batch and unrelated local edits; read architecture/security rules and capture baseline failures.
- [x] Reproduce step-4 candidates; fix readonly metadata and native historical restore with failing regressions. Correct measured designer test timing; product-attribute Save eligibility and palette navigation rechecks pass.
- [x] Publish tax/HSN or SAC and FIFO/moving-average prerequisites; configure active customers, receivables, dated payment policies and supported Sales types through UI/API. All three products are ACTIVE; fixture IDs and scripts retained.
- [x] Verify Sales draft, exact calculation, replay/readback, acceptance and submission in all three companies. Foreign-company and self-approval refusals preserve state; owner reads confirm zero posted journal/invoice/open-item/stock effects from drafts.
- [x] Run affected checks: Console 205 unique tests, Catalog 9, Accounting 11 and Vouchers 41 passed. Type/lint/syntax checks passed. Final live evidence has 28 passing cases, including native restore and six owner readback/reconciliation checks.
- [x] Complete manual simplification and security review, correct the discovered restore/loading-state defects, update governing decisions and [batch results](tenant-admin-fixes-4-6-results-2026-10-29.csv). Named review commands unavailable; equivalent manual review performed.

- [x] **4. Existing bug candidates:** readonly metadata and native version restore fixed; attribute Save and command palette verified. Fixture timing maintenance is distinguished from application fixes.
- [x] **5. Business test configuration:** published inventory/tax assignments, three active products, Sales types and customer/account prerequisites verified. Today-effective product overrides preserve future company-default history.
- [x] **6. Supported Sales reference flow:** three account bills saved, calculated, accepted and submitted through UI; exact replay, scope/approval boundaries and non-posting owner effects verified. This is the explicit untaxed account profile.
- [ ] **6. Remaining live posting/taxed-product/stock acceptance - BLOCKED:** invoice/stock execution flags are disabled; C2/B15–B19 and C3 stock/statutory release prerequisites remain unverified. Complete the governing owner/release work and second-person approval before live posting and nonzero ledger/tax/stock reconciliation. Current checks do not satisfy these gates.

## Proposed remaining sequence after step 6 — reviewed 2026-10-29

This is a source/document review at local commit `5ca8767`, not a new live test run.
The [remaining-work CSV](tenant-admin-pending-after-6-2026-10-29.csv) records complexity,
dependencies, source findings and completion criteria. These numbers define the proposed
next sequence; they are not the separate Vouchers B01-B45 batch identifiers.

Steps 1-5 and step 6's untaxed draft/submission slice have completion evidence. Step 6's
posting, taxed account/service and stock acceptance remain open and are carried into
items 13 and 15 below. Fixed B01-B03, resolved C01-C04, configured P01-P02 and completed
M01-M03 are not reopened as new implementation work. The historical failed record links
still need the broader recheck in item 7. The platform acceptance's native Redis result
also supersedes the older Auth handler skip for that same case.

| Sequence | Complexity | Pending work |
|---|---|---|
| 7 | Low | Repeat interrupted stock UI checks and previously failed record-link destinations. |
| 8 | Medium | Native opening races, remaining Audit integrations and provider expiry/lifecycle evidence. |
| 9 | High | Supported live report source/generation, worker, run and export readiness. |
| 10 | Medium | Report hub/category cards connected to discovery and the existing workspace. |
| 11 | Medium | Ordinary financial books/ledgers using that workflow; invoice/stock additions follow owner readiness. |
| 12 | High | Receipt and Payment UI with ordinary-money owner/release and reconciliation checks. |
| 13 | High | Account/service invoice owner and statutory completion, Purchase UI and step-6 C2 carryover. |
| 14 | High | Live company dashboard aggregate and customer lookup, replacing sample data. |
| 15 | High | Goods/stock owner completion, Stock adjustment UI and step-6 C3 carryover. |
| 16 | Medium | Configured real invitation delivery and recipient acceptance. |
| 17 | High | Individual control and populated-workflow acceptance across the three profiles. |
| 18 | Low | Current evidence/catalogue/status reconciliation without rewriting historical ledgers. |

Recommended first delivery group is **7-11**: close cheap rechecks and native evidence,
establish working report sources, then connect report/book navigation. Implementations
in 10/11 may proceed while 9 is awaiting a prerequisite, but live completion remains
dependent on a READY supported source. Invoice/stock books finish alongside 13/15.
Item 14's empty/live source integration can start earlier; its full populated cash/invoice
acceptance follows 12/13. Item 16 can proceed whenever transport prerequisites
exist. Item 17 starts in the first group and continues per slice; item 18 is maintained
per slice and finalized after the full acceptance run.

High-complexity work needs a short phase plan before implementation:

- **9:** readiness/configuration and source contract; READY generation and worker path;
  supported runs/export jobs; failure/recovery/permission acceptance.
- **14:** agree supported aggregate/source freshness contract; implement owner/read API
  and generated client; wire dashboard and native customer lookup; empty/populated and
  scope/reconciliation verification.
- **12:** typed ordinary-money form/capture; draft/reload/replay and allocation validation;
  separate-actor approval and owner delivery under applicable C1 prerequisites;
  ledger/register/reversal acceptance.
- **13:** finish B15 calculation/commercial scope, B16 selected tax scope, B17/B18 owner
  posting and report bridges, B19 legal issue/artifacts; integrate Purchase; complete
  selected Sales/Purchase acceptance and C2 evidence. Open governing decisions retain
  their decision gates; this backlog does not silently select unsupported profiles.
- **15:** close stock design/owner prerequisites and selected B20-B26 producer work;
  integrate adjustment/goods workflows; finish B27a-e and required B28-B36/client
  dependencies; reconcile stock/GL and satisfy applicable C3 evidence.
- **17:** deduplicate the existing coverage inventory; execute existing workflow slices;
  extend cases as 9-16 land; perform final security/correctness review and reconcile
  the result CSVs. Route smoke and isolated unit tests retain their narrower labels.

No application code, release flags, credentials or live data changed during this review.

## Active implementation after step 6

User authorized the proposed sequence and quick High-complexity plans on 2026-10-29.
The phase outlines above are the starting delivery contracts; record refinements before
each High item. Preserve the user's concurrent `zz-routing-visual.test.tsx` work.

- [x] **7:** all 115 original record links passed in the final UI ledger after four recoverable 503 rechecks; all three stock views passed selection/refresh/reload. Original failures remain in their ledgers with the superseding recheck evidence.
- [ ] **8 — IN PROGRESS:** three native opening races passed; Audit full suite passed 224 with zero skips, including native migrations and 11 real broker cases. Natural provider expiry → 401 → real Auth refresh → identical authorized read passed. VM reboot/suspend lifecycle evidence remains separate.
  - [x] User-requested permanent Tenant Administrator opening access: [plan](tenant-admin-permanent-opening-authority-plan.md); seven existing native grants applied by the platform operator with replay and retained assignments. 34 Identity cases, five page/scope cases and all 17 native MySQL opening cases passed. All three existing QA company capture-field readbacks passed; an auxiliary fresh company was created/activated/bootstrapped through UI and its zero opening finalized/replayed without a journal. Balanced cash/equity UI preview passed and was discarded without saving test balances. Historical finalized and field/scope safeguards remain.
- [x] **9 — supported report readiness:** six managed source/dispatcher/worker lanes running with exact three-company scopes; 12 startup/selection tests passed. Permanent reporting authority applied through the authenticated fixed-seed UI/API (nine read/report grants); future tenants inherit the same canonical role. Owner generation mismatch reproduced/fixed with 14 native feed/snapshot tests. All 24 live discovery, READY-source, Trial Balance, four-format private export and history checks passed across the three QA companies. Historical quarantined/blocked jobs remain; financial release gates and unknown prior history remain separate.
- [x] **10 — supported report navigation:** scoped discovery connects the hub/category cards to the native workspace with fail-closed unavailable states. 62 affected component cases passed; all three company hub search/clear/category/Trial Balance checks passed. Individual populated report semantics remain item 17 acceptance.
- [x] **11 — ordinary book connection:** the same discovery/workspace path connects ten book mappings. All three company book-navigation and native Cash Book checks passed with exact zero posted effects. Invoice/stock book acceptance remains with 13/15; these passes do not establish every report calculation.
- [ ] **12 — IN PROGRESS:** [money entry plan](tenant-admin-money-entry-plan.md), kind-bound Receipt/Payment routes, typed money policy and draft/submission flow implemented. All 18 live type/draft/replay/exact-amount/submission/self-approval-refusal cases passed across three companies. All 19 existing native money execution/allocation/race tests pass with zero skips; the close-race fixture now completes its zero opening before execution (initial refused run retained). Actual posting, second-actor owner delivery and nonzero reconciliation retain C1/actor gates.
- [ ] **13 — IN PROGRESS:** [Purchase/invoice entry plan](tenant-admin-invoice-entry-plan.md) recorded before native UI integration. Native untaxed account Purchase entry, exact save/replay, authoritative calculation/acceptance, submission and self-approval refusal pass in all three companies (nine prior final live cases). Rounded payable is 42.1200 / 42.1234 / 42.0000 while input remains 42.1234. Dedicated synthetic NON_GST expense defaults are dated and configured through APIs; initial stale projection/fixture failures are retained. 38 affected component cases and 19 existing native invoice tests pass with zero skips. Supported untaxed account draft editing is now locally verified, including preservation of unrelated capture and source versions. User-directed country/tax selection is recorded; statutory/goods UI, dedicated editing for other native profiles, legal issuance and remaining C2 owner/release scope remain separate. Post-fix live acceptance is NOT_RUN while the VM is off.
- [x] **14 — supported live overview:** native immutable-source SQL aggregates, exact currency amounts, covered posting dates and real Accounting customer lookup replace sample figures. Refined [plan](tenant-admin-live-dashboard-plan.md) recorded before implementation. Four API cases and four native MySQL cases pass, including nonzero fixture reconciliation and tenant/company/read-deny boundaries; 23 affected Console cases pass. Six live UI/API cases pass across the three companies. Populated live invoice/collection acceptance retains C1/C2 prerequisites. [Review](tenant-admin-live-dashboard-review-2026-10-30.md).
- [ ] **15:** [stock entry plan](tenant-admin-stock-entry-plan.md) records native action inventory and the missing physical-count contract. User selected physical count with calculated difference, continuing movements reconciled against a recorded cutoff, and current verified native cost for surplus with mandatory review when absent. Both policy questions are resolved; B25 native grain/API/migrations/locking/review and D02/D03/C3 owner acceptance remain. All 31 previously run existing native stock effects/concurrency/costing/GL/reconciliation/reporting cases pass with zero skips. They do not establish count execution.
- [ ] **16:** user confirmed no current SMTP/provider or controlled recipient (2026-10-29). Existing signed invitation routing, encryption, deduplication, delivery worker and provider handling passed 17 focused fixture tests. Actual external receipt remains a named prerequisite, not a completion claim.
- [ ] **17:** individually executed workflows, per-slice and final acceptance.
  - [x] Report parameter/control review: array/boolean and inventory-group lookup regressions reproduced and fixed. Typed arrays/checkboxes/counts preserve decimal strings; scoped item groups, warehouses, batches and retained reference labels use native resources. All 35 focused component/contract cases pass; TypeScript passes. Live 38-definition control/parameter sweep: 219 passes, nine bank fixture prerequisites. These are labelled control/parameter checks, not populated report acceptance.
  - [x] Actual typed UI submission: all three companies send native array `[30,90,180]` and boolean `false`, while invalid array text is refused locally. All three payload checks pass. Separate stock-source checks remain BLOCKED because current READY financial snapshots lack complete inventory coverage. Original accepted-job assumptions are retained in the initial ledger; source guards were preserved.
  - [x] Reproduce the user-reported Items search/dropdown misalignment with both a component regression and live desktop/tablet/mobile evidence; use the shared filter layout.
  - [x] Complete the requested other-master alignment review: shared CSS for native dropdown hints, reference lookups, date filters and narrow wrapping; all 45 desktop master destinations and 20 representative tablet/mobile cases pass after rechecks. Four native browser geometry cases and 27 affected product component cases pass. [Review](master-filter-alignment-review-2026-10-30.md) and reusable CSV recorded.
- [ ] **18:** current findings/coverage documentation and reusable evidence index.
  - [x] Reconcile the current implementation slice, including distinct native suite identities, historical versus final live ledgers, exact test prerequisites and bug/gap categories. [Current review](tenant-admin-current-implementation-review-2026-10-30.md), [CSV](tenant-admin-fixes-after-6-results-2026-10-30.csv) and reusable commands updated. Full backlog reconciliation follows the remaining owner/activation acceptance.
- [ ] Final simplification and security/correctness review; correct findings and rerun affected checks.
  - [x] Current completed slices reviewed manually; report lookup page/cursor strictness corrected with a reproduced regression. Final affected tests, TypeScript and Python Ruff pass. Named review commands are unavailable; equivalent checks and remaining limitations are recorded in the current review. Full final review remains after the outstanding statutory/count/activation work.

## Execution notes

- [x] User-requested UI review of #1–18 completed: [review and delivery order](tenant-admin-ui-review-2026-10-30.md), [12 bugs / 8 gaps](tenant-admin-ui-review-findings-2026-10-30.csv), and [separate execution evidence](tenant-admin-ui-review-execution-2026-10-30.csv). Reviewed desktop/tablet/phone controls and configured company forms, corrected harness timing probes, and passed 164 focused component tests. Application fixes were not made during this review.
- [x] Implement and locally verify all 12 UI bugs, three UI gaps and supported slices of two further gaps, following quick designer/draft plans. [Fix review](tenant-admin-ui-fixes-review-2026-10-30.md) and [20-row CSV](tenant-admin-ui-fixes-results-2026-10-30.csv) distinguish local verification from full acceptance. Scoped money/untaxed Purchase draft editing is now implemented; dedicated native profiles remain separate. Final supported-slice simplification/security review and corrections are recorded.
- [ ] Complete dedicated draft editors/stock source metadata, native goods/statutory Purchase, native physical count and controlled invitation acceptance. These findings remain partial/open, with the two count policy choices resolved.
- [ ] Run the reusable three-company post-fix UI acceptance after VM services return. The user shut down the VM; live post-fix acceptance is NOT_RUN, while local component/browser/type checks completed.

- Initial state: application and platform-administrator edits already existed locally; this task must preserve them.
- Existing QA tenant: `01a186e4-81a0-7221-8f57-2404a864ff43`; retained fixture IDs and credential-safe reuse instructions are in `docs/testing/tenant-admin/`.
- The earlier acceptance run used isolated backend/component fixtures plus separate real UI/API checks. Its passes do not establish unexecuted feature coverage.
- Tunnel supervisor reconnect/launch-failure/stop/foreign-listener tests plus startup/reuse tests: 9 passed. Live managed supervisor installation and reconnect passed; VM reboot/suspend was not exercised.
- Audit's 13 container/opt-in broker skips and Auth's one actual Redis-backed handler skip remain verification gaps. Full unrelated feature suites and steps 4-6 were not run or changed by this batch.
- Final live recheck completed at 2026-10-29 14:08 UTC after the last formatting guard change; all 12 named checks passed across the retained three-company tenant.
- Steps 4-6 execution and reuse details: [business batch note](tenant-admin-business-fixes-2026-10-29.md). Final owner readback completed at 2026-10-29 15:40 UTC with all six checks passing, including exact GST definition totals. Original acceptance CSVs and unexecuted feature gaps remain historical and explicit.

## Company Default product masters - 2026-10-30

- [x] User-requested permanent one Default product type and one Default product group:
      authenticated Catalog source provisioning for new and existing enrolled companies,
      audited initial publication/root edge, serialized retries and retained customization.
- [x] Replace browser General creation with bounded native-contract Default readiness,
      including published revision verification and remaining-step retry.
- [x] Local Catalog/source/disposable MySQL/UI tests and static/security review;
      [plan](company-product-defaults-plan.md),
      [review](company-product-defaults-review-2026-10-30.md) and
      [CSV](company-product-defaults-results-2026-10-30.csv).
- [ ] Live existing-company catch-up and fresh company wizard check: the attempted
      signed-source catch-up failed before company processing because Identity is
      offline after VM shutdown. Updated normal worker or documented one-shot command
      applies the pair when services return. Live records have not been reported as fixed.

## Product group/type right-side creation - 2026-10-30

- [x] + New beside both selectors, shared right-side Drawer and reused native
      group/type/requirements forms, gated by company-scoped existing permissions.
- [x] Compatible group auto-selection, explicit type publication and verified
      selection, cancelled-edit confirmation and exact uncertain-write retries.
- [x] Product draft retained in both modes; portal submit events isolated from the
      outer product form. 229 affected tests, TypeScript and 18 native browser
      layout combinations passed. [Plan](product-reference-create-drawer-plan.md),
      [review](product-reference-create-review-2026-10-30.md),
      [CSV](product-reference-create-results-2026-10-30.csv).
- [ ] Live authenticated acceptance: Identity remains offline after VM shutdown.
      Local component and fixture-browser verification is complete; live delivery
      is not claimed.

## Product family card applicability - 2026-10-30

- [x] Reproduce the always-visible card in simple and unverified product modes.
- [x] Share inventory card rules with Masters and use selected-company product configuration.
- [x] Verify mode changes, loading/failure, company scope, existing navigation and types; review and record results.
      113 affected tests passed; final 34-case hub rerun and TypeScript passed.
      [Results](product-family-card-results-2026-10-30.csv).

## Product Add price defaults and labels - 2026-10-30

- [x] Default each new price to two decimals; number rows only for multiple prices.
- [x] Verify add/remove/reindex flows in both product modes, retained edits and types.
      70 tests across five suites and TypeScript passed.
      [Results](product-price-setup-results-2026-10-30.csv).

## Remove product tax/price note - 2026-10-30

- [x] Remove the shared simple/family creation note, client state/validation and
      API inputs/detail fields/native form metadata. Keep reviewed versions,
      exact amounts and normal publication/authority checks.
- [x] Remove tax assignment and draft/published price columns with Catalog
      0211-0213; retain official tax definition evidence and audit history.
- [x] Native fresh-schema/populated-row migration and rollback checks; private
      table backup and local Catalog database upgrade to 0213 completed.
- [x] Finish the broader tax/pricing regression review and record final CSV.
- [x] Fix coordinated release bindings and master usage model exports; correct
      pricing membership fixtures while retaining rejection of unverified buyers.
- [ ] Authenticated UI acceptance after Identity/Catalog/gateway return.
      [Plan](product-commercial-note-removal-plan.md).
