# Final framework reviews and fixes

Scope: reusable Reports API/database framework and the UI already implemented. The user
explicitly excluded load/soak testing and further UI features. Review verification uses normal
functional tests and disposable native migration checks only.

## Review 1: correctness, scope and immutable evidence

Walked registry/parameter contracts, source-generation publication, native/materialized results,
job/attempt fencing, artifact guards and download authorization against CLAUDE.md sections 5/6.
Checked tenant/company/session guards, current input permissions, same-transaction audit/outbox,
Decimal/currency/date semantics, bounded reads, immutable retained evidence and private storage.
Reports do not post money, allocate invoice numbers or edit closed-period documents.

Findings fixed:

1. Definition implementation hashes depended on Git LF/CRLF conversion. Normalizing line endings
   now makes identical packaged source stable across checkout conventions.
2. Export source labels consulted generation metadata instead of the completed run's retained
   owner manifest. Labels now use the frozen provenance and reject missing provenance.

Both regressions failed before the fixes. Combined identity/export/adoption/drill-down gate:
24 passed (`review1-red.log`, `review1-green.log`).

## Review 2: retained retrieval and recovery

Rechecked the fixed paths, source/attempt immutability guards, retry/cancel transitions,
materialized batch integrity, outbox repair, source permissions and renderer/file publication.
Reviewed additive migrations and API/client synchronization. No cross-service database access,
arbitrary SQL or automatic deletion of completed output was introduced.

Finding fixed: removing an optional drill-down target from the active registry made a retained
parent result return 404. Retrieval now preserves the original result and omits the unavailable
link. The child command still validates its target and current authority.

The regression failed with 404 before the fix. Drill-down/adoption/execution gate: 17 passed
(`review2-red.log`, `review2-green.log`). Earlier implementation checks also fixed result batch
corruption handling, resource-kind confusion, UI polling races and saved-filter restoration.

The `/simplify` and `/security-review` slash commands are unavailable in this environment;
these are the equivalent manual code/security passes. Final complete functional, native
migration, lint/type, generated-contract and packaging results are recorded in execution.md.

## Additional final review requested on 2026-10-15

Reviewed the current API commands, typed inputs, actor/company/source permission checks,
bounded result/history reads, job transitions and recovery, snapshot read-view/publication,
retained runtime identities, export supervision, filesystem publication and temporary cleanup.
The review applied the same security/correctness checklist and manual simplify/security-review
equivalents. No UI additions, load/soak runs, production activation or publishing were performed.

Two findings were reproduced and fixed:

1. **P1: calculation ownership expired before the first output batch.** Jobs had a 60-second
   lease, but source loading, native calculation and the synchronous reference calculator did
   not renew it. A valid slow calculation could repeatedly lose its attempt before publishing.
   The worker now supervises these stages with fresh authority checks and five-second lease
   pulses. Reference CPU work runs in a worker thread so it cannot block the heartbeat loop.
   Exports reuse the same supervision helper; work is joined before cleanup after revocation
   or cancellation. Attempt fencing and configured lane/renderer budgets remain in effect.
2. **P1: calculation identities omitted shared financial dependencies.** Changes to shared
   exact-decimal validation, money rules, bounds or keyset comparison could leave both the
   definition identity and retained ledger identity unchanged. Both now include those source
   hashes, storage/canonicalization helpers and relevant Python/library versions. Identical
   LF/CRLF source still produces the same identity.

The initial regression run had **11 failures and 2 passes** (`review3-red.log`). Lease tests
advance a controlled clock while using small ordinary fixtures; they do not wait for a real
long-running calculation or generate load. Added checks also revoke authority and cancel
while calculation is waiting, asserting no published rows and no unfinished supervised work.

Verification after fixes:

- Affected SQLite/API/worker/registry tests: **118 passed, 1 MySQL-only skip**
  (`review3-functional.log`).
- Native MySQL: **53 passed**; schema/model/index parity and full migration downgrade/upgrade
  through `0033` passed (`review3-native.log`). No schema changes were required.
- Ruff check/format, strict mypy (**98 source files**), OpenAPI and presentation asset checks
  passed. The public API schema did not change.
- A fresh wheel built and installed in the isolated package environment; framework worker and
  calculation-dependency imports passed (`review3-wheel-build.log`, `review3-wheel-install.log`,
  `review3-wheel-import.log`). All four renderers ran in the affected export tests.

Compatibility: this hardens identities before production activation. Earlier pinned-query runs
require their original runtime/build or a newly requested run; the worker does not rewrite
completed identities to accept changed rules. Materialized rows and completed export files
remain retained. Preserve runtime builds referenced by retained query results when deploying.
No other confirmed defect was found in the reviewed paths. Historical cold-build/XLSX speed
limitations and Linux validation remain as previously documented; neither was re-benchmarked.

## Report API review fixes requested on 2026-10-22

Fixed all four findings from the deep API review:

1. Outstanding-bill/advance export views retain party, role and DEBT/CREDIT direction so
   positive amount magnitudes cannot disguise credits as debts. API/download regressions
   exercise CSV, XLSX, HTML and PDF with debt 150 and credit 70.
2. Every Celery delivery executes in an expendable process with a parent deadline and an
   independent child watchdog. Windows starts the base interpreter directly with CPython's
   venv launcher environment, avoiding an orphaned interpreter behind a killed redirector.
   Real tests cover a stalled child, a subsequent solo task, watchdog termination, private
   credential round-trip and a report child opening disposable MySQL. Process memory is
   capped at 512 MiB. Lease expiry and existing attempt fencing govern recovery.
