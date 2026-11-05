# Operate voucher navigation checklist

Purchase card follow-up (2026-11-01): removed the generic Purchase cards and
labelled Mixed bill **Purchase - Goods & Services Bill**, using the casing of
the neighbouring Product Bill and Account Bill cards. Specific type links, card
search and print settings are retained. The 61 focused navigation/page/list tests
and TypeScript check passed; desktop and mobile checks confirm the updated cards.
Manual simplification and security review found no additional issue: this change
affects card presentation, preserving owner scope, type identity and saved history.

Single-type card follow-up (2026-11-01): removed the redundant All card when a
workflow has one confirmed active type. Purchase returns / debit notes and
Supplier credit notes now each show their sole configured type. The Debit Note
description explains product/account coverage; no duplicate disabled return card
was added. The live effective configuration permits ACCOUNTS, ITEMS and MIXED
modes and ACCOUNT, GOODS and SERVICE invoice supplies. Existing entry, posting
and physical-stock behavior is unchanged.

Both sole-type regression cases failed before the fix. All 35 focused
navigation/page tests and the Console TypeScript check then passed. Live checks
at 1440px and 390px confirmed one Debit Note card, one Credit Note card, no
redundant All cards, preserved selected-type URLs, caption search and print
cards. Evidence is in the ignored `.test_artifacts/purchase-card-review/`
directory. Manual simplification and security review confirmed that this
card-only change preserves company validation, authorization, type identity
and existing history routes; no additional source issue was found.

Related Purchase card grouping (2026-11-01): the sole Debit Note, Credit Note
and Goods Receipt Note cards now share **Returns, Notes & Receipts** on the
Purchase family page. Related kinds with multiple types, more/previous pages,
empty results or failures retain their own sections and paging/retry controls.
Purchase bills, orders and print configuration retain their sections. Existing
card rendering and validated, company-scoped type reads are reused; no list,
entry, permission, configuration or stylesheet change was needed.

The three grouping regressions failed before implementation. All 38 focused
navigation/page tests and the Console TypeScript check passed after the change.
Tests cover individual/shared-title search, empty search and restoration,
multiple types, incomplete paging and a last page containing one type. Live
1440px/390px checks confirm three shared cards in a desktop row/mobile stack,
no overflow, hidden empty groups, working search and exact type-filtered links.
Updated browser evidence is in `.test_artifacts/purchase-card-review/` (ignored).
Manual simplification and security/invariant reviews found no additional issue:
the shared grid uses the existing design system, type validation and scoped
authorization remain intact, and financial/stock behavior is unchanged.

Sales card refinement (2026-11-01): clarified the Sales invoices, Customer returns
& credits, Orders & quotations, and Delivery notes & challans sections, including
customer-specific summaries. The standard Mixed Invoice caption is now
**Sales - Product & Account Invoice**. Descriptions explain the item/account
combination, product/account invoices, pro forma documents, credit adjustments,
quotations, orders and deliveries. Existing custom names and nonstandard profiles
are preserved. Search accepts descriptions, current/original captions and codes;
preliminary-invoice searches show the Pro Forma card alone.

The initial Sales regression failed before implementation. All 42 focused
navigation/page tests and the Console TypeScript check passed. Authenticated
1440px/390px browser checks confirmed four invoice types, one Credit Note, two
order/quotation types and two delivery/challan types. Each viewport checked all
16 cards, seven search cases, existing type-filtered links and print links with
no overflow or application errors. The sole Credit Note has no All duplicate;
the multiple-type sections retain their All cards. Updated evidence is in
`.test_artifacts/sales-card-review/` (ignored). Manual simplification and
security/invariant reviews found no additional issue: captions, summaries and
descriptions are local presentation, scope validation and authorization remain
intact, and no list, configuration, native entry or posting changes were made.

The subsequent role and company-scope review is completed in
[voucher-access-review.md](voucher-access-review.md), including consistent New,
Import, direct-page and configuration authorization, and its verification evidence.

Implementation authorised on 2026-11-01. Scope and phases:
[operate-voucher-navigation-plan.md](operate-voucher-navigation-plan.md).

- [x] Place Income, Expense and Inventory after Business overview under Operate.
- [x] Searchable landing and family cards using existing shared UI/CSS.
- [x] Cover all 22 voucher kinds, including orders, job work and internal vouchers.
- [x] Read company-configured active types with explicit paging and page-local name/code search.
- [x] Keep generic kind lists available for historical vouchers and retired types.
- [x] Reuse the existing voucher table with exact kind/type filters, search, statuses,
  signed-cursor paging, refresh, review and supported draft editing.
- [x] Verify company/type/kind before opening a type-specific voucher list.
- [x] Provide New voucher and Import voucher links on every authorised kind/type list.
- [x] Preserve selected kind/type into existing entry and supported import workflows.
- [x] Use the full existing Sales and Purchase composers with exact selected-type
  reads; keep Sales back navigation inside its unsaved-change protection.
- [x] Explain the existing eight-kind file-import capability on unsupported-kind import pages.
- [x] Connect per-kind print configuration with safe workflow back navigation.
- [x] Preserve existing inventory masters, voucher draft and print routes.
- [x] Scoped access, invalid routes, mismatched responses, empty/loading/error/retry,
  search, paging and accessible navigation tests.
- [x] New navigation tests: 105 passed; 100% statements/lines/functions,
  95.53% branches across new navigation modules, pages and import landing.
