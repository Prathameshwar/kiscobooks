# Access-control remediation — 2026-10-22

Authorized after the [roles and permissions review](access-control-review.md).
Phases: fix administrative delegation and policy revocation; implement the Console
access-management surface; verify regressions and security invariants. Initial
financial-role provisioning needs a separate authority decision, requested from
the user under CLAUDE.md's rule “Don't silently answer an open question.”

## Implemented fixes

| Review finding | Result |
|---|---|
| Assigned custom-role edits bypass assignment safeguards | Permission changes check every active, unexpired assignment, including scheduled grants. The editor needs `role.assign` at each affected scope, must hold the old and new permission sets there, and cannot change their own or their group's grants. Metadata remains separately editable. |
| Group membership grants field access the editor lacks | Membership addition/removal and group lifecycle reuse the direct field-delegation check. Both allow and deny policies are checked because removing a deny can restore access. Roles with field policies receive the same checks on assignment, revocation, regrant and lifecycle. |
| Catalog/Vouchers policies cannot be revoked | The update path recognizes all five registered document entities. Existing immutable subject/field/scope, endpoint permission, field delegation and tenant checks remain enforced. |
| Role changes lack reconstructable audit evidence | `role.updated` records permission keys before/after and separation-of-duties warnings. Creation's warning key now matches the audit allowlist. Policy updates record active state and allow/deny effect. Events use the existing transactional outbox. |
| Console role route absent and account classification mislabeled | `/roles` displays paged roles, concrete permissions and scoped assignments; authorized users can create/edit/clone roles, assign expiring access, and confirm reasoned revocation. The account chip identifies account classification. |
| Client wildcards disagree with backend | UI permission gates require exact keys. Wildcards confer no UI authority. Component tests now reflect that behavior. |
| Department grants discarded for access review | The session retains grant scope and validity. Only valid `role.read`/`role.assign` keys are recognized across scopes for access-directory controls, sidebar and palette; business and role-composition authority is not flattened. Identity filters reads and checks mutations against the real scope. |

The field-authority helper is service-owned and shared by direct and indirect
delegation paths. Conditional denies are considered potentially applicable;
conditional allows cannot authorize unrestricted delegation. Policy and assignment
scans are bounded at 1,000 and fail closed above that bound. This is a processing
bound, not a newly introduced policy-creation quota.

The Console `/api/access` proxy permits only declared Identity access endpoints,
methods and query keys. It reuses the same-origin, bounded-body, server-held-token,
expiry, configured-origin, redirect rejection and no-store mechanisms. Browser
permissions are visibility hints; upstream errors retain the entered draft. A
revocation requires a fresh reason in its confirmation dialog; a previous grant's
reason is not silently reused. The initial UI accepts exact subject/scope IDs;
named subject directories and role/group lifecycle screens remain future work.

No backend route/schema, permission key, role seed, dependency, shared Python
library, model or migration was changed by this remediation. The generic existing
audit changes contract already supports the added safe keys. Audit consumer
envelope/version handling is unchanged.

## Validation

- Focused Identity authorization, role, lifecycle, field customization, cache,
  audit, credential and authentication regressions: **84 passed**.
- Shared UI full suite: **1,781 passed across 57 files**; coverage gate passes
  (99.39% lines/statements, 94.38% branches, 99.35% functions). Permission gates
  have 100% coverage.
- Final Console full suite: **769 passed across 71 files**; final role-form/proxy
  tests: **20 passed**. Coverage gate fails at 79.06% functions and 84.75% branches
  against 90%/85%, despite 97.95% lines/statements. The new roles directory has
  97.87% lines, 90.69% branches and 93.33% functions; the new access route and
  scoped-permission helper have 100% coverage. Untested functions in existing
  banking, voucher, company and platform screens dominate the global deficit.
  Thresholds and unrelated screens were not changed to bypass this gate.
  Excluding only the new access/roles files from that same report gives 78.34%
  functions and 84.44% branches, confirming the remaining deficit belongs to
  existing files; this is not a clean pre-change coverage baseline.
- Final access-control regression file: **20 tests**, covering mixed-company
  edits, assignment/revoke/regrant/lifecycle field exceptions and audit conflict
  evidence. All pass within the final complete-file rerun below.
