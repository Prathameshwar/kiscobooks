# Product opening stock UI delivery

User authorized all phases on 2026-10-28, including final reviews and fixes.
Plan: [product-opening-stock-ui-plan.md](product-opening-stock-ui-plan.md).
Preserve existing work and paths. Reuse shared UI and styles. General posting
activation, commit/publication and a subsequent task remain separate.

- [x] 1. Workspace, readiness, scoped proxy and navigation.
- [x] 2. Product creation/detail/directory integration.
- [x] 3. Four-step entry, authoritative calculation and tracking/history.
- [x] 4. Durable worksheet, draft preparation and approval handoff.
- [x] 5. Import validation, history, resumable chunks and reports.
- [x] 6. Reconciliation, explicit zero, legacy adoption and finalization.
- [x] 7. History, revisions, exports and correction controls.
- [x] 8. Native/browser/unit/type/accessibility/theme verification.
- [x] Review 1 and fixes: contracts, arithmetic, permissions and recovery.
- [x] Review 2 and fixes: complete workflows, responsive experience and regressions.

## Implementation and evidence

The dedicated `/inventory/stock/opening` workspace replaces the generic voucher
wrapper. It reads one company cutover and its immutable worksheet, rather than
starting an independent opening for each product. Company-scoped stock readers
can review; controller, zero-declaration, draft/import, commit and export actions
have separate scoped permission checks. Server owners continue to enforce all
object and field permissions.

The four-step entry reuses shared form layout, sidebar review, stepper, searchable
references, date/decimal inputs, notices, confirmations, tables and pagination.
Calculation remains the Accounting owner?s exact-decimal operation. Entry covers
fixed product-unit conversions, warehouses/bins, RATE or VALUE, prepared batches
and serials, required manufacture/expiry facts, known/unknown receipt history,
cohort order, explicit zero-value reasons and linked opening journals. Goods-only
creation shortcuts verify an activated stock profile and preserve the existing
four-step product wizard and Create-from-any-valid-step behavior.

Worksheet registration/replacement preserves company-wide allocations and frozen
version/hash evidence. Draft preparation uses durable native opening-import jobs,
with current product/version/base-unit proofs and bounded ordered chunks (100
lines, 1,000 serials per voucher). Upload supports native JSON and CSV/TSV/XLSX up
to 2 MiB; versioned CSV/template specifications, validation, reviewed commit,
continued chunks, retained-effect cancellation, history and result CSV are exposed.
Drafts never imply stock posted. A company-scoped voucher review route reuses the
native submit/approval/issue/posting workflow and its existing authority checks.

Completion shows owner reconciliation and accounting preview, explicit narrow
zero confirmation, reviewed legacy adoption, finalization and guarded reopening.
History includes typed product/warehouse filters, unknown receipt age, stock
movement links, immutable worksheet revisions and authorized signed CSV exports.
Posting corrections continue through native vouchers and their dependencies.

### Review 1: contracts, security and recovery

Reviewed CLAUDE.md sections 5?6 and simplified the implementation. The `/simplify`
and `/security-review` slash commands are not tools in this Codex session; their
required subject areas were reviewed explicitly instead.

Fixed opening access being coupled to stock-post authority; added the missing
native voucher-detail handoff route; added a narrow same-origin owner allowlist,
bounded upload envelope and private CSV passthrough; rejected malformed paths,
fragments, control characters, duplicate and unsupported query parameters.
Preserved exact command body/key after unconfirmed responses, frozen worksheet
versions across local edits, ownership checks, protected-cost failure behavior,
current item proofs, explicit values and BigInt-only client totals. Ordinary
product proxy limits were preserved. No new endpoint, model, migration, permission
or generated-client change is needed for this UI delivery.

### Review 2: workflow and experience

Fixed unit-selection timing; reset allocation-only state after Add so retained
warehouses cannot block worksheet saving; added explicit discard confirmation,
step/error focus, honest step completion and persistent conversion/value review.
Fixed manager-only template reads for history-only reviewers and a parent refresh
that could unmount a newly staged job. Added batch manufacture/expiry/shelf-life
checks, business serial labels, preserved unit/serial selections, physical-location
filtering, mandatory labels, paged worksheet rows, guarded navigation, consistent
tab styling and wrapped evidence text. Closed/pending stock blocks editing; Ready
jobs can be explicitly revalidated. Untouched opening value is shown as Not
declared rather than an implicit zero.

### Verification

- Console TypeScript check passed.
- Final focused/regression run: **158 tests passed in 18 files**, including the
  opening proxy/allowlist, decimal arithmetic, native draft construction,
  company-scoped pages, four-step entry, inclusive batch expiry, serial counts,
  full-worksheet retention, exact retries, zero declaration, incomplete
  reconciliation, import commit/cancel/history, revisions, product activation
  shortcuts and the existing advanced/simple product creation and import flows.
- Native authenticated reads as tenant3 verified readiness/capabilities and import
  history. Identity, Catalog, Accounting and Vouchers readiness returned 200.
- Live tenant3 browser checks verified worksheet, import history and reconciliation,
  light/dark/ledger palettes and a 390px mobile viewport, with zero page errors and
  no document horizontal overflow. Screenshots were inspected. The stopped managed
  Authentik SSH tunnel was restored for sign-in; no provider account or role was
  modified for this UI work.
- Existing native stock/calculation/import/GL engine evidence remains in
  [the API delivery record](product-opening-stock-api-delivery.md). These UI changes
  do not change the database or engine admission policy.

### Activation and verification limits

The existing QA company reports legacy stock requiring controller review and
missing account mapping at books begin. Those balances were not adopted,
restated, finalized or posted by this UI review. Positive command and edge-case
UI tests use controlled owner responses; the native engine?s positive physical
posting evidence belongs to the preceding API delivery. Normal installation
stock posting remains disabled, with its reason visible. Commit/publication and
another task await the user?s instruction.
