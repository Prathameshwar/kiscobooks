# Local authentication provider

`AUTH_PROVIDER` selects who owns credentials: `local` (the default) or `authentik`. Both stay
supported permanently; the choice is per installation. With `local`, **Identity is the OpenID
Connect provider** for the first-party clients (Auth app, Console, later mobile): it owns sign-up
credentials, sign-in, password change and recovery, and issues the same kind of RS256 access
token the platform already verifies (`billing_platform.oidc.AccessTokenVerifier`), so no
downstream service changes. Decision record: [tech-stack](tech-stack.md) decision log,
2026-10-31. Delivery checklist: [local-auth-todo](local-auth-todo.md).

This reverses, for the `local` provider only, the 2026-10-20 decision that Authentik is the
credential owner ([account-registration](account-registration.md)). With `authentik` that decision
is unchanged and so is every Authentik flow.

## 1. Scope

In: email + password sign-up with manual review, username or email + password sign-in (authorization code + PKCE),
refresh with rotation, sign-out revocation, password change, recovery by **operator-issued
one-time link**, tenant-administrator provisioning, first-run platform administrator creation.

Out of v1 (deliberately): MFA/TOTP, social login, SAML, WebAuthn, recovery by email (SMTP is
still deferred — [account-registration](account-registration.md)), importing Authentik password
hashes. "Step-up" means entering the password again (`prompt=login`).

## 2. Configuration

Identity (`IDENTITY_` prefix):

| Variable | Meaning |
|---|---|
| `IDENTITY_AUTH_PROVIDER` | `local` (default) or `authentik`. |
| `IDENTITY_LOCAL_AUTH` | JSON `LocalAuthSettings` (below). Required for `local` to work; without it the local endpoints answer 503 and nothing else changes. |

`LocalAuthSettings`: `issuer` (exact string in every token; the public URL of the OIDC mount,
e.g. `https://bill.example.com/identity/oidc`), `audience` (the API audience in access tokens;
it **must differ from every client id**, because an ID token's audience is the client id, and an
ID token must never pass as an access token), `auth_ui_url` (Auth app origin, where the sign-in page and
recovery links live), `clients[]` (`client_id`, `secret_sha256`, `redirect_uris[]`, exact match),
`bff_secret` (≥ 32 bytes, shared with the Auth app server), `key_encryption_key` (32 bytes,
base64; encrypts signing keys at rest), TTLs (`access_token_seconds` 300, `refresh_token_seconds`
43200, `session_seconds` 2592000 — the absolute life of one sign-in however often it is
refreshed — `code_seconds` 60, `request_seconds` 600, `recovery_token_seconds` 600), lockout
(`max_failed_attempts` 5, `lockout_seconds` 900) and `registration_enabled`.

`jwks_url` (optional) is where services fetch the key set when the public issuer URL is not
reachable from them; it defaults to `<issuer>/jwks`.

With `local`, Identity's own verifier settings are **always derived** from `IDENTITY_LOCAL_AUTH`
(`issuer`, `audience`, the key-set address and the access-token lifetime); a stale
`IDENTITY_OIDC` is ignored, so the two can never disagree about who issued a token. The
verifier accepts **plain HTTP only for loopback hosts**
(`localhost`, `127.0.0.1`, `::1`) so a development machine needs no certificate; any other host
must be HTTPS.

Auth app (`mfes/apps/auth/.env.local`): `AUTH_PROVIDER` (default `local`), `AUTH_LOCAL_ISSUER`,
`AUTH_LOCAL_CLIENT_ID`, `AUTH_LOCAL_CLIENT_SECRET`, `AUTH_LOCAL_BFF_SECRET`; `IDENTITY_URL` and
`NEXTAUTH_*` as today. Existing Authentik installs set `AUTH_PROVIDER=authentik` on both sides
and keep every `AUTHENTIK_*` variable. Identity keeps only the SHA-256 of the client secret.
`start\win\local-auth.bat` writes every one of these for a development machine (`setup.bat`'s
environment step runs it too whenever the provider is `local`, and regenerating `identity.env` keeps
`IDENTITY_AUTH_PROVIDER` and `IDENTITY_LOCAL_AUTH`, because replacing the key-encryption key would make
every stored signing key unreadable); it is safe to
run again, keeps existing secrets (the key-encryption key must never change once a signing key
is stored under it), leaves an `authentik` installation alone and never prints a secret.

