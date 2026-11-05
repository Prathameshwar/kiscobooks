# Platform tenant and administrator lifecycle/recovery

> **Provider note (2026-10-31).** Recovery here is described for Authentik. With `local` (the default) the platform operator is offered a one-time recovery **link** (`/reset?token=…`, 10 minutes, single use) and never an email, because email delivery is not configured; the link is handed over privately. The tenant-user equivalent also requires the operator to have signed in within the last five minutes. See [local authentication](local-auth.md).

Requested 2026-10-26. Preserve the existing tenant, user, role and Authentik
ownership boundaries and reuse the Console design system.

## Phases

1. Review and regress tenant activation/deactivation and administrator access
   activation/deactivation. Keep reversible suspension separate from terminal
   account deactivation and role revocation. Preserve last-administrator and
   operating-workspace protection. Add direct detail actions and reliable row
   actions, confirmations, fresh authorization and stale-record protection.
2. Add tenant-administrator password recovery through Authentik's native recovery
   contract, with target-account checks and audited platform authority. Never
   store passwords or recovery tokens in billing tables. The reset delivery
   preference is both an expiring link to share securely and native email.
   Email remains disabled until the provider's SMTP configuration is supplied.
   Keep the restricted account-review provider separate from recovery authority.
3. Synchronize affected API schemas, generated SDK, scripts and policy docs.
   Verify native authorization, lifecycle/replay/last-administrator/provider
   failures, UI validation and navigation. Review, fix findings and build/reload
   the managed applications. Do not change real tenant status or trigger a real
   user's password reset during verification.

## Initial findings

- Tenant list suspension/restoration exists, but detail pages lack those actions
  and lifecycle writes do not carry the displayed revision or a replay receipt.
- Administrator suspension/restoration, revocation and invitation resend exist
  with optimistic checks, fresh platform authorization and last-admin protection.
- Password recovery is missing. Authentik 2026.8 exposes POST recovery-link and
  recovery-email actions guarded by object-scoped reset-password authority.
- Billing user deactivation is terminal; activation/deactivation of access must
  use the existing reversible suspension mechanism rather than bypassing that
  invariant. Invitation acceptance remains provider-verified.

## Verification

Implemented and verified on 2026-10-26. Managed services are reloaded and ready.
Existing unrelated edits and publication state remain intact. No commit or
publishing action is included in this request.

## Implementation and decisions

- Tenant list and detail pages expose Activate/Deactivate actions with a reason,
  displayed `updated_at` revision and required idempotency key. Stale decisions
  cannot overwrite newer changes. Replays return the original receipt and recheck
  current authority. The operating workspace and closed tenants are protected.
- Administrator access uses reversible suspension/restoration. Terminal account
  deactivation is not bypassed. Last-active-administrator checks, role revocation,
  invitation resend and fresh fixed-role authorization are retained. Restoring an
  invited assignment still requires verified invitation acceptance.
- Directory kebabs open administrator access and password recovery sections on
  the real detail page. Sections scroll and focus after asynchronous loading.
  Pending actions, validation, conflicts and sign-in recovery use existing controls.
- Decision: offer both expiring recovery links and native recovery email, as
  requested by the user. Links expire after ten minutes. Billing never sets a
  password, activates an account through recovery, or saves a generated recovery
  link/token. Copy, Hide and expiry clearing are explicit. Hiding does not revoke
  a provider link. Email remains disabled until SMTP configuration is supplied.
- The closed recovery API requires a fresh configured platform operator, live
  tenant-access management permission, customer tenant, active accepted user and
  effective fixed tenant-admin assignment, and both displayed revisions. It maps
  the stored opaque Authentik OIDC UID (or an existing legacy UUID) and checks the
  exact provider subject, email, active/verified application scope, type and
  absence of privileged groups/roles. UID lookup uses the native bounded email
  filter followed by exact subject verification; ambiguous or paginated results
  are refused. Existing identity subjects are never rewritten. Provider
  accounts outside this recovery scope remain managed by their sign-in provider.
- Recovery is a keyless external action. Supplying an idempotency key is rejected;
  neither the browser nor transport retries automatically. An uncertain outcome
  asks the operator to check with the administrator before requesting another.
  An audited request intent commits before the provider call, outside database
  locks. Audit holds actor/target/assignment references and delivery kind, never
  generated links or passwords. Email acknowledgment means provider delivery was
  requested, not that the recipient received it.
