# Phase 2 execution record

Authorized by the user's instruction to complete the entire next phase uninterrupted with
review. Scope is B10-B14; B09 is already verified. Status: VERIFIED for the ordinary-money
scope recorded below. B01-B14 now total 14 verified parent batches. Activation, publication
and deployment remain separate; Phase 3 starts with B15.

## Ordered work

1. B10: review unfinished sequence work; keep number allocation inside authoritative posting.
   Shared typed money sections, account selection/control, fiscal readiness and owner execution
   with durable prepare/reserve/commit, retries and reversals. Preserve existing balance APIs.
2. B11: atomic partial/multiple bill/advance allocation, reversal/reallocation and dated history.
   Reuse native owner allocation/FX arithmetic and original due dates; no duplicate cash entry.
3. B12: payment modes and instrument evidence/history, book/clearance/reconciliation separation,
   explicit post-dated recognition and current-period guards.
4. B13: Payment/Receipt, split tenders, advances/refunds/on-account balances and native non-tax
   settlement adjustments. Add inputs/configurations to shared voucher storage, not kind tables.
5. B14a-d: ledger/day book/TB, P&L/Income & Expense, Balance Sheet and earnings bridge,
   party/bill/advance/aging/cash/bank registers. Freeze sources, classifications, dates, currency
   and permission scope. Reconcile with owner facts; declare unsupported imported YTD explicitly.
6. Regenerate contracts/clients, integrate common entry/read flows, run native DB/broker and
   affected UI/client checks, review security/correctness and maintain the tracker/todo evidence.

## Implementation guardrails

- Existing Accounting ledger/subledger remains the only money authority. Identity reservation
  and first-use ratchet remain mandatory; external calls never occur inside a money transaction.
- Posted monetary facts and accepted voucher revisions stay immutable; corrections append
  reversals. Company/period fences serialize posting, cancellation, close and competing allocation.
- Ordinary profiles only in this phase: Journal, Contra, Payment, Receipt, bill/advance adjustment
  and manual banking inputs. Tax, stock, external payment providers and payroll remain gated.
- Configurations may narrow supported profiles, account roles, modes and date purposes. Never
  enable unimplemented behavior through a checkbox or custom attribute.
- B09's known unfinished sequence endpoint is in this phase's scope. Replace its independent
  allocation boundary with a reviewed atomic posting integration; record behavior/test changes.
- Existing unrelated Catalog work and local paths stay intact. No commit/publish/deploy is
  authorized. C1 activation is a separate release checkpoint from verified phase implementation.

Resolved implementation contracts, tests, review findings and operational handoff follow.
The verification record preserves original failures and the successful corrected reruns.

## Implemented scope and decision slices

| Batch | Concrete delivery |
|---|---|
| B10 | Ordinary Journal and Contra through protocol v2; exact account lines, live owner account/group/currency validation, fiscal evidence, current Identity reservation, atomic posting numbers, cancellation/recovery and reverse-only correction. Readiness composes existing calendar/opening/period close checks and pending owner work. Existing cumulative balance reads stay compatible. |
| B11 | Selected partial/multiple bill and advance instructions compose with native open-item allocation in the same transaction. Pure allocation records no duplicate cash journal. Native realized FX remains linked to allocation authority. Reversing allocations preserves dated history and original due terms; competing consumption is serialized. |
| B12 | Shared tender mode/reference/instrument-date inputs; native instrument and append-only bank history; manual presentation, dishonour, clearance, reconciliation and unwind. Legacy/opening GL lines can adopt explicit bank evidence through an idempotent guarded API. BOOK_DATE versus MATURITY_DATE recognition is explicit. |
| B13 | Payment/Receipt, advances, refunds, on-account balances, split tenders and bounded non-tax discount/fee/write-off adjustment legs. Purpose, party role, group/account behavior and tracking are enforced. Company/type/class money policy may narrow supported behavior; custom attributes cannot supply posting rules. |
| B14a | Frozen account/party ledgers, day book, cash/bank books, trial balance and daily/monthly account/group summaries with opening, gross turnover, running/closing amounts and exact currency basis. |
| B14b | Profit & Loss and accrual Income & Expense from native head/group classifications, with current/comparative source scopes. |
| B14c | Balance Sheet with entered opening equity, prior untransferred earnings, current-year earnings, TB/P&L reconciliation and retained-history guards. A new financial year derives carry without cloning entered openings. |
| B14d | Outstanding bills, advances, dated aging, payment/receipt registers and bank reconciliation. Tender-grain signed amounts and source lineage prevent join multiplication. Bank booking and statement events remain distinct. |

