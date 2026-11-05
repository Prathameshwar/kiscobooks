# Simple product API

2026-11-04 addition: the [batch creation contract](simple-product-batch-opening-plan.md)
extends ready-on-Save options/input with a configured batch step, per-row prices and
multi-line native opening. Catalog's price resolver accepts verified `lot_id`.

2026-11-04 serial addition: the [serial creation contract](simple-product-serial-opening-plan.md)
adds configured Serial/IMEI input at product or batch level, derives whole opening
quantities and registers native physical units before posting. The current Simple
UI uses `/simple-product-creations` to make the product ready and finalize its
opening on Save. The low-level `/products` lifecycle described below remains a
separate draft operation.

Original API surface, 2026-10-28. The initial API phase plan
is [simple-product-api-plan.md](simple-product-api-plan.md), and test/review evidence
is recorded in [the implementation TODO](simple-product-api-todo.md).

## Company authoring mode

Base path: `/v1/companies/{company_id}` on Catalog.

| Method and path | Contract |
|---|---|
| `GET /product-configuration/authoring` | Current `product_family_sku_enabled`, `row_version`, `policy_generation` |
| `POST /product-configuration/authoring/preview` | Desired boolean, expected version/generation and change reason; returns blockers and a signed preview |
| `PATCH /product-configuration/authoring` | Same request plus `preview_token`; idempotency key required |

New companies resolve false immediately. GET creates no configuration row and
reports version zero until the first write. Existing companies retain advanced mode
through the explicit compatibility seed, never inferred from company projections.
Migration 0210 and the [roster procedure](../seeds/product-authoring/README.md) are
release prerequisites. Do not deploy the new fallback before reconciling the roster.

This live company control belongs to Catalog Product Configuration. It is not a
dated product-default release, Identity inventory capability, or product override.
Reads require `product_configuration.read`; preview/commit also require
`product_configuration.manage`. Native field policies apply. Previews expire after
15 minutes, bind the actor/company/request, and are rechecked under the company lock.

Enabling preserves every item/family/profile/stock ID. Disabling rejects retained
variant structure, non-single-default families, axes/keys, explicit retained
required/enabled variant policies, and unfinished bulk jobs. Blockers are bounded
reason codes without protected product identities. Nothing is merged or cleared.

## One product resource

| Method and path | Behavior |
|---|---|
| `GET /products/field-set?operation=create` | One product form contract, native controls, source and authoring versions |
| `GET /products/field-set?operation=update&object_id={item_id}` | Current object/field/lifecycle-specific metadata |
| `POST /products` | Atomically creates a SIMPLE family and its one default item |
| `GET /products` | Lean signed-cursor directory, one row per item |
| `GET /products/{item_id}` | Single product detail and aggregate revision |
| `PATCH /products/{item_id}` | Atomic simple-product edit with revision and authoring checks |

Example creation after reading the company authoring version:

```json
{
  "authoring_version": 0,
  "code": "NOTEBOOK-A4-200",
  "name": "A4 notebook, 200 pages",
  "kind": "GOODS",
  "product_type_revision_id": "<published-type-revision UUID>",
  "base_unit_id": "<unit UUID>",
  "sellable": true,
  "purchasable": true
}
```

Send the standard `Idempotency-Key` header on writes. Creation returns 201, a
Location ending in the item ID, and one resource containing `id`, `code`, `name`,
permitted descriptive fields, `revision`, `authoring_version`, `policy_generation`
and bounded related-operation links. No second editable family identity or nested
`default_item` is required. The internal family code is generated server-side.

Product ID is exactly `Item.id`; product code maps to `Item.sku`. Existing family
and item API clients and receipt identities remain supported. Product reads can
also inspect advanced items. Simple aggregate PATCH rejects a shared/variant family;
advanced edits continue through the existing explicit APIs.

Example edit:

```json
{
  "revision": "<revision returned by product GET>",
  "authoring_version": 0,
  "name": "A4 notebook, 200 pages - ruled"
}
```

Revisions bind actor, tenant, company, item, family and both row versions. They
expire after one day and never grant authority. A native family or item edit makes
the prior product revision stale. A live mode change makes the authoring version
stale. Reload instead of silently retrying changed input under the old receipt key.
Invalid or expired revisions return 422 with a `revision` field error and an
instruction to review the latest saved product. This applies to product edits and
product-owned setup adapters. The editor preserves entries during explicit revision
review; the subsequent save uses the reviewed revision and a fresh idempotency key.

Creation reuses native references, custom-field claims, default acceptance,
configuration review and initial units/barcodes/attributes/tax/price setup. Products
remain drafts; native readiness/activation rules and draft-price publication apply.
Initial setup requires its existing additional permissions. Failures roll back all
created records and audit events. Existing active-product editing restrictions hold.

