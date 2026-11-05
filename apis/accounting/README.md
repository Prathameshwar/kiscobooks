# Accounting API

Accounting owns a company's chart of accounts and its counterparty masters: account heads,
account groups and their closure paths, ledger accounts with tax and bank profiles, parties with
roles, addresses, contacts, tax registrations, identifiers and bank accounts, payment terms,
accounting and credit policies, and the posting mappings that later services resolve. Identity
supplies the verified actor, company, capability, layout and field-policy context; Accounting
never issues it. See [design](../../docs/accounting-design.md) for the model and decision log and
the [master completion todo](../../docs/accounting-masters-todo.md) for phase state.

Accounting also owns journals, fiscal periods, openings, open items, settlements, credit,
charges and accounting tax; see the [finance contract](../../docs/accounting-finance-contract.md).
The [Vouchers plan](../../docs/vouchers-plan.md) replaces future Billing/Payments applications
with one document API. Accounting retains posting authority; the proposed stock/value extension
is future work. Company scope and field protection apply throughout.

## Contract

Business routes are prefixed `/v1/companies/{company_id}` and every one declares a required
permission. Only `/health/live` and `/health/ready` are public operational probes. Lists follow
[api-conventions](../../docs/api-conventions.md) — signed keyset cursors, allowlisted typed
filters, allowlisted sorting and a lean `ListItem` projection, never the detail model. Each
resource also serves `GET /{resource}/field-set`, which clients render forms from instead of
hardcoding a field list.

Two cross-resource surfaces sit alongside the masters: `/imports/{preview,apply}` for bounded
transactional loads, and `/exports/{resource}` plus `/history/{resource}/{object_id}` for
protected extraction. Read denies apply to all three, exactly as they do to detail reads.

`openapi.json` is committed and is the input to `clients/api-client` generation.

## Local development

Use Python 3.12 and the committed lockfile. From this directory:

```powershell
uv sync --frozen
uv run --frozen uvicorn accounting.main:create_app --factory
uv run --frozen pytest --cov
uv run --frozen ruff check src tests tools
uv run --frozen ruff format --check src tests tools
uv run --frozen mypy src tests tools
uv run --frozen python tools/export_openapi.py --check
uv run --frozen python tools/export_field_contract.py --check
uv run --frozen python -m tools.export_master_matrix --check
uv run --frozen python -m tools.generate_exports --check
```

`mypy` covers source, tests and tools under strict settings. The generated
[resource matrix](../../docs/accounting-master-matrix.json) records fields, dependencies,
query support, permissions, indexes and workflows for all 29 business resources.

`dbs/accounting` is deliberately outside the lint scope: each revision carries its generated DDL
as one verbatim string, and reflowing those strings is how a `VARCHAR` length or a collation
quietly changes. Read revisions line by line instead — see the note on native verification below.

`start/win/start-services.ps1` runs the HTTP process on port 8011 from the repository root
(the registry-driven launcher reads `start/win/conf/services.json`; `start-all.ps1` starts every
service). Configuration is environment-only under the `ACCOUNTING_` prefix: `ACCOUNTING_DATABASE_URL` and
`ACCOUNTING_ACTOR_SIGNING_SECRET` are required, and `ACCOUNTING_ENCRYPTION_KEY` — 32 hex-encoded
bytes — is required before any party bank account can be written. Supply all three from
deployment secret storage. Startup neither creates nor migrates a database.

From the repository root, apply migrations only against the intended development database:

```powershell
apis/accounting/.venv/Scripts/python.exe -m alembic -c dbs/accounting/alembic.ini upgrade head
apis/accounting/.venv/Scripts/python.exe -m accounting.seeds.reference
```

The original master increment used revisions 0001-0072. Finance and tax increments extend
the chain through 0108. `accounting.metadata.MIGRATION_HEAD` names the revision the
service expects; readiness reports a mismatch rather than migrating. ISO reference data is seeded
after migrating and before starting, and the account-group and account templates in
`accounting/seeds/templates.py` establish the fixed business chart during
`POST /accounting-setup/initialize`: five heads, 28 groups and 12 active starter accounts.
The existing bounded finance bootstrap can initialize this fixed chart without master CRUD
authority. Existing authored/installed charts are preserved. Further chart and registration-specific
additions use the separately authorized `POST /accounting-setup/preview` and `/install`, never a migration.

## Native database verification

SQLite tests do not replace a live MySQL check: MariaDB narrows a `DECIMAL` scale silently, and
`alembic --autogenerate` misses generated columns, index renames and `VARCHAR` length. For a
disposable native run, set `ACCOUNTING_TEST_MYSQL_SERVER_URL` to a loopback development server URL
carrying no database — it defaults to the disposable server `start/win/identity-test-mysql.ps1`
listens on — then from this directory:

```powershell
uv run --frozen python -m tools.verify_mysql --full-suite
uv run --frozen python -m tools.verify_legacy_mysql
```

