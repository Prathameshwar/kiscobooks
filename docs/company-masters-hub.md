# Company Masters card hub

## Agreed scope and phases

1. Register one Masters menu entry inside Administer, without
   submenu entries. Inventory, accounting and tax master pages stay at their existing
   URLs; departments and financial years keep their existing navigation.
2. Add `/masters` with cards for the 43 core masters: 29 Catalog, 10 Accounting and
   four Tax. Reuse the shared ActionCard grid, headings, notices and company picker.
   Filter by active tenant/company grants for the selected company. Preserve backend
   feature, field and lifecycle applicability; do not invent feature restrictions
   on preparatory master authoring (warehouse authoring explicitly works with
   inventory disabled). Readers navigate to view pages; mutations remain separately
   authorised on the existing pages/APIs.
3. Keep Masters selected on linked resource pages and preserve safe Back to Masters
   navigation. Verify role/scope/expiry, all 43 links, empty/no-company states,
   keyboard/sidebar behavior, responsive themes and affected navigation tests.

Decision 2026-10-27: consolidate the sidebar master destinations into a single card
hub. Existing bookmarked inventory overviews remain supported. Company feature
configuration and per-record readiness continue to be enforced by their owning
screens and APIs rather than guessed from a master category's name.

## Implementation and verification

All three phases are complete. Masters is the first entry inside Administer;
Reports is under Books and Reports, with four category submenus. Masters has no
submenu. The previous Inventory master groups and
Accounting/Tax master sidebar trees are consolidated; their bookmarked URLs remain
available. The hub lists individual cards in eight readable groups with search.
Suppliers and customers share the Parties card, matching the underlying master count.
Departments and financial years remain in their existing administration/settings paths.

Each card requires active tenant/company read authority for the selected company.
Role labels, stale effective permissions, expired/future grants, platform scope,
department scope and another company's grants cannot unlock business masters.
Platform administrators retain their existing separation from customer business data.

Tax applicability is checked through the existing authorised Catalog tax context,
using the selected company's country rather than tenant defaults. Non-Indian
companies do not see the India-specific Tax cards or section. Failed or mismatched
context disables only unverified Tax links and offers retry; other masters remain
usable. A Tax-only reader with no applicable cards gets an accurate empty message.
This supersedes displaying country-inapplicable cards as disabled.

Safe `returnTo=/masters` is accepted by Catalog, Accounting, Tax, warehouse,
attribute and pricing navigation. Unsafe origins and query-bearing hub return
targets remain rejected. Resource pages select the single Masters sidebar item.

Review found and fixed a standalone search control stretching vertically inside
the page's flex column: it now sits in the shared FilterBar. Browser checks also
reproduced a 2 px account-menu overflow at 1024 px; the shared header/account flex
containers now permit shrinking without clipping the menu. The stylesheet
regression failed before that fix and passes afterward.

Verification:

- 182 affected Console tests passed across ten suites (the 25 final hub cases
  include the subsequent country-hiding and search-layout changes).
- 92 shared UI tests passed, covering header menus, shell and content layout.
- Console TypeScript and changed-file whitespace checks passed.
- A browser harness using the actual Console shell, providers, components and
  CSS with synthetic company context checked 43 native links, search, permission
  filtering, absent company, hidden non-India Tax cards and 12 width/theme
  combinations: 1440, 1024, 390 and 320 px in Light, Dark and Ledger. No overflow
  or browser errors remained. Desktop/mobile screenshots were inspected.
- The harness used fixed data responses and made no live business writes.
  Existing destination UI/API tests cover their native workflows; this change
  does not claim a new live CRUD exercise of all 43 master categories.

Manual simplification and CLAUDE.md §§5–6 security review found no remaining
blocking issue. The named simplify/security-review commands are unavailable in
this session. No API contract, schema, financial mutation or permission grant
changed. Unrelated workspace edits were preserved; these changes are not published.

## Landing-page review, 2026-10-27

