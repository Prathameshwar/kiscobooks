# Reports API - financial statements and registers

Reports owns reconstructible read models and frozen outputs, never the financial books.
Accounting is the financial source owner. API prefix: `/reports/v1/companies/{company_id}`
through the gateway; local service port 8013. Payroll is excluded.

The reusable framework is available under `/reports/v2/companies/{company_id}` through the
gateway. It adds typed definitions, immutable source generations, durable background runs,
scoped row paging/drill-down and independent PDF/HTML/CSV/XLSX exports. Existing v1 routes
remain supported. See the [execution record](../../docs/reports-framework/execution.md) and
[framework usage guide](../../docs/reports-framework/usage.md). New admissions are disabled
by default and require explicit worker, owner, authority and private-folder configuration.

The user excluded load/soak testing from this delivery. Earlier benchmark evidence is retained
as historical development evidence; it is not a production capacity guarantee.

## Existing v1 contract

1. Request a generation with `POST /report-generations` and `Idempotency-Key` (202).
2. The worker requests a signed immutable Accounting snapshot, resumes bounded pages,
   catches up through a frozen committed sequence and reconciles complete source facts.
   It atomically switches the company activation pointer only after successful checks.
3. Request `POST /report-runs` with `generation_id`, a definition code and its required filters.
   Poll the run, page its frozen rows, or download its signed CSV artifact.

GET generation/run lists use signed keyset cursors (50 default, 200 maximum), lean
SQL projections and no exact total. Definition catalogue and field-set metadata advertise
only implemented definitions. Runs retain generation, source manifest, rules, permission
scope, reconciliation and artifact hashes. A new generation never rewrites an old run.

Phase 2 supplies 16 financial definitions: ACCOUNT_LEDGER, DAY_BOOK, TRIAL_BALANCE,
PROFIT_LOSS, INCOME_EXPENSE, BALANCE_SHEET, ACCOUNT_SUMMARY, PARTY_LEDGER,
OUTSTANDING_BILLS, ADVANCES, AGING, CASH_BOOK, BANK_BOOK, BANK_RECONCILIATION,
PAYMENT_REGISTER and RECEIPT_REGISTER. SOURCE_RECONCILIATION remains a diagnostic.
Tax, stock, WIP, order and job-work feeds arrive in their named later batches.
The console provides definition/parameter selection, generation status, frozen paginated
rows, signed CSV and permission-controlled banking history. No mobile app exists here.

Statements use full-company base currency and native head classifications; income/expense
is accrual-based. Account/party books may select one transaction currency. Balance Sheet
separates entered opening equity, prior untransferred earnings and current-year earnings;
carry is derived, never another opening journal. Day/month account and descendant-group
summaries retain opening, gross turnover and closing balances. A leaf contributes once.
Missing retained history or required classifications prevents a plausible partial statement.
Imported pre-cutover YTD and automated annual profit transfer are not implemented.

Bill/advance/aging views apply allocations and reversals as of the requested date and keep
original due dates across years. Money registers use tender grain, exact FX residuals and
signed reversal amounts; legacy entries without instrument evidence use UNSPECIFIED mode.
Bank books follow GL booking dates. BRS separately considers dated instrument events and
requires a statement balance plus complete instrument evidence (including adopted legacy
opening lines). It never posts money from a clearance/reconciliation event.

## Storage and recovery

Thirteen business tables: report_company, report_generation, report_bundle,
report_staged_fact, report_fact, report_line, report_account_total, report_activation,
report_source_claim, report_definition, report_run, report_row and report_artifact.
Three standard platform tables support idempotency, outbox and inbox. Native migrations
0001-0016 each execute one DDL statement and have a downgrade.

Native journal-line projections retain separate transaction/base amounts, currency,
PRINCIPAL/FX component, account, party/role, period and posting date. FX lines may have
zero transaction amount and positive base amount. DAY/MONTH totals store gross base
currency debit and credit as DECIMAL(19,4), never sums across currencies. Full exported
facts retain descriptions, classification, source/reversal identities, terms and rates.

