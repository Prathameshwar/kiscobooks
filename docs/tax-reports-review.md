# Tax reports review

Execution record for [the delivery plan](tax-reports-delivery-plan.md).

## 1. Invoice Tax Register

Complete. Added the dedicated tax workspace, calendar/date-basis/party/registration
filters, full-result invoice/tax search, essential columns, currency-separated
summaries, history, private saved views and shared kebab/detail navigation.
Taxable bases count distinct supply facts instead of repeating CGST/SGST bases.
Summary arithmetic preserves note direction and never mixes currencies/comparatives.
Existing source verification still gates unsupported taxed notes and legal profiles;
reporting does not activate them. Recorded-tax totals are not a filing or tax payable.

The missing taxable value/search/summary regressions failed before implementation.
Verification: 32 invoice/calculation/native query tests, 63 affected UI tests,
18 disposable MySQL checks including positive tax files, company/actor/permission
denial and signed journal navigation; migration/model/index parity and downgrade/
upgrade pass. Strict affected Python and application/test TypeScript checks pass.
Reports OpenAPI and API client 0.2.51 are synchronized.

Live card navigation, native tax-source refresh, search/apply print guard, own
history, saved-view create/restore/delete, Columns and Light/Dark/Ledger at desktop/
mobile widths pass. All four protected files and PDF preview pass with the live
company's genuine empty tax selection. No browser exceptions or page overflow.
Positive tax-source scenarios use disposable schemas, not synthetic live postings.

## 2. Input Tax Credit Register

Complete. Closing positions, Period events and combined detail have distinct
registered views. Currency-separated closing states and event action amounts
never double count. Search and tax-code filters cover the complete selected
history. The As of calendar and filters share the compact workspace controls.
Late-posted VERIFY evidence does not backdate eligibility; both committed posting
and event dates must fall within the position cutoff.

Missing position/code regressions failed before implementation. Verification:
64 affected UI tests, strict affected Python and application/test TypeScript,
26 disposable MySQL checks with actual credit files, native/reference parity and
migration/model/index parity plus downgrade/upgrade. The late-evidence regression
and eight credit-focused checks pass. Live view switching, calendars, history,
saved views and optional columns pass. Four actual protected files and PDF preview
pass, with desktop/mobile review in all three themes. No browser errors or page
overflow; populated amount scenarios use disposable verified native data.

## 3. Tax to Ledger Reconciliation

Complete. Added tax ledger and posting-purpose
filters, full-result ledger search, verified row counts and currency-separated
debit/credit/net movement. Negative net is valid movement, never an invented
mismatch. Ledger IDs must belong to the frozen company source. Business names
are consistent across workspace, history, result title and file metadata.

The missing ledger summary/filter regressions failed first. Source validation
rejects ledger IDs outside the frozen company before publishing a result. Posted
tax-account lines preserve debit/credit side, amount, currency and journal date;
the signed journal drill retains generation and posting scope. Tests cover source
permission revocation, another actor and wrong-company access for all three reports.

Live card, financial source refresh, ledger select/clear, purpose apply/reset,
business/source views, history, saved-view lifecycle and Columns pass. Four real
private downloads and byte-identical PDF preview pass. Light, Dark and Ledger at
1440/390 widths pass without browser errors or page overflow. Populated native
fixtures independently verify exact output tax and ledger credit of 20.0000.

## Final shared review

Corrected crowded default print layouts after inspecting populated native HTML:
invoice tax and ledger views have nine columns, including period; credit closing
positions have eleven, and events nine. Full source details remain explicitly
available. Comparative rows retain period labels and current totals do not double
count. Current-period totals are clearly labelled in UI and file metadata.

The live review reproduced clicking Apply before ledger hydration completed.
Regression tests failed first; Apply now waits for scoped reference verification.
The unprepared-tax notice names the actual Refresh tax data control. Journal
navigation preserves the selected credit event view and optional columns without
an incorrect unapplied-filter warning. Row details use a drawer outside the table.
Theme-driven server context refreshes recreated the fiscal-year object and reset
applied selections. A failing rerender regression reproduced the issue; discovery
now depends on the year dates, preserving the applied report when those dates stay
the same. The live loop asserts view/filter and Print readiness after theme changes.

