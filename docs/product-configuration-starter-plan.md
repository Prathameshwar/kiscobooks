# Minimal company product configuration and pricing controls

Approved 2026-11-04: implement company setup and Product Configuration end to end.
The later [Simple Product delivery](simple-product-ready-plan.md) restores creation;
product edit/detail and advanced authoring remain deferred. Warehouse pricing is excluded; batch and
physical-declaration pricing remain unimplemented and outside this change.
The [Simple multiple-price follow-up](simple-product-multiple-prices.md) makes
creation and import consume configured selling levels and required coverage.

## Decisions

- New companies receive one company-owned published starter configuration through
  Catalog's verified enrollment/setup workflow. Retry safely; preserve existing
  configuration, products, authoring mode and historical adoption pins.
- Starter entry options are disabled, Simple authoring remains the new-company
  default, and the existing Default group is reused. The later Simple Product
  decision adds an untracked Goods type and FIFO inventory profile when inventory
  is enabled. Warranty, return, handling and identifier profiles remain disabled.
- One price level, optional selling/purchase references, MRP disabled; base-unit
  fixed pricing in company currency. Additional unit prices, quantity tiers,
  channels, other pricing currencies and formula prices start disabled.
- Add typed INHERIT/DISABLED/ENABLED controls over those existing capabilities.
  The existing level count is required coverage, not permission to use extra
  levels: retain that meaning and add an explicit multiple-level control.
  Historical configurations inherit existing supported behaviour; only new
  starters select minimal defaults. Preserve existing unit-derivation policy as
  its sole authority; no duplicate pricing policy or automatic currency conversion.
- Company setup must verify configuration publication and default pricing policy
  readiness before reporting completion. Existing incomplete/authored setup needs
  explicit review rather than overwriting user work.
- Disabling entry preserves published history and supported historical reads;
  future authoring/publication/resolution use effective product configuration.

## Phases

1. Contracts and enforcement: migration/model/schema/metadata/audit consistency;
   effective configuration and native pricing authoring/publication/resolution;
   regression coverage for disabled dimensions, history and authorization.
2. Automatic starter: audited idempotent provisioning after existing type/price
   defaults, company setup/readiness integration, isolation/retry/preservation tests.
3. Product Configuration UI: compact current summary, grouped optional settings,
   native field metadata, read-only and publication/recovery behaviour; client sync.
4. Native/API/UI verification, schema upgrade/downgrade checks where available,
   static checks and security/simplification review; record evidence and limitations.

## Progress

- [x] Contracts and enforcement
- [x] Automatic starter and company setup
- [x] Product Configuration UI and generated contracts
- [x] Verification and final review

## Review findings resolved

- Required sale-level coverage and permission to use extra levels are distinct;
  the existing count retains its meaning and the explicit switch gates extra levels.
- Company capabilities now commit during creation using native commands and actual
  creator grants. Catalog cannot publish an inventory-disabled starter before a
  requested inventory capability reaches the first company snapshot.
- Migration checks use the exact model constraint names, a single additive ALTER,
  and a guarded downgrade that refuses authored values.
- Existing configuration, authoring choices and pricing policies are preserved;
  audit failure rolls the entire starter back, and concurrent retries publish once.
- Published pricing summaries use readable native metadata and saved values;
  protected/missing values are never presented as disabled settings.

## Local database delivery

Applied Catalog 0215 → 0216 on 2026-11-04 using the existing protected local DDL
credential. Both pre-existing pricing-policy rows retained all original values,
verified by a logical hash before/after. All 182 Catalog model tables, migration
and readiness heads, native constraints and Alembic comparison match with zero
differences. No product configurations were republished in the existing company.

Isolated MySQL 9.6 verification covered upgrade/downgrade/re-upgrade, retained old
values, refusal to discard authored modes, concurrent starter creation, effective
goods/service defaults and publication of a later configuration. The isolated
database server was shut down after verification. Evidence is retained locally in
the ignored `.tools/product-config-starter-review/` directory.

## Validation notes

- Console: 215 affected tests passed; TypeScript passed.
- Identity: 18 automatic setup tests passed, including initial capability state,
  incomplete publication, pricing-policy readiness and retry behavior.
- Catalog: 24 focused configuration/pricing tests, 27 configuration regressions,
  and 11 pricing/bulk compatibility tests passed. Two isolated MySQL tests passed,
  including native API publication. The older Docker-container migration test was
  skipped; the new migration was verified separately on local MySQL 9.6.
- Coverage of the new provisioning and pricing-gate modules: 97.20% including
  branches; the new pricing domain module and gate validator each have 100%.
- OpenAPI and generated Catalog client are synchronized; client version 0.2.65.
  Audit contract checks and scoped strict mypy/Ruff checks pass.
- The full shared-client typecheck has a pre-existing unrelated failure:
  `tests/accounting-types.ts:5` references `AccountCreate`, which is absent from
  the committed Accounting generated contract. Catalog client type tests pass.
  No Accounting contract was changed by this task.
- Manual simplification and security/invariant review completed. `/simplify` and
  `/security-review` are not available in this session; the equivalent review
  checked tenant/field access, immutable publication, exact values, audit atomicity,
  enrollment concurrency, capability ordering and migration safety. Findings and
  fixes are recorded above.
- Full repository suites and an overall service coverage run were not performed.
  Native testcontainer-only coverage is separately identified when skipped;
  the new migration and setup were tested on an isolated local MySQL instance.
