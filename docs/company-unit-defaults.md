# Automatic company units and packaging

## Plan

1. Provision a bounded versioned Catalog-owned starter set from verified company
   settings: count/service units for active companies; metric/count stock units
   and packaging labels only when inventory is enabled. No schema changes.
2. Connect the existing enrollment worker and company wizard to the same atomic,
   idempotent provisioner. Preserve existing units, conversions and pack types;
   never infer a box/bag size or reinterpret retained product quantities.
3. Verify native authority, field policies, audit, retries, configuration changes,
   rollback/isolation, exact conversions, API/SDK sync and real company setup.
4. Live verification found that another company pushed the user's existing gateway
   grant envelope beyond its 24KB transport bound. Scope the signed company request
   to tenant grants plus that company's company/department grants, preserving exact
   permissions and validity windows. Keep the bound and noncompany behavior intact;
   verify Identity gateway regression/step-up/isolation and resume the same company.

## Decisions

- Units and conversions have no separate company capability flags. Inventory is
  the existing gate for physical stock defaults and pack labels. Noninventory
  companies still use piece, hour, day and job quantities for ordinary services.
- Ratios are exact positive integers, reduced and direct to canonical roots.
  A day means 24 hours of elapsed time, not a working day. Months, working days,
  product/container sizes, density and dimensions are never guessed.
- Starter conversions are created only for newly inserted units. Existing units
  without declarations remain untouched. A new unit can target an existing root
  only when its semantic settings and identity declaration match the starter pack.
  This prevents backfill from changing the meaning of existing product history.
- Renamed, inactive, custom-precision or custom-conversion records are preserved.
  Skipped relations are reported as notices; users can review them in the existing
  masters screens. Physical defaults are retained when inventory is later disabled.
- Native exact quantity storage and target-unit precision still govern conversion
  results. Unrepresentable quantities reject instead of rounding.
- Setup supplies its expected inventory setting. A source snapshot still showing
  the previous setting returns the existing transient `source_unavailable` error
  before any receipt or data is committed. The same setup key/body can then retry.
- Unit and tax default transactions are independent from the verified source lease
  and from one another. A runtime failure is logged and retried on refresh; it
  cannot roll back a valid lease or suppress the other provisioner's work.
- Company requests transport only their applicable grants; the 24KB gateway bound
  is preserved. Other-company grants remain in the original session actor.

## Verification

Native scope: 4 service/count units and declarations, expanding to 17 units,
17 canonical declarations and 8 pack labels with inventory. No ORM model or SQL
schema changes are needed. The source refresh covers API-created companies and
later inventory enabling; the Console awaits verified readiness before continuing.
The operator command in [seeds/units](../seeds/units/README.md) completed against
the configured installation. Existing eligible companies were backfilled.

Review 1 covered exact arithmetic, canonical-root ordering, native quantity
precision, company/tenant boundaries, retained product semantics, immutable
conversions and audit rollback. Preserved existing undeclared units rather than
adding relationships that could reinterpret their historical SKU quantities.
Replays check the exact committed fields against current row/field authority.

Review 2 covered setup feature synchronization, idempotency receipts, independent
worker failure recovery, proxy allowlists, packaging and live company creation.
Fixed the feature-timing/sticky-receipt risk and the accumulating gateway-context
failure discovered during the first live company creation. The original company's
remaining steps completed with its original company ID and setup keys.
Manual simplify/security/correctness review substitutes for the unavailable slash
commands; no authority bypass, automatic role widening or transport-limit increase.

- 218 focused Console tests passed; Console TypeScript passed.
- 39 Catalog unit/source/tax regression tests passed. The final expanded 28
  default/source checks passed, including expected-feature retry without a sticky
  receipt, native exact conversion, wrong-company rejection and independent
  tax setup after a rolled-back unit provisioner failure.
- 17 Identity gateway/session/encoded-path/step-up regressions passed, including a
  204-grant actor retaining only exact company and owned-department authority.
- Catalog database, migration and readiness heads are 0208; all 180 model tables
  match, with no native differences and a passing Alembic check.
- Changed Catalog and Identity source modules pass Ruff and strict typing. Catalog
  OpenAPI/field/audit contracts and generated SDK are synchronized, API-client
  version 0.2.37 and its lock metadata agree. Wheel checks include the manifest,
  provisioner, CLI and schemas. The existing whole-Catalog typing issue in
  `tasks/definition_revisions.py:58` is outside this change.
- A second fresh company completed the actual tenant3 creation wizard, including
  synchronization retries and the final company handoff. Native readback confirmed
  17 units, 17 declarations and 8 pack labels; 1.25 kg converted exactly to 1250 g.
  Repeat provisioning and same-key replay added no rows. All three directories
  displayed their defaults; desktop/mobile directory and wizard-review checks
  showed no page overflow or browser errors. Existing shared styles were reused.

Private reports, screenshots and verification company IDs are stored beneath
ignored `.tools/extension-masters/unit-defaults-*` paths.
