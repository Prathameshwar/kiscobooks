# Unit, conversion, configuration and stock review — 2026-10-31

Reviewed source snapshot: `f6773b1b`. This review changes documentation and saves
reproduction material; it does not change application behavior or production data.

The review found **8 functional bugs and 7 gaps**, including one test-coverage gap.
The most urgent problems are the opening-stock unit picker’s incompatible API
query, incomplete voucher unit admission, and inexact public ratio transport.

## Scope and evidence

Traced unit/pack schemas, models, default seeding, canonical relations, dated SKU
bindings, company numeric suggestions, product creation/setup, barcode resolution,
pricing unit eligibility, Catalog quantity previews, opening calculations, signed
stock source facts, stock reads, stock reconciliation and voucher item capture.

- Existing Console suites: **162 passed** across ten selected files.
- Accounting suites: **70 passed** across opening arithmetic/review/preview,
  stock policy, tracking, costing, reconciliation, reporting and selection.
- Catalog suites: **72 passed, 2 failed** across twelve selected files. Both
  failures are missing-tenant-scope fixture errors, detailed in G07; these are not
  evidence of a tenant-isolation bypass.
- Additional API reproduction: **1 passed**, confirming the opening dropdown
  request returns 422 while the supported undated binding and dated revision
  requests both return 200.
- Additional Console diagnostic probes: **5 passed**, confirming current defects
  in stock display, company defaults, required conversions, pack scans and ratio
  transport. These deliberately assert observed defects, not desired regressions.
- A disposable SQLite ORM probe confirmed both invalid voucher unit cases at
  the actual native pre-approval master-validation function. Pydantic-to-JSON
  output and JavaScript parsing confirmed the ratio precision loss.

These are application/API/domain/component checks. SQLite was disposable and no
driver was mocked in database probes. Live MySQL, RabbitMQ, installation activation,
browser CSS/layout, and full financial posting were not rerun. Do not interpret
master-validation acceptance as proof that an invalid stock effect was posted.

## Confirmed bugs

| ID | Priority | Fix complexity | Finding and consequence |
|---|---|---|---|
| B01 | High | Medium | Opening stock cannot load unit choices: `OpeningStockEntry.loadUnits` sends `as_of` to the unit-binding list, while Catalog only accepts that filter on dated definitions such as revisions. The real API returns 422. |
| B02 | High | High | Voucher master admission checks item/unit activity independently, without enforcing the SKU’s dated binding, allowed dimension, precision or increment. A whole-piece SKU with quantity `1.5`, and the same SKU with an unrelated kg unit, both pass native pre-approval master validation. |
| B03 | High | Medium | `BarcodeResolution` and `EffectiveUnit` serialize numerator/denominator as JSON numbers. `9007199254740993` becomes `9007199254740992` in JavaScript, unlike the protected string transport used by unit-conversion and unit-revision reads. |
| B04 | High | Medium | Scanning a pack barcode in physical stock entry selects the pack unit and labels the scan successful. The form locks unit selection to base-only; save then rejects the mismatched unit. The scanned binding/revision/ratio is discarded. |
| B05 | Medium | Medium | Product creation derives quantity rules only from the master unit and serial grid. Company numeric quantity defaults are fingerprinted but are not applied or offered for acceptance. A configured COUNT increment of `5` creates a base binding with increment `1`. |
| B06 | Medium | Medium | Company alternate-unit `REQUIRED` and optional default-enabled settings do not initialize or validate the create wizard’s conversion choice. The checkbox starts false and the builder returns a base-only setup without an error; required readiness is discovered later. |
| B07 | Medium | Low | With company quantity precision 2, stock `0.0010` appears as `0.00` without an exact secondary value. The same rendering pattern exists in stock summaries/opening worksheets/history. Storage and arithmetic remain correct, but the visible stock figure is misleading. |
| B08 | Medium | Medium | Stock quantity lists, summaries and opening history omit the actual base-unit label. Mixed products therefore show indistinguishable quantities despite using pcs, kg or another unit. Stock read schemas do not expose a base-unit identity/label alongside quantity. |