Reviewed Masters and Reports together after both menu entries were complete.
No further application changes were needed. All 157 tests across 11 affected
Console suites passed, and Console TypeScript passed. Repeated browser checks
using fixed service responses passed at 320, 390, 1024 and 1440 px in all three
themes for each hub; inspected desktop/mobile screenshots showed consistent
spacing, alignment and card layout. Search, scoped card visibility, company
selection, country applicability and safe navigation remained correct. No browser
errors or horizontal overflow were observed. This review did not exercise live
master mutations or report jobs. Manual security and correctness review found no
new blocking issue.

## Live tenant-administrator access check, 2026-10-27

A live sign-in reproduced the reported Exchange-rates-only hub for a tenant
administrator. The selected company was active. The session contained the
tenant-administrator setup grants, including `accounting.finance.read`, but no
Catalog master reads, Accounting master-family reads or `report.read`. The single
visible card therefore matches the current role catalogue; it is not a missing
database table or a card-rendering failure. The Reports menu was also correctly
absent for that session.

Company Administrator is a separate business role. Broadening tenant administrators
or bootstrapping company-owner access is an authorization-policy change, subject to
the role delegation/self-assignment rules. A decision was requested on granting the
creator company-scoped Company Administrator access when creating a company and
repairing the reported account's existing company. No assignment or guard was
changed during diagnosis. At that point Masters and Reports were ordered within
Books; navigation grouping does not control access.

The creator-access decision was subsequently approved and implemented; see
[company-owner-access.md](company-owner-access.md). The account now has company-scoped
Company Administrator access, and the role seed includes the previously omitted
identifier type/namespace and sales channel permissions. A live sign-in shows 42
cards. Further API verification identified unconfigured Catalog Identity source
replication as a separate 503 blocker; card visibility alone does not certify
working master reads or writes. Automatic source enrollment is awaiting the
additional scope decision recorded in that document.

## Amendment 2026-10-30 — Voucher types

A twelfth group, **Vouchers**, adds one card, **Voucher types** (`/masters/voucher-types`, gated on
`vouchers.read` for the open company): 52 cards in 12 groups. The Purchase invoice and voucher entry
screens already linked to that address and reached a 404 because the masters page knew no such resource.
Behaviour and permissions are in [voucher-extensibility](voucher-extensibility.md).

## Product family card decision - 2026-10-30

The Masters hub now uses the selected company's verified Product configuration
(`product_family_sku_enabled`). Product families appears only when family/SKU
mode is enabled. Simple mode shows Products, without a family card or SKU wording.
Product types, groups and other applicable masters remain available. While the
structure is unknown, loading, denied or from a different company, the family
card stays hidden. The static catalogue still defines 52 possible destinations;
configuration and permissions determine the displayed cards.

Masters and the inventory overview share the same pure product-structure card
mapping. Refreshing settings updates the cards while retaining the master search;
no company setting is changed by opening the hub. Existing native product reads,
company grants, field policies, authoring and publication controls remain in place.

Six fail-first cases reproduced the original always-visible card. Review also
corrected nullable mode access, including the absent-company/no-provider path.
Manual equivalents of simplify and security-review checked CLAUDE.md sections 5
and 6: the mapping does not mutate the shared catalogue or widen permissions,
and company/response identities must both match before exposing family cards.
Final validation is recorded in the
[CSV](product-family-card-results-2026-10-30.csv).
All 113 affected tests across five suites passed. The final 34-case hub rerun
and console TypeScript passed after the nullable-mode correction. No further
review finding remains within this UI scope. This verification uses component
and provider tests; it does not claim a new authenticated browser session.

## Promotion card visibility decision - 2026-11-04

Promotion stacking policies appears only after authoring configuration is verified
as enabled for the currently selected company. Loading, disabled, failed and
wrong-company responses hide the card and its empty section. The hub does not
show the promotion-specific unavailable notice or retry button. Users can reload
the hub after a temporary failure; the dedicated authoring page retains its own
configuration checks and recovery. Other master cards keep their existing behavior.

Regression cases reproduced the unwanted loading/error cards before the fix.
All 38 hub tests and scoped TypeScript passed. Manual review found no permission
or write-path changes; server authorization remains authoritative.
