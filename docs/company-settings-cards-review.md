# Company Settings cards review

Requested 2026-10-26. Reuse the shared ActionCard, SectionHeader, layout classes
and native page permission checks.

## Phases

1. Regression checks for selected-company visibility, read/manage labels, grouped
   cards, empty access and Settings return links. Confirm the existing gaps.
2. Group Company setup, Business configuration and People and access. Add the
   existing warehouse-settings destination, correct action labels, preserve Back
   links and align readiness checks with current company grants. Keep platform
   and tenant-wide administration in their existing areas.
3. Run affected unit tests, responsive/theme browser checks and production build.
   Review accessibility, destinations and permission boundaries; fix findings.

## Boundaries

Cards are navigation hints; native pages and APIs enforce authorization. No new
permissions, API contracts, schemas or shared CSS are planned. Keep unrelated
workspace edits intact. This request does not include committing or publishing.

## Verification

Completed 2026-10-26.

- **Company setup:** Company configuration, Financial years, Company readiness.
- **Business configuration:** Product configuration, Accounting configuration,
  Warehouse settings. The accounting label is shorter; its description explicitly
  includes accounts, parties and suppliers. Warehouse settings opens the existing
  native configuration page.
- **People and access:** Users, Roles, Role assignments, Permissions. Shared
  notifications and tenant-wide administration have an authorized link to
  Organisation administration.

Cards use active selected-company or tenant grants rather than aggregate
permissions or account labels. Read/manage labels reflect the requested action;
role composition remains tenant-owned, and warehouse publishing is recognized
separately from warehouse management. Empty groups stay absent. An account with
no applicable settings gets an explanation and My access link; an account without
a selected company gets the existing company-selection state.

Review found and fixed:

- Settings return links missing from access cards and permission-page routing.
- User/role directories dropping their Settings parent while filtering and
  navigating to related records. Validated nested returns now preserve that
  parent; external and self returns fall back to Organisation administration.
- Readiness checks using aggregate permissions instead of current company grants.
- Invite-only users being sent through an unreadable directory.
- The warehouse Back label naming warehouses when returning to Company Settings.
- A duplicate page heading in the accounting destination; supporting configuration
  now uses the existing SectionHeader.
- A Next.js page-props type error from the permission page's optional default
  argument. Its props signature now matches the native page contract.

Manual simplicity and security reviews confirmed reuse of shared controls and
styles, permission-aware navigation and validated return paths. No new write
paths, authority, permission definitions or money/audit behavior were introduced.
Native pages and APIs retain their independent authorization checks.

- 799 affected unit tests passed across 58 files. After the page-signature fix,
  all 27 affected permission-page tests passed again and Console TypeScript passed.
- 770 fixture browser checks passed across 320/390/768/1440px layouts and
  light/dark/ledger themes. These cover card destinations, keyboard navigation,
  Back links, company/tenant/read-only/invite-only access, expired/foreign grants,
  ordinary users, platform users without a company, empty states and overflow.
  No browser errors, fixture business writes or live business writes occurred.
- Desktop and mobile screenshots were inspected with the native Console root
  class and shared styles. No remaining card wrapping or layout issues were found.
- The optimized production build passed. The managed Console was restored on
  port 4320, and a generated JavaScript asset returned HTTP 200. The task-owned
  browser preview was stopped.

No API, database, generated SDK or shared CSS changes were needed. Changes remain
local; this request did not include committing or publishing.
