# Simple product creation ready on Save

Follow-up: [the creation UI review](simple-product-ui-review.md) records the latest
layout, validation, accessibility, field-access and navigation improvements.
The [details-switch follow-up](simple-product-details-switches.md) adds configured
Brand, Model and Barcode switches and native barcode capture on the same Save.
The [multiple-price follow-up](simple-product-multiple-prices.md) replaces the
single selling amount with named configured levels when multiple pricing is enabled.
The [batch-entry follow-up](simple-product-batch-opening-plan.md) adds a configured
second step, tracking choice, batch prices and multi-line opening posting.

Authorized 2026-11-04: resume Product Configuration and deliver the simple product
flow, company defaults, immediate activation, live prices and posted opening stock.

## Agreed behaviour

- Type (Goods / Services, default Goods), name, optional code (generate 10 characters), group, base unit, applicable tax,
  configured Purchase/Selling/MRP prices, opening quantity and opening date.
- Purchase price is per base unit in company currency. Positive opening quantity
  requires Purchase price; carrying value is its exact product with quantity,
  rounded by the native Accounting rules. No separate opening-rate input.
- Services hide opening stock; the native API rejects any service stock input.
  Units, groups, taxes and pricing applicability follow the selected kind.
- GST-enabled companies use HSN for goods and SAC for services, with native GST
  classification/rule selection and validation before activation. Tax defaults are
  never guessed from the product's name or selling price.
- Opening date is the company's books-begin date. Product/unit facts must be valid
  then. No separate submission, approval or activation screen for this flow.
- Save completes only after requested native effects complete. Stable commands
  and retained receipts recover partial execution without duplicate stock/value.
- Repeated creation supports independent new products. It must not reopen or
  rewrite another product's posted opening, even after that product starts trading.
- Existing company-wide cutover/corrections and configured advanced workflows
  retain their history. Closed periods and field/scope permissions still apply.

## Delivery phases

1. Finish Product Configuration controls and UI review: Model, Brand, unit
   conversion, native enforcement, migration, responsive presentation and tests.
2. Prepare a simple stock-ready company: inventory defaults, default location,
   account/valuation mappings, applicable books and no approval step for the
   explicitly authorized simple creation operation. Preserve existing companies.
3. Extend native opening recording for independent new products, with one opening
   per product, period checks, retained manifest/stock/GL evidence and isolation
   from already traded products. Reuse native stock execution and reconciliation.
4. Add a durable creation workflow that derives defaults, generates blank codes,
   applies definitions/tax/prices, activates and posts the opening. Retain progress,
   audit and exact idempotency keys; never call remote owners in a money transaction.
5. Add the simple creation UI and navigation using native field metadata and shared
   CSS. Validate all inputs together; surface recoverable failure on the same form.
6. Verify contracts, native migrations, repeated creation/trading, permissions,
   replay/recovery, UI behaviour and responsive themes. Complete manual security
   and simplicity review, with exact evidence and any limitations recorded here.

## Evidence

The subsequent [end-to-end review](simple-product-end-to-end-review.md) records
configuration/form alignment and receipt-permission fixes, expanded default
Goods/Services coverage, and the latest verification evidence.

Implemented locally on 2026-11-04. Product Configuration, company defaults and
`/masters/items/new` use native metadata and shared styles. The form defaults to
Goods, switches HSN to SAC for Services, hides service stock, and publishes the
selected purchase/selling prices and enabled MRP before activation. A positive
opening uses the company books-begin date and the native Accounting calculation.

