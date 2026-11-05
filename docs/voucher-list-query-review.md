# Voucher list query review

The `GET /v1/companies/{company_id}/vouchers` list uses a lean projection of the
voucher header, its current revision, type, and optional number assignment. Historical
revisions cannot appear as separate rows. Every query is bounded by tenant and company;
the response has no unconditional total and reads at most `limit + 1` rows (default 50,
maximum 200).

| Capability | Contract and access path |
| --- | --- |
| Paging | HMAC-signed cursor bound to actor authority, resource, filters and sort; `id` or `(document_date, voucher_id)` keyset, in either direction. |
| Filters | Exact `status`, `type_id`, `type_revision_id`, `kind`, `party_id`, `item_id`, `issue_number`; inclusive `document_from`/`document_to`; existing indexed custom-header, assignment and counter filters. |
| Search | `q` resolves a voucher UUID by primary key or uses an escaped, anchored prefix on the issued display number. It does not scan narration, JSON, or child text. |
| Sort | `id`, `-id`, `document_date`, `-document_date`; ID is the unique date tie-breaker. Other resources retain their allowlisted ID sort. |
| Projection | ID, status, revision, type ID/code/kind, document date and issue number. Read-denied fields are omitted and cannot be used to filter, search, or sort. |

Custom-field filters require an indexed, searchable definition and match the
current revision ID. Assignment and counter filters also use current-revision
facts, so edits cannot leave a historical match visible in the list.

The primary voucher status list already has `(tenant_id, company_id, status, id)`.
Revisions now have `(tenant_id, company_id, document_date, voucher_id,
revision_number)` for date range and date keyset access. Voucher types use
`(tenant_id, company_id, type_id, id)`; issued-number search uses
`(tenant_id, company_id, display_number, revision_id)`. Party and item filters
use `(tenant_id, company_id, party_id/item_id, revision_id)`. The current revision and
number assignment joins use unique keys, so they do not multiply rows. Query values
are bound parameters; unsupported filters and sort modes return 422.

The type-revision filter has `(tenant_id, company_id, type_revision_id, voucher_id,
revision_number)`. Assignment and counter filters use `(tenant_id, company_id,
role, principal_id, revision_id)` and `(tenant_id, company_id, counter_id,
revision_id)` respectively. These indexes trade additional write cost for bounded
selective list access.

The query is validated by current-revision, ascending/descending cursor-tie,
filter, number-search, escaping, scope, and read-policy tests. A native MariaDB
`EXPLAIN` was unavailable in this workspace because no disposable Vouchers test
database is configured. Before activating this access path on a large dataset,
capture `EXPLAIN` for date-ordered, status-filtered, and number-prefix requests;
review any filesort or table scan against actual cardinality.
