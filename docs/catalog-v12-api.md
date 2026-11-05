# Catalog product configuration and authoring

Implementation: 2026-09-12; Company-only configuration: 2026-10-30. These APIs provide native configuration, complete draft
product/service definitions, explicit variants and configuration adoption. See the
[pricing API](catalog-v13-api.md) and [tax/activation API](catalog-v14-api.md) for related
workflows; these APIs never create physical inventory.

## Configuration

All paths below are relative to `/v1/companies/{company_id}`.

| Routes | Contract |
|---|---|
| POST `/product-configurations/company` | Company-bound draft input without `scope_id` or owner selectors; atomically creates/reuses the company scope |
| POST/GET `/product-configuration-scopes`, GET `/{id}` | Company-only creation/listing; historical non-company IDs remain read-only and protected |
| POST `/product-configurations`, GET/PATCH `/{id}` | Compatibility draft creation for a verified Company scope; PATCH requires `expected_version`; retired scope writes rejected |
| GET `/product-configurations/{id}/preview`, POST `/{id}/publish` | Company-only review/publication; validate native restrictions and references; publish checks draft, company generation and Identity source versions |
| GET `/product-configuration-scopes/{id}/drafts` and `/revisions` | Lean signed pages; revision `effective_on` filters publication start dates |
| GET `/product-configuration-revisions/{id}` | Immutable dated publication and protected native children |
| GET `/product-configuration/effective`, `/catalog-defaults`, `/item-groups/{id}/defaults` | Dated effective defaults, restrictions, sources and per-setting applicability/locks |
| GET `/product-configuration/authoring-defaults` | Authorized type, exact quantity and price suggestions with source-version acceptance |

The four permissions are `product_configuration.read`, `.manage`, `.publish` and `.adopt`.
Underlying product, type, group, unit and profile read permissions and field policies still
apply. Listing scopes does not expose owners that the actor cannot read. Company admins
receive the write permissions; existing business readers receive configuration read access.

Current/proposed defaults use Company revisions with native type/unit baselines and hard
constraints. Company profile choices override optional type defaults; contradictory native
restrictions fail. Internal historical pin reads preserve the original retired hierarchy.

Adoption previews include `resolution_version=2`; it is bound into signed review
evidence and new native adoption records. Clients must verify it and cannot
select it in the commit body. Adoption history exposes the protected marker;
version 1 rows preserve their original ordering and version 2 pins preserve the
reviewed Company VALUE/CLEAR choices. Unsupported versions or retired sources
in version 2 pins fail closed. Company publication previews validate the native
constraints of configured default goods/service types. Catalog migration 0214
must precede API deployment; reverting its column requires an online check and
is refused after a version 2 adoption exists.
Scope list filters accept only `scope_kind=COMPANY`; owner filters are removed.
Configuration option sources are published product-type, attribute-set, inventory-template,
warranty, return-policy and handling revisions, identifier profiles, currencies and adoption
target items. Unrevisioned type/group/family ownership option sources are removed.
Existing family/SKU queries still derive the primary group at
`as_of`; an explicitly inconsistent group/type/family is rejected. Candidate queries omit
family/SKU identity and may select a proposed group/type or exact published type revision.

Nested PATCH updates only supplied fields. Omitting `options`, `profiles` or `pricing` siblings
preserves them. Changing an option away from OPTIONAL clears its omitted default; changing a
profile away from VALUE clears its omitted ID. Explicit incompatible pairs fail validation.
INHERIT resumes ancestry; profile CLEAR removes a default. `numeric_defaults` is an explicit
replacement collection, bounded by the seven dimensions; an empty list resumes inheritance.

Shared COMPANY and BOTH scopes may contain goods defaults. Manufacturer, measured units,
physical profiles and MRP are inapplicable to service resolution; an explicit incompatible
SERVICE-scope choice is rejected. Profile references require native read permissions and field
access. Company capabilities remain authoritative, including additional sale levels.

Effective `settings` identify each field's origins, applicability, overrideability and hard
restriction reason. These explain configuration constraints; write authority still comes from
the existing field-set and field-policy mechanism. Preview `comparisons` contain before/after
values and changed fields for each applicable kind. If the existing configuration conflicts,
`before` is null and `before_conflicts` explains it; a valid replacement can still be previewed
and published. Protected reads still fail closed. Invalid drafts return the standard error
envelope. Publication preserves earlier revisions and pins; it describes future defaults and
does not imply existing-product adoption or Billing enforcement. Pricing requirements refer
to the implemented [pricing APIs](catalog-v13-api.md).

### Authoring defaults and explicit acceptance

`GET /product-configuration/authoring-defaults` takes `as_of`, `kind` and optional type revision,
group, family/SKU, unit, SKU unit revision and currency. Existing SKUs resolve adopted pins;
candidates resolve current dated defaults. With `include_price=false`, quantity suggestions do
not require price-currency access. Missing selections are reported in `missing`.

