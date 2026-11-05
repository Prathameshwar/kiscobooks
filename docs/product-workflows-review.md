# Product workflows: end-to-end review

Authorized 2026-10-28: review creation, management and operational use in both
single-product and Product Family/SKU modes; reproduce and fix gaps, then verify.

- [x] Map current creation, edit, setup, activation and operational contracts.
- [x] Exercise both modes in the authenticated application.
- [x] Review state changes, permissions, metadata, retries and linked records.
- [x] Reproduce findings with focused tests and apply fixes.
- [x] Run relevant regression suites and TypeScript checking.
- [x] Review the final changes for simplicity, authorization and data preservation.

Preserve the original company setting after live verification. Keep verification
records clearly named. Record actual lifecycle and operational evidence separately;
a passing create/edit journey does not establish that stock posting succeeded.
The previously reported repository-wide function coverage gate remains open until
a later coverage run proves it meets the configured threshold.

## Findings and evidence

1. Specification declaration changes (roles, allowed options, order and removal)
   were absent from the unsaved-change check. Include them; protect page navigation
   and company changes, and require confirmation before replacing a draft through
   the product selector. The same guard covers both product modes.
2. An unconfirmed specification/variant save could be followed by edits and a
   different request/key. Freeze the fields, retain the original receipt, prevent
   other writes and recover the original save. Keep confirmed receipts until the
   follow-up read succeeds. Validate native write responses before accepting them.
3. Specification editing did not explain or block a changed/unavailable authoring
   mode. Preserve entries and block new writes, including a changed simple-product
   authoring version. Recovery of a previous command remains available.
4. Live activation correctly rejected a commercial verification product without
   tax configuration, but showed six identical "Review tax" messages. Explain the
   missing classification, treatment or published rule separately for sales and
   purchases, including future effective boundaries. Preserve native eligibility.
5. Simple-product activation used the advanced "SKU activated" success message.
   Use the product label in simple mode.
6. Activation was repeatedly impossible after an equivalent Identity refresh:
   its signed digest included the changing transport watermark in configuration
   and nested tax resolutions. Three immediate live attempts failed with 409.
   Configuration adoption had the same defect. Exclude only that transport counter
   from the reviewed values; retain current source freshness and authorization,
   actual configuration/tax values, policy generation, revisions and dependency
   pins. Commit still records the current watermark. New tests reproduce both
   configuration and nested-tax failures and require changed settings/generations
   to reject the old review. No API schema or posting contract changed.
7. Active product details lacked the directory's stock, tracking and opening
   actions. Reuse that same eligibility/permission-checked menu on the detail in
   both modes, with a visible Inventory label. Preserve unsaved setup navigation
   guards and omit the menu for known service products.

Core UI regression: 197 tests passed across 11 suites. Covers both creation
flows, variant creation, declaration/value writes, stale mode/version guards,
interrupted saves, activation, tracking completion and stock-action permissions.
After the final receipt-control refinement, 46 focused tests passed across the
attribute, readiness and accessibility suites. Final TypeScript checking passed.
Ruff and strict mypy checking passed for all three changed Python task modules.

Authenticated live evidence: commercial simple-product activation correctly
rejected missing tax setup; a clearly named internal simple product was created,
activated after the source-refresh fix and edited while active. The advanced
wizard created a family/default SKU; the SKU activated through the reviewed UI
action and was then edited while active. Native readback confirmed lifecycle state
and identity. Original company mode restored, with no browser page errors. Evidence:
`.test_artifacts/product-workflows-live.json` and
`.test_artifacts/product-workflows-activation-probe.json`. Two internal verification
products remain active with selling/purchasing disabled. No stock or financial
voucher was posted and no tax rule was fabricated or changed.

Operational UI regression: 173 tests passed across 13 suites, covering imports,
configuration adoption/retries, stock screens, batches/serials, opening entry,
related actions and guarded simple setup. The initial Catalog regression passed
38 tests across seven suites. A final run covers the changed activation/adoption
owners and reports their coverage separately.

Final manual simplicity/security review: use shared confirmation/navigation guards
and existing controls; add no CSS, dependency, table or API schema. Review tokens
retain actor/company binding and expiry. Current permissions, hidden/read-only
fields, source freshness, native references, product versions, configuration values
and policy generation remain enforced. Equivalent transport refreshes do not
change those reviewed values. Unknown saves retain the original operation/body/key
and confirmed saves retry readback without repeating a mutation. No posting or
money-validation path was widened. `/simplify` and `/security-review` are not tools
in this session; these are their manual equivalents, following CLAUDE sections 5/6.

Final detail/inventory checks: 61 tests passed across the detail and product menu
suites before aligning the trigger with the shared Menu's visible-label contract;
the final inventory suite then passed all 23 tests. Authenticated browser checks
in both modes confirmed the visible Inventory menu explains a non-stock product's
missing activated stock profile, disables Manage stock and omits Record opening
stock. The original company mode was restored. Final readiness wording tests
passed 21/21, and final TypeScript checking passed after the menu integration.

Final backend result: **19/19 tests passed**, including all six new
activation/adoption source-refresh cases, existing activation rollback/permissions,
price coverage and adoption boundaries. Combined coverage of the three changed
backend owners is **91.01%**, meeting the configured 90% threshold. This is scoped
coverage, not a claim about whole-service coverage. Output:
`.test_artifacts/product-workflows-api-final.log`; coverage JSON:
`.test_artifacts/product-workflows-api-coverage.json`. The six new cases also
passed independently without instrumentation. The final UI sets cover **372
distinct tests** (197 core + 173 operational + two additional detail-menu cases),
with affected suites rerun after refinements.

Review complete: all seven implementation findings above are fixed. The earlier
repository-wide console function-coverage gate remains open (last full report:
77.12% versus 90%); it was not relaxed or represented as passing. No commit or
publication was performed.
