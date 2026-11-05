# Bill ? Windows launchers

Launch the eight APIs (Identity, Audit, Catalog, Notification, Accounting, Vouchers,
Reports, Design), nginx, Redis, the workspace-local RabbitMQ node and the Authentik SSH
tunnel to the already-running VM. UI uses the separate
`start-web.bat` launcher (the existing `start-web.cmd` alias still works).

From the repository root:

```bat
start\win\setup.bat
start\win\start-all.bat
start\win\status.bat
start\win\stop-all.bat
```

Start MySQL separately through its installed Windows service. Configure each service's
connection in the ignored `start/win/env/<service>.env` file before starting APIs.
The generated default is `root` with no password; it must be edited if your server
uses credentials. Create/migrate the service databases separately; startup does not
initialize or migrate databases, change installed services, or enable financial execution.
Do not put passwords in tracked `services.json` or chat.

Development environment generation also configures Identity's encrypted company-bank
storage through `IDENTITY_BANK_ACTIVE_KEY_ID` and `IDENTITY_BANK_ENCRYPTION_KEYS`.
Missing pairs are generated once; existing keys survive repeated setup and `-Recreate`.
Partial or invalid settings are rejected. Keep the ignored `identity.env` key ring
with your local database backup; production keys remain secret-manager settings.

The [local schema synchronization record](../../docs/local-schema-sync.md) lists verified
migration heads, model comparisons and the checks to repeat after schema changes.

## Commands

| Script | Behavior |
|---|---|
| `setup.bat` | Download and verify pinned nginx/Redis archives, sync Python dependencies, generate development environment files. |
| `start-all.bat` | With `AUTH_PROVIDER=authentik`, start or reuse the Authentik SSH tunnel (the VM must already be running); with `local` (the default) there is nothing to tunnel to and that step is skipped. Then Redis, local RabbitMQ, APIs and nginx; check readiness and return 1 if any component fails. |
| `start-services.bat` | Start all eight APIs and wait for HTTP readiness. Accepts `-TimeoutSeconds 45` (default). |
| `start-nginx.bat` / `stop-nginx.bat` | Validate/start nginx or gracefully quit the verified managed master. |
| `start-redis.bat` / `stop-redis.bat` | Start a localhost-only, cache-only Redis instance or send SHUTDOWN NOSAVE to its verified listener. |
| `status.bat` | Report health without launching/stopping processes; return 0 only if all checks pass. |
| `repair-audit.bat` | Synchronize local producer event registrations, restart only the managed Audit consumer, then check backend health. Run after audit contract changes cause `unconfigured` services; requires running backend infrastructure. Stops at a failed step and preserves its exit code. |
| `stop-all.bat` | Stop all supported owned delivery/review/reference workers, nginx, all eight APIs, Redis and the authenticated local RabbitMQ node; keep MySQL running. Continue after component failures and return 1 if any stop fails. |
| `start-web.bat [all\|auth\|console]` | Start both Next.js dev servers by default; reuse existing managed servers and wait for HTTP readiness. |
| `stop-web.bat [all\|auth\|console]` | Stop the selected managed UI servers; repeated stops succeed. |
| `status-web.bat [all\|auth\|console]` | Report UI process ownership and web-server readiness; return 0 only when selected servers are UP. |

Start/stop commands support `-WhatIf` through their PowerShell wrappers. `repair-audit.bat` runs its repair immediately and accepts no arguments.
`start-all.bat`, `start-web.bat` and its `start-web.cmd` alias, `stop-all.bat` and
`stop-web.bat` and `repair-audit.bat` wait for a keypress before closing after success or failure.
For unattended use, set `BILL_NO_PAUSE=1`; the original command exit code is preserved.
Repeated starts reuse managed processes and recheck health; repeated stops succeed when already
stopped. Ports occupied by processes outside the launcher are reported and left untouched.
Older foreground API/nginx/Redis launches must be closed manually once before switching
to this launcher. No image-name or window-title taskkill fallback is used. Successful
stops clear stale process records and stop markers; failed stops retain them for inspection.

Processes run hidden and detach from the initiating terminal. Closing that terminal
or pressing Ctrl+C there does not stop them; use the stop commands. API shutdown first
asks Uvicorn to drain active requests and run lifespan cleanup; a 15-second timeout
falls back to stopping only the verified managed process tree. nginx uses graceful
quit and Redis uses SHUTDOWN NOSAVE, with the same scoped fallback.

