# Identifier master and profile endpoint registry

## Stable identifier types and namespaces

The console uses native Catalog management contracts for `identifier-types` and
`identifier-namespaces` under `/v1/companies/{company_id}`. Each supports GET/POST
collection, GET/PATCH detail and POST `/{object_id}/activate` / `deactivate`.
Reads require `identifier_type.read` or `identifier_namespace.read`; commands
require the corresponding `.manage` permission. Commands require Idempotency-Key,
and update/lifecycle bodies require expected_version. Audit/outbox and versions
commit atomically; replay rechecks current authority and field access.

| Resource | Create fields | Editable fields | List filters | Search / sorts |
|---|---|---|---|---|
| identifier-types | code (30), name (100), strict boolean is_barcode | name | code, is_active, is_barcode | Indexed code prefix / id, code and their descending forms |
| identifier-namespaces | code (40), name (120) | name | code, is_active | Indexed code prefix / id, code and their descending forms |

New records start active. Input is closed, labels must be printable, and codes use
uppercase letters/digits/dots/hyphens/underscores. Stable codes are already referenced
by native barcode records; changing a code or barcode classification is forbidden.
Referenced definitions cannot be retired, including references retained in history.
Deactivation preserves identity and audit history. No hard deletion is available.
Lists use lean protected projections, signed keyset cursors, limit 50/default and
200/maximum, and reject duplicate/unknown query fields and unindexed name sorting.
Denied fields are also forbidden in search, filters and sorting.

Decision 2026-10-25: expose the existing native identifier tables with versioned
descriptive/lifecycle commands, retain stable code/classification semantics and
existing indexed code queries, and add protected metadata/UI without changing DDL.
See [units and identifiers delivery](units-identifiers-ui-api.md).

## Identifier profiles

These seven C6.06 operations are present in the generated Catalog OpenAPI. They require
current Identity authority and company scope. Writes require Idempotency-Key; updates and
lifecycle commands require expected_version. Requirements are authored atomically with
creation and cannot be edited later. Read-denies also protect filters, search and sorting.
See [profile contracts](catalog-profiles-api.md).

| Method and path | Permission | Request body | Query fields |
|---|---|---|---|
| GET `/v1/companies/{company_id}/identifier-profiles` | identifier_profile.read | - | limit, cursor, q, sort, custom_filters, is_active, code |
| POST `/v1/companies/{company_id}/identifier-profiles` | identifier_profile.manage | IdentifierProfileCreate | - |
| GET `/v1/companies/{company_id}/identifier-profiles/{object_id}` | identifier_profile.read | - | - |
| PATCH `/v1/companies/{company_id}/identifier-profiles/{object_id}` | identifier_profile.manage | IdentifierProfileUpdate | - |
| POST `/v1/companies/{company_id}/identifier-profiles/{object_id}/activate` | identifier_profile.manage | ExpectedVersion | - |
| POST `/v1/companies/{company_id}/identifier-profiles/{object_id}/deactivate` | identifier_profile.manage | ExpectedVersion | - |
| GET `/v1/companies/{company_id}/identifier-profiles/{profile_id}/requirements` | identifier_profile.read | - | limit, cursor, q, sort, identifier_type, namespace_rule |

Header search uses indexed code/name prefixes. Child requirements reject q and accept
only the documented typed filters and stable sorts. The inherited custom_filters parameter
cannot enable unsupported custom fields on these native-only entities. Page size defaults
to 50 and is capped at 200; cursors bind company, actor authority, resource and query.
Physical identifier values, child edits and consumer activation are outside these operations.

Decision 2026-09-12: freeze the implemented identifier operation contracts separately from
pending inventory, warranty, returns and handling APIs. C6.06 remains open.
