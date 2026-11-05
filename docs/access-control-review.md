# Roles, permissions and access-control review

Reviewed 2026-10-22 against the current working tree. This is a review of implemented behaviour, including local changes already present. Application code was not changed during this review.

> **Status: findings 1-3 are fixed**, and each fix has since been reviewed per phase.
> See [access-control-fixes.md](access-control-fixes.md) for the implementation,
> the regression evidence and the review findings applied on top. Finding 4 is a
> provisioning-authority decision and remains open; nothing was implemented for it.

Remediation update: the three P1 findings below have now been fixed with regression
tests, audit permission differences, and a Console Roles & access page. Wildcard UI
gates and scoped access navigation were corrected too. The original review below
preserves the evidence before remediation. See [access-control-fixes.md](access-control-fixes.md)
for current implementation, validation and outstanding financial-provisioning policy.

## Assessment

The platform has a substantial authorization foundation: server-resolved scoped RBAC, field-policy refinements, signed gateway contexts, tenant filtering, restricted platform authority and read-only support sessions. Four confirmed gaps need attention. Two bypass delegation safeguards; one prevents field-policy revocation; one blocks financial-role provisioning for a fresh tenant. Passing existing tests did not cover these cases.

| Priority | Finding | Evidence |
|---|---|---|
| P1 | Editing an assigned custom role bypasses assignment safeguards | Direct assignment denied with 403; permission replacement accepted with 200 and changed the subject's live grants, including the editor's own assignment |
| P1 | Group membership bypasses field-access delegation safeguards | Direct field allow denied with 403; joining a group accepted with 201 and made the subject allowed while the editor remained denied |
| P1 | Catalog and Vouchers field policies cannot be updated or deactivated | Policy creation returned 201; deactivation returned 404; subsequent listing showed the allow still active |
| P2 | Fresh tenants have no supported path to provision financial roles | The only initial role is `tenant_admin`; assigning even a controller role containing only `ledger.post_journal` returned 403 |

P1 denotes a security safeguard bypass or inability to revoke an access exception. These are authenticated administrative paths, with the prerequisites described below; no anonymous or arbitrary cross-tenant exploit was demonstrated.

## Confirmed findings and fixes

### 1. Assigned-role edits need assignment authorization

Location: [roles.py](../apis/identity/src/identity/api/roles.py), `update_role`, lines 190-252. Compare [lifecycle.py](../apis/identity/src/identity/api/lifecycle.py), `role_lifecycle`, lines 400-440.

`PATCH /v1/roles/{role_id}` checks tenant-scoped `role.manage`, system-role immutability and whether the editor holds the proposed permissions. It replaces `RolePermission` rows without checking the role's existing assignments. Editing a role therefore changes effective user/group authority without requiring `role.assign` or rejecting a role assigned to the editor.

An in-process HTTP probe created an empty custom role with an existing user assignment. The editor held tenant-scoped `role.manage` and `invoice.read`, but no `role.assign`. A direct assignment returned 403. Updating the assigned role to contain `invoice.read` returned 200, and `live_grants` then contained that permission for the subject. The same sequence succeeded when the subject was the editor.

Impact: an editor can delegate permissions they currently hold through role composition despite lacking assignment authority, and can change their own effective role. This does not establish an ability to compose arbitrary unheld permissions. It can nevertheless preserve permissions through an independent assignment after another grant expires or is revoked.

Recommended fix: treat permission changes to assigned roles as access changes. Check every relevant active or scheduled user/group assignment against `assignment_actor`, the assignment's actual scope and the shared assignment-change guards. Reject self/group modifications, and check the affected old/new permission sets so removal cannot bypass administration rules either. An unassigned role can remain a composition-only operation. Make the checks and mutation atomic under the existing tenant lock. Add regression tests for other-user, own-user, own-group, scheduled and mixed-scope assignments.

Audit follow-up: `update_role` emits `role.updated`, but its payload lacks the permission before/after set and the returned separation-of-duties warnings. Creation records conflict warnings; updating does not. Include safe permission keys and conflict evidence so reviewers can reconstruct an access change.

### 2. Group joins need effective field-delegation checks

Location: [security.py](../apis/identity/src/identity/api/security.py), `guard_group_join`, lines 86-133; [org.py](../apis/identity/src/identity/api/org.py), `add_group_member`, lines 369-433. Related group lifecycle/removal logic is in [lifecycle.py](../apis/identity/src/identity/api/lifecycle.py), `guard_group_change`.

The direct field-policy guard checks both endpoint authority and whether the editor actually has the field access they are trying to delegate. The group-join path finds an active group allow policy and requires only tenant-scoped `field_policy.manage`. Role-assignment guards run for group roles, but equivalent field-specific checks do not run for group policy effects.

