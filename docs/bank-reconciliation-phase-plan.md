# Bank reconciliation delivery plan (B43)

## Implementation checkpoint (2026-10-13)

The selected mapped-CSV slice now has Accounting-owned mapping revisions, persisted preview
and reviewed imports, row-level duplicate decisions, exact grouped/partial match preview and
commit, compensating unmatch, reviewed opening items, per-account review policy revisions,
frozen statement sessions, and non-posting bank adjustment proposals. A proposal can be
resolved only after the ordinary voucher path commits a matching money intent and its bank
instrument is matched to the statement row. Reports has an evidence-backed final-session
report and a bank/book residual worklist with dated aging; the older balance-only report is
labelled manual. The console offers CSV mapping, preview, review, grouped matching,
proposals, opening items, session history and finalization. Generated API
contracts, field policies, role scopes, outbox audit events and one-table-per-revision MySQL
migrations are included.
Bank reconciliation commands require an active fixed-currency bank account with an explicit
`reconciliation_start_date` on its bank profile; this is the per-account opt-in and cutover.

An overlapping bank export is previewed with duplicate classifications, but its commit is
rejected if another committed statement owns any of the same dates. Operators must obtain
non-overlapping statement periods for the first release; this preserves an unambiguous
opening/closing balance chain. Replaying the identical committed file returns its original
import identity.

Local verification includes the native MySQL migration downgrade/upgrade round trip, focused
Accounting reconciliation tests, Reports suite, console typecheck and console tests. The B43
release status remains `IN_PROGRESS`: B19 is still `PLANNED`, and AC27 still requires a
broker replay rehearsal. Native concurrent import/match tests passed. No live bank feed or automatic financial
posting is asserted.

**Status:** detailed implementation plan, not implementation or release evidence (2026-10-12).
Mapped CSV is the selected first statement format. B43 remains `IN_PROGRESS` with only the
pure CSV and match preflight implemented. Its release dependency on B14/B19 and independent
activation gate remain as recorded in the [delivery tracker](voucher-delivery-tracker.md)
and [Phase 7 contract](voucher-phase7-execution.md). Payroll is excluded.

## Purpose and authority

Deliver bank-statement-to-books reconciliation for an India-based company with multiple bank
ledgers, cheques/PDCs, UPI, NEFT/RTGS/IMPS, transfers, cross-year uncleared items and optional
foreign-currency bank accounts. A statement is third-party evidence, not a posting command.
Accounting owns bank account identity, statement imports, bank instruments, match allocations,
opening BRS, reconciliation sessions and their audit events. Vouchers proposes and executes
ordinary Payment, Receipt, Contra, Journal or refund/correction documents; only its existing
Accounting execution path can create money effects. Reports projects a frozen Accounting
generation; the console is a client of protected APIs. No new service or separate payment GL.

