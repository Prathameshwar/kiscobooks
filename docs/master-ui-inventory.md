# Core master UI inventory

Reviewed 2026-10-25 against console routes/components, Catalog and Accounting OpenAPI,
the native model registries, and their governing master contracts.

There are **2 core business masters without a complete management UI** in this inventory.
This counts independently meaningful master categories, not every database table. Revisions,
assignments, aliases, child contact/address/profile records, transaction documents, reports,
imports, and policy/configuration workflows are excluded. It is not a count of all planned
modules or all remaining application work.

| Area | Count | Pending master UIs |
|---|---:|---|
| Accounting | 2 | Exchange rates, charge policies |
| **Total pending** | **2** | |

Existing core master screens cover tenants/workspaces, companies, departments, users,
user groups, roles; countries, states, currencies, languages and timezones; units,
manufacturers, item groups, unit conversions, pack types, identifier types, identifier
namespaces and identifier profiles; attribute definitions, options and sets/templates;
sales channels, price levels and price plans;
inventory/tracking, warranty, return and handling profiles with native draft/revision publication;
Products/SKUs, product families, product types, category schemes, categories, brands,
brand series and manufacturer sites with native authoring, reviewed transitions and readiness;
warehouses, warehouse groups and bins/racks; company financial years; and native account
heads, account groups, ledger accounts, parties/customer/supplier management, commercial
types, payment terms and withholding sections/rates. Fixed account heads correctly have
read-only pages. Tax categories, classifications, rules and rates now have native
management screens under `/tax`. Permissions,
company configuration, warehouse settings and the new product configuration workflow are
separate administration/configuration screens.

Important qualifications:

- The older `Customers` screen still uses a stand-in book/search source. Native customer
  management is now provided by `/accounting/parties` with its CUSTOMER role filter;
  `/accounting/suppliers` uses the shared party identity and active SUPPLIER role. Related
  registrations, contacts, beneficiaries and policies are linked from native party details.
- Dedicated `/masters/attribute-definitions`, `/masters/attribute-options` and
  `/masters/attribute-sets` pages manage the reusable attribute masters. Sets include draft
  membership and immutable revision publication. `/products/attributes` retains product
  attribute/variant assignment and its inline definition/option editor.
- Product configuration offers existing published profile/type references. Those pickers do
  not replace the corresponding master creation/publication screens.
- The dynamic `/masters/[resource]/[[...record]]` route supports units, manufacturers,
  item groups, warehouses, warehouse groups, bins/racks and the five units/identifier
  resources, the three attribute resources, the three pricing resources, the four reusable
  product profile resources and all eight products/classification resources listed above. Other resources still require
  their own implementation.
- Conversions correctly remain create/read only; profile requirements are authored
  during creation and remain immutable. Type/namespace codes and type classification
  are stable, with native versioned name/lifecycle commands and reference guards.

Sources: [Catalog inventory](catalog-table-inventory.md), [Catalog schema](catalog-schema.md),
[commercial masters](catalog-commercial-masters-api.md),
[Accounting master contract](accounting-master-contract.md), and
[product configuration delivery](product-configuration-ui-api.md), and
[account/party/supplier delivery](account-party-supplier-ui-api.md), and
[tax master delivery](tax-master-ui-api.md), and
[warehouse structure delivery](warehouse-structure-ui-api.md), and
[units and identifiers delivery](units-identifiers-ui-api.md), and
[attribute master delivery](attribute-master-ui-api.md), and
[pricing master delivery](pricing-master-ui-api.md), and
[product profile delivery](product-profile-ui-api.md), and
[products and classification delivery](product-classification-ui-api.md).
