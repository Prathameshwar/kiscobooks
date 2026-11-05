# Organisation and access delivery

Requested 24 October 2026: inspect and complete Tenants/Workspaces, Companies,
Departments, Users, User Groups and Roles, including UI and a final review.

## Quick plan

1. Check existing implementation and contracts. Preserve the working tenant,
   company, user and role workflows. Fill department/group detail, directory and
   form-metadata gaps; verify tenant/company/department authorization and audit.
2. Deliver missing department and user-group administration with shared layouts,
   searchable selectors, validation, directories, kebab actions and navigation.
   Include department parent changes and lifecycle, group member add/remove and
   lifecycle. Keep affiliation separate from authorization and confirm security
   changes before submitting. Generate API/client contracts together.
3. Run affected suites and broader checks, inspect rendered mobile/desktop flows,
   review all six areas against security/correctness rules, and fix findings.
   Recheck database/model/script alignment if contracts require storage changes.

The user authorized phased implementation and the final review in the request.
Existing nested-department behavior is retained; this task does not resolve the
open product question of whether nesting should be required at launch. No new
tenant switching, credential ownership or permission catalogue is introduced.
Tenants are workspaces; company affiliation does not grant permissions.

## Initial implementation check

| Area | Existing implementation | Work identified |
|---|---|---|
| Tenants/Workspaces | Platform directory, create/detail/edit and lifecycle | Verify routes, validation, access and navigation |
| Companies | Directory, create/detail/edit, setup/readiness and fiscal years | Verify scoped entry points and links |
| Departments | Create/list/update/reparent/lifecycle APIs | Administration UI, detail contract, form metadata and navigation |
| Users | Tenant directory/profile/invitation/lifecycle; company people projection/invite | Verify scoped workflows and links to groups/departments |
| User Groups | Create/list/update/lifecycle/member APIs | Administration UI, detail/member labels, directory filters and navigation |
| Roles | Directory/detail/create/edit/clone, permissions and scoped assignments | Verify group subject integration and action safeguards |

## Delivery and verification

The three implementation phases are delivered. Verification and review results
are recorded below.

### Routes and behavior

| Master | Entry point | Delivered workflow |
|---|---|---|
| Tenants/Workspaces | `/platform/tenants` | Existing platform directory, create/detail/edit, administrative invitation and lifecycle workflows verified |
| Companies | `/companies/manage` | Existing scoped directory, setup/create/detail/edit, financial readiness and fiscal-year navigation verified |
| Departments | `/departments` | Company directory, indexed code search, status filter, cursor paging, create/detail/edit, head-user selection/link, child creation, reviewed parent change and deactivate/reactivate |
| Users | `/users` | Existing tenant and company people workflows verified; selected-company affiliations now support reviewed add, end and make-primary actions |
| User Groups | `/user-groups` | Tenant directory, indexed code search, status filter, paging, create/detail/edit, reviewed membership addition/removal and deactivate/reactivate; links to scoped role assignments |
| Roles | `/roles` | Existing directory/detail/create/edit/clone, permission composition and scoped assignment/revoke/regrant flows verified; lifecycle draft/navigation guard corrected |

The main navigation and organisation landing page expose the missing masters.
Related access pages share links through `AccessNavigation`. Existing shared
controls, CSS, tokens and layouts are reused; no package or app styles were added.
Department/group forms render descriptors derived from their strict API input
schemas. They do not claim new custom-field or field-policy support for these
unregistered Identity entities. Existing company field policies remain intact.

Affiliations on user details apply explicitly to the selected company. Tenant
administrators can affiliate an existing tenant user; company administrators can
manage affiliations for people they may already read in that company. Adding an
affiliation grants no role. Invitations and account-wide profile/lifecycle changes
retain their independent authority. Primary changes validate both the new and
previous primary scope on the server; invited users cannot be made primary in the UI.
Ended affiliations remain historical and cannot be silently recreated over the
existing unique association; the API reports a conflict instead.

### Authority and safety review

| Actor | Administration behavior |
|---|---|
| Platform administrator | Platform tenant/workspace administration follows the explicit platform grants. Platform classification does not grant authority over tenant users, groups, companies or departments. |
| Tenant administrator | Tenant-scoped grants authorize the corresponding tenant directories and company descendants. Role composition and assignment still require held authority and pass independent server delegation checks. |
| Company administrator | Manages authorized company departments and current people affiliations using company grants. Tenant group writes and account-wide user profile/lifecycle remain unavailable without tenant grants. |
| Department administrator | Reads the authorized subtree, edits its authorized departments and creates children under an authorized parent. Root creation/moves require company-wide or tenant authority. Source and destination are independently checked for a move. |
| Ordinary user/reader | Sees only authorized directories/details and self-service access. Management actions are absent; membership and affiliation do not implicitly confer administration. |