Until `AUTH_PROVIDER` is set in the Auth app a dev server defaults to `local` and **fails
closed** (the sign-in page reports the provider as unavailable); run the script, or set
`AUTH_PROVIDER=authentik` to keep using Authentik.

## 3. OpenID Connect surface (public; nginx path `/identity/oidc/…`, service path `/oidc/…`)

Authorization code with PKCE (S256 only), confidential clients, no implicit/hybrid, no dynamic
registration, no userinfo.

| Endpoint | Behaviour |
|---|---|
| `GET /.well-known/openid-configuration` | Discovery. `issuer` is the configured string. |
| `GET /jwks` | Public RSA keys only (`kty RSA`, `use sig`, `alg RS256`, `kid`); never a private member. |
| `GET /authorize` | Validates `client_id`, **exact** `redirect_uri`, `response_type=code`, `scope` contains `openid`, `state`, `nonce`, `code_challenge`+`S256`. An unknown client or redirect is a 400 and **never** a redirect. Any other fault redirects to the validated URI with `error`/`state`. Success stores a hashed, 10-minute authorization request and redirects to `<auth_ui_url>/signin?request=<id>`. There is no SSO cookie: every authorization asks for the password, so `prompt=login`/`max_age` are always satisfied. |
| `POST /token` | `authorization_code` (code + `code_verifier` + `redirect_uri`) or `refresh_token`. Client auth `client_secret_post` or `client_secret_basic`. `Cache-Control: no-store`. |
| `POST /revoke` | RFC 7009 for refresh tokens; revokes the whole family; always 200. |

Access token (RS256, `kid` header): `iss`, `aud` = configured audience (no `azp`), `sub`, `exp`,
`iat`, `jti`, `auth_time` (the original sign-in, preserved across refresh), `scope` (granted,
contains `billing.api`), `email`, `email_verified`. Lifetime ≤ `access_token_seconds` (≤ 900).
ID token: `iss`, `aud` = client id, `sub`, `exp`, `iat`, `auth_time`, `nonce`, `email`,
`email_verified`, `name`, `billing_registration_region` (`{country_code,state_code}`, private
claim the setup form reads). Refresh token: opaque 256-bit, only with `offline_access`.

Refresh rotation: each use marks the token used and issues a successor in the same family.
**Presenting a used token revokes the family** (theft signal) and fails with `invalid_grant`.

## 4. Auth-app-only endpoints (`/internal/v1/local-auth/…`)

Never routed by nginx (`/identity/internal/` is a 404 publicly). Every call needs
`X-Auth-Bff-Secret` (constant-time compared). Errors use the platform envelope
`{"error":{"code","message"}}`; field errors add `"fields"`.

The Auth app is the only caller, so Identity cannot tell end users apart by network address. The
Auth app therefore forwards the end user's address in `X-Client-Address`, and Identity throttles
sign-in, registration and recovery per that address. **When the header is absent no per-address
limit is applied** — a per-caller window would be one shared budget for the whole installation.

The address is believed only as far as this installation vouches for it. `X-Forwarded-For` can be
trusted only at its end, where a proxy the installation runs appended what it saw; everything
earlier is whatever the client claimed. `AUTH_TRUSTED_PROXY_HOPS` (Auth app, `0`–`3`, default `0`)
says how many such proxies stand in front of it: the entry that many places from the end is the
person, a shorter chain is refused, and with `0` — also the case when the app is reached directly
— no header is used at all, because a client could otherwise rotate its address to dodge a limit
or borrow someone else's to spend their budget. Behind the shipped nginx, set it to `1`.

