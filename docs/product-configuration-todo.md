# Product Configuration correction TODO

## Company-only simplification — 2026-10-30

The current ownership decision supersedes the earlier inheritance corrections.
The active checklist is [Company-only Product configuration](company-only-product-configuration-plan.md).
Review and reusable cases are in [the review report](company-only-product-configuration-review.md).
The follow-up [consumer review TODO](company-product-configuration-consumer-review-plan.md)
tracks adoption versioning (Catalog 0214), configured default-type validation and
the complete product/unit/price/import/activation review.
It is complete locally: [consumer results](company-product-configuration-consumer-results-2026-10-30.csv)
record 27 PASS and two NOT_RUN deployment/live-VM checks. Catalog 0214 must precede
the matching API deployment; existing pins retain version 1 semantics.
Historical results below remain evidence for their original implementation dates.

Authorized on 2026-09-13. This is the single task list for the approved correction plan.
Scope: Catalog configuration and its product, unit, pricing and bulk consumers. Existing
published revisions, product pins and unrelated workspace changes must be preserved.

- [x] 1. Record the corrected field, inheritance, goods/service and lifecycle contract.
- [x] 2. Reproduce and fix omitted-group resolution and nested PATCH replacement; cover
      explicit inheritance/clearing, ownership and historical selection.
- [x] 3. Provide consistent authorized authoring suggestions and explicit default acceptance
      for product types, unit numeric rules and price numeric rules; retain exact values.
- [x] 4. Expose effective values, per-setting provenance/applicability and publication
      differences/conflicts through protected configuration responses and previews.
- [x] 5. Make draft/active adoption boundaries explicit in API, previews and bulk; preserve
      source pins and reject unsupported structural changes to active products.
- [x] 6. Complete regressions, Ruff, strict mypy, generated contracts/client, documentation
      reconciliation and simplification/security review; record actual results below.

## Decisions

- Existing typed tables and ownership remain authoritative. New migrations are needed only
  if the final storage contract changes; never rewrite a published migration.
- Defaults suggest values; accepted authoring values become native product/unit/price data.
  Defaults never silently rewrite existing records or weaken a hard requirement.
- Existing-product queries derive their dated group; caller-supplied inconsistent ownership
  is rejected. Hypothetical candidate queries omit family/SKU identity.
- PATCH preserves omitted fields. Explicit INHERIT resets an override, profile CLEAR removes
  a selected default, and a numeric dimension list is an explicit replacement collection.
- Goods-only manufacturer, inventory, handling and instance-identifier settings do not apply
  to service candidates at shared COMPANY/BOTH-group scopes. Explicit incompatible settings
  at SERVICE type/family/SKU scopes are rejected.
- Active structural adoption remains blocked without the required replacement/history
  workflow. This task does not claim stock-aware or Billing-side enforcement.

## Verification

Baseline review: 13 focused existing tests passed. Disposable probes reproduced the group
lookup mismatch and nested PATCH sibling reset before implementation.

Phase 2 verification: both new regressions failed before fixes; 15 focused tests passed after
correction. Goods/service applicability and publication explanation regressions also passed.
Default suggestions/acceptance passed an end-to-end service/type/unit/price scenario with exact
0.20/0.25 grid intersection and stale-version rejection. The focused configuration, default,
activation and adoption run passed 18 tests. Review found a latest-default lookup before pinned
SKU resolution; a regression failed for that conflict, then passed after resolving pins directly.
The same test covers unauthenticated/unpermitted requests, wrong-company ownership, inconsistent
family/group/kind context and invalid dates.

Final verification results:

| Check | Result |
|---|---|
| Focused configuration/default/activation/adoption regression | 18 passed |
| Latest configuration corrections, including pinned defaults and repair previews | 6 passed |
| Latest native acceptance and field-deny ordering | 2 passed |
| Ruff lint, Catalog source/tests/tools | Passed |
| Ruff formatting, changed Python files | 23 files passed |
| Strict mypy, source/tests/tools | 353 files passed |
| OpenAPI generation and generated Catalog client consistency | Passed |
| TypeScript typecheck and client transport tests | Passed; 2 tests |
| Changed guide/checklist relative links and diff whitespace | Passed |
| Core configuration/activation/API/migrations batch | 41 passed; 1 Docker-dependent test skipped |
| Product authoring batch, including corrected expectation | 77 distinct tests passed |
| Pricing batch, including corrected expectation | 92 distinct tests passed |
| Bulk batch | 88 passed |
| Combined affected suite, 73 modules | 298 distinct tests passed; 1 skipped |
| Configuration domain and new-helper coverage | 25 passed; 100% domain, 98.13% combined |


