# Platform administration: first three improvements

Date: 2026-10-21. Status: implementation approved; tracked in the companion todo list.
The user approved all six phases, sequential implementation and phase reviews.
Application changes, migrations and local provider configuration are authorized.
Commit and publication require a separate request.

## Scope and current findings

| Improvement | Current implementation | Intended result |
|---|---|---|
| View tenant | Existing protected detail API; the directory opens a drawer | A full Console page with shared cards, regional labels, navigation and permitted actions |
| Change password | Authentik owns credentials; a plan exists but no application page/menu action exists | Change password above Sign out, a separator, and a branded page leading to an authenticated Authentik form |
| Account approval inside JANSO | Public signup creates inactive, unverified Authentik accounts; approval is manual in Authentik | A protected platform account-review directory and detail page, with explicit manual verification, approval/rejection and reliable provider integration |

References: [tenant management](tenant-management.md),
[tenant view plan](tenant-view-page-plan.md),
[password-change plan](change-password-plan.md),
[account registration](account-registration.md),
[roles and permissions](roles-permissions.md), and [audit](audit.md).

Use the existing Identity, Auth, Console, Audit and shared UI mechanisms. No new
service, datastore, theme or dependency is proposed. Concurrent company-wizard
and Notification work must be preserved and assessed before implementation starts.

## Product and security decisions proposed for agreement

1. View tenant remains at `/platform/tenants/{tenantId}`. Generated workspace IDs
   stay hidden. No tenant business records are added to the platform view.
2. Change password is available to authenticated users, including platform admins.
   The branded application page opens Authentik's secure native form in the same
   tab. Password entry and policy enforcement remain in Authentik. Current
   password, any configured MFA, new password and confirmation are required by the
   selected flow. External-provider accounts receive appropriate provider guidance.
3. Manual approval remains available without SMTP. Approval requires the operator
   to confirm they independently checked the person's identity and email. A
   checkbox is a recorded administrator attestation, not an email challenge.
4. Account approval applies only to public registrations for this Bill application.
   It never permits editing unrelated Authentik accounts, platform operators,
   service accounts, passwords, groups, roles or arbitrary provider attributes.
5. Approval activates and marks the account's email as manually verified. It does
   not create a tenant or grant a role. Existing onboarding lets approved users
   create their own tenant; the existing admin tenant-creation flow stays separate.
6. Rejecting an unapproved registration keeps it inactive and unverified, with a
   recorded reason. Reopening a rejection is an explicit audited action. Disabling
   existing approved users, granting platform-admin access, and session-management
   screens are separate future work.
7. Add narrow proposed permissions `platform.account.read` and
   `platform.account.review`. Grant them only through reviewed platform-admin
   system-role seeds; ordinary tenant admins and platform-support roles do not gain
   review authority. Existing configured-operator checks still apply.

## Phase 1 — Verify integration capabilities and finalize contracts

**Purpose:** resolve provider and session requirements before building security UI.

- Inspect the installed Authentik version's supported self-service stages,
  current-password verification, configured MFA, policy validation, cancellation,
  native audit events and post-change session behavior.
- Verify supported management API pagination, application registration markers,
  immutable account identifiers, restricted account reads/updates, preservation of
  attributes, and concurrency/version support. Confirm how provider identifiers map
  to verified OIDC subjects; never assume that a numeric provider ID is an OIDC sub.
- Prove a non-superuser service account can perform the required Bill registration
  operations. Specify its least provider-native permissions and object scope, plus
  the server adapter's fixed account/field allowlists. The password-change flow
  must not use this management credential. If sufficient scope cannot be achieved,
  report the exact limitation before enabling the approval feature.
- Design provider status reconciliation and import of existing pending registrations
  through the supported API. Do not read or write Authentik's database directly.
- Finalize typed Identity routes, reference-label lookups, narrow permissions,
  audit action names, error envelope and retry semantics. Proposed review routes:
  `/v1/platform/accounts`, `/v1/platform/accounts/{id}`, and
  `/v1/platform/accounts/{id}/review`.
- Specify the minimal review projection and durable command state in Identity:
  provider identity, reviewable signup metadata, version, administrator decision,
  reason, timestamps and provider-application result. No password or token columns.
  Searchable name/username/email metadata is a deliberate change from the current
  provider-only pending-profile policy; document purpose, access and retention.
- Keep registration country/state metadata as editable onboarding defaults; review
  does not grant jurisdiction, workspace membership or business permissions.
- Finalize password-change completion evidence and the exact re-sign-in policy.
  A return URL or `?success=1` is not proof of a password change. Existing issued
  billing/OIDC tokens must not be assumed revoked by a provider password update.

**Exit:** saved API/data/security decisions and disposable-account capability
checks pass. No broad provider credential or unsupported session guarantee remains.
These checks are authorized only when implementation is subsequently agreed.

## Phase 2 — Deliver the full View tenant page