- A separate Authentik service credential holds object-level user view/reset
  permissions and view of its email stage. It receives no global user permissions,
  change-user authority, or administrative roles. Enrollment performs the trusted
  permission handoff. The native recovery flow requires a bound eligible user,
  preserves configured MFA, restricts password prompt values and never creates
  accounts or logs the recipient in automatically. Existing brand recovery flows
  are preserved if they differ from this deployment.
- Correction, 2026-10-29: recovery also supports verified, nonprivileged accounts
  in `bill/tenant-administrators` carrying a valid provisioning-command marker.
  A native event policy grants the separate recovery role object-only view/reset
  authority after creation/update by the dedicated provisioning service. It
  checks the actor, model, account path/type, deterministic username, verification
  marker and absence of privileged groups/roles; it sends no notifications.
  The preparation script reconciles older provisioned accounts through that same
  policy. Future accounts require the native event worker to process the handoff;
  before that, recovery fails closed. There is no global recovery user authority
  and the provisioning credential is never reused for recovery.
  Native verification exposed Authentik 2026.8.4's additional generic POST guard:
  it requires `add_user` on the target object before checking reset authority.
  The role therefore also receives **object-only** `add_user` on eligible users.
  It receives no global `add_user` and cannot create users, change profiles or
  delete users. Enrollment and existing-account reconciliation use the same
  grant. Native permission regressions verify these limits.
- `prepare-administrator-recovery.ps1` installs the blueprint, captures the native
  credential privately, and configures Identity. It enables the email-stage setting
  only when Authentik SMTP host and sender are configured. After providing SMTP,
  rerun that script and restart Identity. Provider startup stderr is captured and
  the actual native exit code determines blueprint success.
- The shared bounded JSON transport is library 0.41.1, with all eight service locks
  and the library lock synchronized. It refuses redirects, bounds response bytes,
  redacts failures and performs no retries. Account review keeps its separate
  credential and policy. Identity OpenAPI and SDK 0.2.28 are synchronized, and web
  consumers were refreshed. Audit delivery selection and history value allowlists
  include the new request events. Existing Tenant, User, assignment, audit/outbox
  and lifecycle receipt models are reused; no billing DDL changes were required.

## Review and evidence

Login self-service recovery is documented in [forgot-password.md](forgot-password.md).
After configuring SMTP, `start/win/registration/prepare-password-recovery.bat`
prepares both the public email flow and this administrator email option while
preserving the administrator link flow. Restart Auth and Identity afterward.

- Review 1 fixed missing lifecycle detail actions, stale tenant writes, incomplete
  kebab navigation, unsupported Card attributes, invitation restoration messaging,
  and validation/pending/conflict behavior.
- Review 2 checked current authorization and tenant boundaries, last-admin rules,
  provider identity/profile matching, credential scope, token persistence, native
  email acknowledgment, disabled SMTP behavior, transport duplication, secret
  error handling and asynchronous section focus. No unresolved code finding remains.
  The repository slash review commands are not exposed in this session; these were
  manual security and simplification reviews.
- Native Identity scope/lifecycle/recovery/provider checks: 75 passed. Final
  adapter checks after shared transport extraction: 43 passed. Audit checks: 36
  passed. Shared transport: 8 passed. SDK transport: 8 passed. Windows registration
  and recovery deployment checks: 8 passed. The recovery no-replay guard also passed.
- Console verification: 593 checks across 56 files passed; final affected-page
  checks including expiry and asynchronous focus passed 41 tests. Strict mypy
  passed seven source files, Console TypeScript passed, and affected Ruff checks
  passed. OpenAPI and generated SDK checks passed.
- Browser review: 163 checks across desktop/mobile and light/dark/ledger, no
  browser errors. Twenty-four writes used intercepted fixtures, with zero live
  writes. Tenant activation/restoration, recovery link copy/hide, disabled/enabled
  email presentation and kebab destinations were exercised. Screens were inspected.
- Authentik blueprints and the restricted credential were prepared locally; fresh
  native flow-policy planning and object-permission checks passed using an unsaved
  fixture, without saving users, issuing recovery tokens, changing passwords or
  sending emails. Local SMTP is absent and email is disabled.
- Production Console build passed and the managed Console returned UP on 4320.
  The live provider read initially found the stopped localhost SSH tunnel. Starting
  the existing managed tunnel restored trusted HTTPS; the restricted credential
  returned the expected empty UUID lookup. No TLS verification was bypassed.
- Identity and Audit were reloaded and reported ready on 8001/8002. The live
  Identity specification includes password recovery and required tenant revisions.
  Console remained UP on 4320. The review-only preview was stopped; the managed
  Authentik tunnel remains running for application sign-in and recovery.