The probe applied a tenant-wide read deny for `identity.company.credit_limit_default` to the editor and recipient, and a company-scoped allow to an initially empty group. The editor held `group.manage`, `field_policy.manage` and `company.read`. Creating the company-scoped allow directly for the recipient returned 403. Adding the recipient to the group returned 201. The normal `CompanyAccess` resolver then allowed the recipient's field while continuing to deny it to the editor.

Impact: a more-specific group allow can override a broader deny and delegate access the editor lacks. The probe did not add the editor to their own granting group; that explicit self-join guard works.

Recommended fix: evaluate effective field-access changes caused by membership and group lifecycle changes, using the same registered fields, scopes, conditions, endpoint permission and no-self/no-unheld-delegation rules as direct policy administration. Include removal of memberships or deny policies when it would widen effective access. Add tests for tenant-deny/company-allow, conditional policies and group activation.

### 3. External document policy update rejects supported entities

Location: [customization.py](../apis/identity/src/identity/api/customization.py), `update_policy`, lines 555-565. Compare `guard_policy` at line 425 and `policies` at line 604; supported contracts are in [document_fields.py](../apis/identity/src/identity/domain/document_fields.py).

Creation and listing accept registered Catalog/Vouchers document entities. Update accepts only `identity.company` or an Accounting contract. It returns `policy not found` for a policy whose entity is in the external document registry.

HTTP probes confirmed the issue for `catalog.item.sku` and `vouchers.voucher.document_date`: create 201, deactivate 404, list still active. The same registry mismatch also affects `catalog.product_family`, `vouchers.voucher_item` and `vouchers.configuration` by inspection.

Impact: a previously allowed field exception cannot be revoked through this API. Deny policies also cannot be relaxed or corrected. Affected administrators may be driven to database intervention.

Recommended fix: use the same registered entity validation across create, list and update. Preserve immutable subject/field/scope checks and rerun `guard_policy` before mutation. Test allow-to-inactive, deny-to-inactive and effect changes for every supported entity family, including unauthorized and foreign-tenant callers.

### 4. Initial tenant roles cannot reach financial provisioning

Location: [tenant_provisioning.py](../apis/identity/src/identity/services/tenant_provisioning.py), fixed `tenant_admin` lookup at line 117 and initial assignment around line 161; [authorization.py](../apis/identity/src/identity/domain/authorization.py), `assert_permissions_held` and `assert_assignment_change_allowed`; [system_roles.py](../apis/identity/src/identity/domain/system_roles.py).

Provisioning grants the first administrator only `tenant_admin`. Delegation deliberately requires the granter to hold every permission in the target role at the assignment scope. `tenant_admin` has organization/configuration authority and limited books-bootstrap keys, but lacks transaction, posting, operational reporting and many master-data permissions.

Catalogue comparison found that `company_admin`, `billing_clerk`, `billing_approver`, `accounts_clerk`, `controller`, `viewer` and `tenant_auditor` each contain keys the initial administrator does not hold. An HTTP probe using the exact shipped tenant-admin permission set could not assign even a minimal controller role containing only `ledger.post_journal` (403). The full controller contains 58 keys outside tenant-admin's set.

Platform administration is not an escape hatch: it has no tenant-business assignment authority, and support is read-only. Cloning/composition requires already-held permissions too. Additional role seeding creates role definitions; it does not assign an initial financial authority.

Impact: a tenant provisioned solely through the supported bootstrap cannot establish its financial operating users without separately provisioned authority. This is a workflow dead end, rather than a reason to remove the escalation guards.

Recommended fix: make a documented provisioning decision for initial financial authority. A narrow, audited system-principal bootstrap for designated separate administrators could preserve separation of duties. Specify scope, recipients, one-time/replay semantics and who can approve it. Do not silently give the tenant administrator every money permission. The existing open decision about irreversible `period.lock` is separate and remains unresolved.

## Implemented authorization model

Authentication uses OIDC/JWT validation and provider keys. Authorization is a custom scoped RBAC implementation with field/condition refinements resembling ABAC; it is not enforced by OpenTelemetry or a third-party policy engine. OpenTelemetry and structured logging support observability, while transactional audit events provide security evidence.

