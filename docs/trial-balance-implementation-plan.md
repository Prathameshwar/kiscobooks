# Trial Balance: two-layout implementation plan

Requested 2026-11-02: implement the two illustrated Trial Balance layouts with a
switch, keeping the closing-balance summary as the default, and support expansion
through the accounting hierarchy. This document is the proposed delivery plan;
implementation phases were authorized by the user on 2026-11-02, including final
review and fixes. Actual progress and evidence are recorded in
[Trial Balance delivery](trial-balance-delivery.md).

## 1. Agreed product behavior

| Item | Behavior |
|---|---|
| Default layout | **Closing balances**: account/group name, closing Debit and Credit. |
| Alternate layout | **Opening and movement**: name, Opening Dr/Cr, Period Dr/Cr and Closing Dr/Cr. |
| Layout switch | A labelled shared segmented control. Switch columns immediately on the same completed report; preserve dates, expansion, row position and zero-row setting. |
| Hierarchy | Native account head -> root group -> nested groups -> ledger account. Support the actual variable group depth, including accounts attached directly to a root group. |
| Initial expansion | Heads expanded to show their immediate groups; deeper groups collapsed. |
| Level controls | Heads, Groups, All groups and Ledgers, plus individual expand/collapse. Level controls set an expansion policy; they do not download the entire tree. |
| Zero rows | Show zero rows by default. When disabled, hide only accounts with zero opening, debit, credit and closing; a zero closing with period activity remains visible in both layouts. |
| Totals | Full-company totals remain visible independently of hierarchy expansion and pagination. Summary shows closing totals; detailed shows all three pairs. |
| Drill-through | Ledger action opens the existing signed Account Ledger drilldown at the same source and dates; returning restores the Trial Balance position. |
| Entry point | Reports -> Finance -> Trial balance opens a dedicated workspace through the existing `/reports/workspace?report=TRIAL_BALANCE` URL. |
| Formatting | Company currency, amount precision, rounding and date settings; the completed run's retained display configuration governs its rows and exports. |
| Filters | Closed initially, opened by the Filter icon immediately after Refresh accounting data. Includes year/dates, expansion level, zero rows and available statement periods; reopening preserves choices. |
| Export toolbar | Export hierarchy follows the Filter icon. A split button exports PDF initially; its menu offers Excel, CSV and HTML and remembers the chosen format. |
| Compact layout | Tight title/subtitle spacing, one action toolbar and a persistent layout switch beside statement metadata above the table; responsive wrapping in all themes. |

A new ordinary visit starts in Closing balances. The current mode and expansion
may be retained for return navigation within that company/actor/report session;
a previous Detailed visit must not silently change the default for a new report.

The first valid company/year/source selection prepares the report automatically.
Subsequent date changes use Apply, retaining the previously applied result while
the next request runs. Refresh obtains a compatible new verified source and report.
Source preparation, report calculation and export progress have distinct states.
An unavailable or incomplete source never appears as a balanced zero report.

## 2. Existing implementation and reuse

- Accounting owns posted journals and financial configuration. Reports already
  receives verified frozen Accounting source generations and native daily balances.
- `domain/statements.py` calculates exact account opening, gross period debit and
  credit, signed closing and split closing balances. Initial-opening corrections
  and linked reversals already have defined treatment.
- `queries/native_statements.py` supplies bounded native aggregates with reference
  parity. Reuse those inputs rather than copying the journal calculation into UI.
- The current TRIAL_BALANCE definition is version 5 with generic default/compact
  views. Its rows are accounts with direct group labels and a closing control row;
  it does not supply a complete expandable hierarchy or split opening columns.
- The v2 framework stores frozen result batches, result evidence, permissions,
  display configuration, signed drilldowns and independent exports. Existing
  result paging is ordinal-based; parent-child tree paging needs an indexed contract.
- `ReportWorkspace.tsx`, Day Book and the report export helpers provide existing
  source/run lifecycle, retry, return-navigation and private download patterns.
  Shared `SegmentedControl`, `IconButton`, tables and tokens provide UI mechanisms.

