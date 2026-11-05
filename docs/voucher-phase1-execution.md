# Phase 1 implementation record

Started 2026-10-10 following explicit authorization to implement B01-B08.
The batch tracker and todo remain the completion authority. This record separates
verified implementation from contracts for later owners and capabilities.

## Foundation decisions

- Accounting remains the only owner of financial, settlement, tax and future stock
  effects. Existing finance routes, source identities and cumulative balance semantics
  remain compatible. No Vouchers balance tables or independent posting adapters.
- C0 supports common draft content, type/configuration administration, approval and
  non-statutory document evidence. Every actual financial/stock execution profile stays
  disabled until its corresponding later batch and owner contract pass.
- The 22 code-defined kinds are discoverable. Company types and classes may narrow
  supported sections/defaults; they cannot invent executable behavior or widen rights.
- One stable voucher, immutable content revisions and stable logical line keys; local
  children carry tenant/company/revision identity. No table per kind or financial year.
- Exact strings on the wire and DECIMAL(19,4) in storage for quantities/amounts.
  Phase 1 stores item identity and quantities; pricing, tax and account allocation
  sections remain explicitly unavailable until their planned batches.
- Configuration is native, typed and versioned. Restrictive inheritance intersects
  allowed sets and tightens requirements/limits. Unknown settings fail validation.
  Custom fields use Identity definitions and never determine financial behavior.
- Posting, stock, statutory and credit-term dates remain separate. Draft financial-year
  selection is derived from signed company calendar facts and is not posting authority.
  Issue numbering is separate from future Accounting/statutory posting numbering.
- Unknown execution outcomes remain pending. Timeout cannot release claims. A definitive
  owner cancellation wins against a delayed command; committed effects require a later
  supported correction. Native owner-protocol races are verified; activated financial and
  stock profile races remain obligations of their later batches.
- Report feeds must identify committed source generation/checkpoint and exact row grain.
  Report projections are reconstructible and never an alternative ledger. D02/D03/D08/
  D09 and later slices of D01/D04-D07/D11/D12 remain gated before dependent activation.

## Baseline

Existing source inspected: Accounting ledger/subledger/fiscal/tax APIs and signed
Identity posting client; platform tenant sessions, idempotency, outbox, service signing,
custom-field validators, field policy and keyset pagination; Identity gateway/company
context; Catalog definition adoption; Audit publisher; Windows service manifest and
generated TypeScript client. Concurrent Catalog and platform constants edits predate
this implementation and must be preserved.

Test commands/results and implementation evidence are appended as verified.

## Verification checkpoint - 2026-10-10

The Phase 1 common foundation is implemented. This record documents the C0 slices of
B01-B08; it does not claim that invoice calculation, actual posting, GST, settlement,
stock movement or financial reports are implemented. C0-C4 release activation is separate.
No production database migration, commit, publish or deployment was performed.

### Batch evidence

