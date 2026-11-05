# Local database, migration and model synchronization

## Vouchers payable total, 2026-11-04

The eight configured localhost databases now match **544 model tables**, migration
heads, readiness inventories and Windows service mappings. Identity is `0100`, Audit
`0003`, Catalog `0221`, Notification `0116`, Accounting `0235`, Vouchers `0116`,
Reports `0043` and Design `0009`. The final read-only verifier found no missing or
extra tables, native differences or Alembic changes in any service. Credential-free
reports are in ignored `.tools/schema-sync-20261104-final/`.

Vouchers was the only initial mismatch: the model and migration had `payable_total`,
but the database was at `0115` and its readiness inventory still declared `0115`.
The `0116` migration's check name initially differed from the SQLAlchemy naming
convention. A restored-schema rehearsal caught this; the unapplied migration was
corrected and a regression test now checks both upgrade and downgrade names.

A private full Vouchers backup was made at
`.test_artifacts/vouchers-0116-81a828a130f8181b/vouchers-before.sql` before the
live upgrade. The corrected `0115 -> 0116` revision passed a disposable-schema
restore, Alembic and native comparisons, then was applied with the owned Vouchers
API and its three running workers stopped. All 19 existing invoice detail rows were
retained and the new nullable column is null on those rows. The API and previously
running workers were restarted; the API readiness probe returned HTTP 200. Rehearsal
and live summaries are beside the private backup. The temporary schema was removed.

Validation: 11 schema/readiness tests and 41 focused Vouchers tests passed; scoped
Ruff and strict mypy passed. The Vouchers API remained ready (HTTP 200), and all
three restarted workers were running. Existing Alembic warnings about a generated
counter default remain covered by the separate native comparison. No commit or
publication was performed;
unrelated working-tree edits were preserved.

## Immediate party/account opening posting, 2026-11-04

Accounting advanced from 0233 to 0234. The migration replaces the master opening
status check in one ALTER statement, adding POSTING, POSTED and REVERSED while
preserving PENDING and WITHDRAWN. The existing opening record has identical hashes
for all original values before and after the upgrade. Runtime grants are unchanged.

All 147 Accounting tables, native constraints, migration/readiness heads and Alembic
comparison agree with zero differences. Reports are retained in the ignored
`.tools/master-opening-final-sync/` directory. Accounting and its previously running
publisher and posting-delivery workers were restarted; live/readiness probes return
200 and the served creation contract includes the new posting statuses and profiles.
Administrator credentials were supplied through masked input and used only in
memory. See [the implementation and verification record](master-opening-immediate-posting.md).

## Simple Product import continuations, 2026-11-04

Catalog advanced from 0218 to 0219; Accounting advanced from 0232 to 0233.
Each revision replaces the shared import-state check in one ALTER statement,
allowing `VALIDATING` and `IMPORTING` continuations. Both existing import-job
counts were zero and remained zero. Table counts are unchanged. Downgrade refuses
outstanding continuations. DDL snapshots are retained in the ignored
`.tools/simple-import-*-before.sql` files. See [the import delivery record](simple-product-import-plan.md).

## Simple Product and Model controls, 2026-11-04

Catalog advanced from 0216 to 0218; Accounting advanced from 0231 to 0232.
Private backups were taken first. Logical hashes verify that every original
Product Configuration option and company stock opening row retained its values.
The new columns preserve old configuration with INHERIT and old opening controls
as company baselines. Per-product openings and creation receipts have native
uniqueness constraints; populated receipt/history rollback is refused.

Read-only verification confirms Catalog's 183 tables and Accounting's 147 tables,
matching models, native constraints, migration/readiness heads and Alembic checks
with zero differences. Reports and backup hashes are in the ignored
`.tools/product-config-starter-review/simple-*` artifacts. Existing business
configuration was not republished. Local stock posting admission and native owner
connections were configured for the authorized Simple Product opening flow;
service startup is separate. See [the delivery record](simple-product-ready-plan.md).

## Product Configuration pricing controls, 2026-11-04

Catalog advanced from 0215 to 0216 for six typed pricing-option columns on
`product_pricing_policy`. Existing rows default to INHERIT; the two retained rows
have identical hashes for every pre-existing field before and after the upgrade.
The native migration/rehearsal and model synchronization checks passed: all 182
Catalog tables, native constraints, readiness head and Alembic comparison agree.
Other service schemas were not changed by this enhancement.

The isolated MySQL 9.6 rehearsal verified downgrade/re-upgrade while all settings
inherit, rejection of rollback after a setting is authored, concurrent starter
publication and API publication of a later configuration. Evidence is retained in
`.tools/product-config-starter-review/`; the temporary server was shut down.
See [the implementation record](product-configuration-starter-plan.md).

