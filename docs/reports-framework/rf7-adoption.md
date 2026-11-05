# RF7: API, console and operations adoption

Status: implementation complete within the revised API/database scope; admission flags remain
disabled by default. Keep the completed UI; additional UI features and browser rehearsal are
outside the user's final scope. Final functional evidence is in [the execution record](execution.md).

Implemented:

- Discovery exposes parameter schemas, registered views and only dependency-ready,
  permitted export formats with server budgets. Field-set metadata is available in v2.
- Actor/permission/company-bound run and export history uses indexed UUID keysets,
  lean projections and bounded pages. Versioned source history excludes legacy sources.
- Signed row drill-downs retain parent source generation, permission context and display;
  comparative and summary period boundaries determine the child query. Current target
  permission is required at both link issuance and child admission.
- The console supports typed filters, view/source selection, run status, automatic polling,
  cancel/retry, bounded 50-row result pages, parent navigation and independent exports.
  Saved runs restore their parameters. Report/export history stays paginated.
- Number/date presentation uses retained Identity display configuration through the shared
  UI formatter. The classic reports and banking screen remains accessible.
- Downloads use a separate authenticated Next streaming route. A short-lived grant stays
  server-side. PDF/HTML/CSV/XLSX bodies are never accumulated in React or a server buffer;
  attachment, private/no-store, sandbox and nosniff headers are applied.
- Additive migrations 0032 (actor history index) and 0033 (drill-down origin) match models.
  OpenAPI and the Reports TypeScript client include retained presentation and parameters.

Verification so far (Windows, 2026-10-15):

- Native MySQL API/drill-down/export gate and migration parity/round trip passed through 0033.
- Latest API integrity/execution/drill-down/export gate: 27 passed; latest adoption 8 passed.
- Reporting UI, download and page gate: 37 passed. Automatic-completion race and saved-filter
  regressions were reproduced before fixes. Invalid grants, current auth, unsafe media and
  cross-site navigation are covered.
- Materialized row pages now validate batch hash/count, continuity and completed count before
  display or issuing drill-down links. Four external-corruption fixtures failed before the fix.
- Console and shared UI typechecks pass after refreshing the local generated-client package.
- The whole-console functional rerun passed 392 tests with two workers. Its initial run had
  five timing failures under concurrent checks; the limited-worker rerun passed all of them.
- Shared report/display formatter checks passed 119 tests. Both final backend reviews and
  regression fixes are recorded in [reviews.md](reviews.md).

The [usage guide](usage.md) documents API commands, worker processes, readiness limitations,
private filesystem configuration, retention and rollback. Final native migration and full
Reports checks are recorded centrally in execution.md. No production activation or
completed-file deletion occurred. No load/soak tests or further UI features remain in scope.

Evidence: `.test_artifacts/reports-framework/rf7-*` logs in the local workspace.
