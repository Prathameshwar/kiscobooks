# First-run wizard

Run `prepare.bat` once to generate the local setup key and configure the existing
Identity/Auth environment files. It preserves an existing key and other settings.
Environment writes use private temporary files and restore the original contents
if a write fails. A missing key file is recovered from matching environment keys.
Keep `setup-key.txt` private; it is ignored by Git and restricted to your Windows account.

Before preparing, apply Identity migrations and installation seeds with a deployment
database account (`python -m identity.install` in the Identity environment). Runtime
database accounts intentionally have no DDL permission. The wizard never migrates a database.

For this computer's Ubuntu VM, `apply-authentik.bat` applies the local Bill OAuth
grant types and email mapping through the existing SSH key. The provider must
already exist. It preserves its client secret and callbacks. The file targets the
standard local Bill scopes; customize it before use with a provider that has extra scopes.
The IdP administrator must separately verify the intended administrator's email
and set the user attribute `billing_email_verified` to boolean `true`.

Restart Identity and Auth after preparing. Start all APIs, Redis, Authentik and its
local tunnel, then open <http://localhost:4310/setup>. Use the key in `setup-key.txt`.
Run `check.bat` for a read-only connection verification. It unlocks a temporary setup
session, checks the required service contracts, and exits nonzero when attention is needed.
Use your intended administrator's Authentik account with a verified email; the wizard
never creates a password or silently promotes Authentik's `akadmin`.

SMTP configuration is optional and remains server-administered through Notification.
Connection checks include all seven APIs, Identity defaults, Redis and Authentik.
On completion the operating tenant, administrator, platform role, installation record
and audit outbox events commit together. Setup is permanently closed; there is no public reset.
After checking access, the wizard links to <http://localhost:4320/platform>.

Use the existing `../start-web.bat` and `../stop-web.bat` to manage the UI.
Use `../start-all.bat` and `../stop-all.bat` for the backend; MySQL remains separately
managed. VM start/stop and the SSH tunnel remain separate under `../authentik-vm/`.

## With the local provider (the default)

`AUTH_PROVIDER=local` needs no Authentik VM, tunnel or `apply-authentik.bat`. Run
`..\local-auth.bat` once: it writes `IDENTITY_AUTH_PROVIDER` / `IDENTITY_LOCAL_AUTH` to
`env\identity.env` and the matching `AUTH_*` settings to `mfes\apps\auth\.env.local`, keeps any
existing secret, and prints variable names only. Restart Identity and Auth, then open
<http://localhost:4310/setup>: the wizard first asks for the setup key, then creates the first
administrator's account (name, email, password) before the usual completion step. Recovery is by a
one-time link an administrator creates; there is no email yet. To stay on Authentik, set
`IDENTITY_AUTH_PROVIDER=authentik` and `AUTH_PROVIDER=authentik` and keep every `AUTHENTIK_*`
variable. An installation that already has people on Authentik moves them with `..\local-auth-cli.bat adopt-users`
(see [local-auth](../../../docs/local-auth.md) §9). See [local-auth](../../../docs/local-auth.md).
