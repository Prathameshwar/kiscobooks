# API CRUD & List Conventions

**Status:** Agreed platform rule; required for every API
**Date:** 2026-09-03
**Scope:** Backend services, generated clients, web and mobile consumers
**Related:** [tech-stack.md](tech-stack.md) · [field-permissions.md](field-permissions.md) · [custom-fields.md](custom-fields.md)

This document defines one predictable contract for CRUD and list endpoints. Services own domain policy and resource-specific query definitions; `libs/platform` owns the common mechanism.

---

## 1. Route shape and CRUD

Resource routes use plural nouns and explicit API versions:

```text
POST   /v1/resources              create
GET    /v1/resources/{id}         detail
PATCH  /v1/resources/{id}         partial update
GET    /v1/resources              list
```

- Create returns `201`, the detail response, and `Location`.
- Detail and update use distinct Pydantic response/request schemas with `extra="forbid"`.
- PATCH validates the changed-field set against current state; payload presence alone is not a change.
- Every route declares a permission and enforces tenant plus object-level scope.
- `DELETE` exists only where deletion is genuinely allowed. Deactivation, cancellation, approval, posting and other lifecycle transitions use explicit domain actions; they are not disguised as deletion or arbitrary status PATCHes.
- Hard deletion is forbidden for anything referenced by posted or audit-relevant data.
- Bulk mutation is a separate bounded operation with an item cap. Work beyond that cap is asynchronous.
- All errors use the shared error envelope. Unknown query/body fields return `422`; they are never silently ignored.

---

## 2. Standard list request

Every list endpoint supports the common parameters that apply to it:

```text
GET /v1/resources
    ?limit=50
    &cursor=<opaque>
    &q=<search text>
    &sort=-created_at,name
    &status=active
```

`limit`, `cursor`, `q` and `sort` are reserved common names. Filters are resource-specific, typed query parameters such as `status`, `channel`, `created_from` and `created_to`; there is no arbitrary field/operator query language.

### 2.1 Pagination

- Keyset/cursor pagination is the default for every growing table.
- Default `limit` is 50; maximum is 200. An endpoint may set a lower maximum, never a higher one without a documented performance review.
- Fetch `limit + 1` rows to derive `has_more`; return only `limit`.
- The cursor is opaque, versioned and HMAC-signed. It contains the resource key, normalized sort specification, last sort values, direction and a hash of filters/search/scope.
- Reusing a cursor with changed filters, search, sort, tenant or resource returns `422`.
- A malformed, expired, unknown-version or bad-signature cursor returns `422`, never `500`.
- Every sort has a unique deterministic tie-breaker; append `id` automatically when absent.
- Offset/page-number pagination is allowed only for a demonstrably bounded reference list. The endpoint must document its maximum cardinality. Deep offset on transactional tables is forbidden.
- Exact `total` is not returned by default. `include_total=true` is endpoint-specific and permitted only when the filtered count is demonstrably cheap and required by the product. The count must name a filtered entity column, for example `count(Resource.id)`, so the tenant filter can attach.

### 2.2 Filtering

- Each resource declares a typed filter model and an allowlist mapping public parameter names to SQLAlchemy columns and allowed operators.
- Standard operators are exact equality, bounded `in`, boolean, and date/number `gte`/`lte`. Prefix and range filters are endpoint-specific.
- Unknown filters or unsupported values return `422`.
- `in` lists are capped at 100 values; repeated/combined filters are capped to prevent query-amplification attacks.
- Filtering values are always bound parameters. A client value is never interpolated into SQL or treated as a column name.
- A filter must be backed by an appropriate index at expected scale. Adding a public filter means reviewing the model, migration and query plan together.
- Custom fields may be filtered only when `is_searchable=true`, through `custom_field_value_index`.
- A field denied for read cannot be exposed indirectly through filtering.

### 2.3 Search

- `q` searches a resource-specific, code-defined field set. It never means “search every string column.”
- Search input is trimmed and normalized; maximum length is 200 characters. Endpoint-specific minimum lengths prevent broad scans.
- Exact identifiers and codes use equality; names commonly use indexed prefix search.
- Unanchored `LIKE '%term%'` is forbidden on growing tables. Natural-language contains search requires a reviewed MariaDB `FULLTEXT` index or a separately approved search system.
- Search never includes encrypted values, BLOB/TEXT payloads, secrets, tax identifiers, or fields the actor cannot read.
- Searchable custom fields follow [custom-fields.md](custom-fields.md) §7; raw MariaDB JSON is not scanned.

### 2.4 Sorting

- `sort` is a comma-separated allowlisted list. `name` is ascending and `-name` descending.
- At most three client-selected sort fields are accepted; the server adds `id` as the final tie-breaker.
- Public sort names map to SQLAlchemy column objects in code. Raw client strings never enter `ORDER BY`.
- Sort fields must be indexable and supported by the endpoint's query plan. Sorting on BLOB, JSON, unindexed computed expressions or remote data is forbidden.
- Null ordering is defined per field and encoded into the cursor; it is never left to a database/client default.
- A field denied for read cannot be used for sorting because relative ordering leaks its value.

