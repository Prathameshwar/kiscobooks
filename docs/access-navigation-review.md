# Users, roles and permissions navigation review

Requested 2026-10-25. Reuse the existing Console menu, cards and directory actions.

## Audit and phases

1. **Entry points.** Organisation administration already exposes users and roles,
   but lacks separate assignment and permission cards. Group assignments and
   permissions on the Roles & access card landing page and in command search. Keep
   platform access on its dedicated tenant-administrator boundary.
2. **Related actions.** Add permission-aware user and role directory shortcuts to
   the existing assignment pages. Link role permissions to their actual detail
   section, preserving filtered directory returns. Keep mutation actions under
   the existing tenant/company authority.
3. **Verification.** Regression tests first; review admin/reader/company/platform
   scope, working destinations, active submenu selection and filtered returns.
   Run affected UI tests, types, responsive browser checks and production build.

Permissions are an application-owned read-only catalogue. Administrators manage
custom role composition and scoped assignments through existing pages/APIs.
Company administrators use their company user projection and assignment grants;
tenant administrators own account-wide profiles and custom role composition.
Platform administrators manage tenant administrators through `/platform/access`.
Ordinary users retain My access. This task adds navigation, not authorization.

Existing unrelated and staged changes will be preserved. No API/schema or
publishing change is planned.

## Verification

Completed 2026-10-26.

- Organisation administration has separate Users, Roles, Role assignments and
  Permissions cards. The Roles & access link now opens `/organisation/access`,
  with cards for roles, assignments and permissions; the rail stops at two levels.
  Keyboard search retains each permitted destination. Company Settings has direct
  access cards and uses the same scoped authority as the destination pages.
- User and role kebab menus open filtered assignments and preserve directory
  filters on return. Role menus open their permission section; it scrolls into
  view and receives focus after asynchronous record loading. Review corrected a
  duplicate accessible region name and the existing flat-menu test expectation.
- Manual simplicity and security reviews confirmed reuse of existing controls,
  styles, scope helpers, validated return links and native APIs. Permission
  catalogue records remain read-only, custom role management stays at tenant
  scope, and company assignment changes retain server-side delegation checks.
  Platform and ordinary-user entry points keep their existing boundaries.
- 365 affected Console tests passed across 30 test files. Console TypeScript and
  the optimized production build passed.
- 175 fixture browser checks passed across desktop/mobile and light/dark/ledger
  themes, covering tenant, company, reader, platform and ordinary-user access,
  cards, nested menus, row shortcuts, focus and Back navigation. No browser
  errors or business writes occurred. Desktop and mobile screenshots were also
  inspected for layout issues.
- The managed Console was restored on port 4320; a generated JavaScript asset
  returned HTTP 200. The task-owned browser preview was stopped.

No API, database, SDK or shared CSS changes were needed. Changes remain local;
this navigation request did not include committing or publishing.
