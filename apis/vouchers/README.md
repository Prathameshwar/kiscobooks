# Vouchers API

Shared voucher document foundation, port **8012**, public gateway prefix **/vouchers**.
This service stores documents and evidence. Accounting remains the authority for journals,
balances, settlements, tax and future stock effects. Payroll is excluded.

Implementation and activation checks are tracked in
[the Phase 1 record](../../docs/voucher-phase1-execution.md) and
[the live todo](../../docs/voucher-implementation-todo.md). Do not infer C0 activation
or financial readiness from a healthy process.

## Implemented surface

- 22 immutable system kinds and supported profiles; company-defined types and revision-bound
  classes. Shared tables only: 37 voucher tables and three platform infrastructure tables.
- Typed native configuration, restrictive company/type/class resolution, dated bindings,
  publication, retirement, optimistic versions and captured configuration digests. Allowed
  issue series/template revisions and inherited defaults are enforced at issue/render requests.
- Stable document IDs, immutable revisions/logical line keys, item identity and exact
  actual/billed quantities, parties, references, attachment metadata and source links.
- Draft/edit/submit/approve/reject/cancel and non-statutory issue numbering by company year.
  Reprinting uses the same document/template evidence and never allocates a posting.
- Twelve typed header/item custom-value types, Identity-owned definitions, local signed
  projections, uniqueness claims, auxiliary sequences, indexes and explicit compatible adoption.
  A permission-aware mapping primitive supports later source-linked document conversions.
- Durable artifact/execution work, signed Accounting command/status/result adapters,
  strict terminal identity, transactional audit outbox and confirmed RabbitMQ publisher.
- Masked reads, filtering and paginated export/history; signed cursors and short-lived,
  current-authority artifact downloads. Generated TypeScript client and common web entry/workflow/history forms.

Phase 2 adds typed accounts, tenders and selected bill instructions to shared immutable
revisions. Journal, Contra, Payment and Receipt support ordinary posting/reversal, advances,
refunds, split tenders and non-tax bill adjustments through the Accounting owner. Native
policy restricts account roles, currencies, tracking, modes, instrument dates and references.
Both owner and producer money flags default to disabled; C1 release activation is separate.
Invoice calculations, GST, stock movement and statutory numbering remain later batches.
Attached object keys are scoped
references; this foundation does not claim uploaded-object verification or download authority.

## Local operation

Use the existing Windows setup/service manifest; it includes the independent database,
migration tree and service. No existing application database was migrated during this task.

Required environment values: `VOUCHERS_DATABASE_URL`,
`VOUCHERS_ACTOR_SIGNING_SECRET` (same gateway verification key as Identity), and
`VOUCHERS_ARTIFACT_SIGNING_SECRET`. Generate secrets privately; never commit env files.

From `apis/vouchers`:

```powershell
uv sync --locked
uv run alembic -c ../../dbs/vouchers/alembic.ini upgrade head
uv run uvicorn vouchers.main:create_app --factory --host 127.0.0.1 --port 8012
```

Workers accept `--env-file <private-file>`:
`vouchers.tasks.artifact_worker`, `vouchers.tasks.source_worker`,
`vouchers.tasks.execution_worker`, `vouchers.tasks.audit_publisher`. The existing `start/win/audit-workers.ps1` manages
`vouchers-artifacts`, `vouchers-sources`, `vouchers-executions` and `vouchers-publisher`, including owned
PID checks and hidden process windows. Source polling requires configured
`VOUCHERS_SNAPSHOT_OWNERS`; each entry has owner, HTTPS origin (literal loopback HTTP is allowed for local development), key ID, secret and explicit
tenant/company scopes. Configure matching `*_VOUCHER_SNAPSHOT_CREDENTIALS` on Identity,
Catalog and Accounting. Responses are signed and bound to the exact request.

Push ingress uses `VOUCHERS_SOURCE_CREDENTIALS` with explicit issuer, operation and company grants. Source credentials default to
`vouchers.sources.apply` only; execution receipts require a separate explicit
`vouchers.execution.result` grant for Accounting.
Internal source/result routes are unavailable through the public Vouchers gateway.
Master snapshots are validation evidence for drafts, never financial posting authority.

