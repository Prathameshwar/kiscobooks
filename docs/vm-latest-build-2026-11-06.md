# Latest VM build — 6 November 2026

Requested scope: deploy the latest local application source and database schema to
the existing VM, preserving all tenant data and service credentials.

## Deployment phases

1. Freeze the local working tree into a source archive and hash manifest. Confirm
   the saved SSH profile connects to `srv2111154` as `root`.
2. Create a separate candidate release; install dependencies with frozen lockfiles,
   and ensure editable Python packages resolve inside that release.
3. Back up all eight databases. Compare migration heads and run each service's
   `alembic upgrade head` using the saved migration credentials.
4. Build Auth and Console, type-check all three web packages, and run affected
   backend regressions and the web suites. Compare unrelated failures with the
   previous release before deciding whether they are introduced regressions.
5. Switch the current-release symlink only after release checks succeed. Restart
   the existing APIs, web applications, and workers; verify health and the existing
   purchase reconciliation. Keep the previous release available for rollback.

## Candidate and database evidence

- Previous release: `purchase-readiness-20261106-172200`.
- Candidate: `latest-build-20261106-180159`.
- Initial snapshot: 6,213 source files, based on Git `8c70b4a` plus local changes.
- Exact candidate source hashes matched the complete manifest after the first
   deployment corrections.
- All eight frozen Python dependency installs and the frozen pnpm install passed.
- All eight Python services and their shared platform package resolve inside the
   candidate release. Installed Accounting/Catalog TypeScript clients match source.
- Backup: `/root/kiscobooks-backups/latest-build-20261106-180217/databases.sql`,
   374,878,189 bytes, private permissions. Existing data was not replaced.
- Migration checks passed for Identity `0100`, Audit `0003`, Catalog `0223`,
   Accounting `0235`, Vouchers `0116`, Reports `0043`, Notification `0116`, and
   Design `0009`. These already match the latest source; no schema upgrade was pending.

## Corrections discovered during release validation

- The production Auth build rejected `PreparationProgress` because it uses hooks
   without a client-component declaration. Added the declaration locally and on
   the candidate, then rebuilt successfully.
- The shared UI client-boundary regression also identified `FieldGroup`. Added
   its client declaration; the existing regression now passes.
- Attribute tests confused the named fieldset with its input/select. Narrowed the
   selectors to the actual controls, retaining all behavioral assertions.
- Seven voucher-rule tests queried text directly on a legend whose title is
   nested. Changed them to query the accessible field group. The same seven
   failures were reproduced against the previous running release before correction.
- The invoice-designer gallery undo/publish-indicator test also fails on the
   previous running release. It is recorded as a pre-existing limitation, not
   counted as a passing test.

## Verified checks so far

- Auth and Console production builds; UI, Auth, and Console TypeScript checks.
- Shared UI: 2,331 passed, 1 skipped, including native browser layout checks.
- Auth: 327 browser-component and 393 server tests passed; 4 skipped.
- Accounting: 26 purchase/stock regressions passed.
- Vouchers: 6 source-readiness/scope regressions passed.
- Reports: 6 capitalised purchase-tax regressions passed.
- Catalog: 16 creation/import/source/stock-facts regressions passed.
- Identity: 27 company-context/authorization/source regressions passed.
- Runtime source-selection regressions: 3 passed.
- Shared platform authorization regression suite passed.

## Final activation and verification

- Activated `/opt/kiscobooks/releases/latest-build-20261106-180159` through an
  atomic `/opt/kiscobooks/current` symlink replacement. The previous release is
  retained for application rollback.
- All 8 API readiness endpoints passed. All 27 previously active application and
  worker units restarted successfully and remained active without restarts.
- Auth and Console responded locally; public HTTPS sign-in and the website passed.
- Final affected Console suite: **21 files / 424 tests passed**, including the
  corrected voucher-rule tests. Platform authorization: **18 passed**.
- Verified suites total **3,577 passed**, with 5 opt-in tests skipped. This total
  covers the selected backend suites, complete UI and Auth suites, and all changed
  Console unit-test files. The complete 504-file Console suite was not finished;
  its broader runs were stopped after identifying and comparing unrelated failures.
  The pre-existing invoice-designer undo/publish-indicator failure remains open.
- Native post-deployment reconciliation: **30 posted journals balanced**, **13 stock
  receipts reconciled**, and **18 negative scenarios had no committed effect**.
- Tax and credit report evidence reconciles for all **30 test purchases**. Stock
  Summary and Item Ledger quantities reconcile for **5 stock products**.
- The actual Reports source cut was reverified with the deployed code: generation
  remains `READY`, 31 invoice records (30 scenario purchases plus an earlier test
  purchase), and **zero reconciliation differences**.
- The existing report limitation remains: batch-level valuation is unavailable
  under complete-company coverage when multiple batches share a warehouse cost
  pool. Stock quantities and native receipt costs reconcile; this deployment does
  not invent per-batch values or claim to resolve that limitation.

Git publication is separate: this workstation's managed filesystem permissions
deny writes to `.git/FETCH_HEAD`, so it cannot fetch/commit/push this deployment.
Concurrent local work is preserved; no unrelated changes were staged or published.