### Reproduction and fix boundaries

**B01:** Request `/v1/companies/{company}/items/{item}/unit-bindings?limit=50&as_of=2090-01-01`
for an authorized seeded product: 422, `this definition has no effective-date filter`.
Remove `as_of` from the binding list and retain it on the selected binding’s
revision list. The browser proxy currently permits the invalid filter, and UI
fixtures return success for it. Keep date selection authoritative at revision level.
Evidence: `OpeningStockEntry.tsx:175`, `product_definition_reads.py:131` and the
saved Catalog API diagnostic probe.

**B02:** Seed active, same-company item, COUNT unit and MASS unit evidence, plus
an eligible item transaction policy. Run `validate_masters(..., capture=False,
kind="SALES")` with `1.5` COUNT and with the unrelated MASS unit. Both return
normally. The item policy has kind/direction/inventory flags but no dated unit grid;
`ItemInput` only enforces general DECIMAL(19,4) bounds. Stock admission has separate
native base-unit checks; this finding concerns voucher item/unit admission.
Evidence: `vouchers/tasks/documents.py:249`, `vouchers/schemas/sources.py:87` and
`vouchers/schemas/documents.py:33`.

**B03:** Serialize numerator `9007199254740993`, denominator `9007199254740995`.
JavaScript parses them as `9007199254740992` and `9007199254740996`. Fix both public
response models, OpenAPI, SDK types and all readers together. Database BIGINT
storage and exact server arithmetic need no narrowing or float conversion.
Evidence: `catalog/schemas/product_authoring.py:154`,
`catalog/schemas/effective_item.py:37`; compare existing string serializers in
`catalog/schemas/product_definition_reads.py:192` and `schemas/units.py:197`.

**B04:** Resolve a 12-pcs-per-box barcode in a Receipt Note. `VoucherItems.scan`
sets the line unit to BOX. `VoucherUnitReference` disables the unit picker for
physical stock. `buildStockCapture` then requires PCS and refuses save. Until a
complete entered/base conversion contract exists, provide a clear actionable
refusal or an authoritative conversion flow; do not silently change quantity or
pretend the pack unit is the product’s base identity.
Evidence: `VoucherItems.tsx:28`, `VoucherUnitReference.tsx:24`, `voucher-stock.ts:35`.

**B05/B06:** Build new product setup with a COUNT master increment 1 and company
quantity increment 5: the created base setup uses 1. Set alternate units REQUIRED
but leave the create checkbox false: setup still contains only BASE, with no
error. Quantity rules are defaults, not a blanket authorization restriction;
offer/apply the native narrowed suggestion with explicit override/acceptance
semantics, while required options must have visible completion guidance.
Evidence: `product-creation.ts:144`, `ProductCreationSetup.tsx:298` and `:761`;
compare `configuration_authoring.py:110` and `ProductCatalogSetup.tsx:520`.

**B07/B08:** Render a stock row with quantity `0.0010` inside the shared display
provider configured with quantityPrecision 2. The On hand cell reads `0.00`,
and there is no unit column or exact quantity. Preserve company display preferences
and add exact evidence where needed; attach authorized native unit labels without
per-row synchronous cross-service reads or invented labels for protected fields.
Evidence: `StockDirectory.tsx:31`, `VoucherStockSummary.tsx:14`,
`OpeningStockWorkspace.tsx:302`, `OpeningStockHistory.tsx:86` and
`accounting/schemas/stock.py:93`.

## Gaps and retained implementation boundaries

