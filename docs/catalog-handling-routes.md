# Handling profile endpoint registry

These eleven C6.06 operations reuse Catalog master and revision commands. Current Identity
authority, company scope and field policies apply to every request. Writes require
Idempotency-Key; updates, lifecycle changes and publication require expected_version.

| Method and path | Permission | Request body | Query fields |
|---|---|---|---|
| GET `/v1/companies/{company_id}/handling-profiles` | handling_profile.read | - | limit, cursor, q, sort, custom_filters, is_active, code |
| POST `/v1/companies/{company_id}/handling-profiles` | handling_profile.manage | HandlingProfileCreate | - |
| GET `/v1/companies/{company_id}/handling-profiles/{object_id}` | handling_profile.read | - | - |
| PATCH `/v1/companies/{company_id}/handling-profiles/{object_id}` | handling_profile.manage | HandlingProfileUpdate | - |
| POST `/v1/companies/{company_id}/handling-profiles/{object_id}/activate` | handling_profile.manage | ExpectedVersion | - |
| POST `/v1/companies/{company_id}/handling-profiles/{object_id}/deactivate` | handling_profile.manage | ExpectedVersion | - |
| GET `/v1/companies/{company_id}/handling-profiles/{profile_id}/revisions` | handling_profile.read | - | limit, cursor, q, sort, published, fragile, keep_dry, keep_upright |
| POST `/v1/companies/{company_id}/handling-profiles/{profile_id}/revisions` | handling_profile.manage | HandlingRevisionInput | - |
| GET `/v1/companies/{company_id}/handling-profiles/{profile_id}/revisions/{object_id}` | handling_profile.read | - | - |
| PATCH `/v1/companies/{company_id}/handling-profiles/{profile_id}/revisions/{object_id}` | handling_profile.manage | HandlingRevisionUpdate | - |
| POST `/v1/companies/{company_id}/handling-profiles/{profile_id}/revisions/{object_id}/publish` | handling_profile.publish | ExpectedVersion | - |

Master pages support code/name prefix search, is_active/code filters and stable code/name/id
sorting. Revision history supports published/fragile/keep_dry/keep_upright filters and
revision/id sorting; it rejects text search. Signed keyset pages use limit 50 by default and
200 maximum. Read-denied fields cannot drive search, filters or sorts. Options register
catalog.handling_profiles.

Native temperature bounds use exact decimal strings, four-place storage and explicit CELSIUS
when either bound exists. Bounds cannot be below -273.15 or have minimum greater than maximum.
No bounds means a null unit. The three handling flags default false. Instructions are optional,
bounded to 2,000 characters, trimmed and excluded from lean history pages.

PATCH merges supplied fields before whole-definition validation. Explicit null clears bounds,
unit or instructions; flags cannot be null. Published revisions are immutable. Master codes
freeze once a revision exists. Current field authority, parent membership, scope and receipt
replay use the same command mechanisms as other native profiles.

Decision 2026-09-12: physical handling defaults bind only to goods-only product types. Catalog
stores requirements; monitoring, shipment enforcement and cold-chain compliance are external.
