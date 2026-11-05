# RF0 baseline and design evidence

Recorded 2026-10-14. All timings below are local observations, not capacity promises.

## Environment and workloads

Windows development host: 22 logical processors, 68,125,036,544 bytes installed memory,
Python 3.12.9, MySQL 9.6.0 on loopback port 13396, SQLAlchemy 2.0.54. Native tests create
random disposable schemas and never reset an application database. RabbitMQ uses the
repository's private local test vhost. This host is not the proposed production benchmark profile.

`apis/reports/tools/framework_data.py` generates deterministic, independently balanced journals
across two financial years. N transactions produce 2N journal lines and 3N + 33 source facts.
Generation is streaming and supports up to 10 million transactions; this generator capacity is
not evidence that the legacy ingestion path supports that size. Invoice and bank evidence use
the existing correctness fixtures, supplemented with complete finalized-session controls.

## Observations

| Probe | Observed result |
|---|---|
| Legacy domain, 1,000 transactions / 2,000 journal lines / 3,033 facts | Load 0.9091 s; reconciliation 0.6595 s; calculation 0.0933 s; total 1.6619 s with Python allocation tracing enabled |
| Same domain probe | 1.726 MB wire data; 9,088,795-byte traced allocation peak. This is not process RSS. |
| Native legacy, 100 transactions / 333 facts | Staging 0.463 s / 337 SQL statements; apply/activate 5.538 s / 2,461 statements; one trial balance 0.135 s / 16 statements |
| Guarded native query | Direct ORM aggregates return Decimal and exclude other tenants. An unfilterable Core alias and the tested nested alias aggregate fail closed. |
| Accounting source fence | Existing native concurrent-posting test confirms a competing commit stays blocked until the snapshot transaction releases its company fence; catch-up retains the committed change. |
| XlsxWriter 3.2.9 | 10,000 rows, constant-memory mode, 0.282 s; workbook created successfully |
| Jinja2 3.1.6 | Autoescaping probe passed |
| WeasyPrint 70.0 | Import failed because native layout libraries are unavailable on this Windows host |
| ReportLab 4.5.1 | 2,000 rows with repeated table headers, 0.314 s; PDF created successfully |
| Celery 5.6.3 | Packaging/import succeeded; actual delivery/recovery belongs to RF2 |

Reproduction commands, from the relevant service directory:

```powershell
# Reports
.\.venv\Scripts\python.exe -m tools.framework_baseline --transactions 1000 --output ../../.test_artifacts/reports-framework/baseline-domain-1000.json
.\.venv\Scripts\python.exe -m tools.framework_native_baseline --transactions 100 --output ../../.test_artifacts/reports-framework/baseline-native-100.json
.\.venv\Scripts\python.exe tools/verify_mysql.py

# Accounting: includes actual snapshot/write-fence, rollback and feed-isolation tests
.\.venv\Scripts\python.exe -m tools.verify_mysql --tests tests/test_reporting_feed.py
```

Raw benchmark/renderer files are under ignored `.test_artifacts/reports-framework/`. The native
query plan is saved with the native benchmark. The original suite had 90 passes, one skipped
broker test and 87.06% domain coverage. Added adversarial bank/control/deadline fixtures raised
domain coverage to 90.69% before framework code. The broker tests separately passed against
the local live broker. Native Accounting verification and migration round trip passed.

## Decisions for implementation

- Keep the proposed SLOs as acceptance targets. RF8 must measure native Tier M/L mixed load,
  actual RSS, I/O and owner posting impact; the small probes do not establish those targets.
- Use direct guarded ORM aggregates initially. More elaborate query shapes require native
  isolation tests and a reviewed guard-compatible implementation, not `unfiltered()` reads.
- RF1 adds immutable standard-library contracts and report-specific Pydantic adapters. V1
  stays compatible; actual packaged source hashes identify new implementations.
- RF3 retains the production source cap until a consistent-read/barrier protocol, bounded
  verification and incremental version storage pass native parity and capacity gates. The
  existing full snapshot under a write fence is the baseline to replace, not a scalable design.
- Select ReportLab 4.5.1 for PDF layout, with the same document model and design tokens used by
  HTML/Excel. HTML uses trusted Jinja templates. This removes the unavailable native Pango
  dependency. Linux packaging, fonts, visual quality and resource isolation remain RF6 gates.
- Use XlsxWriter 3.2.9 constant-memory output; explicit text preserves identifiers and amounts
  that exceed Excel's precision. Queue behavior and pinned production dependencies follow in
  the implementation phase that consumes them.

References: [ReportLab tables](https://docs.reportlab.com/reportlab/userguide/ch7_tables/),
[XlsxWriter memory mode](https://xlsxwriter.readthedocs.io/working_with_memory.html).