- [x] Existing affected tests: 233 passed across 19 suites.
- [x] Final navigation, selected-type and connected invoice tests: 154 passed
  across nine suites, retaining the navigation coverage above. A later Sales
  navigation fix passed 79 tests across five suites, including its page and polish
  tests. In total, 418 distinct tests across 30 suites passed.
- [x] Console TypeScript check green after phase 2. The separate initial overview
  errors were resolved by concurrent work; those files were preserved.
- [x] Authenticated browser loop across all kind/type lists and New/Import links.
- [x] Desktop/mobile visual inspection and final verification recorded.

## Review findings

Manual equivalents of `/simplify` and `/security-review` were performed because
the slash commands are unavailable in this tool session.

Simplification: reused the current directory, type readers, print pages, full
Sales/Purchase composers, generic entry, importer and shared presentation primitives. The operation map is one
plain module shared by cards, route validation and return-path validation. Generic
kind cards explicitly say "All … vouchers", distinguishing them from configured
type cards with similar names. No application stylesheet or duplicate table was added.

Security: no new service permissions, tenant scopes, database queries, posting
rules or activation gates. Routes resolve the live open company and scoped grants.
Type and voucher responses are checked for company and requested kind/type.
Redirect inputs are limited to canonical, bounded, allowlisted local operation
destinations; arrays, external destinations and inconsistent family/kind paths
are rejected. Existing entry, import and print services reauthorise writes.
No unresolved security findings were identified in the changed navigation.

## Verification details

The supplied QA login succeeded. The live loop reached all three area landings,
11 family pages, 22 kind lists and 46 company-configured type lists. It checked
New and Import links and followed the entry/import destinations for every kind.
Type-specific lists retained their exact type selection. Number search reached
the expected empty result; unit tests also verify status and signed-cursor paging.

Early browser attempts exposed cold development compilation delays and a harness
viewport-call error. The focused follow-up checks native invoice composers,
print returns and mobile navigation after correcting the harness.

Final browser result: zero errors. Both full invoice composers displayed Save
draft with the selected configured type and the correct list back link. Purchase
and debit-note print configuration returned to the Purchase family. Desktop
screenshots at 1440px and mobile screenshots at 390px were inspected; family
cards, list actions, filters and empty states use the existing responsive UI,
and both checked mobile pages had no horizontal overflow.

The existing Purchase Mixed Bill type has Accounts mode disabled; its native
composer correctly shows the configuration gate. The Purchase Account Bill type
opens the full composer. No entry capability or configuration was changed to
bypass that gate. File import remains limited to eight supported accounting kinds;
other kind-specific import destinations explain the limit and link to supported
import workflows.

Coverage scope is the new operation components, routes, map and import landing.
An exploratory run also included the entire pre-existing sales lookup module;
all 154 tests passed, but that broader module's unrelated untested branches failed
the global coverage floor. The final run uses the documented new-navigation
scope, meets the unchanged coverage thresholds, and separately verifies the new
exact-type lookup branches with nine tests. No coverage threshold was lowered.

Ignored browser evidence lives in `.test_artifacts/operate-navigation-live.json`;
screenshots use `.test_artifacts/operate-*.png`. Session state is stored with
Windows DPAPI. No credentials, provider tokens or session cookies are recorded
in tracked files or the browser result JSON.

## Follow-up menu, card and list review (2026-11-01)

- Confirmed the operation map covers all 22 kinds and keeps company-scoped menu
  visibility, route access, exact type verification and safe return destinations.
- Fixed card search to match the full displayed generic voucher and print card
  titles. Two regression cases failed before the fix and pass afterward.
- Corrected the configured-type paging hint so the last page does not suggest an
  unavailable next page.
- Removed the duplicate page gutter from scoped voucher lists, using the shared
  flow layout inside their existing page wrapper. Headings now align with the
  breadcrumbs and mobile tables retain the normal content width.
- Review tests: 107 operation tests passed with 100% statements/lines/functions
  and 95.53% branches; the existing menu, shell and directory suites passed another
  36 tests. Console TypeScript passed.
- Manual simplification/security review: no new auth, financial, tenant-scope,
  posting or import capability changes; no unresolved source-review findings.
- Authenticated browser review completed: 198 distinct page/viewport checks at
  1440px and 390px, covering three menus, 11 family pages, all 22 voucher kinds
  through 28 kind-list routes, and 39 distinct company-configured types through
  46 type-list routes. Types reused by multiple workflows account for the route
  count being higher than the distinct type count.
- New, Import, selected kind/type, default status, search controls and family
  back links were checked on the list pages. All 22 print-kind pages returned to
  their originating workflow. Mobile navigation opening/Escape and the three
  exact Operate destinations in the command palette passed.
- All 74 distinct scoped list data reads returned HTTP 200 through the actual
  authenticated application proxy, with a bounded limit of 25 and company,
  kind, type and row-version checks. No card overflow or browser application
  errors remained. Populated-row actions and paging are covered by the unit
  tests; the live pass checks the data available to the QA account.
- The development run encountered one transient workspace/session read returning
  HTTP 503; retrying the same authorised destination succeeded. The review
  scripts also needed hydration/reload handling and exact command-label matching
  to distinguish Income from similarly named reports. These interruptions are
  retained in the evidence; no access checks were bypassed.
- Final evidence is `.test_artifacts/operate-review/result.json`; inspected
  desktop/mobile list, card, print-card and command screenshots are in the same
  ignored directory. Existing import and entry capability limits documented
  above still apply. No outstanding menu/card/list source defects were found.
