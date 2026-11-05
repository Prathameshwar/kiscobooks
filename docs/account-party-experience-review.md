# Account and party master experience review (2026-10-27)

User request: enhance account and party masters to the same standard as the product
experience review, reusing the shared design system and native financial contracts.

## Delivery phases

1. Inspect native account/party schemas, field controls, permissions, existing tests
   and authenticated screens. Identify UI/flow gaps without changing financial rules.
2. Improve directories, metadata-driven forms, record details and related workflows:
   clear context, navigation, statuses, validation, messages and safe recovery.
   Write failing regressions before fixing defects; keep shared controls/CSS.
3. Verify focused UI/native API suites and TypeScript. Exercise account/party creation,
   editing, lifecycle/related navigation and validation in a live tenant3 session.
4. Review accessibility, responsive themes, permissions, protected fields and exact
   retry behavior. Fix review findings, retest and record evidence and limitations.

Balances remain outside master forms. Suppliers remain parties with active supplier
roles. Native company scope, audit, versions, field policies, dependencies and
lifecycle commands remain authoritative. No API/model/schema changes are planned
unless the review identifies a concrete native contract defect.

## Delivered experience

Accounts, parties and suppliers share scoped routed area navigation. Directories use
FilterBar/TableSearch, labelled status badges, native sorting, applied-filter chips,
secondary reference filters and accurate loading/error/empty states. The directory
body uses the shared flow rhythm so filters, results and paging have proper spacing.
All native party roles can be filtered. Suppliers never falls back to an unfiltered
party list when role-filter authority is absent.

Account forms group identity, currency/rounding, posting controls and description.
Party forms group legal/shared identity and notes. Resource-specific guidance sits
beside the shared form card/footer, with permitted chart/group/party setup links.
Native nullable schema constraints now drive full-width description/notes textareas
and their maximum lengths. Dependency help and errors are associated with controls;
multiline notes are accepted without accepting non-printing control characters.

Definitive create conflicts retain values and allow correction with a new request
identity. Uncertain writes retain exact-request recovery and lock editing. Native
create availability is checked separately from manage authority. Existing-record
conflicts retain reviewed reload and protected/unchanged values remain untouched.

Details use readable scalar facts and native reference hydration. Party details gain
a primary edit/related-actions control; related cards are grouped by purpose with
shared spacing. Related role creation retains/protects its originating party just as
account child creation protects its account. Supplier-role write links require the
active party and current target manage/read grants.

## Native defect found in authenticated verification

A customer/supplier account could not select its party: the UI supplied the supported
role query, but the reference API attempted to filter Party.role, which does not
exist. A failing native regression reproduced the 422. Party directories and options
now share one active-role EXISTS predicate over native PartyRole facts, enforcing
company scope and readability of party_id, role and status. New choices require the
matching active role. Exact hydration retains historical identities, including a
retired role, while still checking field authority. A party without that active role
is absent. Wrong-company and unauthenticated requests remain rejected.

No endpoint/schema/model/permission changes were needed; OptionQuery already admits
these roles. OpenAPI freshness and strict mypy passed; no generated client or database
migration change is required. The managed Accounting service was reloaded on 8002
and its readiness returned HTTP 200.

## Review and fixes

First review covered native contracts, financial boundaries, permissions, field
policies, scope, conflicts, retries and relationship ownership. Fixed: unsupported
party-role reference filtering, unsafe supplier-directory fallback, mutable party
creation context, create-availability checks and locked duplicate-create recovery.
Second review covered presentation, layout, accessibility and navigation. Fixed:
resource-specific sections/guidance, readable detail choices, related-card grouping,
loading pager messages, nullable textarea constraints/help, multiline validation and
filter-to-results spacing. New defect regressions were run failing before fixes.

A browser stall exposed a redundant external Google Fonts stylesheet import in
shared tokens, despite both applications importing the local Inter font. The external
import is removed, matching the existing design-system contract. The pending shared
UI 0.1.22 release already covers this workspace's shared UI changes. No dependency,
app stylesheet or duplicate CSS was added. A failing token regression now prevents
reintroducing the external stylesheet.

Manual equivalents of the unavailable simplify/security-review commands reviewed
CLAUDE.md sections 5 and 6. Native references/grants/field controls remain authoritative;
parent links use validated return chains; sensitive beneficiary numbers stay write-only;
no posted balance or financial command is added. Native master audit, versions and
idempotency remain unchanged. No unresolved finding remains in this scoped review.

## Verification ledger

- Full accounting/account Console selection: 323 tests across 13 files passed.
  After the final spacing adjustment, the 52 affected directory/navigation/experience
  tests passed again. Console TypeScript passed.
- Shared UI token/layout/density/menu selection: 97 tests across four files passed.
- Native baseline: 27 configuration/account/party/field-policy tests passed.
  Post role-query fix: 11 configuration/list tests passed; multiline persistence
  regression: 1 passed. Ruff and strict mypy on all three changed query modules passed.
- OpenAPI freshness passed; public typed contracts and storage remain unchanged.
- Actual tenant3 verification used Catalog enrollment verification company. Its books
  were initialized and its groups-only chart installed through normal reviewed UI.
  Created party P-MVQQSG57, activated it, added/activated CUSTOMER and SUPPLIER roles
  on that same identity, edited the party, created/edited/activated its linked customer
  account AR-MVQQSG57 and verified the same identity appears in Suppliers. No posted
  balances, financial documents, personal identity numbers or real contact messages
  were created. These explicitly labelled verification masters remain available.
- 60 browser theme/viewport checks passed across the ten account/party/supplier/
  related-role screens (1440/390 px, Light/Dark/Ledger), with no overflow or browser
  errors. Representative desktop/mobile screenshots were inspected.

Existing assertions now target inline field errors and breadcrumb links specifically;
the supplier-role shortcut is checked after activation with its target grant. The row
menu check waits for the fetched row rather than just its outgoing request. These
reflect the intended UI and asynchronous completion without weakening authority checks.
Private browser evidence is retained in ignored .tools/extension-masters artifacts.

Final browser recovery/accessibility check also passed: multiline notes saved and read
back on the active party; a real duplicate-code 409 retained legal details, allowed
correction and confirmed discard without a duplicate; eighteen directory theme/viewport
rechecks passed after the spacing fix; the mobile related menu stayed in bounds and
Escape restored trigger focus. The local Inter font loaded with zero external font
requests. No browser errors occurred. All four phases are complete locally.
