# Catalog units and pack types

**Implemented increment:** API and database, with console management for units,
pack types and canonical conversions. Official unit-code mappings remain API-only.
No stock ledger is introduced by these screens. Unit and pack tables
remain revisions 0007-0010; Identity context adds Catalog revisions 0016-0027.
All operations require verified current Identity company, user and field-policy sources.

| Resource under /v1/companies/{company_id} | Operations | Permission |
|---|---|---|
| units | POST; GET list/detail; PATCH; POST /{id}/activate and /deactivate | unit.read for reads; unit.manage for commands |
| pack-types | POST; GET list/detail; PATCH; POST /{id}/activate and /deactivate | pack_type.read; pack_type.manage |
| units/convert | POST exact quantity preview (no mutation/idempotency key) | unit.read |
| unit-conversions | POST; GET list/detail | unit.read; unit.manage |
| unit-tax-codes | POST; GET list/detail; POST /{id}/close | unit.read; unit.manage |
| entities/{entity_type}/field-set | GET protected metadata | Corresponding read permission |

Commands require Idempotency-Key. Create returns 201 and Location. Unit/pack PATCH and
lifecycle commands require expected_version; stale versions return 409. PATCH compares actual
normalized changes, so unchanged denied fields do not block an otherwise permitted no-op.
Successful changes increment row_version and emit audit/outbox in the same transaction.
A retained key cannot be reused with another request. Replay checks current company/user/field
authority and renders current protected state; receipts contain IDs and changed-field names.

There are no hard-delete endpoints. Deactivation removes selectability but retains history.
A unit referenced by a conversion or official-code mapping cannot change code, dimension,
precision or increment, or be deactivated. Product bindings and direct base-unit references also
participate in the locked usage guard. Labels remain editable. Pack types have no physical
quantities or global conversion factors; item-specific packs belong to bindings.

The unit dependency guard checks every direct unit foreign key in Catalog's
trusted mapped schema, including compound parents/children, measured attribute
options, promotion limits and retained product/tax definitions. Checks are scoped
to both tenant and company and use existence queries; no dependent IDs or values
are exposed in conflict responses. Historical/inactive references still protect
the meaning of their units.

Unit/pack PATCH validates the merged saved and submitted settings. Inconsistent
quantity grids or invalid labels return 422 with safe field messages, retain the
saved version, and emit no success/audit mutation. Raw Pydantic inputs and protected
saved counterparts are never returned in the error response.

## Numeric and conversion rules

- Dimensions: COUNT, MASS, VOLUME, LENGTH, AREA, TIME and JOB; services can use TIME/JOB.
- Storage remains DECIMAL(19,4). Units declare 0-4 allowed decimal places and an exact positive
  increment representable at that scale. Wire decimals are strings; fractional JSON numbers
  are rejected. Company display precision does not narrow physical storage.
- Canonical ratios use positive signed-BIGINT numerator/denominator, stored reduced.
  Wire ratio parts are decimal-digit strings, preserving integers above JavaScript's safe-number range. Declare
  a root with a 1:1 self relation first. Every other same-company, same-dimension unit points
  directly to it. Chains, cycles, multiple roots for one source and cross-dimension relations reject.
- Relations are immutable. A replacement definition gets a new unit identity. Units are locked
  in stable ID order before relation creation so concurrent lifecycle changes cannot bypass checks.
- Composed conversions retain exact rational intermediates even when their reduced parts exceed
  stored BIGINT limits. Final quantities must fit DECIMAL(19,4) and the target grid; no rounding.
- [Product unit commands](catalog-v12-api.md) implement fixed packs, structured compound entry
  and measured dual quantities. Product ratio inputs and outputs use decimal integer strings;
  legacy integer requests remain accepted. XLSX ratio cells must contain text.
- Where both units share a declared canonical root, the product ratio must match it. Containers
  without that shared declaration retain SKU-specific ratios. Adding a global relation validates
  existing product revisions, including closed history, under the same company lock.
  The check allows at most 1,024 affected nonidentity revisions and rejects overflow.
- Measured entry requires distinct entered/base unit identities without a shared canonical
  relationship, and an explicit actual base
  quantity. Serial-tracked SKU base rules must remain whole-count across scheduled revisions.
  Authoring, activation, quantity and pricing consumers reject incompatible definitions.

Official unit codes are independent of unit names. The caller supplies jurisdiction and code;
this API does not infer a statutory code or adopt a tax jurisdiction. Inclusive DATE intervals
cannot overlap for company/unit/jurisdiction. Close requires expected_valid_to and may only
shorten the interval. A new mapping can start the following day; previous values stay addressable.

## Lists and field protection

| Resource | Filters | Search | Sort |
|---|---|---|---|
| units | code, dimension, is_active | Escaped code/name prefix | code, name, id; ascending/descending |
| pack-types | code, is_active | Escaped code/name prefix | code, name, id; ascending/descending |
| unit-conversions | from_unit_id, canonical_unit_id | Exact unit filters | id, -id |
| unit-tax-codes | unit_id, jurisdiction, valid_at | Escaped official_code prefix | id, -id |

POST units/convert validates readable, active, compatible units and their canonical relations,
then validates input precision/increment and exact target representability. It never rounds a
stock quantity. Identity conversion also checks the unit's own quantity rules.

Lists use limit 50 by default, maximum 200; signed expiring keyset cursors; id tie-breakers;
explicit lean columns; limit+1; and no unconditional total. Cursors bind company, tenant, actor,
source-policy version and normalized query. A source version change may require restarting paging.
Unknown/repeated query keys reject. Unsupported conversion text search rejects explicitly.
Read-denied fields are absent from output and cannot be used in filters, search or sorting.
Conditional read denies are conservative for lists/metadata; detail evaluates current row values.
Write conditions are checked before and after mutation. Native input requiredness remains intact
when response fields are omitted, and generated client output fields are optional accordingly.

## Verification and release limits

API tests cover complete lifecycle, same-key retry, changed-key collision, stale version,
no-op, duplicate code, reference checks, exact precision, date overlap/closure, tenant/company
scope, missing/stale sources and read/write-denied replay/query paths. A separate actual
Identity process supplies the source for Catalog metadata, unit create/retry/list and readiness.
MySQL concurrency/query plans and real RabbitMQ recovery remain C15 release gates.

## Decision log

- 2026-09-11: Delivered the existing unit/pack models as complete protected workflows, using
  shared idempotency, tenant access, list and audit mechanisms. Conversions are immutable;
  official-code closure uses an expected end date. Catalog does not create physical stock.
- 2026-09-13: Canonical declarations govern compatible SKU ratios in either command order;
  retained history cannot be reinterpreted. Product ratios and bulk preview ratios use exact
  strings. Serial scheduling and measured identity checks apply through quantity/pricing
  consumers. Intermediate rational arithmetic is independent of persisted BIGINT bounds.
- 2026-10-27: Extended semantic dependency protection to every mapped direct unit
  reference, including compound components and non-product definitions. Invalid
  merged unit/pack updates now return safe 422 field errors instead of 500. The
  product wizard derives exact compatible entry steps and rejects unavailable
  measurement fields; the conversion checker retains exact results alongside the
  company display format. See unit-conversion-review.md for regression/live evidence.