Baseline from the preceding readiness review: 98 backend checks passed, one
discovery check failed, and 43 Console checks passed. The failing discovery check
expects 39 definitions while 44 are registered after five analytics additions.
These are fixture checks, not proof of live Trial Balance readiness. Phase 1 will
reproduce and resolve that catalogue-test mismatch before relying on green gates.

Governing references:
[financial reporting](voucher-posting-reporting-design.md),
[account recording](voucher-account-recording-design.md),
[framework usage](reports-framework/usage.md),
[export delivery](report-export-delivery.md),
[design system](design-system.md), and [repository rules](../CLAUDE.md).

## 3. Financial and hierarchy contract

For each account at one frozen source and requested posting-date range:

```text
opening_signed = retained balance before the period
                 + existing same-start-date opening/correction effects
period_debit   = gross ordinary debit movements in the period
period_credit  = gross ordinary credit movements in the period
closing_signed = opening_signed + period_debit - period_credit

opening_debit  = max(opening_signed, 0)
opening_credit = max(-opening_signed, 0)
closing_debit  = max(closing_signed, 0)
closing_credit = max(-closing_signed, 0)
```

Each parent sums its descendant **account-side** opening and closing Dr/Cr
independently, and sums gross movement Dr/Cr. It must not net a debit account
against a credit account before constructing these columns. Existing master
`nett_balances` settings do not silently change this selected gross-side layout.

Grand totals aggregate leaf accounts once. Parent rows, depth changes, zero-row
visibility and loaded pages do not alter financial scope. A group's signed bridge
uses Opening Dr - Opening Cr + Period Dr - Period Cr = Closing Dr - Closing Cr.
Complete-company opening, period and closing pairs each reconcile. A mismatch
blocks report completion; preserve diagnostic evidence without balancing entries.

Use Decimal throughout the server, exact decimal strings in wire/storage JSON,
and the shared client formatter. Display rounding must not change exact controls;
disclose a display residual when rounded rows do not visibly sum to rounded totals.

Retain posted history for inactive accounts, original entries and dated reversals.
Draft/prepared/void documents have no GL effect. Use recorded base amounts for the
complete-company Trial Balance, including base-only FX effects. Preserve existing
raw nominal-account carry across years; do not invent annual profit transfers or
recalculate earnings as Trial Balance journal entries.

The hierarchy is frozen from the source's native heads and group parent links.
Renaming or reparenting masters later cannot rewrite a completed run. Missing
classifications, cycles, dangling references or cross-head ancestry block a new
hierarchy result. Root ordering follows financial nature, then stable head code/ID;
sibling ordering follows stable group/account code and ID. Do not impose a fixed
number of subgroup levels. CURRENT and COMPARATIVE use separate node identities
and totals when an existing comparison is requested.

## 4. Versioned result, reads and exports

### Canonical result

Introduce the next TRIAL_BALANCE definition version with an isolated handler,
reusing the existing account aggregate calculation. Every canonical node carries
stable node/parent identity, node kind, depth, code/name, currency, period,
child/descendant-account counts and the six monetary columns. The report manifest
retains all three total pairs, differences, leaf-account count, hierarchy identity,
source evidence and display identity. It is available without reaching the last page.

Register `default` as Closing balances and `detailed` as Opening and movement.
Both are ordered projections of the same canonical result with the same calculation
identity, so switching or exporting either view does not create a second money
calculation. Keep older completed runs readable/exportable with their retained
definitions. A legacy run without hierarchy facts uses its existing renderer and
offers a new compatible run for the new experience; do not reconstruct it from
today's masters. Keep other statements and ledger runtimes compatible.

### Bounded hierarchy access

Add a Reports-local reconstructible hierarchy index over frozen result batches.
Store scoped job/attempt/period/node/parent identities, sibling order, zero-row
eligibility and the result-row/batch locator. Financial values remain in canonical
immutable output. Publish the index under the same attempt fencing as result
batches; it becomes readable only when the entire job is COMPLETE and verified.