D01/D04 ordinary money scope uses Accounting's existing company fence and co-located
GL/open-item/allocation authority. Money preparation is durable; Identity reserve/confirm
calls stay outside database transactions. A terminal rejection abandons prepared state
without consuming a number; a transport outage retains the same attempt for reconciliation.
Commit rechecks current authority, period, source versions and cancellation. Generic journal
post/void cannot post or discard a voucher-owned journal. No separate billing/payment ledger
or per-voucher-kind table has been introduced.

D06 selects STANDARD for four money kinds and ADVANCE for Payment/Receipt. Refund and
bill-adjustment purposes are explicit native inputs. Cost-centre dimensions are unavailable
in this slice. Exact foreign-currency inputs require the native policy to enable them;
unsupported profiles and tax/stock fields are rejected. One-tender configuration means one
tender overall, except Contra needs one per transfer account leg. Instrument evidence has
no provider authority and stores references, never raw card details.

D11 selects retained owner history from books-begin, frozen current source classifications
and complete-company base-currency statements. Transaction-currency books require one
selected currency. Missing historical coverage blocks calculations; pre-cutover imported
YTD is not reconstructed. Balance Sheet reports untransferred earnings explicitly rather
than creating an annual profit-transfer entry. Allocation-only changes advance report source
history without inventing GL turnover. Already frozen rows/artifacts are never rebuilt in
place; current authorization is checked whenever they are read or exported.

D12 reuses existing generation/open/close/reopen transitions. Readiness is an assessment,
not a new authorization to post or close. Prepared native money work blocks closure; owner
commit uses the same fence. CLOSED reopening remains authorized/audited; LOCKED is terminal.
Cross-year bills, advances, instrument history and original due dates remain stable. Later
stock/order/tax producer close evidence and automated annual profit transfer remain outside
this ordinary money slice.

## Storage, APIs and synchronization

- Vouchers migrations 0037-0040 create `voucher_financial_detail`, `voucher_account_detail`,
  `voucher_tender` and `voucher_bill_instruction`, linked to immutable common revisions.
- Accounting 0115-0116 extend the journal-kind constraint; 0117-0120 create
  `voucher_money_intent`, `bank_instrument`, `bank_instrument_event` and
  `voucher_money_allocation`. Each migration has one DDL statement. Existing native GL,
  sequence, opening, open-item and allocation structures remain authoritative.
- Public Vouchers post/reverse return a durable operation (202). GET, recover and cancellation
  retain identity after unknown outcomes. Polling selects both POST and REVERSE work. Native
  owner execution/status endpoints remain private and signed with explicit company grants.
  Typed operation reads expose the stable rejection code, without the private command;
  the console explains rejection and prevents reposting an already committed local operation.
- Accounting adds fiscal-year readiness and typed bank list/detail/history/event/adoption
  APIs. Growing lists are scoped keyset pages; history is append-only and event writes use
  expected prior-event identity. Field read/write/filter authority is enforced by the owner.
- Reporting contract 0.2.0 has 19 fact grains and excludes private delegated credentials.
  Vouchers execution client 0.2.0 uses fixed-scale Decimal wire values; billing-platform
  0.30.0 adds explicit field-policy namespace provenance. Identity supplies both Accounting
  and Vouchers namespaces to financial voucher commands. Consuming lockfiles are synchronized.
