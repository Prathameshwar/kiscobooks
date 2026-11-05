# RF3 source generations — implementation record

Decision 2026-10-29: Accounting report lineage inherits the generation of its
preceding sealed feed manifest (initial generation 1). The mutable Accounting
setup/concurrency counter is not report lineage: non-source administration actions
can advance it without a committed report bundle. Snapshots and later changes must
retain the same lineage at the source barrier. Existing sealed receipts remain
unchanged; Reports still compares generation, schema, tenant/company scope,
permissions and exact controls before publishing. A quarantined source is replaced
only by a newly requested verified FRESH generation, never edited into readiness.

Implementation is complete within the user's revised API/database scope. Default admission
limits remain unchanged. Load/soak gates are excluded from delivery; earlier measurements
below are historical evidence. Both final reviews and current functional verification are
recorded in [execution.md](execution.md).

## Owner read view

Accounting v2 admits a durable snapshot build and returns readiness separately from pages.
A separate worker claims at most one build per company, establishes the first consistent
read in a dedicated REPEATABLE READ session while holding the existing commit fence in a
second session, then releases that fence. The ordinary engine stays READ COMMITTED.
Pages and controls come from the same read view. A failed or expired attempt restarts a
new read view; its old pages cannot become visible in the replacement attempt.

Each immutable owner batch has at most 200 facts and 900,000 canonical bytes. The completed
manifest publishes only after counts and checksum reconcile. The default source bound is
100,000 facts and the read-view time budget is 900 seconds; deployment settings can change
these only after capacity verification. Retained snapshots do not expire automatically.

Native evidence: nine source protocol tests passed, including the original source feed.
A concurrent write completes while the new read view remains open; its sequence and values
remain absent from that older view. The new complete snapshot matches the legacy source
snapshot's counts, checksum and controls. Revisions 0151–0152 preserve the old snapshot API.