| Layer | Implemented behaviour |
|---|---|
| Permission catalogue | 248 concrete code-defined keys; malformed, duplicated or unknown shipped keys fail validation; server grants have no wildcards |
| Roles | 12 immutable shared system roles; tenant roles can be created/cloned and edited; permission sets combine additively, without role inheritance |
| Assignment | User or user-group subject plus role plus tenant/company/department scope; active flag and inclusive date validity |
| Scope | Tenant grants reach its companies/departments; company grants reach that company; department checks use explicit ancestry, with bounded hierarchy |
| Membership | Organizational membership is distinct from a role grant; joining a company alone is not business permission |
| User type | Identity/account classification, not permission authority; setting `platform_admin` as a profile value does not replace role/operator checks |
| Endpoint/object checks | A coarse endpoint permission is followed by checks against the actual object company/department; shared adapters carry signed company context where required |
| Field policies | Refinement inside endpoint/object authority; default allow, more-specific scope wins, deny wins at equal scope; registered fields and validated conditions |
| Persistence | Shared ORM SELECT tenant filtering; stricter guarded sessions additionally reject unsafe session reuse, scoped raw SQL and unsafe writes where enabled |

The core mechanisms are [authz.py](../libs/platform/src/billing_platform/authz.py), [permissions.py](../libs/platform/src/billing_platform/permissions.py), [gateway.py](../libs/platform/src/billing_platform/gateway.py), [field_policy.py](../libs/platform/src/billing_platform/field_policy.py) and [session.py](../libs/platform/src/billing_platform/db/session.py).

### Shipped roles

Counts reflect literal permission keys in the reviewed working tree. `scope_hint` guides assignment; the assignment's scope is the enforcement boundary.

| Role | Keys | Default hint | Implemented purpose |
|---|---:|---|---|
| `platform_admin` | 8 | platform | Tenant/account/plan/platform configuration administration; no tenant-business assignment or transaction authority |
| `platform_support` | 4 | platform | Platform tenant discovery, support impersonation, audit/activity reads; target access requires a valid support session |
| `tenant_admin` | 39 | tenant | People, groups, roles, field policy and configuration; limited financial-year/bootstrap setup |
| `tenant_auditor` | 84 | tenant | Broad read/export and security-audit visibility; no business administration or money writes |
| `company_admin` | 143 | company | Broad company/master/configuration authority and scoped role assignment; includes some accounting operations, such as bank-session finalization |
| `salesperson` | 29 | company | Sales/master reads and legacy invoice preparation keys |
| `billing_clerk` | 48 | company | Document preparation, including voucher create/edit; excludes voucher approval |
| `billing_approver` | 17 | company | Approval/acceptance and related reads; excludes voucher creation |
| `accounts_clerk` | 13 | company | Payment recording/allocation/refund and related operational reads |
| `controller` | 64 | company | Accounting operations, journal authority, period closing/reopening and voucher approval; excludes irreversible period lock |
| `viewer` | 37 | company | Selected business/master read access |
| `customer_portal` | 4 | company | Legacy invoice/payment keys; no voucher permissions or implemented customer-owner portal path was found |

Six separation-of-duties pairs are validated against each shipped role. Custom role composition returns warnings rather than rejecting conflicting pairs. Multiple otherwise safe roles can also combine into a conflicting effective user set: the resolver is additive, and there is no general per-user conflict prohibition. Voucher workflow self-approval rules are separate. This is an intentional policy limitation that must not be described as universal maker/checker enforcement.

### Authentication, revocation and platform access

- Ordinary grants are cached by tenant/user for 30 seconds by default, configurable from 1 to 300 seconds. User-targeted assignment/membership changes invalidate after commit, including regrant's explicit post-command invalidation. Group-role and role-permission changes use the documented TTL window. Redis failure falls back to live DB resolution; it does not confer authority.
- User and tenant lifecycle, token expiry and token invalidation timestamps are checked live for normal authenticated requests. API tokens store hashes, intersect their scope with live owner permissions and remove sensitive policy/identity-administration permissions.
- Gateway actor contexts use HMAC over the raw encoded body with a 60-second timestamp window and strict bounded schema. Accounting/Vouchers/Reports also validate signed company context against actor/tenant/company.
- Platform routes require both permission and a provider-linked operator mapping or the persisted installation administrator. Client `user_type` and an ordinary API token cannot certify platform-operator status. Sensitive platform mutations require fresh authentication where declared.
- Support sessions are attributed, time-limited and checked live. Effective permissions are restricted to `.read` keys excluding `platform.*`, and service adapters reject support writes. Target field policies remain applicable. Configured support-operator mapping is required; the installation-admin fallback on platform routes is not automatically support provisioning.
- Platform history uses a purpose-bound signed operator marker and event-family permissions. It does not grant platform operators ordinary tenant-business audit access. `audit.read_security` is separate from `audit.read`.

### Service and client applicability