- Build a protected Console page using existing page context and the live platform
  detail API. Reuse `PageNavigation`, `PageHeader`, cards, badges, field/detail
  layouts, notices and existing central spacing and typography.
- Present tenant name/status, primary contact, Country/State, Currency, Timezone,
  Language, creation/update dates and applicable suspension details. Resolve names
  through existing bounded reference APIs/cache; preserve stored codes as fallback
  when a reference is retired or its optional label lookup is unavailable.
- Provide Back to tenants and breadcrumbs. Allowlist and preserve search, filters,
  sort and paging state on return, including direct visits and page reloads.
- Move directory View details to the page. Keep administrator-invitation handoff
  and suspension/restoration as separate existing actions. Reuse their request,
  error and fresh-auth mechanisms rather than creating alternate mutation paths.
- Show Edit only with existing authority and an editable tenant status. Cover
  loading, 401, 403, 404, stale administrative proof, outage/retry, and closed status.
- Scope account/contact information to the existing tenant-detail contract. Do not
  invent user counts, usage, billing totals or cross-tenant financial access.

**Exit:** component/route regressions, safe navigation checks and TypeScript pass;
desktop/mobile and Light/Dark/Ledger layouts are reviewed. No DB migration or
Identity API change is expected for this item.

## Phase 3 — Deliver Change password with Authentik

- Apply an idempotent dedicated authenticated Authentik flow, leaving existing
  enrollment and ordinary sign-in intact. Require current-password verification,
  configured MFA, matching new/confirm passwords, rejection of unchanged passwords
  and a consistent 6–128 Unicode-character range. Test policy enforcement directly
  at the provider, including requests outside the application UI.
- Add a reusable non-focusable separator to the shared UserMenu. Place Change
  password immediately above Sign out, with the separator before Sign out.
  Preserve the menu's arrow-key behavior, Escape handling and focus restoration.
- Add a branded Auth page at `/change-password`, with a server-configured secure
  provider destination, authenticated access, back navigation, concise instructions,
  Continue and Cancel actions, connecting/error states and sign-in recovery.
- Preserve provider browser authentication; handle an expired provider session
  separately from an expired JANSO session. Validate all callback/return destinations.
  Do not expose tokens, forward arbitrary account IDs or put credentials in URLs.
- Implement the verified Phase 1 completion policy. Use native provider completion
  messaging if no trustworthy callback is available; return guidance must not claim
  success based only on navigation. Offer the existing protected sign-out and fresh
  sign-in path, with explicit tested scope of revocation and safe failure recovery.
- External-provider or passwordless accounts receive usable guidance rather than
  an unsupported local-password promise. SMTP remains unnecessary for this flow.

**Exit:** menu/page tests and affected Auth/Console/shared UI checks pass; a
disposable provider account covers successful change, wrong current password,
mismatch, unchanged password, 5/6/128/129 boundaries, cancellation, expired sessions
and configured MFA. Document the observed token/session behavior.

## Phase 4 — Deliver account-review API, database and provider coordination

- Add the agreed minimal Identity review projection and durable operation storage,
  with reviewed indexes, a unique provider/account identity, versions and bounded
  metadata. Use the existing platform-control scope and deny ordinary tenant access.
  Migrations follow one DDL statement per revision and include downgrade behavior.
- Add the two agreed permissions to the fixed catalogue, system-role seeds,
  documented permission matrix and shared-library versions/consumer lockfiles.
  Seed updates must preserve existing tenant-specific role assignments.
- Add protected list/detail/review APIs with configured-operator checks and live
  grants. Review mutations additionally require authentication within five minutes,
  strict fields, expected version, reason, explicit verification attestation and an
  idempotency key. Audit account reads and decisions without name/email values.
- Provide indexed allowlisted search, typed status filters, signed keyset paging,
  stable sorts and lean rows. Defaults: 50 rows; maximum 200. Do not fetch every
  provider account or return an unbounded profile blob to populate a page.
- Keep passwords and provider credentials exclusively server-side. Use trusted
  HTTPS, fixed endpoints, bounded responses/timeouts, fail-closed eligibility checks,
  rate limits and secret redaction. Preserve unrelated account attributes and region
  metadata when setting the exact allowed activation/verification fields.
- Persist intent and audit/outbox together before applying provider changes using
  the existing durable execution mechanism. Remote Authentik writes and Identity
  commits are not one transaction. Claim operations safely, serialize competing
  decisions, recheck current provider metadata and verify the applied state.
- Treat lost responses, provider outage, local rollback, changed email, duplicate
  submissions and competing decisions as explicit recoverable outcomes. Replays
  reuse the command key and reconcile absolute provider state. Never display
  Approved merely because an operation was queued or an HTTP response was lost.
- Import only eligible existing Bill registrations in bounded batches; keep import
  repeatable. Distinguish administrator review status from observed provider state,
  show drift, and require reconciliation rather than silently overriding external
  administrator edits. Profile/email changes invalidate stale verification evidence.
