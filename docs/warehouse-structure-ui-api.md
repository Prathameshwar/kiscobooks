# Warehouse structure UI and API delivery

Scope: warehouse groups and warehouse bins/racks, using the existing console layout,
CSS, forms, searchable selects, tables and native Catalog commands. Groups organize
locations; membership confers no access or stockholding capability. Bins remain attached
to their original warehouse. Dates preserve parent and primary-group history.

## Phases

1. Verify native contracts; add protected form hints, read-only company business-date
   context and primary-group history reads where needed. Test and synchronize OpenAPI/client.
2. Implement linked directories, create/edit/detail, lifecycle actions, dated hierarchy
   and warehouse membership. Preserve filters/back navigation and unconfirmed save recovery.
3. Test the UI/API and production build. Review permissions, history, validation,
   navigation and shared styles; fix findings and record verification here.

## Implementation

- `/masters/warehouse-groups`: searchable, filtered, cursor-paged directory; create,
  edit and detail screens; kebab actions for activation, deactivation and parent changes.
- `/masters/warehouse-bins`: bins/racks directory with warehouse filtering and matching
  create, edit, detail and lifecycle screens. Warehouse identity is immutable after create.
- `/masters/warehouse-groups/{id}/reparent`: review and confirm a dated parent change.
  Parent history, direct children and descendant warehouse membership are available on
  group details, with a business-date selector for composition.
- `/masters/warehouses/{id}/group`: primary-group history and reviewed dated membership
  changes, including removal of an open membership. Existing warehouse detail screens link
  here and to their filtered bins directory.
- Existing shell, navigation, cards, form layout, table, kebab, searchable select, notices,
  date formatting and confirmation styles are reused. No new CSS or dependencies.

Native commands retain company/tenant scope, expected-version/generation checks, field
authorization, idempotency, audit/outbox behavior and dependency/cycle fences. New API
reads provide a protected company business-date context and lean signed-cursor primary-group
history. Dated history listing is shared with the existing parent-history implementation.
Native field metadata supplies labels, input types and reference sources for all four
structure entities. Initial group creation uses manage permission; subsequent parent moves
require the separate move permission. OpenAPI and API client `0.2.19` are synchronized.

## Access

| Action | Company-scoped permissions |
|---|---|
| Read groups / parent history / child groups | `warehouse_group.read` |
| Read group warehouse members / warehouse membership history | `warehouse_group.read` and `warehouse.read` |
| Create/edit/activate/deactivate a group | `warehouse_group.read` and `warehouse_group.manage` |
| Change a group's parent | `warehouse_group.read` and `warehouse_group.move` |
| Change warehouse primary membership | Both read permissions plus `warehouse.manage` and `warehouse_group.manage` |
| Read bins/racks | `warehouse_bin.read` |
| Maintain bins/racks | `warehouse_bin.read` and `warehouse_bin.manage`; creating a bin also needs warehouse read access for selection |

Read-denied fields are omitted from display and filters. Conditional field authority is
not treated as unconditional write permission. Read-only users can browse permitted
directories/history; actions and links require their relevant permission for the open company.

## Review and fixes

The final review covers CLAUDE.md sections 5 and 6. `/simplify` and `/security-review` are
not available as commands in this environment; equivalent code, permission and invariant
reviews are performed manually. Warehouse structure does not post money or move stock.
Existing audited commands are reused, and no database models or DDL are changed.

Regression checks caught and fixed:

1. Missing native form hints, protected business-date context and membership-history read.
2. The proxy initially omitted parent/assignment metadata from its closed namespace.
3. Initial record loading could overwrite a user's first edit; forms now wait for draft initialization.
4. Bin label edits unnecessarily required warehouse read access; this applies to warehouse selection on create.
5. Detail/edit/caller return links lost filtered directory state; bounded, local return
   chains now preserve it, including when directory filters are cleared.
6. Dated-change review did not identify its target; the review now names and links the selected group.
7. Native effective-date errors were not mapped to the displayed control; date errors now
   appear beside the input, and command errors without editable controls remain visible.
8. Browser focus could run before a rejected change's controls unlocked; focus now follows
   the committed error/form state. Desktop and mobile browser regression checks pass.

Unconfirmed writes freeze their inputs and retain the exact body and idempotency key.
Conflicts require reload/review confirmation; validation failures retain the draft and
focus the affected field. Back navigation and company switching guard unsaved work.

## Verification

- API suites: 73 passing HTTP/integration checks, covering the new reads, native grouping,
  bins, warehouse policies/storage/operations and the shared classification reads (`not mysql`).
- Full console regression: 1,903 passing checks across 142 files. After the final review
  fixes, 169 affected checks pass across six files, including both new masters and existing warehouse/master workflows.
- Production console build, TypeScript, API-client generation/type checks, all eight
  API-client transport tests, Ruff and strict mypy pass.
- Read-only live schema check: Catalog model tables (164), database and migration head `0191` align; no pending DDL.
- All 86 Edge browser checks pass at 1440px and 390px in light, dark and ledger themes.
  They use actual console components and shared production styles through an isolated
  fixture API; live warehouse records are not changed.
- Managed Catalog was refreshed and is ready. Live OpenAPI contains both new reads;
  unauthenticated API/proxy checks preserve protection. All eleven local infrastructure/API
  components report UP. The console uses development mode and loads UI changes automatically.

No outstanding implementation, correctness or permission findings remain in the reviewed
scope. The reusable warehouse masters reduce this inventory's pending core master UIs from
27 to 25. Evidence is retained locally under `.tools/warehouse-structure-review/` and
the warehouse API/console regression logs; the temporary browser preview is stopped after review.