`custom_fields` carries item definitions; `shared_custom_fields` carries family
definitions. Both appear within one form contract, with distinct keys and native
bindings. Clients use those bindings when evaluating native-name custom-field
conditions; presentation aliases never replace server-side field permissions.
Code/name appear once. Hidden fields remain protected in detail, lists, filtering,
search, sorting, imports and receipt rendering.

## Attributes and family-owned setup

| Method and product path | Native behavior reused |
|---|---|
| `GET /products/{item_id}/attribute-form` | Product specifications, values and edit capability, without duplicate family/SKU names |
| `PUT /products/{item_id}/attributes` | Family declarations plus this product's values |
| `POST /products/{item_id}/groups` | Dated primary group assignment |
| `POST /products/{item_id}/manufacturers` | Dated manufacturer assignment |
| `PUT /products/{item_id}/categories` | Native category assignment/preview rules |
| `POST /products/{item_id}/category-preview` | Signed category replacement preview using the product revision |

These mutations take `revision` and `authoring_version` with their native business
fields. Attribute input uses `attributes` for declarations and `values` for typed
selections; no second editable default-SKU identity/version is needed. Adapters
resolve the family internally, check the product aggregate, then invoke the same
native command. Expected versions, field policies, lifecycle and date restrictions
are preserved. Initial values/declarations remain bounded by native limits.

Ordinary attributes do not require advanced mode. Variant axes and sibling creation
do require it, even through legacy routes, initial setup and bulk. Enabling the switch
does not bypass product-type `allow_variants`, effective options or permissions.
The existing `variants_mode` and `variants_default` policies remain independent;
new REQUIRED/default-enabled variant policies cannot be authored while the live
company switch is false. Historical pinned rules are not rewritten.

## Bulk/import

The native registry accepts resource `simple_product` with CREATE, UPDATE and AUTO
selection. It uses the same product schemas/mutation logic, with one code/name.
Code matching uses Item.sku; creation results and dependent `$ref` IDs use Item.id.
Shared custom fields retain their own namespace. Existing product_family/item
operations and legacy templates remain available for compatibility.

Product import templates default to `simple_product` when the company switch is
false, and the existing family/item resources when true. The adapter prepares
authoring/revision evidence, so spreadsheets do not need to supply those bookkeeping
columns. Reviewed jobs pin authoring mode and native dependency versions; stale
work fails instead of silently changing meaning. Existing chunk/atomicity, rollback,
worker authority and completed-command replay rules remain in force.

## Stock and opening boundaries

The product-mode flag does not grant or disable inventory, batch, serial, expiry,
warehouse/bin, unit, barcode, price or tax capabilities. Existing type/profile,
Identity capability, permissions and operational policies still determine behavior.
All downstream sources continue receiving the same item_id.

Opening remains an Accounting/Vouchers operation. Simple mode selects the product;
advanced mode selects the SKU. Both resolve to item_id. Existing COMBINED/LINKED_GL
opening modes, books-begin date, warehouse/lot/serial inputs, remaining GL-value
claims, duplicate checks, reconciliation and reversals remain authoritative. A
low-level Catalog product save never posts stock or stores an opening quantity/value.
The ready-on-Save creation coordinator invokes the native Accounting/Vouchers
operations and retains their receipt references; physical stock remains with its owner.

## Decision log

2026-11-04: Simple creation captures configured serial identifiers inline, at
product or batch level, and derives opening quantity from physical unit rows.
One Save registers identities and completes native opening posting/finalization;
serials introduce no additional pricing dimension. See the serial contract above.

2026-10-28: user authorized all API phases before UI, with a maintained TODO and two
final reviews. Use an additive product facade, live company singleton and explicit
legacy compatibility seed. Preserve the internal family/item and stock identities.
The later UI must prioritize familiar labels, one clear creation flow and the shared
style/CSS/layout system for business and ordinary users.

2026-10-29 review corrections: basic product detail reads remain available through
the existing native detail view when authoring settings cannot be read; create/edit
selection still requires verified settings. Product PATCH validates both members'
field policies and scoped references before claim/index persistence can flush them.
Invalid revision errors identify `revision`, preserving 422 for invalid actor/owner
tokens while enabling explicit edit recovery. Directory read failures, no matches
and an empty catalogue have distinct states. See [review evidence](product-master-review-fixes.md).

2026-10-28 UI delivery: the console selects the authoring experience from the live
company setting. Simple mode has one Products destination and one identity form;
advanced mode retains family/SKU authoring. Product edits and shared setup use
the guarded product facade, while operational item IDs stay unchanged. See the
[UI delivery checklist and verification record](simple-product-ui-todo.md).

2026-10-29 tracking navigation: simple and advanced product-list kebabs and the
product view's Inventory menu share verified tracking applicability. Active product
actions use the activated inventory profile and enabled company batch/serial
features. Applicable actions open the existing product-filtered management screens,
retaining the originating product or list context. Missing permission/configuration
never grants an action; inaccessible product filters cannot become unfiltered reads.
See [implementation and verification](product-tracking-navigation.md).
