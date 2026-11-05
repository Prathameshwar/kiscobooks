# Platform administrator acceptance testing

The sections below preserve the original pre-fix baseline. The subsequent
[fix verification record](fix-verification.md) and findings CSV retest columns
describe the authorized fixes and their new evidence.
The updated CSV contains **13 findings: seven fixed and verified, six open or
partly verified**. The selected fix regression suites passed **975 tests**, with
two MySQL skips covered by six separate native executions. Final live runs passed
18 grouped checks. See the fix record for duplicate executions and retained
intermediate failures; the original results below remain the pre-fix baseline.

Tested locally on 2026-10-29. Application code, configuration, migrations, existing
tenant records and the supplied operator password were left unchanged. No commit
or publication was performed. New test code and this report are the deliverables.

Start with [the findings CSV](../../platform-admin-findings-2026-10-29.csv). It
contains severity, reproduction steps, expected/actual behavior, evidence, source
locations, regression tests and retest acceptance for each bug, gap or limit.
[The reusable checklist](regression-checklist.csv) describes 40 workflows/checks.
[The individual automated results](automated-results-2026-10-29.csv) preserve
the actual result and execution level of every selected test.
[The live results](live-results-2026-10-29.csv) separate explicit checks, route
observations and the corrected search-selector harness failure.

The final automated ledger contains **947 executions: 937 passed, 7 failed,
3 skipped**. These are selected platform-related suites, not the entire repository
or a coverage-percentage measurement. The original two MySQL skips were rerun
successfully on native MySQL 9.6.0 in separate schemas; the Redis skip was rerun
successfully against native Redis. Those three extra passes are included in 947;
the original skips are preserved for transparency. Retries, initial harness
failures and the initial shared-schema native failure are not double-counted.

| Suite | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Identity selected existing suites | 218 | 0 | 2 |
| Console selected component/proxy suites | 374 | 0 | 0 |
| Auth component suites | 159 | 0 | 0 |
| Auth server suites | 101 | 2 | 1 |
| Audit selected suites | 58 | 0 | 0 |
| Notification selected suites | 22 | 0 | 0 |
| New joined acceptance/regression tests | 2 | 5 | 0 |
| Separate native MySQL checks | 2 | 0 | 0 |
| Separate native Redis check | 1 | 0 | 0 |

Five failing new tests reproduce three application findings: unsupported subject
mapping in recovery, exclusion of the provisioning account path from recovery,
and three control-character validation cases. Two existing Auth tests fail because
their assertions reject trace headers. Failures are retained, without xfail or
relaxed expectations. The initial joined workflow assertion was corrected to
respect intentional one-time password disclosure on provisioning replay; that
harness mistake is not an application finding.

Live browser evidence uses real Authentik login and the configured operator, real
Console/Identity, the working database and Audit delivery. It is separate from
the 947 automated executions. Live writes created only a new QA tenant,
administrator, backup invitation and inactive pricing offering. Tenant edits,
last-admin protection, invitation lifecycle, tenant lifecycle/replay/staleness,
pricing revisions and native audit delivery passed. Recovery failed with HTTP
409, matching the new regression. Twenty-one QA tenant platform events were
observed through Audit. Earlier browser transition/selector failures were
harness errors; the initial discovery timeout is separately recorded as an
intermittent environment observation.

Some initial page captures show pending skeletons. They are marked OBSERVED,
not PASS. Use settled-page checks and the final read-only run for data-rendering
evidence. The first layout run used unsupported theme query parameters, so its
three-theme labels are not theme verification; the final read-only theme check
sets the real theme preference and asserts the applied HTML attribute.
The final read-only checks passed four anonymous proxy refusals, ten native read
contracts, four settled data pages, all 12 notification destinations, 12 mobile
page/theme combinations and the password handoff page. Tenant search passed in
a separate fresh-login rerun after correcting `textbox` to the actual `searchbox`
role. Those final runs recorded no JavaScript page errors. Mobile assertions
establish applied theme and document-width behavior, not exhaustive accessibility
or every interaction at every viewport. The shell's internal scrollport can make
full-page screenshots crop scrollable content; screenshot extent is not proof
that all content was inspected.

Raw logs, JUnit reports, screenshots, native run outputs and browser JSON are in
the ignored local folder `.test_artifacts/platform-admin-20261029/`. They can
contain existing account metadata, so only the sanitized result CSVs are in docs.
No password, access token, invitation secret or recovery link is intentionally
written into the documentation. Local browser contexts accept the installation's
self-signed HTTPS certificate; this does not certify production TLS trust.

The following remain separate live acceptance work: a new public registration
through approve/reject/reopen and first sign-in, invitation acceptance, actual
password changes and native session effects, recipient mailbox/provider delivery,
shared reference mutations/propagation and deployment migration round trips.
Fixtures, handoff pages and readiness must not be presented as those outcomes.

## Repeat isolated suites

Run these commands from the existing local project root. They use existing
virtual environments, pnpm and installed workspace dependencies. No application
service or real provider is required for ordinary fixture suites. The suite
runner continues after a failure, writes logs/JUnit/per-test CSVs and exits
nonzero when a suite fails.

```powershell
$qaRun = '.test_artifacts/platform-admin-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& apis/identity/.venv/Scripts/python.exe docs/testing/platform-admin/run_suites.py --output $qaRun
```

Use `--suite identity`, `console`, `auth`, `auth-server`, `audit` or
`notification` for a focused rerun. The Identity selector automatically includes
the added `test_platform_admin_acceptance.py`. Its joined tenant/admin and
pricing workflows are API acceptance tests with fake provider adapters.

