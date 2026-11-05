# Attribute master UI and API

Delivery plan (25 October 2026), authorized by the requested end-to-end implementation:

1. Reuse the native definition, option, set, revision and membership contracts. Add typed authoring metadata and a closed Console proxy policy. Preserve the existing product attribute assignment workflow.
2. Add company-scoped directories, create/edit/detail pages and lifecycle actions for definitions, options and sets. Reuse shared controls, CSS, notices, navigation and command recovery.
3. Add set revision history, bounded draft membership with searchable definitions, ordering/requiredness/variant eligibility, and explicit immutable publication. Protect complete replacement against missing field access.
4. Test native API/metadata contracts, UI success/failure/access/validation/navigation, review in a browser, verify the schema and generated client, and fix review findings.

Storage already contains these five native tables. Sets/templates are reusable identities with numbered immutable published revisions; they are not product assignments. Maximum draft size is 128 definitions. Integer and decimal option values remain exact strings in the browser and on the wire.

## Implemented contracts

- `/masters/attribute-definitions`, `/masters/attribute-options`, `/masters/attribute-sets`:
  signed-page directories, code/name search, authorized filters, detail/create/edit pages,
  separate versioned lifecycle commands, scoped action menus and bounded internal return
  navigation. All navigation uses explicit current tenant/company grants.
- Definition forms expose the five native value types, optional numeric measurement
  dimension and variant eligibility. Option forms resolve a same-company definition,
  render only its typed value, and select compatible measurement units. Integer/decimal
  values stay exact strings; false, zero and unset remain distinct. Changed-field edits
  retain protected values and references. Native dependency/semantic locks remain in force.
- `/masters/attribute-sets/{set_id}/revisions/new` and `.../{revision_id}` author and
  review membership. Drafts allow zero to 128 distinct definitions, explicit requiredness,
  eligible variant axes and ordered display. PUT is a complete bounded replacement; the
  UI requires complete readable membership and writable replacement fields before editing.
  Published revisions are immutable, and publication is a separate confirmed action.
- Catalog field-set metadata now includes typed attribute controls. `operation=publish`
  is restricted to template revision/member metadata and resolves `attribute_set.publish`
  rather than `attribute_set.manage`. Field policy still applies; metadata grants no authority.
- A closed Console proxy policy admits only native method/path/query combinations for these
  masters and revisions. Existing item/family assignment paths are preserved. The older
  product attribute page now also checks explicit tenant/company grants.
- No ORM, migration, seed or schema change. Existing native commands retain tenant/company
  boundaries, optimistic versions, idempotency, audit and dependency guards. Catalog OpenAPI
  and the generated Catalog client are synchronized; SDK version is 0.2.21.

## Review decisions

Reused shared CSS/layout, searchable reference controls, native selects, exact-value fields,
tables/pagers, menus, notices, dialogs, draft navigation guards and command recovery. No new
CSS, runtime dependency, alternate persistence or business expression was added.

Unconfirmed saves freeze values and retain their exact body/idempotency key. Conflicts retain
the draft until a confirmed reload. Field validation focuses the first invalid control.
Canonically equivalent native numeric edits may return an unchanged optimistic version;
these valid no-op receipts are accepted. Optional measurement dimensions can be cleared.
Reference errors and general errors remain visible when a protected input cannot be rendered.
Add/remove/reorder controls explicitly use `type=button`; they never submit membership.
Publication receipts must identify the same company, set and revision and confirm publication.

Review also corrected duplicate-create recovery without discarding entered values, resolved
definition/unit labels on detail pages, and named each row action menu for its readable label.
Directory menus, detail actions and editor access use the same field rules, including access
limited to an option's typed value or measurement unit. Native dimension metadata includes
all seven supported dimensions; the regression fixture is captured from that native contract.

## Verification

Native API regression: **41 passed**, with a subsequent **9 passed** metadata regression
after correcting dimension choices. Final focused Console regression: **111 passed**.
The complete Console suite passed **2,127 tests across 150 files**, with no failures.
Catalog lint, strict typing, OpenAPI freshness, generated SDK freshness/types and all **8**
SDK transport tests passed. No schema changes were necessary: the read-only local audit
confirmed migration/model/database head `0191`, all **164** model tables and no Alembic drift.

Browser review uses actual Console components, providers and shared CSS with intercepted
API fixtures; it does not create local business records. Native authenticated contracts are
covered by the API tests; local readiness and unauthenticated proxy rejection were also
checked. Final browser review passed **128 checks** at 1440px and 390px in light, dark and
ledger themes, including master authoring/lifecycle, template membership/publication,
permission restrictions, validation focus, dirty navigation and exact uncertain-save retries.
The production build passed and managed Console returned to `UP` on port 4320.

All four delivery phases and the manual code/security review are complete. Review findings
were fixed and covered by focused regressions before the final complete suite and build.