- OpenAPI, Identity Accounting field metadata and generated TypeScript clients include the
  new contracts. The console provides policy-aware financial entry, operation/reversal
  recovery, financial reports and bank history. There is no mobile application in this repo;
  the portable client is implemented, while mobile release delivery remains a C1 selection.

## Review findings and verification

Manual equivalents of `/simplify` and `/security-review` are used because those skills are
not callable in this session. Reviews walk CLAUDE security and correctness invariants.
Concrete defects reproduced and corrected include:

- B09 exported execution filters read `status` instead of the stored `outcome`.
- Reloaded native Decimal scales changed source fingerprints; canonical money serialization
  now fixes scale without binary floats.
- Unsupported profiles and selected policy constraints could bypass native input checks.
- Legacy receipts did not count new voucher cash when checking the daily party limit.
- Cancellation during Identity reservation could try to abandon already cancelled intent.
- Generic journal post/void and adopted legacy-bank reversal could bypass owner bank guards.
- Readiness could imply close-ready while native owner closing checks still failed.
- Partially failed multi-allocation bundles needed explicit no-effect rollback evidence.
- Report inputs accepted ignored currency/filter combinations; invalid combinations now fail.
- Day book included synthetic opening rows; aging used transaction amounts in base reports.
- Day/month summaries omitted carried balances; money registers omitted tender-grain lineage.
- Split instrument FX required one exact residual; journal/tender joins now use indexed maps.
- BRS accepted party/group filters that could hide bank movements; API and UI now require
  the complete selected bank ledger. The UI also explains BLOCKED report runs correctly.
- Older audit tests assumed six setup events; committed reporting capture adds a seventh.
- The party-source snapshot fixture bypassed company initialization and failed the required
  reporting barrier. It now initializes its isolated company through the public setup API.

Native tests include tenant isolation of every new table, scoped FKs/DECIMAL scale, duplicate
delivery/concurrent execution, cancellation and authority outages, closed periods, one
number/effect, allocation rollback, cash caps, bank history/reversal, live RabbitMQ delivery
and Audit chain verification. A signed cross-service acceptance test posts and reverses an
advance, exports owner facts in bounded pages, reconciles financial reports and proves the
earlier frozen result remains unchanged. Report recovery checks retain the last good
generation, publish no partial failed run, and preserve reading older frozen output.
The money acceptance slice also settles a USD bill at a different receipt rate, verifies
one INR cash movement plus realized FX, and reverses the receipt, allocation and FX atomically.

Verification evidence is local under `.test_artifacts/`; counts below are separate suites
and overlapping acceptance slices, not an additive total. All four failures from the original
Accounting run have successful current native reruns. No unresolved security/correctness
finding remains within this supported phase scope after the manual review.

| Check | Result |
|---|---|
| Platform full suite | 1,034 passed; 97.97% coverage. |
| Vouchers full native MySQL + RabbitMQ | 126 passed; 90.96% overall and 96.79% domain coverage. All 40 migrations, model/index parity and downgrade/upgrade passed. |
| Reports full native MySQL + RabbitMQ | 64 passed; 90.71% overall and 93.26% domain coverage. All 16 migrations and downgrade/upgrade passed. |
| Accounting original full native run | 510 passed, 4 failed, 6 broker-only skipped. The failures were three obsolete setup-event assertions and one uninitialized source-snapshot fixture; corrections are verified in the focused reruns below. The original command exited nonzero and is retained as such. |
| Accounting native money/boundary/profile/readiness/isolation/Audit slice | 71 passed, including 9 live-broker Audit flows; 120-revision model parity and downgrade/upgrade passed. |
| Accounting signed money-to-report acceptance and readiness slice | 6 passed; native migration round trip passed. |
| Accounting foreign-currency settlement and corrected audit assertions | 11 passed; native migration round trip passed. |
| Accounting additional coverage/native broker run | 21 passed, including all 9 live-broker Audit flows, signed money-to-report acceptance, foreign-currency receipt/reversal and corrected audit assertions; migration round trip passed. |
| Accounting final native regression group | 33 passed: source snapshot, money boundaries/profiles/readiness, financial boundaries, allocations, credit and openings. All 120 migrations round-tripped. |
| Accounting bank-read security and source-snapshot correction | 2 passed natively; filter/permission-bound cursors, field protection, company isolation and history pagination; migration round trip passed. |
| Accounting combined final coverage | 95.14% overall and 99.60% domain; configured coverage floors passed. See the baseline limitation below. |
| Console full suite | 328 passed across 29 files; 97.66% lines/statements, 90.52% functions, 85.33% branches; configured thresholds passed. |
| Identity policy namespace/gateway slice | 11 passed; strict typing and Ruff passed. |
| Portable API client | All generated contracts match; TypeScript and all 8 transport tests passed. |
| Static checks | Accounting/shared contracts (125 modules), Vouchers (50), Reports (25) and changed Identity context pass strict mypy; affected Python lint/format, console typecheck, OpenAPI and Accounting metadata/audit/financial manifests pass. |

