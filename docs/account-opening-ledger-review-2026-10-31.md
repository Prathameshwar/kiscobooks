# Account opening and account ledger review - 2026-10-31

This review found **2 Low bugs and 4 Medium gaps**. No new Critical or High
financial defect was confirmed in the reviewed paths. Application code, financial
data, permissions and deployed configuration were not changed. Nothing was
committed or published. Review documents and replayable diagnostics were added.

The complete records are in [findings.csv](testing/account-ledger-review/findings.csv)
and [cases.csv](testing/account-ledger-review/cases.csv). Severity describes the
current impact; complexity describes the likely implementation effort.

Follow-up: [the account-opening fixes](account-opening-fixes-2026-10-31.md) address
AO-B01 and AO-B02, including the related date surfaces and a restricted-finalization
label found during implementation review. The original review/evidence below is
retained; the CSVs track current verification and status. AL-G01 through AL-G04
remain pending account-ledger work. The saved UI probes now assert fixed acceptance
behavior; Reports probes continue to reproduce the remaining ledger gaps.

## Findings

| ID | Category / severity | Finding | Complexity |
|---|---|---|---|
| AO-B01 | Bug / Low | Opening document and history dates bypass company date/datetime formatting. | Low |
| AO-B02 | Bug / Low | A failed posting-link lookup can display "Draft not prepared" for a finalized opening. | Low |
| AL-G01 | Gap / Medium | Same-day ledger ordering lacks the native owner commit sequence specified by the design. | High |
| AL-G02 | Gap / Medium | Ledger particulars omit journal/line narration and human source explanation. Some voucher lineage and drilldown already work. | Medium |
| AL-G03 | Gap / Medium | Journal-filtered results display correct full-ledger balance-at-row without explaining that scope or giving separate filtered totals. | Low |
| AL-G04 | Gap / Medium | The ledger view lacks a period gross-debit/gross-credit/closing summary for its pinned result. Separate daily and period summary reports already exist. | Medium |

AO-B01 reproduces with `dd/MM/yyyy` configured: document evidence still shows
`2026-03-25 / 2026-04-05`. History additionally renders raw captured/finalized
timestamps and opening/coverage dates. Use the shared date and datetime formatters,
preserving unknown/restricted states and native stored dates.

AO-B02 reproduces when `/posting-link` returns 503. The component shows the lookup
error and "Draft not prepared" together. The native API already distinguishes a
successful `NOT_PREPARED` result; the UI should distinguish loading, unavailable,
unprepared and posted states without assuming anything about financial state.

AL-G01 concerns presentation and provenance, not incorrect closing arithmetic.
Current ordering `(posting_date, journal_id, line_sequence, line_id)` is stable and
its pagination tests pass, but journal identity is not native commit order. A draft
created earlier can be posted later. Reports ingestion sequence is also not a
substitute for owner commit sequence.

AL-G02 is visible in the generated ledger row and its definition: native journal
and line descriptions are retained by Accounting but omitted from report output.
Existing numbers, kinds, monetary values, some voucher lineage and report
drilldowns remain useful. Complete protected particulars and owner handoffs rather
than replacing the existing report framework or inventing unavailable evidence.

AL-G03 reproduces in both the reference calculation and the production native
query over disposable source evidence. The displayed balances equal their full
account-ledger counterparts. Opening plus only the displayed journal's movements
does not necessarily equal that balance because earlier movements are omitted.
This requires clear full-ledger balance-at-row labelling and separate filtered
turnover, or a movement-only view without running balance. No incorrect arithmetic
was demonstrated.

