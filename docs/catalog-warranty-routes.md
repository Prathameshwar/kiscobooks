# Warranty policy endpoint registry

These eleven C6.06 operations reuse Catalog master and revision commands. Current Identity
authority, company scope and field policies apply to every request. Writes require
Idempotency-Key; updates, lifecycle changes and publication require expected_version.

| Method and path | Permission | Request body | Query fields |
|---|---|---|---|
| GET `/v1/companies/{company_id}/warranty-policies` | warranty_policy.read | - | limit, cursor, q, sort, custom_filters, is_active, code |
| POST `/v1/companies/{company_id}/warranty-policies` | warranty_policy.manage | WarrantyPolicyCreate | - |
| GET `/v1/companies/{company_id}/warranty-policies/{object_id}` | warranty_policy.read | - | - |
| PATCH `/v1/companies/{company_id}/warranty-policies/{object_id}` | warranty_policy.manage | WarrantyPolicyUpdate | - |
| POST `/v1/companies/{company_id}/warranty-policies/{object_id}/activate` | warranty_policy.manage | ExpectedVersion | - |
| POST `/v1/companies/{company_id}/warranty-policies/{object_id}/deactivate` | warranty_policy.manage | ExpectedVersion | - |
| GET `/v1/companies/{company_id}/warranty-policies/{policy_id}/revisions` | warranty_policy.read | - | limit, cursor, q, sort, published, duration_unit, start_trigger |
| POST `/v1/companies/{company_id}/warranty-policies/{policy_id}/revisions` | warranty_policy.manage | WarrantyRevisionInput | - |
| GET `/v1/companies/{company_id}/warranty-policies/{policy_id}/revisions/{object_id}` | warranty_policy.read | - | - |
| PATCH `/v1/companies/{company_id}/warranty-policies/{policy_id}/revisions/{object_id}` | warranty_policy.manage | WarrantyRevisionUpdate | - |
| POST `/v1/companies/{company_id}/warranty-policies/{policy_id}/revisions/{object_id}/publish` | warranty_policy.publish | ExpectedVersion | - |

Master pages support indexed code/name prefix search, active/code filters and stable code/name/id
sorting. Revision history supports published, duration_unit and start_trigger filters with
revision/id sorting; text search is rejected. Both use signed keyset cursors (50 default, 200
maximum). Read-denies also prohibit filtering or sorting by the denied field. Revision list
payloads omit coverage_description. Options register catalog.warranty_policies.

Duration remains an integer plus DAYS (1..36500), MONTHS (1..1200) or YEARS (1..100). Calendar
units are preserved; no implicit conversion to days occurs. Start triggers are SALE, DELIVERY
or INSTALLATION. Optional readable coverage text is bounded to 2000 characters and never
drives calculations. Draft PATCH validates the merged result, distinguishes omitted values
from an explicit null description, and rejects clearing required terms. Publication validates
all material fields and freezes the revision. Stable master codes cannot change once a revision
references them. Claims, trigger evidence and service execution remain with their owners.

Decision 2026-09-12: reuse the existing scoped revision pipeline and native domain rules; the
profile itself is a definition, without an implied operational consumer acknowledgement.
