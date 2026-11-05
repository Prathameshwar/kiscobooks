# Balance Sheet workspace

## Agreed phases

1. Confirm as-of inputs, existing account natures and opening/earnings contracts.
2. Register Standard and Comparative presentations over the verified calculation.
3. Build Standard with independent liabilities/equity and asset columns.
4. Build Comparative with two as-of dates, changes and scoped ledger links.
5. Reuse report progress, source recovery, cancellation and retained-result behavior.
6. Deliver complete-result exports, two-sided print, and retained history.
7. Review correctness/security/accessibility, test and restart affected processes.

## Financial contract

The v6 request takes `date_to`, optional `comparative_to`, and `show_zero` (false
by default). These are as-of balances, not activity ranges. The calculation adapter
uses the frozen source coverage start for both calculations. Dates before that
coverage are rejected, never silently moved. Each date must belong to a financial
year in the source. Account natures and groups come from the source; current and
non-current categories are not inferred from names.

Equity includes recorded equity plus opening, prior untransferred, and current-year
earnings exactly once. The presentation verifies its account sums and earnings
against the engine's controls and requires Assets = Liabilities + Equity. Losses
remain negative equity contributions. No balancing adjustment is invented.

Comparative aligns immutable account IDs in the same generation. An account remains
visible if either balance is nonzero. Change percent uses the absolute previous
balance; a zero denominator displays a dash. All amounts remain decimal strings.

## Presentation and delivery

Standard is the default, with liabilities/equity left and assets right, stacked on
phones. Comparative is a vertical statement. Group expansion affects only display;
summary totals always cover the whole result. Pages contain at most 200 source
rows; accounts identify their groups even when a group header is on another page.
Exports include all rows and label overlapping section/group/account totals.

Filters offer as-of date, comparison presets (previous financial year end, previous
month end, same date last year, custom), and Include zero accounts. Only completed
results supply displayed dates, totals and export views. Source preparation and one
verification-recovery refresh use existing permissions. An unavailable historical
date remains an explicit error. Ledger links include opening balances and retained
history through the chosen date. Derived earnings are disclosed, not presented as
a fabricated ledger account.

This is a management Balance Sheet, not a statutory filing format.

## Backend review safeguards

Dates before the selected generation's coverage are rejected at admission with
422, before a report is queued. Refreshing the same source cannot create missing
historical records.

Standard PDF/HTML uses one complete two-sided document. Package delivery for that
layout is rejected at admission; larger statements can use CSV/Excel, or the
Comparative layout's package delivery. This avoids accepting a job that exceeds
the two-sided renderer's whole-statement buffer while using a per-part budget.

Before printing, the two-sided renderer requires known sides, consistent currency,
exact amounts, and exactly one correctly placed grand total per side. The two
grand totals must agree. Invalid rows cannot be silently dropped or printed as
grand totals. The retained source row count is preserved across the print projection.

The backend review verified 78 financial/report-framework regressions and 24 focused
print, execution and package-capacity tests. Comparative packages preserve all source
rows and their manifest counts. Strict mypy, Ruff and formatting checks passed.

## Completion and review — 2026-11-03

All seven phases are implemented. The workspace shares its lifecycle controls with
Profit and Loss, while each report retains its own financial presentation and
parameter contract. Standard HTML/PDF uses a bounded two-sided projection with
aligned grand totals; CSV/Excel retain labelled full-result rows. Renderer content
identity includes the new projection. Completed older reports retain their layout.

Review fixes removed duplicate Standard grand totals, corrected the report subtitle,
aligned the side footers, and preserved comparison presets after applying filters.
History requests use the server's report-code filter so unrelated runs cannot
crowd out recent Balance Sheet runs.
Historical dates before source coverage remain errors rather than shifted dates.
Current/prior ledger links use signed server mappings and frozen source coverage.
Tenant/company permissions and artifact download authorization remain enforced by
the existing report framework; no posting or financial mutation was introduced.

Verification: 147 affected backend tests passed, followed by 14 focused Balance
Sheet tests covering the final adapter and both calculation paths. UI interaction,
route and existing Profit and Loss regressions passed. Browser checks cover both
views, open filters, 320/390/1440-pixel widths, and light/dark themes. TypeScript,
strict mypy on the affected backend modules, Ruff, and diff checks passed.

## UI review — 2026-11-03

The final UI review reproduced and fixed hidden comparison-date correction controls,
account detail disappearing after paging past a collapsed group, and large balances
overflowing their cells on narrow screens in both views. Invalid comparison choices
now open Filters and focus the relevant control. Filters disclose the resolved
comparison date and apply the accounting history lower bound to date inputs.

Amount columns identify the completed report's as-of dates, including while new
filters are edited. Changing pages expands groups so accounts whose group header
was on an earlier page remain visible. A paged-result note makes clear that totals
cover the whole report. Mobile tables size monetary columns to their content and
keep horizontal scrolling inside the statement region.

The affected interaction, report navigation, export and shared Profit and Loss
suite passed 72 tests. Browser layout checks cover Standard and Comparative,
filters open/closed, light/dark themes, 320/390/1440-pixel widths, and large signed
decimal amounts in both views. These use mocked API results and real browser CSS
layout. TypeScript checks passed. Review retained the existing permission gates,
signed drilldown/download requests and exact decimal-string formatting; no backend
or financial calculation changes were required.
