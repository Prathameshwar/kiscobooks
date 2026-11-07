# Batch configuration and master review — 2026-11-07

Review of the current local working tree, including existing uncommitted changes.
Application code was not changed. This review covers company capabilities, Product
Configuration, Product Type and Inventory Profile masters, Simple and Advanced
creation, separate batch registration/correction, batch pricing and opening stock.
It does not establish the state of a deployed VM or production database.

The subsequent [batch and expiry create/edit UI review](batch-expiry-ui-review-2026-11-07.md)
records nine additional client findings and executable React/JSDOM evidence.

## Findings

P1 means a policy/data-integrity defect or a broken core workflow. P2 means a
functional inconsistency with a narrower trigger. Findings marked **probe** have
executable evidence in `testing/batch-config-review`; others are **code trace**.
The probes assert the existing bad behavior, so a passing probe confirms a defect.

### B01 — P1: Batch-off removes mandatory expiry and FEFO requirements

**Probe.** Configure a Goods type allowing `NONE` and `BATCH`, with
`require_expiry=false`; select a lot-tracked inventory template with
`expiry_required=true`, manufacture required, FEFO and minimum remaining life.
`product_stock_choice.available()` reports expiry required but batch optional.
Choosing batch-off then clears both required dates, shelf life, remaining life and
changes FEFO to FIFO in the activated profile.