The earlier broad test process ended across the session interruption without recoverable final
output. Its partial progress is not counted as a pass. The resumed run saves separate core,
product, pricing and bulk logs and JUnit reports under
`.test_artifacts/product-config-verification-20260913/`. `summary.json` reconciles repeated
cases using their final result: both outdated expectations pass after correction. The skipped
case is the live MySQL roundtrip because Docker is unavailable; offline migration checks passed.
The bulk worker entrypoint test emits a runpy import warning while passing.

## Review findings

Manual simplification and security review covers CLAUDE.md sections 5 and 6. The requested
`/simplify` and `/security-review` slash commands are not available in this environment.

- Corrected a redundant latest-default resolution before SKU pin selection; ownership and
  date validation now occur against the actual pinned selection.
- Corrected publication preview so a valid replacement can repair conflicting current
  defaults. Only domain conflicts are reported in `before_conflicts`; permission failures
  still abort the read.
- Preserved explicit whole-unit restrictions in suggestions for existing unit revisions.
- Corrected invalid price-basis arithmetic from an unexpected 500 to the standard 422
  validation envelope; the API regression failed before correction and passed afterward.
- Corrected acceptance validation order so native write denies precede acceptance mismatch
  errors. The regression first returned 409 for a denied field and now passes with 403.
- Native create/update handlers still enforce field writes, company scope, exact Decimal
  values, expected versions, audit/outbox and idempotency. Acceptance fields are command
  controls only and cannot be mass-assigned to ORM rows.
- Requests omitting the new acceptance control retain their existing idempotency identity.
  Suggestions require both configuration authority and access to referenced native fields.
- The broad run exposed two old service-applicability expectations. Updated them to
  verify shared physical profiles are excluded from services and ordinary service pricing
  remains available; explicit service MRP declarations must still be rejected.
- No database schema, dependency, permission-catalogue or external-consumer change is required.
  The generated Catalog contract has no existing web/mobile configuration consumer to update.

Review is complete with no unresolved findings in the changed behavior.

Known baseline check findings: full migration lint reports 127 pre-existing E501 findings in
unchanged published migrations. Whole-service formatting check identifies nine unchanged
files. Task files are checked separately; published migrations and unrelated formatting are
not rewritten by this task.

## Product integrity corrections - 13 September 2026

Authorized scope: the eight reproduced defects in the product domain review.

- [x] Quick plan: protect lifecycle dependencies and aggregate edits; correct attribute
      and quantity validation; finish regression, API contract and documentation checks.
- [x] Phase 1: guard active group moves, tracking capabilities, default-SKU edit versions
      and referenced price-level retirement.
- [x] Phase 2: enforce closed attribute options, overlapping future unit grids, minimum
      sale quantity grids and compound-entry readiness.
- [x] Phase 3: run affected tests, Ruff, strict mypy, contract generation and manual
      simplification/security review.

Active-product maintenance, physical Billing batch/serial operations and product UI
remain separate work. No database schema change is planned for these corrections.

Initial verification: all eight new regressions failed against the reviewed implementation
for the expected defect. The first four lifecycle/concurrency fixes then passed. Four added
boundary tests passed, covering reversed unit scheduling, closed options over existing scalar
values, future descendant assignments and policy-only/unused price-level retirement.

The focused integration run passed 34 tests, including all eight fixes, each individual
tracking capability, successful tracked activation and existing classification permissions.
Strict mypy passed 357 files; source/tests/tools lint, formatting of 24 task files, OpenAPI,
generated Catalog client, TypeScript typecheck and two client transport tests passed.

