# Tenant administrator acceptance tests

This is a UI-led examination of the unchanged local installation. The test tenant
was created in the platform tenant wizard, activated by that existing workflow,
and its new administrator signed in through the real Authentik login. Three
companies were then created and bootstrapped using their six-step UI wizard.
Application code, environment configuration, migrations and existing tenants
are outside this test task. No application database row was edited directly.

Start with [the findings CSV](../../tenant-admin-findings-2026-10-29.csv).
The retained tenant is `QA Tenant 2026-10-29 mvtba4nh`
(`01a186e4-81a0-7221-8f57-2404a864ff43`). Its three active company profiles are:

| Profile | State | Amount / quantity decimals | Rounding | Inventory enabled | Barcode | Bill-wise | Payment days | Payment hold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Retail | IN-MH | 2 / 3 | half_up | Yes | OPTIONAL | Yes | 0 | No |
| Services | IN-KA | 4 / 2 | half_even | No | DISABLED | No | 30 | No |
| Distribution | IN-GJ | 0 / 4 | half_up | Yes | OPTIONAL | Yes | 60 | Yes |

Product-type requirements and company product defaults were published. Products
were saved as drafts; activation review explicitly requires the remaining
inventory/tax assignments. Those prerequisites are recorded, and product
activation is not claimed as completed.

The selected existing regression suites plus the new audit-cursor regression
finished with **6,251 passes, 8 failures and 3 skips**. Live/UI/link counts are in
`summary.json` and are separated by execution level.
The detailed deliverables are:

- [Reusable test cases](reusable-test-cases.csv): actual steps, preconditions,
  expected outcomes, latest status and explicit execution scope.
- [Live results](live-results-2026-10-29.csv): UI workflows, supporting API checks,
  route smoke and individual interaction smoke are distinguished.
- [Automated results](automated-results-2026-10-29.csv): one row per existing
  component/API regression test, including failures and skips.
- [Menu, link and control coverage](menu-link-control-coverage.csv): elements
  discovered from the actual rendered UI, with destination and functional status.
- [Retained test fixtures](test-fixtures.csv): active tenant and companies plus
  the records saved during these tests. Credentials are excluded.
- [Harness/prerequisite findings](harness-findings.csv): retained test selector,
  navigation, test-data and incomplete-prerequisite checks requiring correction
  or retesting; these are separated from application findings.
- [Machine-readable totals](summary.json).
- [Execution environment](execution-environment.csv): tested working-tree revision,
  service origins and storage/credential scope, without secrets.

## Reuse

Run from `C:\Pratham\Personal\softwares\bill`. Browser checks require the existing
Auth and Console at ports 4310 and 4320, Authentik, nginx and the relevant APIs and
workers. The runner uses the installed ignored Playwright tooling and Edge.
Use a new `QA_OUTPUT` directory to create an independent test tenant. Supply the
platform credentials through `QA_USERNAME` and `QA_PASSWORD`; do not commit them.

```powershell
$env:QA_OUTPUT = '.test_artifacts/tenant-admin-new-run/live'
node docs/testing/tenant-admin/run_live.cjs provision
node docs/testing/tenant-admin/run_live.cjs companies
node docs/testing/tenant-admin/run_live.cjs products
node docs/testing/tenant-admin/run_live.cjs suppliers
node docs/testing/tenant-admin/run_live.cjs policies
node docs/testing/tenant-admin/run_live.cjs workflows
node docs/testing/tenant-admin/run_live.cjs additional
node docs/testing/tenant-admin/run_live.cjs masters
node docs/testing/tenant-admin/run_live.cjs verify
node docs/testing/tenant-admin/run_live.cjs access-checks
node docs/testing/tenant-admin/run_live.cjs finish
node docs/testing/tenant-admin/run_live.cjs retain-fixtures
node docs/testing/tenant-admin/run_live.cjs last-mile
node docs/testing/tenant-admin/run_live.cjs reports
node docs/testing/tenant-admin/run_live.cjs crawl
```

