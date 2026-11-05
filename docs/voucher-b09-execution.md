# B09 execution record

Authorized on 2026-10-10 by the instruction to proceed after Phase 1.
Status: VERIFIED for the B09 export/projection/run foundation. Financial statements,
release activation and deployment remain pending; separate concurrent sequence work has a
known failing test recorded below.

Implementation sequence:

1. Versioned shared financial feed contracts; Accounting transaction journal and frozen
   export manifests, signed company-scoped transport, snapshot/catch-up with rollback tests.
2. Reports database/service: staged immutable generations, atomic complete-bundle ingestion,
   source identity/version dedupe, native journal-line and daily/monthly account facts,
   reconciliation and verified generation cutover. Keep existing frozen readers pinned.
3. Versioned report definitions, asynchronous reconciliation runs, row paging and protected
   artifacts; complete-input authorization and revocation. Statement calculations remain B14.
4. Gateway, workers, generated clients, native migrations, regression tests and review.

D11 implementation decisions: one Accounting transaction produces one durable change bundle;
its monotonically allocated company sequence is protected by the existing company lock and
rolls back with the transaction. Snapshot materialization holds the same lock, records the
last committed sequence, and retains immutable pages. Reports catches up through an explicit
end barrier and switches only a reconciled shadow generation. Metadata changes and reversals
are exported as new facts; old snapshots/generations stay frozen. Initial history is the
owner's retained ledger from books-begin with explicit opening provenance; missing required
setup, classifications or facts blocks readiness rather than inventing them. New statutory,
stock and dimension feeds remain unavailable until their owning batches implement them.

## Implemented scope

- `clients/reporting`: reporting-contract 0.1.0 with 15 native owner grains, schema/content
  hashes, exact decimal wire values and requester-bound signed paged transport. Shared
  signing helpers live in billing-platform 0.29.0; all 11 project locks are synchronized.
- Accounting migrations 0111-0114 and ORM models retain immutable report_change,
  report_change_fact, report_snapshot and report_snapshot_fact. Root transaction capture
  records committed final facts/control totals plus audit; sequence allocation rolls back.
  Private export routes use separate explicit Reports company grants; public nginx denies
  the owner internal prefix. Existing financial_v1 consumers retain their wire contract.
- `apis/reports`, `dbs/reports`: 13 business plus 3 platform tables, migrations 0001-0016.
  Generation/bundle staging, source claims, native journal lines, gross DAY/MONTH account
  totals, definition/run/rows/artifacts and atomic activation share one company scope.
  All amounts remain DECIMAL(19,4); exchange-rate source facts retain native 19,8 precision.
- Resumable source worker materializes an owner snapshot then contiguous changes through
  an explicit end barrier. It validates signatures, schema/scope, hashes/counts, immutable
  posted identities, native references, journal balance and owner control totals before
  switching the active generation. Partial/invalid inputs cannot activate. Rebuilds retain
  old generations/runs; fiscal transitions and subsequent backdated entries require a new
  generation. No dependent mutable carry cache exists in B09.
- API catalogue/field-set, lean generation/run lists, idempotent requests, frozen row paging,
  protected 120-second CSV downloads, live complete-input authorization and revocation.
  The worker and publisher use REPORTS_ configuration. Identity forwards Accounting input
  policies to Reports; Audit accepts the explicit Reports issuer. No cross-service ORM/SQL.
- Windows service/env/gateway/worker registration, OpenAPI and portable Reports client.
  The shared Vouchers owner worker now uses the same tested signing mechanism.

The implementation reuses the shared generation/checkpoint mechanism rather than separate
projection machinery for every report. Source monetary facts and report output are not
editable balances. Source receipt IDs and retained owner facts provide drill-down lineage;
public statement-specific drill-down and calculations remain B14.

## Capability boundary and D11 decisions

B09's only definition is SOURCE_RECONCILIATION. Its COMPLETE status proves the selected
retained owner snapshot reconciles, with NOT_A_FINANCIAL_STATEMENT in the run evidence.
Actual account ledgers, TB, P&L/Income & Expense, Balance Sheet, cash/bank/party statements
and their opening/earnings/netting rules remain B14a-d. Tax, inventory, job-work/WIP and
order registers require their planned producer/report batches. No voucher POST/REVERSE
profile is enabled, and no Reports web/mobile screen is delivered by this foundation.

The 15 grains are account_head, account_group, account, party, financial_setup, fiscal_year,
fiscal_period, fiscal_status_transition, journal, journal_line, opening_batch,
source_document, open_item, allocation and COMMITTED voucher_execution. Draft financial
records are retained as source facts but never contribute to posted GL totals. Party exports
exclude bank details and tax identifiers. Line descriptions and exact native rates are retained.

Classification is frozen as known to a generation; missing pre-baseline label history is
not fabricated. Monetary history coverage is RETAINED_LEDGER from books-begin, with explicit
native opening identities. It does not certify complete imported YTD or resolve the future
B14 opening-versus-movement/earnings bridge. Missing setup/required references block readiness.
The scope/permission hash describes the complete owner grant, while each run separately pins
and rechecks its human actor's disclosure authority. Conditional read denies conservatively
block the complete-company diagnostic instead of creating misleading partial totals.

