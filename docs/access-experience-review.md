# Access experience by administrator level

Requested 2026-10-24: review and complete the user, role and permission experience
for platform operators, tenant administrators, company administrators and users.

## Phased implementation

1. Review the documented authority model and route/navigation gates. Keep account
   classification separate from assigned roles. Add regression tests first.
2. Provide a bounded company people directory and company invitation path. Company
   grants must never unlock tenant profiles, global lifecycle actions or groups.
3. Complete scoped subject selection and assignment validation before confirmation;
   show effective permission scopes and a self-service access view.
4. Review simplification, authorization, isolation, audit and accessibility. Run
   affected tests, generated-contract checks, TypeScript and a production build.

The user authorized implementation and review. No live access changes, commits or
publication are part of this task.

## Intended experience

| Principal | What they can do |
| --- | --- |
| Platform administrator | Use platform accounts, tenants, plans and configuration when granted; inspect their own access. Tenant business data needs the existing audited support path, not operator status. |
| Tenant administrator | Invite/manage tenant profiles, review/compose custom roles from held tenant permissions, and manage grants within their authority. System roles are read-only. |
| Company administrator | Read affiliated tenant users and invite new tenant users into an authorized company. Assign only held permissions at that company or permitted departments. Global profile/lifecycle and tenant group administration remain tenant responsibilities. |
| Regular user | Inspect their own current grants and effective permissions without receiving directory or mutation authority. Any administrative links depend on actual grants. |

Membership records affiliation and conveys no permission. Company invitations
create a new tenant-user account and a company affiliation together, without role
grants. They cannot link or alter an existing account, provision operators/service
accounts or expose profiles from other companies. Tenant administrators handle
existing-account affiliations and account-wide lifecycle changes.

## Existing unresolved policy

The initial financial-role provisioning decision in
[access-control-fixes.md](access-control-fixes.md) remains unresolved. No bootstrap
exception is introduced. The assignment check and UI explain a delegation denial
before a grant is committed. Tenant/company administrator labels never imply money
permissions or a bypass of the held-permission rule.

## Verification

All four phases are implemented and reviewed locally. The final full test suites,
type checks, generated contracts, production build and browser checks pass. The
pre-existing console coverage-gate limitation is recorded below.

### Completed changes

- `/users` resolves a tenant directory for tenant administrators and a current
  company people projection for authorized company administrators. Company changes
  remount its records/drafts; a missing or unauthorized company produces guidance.
- Company invitations use their own strict generated schema. The company path
  fixes the affiliation and account classification. Existing-account conflicts,
  field validation, pending writes, uncertain responses and discard navigation
  retain useful feedback and avoid duplicate submissions.
- User detail links can preselect a person for role assignment. Company subject
  search follows the selected assignment company, clears dependent selections and
  excludes direct self-grants. Tenant-only group choices stay hidden otherwise.
- Assignment review runs the server's non-mutating check before confirmation.
  Inputs are locked during checking and while confirmation is open. The committed
  grant repeats authorization checks; a previous preview cannot bypass revocation.
- Permission catalogue indicators distinguish tenant authority, authority in the
  selected company, authority elsewhere and permissions not held. System roles
  and permission keys remain read-only; custom roles are still tenant-managed.
- `/my-access` is an authenticated self-read from the request's session. Navigation
  and the account menu expose it without directory permission. Organisation and
  company settings now link the Users workflow within their respective grants.
- Assignment subject labels are projected per authorized company and current
  affiliation. Distinct projected membership pairs are bounded by the paged rows;
  tenant-wide labels still require tenant user read. Company field-policy denies
  remain enforced on company labels.
- No model or migration change is required. Identity OpenAPI and the generated
  client are synchronized; the client version is **0.2.12**, with its lock updated.
  No new styles or runtime dependencies were introduced.

### Review findings

An existing regression test caught incorrect tenant-scope picker activation. The
follow-up review added red/green cases for a missing preselected company name in
grant confirmation and an unsupported account-type filter carried into company
directory chips. These are corrected. Account-type labels never authorize an
action; live grant scope remains authoritative. The browser runner waits for
dialog animations to settle before assessing legibility.

The build also caught a read-only query-filter mutation in the first cleanup.
Company directories now allowlist only their supported filters when parsing the
query; no cast or mutation is used to bypass the shared query type.

Simplification review retained one invitation-creation service for the two entry
points and one assignment-check implementation shared by preview and grant. Shared
selectors, forms, dialogs, tables and existing styles are reused. Security review
walked CLAUDE sections 5 and 6: tenant and object scoping, changed-field restrictions,
no-self/group/held-permission guards, fixed catalogue, role immutability, audit
outbox transactions, credentials owned by Authentik and uncertain-write handling.
No new money, posting or support bypass is introduced. `/simplify` and
`/security-review` commands are unavailable in this session; the reviews were
performed directly against the same governing checklist.

The full Identity API suite passed **1,817 tests**, with **one existing skip**, and
coverage increased from 92.51% to **92.55%**, above its 90% requirement. All changed
API source modules were included in this final run.

The targeted user/role/security API run passed **54 tests**; the new company people
and existing access-contract tests passed **8**. The scoped UI/navigation review
passed **135 tests** and the final two regression files passed **20**. Ruff and
strict mypy pass on all six changed Python source modules. Generated clients,
client TypeScript, all **8 client tests**, console TypeScript and lock verification
pass. The final full console run passed **1,214 tests across 105 files**. Console
TypeScript passes after restoring only the verified automatic build changes to
route references and configuration. The final isolated production build passes;
the live development build remains at its original path.

| Console coverage | Before this review | Final run |
| --- | ---: | ---: |
| Statements/lines | 97.65% | 97.67% |
| Branches | 84.28% | 84.45% |
| Functions | 79.59% | 79.77% |

All overall measures improved. The coverage command still exits unsuccessfully
because the existing branch/function gates require 85%/90%. No threshold or
exclusion was weakened. Earlier full UI runs included stale expectations and
interaction timeouts under concurrent load; the final run uses two workers and
all tests pass after the review fixes. The temporary fixture preview server is
stopped, unrelated work is preserved, and no commit or publication was performed.

Browser review uses real console components with fixture BFF responses. It checks
1440px and 390px, existing themes, tenant workflows, company invitation and grant
review, read-only catalogue, regular-user self access and operator separation.
It does not verify live invitation delivery, real Authentik sign-in or mutate live
business access. **80 browser checks passed**, with no page errors. MySQL-container
tests remain separate from the SQLite API suite.
