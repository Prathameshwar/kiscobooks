# Identity gap operations

> **Provider note (2026-10-31).** `AUTH_PROVIDER` now defaults to `local`. An installation that signs in
> through Authentik must set `IDENTITY_AUTH_PROVIDER=authentik` (Identity refuses to start with a legacy
> `IDENTITY_OIDC` and neither provider chosen). With `local`, the gateway must also route `/oidc/` and
> overwrite `X-Forwarded-For` — see `deploy/nginx/identity.conf.example` and
> [local authentication](local-auth.md).

Status and evidence: [todo](identity-gap-todo.md). This is the deployment contract for
implemented capabilities; live Authentik, Azure RBAC, external email and Billing verification
remain separate gates. No production deployment is performed by this work.

## Deployment order

1. Back up Identity and run the existing integrity inventory. Apply Identity migrations
   through 0057 with its own database credential, then `python -m identity.install` using
   the existing installation entry point. Each revision has one atomic DDL statement.
2. Deploy shared `billing-platform` 0.17.0 with the synchronized service locks. Audit,
   Catalog and Notification consume the shared signed actor format. Do not send legacy
   flat permission arrays to Notification. Identity rejects legacy signed impersonation
   contexts; support sessions use a verified bearer and live session revalidation.
3. Configure Authentik, Redis and the Identity API, then Auth and Console. Run behind TLS
   using [the nginx example](../deploy/nginx/identity.conf.example); strip client-supplied
   actor headers and keep internal service routes off the public ingress.
4. Start authenticated Audit and Notification consumers before their publishers. Stop
   the old unsigned Audit writer. Do not bind Identity invitation/preference routes to
   legacy unsigned Notification consumers. Install each tenant's invitation template and
   configure a verified email sender/provider route before sending invitations.
5. Configure Azure's private container, bank keyring, and recovery workers. Enable the
   Billing publisher only after Billing has deployed its durable inbox consumer.

## Authentication and browser configuration

Identity uses `IDENTITY_OIDC` JSON with `issuer`, `audience`, `jwks_url`, `api_scope`
(default `billing.api`) and `max_token_seconds` (default 300). Issuer/JWKS must use HTTPS.
Authentik signs RS256 access tokens, issues the configured API scope, and supplies subject,
issuer/audience/time claims, including original `auth_time` retained across refresh.
After self/admin session revocation, both `iat` and `auth_time` must be later than
`user.tokens_valid_after_at`; missing `auth_time` fails closed for revoked users.
The subject must resolve to one active local user; an optional
`org_id` must agree with that user's tenant. Permissions come from live local grants.
Invitation acceptance additionally requires verified email matching the pending invitation.
Linking another identity requires fresh authentication and signed `linked_identities`
claims; an administrator cannot bind an arbitrary provider subject to another user.

Set `IDENTITY_PUBLIC_AUTH_URL`, `IDENTITY_REDIS_URL`, the two signing secrets and
`IDENTITY_PLATFORM_OPERATORS` (explicit subject-to-local-operator-UUID JSON map).
Bootstrap operators must already have the relevant platform grant. Tenant creation and
invitation resend require `Idempotency-Key`; replay rechecks current authority.

`IDENTITY_REDIS_URL` backs both the step-up proof store and the permission-resolution
cache (org-model §5.2). When it is set, a user's effective grants are cached and
`IDENTITY_AUTHZ_CACHE_TTL_SECONDS` (default 30, range 1–300) is the revocation bound
(CLAUDE.md §5.4): a role change not caught by eager invalidation takes effect within
that window. Eager invalidation covers user-scoped grant changes (assignment
grant/revoke/regrant against a user, and group membership); group-subject assignments
and role permission edits are bounded by the TTL. A Redis outage is fail-open — grants
resolve live from the database, never blocking a request and never widening access.
When `IDENTITY_REDIS_URL` is unset, grants resolve live on every request and step-up is
unavailable.

