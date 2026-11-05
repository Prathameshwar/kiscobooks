# Advanced product creation: Phase 4 owner contracts

Reviewed 2026-11-05 after Phase 3. The optional per-SKU opening uses the
existing [Simple product opening coordinator](simple-product-batch-opening-plan.md)
owner routes. This document records the owner boundary before adding Advanced
commands. The [live TODO](advanced-product-creation-todo.md) remains the review
record.

| Fact or operation | Native owner and route | Advanced coordinator responsibility |
|---|---|---|
| Product identity, effective unit and profile | Catalog `GET /items/{id}/effective-facts` | Verify the activated SKU, current base-unit revision and selected stock mode. |
| Location | Catalog `GET /warehouse-configuration` and native warehouse/location policy; Accounting opening capture | Present an allowed opening warehouse and preserve its ID. Accounting validates the final location. |
| Batch and physical MRP | Accounting `POST /stock-tracking/batches` | Preflight field access, send one stable key per batch and retain lot IDs. |
| Batch purchase and named selling prices | Catalog `POST /batch-prices` | Apply the native price plan and precision rules after the Accounting lot exists; retain the publication response. |
| Serial/IMEI identifiers | Accounting `POST /stock-tracking/serials/check-identifiers` and `POST /stock-tracking/serials` | Verify field access and company identifier uniqueness, preserve each stable key and physical-unit ID. |
| Exact opening quantity and value | Accounting `POST /stock/openings/calculate` and `POST /stock/openings/products/{item_id}` | Retain the exact calculation and opening control manifest. Never calculate a posting amount in Catalog. |
| Voucher lifecycle | Vouchers capability, type, effective configuration, `POST /vouchers` then submit/issue/post | Require a current opening type and no approval requirement for immediate posting; retain voucher and operation IDs. |
| Reconciliation | Accounting `GET /stock/openings/{id}/reconciliation` and finalize | Finish only after the posted Voucher and physical/value controls agree. |

All owner calls occur after committing the pending command and its stable
idempotency key in Catalog. A lost response leaves that command pending; a retry
sends the same key. Only a definite owner rejection clears it. A posting
operation whose result is uncertain remains pending until Vouchers reports its
state. A posted opening is shown as complete only after Accounting finalizes
the matching control. The per-SKU receipt keeps other SKUs visible even while
one opening needs attention.

## Advanced per-SKU contract

`POST /definitions/{creation_id}/skus/{item_id}/opening-preflight` checks an
`OPEN` or `SKIP` decision without saving it. `POST .../opening` saves the
decision with a stable `Idempotency-Key` and expected creation version.
`POST .../opening/advance` executes one retained owner command. The client may
call advance until the SKU says `POSTED`; a `503` leaves its exact pending key
for retry. A `SKIP` decision has no owner call. The parent creation becomes
`COMPLETE` only when every SKU is activated and each opening is `POSTED` or
`SKIPPED`.

An `OPEN` command accepts the books-begin date, an optional active warehouse,
exact quantity and purchase cost, up to 64 batches and up to 200 serial units.
Batch prices include purchase, named selling levels and physical MRP through
the existing batch owner routes. The coordinator requires a base-unit revision
effective on the books-begin date, an active stock inventory profile, a batch
shape matching that profile and one serial/IMEI set per physical unit when
serial tracking is enabled. It reads the SKU's own identifier profile for
normalization and company uniqueness checks. Catalog does not calculate the
opening stock value: Accounting's exact calculation and final reconciliation
are retained with the Voucher posting operation.

`apis/catalog/src/catalog/tasks/advanced_creation_opening.py` contains the
decision, native preflight, lease, pending command and owner receipt handling;
the API and schemas live beside the earlier Advanced routes. The existing
`advanced_product_creation.progress` JSON and lease fields from revision
`0223` hold per-SKU state. No new database table or migration is needed.

For an opening dated before the product's creation date, the base-unit binding
must start by the books-begin date. The SKU setup command already accepts a
per-unit `valid_from` distinct from the setup's commercial effective date; the
wizard must show this requirement before activation. A missing binding is a
preflight blocker rather than an attempted stock posting.

## Review and verification

The coordinator checks the current actor, company, SKU and submitting user,
then native unit/profile/identifier and Accounting field authority. For open
stock it requires the books-begin date and a published active SKU. Selected
warehouses are read from Catalog and must be active; a selected warehouse does
not depend on a configured default. Stock value comes from Accounting's exact
calculation. The pending command and stable key are committed before any owner
POST. Retried uncertain responses reuse the key, and only a posted Voucher plus
Accounting reconciliation marks an opening `POSTED`. A previously posted SKU
receipt remains intact while another SKU is skipped or resumed. Audit markers
contain IDs and actions, not quantities, prices or identifiers.

The final Advanced opening suite passed **5 tests**: exact serial count and
skip shape, a books-begin unit blocker, skip replay, closed-books preflight,
lost-response retry with exact value, and a retained posted receipt across
two variant SKUs. The native Simple owner regression passed with it: **6 passed**
in the final focused run. The broader Advanced/Simple batch and serial run
passed **16 tests**. Ruff and strict mypy passed for the changed code;
OpenAPI, audit contract and generated Catalog client checks passed after the
new routes. Live Accounting/Vouchers integration is part of Phase 7's scenario
matrix; these Phase 4 tests use simulated owner responses and the existing
native Simple owner contract tests. No blocking Phase 4 finding remains.