Initial supported bounds: 100,000 facts per snapshot/generation; at most 200 facts and
1 MiB per transport response; 1,000 change bundles per worker poll before resuming next poll.
Snapshot materialization holds the owner company fence, so B45 must measure write latency
and larger-volume ingestion before increasing these limits. Rebuilds create new generations;
there is no in-place repair API or automatic history deletion. Small diagnostic CSVs are
stored in the Reports database; large exports/object storage and additional formats remain
future work. Controlled direct SQL maintenance that bypasses Accounting ORM capture needs
an explicit rebaseline; ordinary APIs stay within the company-fenced commit contract.

## Verification evidence

Executed locally on 2026-10-10:

| Check | Result |
|---|---|
| Reports final native MySQL + live RabbitMQ suite | 35 passed; 16 revisions upgrade/downgrade/upgrade, model/index/unique/scoped-FK parity and DECIMAL scale passed |
| Reports ordinary full suite | 34 passed, one broker-only skip; broker case separately passed natively |
| Reports domain coverage | 98.84%, above the 90% floor |
| Accounting native financial regression slice | 32 passed: exports, fiscal lifecycle, journals, openings, allocations, execution receipts, native commit/snapshot race; 114-revision migration round trip passed |
| Accounting final export regression after wire-description addition | Ordinary feed: 3 passed, one native-only skip. Native current-workspace slice: 9 passed; one separate concurrent sequence-allocation test failed (see below). The unchanged migration chain already passed its full round trip above. |
| Shared platform full suite | 1,034 passed; 97.97% coverage, signing helper 100% |
| Vouchers owner transport compatibility | 2 passed; strict typing/lint passed |
| Identity Reports gateway scope | 9 passed |
| Portable clients | TypeScript typecheck and Reports/Vouchers retry-contract tests passed (2 tests); Reports/Identity/Vouchers generation freshness passed |
| Static checks | Reports 23 source modules, shared contract 3 modules, Accounting export 3 modules, shared signing/outbox and Vouchers worker strict typing; targeted Ruff passed |
| Operational files | PowerShell parser and JSON validation passed; nginx Reports/company-step-up/private-prefix wiring reviewed |

Useful reproduction: Reports `tools/verify_mysql.py` (with loopback REPORTS_TEST_BROKER_URL
for the broker case); Accounting `python -m tools.verify_mysql --tests
tests/test_reporting_feed.py tests/test_fiscal_api.py tests/test_ledger_api.py
tests/test_openings_sources.py tests/test_allocations.py tests/test_voucher_execution.py`.
The runners create/drop only validated disposable company-independent test schemas.
Tests cover transaction/savepoint rollback, missing/duplicate/conflicting pages, interrupted
signed transfer/resume, immutable committed amounts, failed generation retaining prior active
state, source coverage, cross-tenant tables, company/object access, read denies, revocation,
idempotency, CSV escaping, zero-transaction-amount FX lines and signed broker redelivery dedupe.

## Review and handoff

Manual security/simplification review used because `/simplify` and `/security-review` are
not callable session tools. Findings corrected: exact FX component semantics, owner response
byte bounds, immutable generation/run identities and terminal evidence, committed identity
changes/disappearance, complete-input period permission, lean SQL list projections, publisher
REPORTS_ environment prefix, and shared request-bound signing duplication. Publisher-prefix
and FX regressions were first reproduced by failing tests. No unresolved B09 security finding
was identified within the supported limits; this is not a statutory/report activation review.

During final checks, separate concurrent Accounting sequence edits introduced an import from
billing_platform.db.types that prevented service startup. The feed test reproduced the error;
a one-line import correction uses billing_platform.ids.uuid7. That separate sequence feature
was preserved and is not included in B09's implementation/acceptance claims. Its newly added
`test_document_sequence_allocation_runtime` fails with HTTP 500: `allocate_sequence` reads
`current.tenant_id` and `current.user_id`, whereas Access has `actor` and `context`. The final
Accounting command therefore exited nonzero (9 passed, 1 failed); this is not reported as an
all-green workspace. The sequence feature still needs its own transaction, authorization,
idempotency, audit, numbering-contract and concurrency review before its B10 acceptance. Concurrent
Catalog/other work was also preserved. The user stopped parallel editing for this final pass.

No real-company migration, service deployment, live gateway acceptance, commit or publication
was performed. Native nginx is absent in this workspace, so gateway checks are static plus
Identity route-scope tests; live gateway activation remains a release gate. Temporary native
verification infrastructure is stopped after checks. Normal rollout order is shared contract,
Accounting 0111-0114 and private owner credentials, Reports 0001-0016 and its private credentials,
Audit issuer/broker grants, API/workers, then gateway. Stop admissions/workers for repair;
after real history exists, use reviewed forward repairs, never delete receipts or frozen runs.

Next batch: B10 Journal/Contra. B14 remains responsible for financial report calculations;
B09 resolves only the export/projection/run slice of D11. C0-C4 activations stay unchecked.
