# Create account and manual approval

Current end-to-end verification: [signup, approval and tenant creation review](onboarding-review-2026-10-27.md).

Open `http://localhost:4310/login` and select **Create account**. The branded form
collects full name, username, email, Country, State, password and password confirmation.
The server derives an initial workspace name from the email local part, removing
tag suffixes and separators (for example `acme.books+test@…` becomes `Acme Books Workspace`).
There is no workspace-name input. The workspace can be renamed after approval.
An invitation signup joins its existing tenant. It stays
in JANSO throughout registration. Passwords must contain 6–128 Unicode characters,
with matching confirmation. The Auth API and Authentik enforce the same range;
the strength meter recommends a longer, unique passphrase without blocking a
valid six-character password. Authentik's score threshold is disabled for this
enrollment flow so it does not impose a conflicting minimum.

Country and State use active Identity database reference rows, in one shared form
row. India is selected when active; State is required when that country has active
subdivisions. Changing Country clears State. Unavailable reference data blocks
creation and offers retry. The server reloads and validates the active country/state
pair before contacting Authentik, including requests submitted outside the browser.

The fixed enrollment blueprint saves `billing_registration_workspace_name` (an empty
value for invitation signup) and `billing_registration_region` with
`country_code` and `state_code` in the provider account. After approval and OIDC
sign-in, the checked profile supplies these as private Auth session metadata. Only
an active matching pair is offered as editable workspace defaults. Identity validates
the final values and persists them in the tenant's existing country/state columns;
currency, time zone and language are resolved by the existing backend defaults.
No credentials or pending account profile are stored in billing tables.

New accounts appear in Authentik under `bill/pending-registration`, with
**Active disabled**, `billing_email_verified: false`, external user type, and no
groups. They cannot sign in until approved. Approval queues account-ready email
when platform delivery is configured; passwords are never included.

After public-signup approval completes, Identity creates the requested tenant and
first administrator in the same transaction as the completed decision. The next
login opens that workspace. An invitation signup gains access by accepting its
existing invitation after approval.
Platform administrators can also create and manage tenants through
**Administer → Platform administration → Manage tenants**. See
[tenant management](tenant-management.md) for immediate platform tenant provisioning,
legacy invitation handoff and permissions.

## Approve an account

1. Sign in to the billing Console as a platform administrator. Open **Platform
   administration → Account approvals**. Opening the directory automatically imports
   the newest registrations; **Refresh accounts** checks again. Open the applicant's record.
2. Independently check the person's identity and displayed email. Enter a review
   reason, attest to that check, then confirm **Approve account**. The review API
   records the decision and audit event before the restricted provider worker
   activates the account, marks its email verified, and creates the requested
   workspace for public signup. Wait for **completed**;
   a queued decision does not yet enable sign-in.
3. For a tenant invitation, the user signs in with the chosen username and password
   and accepts the invitation using the same verified email. Registration and
   approval alone does not grant invitation access or a platform role. Earlier
   registrations without a workspace request need a workspace name entered by the
   reviewer before approval.

To deny a pending account, select **Reject registration** in Account approvals.
The account remains inactive and unverified. Provider drift and revocation need
administrator reconciliation; see [platform account reviews](platform-account-review.md).
Billing platform administrator and Authentik administrator remain separate roles.

## Local preparation

Run `start\win\registration\prepare.bat`. It applies the idempotent enrollment
blueprint over the existing verified SSH connection and writes
`AUTH_REGISTRATION_MODE=manual-review` to the private Auth `.env.local`. Existing
`AUTHENTIK_ISSUER`, `NEXTAUTH_URL`, and `AUTH_REDIS_URL` must already be configured.
Then restart Auth with `stop-web.bat auth` followed by `start-web.bat auth`.
`apply-authentik.bat` reapplies the enrollment blueprint without changing env.
After updating regional enrollment, also run
`start\win\platform-setup\apply-authentik.bat` to update the checked email/profile
claim mapping. Both use the existing verified SSH connection; preserve existing
account attributes when manually approving an account so saved defaults survive.
`IDENTITY_URL` must point to the existing Identity API with migrated and seeded
country/state reference tables (`python -m identity.install` during deployment).