3. Native validation retains the requested scoped party for the shared calculation's
   second validation. Invoice headers remain selected by their date/batch component, so
   filter validation cannot seed an otherwise excluded invoice into a result. A valid
   party-filtered summary completes on its first attempt;
   invalid filters block as verification failures rather than retrying as dependency outages.
4. Daily/monthly summaries emit selected account/group rows in quiet periods with unchanged
   carry. Expansion counts account/group periods before allocating rows and includes the
   comparative budget. Tests assert balances directly in addition to reference/native parity.

The initial financial/export regression run failed all nine cases for the reviewed defects.
An existing API test was updated to traverse pagination because correct quiet-day output
exceeds a single 200-row page. Corrected framework definitions use version 3; the legacy
summary rule uses version 2. Omitted framework versions select the latest registered version.
Completed evidence is preserved; original runtime builds remain necessary for old pinned
queries. No model/schema migration, admission activation, commit or publishing was performed.

Manual simplify/security-review equivalents checked scoped queries and private child
configuration, authority/publication fences, cancellation/retry behavior, exact arithmetic,
allocation bounds and retained identities. No further confirmed security finding remains.
Public OpenAPI and the generated Reports TypeScript contract were synchronized.

Verification: affected discovery/native-summary/export/registry suite **92 passed**; native
MySQL suite **67 passed** with schema/model/index parity and downgrade/upgrade through `0033`.
The full coverage run reached **93.45%** domain branch/statement coverage (90% gate), with
**391 passed, 6 skipped and 3 failed**. Those three failures exposed invoice header retention
during filter validation and were corrected by retaining only parties. The fresh affected
native families passed **36 tests, 1 skipped** on SQLite; invoice/summary tests passed
**18 tests** on MySQL, including schema parity and downgrade/upgrade.
Ruff check/format, strict mypy (100 source files), OpenAPI, presentation-asset checks, client
typecheck/smoke (**8 transport tests passed**), Reports UI tests (**48 passed**) and the rebuilt
wheel's installed worker/query entry points passed. The final full suite after the invoice
correction completed with **394 passed, 6 skipped** in 588.88 seconds. Skipped checks require
a live broker, native row locks,
native index access, or Windows symbolic-link privilege; the real child/native-database check
was separately exercised successfully in the MySQL suite.

## Presentation and capacity extension review on 2026-10-22

Implemented the authorized extension: default/compact views for all 27 report definitions,
exact party-balance views for outstanding bills/advances, resumable native ACCOUNT_SUMMARY
bulk periods and bounded PDF/HTML ZIP packages. API discovery, generated client and console
controls expose retained choices and capacity limits. Additive migrations `0034` and `0035`
retain immutable run options and fenced calculation checkpoints.

Final review reproduced and corrected period-boundary opening/turnover differences and bulk
setup lease expiry. It also corrected missing calculation dependency identities, retained
comparative labels, checkpoint period/count validation and package scratch bounds. The complete
review and verification evidence is recorded in [presentation-capacity.md](presentation-capacity.md).

Full suite: **402 passed, 6 skipped**; final affected coverage gate: **41 passed**, **93.49%**
domain coverage. Latest capacity/lease/runtime regressions: **29 passed** on each of SQLite
and MySQL. Migration downgrade/upgrade and model/index parity through `0035`, lint/format,
strict typing, generated contracts, console checks and an installed-wheel PDF/HTML ZIP smoke
test passed. No further confirmed defect remains in the reviewed paths. Production activation,
Linux and load/soak validation remain separate; bulk currently extends account summaries only.


## Review 5: all 27 report APIs

The [report-by-report review](report-by-report-review.md) records official Tally concepts,
per-report column and drilldown changes, typed prefix search/filter/sort queries, immutable
selected-result provenance and original-balance semantics. Every report uses a bounded worker
for result selection and ordinary signed ordinal pages for the selected output. Selection
exports retain the parent control context and identify selected rows.

Review fixes removed unbounded HTTP ledger traversal, pinned row detail to signed cursor
positions, strengthened complete definition identity, corrected GL account/currency labels,
and aligned journal links with actual journal posting dates rather than invoice document,
tax-point or allocation dates. Current authority/field denies, tenant/company ownership,
private exports, immutable attempts and exact money remain enforced. New scoped journal index
migration `0036` matches the model and passed downgrade/upgrade and native access tests.
Runtime v1 remains packaged; new ledger semantics live in frozen v2. Console GET link/proxy
compatibility and generated contracts are synchronized. No unresolved functional/security
finding was found in reviewed scope.

Validation: full regression **498 passed, 6 infrastructure/native skips**; final MySQL
navigation/invoice/index gate **106 passed**, model/index parity and migrations passed.
Focused domain coverage gate **103 passed**, **94.89%**, above 93.49% prior coverage.
Whole-service coverage assertion remains below its default 90% threshold (85.47% full-run
measurement); renderer child entrypoints and retained runtime helper branches are uncovered.
This is recorded separately from the passing domain policy and functional tests. Console
compatibility **39 passed**, subsequent detail formatting **14 passed**; console/client typing,
8 client transport tests, Ruff/mypy, contract drift and installed wheel checks passed.
Production load/soak and release activation remain outside this task.