## UI start and stop

From the repository root, or double-click the BAT files:

```bat
start\win\start-web.bat
start\win\status-web.bat
start\win\stop-web.bat
```

Auth opens at `http://localhost:4310/login`; Console at `http://localhost:4320`.
Append `auth` or `console` to start, stop or inspect one app. PowerShell equivalents
accept `-App auth`; start also accepts `-TimeoutSeconds 60` (default, maximum 180).
Start and stop support `-WhatIf`. Commands work from any current directory.

Use Node.js 20 or newer on PATH and the pnpm version pinned by `mfes/package.json`.
If a selected app is missing Next.js dependencies, start runs
`pnpm install --frozen-lockfile` in `mfes` and propagates installation failures.
After changing dependencies, run that install command yourself. Next.js loads
each app's ignored `.env.local` file normally; launchers do not generate secrets.

UI runs hidden and detached. Use `stop-web.bat` to stop it; closing the launch
terminal leaves it running. Older foreground `pnpm dev` instances must be stopped
with Ctrl+C before switching. Backend `stop-all.bat` and UI `stop-web.bat` are separate.
Neither stops MySQL or the separately managed Authentik VM/tunnel.
Start checks port conflicts before launching either app; failed startup rolls back
only servers created by that invocation. A workspace UI lifecycle lock also serializes
dependency installation, starts, probes, rollback and stops.

UI startup/status verify the listener belongs to the managed process tree and
`/favicon.svg` returns the expected JANSO SVG. `UP` certifies the development HTTP
server; it does not certify sign-in, backend availability or every page. `DOWN`,
`STARTING`, `EXITED`, `EXTERNAL`, `DEGRADED` and `ERROR` describe the failing stage.
The Next worker inherits `web-stop.cjs`, which observes the managed stop marker
and invokes Next's registered shutdown handlers inside that process. This avoids
Windows' immediate external SIGTERM termination. Stop waits 15 seconds before
falling back to the verified process tree; no global Node kill is used.

