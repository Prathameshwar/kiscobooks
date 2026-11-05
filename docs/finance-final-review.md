# Finance reports: final review and fix backlog

Reviewed 2026-11-03. Scope: all 22 cards in `/reports/finance`, including the
previously delivered Trial Balance, Profit and Loss and Balance Sheet, and all
registered views used by these screens. The original review was read-only. The
user subsequently authorized fixes; the implementation and validation record is
below. The findings retain their original evidence for traceability.

P1 means incorrect or misleading financial results/downloads or reconciliation
work; P2 means a broken workflow or material presentation issue. Findings below
distinguish reproduced behavior from findings established by reading the code.

## Confirmed bugs

### F01 — P1: payment and receipt totals add reversals

**Reports:** Payment register; Receipt register.

`BookSummary.add` adds every tender's unsigned `amount`. The report rows correctly
retain `signed_amount` and reversal lineage, but the summary card labelled
**Total amount** does not use them. A payment of 40 followed by its complete
reversal produces rows -40/+40 and a displayed total of **80**, instead of a net
payment of zero. The same accumulator serves receipts. Voucher/instrument counts
also include the reversal without identifying it separately.

**Evidence:** reproduced with the existing reversed-bank-instrument fixture through
the real payment calculation and summary function.
[book_summaries.py:73](../apis/reports/src/reports/domain/book_summaries.py#L73),
[NativeBookWorkspace.tsx:560](../mfes/apps/console/app/components/NativeBookWorkspace.tsx#L560).

**Fix:** define net payment/receipt totals with the appropriate tender direction;
show reversal/gross counts separately if useful. Test full and partial reversals,
multiple tenders, comparative rows and multiple currencies.

### F02 — P1: the unmatched-bank worklist includes reversed and matched items

**Report:** Unmatched bank transactions.

The worklist computes the latest instrument event but does not exclude or classify
`REVERSED`. A fully reversed 40 instrument remains `BOOK_ONLY` with a residual of
40. Fully matched bank and book rows with zero residual also appear in this report,
whose card describes transactions awaiting reconciliation. There is no visible
status filter to separate pending work from completed activity.

**Evidence:** both cases reproduced using real bank fixtures. The cancelled item
was reported as 26 days old and awaiting work.
[registers.py:481](../apis/reports/src/reports/domain/registers.py#L481),
[registers.py:561](../apis/reports/src/reports/domain/registers.py#L561).

**Fix:** remove reversed items from actionable residuals; default to genuinely
unmatched/partially matched items. If completed activity is needed, expose it as
an explicit filter and label it accurately. Test dated reversals and later matches.

### F03 — P1: fiscal-year performance defaults can omit imported YTD

**Reports:** Profit and Loss; Income and expenditure.

Both screens move the fiscal-year start forward to the snapshot's detailed-history
start. The backend deliberately includes imported YTD only when the requested
start is the originating fiscal-year start. The UI adjustment therefore disables
valid imported YTD, even though the financial source supports the full-year result.
Profit and Loss also makes this adjustment during refresh/recovery.

**Evidence:** a UI probe requested 2026-04-01 but submitted 2026-10-31. With the
existing YTD fixture, the real backend returns net **260** for 2026-04-01 and
**160** when the start is changed to its 2026-04-02 history boundary. The missing
100 is the imported YTD amount, for both reports.
[NativeBookWorkspace.tsx:97](../mfes/apps/console/app/components/NativeBookWorkspace.tsx#L97),
[FinancialStatementWorkspace.tsx:146](../mfes/apps/console/app/components/FinancialStatementWorkspace.tsx#L146),
[FinancialStatementWorkspace.tsx:183](../mfes/apps/console/app/components/FinancialStatementWorkspace.tsx#L183),
[opening_coverage.py:24](../apis/reports/src/reports/domain/reporting/opening_coverage.py#L24).

**Fix:** preserve the requested performance period and let verified YTD coverage
determine eligibility. If the period is unavailable, explain that without silently
changing it. Disclose imported amounts only when they are actually included.

### F04 — P1: download links can belong to a different displayed result

**Reports:** Trial Balance and the 19 NativeBookWorkspace finance reports.

After exporting result A, opening result B from finance history updates rows and
dates but leaves A's prominent **Download report / Print preview** links in place.
The shared `selectRun` path also leaves them when drilling into another result.
Trial Balance's `retain`, Apply and refresh paths likewise do not invalidate the
previous export; changing its hierarchy also leaves the earlier export visible.
Profit and Loss/Balance Sheet explicitly clear their exports and avoid this case.

**Evidence:** UI regression probe exported A, opened B, verified B's rows, and
confirmed A's download link was still present. Trial Balance verified by code path.
[NativeBookWorkspace.tsx:340](../mfes/apps/console/app/components/NativeBookWorkspace.tsx#L340),
[NativeBookWorkspace.tsx:604](../mfes/apps/console/app/components/NativeBookWorkspace.tsx#L604),
[TrialBalanceWorkspace.tsx:123](../mfes/apps/console/app/components/TrialBalanceWorkspace.tsx#L123).

**Fix:** bind export state to the result ID and exported presentation. Clear it
when that selection changes, or explicitly label it as an older export with its
dates and view. Cover in-progress exports completing after a selection change.

### F05 — P2: wide PDF bands lose the identity of financial rows

**Reports:** the 18 default finance views with more than eight columns; Income and
expenditure and the eight-column Balances by party views are not affected by this
particular banding issue.

The PDF renderer repeats only column zero across bands. These finance views put
`period` or `row_kind` first. Subsequent pages therefore contain amounts against
labels such as `CURRENT`, with no invoice reference, account or stable row number.
Page breaks and varying text heights make cross-page matching particularly fragile.

**Evidence:** generated a two-invoice Sales register PDF. Page 1 contains both
invoice references and customers; page 2 contains currency, commercial amount,
tax and payable, but neither invoice reference nor customer.
[pdf_layout.py:144](../apis/reports/src/reports/rendering/pdf_layout.py#L144),
[finance_views.py](../apis/reports/src/reports/domain/reporting/finance_views.py).

**Fix:** declare report-specific identity columns repeated in every band, with a
stable row identifier where needed. Test extracted content and visual readability
on multipage invoices, ledgers, ageing, bank evidence and settlement reports.

### F06 — P2: direct links to retained reports depend on new-run availability

**Reports:** all 19 NativeBookWorkspace finance reports, including account-ledger
links opened from Trial Balance, Profit and Loss and Balance Sheet.

The auto-load effect returns when `run_enabled` is false or no current generation
was discovered, before checking `initialRun`. A completed retained report can
therefore fail to open even when reading it is allowed. Discovery can also prepare
a new snapshot before attempting to open an explicitly requested retained result.

**Evidence:** UI probe with `run_enabled: false` and a valid retained run confirmed
that the run-detail GET was never sent. Manual history is a possible workaround;
the defect is in direct-link loading.
[NativeBookWorkspace.tsx:210](../mfes/apps/console/app/components/NativeBookWorkspace.tsx#L210),
[NativeBookWorkspace.tsx:497](../mfes/apps/console/app/components/NativeBookWorkspace.tsx#L497).

**Fix:** handle retained-run loading before new-run discovery/preparation gates;
validate the retained run and its own source independently.

### F07 — P2: report drilldowns lose print/export actions

**Reports:** account-ledger drilldowns from statements and drilldown results shown
inside any of the 19 NativeBookWorkspace finance screens.

Both export controls require `!run.origin`. A completed account ledger opened from
a financial statement therefore has no Export or Print/PDF action even for a user
with `report.export`. Rerunning the ledger as a new root report is required to
recover these controls.

**Evidence:** UI probe with a completed account-ledger child run confirmed the
Print/PDF button is absent.
[NativeBookWorkspace.tsx:655](../mfes/apps/console/app/components/NativeBookWorkspace.tsx#L655).

**Fix:** calculate export capabilities/counts for the displayed child result and
allow exporting its frozen rows while keeping parent navigation intact.

### F08 — P2: older Profit and Loss / Balance Sheet history is unreachable

**Reports:** Profit and Loss; Balance Sheet.

History fetches `limit=20`, renders that page, and never consumes `next_cursor`.
Once a company has more than 20 runs, users cannot browse older completed reports
through these screens. This is confirmed in the shared component; no live history
records were created for the review.
[FinancialStatementWorkspace.tsx:266](../mfes/apps/console/app/components/FinancialStatementWorkspace.tsx#L266).

**Fix:** add bounded Older/Next history navigation and preserve the selected
report's dates/view when opening it. Include mixed completed/failed runs in tests.

### F09 — P2: source recovery remains inconsistent in the three main statements

**Reports:** Trial Balance; Profit and Loss; Balance Sheet.

Their preparation functions attempt only REFRESH when a prior generation exists.
A quarantined incremental chain therefore returns the same generic preparation
error on repeated attempts. They do not have the bounded FRESH fallback added to
the other finance screens. Their terminal report messages also describe every
BLOCKED result as snapshot verification failure, including the new deployment
mismatch code `REPORT_IMPLEMENTATION_UNAVAILABLE`.

**Evidence:** inspected both preparation and terminal-error branches. This is a
code-confirmed gap; no production generation was rebuilt during this review.
[TrialBalanceWorkspace.tsx:91](../mfes/apps/console/app/components/TrialBalanceWorkspace.tsx#L91),
[TrialBalanceWorkspace.tsx:129](../mfes/apps/console/app/components/TrialBalanceWorkspace.tsx#L129),
[FinancialStatementWorkspace.tsx:122](../mfes/apps/console/app/components/FinancialStatementWorkspace.tsx#L122),
[FinancialStatementWorkspace.tsx:153](../mfes/apps/console/app/components/FinancialStatementWorkspace.tsx#L153).

**Fix:** share bounded recovery and failure classification across all finance
screens, preserving dates and source verification. Never rebuild for an
implementation-version mismatch.

### F10 — P2: From date implies a filter that two reports do not apply

**Reports:** Invoice settlement register; Bank balance agreement.

Both expose From/To dates and display the result as that period. Settlement history
selects all allocations posted on or before To, including those before From.
Bank balance agreement similarly computes the as-of book/instrument position
without using From to restrict it. The as-of calculations are defensible; the
current input and period labels misrepresent their meaning.

**Evidence:** a settlement request for April 2027 returned an allocation dated
2026-04-03. The bank agreement path is explicitly as-of in the implementation.
[invoice_registers.py:252](../apis/reports/src/reports/domain/invoice_registers.py#L252),
[registers.py:247](../apis/reports/src/reports/domain/registers.py#L247),
[finance-workspace.ts](../mfes/apps/console/app/lib/finance-workspace.ts).

**Fix:** use a clear As-of contract and caption for cumulative history/control, or
implement an explicitly separate period-activity filter without changing balance
semantics. Keep API, UI, export headings and comparative behavior consistent.

## Usability and consistency gaps

- **G01 — snapshot freshness:** all three screen implementations choose a READY
  snapshot without comparing it with current owner progress. The newer finance
  screens show the earliest history date but no captured-at timestamp. A valid old
  snapshot can look current. Add visible capture time/staleness and a defined
  automatic refresh policy for new runs; preserve retained historical results.
  See `NativeBookWorkspace.tsx:210`, `FinancialStatementWorkspace.tsx:109`, and
  `TrialBalanceWorkspace.tsx:160`.
- **G02 — finding rows at scale:** the 19 finance screens only page 50 rows at a
  time; they do not expose the existing result-query search/sort mechanism. Add
  report-specific reference/account/status search and sorting where appropriate,
  retaining the backend's original-balance semantics. See
  `NativeBookWorkspace.tsx:251` and `domain/reporting/navigation.py:141`.
- **G03 — bank-session selection:** choosing a finalised session updates only its
  ID. It does not populate or validate its exact dates/currency against the other
  filters, although the calculation requires all of them to match. A valid session
  selected with default fiscal-year dates can consequently fail during execution.
  Populate session-owned fields and show scope conflicts before submitting; bank
  pickers should also restrict choices to bank accounts. See
  `FinanceSessionReference.tsx:26`, `NativeBookWorkspace.tsx:575`, and
  `registers.py:335`.
- **G04 — invoice selection uses internal UUIDs:** component and settlement
  primary filters expose an invoice ID text field because the reference map has
  no invoice source. Add a scoped picker displaying invoice number, party and date.
  This also applies to the advanced invoice filters on sales/purchase registers.
  See `NativeBookWorkspace.tsx:49` and `NativeBookWorkspace.tsx:584`.
- **G05 — Income and expenditure zero rows:** unlike Profit and Loss, it has no
  zero-account control, and the underlying profit calculation emits all nominal
  accounts. Add a default-off Include zero accounts option and retain totals and
  nonzero imported-YTD disclosures. See `statements.py:315`,
  `schemas/report_parameters.py:73`, and `finance_views.py:314`.
- **G06 — frozen display consistency:** finance table cells use `run.display`, but
  summary money and period/history captions use current display context. Opening
  retained results after display preferences change can give inconsistent formats
  between summary, rows and export. Use the retained configuration throughout the
  completed report. See `NativeBookWorkspace.tsx:514`, `:534`, and `:664`.

## Report-by-report review coverage

All rows below also need the common snapshot freshness review (G01). “Shared”
means F04/F06/F07 in the NativeBookWorkspace lifecycle; F07 applies when viewing
or opening a drilldown. “PDF” means F05 for the default view. These are shared
defects counted once above, not separate bugs per card.

| Report | Views reviewed | Bugs and gaps requiring attention |
|---|---|---|
| Trial Balance | Closing balances; Opening and movement | F04, F09; downstream ledger F06/F07. History should filter by report code before paging. |
| Profit and Loss | Statement; Period comparison | F03, F08, F09; downstream ledger F06/F07. |
| Balance Sheet | Standard; Comparative | F08, F09; downstream ledger F06/F07. No additional balance-equation defect confirmed. |
| Income and expenditure | Statement | F03, Shared; G02, G05, G06. |
| Account ledger | Transactions | Shared, PDF; G02/G06. No additional running-balance defect confirmed. |
| Day book | Posted journal entries | Shared, PDF; G02/G06. Current-period debit/credit summary checked. |
| Party ledger | Transactions | Shared, PDF; G02/G06. Role/currency and open-item reconciliation reviewed. |
| Cash book | Cash transactions | Shared, PDF; G02/G06. Account-kind restriction and running balances reviewed. |
| Bank book | Bank transactions | Shared, PDF; G02/G06; restrict picker to bank accounts. |
| Account summary | Period movement, Day/Month | Shared, PDF; G02/G06. Opening/carry and ancestor group totals reviewed. |
| Outstanding bills | Bill detail; Balances by party | Shared; PDF on detail view; G02/G06. Debt, credit, dated allocations and currencies reviewed. |
| Advances | Unapplied credits; Balances by party | Shared; PDF on detail view; G02/G06. Credit-only selection and exact net amounts reviewed. |
| Receivables/payables ageing | Ageing matrix | Shared, PDF; G02/G06. Due-date boundaries and unknown-date bucket reviewed. |
| Payment register | Payment detail | F01, Shared, PDF; G02/G06. |
| Receipt register | Receipt detail | F01, Shared, PDF; G02/G06. |
| Bank balance agreement | Balance agreement | F10, Shared, PDF; G03/G06. Control remains diagnostic, not finalisation. |
| Finalised bank reconciliation | Session evidence | Shared, PDF; G03/G06. Frozen session membership/control checks reviewed. |
| Unmatched bank transactions | Unmatched worklist | F02, Shared, PDF; G02/G03/G06. |
| Sales register | Invoice register | Shared, PDF; G02/G04/G06. Original/reduction signs and document-currency totals reviewed. |
| Purchase register | Supplier invoice register | Shared, PDF; G02/G04/G06. Supplier charges/differences and reductions reviewed. |
| Invoice component register | Components and allocations | Shared, PDF; G02/G04/G06. Separate component/allocation amounts reviewed. |
| Invoice settlement register | Settlement history | F10, Shared, PDF; G02/G04/G06. Allocation/reversal dates and as-of activity reviewed. |

## Evidence and suggested fix order

Review probes are under `.tools/finance-final-review/`; they use synthetic/existing
test fixtures, not live customer data. `backend-probes.json` contains the monetary,
bank, YTD, settlement and PDF observations. `sales-bands.pdf` is the sample export.
The baseline review run passed **81 tests** across finance view contracts, book
summaries, Profit and Loss/Balance Sheet presentations, Trial Balance calculations,
money reports, native open items and native statement calculations. Output:
`.tools/finance-final-review-baseline.log`.
The four new UI assertions all failed for the intended defects (F03, F04, F06,
F07). Their test file was moved out of the normal test suite after the review;
the probe source and output logs remain available for the fix phase.

1. Fix F01/F02/F03 financial interpretation and F04 download binding first.
2. Fix F09 recovery and F06/F07/F08 retained-result navigation/export.
3. Fix F05 PDF identity and F10 date semantics.
4. Address G01-G06 with report-specific interaction and export checks.

The existing end-to-end export smoke tests check PDF signatures and workbook/CSV
structure; those checks do not detect semantic reversal totals, imported-YTD UI
requests, stale download binding or PDF cross-band identity. Add regression tests
for the findings above rather than relying on the previous green smoke tests.

## Fix execution (authorized 2026-11-03)

1. Correct reversal totals, bank residuals, fiscal-year dates and export binding, with regressions.
2. Repair retained-run navigation, history, automatic preparation and frozen display.
3. Improve PDF identity bands, as-of filters, reference selection, search and zero rows.
4. Run the affected backend/UI suites, review security and correctness, then restart the affected runtime.

### Implemented corrections

| Finding | Change |
|---|---|
| F01 | Tender totals use signed journal amounts, with payment direction inverted to express net paid. Voucher counts explicitly include reversals. |
| F02 | The unmatched worklist excludes fully matched residuals and instruments reversed on or before the selected date. |
| F03 | P&L and Income and Expenditure preserve the fiscal-year start, allowing eligible imported YTD. Recovery preserves user dates, including Trial Balance. |
| F04 | Selecting another result or changing Trial Balance presentation clears its export and cancels polling. Late results cannot restore an obsolete download. |
| F05 | Wide PDFs repeat a business reference and stable row number in every band, with company and period metadata. |
| F06 | Retained finance reports load before new-run availability/source-preparation gates. |
| F07 | Drill-down results expose exports using their completed view, correct row counts and target definition. |
| F08 | Statement history supports cursor-based older pages. Trial Balance filters history by report code before pagination. |
| F09 | All finance screens share bounded incremental-refresh/full-rebuild recovery, preserve pending build identity and distinguish implementation failures from source verification failures. |
| F10 | Bank balance agreement and settlement history use version-6 as-of contracts. Cumulative captions and exports use “As of”, including retained results. Settlement comparisons compare cumulative positions at two dates. |
| G01 | The source API exposes the immutable cut's verification timestamp. New calculations refresh a known snapshot older than five minutes when the actor can prepare sources; retained runs remain frozen. Missing legacy timestamps are labelled unavailable. |
| G02 | Finance workspaces expose bounded worker-backed prefix search, exact status/type/currency filters and typed sorting. Selected-result exports retain original running balances and explain this explicitly. |
| G03 | Verified reconciliation sessions populate and lock their dates/currency. Bank and cash account selectors use the corresponding owner filter and validate retained choices. |
| G04 | Invoice filters use a company-scoped, cursor-paged picker with invoice reference, type, posting date and currency. Its search is explicitly limited to the loaded page; Load more preserves bounded reads. |
| G05 | Income and Expenditure uses version-6 parameters with Include zero accounts off by default. Totals and nonzero imported-YTD disclosures remain intact. |
| G06 | Completed report money and period captions use retained display settings. History-list timestamps remain navigation metadata formatted with current preferences. |

### Review boundaries

No ledger postings, migrations, role grants or accounting facts are changed. The
new invoice proxy routes allow bounded company-scoped GETs only; owner permission
and field-policy checks remain authoritative. Source preparation retains its
existing manage permission and idempotency keys. Money stays Decimal in the
backend, and row selection never recalculates balances or mutates its parent.
PDF text continues through the escaped renderer; downloads remain private.

The `/simplify` and `/security-review` commands are unavailable in this session.
Equivalent manual reviews cover the touched state transitions, shared recovery
helper, tenant/company boundaries, input allowlists and money invariants.

Validation completed on 2026-11-03:

- Broad backend regression: 77 passed. Final execution, review, query, API and
  registry suite: 100 passed, including all 19 native finance reports, their 21
  views, drill-downs and PDF/Excel/CSV exports. These suites overlap.
- Final console regression: 241 passed across 14 files, including Trial Balance,
  P&L, Balance Sheet, native books, finance filters/recovery, reference pickers
  and shared inventory/analytics/tax workspaces.
- Browser layout checks: 2 passed, covering every native finance view at desktop
  and mobile widths, both themes, and expanded filters; GST setup card layout
  also passed. Representative mobile/desktop screenshots and a wide PDF band
  were inspected manually.
- Ruff, strict mypy (9 source files), console TypeScript, Reports OpenAPI drift
  and generated Reports client checks passed.

Logs are under `.tools/finance-fixes-*.log`; corrected monetary/PDF probes are
under `.tools/finance-fixes/`. Browser screenshots are under
`.tools/finance-review/`. These are fixture-based checks, not validation of live
customer accounting data. The original review evidence is preserved separately.

Reports API, dispatcher, short/bulk calculation workers, PDF render worker and
console were restarted after validation. Reports readiness returned `ready`, all
six reporting/source workers were running, the finance route returned its
expected unauthenticated sign-in redirect, and the full launcher health check
reported every component UP, including audit delivery.