The generated tenant administrator credential is retained as Windows DPAPI
ciphertext in the ignored output directory. Only the creating Windows user can
decrypt it. `resources.json` contains nonsecret IDs and fixture metadata. Keep
this private runtime directory for follow-up testing; do not put its credential
file or browser session material into docs or Git.

For focused runs, `QA_COMPANY_KEY` selects `retail`, `services` or `distribution`.
The `masters` phase also accepts `QA_RESOURCE` (`brands`, `manufacturers` or
`item-groups`). Clear these environment variables before a full run.
The default action timeout is 30 seconds. `QA_ACTION_TIMEOUT_MS=90000` was used
for the final focused rechecks because cold development compilation stalled
several requests. Application and existing regression-suite timeouts were not
changed. The earlier timeout evidence is retained.
`QA_CONFIG_ONLY=1` limits `workflows` to product configuration. These switches do
not authorize operating on an unrelated tenant. The setup runner refuses to
provision again into an output directory that already contains a tenant.

```powershell
python docs/testing/tenant-admin/run_suites.py --suite console
python docs/testing/tenant-admin/run_suites.py --suite identity
python docs/testing/tenant-admin/run_suites.py --suite all
python docs/testing/tenant-admin/collect_report.py
```

The existing service suites use isolated test fixtures; these results do not
prove live browser execution. MySQL-specific/native suites are not included in
the selected regression runner. Every successful live save uses the application
UI/API and its native local database connection. The report collector defaults to
`.test_artifacts/tenant-admin-20261029`. Pass `--artifacts` and, optionally,
`--report-dir` to collect another run without changing the script.

The original full Console run and one-worker retest are retained. The retest
contains only previously failing files and uses the same configured timeouts.
The first Catalog/Accounting runs reached the harness's one-hour limit without
final JUnit reports. Their dots are not counted as passes. Subsequent full runs
use a three-hour harness limit and per-test logs. A redundant second Console run
was stopped and excluded from canonical results. Application timeouts were
unchanged.

## Interpreting results

`PASS` means the assertion stated in that row passed. `LIVE_UI_ROUTE_SMOKE`
establishes rendering, errors and route accessibility, and does not establish
CRUD completion. `LIVE_UI_INTERACTION_SMOKE` establishes the specific small
interaction described in the row. Isolated automated results establish only
the behavior of the named tests and their fixtures.

`NOT_RUN_INDIVIDUALLY` and `NOT_INDIVIDUALLY_EXERCISED` are explicit gaps. They
must not be counted as complete end-to-end feature coverage. Discovered controls
generate reusable cases for later functional testing. Disabled/preview features,
money admission, outbound delivery, missing prerequisites and failed checks
remain visible; configuration gates are not changed to make tests pass.
Generated control cases use stable IDs and `:record_id` placeholders so a new
run can reuse the case with its own fixture records.
Report parameter controls are inventoried after selecting each report in the
loaded workspace. Their `?report=CODE` routes are reusable entry templates;
`SETTINGS_RENDERED_BY_UI_SELECTION` describes the actual rendering check.
Rendering these settings does not exercise parameter validation or exports.

The crawl resumes from saved surface inventories. Set
`QA_COLLAPSE_RECORD_LINKS=1` to render each page shape and check the remaining
record URLs/query variants through authenticated HTTP. Such links are explicitly
marked `LIVE_AUTHENTICATED_LINK_HTTP`; they are not individual UI executions.
Omit this switch to render every discovered URL. Both modes preserve the
distinction from completed workflows and from unexercised controls.

Browser harness selector, hydration and navigation corrections are retained in
the ignored initial-run evidence. Initial runs that selected a different company
than intended are invalid as company-specific evidence; the final checks verify
the actual selected company. Fixing the harness changes no application code.
During the prolonged run, the existing Authentik SSH tunnel stopped listening.
Its original managed startup helper restored the forwarding process; the VM,
keys, provider configuration and databases were preserved. Sign-in-page captures
were excluded from application coverage and retained in a separate ignored
authentication-redirect inventory for rechecking.

