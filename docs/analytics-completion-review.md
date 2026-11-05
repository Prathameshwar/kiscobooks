# Analytics completion and review

Authorized 2026-11-03: inspect every report under `/reports/analytics`, complete
pending work one at a time, then review and fix the whole delivery.

The five business reports already have native calculations and exports. The
three controls also have calculations, but still open the generic workspace.
This pass completes those user flows and verifies every registered view.

## Report loop

| Order | Report | Phases |
|---|---|---|
| 1 | Sales performance | Verify customers/products/categories/trends and returns; add automatic source preparation, recovery, visible progress and exports; test. |
| 2 | Profit and margin analysis | Verify P&L and product-cost evidence; preserve fiscal-year/comparison dates and frozen display; test all views. |
| 3 | Customer insights | Verify purchase/return history, segmentation and currency separation; complete retained-run navigation; test. |
| 4 | Expense and profit leakage | Verify expense/diagnostic separation and comparisons; preserve applied columns and drill-down exports; test. |
| 5 | Cash and working capital | Verify cash equation, dues, credits and stock availability; complete data refresh and unavailable-state presentation; test. |
| 6 | Balance continuity | Add a dedicated workspace with complete financial-year selection and readable continuity columns; verify native results, drill-downs and exports. |
| 7 | Source reconciliation | Add a snapshot-wide workspace without misleading period filters; show source counts and debit/credit controls; verify exports. |
| 8 | Invoice to ledger reconciliation | Add a dedicated dated workspace with invoice/account selectors, readable posted effects and audit view; verify source links and exports. |

Final review covers tenant/company permissions, exact money, source freshness,
historical runs, filters, cancellation, exports, mobile layouts and shared-workspace
regressions. No postings, database migrations, new permissions or dependencies are
planned. Existing frozen reports remain readable. Runtime services are restarted
after validation. Publication is separate from this implementation request.

## Execution

All eight report loops are implemented. Existing native calculations were reused;
the pending work was in report-specific presentation, source recovery and several
boundary cases found during review.

| Report | Completed implementation and review |
|---|---|
| Sales performance | Missing/stale snapshots prepare automatically with bounded refresh/full-rebuild recovery; progress and downloads appear at the top; all customer/product/category/trend views and returns verified. |
| Profit and margin analysis | Full fiscal-year selection retains eligible imported YTD. Admission and calculation accept the same verified aggregate coverage as P&L. Detailed invoice/product data and trends remain restricted to retained history, with a visible disclosure. |
| Customer insights | Retained runs open before new-run/source gates, including direct history URLs. Customer/return activity, segments and currency separation retain their existing verified calculations. |
| Expense and profit leakage | Automatic verification recovery, frozen display and applied-column retention. Imported YTD is included in company totals without inventing supplier or monthly history. Diagnostic reductions are not deducted twice. |
| Cash and working capital | Queued calculations offer Stop. Cash/credit/dues/stock separation remains verified. Missing evidence is explained visibly; it is not substituted with zero or a forecast. |
| Balance continuity | Dedicated Analytics workspace, complete-year defaults and selector, compact continuity view and source-detail view, history, search, exports and account/carried-bill drill-downs. |
| Source reconciliation | Dedicated snapshot-wide workspace with source counts and debit/credit controls; no misleading From/To filters. Uses immutable verification evidence. |
| Invoice to ledger reconciliation | Dedicated dated workspace, verified invoice/account selectors, posted-effect and source-detail views, journal drill-downs and private exports. |

Final review also corrected analytics values remaining visible after a 401/403,
hidden debit/credit columns on ledger drill-downs, current preferences changing
historical amount/date display, and oversized charts/introductory spacing. YTD
drill-downs now restrict dates to available transaction history; aggregate-only
periods expose retained row details without promising missing transactions.
The main reconciliation PDF projections keep core monetary checks together in
one column band; additional identifiers remain in Source details.

New Analytics calculations report calculation version 3. The three control
definitions use version 6. Existing frozen results keep their retained schemas
and display settings. There are no route/schema, database or permission additions.

## Verification and boundaries

- Broad backend suite: 148 passed, including all eight reports and all 29 views,
  native MySQL execution, drill-downs and actual private PDF/XLSX/CSV exports.
- Imported-YTD and drill-down follow-up: 7 passed. Final control projection and
  PDF checks: 6 passed, including monetary headers on the first PDF page.
- Shared console regression: 197 passed across 11 files. Final Analytics checks:
  40 passed, including the new visible evidence-limit regression. Runs overlap.
- Browser review checks all 29 views at 1440, 390 and 320 pixels in light/dark
  themes, contained table scrolling and bounded chart height. Representative
  desktop/mobile screenshots and the invoice bridge PDF were inspected manually.
- After the final control projection changes, 12 workspace checks and the browser
  suite passed again using regenerated catalog definitions.
- Ruff, strict mypy for seven changed source modules, console TypeScript, Reports
  OpenAPI drift and generated-client checks passed.

Artifacts are under `.tools/analytics-completion/`; logs use
`.tools/analytics-completion-*.log`. Financial checks use populated synthetic owner
facts in disposable MySQL schemas. These checks do not certify live customer data.
Incomplete stock costs/history and aggregate-only migration history remain
explicitly unavailable where detail cannot be established.

The `/simplify` and `/security-review` commands are unavailable in this session.
Equivalent manual reviews covered shared-state reuse, cancellation, immutable
results, signed drill-down scope, current permissions, company/source boundaries,
bounded reads, Decimal calculations and private downloads. No additional security
or money-write changes were required.

The console, Reports API and report execution/render workers were restarted.
The API readiness endpoint reports ready, all six reporting/source workers are
running, and the Analytics route responds with the expected sign-in redirect.
