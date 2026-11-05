# Tenant management

> **Provider note (2026-10-31).** Administrator accounts are described against Authentik. With `local` (the default), *new* creates the administrator's account in Identity with the password the platform operator typed, and *existing* offers a local account that is active, verified and not yet in a tenant; the administrator signs in through the Auth app and accepts an invitation with the verified email on that account. See [local authentication](local-auth.md).

Use **Administer → Platform administration → Manage tenants** at `/platform/tenants`.
The shared directory provides prefix search over tenant names, status filters,
name/creation sorting, signed cursor paging, and permission-gated row menus.
Actions include details, editing, administrator access, suspension,
and restoration. Closed tenants remain visible but cannot be changed; an operator
cannot suspend their own operating workspace. Business records are retained.

Creation takes tenant name, administrator name/email, Country and State. The operator
chooses a new Authentik account or an existing active, verified account whose subject
is not linked to another tenant. The new-account path offers a generated password or
one entered by the operator. The operator must affirm that the recipient controls
the email address before the account is marked verified. This is a platform-operator
attestation, not an emailed proof. Authentik activation, password setting, local
active membership and the fixed `tenant_admin` grant must all complete before the
create command succeeds. A provider create/password failure leaves no new local
tenant. If activation fails after local commit, the provider account remains
inactive and the same request key retries activation without creating another tenant.
The location controls share one row on wide screens and stack on mobile. States
come from active reference tables and are filtered by country; changing country
clears the state. Countries without active subdivisions permit an empty state.
Identity saves the default state and validates its country membership.
Currency comes from Country.default_currency_code, language defaults to English,
and timezone defaults to Asia/Kolkata for India or UTC otherwise. These defaults
apply to new companies; their own jurisdiction and posted records stay unchanged.
Public signup asks for no workspace name: Auth derives it from the email address,
and platform approval creates the tenant automatically. Both creation paths show
manual access details and queue account-ready email when configured.
Workspace IDs are generated only by Identity as `workspace-<tenant UUIDv7 hex>`;
the time-ordered UUID avoids timestamp collisions and sequence allocation. They
remain immutable and are hidden from tenant forms, listings and detail overlays.
Existing identifiers remain unchanged. API request schemas reject caller-supplied
slugs; responses retain them for integration compatibility.
New tenant opens `/platform/tenants/new`; Edit details
opens `/platform/tenants/{id}/edit`. Creation uses three shared wizard steps: Tenant
details, Administrator, and Review & create. Existing-account search requires explicit
selection; pending registrations offer Yes to review the existing account or No to
keep the draft. The review step supports returning to edit details and shows the
access handoff after creation. Editing retains the grouped form. Both use shared
responsive controls, validation messages and API choices. Directory search,
filters and paging state are retained by Back to tenants. Read-only details and
administrator access remain available from the directory. The creation result
shows the new password once and never stores it in the local draft, audit event,
notification event or idempotency receipt. The operator shares it privately and asks
the administrator to change it after sign-in. Existing accounts keep their own
password. The Console always shows a sign-in link for manual handoff. When platform
notification routing and an email transport are configured, Identity stages a
`tenant.administrator.ready` message containing the sign-in link and username only.

Older invited administrators continue using the acceptance flow below.
The administrator accepts the invitation with a verified Authentik email matching
the invitation. While SMTP is deferred, privately share the three-day invitation
link from the details drawer. Changing the primary contact does not replace the
administrator or change their invited email. An expired invitation is not reusable.
Clicking Accept while signed out starts Authentik sign-in and resumes that same
invitation on return without a second click. A random, same-tab return marker binds
the resumed action to the initial click; merely opening an invitation URL never
accepts it. The backend still requires a matching verified provider email.

Self-service registration creates an inactive Authentik account for manual review.
After activation and email verification, login passes through Auth `/onboarding`.
Existing users continue to their requested Console page. Verified users without a
workspace can create one and receive only its `tenant_admin` grant. Users who were
invited should use their acceptance link. The documented one-login-per-tenant
identity model remains in force; no platform permissions are granted by onboarding.

## Access and recovery

Directory/detail reads require a configured platform operator with live
`platform.tenant.read` authority and a valid provider token. Browsing continues
after the original login is five minutes old. Creation, editing, lifecycle changes,
and administrator access writes additionally require authentication within five minutes;
refresh does not renew that proof. The API returns
`platform_reauthentication_required` for stale proof. Editors then offer
**Sign in again**, returning to the same form. Explicit reauthentication retains
the draft and creation key in per-tab session storage for up to thirty minutes;
it is consumed on return and cleared on save/cancel. No token, password or invitation
is stored there. A recovered draft requires review and an explicit save.
Ordinary permission denials
show access errors without an automatic login loop.

