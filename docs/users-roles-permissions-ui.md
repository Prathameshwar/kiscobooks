# Users, roles and permissions UI delivery

Requested 2026-10-24: implement the administrative UI end to end, reusing shared
styles, layout, navigation, tables, kebab actions, forms and searchable selectors.

## Phases

1. Define typed access adapters, narrow proxy allowlists, tenant/scope-aware UI
   permissions and safe navigation. Add regression tests before fixes. Establish
   the API contract and preserve existing unrelated changes.
2. Implement users directory, invitation and profile edit/detail pages with status
   actions, invitation history/resend/cancel, validation and clear messages.
3. Implement role directory/detail/create/edit/clone and a searchable fixed
   permission catalogue. Preserve system-role immutability and show separation of
   duties warnings. Send only changed role fields.
4. Implement scoped assignment directory/create and revoke/regrant actions. Resolve
   users, groups, roles, companies and departments through searchable lookups;
   preserve reasons, validity, no-self-assignment and scope/delegation safeguards.
5. Review security/correctness and simplification; run affected unit/API tests,
   TypeScript, production builds and desktop/mobile browser workflows. Record
   findings, fixes and practical validation limits.

Each phase ends with its affected tests passing. The user authorized phased
implementation and review; no commit, publish or changes to live user access are
requested. API changes are included only where the implemented workflow requires
them and must include contract/client synchronization.

## Governing contracts

- Users belong to the tenant. Tenant-level user permissions are required for its
  global directory/profile/lifecycle; a company grant reaches only the new current
  company-affiliation projection and new-person invitation path. See the follow-up
  [access experience review](access-experience-review.md).
- Role reads and assignment reads are scoped by Identity. Role management requires
  tenant authority. Permissions are a fixed code catalogue; the UI cannot create keys.
- System roles cannot be edited or deactivated; customisation means cloning.
- Membership is affiliation, not authorization. Assignment grants are independent.
- Composition and grant changes remain subject to held permissions, target scope,
  no self-modification, group membership and field-policy checks in Identity.
- Initial financial-authority provisioning is an existing open policy decision
  ([access-control-fixes](access-control-fixes.md)); this UI retains those guards and
  presents their denials. It does not invent a bootstrap exception.
- Passwords, MFA and provider connections remain with Authentik. User deactivation
  anonymizes irreversibly; suspension/resumption are separate status transitions.
- Most existing admin writes do not support command idempotency. They must not be
  automatically replayed after an uncertain response. Preserve the draft and require
  review/reload before repeating. Invitation resend supports its actual idempotency key.
- Field metadata currently protects registered company entities, not these user/role
  forms. Forms use the generated UserInvite/UserUpdate/Role schemas; no unimplemented
  user field-set endpoint will be invented.

## Execution

All five phases are implemented and reviewed. The final API suite passes; UI
interaction tests, TypeScript, production build and browser review pass. The
existing console coverage-gate limitation is documented below.

### Delivered routes and actions

| Area | Pages | Actions |
| --- | --- | --- |
| Users | `/users`, `/users/new`, `/users/{id}`, `/users/{id}/edit` | Search, status/type filters, cursor paging, kebab view/edit, invite, profile update, invitation history/resend/cancel, suspend/resume, typed confirmation before irreversible anonymization |
| Roles | `/roles`, `/roles/new`, `/roles/{id}`, `/roles/{id}/edit`, `/roles/{id}/clone` | Search, scope filter, paging, kebab view/edit/clone, searchable permission multiselect, separation-of-duties warnings, custom-role deactivate/reactivate |
| Permissions | `/permissions` | Read-only catalogue, resource/search filters, paging, tenant authority indicators |
| Assignments | `/assignments`, `/assignments/new` | Role/user/group/scope/state filters, searchable subjects and scope, review before grant, reason and inclusive validity dates, kebab revoke/regrant |

All pages use the existing console shell, navigation, cards, shared forms, tables,
kebab menus, dialogs, searchable selectors, error states and formatters. There are
no new application CSS rules or runtime dependencies. Tenant changes remount the
screens so drafts, cursors, labels and pending callbacks cannot cross tenants.

### API and client synchronization

- `GET /v1/user-groups?q=` searches the indexed **code prefix**, with 2–40 characters.
- `GET /v1/companies/{company_id}/departments?q=` searches the company-bound indexed
  **code prefix**, with 2–20 characters. Wildcards are escaped; existing department
  scope filtering is retained. Group and department name searches are not claimed.