Sign-in uses Identity itself by default (`AUTH_PROVIDER=local`; run `local-auth.bat` once to write the
settings — see [local authentication](../../docs/local-auth.md)) or, when `AUTH_PROVIDER=authentik`,
Authentik. Configure `mfes/apps/auth/.env.local` and
`mfes/apps/console/.env.local` as described in [the UI README](../../mfes/README.md#authentication-configuration).
Without those settings the login screen can render, but sign-in fails and the
Console root currently returns HTTP 500 (`Authentication is not configured`).

With `AUTH_PROVIDER=authentik`, `start-all.bat` starts the managed Windows SSH tunnel automatically when it is not
running, or reuses the existing managed tunnel. Start the Authentik VM first with
`authentik-vm\start.bat` in an administrator terminal. A tunnel failure is reported
as incomplete startup while the other backend components are still checked. The
tunnel forwards `localhost:9443` and `localhost:9000`; its startup confirms transport
availability, while Authentik application readiness remains separate. `stop-all.bat`
continues to leave the VM and tunnel running; use `authentik-vm\stop-tunnel.bat` for
the tunnel and the separate VM controls for the guest.

## Prerequisites and setup

- Windows PowerShell 5.1, Python 3.12 and `uv` on PATH.
- MySQL running with valid per-service connection settings and migrated schemas.
- Portable RabbitMQ/Erlang archives installed as described in
  [local-rabbitmq.md](../../docs/local-rabbitmq.md). Setup does not install these;
  start-all uses their existing launcher and checks the local node.
- Node/pnpm are needed only for UI. Azurite, Authentik and background workers are
  separately managed; these scripts start the HTTP APIs, not their worker fleet.

Individual setup steps:

```bat
start\win\setup.bat -Component nginx
start\win\setup.bat -Component redis
start\win\setup.bat -Component python
start\win\setup.bat -Component envs
```

Existing database/encryption values are preserved. Gateway verification keys are
aligned to Identity. `-Recreate` rebuilds selected binaries/environments or regenerates
environment secrets; stop corresponding components first. Setup validates recursive
filesystem targets and rejects junction/symlink traversal.

API startup reads UTF-8 environment files directly into child process environments.
Values are literal: no shell expansion of `%`, `!`, quotes, JSON or `&`, and no temporary
batch files containing secrets. Keys use `NAME=value`; duplicate or malformed keys fail.
New Identity environment files include the local Redis URL. Existing files can add
`IDENTITY_REDIS_URL=redis://127.0.0.1:6379/0` to enable its cache/step-up store.
`IDENTITY_COMPANY_DISPLAY_CACHE_TTL_SECONDS` defaults to 300; set it to 0 and
restart Identity to disable only the versioned display-config projection.
Local company-display integration tests use `TEST_IDENTITY_REDIS_URL`, configured
in the Windows user environment from the existing Identity Redis URL. See
[the cache operations and test instructions](../../docs/company-display-cache.md#local-integration-tests).

## Ports and health

| Component | Port | Probe |
|---|---|---|
| MySQL | 3306 | TCP reachability only; API readiness verifies database access. |
| Redis | 6379 | Redis PING/PONG. |
| RabbitMQ | 5672 | AMQP 0-9-1 negotiation; start/stop additionally authenticate the local node. |
| nginx | 8090 | `/nginx-health` returns `ok`. |
| Identity | 8001 | `/health/live` and `/health/ready`. |
| Audit | 8002 | `/health/live` and `/health/ready`. |
| Catalog | 8003 | `/health/live` and `/health/ready`. |
| Notification | 8010 | `/health/live` and `/health/ready`. |
| Accounting | 8011 | `/health/live` and `/health/ready`. |
| Vouchers | 8012 | `/health/live` and `/health/ready`. |
| Reports | 8013 | `/health/live` and `/health/ready`. |
| Auth UI | 4310 | Owned listener and expected `/favicon.svg` response. |
| Console UI | 4320 | Owned listener and expected `/favicon.svg` response. |

`DOWN` means no listener. `DEGRADED` means a port is occupied but its expected probe
fails. API readiness uses each service's existing contract; some check database access,
others also check required schema/migration versions. It does not certify all business
workflows, worker delivery or release activation.

If an API is live but shows `Database/schema not ready` after a code update, compare
its database's `alembic_version` with that service's migration head. Apply pending
revisions explicitly using a DDL connection after taking a backup, then rerun startup.
The [2026-10-24 recovery record](../../docs/local-schema-sync.md#startup-recovery-on-2026-10-24)
documents this condition for Catalog and Vouchers and the verified repair.

Ports, project paths and factories live in `conf/services.json`. Setup renders nginx's
listen/upstream ports from that registry; rerun nginx setup after changing them. Routing
and authorization policy remain in `conf/bill.conf`. The local gateway and APIs bind to
127.0.0.1. Example: `http://localhost:8090/identity/health/live`. Business and documentation
routes may require authentication according to service policy.

## Logs and tests

Ignored local artifacts:

- `bin/`: verified downloaded nginx/Redis binaries.
- `env/`: local development environment files and secrets.
- `runtime/`: process IDs, creation times, executable paths and shutdown markers.
- `logs/<service>.stdout.log` / `.stderr.log`: current run output.
- `logs/web-auth.stdout.log` / `.stderr.log`, `logs/web-console.stdout.log` / `.stderr.log`: UI run output.
- `.tools/rabbitmq-runtime/`: broker state, credentials and logs.

State ties managed processes to this workspace, executable and creation time; stale or
reused PIDs cannot authorize stopping another process. Runtime state contains no secrets.
Don't delete state while components are running.
Per-component file locks serialize simultaneous start/stop commands and release automatically
when the controlling process exits.

Run regression tests with Windows PowerShell and the built-in Pester module:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Pester -Script start/win/tests/launchers.Tests.ps1 -EnableExit"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Pester -Script start/win/tests/web.Tests.ps1 -EnableExit"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Pester -Script start/win/tests/stop.Tests.ps1 -EnableExit"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Pester -Script start/win/tests/start-all.Tests.ps1 -EnableExit"
node --test start/win/tests/web-stop.test.cjs
```

Opt-in live UI regression (requires dependencies installed and both UI ports free):

The live regression sets `BILL_NO_PAUSE=1` for its batch calls and restores the
previous value afterward, so automated checks do not wait for keyboard input.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File start/win/tests/web-lifecycle.ps1
```

## Launcher decisions

- 2026-10-31: `start-all` and the account-review worker read the sign-in provider from
  `env\identity.env` (`IDENTITY_AUTH_PROVIDER`, default `local`). The Authentik tunnel is started only
  for `authentik`; the review worker needs `IDENTITY_LOCAL_AUTH` for `local` and the Authentik review
  token for `authentik`. An unknown provider value stops the script rather than being guessed.

- 2026-10-27: Include the managed Authentik SSH tunnel in start-all before API startup.
  Reuse a running tunnel, propagate failures, continue independent backend startup,
  and preserve WhatIf. Verify both forwarding ports when starting or reusing a tunnel,
  bound SSH connection attempts and detect lost connections with keepalives.
  VM startup and VM/tunnel shutdown remain separately managed.
- 2026-10-27: Keep stop-all and stop-web batch windows open after success or failure,
  preserving exit codes and the unattended option. Backend stop includes all supported
  owned delivery workers, including optional workers launched through audit-workers.
  Continue stopping other components after worker errors; retain state on failed stops
  and clear stale state on successful repeated stops. Forced stops revalidate the root
  creation time and exclude orphan processes older than their apparent parent; delivery
  workers use the same verified tree stop. Keep UI and Authentik separate.
- 2026-10-27: Wait for a keypress after both success and failure in start-all and
  start-web batch launches. The CMD web alias delegates to the BAT launcher so it
  pauses once. Preserve startup exit codes and the `BILL_NO_PAUSE=1` unattended option.
- 2026-10-23: Pause failed start-all batch launches so double-click users can read
  errors; allow unattended callers to opt out with `BILL_NO_PAUSE=1`. Backend starts
  can replace stale process records after PID reuse, preserving unrelated processes
  and retaining port-conflict checks. Stops still reject mismatched process identities.
- 2026-10-19: Replace temporary environment-bearing BAT files and window-title stops
  with hidden managed hosts, per-run logs and verified process identity. Stop all seven
  registry APIs; graceful shutdown has a scoped timeout fallback. Preserve external
  listeners and MySQL. Report protocol/HTTP readiness and truthful exit codes. Keep UI,
  workers, migrations and release activation outside backend startup.
- 2026-10-19: Bind local nginx to localhost, render upstream/listen ports from the
  registry, check configuration before launch, encode generated MySQL credentials,
  and propagate Python setup failures instead of reporting successful setup.
- 2026-10-19: Manage Auth/Console dev servers separately from backend components,
  preserve the CMD alias, bind localhost, verify owned HTTP listeners, roll back
  failed launches and invoke Next worker shutdown handlers through a stop marker.
  Keep Authentik/API configuration explicit and separate from web-server readiness.

## Verification on 2026-10-19

Windows PowerShell 5.1 regression suite, PowerShell parser checks, Python compilation,
nginx configuration validation and whitespace checks passed. Live runs launched all
seven APIs, localhost Redis/nginx and the local RabbitMQ node. Redis PING, nginx health,
AMQP negotiation, repeated API start, complete stop and repeated stop were exercised.
API logs confirm Uvicorn lifespan shutdown completed, including Vouchers and Reports.
All test-launched components were stopped; the installed MySQL96 service remained running.

Full API database readiness remains unverified on this machine: generated root/no-password
connections receive MySQL error 1045. Start/status report DEGRADED and failure instead of
claiming success. No database migration, financial activation or worker execution was performed.

UI verification passed 20 PowerShell regressions, four Node shutdown-hook tests,
and the opt-in live lifecycle script. The 18 backend launcher regressions also
passed after fixing the process-exit inspection race. Existing Auth and Console
suites passed 52 and 393 tests respectively. Live checks covered both apps,
the CMD alias, invocation from another directory, repeated start without PID
changes, individual stop/restart, repeated stop, child startup failure rollback,
and preservation of an external listener. Logs confirm Next shutdown handlers ran.
The login page returned HTTP 200. Console's HTTP 500 from missing authentication
settings was observed and remains a configuration prerequisite, not a launcher
health claim. All test-started UI processes were stopped and ports 4310/4320 freed.

Manual simplification/security review covered literal environment handling, process ownership,
PID reuse, localhost binding, setup path boundaries, failure codes and preservation of unrelated
work, plus UI shutdown, rollback, dependency-install failure handling and the distinction
between HTTP-server health and authenticated application readiness. No further findings
remained within the reviewed launcher scope. The repository's
`/simplify` and `/security-review` slash commands are unavailable in this Codex environment;
the manual review above is the fallback, not a claim that those commands ran.

## Database and Authentik setup on 2026-10-20

The root/password connection was confirmed, seven application databases were migrated,
and per-service runtime accounts were configured. All seven API readiness probes passed;
the earlier root/no-password database prerequisite above is now resolved locally.
Redis and Auth/Console settings are configured. Authentik runs in the requested 4 GB
Ubuntu Hyper-V VM with verified HTTPS discovery. Full login still needs a linked
Identity user, tenant and local grants. Keys, credentials and VM shortcuts are in
ignored local files under `authentik-vm/`.

See [local login setup](../../docs/local-login-setup.md) for database versions, credentials
locations, the prepared Authentik Compose setup, HTTPS, OAuth and user provisioning.
`start-authentik.bat`, `status-authentik.bat` and `stop-authentik.bat` manage that separate
Compose project after Docker is installed; stopping preserves its database. Docker/WSL
were not installed; Docker runs inside Ubuntu. Use `authentik-vm/start.bat` and
`authentik-vm/tunnel.bat` for this setup. An external Authentik server is supported too.


## First-run platform wizard

The setup screen is <http://localhost:4310/setup>. Prepare it with
`platform-setup/prepare.bat` after Identity migrations/seeds, then restart Identity/Auth.
The private key is stored in `platform-setup/setup-key.txt`. The wizard creates the
first platform administrator from a freshly authenticated Authentik account with a
verified email and opens Console `/platform`. It checks connections and permanently
closes setup on completion. See [wizard guide](../../docs/platform-setup.md).

## Account registration

Login links to the branded `/signup` form. Run `registration/prepare.bat` to
configure local Authentik enrollment and enable manual-review mode, then restart
Auth. New accounts stay inactive and unverified until an Authentik administrator
approves them; billing invitations grant workspace access separately. SMTP is
deferred. See [account registration](../../docs/account-registration.md).


### Managed reference catalogs

Settings ? Countries / States / Languages / Currencies requires a platform
operator with platform.config.manage. Apply each service's current migration head;
the [local schema synchronization record](../../docs/local-schema-sync.md) lists the
verified revisions. Seed defaults before starting reference consumers. Application
startup never applies migrations.

Run `reference-sync-prepare.ps1` once after service env files exist. It adds scoped
owner/consumer secrets without replacing other settings; mismatched credentials
are refused. Restart Identity after preparing its credentials. Consumer env files
can set REFERENCE_SYNC_DATABASE_URL to a dedicated local worker account. Grant
only SELECT/INSERT/UPDATE on country, state, currency, language,
reference_revision and reference_sync_state; keep Accounting's financial grant
separate. Production uses trusted HTTPS and deployment-managed secrets.

`start-services.bat` now starts both managed reference workers after API readiness.
`stop-all.bat` stops them before APIs. Standalone controls are
`start-reference-sync.bat`, `stop-reference-sync.bat` and
`status-reference-sync.bat`. Worker logs use catalog-reference-sync and
accounting-reference-sync; credentials are never written to runtime state.
New custom references remain unavailable to new workspace/company selection
until both consumers acknowledge delivery. Restore a consumer by installing
canonical seeds and replaying the retained journal from its last local checkpoint
or from the beginning after a rebuild. Never advance a checkpoint by hand.

## Reference dropdown cache

Identity uses the Redis instance already started by these scripts for global
country/state/currency/language/timezone choices. No additional launcher is
required. `IDENTITY_REFERENCE_CACHE_TTL_SECONDS=300` in private `env/identity.env`
controls retention (0 disables this cache). Reference edits and synchronization
acknowledgements invalidate transactionally; never flush shared Redis to refresh
choices. Identity migration 0080 is required. See
[cache configuration and verification](../../docs/reference-cache.md).

## Platform account approvals and password change

Apply Identity migrations to the current head (this feature requires at least `0083`),
seed system roles, and run
`registration/prepare-account-review.bat` for the restricted provider service.
Run `registration/apply-password-change.bat` for the authenticated native flow.
Run `registration/prepare-review-audit.bat` to configure local signed audit delivery.
Restart Identity after configuration. `start-services.bat` starts the review worker
and, when configured, its audit publisher/consumer; `stop-all.bat` stops them.
Independent review controls are `start-account-review.bat`, `stop-account-review.bat`
and `status-account-review.bat`. Provider decisions require read-back confirmation.
See [account review](../../docs/platform-account-review.md) and
[password change](../../docs/change-password.md) for use, deployment and recovery.
