# Local login setup

## Current computer: 2026-10-20

MySQL 9.6 is installed and the supplied administrator login connected successfully.
Seven application databases were created and migrated using the existing migrations.
Runtime credentials are generated, restricted to their own database, and saved only in
ignored `start/win/env/<service>.env` files. The administrator password was not saved.

| Database | Migration | Tables |
|---|---|---:|
| identity | 0066 | 46 |
| audit | 0003 | 4 |
| catalog | 0178 | 152 |
| notification | 0026 | 26 |
| accounting | 0152 | 96 |
| vouchers | 0085 | 62 |
| reports | 0033 | 29 |

Identity installation populated 168 currencies, 239 countries, 5,027 states,
12 system roles, 479 role permissions and the shipped business classifications.
It creates no users, tenants or companies. Existing unrelated databases were preserved.
Runtime accounts have no DDL or grant authority; Audit has only SELECT/INSERT on
`audit_event`, with separate mutable infrastructure grants. Live connection and denied
cross-database reads passed for every account; Audit evidence deletion was denied.
All seven API readiness probes passed with these credentials.

Redis is already installed and listening on localhost. Identity and Auth Redis URLs are
configured. Ignored Auth/Console `.env.local` files now contain their local URLs, shared
session secret and service bases. Identity has the planned local HTTPS OIDC settings.
Auth's provider client secret is configured after the local OAuth blueprint applied.
Authentik runs in the Ubuntu VM. **Full application login still needs an activated
Identity user/tenant and the intended roles/company membership.**

## Choosing where Authentik runs

This laptop runs Windows 11 Enterprise build 26100, with about 63 GB RAM and 348 GB
free disk. This session is not elevated; Docker and WSL are absent. Windows reports an
active hypervisor, so the CPU flags alone cannot establish WSL availability. Installing
WSL/Docker needs an administrator and may need a restart or device-policy approval.
At the initial inspection, no Windows feature or Docker installation had been attempted.

Update: at the user's request, Hyper-V's PowerShell management feature was enabled and
**Bill-Authentik-Ubuntu** was created with 4 GB RAM, two CPUs and a 32 GB disk on the
existing Default Switch. Docker Desktop and WSL remain uninstalled. The official
Ubuntu 24.04 dated VHD download passed SHA-256 verification; its Azure-only datasource
was corrected locally to NoCloud. SSH login, console password provisioning and guest
Docker installation were verified. All Authentik containers are healthy, the OAuth
blueprint applied, and verified HTTPS discovery/RSA JWKS checks passed. The local
`akadmin` password was checked successfully. Auth/Console started with their settings.
Connection details, the SSH key and credentials are in ignored files under
`start/win/authentik-vm/`; [VM instructions](../start/win/authentik-vm/README.md).

Authentik can instead run on another Linux machine or an existing server. This leaves
the UI, APIs, MySQL and Redis on this laptop. Use the server's trusted HTTPS issuer,
client ID/secret, and discovery `jwks_uri` in Auth `.env.local` and `IDENTITY_OIDC`;
audience must equal the OAuth client ID. The server must allow the localhost callback
below. Restart Identity and both web apps after changing configuration.

## Running the VM on this machine

Use `start/win/authentik-vm/start.bat` and `tunnel.bat` before the APIs/UI.
`ssh.bat` opens the guest shell. Run VM start/stop/status as administrator.
The detached, managed tunnel stops with `stop-tunnel.bat`. Its loopback bindings
preserve the localhost HTTPS issuer. The HTTPS certificate and Windows Current User
CA trust are configured and verified.