- Configure the least-privilege service credential in ignored environment/secret
  storage. Provide an idempotent local preparation/verification script and documented
  production setup. Disable review safely until required provider scope is validated.
- Regenerate OpenAPI and TypeScript contracts together. Update existing audit-source
  allowlists and consumers where needed for the new administrative event names.

**Exit:** migration, domain/API, live permission revocation, replay/concurrency,
rollback, provider failure/reconciliation and unauthorized-account tests pass.
Native disposable DB/provider tests demonstrate verified application of decisions.

## Phase 5 — Deliver account review inside the Console

- Add an Account approvals card under `/platform`, using the same shared gradient
  card design as Manage tenants and Edit platform details.
- Add `/platform/accounts`: search, review-status filter, stable sort, paging and an
  icon refresh control in the shared aligned toolbar. Reuse central list styles.
- Add `/platform/accounts/{id}`: name, username, email, registration date, regional
  selections, provider activation/verification state, review history and any pending
  operation. Use the same reusable detail layout as the tenant page.
- Provide View, Review/Approve, Reject, and authorized Reopen actions where applicable.
  Use full pages for review and validation; use confirmations for final decisions.
  Keep any unavailable action clearly explained and enforce it again in the API.
- Approval requires checking the displayed email/identity, an explicit attestation
  and a reason. Explain that manual approval sends no email, and that the approved
  user can sign in to create a tenant or accept their existing invitation.
- Rejection requires a reason. Processing/Needs attention states show safe retry or
  refresh guidance; a provider timeout never becomes a false success message.
- Implement Back/breadcrumbs, list-state restoration, draft recovery for explicit
  reauthentication, focused field errors, duplicate-submit protection, success/error
  notices, and complete 401/403/404/409/422/429/503 handling.
- Do not place provider credentials or detailed applicant data in browser storage.
  Save only minimal temporary form state if recovery requires it, with a bounded TTL.
  Account-review reads stay live; reference choices reuse existing Redis caching.

**Exit:** page/component tests and TypeScript pass, with keyboard/accessibility,
mobile/desktop and all-theme reviews. Billing platform operators can review eligible
registrations without entering Authentik's admin console.

## Phase 6 — End-to-end verification and final review

Verify each flow using disposable accounts and a disposable Identity schema:

| Scenario | Required result |
|---|---|
| Tenant list → View → Edit → Back | Full page; correct tenant; list state and permitted actions preserved |
| Password change | Wrong password/mismatch/invalid length rejected; successful change accepts the new password and rejects the old one; session behavior recorded |
| Signup → Pending review → Approve → Sign in | Manual verification recorded; provider activation confirmed; normal OIDC login and onboarding succeed |
| Approved user creates a tenant | Country/State and generated workspace ID/defaults retained; only their scoped tenant-admin grant is created |
| Approved invited user | Existing email/tenant invitation checks hold; approval itself creates no workspace grant |
| Reject/Reopen | Rejected account cannot sign in; only an explicit authorized action reopens review |
| Provider outage/lost response/retry | Durable operation reconciles; no duplicate effects, lost decisions or false success |
| Stale proof/revoked grant/ordinary tenant role | Server refuses administrative mutation; UI gives correct recovery or access message |
| Unrelated provider account/operator/service account | Excluded from the queue and denied by direct API requests |
| Changed applicant email/concurrent reviews | Stale evidence refused or reconciled explicitly; only the authorized current decision completes |

- Run affected Identity/Auth/Console/shared UI tests, strict Python checks,
  TypeScript, production builds, migration round trips and contract checks.
- Confirm provider-native audit events and Identity decision audit/outbox, including
  redaction, rollback and delivery configuration. Queued audit is not delivered audit.
- Review CLAUDE.md §§5–6, shared-style reuse and duplication. Run the required review
  commands if available; otherwise record the equivalent manual review and findings.
- Update registration/tenant/password run instructions, security decisions,
  migration/seed steps, credential rotation/reconciliation notes and verification
  evidence. Restore the normal local platform after disposable tests.
- Report exactly what passed, what was skipped and any remaining provider limits.
  No live user's password, approval status or tenant is changed for testing.

**Exit:** all three improvements work through the intended UI/API/provider/DB
paths, required checks pass and no blocking review finding remains. SMTP remains
deferred as previously requested. Completion does not imply commit/publication;
that follows only a separate authorized request.

## Tracking

- [x] Phase 1: provider capability proof and final contracts
- [x] Phase 2: full View tenant page
- [x] Phase 3: Change password
- [x] Phase 4: account-review API/DB/provider coordination
- [x] Phase 5: account-review Console pages
- [x] Phase 6: end-to-end verification and final review

Planning decision, 2026-10-21: combine the first three pending platform improvements
into this six-phase proposal. Earlier feature plans remain references; this document
defines the agreed delivery order. Implementation approved on 2026-10-21.
