# Product management UI restoration

User-approved scope, 6 November 2026: restore the retired product management pages,
review and fix one page at a time, and finish with a complete UI consistency review.
This supersedes the UI retirement decision for the routes listed here.

## Ordered delivery loops

| Loop | Pages | Implementation and review gate |
| --- | --- | --- |
| 1 | Product/SKU detail, edit, completion | Restore routes, directory/reference links, native Simple and Advanced reads/edits, saved-state completion and draft protection. |
| 2 | Product Profile create, detail, edit, completion | Product Profile means the product-family aggregate used by Advanced creation. Reuse the current wizard; retain separate family/SKU identities and field permissions. |
| 3 | Standalone attributes and variants | Restore company/product selection, typed values, family declarations and additional SKU authoring with current metadata and exact native commands. |
| 4 | Batch list, create, detail, edit, history | Restore native registration, date correction, holds/lifecycle actions and paged history. Registration must not claim stock receipt or value. |
| 5 | Serial list, create, detail, edit, history | Restore identifier registration and read-only immutable identity; expose supported hold/lifecycle changes and history instead of pretending serial identifiers can be edited. |
| 6 | Final review | Check every route, link, state and permission; test desktop/tablet/phone, all three themes, long labels, keyboard/focus, overflow and production build. |

For every page: inspect the current contract and UI, record a failing regression for
findings, implement, review CSS/styles/alignment/UX, then run behavioral and browser
checks before moving to the next loop. Record actual results below. Backend APIs,
posting/activation rules, tenant/field access, immutable identifiers and native
idempotency remain authoritative. Preserve concurrent workspace changes.

Use shared components and centralized token CSS. Keep navigation safe and bounded.
Cover loading, empty, denied, unavailable, validation, stale-version and uncertain
save states. Do not discard user input during refresh or repeat uncertain writes
with a different body/key. Completion URLs read persisted state; they do not rerun
old creation, activation or opening-stock commands.

## Progress and findings

- Inventory confirmed: product record routes explicitly reject requests; batch and
  serial catch-all routes return 404; record/reference/import links are suppressed.
  Original dedicated product/tracking screens are absent from available Git history.
- Current native Catalog and Accounting APIs, closed proxy policies and shared
  field/navigation/command components remain available for restoration.
- Important UX contract: Simple edits must use the public product aggregate API,
  which updates both family and SKU labels. Editing only a native SKU would leave
  the Simple directory showing a different product name.
- Loop 1: product/SKU detail, edit and old completion routes restored. Native Simple
  edits retain the aggregate revision and mode version; Advanced edits retain native
  metadata/version checks. Completion reads current state without repeating writes.
- Desktop visual review found four-column forms with trading flags mixed among
  identity fields. Shared scoped styles now use two columns, one on phones, with
  trading controls grouped. Existing full-width descriptions remain full width.
- Added a form initialization guard after tests exposed empty first-render values;
  validated exact uncertain-save replay, denied fields, validation focus and the
  saved checkbox values. Final focused behavior: 14 passed. Browser review: 6 page
  scenarios × 4 widths × 3 themes = 72 geometry checks passed; Inter is embedded in
  browser fixtures. Artifacts use real component DOM and centralized CSS.
- Loop 2 complete: Product Profile create/detail/edit/completion are restored.
  Create reuses Advanced creation; direct Profile routes require Advanced mode.
  Completion links to persisted records and does not repeat activation or opening.
- Loop 3 complete: standalone typed specifications, Profile declarations/options,
  and additional draft variants are restored. Product selection uses supported
  native/public directories. Variants render current create metadata, including
  trading settings and required custom fields. Boolean false and exact decimals
  survive unchanged; active SKU specifications remain protected.
- Loop 4 complete: batch list/register/detail/date correction/hold/lifecycle and
  paged history/event views are restored. MRP uses the company currency and the
  verified product base unit. Corrections send only changed dates; an unreadable
  or unchanged existing date is never silently cleared.
- Loop 5 complete: serial list/register/detail/hold/lifecycle and history/event
  views are restored. Configured identifier slots and required batches are
  enforced. Serial identifiers and batch assignment are immutable native facts;
  the edit page clearly explains supported changes.
