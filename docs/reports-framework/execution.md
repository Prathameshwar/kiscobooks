# Reports framework execution record

Inventory extension (2026-10-22): ten additional definitions bring the catalogue to 37.
[Implementation, API inputs, two reviews, verification and limits](inventory-implementation.md)
record the completed reporting layer and trusted Accounting publication adapter. The actual
B20-B26 stock posting/costing producer and stock activation remain unfinished and separate;
missing inventory evidence blocks execution. No load/soak tests or new UI code were added.

Started: 2026-10-14. User authorized RF0-RF8 implementation in order, with complete phase
verification and two final review/fix passes. Governing scope: [framework plan](../reports-framework-plan.md).

## Decisions

- 2026-10-22: user authorized the presentation/capacity extension and final review uninterrupted.
  [Three-phase scope and decisions](presentation-capacity.md) add named views, opt-in native
  bulk summaries and bounded PDF/HTML packages plus matching console controls. This supersedes
  the earlier UI-feature exclusion for these controls; load/soak and production activation
  remain excluded.

- D02: user selected a private filesystem as the default artifact backend. S3/Azure/cloud
  services must not be mandatory. A configured persistent folder is supported on one host;
  multi-host workers need a durable shared mount of that folder. The adapter remains replaceable.
- D03: user selected keeping completed reports/exports. Automatic cleanup is limited to
  abandoned temporary files; completed output and evidence are not automatically expired.
- D07: user confirmed Windows deployment first on 2026-10-15. Validate Windows rendering
  and packaging now; Linux native validation follows before Linux activation.
- Phase-plan approval is complete; no further phase-by-phase approval is required for the
  authorized implementation. Production activation and infrastructure purchases are separate.
- 2026-10-15 scope revision: user selected framework + UI + two review/fix passes and then
  explicitly said "I don't want load test". Stop load/capacity/soak runs. Normal functional,
  correctness, permission, migration and build checks remain in scope. Earlier capacity
  evidence is historical only; outstanding load gates are removed from this delivery.
- Final scope clarification: focus remaining work on API/database. Keep the UI already
  implemented, as explicitly requested; add no further UI features. Complete two backend
  review/fix passes and normal functional checks. No load or soak testing.

## Phase ledger

