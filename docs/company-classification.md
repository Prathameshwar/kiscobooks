# Company business classification

Implemented in Identity. Classification is descriptive metadata and does not select tax
rules, grant permissions, or enable company capabilities.

## Model and defaults

| API field | Storage | Default / clearing |
|---|---|---|
| `business_category_code` | Nullable FK from `company` to `business_category.code` | Omitted on create or explicit null: unclassified |
| `business_roles` | `company_business_role` bindings to `business_role.code` | Omitted on create: `[]`; empty list clears all roles |
| `store_format_code` | Nullable FK from `company` to `store_format.code` | Omitted on create or explicit null: unspecified |

On PATCH, omitted fields are unchanged. Explicit null is rejected for `business_roles`;
use an empty list. Role arrays replace the selected set, reject duplicates, and are
returned in code order. At most 32 selections are accepted. These descriptive fields
remain editable after first posting, without changing any accounting or statutory rules.
Existing `industry_code` (NIC/NAICS) and `business_nature` remain independent and supported.
No migration guesses classifications from legacy values.

The reference tables are global, seeded, and have no CRUD API. Each has a natural-key
`code VARCHAR(32)`, `label VARCHAR(100)`, `sort_order SMALLINT`, and `is_active BOOL`.
They are intentional exceptions to tenant/id/audit mixins, like global ISO reference
catalogues. Deployment seeds manage them; tenant requests only read their active choices.

`company_business_role` has UUIDv7 `id`, `tenant_id`, `company_id`, and
`business_role_code`. A unique `(tenant_id, company_id, business_role_code)` prevents
duplicates. The composite foreign key to `company(tenant_id, id)` enforces parent/tenant
agreement, and the session tenant filter covers direct binding queries. Company mutations
manage the binding set and emit the existing company audit event in the same transaction;
bindings have no independent CRUD or lifecycle. Retained bindings retain their IDs.

## Shipped choices

| Business category code | Label |
|---|---|
| `general` | General |
| `mobile_electronics` | Mobile & Electronics |
| `pharmaceutical` | Pharmaceutical |
| `fmcg` | FMCG |
| `apparel` | Apparel |
| `other` | Other |

Business roles: `retailer`, `manufacturer`, `wholesaler`, `distributor`, `stockist`,
`online`, `store`. Store formats: `shop`, `mart`, `supermarket`, `online`, `other`.
A company may have multiple roles; store format is optional and does not imply a role.

Point of Sale is the separate `point_of_sale` capability, managed through the existing
company feature API. Its configuration is reversible, has no tax-system restriction,
and does not require inventory (services can also be sold at a counter). This change
adds capability configuration, not a checkout or payment implementation. Classifying a
company as Retailer or Mart does not automatically enable it.

## API

`GET /v1/company-classifications` returns `business_categories`, `business_roles`, and
`store_formats`, each containing `{code, label, sort_order}` for active reference rows,
ordered by `sort_order` then `code`. Requires authentication and any of `company.create`,
`company.read`, or `company.update`. These global choices contain no company data.
POST/PUT/PATCH/DELETE on the lookup route are not supported.

The classification portion of a `POST /v1/companies` or
`PATCH /v1/companies/{company_id}` body is:

```json
{
  "business_category_code": "pharmaceutical",
  "business_roles": ["distributor", "wholesaler"],
  "store_format_code": null
}
```

The create/get/update detail responses include all three fields. Company list responses
remain lean. The company field-set includes both scalar references and the role selection;
relationship form metadata is kept separately from scalar column metadata.
Unknown or inactive selections return 422. A previously selected inactive code remains
readable and can be retained unchanged or removed; it cannot be newly selected. All existing
company permissions, tenant filtering, and object-scope checks still apply.

To configure Point of Sale after creating the company:

```text
POST /v1/companies/{company_id}/features/point_of_sale/enable
POST /v1/companies/{company_id}/features/point_of_sale/disable
```

Catalog's existing minimal company snapshot does not use these descriptive fields, so its
company projection contract is unchanged. POS configuration uses the existing feature events.

## Deployment and verification

Platform installation runs Identity setup once the intended MySQL database exists and
`IDENTITY_DATABASE_URL` is configured. From the repository root on Windows:

```powershell
.\start\win\install-identity.ps1
```

If PowerShell script execution is disabled, or to run setup directly, use the Identity
Python environment (no execution-policy change is needed):

```powershell
.\apis\identity\.venv\Scripts\python.exe -m identity.install
```

Setup applies all Identity migrations (including classifications through `0042`), then
loads ISO reference values, system security roles, and all business classification choices.
Those defaults commit in one transaction; a seed failure rolls them all back. A failed
migration prevents seeding. MySQL schema changes commit per revision, so a retry resumes
migrations and repeats the idempotent seed. Rerun the same command when upgrading.

For an existing migrated database, classifications can also be refreshed independently:

```powershell
.\apis\identity\.venv\Scripts\python.exe -m seeds.business_classifications --dry-run
.\apis\identity\.venv\Scripts\python.exe -m seeds.business_classifications
```

The seed is repeatable: updates labels/order, activates shipped codes, and deactivates
withdrawn codes without deleting referenced rows. A dry run rolls back all changes.
Existing companies remain null/empty until classified. Unclassified creation continues
working even before the reference seed is applied.

Tests cover schemas, API create/read/update/clear, unchanged-role ordering, active reference
validation, seed reruns/withdrawal, tenant isolation, forbidden writes, DB foreign keys,
duplicate bindings, audit changes, feature configuration, and migration/model agreement.
The MySQL tests additionally upgrade a populated pre-change database, round-trip role bindings,
and downgrade without losing the original company. By default they use Docker; alternatively
set `IDENTITY_TEST_MYSQL_URL` to an **empty disposable MySQL 9.6 database**. Migration tests
upgrade/downgrade that database and must never target application data. An explicit
Alembic configuration URL takes precedence over an inherited application database URL.

## Decision log

- 2026-09-11: User requested category/role classification across API, DB and tests, then
  specified reference tables without CRUD. Implemented optional FK references, multiple
  tenant-scoped role bindings, seeded global choices, and separate POS configuration.

- 2026-09-11: Added Online and Store business roles and Online store format. Added the
  Identity installation command to migrate and load default catalogues automatically,
  with atomic seed transactions and safe reruns. Companies retain optional classifications;
  loading choices does not create a company or assign its role/category.

- 2026-09-11: [Company setup review](company-setup.md) documents country/currency selectors, pharmacy licence forms, validation and remaining client/Billing boundaries.