Manual simplification/security review: shared profile selection now enforces tracking flags
for draft selection and resolution. Unit validation shares one bounded, company-scoped query;
group traversal uses the existing bounded graph and an indexed existence lookup. Both group
moves and product/pricing writes retain the company transaction lock, tenant filtering,
field authorization, version checks and same-transaction audit/receipts. Rejected commands
roll back their dependent writes. Omitted new version controls preserve existing receipt
identity. Group-only administrators retain move authority; native dependency field denies
still apply and conflict messages disclose no dependent IDs. No migration or dependency
change is needed. `/simplify` and `/security-review` are unavailable in this environment;
these checks were performed manually against CLAUDE.md sections 5 and 6.

Bulk follow-up: all 11 distinct product/pricing/tax/configuration adapter scenarios passed
across the initial run and corrected follow-up. The new stale-edit test first expected a
FAILED worker state, but the existing generation guard raises an earlier review ConflictError.
The corrected test checks that explicit rejection and preservation of the newer SKU value.
No production adjustment was needed for this test expectation.

Final broader review caught a weakened legacy 64-binding guard when expanding future-revision
validation. The binding bound is restored independently of the 1,024-revision bound. The
pricing/tax run had two activation busy/retry conflicts during concurrent SQLite verification;
all three tax/security cases passed unchanged when rerun separately. Production command
timeouts/retry rules were preserved. Targeted unit/boundary verification follows the correction.

Final correction verification is complete:

| Check | Final result |
|---|---|
| Product/configuration/classification/activation suite | 178 distinct cases pass after targeted corrections/reruns |
| Pricing/tax suite | 118 distinct cases pass after isolated busy/retry reruns |
| Bulk product/pricing/tax/configuration compatibility | 11 distinct cases pass after correcting the stale-review test expectation |
| Combined regression cases | 307 distinct cases pass; 16 new regression cases included |
| Final unit/boundary/activation follow-up | 10 passed |
| Strict mypy | 357 files passed |
| Ruff lint / task formatting | Source/tests/tools clean; 24 task files formatted |
| OpenAPI / Catalog client / TypeScript | Export, generated consistency and typecheck passed |
| Client transport tests | 2 passed |
| Documentation links / diff whitespace | Passed |

The initial broad runs reported one real legacy-binding-bound regression (fixed) and three
activation busy/retry conflicts under concurrent SQLite execution (passed on isolated rerun).
These are not counted as clean initial runs. The final results above deduplicate repeated
cases, using their latest outcome. Logs, JUnit reports, static-check evidence and the reconciliation
script/result are retained in `.test_artifacts/catalog-fixes-20260913/`.

No unresolved findings remain in the eight corrected behaviors. Verification used synthetic
SQLite/ASGI data; live MySQL concurrency and downstream Billing execution were not exercised.
No database migration, deployment, commit or publication was performed. Earlier workspace edits
were preserved. Active-product maintenance, physical batch/serial operations and UI work remain
outside this correction scope.

## Unit and conversion corrections - 13 September 2026

Authorized follow-up to `.test_artifacts/unit-review-20260913/review.md`.

- [x] Phase 1: add failing regressions for serial scheduling/entry, canonical versus
      product conversion authority, exact ratio transport, measured identity and composed ratios.
- [x] Phase 2: correct the five findings in native commands and consumers; preserve
      published history, tenant/field authority, audit and idempotency.
- [x] Phase 3: verify positive cases, reverse command ordering and bulk/client compatibility;
      regenerate OpenAPI/client and reconcile the unit guides.
- [x] Phase 4: finish affected regressions, lint/type checks and manual simplification/security
      review; correct any further defects and record results.

Decisions for this correction:

- Declared canonical relations are authoritative wherever both units share a root.
  Containers without a shared canonical relation retain their SKU-specific pack ratios.
  Adding a canonical relation must also preserve existing product revision history.
- Serial base rules must remain whole-count through every scheduled interval and quantity
  consumer. Invalid existing definitions fail closed; corrections do not rewrite history.
- Product ratio wire values use decimal integer strings; existing integer requests remain
  accepted for compatibility. Integer-backed native persistence and idempotency identity remain.
- Measured entry requires distinct entered/base units without a shared canonical relation.
  Neither measured mode nor nominal ratios can override declared fixed conversions.
- Composed rational intermediates are not stored BIGINT components; final stock quantities
  must still fit DECIMAL(19,4) and the target quantity grid exactly.