| Call | Success | Failures |
|---|---|---|
| `GET /status` | `{provider:"local",registration_enabled,recovery:{link:true,email:false},setup:{administrator_exists}}` | 401 secret, 503 unconfigured |
| `GET /requests/{id}` | `{expires_at}` | 404 unknown/expired/used |
| `POST /login` `{request_id,identifier,password}` | `{redirect_to}` (callback URL with `code`,`state`) | 401 `invalid_credentials` (identical for unknown username/email and wrong password), 403 `account_pending` and `account_disabled` (only after the right password), 404 request, 423 `account_locked` `{retry_after}` + `Retry-After`, 429 |
| `POST /registrations` `{name,username,email,password,country_code,state_code,workspace_name?}` | 201 `{status:"pending-review"}` | 422 fields (a username shaped like a derived provisioning name is refused); 422 `registration_unavailable` (generic: does not say *which* detail is taken — see §6 on what it still reveals); 503 |
| `POST /password/recovery/inspect` `{token}` | `{valid:true}` | 404 |
| `POST /password/recovery/redeem` `{token,new_password}` | 204 | 404, 422 `fields.new_password` |
| `POST /setup/administrator` `{name,email,password}` + `X-Setup-Key` | 201 | 403 key, 409 setup closed / account exists, 422 |

Public with the user's access token: `POST /v1/session/password` `{current_password,new_password}`
→ 204; 401 bad token; 422 `fields.current_password` for a wrong current password (rate limited,
counts toward lockout).

Operator-issued recovery (local only; 409 otherwise): `POST /v1/users/{user_id}/password-recovery`
`{reason}` and the existing platform administrator recovery endpoint both return
`{recovery_url, expires_at}` — `<auth_ui_url>/reset?token=…`, valid 10 minutes, single use.
`delivery: "email"` answers that email recovery needs configured delivery; use a link.

A link is a way into someone's account, so the tenant route is the most guarded in the provider:

- the operator needs `user.update` at tenant scope, **and** must have typed their own password
  within the last 5 minutes (`auth_time`, which a refresh preserves: a kept-alive stolen session
  never looks fresh) — otherwise 403 `reauthentication_required` and the Console offers "Sign in
  again";
- not for yourself, not for an inactive user, not for a user with no local sign-in;
- never a route to more authority than the operator holds, **measured where the target holds
  it**: each of the target's grants is checked against the operator's permissions at that
  grant's own scope, so company A's clerk cannot reset someone who posts in company B or
  tenant-wide. Grants that start in the future count, on the day they start (the link
  outlives today). The refusal never names a permission;
- never for the platform operator (the configured operators and the administrator first-run
  setup recorded): that authority is configuration, not a grant, so no permission
  comparison can see it. Operators are recovered from the platform access page;
- an API token cannot be used (the route and `POST /v1/session/password` need an interactive
  session);
- audited as `user.password_recovery_requested` against the target, with the operator and the
  reason; the target's later `user.password_recovery_completed` is recorded as the target.

Sign-in accepts a username or email address in `identifier`, trims surrounding whitespace and
lowercases it. A value containing `@` is looked up only as an email; all others are looked up
only as usernames. Provisioned administrator usernames are accepted. The old `email` request
field remains an alias for compatibility; sending both fields is rejected. The browser form
uses a text input labelled "Username or email address". Both identifiers share the resolved
identity's rate-limit budget and credential lockout. Internal routes stay outside OpenAPI.

## 5. Data (identity database, MySQL; installation-global, no `tenant_id`)

A sign-up exists before any tenant does, exactly as an Authentik account does, so these tables
are deliberately outside the tenant filter and reachable only through the code in
`identity/local_auth/`. `docs/identity-schema.md` §6.