| Area | Enforcement reviewed | Remaining issue/limit |
|---|---|---|
| Identity | OIDC/API tokens, live principal status, scope/delegation/field guards, locks and post-commit invalidation | Findings 1-4; legacy unguarded session factory |
| Catalog | Signed actor, company/department scope checks, registered field policies, tenant filtering and guarded sessions | Policy-administration update gap belongs to Identity |
| Accounting | Signed actor plus bound company context, object authority, field policy and guarded persistence | Focused authorization regressions passed; no exhaustive transaction endpoint review claimed |
| Vouchers | Signed actor/company contexts, complete policy namespaces, workflow/counter authority and tenant/company checks | Field-policy administration gap; legacy portal role does not cover voucher workflows |
| Reports | Signed actor/company contexts, report plus source permissions, field restrictions and current-authority checks for export downloads | Reviewed current source including concurrent local report changes; focused tests only |
| Notification | Signed scoped actors, tenant-scoped management and company-scoped delivery lookup; authenticated internal ingress | Legacy unguarded session factory; permission and tenant-isolation tests passed |
| Audit | Signed actor, scope-aware history/security/export checks and narrowed platform history | Legacy unguarded session factory; source tests do not establish live consumer configuration |
| Console/shared UI | Server-resolved permissions drive rendering; API remains the enforcement point | Navigation advertises `/roles`, but no page is implemented; role chip shows `user_type`, not assigned roles |

Additional hardening/workflow observations:

1. Identity, Audit and Notification still use `create_session_factory` with `guarded=False`, unlike Catalog, Accounting, Vouchers and Reports. ORM SELECT filtering still exists. This is a defense gap for identity-map reuse, context changes, raw SQL and write ownership, not a demonstrated HTTP tenant escape. Adoption needs explicit handling of legitimate platform/seeding operations.
2. `/v1/session` resolves its flat permission list at company scope. It returns the underlying scoped grants, but Console drops department grants from its authorization presentation and keeps only company IDs plus flat permissions. Department-only rights therefore cannot be represented for department-targeted controls without a selected department/scope-aware UI contract. Do not flatten them into company-wide API authority.
3. Shared UI permission helpers accept wildcards such as `*` and `company.*`; the backend catalogue does not. Normal server responses use concrete keys, so no API bypass was demonstrated. Remove/document this presentation-only mismatch and align tests with the server contract.
4. The documented customer portal promises customer-owned rows. The shipped portal role contains legacy invoice/payment permissions, and no implemented customer-owner document path was found. Treat portal delivery as incomplete; do not reuse company-wide business APIs as a portal without an explicit ownership check.
5. Role and assignment lifecycle events, token/session changes, group changes, impersonation and field-policy mutations emit transactional outbox audit events. An audit event records a change; it does not enforce its authorization. Fix the guards independently of event coverage.

## Verification and limits

Existing focused backend tests: **290 passed**, covering shared authorization/tenant/field primitives (129), Identity roles/cache/assignments/seeds/impersonation/auth bounds/gateway URI scope (76), Catalog actor/scoped/field security (4), Accounting authorization/field-policy regressions (27), Vouchers counter/auth/policy-context/scope/replay (6), Reports source authority/current-authority exports (5), Notification permission/tenant/delivery checks (5), and Audit authentication/platform history (38).

Six additional disposable probes reproduced the four findings, including both other-user and own-user role edits and both Catalog and Vouchers policy deactivation. Their passing assertions recorded vulnerable current behaviour; they were removed after evidence capture rather than added as tests accepting those behaviours. Future fix tests should assert rejection or successful authorized revocation instead.

Shared UI permission tests: **19 passed**. Console session display/selection and platform page/history visibility tests: **24 passed**. Total focused existing tests: **333 passed** (290 backend and 43 UI), plus the six reproduction probes.

Review included shared mechanisms, all seven service authentication adapters, route declaration scanning, Identity access-management implementations, system-role catalogue, gateway configuration and Console permission/session/navigation code. The scan's only unclassified routes were health probes and Vouchers' internal execution-result receiver; that receiver explicitly verifies service issuer, operation, tenant/company scope and a signed request body.

This is not a penetration-test or deployment certification. No production accounts were mutated, no database data was repaired, and no application fixes were applied. In-process probes used disposable SQLite fixtures and signed test actors; Identity role-edit tests exercise its internal signed-context route adapter rather than real-provider OIDC login. Live nginx deployment, provider configuration, all asynchronous workers, mobile flows and every individual business endpoint were not exhaustively exercised. Previously noted live Audit consumer/configuration activation remains a separate deployment check. Concurrent and prior working-tree edits were preserved.