---

## 3. Standard list response

```json
{
  "items": [
    {
      "id": "019...",
      "name": "Example",
      "status": "active",
      "created_at": "2026-09-03T12:00:00Z"
    }
  ],
  "page": {
    "limit": 50,
    "has_more": true,
    "next_cursor": "v1..."
  }
}
```

- `items` uses a dedicated `<Resource>ListItem` schema, never the detail schema or an ORM object.
- List items contain only identifiers and fields needed to identify, compare and act on rows in that list.
- Large text, JSON, encrypted content, attachments, child collections, audit history and provider payloads are detail-only.
- There is no generic client-controlled `fields` parameter. It complicates authorization, generated clients, caching and query planning. A specialized projection gets a named endpoint or named response schema.
- Read-denied fields are absent from list items, exports, filters, search and sorting.
- Money values, when relevant, include currency and use the shared formatter contract; dates remain ISO in the API.

---

## 4. Query and index rules

Every list query is designed from its access path, not assembled as unrestricted ORM convenience:

1. Start with session-level tenant filtering and object-scope criteria.
2. Select explicit list columns; do not load the full entity.
3. Apply only typed/allowlisted filters and search.
4. Apply stable allowlisted ordering plus `id`.
5. Apply keyset predicate from the verified cursor.
6. Fetch `limit + 1`.

- No N+1 queries. Small to-one display data may use a deliberate join; to-many summaries use a reviewed aggregate or batch query.
- List queries never deserialize unused JSON/BLOB/TEXT columns.
- Composite indexes normally begin with `tenant_id`, then equality filters, then range/sort columns, ending in `id` where it supports the cursor.
- A foreign-key-supporting index may lead with its FK as documented in the database plan; tenant isolation still comes from the session filter.
- New production-scale list paths include MariaDB `EXPLAIN` evidence in review. `type=ALL`, filesort, or temporary tables on a growing table require an explicit justification and measured bound.
- Query timeouts and page caps are defence in depth; they do not excuse an unindexed query.
- Cache only after authorization and tenant scoping. Cache keys include tenant, actor scope, normalized filters, search, sort and cursor.

Example access index for a tenant-scoped delivery list filtered by status and sorted newest-first:

```sql
KEY ix_notification_delivery_tenant_status_created_id
    (tenant_id, status, created_at, id)
```

---

## 5. Shared mechanism versus service policy

`libs/platform` owns:

- Generic `Page[T]` and `PageMeta` response schemas
- Limit validation and `limit + 1` page construction
- Versioned HMAC cursor encoding, decoding, expiry and key rotation
- Canonical filter/search/sort fingerprinting
- Safe sort-direction and null-order helpers over code-provided column maps
- Common query-validation errors and OpenAPI parameter descriptions
- Reusable test fixtures for cursor tampering, boundaries and stable ordering

Each service owns:

- Its `<Resource>ListItem` schema
- Typed filter model and allowed operators
- Searchable and sortable field allowlists
- Default ordering and null policy
- Permission/object-scope rules
- SQLAlchemy statement and supporting MariaDB indexes
- Whether an exact total is cheap and justified

The shared library must never import a service model or decide domain-visible fields.

---

## 6. Mandatory tests per list endpoint

- Empty, one-row, exact-limit and `limit + 1` pages
- First and subsequent cursor pages with no duplicates or omissions under stable data
- Stable ordering when primary sort values tie
- Invalid limit, unknown filter, unsupported sort and malformed/tampered/mismatched cursor return `422`
- Search normalization, minimum/maximum length and escaped special characters
- Every supported filter and sort direction
- Unauthenticated `401`, unpermitted `403`, and wrong-company scope `403` where an object scope is supplied
- Two-tenant isolation with identical filter/search values
- Read-denied fields absent from items and rejected as filter/search/sort inputs
- Fixed query-count assertion to catch N+1 regressions
- MariaDB integration test for the real indexed path; SQLite is insufficient for collation, FULLTEXT and optimizer behaviour
- Detail-only large/sensitive columns proven absent from the generated SELECT

## 7. Decisions recorded

- 2026-09-11: billing-platform 0.4.0 adds the lean multi-sort list executor, explicit null ordering, typed filter/search helpers, and version 2 cursors. New cursors expire after 15 minutes by default (maximum 24 hours), accept at most four verification keys, and bind the current authority and normalized query. Old unexpiring version 1 tokens must restart pagination. Identity/Notification keep their existing service list adapters; migrating their full list behavior is separate work.

- Cursor pagination is the platform default; offset is the bounded-reference exception.
- Exact totals are opt-in, never an automatic tax on every request.
- Filters are typed resource parameters, not an arbitrary query DSL.
- Search and sort fields are code allowlists and must be index-supported.
- List responses use lean dedicated schemas; clients cannot request arbitrary columns.
- Shared mechanics live in `libs/platform`; visibility and query policy remain in the owning service.

## 8. Open questions

None for the common CRUD/list contract. Each endpoint still documents its resource-specific filters, search fields, sorts, default order and supporting indexes before implementation.