Running as a module makes the tool's shared test helpers importable. It creates a random
`accounting_test_` schema, upgrades to head, asserts model/migration parity with
`compare_metadata`, exercises setup, template install, listing and concurrent idempotent retries,
downgrades to base and re-upgrades, then drops only that schema. It needs database creation
rights and never selects an existing application database. The migration environment is bound
to that random schema even if the caller already has `ACCOUNTING_DATABASE_URL` set, and the
actual connection is checked. `--full-suite` runs every Accounting test with native foreign
keys and coverage before the migration round trip; `--regressions` runs only the three data
and policy regression suites. Omitting both flags runs the native smoke and migration checks.
The native smoke also explains representative alias, display-order and dated association
queries. The legacy harness starts at 0037 with v1/v2 installations and existing masters;
it checks schema retry, metadata rollback/retry, safe template upgrades and used-account conflicts.

## Identity policies and gateway

The checked-in nginx `/accounting/` location calls Identity's private authorization endpoint
with the original request URI and session credentials. It replaces all four actor/company
context headers with signed values returned by Identity. Identity's internal routes are not
publicly proxied. Unauthorized requests and unavailable authorization dependencies return the
JSON error envelope. Identity and Accounting must share `ACTOR_SIGNING_SECRET`; the Windows
environment generator aligns verification keys on rerun while preserving database and
encryption settings. Restart affected development processes after deliberately applying an
environment change.

Identity owns policy administration through `/v1/field-policies` and native layout through
`/v1/entities/{entity_type}/field-config/{field_key}`. The generated Accounting field contract
registers `accounting.party`, `accounting.account`, and all other Accounting resource types.
Policy authoring requires tenant-scoped `field_policy.manage`, the corresponding resource's
read/manage permission at the policy scope, and the existing subject/delegation guards.
Layouts require tenant-scoped `field_config.manage`; making additional fields required is
still rejected until an existing-data validation workflow exists. Accounting custom-field
definitions are not implemented. Regenerate `tools/export_field_contract.py` whenever native
fields change, then regenerate Identity OpenAPI and the TypeScript client when its schema changes.

Conditions use native UUID, date and Decimal types consistently. Writes check existing and
resulting state; creates check only resulting state. Lists, exports, history and form metadata
have no complete per-record snapshot, so conditional denies are applied conservatively and
conditional allows cannot relax them. Structural read denies make the resource unreadable;
history omits denied changed-field names. Form writability also requires a scoped manage grant
and an editable resource. Layout visibility remains presentation rather than authorization.

## Template upgrades and import receipts

Template version 3 retains the full GST registration UUID in generated account identifiers.
The base has 28 groups (15 primary and 13 subgroups); the optional GST extension adds
Tax Recoverables. Preview before installing with a new idempotency key for each selection
to create version 3 bindings. The safe legacy Reserves correction moves it under Capital
only when its subtree has no used account and existing classification agrees.
A compatible version 1 account is reused, including a financially used account, without
changing its identity, tax profile or old bindings. Reuse requires an exact registration and
classification match. A registration whose old installation collided gets separate accounts.
The original receipts and bindings remain historical evidence; this is an explicit install
workflow, not an automatic mutation of existing company data.

After upgrading an existing 0037 database, complete the explicit company metadata backfill
before serving traffic. Pending metadata blocks company reads, writes and saved-command
replays; readiness remains unavailable while any setup is pending. See the
[release procedure](../../docs/accounting-masters-release.md) for scope, commands and rollback
restrictions. Schema migration alone does not rewrite company data.

Imports still accept up to 200 records and 50-character client keys. Stored receipts contain
only ordered IDs, and replay reconstructs the client-key mapping from the identical request.
Old key-to-ID receipts remain readable. Preview rolls back business and audit effects; apply
and replay recheck current authorization.

## Audit publisher

Run the HTTP service and publisher as separate supervised processes. From this directory:

```powershell
uv run --frozen python -m accounting.tasks.audit_publisher --env-file ../../start/win/env/accounting.env
```

In addition to `ACCOUNTING_DATABASE_URL`, the publisher requires
`ACCOUNTING_AUDIT_BROKER_URL`, `ACCOUNTING_AUDIT_BROKER_USER`, and
`ACCOUNTING_AUDIT_EVENT_SECRET` (at least 32 characters). Supply private credentials through
the environment or secret storage; the HTTP environment generator does not provision broker
users. The key ID defaults to `accounting.current` and the exchange to `platform.audit`.
Configure the Audit consumer's `AUDIT_SOURCE_CREDENTIALS` entry under that key ID with issuer
`accounting`, the matching broker user/secret, and the exact `AUDIT_EVENTS` set from
`accounting.events.audit_contract`, including setup update/metadata upgrade and group-alias
events. Publisher confirms precede outbox acknowledgement, and
Audit deduplicates redeliveries. Broker topology and credentials must be provisioned before
running either process; no production broker or application outbox is modified by tests.

The [September 14 review](../../docs/accounting-review-20260914.md) records reproduced defects,
repairs, verification evidence and remaining scope.
The [master completion reviews](../../docs/accounting-masters-completion-review.md) record
the subsequent six-phase implementation and both final review-and-fix passes.

Reusable integration probes run isolated test processes and credentials:

