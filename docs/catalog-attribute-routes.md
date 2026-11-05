# Native attribute endpoint registry

This registry describes the 24 implemented C6.03 operations in the generated Catalog OpenAPI.
Base prefix is retained in each row. All operations require current Identity authority and
company scope. All writes require Idempotency-Key; updates/publication/lifecycle changes also
require expected_version in the named request body. Every native changed field is checked,
and reads/filters/sorts respect current read-denies. See [contracts](catalog-attributes-api.md).

| Method and path | Permission | Request body | Query fields |
|---|---|---|---|
| GET `/v1/companies/{company_id}/attribute-definitions` | attribute_definition.read | - | limit, cursor, q, sort, custom_filters, is_active, code, value_type, measurement_dimension, is_variant_capable |
| POST `/v1/companies/{company_id}/attribute-definitions` | attribute_definition.manage | AttributeDefinitionCreate | - |
| GET `/v1/companies/{company_id}/attribute-definitions/{object_id}` | attribute_definition.read | - | - |
| PATCH `/v1/companies/{company_id}/attribute-definitions/{object_id}` | attribute_definition.manage | AttributeDefinitionUpdate | - |
| POST `/v1/companies/{company_id}/attribute-definitions/{object_id}/activate` | attribute_definition.manage | ExpectedVersion | - |
| POST `/v1/companies/{company_id}/attribute-definitions/{object_id}/deactivate` | attribute_definition.manage | ExpectedVersion | - |
| GET `/v1/companies/{company_id}/attribute-options` | attribute_option.read | - | limit, cursor, q, sort, custom_filters, is_active, code, definition_id, value_type |
| POST `/v1/companies/{company_id}/attribute-options` | attribute_option.manage | AttributeOptionCreate | - |
| GET `/v1/companies/{company_id}/attribute-options/{object_id}` | attribute_option.read | - | - |
| PATCH `/v1/companies/{company_id}/attribute-options/{object_id}` | attribute_option.manage | AttributeOptionUpdate | - |
| POST `/v1/companies/{company_id}/attribute-options/{object_id}/activate` | attribute_option.manage | ExpectedVersion | - |
| POST `/v1/companies/{company_id}/attribute-options/{object_id}/deactivate` | attribute_option.manage | ExpectedVersion | - |
| GET `/v1/companies/{company_id}/attribute-sets` | attribute_set.read | - | limit, cursor, q, sort, custom_filters, is_active, code |
| POST `/v1/companies/{company_id}/attribute-sets` | attribute_set.manage | AttributeSetCreate | - |
| GET `/v1/companies/{company_id}/attribute-sets/{attribute_set_id}/revisions` | attribute_set.read | - | limit, cursor, q, sort, published |
| POST `/v1/companies/{company_id}/attribute-sets/{attribute_set_id}/revisions` | attribute_set.manage | AttributeSetRevisionCreate | - |
| GET `/v1/companies/{company_id}/attribute-sets/{attribute_set_id}/revisions/{object_id}` | attribute_set.read | - | - |
| GET `/v1/companies/{company_id}/attribute-sets/{attribute_set_id}/revisions/{object_id}/members` | attribute_set.read | - | limit, cursor, q, sort, definition_id, is_required, allow_variant_axis |
| PUT `/v1/companies/{company_id}/attribute-sets/{attribute_set_id}/revisions/{object_id}/members` | attribute_set.manage | AttributeSetRevisionUpdate | - |
| POST `/v1/companies/{company_id}/attribute-sets/{attribute_set_id}/revisions/{object_id}/publish` | attribute_set.publish | ExpectedVersion | - |
| GET `/v1/companies/{company_id}/attribute-sets/{object_id}` | attribute_set.read | - | - |
| PATCH `/v1/companies/{company_id}/attribute-sets/{object_id}` | attribute_set.manage | AttributeSetUpdate | - |
| POST `/v1/companies/{company_id}/attribute-sets/{object_id}/activate` | attribute_set.manage | ExpectedVersion | - |
| POST `/v1/companies/{company_id}/attribute-sets/{object_id}/deactivate` | attribute_set.manage | ExpectedVersion | - |

No exact count, deep offset, arbitrary sorting or raw canonical-value field is exposed. Member
replacement is an aggregate command; there are no independently editable published member routes.
Registered option sources and entity field-set endpoints are shared existing Catalog APIs.


## Native product authoring integration

These operations complement the 24 master/template operations above.

| Method and path (company prefix `/v1/companies/{company_id}`) | Purpose | Permission |
|---|---|---|
| GET `/items/{object_id}/attribute-form` | Bounded declaration/option/value graph with labels and write capabilities; no query parameters | item.read plus current read authority for referenced resources |
| PUT `/items/{object_id}/attributes` | Replace DRAFT SKU values with exact typed selections | item.update and current dependency authority |
| PUT `/product-families/{object_id}/attributes` | Replace draft declarations/default values, or add allowed options to ACTIVE families | item.update and current dependency authority |
| POST `/product-families/{object_id}/variants` | Create one explicit DRAFT SKU in a DRAFT/ACTIVE variant family | item.create, item.update and current dependency authority |

All commands require Idempotency-Key and expected_version. Explicit default value replacement
also requires expected_default_item_version. Existing lean child list/detail routes remain
available; the form graph avoids a detail request for every displayed value or label.
