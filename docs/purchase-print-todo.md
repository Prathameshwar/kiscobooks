# Purchase printing delivery

2026-10-31. User authorized including Purchase printing and making the necessary
changes and fixes. Continue phase by phase under that authorization. Preserve
unrelated workspace edits and the pending Purchase API owner work.

## Phases and todo

1. Contract and baseline
   - [x] Trace Purchase actions, Design routing/canvas and Vouchers artifacts.
   - [x] Identify existing renderer, disclosure and download gaps.
   - [x] Resolve the renderer/runtime/authority decision required by
     [invoice-design.md section 9](invoice-design.md#9-open-questions).
   - [x] Record supported layouts, frozen source facts, formats and fallback rules.
   - [x] Establish affected unit/native baseline (138 Console / 9 artifact cases).
2. Preview and print interaction
   - [x] Add an isolated saved-revision print route and entry-button helper.
   - [x] The Purchase page shows Print for the last saved revision (2026-11-01): a link when it may be printed, a
     disabled button saying why when it may not (unsaved edits, an unconfirmed request, a posting in progress, an
     open editor). Hidden without company-scoped `vouchers.read`, `vouchers.artifact.create`,
     `vouchers.artifact.read` and `accounting.account.read`. See [purchase-e2e-review](purchase-e2e-review.md).
   - [x] Accept saved revision/version identities only in the print API.
   - [x] Review the entry button's unsaved-edit and uncertain-command guards (`purchasePrintAction`, tested).
   - [x] Implement an accessible preview with loading, retry and failure states.
   - [x] Distinguish draft/cancelled/reversed copies and internal Purchase voucher
     output from the supplier's original tax invoice.
   - [x] Preserve company display formats and exact owner-produced amounts.
3. Rendering and protected delivery
   - [x] Render the standard layout and the documented restricted A4 flow profile.
   - [ ] Honor the full Invoice Designer canvas and all supported designer features.
   - [x] Bind output to voucher revision, template version and disclosure scope.
   - [x] Implement protected generation/status/download and safe retry/reprint.
   - [x] Recheck current company/native field authority and owner facts at download.
   - [x] Record deployment, worker and private-storage requirements.
4. Verification and review
   - [x] Write failing regressions before fixing confirmed defects.
   - [x] Verify long descriptions, many lines, repeated headers and a single totals block.
   - [ ] Check preview on desktop/mobile and inspect generated PDF pages.
   - [x] Test wrong-company, denied fields, permission revocation, stale revision and replay.
   - [ ] Run affected tests, typecheck/build and native worker/API verification.
   - [ ] Complete simplify/security/correctness review and fixes.
   - [ ] Record evidence and any remaining deployment/coverage limits.

Each phase closes with its tests, review, fixes and an updated checklist. Printing
does not allocate a voucher number, post, approve, pay or change saved bill facts.

## Initial findings

- Connected Purchase has no print action.
- Design owns layout versions and resolution; its current no-rule fallback is
  the most recently published company template, while the agreed standard-layout
  fallback is still pending implementation. Console text describes that planned
  state as though printing were already available.
- Vouchers has an existing asynchronous HTML artifact foundation and protected
  two-minute download tickets. Its renderer currently prints JSON sections, not a
  finished Purchase voucher or a PDF, and requires a separately provisioned legacy
  template revision.
- The legacy artifact template field vocabulary does not include invoice facts.
- The product-fields proxy permits artifact creation but does not expose artifact
  status/download. The connected Purchase screen does not consume this pipeline.
- Do not open the browser-only Design render-evidence write route: that would
  let a browser assert evidence without producing a verified artifact.

## Accepted choices and parallel ownership

The user accepted Chromium/Celery on their VM, private local disk and a dedicated
service identity, then accepted a versioned standard A4 layout shipped with the
renderer. Custom published rules remain immutable and take precedence.

The user is implementing Purchase entry UI in parallel. Printing changes belong in
separate modules; do not edit their entry components, entry contracts or their tests.
The print screen is `/vouchers/{voucherId}/print?revision={revisionId}&version={rowVersion}`.
`app/lib/purchase-print.ts:purchasePrintHref` creates that link. Its input must come
from the last confirmed save, not the editor's provisional values. Entry UI must gate
the button on `vouchers.read`, `vouchers.artifact.create`, `vouchers.artifact.read` and
the absence of unsaved edits or uncertain commands.

The same-origin `/api/purchase-print` proxy serves only:

- `POST /v1/companies/{company}/vouchers/{voucher}/print-jobs` with
  `{expected_version, revision_id}` and a stable idempotency key.
- `GET /v1/companies/{company}/voucher-print-jobs/{job}` for status.
- `GET /v1/companies/{company}/voucher-print-jobs/{job}/download?token=...` for a
  current-authority, integrity-checked PDF. Tickets expire after 120 seconds.

These contracts have focused unit/native verification; the release checks below remain.
No runtime storage/broker/worker configuration has been enabled by merely adding them.

## Evidence so far

- `.tools/purchase-print-context-red.log`: reproduced missing signed Vouchers display
  facts. `.tools/purchase-print-context-green.log`: 3 Identity context cases passed.
- `.tools/purchase-print-design.log`: signed company/tenant resolution and built-in
  fallback/custom priority case passed, including canvas float geometry.
- `.tools/purchase-print-final-tests.log`: 38 affected Vouchers/artifact/supporting-file
  cases passed. `.tools/purchase-print-mysql-final.log`: the final 15 Purchase-print
  cases, native migration/model/index parity and downgrade/upgrade passed against a
  disposable MySQL schema. No live schema was changed.
- `.tools/purchase-print-accounting-tests.log`: 10 owner cases passed, including exact
  preview and immutable posted amounts after master changes and field-denied access.
- `.tools/purchase-print-console-tests.log`: 33 preview, page, proxy and PDF-integrity
  cases passed. `.tools/purchase-print-shared-ui.log`: 23 shared style/layout checks passed.
- Strict mypy passed for 11 Vouchers, 3 Design and 2 Accounting source files. Focused
  Ruff checks passed for the new renderer/owner code and tests.
- `.test_artifacts/purchase-print-20261031/standard-pdf-page-1.png`: actual A4 PDF
  inspected visually. `layout-checks.json` records the large-amount column bounds after
  fixing numeric clipping. Multipage PDFs were inspected through extracted page text.
- `.tools/purchase-print-custom-red.log`: confirmed A5 custom paper was silently
  discarded by the first renderer draft. Unsupported paper/options now fail explicitly.
- `.tools/purchase-print-revocation-red.log`: reproduced a download remaining available
  after an owner permission was removed. The print disclosure fingerprint now includes
  effective company-scoped grants and actor groups; the final native regression passes.

## Review findings and fixes

Manual security/correctness review covered CLAUDE.md sections 5 and 6. The requested
slash-command reviewers are not available in this session; this records the manual
equivalent, not a claim that those commands ran. Reviewed company/tenant boundaries,
current native and owner field access, immutable posted facts, exact Decimal formatting,
idempotent admission, audit/outbox atomicity, worker leases/duplicate delivery and PDF
integrity. The renderer child has a restricted environment, no service credentials,
disabled network/JavaScript and a parent-enforced timeout. Source and completed job
evidence are immutable. Review also fixed the tenant-guarded pending-count query and
large-amount clipping. These checks do not replace VM identity/sandbox verification.

## Independent review hardening (2026-11-01)

Part of the [end-to-end review](purchase-e2e-review.md). Each fix started with a failing
test (`.tools/purchase-print-*-red.log`).

- **Worker hang (high).** A stuck browser could block the single Celery worker. The parent
  now owns a bounded stop sequence (Windows Job Object, bounded `taskkill` fallback), the
  child bounds each step and exits 75 → `RENDER_TIMEOUT`.
- **Lost PDF.** A finished PDF could be replaced by the deadline watchdog or lost behind a
  hung driver exit. It is now delivered before teardown; the watchdog is disarmed under a
  lock first.
- **Continuation pages** carried no identity. Every page footer now repeats the voucher
  number, supplier, supplier invoice reference and date (escaped).
- **Button gate** omitted `accounting.account.read`; the Console and the print page share
  one `PRINT_PERMISSIONS` list.
- **Open at that review:** no ledger account per line, no company address/GSTIN/PAN, only the due
  date as terms, no tenders/advances on the page, non-base currency cannot print, names and
  display formats are not frozen to the posted bill, Design can publish layouts the print
  refuses, downloads are not audited. Decisions are in the review's D6.

## Print content follow-ups (2026-11-01)

Done under the owner's "best fit" direction (see [purchase-e2e-review](purchase-e2e-review.md) 6.1):

- [x] Accounting's journal number prints as "Voucher no." on a posted bill (header block, page
  footer, custom binding); a draft says "Not allocated".