## Current verification, 2026-11-04

This platform-wide check preceded the Catalog 0216 enhancement recorded above.

All eight configured databases now match 542 model tables, migration trees,
readiness inventories and Windows service mappings. Verified heads: Identity `0100`,
Audit `0003`, Catalog `0215`, Notification `0116`, Accounting `0231`, Vouchers `0115`,
Reports `0043` and Design `0009`. Native constraints/options and Alembic comparisons
pass. Credential-free reports are retained in `.tools/schema-sync-20261104/`.

The initial check found Design at `0008`, missing `invoice_template.voucher_kind
VARCHAR(50) NULL` and `line_profile VARCHAR(16) NULL`. Applied the existing reviewed
revision `0009`, which adds both columns in one ALTER statement and preserves
templates with no declared document context. Models, API contracts and migration
history already agreed and required no edits.

Administrator credentials were entered through a masked local dialog and passed
directly to the repair process in memory; they were not saved or printed. The helper
created private backups, restored one to a generated temporary schema, rehearsed
upgrade/downgrade/upgrade and verified native/Alembic parity before the live forward
upgrade. All **7 existing rows** across Design's seven tables were retained,
including the template and its assignment; runtime grants are unchanged. The
temporary schema was removed. Backup and retention evidence are under ignored
`.test_artifacts/design-startup-20261104-upgrade/design/` with private Windows ACLs.
No business records were edited. Existing Alembic warnings about cyclic foreign
keys and generated defaults were covered by the separate native schema comparison.

Independent post-upgrade verification reports Design database, migration and
readiness head `0009`, no native differences and Alembic check exit 0. All eight
API readiness endpoints return HTTP 200 with status `ready`; Design recovered
without a process restart.

Validation: 8 schema-verifier tests, 24 Design service/context tests and 49 Windows
launcher/worker tests passed. All 78 startup PowerShell scripts parsed successfully;
the local credential helper also passed syntax checking. Manual migration,
credential-handling and data-retention review found no remaining mismatch. Existing
unrelated edits were preserved. No commit or publication was performed.

## Synchronization and shutdown repair, 2026-11-03 (evening)

The current working tree added company-setup tables and goods-purchase migrations.
Identity's database was already at `0100`, but its readiness inventory still
declared `0097` and omitted `company_setup_run`, `company_setup_step` and
`report_source_enrollment`. Updated that inventory and the Accounting/Vouchers
readiness heads to match their reviewed migration chains.

Applied Accounting `0230 -> 0231` and Vouchers `0111 -> 0115`. Each database was
backed up privately, restored into a generated disposable schema, and tested with
upgrade/downgrade/upgrade, Alembic comparison and extended native schema comparison
before the live forward upgrade. Fresh live backups are retained under ignored
`.test_artifacts/schema-sync-20261103-upgrade/`. All original table counts matched:
**13,659 Accounting rows** and **241,080 Vouchers rows**. Runtime grants were
unchanged, and both disposable schemas were removed. Credentials were entered
through hidden prompts and used only in process memory/environment.

The reported shutdown error was `Process identity changed for vouchers`, rather
than a failure of the Identity API. Its PID and creation timestamp matched the
workspace record, but Windows did not expose the executable path. The launcher
now permits only the workspace-local graceful stop marker in that case. Forced
termination and Redis/nginx endpoint shutdown still require full process identity;
reused PIDs and foreign workspace records remain rejected. The real Vouchers stop
succeeded, followed by a complete `stop-all.ps1` run with exit 0, including the same
condition on Accounting. Backend processes were left stopped; MySQL remains running.

Final `dbs/verify_sync.py` verification passed for all eight services and **542
model tables**: zero missing/extra tables, zero native differences, eight successful
Alembic checks, and matching database, migration, readiness and launcher mappings.
Credential-free reports are in `.tools/schema-sync-20261103-final/`.

| Service | Database / migration head | Model tables |
|---|---|---:|
| Identity | 0100 | 67 |
| Audit | 0003 | 3 |
| Catalog | 0215 | 182 |
| Notification | 0116 | 30 |
| Accounting | 0231 | 147 |
| Vouchers | 0115 | 74 |
| Reports | 0043 | 32 |
| Design | 0008 | 7 |

