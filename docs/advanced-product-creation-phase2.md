# Advanced product creation: Phase 2 definition review

Reviewed 2026-11-04. This phase implements the native Product Profile and
explicit SKU definition transaction from [the plan](advanced-product-creation-plan.md).
The [live TODO](advanced-product-creation-todo.md) remains the phase gate.

## Contract and files

`POST /v1/companies/{company_id}/advanced-product-creations/definitions`
accepts a strict Profile, ordered explicit SKUs and optional native family
attribute declarations. The first SKU is the default. The endpoint requires an
`Idempotency-Key`; a replay returns the original family, SKU IDs and receipt.
`GET /definitions/{creation_id}` returns the submitting actor's company-scoped
stage and IDs for recovery. `DEFINED` with next step `SETUP` means only native
definitions are present; it does not imply a usable or active product.

| File | Phase 2 change |
|---|---|
| `apis/catalog/src/catalog/schemas/advanced_product_creation.py` | Strict Profile/SKU input, 64 SKU and 64 KiB bounds, duplicate code rejection, receipt/result schemas. |
| `apis/catalog/src/catalog/api/advanced_product_creation.py` | Submit and actor-scoped status endpoints under the existing wizard prefix. |
| `apis/catalog/src/catalog/tasks/products.py` | One idempotent transaction reusing native family, attributes and variant handlers. |
| `apis/catalog/src/catalog/tasks/advanced_product_creation.py` | Canonical request/hash receipt, marker-only audit, private status read. |
| `apis/catalog/src/catalog/models/advanced_product_creation.py`, `dbs/catalog/versions/0223_advanced_product_creation.py` | Durable receipt model and guarded single-table migration. |
| `apis/catalog/src/catalog/models/__init__.py`, `metadata.py`, `tests/test_migrations.py` | Model registration, expected head and migration coverage. |
| `apis/catalog/src/catalog/events/audit_contract.py`, `contracts/audit-events.json`, `mfes/apps/console/app/lib/catalog-audit-entities.ts` | Registered, generated admin audit marker. |
| `apis/catalog/openapi.json`, `clients/api-client/src/catalog.d.ts`, `clients/api-client/package.json` | Generated API contract and client version. |
| `apis/catalog/tests/test_advanced_product_definition.py`, `test_advanced_product_definition_mysql.py` | Scoped, rollback, replay and native migration checks. |

The command checks the company mode, policy generation, effective configuration
source version and business date before writing. Existing Catalog code checks
scope, current field policies, published Product Type, units, options, required
attributes and variant signatures. The transaction writes no setup, price,
tax, stock, Accounting or Voucher effects. Its audit markers contain IDs and
change metadata without submitted Profile/SKU content.

## Bounds and recovery

A submission accepts up to 64 explicit SKUs and 64 KiB of canonical validated
JSON. Numeric custom-field floats are rejected. A larger family can add further
SKUs later through the existing bounded native variant command. The wizard
must show this limit before submit. The retained request is the validated
canonical JSON, not a byte-for-byte copy of the HTTP body. The hash and key
identify the accepted command; reusing a key with changed values fails. The
receipt keeps the submitting actor, family/SKU IDs and progress fields for
Phases 3–4. A failed later SKU rolls back the family, earlier SKUs, receipt and
audit events from the same command.

## Review and verification

`CLAUDE.md` §§5–6 review: the endpoints require actor scope; object status is
actor/company scoped with tenant session filtering; strict inputs reject
unknown fields; field writes and native reference reads are server checked;
replay has one effect and rechecks permission; audit/outbox share the Catalog
transaction. There is no money or stock mutation in this phase. No blocking
finding remained after review.

Focused Catalog definition, draft, native authoring, migration and audit tests:
**25 passed, 1 skipped**. The skipped test needs the optional dedicated Docker
MySQL server. A private backup of local `catalog` was saved outside the
repository at `%LOCALAPPDATA%/BillBackups/catalog_phase2_20261104.sql`.
Restoring it to an isolated schema and upgrading `0222→0223` passed. Two native
definition scenarios passed there, the nonempty receipt downgrade guard held,
and model comparison found zero differences. The isolated schema was removed.
Local `catalog` was then upgraded to `0223`; its migration head and model match
with zero differences. All eight local database heads match their current
script heads. Ruff and strict mypy on changed Python, generated
OpenAPI/audit checks, Catalog client generation check, standalone Catalog
declaration compilation and Console typecheck passed.
The final definition-focused run, including mode-change denial, passed
**5 tests**.
The full API-client typecheck still fails on the pre-existing Accounting
declaration test: `tests/accounting-types.ts` expects `AccountCreate`, which
the concurrently modified Accounting declaration does not export. The
Catalog-only declaration check passed; no Accounting file was changed here.

Phase 3 will apply per-SKU native setup and readiness. Phase 4 will handle
optional opening through its native owners. Phase 5 will implement the
mode-selected card and wizard UI. These phases remain subject to their own
review and the user's phase confirmation.
