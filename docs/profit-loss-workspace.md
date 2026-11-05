# Profit and Loss workspace

The `/reports/workspace?report=PROFIT_LOSS` screen offers two registered views over a
verified company generation. Statement is the default. Period comparison runs the
same frozen Profit and Loss calculation for the selected prior period and aligns
accounts by immutable account ID.

## Statement

The statement separates direct income, direct expenses, indirect income and
indirect expenses. Groups use the frozen account group and the source
`affects_gross_profit` classification. Gross profit follows the direct sections;
net profit follows all four sections. Group and section amounts are sums of
their account rows. The worker verifies total income, total expense, gross
profit and net profit against the authoritative source totals before publishing.
If that check fails, it publishes no completed result.

Zero accounts are hidden by default. An account with a nonzero imported YTD
component remains visible even when its net amount is zero, so migration
evidence is not concealed. A user can include all zero accounts through Filters;
the choice creates a new run so the on-screen rows and export rows agree. The
four sections and final totals remain visible even when amounts are zero.
Groups can be collapsed on the current screen without changing the frozen result.
Results use signed cursor pages with a maximum of 200 rows per request. Summary
cards come from full-result evidence, so paging never changes the totals.
The full statement cannot be narrowed with a result query. The run API requires
comparison dates for the comparison view and rejects them for Statement.

## Period comparison

Users can select the immediately preceding period, the same calendar dates in
the prior year, or custom dates. Current, previous and change are exact decimal
amounts. Change percent is `(current - previous) / abs(previous) * 100`, rounded
to two decimal places for display. When previous is zero, the percentage is
undefined and shown as a dash. An account that exists in only one period has
zero for the other period. Accounts with zero in both periods follow the zero
account filter. The service checks that account classification is consistent
between periods and verifies each period's totals separately.

The account name opens current-period ledger entries. In comparison view, the
previous amount opens previous-period entries. Both links are signed report
drilldowns that resolve company scope and permissions on the server.

## Source and export contract

The workspace prepares a source when the user has `report.definition.manage` and
none is ready. It also refreshes and retries once when verification reports a
stale source. The user can refresh explicitly. The progress strip shows source,
queue and calculation stages, with Stop for a queued or running job.

PDF, Excel, CSV and HTML use the registered view of the completed run. Exports
contain the complete result, not just the visible page, and the download appears
beside the export action when ready. Export limits and permission checks remain
server-owned. The run and its download retain the source generation, period and
view. Account and group codes use the same export Code column. Display
rounding uses the company's display configuration; calculations remain
four-decimal values.

Eligible imported year-to-date amounts are included only under the reporting
contract in [voucher-posting-reporting-design.md](voucher-posting-reporting-design.md).
The screen and exports identify included imported YTD amounts. Historical
transaction detail is unavailable before cutover, and the comparison does not
fabricate it. The workspace keeps the verified source's coverage date visible.

## UI review (2026-11-03)

A pending or failed replacement keeps the last completed report in its own view,
with an explicit notice. Exports use that completed view. View changes and account
drilldowns wait for active work to finish. Applying filters returns keyboard focus
to the Filters button. Large totals wrap inside summary cards; mobile Statement
fits the screen, while comparison keeps a bounded pinned account column and
horizontal scrolling. Negative gross and net totals use loss styling.