Quantity suggestions intersect configured and native unit grids exactly: increments 0.20 and
0.25 produce 1.0000. Narrowing appears in `adjustments`. Price suggestions carry independent
precision, increment, currency and positive exact basis. A currency mismatch or incompatible
basis fails validation; values are never silently rounded or converted.

To accept a suggestion, copy its native fields and returned `acceptance` object into the
command's `accept_defaults` field:

- Family creation checks the selected `product_type_revision_id`.
- Unit-binding creation and numeric revision check `quantity_decimal_places`, `quantity_increment` and
  `fractional_entry` for the selected unit and `valid_from`.
- Price-numeric creation checks precision/increment for the SKU, unit revision, currency and
  `valid_from`. Copy the suggested basis explicitly when authoring the separate price history.

Acceptance includes the business date, policy generation, Identity source version and optional
candidate group. Commands re-resolve under their normal authorization and transaction locks,
reject stale acceptance or mismatched supplied values, and retain native audit/idempotency.
A suggested candidate group is context only; create its dated family assignment explicitly.
Requests without `accept_defaults` retain normal explicit authoring. No default publication
rewrites saved unit rules, numeric revisions, price amounts or existing adoption pins.

## Product authoring

Existing family/default-SKU create, descriptive PATCH and root browse APIs remain documented
in [the product API](catalog-products-api.md). Kind, selected type and base-unit identity remain
immutable through those PATCH routes.

| Routes | Contract |
|---|---|
| POST `/product-families/{id}/groups` | Dated primary group; forward revisions close the preceding interval |
| POST `/product-families/{id}/category-preview` | Review a complete category set under current authority and configuration |
| PUT `/product-families/{id}/categories` | Draft replacement or reviewed, future-dated active-family replacement; scheme and primary constraints |
| POST `/product-families/{id}/manufacturers` | Dated goods-only manufacturer/site/role assignment; reject overlaps |
| PUT `/product-families/{id}/attributes` | Native declarations and permitted options; default-SKU replacement checks both family and SKU versions |
| POST `/product-families/{id}/variants` | Explicit SKU and one option per axis; canonical combination uniqueness |
| PUT `/items/{id}/attributes` | Replace native typed values while preserving variant identity constraints |
| POST `/items/{id}/unit-bindings`, `/unit-revisions` | SKU base, sale/purchase/pack or measured definitions; immutable dated numeric revisions |
| POST `/items/{id}/barcodes`, `/barcode-state` | Exact product/pack identifiers, GTIN checksum and explicit activation/deactivation; identities remain reserved |
| POST `/items/{id}/quantity-preview` | Read-only fixed/compound/measured conversion using effective SKU base precision and increment |
| GET `/items/{id}/requirements`, `/configuration` | Definition readiness and effective/pinned configuration; actual eligibility comes from activation preview |
| GET `/items/{id}/configuration-adoption/preview`, POST `/configuration-adoption` | Signed expiring draft-SKU preview and checked explicit adoption |

Assignments, family options, SKU values, unit bindings, barcodes and adoptions have GET list
and detail routes beneath their owner. Revision lists/details are under
`/item-unit-bindings/{id}/revisions`; adoption sources are under
`/product-configuration-adoptions/{id}/sources`. OpenAPI is the exact request/response contract.

All commands require an idempotency key and the aggregate's expected version. Family commands
use the family version; SKU commands use the item version. Family attribute commands that
supply default-SKU values or declare axes also require `expected_default_item_version`.
Missing child versions return 422; stale versions return 409 without changing either record.
The response returns `item_id` and `item_version`, including declaration-only saves that leave
the SKU unchanged. Omitted/empty default values on a non-axis declaration leave existing SKU
values unchanged; clear them explicitly through `PUT /items/{id}/attributes`.
Variant creation additionally
requires `item.create`; adoption requires configuration adoption authority. Commands check
current Identity facts and field authority, take the company lock, and commit changes,
version increments, audit events and receipts together. Replay rechecks current authority.

Child lists use signed keyset pages (50 default, 200 maximum), ID sorting and lean projections.
Dated child resources support `as_of`. Unsupported filters/search fail instead of being
ignored. Scalar attribute contents are available only through protected detail reads.
Family declarations are bounded at 128 attributes, eight axes, and 128 options per attribute;
aggregate option validation is bounded at 1,024. A nonempty permitted-option list is closed
for both axis and non-axis attributes: scalar input cannot bypass it. Tightening a list rejects
existing scalar/out-of-list SKU values; clear or correct those values before changing the list.
SKU unit authoring is bounded at 64 bindings.
Compound entry is bounded at 32 components. Limits are enforced when adding definitions.
Readiness checks probe current dated definitions and active barcodes; retained historical
revisions do not consume these bounds. No Cartesian-product variant generation occurs.