- [x] Expense ledger name under each particular; restricted names print "Ledger restricted".
- [x] Supplier invoice no. and date, payment due, credit period (derived).
- [x] Tenders (mode, cash/bank ledger, reference, date), advances and credits, and the balance after.
- [x] Display formats frozen in the snapshot and covered by the integrity hash (already the case; now tested).
- [x] Foreign-currency bills refused before the owner is asked, naming both currencies.
- [x] `purchase-pdf@2` and `purchase-a4@2`; local-only, off-by-default Chromium sandbox switch;
  `vouchers.print_job.download` access audit event.

Remaining content gaps, in the order they would matter:

- [ ] **Company legal name, address, PAN and GSTIN on the header.** The signed company context from
  Identity carries the display name and formats, and `registrations` without their numbers. Adding
  them is an Identity contract change (a versioned, signed extension of the context, with its own
  field-policy story for tax identifiers); a synchronous Identity call inside the print path is not
  allowed. The header names the company by its display name only.
- [ ] **Foreign-currency bills.** Needs Accounting to calculate and post foreign-currency invoices
  (an exchange rate and base-equivalent amounts) first; then the print needs the currency's minor
  units and both amounts. Today such a bill is refused with a clear message.
- [ ] **Credit days stored on the bill.** The bill stores only a due date, so the credit period is
  derived (due date minus invoice date). If a bill ever stores terms or credit days, print those.
