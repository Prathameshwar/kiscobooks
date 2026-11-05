# Units and conversion review

## Scope and phases

1. Trace the documented unit/pack/canonical conversion contracts, exact arithmetic,
   lifecycle/reference guards, field permissions and dated product bindings. Inspect
   current consumers in configuration, product creation/setup, pricing, attributes,
   BOM definitions and imports. Review voucher integration separately later, as the
   user requested; do not activate or change voucher/stock execution in this work.
2. Reproduce confirmed gaps with regression tests, then fix them using the existing
   native commands, shared quantity rules, UI controls/styles and permission checks.
   Keep API/SDK/docs synchronized if any contract changes are necessary.
3. Run affected native and Console suites, strict typing/lint and live read-only or
   isolated-record checks as applicable. Review correctness/security and UI twice,
   record findings and limitations and finish with all affected checks green.

No new costing, stock reconciliation, posting or rounding policy is authorized.
Exact quantities, rational strings and company/tenant boundaries remain mandatory.

## Findings and delivered fixes

All phases are complete. Review found and reproduced the following defects before
fixes; voucher code and posting activation were excluded throughout.

- Unit dependency checks omitted retained compound parents/children and some
  non-product references. Semantic edits and retirement could reinterpret them.
  The guard now checks Catalog's trusted mapped direct unit foreign keys through
  tenant/company-scoped existence lookups while holding the existing company
  mutation lock. Historical/inactive references still protect meaning. Labels
  remain editable; failed changes do not advance versions or emit success audit.
- The merged unit/pack PATCH validation could raise an uncaught Pydantic error,
  returning 500 for an incompatible unit increment/precision or a blank pack name.
  It now returns 422 with safe field messages, without raw inputs or protected
  saved values. Current-version correction and idempotent label replay are covered.
- Company display precision could make a native nonzero conversion appear to be
  zero. The checker now additionally shows the exact storage value whenever it
  differs from the configured display. Identity-conversion guidance is corrected.
- Product creation coerced null precision to zero and fabricated a missing unit
  increment. It also forced serial increments to one and copied alternate steps
  without checking exact base representability. Unknown/invalid grids now block
  creation. Serial steps use the smallest whole multiple of the declared step;
  alternate steps use the smallest permitted multiple that converts exactly to
  the base grid. For example, a 2.5-unit serial grid needs whole steps of 5; a
  0.01-pack grid at 12 pieces/pack needs steps of 0.25 when the base requires whole
  pieces. Steps beyond DECIMAL(19,4) reject. The wizard displays the derived steps.

The client arithmetic chooses valid defaults and validates inputs; it is not a
replacement quantity authority. Native canonical consistency, current/future base
and alternate grids, measured actual quantities, serial rules and immutable
barcoded bindings remain enforced by Catalog. Exact ratios remain integer strings.

## Consumers reviewed

- Unit and pack management, immutable canonical declarations, exact conversion
  preview, official-code validity/closure, active-reference selection, field
  permissions, scoped paging and dependency guards.
- Product create/edit base-unit handling, dated fixed/measured bindings, scheduled
  grid compatibility, structured compound entry, minimum quantities and serial
  base requirements. Existing base identities cannot be replaced through edits.
- Authoring/configuration defaults and their unit narrowing; price basis and unit
  quantities; measured attributes and canonical values; BOM definition/run quantity
  checks; bulk unit/ratio transport and retained-history consistency.

Official unit-code management remains API-only. Persisted multiplicative compound
components and their domain factor are protected; this work does not add a new
compound-definition editor or infer compound stock movements. Existing native
API-only quantity/revision operations are not newly exposed in Console merely to
test them. These are retained documented boundaries, not new feature claims.

## Verification and reviews

Native baseline domain/integrity/compound suites passed 25 tests. Core unit,
canonical relation and product-unit suites passed 28 tests; six new dependency and
merged-validation regressions passed. The final current unit/relation/dependency
API run passed 19 tests after all fixes. Configuration defaults, pricing/unit,
attribute and BOM consumer suites passed 54 tests. Some suites share coverage;
these counts are recorded per run rather than added as distinct cases. Console
verification passed 174 tests across seven suites, including large exact ratios,
storage bounds, protected grid fields, configured number grouping and recovery.
Ruff, strict mypy, TypeScript, OpenAPI and generated Catalog client freshness checks
passed. Existing error/API shapes are unchanged, with 422 already declared; no
schema/model/seed/migration or client-version change is necessary.

The live Catalog source was restarted with the fixes. In the existing isolated
tenant3 verification company, native checks created labelled test units and
canonical declarations, verified 0.1 g becomes exactly 0.0001 kg, rejected an
unrepresentable result and incompatible dimension, rejected an inconsistent merged
PATCH with 422 and referenced retirement with 409, and verified label save/replay
at one resulting version. A product alternate binding accepted the narrowed 0.25
entry step and its unit identity read back correctly. No voucher, financial,
opening-stock, physical batch/serial or balance operation was invoked.

The live conversion screen and a read-only product creation draft passed 12
desktop/mobile checks across light/dark/ledger themes. The product draft visibly
showed the 0.25 alternate step for 12:1 conversion; its six layout checks made no
writes. The conversion view displayed both its configured rounded figure and the
exact nonzero result. Final browser checks recorded no errors or overflow; private
artifacts remain in ignored .tools/extension-masters.

Manual simplify/security reviews covered CLAUDE.md sections 5 and 6 because those
slash-command tools are unavailable. The second review checked lock/scope/query
boundaries, rollback, safe error envelopes, replay authority, exact arithmetic,
profile/configuration gating and the displayed derived rules. No remaining defect
was found within this review scope. Existing release-level MySQL concurrency,
broker recovery and load gates remain separate; this is not a voucher release or
stock-execution readiness claim.