Provide typed company-scoped hierarchy discovery/child reads under the completed
report run, with a proposed route `/report-runs/{id}/hierarchy`. Read roots or one
parent's immediate children through signed keyset cursors, 50 default/200 maximum.
Bind cursors to company, actor/permission context, run attempt, period, parent,
sort and zero-row setting. Check scope and retained batch integrity on every read.
Validate node identity against that completed run; never trust client parent IDs.

The UI loads branch pages on demand and keeps a bounded cache. Expanding to Ledgers
sets the desired level and loads visible portions progressively. Large sibling
sets have explicit Next/Previous pages, replacing the prior sibling page. Keep a
1,000-row cache including pending reservations, a 100-cursor history window, and
First accounts recovery. Avoid unbounded tree requests, browser
financial aggregation, page-only totals and recursive fetch-all expansion.

Any required table/index migrations belong only to Reports, with matching model,
schema/factory/metadata updates, one DDL statement per revision and downgrade.
Freeze the precise index and query plan in Phase 1 before creating migrations.
No cross-service database access is introduced.

### Layout-aware exports

Reuse the existing independent PDF/XLSX/CSV/HTML jobs and private artifact delivery.
The selected layout is the default export layout. Offer Current hierarchy and All
ledgers: Current hierarchy includes the selected level and manually expanded
branches across the complete report, including rows beyond the loaded pages;
All ledgers includes the complete hierarchy. Zero-row visibility matches the screen.

Persist typed, bounded presentation options with each export: layout, period,
hierarchy level and validated explicit expanded node identities where needed.
These choose retained rows, not financial scope. Reject incompatible layouts,
foreign/unknown nodes or capacity overflow. Browser requests submit identities
and presentation settings, never computed balances or collected report pages.

PDF/HTML use indented hierarchy, clear group styling, repeated headers, full totals,
company/date/currency/freshness context and grouped Dr/Cr headers for Detailed.
Excel retains exact numeric cells, hierarchy outline levels where supported,
explicit account/group/total row types and the existing context sheet. CSV retains
node type, level, code/name/parent context and the selected monetary columns so
hierarchy rows are distinguishable from additive account rows. Group and grand
total rows must never be described as another set of financial entries.

## 5. Delivery phases and exit criteria

| Phase | Deliverables | Exit criteria |
|---|---|---|
| **1. Contracts and baseline** | Finalize both layouts, switch/default/state rules, variable-depth hierarchy, zero-row behavior, controls, compatibility, paging/index shape and export options. Audit native head/group/source facts and local worker readiness. Reproduce the existing discovery failure and repair its stale expectation with meaningful catalogue assertions. | Reviewed contract and independent arithmetic fixtures; source gaps explicitly identified; affected existing tests green; exact migration/query requirements recorded. |
| **2. Calculations and frozen hierarchy** | Add the versioned Trial Balance handler, split opening sides, independent parent-side aggregation, all three controls and complete manifest totals. Reuse native aggregates and build frozen topology/index under the existing worker attempt fence. Deliver matching migrations/models if required. | Reference/native parity, mixed-side groups, arbitrary depth, inactive history, zero closing with turnover, corrections, FX and cross-year fixtures pass. Migrations upgrade/downgrade and exact storage/index parity pass; other statements remain green. |
| **3. APIs, discovery and compatibility** | Register default/detailed views, typed summary/hierarchy reads, signed branch paging and scoped presentation options. Reuse current report submission/cancel/retry flow. Synchronize OpenAPI, generated API client, schema metadata and consumers. Preserve older completed reports. | 401/403/wrong-company/tenant/read-deny/revocation checks; malformed parent/cursor/period inputs rejected; deep sibling paging has indexed plans and stable order; full totals independent of paging; legacy read/export regressions pass. |
| **4. Dedicated Trial Balance UI** | Connect the Finance card/current URL to the dedicated screen. Build company/year/period header, default Closing balances and Detailed switch, grouped headers, hierarchy level controls, branch paging, full totals, zero-row control, automatic preparation and Apply/Refresh. Implement responsive progress/error/retry/history/source-detail states and return state. | UI tests prove default and both modes, no recalculation on switch, expansion/position preservation, correct applied dates, old-result retention, bounded reads, company/actor isolation and honest unavailable/empty states. Keyboard, focus, all themes and narrow widths pass. |
| **5. Ledger drilldowns and real exports** | Wire signed account drill-through and Back restoration; deliver both layouts in existing export formats with current/all-ledger hierarchy options, private PDF preview and independent job recovery. Extend shared export options only where required. | Actual PDF/Excel/CSV files agree with independent full-result totals and selected hierarchy, including off-page accounts; HTML regression checks pass. Layout switch during an export cannot change that export. Permission revocation, stale branch IDs and exact retry identities are covered. |
| **6. Final review and readiness** | Review arithmetic, hierarchy, source completeness, query bounds, permissions, UI recovery and the Finance -> Trial Balance -> Account Ledger journey. Verify configured local workers/snapshots, affected full suites, coverage, lint/types/client freshness and browser/export evidence. Resolve in-scope findings and record remaining external blockers. | All affected checks green; new domain coverage meets 90% and overall coverage does not decrease; disposable native MySQL tests and nonempty browser fixtures pass; live read-only evidence and download checks recorded where source/configuration supports them; final simplification/security review findings reported. |