- Active-product maintenance, measured-pricing workflow expansion, UI and Billing are separate
  design work. No migration or shared-library change is planned for these five corrections.

Review corrections:

- Bulk preview serializers preserve ratio digits, including nested changes, without modifying
  persisted evidence or the values used by field policies.
- Canonical and product dependency read permissions are checked before querying, including
  empty result sets. Unit-only administrators retain their command authority; field denies
  still apply and conflicts disclose no dependent product IDs.
- Measured definitions cannot bypass a declared canonical conversion. Both command orders and
  legacy quantity/pricing/activation consumers are covered. Undeclared variable packs remain valid.
- Canonical declaration guards include closed fixed/measured history, remain bounded at 1,024
  affected nonidentity revisions, and share the company transaction lock with product writes.
- Native persistence, request receipt identity, expected versions, tenant/company filtering,
  audit and outbox transactions remain intact. No migration or shared-library change is needed.

Initial verification passed all nine original regressions and 40 affected cases. The bulk
round-trip test required its synthetic proof to match source version 3 and an UPDATE_ONLY job
for an existing SKU; both fixture corrections preserve production authorization and import rules.
Final verification reconciled 118 distinct passing backend cases, including 25 new regressions.
The 80-case run recorded 79 passes and the fixture source-version failure described above.
A four-case follow-up exposed the missing UPDATE_ONLY test setting; the final 35-case
post-review run and the additional valid-measurement check passed completely. Results use
each case's latest outcome; the earlier failures are retained in the test evidence.

Ruff passed for source/tests/tools; all 16 task Python files pass formatting. Strict mypy
passed 362 files. OpenAPI export consistency, generated client consistency, TypeScript
typecheck and two client transport tests passed. Manual simplification and security review
followed CLAUDE.md sections 5 and 6; the slash-command tools are unavailable in this environment.
Logs, JUnit reports and the reconciliation manifest are in
`.test_artifacts/unit-review-20260913/fix-verification.json`.

No unresolved findings remain in the five corrected behaviors and their review follow-ups.
Verification used synthetic SQLite/ASGI data; live MySQL concurrency and downstream Billing
execution were not exercised. No migration, deployment, commit or publication was performed.
Existing unrelated workspace changes were preserved.

## Pricing review corrections - 14 September 2026

Authorized follow-up to the pricing review; preserve concurrent workspace edits.

- [x] Phase 1: add failing regressions for native/bulk publication and activation guard
      validation, mixed tax bases, known dated dependency gaps and preview history conflicts.
- [x] Phase 2: share exact commercial validation across preview, publication, resolution
      and required-price activation. Preserve purchase/reference separation and approval rules.
- [x] Phase 3: expose bounded dated coverage and transaction-context requirements in price
      preview; prevent publishing beyond known unit/source coverage and misleading same-date
      replacement readiness. Verify measured-quantity boundaries remain explicit.
- [x] Phase 4: correct the two obsolete pack-unit test fixtures; update API/client/docs,
      run affected regressions and static checks, then review security and simplify the changes.

The delivered company/SKU contract remains the implementation boundary. Customer/supplier
agreements, physical-stock allocations, final Billing tax/discount/approval execution and
audited withdrawal of immutable publications require their own lifecycle/source contracts;
these deferred capabilities will not be represented as implemented by this correction.

Review follow-ups corrected the requested pack's MRP coverage when deriving a base price,
preserved missing-MRP activation requirements, and removed duplicate adoption validation
inside the locked activation command. Standalone adoption retains fresh signed-preview
validation. The activation lifecycle now passes with the normal command budget.

Verification: **245 unique backend cases have passing latest results**, covering pricing,
bulk, units, activation, adoption and related authoring. The original instrumented broad run
was stopped for speed; completed passes were retained and every remaining case was run in
two independent groups. The final 18-case activation/adoption run passed completely.
Earlier missing-MRP and command-timeout failures are retained in the evidence; both prompted
the corrections above. Initial Windows argument quoting affected test collection only and
was corrected by passing literal case IDs directly to pytest.

The 57-case coverage run passed: **96.88%** combined coverage for the pricing domain and the
two new readiness/schedule modules; the pricing domain is **100%**. This is targeted coverage,
not a claim about whole-service coverage. Coverage uses the repository's existing test-only
instrumentation budget; production command limits were not changed.

