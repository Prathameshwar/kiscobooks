> Superseded 2026-11-06: the user authorized [page-by-page product management restoration](product-management-ui-restoration.md). The retirement record below is historical; the restoration record tracks which pages have been implemented and verified.

# Product authoring UI removal

Decision 2026-11-04: remove the existing Simple and Product profile / SKU create,
edit, detail and creation-completion UI before designing a replacement. This is
UI-only work authorized by the user; no replacement authoring flow is introduced.

## Delivery phases

1. Retire product/family record routes and remove entry links while preserving
   both directories, import, reference selection and inventory workflows.
2. Delete product-only editors, detail/setup components, completion handoff,
   variant authoring and unused presentation assets. Keep the shared classification
   editor/detail functionality for brands, types, categories and manufacturers.
3. Update affected UI tests, verify routes/navigation and surviving screens, run
   Console TypeScript and review security/correctness boundaries.

Backend services, APIs, proxies, permissions, database records, migrations and
opening-stock execution remain unchanged. The product structure setting remains
available because it also determines directory/import behavior.

Earlier product creation, completion and detail delivery documents describe the
removed implementation and are historical evidence, not the current UI contract.
The replacement experience will be designed separately.

Scope addition 2026-11-04: also remove all batch and serial list, create, edit,
detail and history pages and their navigation. Existing tracking selections in
opening-stock/voucher entry and tracking APIs/data remain available.

## Delivery and validation

All removal phases are implemented. Product/family create, edit, detail and
completion URLs return not found. The attributes/variant-authoring route and all
batch/serial routes are removed. Both product directories remain usable without
record-editing actions; reference selection, imports, classification masters,
stock and opening-stock remain available. Stock summaries retain tracking
evidence without links to the deleted pages.

Deleted dedicated components, creation state/handoff helpers, navigation helpers,
styles and tests for the retired UI. Kept mixed test suites' surviving coverage
and added route/navigation removal regressions. Shared UI is version 0.1.60;
offline frozen-lockfile installation passed and every package export resolves.

Verification: 423 passing tests across 29 affected Console suites, combining the
latest results for each suite. Next route type generation and the final Console
TypeScript check passed. The initial
broader run found seven stale link/menu expectations; all were corrected and the
follow-up run passed all 150 tests. No tests are skipped in this verification.

Manual simplification and security reviews covered shared classification CRUD,
company/field access, reference navigation, removal of orphan imports and styles,
and preservation of all native posting/activation rules. The slash commands
`/simplify` and `/security-review` are unavailable in this environment; their
review areas were checked manually. No unresolved security findings remain.

Existing uncommitted product-section scrolling changes and their regression test
were preserved before removing that UI in the local recovery patch
`.git/product-ui-existing-20261104-091448.patch`. Other pre-existing edits remain
in place. No backend, database, permission or API proxy changes belong to this
task; no commit or publication was performed.

Local test reports and logs are in `.tools/product-ui-removal-review-20261104/`.
