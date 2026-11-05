# Administration navigation review

Decision 2026-10-27: the `/organisation` menu, overview and linked breadcrumbs
are labelled Administration. Routes, permissions and scope checks are unchanged.
The tenant notification menu and heading are labelled Notifications; platform
notifications retain their explicit platform label and separate authority.

Requested 24 October 2026: check menus, submenus, page-opening links and back
navigation after the six-master organisation/access delivery.

## Phases

1. Resolve one permission-filtered navigation tree for the rail and command search.
   Group organisation/access pages and platform pages into accessible submenus.
   Expose the existing tenant/reference pages directly. Correct inactive account
   menu entries and links to pages that do not exist.
2. Add consistent administration breadcrumbs and explicit back destinations.
   Preserve directory filters through view/edit and related user/group/role/
   assignment navigation. Validate internal return destinations, bound nesting,
   and keep draft/pending guards on every added link. Complete company and tenant
   return paths using their existing layouts.
3. Run navigation regressions, affected suites, type/build checks and rendered
   desktop/mobile menu/navigation checks; review scopes and fix findings.

The request authorizes the phases above. Shared CSS/layout/components are reused.
This changes navigation presentation, not API authority, tenant switching, model
storage or migrations. Parent hubs must disclose only the children that the actor's
grants authorize; platform classification grants no tenant administration.

## Initial findings

- The administration rail is flat; platform tenant/reference destinations require
  extra intermediate navigation. Account profile/preferences entries have no
  action; support footer links point to missing console pages.
- Access pages have no breadcrumbs or directory-level back link, and omit company
  links. Organisation's hub admits only tenant-wide administration, even when
  company/department readers have legitimate child directories.
- Editing from a detail page returns to its directory rather than its detail.
  Success links and related assignment links discard the original filters.
- Assignment subjects do not link to authorized user-group details. Company list
  filters are not restored on return and its row/actions omit return context.

## Delivery and evidence

All three phases are implemented and reviewed.

- The console rail and command search resolve the same permission-filtered tree.
  Organisation administration contains companies, departments, users, user groups,
  roles, assignments and permissions. Platform administration contains tenants,
  accounts, reference data (countries, states, currencies, languages and timezones),
  notifications, details, pricing and history. Each parent remains a working link;
  its separate disclosure supports keyboard use and opens the active subtree.
- Platform pages mark their owning submenu destination active. Unimplemented
  profile/preferences entries and missing footer/support destinations are removed.
  My access, change password, sign out and company settings retain working actions.
- Administration breadcrumbs and explicit back links follow directory, detail,
  edit/clone/create and related-page context. Supported filters and page size survive
  these trips; opaque cursors restart. Assignment subjects link to readable group
  or user details. Department child creation returns to its parent detail.
- Company view/edit/create/year links and tenant view/edit/history links retain the
  originating directory. Year generation carries that context to the generated
  year. Company setup confirms departure with an edited draft, and assignment
  navigation retains its pending/draft guards. Invite-only actors are not offered
  an unreadable user detail link after invitation.
- Company/department readers can enter the organisation hub to reach authorized
  child pages. Tenant groups, role composition and notification transport keep
  their independent scope checks. The hub is a reusable `OrganisationOverview`;
  admission does not confer API authority. No API, model or migration changes are
  needed for this navigation delivery.
- Shared `RailGroup` and six token-based shell rules reuse the existing layout.
  `@janso/ui` is version 0.1.19 and the workspace lock check passes.

Navigation regressions were reproduced before their fixes. Red-run evidence is in
`.tools/navigation-review/` (`menu-red`, `links-red`, `company-links-red`,
`tenant-links-red`, `year-links-red` and `year-generation-red` logs). Existing tests
were updated where this delivery intentionally replaces flat menus, inert entries,
old hub admission, labels or return URLs; API mutation assertions remain intact.

Validation:

- Full console suite: **1,348 tests across 118 files pass**. A final additional year
  generation regression and the page-prop fixes pass in the **48-test** company/year
  follow-up. These runs cover 1,349 distinct console tests.
- Shared UI: **1,825 tests across 60 files pass**, including four `RailGroup` tests.
  Coverage passes all gates: **99.32% statements/lines, 94.57% branches and 99.37%
  functions**; overall coverage holds or improves against the preceding review.
- Console and shared UI type checks pass. The isolated production build passes;
  its generated config changes were checked and restored from this turn's exact
  snapshots. The running console's `.next` was preserved.
- **158 browser checks pass** at 1440px and 390px. Menu disclosure/current items were
  checked in light, dark and ledger themes. Filtered view/edit/cancel/back flows,
  role → assignment → group → return, child creation, draft confirmation, company
  editing and tenant editing pass with no page errors or document overflow.
  Desktop/mobile menus and company breadcrumbs were visually inspected. Screenshots
  and results are in `.tools/navigation-review/browser/`.
- Console coverage is **97.83% statements/lines, 85.07% branches and 80.35%
  functions**. Branch coverage now clears the 85% floor (previously 84.81%). The
  coverage command still exits nonzero because the existing 90% global function
  floor is unmet; the previous result was 80.17%. No thresholds were lowered.
- Final whitespace check passes.

Manual simplification and security/correctness review walked CLAUDE.md §§5–6.
The named `/simplify` and `/security-review` commands are unavailable in this
session, so the equivalent review was performed directly. Findings fixed during
review: destination-specific lifecycle filter validation, year generation and
breadcrumb return context, and Next.js's required page-prop type constraint.
Return destinations accept only implemented internal read routes, reject external
origins/control characters, validate query keys and bound nesting. Navigation
visibility uses existing scope helpers; server admission and financial mutations
remain independent. No remaining navigation defect was found within these checks.

Browser validation uses real console components and shared CSS with fixture BFF
responses; it submits no live changes and does not claim a live Authentik login or
a production release. Only the owned temporary review server was stopped. Existing
application services and user work were preserved. Changes are local and uncommitted.