Sources: [required calculation](../apis/catalog/src/catalog/tasks/product_stock_choice.py#L43)
and [profile rewrite](../apis/catalog/src/catalog/tasks/product_stock_choice.py#L104).
The governed [batch plan](simple-product-batch-opening-plan.md) says the switch
must not relax required expiry or mandatory tracking. The Product Type flag is not
the only source of mandatory policy: the inventory template contributes it too.

**Correction:** treat mandatory inventory date/expiry policy as a required batch
choice; reject disabling batches rather than silently weakening the template.

### B02 — P1: Date correction bypasses the expiry feature gate

**Probe, API request.** With company features `inventory` and `batch_tracking`
only, register a batch under a profile where expiry is optional, with no dates.
PATCH the batch with `expires_on=2028-01-01`. It returns **200** and stores the date
while `expiry_tracking` remains absent. The equivalent registration input is
rejected.

Sources: [registration gate](../apis/accounting/src/accounting/tasks/stock_tracking.py#L359)
and [correction branch](../apis/accounting/src/accounting/tasks/stock_tracking.py#L459).
Corrections call `validate_dates()` but do not check the company expiry feature.
The correction field-set also exposes expiry without that capability check.

**Correction:** validate the resulting date state against current company
capabilities on correction and replay, preserving allowed date-removal behavior.

### B03 — P1: Feature locking does not reflect actual batch/expiry use

**Code trace.** Registration and correction emit tracking audit events, without
an Identity feature-use/lock command. Yet the
[feature contract](company-features.md) specifies that
any batch record and any expiry date lock their respective features.

There is a second hole after posting: stock execution includes `expiry_tracking`
in the used-feature set only when the **product profile requires expiry**. An
optional-expiry profile can post a lot with an actual expiry date while leaving
expiry out of the set. Identity locks only features included in the reservation.

Sources: [tracking emission](../apis/accounting/src/accounting/tasks/stock_tracking.py#L582),
[used-feature calculation](../apis/accounting/src/accounting/tasks/stock_effects.py#L162),
[reservation](../apis/accounting/src/accounting/tasks/stock_execution.py#L133),
and [Identity lock](../apis/identity/src/identity/services/posting.py#L221).

**Impact:** settings can be disabled after data has used them; B02 also permits
recording expiry while disabled. This is a lifecycle gap, not merely a missing UI
warning.

**Correction:** coordinate feature use for actual physical declarations and
include actual lot expiry use in posting reservations. Preserve the service-owner
boundary and avoid remote calls inside database transactions.

### B04 — P1: Disabling purchase references makes batch opening stock impossible

**Probe.** Set `purchase_reference_mode=DISABLED`; enter a batch with opening
quantity 1 and purchase cost 10. Preparation rejects
`batches.0.purchase_price` as disabled. Omitting the price fails the schema's
positive-opening-cost requirement instead. The same conflation affects Simple
nonbatch openings; Advanced batch opening calls the same preparation function.

Sources: [required opening cost](../apis/catalog/src/catalog/schemas/simple_product_creation.py#L69),
[disabled reference enforcement](../apis/catalog/src/catalog/tasks/simple_batch_preparation.py#L94),
and [Simple scalar enforcement](../apis/catalog/src/catalog/tasks/simple_creation_preparation.py#L180).
The batch plan explicitly distinguishes reference prices from receipt cost, but
the input and preparation logic use one field for both facts and always publish
an entered purchase cost as a reference price.

**Correction:** separate stock opening valuation input from purchase reference
publication. Reference pricing disabled should not prevent legitimate opening
valuation or require reference-price permissions just to capture cost.

### B05 — P1: Separate batch masters have no usable batch-price workflow

**Code trace.** `/inventory/batches/new` saves only an Accounting physical batch.
It does not create the Catalog lot price scope, publish rates, or offer a batch
price action on the detail page. Catalog resolution requires a selected lot for
products created with batches enabled, then rejects a missing price scope as
unavailable. Existing SKU prices cannot supply that lot.

Sources: [master save](../mfes/apps/console/app/components/StockTrackingPage.tsx#L616),
[master detail actions](../mfes/apps/console/app/components/StockTrackingPage.tsx#L426),
[batch scope lookup](../apis/catalog/src/catalog/tasks/batch_pricing.py#L29),
and [resolution](../apis/catalog/src/catalog/tasks/pricing_resolution.py#L223).
The native `/batch-prices` API exists, so this is an incomplete master workflow
rather than absence of backend pricing support. Simple one-save creation does
perform the missing price step.

**Correction:** provide protected initial and subsequent batch-price actions,
with price-level coverage and publication/retry handling, from the batch/product
master. Missing rates should produce actionable readiness information.

### B06 — P2: Batch master registration ignores required/disabled physical MRP

**Code trace.** Accounting's verified `TrackingSource` carries tracking/date
requirements but no pricing/MRP policy. `BatchPrepare` makes MRP optional and checks
only that amount, currency and unit are supplied together. Consequently separate
registration can omit required MRP or enter MRP when Product Configuration disables
it. Catalog discovers the mismatch only when initial batch prices are published.

Sources: [source and prepare schemas](../apis/accounting/src/accounting/schemas/stock_tracking.py#L24),
[registration validation](../apis/accounting/src/accounting/tasks/stock_tracking.py#L358),
and [later MRP rejection](../apis/catalog/src/catalog/tasks/batch_pricing.py#L99).
`BatchCorrect` supports dates only; there is no ordinary MRP correction action.
The incorrectly registered lot therefore cannot be repaired through that form.

**Correction:** make the registration flow obtain verified applicable declaration
policy before committing an immutable MRP, and surface required/disabled status in
the form. Define a controlled repair path for unused bad declarations.

### B07 — P2: Advanced opening accepts zero cost, then fails internal validation

**Probe, schemas and real UI policy.** An Advanced nonbatch opening with positive
quantity and `purchase_price=0` passes both `openingErrors()` and
`AdvancedOpeningInput` (`ge=0`). `local_preflight()` converts it to
`SimpleCreationInput`, whose price requires `gt=0`. That conversion raises an
uncaught Pydantic `ValidationError` after the request has been accepted, once prior
readiness checks pass. The batch UI also accepts zero purchase cost although
`SimpleBatchInput` rejects it at request validation.

Sources: [Advanced schema](../apis/catalog/src/catalog/schemas/advanced_product_creation.py#L309),
[internal conversion](../apis/catalog/src/catalog/tasks/advanced_creation_opening.py#L203),
[Simple schema](../apis/catalog/src/catalog/schemas/simple_product_creation.py#L100),
and [UI validation](../mfes/apps/console/app/lib/advanced-product-opening.ts#L47).
The endpoint error consequence follows from the uncaught conversion; a complete
HTTP reproduction past all readiness gates was not performed.

**Correction:** agree zero-value opening behavior, align both input contracts and
UI validation, and translate invalid user input into a field-level 422 response.
Native Accounting arithmetic already supports zero valuation.

### B08 — P2: Advanced batch creation requires redundant SKU prices and MRP

**Probe, real UI policy.** Select batches and enter complete batch purchase,
selling and MRP values in opening rows. `openingErrors()` returns no errors, but
`businessErrors()` still requires SKU purchase reference, selling price and product
MRP. The final submit aggregates these errors and blocks creation. Those SKU prices
are not candidates for lot-scoped resolution, and the product MRP is not the lot's
physical MRP.

Sources: [unconditional SKU requirements](../mfes/apps/console/app/lib/advanced-product-business.ts#L32),
[submit aggregation](../mfes/apps/console/app/components/AdvancedProductWizard.tsx#L128),
and [batch activation coverage exception](../apis/catalog/src/catalog/tasks/activation.py#L113).
The backend activation intentionally skips SKU-price coverage for an enabled batch
choice; the Advanced client does not follow that contract.

**Correction:** evaluate required prices and declarations against the selected
batch scope. Require SKU-level sources only where a separately documented feature
actually consumes them.

## Additional gaps and limits

- **Shelf-life validation can be bypassed by omitting manufacture.** A valid
  inventory template may have shelf life without requiring manufacture date.
  `validate_dates()` and Simple preparation check the shelf-life duration only
  when both dates exist. Both creation UIs hide manufacture unless it is required,
  so users cannot voluntarily supply it in this configuration. An expiry in 2090
  with a 30-day shelf-life setting passes the native date validator when manufacture
  is absent (**probe**). Decide whether shelf life mandates manufacture, permits a
  derived date, or explicitly leaves duration unchecked; communicate that choice.
  Sources: `accounting/domain/stock_tracking.py:36`,
  `catalog/tasks/simple_batch_preparation.py:69`,
  `SimpleProductBatches.tsx:21`, `AdvancedOpeningReviewStep.tsx:27`.
- **Batch choice cannot be changed on an existing product.** `ItemStockChoice`
  rejects all persistent updates/deletes. This is documented behavior, not an
  accidental bug. Enabling company batches does not migrate existing batch-off
  products. There is no reviewed migration workflow even for unused products;
  configuration should make this consequence clear.
- **Expired opening stock has no quarantine capture.** Preparation and posting
  reject expiry before books-begin date. That is an explicit current limitation;
  it should not be presented as a generic inability to enter a valid expiry date.
- **Advanced zero-stock batch creation differs from Simple.** Simple retains
  zero-quantity batch identities and prices. Advanced opening requires positive
  batch quantities; skipping opening creates no batches. Separate registration
  then encounters B05/B06. This is a workflow gap requiring scope agreement.

## Verification

Executed from the local service virtualenvs, with pytest cache disabled:

| Check | Result |
| --- | --- |
| Catalog `test_simple_batch_validation`, `test_batch_price_sources`, `test_batch_security`, `test_simple_batch_creation` | 11 passed |
| Accounting `test_stock_tracking` | 9 passed |
| Catalog `test_advanced_product_opening`, `test_company_product_configuration` | 20 passed |
| Review Catalog probes | 3 passed, confirming B01/B04/B07 |
| Review Accounting probes | 2 passed, confirming B02 and optional-manufacture shelf-life gap |
| Direct Node execution of real Advanced UI policy functions | 2 assertions passed, confirming B07/B08 |

The targeted Vitest suite could not start: local `pnpm` was unavailable; direct
Node invocation found Vitest but Vite/esbuild failed with `spawn EPERM`. No browser
rendering results are claimed. Review probes are retained so the observations can
be reproduced and later rewritten as fixed-behavior regression tests.

Example commands, from the corresponding service directories:

```powershell
.venv/Scripts/python.exe -m pytest -c pyproject.toml -q ../../docs/testing/batch-config-review/catalog_probes.py -p no:cacheprovider
.venv/Scripts/python.exe -m pytest -c pyproject.toml -q ../../docs/testing/batch-config-review/accounting_probes.py -p no:cacheprovider
```

From the repository root:

```powershell
node docs/testing/batch-config-review/console_probes.cjs
```

The existing passing suites verify useful ordinary tracking/pricing/retry
behavior; they do not cover the policy combinations in these findings. Repair
B01–B04 first, then complete batch master pricing/declaration admission and align
Advanced validation. No fixes, commits or publishing were performed.
