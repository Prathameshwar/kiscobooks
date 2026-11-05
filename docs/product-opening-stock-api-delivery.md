# Product opening stock API delivery checklist

Started 2026-10-28. User authorized all nine phases and two final reviews with
fixes, uninterrupted. UI, commit/publication and normal posting activation are
outside this task. Preserve concurrent work.

- [x] 1. Baseline, contracts, owner/schema manifest and readiness policy.
- [x] 2. Typed draft quantity/rate/value calculation and validation APIs.
- [x] 3. Unit conversion evidence, historical cohorts, batch/serial allocations.
- [x] 4. Reviewed native posting, combined/linked GL and exact recovery.
- [x] 5. Opening cutover manifest, reconciliation and finalization fence.
- [x] 6. Immutable correction and recovery with dependency guards.
- [x] 7. Durable bounded import, review, native draft creation and resumable chunks.
- [x] 8. Authorized opening status/history/reconciliation reads and exports.
- [x] 9. Native integration, schema/model/scripts/contracts/SDK synchronization,
  coverage, type/lint and migration/release rehearsal.
- [x] Review 1: arithmetic, security, concurrency and rollback; fix and recheck.
- [x] Review 2: complete API flows, recovery, migrations and release claims;
  fix and recheck.

## Agreed scope and decisions

The user's instruction to implement the plan accepts its recommendations: books-
begin cutover, warehouse FIFO/MVA cost pools, explicit unknown historical age,
configured/evidenced zero cost, company-owned usable goods, existing approval
separation, explicit combined versus linked GL and reversal/replacement only
before dependencies. Unsupported custody/disposition, later per-product cutover,
retroactive recosting and UI remain excluded as specified in the plan. Reject
unsupported facts explicitly; never substitute zero or drop import rows.

## Design / migration manifest

Catalog continues to own published units/conversions and source fences. Vouchers
owns opening drafts and durable import metadata; Accounting owns cutover state,
physical/financial effects and manifest reconciliation. Extend the common signed
execution contract, existing revision children and source proof; do not introduce
a second balance or posting authority. Exact schema/migration details are recorded
as the implementation contracts are inspected. Every new table/column is paired
with a reviewed single-DDL revision and native parity rehearsal.

## Verification evidence

- Vouchers baseline capture/retirement: 11 passed. After typed opening capture,
  the seven capture checks passed again.
- Accounting SQLite baseline: 30 passed, three existing FIFO residual
  reconciliation assertions failed in serial/transit scenarios. These must be
  checked on native MySQL before changing exact ledger arithmetic; integration
  acceptance uses the real database, as required by repository instructions.
- New pure opening arithmetic and existing costing: 28 passed, including explicit
  RATE/VALUE, quantity grids, exact rational conversions and rejection of invalid
  or missing values. Public opening-control tests and strict types are running.
- Implementation in progress: shared typed opening evidence, signed Catalog unit
  revision proofs, historic receipt dates, same-position cohorts, immutable
  Vouchers capture, durable Accounting manifest/claims, calculation/readiness/
  registration/finalization APIs and native posting fence. None of this is yet
  claimed complete or rolled out locally.
- Current migration manifest: Vouchers 0102 typed opening JSON on existing detail;
  0103 opaque cutover ID on existing context. Accounting 0213 cutover control;
  0214 immutable cohort claims. Each revision has one DDL and refuses destructive
  downgrade when evidence exists. Native migration/parity rehearsal remains due.

Continuation evidence:
- Accounting native MySQL: 58 passed. This includes all three ledger scenarios
  that fail under SQLite; no ledger arithmetic was weakened for SQLite. Accounting
  0213-0215 upgrade/downgrade/re-upgrade and full native model parity passed.
- Public opening-controller checks: three passed after fixing a Decimal default
  serialization defect exposed by the missing-cohort test.
- Opening import checks: six passed, covering two-chunk progress, no effects from
  dry-run, idempotent native draft creation, duplicate content under a different
  source key, protected read/export, version conflicts, cancellation and invalid
  decimal inputs. Import completion explicitly means drafts created; it never
  claims physical stock posting or financial approval.
- Additional implementation: manifest revisions/reopen/replacement and reviewed
  legacy adoption; explicit unknown-age provenance on receipt origins (0216);
  bounded JSON/CSV/TSV/XLSX imports, immutable job/cohort receipts (Vouchers
  0104-0105), authenticated expiring report tickets. These additions still need
  final native integration, migration synchronization and the two final reviews.

No live stock effects or admission flags have been changed.