- Audit signed delivery and ingestion compatibility regressions: **29 passed**.
- Ruff checks/format and strict mypy on affected Identity files; Console and UI
  TypeScript checks pass.
- Full non-MySQL Identity regression/coverage run: **1,723 passed, 1 skipped,
  2 failed** in 22m57s; overall coverage **92.41%**, domain directory **98%**,
  field-delegation helper **97%**. Both failures were test-contract drift:
  the previous group policy test omitted the newly required `company.read`, and
  a platform rollback test expected an exception instead of the existing
  sanitized HTTP 500. The assertions were corrected while preserving rollback
  checks; all three formerly failing parameter cases pass on rerun. A final
  rerun of both complete files plus new access regressions: **123 passed**.
  The entire 22-minute suite was not repeated after these assertion-only changes.

Initial full UI failures were three outdated wildcard fixtures and seven Console
timeouts while large suites ran with unrestricted parallel workers. Wildcard
fixtures were corrected for the new intentional behavior. The complete suites
passed with bounded workers; no global timeout was increased. Existing platform
audit tests emit React `act` warnings while passing.

Identity OpenAPI verification reports pre-existing working-tree drift only on
`/v1/companies/{company_id}/display-config`, with no changed schemas. This change
does not alter that endpoint or overwrite concurrent company work.

## Security and simplification review

Manual review walked CLAUDE.md §§5–6: tenant-bound request sessions and tenant
locks precede reads/mutations; actual company/department ancestry is resolved;
expired grants do not authorize changes; future assignments cannot evade edit
checks; live group membership protects self-modification even when absent from
signed actor headers. Denied operations roll back both rows and outbox evidence.
System roles remain immutable, scopes unrelated to a role policy are excluded,
and a client cannot introduce tenant or permission authority through proxy input.
Audit differences contain concrete permission keys and policy states, without
new denormalized profile data. Existing money admission, posting, period,
idempotency and immutable-history rules are preserved.

Simplification reuses the existing assignment guards, direct field-delegation
logic, shared proxy, generated Identity types, UI primitives and signed cursors.
No second authorization engine or custom CSS was introduced. `/simplify` and
`/security-review` tools are unavailable in this session; equivalent reviews
were performed manually. No additional confirmed security defect in these fixes
was identified. This is source/test evidence, not live deployment certification.

## Phase-by-phase review pass — 2026-10-22

`/code-review` was run per phase (policy revocation, indirect delegation, role
edits) once the three fixes were in the tree. Eight findings; five applied, three
recorded as decisions rather than changed.

Applied:

- **The actor's own field authority is resolved once per request.** The indirect
  checks ask the same question repeatedly — a group join iterates its role
  assignments, and each role its policies — and each call loaded the editor's
  authority again (`CompanyAccess.load`, or the policy scan). With the declared
  1,000-row bounds that permitted ~10⁶ resolutions on one `POST`. A request-scoped
  memo (`services/field_delegation.DelegationCache`) holds the actor's authority,
  the per-role policy list and the checks already settled; the request holds the
  tenant lock, so no row can change under a reused list. Pinned by a test that
  asserts one resolution for a join carrying three policies.
- **A policy naming an unregistered entity is skipped** rather than failing the
  edit of whatever role carries it ([field-permissions](field-permissions.md) §13).
  The membership test is now one `registered()` helper, used by the update path too
  instead of a third copy of the entity list.
- **Condition changes are audited** on `field_policy.updated`, as a changed-field
  marker. A deny whose condition was narrowed previously recorded an apparent no-op.
- **Metadata-only role edits emit a real diff.** `role.updated` carried
  `changes={}` for a rename; it now records name, description and `scope_hint`,
  the first two as markers. The same path returned an empty
  `separation_of_duties_warnings`, which read as "the conflict is resolved" to the
  console; it now reports the pairs the role still holds.
- **The audited permission set is the stored one.** `RoleUpdate.permissions` has no
  uniqueness validator, so a repeated key made the security event disagree with
  `role_permission`.
