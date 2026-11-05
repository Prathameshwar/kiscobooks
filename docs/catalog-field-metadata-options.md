# Catalog field metadata and registered options

The existing company/entity field-set API now returns effective custom definitions alongside
labels, requiredness, visibility, order, writability, help text, placeholder and display group.
Custom definitions include their exact type, validation, static choices, default, dynamic source,
dependency, visibility condition and sequence configuration. Field read-denies remove the entire
entry. Conditions that name unreadable fields are withheld and the entry becomes unwritable.

Tenant layout applies before company layout. Non-null company overrides win; null means inherit.
Custom layout defaults are resolved once and consumed by both metadata and write validation.
Native suggested_value is form guidance: native command schemas remain authoritative and no
financial or structural business default is rewritten by Identity layout. Layout grants no rights.

GET /v1/companies/{company}/option-sources/{source_key} uses the shared list contract: limit 50,
maximum 200, signed keyset cursor, 2-200 character escaped code/name prefix search, and id/code/name
sorting (optional minus prefix). Lean items contain value (UUID string), code and label. There is
no total count or custom JSON payload. Cursors bind source, company, actor, policy version and query.

| Registered source | Required read permission | Parent |
|---|---|---|
| catalog.units | unit.read | None |
| catalog.pack_types | pack_type.read | None |
| catalog.item_groups | item_group.read | None |
| catalog.category_schemes | category_scheme.read | None |
| catalog.item_categories | item_category.read and category_scheme.read | Required parent_id names an active scheme |

Only active options appear. Code, name and active-status fields must be readable. Category
selection also requires readable scheme_id and parent status. Unknown sources, unexpected query
keys, duplicate parameters, unregistered sorts, invalid parents and cursor reuse across parents
are rejected. No authored URL, arbitrary query, or external SQL is accepted as an option source.

A dynamic custom category field depends on another dynamic field backed by catalog.category_schemes.
Other registered sources take no parent. Invalid source/dependency configuration fails closed.
Writes query only bounded candidate UUIDs (at most the 128 definition limit), lock referenced
options through commit, and call the shared custom-value validator. Changing a parent revalidates
its child; explicitly clearing an optional child permits a new parent. An unchanged historical
value survives retirement of its option; a new or changed value cannot select a retired option.

Searchable custom-field writes remain unavailable until the separate index-generation/rebuild
workflow is ready (C5.03). Registered options do not silently enable that workflow, uniqueness
adoption, fiscal sequences, Product Configuration, product/price/tax masters or Billing sources.

Decision 2026-09-11: keep source registration and models in Catalog, reuse shared list/security
mechanisms and custom validation, and extend the closed registry as additional masters ship.
These API contracts contain no Catalog UI implementation.