| Table | Purpose |
|---|---|
| `local_identity` | `seq` INT PK (= review `provider_id`), `uid` UUID (= `provider_uuid`), `sub` CHAR(64) unique (the token subject), `email` unique, `name`, `username` unique, region, `workspace_name`, `path`, `status` (`pending`/`active`/`disabled`), `email_verified_at`, review/provision command markers, timestamps. |
| `local_credential` | `identity_seq` PK/FK, `password_hash` (argon2id), `hash_version`, `password_changed_at`, `failed_attempts`, `lock_ends_at`. |
| `local_recovery_token` | SHA-256 of a 256-bit token, `expires_at`, `used_at`, `issued_by`. |
| `local_signing_key` | `kid`, public JWK, private JWK **AES-256-GCM encrypted** (associated data = `kid`), `status` (`active`/`retiring`/`retired`). |
| `local_authorization` | Hashed request id → (after login) hashed code; client, redirect, scope, nonce, PKCE challenge, `authenticated_at`, `consumed_at`. |
| `local_refresh_token` | Hashed token, `family_id`, identity, client, scope, `authenticated_at`, `rotated_at`, `revoked_at`, `expires_at`. |

Lifecycle is `status`, or a date; never a second boolean beside it (rule 4.12).

## 6. Security controls

- **Passwords**: argon2id (memory-hard, per-hash random salt, parameters stored in the hash so they
  can be raised; `needs_rehash` upgrades on sign-in). 6–128 Unicode code points
  ([account-registration](account-registration.md) amendment, 2026-10-20); strength is advice.
  Never logged, audited, echoed or put in a URL. Hashing is ~140 ms and 64 MiB, so it runs in a
  small bounded thread pool (`local_auth/offload.py`: at most 4 at once, 8 more waiting, then
  429) instead of on the event loop — Identity is the gateway's authorizer, and a stalled worker
  stalls everything. argon2-cffi releases the GIL, so this is real parallelism. The total is
  held to at most half the 30-connection database pool (a test pins it): a request keeps its
  connection while its hash runs, so more in flight would let a flood of sign-ins queue every
  other service's authorization behind them.
- **What sign-in does and does not reveal**: an unknown username/email and a wrong password answer
  identically and cost the same hashing time (a fixed dummy hash); a pending or disabled status
  is revealed only after the right password. Two things are *not* hidden, and cannot be until
  email verification exists: registration answers 201 for a new email and a generic 422 for a
  taken one, and the sixth wrong guess at a real account answers 423 while an unknown email
  never does. Neither names a person or a field, and both are slowed by the throttles below.
- **Throttling**: per account (lockout after `max_failed_attempts`, `lockout_seconds`), per
  authorization request id and per forwarded end-user address (§4) inside the handlers, a
  window limiter on `/oidc/authorize`, and nginx `limit_req` on the `/identity/` location (10
  r/s per address, burst 30; the token exchange comes from the Auth app server, so that one
  budget is shared by every user's code exchange — raise it with the installation, not per
  user). Details that matter:
  - The failure counter and the lock are committed even though the attempt fails, and the
    credential row is **locked while a failure is counted**, so a burst of simultaneous guesses
    is counted one by one (a lost update would count a burst of N as one).
  - The input window is keyed on the identifier folded the way the database folds it (case and
    accents), so `ásha@…` and `asha@…` — one row to MySQL — share one budget.
  - The throttles have their own table (`app.state.local_limiter`, 65,536 keys, wiped each
    minute), because their keys are text a caller chooses and the shared middleware table
    refuses new keys when full. Each key is also hashed into one of 4,096 slots per bucket, so
    inventing keys cannot fill the table and lock everyone out — at worst it crowds a few
    slots, whose keys then share a budget. A second window keyed on the resolved identity ID
    gives username and email one account budget; both also use the same credential failure counter. `/oidc/token` and `/oidc/revoke` have no per-address window: they
    are authenticated by a 384-bit client secret, and the only address they see is the Auth
    app's own.
  - A locked account still costs a hash so timing does not reveal the lock.
  - Accepted: because lockout is per account, anyone who knows an email can keep that account
    locked (5 guesses per 15 minutes). That is the price of lockout; an operator recovery link
    clears it, and the per-address limit makes it expensive from one place.