Validation: 11 schema/readiness regression tests, 814 Identity migration tests,
one Accounting constraint test, seven Vouchers schema tests and 49 launcher/stop/
report-worker tests passed. Four Identity container tests were deselected and one
Accounting native-options test skipped without its disposable native fixture;
native parity was checked separately during both database rehearsals/upgrades.
All 76 Windows PowerShell scripts parsed. Scoped Ruff and strict typing checks
passed. Broader application behavior and coverage suites were not rerun.

Manual simplification, security and correctness review checked credential handling,
data retention, service-local migration ownership, PID reuse protection and the
graceful-only fallback. No additional finding remains. The named `/simplify` and
`/security-review` commands were unavailable; equivalent manual reviews were used.
No commit or publication was performed, and unrelated working-tree edits remain.

## Current verification, 2026-11-03

Repeated `dbs/verify_sync.py --output-dir .tools/schema-sync-20261103` against
all eight configured localhost MySQL schemas and the current working-tree models.
All **538 model tables** match: no missing/extra tables, no native differences and
eight successful Alembic checks. Database heads, migration heads, readiness
revisions where present and Windows launcher mappings agree. The revisions and
table counts remain those in the 2026-11-02 table below. Credential-free JSON
reports are retained under the ignored `.tools/schema-sync-20261103/` directory.

The launcher regression sweep reproduced one stale TLS test: it expected the
Authentik CA while reading the private installation's default local provider.
The test now selects Authentik explicitly. Additional checks cover local sign-in
without Authentik trust and an absent Authentik CA; explicit operator trust also
avoids reading private provider settings. Runtime scripts and authentication
behavior are unchanged.

Verification: **8 schema-verifier tests** and **86 launcher/provider tests** pass;
all **76 Windows PowerShell files** parse without errors. Manual simplification,
security and correctness review found no additional issue. `/simplify` and
`/security-review` commands were unavailable; those named commands were not run.
No application code changed, so broader application/coverage and Python
lint/type-check suites were not rerun.

The separate runtime health check returned exit 1: MySQL, Accounting and Vouchers
were UP; Redis, RabbitMQ, nginx and the other six APIs had no listeners, and audit
delivery was DEGRADED. Schema alignment does not certify running services or
worker delivery. No migrations, data updates, grants, admission changes, service
starts/stops, commits or publication were performed. Original local paths and
unrelated work were preserved. Earlier verification history follows.

## Current verification, 2026-11-02

All eight configured localhost schemas match their models, migration scripts,
readiness revisions where present and Windows launcher mappings: **538 model
tables**, no missing/extra tables or native differences, and eight successful
Alembic checks.

| Service | Database / migration head | Model tables |
|---|---|---:|
| Identity | 0097 | 64 |
| Audit | 0003 | 3 |
| Catalog | 0215 | 182 |
| Notification | 0116 | 30 |
| Accounting | 0230 | 147 |
| Vouchers | 0111 | 74 |
| Reports | 0042 | 31 |
| Design | 0008 | 7 |

The earlier full sweep found Reports at revision 0041 without `report_hierarchy_node`.
Its version-6 Trial Balance model and reviewed one-statement migration 0042 already
agreed. Backed up Reports privately, restored the backup into a generated disposable
schema, rehearsed 0041 -> 0042, and verified native/Alembic parity and row retention.
Removed that disposable schema after the successful rehearsal.

The subsequent master-creation opening delivery applied Accounting 0230 for
`master_opening_balance`. A private Accounting backup was restored to a disposable
schema; upgrade/downgrade/upgrade, native model/index/FK parity, 38 native API/domain
tests and refusal to downgrade populated evidence passed. The owned Accounting API
and its running posting-delivery worker were restored after the forward upgrade.
Every original table retained its row count and runtime grants stayed unchanged.
The new table started empty. The service-specific verifier reports head/readiness
0230, 147 models, no missing/extra tables, no native differences and Alembic check 0.
Accounting live/ready health endpoints return 200. Evidence is privately stored in
`.test_artifacts/master-opening-schema-sync-20261102-e8c96ecd2d754f4ab64d92fca01a0668/`.

Stopped the owned Reports API and its five workers, took another private backup,
and applied the existing forward migration. All **4,477 rows in the 30 original
application tables** retained their counts; the new locator table started empty.
Runtime grants were checked before and after and remained unchanged. The worker
stops used the launcher's bounded, ownership-checked process-tree fallback after
15 seconds. All previously running Reports processes were restored; the Accounting
snapshot publisher and other services were preserved.

Reports `/health/live` and `/health/ready` return HTTP 200. All five Reports workers
are running. The native MySQL regression run passed **20 checks**, full migration
downgrade/upgrade and model/index/FK parity; its separate loopback server was then
stopped. The schema-verifier regression suite passed **8 tests**. The one-off Python
and PowerShell maintenance scripts passed parsing checks.