There is no entity hard-delete UI. Group member removal uses the existing audited
association removal; user accounts, group records and historical audit evidence are
retained. Keyless writes freeze after an uncertain result until the administrator
reloads and reviews. Pending writes block navigation and company changes. Parent
choices exclude self, descendants and inactive/unmanageable destinations, while
the server remains authoritative for ancestry, depth and access checks.

### Contracts and review fixes

- Added authorized department/group detail reads and scoped form-descriptor reads.
  Department and group directories now use dedicated lean list projections,
  bounded signed cursor queries and typed status/ID filters. Existing default
  group ordering remains compatible; the UI requests indexed code ordering.
- Group-member names are resolved in one bounded query and disclosed only with
  tenant-wide `user.read`. Department head labels use the authorized user detail
  surface. Selected-company membership filters cannot cross the company boundary.
- Blank organization names/codes and control characters are rejected by the API.
  Optional text normalizes to null. Inactive departments reject edits/reparenting,
  matching their form metadata. Group codes remain fixed after creation.
- Fixed successful HTTP 204 handling in the JSON proxy, so member removal is
  reported as success. Destructive kebab items use the shared danger treatment.
- Fixed form load retry, user/role lifecycle draft guards, member-selection guards
  before group status changes, and parent/child in-flight navigation guards.
  Confirming a discard no longer triggers a second unload prompt.
- Corrected the shared unsaved-change guard's commit timing. Its listeners now
  update before paint, so a just-loaded or just-saved form does not retain a stale
  dirty-state decision during a company change. Two deterministic regressions
  cover newly dirty and newly saved state; existing reference tests exposed the
  same issue in the broader run.
- Fixed affiliation display rendering and department action spacing using the
  existing shared layout. Create-only users are not offered unreadable detail links.
- Tightened the child-department creation page guard: a direct parent-prefilled
  URL still requires an active management grant. Read-only departmental users see
  the permission guidance, while the API independently checks the actual parent.
- OpenAPI, generated Identity client and consumers are synchronized at client
  version 0.2.14. No model, migration, permission catalogue or startup-script change
  was needed. All seven current schemas were rechecked read-only.

Each identified bug was reproduced by a failing regression before its fix.
Manual simplification and security/correctness review covered CLAUDE.md sections
5 and 6. The named `/simplify` and `/security-review` commands were unavailable;
equivalent manual reviews were performed. Money execution, financial activation,
credential ownership and live stock were outside this delivery and preserved.

### Verification evidence

The final full console suite passed 1,319 tests across 113 files. Identity's affected
suites passed 66 tests, and Ruff and strict mypy passed. All eight API-client tests,
generated contract checks and client type checking passed. Full test/build/browser
logs and schema comparisons are retained under ignored
`.tools/organisation-access-review/`.

Console coverage is 97.83% statements/lines, 84.81% branches and 80.17% functions.
The existing global branch/function floors (85%/90%) still fail; thresholds were
not lowered. Before this delivery the same workspace measured 97.75% statements,
84.63% branches and 80.11% functions. Two timing-sensitive existing suites failed
during concurrent verification and passed standalone. A later broader run caught
the shared guard's stale committed-state decision; it was reproduced and fixed
in the guard used by the reviewed pages. Existing test files were preserved.
The final full run passed every test after the fixes, with two workers.

The final isolated production build passed and preserves the live `.next` directory.
The standalone console TypeScript check passed. Its earlier run caught a malformed
parameterized route-test fixture; the corrected test passes each complete segment
array to the page. The last child-creation guard regression was reproduced and
fixed; all 47 affected organisation UI/page tests passed afterward.
After the shared commit-timing fix, all 129 affected tests across six suites passed.

The browser review passed 154 checks with no page errors or horizontal document
overflow at 1440px and 390px in light, dark and ledger themes. It covers all six
directories, detail pages, department/group create and edit forms, user editing,
lower form actions, validation/create, parent-change confirmation, member add/remove,
pending/draft guards, uncertain-write recovery and affiliation confirmation.
Rendered forms, action rows and review dialogs were visually inspected. Its fixture
scaffold uses the same root class and shared shell/styles as the production console.
The final manual security/correctness review found no remaining organisation/access
defects within these tested boundaries.

The browser review uses real components with fixture BFF responses; independent
API tests cover server contracts. It does not claim a live Authentik administration
workflow or a production release. Running services were preserved. Updated API
routes and console pages load through their normal service restart/build workflow.
A final read-only Windows health check reported all eleven backend components UP.

The subsequent [administration navigation review](administration-navigation-review.md)
records the menu/submenu, breadcrumb, return-context and draft-navigation fixes
requested after this delivery, together with their final validation evidence.
