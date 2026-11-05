# Platform setup verification — 2026-10-20

## Implemented

Identity setup status/checks/administrator/complete APIs, one installation-control
migration and installation seed, persisted first operator, seven-step Auth wizard,
shared Stepper/styles and Console platform tenant directory. OpenAPI and TypeScript
Identity contracts regenerated. Local setup-key preparation reads the API registry
and keeps generated secrets in ignored files.

## Verification evidence

- Identity migration/schema/install/setup/platform checks: **555 passed**, four native
  tests excluded from this run. Login/revocation setup subset: **25 passed**, one
  container-dependent test skipped. Native MySQL 9.6 concurrency check separately
  passed: simultaneous completions returned one tenant/user/assignment and four
  transactional audit events.
- Full UI suite: **1,722 passed**. Full Auth suite: **109 passed**, one Redis-dependent
  server test skipped; subsequent added callback, request-limit and post-commit-outage
  regressions passed. Full Console suite: **417 passed**; four new platform-page
  tests and the 13 shell tests subsequently passed.
- Auth and Console production builds passed. TypeScript checks, scoped Ruff/mypy,
  Identity OpenAPI/client drift and task-file whitespace checks passed.
- Actual Edge browser, trusted HTTPS Authentik and isolated MySQL: setup key unlock,
  all configured connections, platform/workspace form, fresh provider sign-in with
  verified email, encrypted draft restoration, optional email skip, confirmation,
  atomic provisioning and live session permission verification passed.
- A separate actual sign-in reached Console `/platform`, listed the provisioned
  operating tenant and confirmed `/setup` remained closed after reload. No browser
  page errors occurred. Screenshots are local artifacts under `.tools/local-login/`.
- The real Identity database was upgraded to **0066**, remains unclaimed with **zero
  users and tenants**, and all seven normal APIs and both web launchers are running.
  Temporary verification services, Authentik callback and test user were removed.
- Windows UI lifecycle regressions: **22 passed**. The working OAuth grant types
  and verified-email mapping were also persisted into the VM's local blueprint;
  Authentik's blueprint loader validated its syntax.

## Final review

The environment has no callable `/simplify` or `/security-review` commands. Equivalent
manual reviews followed CLAUDE.md sections 5/6: authorization, tenant isolation,
constant-time setup key, secret handling, OIDC verification/freshness, origin checks,
rate limits, concurrency, rollback/replay and transactional audit evidence.

Resolved findings: readiness Redis uses RESP2 on this Windows server; API ports derive
from the existing registry; Authentik requires explicit authorization-code/refresh
grants and a verified-email mapping; login retries retain the setup callback; a
post-commit session outage reports saved setup instead of claiming provisioning failed.

## Completion review and follow-up verification

The final review also corrected invalid Console configuration failing after a commit,
invalid application-origin ports, inactive country/currency selection, unbounded POST
buffering, Unicode drafts exceeding cookie limits, confirmation surviving edited
settings, public status forwarding unexpected fields and missing directory pagination.
Readiness checks now run service probes concurrently and validate the readiness
payload. Setup preparation uses private atomic file writes, restores environments
on failure and recovers an existing key without rotating it. Dedicated preparation
and connection-check regressions cover these behaviors.

New `apply-authentik.bat` and `check.bat` commands provide repeatable local provider
configuration and connection verification. The OAuth blueprint attaches the verified
email mapping and preserves the standard Bill scopes, including `billing.api`.
The running provider was inspected to verify its grants and scopes. The cloud-init
source and new `seed-setup-updated.iso` include these changes; creation prefers this
ISO while preserving the corrected VM boot settings and console credentials.

- Identity review suite: **569 passed**, four native tests deselected. Scoped
  Ruff/mypy and OpenAPI/client drift checks passed.
- Native MySQL: installer rerun, revision `0066` downgrade/re-upgrade with reseeding,
  and simultaneous setup completion passed on disposable databases.
- Auth: full run **118 passed**, one infrastructure-dependent test skipped; final
  focused wizard **11 passed** and setup server **12 passed** after the last changes.
- Console platform/shell checks: **18 passed**; final platform-page tests **5 passed**.
- Windows launcher/preparation suite: **45 passed**. Live `check.bat` reported all
  eleven required database/cache/provider/API checks ready.
  Cleanup exposed a process exiting between lookup and termination. The launcher
  now tolerates that race while preserving errors when the process remains alive;
  two additional launcher regressions cover both branches.
  Both new regressions passed in the **21-test backend launcher suite**.
- Final Auth and Console production builds passed. Actual Edge repeated the complete
  wizard using trusted Authentik sign-in and isolated MySQL, returned verified
  platform access, and reported no browser errors. Closed status exposes no draft.
  A separate login reached the Console tenant directory and confirmed setup stayed
  closed after reload. Temporary accounts/callbacks were removed afterward.
- All isolated services and temporary credential files were removed. Both normal
  web apps and all seven APIs are running. Nginx on `8090` passed configuration and
  health checks and forwards `/identity/v1/setup/status`. The real Identity database
  remains revision `0066`, with zero users/tenants and setup available for the intended
  administrator. Re-running installation on the completed disposable database
  preserved its tenant/user and completion metadata.

No unresolved setup security/correctness findings remain in the reviewed scope.
Later live-use recovery found an OAuth callback failing with an expired JWT because
the Ubuntu guest clock was over two hours behind the laptop. Chrony's Hyper-V clock
source was correct, but its startup-only stepping policy left a large correction
slewing slowly. The guest was stepped to that source and its `makestep` policy set
to `1 -1` for later clock jumps. `sync-time.bat` exposes the recovery command.
Setup callback retries now request fresh authentication with the same five-minute
freshness requirement as the wizard. Token time validation was not relaxed.
After real setup completion, sign-out correctly revoked the old login. Authentik
2026.8 treats `max_age=0` as unset and can reuse its remembered reauthentication
state for `prompt=login`, issuing tokens with the old `auth_time`. Sign-in after
logout/revocation and company verification now use `prompt=login&max_age=1` so the
provider must check a positive age bound. Identity still rejects evidence predating
revocation; no account cutoff was reset.
The recovery passed 32 login/company-verification UI tests and TypeScript checks.
An actual Edge browser signed in, retried with the new age bound and confirmed that
the provider displayed credentials and issued a newer `auth_time`. The browser
used the IdP administrator solely to inspect provider behavior; that account is not
activated as a billing user. The intended personal user must sign in to confirm
their own Console access. The real installation has now completed successfully,
superseding the earlier unclaimed-state observations above.
Email transport editing/test-send and plan/configuration management screens remain
explicitly outside this delivery. Production deployments must provide HTTPS, ingress
rate limiting and prevent users from editing the IdP verified-email attribute. Their
release verification is separate from this laptop's local verification.