Staging resumes from a durable ordinal. Only a complete checksum-verified source bundle
advances facts and the checkpoint in one transaction. Duplicates cannot double facts;
conflicting committed identities, missing sequences/references, bad signatures or failed
controls prevent activation. Transport outages retry; verification failures quarantine.
Request a new generation after repairing the source. No API edits report facts or balances.
Earlier-period changes/reopen are reflected by a new generation; no mutable carry cache
exists; daily/monthly report calculations use the same pinned source generation.

The v1 limits remain: 100,000 facts per snapshot/generation, 200 facts and <1 MiB per response,
1,000 catch-up bundles per worker poll. Source snapshots hold a company write fence while
materializing; B45 must measure scale/latency before larger bounds are enabled. Current
bounded v1 CSV artifacts are stored in the Reports database. V2 exports use the configured
private filesystem and independent jobs. Completed reports/exports are retained; automated
cleanup removes only abandoned temporary files with matching terminal attempt evidence.

## Authorization and configuration

Environment uses REPORTS_DATABASE_URL, REPORTS_ACTOR_SIGNING_SECRET,
REPORTS_ARTIFACT_SIGNING_SECRET and REPORTS_OWNERS. The last is a JSON list of owner
objects: owner=accounting, origin, key_id, secret and explicit tenant_id/company_id scopes.
Accounting must have matching ACCOUNTING_REPORT_CREDENTIALS keyed by key_id. Use private
HTTPS origins (literal loopback HTTP only for local development); never commit credentials.
Owner calls are signed, response-bound and made outside Reports database transactions.
No service reads another service database or reuses a public actor token for ingestion.

Run the API with `uv run uvicorn reports.main:create_app --factory --port 8013`.
Run synchronization with `uv run python -m reports.tasks.worker --env-file <private-file>`.
Run audit delivery with `uv run python -m reports.tasks.audit_publisher --env-file <private-file>`.
The publisher uses REPORTS_AUDIT_BROKER_URL, REPORTS_AUDIT_BROKER_USER,
REPORTS_AUDIT_EVENT_SECRET and REPORTS_AUDIT_EVENT_KEY_ID; configure the matching Audit
Reports issuer and broker-user allowlist. The worker launcher skips unconfigured source
workers; applying migrations, creating credentials and starting services are deployment work.

Input authority requires report.read plus accounting.finance/head/group/account/party/setup.read
and period.read for the company. Generation requests additionally need report.definition.manage;
downloads need report.export. Applicable read-deny policies conservatively block complete-company
reports. Every retrieval rechecks live authority; artifacts and cursors are actor/scope-bound.
Download tokens expire after 120 seconds. CSV free text is formula-escaped.
Financial definitions additionally require ledger and applicable bill/settlement permissions;
BRS and payment/receipt registers require accounting.bank.read, including frozen retrieval
and export. Unsupported/ignored filters are rejected, not silently discarded.

The Phase 2 19-grain contract changes the owner manifest schema hash. Upgrade compatible
owner/consumer packages and request a fresh generation. Previously frozen outputs remain
readable with current permissions; old snapshots cannot imply absent facts are zero.

## Verification

```powershell
uv run pytest -q --cov=reports.domain --cov-report=term-missing
uv run ruff check src tests tools
uv run mypy src
uv run python tools/verify_mysql.py
uv run python tools/export_openapi.py --check
```

Native verification uses only a disposable loopback reports_test_<uuid> schema, checks
columns/indexes/scoped FKs/DECIMAL scale and runs upgrade/downgrade/upgrade. The RabbitMQ
test requires REPORTS_TEST_BROKER_URL; it uses ephemeral queues and verifies confirmed,
signed delivery through the real Audit handler including duplicate suppression.
See [Phase 2](../../docs/voucher-phase2-execution.md) and
[B09](../../docs/voucher-b09-execution.md) for evidence and activation limits.