Migration credentials were passed in process memory and were not written to script
files, service environments or backups. No runtime grant, admission flag, financial
posting, model definition or applied migration history was changed. Manual schema,
scope, retention, credential-handling and process-ownership review found no remaining
drift. The broader Reports test/coverage release checks remain separately recorded in
[Trial Balance delivery](trial-balance-delivery.md).

Credential-free final comparisons are in `.tools/trial-balance-review/schema-final/`.
Private SQL backups, process state and table retention evidence are in
`.test_artifacts/trial-balance-schema-sync-20261102-42ba92a521194cae95f984f9a629fbb6/`.
Original project paths and unrelated work were preserved. No commit or publication
was performed. The following sections retain earlier verification history.

## Current verification, 2026-10-31

All eight localhost MySQL schemas match their models, migration heads and native
constraints: 527 tables, no missing/extra tables or native differences, and all
Alembic checks pass. Identity is 0095, Catalog 0214, Accounting 0225, Vouchers 0109;
Audit 0003, Notification 0116, Reports 0038 and Design 0008 are unchanged.

The affected schemas were backed up, restored into disposable schemas, upgraded
and compared before live forward upgrades. Every original table's row count was
retained while owned writers were stopped. Backups, rehearsal logs and retention
evidence are private under `.test_artifacts/unit-stock-schema-upgrade-20261031-r2/`
and the Catalog rehearsal/live directories. No business history was rewritten.

Identity's local-auth model check names now explicitly preserve their applied DDL
names. Its readiness check requires owned tables and head 0095 instead of SELECT 1.
This closes the false-ready state that allowed local `/oidc/authorize` to fail with
a missing `local_authorization` table. Identity/Catalog/Accounting/Vouchers readiness
and local public JWKS are HTTP 200; the browser reaches the local password form.
The recorded platform operator was adopted through the native local-auth workflow
with its existing user, tenant and grants preserved; its password setup link was
checked without redeeming it. Credentials and recovery tokens are outside reports.

Verification: 791 Identity/schema/adoption regressions and four readiness/runtime
tests pass; Ruff and strict mypy pass for the affected Identity files. See the
[High-finding implementation record](unit-stock-fixes-2026-10-31.md) for stock/unit
regressions and scoped remaining release evidence. The following entries retain
the earlier synchronization history.

Verified on 2026-10-29 against all eight configured localhost MySQL databases and
the current working-tree models, migration chains and Windows launcher registry.
Earlier repairs and startup recovery are retained below as historical evidence.

## Verified revisions

| Service | Local database and migration head | Model tables |
|---|---|---:|
| Identity | 0089 | 56 |
| Audit | 0003 | 3 |
| Catalog | 0210 | 182 |
| Notification | 0116 | 30 |
| Accounting | 0222 | 141 |
| Vouchers | 0105 | 71 |
| Reports | 0038 | 28 |
| Design | 0008 | 7 |

Each database revision matches its independent migration chain. The readiness revision
constants in Catalog, Accounting, Vouchers, Reports and Design match those heads. The launcher
registry identifies the same service projects, databases and migration configurations.

## Revalidation after opening and product tracking changes, 2026-10-29

Ran `python dbs/verify_sync.py --output-dir .tools/database-sync-review` against
all eight configured databases. All **518 model tables** are aligned, and every
service report returned `aligned: true` with Alembic comparison exit code zero.
Database heads, migration heads and available readiness constants agree. Extended
native inspection found no missing/extra tables or primary/foreign/check constraint,
generated-column, collation or table-option differences. The Windows launcher
registry still maps each service to its own models, database and migration chain.

Accounting is already at 0222 with the four financial-opening evidence tables and
nullable historical document/due dates. The recent tracking navigation work reuses
existing batch/serial schemas and needs no migration. No drift correction, schema
upgrade, stamp, model change, permission grant or data update was necessary.

The schema-verifier regression suite passed **8 tests**. This was a read-only
schema check; no application records, reference seeds, posting admission or service
processes were changed. Individual credential-free JSON reports are retained under
the ignored `.tools/database-sync-review/` directory. Historical runs below retain
their original revision and table counts.

## Product and stock workflow synchronization on 2026-10-28

Verified all **514 model tables** across the eight configured databases using
`dbs/verify_sync.py`. Every migration head, readiness constant where present,
launcher mapping, Alembic comparison and extended native schema comparison passed.
There are no missing/extra tables or native constraint, generated-column, column
collation or table-option differences.