Ruff, strict mypy (367 files), formatting (16 task Python files), OpenAPI and generated-client
consistency, TypeScript typechecking, two client transport tests and diff whitespace checks
passed. Manual simplification and security review followed CLAUDE.md sections 5 and 6 because
the slash-command tools are unavailable. No unresolved blocking findings remain within these
corrections. Tests used synthetic SQLite/ASGI data; live MySQL and downstream Billing were not
exercised. One existing bulk-worker runpy warning remains in the test log.

Evidence and reconciled outcomes: `.test_artifacts/pricing-fixes-20260914/verification.json`.
No migration, deployment, commit or publication was performed; unrelated work was preserved.

## Product Tax corrections and gaps - 14 September 2026

Authorized implementation of the Product Tax review, including the identified gaps.

- [x] Phase 1: failing regressions; GST splits/ceilings; full classification coverage;
      goods/service compatibility; current dependency authorization on receipt replay.
- [x] Phase 2: native classification applicability and explicit compensation-cess semantics;
      audited future correction/withdrawal and atomic reviewed tax change sets; matching migrations.
- [x] Phase 3: complete dated publication validation, affected-product impact preview, future
      tax activation readiness, tax master options/usage/aliases/external keys, activation profiling.
- [x] Phase 4: regression/security/tenant/audit coverage; migration/model checks; generated
      OpenAPI/client/docs; simplification and security review; resolve review findings.

Implementation decisions: preserve published evidence and existing local paths; never silently
rewrite effective tax values. Future corrections use explicit reviewed commands. Standard GST
uses equal central/state components and statutory component ceilings. Supported cess is explicitly
India compensation cess, with consistent schedules across the three supply contexts; unsupported
levies fail validation. Native reviewed HSN/SAC applicability is distinct from downloading or
certifying government source documents. Invoice registration/place-of-supply/reverse-charge
determination remains Billing's documented responsibility. User authorization includes these
phases and their necessary API/schema changes; no further phase approval is required.

Review follow-ups corrected bulk release child guards, goods/service checks for restricted
empty groups, and review queries that counted unrelated company history. Product review now
follows relevant current/future dependencies and enabled commercial directions. Rate and
release receipt replay also rechecks component fields and fixed-cess unit access. Each bug
has a retained failing reproduction and a passing regression. Activation uses transaction-local
subject lookups with current source checks; the production command timeout remains 10 seconds.

Verification reconciles **130 unique passing backend cases and one skipped live MySQL case**.
The full tax/activation run passed all 56 cases. After the final receipt-authorization correction,
all 29 affected tax command/security cases passed again. The 17-case review/shared-adapter run
and three pricing foundation/publication cases also passed. Results count each case's latest
outcome rather than adding repeated runs.

The earlier broad run recorded 104 passes and two failures: an obsolete stored-data error
expectation and missing tax master route registration. Both were corrected and their cases
passed again. A later command referenced a nonexistent foundation test filename and collected
no tests; the corrected invocation passed. Earlier failing reproductions remain in the evidence.

Tax domain line and branch coverage are **100%** in the final targeted coverage run. This is
not whole-service coverage; the earlier broad coverage file predates final source changes and
is not final coverage evidence. Ruff passed for source/tests/tools, strict mypy passed 372 files,
and all 42 checked task files are formatted. OpenAPI and generated Catalog client consistency,
TypeScript typechecking, two client transport tests and whitespace checks passed.

All eight migrations (0117-0124) were read and checked with their models; the two offline migration
tests passed. Live MySQL roundtrip was skipped because Docker and a configured test server are
unavailable. Corrections retain history; restoring older uniqueness/mapping constraints may fail
when retained data uses the new capabilities. No migration was applied to a business database.

Manual simplification and security review followed CLAUDE.md sections 5 and 6 because the
slash-command tools are unavailable. No unresolved blocking finding remains in the reviewed
Catalog behavior. Verification used synthetic SQLite/ASGI data; live MySQL concurrency and
downstream Billing execution remain unverified. Invoice transaction decisions retain the
documented Billing boundary. No deployment, commit or publication was performed.

Evidence and per-case reconciliation: `.test_artifacts/product-tax-fixes-20260914/verification.json`.