Removing `AUTH_REGISTRATION_MODE` disables the JANSO registration API. Also disable
the Authentik enrollment flow if shutting down enrollment at the provider itself.
It is an intentionally public native enrollment flow.

The Auth API exposes public `GET /api/registration` (availability and active regions) and
`POST /api/registration` (strict account fields). Success returns HTTP 201 with
`{"created":true,"status":"pending-review"}`. Inputs are bounded to 8 KiB,
mutations require the configured Auth origin, and a distributed Redis cap permits
20 submissions per minute across Auth instances. Redis failure blocks creation.
The nginx template includes an optional `/api/registration` ingress limit; use
per-IP limits at production ingress in addition to the application cap. Direct
development UI ports retain the application limit. Authentik's own public ingress
also needs rate limits before exposing its enrollment flow beyond this laptop.

Identity's deliberately public `GET /v1/registration/options` returns only active
global country/state codes and names, never tenant data or account lookups. Reads
are bounded and rate-limited; unknown query fields are rejected. The Auth adapter
uses a fixed server-configured destination without forwarding caller credentials.
Public `GET /v1/registration/invitation` returns only `{ "available": true|false }`
for a tenant/invitation/email combination; it is rate-limited and never returns
tenant or recipient details. The Auth server uses it before invitation signup.
Ordinary registration accepts exactly eight named fields; invitation registration
accepts the eight account fields with an empty workspace request plus the two
invitation UUIDs. Auth asks Identity to confirm that the pending invitation belongs
to the submitted email before creating the provider account. Arbitrary provider attributes,
groups, activation, roles and verification flags are rejected.

Credentials pass transiently through the Auth server to Authentik's anonymous
flow executor over trusted HTTPS. They are never put in billing tables, Redis,
logs, URLs or browser storage. The adapter starts a separate provider session;
it never forwards the caller's authenticated cookies or authorization. Only the
exact executor's intermediate redirect is followed, using GET without passwords.
The provider terminal redirect is consumed by the adapter and never navigates
the browser away from the branded form.

SMTP and automatic email verification are deferred. When adding them, require a
successful one-time email challenge before setting `billing_email_verified` and
activating a new account. Merely configuring SMTP must not auto-verify accounts.
The current Authentik claim mapping reads the explicit verification attribute.
Identity revisions 0086 and 0087 add the requested workspace to the review
projection and durable decision. Credentials and approval flags remain in Authentik.

Decision record, 2026-10-20: keep Authentik as credential owner; implement native
enrollment through the Auth BFF and branded UI, with explicitly authorized manual
review until email delivery is configured. Preserve independent workspace grants.

Decision amendment, 2026-10-20: at the user's request, accept 6–128 characters
instead of 12–128 across registration UI, server validation and provider policy.
Count Unicode code points consistently; retain password strength as advice.

Decision amendment, 2026-10-21: initial registration also selects database-backed
Country/State with India as the active default. Save the fixed region in Authentik,
carry it privately as editable setup metadata and validate again in Identity. Reuse
the active tenant reference queries and shared form layout; no new datastore,
Identity account table or migration is needed for registration profile metadata.

Decision amendment, 2026-10-27: the platform Account approvals workflow replaces
direct Authentik administrator edits for ordinary manual registration decisions.
New accounts remain inactive until the reviewed provider update is confirmed.

Decision amendment, 2026-10-27: ordinary signup derives its workspace name from email and
completed approval creates one tenant with the verified account as its first
administrator. Invitation signup joins its existing tenant. Tenant creation checks
for an exact pending-registration email and routes the operator to review.

Decision amendment, 2026-10-31: credentials can be owned by Identity (`AUTH_PROVIDER=local`, the
default) as well as by Authentik. Registration, manual review, approval and the one-time recovery
link behave identically from the operator's side; the review state machine runs unchanged over
`local_identity` through the same adapter interfaces (`identity/services/identity_provider.py`). The
6–128 character password rule and the generic "These account details cannot be used" answer apply to
both. With `local`, a username is not a sign-in credential: people sign in with their email address.
See [local-auth](local-auth.md) and [tech-stack](tech-stack.md) decision log.