Accounting was at 0212 and Vouchers at 0101. Backed up both databases, restored
each backup into a disposable schema and rehearsed the existing forward migrations
to 0216/0105. After stopping the affected owned APIs/workers, took new backups and
applied the same revisions locally. All 134 original Accounting tables (14,361 rows)
and 69 original Vouchers tables (59,528 rows) retained their row counts. No schema
reset, stamp, historical migration edit, runtime grant or admission change occurred.
Affected APIs/reference/delivery workers were restored; all 12 runtime probes are UP.

All 63 Windows PowerShell files parsed, all 49 affected launcher tests passed, and
all eight schema-verifier regression tests passed. Updated one stale shutdown-test
count to include the three added source/execution workers while preserving PID
reuse protection. No application model repair or new migration was required.

Details: [2026-10-28 synchronization record](schema-sync-20261028.md). Ignored
backups and retention evidence are in `.test_artifacts/schema-sync-upgrade-20261028/`;
the final eight read-only reports are in `.test_artifacts/schema-sync-20261028-final/`.
Credentials were supplied in memory and were not saved in scripts/environment files.
Earlier sections below retain their historical revision counts.

## Masters and Reports synchronization on 2026-10-27

Repeated `dbs/verify_sync.py` against all eight live databases after the landing-page
review. All 461 registered model tables match their schemas, each database is at
its single migration head, and readiness constants and Windows registry mappings
agree. Every Alembic check passed; there are no missing/extra tables or native
constraint, generated-column, collation or table-option differences. Identity is
now verified at `0087`; the earlier `0085` record is historical.

The two landing pages reuse existing models and API contracts. No new database
objects, migrations, startup migration behavior or permission grants were needed.
All 38 report card codes exactly match the native report registry. The system-role
seed dry run found all 12 roles and 551 grants unchanged and rolled back its
transaction. No user assignments or application data were changed.

Identity, Catalog, Accounting and Reports OpenAPI exports passed `--check`; the
generated TypeScript clients passed the full `check:generated` command. Eighteen
schema-verifier/role regression tests and 35 backend/reference-worker launcher
tests passed. All 58 Windows PowerShell files parsed successfully. The launcher
tests initially could not load under the shell's default execution policy; rerunning
with a process-only policy override passed without changing machine policy.

Read-only schema summaries are retained under ignored
`.tools/schema-sync-20261027-hubs/`. Manual security and correctness review found no
additional issue. No live financial jobs, migrations or service restarts were run.

## Repairs verified on 2026-10-23

- Restricted Audit migration metadata to its three owned tables. Importing the shared
  SQLAlchemy registry previously proposed unrelated platform tables for Audit.
- Upgraded Notification from 0026 to 0116 through its existing migrations, after a local
  backup and graceful API stop. All original table row counts were preserved.
- Restored migration-defined server defaults in Catalog, Vouchers and Reports metadata.
  Quoted SQL expressions represent date and empty-string defaults accurately to Alembic.
- Marked existing explicit check-constraint names as already converted by SQLAlchemy's
  naming convention. Models now retain the names used by the original native migrations.
- Matched Notification's callback and trace identifier types to their existing ASCII
  binary `CHAR` definitions, and request priority to unsigned `TINYINT`. SQLite variants
  retain the existing test representation. Public request and response shapes are unchanged.
- Added Accounting migration 0156 to align `inventory_report_record` with its model's
  `utf8mb4_unicode_ci` collation and explicit DYNAMIC row format. Revision 0155 is unchanged.
  The local database was backed up before applying 0156; evidence row count was preserved.
- Updated Catalog's migration regression parser to cover inline literal DDL in revisions
  0179–0180 as well as module-level DDL literals, including unindented/quoted columns.

## Verification on 2026-10-23

All seven service environments passed `python -m alembic -c alembic.ini check`, run from
their respective `dbs/<service>` directories with their existing local database URL loaded.
This compares tables, columns, nullability, native types, defaults, indexes, unique keys
and foreign keys against the metadata selected by the actual migration environment.

Additional live inspection compared primary keys, check names and expressions, generated
column definitions/storage, explicit column collations, and table engine/collation/row
format. MySQL's equivalent hex notation, identifier quoting, `!=`/`<>`, singleton `IN`,
and `IN` member ordering were reviewed/normalized. No differences remain. This extra
inspection matters because Alembic does not compare check constraints or table collations
and emits warnings for some equivalent MySQL-rendered generated expressions.

An isolated `accounting_test_<uuid>` database reproduced the collation regression at
0155, then passed after 0156. Upgrade, downgrade and re-upgrade retained an inserted
evidence row. Native schema/inventory tests and Alembic comparison passed. The disposable
database was removed afterward.