No code fixes, commit or publication are part of this deliverable. New QA data is
retained so the findings can be reproduced and subsequent fixes retested.

## Subsequent fixes: steps 1-3

The original acceptance CSVs above remain historical evidence. The separately
authorized fixes are recorded in [the execution note](../../tenant-admin-foundation-fixes-2026-10-29.md)
and [batch results](../../tenant-admin-fixes-1-3-results-2026-10-29.csv).
`node docs/testing/tenant-admin/verify-foundation.cjs` reuses the retained encrypted
credentials and provider UI sign-in, then checks both audit surfaces in all three
companies, cross-company cursor refusal, company-context cookie preservation,
recovery pages and four concurrent ordinary refresh requests. Its browser is
closed on completion. Its output is the ignored
`.test_artifacts/tenant-admin-20261029/live/foundation-fixes-results.json`.
This checks the named scenarios; it does not establish full feature coverage or
an expired-token exchange against the live provider.

## Subsequent fixes: steps 4-6

See [the business batch note](../../tenant-admin-business-fixes-2026-10-29.md),
[results CSV](../../tenant-admin-fixes-4-6-results-2026-10-29.csv) and
[current TODO](../../tenant-admin-fixes-todo.md). The new scripts configure and verify
the retained companies through real UI login and ordinary owner APIs:

```powershell
node docs/testing/tenant-admin/configure-business.cjs
node docs/testing/tenant-admin/configure-sales.cjs
node docs/testing/tenant-admin/verify-business.cjs
node docs/testing/tenant-admin/verify-designer.cjs
node docs/testing/tenant-admin/verify-business-readback.cjs
```

The native API helper keeps provider tokens in memory, checks the current encrypted
session cookie and uses the existing Auth refresh boundary. Non-Identity native calls
are limited to the retained QA companies; retries preserve the same write key.
Owner reconciliation requires these QA companies to have no posted transactions.
After separate release activation, use fresh fixtures or an explicit before/after
baseline for posting scenarios. Draft/submission passes do not verify live posting,
taxed goods/services, statutory issuance or a stock release.

## Subsequent implementation: steps 7 onward

Current evidence: [results CSV](../../tenant-admin-fixes-after-6-results-2026-10-30.csv)
and [TODO](../../tenant-admin-fixes-todo.md). The collector keeps historical ledgers
unchanged and distinguishes UI checks, native test schemas, fixture suites and
unavailable prerequisites:

```powershell
apis/accounting/.venv/Scripts/python.exe docs/testing/tenant-admin/collect_pending_results.py
node docs/testing/tenant-admin/verify-pending-links.cjs
node docs/testing/tenant-admin/verify-natural-refresh.cjs
node docs/testing/tenant-admin/verify-permanent-role-authority.cjs
node docs/testing/tenant-admin/verify-permanent-role-authority.cjs --opening
node docs/testing/tenant-admin/verify-opening-authority.cjs
node docs/testing/tenant-admin/verify-report-readiness.cjs
node docs/testing/tenant-admin/verify-report-navigation.cjs
node docs/testing/tenant-admin/verify-money-entry.cjs
node docs/testing/tenant-admin/verify-live-overview.cjs
node docs/testing/tenant-admin/verify-purchase-entry.cjs
node docs/testing/tenant-admin/verify-report-controls.cjs
node docs/testing/tenant-admin/verify-report-typed-submit.cjs
```

The fixed system-role update was applied by the configured platform operator.
Canonical Tenant Administrator reporting grants persist and seed future tenants.
The user-approved 2026-10-30 opening policy adds seven existing native grants to
the same canonical role. The `--opening` runner reviews/applies that catalogue
through the protected platform operator session and checks all three retained
company scopes. It issues no write when the catalogue is already current.
The opening runner retains a separate auxiliary services company in
`resources.openingCompany`, created through the wizard for fresh bootstrap and
zero-opening checks. It is not a fourth report-source scope. Balanced test values
are entered only for preview and discarded; the explicit zero confirmation has
no journal effect. Reuse preserves finalized history rather than resetting data.
Initial failed harness assumptions and interrupted navigation remain in the
ignored logs and `pending-8-opening-access-initial-results.json`.
Reporting uses immutable READY snapshots, real workers and private export files;
the QA date range begins at retained books-begin coverage. Older quarantined
generations and blocked attempts remain in history. The invitation transport and
provider fixture checks do not establish actual external mailbox receipt.

