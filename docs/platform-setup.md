# First-run setup wizard

> **Provider note (2026-10-31).** This page describes the wizard with `AUTH_PROVIDER=authentik`. With `local` (the default) the same seven steps run with no Authentik: the administrator step asks for the first administrator's name, email and password and creates that account in Identity (setup key required; its email counts as verified because the operator typed it), then signs in with it; the Authentik email-verification section below does not apply; and the readiness check is named *Identity signing keys*. See [local authentication](local-auth.md).

The Auth application exposes `/setup`. Seven steps unlock setup, check configured
connections, collect platform defaults and the internal administration workspace,
authenticate the intended administrator through Authentik, explain optional email
delivery and review/complete the installation. Light, Dark and Ledger themes use
the existing shared design system.

## Preparation

Deploy Identity revision `0066` and run `python -m identity.install` with a deployment
account. Runtime accounts retain only data permissions. Installation seeds create
the singleton control row; application startup performs no DDL or seed writes.

The shipped installation name defaults to **KiscoBooks**; its publisher is
**Khushiyan Enterprise**. The generic `platform_installation.name` field remains
`VARCHAR(200)` nullable until setup completes; no table/column rename or new DDL
is needed for this data change. The installation seed synchronizes an exact legacy
Janso name (case-insensitive, ignoring surrounding whitespace) on deployment,
without changing custom platform names, customer organisations/companies or
bootstrap completion/replay evidence. Completed installations receive one system
`platform.details_updated` outbox event in the same transaction. Re-runs are no-ops.

For an existing installation, without running unrelated pending migrations:

```powershell
start/win/sync-branding.bat -DryRun
start/win/sync-branding.bat
```

This is the deployment seed workflow, using the private `identity.env` and ORM
model; it runs no provider operations or direct manual SQL updates. Alternatively,
a freshly authenticated operator with `platform.config.manage` can edit the name
through the existing Platform details UI/API. The publisher name is product
branding, not a replacement for any customer's stored company name.

Run `start/win/platform-setup/prepare.bat`. It generates a random local key, protects
`setup-key.txt` with the current Windows account's ACL and writes matching
`IDENTITY_SETUP_KEY` values to Identity and Auth's ignored environment files. It
derives the service readiness URLs from `start/win/conf/services.json`.
Preparation preserves matching keys, restricts private files to the Windows account,
and restores environment contents on a write failure. Run
`start/win/platform-setup/check.bat` after restart to verify all required connections.

Restart Identity and Auth and start the API/Redis/Authentik dependencies. Visit
<http://localhost:4310/setup>. Database passwords, OAuth client secrets and SMTP
credentials stay in server configuration; the browser cannot select probe targets.

## Authentik email verification

Authentik's default OAuth email mapping explicitly returns `email_verified: false`.
For this application, attach the mapping defined in
`start/win/platform-setup/authentik-email.yaml` to the `janso-local` provider and
remove its default email mapping. The local VM launcher
`start/win/platform-setup/apply-authentik.bat` applies this file over SSH. It targets
the standard local Bill scopes including `billing.api`; customize the scope list
before applying it to a provider with additional mappings. Client secrets and
callback addresses remain untouched.
Enable only the provider's `authorization_code` and `refresh_token` grant types.
Authentik 2026.8 defaults new providers to an empty grant-type list, which otherwise
rejects the browser authorization request before displaying sign-in.

The IdP administrator must independently verify the intended person's email and set
their Authentik user attribute `billing_email_verified` to the JSON boolean `true`.
Users must not be able to edit this attribute through enrollment/profile flows.
This attribute produces a signed verified-email claim; billing never trusts a
browser-supplied email or verification flag. The setup wizard requires fresh sign-in
within five minutes. Authentik manages the password and authentication factors.
The wizard requests `prompt=login` with `max_age=300`, matching the server freshness
check. Authentik may prompt a newly signed-in user a second time to satisfy its explicit
reauthentication policy; complete that prompt. Identity independently checks `auth_time`
and rejects evidence older than five minutes.

After sign-out, billing revokes the previous provider authentication time. The Auth
login retry and company verification request `prompt=login&max_age=1`: Authentik
2026.8 ignores a zero age bound and can otherwise reuse its remembered reauthentication
state. Sign in with the personal account activated by the wizard. Authentik's `akadmin`
account alone has no billing access.

## Security and recovery

The setup key establishes installation authority before the first local user exists.
It is compared in constant time, never returned by an API and never stored in browser
local/session storage. Setup access and the draft live in an encrypted HttpOnly,
SameSite cookie scoped to `/api/setup`; Authentik session cookies remain separate.
The draft survives the authentication redirect for 30 minutes. POSTs require the
configured Auth origin. Application and Identity request limits bound abuse; deploy
the web application behind an ingress rate limiter for multi-worker installations.
Request streams are bounded before JSON parsing, and draft size is limited by UTF-8
bytes to keep the encrypted cookie within browser limits. Only active countries and
currencies are offered. Invalid origin ports are rejected before any records commit.
The displayed application origin comes from the configured Console URL; editing
installation metadata does not change the server environment or OIDC callbacks.

Completing creates the operating tenant, active `platform_admin` user, system role
assignment, installation metadata and four audit outbox events in one transaction.
The singleton row is locked to serialize concurrent completion. A lost response can
be retried by the same fresh provider subject with the same normalized details;
different subjects/details are refused. Persisted operator identity works across
restarts and still requires active local user/tenant and live grants.

Completion permanently closes first-run setup. Existing tenants also disable setup
even without a completion record. There is no HTTP reset, and an empty user table
does not reopen a completed installation. Restore the complete database from backup
for disaster recovery; operator additions remain an explicit administrative procedure.

The resulting Console `/platform` page lists tenant summaries through the guarded
platform API. It exposes no tenant business data. Tenant creation/lifecycle APIs
remain available; plan/configuration management screens are outside this delivery.
The directory follows signed paging cursors and lets users return to the first page.

Email transport configuration and sending test emails are deferred to Notification's
server-administered setup; this optional wizard step states that limitation explicitly.

## Decision log

- 2026-10-30: synchronize KiscoBooks branding through the existing deployment seed
  and generic installation metadata model. Preserve exact custom platform names,
  customer records and first-run replay proof. Keep data updates outside DDL
  migrations and allow a standalone seed to avoid applying unrelated migrations.
  Completed legacy-name changes carry an atomic system audit event.