TallyPrime demonstrates imported statement rows, exact/potential and grouped/partial matches,
manual bank dates, opening BRS and unlinking. QuickBooks Online separates feed matching,
categorization/exclusion and statement-period reconciliation with retained session reports.
These are functional references, not storage-model claims or an instruction to auto-post:
[Tally reconciliation](https://help.tallysolutions.com/auto-bank-reconciliation/),
[Tally reports](https://help.tallysolutions.com/bank-recon-reports/),
[QuickBooks bank matching](https://quickbooks.intuit.com/learn-support/en-us/help-article/bank-transactions/match-transactions-quickbooks-online/L0MF3Fn6y_US_en_US),
[QuickBooks account reconciliation](https://quickbooks.intuit.com/learn-support/en-us/help-article/statement-reconciliation/reconcile-account-quickbooks-online/L3XzsllsK_US_en_US).

### Current starting point

| Area | Executable now | Missing for B43 |
|---|---|---|
| Bank book | Immutable `bank_instrument`/`bank_instrument_event`, protected reads and manual dated events; legacy/opening journal-line adoption | Statement-row link, partial clearing semantics and reviewed statement match |
| Input | Bounded `domain/statement_csv.py` parser and `domain/statement_matching.py` allocation preflight | Mapping revision, persistent import/row, overlap dedupe, locking and API |
| Report | Bank book/outstanding derived from owner facts, compared to an operator-entered statement balance | Imported row coverage, frozen session, opening/ending chain and discrepancy provenance |
| Other controls | Party subledger versus GL reconciliation can block period close | This is independent of bank reconciliation; do not silently substitute it |

The existing report's `reconciled = (entered statement balance == expected balance)` is a
**balance agreement**, not row-level statement reconciliation: two missing opposite bank
entries can net to zero. Retain its historical contract until a versioned replacement is
available; label the old result accurately in the UI/API rather than claiming complete
statement coverage. `AccountBankProfile.reconciliation_start_date` has no complete opening
BRS workflow today.

## Shared financial and data rules

1. Scope every row by tenant, company and bank account. An Accounting BANK account must map to
   the selected company bank identity. Statements, matches and sessions are in that account's
   transaction currency. Base-currency GL equivalents and AS 11 FX entries are separate
   reported/accounted facts, never substituted for the bank's currency amount.
2. Keep `posting_date`, instrument date, bank transaction/value date, statement period and
   recorded time separate. A past-year cheque clearing this year does not book the money twice.
   A later import may establish a historical bank date without reopening that date's GL
   period; control this through session amendment/authority, not a fictitious posting.
   New financial corrections use an open, postable period; locked journals are not edited.
3. Bank credit/debit direction must be explicitly mapped to the bank asset's book debit/credit
   direction. Never infer side solely from an unsigned amount or narration. Account, currency,
   direction and residual must match before a proposed or committed allocation.
4. A bank instrument's lifecycle (`BOOKED`/`PRESENTED`/`CLEARED`/etc.) remains distinct from
   allocation coverage and session finalization. A manually entered bank date is marked
   `MANUAL_EVIDENCE`, never represented as a linked imported statement row. A partly matched
   instrument has a positive residual; it cannot be described as fully reconciled merely
   because its existing whole-instrument event says `CLEARED`.
5. Statement import, matching and unmatching create no journal line, bill allocation or stock
   movement. Missing entries, interest, charges, returns, dishonours and transfers become
   proposals for authorized common vouchers. No automatic balancing journal is permitted.
6. Every mutation is idempotent and audited in the owner's transaction. Source files/narratives
   are protected data; logs and audit payloads hold references, hashes and changed-field
   evidence, not raw bank descriptions or full account numbers. Read and export policies apply
   to statement rows, matches, sessions and reports.

## Proposed persisted grains

These are Accounting-owned candidate tables; finalize names and indexes with the existing
model/migration conventions, one DDL statement per revision. Reuse existing journal,
instrument, account, fiscal, outbox and idempotency tables rather than duplicating them.

| Grain | Required identity and retained evidence |
|---|---|
| `bank_statement_mapping_revision` | Bank account, file format/encoding/delimiter, header/date/decimal/debit-credit convention, currency and effective revision; immutable after used |
| `bank_reconciliation_policy_revision` | Per-account manual/suggestion mode, bounded match date window, exact-reference normalization, candidate ranking and maker-checker rule; no baseline auto-post or auto-match commit |
| `bank_statement_import` | Account, mapping revision, file hash, source artifact reference, reported opening/closing and date range, uploader/reviewer, preview/committed/rejected status and counts |
| `bank_statement_row` | Import/source line, bank transaction and value dates, direction, exact amount/currency, protected reference/narrative, external transaction ID, normalized hash, optional running balance and duplicate-review status |
| `bank_opening_reconciliation_item` | Reviewed pre-start book-side uncleared instrument/journal-line identity and residual, original book date, cutoff and source; no new money |
| `bank_match_allocation` plus `bank_match_event` | Statement row, bank instrument/journal line, positive exact allocated amount, bank date, match group, actor, source versions, reason and append-only reversal/unmatch lineage |
| `bank_reconciliation_session` plus frozen membership/control | Account, statement interval, beginning/ending balances, selected import(s), Accounting source barrier/hash, counts and totals, outstanding items, status, reviewer and immutable close/amend history |
| `bank_adjustment_proposal` | Source statement row(s), proposed existing voucher kind/accounting treatment, amount/currency, draft voucher link, approval/rejection and consumed-source guard; never a money row |

Prefer `(company, bank account, external transaction ID)` uniqueness when the bank supplies
a trustworthy ID. Without one, detect overlap by canonical row hash plus date/amount/reference
and require review of true same-day duplicates; a hash alone cannot decide that two equal UPI
payments are the same event. Keep one import of the same file idempotent. Allow an overlapping
export only to add genuinely new observations. Index open rows and allocation residual queries
by company/account/date/status, with keyset paging and bounded candidate windows.

### Candidate protected API contracts

Use established Accounting route conventions and idempotency headers; final names are fixed
in R0 alongside the OpenAPI schemas. All list endpoints have bounded filters/keyset pages.

| Operation family | Command/read purpose |
|---|---|
| `/bank-statement-mappings`, `/bank-reconciliation-policies` | Draft, review, publish and read immutable account-scoped revisions |
| `/bank-statement-imports/preview`, `/bank-statement-imports`, `/bank-statement-imports/{id}/commit` | Validate/map a file, retain a reviewable batch, then commit deduplicated rows |
| `/bank-statement-imports/{id}/rows`, `/bank-reconciliation-candidates` | Protected evidence and ranked, non-committing suggestions |
| `/bank-matches/preview`, `/bank-matches`, `/bank-matches/{id}/unmatch` | Exact allocation check, atomic reviewed commit and compensating unmatch |
| `/bank-opening-items`, `/bank-reconciliation-sessions`, `/bank-reconciliation-sessions/{id}/finalize` | Opening BRS and frozen period review/finalization; explicit amendment command for later evidence |
| `/bank-adjustment-proposals` | Reviewed bank-row-to-existing-voucher draft link, with source consumption guard |

Import preview and candidate reads require bank-statement read authority; commit, match,
unmatch, opening items and session finalization need separate permissions. Export is separate.
Field denies apply to row narratives, references, amounts and generated reports. A bank account
can choose `MANUAL_ONLY` or `SUGGEST_AND_REVIEW` initially; exact matches are never committed
without an authorized review in the first release.

## Phase R0 — contract and regression baseline

**Owner:** Accounting, Reports, Vouchers design. Inventory existing bank profiles, instruments,
manual events, CSV/match helpers, report source grains, voucher correction paths, permissions,
field policies and fiscal close behavior. Freeze a concrete bank debit/credit convention and
the definition of `BOOKED`, `CLEARED`, `MANUALLY_CLEARED`, `PARTIAL`, `MATCHED`, `RECONCILED`
and `SESSION_CLOSED`. Decide which existing event actions remain source facts versus
derived projections; do not silently reinterpret historical events. Explicitly review the
current manual bank-event `posting_period` guard: non-posting historical bank evidence needs
its own session lock/amendment rule, while correction vouchers still require fiscal postability.
Historical `RECONCILED` events without an imported row remain labelled manual evidence;
they require an explicit reviewed cutover basis and are not silently promoted to linked matches.

**Deliverable:** versioned owner/API/event contract, migration sequence, old-to-new report
compatibility rules and failing regression fixtures for false-zero balance, overlapping CSV,
partial matching and cross-year cheque clearing. No release flag changes. **Exit:** reviewers
can trace every proposed new row to an owner, permission, audit event and correction path.

## Phase R1 — reviewed statement ingestion

**Owner:** Accounting. Build mapping revision, import and row storage; preserve the existing
bounded parser as the first-stage validator. Add preview -> reviewed commit commands with
file/mapping hashes, row totals and account/currency/date validation. Support UTF-8 mapped CSV
first, including explicit statement opening/closing balance or a separately reviewed balance
checkpoint. Check line arithmetic when running balances exist. Reject ambiguous sign, mixed
account/currency, changed mapping, duplicate transaction IDs, malformed dates, CSV formula
cells and inconsistent totals. Make overlap results reviewable: imported, existing, ambiguous.

**API shape:** mapping create/revise/list/detail; statement preview; import commit/list/detail;
paginated statement rows and duplicate decisions. Require upload/import/review/read/export
permissions and field policy. Private artifact storage only; no public bank-file URL.
**Exit:** reimport and crash/retry create one set of rows, wrong-company/bank access is denied,
and no import can change GL, instrument state or voucher balances.

## Phase R2 — book evidence and opening BRS

**Owner:** Accounting. Link eligible posted bank journal lines to bank instruments one-to-one
or by exact split tender identity; detect uncovered, duplicated or reversed lines. Reuse
existing adoption only for legitimate legacy/opening lines. Add reviewed pre-start uncleared
items at the bank profile's reconciliation start date, tied to original book evidence.
Support cheques/PDCs, electronic transfers, deposits and cross-year outstanding items.
Manual bank-date clearance is allowed with reason/source and separate `MANUAL_EVIDENCE`
classification. Cleared or matched historical items cannot be cancelled as if they never
reached the bank; corrections retain original linkage.

**Exit:** book-side outstanding totals replay across years; opening BRS adds no second journal;
a current-year statement can match a prior-year cheque; a missing opening item is visible as
a discrepancy, never silently dropped by the start-date filter.

## Phase R3 — suggestions and committed matching

**Owner:** Accounting. Generate bounded, ranked **suggestions** using exact external ID or
instrument reference/amount/side first, then date-window/party/reference heuristics. Keep
suggestions explainable and read-only. Do not copy another product's automatic-post behavior.
Commit reviewed one-to-one, many-to-one, one-to-many and partial allocations using the pure
preflight plus native database row locks in stable identity order. Verify live residuals,
current source versions, account/currency/direction, statement status and bank/session dates inside
the same transaction. Reject over-allocation, duplicate pair and stale preview. Unmatch by
an audited compensating event and restore exact residuals; block unmatching of a finalized
session until an explicit amendment/reopen is authorized.

**API shape:** candidate search, match preview, commit, allocation history and unmatch.
**Exit:** two concurrent workers cannot consume the same row/instrument twice; partial/grouped
matches conserve exact amounts and leave visible residuals; a replay has one effect.

## Phase R4 — statement-period reconciliation and corrections

**Owner:** Accounting with Vouchers for correction proposals. One session covers one bank
account/currency and an explicit statement interval, with a controlled opening balance
chained from the prior finalized session or a reviewed cutover opening. Calculate:

`statement ending = statement opening + imported credits - imported debits`

and independently compare the bank ending balance with book ending adjusted for **dated**
uncleared book receipts/payments and opening BRS. Finalization requires zero monetary
difference, complete disposition of imported bank rows, no over/under allocations, no
unreviewed duplicates and a stable Accounting source barrier. Book-only entries may remain
outstanding with an explicit age/reason; bank-only real entries need an authorized voucher or
a documented unresolved exception, which does not earn a fully reconciled status.

Distinguish `BALANCE_AGREES`, `ROWS_COVERED`, `FINALIZED` and `EXCEPTION_OPEN` in API/report
output. Freeze a session report, row membership and hashes. Late bank files or corrections
create an audited amendment generation; past session output is not rewritten. Proposed
fees/interest/direct payments/receipts/returns use Vouchers' common draft/review/execute
path and source-capped identity. No statement command allocates a voucher number or posts a
journal. **Exit:** a pair of opposite missing bank rows cannot yield `FINALIZED` merely
because the net difference is zero; previous ending and next beginning chain exactly.

## Phase R5 — reports and console workflow

**Owners:** Reports and console, with Accounting as fact authority. Publish frozen,
company-scoped bank-row, book-row, allocation, opening BRS and session facts at one owner
barrier; validate counts, signed totals, residuals and source hashes before a generation is
READY. Provide Banking Activities, imported statement, book-only/bank-only, potential/partial
matches, uncleared aging, reconciled-later, session history and discrepancy reports. Show
bank balance in account currency; show base-currency/AS 11 effects separately. Keep the old
manual-balance report clearly labelled and make a new evidence-backed reconciliation report
version rather than changing historical output silently.

Console sequence: choose bank/account -> upload and map -> preview duplicate/total controls
-> reviewed import -> inspect suggested or manual grouped matches -> prepare correction
voucher where needed -> inspect opening/ending/difference -> finalize/export. UI must show
pending, blocked, partial, wrong-account and stale-source states without inventing a match.
Regenerate OpenAPI and typed clients with each completed API slice. **Exit:** report totals
equal Accounting at the frozen barrier; denied fields stay absent from exports; the operator
can explain each remaining difference by drilling to source evidence.

## Phase R6 — hardening and staged activation

Run affected full suites, strict typing/lint, migrations against disposable native MySQL,
concurrent match/unmatch and import retries, broker/outbox replay, report generation rebuild,
permission/field-deny/tenant isolation and crash recovery. Rehearse two bank accounts, an
overlapping export, same-day duplicate UPI entries, grouped deposits, fees, dishonour,
cheque/PDC clearing after a financial-year boundary, an amended closed session and one
foreign-currency account under the selected AS 11 treatment. Verify `posting_date` and
period locks on every resulting correction voucher. Compare new session output to owner
rows and prove no statement import alone changes GL. Complete AC27 and applicable B45
readiness; record evidence in the delivery tracker/todo. Enable per company only after the
selected B43 scope and upstream B14/B19 gates actually pass. CSV-first does not assert live
bank connectivity, every bank format, or automatic financial posting.

## Phase boundaries and dependency order

`R0 -> R1 -> R2 -> R3 -> R4 -> R5 -> R6`. R1 may ship internally as a protected import
preview without enabling reconciliation. R3 cannot commit against non-persisted R1 rows;
R4 cannot finalize without R2 opening continuity and R3 allocation conservation; R5 can
show partial progress but cannot label it final. B42 Razorpay provider and B44 cheque-book
management remain independent integrations. Their instruments may later provide evidence,
but neither replaces the statement owner, a reviewed match or B43 release proof.