- Row-bound overflows raise a validation failure, not a permission denial, matching
  `services/accounting_context` on the same bound and the same table.

A scoped security review of the five changed files against CLAUDE.md §§5-6 found
**no reportable vulnerability**, and recorded the bypass paths it checked closed:
guard coverage by constructor/delete sweep (every writer of `role_assignment`,
`role_permission`, `user_group_member` and `field_policy` reaches a guard before the
write), the scope intersection against how role-subject policies actually resolve,
subject/scope confusion between user and group subjects, `DelegationCache` key
completeness and lifetime, `registered()` failing open, tenant isolation through the
session filter, and scope-probing or PII in denials and audit payloads.

It did surface one **functional** defect, pre-existing and fail-closed, which this
remediation's own contract depends on. A group-level change has no joining user to
name, and the placeholder passed for it was `uuid.UUID(int=0)` — which *is* the
`SCOPE_ALL` sentinel, so `AssignmentChange` rejected it as a subject. Every
`DELETE /v1/user-groups/{id}/members/{user}` and `POST
/v1/user-groups/{id}/lifecycle` on a group holding an active, unexpired role
assignment answered 422, so "removal and group lifecycle are checked too" was in
practice "refused outright". The subject of such a change is the **group**, which is
what the guards are now given; guard 2 then refuses an actor who belongs to it, as
`guard_group_change` already did with a clearer message. Caught by a failing test
first (both parameter cases returned 422 for exactly that reason), then fixed: an
authorized removal and deactivation now succeed, and an editor who cannot grant what
the group carries is still refused.

Recorded, not changed:

- Joining a **restriction-only** group, and withdrawing an exception, both require
  field-policy administration and the access concerned. Consistent with the direct
  path and with this remediation's own tests; the lockout consequence is stated in
  [field-permissions](field-permissions.md) §13. Making the check direction-aware —
  allow policies when a change extends access, deny policies when it withdraws —
  is a policy change to a just-documented contract, so it is the user's call.
- Editing an in-use role now needs `role.assign` as well as `role.manage`. Intended,
  and the review asked for it; now stated in
  [roles-permissions](roles-permissions.md) §1.5 rather than only in a guard's
  error message.

Second-pass verification: access-control regressions **26 passed** (six tests added —
the authority-resolved-once count, the condition marker with its no-op counterpart,
the audited rename, the unregistered-entity skip, and the two group-level change
cases); role, org, lifecycle, customization and policy suites **62 passed**.

Full Identity suite with coverage: **1,735 passed, 13 skipped** in 27m, total
coverage **92.39%** against the configured 90% gate. `domain/authorization.py` is at
100% and no `domain/` module is below the floor; the new field-delegation helper is
at 94%, `api/roles.py` 95%, `api/customization.py` 91%, `api/security.py` and
`api/lifecycle.py` 88%. The previously recorded 92.41% was measured on a tree with
two failing tests and before other concurrent Identity edits, so the 0.02-point
difference is not attributable to this change; the full run also predates the
unregistered-entity test, which only adds covered lines. Ruff and strict mypy clean
across 179 Identity sources. The Identity OpenAPI check reports one difference
against the committed contract — the `display-config` description belonging to the
concurrent company-context work — and nothing from this change, so `openapi.json`
was deliberately not regenerated.

## Pending policy and remaining scope

Financial-role provisioning for a new tenant remains blocked by the existing
held-permission delegation rule. The pending choice is either narrowly authorize
tenant admins to assign approved shipped business roles to other users at company
scope with fresh authentication and audit evidence, or implement an audited
operator-controlled initial provisioning path. Neither exception is implemented
until the authority model is selected; custom-role delegation remains guarded.

The review's broader observations—guarded-session adoption in legacy adapters,
customer-owned portal enforcement and general effective-user separation-of-duties
policy—remain separate work. The existing role-conflict policy warns on custom
composition; it does not enforce a universal maker/checker system.

Live MySQL/Redis/provider/gateway/browser verification is not included in the
in-process tests. Platform-audit runtime activation and issuer allowlist checks
remain documented in [platform-audit-review.md](platform-audit-review.md).
Concurrent working-tree edits are preserved. No commit or publication performed.