Each phase includes tests and review, and ends with the repository working. Phase
work begins after agreement on this plan; further phase confirmations are needed
only if scope or a governing unresolved business decision changes.

Implementation reuses Reports and the shared Console/UI packages. It does not
require a new service or change Accounting's posting rules. Verify local source,
broker, worker, authority and private export-folder readiness as part of delivery;
record any configuration gap separately from calculation correctness. Financial
posting/release activation and publication retain their existing authorization rules.

## 6. Acceptance fixtures and checklist

The two illustrated layouts share this independent fixture, amounts in INR:

| Head | Opening Dr | Opening Cr | Period Dr | Period Cr | Closing Dr | Closing Cr |
|---|---:|---:|---:|---:|---:|---:|
| Assets | 100,000 | 0 | 90,000 | 50,000 | 140,000 | 0 |
| Liabilities | 0 | 40,000 | 10,000 | 50,000 | 0 | 80,000 |
| Capital and Equity | 0 | 60,000 | 0 | 0 | 0 | 60,000 |
| Income | 0 | 0 | 0 | 120,000 | 0 | 120,000 |
| Expenses | 0 | 0 | 120,000 | 0 | 120,000 | 0 |
| **Grand total** | **100,000** | **100,000** | **220,000** | **220,000** | **260,000** | **260,000** |

- [ ] New report starts in Closing balances; Detailed uses the same run and amounts.
- [ ] Expand Assets -> Current Assets -> Cash and Bank -> Cash/Main Bank; collapses
  and level changes preserve totals and restore correctly after a layout switch.
- [ ] A group containing one 5,000 Dr account and one 2,000 Cr account shows both
  sides, not only a 3,000 Dr net. Include a balancing account outside that group.
- [ ] Test accounts directly under a root group, multiple subgroup depths,
  empty/zero branches, invalid ancestry and stable duplicate-name ordering.
- [ ] A zero-closing account with opening or gross movements remains visible when
  zero rows are hidden; a wholly unused account follows the visibility setting.
- [ ] Each account and group's signed bridge reconciles; all company total pairs
  reconcile independently. Same-account opposing movements retain both gross sides.
- [ ] Drafts have no effect; delayed voucher acknowledgement does not hide an
  Accounting-committed journal; originals and later reversals retain their dates.
- [ ] Initial opening/correction, prior-year carry, base-only FX and display rounding
  cases agree between the reference calculation, native query, UI and exports.
- [ ] Reparented/renamed/inactive masters cannot rewrite a frozen tree; refreshed
  runs use their new frozen source without changing old report evidence.
- [ ] Branches with more than 200 children page without missing/duplicate rows;
  layout/level changes never trigger download of every branch or recalculate totals.
