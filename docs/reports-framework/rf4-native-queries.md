# RF4 native queries — implementation record

Native handlers for all 27 registered definitions are implemented and checked against their
reference behavior. Admission remains disabled by default. The user excluded remaining
load/soak work; historical measurements below do not establish production capacity.
Current functional checks and both final reviews are recorded in [execution.md](execution.md).

The first slice covers account/party/cash/bank ledgers and day books. It pins an immutable
source cut, uses indexed journal-date and line-sequence keys, and computes exact running
balances. Opening rows precede entries; comparative periods retain their separate order.
Interactive pages use bounded SQL prefix aggregates. Sequential exports carry bounded
account balances so they do not recompute every preceding line for each page.

Journal lineage is a derived, immutable link from an execution fact version to each JOURNAL
effect. The source version supplies scope and validity; replacing it leaves older cuts and
links intact. This avoids scanning execution JSON for each report page. The link is derived
from the retained payload in the same transaction, never supplied by the report requester.

All query aliases retain session-level tenant protection and explicit company/epoch/cut
predicates. Metadata counts/byte evidence are read before loading source JSON. No offsets,
unfiltered SQL bypasses, live Accounting reads or unbounded result arrays are permitted.

Subsequent slices cover native statement/summary aggregates and bounded invoice, open-item
and bank components. Existing pure calculators remain the reference for every family.


## Native ledger slice

The v2 worker can pin a ledger query without writing report-result batches. Row count and
content hash remain unknown until an export enumerates the result; the run has a logical
identity, exact source cut and packaged query implementation fingerprint. Changed or missing
query code fails closed. Native admission uses the SHORT lane; the flag
`REPORTS_NATIVE_QUERIES_ENABLED` defaults to false. Disabling admission preserves reads of
already completed compatible plans. Other families still use their bounded reference plans.

Revisions 0025?0029 add generated line order, a supporting index, journal-effect links,
epoch query capability and the immutable posted-line projection. Existing epochs remain
reference-only; a fresh generation or compaction supplies new query projections. The
posted projection is created from verified source versions, checked against the selected
cut, reconciled by row counts and exact base-currency totals, and published with source
readiness. A backdated append leaves older cut balances unchanged. All revisions have one
DDL statement and a working downgrade; native migration/model parity and round trips pass.

The first 20,000-line joined query probe missed its target: 20 pages had median 1.361 s,
p95 1.558 s and maximum 3.350 s. A separate profiler showed that aggregate joins and
cross-table sorting dominated DB time. The posted-line projection removes both joins from
selection and prefix aggregation. Its 20,000-line probe has median 0.229 s, p95 0.265 s and
maximum 0.307 s across 20 pages; dimension loading took 0.120 s and peak RSS was 95.0 MiB.
These are local query measurements, excluding HTTP authorization/serialization and mixed-load
acceptance. The accompanying full publication took 77.149 s for 30,033 source facts.

Native regressions pass 241 tests with two broker skips. Ledger parity covers all five codes,
comparative periods, tiny page boundaries, sequential balance carry, filters, lineage, scope,
revocation, pinned API results and retained-cut behavior after backdated additions. Ruff and
strict mypy pass across 61 modules. The million-line shallow/deep query benchmark is running.
Its synthetic Core fixture deliberately excludes large receipt/claim construction; it checks
known expected running balances on every sampled page and cannot prove ingest capacity.

## Statement, invoice and daily-total work (2026-10-15)

Native plans now include the five financial statement/summary definitions, the eight invoice
registers and source reconciliation. Statement calculations reuse the reference financial rules
on native grouped inputs; invoice plans load bounded document components, preserving separate
component, tax, settlement and GL grains. Source reconciliation returns the verified cut evidence.
The combined family suite passed 29 native tests before adding the daily-total optimization.

MySQL CASE expressions returned date strings where SQLite returned dates. The native parity
suite reproduced the problem; normalizing at the DB boundary fixed all seven failures. The
subsequent statement suite, model parity and migration round trips passed.

The initial million-line query fixture failed the page target: shallow/deep p95 values were
6.080 s, 25.276 s and 19.206 s. EXPLAIN showed tuple cursor comparisons discarding prior index
records. A native handler-read regression failed (nine preceding records read for one deep row)
and passed after using the shared scalar-range seek mechanism. Historical balance sums still
cost seconds, so revision 0030 adds exact immutable daily deltas, including opening effects,
transaction/base currency, debit/credit and original line counts. Both projection types must
reconcile before READY. Query projection version is now 4; older epochs require a rebuild.

The new million-line query-only fixture checks every sampled running balance and records:

| Position | Samples | Median | p95 | Maximum |
|---|---:|---:|---:|---:|
| First page | 20 | 102.84 ms | 159.28 ms | 333.64 ms |
| Middle cursor | 20 | 102.03 ms | 168.44 ms | 234.05 ms |
| Deep cursor | 20 | 104.95 ms | 149.17 ms | 227.86 ms |

Peak process RSS was 107,118,592 bytes (102.16 MiB). This is `rf4-query-million-daily.json`:
synthetic Core cloning in a disposable schema, excluding HTTP/authorization/serialization,
large receipt/claim construction, and mixed-load SLO acceptance. It overlapped development
work and is not an isolated production benchmark. Flags and default source limits remain off/unchanged.

The separate current-projection publication benchmark was invalidated by concurrent source
edits and late Python imports. Its failure is retained as `rf4-full-publication-million.log`.
The incremental verifier is now loaded with the publisher at process startup; a fresh
`rf4-full-publication-million-frozen` run subsequently completed, as recorded in RF3.
Remaining load/capacity gates were removed from delivery by the user. Retention checks and
both final whole-framework review/fix passes are recorded in execution.md and reviews.md.