| ID | Priority | Complexity | Gap |
|---|---|---|---|
| G01 | High | High | General receipt/dispatch/transfer/return capture is base-quantity-only. Fixed alternate entry has native conversion evidence only in the special opening capture. General stock lines cannot retain entered unit, dated revision and entered/base quantities. |
| G02 | High | High | Measured dual quantities exist in Catalog authoring/preview, but opening and ordinary stock execution have no measured-entry contract. The opening picker accepts only FIXED revisions; nominal weight must not become actual stock weight. |
| G03 | Medium | High | Structured additive compound quantity preview exists in Catalog but is not exposed in voucher/stock entry. Separately, multiplicative compound definitions have a table/domain helper but no reachable authoring API or recursive resolution caller. These are distinct mechanisms and should not be conflated. |
| G04 | Medium | Medium | Dated official unit/tax-code mappings are API-only. Tenant administrators cannot manage or review GST UQC and other jurisdiction mappings in the UI. This is a documented boundary, not a failed existing screen. |
| G05 | High | High | Physical count with unit-aware observations and calculated variance remains unimplemented. The approved movement cutoff and verified-cost/review policies are documented, but StockAction contains no native count/adjustment action or observed-zero versus uncounted workflow. |
| G06 | Medium | Medium | Catalog effective-product stock readiness can only return NOT_APPLICABLE or UNAVAILABLE, with an unconditional accounting-unavailable reason for stock goods. There is no verified ready-state integration with the existing Accounting/Vouchers owner activation. Keep fail-closed behavior until that integration is proven. |
| G07 | Medium | Low | Two unit database/isolation tests seed/flush without tenant scope and fail inside the stock-source fence before reaching their intended assertions. Update fixture scoping; do not weaken tenant or stock-source guards. |

Evidence:

- G01/G02: `clients/voucher-execution/src/voucher_execution/stock.py:38`,
  `OpeningStockEntry.tsx:201`, `catalog/tasks/product_quantity.py:21` and signed
  opening facts in `catalog/tasks/stock_sources.py:312`.
- G03: `catalog/api/product_authoring.py:1049`, `catalog/domain/units.py:162`,
  `catalog/models/units.py:81`; reference search found no production caller of
  `compound_factor` and no Console quantity-preview caller.
- G04: `docs/catalog-unit-api.md` and `catalog/api/unit_relations.py:123`.
- G05: `docs/tenant-admin-stock-entry-plan.md:24`, including the accepted cutoff
  and surplus-cost decisions; `voucher_execution/stock.py` action catalogue.
- G06: `catalog/api/product_authoring.py:936` and `schemas/effective_item.py:31`.
- G07: `test_units.py::test_all_unit_tables_are_tenant_isolated` and
  `test_units.py::test_database_rejects_cross_company_conversion_and_duplicate_codes`.
  Both raise `TenantContextError` from the stock-source `before_flush` query.

## Suggested implementation sequence

1. Fix B01 so opening quantities can be entered; restore G07’s broken test fixtures.
2. Fix B03’s wire precision and B07/B08’s stock quantity presentation.
3. Fix B05/B06 so new products honor company unit defaults and required choices.
4. Plan and implement B02’s native unit admission, then resolve B04/G01 against
   that same entered/base quantity contract.
5. Plan measured and compound workflows G02/G03; add G04’s existing API controls
   and G06’s verified readiness integration as their dependencies permit.
6. Implement G05 using the already approved cutoff/cost decisions and the same
   authoritative quantity admission; retain observed-zero, history and valuation.

For the high-complexity admission/conversion work, the quick plan is: define
versioned company/SKU/unit/revision facts; validate entered and actual measured
quantities and date/role/grid rules before approval and posting; retain immutable
entered/base snapshots; connect UI and SDKs; then verify replay, returns, serial
counts, cutoff movements, tenant scope and value conservation against native owners.
No new business policy is decided or implemented by this review.

## Reusable material

- `docs/testing/unit-stock-review/findings.csv`: all bugs/gaps, priorities,
  complexity, reproduction, expected behavior and source evidence.
- `docs/testing/unit-stock-review/cases.csv`: reusable regression/acceptance cases
  including supported paths and explicit unimplemented boundaries.
- `docs/testing/unit-stock-review/run_probes.py`: replays diagnostic probes using
  temporary test files and disposable SQLite. Diagnostic assertions intentionally
  describe current defects; convert them to desired-behavior regressions when fixing.
- Private output is in ignored `.test_artifacts/unit-stock-review-*` files.

Reviewed exact arithmetic, semantic mutation locks, immutable history, signed
source fencing, tenant/company scope and protected fields. No production database
mutation, release activation or application fix was made during this review.