The Console BFF accepts fixed platform paths only, binds writes to same-origin
requests, limits JSON to 16 KiB/ten seconds, and keeps tokens server-side.
Creation retries preserve their idempotency key until the form changes.
Mutations and sensitive reads record audit through the same database transaction.
Tenant defaults apply only to new companies, preserving existing company settings.

## Platform details

The `/platform` landing page uses shared `ActionCard` styling with themed gradients
and icons. Configured operators with `platform.config.manage` can open
**Edit platform details** at `/platform/details`. The GET/PATCH
`/v1/platform/details` endpoints read/update only installation name and public URL;
writes require fresh authentication, live authorization, a row lock and a
transactional audit event. Setup completion, the original request proof, operating
tenant and first administrator are immutable through this API.
An Audit deployment's Identity source allowlist must include
`platform.details_updated` before enabling broker delivery. The payload records
changed field names with redacted values; it uses the existing event envelope.

The public URL is metadata, not deployment configuration: changing it does not
update nginx, OIDC callbacks or trusted origins. HTTPS is required outside loopback
development. Credentials, URL paths, queries and fragments are rejected.
**Fees and pricing** is visibly disabled with Coming soon and has no endpoint.

## Database and configuration

Upgrade Identity through `0076` using a migration credential. Revisions
`0067`–`0071` each add one directory index, declare an inverse downgrade, and match
the Tenant model. Continue using the existing installation entry point and role
seeds. Set `IDENTITY_PUBLIC_AUTH_URL` to the public Auth origin: HTTPS, except for
loopback HTTP development. The local value is `http://localhost:4310`.
Email delivery remains deferred until SMTP/provider configuration is supplied.
Revisions `0072` and `0073` materialize language and timezone reference tables;
`python -m identity.install` seeds both after migration. Language uses the existing
shared ISO dataset; timezone uses pinned `tzdata==2026.3`, including UTC and aliases.
Labels do not contain fixed UTC offsets, which change with daylight saving time.

## Decision log

- 2026-10-27: render the creation wizard outside the Console shell, like company
  creation, so it has one masthead and one viewport scroller. Keep platform
  breadcrumbs and return links; permission-denied and edit pages retain the shell.
- 2026-10-27: split platform tenant creation into a three-step wizard using the
  existing shared layout. Check pending registrations before review and again before
  creation; show access details within the final step. Keep tenant editing unchanged
  and exclude passwords and email attestation from recovered drafts.
- 2026-10-20: replace tenant create/edit drawers with dedicated protected pages;
  retain read-only and lifecycle overlays. Share the form and BFF/error mechanism.
- 2026-10-20: expose editable platform metadata using existing installation columns,
  without a migration or expanding bootstrap authority. Keep fees/pricing UI-only.

- 2026-10-20: retain `/platform` as a landing page; move listing into a dedicated
  directory using shared design-system components.
- 2026-10-20: require fresh authentication for sensitive actions while permitting
  ordinary reads with valid authority; remove the unconditional login link.
- 2026-10-20: share atomic provisioning between administrator invitations and
  verified self-service onboarding. Credential signup alone grants no local access.
- 2026-10-20: bind all four regional defaults to active database/API choices,
  with ISO 639-1 language codes and IANA timezone codes. These are configuration
  choices; selecting a language does not introduce translated UI labels.
- 2026-10-20: suggest workspace IDs from tenant names in the platform creation
  drawer, preserving manual edits until the next new tenant. Normalize to the
  existing ASCII ID constraints; uniqueness remains enforced by Identity.

- 2026-10-21: replace name-derived editable IDs with backend-generated UUIDv7-based
  identifiers. Simplify both creation paths to Country and State; persist an optional
  tenant default state under a composite country/state FK. Keep English/India-or-UTC
  defaults in the provisioning service and preserve optional regional overrides for
  integrations. This supersedes the earlier suggestion/manual-edit decision.
- 2026-10-27: resume an explicitly clicked invitation after Authentik sign-in using
  a same-tab marker; keep verified-email ownership and the existing one-use backend
  acceptance check.
- 2026-10-27: preserve an invitation when a recipient opens signup. Show existing
  and new account paths on the acceptance page, including the current approval and
  email verification requirement. Keep the copyable link available even when
  provider-backed email delivery is configured later.
- 2026-10-27: public account approval creates the requested tenant and its first
  administrator immediately after verified provider readback. Before the platform
  tenant form creates an invitation, it checks the entered email for a pending
  registration and offers Yes to review or No to keep the draft. The tenant API
  repeats the exact-email check under its creation lock.
- 2026-10-27: platform-created tenants now require an immediately active first
  administrator. A dedicated Authentik API service creates and sets a password for
  new users, or links an unbound active verified user. The platform operator attests
  email ownership for a new account. The local transaction records the fixed role
  and a password-free notification; the first response alone reveals the password.
  This supersedes invitation handoff for new platform-created tenants. Legacy
  invitation acceptance remains for existing pending records and other invite flows.
