# Inventory template endpoint registry

These eleven C6.06 operations use the existing Catalog master and history command pipelines.
Current Identity authority and company scope are required. Every write uses Idempotency-Key;
updates, lifecycle commands and publication also require expected_version. Read-denies protect
response fields, search, filters and sorting. See [profile contracts](catalog-profiles-api.md).

| Method and path | Permission | Request body | Query fields |
|---|---|---|---|
| GET `/v1/companies/{company_id}/inventory-templates` | inventory_profile_template.read | - | limit, cursor, q, sort, custom_filters, is_active, code |
| POST `/v1/companies/{company_id}/inventory-templates` | inventory_profile_template.manage | InventoryTemplateCreate | - |
| GET `/v1/companies/{company_id}/inventory-templates/{object_id}` | inventory_profile_template.read | - | - |
| PATCH `/v1/companies/{company_id}/inventory-templates/{object_id}` | inventory_profile_template.manage | InventoryTemplateUpdate | - |
| POST `/v1/companies/{company_id}/inventory-templates/{object_id}/activate` | inventory_profile_template.manage | ExpectedVersion | - |
| POST `/v1/companies/{company_id}/inventory-templates/{object_id}/deactivate` | inventory_profile_template.manage | ExpectedVersion | - |
| GET `/v1/companies/{company_id}/inventory-templates/{template_id}/revisions` | inventory_profile_template.read | - | limit, cursor, q, sort, published, lot_tracking, serial_tracking, expiry_required, identifier_profile_id, issue_strategy, valuation_method |
| POST `/v1/companies/{company_id}/inventory-templates/{template_id}/revisions` | inventory_profile_template.manage | InventoryRevisionInput | - |
| GET `/v1/companies/{company_id}/inventory-templates/{template_id}/revisions/{object_id}` | inventory_profile_template.read | - | - |
| PATCH `/v1/companies/{company_id}/inventory-templates/{template_id}/revisions/{object_id}` | inventory_profile_template.manage | InventoryRevisionUpdate | - |
| POST `/v1/companies/{company_id}/inventory-templates/{template_id}/revisions/{object_id}/publish` | inventory_profile_template.publish | ExpectedVersion | - |

Master pages support indexed code/name prefixes. Revision pages reject text search and allow
revision/id sorting, published state and the listed typed inventory filters. Both use signed
keyset cursors with default 50 and maximum 200 rows; detail-only fields stay out of list payloads.
The inherited master custom_filters parameter cannot enable custom fields on this native entity.
Options use the existing company option-source endpoint with catalog.inventory_templates.

Draft PATCH merges only supplied fields. Optional identifier and day constraints may be cleared;
flags and strategies cannot be null. Publication validates all promoted fields and dependencies,
then freezes the entire revision. Later changes create another revision. Publication authors a
Catalog definition; actual product adoption, stock operations and consumer acknowledgement
remain separate capabilities. C6.06 is still incomplete.

Decision 2026-09-12: reuse typed master/history mechanisms and real scoped identifier FKs;
reject physical quantities, values, devices and stock-posting fields in these requests.