Fixed conversions use exact positive rational factors and must fit the SKU base grid.
Numerator/denominator are decimal integer strings on the wire; existing integer requests
remain accepted with the same idempotency identity. XLSX requires text ratio cells.
Where both units share a canonical root, the SKU ratio must match the declared conversion;
undeclared container ratios remain product-specific. New canonical declarations also check
closed product revision history. Inconsistent legacy definitions fail closed in consumers.
Measured conversion requires distinct entered/base units without a shared canonical relation,
and an explicit actual base quantity; a nominal ratio never
substitutes for a measurement. Base revisions validate every overlapping current/future fixed
alternate revision; alternate revisions likewise validate every overlapping base revision.
This check is bounded at 1,024 affected revisions, excluding already expired history.
Minimum-sale edits must fit every current/future SKU base grid as well as the unit master.
Serial-tracked products require whole-count base rules in every scheduled interval.
Authoring rejects fractional serial base revisions; activation reports
`integer_serial_base_quantity` for invalid existing schedules. Quantity and pricing resolution
also reject invalid effective serial base rules.
Compound DISABLED rejects multi-component input; ordinary single-component pack input and
readiness remain valid. No preview mutates a balance or rounds an incompatible quantity.

## Adoption and history

A preview binds actor, company, SKU, family/item versions, configuration sources, Identity
source version and company policy generation. It expires after 15 minutes. Missing required
definitions, protected dependencies and stale tokens reject commit. Successful adoption pins
the exact source revisions. Later publication leaves those pins unchanged; a new preview and
explicit commit are needed to adopt new defaults. Group reassignment that changes a pinned
structure requires re-adoption. Standalone adoption requires a DRAFT family and SKU. An active
SKU preview returns `eligible=false` and `active_structural_adoption_unsupported`; an active
family also blocks standalone draft adoption. Bulk configuration adoption uses the same
preparation and commit handlers. No active structural migration is implied. Group reparenting rejects moves affecting an ACTIVE
SKU through a current/future family assignment, including descendants in the dated hierarchy.
The conservative dependency check retains historical pins until a migration workflow exists.

Activation is implemented through the separate [activation API](catalog-v14-api.md), which can
activate a draft SKU in an already active family. Its internal adoption preview is scoped to
`purpose=ACTIVATION` and requires activation authority. Effective configuration reports
`activation_supported=true`; the retained, deprecated `activation_available` means service
support only, not per-SKU eligibility.

Referenced masters cannot change identity, type, unit semantics or lifecycle underneath these
definitions. Descriptive names remain editable. Audit entries contain changed field names
and actor/entity references, without copies of product values or preview tokens.

## Storage and shared contract

Migrations 0064-0082 added 19 reversible single-CREATE revisions, taking Catalog to 80 tables at V1.2.
They comprise seven configuration tables and twelve product definition/adoption tables.
Models, schemas, field metadata, factories, tenant tests and the generated TypeScript client
ship together. Shared permission catalogue version is 0.18.0, synchronized across all six
consuming lockfiles. The Catalog publisher declares 172 exact audit routes.

## Related implemented APIs

See [pricing](catalog-v13-api.md), [tax and activation](catalog-v14-api.md), and
[bulk commands](catalog-v15-api.md). Customer/supplier facts, physical stock execution and
Billing-side enforcement retain their documented external boundaries. The 2026-09-13
corrections reuse existing storage and permissions; they add no migration or UI screen.

## Decision log

- 2026-09-12: Delivered essential V1.2 configuration and product definitions together under
  the authorized execution plan. Per-SKU adoption uses a protected signed preview; generalized
  bulk adoption remains V1.5. Price purpose requirements are configuration only until V1.3.

- 2026-09-13: Corrected nested PATCH and dated group resolution; added protected per-setting
  explanations, publication differences and explicit default acceptance. Shared goods-only
  defaults no longer block services. Draft/active adoption and separate activation support are
  explicit; immutable histories and pins are preserved.

Decision 2026-09-13 (product integrity): aggregate attribute saves check the default-SKU version;
closed option lists apply to scalars too. Unit/minimum validation covers future intervals in
both directions. Compound readiness distinguishes available bindings from entered components.
Active-product group moves are blocked until explicit adoption migration is available.


### Category maintenance extension - 14 September 2026

Category replacement remains editable for DRAFT families. ACTIVE families now have the narrow
reviewed, strictly future-dated category maintenance path documented in the
[classification API](catalog-classification-api.md#scheme-governance-and-dated-membership---14-september-2026).
Other structural draft-only guards remain. `FamilyCategory` history includes `valid_from` and
`valid_to`, and category lists accept `as_of`. Each scheme's native requiredness is evaluated
by requirements and activation; the global `category_mode` continues to apply alongside it.