AL-G04 should reuse existing daily/period summary calculations under the same
frozen source, currency and permission scope. Never calculate a supposed full-period
total by adding only the current UI page. This follows the balance definitions in
[the recording design](voucher-account-recording-design.md#4-balance-definitions-and-running-ledgers)
and the shared table rules in [the design system](design-system.md).

## Confirmed implemented behavior

The existing [opening review implementation](account-opening-review-implementation.md)
was checked rather than treating its resolved findings as still open. Current
coverage includes:

- Exact captured opening declarations, immutable revisions, bounded import and
  chunk preparation, historical FX carrying values, explicit YTD coverage and
  unknown-age on-account evidence.
- Native posted-only journals, current fiscal/period checks, durable owner
  reservation/confirmation, reconciliation, genuine zero opening, partial-post
  recovery, retained original/reversal history and linked replacement.
- Separate controller capture/prepare and native posting authority; company,
  tenant, field, replay and export protection; current worksheet conflict/reload.
- Frozen Reports generations, account/group/party/role/cash/bank selection, BASE
  and transaction basis, opening/running balance, bounded cursor/export ordering,
  backdated append stability and daily/year continuity.

The compatibility Accounting `/ledger/balance` endpoint is a cumulative as-of
balance. It is not the period ledger; Reports supplies the richer dated ledger.
The current balance security rule deliberately requires both original and base
monetary field permissions. This conservative behavior is explicitly covered by
the existing ledger tests and was independently reproduced with valid scoped
field policies. It is **not counted as a bug**, and this review does not recommend
relaxing permissions without a policy decision.

## Verification and limits

- Accounting domain/metadata baseline: **54 passed**.
- Console opening, recovery, imports, permissions and continuity baseline:
  **115 passed**, 9 test files.
- Reports native-ledger, opening-effect, daily, migration-mode and continuity
  baseline: **31 passed, 1 MySQL-only test skipped**.
- New diagnostics: **2 UI reproductions passed**, **2 Reports reproductions
  passed**, and **1 Accounting security check passed**. A green
  reproduction means the documented defect/gap was observed; it does not mean the
  future acceptance case passes.
- Fresh migrated MySQL opening lifecycle: **55 passed**, including native
  concurrency and correction/recovery; migrated through Accounting head `0225`.
- Reports native MySQL ledger: **10 passed, no skips**, including the deep indexed
  cursor check. Migration/model/index/constraint parity and downgrade-to-base/
  upgrade-to-head verification passed through Reports head `0038`.
- Direct Accounting ledger API checks: **7 passed**, covering posted-only as-of
  balance, exact post/reversal retries, year continuity, validation/period guards,
  intent recovery, field-denial rollback and native numbering ownership.
- Read-only checks across **12 existing companies** found posted GL totals
  balanced and every posted journal header equal to its native line totals.
  The live data contains only **2 posted journals**, **0 financial-opening
  revisions**, and **2 finalized opening batches**. This small dataset cannot
  establish production-scale or populated live opening coverage.

Native verification used existing guarded runners and fresh randomly named test
schemas; both runners completed successfully and dropped their own test schema in
`finally`. Accounting's native API tests use
real MySQL transactions and existing service-boundary Identity doubles. The
baseline tests use their existing disposable fixtures; UI probes use component
fixtures. No driver-level mocks were added.

This is targeted code/contract, component, native API and read-only persistence
review. A new authenticated browser journey, a real approval/provider outage,
every report export format, a full repository suite and an accounting load test
were not performed. The CSV distinguishes reproduced defects, inspected gaps,
existing passing regressions and future acceptance cases.

Final review validation: both CSVs parse cleanly, all **33 IDs** (6 findings and
27 cases) are unique, all evidence file paths resolve, Python diagnostic lint and
format checks pass, and no temporary probe test files remain. The final replay
passed all five probes. Credentials are excluded from the report artifacts.

## Suggested fix order

1. AO-B02: correct posting-link state labels and retry behavior.
2. AO-B01: apply configured date/datetime display consistently.
3. AL-G03: explain filtered balance scope in UI and exports.
4. AL-G02: complete protected particulars and source navigation.
5. AL-G04: expose a summary for the complete pinned ledger scope.
6. AL-G01: introduce native commit ordering with historical/runtime compatibility.

For High-complexity AL-G01, first define the Accounting commit-sequence contract
and retained-history fallback. Then implement native allocation at commit,
versioned exports/events and projection/index migrations. Finish with a new report
runtime and cursor identity while preserving existing completed reports, followed
by same-day out-of-creation-order posting, rebuild, concurrent commit, snapshot and
deep-pagination tests. No implementation has been authorized by this review request.

## Reuse

From the existing local workspace:

```powershell
& apis/accounting/.venv/Scripts/python.exe docs/testing/account-ledger-review/run_probes.py
```

Use `--only accounting`, `--only reports` or `--only console` to run one group.
The runner copies each diagnostic to a uniquely named test file inside its existing
project harness, and removes that file only if its checksum is unchanged. Logs,
JUnit and Vitest JSON stay in ignored `.test_artifacts`. The existing project
virtual environments and Console dependencies are required. The runner forces
in-memory SQLite for its Python probes regardless of inherited test database URLs.
It does not create tenants or write live financial data.

`cases.csv` is the reusable lifecycle and ledger checklist. For MySQL coverage use
the existing `tools.verify_account_opening_mysql` and Reports `tools.verify_mysql`
runners with their loopback, schema-free server URL environment variables and
appropriate authorized local credentials. They migrate and drop only their own
validated random test schemas. Keep credentials out of reports and command history.