## Final verification, 2026-10-28

Implementation and both reviews are complete. The usage/permission/retention
contract is [product-opening-stock-api.md](product-opening-stock-api.md).

- Accounting native MySQL: 60 checks passed with 94.44% changed opening-domain
  branch coverage (90% floor); subsequent review flow run: 31 passed; final GL and
  legacy run: four passed. Runs overlap and are not claimed as 95 unique tests.
  Earlier native ledger coverage also verified the three SQLite-only residual
  discrepancies without weakening exact arithmetic.
- The native flows cover FIFO/MVA cohorts, combined and linked GL, posted replay
  with admission disabled, terminal delivery, finalization, reopening, immutable
  reversal/replacement, original/unknown age, prepared batch/serial/both profiles,
  expiry refusal, normal issues consuming imported costs, dependency blockers,
  competing finalizers and competing cohort writers. Financial inventory opening
  edits also respect the cutover fence; both valued and zero-value terminal
  confirmations block period closing until delivery.
- Vouchers native harness: 38 passed, including bounded files, native capture,
  dry-run rollback, chunk checkpoints/replay and failure after native allocation
  but before checkpoint. Completed drafts survive; only the failed chunk resumes.
  The final 23 file-mapping checks passed with 94.59% statement/branch coverage,
  including an actual oversized native JSON document rejected before DB work.
- Shared execution contracts: 32 passed, including backward-compatible wire
  hashes and strongly typed serialization schemas. Catalog unit/fence checks:
  four passed. Identity source checks: three passed; role/seed checks: nine passed.
  Audit source checks: ten passed; production emitter/consumer integration: two
  passed. Relevant strict mypy and Ruff checks passed.
- Generated Accounting/Vouchers OpenAPI, Identity field contracts, Accounting
  audit matrix and API client 0.2.39 are synchronized. Execution client 0.3.6 and
  all three consuming service locks agree. SDK type checks/eight transport tests,
  Console type checks and 25 focused UI compatibility tests passed. A pre-existing
  unsupported `exact` option on a role-based test query was removed; screen
  behavior was unchanged.
- Bounded rehearsal: 1,000 allocation rows / 10,000 distinct serials produced ten
  native chunks, 769,292 CSV bytes and 1,372,077 native JSON bytes. Parsing took
  0.209s; manifest validation took 0.093s on this workstation. This measures
  mapping/validation, not a claim of maximum physical-posting throughput.
- Disposable MySQL upgrade/downgrade/re-upgrade and full model parity passed for
  Accounting 0213-0216 and Vouchers 0102-0105. Local databases are verified at
  0216/0105 with full model parity and unchanged native effect counts. A nullable
  age flag preserves legacy inference; populated provenance blocks destructive
  downgrade. No fabricated history was backfilled.
- Affected APIs and configured source/execution/terminal-delivery workers were
  refreshed through owned-process launchers. All eight API readiness probes
  return 200. Real Authentik login as tenant3 verified opening readiness,
  capabilities and authorized import history through the gateway.

## Review findings and fixes

Review 1 (manual arithmetic/security/concurrency equivalent; `/simplify` and
`/security-review` commands are unavailable in this tool session): fixed a Decimal
default serialization defect, an oversized limiter key, zero declaration's
accidental period-post requirement, a wrong history field set, contributing-field
denies, an oversized JSON error path, immutable revision access and legacy receipt
wire comparison. Added actor/version-bound exports and retained correction reasons.

Review 2: fixed FIFO tie order across separate chunks, incomplete confirmation
fences for journal-backed stock, the matching period-close gap, financial GL
opening edits bypassing a finalized physical cutover, legacy adoption reopening
as another opening, rollback of transaction-local draft bookkeeping, and schema
generation weakening typed output. Removed the obsolete per-position opening
probe now superseded by immutable cohort claims under the company lock. Rechecked
native flows and schema parity after fixes.

Live authorization also exposed missing draft-import rights in Stock Operator.
The system role and seed now include existing `vouchers.import.read/manage/commit`;
the dry run/apply added exactly three permissions, with no role, assignment or
unrelated permission changes. The scoped QA actor cache was refreshed. Future
company creation uses the same synchronized role catalogue. Financial management,
voucher approval and period closing/reopening remain separate authorities.

The existing QA company's read-only readiness correctly reports legacy history
requiring controller review and missing account mapping at books begin. Its prior
data was not adopted or restated automatically. Normal stock admission remains
disabled; UI, full Reports source-cut activation, commit/publication and the next
task remain outside this delivery.