| Batch | Delivered evidence and scope |
|---|---|
| B01 | Existing Accounting/Identity/Catalog contracts, tests and generated clients reviewed; concurrent Catalog changes isolated and preserved. Existing journal, balance and settlement APIs remain compatible. |
| B02 | Shared 33 business + 3 platform table manifest, 36 independent one-DDL migrations, scoped composite FKs, exact quantities, immutable revisions/line identity; 22-kind/profile/section registry and disabled effect gates. Initial decision slices recorded in the concrete contracts note. |
| B03 | Shared signed command/result client, three signed owner snapshot APIs, explicit source credentials, immutable request/configuration identities, canonical source payload and generation receipts; D11 export/barrier and D12 close/readiness contracts fixed for subsequent implementations. |
| B04 | Service/config/auth/readiness/gateway, company step-up forwarding, private owner routes, precise audit allowlists, real confirmed broker delivery, source/artifact/execution workers, Windows tooling, OpenAPI/TypeScript transport and local test runner. |
| B05 | Scoped draft aggregate with items, parties, references, attachment metadata and links; optimistic revisions, maker/checker approvals, lifecycle history, typed COMMON/SALES/PURCHASE policy revisions and dated restrictive bindings. |
| B06 | Company type cloning with immutable origin, classes, publication/retirement, effective configuration, both custom entities, all 12 value types on headers and items, typed indexes/claims/sequences, permissions/filter/export denial, labels/help snapshots and rollback-only adoption preview plus atomic apply; explicit compatible, authorized conversion mapping primitive. |
| B07 | Immutable durable producer commands, revision/approval/master/configuration checks, pending-operation fences, Accounting source guard/terminal receipts, cancellation tombstones, signed status reconciliation, committed generation, transactional callback rollback, close/retry/year-boundary tests and local POSTED history. All production effect profiles remain disabled. |
| B08 | Issue numbers by company/series/fiscal year, configuration-scoped series/template defaults, immutable assignments, pinned templates/artifacts, safe large-document storage, status/issue-aware print cache, expiring protected downloads and reprint isolation; common web header/custom/item/quantity/party/reference/class entry and permission-gated workflow/history. |

Implementation locations: `apis/vouchers`, `dbs/vouchers`, the three owner snapshot routes,
Accounting's `voucher_execution` adapter/models and migrations 0109-0110,
`clients/voucher-execution`, `clients/api-client`, console voucher components, and Windows
service/gateway/worker configuration. See [the contracts/table manifest](voucher-phase1-contracts.md)
and [service operation instructions](../apis/vouchers/README.md).

### Verification evidence

- Vouchers native MySQL + RabbitMQ run: **87 passed**. All 36 migrations, column/index/unique/FK
  parity, downgrade/upgrade, tenant/company isolation, concurrent edit/number allocation,
  confirmed audit publication and consumer redelivery were checked in disposable databases.
  Audit consumer persistence in the broker fixture uses SQLite; it is not a native Audit-DB claim.
- Vouchers ordinary suite: **85 passed, 2 explicitly skipped** (native lock and broker cases);
  domain coverage **99.07%**, above the required 90% threshold.
- Accounting native owner/fiscal/source integration: **18 passed**, including the final authority-expiry
  regression and the 110-migration downgrade/upgrade round trip. Native tests cover
  the real owner transaction/receipt boundary, not an enabled GL/stock profile.
- Shared platform suite: **1,032 passed**. Earlier affected Identity regression slice: **32 passed**;
  final Identity owner snapshot/gateway slice: **9 passed**. Catalog owner snapshot: **1 passed**;
  earlier affected Catalog/Accounting compatibility slices: **17/14 passed**.
- Console: earlier full suite **273 passed**; final voucher/page/item/workflow
  slice **12 passed**, including configured issue defaults; proxy slice **26 passed** earlier. Generated-client transport,
  TypeScript checks and OpenAPI generation checks passed.
- Strict mypy: all **46 Vouchers modules**, new Accounting adapter/shared execution client,
  owner snapshot routes and affected Identity customization/context modules passed.
  Ruff checks/format and static Windows worker/env script parsing passed; the service
  manifest JSON and generated OpenAPI/TypeScript clients were validated.

Reproducible commands (from each service/client directory unless noted):

- Vouchers: `python tools/verify_mysql.py` with the isolated broker URL supplied privately;
  `pytest -q --cov=vouchers.domain --cov-report=term-missing`; `mypy src/vouchers`;
  `ruff check src tests tools`; `ruff format --check src tests`;
  `python tools/export_openapi.py --check`.
- Accounting: `python -m tools.verify_mysql --tests tests/test_voucher_execution.py
  tests/test_fiscal_api.py tests/test_voucher_sources.py`; targeted strict mypy and Ruff
  on the new execution adapter/models/tests.
