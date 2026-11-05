# Return policy endpoint registry

Twelve C6.06 operations reuse Catalog master/revision transactions and protected list helpers.
Every request uses current Identity authority and company scope. Writes require Idempotency-Key;
updates, lifecycle changes and publication require expected_version.

| Method and path | Permission | Request body | Query fields |
|---|---|---|---|
| GET `/v1/companies/{company_id}/return-policies` | return_policy.read | - | limit, cursor, q, sort, custom_filters, is_active, code |
| POST `/v1/companies/{company_id}/return-policies` | return_policy.manage | ReturnPolicyCreate | - |
| GET `/v1/companies/{company_id}/return-policies/{object_id}` | return_policy.read | - | - |
| PATCH `/v1/companies/{company_id}/return-policies/{object_id}` | return_policy.manage | ReturnPolicyUpdate | - |
| POST `/v1/companies/{company_id}/return-policies/{object_id}/activate` | return_policy.manage | ExpectedVersion | - |
| POST `/v1/companies/{company_id}/return-policies/{object_id}/deactivate` | return_policy.manage | ExpectedVersion | - |
| GET `/v1/companies/{company_id}/return-policies/{policy_id}/revisions` | return_policy.read | - | limit, cursor, q, sort, published, returns_allowed |
| POST `/v1/companies/{company_id}/return-policies/{policy_id}/revisions` | return_policy.manage | ReturnRevisionInput | - |
| GET `/v1/companies/{company_id}/return-policies/{policy_id}/revisions/{object_id}` | return_policy.read | - | - |
| PATCH `/v1/companies/{company_id}/return-policies/{policy_id}/revisions/{object_id}` | return_policy.manage | ReturnRevisionUpdate | - |
| GET `/v1/companies/{company_id}/return-policies/{policy_id}/revisions/{object_id}/conditions` | return_policy.read | - | limit, cursor, q, sort, condition_code |
| POST `/v1/companies/{company_id}/return-policies/{policy_id}/revisions/{object_id}/publish` | return_policy.publish | ExpectedVersion | - |

Master pages support code/name prefix search, is_active/code filters and stable code/name/id
sorting. Revision history supports published/returns_allowed filters and revision/id sorting.
Conditions use condition_code filters and condition_code/id sorting. Revision and condition
pages reject text search. All growing lists use signed keyset cursors (50 default, 200 maximum);
read-denied fields cannot be used to filter or sort. Options register catalog.return_policies.

New drafts default to returns forbidden, null window and no conditions. Enabled returns require
window_days 0..36500. Supported codes are ORIGINAL_PACKAGING, PROOF_OF_PURCHASE,
COMPLETE_ACCESSORIES, UNUSED and UNDAMAGED. A revision accepts at most five distinct codes;
they are native eligibility obligations, not executable refunds or stock dispositions.

PATCH merges only supplied fields and validates the complete result. Clearing an enabled policy
requires returns_allowed=false, window_days=null and condition_codes=[]. Null flags/condition
arrays are rejected. Reordering the same code set is a no-op; retained rows keep their IDs.
Published revisions are immutable. Master codes become immutable when a revision references them.

condition_count is server-maintained and database-bounded. Editing, publishing, child browsing
and receipt replay verify the stored set against it; incomplete restored data fails closed.
Condition writes and publication obey child field policies. Fresh commands use the shared
transaction-local before/after checks; retained receipts evaluate current policy conservatively
because draft conditions may have changed. Header, children, receipt and audit commit together.

Decision 2026-09-12: no return/refund or stock movement execution is introduced. Product-type
profile references are implemented and reviewed in C6.06. External consumer acknowledgement
and live release gates remain open. Policy/type reactivation also verifies that published native
conditions are complete; an incomplete restore cannot reactivate a weaker return definition.

Decision 2026-10-29: ordinary return-condition field metadata marks `revision_id`
readonly because the parent revision owns the aggregate. Publication metadata retains
its changed-field authority checks. No condition-reparenting endpoint is introduced.