Reproduction uses each service's `.venv/Scripts/python.exe -m tools.verify_mysql`
(Accounting adds `--full-suite` or `--tests`), with the local disposable MySQL server
and broker configured by the Windows helpers. Full coverage adds `PYTEST_ADDOPTS` with
`--cov=<service> --cov-report=term-missing --cov-report=json:<artifact>`; greenlet/thread
tracing measures async SQL execution. Console uses
`pnpm --filter @janso/console exec vitest run --coverage`; the portable client uses
`pnpm check:generated`, `pnpm typecheck` and `pnpm test`. Credentials stay in local runtime
files/environment and are not included in logs or these notes.

Final Accounting coverage combines the full run with current focused runs. Coverage line
maps from before formatting are discarded for `party_documents.py`, `subledger_posting.py`
and `voucher_money_effects.py`; these files use only their current reruns. Focused measurement
runs do not independently apply the whole-service coverage threshold; the combined report
does. An overlapping ordinary-suite rerun was stopped and contributes no verification or
coverage evidence. The September 15 coverage artifact predates 33 subsequently added modules
and measures 6,912 statements versus the current 10,381; it is not a comparable pre-phase
baseline. No measured before/after overall-coverage comparison is claimed.

## Operational handoff and limits

Deploy compatible shared contracts and Identity policy contexts first, then Accounting
0120, Vouchers 0040, matching owner credentials/permissions, API/workers, Reports and console.
Reports' expanded schema hash requires a fresh generation; old snapshots cannot stand in
for missing instrument facts. Previously frozen outputs remain readable under live policy.
Configure `VOUCHERS_MONEY_EXECUTION_ENABLED` and `ACCOUNTING_VOUCHER_MONEY_ENABLED` only
after the separate C1 release checks. Both default false. Unknown outcomes must be queried
under the original execution identity; never clear them by deleting receipts or creating
another attempt.

PDC recognition is explicit: BOOK_DATE recognizes now; MATURITY_DATE rejects premature
posting. No automatic maturity scheduler, provider transfer, statement import, cheque-book
printing or cash denomination feature is implied. Manual bank events do not write GL.
Tax invoices, GST/VAT, stock, orders, job work and manufacturing remain later phases;
payroll stays excluded. Reports retain B09 bounded snapshots/generations (100,000 facts),
in-database CSV and separate B45 load/retention obligations. Live nginx is absent here;
gateway scope is tested and routing reviewed, with live rollout acceptance still pending.

No real-company database migration, deployment, commit or publication is part of this task.
Disposable native round trips do not authorize production downgrades: journal-kind downgrade
requires no VOUCHER history, and dropping evidence would destroy auditability. Preserve real
history with reviewed forward repairs. Existing local paths and unrelated work are preserved.
The temporary MySQL service on 13396 and local RabbitMQ started for these checks were
stopped after verification; the pre-existing MySQL service on 3306 was not changed.
