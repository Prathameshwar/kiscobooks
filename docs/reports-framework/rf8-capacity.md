# RF8: capacity and recovery evidence

Status: CLOSED AS HISTORICAL EVIDENCE; user excluded load testing on 2026-10-15. No further
load/capacity/soak tests will run for this delivery. These are development measurements,
not production capacity approval. The in-progress million-line database/export run was cancelled.
Host: Windows, 22 logical CPUs, approximately 68 GB RAM; runs overlap other development work.

| Boundary | Fixture | Observed result |
|---|---|---|
| Guarded native MySQL ledger query | 10 million posted lines, 20 samples per cursor | p95 first 119.69 ms, middle 148.86 ms, deep 127.67 ms |
| Native financial query | Same fixture, 20 samples/report | p95 summary 143.49 ms; BS 9.10 ms, income/expense 7.61 ms, P&L 8.11 ms, TB 8.16 ms |
| Frozen rows to durable CSV | 10 million rows × 20 columns | 693.91 s; peak 73,359,360 B; output 1,902,400,176 B; all rows verified |
| Frozen rows to durable XLSX | 10 million rows × 20 columns | 2,874.12 s; peak 74,498,048 B; output 565,374,173 B; 10 sheets; all rows/cells verified |
| Frozen rows to durable CSV | 1 million rows × 20 columns | 69.58 s; peak 72,671,232 B |
| Frozen rows to durable XLSX | 1 million rows × 20 columns | 379.42 s; peak 73,932,800 B; proposed 300 s target unmet |
| Incremental consumer | 3,000 changes produced at 50/s, 2 s production poll | freshness p95 24.109 s, max 27.109 s; peak 140,316,672 B; 6,002 posted lines verified |
| HTML presentation | 20,000 rows × 10 columns | 6.25 s; all 200,000 values verified |
| Isolated PDF presentation | 5,000 rows × 4 columns | 30.03 s; 157 pages; child peak 178,286,592 B; every ID/amount verified |

The large query fixture is created only in a randomly named disposable loopback schema. Its
initial source is verified, then Core-cloned synthetic history is added to measure query capacity.
It has two accounts over two fiscal years; all financial outputs equal an independent weighted
730-day reference fixture. It does not prove production ingestion, high-cardinality dimensions,
HTTP/auth latency or concurrent tenant throughput. Schema cleanup completed.

The ten-million XLSX stress run started before the final RF6 styling changes. Its recorded source
hash identifies the measured implementation; it must not be described as a timing for the final
styled workbook. A styled million-row check completed before the scope change: 495.07 s,
75,108,352 B peak RSS, with all rows verified (`rf7-styled-xlsx-million.log`). The proposed
300-second target was not met. The large database-to-artifact check was cancelled at the
user's request; its verified disposable synthetic schema was removed.
Files remain private and retained under the ignored local evidence directory.

The freshness run uses signed synthetic transport with the real guarded consumer and MySQL. It
excludes Accounting posting, network and broker latency, so it is a lower bound for full source
freshness. The current full million-line publication completed with bounded memory but took about
114 minutes across staging, receipt and claims/projection publication; this remains a cold-build
performance limitation.

Database-to-artifact capacity, high-cardinality/mixed tenants and sustained soak are excluded
from this delivery, not pending work. Normal recovery tests and both final review/fix passes
are recorded in [the execution record](execution.md). Operating limits and rollback guidance
are in [the usage guide](usage.md). Default source/reference/materialized-result caps remain
unchanged; the historical measurements do not authorize higher production limits.

Evidence: `rf8-query-ten-million.json`, `rf8-export-ten-million*.log`,
`rf3-freshness*`, `rf4-full-publication-million-frozen.json`, and `rf6-large-value-proof.log`
under `.test_artifacts/reports-framework/` (private local artifacts, not committed).