The overview runner compares displayed company totals and covered dates with the
native immutable-source read and follows an actual customer lookup to its record.
The three retained source cuts currently cover October 1 onward; earlier history
is explicitly unavailable. Their empty posted activity does not prove populated
live invoice or collection effects. Nonzero overview reconciliation is separately
verified against disposable native test schemas.

The reusable [master layout check](verify-master-filter-layout.cjs) discovers
available master cards through the signed-in UI. It measures query/filter top
edges, height, hint placement and viewport overflow. `QA_LAYOUT_WIDTHS` accepts
`1440,768,390`; `QA_LAYOUT_ROUTES` selects explicit directory routes;
`QA_LAYOUT_PHASE` saves a distinct ledger. `QA_FAILED_ONLY=1` rechecks failures
from `QA_RECHECK_PHASE` (default `master-filter-layout`). The separate
[master alignment CSV](../../master-filter-alignment-results-2026-10-30.csv)
merges the current checks; old failed attempts remain in their original ledgers.
Geometry checks do not claim individual execution of every filter option.

Purchase uses the explicit synthetic NON_GST account profile and native active
supplier/payable/expense facts. Its input line retains `42.1234`; expected payable
totals are `42.1200` (retail), `42.1234` (services), and `42.0000` (distribution),
according to the retained rounding configurations. New dated defaults and account
activation can take time to reach the native voucher master projection; preserve
failed attempts and rerun with a distinct `QA_PURCHASE_PHASE` after propagation.
An original Retail draft with the old QA total/expense was corrected via the native
revision API. This is fixture maintenance and does not establish a Purchase edit UI.
`QA_COMPANY_KEY` selects one profile. Submission/self-approval-refusal evidence
does not establish posting, GST issuance or C2 release.

The report-control runner selects all 38 discovered definitions in each company,
inspects labelled native controls and validates typed parameters using the owner
API. Missing bank account/statement/session fixtures are BLOCKED cases. These are
control and parameter checks, not populated report calculation acceptance.
The typed-submit runner checks actual UI array/boolean requests separately from
stock job acceptance. A READY financial generation does not imply complete
inventory coverage; the current three sources refuse stock report jobs with 409.
Those source cases remain BLOCKED. Original accepted-job assumptions are retained
in `pending-17-typed-submit-results.json`; the distinct recheck separates the
verified payload from the unavailable inventory prerequisite.
`QA_REPORT_PHASE` preserves a distinct recheck ledger. The collector gives every
suite artifact its own identity; results.xml files from different native suites
cannot overwrite one another. Current CSV row counts are evidence entries and may
include repeated assertions from distinct suite contexts.

Existing owner integration suites can be rerun on the dedicated native test server:

```powershell
$env:QA_MYSQL_SERVER_URL='mysql+asyncmy://root@127.0.0.1:13396'
apis/accounting/.venv/Scripts/python.exe docs/testing/tenant-admin/run_native_opening_races.py --suite invoice-owner
apis/accounting/.venv/Scripts/python.exe docs/testing/tenant-admin/run_native_opening_races.py --suite money-owner
apis/accounting/.venv/Scripts/python.exe docs/testing/tenant-admin/run_native_opening_races.py --suite stock-owner
```

The helper creates and drops only its validated disposable schema. Model-schema
tests do not replace migration, financial release, statutory, count or live
populated-workflow acceptance. Never substitute an application database URL.

### UI review of fixes #1–18

