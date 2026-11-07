# Latest VM update — 7 November 2026

Authorized scope: deploy the latest local application build and database migrations to the existing VM. Preserve tenant data, saved credentials and concurrent local work.

Phases:

1. Confirm the host/user and running release. Freeze local source into a hashed archive.
2. Prepare a separate candidate release and install frozen Python/pnpm dependencies. Validate source and editable-package paths.
3. Back up all eight databases, compare migration heads and apply pending migrations with the existing migration credentials.
4. Build Auth and Console, run TypeScript and relevant backend/UI regressions. Resolve introduced failures before activation.
5. Atomically switch the release symlink, restart existing services/workers, and verify readiness, public pages and database/report checks. Retain the previous release and database backup.

- [x] Host and runtime inspected: `srv2111154`, `root`; previous release `product-ui-review-20261106-182029`.
- [x] Source snapshot and candidate preparation.
- [x] Database backup and migration verification.
- [x] Builds and release regressions.
- [x] Activation and post-deployment verification.

## Deployed release

- Active release: `/opt/kiscobooks/releases/latest-build-20261107-061719`.
- Source was refreshed after the user confirmed parallel edits were complete. Subsequent comparisons found further product-creation edits during verification; these were frozen into additional Console builds and included. Final runtime source verification covered 6,358 files, including the deployment regression corrections, retained-feed compatibility fix and later scenario tests.
- Backup: `/root/kiscobooks-backups/latest-build-20261107-061719/databases.sql`, 760,551,727 bytes, private permissions and verified SHA-256. All existing financial data was preserved.
- All eight schemas already matched source heads: Identity `0100`, Audit `0003`, Catalog `0223`, Accounting `0235`, Vouchers `0116`, Reports `0043`, Notification `0116`, Design `0009`. `alembic upgrade head` completed for each; no new DDL was pending. An initial working-directory error stopped before DDL and was corrected.
- Frozen dependencies, eight editable service/platform source-path checks, Auth/Console production builds and UI/Auth/Console TypeScript checks passed.

## Release checks and corrections

- Selected backend suites: 170 passed. Additional P&L/native report suites: 86 passed.
- Shared UI: 2,338 passed, 1 skipped. The existing VM Playwright installation was linked for the required browser suite; no browser tools were published as application dependencies.
- Auth: 327 component/browser tests and 393 server tests passed, 4 skipped. An early-click provider timing test failed during parallel execution, then passed in isolation and in the complete single-worker rerun; no Auth implementation change was needed.
- Console: 26 selected files / 329 tests passed. Outdated assertions were corrected for optional master codes, the opening unit-cost field and the retained edit-form Trading fieldset.
- Post-deployment review found a retained-feed compatibility gap. Warehouse policy fields are additive, but reporting-contract 0.14.1 rejected the exact 0.14.0 schema hash used by 234 READY retained snapshots. The previous release confirmed that identity. Version 0.14.2 explicitly preserves this known schema while retaining unknown-schema and fact-hash rejection. The regression first failed, then passed; the complete compatibility/inventory/native/framework suite passed 180 tests. Consumer lockfiles were updated and scoped Ruff passed. Snapshot identities, contents and financial history were not rewritten.
- The corrected contract was installed with frozen locks and all 27 existing application/worker services restarted. The previous application release remains available for rollback.

## Live verification

- All 27 application and worker services are active. All eight API readiness endpoints return HTTP 200. Public HTTPS sign-in and Console entry pages respond correctly.
- BTCL overview and source-readiness requests returned HTTP 200 after the compatibility correction. The temporary overview failure came from the rejected retained schema and a short service-restart window.
- BTCL P&L calculated successfully against the deployed definition and existing verified source from **6 November 2026**, producing six presentation rows. April 1 correctly raises `InsufficientHistoryError`; the updated UI defaults to supported coverage and identifies a partial financial-year period.
- Post-deployment financial checks: 72 posted journals, zero unbalanced journals; 50 stock receipt origins, zero receipt/movement quantity differences. Counts match the pre-deployment check.
- No live purchase, journal, opening balance or historical report job was edited. Authenticated overview success was observed in the service access logs; the P&L check used a read-only native calculation, not a new posted document or report job.

## Final Console refresh and overview review

- Included the later SimpleProductCreate/Batches/Serials changes and associated tests. The last frozen product-creation suites passed 84 tests; the updated Catalog creation-details suite passed 8 tests. Console TypeScript and the production build used the existing Console environment.
- Included later untracked scenario fixtures/tests and their results document. The additional Console scenarios passed 48 tests and TypeScript; Catalog client-contract and quantity tests passed 46 tests. These test/document additions followed the final application build and did not change runtime application source.
- Read-only calculation of BTCL's current overview succeeded. Its actual result passed the client's reconciliation validator and rendered through OverviewView with the real Providers. Together with the overview contract, period, share and component suites, 121 tests passed.
- Console was built in a separate directory and its completed bundle swapped while only the Console service was stopped. Previous Console bundles remain available for rollback; their fingerprinted static assets are retained for existing browser tabs.
- Scoped review found no new permission, tenant-isolation or financial-write change in the compatibility fix. Known retained schema identity is explicit; unknown schema and altered fact evidence remain rejected. This review and regression evidence do not claim exhaustive manual testing of every deployed screen.

Git staging/publication was not part of this VM update; concurrent local work remains preserved.