Affected regression/storage suites passed:

| Suite | Result |
|---|---|
| Audit model/migration checks | 28 passed; 2 container tests deselected |
| Catalog model/default/constraint/migration checks | 15 passed; 1 container test deselected |
| Catalog affected storage/domain checks | 25 passed |
| Notification schema/types/callback/admission checks | 24 passed |
| Accounting affected constraint/exchange-rate/source checks | 7 passed |
| Accounting native schema/inventory checks | 7 passed |
| Vouchers affected default/constraint/number-series/replica checks | 22 passed |
| Reports default/source-version checks | 12 passed |
| Backend and UI Windows launcher checks | 46 passed |

The empty-string default follow-up also passed all seven Vouchers default/constraint
checks. Ruff and strict mypy checks passed for the affected Python files. These are
targeted checks; the full application suites and a new overall coverage run were not run.

Manual simplification and security/correctness review found no additional issue in these
changes. Tenant/company predicates, constraint expressions, money types, idempotency,
posting admission and audit emission are unchanged. `/simplify` and `/security-review`
commands were unavailable in this session, so those named commands were not run.

Raw local comparison logs, extended inspection snapshots and database backups are under
the ignored `.tools/schema-sync-audit/` directory. Administrator credentials were passed
only in process memory and were not added to scripts, environment files or backups.

## Operating rule and decision log

- 2026-10-23: Keep each service's schema ownership and migration history independent.
  Correct model metadata to describe existing SQL contracts; use a new forward migration
  for a real table-option change. Preserve existing migrations and retained data.
- Apply migrations explicitly with a database administrator/DDL connection before starting
  updated APIs. Runtime application accounts retain their restricted grants.
- Repeat all eight Alembic checks and the additional native schema inspection after model
  or migration changes. Launcher health probes certify their existing readiness contracts;
  they are not a substitute for this schema comparison.

## Startup recovery on 2026-10-24

Catalog and Vouchers were live but returned HTTP 503 from `/health/ready`. Their
databases remained at the baseline revisions while updated APIs required the newer
import storage. The Windows launcher correctly reported `DEGRADED` and a failed startup.

| Service | Before | Repaired revision | Model tables |
|---|---|---|---:|
| Catalog | 0180 | 0191 | 164 |
| Vouchers | 0085 | 0097 | 65 |

Applied the existing forward revisions explicitly with the local administrator connection.
Full SQL backups were restored into disposable databases first; both upgrade rehearsals
passed Alembic model comparison and retained every original table's row count. After
gracefully stopping the affected managed APIs and ensuring the Catalog reference worker
was stopped, fresh backups were taken before either live upgrade. Both live comparisons
passed and all original table row counts were unchanged. Only the generated disposable
databases were removed.

Catalog's affected migration/schema/import checks passed: 21 tests, with one container
test deselected. Vouchers' affected schema/import checks passed: 19 tests, with one
container test deselected. The actual local MySQL rehearsals covered both migration paths.
All eleven backend component probes subsequently reported `UP`, including HTTP 200
readiness for Catalog and Vouchers. Startup continues to require explicit migrations;
the application accounts' restricted grants and financial activation settings were preserved.

Backups, rehearsal/live comparison logs and retained row-count evidence are in the ignored
`.tools/startup-schema-repair/` directory. The administrator password was supplied through
a hidden prompt and was not saved in scripts or environment files.

## Full synchronization verification on 2026-10-24

All seven Alembic checks passed against the current databases. Every database revision
matches its migration head; readiness revision constants match where present. Model
table inventories contain no missing or extra database tables. The registry's service
projects, database names, environment prefixes and migration locations agree.

Additional read-only inspection found zero differences in primary keys, check names and
expressions, generated expressions/storage, explicit column collations, and table engine,
collation and row format. This includes the new Catalog/Vouchers import tables and the
current Identity/Accounting revisions. No database or application-model repair was needed.

| Targeted suite | Passed | Native/container tests deselected |
|---|---:|---:|
| Identity migration chain/target | 685 | 4 |
| Audit models/migrations | 28 | 2 |
| Catalog migrations/defaults/constraints | 15 | 1 |
| Notification models/migrations/types | 6 | 0 |
| Accounting constraints | 1 | 0 |
| Vouchers defaults/constraints | 7 | 0 |
| Reports defaults | 1 | 0 |
| Windows backend/UI launchers | 46 | 0 |

