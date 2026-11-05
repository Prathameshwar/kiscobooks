# Items / Products delivery review

2026-10-31. User authorized end-to-end review and fixes following the Items-page
product-fields 422 fix. Scope: existing Items/Products authoring flow and its native
Catalog/proxy contracts. Preserve Purchase work and unrelated workspace changes.
No repository publishing, production activation, authoring-mode change or financial
posting. Browser fixtures may publish requirements for a newly created QA-only type;
existing business types and their revisions are not changed.

## Passes

1. Trace existing contracts and establish live and automated baselines.
2. Reproduce defects, apply focused fixes and run affected regression tests.
3. Repeat authenticated browser flows, review security/correctness and record limits.

## Todo

- [x] Review directory, query/proxy validation, paging and return navigation.
- [x] Review product detail, create/edit, setup and confirmed/uncertain save behavior.
- [x] Verify loading, errors, denied fields and company/mode changes in affected suites.
- [x] Establish authenticated browser baseline using the supplied local QA account.
- [x] Reproduce each confirmed defect with a failing regression before fixing it.
- [x] Verify draft create, reload, edit and return to filtered directory in the browser.
- [x] Verify search, status/sort filters, empty states and permission/recovery regressions.
- [x] Check desktop/mobile layout and keyboard-accessible controls.
- [x] Run focused tests, TypeScript and applicable build verification.
- [x] Complete manual simplify/security review against CLAUDE.md sections 5 and 6.
- [x] Record final evidence, QA records and remaining delivery constraints.

## Findings and verification

- Fixed bookmarked searches outside the shared 2–200 character bounds triggering
  Catalog 422 responses. Valid search text is trimmed before sending.
- Fixed route guards treating product/reference search punctuation as traversal.
  Route checks still reject traversal, encoded separators and untrusted origins;
  duplicate/unknown query keys and decoded control characters remain refused.
- Fixed read-denied status appearing as a filter and table column or being sent
  as a filter. Field authority still comes from the native field-set contract.
- Live review then exposed that the facade omitted status metadata even for an
  authorized reader. Added native read-only status to the facade descriptors.
  A new MySQL regression failed before the fix; its final recheck also verifies
  read-denied metadata and server-side status-filter refusal. This changes runtime
  descriptors within the existing response model; no schema/client regeneration
  or migration is needed.
- Preserved Next navigation state when replacing filter URLs and clearing filters.
- Baseline: 203 affected Console cases passed before new regressions.
- Red evidence: nine initial regressions, one additional status-column regression,
  and three reference-search regressions failed for their stated reasons before fixes.
- Final broad run: 281 passed / four failed. Three failures were the deliberately
  added reference regressions while that run held the pre-fix module; the fourth was
  a directory action lookup timeout under load. Targeted rechecks passed all 136
  transport cases and all 29 inventory-action cases without changing that test.
- TypeScript and the actual Next production build pass. Build ID:
  `T2r36pNKXUNeZBbZrbhFz`. The isolated build completed compilation, type/lint checks,
  all 15 static pages and traces; generated configuration changes were restored.
- Authenticated type/group creation (preserving the parent draft), draft creation,
  saved-detail reload, editing, filtered directory return, mobile directory/form,
  keyboard validation, unsaved-change confirmation and transport recovery pass.
  The edit recheck confirmed the saved name through native GET and a browser reload.
  All 13 browser checks passed across the full run and focused rechecks. The full
  run passed 11 checks; the repeated edit fixture supplied its already-saved name
  (correctly disabling Save), and one return navigation remained on Loading product
  settings. The runner now alternates two QA names to make a real edit; save,
  native readback, reload and filtered return passed on recheck. Raw failed reports
  are retained alongside the final per-check result in validation.json.
  The search harness now uses the
  documented indexed prefix (including punctuation), rather than a middle-of-name
  substring. Cold development-route waits are allowed without changing app behavior.
- Earlier live runs encountered an unavailable/restarting Console, transient
  authentication unavailability and a development-page 404. The unchanged edit
  route subsequently passed; no application routing fix is claimed for that event.
  QA records are retained: one draft product, one product group and one newly
  published QA type requirement revision. No financial transaction was posted.
- Native MySQL Catalog verifier: seven product workflows, concurrent idempotency,
  three mode/axis races, model parity, and upgrade/downgrade/reapply all passed.
  The full recheck including status metadata/read-deny/filter-refusal passed.
  An earlier attempt encountered a retryable native lock conflict in a separate
  specs/axes workflow; the unchanged workflow passed on the full rerun.
- Additional request: added the Voucher types card under Company settings →
  Business configuration. It uses the existing company-scoped read/manage grants;
  all 23 settings-page cases, TypeScript and authenticated card navigation passed.
  Default voucher-type
  provisioning remains a separate onboarding gap in the Purchase API todo.

Manual simplify/security review: changes reuse shared search bounds and existing
metadata/list/navigation components. No new dependencies, API routes, models,
migrations or financial behavior. Proxy destinations remain fixed to the gateway; query values
cannot become routes or origins. Read-denied status is suppressed in controls,
requests and columns. Native authorization, scoped sessions, audit/outbox behavior
and replay keys are preserved. No additional security finding from the changed
code. Browser credentials stay DPAPI protected; screenshots remain private.

Evidence: [browser report](testing/items-delivery/review.json),
[final validation and per-check sources](testing/items-delivery/validation.json),
[edit recheck](testing/items-delivery/review-recovery.json),
[navigation recheck](testing/items-delivery/review-navigation-recovery.json),
[runner](testing/items-delivery/review.cjs), private screenshots in
`.test_artifacts/items-delivery-20261031`, and local test logs in `.tools/items-delivery-*`.
The earlier Purchase API tracker retains its separate pending items.