- API client: `node scripts/generate.mjs --service=vouchers --check`, `pnpm exec tsc --noEmit`,
  `node --test tests/vouchers.test.mjs`. Console: `pnpm exec tsc --noEmit` and Vitest on
  `vouchers`, `vouchers-page`, `voucher-items`, `voucher-workflow` test files.
- Repository: PowerShell parser over changed worker/env scripts; service manifest JSON parse;
  scoped whitespace review. Native logs: `.test-vouchers-mysql.log` and
  `.test-voucher-accounting-mysql.log` (local ignored evidence, no secrets printed).

These counts overlap by slice and must not be added into a misleading unique-test total.
The test schemas were created on a separate loopback MySQL instance; the existing MySQL
service/database was not migrated or reset.

### Activation and later obligations

- [ ] C0 release activation: deploy/configure scoped credentials, owner synchronization,
  system role bootstrap, company types/series/templates, gateway/worker runtime and selected
  client delivery. The repository contains no mobile app; shared wire contracts are available,
  but no mobile application or browser deployment is claimed. Live nginx smoke testing is a
  deployment check; this run verifies gateway auth behavior and reviews its routing configuration.
- [ ] B09: implement the agreed complete owner export/barrier, projection and rebuild protocol.
  Current-document export is not a financial feed or a Balance Sheet.
- [ ] B10 onward: implement native financial profile payload/effect executors, current Identity
  first-use/reservation authority and all GL/subledger/period/report acceptance before enabling
  any actual POST/REVERSE profile. The C0 callback fixture proves atomicity/fences, not money logic.
- [ ] B15 onward: native pricing, stacked charges/discounts/tax, free/deal calculation, statutory
  identities and artifacts; they cannot be enabled through arbitrary policy/custom JSON.
- [ ] B20 onward: stock-period, positions/valuation/origin/return/import/repair extensions.
- [ ] Larger-than-1,000-document custom adoption requires an explicit resumable migration;
  C0 rejects it atomically. Object storage/upload verification and rich financial/client forms
  remain separate capabilities, rather than fabricated success on metadata references.

### Simplification and security review

Manual equivalents were performed because `/simplify` and `/security-review` are not
callable tools in this session. Fixed findings include duplicate MySQL FK names; missing
ORM history immutability; omitted defaults; raw history cursors; unsafe adoption indexes/
claims; untyped custom-filter errors; item-field metadata disclosure; retirement blocking
cancellation; source-message identity reuse; overly broad result credentials; artifact
access after voucher-read revocation; stale draft print reuse; missing issue number; TEXT
capacity; case-sensitive index portability; queued-document edit/cancellation races;
terminal operation rewrites; current evidence checks before queueing; request-bound signed
recovery; commit expiry; missing voucher company-step-up forwarding; and public routing of
new Catalog/Accounting owner endpoints. New private endpoints remain credential/scoped even
when accessed directly. No unrelated staged/unstaged work was removed or published.

The tracked whitespace check (allowing Windows CRLF) reports only three pre-existing blank
EOF lines in concurrent Catalog tests. Their files were preserved.


### Operational handoff

Publish/deploy only through the separately authorized repository workflow. The intended
rollout order is shared platform/client contracts, compatible Identity/Catalog/Accounting/
Audit owners and permissions, native Vouchers/Accounting migrations, scoped credentials,
Vouchers API and workers, then gateway and console. Use readiness plus owner/broker probes;
a process starting is insufficient. All actual effect profiles remain disabled.

Native test databases exercised full downgrade/upgrade, but that is not a production rollback
recipe. After real documents exist, preserve revision/number/receipt history and use a reviewed
forward migration; stop admissions/workers before a repair. Unknown execution outcomes must
be reconciled through owner status, never cleared by deleting an operation or retrying under
a new identity. The initial 36-revision Vouchers chain has not been applied to a real company.

Next implementation batch: **B09**, committed financial exports/barriers and the Reports
foundation, followed by B10 Journal/Contra execution. Remaining D-gate and acceptance slices
stay attached to their original batches. No commit or publication reference exists for this
local implementation.