Auth requires `AUTHENTIK_ISSUER`, `AUTHENTIK_CLIENT_ID`, `AUTHENTIK_CLIENT_SECRET`,
`NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `CONSOLE_URL`, `IDENTITY_URL`, and `AUTH_REDIS_URL`
for refresh coordination. All Auth instances share Redis and the session secret;
credential keys are HMACs and result payloads use authenticated encryption with
15-second TTLs. Redis failure denies refresh; existing unexpired access remains valid.
Use protected Redis networking and TLS where traffic crosses a network.
Configure the exact
callback URL `/api/auth/callback/authentik` in Authentik. Console uses `AUTH_URL`,
`IDENTITY_URL`, and the same `NEXTAUTH_SECRET`. For sibling subdomains set
`AUTH_COOKIE_DOMAIN` to their shared trusted parent domain. All subdomains receiving
this cookie must be controlled and trusted. Access/refresh tokens stay in encrypted
HttpOnly cookies and are omitted from the session JSON. Use HTTPS for shared cookies.

The Auth signup screen uses native Authentik enrollment through the Auth BFF,
with inactive, unverified accounts pending manual approval. See
[account registration](account-registration.md). Password recovery continues through
the provider login flow. Sign-out revokes Identity sessions and the provider refresh token on a
best-effort basis. During a dependency outage, local cookies are still cleared but
remote revocation is not guaranteed; retry administrative revocation if required.
Logout confirms on GET and executes through NextAuth's CSRF-protected POST.
Re-login after revocation/logout forces fresh provider authentication.
Previously minted gateway contexts expire within 60 seconds.
In-app fixed-window limits supplement nginx's global limits; limits are per process.

Step-up challenges/proofs use Redis TTLs. A completed challenge must follow a fresh IdP
login and a committed audit receipt. Proofs bind tenant, user, company and subject and
expire after five minutes. Session revocation invalidates them. Protected company paths,
query selection, body scopes, membership/assignment/definition/policy references all
check proofs. The default session bootstrap omits protected company details without a
proof. Tenant-wide discovery is not a company authentication ceremony. Redis failure
fails protected access closed. Browser proofs use company-specific HttpOnly cookies.
Successful completion also sets an HttpOnly company-selection hint. Console passes
that company and only its proof into session bootstrap; Identity rechecks local
scope. Logout removes both selection and proof cookies. Expired proofs trigger
company verification without exposing proof values to JavaScript.

Decision record, 2026-10-20: retain Authentik/NextAuth and enforce original-provider
authentication as the revocation boundary. Reuse existing Redis for encrypted
cross-instance refresh coordination; preserve financial retry identities and local
error recovery. Evidence: [login/API remediation](login-api-fixes-2026-10-20.md).

Support access requires a fresh authorized platform operator, reason/ticket, active
local target and bounded duration (maximum 30 minutes). It is read-only, revalidated on
every Identity request, and carries real/effective actor attribution to downstream audit.
Run `python -m identity.tasks.support_expiry` to audit expired sessions. The expiry task
is bounded and replayable; access is already denied at expiration without waiting for it.

## Private Azure documents

Set `IDENTITY_AZURE_BLOB` to JSON containing `account_url`, `container` and optional
`managed_identity_client_id`. The account URL is an HTTPS Azure Blob endpoint, with no
SAS or credentials. The SDK uses managed identity or environment credentials
(`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` supplied through a secret
manager). Keep the container private and disable public blob access on the account.
Grant the identity blob data permissions and the account-level ability to generate user
delegation keys. Container CORS allows only the trusted application origins, PUT/GET/HEAD
and necessary upload headers. Do not allow anonymous listing or wildcard origins.

1. Compute the file's SHA-256 digest and generate one document UUID. PUT
   `/v1/companies/{company}/documents/{document}/upload` with type, title, size, MIME,
   digest and optional issue/expiry dates. Reuse the UUID and identical body after an
   uncertain response. At most 20 pending uploads per company are allowed.
2. PUT the file with the returned headers to the five-minute create-only SAS. Only
   PDF, PNG and JPEG are accepted, up to 20 MiB. SAS cannot enforce the byte limit by
   itself; finalization verifies actual size and content. Monitor storage quotas and
   reconciliation backlog. An existing upload cannot be overwritten with this SAS.
3. POST `/{document}/finalize`. Identity verifies actual size, MIME, file signature and
   SHA-256, then creates an ETag-conditional immutable snapshot. The response is replayable.
4. POST `/{document}/download` after company authorization. The audited response holds
   a 60-second read-only snapshot SAS with attachment/octet-stream disposition. Treat
   these URLs as credentials: do not log, persist in business rows, or send to analytics.
5. POST `/{document}/lifecycle` to deactivate/reactivate a ready document. Metadata
   remains readable; inactive downloads are denied. A previously issued link lasts at
   most 60 seconds. Upload references and storage keys never appear in list responses.
6. Schedule company-scoped `/documents/reconcile` calls until `expired` is zero. Each
   call expires at most five overdue pending uploads after a one-minute safety margin,
   deleting base blobs and orphan snapshots. Storage failures roll back DB changes;
   rerunning after a partial cleanup is safe. Finalized documents are retained.

Historical references remain `storage_state=legacy` and fail closed for download until
an explicitly reviewed import verifies content and creates an Azure snapshot. No blind
migration of old public URLs occurs. These resources are for business/statutory company
documents, not storage of full personal national identity numbers. File signature checks
are not antivirus scanning. Configure enterprise content scanning if required by policy.

[Microsoft's user-delegation SAS documentation](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-user-delegation-sas-create-python)
describes the Azure RBAC/delegation setup used by this adapter.

Local protocol verification (no cloud account required):

```powershell
npm.cmd install --prefix .tools/azurite --no-audit --no-fund azurite@3.37.0
powershell -NoProfile -ExecutionPolicy Bypass -File start/win/azurite-local.ps1 -Action start
powershell -NoProfile -ExecutionPolicy Bypass -File start/win/azurite-local.ps1 -Action test
```

Azurite binds loopback port 10000, with generated credentials under ignored `.tools`.
The real HTTP test proves private reads, create-only upload, content verification,
snapshot stability after privileged overwrite and replayable cleanup. Azurite does not
prove cloud managed identity/user delegation; the adapter's delegation contract has
separate SDK tests and requires live Azure validation before deployment.

## Bank encryption and personal tokens

Set `IDENTITY_BANK_ACTIVE_KEY_ID` and `IDENTITY_BANK_ENCRYPTION_KEYS`, a JSON keyring of
base64-encoded 32-byte AES keys (at most eight). Keep old keys during rotation. New writes
store AES-256-GCM ciphertext with tenant/company/row associated data, key ID and last-four
hints. Reveal requires company authority, fresh authentication and a sensitive-read audit.
POST `/v1/companies/{company}/bank-encryption/rotate` repeatedly until `rotated` is zero;
each transaction handles 50 rows by default (at most 100), clears legacy plaintext and audits each rotation.
A missing old key fails closed. Never drop old keys before checking all row key IDs.

The Windows development env generator initializes a key ring when both settings
are missing and preserves existing bank data keys even with explicit env rebuilds.
It refuses partial or invalid active-key configuration. This is local development
setup only; production keys still come from the secret manager. The Console's
bank-profile setup can create a supporting company bank with company read/update
authority. Saved details stay masked. Because bank creation currently has no native
idempotency receipt, an uncertain create must be reconciled against available
company banks before another create; the form never repeats that request.

Personal tokens are shown once and stored as SHA-256 only. They last at most 90 days,
with at most 20 active tokens per user. Effective authority intersects requested scope
with the owner's current live grants. Administration/impersonation permissions are
excluded; interactive identity/preference/session mutations reject personal tokens.
They cannot provide company step-up or fresh bank reveal authentication. Revocation,
owner suspension and tenant suspension take effect on the next direct Identity request.

## Runtime field recovery

The launched owner entity is `identity.company`. Layout is tenant-wide presentation;
field-policy authorization remains independent. Definitions validate static choices,
conditions, types and scope. Dynamic option adapters and fiscal-reset auto numbering
are rejected until their owners exist. A used sequence configuration is immutable.

Definition updates validate/reindex at most 200 affected companies atomically. Larger
contract changes return conflict and require a reviewed migration; they never scan only
a subset and silently accept the remainder. For repair/default backfill use
`POST /v1/custom-field-definitions/{id}/rebuild` with a limit up to 100 and preserve the
returned definition hash and `next_after` cursor between calls. Clients persist this
progress; this API is not an autonomous job scheduler. Replays rebuild deterministically.
Missing/changed contracts fail closed. Required-field additions over existing records
must follow optional definition, backfill, then validated tightening.

## Notification and Audit

Use [Audit delivery rollout](identity-gap-contracts.md#audit-delivery-rollout) and
[local RabbitMQ](local-rabbitmq.md). RabbitMQ 4.3.5 / OTP 27.3.4.17 were installed only
inside ignored `.tools`; the real restart/redelivery/inbox/DLQ verification passed.

Identity Notification publisher variables: `IDENTITY_NOTIFICATION_BROKER_URL`,
`IDENTITY_NOTIFICATION_BROKER_USER`, `IDENTITY_NOTIFICATION_SECRET`,
`IDENTITY_NOTIFICATION_KEY_ID`, plus `IDENTITY_DATABASE_URL`. It signs only invitation
and preference events to `platform.notification`. Notification configures
`NOTIFICATION_IDENTITY_SOURCES` by key ID (`secret`, `broker_user`) and
`NOTIFICATION_IDENTITY_AUTH_ORIGIN`. Run `python -m notification.tasks.identity` and
`python -m identity.tasks.notification_publisher`. For each tenant install the built-in
invitation template using `python -m notification.tasks.invitation_template --tenant UUID`.

Invitation delivery uses its exact encrypted destination and content snapshot. Missing
routes/templates fail for retry; security invitations follow the documented mandatory
security policy. Preference projection is versioned and never overrides consent or
suppression for ordinary messages. Provider adapters still require their own configured
credentials and verified sender. The captured-provider tests are not real email delivery.

## Billing reservation contract

Install [identity-posting-client](../clients/identity-posting/pyproject.toml) into the
future Billing service; it imports no Identity ORM/domain code. Use an HTTPS HTTPX client,
Billing request key and configured Identity response keys. Identity variables are
`IDENTITY_BILLING_RESERVATION_CREDENTIALS` (key ID maps to secret and explicit
`tenant_id`/`company_id` scopes) and `IDENTITY_BILLING_RESERVATION_RESPONSE_SECRET`.

Persist a Billing operation UUID before calling configuration/reserve. Recalculate when
Identity returns a configuration mismatch. Only a verified `pending` receipt authorizes
starting a new money transaction. A replayed `confirmed`/`aborted` receipt means reconcile
the existing operation, never post again. Perform no synchronous HTTP call inside the
money transaction. Atomically commit the ledger and a confirmation outbox entry, then
have Billing's worker call terminal with the original UUID/reference/actual posting time.
Abort only after proving the ledger transaction did not commit. An unknown outcome stays
pending and freezes affected settings/features; there is no timeout-based automatic abort.

The client bounds/timeouts responses, rejects redirects, verifies the response signature
against the exact request, and never invents success on network errors. Retry with the
same durable operation ID and body. Confirmation preserves the first committed timestamp
and irreversible used-feature locks. Snapshot source capture propagates those locks.

Identity also emits `identity.posting_reservation.terminal`; publish with
`python -m identity.tasks.posting_publisher` using `IDENTITY_POSTING_BROKER_URL`,
`IDENTITY_POSTING_BROKER_USER`, `IDENTITY_POSTING_SECRET`, `IDENTITY_POSTING_KEY_ID`.
Billing must bind a durable authenticated/inbox-deduplicated queue to `platform.billing`
before the publisher starts. Actual Billing integration remains open because the service
is absent. Do not replace that release gate with these adapter tests.

## Rollback and observability

Monitor API failures, auth rate-limit rejections, Redis failure, pending document age,
failed bank rotations, oldest outbox event/exhaustion/DLQ counts and unresolved posting
reservations. Log identifiers/error classes only, never credentials or signed URLs.
The new metadata migrations downgrade on empty/new-data-free schemas; encryption,
Azure references and posting-history guards intentionally refuse destructive downgrade
until data has been reconciled/archived. Retain code compatibility and backups during a
rollout rollback; never remove durable freezes or audit records to make rollback pass.

## Reproduce verification

From `apis/identity`, use the synchronized virtual environment:

```powershell
.venv/Scripts/python.exe -m pytest -m "not mysql" -n 4 --cov=identity --cov-fail-under=93.97
.venv/Scripts/python.exe -m ruff check src tests ../../clients/identity-posting/src
.venv/Scripts/python.exe -m mypy src ../../clients/identity-posting/src
```

For actual MySQL tests, first start/check the isolated server using
`start/win/identity-test-mysql.ps1` from the repository root. Create a new empty database
on its loopback port 13396 and set `IDENTITY_TEST_MYSQL_URL` to that disposable database
in the test process. Run the following from `apis/identity` without xdist: these tests
upgrade and downgrade a shared database and must run serially.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_migrations.py tests/test_install.py tests/test_company_setup_mysql.py tests/test_review_mysql.py tests/test_gap_mysql.py -q
```

Never point this destructive migration test target at an application database. The
fixture's explicit test URL takes precedence over application environment configuration.
For broker restart and Azurite checks, use the dedicated commands above. From
`clients/api-client`, run `node scripts/generate.mjs --service=identity --check` and
`node --test tests/*.test.mjs`. The service selector preserves concurrent Catalog output.

## Decision log

- 2026-09-12: User selected Azure Blob. Use private user-delegation SAS and immutable
  snapshots; no account key or long-lived Azure credential is put in application responses or source control.
- 2026-09-12: Added a separate Billing client package and terminal publisher while
  retaining the absent Billing service as an explicit live integration gate.
- 2026-09-12: Shared version 0.17.0 fixes valid empty AES-GCM plaintext round trips,
  adds tested audit-context restoration/rate limiting, and synchronizes consumer locks.
