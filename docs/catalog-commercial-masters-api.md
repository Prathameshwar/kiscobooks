# Commercial masters implementation package (C6.02)

This package follows the source, classification, custom-index and service-wiring
increments. It adds Catalog API/database workflows only. The existing task ledger
remains authoritative; C6.02 is verified and checked in that ledger.

## Delivery sequence

1. Extend the existing master command/list machinery, field descriptors and option
   registry to brands, series, manufacturers and sites. Reuse company policy locks,
   changed-field enforcement, custom validation/indexes, current-authority receipts,
   audit/outbox and signed lean lists. Do not create a second generic CRUD framework.
2. Materialize brand, brand_series, manufacturer and manufacturer_site, with one
   reviewed DDL/model pair each. Add native relationship and lifecycle checks,
   company/tenant FKs, migrations, factories and generated contracts together.
3. Add dated brand_manufacturer relations with explicit production roles, protected
   history and serialized overlap checks. Brand ownership is an independent optional
   party reference and is never inferred from a manufacturing relation.
4. Add product_type and immutable product_type_revision. First revisions carry typed
   supported kind, inventory/tracking modes and unit-dimension requirements. Attribute
   and reusable profile references acquire their actual FKs in C6.03/C6.06; an absent
   reference capability cannot be represented as a publishable placeholder UUID.
5. Review the full API workflows, isolation, protected filters/options, nested-reference
   mismatch, hierarchy moves, retirement, replay and source drift. Run migrations,
   relevant suites, strict typing/lint, coverage and client generation before sign-off.

## Resource contracts

| Resource | Important rules |
|---|---|
| Brand | Company-unique code/name, optional parent brand and owner-party reference, descriptive custom fields. Same-company acyclic hierarchy, maximum eight levels; reparent is a versioned action. No tax inheritance through brands. |
| Brand series | Stable code/name under one brand; unique brand/code. Brand identity is immutable after creation. Inactive brands reject new series. |
| Manufacturer | Company-unique code/name, optional verified party reference and descriptive custom fields. This identifies a producer; it owns no supplier account, balance or tax registrations. |
| Manufacturer site | Stable code/name under one manufacturer; country and optional state use shared ISO references and must agree. Parent identity is immutable. No copied party legal-address master. |
| Brand manufacturer | Same-company brand/manufacturer, native role OEM/CONTRACT_MANUFACTURER/ASSEMBLER, inclusive valid_from/valid_to. No overlapping interval for the same pair/role. An open interval may be closed once; a closed boundary is immutable and its history remains readable. |
| Product type | Company-unique code/name and GOODS/SERVICE/BOTH kind, descriptive custom fields, active lifecycle. The first revision freezes the type code/kind so draft and published requirements retain their meaning. |
| Product type revision | Versioned draft then immutable publication. Closed typed requirements, explicit allowed unit dimensions and inventory/tracking modes; service-only requirements reject physical tracking. Publication pins requirements rather than editing existing products. |

Optional party references remain unavailable until the real party projection contract
is delivered in C5.02. Null means no relationship has been assigned; accepting a non-null
reference requires current owner evidence. Catalog never creates the party as a side effect.
Manufacturer/site/brand relationships on future families and physical receipt lots remain
their respective C7 and Billing integration work.

Every master provides create/detail/update/list/lifecycle and the applicable usage or
relationship actions. Require idempotency keys and expected versions for changes. Lists
default to 50/max 200, use signed keyset cursors, code/name prefix search, typed parent/
kind/activity filters and native id/code/name sorts. Denied fields cannot be used for
querying or option lookup. Child lists retain their parent identity; no unbounded nesting.
The rule for dependent active masters is refusal until an explicit reassignment/closure;
historical relationships remain addressable.

Custom-enabled additions are brand, manufacturer and product_type, as already adopted
in the Catalog schema. Series, sites and relationship rows use native fields. A searchable
field uses the reviewed generation preparation workflow; unique-field adoption remains
gated until its separate complete-coverage implementation exists.

Decision 2026-09-12: deliver commercial masters through the existing Catalog machinery,
with native product-type requirements and real incremental FK integration. Source absence
gates optional party relationships and dependent publication, not ordinary master creation.


Storage decision 2026-09-12: inventory_modes, tracking_modes and unit_dimensions are
small closed enum sets in the typed product-type revision document. They are normalized,
bounded JSON arrays, interpreted only by the native requirement validator and pinned at
publication. They are not arbitrary configuration dictionaries, custom fields, SQL search
dimensions or executable predicates. Identity, kind, revision, lifecycle, booleans and
foreign references remain native typed columns. Attribute/profile bindings will use real
same-company foreign keys when C6.03/C6.06 introduce their owners.

Current commercial route groups: /brands, /brand-series, /manufacturers,
/manufacturer-sites, /brand-manufacturers and /product-types, beneath the standard
/v1/companies/{company_id}. Type revisions are nested beneath their type; the membership
field must be readable for nested reads, writes and replay. Revisions have create/get/list,
update while draft, and publish; production relations have create/get/list and close.


Deployment uses the existing idempotent Identity role seed to add commercial permission
keys. No user assignments are created. Global shared-role seed changes require the existing
per-company source bootstrap procedure; they must not be represented as tenant events
that were never emitted. Source and broker propagation still need live release verification.

The concrete method/path, body and permission matrix is in [commercial routes](catalog-commercial-routes.md).