## Category Scheme corrections and gaps - 14 September 2026

Authorized by the user's request to implement the review and review the completed changes.

- [x] Phase 1: regressions and fixes for ambiguous bulk codes, category parent authority,
      membership receipt authority, and activation membership validation/evidence.
- [x] Phase 2: native per-scheme requiredness and reviewed scheme transitions; dated,
      reviewed active-family membership maintenance with retained history and migrations.
- [x] Phase 3: API/client/history contracts, documentation, regression/security/storage tests.
- [x] Phase 4: affected suites, static checks, migration review, simplification and security
      review; resolve findings and record evidence.

Decisions: category codes remain unique within a scheme; ambiguous bulk codes must use an ID
or an external key. Requiredness applies to active products in the company. Drafts can remain
incomplete until activation. Scheme policy changes are reviewed immediate master changes;
all current/future memberships must remain valid. Active-family membership replacements are
strictly future-dated, previewed, append-only schedules; closed memberships remain readable.
Categories remain merchandising classifications and do not imply price or tax inheritance.

Completed implementation and review. In addition to the four confirmed defects, the review
corrected retirement with closed history, empty-set review permissions on receipt replay,
activation receipt dependencies, overlap after an empty scheduled set, and existing 409/422
response contracts. Activation receipts retain current/future category dependencies; closed
categories outside the activation evidence do not add unrelated authority requirements.
Each correction has retained failing evidence and a passing regression.

Verification reconciles **97 unique passing backend cases, zero failures, and one live MySQL
skip**. Repeated runs are counted once using each case's latest result. The final focused run
passed 28 cases; the final edge run passed 11; the final response/cardinality run passed 17.
The related classification/product/storage suites and 24-case activation/bulk suite are also
included in the reconciliation. Category domain line and branch coverage are **100%**;
this is targeted coverage, not whole-service coverage.

Ruff, strict mypy (384 source/test files), formatting, OpenAPI consistency, generated Catalog
client consistency, TypeScript, two client transport tests and whitespace checks passed.
Migrations 0125-0128 were reviewed with their models; both offline migration tests passed.
Downgrade past 0126 is deliberately blocked to prevent closed history becoming current when
dates are removed. No business database migration, deployment, commit or publication was run.

Manual simplification and security review followed CLAUDE.md sections 5 and 6 because the
slash-command tools are unavailable. No unresolved blocking finding remains in this scope.
Tests use synthetic SQLite/ASGI data. Live MySQL roundtrip/concurrency remains unverified
because Docker and a configured test server are unavailable. Current scheme policies govern
readiness; no historical price/tax inheritance or downstream Billing execution is implied.

Evidence: `.test_artifacts/category-scheme-fixes-20260914/verification.json` and `review.md`
in the same directory. API and migration behavior is documented in `catalog-classification-api.md`.


## Product custom fields corrections and management — 15 September 2026

Authorized: complete the reviewed fixes and gaps, then conduct two review/fix passes.

- [x] Phase 1 — typed defaults, conditions, requiredness, retired selections and rebuild validation (F05–F09); readable validation errors.
- [x] Phase 2 — activation validation, active descriptive maintenance and operation-aware metadata (F02, F03, F10).
- [x] Phase 3 — Identity definition/layout/policy administration for product families and SKUs (F01).
- [x] Phase 4 — reviewed definition adoption, searchable/unique preparation and value backfills (F04).
- [x] Phase 5 — shared metadata-driven forms and product custom-field management UI; generated contracts and docs.
- [x] Review 1 — correctness/security review, regressions and fixes.
- [x] Review 2 — independent end-to-end review, regressions and fixes.
- [x] Final verification — affected suites, coverage, lint/types, generated contracts, migrations and integration gates.

Review evidence: `.test_artifacts/product-custom-fields-review-20260915/`. Implementation evidence: `.test_artifacts/product-custom-fields-fixes-20260915/`. No commit, publication or business-database migration is authorized by this task.


Completed all five phases and two review/fix passes. Definitions can be administered for
families and SKUs, adopted after impact review, and edited through shared Console forms.
Requiredness, defaults, typed conditions, retired history, activation, active descriptive
maintenance, unique preparation and index backfills now use the corrected contracts.