| Phase | Status | Evidence |
|---|---|---|
| RF0 | VERIFIED BASELINE | [Local baseline, query/fence and renderer probes](rf0-baseline.md); native Reports/Accounting migration checks and live broker tests pass. Production capacity remains unverified. |
| RF1 | COMPLETE | [Contracts and compatibility](rf1-contracts.md); 181 tests pass on SQLite and MySQL, 92.21% domain coverage, Ruff/mypy/client checks pass. |
| RF2 | COMPLETE | [Durable execution](rf2-execution.md); SQLite 192 passed/3 infrastructure skips, MySQL 193 passed/2 broker skips, domain 92.47%; live broker, native Identity, Ruff/mypy and client checks pass. |
| RF3 | COMPLETE IN REVISED SCOPE | [Versioned sources, refresh, compaction and recovery](rf3-source-generations.md). Accounting owner suite: 734 passed/18 infrastructure skips. Final native Reports suite and migration checks pass. Historical cold-build speed remains a documented limitation; remaining load/soak gates are excluded. |
| RF4 | COMPLETE; DISABLED BY DEFAULT | [Native query families](rf4-native-queries.md) cover all 27 definitions within declared bounds, with reference parity, exact values, bounded paging and retained runtime checks. Final native functional suite passes. |
| RF5 | COMPLETE; DISABLED BY DEFAULT | [Private local artifacts and independent exports](rf5-artifacts-exports.md): fenced publication, streaming retrieval, current authorization and indefinite completed-output retention. Final native functional suite passes. No cloud storage dependency. |
| RF6 | COMPLETE FOR WINDOWS; DISABLED BY DEFAULT | [Shared presentation](rf6-presentation.md): final installed wheel renders PDF/HTML/CSV/XLSX with packaged assets. Wide/empty visuals, exact-value and shared display checks pass. Linux validation remains separate before Linux deployment. |
| RF7 | COMPLETE IN REVISED SCOPE | [API and preserved UI](rf7-adoption.md): scoped history, signed drill-down, frozen display, streaming downloads, run/export controls. Final MySQL migrations through 0033 pass. Console: 392 passed; typechecks pass. [Worker/configuration/retention runbook](usage.md) complete. No further UI features are in scope. |
| RF8 load/capacity/soak | REMOVED FROM DELIVERY BY USER | [Historical capacity evidence](rf8-capacity.md) retained. The running million-line database/export probe was cancelled on user instruction. No further load tests will run. Normal functional recovery checks remain part of framework review. |
| Review 1 and fixes | COMPLETE | Definition identity normalized across Git line endings; export source labels now use the frozen run manifest. Both defects reproduced before fixes. Review gate: 24 passed; see `review1-red.log` and `review1-green.log`. |
| Review 2 and fixes | COMPLETE | Retained result retrieval now survives removal of an optional drill-down target. Regression reproduced before the fix; 17 passed in the review gate. See [review findings](reviews.md). |
| Additional final review and fixes | COMPLETE | Slow calculation lease renewal and shared financial dependency identities fixed after reproducing 11 failures. Affected checks: 118 passed/1 native-only skip; MySQL: 53 passed with migration round trip. See [review findings and compatibility note](reviews.md#additional-final-review-requested-on-2026-10-15). |

Functional and historical benchmark output is retained under ignored
`.test_artifacts/reports-framework/`; summaries and commands are recorded here. Historical
measurements do not establish production readiness. Remaining load/soak work is excluded,
and no additional UI feature work is in scope.

## Final functional verification (Windows, 2026-10-15)

The full-suite figures below precede the additional requested final review. Its two focused
fixes and subsequent affected-suite/native/package results are recorded in
[reviews.md](reviews.md#additional-final-review-requested-on-2026-10-15); domain calculation
rules and public schemas did not change during that review.

- Reports native MySQL: **359 passed, 3 skipped**; schema/model/index parity and full
  downgrade/upgrade passed through revision `0033`. Evidence: `final-native-functional.log`.
- Reports SQLite/domain coverage: **357 passed, 5 skipped**, **93.40% domain coverage**
  (required floor: 90%). Evidence: `final-functional.log`. Benchmark tests were explicitly
  excluded from both database suites. The SQLite run additionally skips two MySQL-only checks.
- Reports Ruff check/format passed; strict mypy passed for **98 source files**. OpenAPI,
  generated Reports client and presentation-asset drift checks passed; client smoke: **1 passed**.
- Console: **392 passed** on the limited-worker rerun; report workspace/download/page subset:
  **37 passed**. Initial whole-console run had five timing failures during concurrent checks;
  the rerun passed all tests. Console and shared UI typechecks passed.
- Shared UI formatter suite: **119 passed**. Earlier affected platform suite: **1,093 passed**,
  **97.81% coverage**; no platform code changed during the final review fixes.
- Final wheel build/install passed. A two-row fixture rendered all **four export formats**
  from the isolated installed package, including the real Windows PDF subprocess.
  Evidence: `final-wheel-build.log`, `final-wheel-install.log`, `final-wheel-smoke.log`.
- Both review/fix passes are complete with reproduced regressions; see [reviews.md](reviews.md).

The native skips are the two opt-in live-broker checks and the Windows symlink-privilege
case; live-broker checks passed earlier in RF0/RF2. Feature switches remain off by default.
This is a local implementation handover, not a production deployment or capacity guarantee.
No commits or publishing were requested or performed.

## Initial inspection

The starting tree has the proposed plan and Reports README edits from the planning task and
an unrelated untracked `.claude/` directory. Preserve unrelated work. No commits/publishing
are requested. Existing v1 behavior and retained outputs remain compatibility requirements.

The repository also contains Azure Blob/Azurite for Identity; that does not impose a cloud
dependency on Reports. Local MySQL and RabbitMQ tools are available for native testing.

The `/simplify` and `/security-review` slash commands are not exposed as callable tools in
this session. Perform equivalent documented code/security review passes, including the
repository's security/correctness checklists, and record findings/fixes transparently.