Total: 743 backend checks and 46 launcher tests passed. The seven live Alembic and
extended native comparisons above were performed separately from these unit suites.
All 49 Windows PowerShell scripts parsed successfully. A fresh backend startup reported
all eleven component probes `UP`, including readiness for each current service revision.
The full application suites and a new coverage run were not run. Manual simplification
and security/correctness review found no additional issue; `/simplify` and
`/security-review` commands remain unavailable in this environment.

Read-only audit summaries, Alembic logs and native comparison snapshots are preserved
under the ignored `.tools/schema-sync-current-42208d451b86492498a8c71e4eb73372/` directory.
Updated the launcher guide to reference the current record instead of stale installed
revision numbers. Feature minimum revisions remain distinct from the required current head.

## Warehouse/reference delivery verification on 2026-10-24

Repeated the seven live Alembic comparisons against the current working-tree models
after implementing the warehouse/reference UI and Identity lookup contracts. Every
revision and table count still matches the table above. No missing or extra tables,
column/type/default/key drift, or proposed Alembic operations were found. Additional
native inspection found zero differences for all seven services in primary keys,
check names/expressions, generated columns/storage, column collations and table options.
No database, model or migration repair was needed for this delivery.

Compared the installed reference seed rows with the committed datasets and pinned
timezone data, including their stored values and provenance. There are no differences:

| Reference | Installed seed rows | Shipped rows |
|---|---:|---:|
| Countries | 239 | 239 |
| States | 5,027 | 5,027 |
| Currencies | 168 | 168 |
| Languages | 184 | 184 |
| Timezones | 598 | 598 |

These checks were read-only and preserved operator-maintained data. The new API
contracts use the existing Identity tables; regenerated OpenAPI/client definitions
are synchronized with those contracts (client version 0.2.13).

The current Windows backend, UI and reference-sync launcher suites passed all 49
tests; all 49 PowerShell scripts parsed without errors. A read-only status check
reported all eleven backend components UP. Running services were preserved, so new
Identity routes load on the next normal service restart.

Comparison summaries, Alembic logs, extended native snapshots and the reference seed
comparison are retained under ignored `.tools/warehouse-schema-review-20261024/`.
Implementation and broader UI/API verification are recorded in
[warehouse-reference-ui.md](warehouse-reference-ui.md).

## Organisation/access delivery verification on 2026-10-24

Repeated all seven live Alembic/model checks and the additional native comparisons
after the six-master organisation/access delivery. The installed heads and model
table counts still match the table above. Every comparison reports alignment, no
missing/extra tables and zero native differences. New organisation form/detail/list
contracts and UI affiliation workflows reuse existing tables: no DDL or migration
repair was required. Startup scripts and model inventories were preserved.

OpenAPI, the generated Identity client and its UI consumers are synchronized at
client version 0.2.14. Read-only schema evidence is retained under ignored
`.tools/organisation-access-review/schema/`; the implementation and test record is
[organisation-access-delivery.md](organisation-access-delivery.md).

## Configuration delivery verification on 2026-10-25

Repeated the seven live database/model/Alembic comparisons after the company,
product, account/party/supplier configuration and configuration UX deliveries.
All 454 model tables match the installed schemas. Each database remains at the
single migration head listed above, with matching readiness constants where
defined, no pending migrations, no missing/extra tables and no proposed Alembic
operations. The configuration changes reuse the existing storage; no database,
model or migration repair was required.

Additional read-only native MySQL inspection found zero differences across all
seven services in primary keys, check names/expressions, generated expressions
and storage, explicit column collations, and table engine/collation/row format.
The Windows service registry's project paths, database names, environment prefixes
and migration locations agree, and all required local paths exist.

| Targeted suite | Passed | Native/container tests deselected |
|---|---:|---:|
| Identity migration chain/target | 685 | 4 |
| Audit models/migrations | 28 | 2 |
| Catalog migrations/defaults/constraints | 15 | 1 |
| Notification models/migrations/types | 6 | 0 |
| Accounting constraints | 1 | 0 |
| Vouchers defaults/constraints | 7 | 0 |
| Reports defaults | 1 | 0 |
| Windows backend/UI/reference-sync launchers | 49 | 0 |

Total: 743 backend checks and 49 launcher tests passed. All 49 Windows PowerShell
scripts parsed successfully. Native schema comparisons were performed separately
against the live local databases; container migration round-trip tests and the full
application suites were not rerun. A fresh read-only status check reported all eleven
backend components `UP`, including readiness for every API. Running processes and
application data were preserved.

Manual simplification and security/correctness review of this verification found
no additional issues. No application code, credentials or authorization settings
were changed. Read-only comparison summaries, Alembic logs, native snapshots,
test logs and status evidence are retained under the ignored
`.tools/schema-sync-20261025-config/` directory.