- **Tokens at rest**: codes, refresh tokens, recovery tokens and request ids are 256-bit random
  and stored only as SHA-256. Authorization codes are single use, bound to client, redirect URI
  and PKCE challenge, and live 60 s. Reuse of a code revokes the refresh family it created.
- **Signing**: RS256 only, key id in the header, private key encrypted at rest and decrypted in
  memory; rotation publishes the new key before use and keeps the old public key until its last
  token expires. Operators rotate with `python -m identity.local_auth.cli rotate-key`, later
  `retire-keys` (a rotated-out key is retired only after one more access-token lifetime plus a
  minute), and `purge` (spent authorizations, recovery tokens and refresh tokens older than 7
  days). None of them prints key material.
- **Sessions**: a password change or recovery completion sets `user.tokens_valid_after_at`
  (existing durable revocation), revokes every refresh family for that identity, voids any
  recovery link still open, and makes an authorization code issued *before* the change
  unredeemable (otherwise a thief who signed in with the old password could redeem the code
  afterwards and have it stamped past the revocation). Refreshing slides the idle window
  (`refresh_token_seconds`) but never the session: `session_seconds` after the original sign-in
  the password is asked for again. Two simultaneous refreshes of one token are treated as reuse
  (one wins, the family is revoked, the Auth app's Redis coordinator avoids this for a single
  browser), by design.
- **BFF boundary**: the Auth app server is the only caller of `/internal/v1/local-auth/*`.
- **Derived names**: the usernames the platform gives provisioned accounts
  (`bill-admin-<32 hex>`, `admin-<32 hex>`) cannot be chosen at sign-up, so nobody can occupy a
  name an administrator will need.
- **Signing keys and rollback**: a signing key created by the first request is not remembered
  until the transaction that created it has committed, so a rollback cannot leave the process
  signing with a key that was never published.
- **Request size**: a form body is read as a stream and refused past 16 KB, whether or not it
  announced a length, so one request cannot make the service buffer what the proxy allows.
- **First run**: the installation row is locked while the setup administrator is created, so
  two simultaneous calls make one account. Setup creates the account before the person signs
  in to finish it, so a mistyped password would strand it:
  `python -m identity.local_auth.cli reset-setup-administrator` forgets an unused one (only
  while setup is open and no user points at it) so the step can be done again.
- **Starting up**: a legacy `IDENTITY_OIDC` with no provider chosen and no
  `IDENTITY_LOCAL_AUTH` is refused at startup — Authentik's tokens would still verify while
  review, provisioning and recovery quietly switched to the local tables.
