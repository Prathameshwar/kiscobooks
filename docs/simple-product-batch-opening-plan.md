# Simple product batch entry and opening

Requested 2026-11-04: when configured, add a second Simple product step with an
Allow batch switch and rows for batch, expiry, opening quantity, purchase price,
selling prices and MRP. Complete the missing native support, preserving one Save.

## Findings

- Accounting owns real batches, dates, stock positions and receipt cost layers.
  Batch registration and batch stock posting already exist.
- The Simple coordinator and product-opening control currently accept only one
  untracked opening line. They must accept multiple lines for the same product.
- Catalog price scope currently permits only SKU; batch price resolution is not
  implemented. Product MRP is not a physical batch declaration.
- Tracking availability combines company capabilities, the configured Goods type
  and inventory template. Activated profiles are pinned per product. The switch
  must not turn off mandatory tracking or relax required expiry/serial rules.

## Delivery phases

1. **Native batch definitions and pricing.** Preserve Accounting ownership of
   batch identity/expiry and physical MRP. Add protected Catalog batch price scope
   and resolution using verified company/product batch references. Retain native
   numeric grids, price levels, publication, permissions and audit. Add the minimum
   reversible migrations and verify native MySQL parity.
2. **One-save creation and opening.** Persist the selected tracking choice, create
   the product and batches, publish each batch's rates, calculate each row's exact
   opening cost and post one native opening voucher with all positive rows. Keep
   exact commands/keys across retries, enforce the initial-product trading fence,
   and report success only after reconciliation/finalization.
3. **Simple creation UI.** Keep product identity/tax/details in step one. Show the
   second step only for applicable Goods; use an Allow batch switch and editable
   rows, configured selling levels, conditional expiry/MRP and per-row errors.
   Preserve entered rows across navigation and explicit setting changes. Reuse
   shared controls/styles and test desktop/mobile layouts and keyboard operation.
4. **End-to-end review.** Test batch on/off, required settings, multiple batches,
   zero stock, exact values, invalid dates/duplicates, cross-company references,
   field denies, closed periods, failed/uncertain saves and replay. Regenerate API
   contracts/clients, run affected regressions and document actual evidence.

## Decisions

- Services have no batch step. A configured mandatory tracking requirement remains
  enabled. Optional tracking can be selected only within the native type/profile
  capabilities; the selected behavior is pinned when the product activates.
- With batch entry enabled, opening quantities and entered rates belong to each
  row. Each configured selling-price level is a separate column. A positive
  opening quantity requires its purchase price; value is quantity × purchase price.
- Expiry is shown when enabled and required where native policy requires it.
  Manufacture date is also captured if the selected inventory policy requires it.
- Opening date remains company books-begin date. The existing default opening
  location is used internally; no warehouse-specific pricing or user choice is added.
- Batch purchase reference rates and posted opening cost are different facts.
  Changing a reference rate must not rewrite posted receipt cost.
- An initial physical MRP is retained with the batch and must not be replaced by
  later product-default MRP. Multiple physical declarations within the same batch
  require their own allocation support; silently merging different MRPs is forbidden.
- Import capture and separate batch/serial management pages are outside this
  creation-flow request. Existing incompatible import settings remain explicit.

## Delivered contract

Catalog migrations 0220–0221 store immutable `item_stock_choice` and extend
`item_price_scope` with verified `LOT` identity and a mirror of the physical MRP.
A generated lot key preserves one SKU scope and one scope per batch. Accounting
0235 retains the initial MRP amount, currency and declared base unit on `stock_lot`.
Downgrades refuse to discard used batch choices, prices or declarations.

`GET /simple-product-creations/options` returns batch availability, required flags
and protected native field metadata. Creation accepts `batch_enabled` and up to
64 `batches`. Rows own quantity, purchase, configured sale levels and MRP; scalar
stock/prices cannot be mixed with them. Optional batch-off creates an untracked
inventory profile. Mandatory tracking cannot be switched off.

After activation the resumable coordinator registers each batch, calls native
`POST /batch-prices`, and posts positive quantities in one product opening.
Zero-quantity rows retain their identities and prices. One final Save runs
submission, issue, posting and reconciliation; uncertain responses retain exact
commands and per-row keys. Non-batch command hashes/keys remain compatible.

`POST /prices/resolve` and `/prices/coverage` accept `lot_id`. They verify the
Accounting batch belongs to the company/product and is active and not held.
Batch-tracked products require the batch; there is no fallback to another batch
or a SKU scope. Existing price-level/channel/unit rules still apply. Inclusive
MRP and exclusive selling amounts require transaction tax context; they are never
compared as equivalent amounts.

Batch publication schedules do not depend on the product's MRP history. Native
MRP-discount recipes use the batch's physical declaration, with its declared unit,
company currency and jurisdiction; converting tax basis still requires transaction
tax context. Simple creation itself captures fixed prices.

## Verification and boundaries

2026-11-04 follow-up: [serial opening input](simple-product-serial-opening-plan.md)
now supports combined batch-plus-serial profiles. Each batch owns its physical
unit rows; its opening quantity is derived from their count. Batch prices and
expiry remain on the batch. Native opening lines include the registered unit IDs.

- Native MySQL upgrade/downgrade/re-upgrade and model parity passed for both owners.
  Local Catalog is at 0221 and Accounting at 0235.
- Native Catalog tests cover separate batch prices, retained registration replies,
  price resolution and optional batch-off. Accounting tests cover multi-batch
  opening posting, reconciliation, distinct quantities/costs and replay, plus exact
  immutable physical MRP. Coordinator tests check matching voucher/manifest rows.
- UI tests cover the second step, switching, row validation, exact input, configured
  sale levels, navigation and ordinary Simple flow. Browser checks cover four
  widths and three themes with scrolling contained inside the grid.
- OpenAPI and generated API client 0.2.68 include the new contracts.
- This slice supplies creation and native price resolution. A voucher consumer must
  send its selected `lot_id`; it does not add batch selection to other voucher UIs.
  Multiple physical MRP declarations within one lot, actual-cost pricing and batch
  import capture remain outside this request.
- Accounting's full audit-matrix generator encounters unrelated missing event
  categories (`master_opening_balance`, `stock_count`) in this working tree. The
  changed batch evidence fields were updated from native resource definitions;
  unrelated event entries were preserved.

Decision 2026-11-04: batch prices reuse Catalog series/publication; physical identity
and immutable declared MRP stay with Accounting. Product opening admits distinct
lots of one product and remains one finalized opening control.

Final review addressed batch/SKU MRP isolation, exact Decimal audit evidence,
normalized batch-code overflow, required date/settings validation, protected batch
field admission, and price transaction/retry timing. Desktop batch entry uses the
page width; mobile scrolling and hidden accessible labels stay inside the grid.

Final targeted results: 15 Catalog creation/pricing/security/audit checks passed;
three further tenant-isolation/authorization/product-MRP checks passed; seven batch
source/configuration regressions passed. Migration contracts passed (four checks;
the Docker-only generic roundtrip was skipped, with separate native MySQL parity
checks passing for both owners). Accounting posting and MRP suites passed. The
Simple UI suite passed 44 checks, with the final batch-only rerun also green;
browser inspection covered 12 width/theme combinations. Scoped Ruff, strict mypy,
console TypeScript and generated Catalog/Accounting client checks passed.