- [ ] **A stored voucher number.** Vouchers does not store Accounting's number; only the print
  carries it. Showing it on the voucher screen needs the execution result to return the number text
  and a Vouchers column (migration, schema, Console).
- [ ] **Tender ledger names for a posted bill** come from the saved bill, protected by its accepted
  calculation hash, not read back from the posted journal lines.

Limitation, accepted: **master names are not frozen at posting.** The supplier's and the ledgers' names
(and the company display name and formats) are read when a print job is created and frozen into that
job, so a retry or re-render of the same job is identical. A new print after a rename shows the new
name. Tally Prime and QuickBooks reprint with current master data in the same way, so historical
re-freezing of names at the time of posting is not required; posted amounts, dates, numbers and
references always come from the posted records.

## Invoice Designer integration status

Purchase resolves the matching published Design rule, freezes its immutable version,
and falls back to `purchase-a4@2` (was `@1` until 2026-11-01) only when no published rule matches. Publishing a
template alone does not select it for Purchase. Draft designer edits do not print.

Full designer fidelity is **not complete**. The current renderer accepts only the
restricted A4 flow profile documented in [purchase-print-deployment.md](purchase-print-deployment.md).
It refuses unsupported designs explicitly rather than substituting a different layout.
Images/signatures, QR/barcodes, arbitrary placement, advanced table/totals options,
reusable components and other paper/copy settings remain pending.

## Remaining delivery gates

- Finish the combined Console production build after the parallel entry UI changes settle.
  The fresh combined Console typecheck passes; the earlier entry-controller `totals`
  error is resolved in the current workspace. Preserve the UI owner's edits.
- Complete browser desktop/mobile review of the isolated preview. Unit/native coverage
  is recorded above; it is not an authenticated browser-to-worker deployment test.
- Complete full custom designer rendering and visual parity verification. No silent
  custom-layout substitution is permitted.
- Rehearse an authenticated browser-to-worker delivery in isolated QA configuration.
- Configure the deployment's private root, scoped HMAC credentials, separate worker
  database identity, RabbitMQ dispatcher/worker and Chromium sandbox/runtime.
- Record Design render evidence through a signed worker-only path, if included in this
  release; the browser-only `/renders` proxy must remain closed.
- Connect the entry button through the parallel UI work and review its save-state gate.

## Quick end-to-end readiness check (2026-10-31)

Requested after the Invoice Designer integration clarification. Fresh Console print
tests passed: 33 cases across preview, server page, proxy and PDF integrity
(`.tools/purchase-print-quick-console.log`). Three fresh backend checks also passed:
saved-invoice/owner preparation, real Chromium multipage output, and the actual worker
subprocess/private-disk/protected-download path (`.tools/purchase-print-quick-native.log`).
Owner HTTP boundaries are mocked in these focused tests; they do not exercise the
deployment's broker or establish full cross-service browser delivery.
The combined Console `tsc --noEmit --incremental false` check also completed successfully
(`.tools/purchase-print-quick-tsc.log`; empty output, exit 0).

Live Vouchers (`8012`) and Design (`8014`) readiness probes return 200. However, their
running OpenAPI documents contain neither the new Purchase `/print-jobs` route nor
Design's `/internal/v1/print-layout` route. The checked-in implementation has not been
loaded into those running processes. The Console print proxy exists (GET returns 405,
as expected for its POST-only contract).

The local Vouchers and Design environment files also have no print-specific settings,
and the Purchase entry header does not yet call `purchasePrintHref` or expose a print
action. No application/service restart, live migration, financial posting or runtime
configuration change was performed during this check. Live end-to-end printing is
therefore **not ready**; isolated passing tests must not be described as a completed
browser-to-service-to-worker delivery.

Required sequence: connect the saved-revision entry action, apply the matched migration
and service code, configure scoped print identities/private storage/broker/worker, then
verify an authenticated standard-layout copy and a matching supported published custom
layout through real PDF download. Full designer rendering remains separately pending.

### Subsequent local activation during voucher-defaults review

On 2026-10-31, the user supplied local migration credentials. The existing Vouchers
database was backed up, migration `0111` alone was applied with original document/type
row counts retained, and the managed Vouchers API was restarted and is ready. Its Purchase
print route is now loaded along with the reviewed voucher-default bootstrap. This supersedes
the earlier Vouchers code/migration snapshot above. Design and print-specific configuration,
broker/renderer activation and browser-to-PDF delivery remain separate pending work; this
activation does not establish end-to-end printing readiness.
