# Console navigation review and cleanup

## Scope and plan

Keep the existing Console routes, CSS and shared shell. Page and API authorization
remain independent of presentation. Preserve unrelated local changes.

1. Audit the menu, overview cards and supplementary routes. Add regression coverage
   for real destinations, scope filtering, active items and back navigation.
2. Replace the flat Inventory menu with six permission-aware groups backed by real
   overview pages. Remove unimplemented menu placeholders. Add missing tenant
   notification navigation and align platform history and company settings links.
3. Link master directories to their group overview. Preserve validated contextual
   return links through records, edits and revisions. Highlight supplementary
   product and company pages under their owning menu.
4. Review twice for scope leaks, duplicate/dead links, keyboard/mobile navigation
   and retained contextual returns. Fix findings; run affected UI tests, strict
   type checking, browser checks and a production Console build.

## Completion record

Implemented the six Inventory groups and their overview pages, using the existing
ActionCard grid, page navigation and sidebar disclosures. Menus and cards share
the same inventory registry and active company grants. Unimplemented invoices,
payments, ledgers and stock entries were removed. Suppliers now sits under
Accounting. The sample Customers entry was removed; legacy customer links redirect
to the native Parties directory with `role=CUSTOMER` and a bounded search query.

Organisation notifications now has tenant-authorized submenus. Platform history
uses the same explicit event permissions as the platform navigation, including
tenant administrator and notification history. Accounting cards now include
finance-only and charge-policy readers. Product fields checks the selected
company's active grants.

Master directories return to their group overview and retain validated contextual
returns through filters and deeper pages. Product fields, attributes and warehouse
settings have explicit navigation. Tax, notifications, platform access and company
setup pages identify their actual destination for menu highlighting. Closed
submenu disclosures remain closed in the collapsed sidebar.

## Reviews and fixes

1. Scope and hierarchy review: removed obsolete menu entries, grouped masters,
   aligned missing cards and notification links, and checked active, expired,
   foreign-company and department grants. Parent overview pages provide no new
   authority; native page and API checks remain independent.
2. Navigation and usability review: corrected directory return normalization,
   supplementary active items and collapsed submenu visibility. Browser navigation
   exposed a generic master edit-to-details self-return loop; the editor now uses
   the shared link normalizer. Directory breadcrumbs remain separate from the
   contextual Back link. A failing regression reproduced this before the fix.
   Production validation also caught optional default page arguments incompatible
   with Next.js PageProps; route signatures and their callers were corrected.

Manual simplification and security reviews covered shared route metadata, bounded
return URLs, company-scoped controls and tenant notification authority. No API,
permission catalogue, model or database change was needed. Existing business data
and unrelated local edits were preserved.

## Verification

- Initial navigation regressions: nine failures reproduced the original gaps.
- Edit-to-details return regression: failed before the fix.
- Final navigation and generic master checks: 199 tests passed across nine suites.
- Final route signatures and access checks: 26 tests passed across two suites.
- Additional administration, accounting, classification, units, attributes,
  pricing, profile, product configuration, tax and warehouse structure suites
  passed. The changed warehouse settings link expectation also passed in the final
  checks.
- Desktop and mobile visual review uses existing light, dark and ledger themes.
- Browser review: 332 checks passed at 1440px and 390px in light, dark and ledger
  themes, with no browser errors or data writes. Checks include overview cards,
  breadcrumbs, real record/edit/back navigation, submenu highlighting, mobile
  drawer Escape/focus, closed disclosures and command search.
- Strict Console type checking passed. The final production Console build passed,
  including Next.js route signatures and page generation. The managed Console was
  restored and verified UP on port 4320. The temporary browser-review preview was
  stopped after verification.