The MVCC isolation behavior is documented by [MySQL](https://dev.mysql.com/doc/refman/8.0/en/innodb-consistent-read.html)
and the dedicated engine isolation option by [SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html).

## Reports storage and verification

Revisions 0021–0024 add epochs, immutable source cuts, versioned facts and durable source
requests. Validity intervals pin each cut to a sequence. A refresh appends changes and closes
prior intervals in the future of every published cut. Canonical financial payloads never
change. Native relation/date/account/currency/Decimal columns support guarded query plans;
JSON retains the complete original evidence. Tombstones are SQL NULL, not JSON `null`.

Staging validates bounded pages, duplicate identities, immutable financial payloads, sequence,
scope and permission hashes. Completion streams receipt verification before advancing the
epoch. Per-record checks are shared with the legacy reference engine. Native grouped journal
totals, owner counts and controls are verified, and invoice component verification operates
in bounded components. A separate native aggregate checks credit-note entitlement across
component boundaries. Global immutable claims are compared before publication.

V2 source admission offers FRESH, REFRESH and COMPACT, with an explicit verified base for
the latter two. Source copies yield after ten pages and resume from their durable ordinal.
The barrier manifest is pinned together with its sequence; final controls and change receipts
must agree with it. Compaction retains the old epoch/cuts, creates a new base and preserves
the original owner manifest separately from its internal materialization receipt. It does
not delete evidence or modify previously completed reports.

The end-to-end signed transport test admits a fresh generation, waits for source readiness,
publishes it, refreshes metadata and compacts the refreshed cut. All three generations remain
readable at their original values. Wrong-company access, missing grants, idempotency and
strict inputs are tested. A failing barrier-control regression was added before fixing the
missing comparison.

## Current measurements

These are development probes, not production SLO acceptance. The 10,000-transaction run
overlapped regression checks on the same local MySQL server.

| Synthetic business transactions | GL lines | Source facts | Staging SQL | Stage | Receipt verification | Reconciliation | Peak process RSS |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 200 | 333 | 12 | 0.412 s | 0.130 s | 0.493 s | 83.2 MiB |
| 10,000 | 20,000 | 30,033 | 906 | 43.586 s | 8.353 s | 14.605 s | 87.1 MiB |

Preassigned UUIDs let the ORM batch inserts on MySQL, preserving its normal flush guards.
The corresponding legacy baseline used 337 statements just for staging 333 facts, plus
2,461 statements for application/activation. No general unfiltered write bypass was added.

The first million-line probe exposed a quadratic duplicate-lookup path: its missing epoch
predicate prevented a selective identity lookup. At about 173,000 stored facts, the same
200-identity query took 2.318 s before the fix and 0.00753 s after it. Native EXPLAIN changed
from a bundle scan (86,387 estimated rows) to the source identity index (200 estimated rows).
That interrupted run is retained as failed performance evidence, not a capacity pass; its
exact disposable schema was removed after its benchmark processes were stopped.

The corrected early one-million-GL-line run (500,000 transactions; 1,500,033 facts)
completed staging in 1,762.386 s, receipt verification in 606.840 s and reconciliation in
1,453.780 s, with 87.95 MiB peak RSS. It predates buffered pages and the benchmark-helper
flush fix; it excludes immutable claim publication and does not prove READY-state capacity.
The separate `--publish` million-line run remains in progress. A 20,000-line full-publication
probe completed staging in 41.384 s, receipt in 14.213 s and publication in 73.021 s, reached
READY, and used 92.38 MiB peak RSS. Source hashes are recorded at process start.

The completed million-line owner probe copied 1,500,121 facts in 1,570.268 s. Its initial
read-view fence lasted 33.956 ms. Across 20 create/post samples per phase, baseline median /
p95 were 0.77475 / 1.05036 s and during-copy median / p95 were 0.91425 / 1.05010 s. Median
latency increased about 18%; the nearly unchanged p95 is not isolated SLO acceptance.
Concurrent read-view barriers had p95 32.184 ms. The run used an explicit 3,600-second budget;
the default 900-second snapshot budget is insufficient for this measured fixture.

The newer 100-sample owner probe reached the existing 120-writes/minute API guard and was
aborted without publishing capacity results. The corrected run spaces create/post pairs by at least
1.1 seconds outside measured latency, preserving the real application rate guard. A pacing
regression verifies the request count across sliding minute windows. The corrected million-line run completed 1,500,361 facts in 1,298.780 s with 124.0 MiB
snapshot-subprocess peak RSS. Baseline create/post median / p95 were 0.78956 / 1.09109 s;
during-copy median / p95 were 0.61304 / 0.94146 s across 100 samples each. This run observed
no p95 increase; scheduling/cache differences and concurrent development load prevent a
production SLO inference. Initial fence time was 27.569 ms; 100 concurrent barriers had
p95 28.148 ms and maximum 40.391 ms. Neither benchmark includes
mixed companies, network latency, report queries or exports. They overlap local test work.

Commands and logs are in `.test_artifacts/reports-framework/rf3-*`; test tools refuse existing
or non-loopback database schemas. The latest full native Reports run passed 230 tests with
two broker skips and verified migration/model parity and the downgrade/upgrade round trip.
The latest native owner snapshot/control suite passes 20 tests and the migration round trip.
Large Windows asyncmy streaming reads reproduced a protocol buffer failure, so owner and
consumer reads now use buffered keyset pages. A bounded metadata query measures payload
width before requesting JSON records; consumer widths are immutable and checked at insert.
Owner pages admit at most 200 rows/4 MiB native payload; consumer pages at most 200 rows/1 MiB;
reference components at most 20,000 records/16 MiB. Oversized components fail explicitly.
Compaction resumes across changed byte-page boundaries without repeating or skipping facts.

A restricted append verifier is covered by native tests: only complete new ordinary journals, their
lines and source documents may reuse a verified parent. Updates/deletions or other families
continue through full verification. Counts and exact native journal totals still reconcile
with owner controls. Source-interval indexes and claim publication follow the same scope.
The native migration/parity run includes these indexes. Full-rebuild parity, unbalanced
new journals and metadata-update fallback are covered. Polling workers now recover from
dependency errors while preserving cancellation and avoiding private connection details in logs.

The owner benchmark seeds synthetic history only in a random disposable schema, then times
normal guarded create/post API requests before and during a snapshot. Historical cloning
is fixture preparation, not posting-validation evidence; Identity reservation is a boundary
test double. The initial small probe shared one process/event loop between API requests and
copy; the benchmark now uses a separate hidden snapshot subprocess. Its initial million-line
owner attempt failed before starting the snapshot: ordinary journal admission exceeded the
existing ten-second command budget while the legacy feed recomputed company-wide controls.
This is failed capacity evidence, not a passing result.

The owner feed now captures each touched identity's original contribution before its first
flush, folds final committed values into preceding controls under the existing company
fence, and retains the baseline across savepoint rollbacks. Posted journal totals provide
the delta; native snapshots still independently sum posted lines and count all owner rows.
A regression test failed before this change and now compares deltas with that independent
scan. Targeted money, invoice, rollback and native suites pass; the full Accounting domain-coverage suite is still running. Synthetic history
seeding explicitly anchors its controls before normal guarded create/post requests begin.
The larger-sample separate-worker million-line run completed while overlapping consumer work;
isolated capacity acceptance remains outstanding.

The separate-process buffered owner probe with 10,000 transactions/20,000 GL lines completed
30,076 source facts in 46.547 s. The initial view fence held for 44.877 ms. Five baseline
create/post samples had p95 1.00793 s; five during-copy samples had p95 1.10737 s (9.87% increase).
Five concurrent read-view barriers had p95 44.728 ms. This sample is too small for SLO
acceptance and overlapped other development work. The completed million-line result is recorded above.

Failure testing also exposed an expired ORM setup object in snapshot failure auditing.
The regression failed with DetachedInstanceError before the fix; the failure transaction
now loads its own live setup and publishes FAILED without exposing incomplete pages.
The corrected native regression passes.

Verification is persisted once before immutable-claim publication. An interrupted publisher
can reuse this evidence while the generation remains BUILDING and unreadable by report runs.
The same transaction emits a verified audit event; its missing-event regression failed before
the correction. Bounded source/publication/refresh/compaction regressions pass (23 tests), and
strict mypy checks all 55 Reports source modules. The newest native suite passes all 230 tests, with two broker skips and successful migration/model parity and downgrade/upgrade.

`tools.framework_version_benchmark --publish` additionally measures all immutable claim
writes and asserts the final READY state. Earlier versioned measurements exclude that work;
their results must not be presented as full publication capacity. The older million-line
run also predates buffered paging and a benchmark-helper flush correction, as recorded by
its source hashes. It remains staging/reconciliation evidence only.

## Development operation

Accounting: set `ACCOUNTING_REPORT_SNAPSHOT_ENABLED=true` with the existing Reports service
credentials, and run `python -m accounting.tasks.reporting_snapshot` in a separate process.
Reports: configure owner scopes and `REPORTS_SOURCE_VERSIONS_ENABLED=true`, then run
`python -m reports.tasks.source_worker --env-file <private-file>`. Default source capacity is
still 100,000 facts. These switches are off by default; this work does not activate production.

## Recovery, retained evidence and compatibility fixes

- ORM guards read the prior persisted value under the tenant/company guard when an attribute
  is expired. Expired state cannot bypass cutoff, version, attempt or completed-snapshot
  immutability. The shared history helper, independent polling and process-memory mechanism
  are in billing-platform 0.33.0; all root consumer locks are synchronized. The full shared
  suite passed 1,065 tests; resource-helper additions passed targeted checks, with accumulated
  shared coverage 97.91%.
- Independent bounded company polling prevents one long reconciliation from delaying future
  polls for every other company. Owner and consumer defaults allow four concurrent scopes.
- Consumer refresh waits for recoverable interrupted owner attempts. Permanent capacity or
  verification failures do not retry. An expired third owner attempt becomes FAILED rather
  than remaining RUNNING indefinitely. The latest native recovery suite passes seven tests.
- Compaction resumes by entity/source key after its durable output ordinal; it no longer
  rereads all copied facts after each ten-page yield. A regression rejects repeated reads.
- V1 can read bounded versioned generations through the shared source loader. Legacy old-schema
  admission is preserved; new calculations fail closed while frozen old outputs remain usable.
- New native projection columns are derived from retained JSON. Explicit disagreements in
  journal/account IDs, amount or status are rejected before insertion. Four regressions failed
  before the guard and pass in the full native suite. No schema change was needed for this fix.

## Completed million-line full-publication probe

`rf3-full-publication-million.json` completed successfully on 2026-10-14 with
500,000 synthetic transactions, 1,000,000 GL lines and 1,500,033 owner facts. It asserts READY
after all verification and immutable-claim publication:

| Stage | Seconds | SQL statements |
|---|---:|---:|
| Synthetic fixture generation | 320.244 | n/a |
| Fact staging | 2,067.178 | 45,006 |
| Receipt verification | 539.554 | 15,012 |
| Financial verification and claim publication | 3,329.126 | 147,639 |

The process peaked at 191,979,520 bytes (183.09 MiB). This establishes bounded-memory
full initial publication at the requested line count for the captured RF3 source hashes.
The run predates RF4 posted-line projections and excludes HTTP, the broker and owner posting.
It overlapped other local work; its roughly 99-minute consumer build is development capacity
evidence, not a source-freshness or query SLO result. The 30-second incremental freshness gate,
current projection publication cost and mixed-load acceptance remain outstanding. No default
admission cap or feature flag was raised by this result.

## 2026-10-15 verification and performance follow-up

The full Accounting coverage run reached 95.60% domain coverage, with 728 passing, 17 skipped
and three failures. The new snapshot audit events were missing from the audit-contract exporter;
that mapping and generated contract are fixed. The two other failures passed in a focused
42-test rerun; a date-sensitive withholding fixture now chooses its future date at test execution
so collection across midnight cannot make it historical. The full rerun then passed 734 tests,
with 18 infrastructure skips. Production command budgets were not relaxed for testing.

The restricted append verifier now supports complete new invoice, open-item, allocation and
execution components as well as new GL journals. It validates every new record, reconciles the
affected invoices and checks cumulative returns against original supply entitlements including
older sibling notes. Existing updates/deletions and unsupported families retain full verification.
Native regressions include a new note that is individually valid but exceeds entitlement when
combined with a retained older note. Eight targeted native tests and migration round trips pass.
This expands the eligible refresh profile; it does not yet establish the 50-changes/s freshness SLO.
# Current posted/daily projection publication evidence (2026-10-15)

The full current pipeline published a READY source generation with 1,000,000 GL lines,
1,500,033 source facts and the posted-line/daily-balance projections. Peak own-process RSS
was 191,127,552 bytes. Synthetic source construction took 253.50 seconds, guarded staging
1,446.01 seconds (45,006 statements), receipt verification 600.76 seconds (15,012 statements),
and verification/claims/projections/publication 4,542.99 seconds (172,699 statements).
Total cold-build time was about 114 minutes. Memory is bounded; cold-build speed remains
a performance limitation. This is one consumer worker under overlapping development load,
excluding HTTP/broker and owner posting impact. Sustained incremental freshness remains a
separate gate. Evidence: `rf4-full-publication-million-frozen.json`, including source hashes.
