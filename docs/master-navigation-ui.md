# Master navigation and detail links

Scope: the completed Catalog master pages, their revision tables, related-record
links and cross-master return navigation. Treat “View time” as opening a record's
detail view. Reuse shared links, tables, menus, page navigation and existing CSS.

1. Audit route shapes, row actions and return validators; add regression tests for
   real kebab hrefs, preserved directory filters and denied/missing references.
2. Implement bounded shared cross-master navigation, appropriate related shortcuts
   on directory/detail views, and consistent View/Open draft revision actions.
   Expose a protected parent identifier on native configuration revision choices
   where needed to construct the existing nested revision URL; keep API/SDK aligned.
3. Review security, pending/dirty navigation, keyboard links and target pages; fix
   findings, run focused regressions/types/build and review real shared styles.

No new business model or migration is required. Related links depend on current
read authority and readable reference fields. Never construct a nested revision
URL without its verified native parent, or link to an unsupported edit page.

All three phases are complete.

Implemented native View/Edit links on the older Catalog, units/identifier,
attribute and pricing directories. Product directory and detail kebabs now offer
permitted related-record and filtered-list shortcuts. Manufacturer details link
to their sites. Detail Edit returns to the detail page and retains its directory
filters. Type, attribute-template and reusable-profile revision tables offer View
and authorized Open draft links; published and protected revisions cannot gain
an edit action.

Verified read-only references now open their existing master or nested revision
page. Native configuration choices supply `parent_id` only under the existing
parent-field/read/company protections. Catalog OpenAPI, generated TypeScript and
SDK version 0.2.23 match; business models and database migrations did not change.

Review findings and fixes:

- Replaced the product workflow's broad return-route regex with the shared closed
  route/query validator, including bounded parent chains and self-link removal.
  Unknown, external and unsupported edit/revision destinations are rejected.
- Converted imperative kebab navigation to native anchors, retaining keyboard,
  browser new-tab and disabled pending/recovery behavior. Primary actions precede
  related shortcuts. Existing dirty navigation guards remain on inline links.
- Removed guessed links for missing, denied or unverified references. Nested
  revision URLs require their native parent; parent-field denial returns 403.
- Reused the revision action policy across all three histories and removed a
  redundant configuration return-validator branch. Manual simplify and security
  reviews found no remaining issue in the changed navigation/authority paths.

Verification:

- Original navigation and missing-native-parent regression failures were
  reproduced before fixing their implementations.
- 1,028 Console tests across 39 affected files verified: the broad run passed the
  other 38 files, and all 62 Catalog page tests passed on the final rerun after
  correcting an assertion to allow the directory's existing default page limit.
- 21 native Catalog workflow, configuration and field/company authority tests
  passed, including all four reusable-profile parent projections; SDK 8 tests,
  TypeScript, Ruff and strict mypy passed.
- Two browser reviews passed: 48 focused navigation checks and 150 broader
  directory/detail/create/revision checks, at desktop/mobile widths in all three
  themes. No browser errors or document overflow; screenshots reviewed. Browser
  business responses were intercepted fixtures; no live business data was written.
- Console production build passed and managed Console was restored on port 4320.
  Catalog was reloaded on port 8003 and exposes the updated native option contract.
  OpenAPI/SDK freshness and unauthenticated API/BFF protection checks passed.

Independent in-progress Design work remains outside this navigation change.