- `GET /v1/session/companies?id={uuid}` and the department list's `id={uuid}` resolve
  saved selections without scanning pages. They retain visibility, tenant/object
  permissions and field-policy projection; inaccessible choices return no row.
- Assignment directory rows add optional `role_name`, `subject_label` and
  `scope_label`. Names are resolved in bounded queries. User/group names require
  their tenant directory authority; company/department names require object read
  authority. Company names also pass through `CompanyAccess` field-policy projection.
  A denied label is null and the existing authorized assignment reference remains.
- OpenAPI and `clients/api-client/src/identity.d.ts` are regenerated. The API client
  is version **0.2.11**, its npm lock is synchronized, and workspace consumers use
  the linked package. No database/model migration is needed.
- The full API run exposed a pre-existing company setup check-order mismatch.
  `_active_company` now checks endpoint authority, loads through the tenant filter,
  then checks company scope. This retains 403 for unauthorized same-tenant objects
  and 404 for a foreign-tenant object. The existing failing isolation test is the
  regression check; company setup checks are rerun after this small fix.

### Review findings and corrections

- Narrow proxy routes reject unsupported methods, duplicate query keys, path
  normalization, encoded separators and unexpected query parameters.
- Corrected validation focus so typing in one field cannot jump to another invalid
  field. Calendar dates reject malformed/rolled dates without throwing.
- Corrected derived table cells to use the shared table's `value`/`custom` contract.
- Metadata-only PATCH requests omit unchanged permission sets and profile fields.
  Changing a default company clears its dependent department selection.
- Valid uppercase UUID routes accept canonical lowercase response IDs after a save.
  Two failing regression tests were added before correcting the comparisons.
- Keyless writes freeze after an unconfirmed response and require record/directory
  review. Regrant retries retain the original key and body; input edits are locked
  until a definite response. Cancelling an uncertain regrant reloads the directory.
- Pending writes cannot be duplicated; callbacks after unmount are ignored.
- Editors confirm discarding a draft before Cancel, the back link or access-area
  navigation. Browser unload and company-switch guards also retain unsaved work.
- System roles remain immutable; self user suspension/anonymization and direct
  self role assignment are prevented. Group self-membership, held authority, scope,
  role lifecycle and field-policy guards are still enforced by Identity.
- Reviewed company label projection with a failing field-denial regression before
  the fix. A role reader cannot use assignment labels to recover a protected name.

### Validation evidence and limits

Browser review uses the real console components and shell with fixture API data.
It covers user invitation/profile/lifecycle/history, role composition/edit/clone,
department assignment review, revoke and keyed regrant retries, catalogue filters,
read-only controls, saved reference labels, discard navigation and layout overflow.
**66 checks passed**, no page errors, at
1440px/390px across light/dark/ledger. Screenshots and runner are local ignored
artifacts under `.tools/access-browser-review`; live business access was not changed.

The console full suite passed **1,184 tests across 103 files**. Four additional
navigation/canonical-UUID cases pass in the final affected runs: **48 tests** for
all access interactions after navigation changes, then **39 tests** for user/role
and review interactions after the UUID fix. Console TypeScript and the production build pass, as do generated
client checks, client TypeScript and all **8 client tests**. The final build uses
an isolated output directory; its generated changes to the live console's
TypeScript route references were restored after verification.

| Console coverage | Prior baseline | Final full run |
| --- | ---: | ---: |
| Lines/statements | 97.50% | 97.65% |
| Branches | 83.60% | 84.28% |
| Functions | 78.50% | 79.59% |

All overall measures improved. The existing global branch/function gates remain
below their configured 85%/90% requirements; no gates were lowered or excluded.
This causes the coverage command to exit unsuccessfully even though its tests pass.

The affected access/API checks passed **35 tests**, and the setup regression and
its related checks passed **45 tests**. Ruff and strict mypy pass for the touched
API modules. The final full Identity API suite passed **1,813 tests**, with **one
existing skip**, and reached **92.51% coverage**, exceeding its 90% requirement.
The complete suite was rerun after correcting the setup check-order failure.

The browser fixtures do not prove live invitation delivery or real Authentik login.
Those retain their existing provider/notification implementations. MySQL-container
tests are excluded from the SQLite API suite. Initial financial-authority policy
remains the documented administrative constraint.