Catalog's 32-test creation/initial-setup/activation regression passed. Accounting's
native MySQL opening suites passed (7 tests), including exact stock value, replay,
finalization and a new product after another product has traded. The additional
closed-period and Decimal-type assertions passed in the focused 2-test suite.
The native Vouchers test passed creation, automatic submission, numbering and
posting admission with the exact opening manifest. Identity's 18 automatic company
setup and 2 gateway-context tests passed. Configuration/company UI checks passed
(73 tests), with navigation/retired-page checks also passing. The final focused
creation suite passes all 12 tests, including tenant isolation and posting retry.
The final native MySQL matrix passes (1 test covering Goods/Services, GST,
activation, live prices, lost-response recovery, terminal posting retry and retained
receipt rollback). One earlier long-running native attempt returned the expected
busy response; a fresh run passed in 152 seconds with normal command timeouts.

The Simple form's 10 UI tests pass. Four browser tests cover 48 layout scenarios:
Goods/Services and configuration editor/review at 320, 390, 768 and 1440 pixels in
light, dark and ledger themes. Screenshots were inspected, including service SAC
and hidden opening stock on mobile. The final form run also verifies themed Cancel
text after correcting its shared style. Artifacts are in
`.tools/simple-product-ui-review/` and `.tools/product-config-ui-review/`.

OpenAPI, audit contracts and generated TypeScript consumers were refreshed.
Console and API-client type checks and generated-client consistency pass. The
API-client's stale AccountCreate assertion was updated to the existing native
AccountCreation contract. Changed Python application files pass Ruff and strict
mypy. Catalog migration checks pass (4 tests); the Docker-based roundtrip skips
when Docker is unavailable, with isolated native MySQL verification run separately.

Catalog 0217/0218 and Accounting 0232 are applied to the local database after
backup. Existing values were preserved; native schema/model/Alembic verification
reports zero differences across 183 Catalog and 147 Accounting tables. Details
and backup/report locations: [local schema verification](local-schema-sync.md).
Private local owner connections and stock admission are configured. Application
services remain stopped; a live browser Save through the running gateway/workers
has not been exercised. Production deployment/activation and whole-repository
coverage are not claimed.
The dedicated temporary MySQL server on port 13398 was shut down after verification;
the existing local database on port 3306 remains running.

## Review and decisions, 2026-11-04

Manual security and simplicity review was used because the `/simplify` and
`/security-review` commands are not available in this session. Findings fixed:

- Configuration assignment refresh discarded unflushed edits. Field-authorized
  changes now flush before dependent validation, in the same transaction.
- Initial GST classification/rule setup lacked the required treatment binding.
  Initial setup now writes classification, treatment and rule for each direction.
- Opening stock needs native voucher numbering before posting. The coordinator
  now executes submission, issue and posting automatically using the native owners.
- Pending creation must allow native opening proof and preview while preventing
  ordinary trading until completion. The source fence enforces that distinction.
- A lost Save response must not unlock input or permit a second product. The
  retained command is replayed; corrections require a definitive rejection before
  any native product exists. Ambiguous work retains the exact original command.
- A terminal rejected posting could strand creation in finalization. A confirmed
  REJECTED/CANCELLED owner receipt permits a fresh POST attempt on the same voucher
  and control. PENDING/uncertain attempts cannot create another posting operation.
- Required advanced configuration that this simple form cannot capture is rejected
  before product creation. Required Brand/Model/Barcode and
  [Category/Manufacturer](simple-product-category-manufacturer.md) are supported in this form.
- The form's secondary links used an undefined style variant. They now use the
  shared ghost-button style, with a browser check for the themed text colour.

Scope, field permissions, audit, closed periods and exact Decimal calculation
remain enforced by each owner. Remote calls occur outside database transactions.
Only the initiating user can resume a creation, with fresh signed authority; no
credentials are retained in its receipt. API responses are not cached. Tests cover
cross-company/user access, tenant isolation, lost responses and idempotent effects.

Decisions: new companies receive minimal Simple configuration and a zero-confirmed
company baseline; each later new product can add its own immutable opening. This
does not overwrite existing published company configuration or traded products.
The user performs one Save, while native lifecycle/audit steps remain automatic.
Existing product edit/detail, advanced authoring and batch/serial pages stay deferred.
