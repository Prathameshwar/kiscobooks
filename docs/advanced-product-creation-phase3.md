# Advanced product creation: Phase 3 setup and activation review

Reviewed 2026-11-05. Phase 3 adds per-SKU native Catalog setup after the
atomic Product Profile/SKU definition in [Phase 2](advanced-product-creation-phase2.md).
The [live TODO](advanced-product-creation-todo.md) records the continuing phases.

## Commands and recovery

Each submitted SKU has an actor and company scoped progress record. `setup`
applies initial group, units, barcode, category, manufacturer, stock choice,
published tax bindings, price drafts, purchase reference cost and MRP through
the existing Catalog writers in one transaction. The first SKU owns shared
Profile setup. Exact prices and references use the reviewed policy generation,
source version, base-unit revision, currency, precision and dated history rules.
`publish-prices` publishes all of that SKU's drafts in one transaction.
`readiness` maps native activation blockers to Profile, SKU or Business fields.
`activate` uses a current native activation preview; it does not bypass a
missing tax, price, category, unit or inventory profile requirement.

Each write has an `Idempotency-Key` and expected creation version. Setup and
activation also require current family and SKU versions. A successful step
retains only IDs and state in its public receipt. A failed step rolls back its
native rows, policy generation, progress and audit events together. Earlier
SKUs keep their progress, so the wizard can resume the remaining SKU. Once a
first SKU activates its shared Profile, another draft SKU can still finish
setup under the active Profile.

## File changes

| File | Phase 3 change |
|---|---|
| `apis/catalog/src/catalog/schemas/advanced_product_creation.py` | Strict SKU setup, exact reference, publication, readiness and activation contracts with bounded payloads. |
| `apis/catalog/src/catalog/api/advanced_product_creation.py` | Per-SKU routes, idempotency and numeric error handling. |
| `apis/catalog/src/catalog/tasks/advanced_creation_steps.py` | Native transactional setup, reference writes, atomic price publication, activation and scoped replay. |
| `apis/catalog/src/catalog/tasks/advanced_creation_readiness.py` | Native activation preview and step/field blocker paths. |
| `apis/catalog/src/catalog/tasks/advanced_product_creation.py` | Durable per-SKU progress and private status projection. |
| `apis/catalog/src/catalog/events/audit_contract.py`, `contracts/audit-events.json`, `mfes/apps/console/app/lib/catalog-audit-entities.ts` | Registered marker-only progress audit updates. |
| `apis/catalog/openapi.json`, `clients/api-client/src/catalog.d.ts`, `clients/api-client/package.json`, `clients/api-client/package-lock.json` | Exported contract and client version. |
| `apis/catalog/tests/test_advanced_product_setup.py` | Replay, rollback, exact price/cost, publication, permission and blocker coverage. |

## Review

The command rechecks tenant, company, submitting actor, native object scope,
permissions, field writes and source versions. Purchase-plan publication
rechecks purchase-price authority on replay. Pricing and tax stay with Catalog;
there is no Accounting or Voucher call in this phase. Audit/outbox records are
committed with each local state change and contain identifiers rather than
submitted commercial values. The native activation test suite provides the
fully configured positive activation case; the Advanced tests verify that an
incomplete Service SKU remains blocked and its progress stays recoverable.

There is no Phase 3 database migration; `advanced_product_creation.progress`
from revision `0223` holds the new per-SKU fields. Optional stock opening and
cross-owner receipts start in Phase 4. No opening or voucher effect is implied
by an activated SKU.