- **Accepted, not fixed**: a sign-up is an unverified claim to an email address and can squat it
  until a reviewer rejects it (review is the verification; approval is what sets
  `email_verified_at`, and a tenant-administrator operator who then picks that account with
  "select it instead" makes the squatter an administrator — read the match before choosing);
  the password an operator types for a new tenant administrator is not forced to change at
  first sign-in; the `/reset?token=` link sits in the browser's history for the ten
  minutes it lives; the Console shows a recovery link of the right *shape* but does not pin its
  origin to the Auth app (it comes from Identity over the operator's own session).
- **Audit** (outbox, same transaction, in `events/audit_contract.py`): `user.sign_in`,
  `user.account_locked`, `user.password_changed`, `user.password_recovery_requested` (an
  operator issued a link), `user.password_recovery_completed`, `user.refresh_reuse_detected`,
  `user.sign_in_provider_changed` (an operator moved the account to local sign-in) —
  recorded against the linked `user` and its tenant. A failed sign-in is counted on the
  credential, not audited per attempt (that would let an attacker fill the audit trail). A
  sign-up or an identity with no user yet is audited by the existing account-review decision;
  before then only a redacted structured log line exists (no email, no password). Signing-key
  rotation is an operator command and is not audited (the key table is installation-global).

## 7. Account review and provisioning without Authentik

`LocalAccountProvider`, `LocalAdministratorProvider` and `LocalRecoveryProvider` implement the
same methods the Authentik adapters expose (`page`, `pending_email`, `read`, `apply`, `subject`;
`by_email`, `confirm`, `create`, `activate`; `recover`) over the tables above, so the review
state machine, tenant provisioning and administrator recovery are unchanged. `subject` is the
identity's 64-hex `sub`; `apply(active, verified)` sets `status` and `email_verified_at` and
stamps the command marker the reconciler checks. `AUTH_PROVIDER` picks the adapter at one factory
(`identity/services/identity_provider.py`).

## 8. Limits and open items

- `user.authentik_sub` keeps its name for now; it holds the subject of whichever provider is
  active. Renaming it to `idp_sub` is a separate migration.
- No migration of Authentik *credentials*: the provider is chosen per installation. Existing
  *accounts* are moved with `adopt-users` (§9), which re-points each person's `user` row and issues a
  link to choose a password.
- Authlib was considered and not used: the provider is a narrow profile written on `joserfc`
  (see the tech-stack decision log). The only new dependency is `argon2-cffi`.
- Email recovery and verification wait for SMTP; recovery links are handed over by an operator.
- MFA and social login are not in v1.

## 9. Moving an existing installation from Authentik

Credentials are never moved between providers: an Authentik password is Authentik's. But switching an
installation that already has people in it needs more than a setting. Every `user` row is linked to
its sign-in by one subject (`user.authentik_sub`), and under `local` nobody holds the subject the old
rows point at. Left alone, **nobody can sign in — the platform administrator included** — and a fresh
sign-up with the same email is a different account that no one with authority can approve.

`adopt-users` closes that gap, using the operator's own database access as the authority. For each
person it creates a local account (active, email verified — the platform already vouched for it) with
a password nobody knows, points the existing `user` row at the new subject so every role, company and
record stays attached, ends every session the old subject might still hold
(`tokens_valid_after_at`), updates the recorded setup administrator, audits
`user.sign_in_provider_changed`, and prints a one-time link through which the person chooses a
password.

1. **Back up the Identity database.** Adoption replaces the old subject; nothing in the tooling
   puts it back.
2. `start\win\local-auth.bat` writes `IDENTITY_AUTH_PROVIDER`, `IDENTITY_LOCAL_AUTH` and the Auth
   app's `AUTH_*` settings. Identity refuses to start with a legacy `IDENTITY_OIDC` and neither
   provider chosen, so this (or `IDENTITY_AUTH_PROVIDER=authentik`) is required.
3. Apply the Identity migrations, which add the `local_*` tables (revisions 0090–0095):
   set `IDENTITY_DATABASE_URL` from `env\identity.env` and run `start\win\install-identity.ps1`.
4. Restart Identity and the Auth app.
5. `start\win\local-auth-cli.bat adopt-users` moves **the platform operators**: the administrator
   first-run setup recorded and anyone in `IDENTITY_PLATFORM_OPERATORS`. Anyone else must be named
   (`--email ada@example.com`, repeatable) or asked for outright (`--all`: every active user).
   Deactivated users are never brought back, and an email that a *different* local account already
   uses is skipped and reported, not linked.
6. Hand each printed link over privately (it works once and lasts `recovery_token_seconds`, 10
   minutes by default). If one expires, create another from the Console — the platform access page for
   a platform administrator, the user's page for anyone else — now that the account is local.
7. If `IDENTITY_PLATFORM_OPERATORS` named an operator, the command prints the replacement value
   (subjects are not secrets). Operators are recognised there by subject, so update it and restart
   Identity. The recorded setup administrator needs no setting: its subject is updated in the database.

Running it again is safe: accounts that already sign in locally are reported and skipped, and no new
link is issued for them.

## 10. Decision log

### 2026-10-31 ? Username or email for local sign-in

The user requested parity with username sign-in under Authentik. Local sign-in now accepts
either unique identifier and the same password. Registration still requires both username and
email; neither tenant identity nor the OIDC subject changes. No schema migration is needed.
See [verification record](local-auth-username-login.md).