```powershell
# Accounting directory; point to an installed nginx executable.
$env:ACCOUNTING_TEST_NGINX_BINARY = 'C:/path/to/nginx.exe'
uv run --frozen python -m tools.verify_gateway
# Identity directory, with both service source trees importable.
$env:PYTHONPATH = '../accounting/src;.'
uv run --frozen python tools/verify_accounting_bridge.py
# Audit directory; provision IDENTITY_TEST_BROKER_URL and IDENTITY_TEST_BROKER_USER.
uv run --frozen pytest tests/test_live_rabbitmq.py
```

## Accounting to Audit integration

Accounting stages canonical audit events in the business transaction. It makes no synchronous
Audit API call while changing money. Audit APIs serve authorized history, investigations and
exports through Identity and the gateway. Local master revisions retain their short verbs.

See the [event/privacy contract](../../docs/accounting-audit-contract.md), generated
[event matrix](contracts/audit-events.json), [worker/recovery runbook](../../docs/accounting-audit-operations.md)
and [implementation reviews](../../docs/accounting-audit-integration-review.md).
The Windows worker launcher manages the Accounting publisher, Audit consumer and Audit export
publisher separately from HTTP services. Both publishers support `--status`, explicit `--retry`
with dry-run default, and authenticated `--dead-letters` recovery. Secrets stay in private env files.


The Vouchers Phase 1 foundation adds private signed execution/status endpoints and
`voucher_source_guard` / `voucher_execution` in migrations 0109-0110. Configure explicitly
scoped `ACCOUNTING_VOUCHER_EXECUTION_CREDENTIALS` separately from snapshot credentials.
Phase 2 implements ordinary Journal/Contra/Payment/Receipt and their reversals under
`ACCOUNTING_VOUCHER_MONEY_ENABLED` (default false). Tax and stock profiles remain disabled.
The adapter's native transaction/period/cancellation/retry tests are in
`tests/test_voucher_execution.py`; money, banking and allocation tests extend that boundary.


## Committed reporting exports (B09)

Private `/internal/v1/reporting/{tenant}/{company}` endpoints expose immutable snapshots,
head barriers, sequenced change manifests and bounded fact pages to Reports. Configure
`ACCOUNTING_REPORT_CREDENTIALS` with separate Reports requester keys and explicit company
grants. Public gateway access to `/accounting/internal/` is denied.

The 19-grain shared `reporting-contract` covers current classifications, fiscal setup/year/
period transitions, journals/lines, openings, source documents, bills/allocations and committed
voucher execution receipts, money lineage, banking evidence and allocation links. Payloads
exclude delegated credentials, bank secrets and tax identifiers. One root ORM
transaction captures final changed facts, control totals and audit outbox rows atomically;
rollback publishes nothing. The existing company setup lock serializes commit sequences and
snapshot materialization. Normal owner APIs already acquire that same lock before mutations.
Reports never reads this database. Direct Core/raw-SQL maintenance that bypasses ORM capture
is outside the feed contract and requires a controlled rebaseline; do not use it for live edits.

Migrations 0111-0114 add report_change, report_change_fact, report_snapshot and
report_snapshot_fact. They do not rewrite financial_v1 events or prior posted money.
A snapshot is capped at 100,000 facts, with bounded retained pages. Initial coverage is the
retained ledger from books-begin; legacy YTD and absent historical labels are not fabricated.
See [B09 execution](../../docs/voucher-b09-execution.md) for tests and limits.

## Voucher money and manual banking (Phase 2)

Migrations 0115-0116 extend journal kind to VOUCHER; 0117-0120 add shared
voucher_money_intent, bank_instrument, bank_instrument_event and voucher_money_allocation.
The existing journal/line/open-item/allocation tables retain all financial authority.
The journal-kind downgrade requires no retained VOUCHER rows; preserve real history with
forward repairs instead of treating disposable-schema round trips as a production rollback.

Private protocol v2 prepares durable intent, reserves current Identity authority outside
the transaction, then atomically commits GL, bills, allocations, instruments, receipt and
audit/report facts. Posting allocates numbers by company/series/year. Generic journal
post/void cannot bypass voucher execution. A failed allocation bundle leaves no partial
settlement or cash movement; cancellation abandons only uncommitted prepared state.

Company-scoped bank-instrument list/detail/history, event and legacy-adoption APIs use
current field permissions and idempotency. Events append evidence with an expected last
event; booking, clearing and reconciliation are distinct. Cleared/reconciled instruments
require a refund voucher; unreconciling does not erase clearance. BOOK_DATE PDC books immediately; MATURITY_DATE
rejects execution before maturity. There is no scheduler that automatically posts a cheque.

Financial-year readiness reports calendar continuity, current Identity finance evidence,
initial opening state, prepared/draft owner work and native closing checks. Existing
generate/open/close/reopen workflows remain authoritative; LOCKED is terminal. Outstanding
bills carry across years without copied openings or reset due dates. `/ledger/balance`
retains cumulative semantics; frozen period/current/currency views belong to Reports.
See [Phase 2 scope and evidence](../../docs/voucher-phase2-execution.md).
