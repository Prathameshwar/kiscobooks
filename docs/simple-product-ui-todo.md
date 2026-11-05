# Simple product UI delivery

Authorized 2026-10-28: implement all phases in simple-product-ui-plan.md, maintain
this checklist, review twice and fix findings. Preserve existing unrelated work.

- [x] 0: readiness and contract/layout specification.
- [x] 1: company mode provider and closed proxy routes.
- [x] 2: live Product Configuration control.
- [x] 3: navigation, directory and legacy links.
- [x] 4: one-product creation form and setup.
- [x] 5: aggregate editing, detail and ordinary specifications.
- [x] 6: stock, tracking, voucher labels and opening entry.
- [x] 7: simple imports, templates and result links.
- [x] 8: responsive/theme/accessibility verification and regression checks completed;
  the repository-wide function coverage gate remains open below.
- [x] Review 1: usability, reuse and correctness; findings fixed.
- [x] Review 2: permission, company isolation and retries; findings fixed.
- [ ] Repository-wide function coverage: 77.12% versus the configured 90% floor.
  This is an unresolved acceptance gate; do not report the coverage run as green.

## Evidence

Use shared @janso/ui layouts and styles. One product identity in simple mode;
preserve the existing advanced workflow. Record checks and limitations below.

- Local Catalog readiness: applied the additive 0209 -> 0210 migration. Captured
  the authoritative Identity company roster and used the existing audited seed
  under the authenticated operator identity: seven existing companies retained
  advanced mode; a subsequent dry run found zero missing compatibility rows.
  Credentials stayed in process memory. No existing product/stock identity changed.
- New proxy/provider/editor/settings tests: 38 passed. Targeted existing product
  classification, attributes, inventory actions and pages: 101 passed.
- Further regression run: 272 passed, two findings. The import issue test passed
  on isolated rerun; the inventory-card expectation was updated for the intended
  behavior when mode read access is absent. Review rerun: 63 passed.
- Authenticated browser verification: simple directory and both New URLs; one
  product identity form; light/dark/ledger at 1440px and 390px with no horizontal
  overflow. Screenshots inspected; reused the shared two-column form grid for
  a clearer order of name/code, kind/type, unit/quantity and buy/sell controls.
- Review fixes so far: retain drafts during mode refresh/change; freeze accepted
  default receipts; preserve exact uncertain saves; clear optional text fields;
  review a stale aggregate revision explicitly; verify returned metadata/company;
  keep in-progress imports in their original mode; preserve setup navigation and
  unsaved-change guards within the simple product detail.
- Final native-adapter regression: 156 passed. Review/fix regression: 72 passed.
  Final focused check: 82 passed, including ordinary specifications through the
  product facade, guarded group/category writes, stale edit reconciliation,
  company switching, preview blockers and exact settings-review retries.
- Authenticated live create -> detail -> aggregate edit passed. One unactivated
  verification product draft remains, with clearly named verification product
  type/group prerequisites. No financial or stock voucher was posted. The original
  company mode was restored, then independently restored through the real UI's
  preview-and-save workflow during final verification.
- Settled detail and import screens, three themes and two viewport widths passed
  browser checks without horizontal overflow or page errors. Native family setup
  stays inside the product page; groups/manufacturers and units/barcodes have
  distinct headings. Specifications/group/manufacturer/category writes use the
  guarded product facade; ordinary item features retain native operational IDs.
- Final review found and fixed an unconfirmed settings-preview retry changing its
  request after another operator updated the saved mode. Regression proves body
  and idempotency key remain identical, including when the current mode now
  matches the requested choice. Both simple and advanced editors retain drafts.
- Manual equivalents of /simplify and /security-review were performed because
  those commands are not available in this session. Reviewed CLAUDE sections 5/6,
  scoped permissions, company changes/late responses, closed proxy routes,
  metadata/returned IDs, mutation replay, read-only/hidden fields and exact values.
  No unresolved implementation findings remain.
- Additional review fixes: server validation now focuses the affected field while
  retaining entries; simple specifications use product labels for screen readers;
  and an open advanced family draft cannot be resolved/redirected after a mode
  change. Each issue was reproduced with a failing test before its fix. The last
  mode/draft regression passed all 16 tests; final TypeScript checking passed.
- Final interaction checks passed 43 tests across creation, validation, uncertain
  retries, draft refresh and the current sales-entry checks. Specification and
  accessibility checks passed 20 tests. Authenticated browser results are recorded
  in `.test_artifacts/simple-product-final-browser.json` (no page errors, no
  financial posting, original company mode restored).
- The first broad console run completed 4,181 tests successfully, with six test
  failures and one transient suite-load error. Two were five-second timeouts;
  one used a cached directory module from before its sort control was added;
  three voucher tests still mocked the previous save boundary/invalid saved IDs.
  Those voucher fixtures now use the current boundary and valid verified results
  (5/5 passed). A concurrently removed diagnostic probe caused the suite-load
  error. The fresh final full run uses the completed source and controlled workers.
- Final full console run: **276 files / 4,255 tests passed**, with no failing
  test. Lines/statements **91.81%** and branches **85.70%** meet their configured
  floors. Functions **77.12%** do not meet the configured **90%** floor, so the
  coverage command exits nonzero. Among the 389 app files unchanged in the current
  working tree, function coverage is independently only **77.79%** (2,388/3,070).
  Broad unrelated coverage work is outside this product UI delivery; thresholds
  and exclusions were not weakened. Full output and JSON summary are retained in
  `.test_artifacts/simple-product-reviewed-coverage.log` and
  `.test_artifacts/simple-product-ui-reviewed-coverage-20261028/coverage-summary.json`.
- After the final fixes, a fresh acceptance run of all 11 new product UI/policy
  suites passed **65/65 tests**, including the last family-draft and validation
  focus regressions. Final TypeScript checking passed. No commit or publication
  was performed.
- Follow-up end-to-end review of both modes: findings, fixes, authenticated
  creation/activation/edit journeys and current regression evidence are recorded
  in [product-workflows-review.md](product-workflows-review.md). This includes the
  activation/adoption fix for equivalent Identity source refreshes.

- [x] 2026-10-30: product group/type + New right-side panels implemented with reused
      native forms. Both product modes retain drafts and select compatible saved
      groups; types require explicit publication and option verification. 229
      affected cases, TypeScript and 18 native fixture layout combinations passed.
      [Review](product-reference-create-review-2026-10-30.md) and
      [CSV](product-reference-create-results-2026-10-30.csv).
- [ ] Live acceptance of these panels after Identity services return. Identity is
      currently offline; these new local checks do not replace authenticated E2E.