Verification: 80 tax-domain/registry checks, 51 disposable native MySQL checks
(all three reports, closing/event/source-detail exports and comparative CSV/HTML),
migration/model/index parity and downgrade/upgrade. The 51 native checks include
all four file formats with populated values and download-time access revocation.
The final affected UI suite passes all 146 tests across tax pages/workspaces,
Inventory, Stock Summary, native Books, references, exports, navigation and cards.
Strict affected Python, Console application/tax/Inventory/Books/reference test
TypeScript, Reports OpenAPI and API-client generation checks pass. All three
reports pass the final live loop, including applied-filter/view and Print readiness
after each theme change. Twelve actual live CSV/Excel/HTML/PDF downloads and all
three byte-identical PDF previews pass. Identity, Catalog, Accounting and Reports
readiness return HTTP 200; all six managed report/source workers are running.

Manual `/simplify` and `/security-review` equivalents completed against CLAUDE
sections 5 and 6 (slash commands are unavailable in this environment). Reused the
shared workspace, renderer, exact formatters, private export pipeline and verified
sources; no new service, table, dependencies, permission keys or posting path.
Object scope, field/source read denial, actor ownership, signed navigation and
download revocation remain enforced server-side. No unresolved money or access
findings. Amounts remain Decimal strings, currencies stay separate, and selection
uses recorded business dates rather than creation timestamps or current tax policy.

The live company's selected periods contain no recorded tax rows. Positive tax,
credit, late-evidence, ledger and file scenarios use disposable verified native
data; no synthetic operational postings were added to the live company.

Completed 2026-11-02: every report's five-step loop and the final shared review are
complete. No pending item remains within the three-report delivery scope.

## Requested final audit: 2026-11-02

Reviewed all three reports again across calculations, company/actor/source
permissions, date and search filters, views, columns, history, signed navigation,
private exports and print layouts. Corrected four presentation/state findings:

- Restoring a source-detail saved view from a business view dropped reference
  columns. Restoration now validates preferences against the saved target view,
  retaining both selected and deselected columns.
- Changing the view selector changed retained columns before Apply and could
  reveal previously hidden reference columns. Pending column defaults now take
  effect only after the new report succeeds. A failed run retains its displayed
  columns; saving an unapplied view stores the pending selection's defaults.
- Comparative credit-event currency totals lacked an explicit current-period
  caption. The caption now identifies the same current-period basis as the counts
  and verified summary, with comparative rows still available separately.
- Tax-purpose and credit-event labels changed IGST/RCM to Igst/Rcm. Recognized tax
  acronyms retain their casing; credit export metadata also preserves RCM.

Five UI regressions and two export-metadata cases reproduced their stated defects
before fixes. Final affected verification passes 151 UI tests, 82 tax-domain/view
registry tests and 53 disposable native MySQL checks. Native verification includes
all four populated file formats, credit position/event grains, comparative rows,
exact currency amounts, source/actor/company denial, signed journal navigation,
download-time permission revocation, migrations, model/index parity and
downgrade/upgrade. Strict affected Python, Console application/affected test
TypeScript, Reports OpenAPI and generated-client checks pass.

Populated native print review confirms readable nine-column invoice/ledger/event
views and eleven-column closing credit positions, with no page overflow. Manual
simplification and security review found no further calculation or access defect;
the fixes reuse the existing workspace, exact formatters and private export path.

The final stable live pass succeeds for all three reports. It verifies card
navigation, filters, business/source views, unchanged retained columns before
Apply, history, saved source-view reference columns after returning from a business
view, saved-view deletion, optional Columns and the actual Print / PDF control.
Twelve CSV/Excel/HTML/PDF files download successfully; all PDF preview bytes match
their downloads. Light, Dark and Ledger at desktop/mobile widths retain applied
filters, the selected view and Print readiness without browser errors or page
overflow. The live company has no matching tax rows; populated amount and file
scenarios remain independently verified in disposable native databases.

Final audit complete. No unresolved finding remains within these three reports.