The [30 October UI review](../../tenant-admin-ui-review-2026-10-30.md) links its
findings and execution CSVs. `review-ui.cjs` reuses protected credentials and retained
company fixtures, captures desktop/tablet/phone states, and blocks voucher business
writes. It makes only read requests, local unsaved UI edits and company-context
selection; simulated preview/failure responses are labelled separately.

Run `QA_UI_REVIEW_PART=screens`, then `remaining`, `final-checks` and
`payment-recheck` sequentially. `QA_REVIEW_DATE` selects the document date; the
default is the current UTC date. Run `python -B docs/testing/tenant-admin/collect_ui_review.py`
from the repository root to collect this dated report's ignored artifacts.
Captures and successful browser actions are evidence, not assertions that a screen
has no bug. Inspect the separate findings CSV and screenshots before accepting a fix.

### UI fixes and reusable acceptance

The [fix review](../../tenant-admin-ui-fixes-review-2026-10-30.md) and
[20-row fix CSV](../../tenant-admin-ui-fixes-results-2026-10-30.csv) record local
implementation separately from live acceptance. The user shut down the VM; the
post-fix live checks are NOT_RUN. Historical results retain their original verdicts.

From the repository root, with existing Node dependencies and Edge installed:

```powershell
powershell -NoProfile -File docs/testing/tenant-admin/test-ui-fixes.ps1
node docs/testing/tenant-admin/verify-ui-fixes.cjs --offline
python -B docs/testing/tenant-admin/collect_ui_fixes.py
```

The local runner executes affected Console/shared-control regressions, sequential
designer/history browser geometry and both TypeScript checks. `-Phase <label>`
selects a separate ignored local evidence ledger. It requires no VM or sign-in.
The dated collector validates the final local evidence and explicitly unrun live
ledger before writing the current dated CSV; it does not collect future live passes.

After VM services return, reuse the protected QA credentials and three-company
fixtures with:

```powershell
node docs/testing/tenant-admin/verify-ui-fixes.cjs
```

This runner checks native scoped forms/directories/summary/report continuity and
desktop/tablet/phone controls, with unsaved local edits and company-context changes.
It intercepts all voucher/report business writes and asserts none were attempted.
It sends no invitations and performs no posting or source refresh. Real preview/
failure scenarios, versioned save/replay and missing native profiles remain explicitly
separate from its read-only acceptance. Results are saved to a new live ledger;
failed sign-in/services are failures, never passes. Online assertions have not been
executed after the VM shutdown; only syntax and offline mode were checked.

`verify-live-overview.cjs` now expects the selected customer's PARTY_LEDGER workspace
instead of the former party configuration destination. Its old evidence remains
historical. Earlier API-only Purchase fixture maintenance did not prove an edit UI;
the current fix tests now cover the supported versioned money/untaxed Purchase editor.

## Company Default product masters

The [dated review](../../company-product-defaults-review-2026-10-30.md) and
[CSV](../../company-product-defaults-results-2026-10-30.csv) distinguish local
regressions from the live catch-up that is pending while Identity is offline.

From `apis/catalog`, run reusable storage/source regressions:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_company_product_defaults.py tests/test_source_worker.py tests/test_source_enrollment.py tests/test_unit_defaults.py tests/test_tax_defaults.py tests/test_warehouse_defaults.py -q
.venv/Scripts/ruff.exe check src/catalog/tasks/company_product_defaults.py src/catalog/tasks/source_worker.py tests/test_company_product_defaults.py tests/test_company_product_defaults_mysql.py
.venv/Scripts/mypy.exe --strict src/catalog/tasks/company_product_defaults.py src/catalog/tasks/source_worker.py
```

Native concurrency/reuse tests run separately with `QA_MYSQL_SERVER_URL` pointing
to the dedicated local MySQL test server at port 13396, without a database name.
The fixture refuses other hosts/ports or a selected database and creates/drops
only generated disposable schemas. Do not point it at application databases.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_company_product_defaults_mysql.py -q
```

From `mfes/apps/console`, run wizard/native-contract/readiness regressions:

```powershell
pnpm.cmd exec vitest run tests/company-bootstrap.test.ts tests/company-policy.test.ts tests/company-product-defaults.test.ts tests/company-wizard.test.tsx
pnpm.cmd exec tsc --noEmit
```

Once normal services return, restart/redeploy the Catalog Identity source worker
with the updated code. Its verified refresh provisions the missing Default pair.
For product-only catch-up, from the workspace root:

```powershell
apis/catalog/.venv/Scripts/python.exe -m catalog.tasks.source_worker --env-file start/win/env/catalog.env --once --product-defaults-only
```

This uses signed enrollment/snapshot verification and native audited writes; it
does not manually manipulate application tables or grant permissions. Preserve
renamed/custom/General masters. Confirm each QA company's pair in the native UI,
then create an active fresh company and inspect its pair. Keep the resulting live
ledger separate from component/storage results; failed/offline services are not passes.

## Product group and type create panels

The [review](../../product-reference-create-review-2026-10-30.md) and
[CSV](../../product-reference-create-results-2026-10-30.csv) record the inline
right-side forms, product-draft preservation and remaining live acceptance.

From `mfes/apps/console`, run reusable workflow/parent-form regressions:

```powershell
pnpm.cmd exec vitest run tests/product-reference-create.test.tsx tests/product-reference-product-form.test.tsx tests/catalog-master-ui.test.tsx tests/product-classification-ui.test.tsx tests/product-creation-wizard.test.tsx tests/simple-product-create.test.tsx tests/simple-product-ui.test.tsx tests/simple-product-accessibility.test.tsx tests/product-creation-summary.test.tsx tests/product-creation-tracking.test.tsx tests/catalog-master-policy.test.ts tests/product-classification-policy.test.ts
pnpm.cmd exec tsc --noEmit
```

For actual browser geometry, use the existing protected/local QA Playwright runner
at `.tools/ui-review-runner` and installed Edge. These fixture tests are opt-in so
normal component collection does not require the local browser runner:

```powershell
$env:QA_PRODUCT_REFERENCE_BROWSER = '1'
pnpm.cmd exec vitest run tests/product-reference-layout.browser.test.tsx
Remove-Item Env:QA_PRODUCT_REFERENCE_BROWSER
```

The two cases verify 18 group/type × width × theme combinations. Screenshots and
JSON ledgers stay in ignored `.test_artifacts`. They prove layout, not live writes.
When Identity/Catalog return, verify the new controls with the existing QA tenant:
save a compatible group, create a type and draft requirements, explicitly publish
with authorised access, and confirm the selection and original product draft in
both simple and family/SKU modes. Exercise cancellation and retained write retries.
Record live outcomes separately; no manual database changes are needed.
## Product tax/price note removal

Reusable UI checks (from `mfes/apps/console`):

```powershell
pnpm.cmd exec vitest run tests/product-commercial-note-removal.test.tsx tests/product-creation-wizard.test.tsx tests/simple-product-ui.test.tsx tests/simple-product-create.test.tsx tests/simple-product-setup.test.tsx tests/tax-release.test.tsx --no-file-parallelism --maxWorkers=1 --minWorkers=1
```

Backend checks (from `apis/catalog`):

```powershell
.venv/Scripts/python.exe -m pytest tests/test_product_commercial_note_removal.py tests/test_product_initial_setup.py tests/test_simple_products.py tests/test_simple_product_features.py
.venv/Scripts/python.exe -m pytest tests/test_master_usage.py tests/test_field_registry.py tests/test_tax_administration.py tests/test_tax_governance.py tests/test_tax_item_kind.py tests/test_tax_review.py tests/test_pricing_storage.py
```

Native DDL checks additionally run
`tests/test_product_commercial_note_migrations_mysql.py` with
`QA_MYSQL_SERVER_URL` pointing at the dedicated local 13396 test server without
a database. The tests create and delete their own randomized schemas; they
reject application database targets. See the
[removal plan](../../product-commercial-note-removal-plan.md).