## Design service added on 2026-10-25

The `design` database replaces the hand-written `dbs/design/schema.sql` with an
independent eight-revision Alembic chain (`dbs/design/`), one DDL statement per
revision and a working `downgrade` on each. Verified against local MySQL 9.6 on a scratch `design_check` database:
`upgrade head` applies all eight, `alembic check` reports no new upgrade operations
against the models, and `downgrade base` followed by `upgrade head` round-trips. The
partial-unique emulation was exercised directly — two archived rows plus one live row
sharing a code are accepted, a second live duplicate is rejected with an
`IntegrityError`. Two
expected warnings remain — the deliberate `invoice_template` ↔ `invoice_template_version`
foreign-key cycle, which is why the second direction is its own revision 0004, and
Alembic's note that a computed column (`invoice_template.live_code`) cannot be compared
for modification.

Tables are singular and the service owns seven: its own `outbox` plus the six layout and
evidence tables ([invoice-design.md](invoice-design.md) §1). `design.metadata.TABLES` is
listed literally so the readiness probe's comparison cannot shrink when an import moves,
and `MIGRATION_HEAD` (`0008`) is asserted by that probe and by a test against the
revision filenames. The launcher registry now lists design on port 8014 with route
`/design/`, and `write-envs.ps1` generates its `DESIGN_CURSOR_SIGNING_SECRET`.

At this delivery, the local database still held the superseded plural tables and
had no migration revision. The following repair supersedes that pending operator
step and the earlier instructions to drop the legacy tables.

## Synchronization and Design recovery on 2026-10-26

All eight live databases match their independent migration heads and all 461 model
tables listed above. Readiness constants and launcher mappings agree. Alembic checks
and additional native inspection report no differences, including named foreign keys,
check expressions, generated expressions/storage, collations and table options.

Design's six legacy tables contained 98 rows. A full SQL backup was restored into
an isolated rehearsal database and checked against row counts and logical row hashes.
The old tables were then preserved by one cross-schema rename into
`design_legacy_20261026_beab902045`; their relationships, row counts and hashes were
verified again. The existing eight migrations created the current seven-table schema
at revision `0008`. Upgrade, downgrade to base and re-upgrade passed in rehearsal
before the live migration. Only the generated rehearsal schemas were removed.

| Preserved legacy table | Rows |
|---|---:|
| invoice_templates | 35 |
| invoice_template_versions | 35 |
| invoice_template_assignments | 16 |
| invoice_template_assets | 6 |
| invoice_template_components | 6 |
| invoice_render_snapshots | 0 |

These legacy layouts remain in the archive; they were not converted into the new
Design UI's storage. Keep the archive and backup if those layouts are needed later.
The private `start/win/env/design.env` was created with a dedicated account restricted
to SELECT, INSERT, UPDATE and DELETE on `design.*`. Its inability to read another
service's tables was verified. Administrator credentials were supplied through a
hidden prompt and were not saved. The managed Design API now reports ready on 8014;
all twelve backend component probes report `UP`.

Notification's model now explicitly retains `fk_notification_delivery_assignment`,
the name defined by its applied lineage revision `0113`. Column and relationship
contracts already matched; no new DDL, applied-history edits or API shape changes
were required. A regression test first reproduced the naming mismatch. The launcher
test now expects all eight registered APIs and explicitly includes Design.

Added the reusable read-only [verification command](../dbs/README.md):

```powershell
uv run --project apis/identity python dbs/verify_sync.py --output-dir .tools/schema-review
```

It runs each service in its own interpreter, rejects ambiguous private environment
keys, avoids credential output, and reports a nonzero exit for drift. Expression
comparison preserves string literals and operator precedence. Unsupported SQL syntax
is compared conservatively rather than assumed equivalent.

Validation: six verifier regression tests, seven Notification schema/migration tests,
sixteen Design service-contract tests and forty-nine backend/UI/reference launcher
tests passed. Ruff and strict mypy passed for the verifier and affected Notification
model/migration-test files. Live schema checks and the MySQL restore/migration rehearsal ran
separately. Full application suites and a new overall coverage run were not run.

Manual simplification and security/correctness review addressed the constraint-name
and expression-grouping findings. Restricted runtime grants, retained legacy data,
private environment handling and independent migration ownership were checked.
`/simplify` and `/security-review` commands were unavailable, so equivalent manual
reviews were used. Backups, retained row evidence, repair state, schema summaries and
test logs are under the ignored `.tools/schema-sync-20261026/` directory. Sensitive
backup and environment files retain private Windows access permissions.
