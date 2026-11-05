# Product tax and price note removal

Decision, 2026-10-30: the user requested permanent removal of the product creation
"Tax and price source / reason" field from the UI, API and database.

The field feeds `catalog_tax_binding.source_reference`,
`item_price_draft.source_reference` and `item_price.source_reference`.
Remove it from both simple and family/SKU creation, native tax assignments,
price authoring/publication, and bulk price adjustments. Official tax definition
evidence, regulatory evidence, estimate/MRP/guard evidence, exemption reasons,
configuration source versions and immutable audit events have separate purposes.

## Delivery sequence and todo

- [x] Record the failing UI regression for creation without the note; add strict retired-input rejection checks.
- [x] Remove UI state, validation and permission metadata dependencies; update native API schemas and commands.
- [x] Remove the three model columns with three successive single-DDL migrations; verify upgrade and rollback on the dedicated disposable MySQL server.
- [x] Regenerate Catalog OpenAPI/client, update governing docs and reusable test fixtures.
- [x] Fix the remaining coordinated binding input and registered-model exports found by the wider review; preserve verified customer membership in pricing test fixtures.
- [x] Run relevant backend/UI suites, type checks, migration checks and manual simplify/security review; record a CSV result.
- [x] Back up the three affected local tables and apply native Catalog 0211-0213; inspect the resulting columns using the application account.
- [ ] Verify the authenticated running UI when the VM/services are available.

The column migrations delete stored free-text notes. A downgrade can recreate
the column shape but cannot restore deleted text; recovery needs a pre-upgrade
backup. Existing rows retain their IDs, amounts, tax selections and dates.
An old API release still requires non-empty notes when reconstructing price
definitions. Restore the backed-up text before reverting that API; schema
downgrade alone cannot provide full old-release recovery.
Application startup does not run DDL: deployment uses the existing Catalog
Alembic workflow, with API/UI restart after migrating.