Review 1 fixed mixed-type cross-company uniqueness, pending retirement affecting accepted
metadata, browser NOT/null semantics and defaults missing from create-form conditions.
Review 2 fixed retired-value metadata, adoption versioning, invalid static defaults, timestamp
comparison and source synchronization before adoption. It also tightened affected-company
read checks, parent lifecycle metadata, scoped policy administration and validation messages.
The real Identity HTTP producer/Catalog consumer test confirms definition digest, adoption
flag and typed default parity. The existing audit test now uses its fixture's clock.

Final reconciliation: **2,463 unique tests passed, zero failures, four environment-dependent
integration skips**. By area: Catalog 85; Identity 501; platform 72; shared UI 1,620; Console 185.
Two additional API-client transport tests passed. Repeated runs are counted once using the
latest outcome. Identity's full affected run passed 499 cases; new domain checks add two.

Coverage: shared custom-field/metadata Python code 93.40% lines and 90.16% branches (92.27%
combined); new Identity product contract module 100% lines/branches; new shared UI components
100% lines/statements/functions and 86.42% branches. These are targeted coverage figures.
Ruff/formatting, strict mypy (396 Catalog files and all affected Identity/platform files), all
MFE TypeScript checks, generated Catalog/Identity OpenAPI and client consistency, owner
contract export, client typing and whitespace checks passed. Migration models/offline DDL
checks passed; no migration was applied to a business database.

Operational bounds: adoption scans at most 1000 affected owners and reports up to 200 issues;
value backfills use existing reviewed, resumable bulk commands. Larger definition adoptions
are refused without partial approval. The Console needs CATALOG_GATEWAY_URL and deployed
Identity 0058 / Catalog 0129-0130 migrations. Live MySQL locking, deployed broker delivery and
browser sessions remain unverified here. No deployment, commit or publication was performed.
See custom-fields.md for rollout and the artifact verification.json for per-case evidence.


## Practical native attributes review and fixes - 15 September 2026

Authorized: review practical attribute use and fix confirmed bugs and gaps.

- [x] Phase 1: regressions and fixes for exact measured values, stored-value readiness,
      template constraints, full-replacement semantics and historical identity preservation.
- [x] Phase 2: maintain allowed options without changing existing axis identities; create
      and complete draft SKUs in active families while protecting active SKU structures.
- [x] Phase 3: practical Console authoring for definitions/options, family declarations,
      SKU values and explicit variants; shared typed controls and protected API transport.
- [x] Phase 4: review/security checks, affected regressions/coverage, migrations, generated
      contracts and documentation. Preserve unrelated in-progress work.

No automatic Cartesian SKU generation or change to historical pricing/tax/posting semantics.
Attribute changes affecting active SKU identity remain structural and must be refused.
Evidence: `.test_artifacts/product-attributes-fixes-20260915/`.

Verification completed: 2013 distinct passing tests (including three client
transport tests); 1 Docker-only MySQL check skipped. Both review passes and corrections
are recorded in the attribute artifact review.json; verification.json records final reports,
coverage, static checks and source hashes. Migration 0131 is prepared, not applied.


## Additional final attribute review - 15 September 2026

- [x] Reproduce remaining save/reload recovery, protected option editing and measurement label issues.
- [x] Apply focused fixes, review authorization and run affected regressions/static checks.
- [x] Record final findings and verification without changing unrelated work.

Final findings fixed: confirmed writes are not repeated after a failed reload; option label
edits submit only changed writable fields and preserve protected values; existing measured
options show their saved unit label with a readable-ID fallback; hidden unit controls honor
field metadata while scalar edits preserve their stored unit.

Verification: six regressions failed before the fixes. Final suites: Console 233 passed,
shared UI 1642 passed, API authorization/preservation/replay regression 1 passed (1876 total).
Changed Console coverage: 99.77% statements/lines, 93.06% branches, 100% functions; shared
attribute control: 100% throughout. Both TypeScript checks and focused Ruff checks passed.
Manual simplification/security review found no further issue in these changes. These are
component and API integration checks; a deployed browser session was not exercised.
Evidence: `.test_artifacts/product-attributes-final-review-20260915/verification.json` and
`review.json`. Earlier backend/migration verification remains recorded in the prior section.
