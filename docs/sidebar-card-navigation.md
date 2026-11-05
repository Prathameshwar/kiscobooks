# Sidebar and card navigation

Request: keep the console's left panel to two menu levels and open deeper destinations from card landing pages.

## Logs and activities decision — 2026-10-30

Administer has one **Logs and activities** entry at `/logs-and-activities`.
Its two cards open the retained `/audit` and `/activity` destinations, which
highlight the owning entry and link back to the hub. Cards use current active
company or tenant grants independently: `audit.read` and `activity.read`.
A denied card explains its required access and has no destination link. Neither
the hub nor navigation substitutes for native endpoint authorization.
See [delivery review](logs-and-activities-ui-review.md).

## Plan

1. Reproduce the nested sidebar with platform and organisation administration sessions. Keep the permission-resolved navigation catalogue for search and route ownership.
2. Render only top-level groups and their immediate links. Highlight the visible owning link when a deeper directory, record or form is open.
3. Add the missing Reference data and Roles & access card landing pages. Reuse existing platform access, notification and inventory landing pages, shared ActionCard styles, and validated return navigation.
4. Review permissions, card destinations, keyboard search, active highlighting and back links. Run affected UI tests and the console type check, then fix findings.

## Scope

Console presentation only. Existing pages and APIs continue to authorize their own reads and writes. Local project paths stay unchanged.

## Validation

Completed 2026-10-26.

- Regression checks first reproduced third-level sidebar groups and the reference root redirect.
- The left panel renders only top-level groups and immediate links. Deeper directories and record pages highlight their visible owning link; permitted destinations remain searchable through Ctrl+K.
- `/organisation/access` provides shared Roles, Role assignments and Permissions cards. Links retain the hub as their validated return destination; role pages also include the hub in their breadcrumbs.
- `/platform/references` provides Countries, States, Languages, Currencies and Timezones cards. Reference directories return to this hub, while record forms preserve directory filters and unsaved-change guards.
- Existing platform access and notification cards remain available with their original permission boundaries. Inventory, accounting, Company Settings, contextual row actions and related-page returns were covered by affected tests.
- 216 Console tests passed across 22 files; Console TypeScript and Git whitespace checks passed.
- 301 fixture browser checks passed on desktop/mobile in light, dark and ledger themes. Desktop and mobile screenshots were inspected. No browser errors or business writes occurred. The preview was isolated from the running console.
- Manual simplicity and security reviews confirmed reuse of shared ActionCard, RailItem, RailGroup and PageNavigation controls, existing CSS, scope helpers and validated local return paths. No API or database changes were required.

Changes remain local; this request did not include committing or publishing.
