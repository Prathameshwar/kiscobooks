# Operate voucher navigation

Status: implementation completed on 2026-11-01; final verification is recorded in
[operate-voucher-navigation-todo.md](operate-voucher-navigation-todo.md). The user asked to proceed,
check every voucher type list in a loop, and include New voucher and Import
voucher links. The three phases below are the agreed implementation scope.

## Intended experience

The Operate sidebar will show Business overview, Income, Expense, Inventory,
then the existing Voucher drafts destination. Each new destination opens a
searchable card landing page. A family card opens a second page containing
its voucher lists, company-configured voucher types and relevant print settings.
Lists use the existing shared table, filters, paging, review and draft-edit actions.

Decision amendment (2026-11-01, user-requested Purchase cards): the Purchase
family shows specific Purchase type cards and omits the generic All Purchase
vouchers card and types titled Purchase voucher(s). The standard Mixed bill
card is labelled **Purchase - Goods & Services Bill**, matching the title casing
and prefix of Purchase - Product Bill and Purchase - Account Bill. This is a
card caption; the stored type and exact type-filtered list URL are preserved.
Search accepts the displayed caption, original type name and code. Purchase
history remains accessible through the existing all-voucher list and direct list
routes.

Decision amendment (2026-11-01, single-type cards): other voucher kinds omit
their generic All card when the complete active-type result contains exactly
one type. Multiple types, empty results and incomplete paging retain the generic
card; loading does not briefly display it. The count uses the unfiltered type
result, so searching for one of several types does not change this decision.
The Debit Note card explains that purchase returns and supplier adjustments use
product/account details according to its settings. The live company effective
configuration permits ACCOUNTS, ITEMS and MIXED modes and ACCOUNT, GOODS and
SERVICE invoice supplies. A separate disabled product-return card would
duplicate this type. This amendment changes cards only, preserving existing
list, entry, configuration, posting and stock-movement behavior.

Decision amendment (2026-11-01, related Purchase cards): on
`/operate/expense/purchase`, sole active Debit Note, Credit Note and Receipt Note
types share a **Returns, Notes & Receipts** section and responsive card grid.
Purchase returns use the existing Debit Note card. A related kind with multiple
types, incomplete paging, no active types or a load failure keeps its own named
section and existing list/paging/retry behavior. Grouping uses the complete type
result before search, and search matches both individual cards and the shared
section title. Purchase bills, purchase orders and print settings retain their
sections. Other family pages and voucher destinations are unchanged.

Decision amendment (2026-11-01, Sales card refinement): on
`/operate/income/sales`, retain separate invoice, customer-return, order/quotation
and delivery/challan sections because the company has multiple invoice, order
and delivery types. Clarify section and generic-card captions, and label the
standard Sales - Mixed Invoice card **Sales - Product & Account Invoice** with an
explanation of combined item/account details. Give invoices, pro forma invoices,
credit notes, quotations, orders and deliveries relevant descriptions. Search
accepts descriptions and current/original captions and codes. Sole-type All cards
remain hidden; scoped type identities, list routes, print settings and native
entry/posting behavior remain unchanged. This is a Sales card-page refinement.

Example: Expense → Purchase → Purchase - Account Bill → supplier bill list → review
or edit a saved bill. Purchase also offers purchase returns/debit notes,
purchase orders and goods receipt workflows, with distinct print-setting links.
When a company has multiple configured types for a kind, each type gets a named
list link. A type-specific list must verify that the type belongs to the open
company and the expected kind before fetching vouchers.

## Organisation and terminology

| Landing | Families and related voucher kinds |
| --- | --- |
| Income | Sales (sales, credit notes/customer returns, sales orders, delivery notes); Receipts (receipts); Adjustments (journals, reversing journals, memorandum) |
| Expense | Purchase (purchase, debit notes/purchase returns, supplier credit notes, purchase orders, receipt notes); Payments (payments); Cash and bank transfers (contra); Adjustments (journals, reversing journals, memorandum) |
| Inventory | Goods received (receipt notes, rejections out); Goods dispatched (delivery notes, rejections in); Stock adjustments (stock journal, physical stock); Job work (material in/out and job-work in/out orders) |

The existing 22-kind voucher vocabulary remains authoritative. A purchase return
is represented by a debit-note type; a sales return by a credit-note type.
Configured type names and codes distinguish specialised workflows. Related notes
are labelled by their actual kind, rather than claiming that every note is a
return or creating an unsupported purchase-return kind. These navigation groups
do not change ledger classification, posting rules or available entry capabilities.

New landing and family routes use `/operate/income`, `/operate/expense` and
`/operate/inventory`, avoiding collisions with existing `/inventory` master routes.
The existing voucher draft list remains available for browsing across kinds.
Kind/type-specific voucher lists reuse its implementation with explicit filters.
Print cards open the existing `/documents/vouchers/<kind>` configuration pages.
Breadcrumbs and allowlisted return destinations connect the family, list, detail
and print pages. Existing master, voucher and print URLs remain valid.

Card search matches labels, descriptions, type names and codes on the current
bounded page of configured types. Type paging stays explicit; a partial page must
not be presented as an exhaustive company configuration. List search retains the
API's supported number-prefix/UUID search and never scans narration or child rows.

## Phases

1. **Navigation and landing pages.** Add the three sidebar entries in the requested
   order, shared area/family definitions, searchable landing and family cards,
   company-scoped access checks, configured type reads and permission-aware print
   links. Reuse shared ActionCard, PageHeader, PageNavigation, FilterBar and search
   controls without adding application CSS. Finish with navigation and page tests
   and TypeScript checks passing.
2. **Voucher lists and connected navigation.** Extend the existing directory for
   explicit kind/type filters and relevant titles, retain search/status/paging and
   review/edit actions, and connect purchase and other family cards to these lists.
   Only offer creation through existing supported editors; preserve capability
   gates. Add safe back links through list, voucher and print navigation. Finish
   with scoped-list, route-validation, workflow and affected existing tests green.
3. **Verification and documentation.** Exercise company/no-company, denied access,
   empty/loading/error/retry, search, paging and invalid routes. Check the running
   app at desktop and mobile widths using the supplied QA account, inspect
   accessibility and shared styling, perform simplification/security review and
   update the checklist with evidence and any remaining limitations.

## Constraints

- No database migration, new posting workflow or new print engine is needed.
- Permission filtering is a navigation courtesy; routes and services independently
  enforce live tenant/company access. Print management keeps its existing grants.
- Existing in-progress overview, purchase, report and shared UI changes are
  preserved; stage only files changed for this task if publishing is authorised.
- Repository `CLAUDE.md` §2 requires these phases to be agreed before implementing
  a change of this size. The user has delegated layout and grouping decisions;
  the requested agreement is for this concrete execution scope.

## Baseline checks (2026-11-01)

Before application changes, the eight affected navigation, inventory/master,
voucher-directory and print suites passed: **177 tests, zero failures**.

The initial console TypeScript check failed in separate in-progress overview
work: `.next/types/app/page.ts:34` rejects the root page's optional props signature,
and `tests/company-overview.test.tsx:149` calls a function with two arguments where
three were required. Neither file was modified for this task. Concurrent work
resolved these issues; the final console TypeScript check passes.