Audit publisher requires `VOUCHERS_AUDIT_BROKER_URL`, `VOUCHERS_AUDIT_BROKER_USER`,
`VOUCHERS_AUDIT_EVENT_SECRET`, and optional key ID/exchange settings. Provision Audit with
the matching scoped producer and exact event allowlist from `events/audit_contract.py`.
Use the publisher's `--status`, `--dead-letters` and `--retry` commands for delivery
inspection. HTTP health alone does not prove broker delivery.

The console uses `VOUCHERS_GATEWAY_URL` (gateway origin plus `/vouchers`) and the
existing authenticated server proxy. Catalog item/unit lookup uses `CATALOG_GATEWAY_URL`;
party lookup uses `ACCOUNTING_GATEWAY_URL`, with each owner's current field permissions.
The common form supports types/classes, entry mode, header/item custom fields, actual/billed
quantities, parties and external references. Saved vouchers expose permitted workflow and
history actions. Phase 2 adds policy-aware financial entry, durable post/reverse status,
recovery and bank/report screens. No mobile application exists in this repository; portable
generated contracts are shared with future clients.

Execution delivery requires `VOUCHERS_EXECUTION_OWNER` with owner `accounting`, origin,
key ID, secret and explicit tenant/company scopes, plus matching
`ACCOUNTING_VOUCHER_EXECUTION_CREDENTIALS`. Use a credential separate from snapshots.
The `all` worker launcher skips execution delivery if it is not configured. All native
money admission is disabled unless `VOUCHERS_MONEY_EXECUTION_ENABLED=true` and
`ACCOUNTING_VOUCHER_MONEY_ENABLED=true` on the corresponding services. Deploy compatible
Identity gateway contexts first: money commands require signed Vouchers and Accounting
field-policy provenance. Workers reconcile an unknown outcome under the original identity.
Stock, tax and unsupported money profiles remain unavailable even with these flags set.
The [shared protocol README](../../clients/voucher-execution/README.md) describes identity,
cancellation, signed reconciliation and native owner-transaction tests.

Bulk import of Purchase, Sales, Credit/Debit Note, Payment, Receipt, Contra and Journal drafts
([plan](../../docs/voucher-import-plan.md)) adds
`/v1/companies/{company_id}/voucher-import-templates` and `/voucher-imports` (stage, list,
validate, commit, cancel, run, per-voucher results and a signed five-minute result report).
It creates drafts only. Validation runs the native draft write in a rolled-back transaction,
then calls the Accounting invoice preview with the actor's delegated authority; commit
creates one draft per voucher through the ordinary create command. Both advance in bounded
steps of 20 vouchers inside authenticated requests (`POST .../run` continues a job).
Configure `VOUCHERS_MASTER_LOOKUP_OWNER` (owner `accounting`, origin, key ID, secret and
tenant/company scopes; the key must be one of Accounting's
`ACCOUNTING_VOUCHER_SNAPSHOT_CREDENTIALS`) and `VOUCHERS_EXECUTION_OWNER`; validation refuses
to start without both. The upload route alone accepts bodies up to 12 MiB, so a gateway in
front of Vouchers must allow that size for `POST /v1/companies/{id}/voucher-imports`.

## Verification

```powershell
uv run pytest -q --cov=vouchers.domain --cov-report=term-missing
uv run mypy src/vouchers
uv run ruff check src tests tools
uv run python tools/export_openapi.py --check
uv run python tools/verify_mysql.py
```

Native verification creates its own random `vouchers_test_<uuid>` database on loopback
MySQL port 13396, runs all migrations, compares columns/indexes/unique and foreign keys,
runs the API/concurrency suite, downgrades and upgrades again, then drops only that database.
Set `VOUCHERS_TEST_BROKER_URL` to the isolated local RabbitMQ test vhost to include real
confirmed delivery and Audit consumer redelivery checks. Ordinary SQLite runs explicitly
skip the MySQL row-lock and live-broker tests.

Custom-definition adoption validates current documents, then atomically updates claims and
indexes under the company fence. It never rewrites historical values or definitions.
Incompatible values/types/sequences fail; users must correct current drafts or perform an
explicit future migration. C0 adoption is bounded to 1,000 current documents per company;
larger resumable adoption is an outstanding capability, not an implicit partial success.

See [Phase 2 evidence and rollout](../../docs/voucher-phase2-execution.md) for the precise
money scope, native verification, schema changes and activation obligations.