Update 2026-10-23: the VM now has a dedicated internal `Bill-HostLink` adapter at
`192.168.247.2/30`, paired with Windows `192.168.247.1/30`. SSH/tunnel scripts use that
fixed address; the Default Switch remains available for guest internet access. See the
[VM instructions](../start/win/authentik-vm/README.md#verification-and-decision-record)
for setup, persistence and the successful sign-in checks with the guest internet adapter down.

Two failed fresh Authentik databases (`authentik`, `authentik_clean`) were preserved
while correcting blueprint file ownership. The active guest database is
`authentik_ready`; server initialization completed before the worker started.
The Ubuntu trust store includes the host network CA for verified Docker downloads.
The initial cloud-init run reports an error from its failed image download; subsequent
recovery completed setup. Windows Docker Desktop and WSL remain uninstalled.

## Prepared local container setup

The ignored `.tools/authentik/` directory contains the official Authentik 2026.8.4
Compose definition and generated `.env` secrets. Ports 9000/9443 bind to loopback.
PostgreSQL 16 runs in its own container and persistent volume; it does not use or alter
the installed Windows PostgreSQL service. The Docker socket mount was removed because
this OAuth provider needs no automatic outpost deployment. This Authentik version uses
PostgreSQL without a Redis service. It is separate from the APIs' existing Redis.

If an administrator enables WSL 2 and installs Docker Desktop, start Docker Desktop in
Linux container mode, then use these from the repository root:

```bat
start\win\start-authentik.bat
start\win\status-authentik.bat
start\win\stop-authentik.bat
```

They target only Compose project `bill-authentik`; stop preserves containers and data.
Start/status certify container state, not configured authentication. Inspect container
logs when startup fails. Authentik is intentionally separate from `start-all.bat`.

## HTTPS and provider configuration

1. Open `http://localhost:9000`, complete initial setup, and set the `akadmin` password.
2. Import `.tools/authentik/tls/localhost.crt` and `localhost.key` in Authentik's
   certificate/key-pair settings. Select that certificate as the default Brand's web
   certificate. The generated certificate covers localhost and 127.0.0.1 for 90 days.
3. Trust `.tools/authentik/tls/ca.crt` in the browser/Windows Current User Trusted Root
   store if local certificate trust is permitted. The web launcher supplies this CA to
   Node, preserving an existing `NODE_EXTRA_CA_CERTS`. Identity uses a CA bundle that
   retains public roots. Do not disable TLS verification. Renew the certificate before
   expiry; keep its private key and CA key local.
4. In **Applications > Applications**, create an OAuth2/OIDC application with slug
   `janso-local`. Use a confidential client with ID `janso-local`, the standard
   authentication/authorization flows, and a strict redirect URI:
   `http://localhost:4310/api/auth/callback/authentik`.
5. Choose an RSA signing key (RS256), per-provider issuer mode, access-token validity
   `minutes=5`, and the hashed-user-ID subject mode. Assign `openid`, `profile`, `email`
   and `offline_access` scope mappings. Create and assign a scope mapping named
   `billing.api` with expression `return {}`. Permissions stay in Identity.
6. Copy the generated provider client secret into Auth `.env.local`. Check HTTPS
   discovery at `https://localhost:9443/application/o/janso-local/.well-known/openid-configuration`.
   Its issuer and JWKS URI must match Auth and Identity settings exactly. Original
   `auth_time` must remain unchanged on refresh; this Authentik version supplies it.
7. Create a regular Authentik user, then provision its verified subject into an active
   Identity user under an active tenant with the intended roles/company membership.
   `akadmin` is the Authentik administrator, not an application account. The Identity
   installation command does not provision this user. Choose the user's identity and
   tenant/company details before provisioning; there is no default application password.

The stock Authentik email mapping returns `email_verified=false`. Invitation acceptance
requires a real email verification flow and verified mapping; do not hardcode it true.
Ordinary login does not require invitation acceptance.

## Run after provider and user setup

```bat
start\win\authentik-vm\start.bat
start\win\authentik-vm\tunnel.bat
start\win\start-all.bat
start\win\start-web.bat
```

Open `http://localhost:4310/login`. Check the Console session, a refresh after five
minutes, logout and fresh re-login. Stop with `stop-web.bat`, `stop-all.bat`, and
`authentik-vm\stop-tunnel.bat` and `authentik-vm\stop.bat`. Backend stop leaves
the installed MySQL service running.
Migrations use a separately authorized DDL account; runtime accounts cannot rerun them.

## Verification and review

All seven API readiness checks passed after restarting Identity with OIDC/TLS settings.
Auth login, provider and CSRF endpoints returned 200; unsigned Console navigation
redirected to Auth. A real NextAuth sign-in POST created the expected HTTPS authorization
URL, client ID, exact callback and `billing.api` scope. No application user was created
and a completed business login was not claimed. The web launcher suite passed 22 tests,
including local CA selection and preservation of an explicit CA file. PowerShell parser,
cloud-init schema, TLS hostname/chain, database grants/isolation and ignored secret-file
checks passed. No secrets were published.

Manual simplification/security review covered least-privilege database grants, secret
storage, VM targeting, graceful stop, loopback SSH forwarding and verified TLS. The
repository slash-command review tools are unavailable; this is the manual fallback.
VM graceful shutdown/restart was not live-verified because the elevation attempt
remained pending and was cancelled; the VM remains running. The remaining login
setup limit is user/tenant/role provisioning. Authentik's version-check
task also needs the network CA inside its container; that optional outbound check does
not block local authentication.

Sources: [official installation instructions](https://docs.goauthentik.io/install-config/install/docker-compose/),
[pinned Compose source](https://github.com/goauthentik/authentik/blob/version/2026.8.4/lifecycle/container/compose.yml),
[OAuth provider instructions](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/create-oauth2-provider/).


## First-run wizard ? 2026-10-20

Identity now includes revision 0066 and its installation-control seed. Run
`start/win/platform-setup/prepare.bat`, restart Identity/Auth, and use
<http://localhost:4310/setup> to provision the intended first platform administrator.
This computer has been prepared; its private setup key is in
`start/win/platform-setup/setup-key.txt`. [Wizard instructions](platform-setup.md)
explain Authentik's verified-email mapping and the administrator-confirmed attribute.
No test user/tenant was created in the real installation during verification.