- [ ] Grand totals and Current hierarchy exports include eligible off-page accounts;
  All ledgers exports include every eligible account once plus explicit parent rows.
- [ ] CURRENT/COMPARATIVE nodes, cursors and totals cannot be mixed.
- [ ] Company/actor changes abort pending reads and clear prior cached financial
  state; stale callbacks cannot populate another company's report.
- [ ] Permission or monetary field denial blocks complete-company output rather
  than silently omitting unauthorized accounts. Check summaries, branches,
  drilldowns, retained history and downloads as well as new report submission.
- [ ] Slow/failed discovery, source preparation, calculation, branch paging and
  exports have separate truthful states and exact idempotent recovery.
- [ ] Accessible disclosure buttons use expanded state and named actions; table
  headers associate each Dr/Cr with its period. Use semantic tables without
  promising an unimplemented spreadsheet/treegrid keyboard model.
- [ ] All three themes, 320px/narrow/tablet/desktop layouts, long names, zoom and
  keyboard focus remain usable; detailed columns scroll within a named region.
- [ ] Older frozen results remain readable/exportable after deployment.

## 7. Verification and evidence

Run affected Reports domain/native/API/worker/recovery/export suites and Console
navigation/workspace/lifecycle/hierarchy/export suites; test any shared UI changes.
Run Ruff, strict mypy, Console/UI TypeScript, OpenAPI/client and presentation bundle
checks as applicable. Native tests use the existing guarded disposable MySQL
runner and random test schemas; fixture tests force the disposable SQLite harness.
Never run destructive fixture setup against a live company database.

Capture browser evidence for both layouts, several expansion levels, paging,
error/retry, keyboard/theme/narrow layouts and actual opened downloads. Use nonempty
disposable/native fixtures to prove amounts and page completeness; existing live
data is read-only evidence. Do not create financial postings merely to populate
screens. Report any unavailable authenticated browser/source configuration honestly.

Walk CLAUDE.md sections 5 and 6 after implementation. Run `/simplify` and
`/security-review` if available; otherwise perform and record their manual review
equivalents, including arithmetic, tenant/company scope, field denies, retained
context, input allowlists, retry/fencing and private artifact access.

Keep an execution record with actual phase status, commands/results, screenshots,
file evidence and remaining limitations. If committing/publishing is subsequently
requested, stage only this task's files and use the configured `git publish`
dry-run/publish workflow while preserving the workspace's original local paths.

## Decision log

- 2026-11-02: user authorized implementation of all six phases in order, followed
  by review and fixes. No intermediate phase approval or publication was requested.
- 2026-11-02: user selected both illustrated layouts with a switch and the first
  (closing-balance summary) as default, and requested a phase-wise implementation
  plan including UI. Proposed six phases covering contracts, frozen hierarchy,
  APIs, dedicated UI, drilldowns/exports and final verification. Variable-depth
  native hierarchy and independent group debit/credit sides implement the existing
  RPT03/BAL04/BAL08 requirements. Planning does not mark implementation complete.
- 2026-11-02: implementation review selected replacing sibling pages and bounded
  cursor history instead of accumulating rows through Load more. Closing/Detailed
  switches still retain expansion and scroll; both export scopes stream off-page
  eligible rows from the same frozen run.
- 2026-11-02: follow-up filter/disclosure review cancels pending child reads on
  collapse, preset and sibling-page changes. Child loading pauses during period or
  quiet-filter refreshes, and hierarchy controls wait until the new root is ready.
  Obsolete requests cannot release newer request reservations; layout switching
  remains independent of those reads.
- 2026-11-02: user authorized database/script/model synchronization. Rehearsed the
  existing Reports 0042 migration on a restored backup, then applied it with migration
  credentials while owned Reports writers were stopped. Existing row counts and
  runtime grants were retained. Reports API/workers were restored; all eight schemas
  now align with their models, migrations and launcher mappings. Broader Reports
  test/coverage release checks remain separate from this completed schema upgrade.