For the joined acceptance/regression module alone:

```powershell
Push-Location apis/identity
& .venv/Scripts/python.exe -m pytest tests/test_platform_admin_acceptance.py -q
Pop-Location
```

## Repeat native checks

`run_native.py` accepts only the dedicated loopback test server on port 13396,
with no database in the supplied URL. It creates a unique schema per module,
creates model tables, runs the module, then drops only that generated schema.
It also runs both modules sharing a fresh schema in each order to guard against
the outbox isolation regression.
Never supply the application's database URL. These checks prove native locking
and rollback, not Alembic migration round trips.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File start/win/identity-test-mysql.ps1 -Action status
# If the dedicated test server is stopped:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File start/win/identity-test-mysql.ps1 -Action start
$env:QA_MYSQL_SERVER_URL = 'mysql+asyncmy://root@127.0.0.1:13396'
$env:QA_NATIVE_OUTPUT = "$qaRun/native-isolated"
& apis/identity/.venv/Scripts/python.exe docs/testing/platform-admin/run_native.py
```

For the native Redis concurrency case, use the dedicated logical DB 15. The
existing test uses random keys with expiry and does not flush Redis. Its provider
refresh response is mocked, while Redis coordination is native.

```powershell
$env:TEST_AUTH_REDIS_URL = 'redis://127.0.0.1:6379/15'
Push-Location mfes/apps/auth
pnpm.cmd exec vitest run --config vitest.server.config.ts tests/server/auth-handler.test.ts --testNamePattern='rotates one grant'
Pop-Location
Remove-Item Env:TEST_AUTH_REDIS_URL
```

## Repeat live browser checks

Use the workspace's managed services and web apps. The browser harness uses the
existing `.tools/ui-review-runner/node_modules/playwright` and installed Edge.
Those ignored local tools are prerequisites, not a dependency installed by this
change. URLs and browser executable can be overridden with `QA_AUTH_URL`,
`QA_CONSOLE_URL` and `QA_BROWSER`; this harness is verified for the configured
local Authentik installation. It never synthesizes a signed application session.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File start/win/start-all.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File start/win/start-web.ps1
$env:QA_USERNAME = 'pratham'
$env:QA_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host 'Platform password' -AsSecureString)).Password
$env:QA_OUTPUT = "$qaRun/live-verified"
$env:QA_LIVE_READS = '1'
Remove-Item Env:QA_MUTATE -ErrorAction SilentlyContinue
Remove-Item Env:QA_WORKFLOWS_ONLY -ErrorAction SilentlyContinue
try { node docs/testing/platform-admin/live_browser.cjs }
finally { Remove-Item Env:QA_PASSWORD }
```

The default visits 17 administrator pages. `QA_LIVE_READS=1` adds anonymous
proxy refusal, ten native read contracts, settled data pages, tenant prefix
search, 12 notification destinations, 12 mobile page/theme combinations with
the applied theme asserted, and the password-change handoff page. It does not
change a password. Page observations remain observations; explicit checks have
PASS/FAIL results. The script exits nonzero for a failed or blocked check.

For live writes to **new disposable QA records**, run the same harness with
`QA_MUTATE=1`, `QA_WORKFLOWS_ONLY=1` and a new output folder. Remove
`QA_LIVE_READS` if only the write workflow is wanted. It uses random `.invalid`
addresses and a generated in-memory password, attempts native recovery issuance
without consuming any link, and writes only resource IDs to `qa-resources.json`.
Each run creates a new QA tenant/provider account and price. It leaves the QA
tenant suspended, backup assignment revoked and offering deleted, preserving
audit evidence. Verify those final states in the resource manifest if a run fails
early. No hard-delete cleanup of application records is attempted.

After fixes, `QA_RECOVERY_COMPLETE=1` additionally verifies initial sign-in and
completes the native reset for that run's newly created disposable administrator.
It checks mismatch/current-password refusal, new/old credentials and used-link
rejection. Credentials and recovery URLs remain in memory. It never changes the
supplied platform operator's password. This requires the recovery blueprint,
restricted credential and native event worker to be ready. Without that flag,
the workflow still verifies issuance only. The login harness now also asserts
that the company-less platform operator reaches `/platform`.

The 2026-10-29 live fixture is tenant
`01a18638-ce24-7162-a457-f7f6796ece0e` (QA Platform mvt4nxvu), administrator
`01a18638-ce24-7163-9bf4-96d00069402a`, and deleted inactive price
`01a18639-c24c-7531-98bf-761d84ccf40b`. The provider account remains present;
its random initial password was not retained. Existing tenants were untouched.

## Preserve and compare results

Keep each rerun in its own output folder. Compare finding IDs and test names,
not just total counts. A passing subset does not close a finding whose native
workflow still fails. `collect_results.py` builds the saved final automated CSV
from `identity.xml`, `console.xml`, `auth.xml`, `auth-server.xml`, `audit.xml`,
`notification.xml`, `acceptance-final.xml`, `native-isolated/*.xml`, and optional
`auth-redis.xml`. It excludes deselected Redis cases and preserves original skips.

```powershell
& apis/identity/.venv/Scripts/python.exe docs/testing/platform-admin/collect_results.py .test_artifacts/platform-admin-20261029 docs/testing/platform-admin/automated-results-2026-10-29.csv
```

After fixes, rerun the failing acceptance cases first, then the affected suites
and native workflow. Update each finding's status and dated evidence only when
its stated acceptance checks pass. Retain this run as the pre-fix baseline.