- Loop 6 final review: centralized scoped CSS fixes long batch codes and serial
  identifiers overflowing tablet/desktop layouts. Buttons wrap within their
  cards. Two-column forms become one column on phones. Full shared styles,
  app globals, Inter, and theme color schemes are included in browser fixtures.
  Reviewed desktop Profile/attribute forms and dark phone batch/serial forms.
- Review also fixed draft loss during product-mode refresh: keep the mounted
  editor and existing values, freeze new writes until mode/version is verified,
  and preserve exact interrupted-command recovery. Stale-version errors require
  explicit reload/review; validation keeps input and focuses the invalid field.

## Restored route checklist

| Pages | Routes | Review result |
| --- | --- | --- |
| Product/SKU detail, edit, completion | /masters/items/:id, /edit, /created | Verified in Simple and Advanced mode; aggregate/native API ownership retained. |
| Product Profile create, detail, edit, completion | /masters/product-families/new, /:id, /:id/edit, /:id/created | Verified with native family/default-SKU identities and Advanced-only creation. |
| Standalone attributes and variants | /products/attributes; optional item_id or family_id | Typed values, declarations/allowed options, and draft variant authoring verified. |
| Batch list, create, detail, edit, history/event | /inventory/batches, /new, /:id, /:id/edit, /:id/history, /:id/history/:event | Registration and permitted corrections/lifecycle verified; no stock quantity/value write. |
| Serial list, create, detail, edit, history/event | /inventory/serials, /new, /:id, /:id/edit, /:id/history, /:id/history/:event | Registration and supported lifecycle verified; immutable identifiers remain read-only. |

## Final verification, 7 November 2026

- Console regression suite: 16 files, 181 tests passed after the final partial-date
  correction regression. Coverage includes route/access guards, reads, validation,
  native writes, denied fields, mode changes, MRP, batch requirements, uncertain
  replay and stale-save review.
- Browser layout review: 28 page/creation-step states across 1440, 768, 390 and
  320 px, in light/dark/ledger themes: 336 geometry checks passed. Attribute and
  tracking suites were repeated after the final command/UI changes.
- Shared UI: 2,323 tests passed in the full run; its browser suite initially
  selected a Windows-only executable on Linux. Repeating that suite with the
  installed Chromium passed all 8 tests, for 2,331 passed in total. Nine existing
  tests remain intentionally skipped. Shared UI and Console TypeScript passed.
- Native isolated API suites: Accounting tracking 20 passed; Catalog attribute
  authoring 8 passed. These tests use isolated fixtures, not business-company writes.
- Auth and Console production builds passed; Console rebuilt from final source.
  Frozen offline workspace dependency installation passed.
- All eight databases are at their migration heads. This UI restoration changes
  no backend schema or database data and requires no migrations.
- Security/correctness review: malformed IDs/routes rejected, company-scoped
  permissions and native field metadata retained, protected fields omitted,
  versions checked, exact idempotency replay retained, no invented stock or money
  effect, completion read-only, serial identity immutable. Manual review used
  because no callable simplify/security-review command is available here.

Browser checks exercise actual React DOM in Chromium with fixture API responses;
these are not a signed-in live-company business journey. Release smoke checks
cover service/web readiness and unauthenticated route protection. Evidence logs
and screenshots are retained on the VM candidate release and under /tmp with the
kisco-product-ui prefix. GitHub publication is blocked by this session's read-only
.git permission; concurrent repository changes were preserved.

## VM rollout

Candidate: /opt/kiscobooks/releases/product-ui-review-20261106-182029.
Previous release retained: /opt/kiscobooks/releases/latest-build-20261106-180159.
Activated 7 November 2026 after final verification with an atomic release switch.
All 8 APIs are ready, all 27 services are active, and public web checks passed.
All 18 sampled restored routes redirect unauthenticated users to sign-in. The
previous release remains available for rollback. Full evidence is retained at
/tmp/kisco-product-ui-deployment.json and in the release
product-ui-deployment-evidence.json.

