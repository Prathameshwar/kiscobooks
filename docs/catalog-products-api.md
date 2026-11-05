# Catalog draft products and services

Status (2026-09-12): draft family/SKU authoring is extended by native configuration, variants,
classification, unit revisions and explicit adoption. See [V1.2 API](catalog-v12-api.md) and its
verification record. Activation remains gated on V1.3 pricing and V1.4 GST.

## Delivered API

All routes are beneath `/v1/companies/{company_id}` and use existing `item` permissions.

| Route | Behavior | Permission |
|---|---|---|
| POST `/product-families` | Atomically create a DRAFT goods/service family and one default SKU | item.create and item.read |
| GET `/product-families` | Lean company-owned family page | item.read |
| GET `/product-families/{id}` | Field-protected family detail | item.read |
| PATCH `/product-families/{id}` | Edit allowed descriptive draft fields with expected_version | item.update and item.read |
| GET `/items` | Lean SKU page, including family and operation filters | item.read |
| GET `/items/{id}` | Field-protected SKU detail | item.read |
| PATCH `/items/{id}` | Edit draft SKU labels, sale/purchase flags, minimum sale quantity and custom values | item.update and item.read |

Create takes code/name, GOODS or SERVICE, a published product-type revision, optional
brand/series/model/description/custom values and a `default_item` containing SKU/name/base-unit,
sale/purchase flags, optional minimum sale quantity and descriptive custom values. It returns
`family` and `default_item` together. No partially created family survives a failed child write.
No implicit unit/type/master is created. No status, opening stock, on-hand or physical lot field
is accepted by these commands. Kind, type and base unit cannot be changed through draft PATCH.

Lists use the existing signed keyset envelope: default 50, maximum 200, stable ID tie-breaker,
code/SKU/name or ID sorting in either direction, indexed code/SKU/name prefix search and
allowlisted filters. Native read-denies also block search/filter/sort. Detail-only description,
custom JSON and minimum quantity are omitted from lean lists. Custom filters reuse the existing
protected index/rebuild mechanism; a missing ready index never becomes an unfiltered query.
The item list also accepts `base_unit_id`, alongside `family_id`, `status`, `sellable` and
`purchasable`; status/SKU and base-unit/SKU pages have dedicated composite indexes.

## Database and validation

| Table | Purpose |
|---|---|
| product_family | Company-owned descriptive product identity, goods/service kind, explicit simple/variant structure, published type reference and optional brand/series |
| item | Company-owned SKU, family and base-unit identity, default-SKU marker, sale/purchase flags, minimum sale quantity and descriptive custom values |

Migrations 0062/0063 are one CREATE each, with matching ORM, same-company composite foreign
keys, unique company/code and company/SKU constraints, one default slot per family and native
lifecycle/quantity checks. This initial slice reached 61 tables through 0063; the reviewed V1.2 schema now has 80 tables/head0082. The initial command
creates SIMPLE families. Native family attribute authoring declares variant axes and a default
combination; the explicit variants command creates additional SKUs. See
[catalog-attributes-api.md](catalog-attributes-api.md) for current authoring and lifecycle rules.

Type kind and allowed unit dimension must match. Minimum sale quantity is a positive exact
Decimal on the unit's precision/increment grid. A service uses its permitted service units;
physical stock is not recorded. Type revisions must be published and their masters active.
Selected brand/series and base unit require current owner/read authority, with field checks
before reference validation. References stay in the same company and tenant.

Referenced unit code/dimension/precision/increment/activity cannot change. Unit and product
mutations share the company policy lock to prevent check/write races. Referenced brand/series
and product type retirement is rejected. Monetary and inventory-requiredness checks belong to
final activation, not an assertion that a draft is ready to invoice.

Every mutation uses current authority, idempotency, optimistic version checks and transactional
auditing. Family and SKU have separate field/custom contexts. Conditional write policies see
the resulting version. A denied child, stale version or duplicate SKU rolls back the aggregate,
custom claims/indexes, policy generation, audit events and receipt. Replay rechecks current field
write policy; responses use current read policy. No hard-delete endpoint exists.

## Verification

Review reproduced and fixed quantity-grid errors returning HTTP 500, referenced unit semantic
changes, conditional permissions evaluating the old version, referenced master retirement and
product custom-index rebuild eligibility. Regression scenarios cover these findings plus goods/
service creation, draft edits/no-ops/stale versions, paging/search/filtering, duplicate rollback,
child write denies, retained-receipt authorization and tenant/company database constraints.

Native MySQL 9.6 verification has passed both goods/service workflows, all 61-table schema
comparison, upgrade/downgrade/re-upgrade, mapping uniqueness/replay races and 2,000-alias paging.
A local 2,000-draft-SKU fixture paged in ten 200-row pages with no duplicates or omissions;
observed page times were 105.863-178.769 ms. This measures local draft listing, not bulk import
or complete price/tax history workload. The combined regression passed 450 distinct tests with one Docker-only skip and 99.77% overall coverage (100% domain). Generated OpenAPI adds seven operations across four paths; existing paths/schemas
remain semantically unchanged. Client generation, type checking and two transport tests pass.

Decision log: 2026-09-12 ? delivered draft product authoring before optional framework expansion
under the user-approved expedited plan. Reused existing item permissions and common mechanisms;
no new shared-library version, source API, stock ownership or UI is introduced by this increment.

Review follow-up (2026-09-12): reproduced a product PATCH foreign-reference ordering gap
(409 from FK flush instead of the scoped 403). Separated validation from persistence so
current field authorization and reference checks complete before claims/indexes can flush
the changed row. Native MySQL confirms the corrected cross-company response and rollback.

## V1.4 activation

Reviewed activation and immutable profile/source history are available; see [the tax and activation contract](catalog-v14-api.md). Activation availability is a supported-capability flag; SKU eligibility comes from its signed preview.
## Simple product facade - 2026-10-28

The additive [simple product API](simple-product-api.md) supports one public identity
and atomic aggregate editing. Existing family/item routes remain supported. The
company authoring switch defaults to simple for new companies and gates variants
independently of inventory profiles and ordinary attributes. See the rollout seed
and API completion evidence linked from that document.
