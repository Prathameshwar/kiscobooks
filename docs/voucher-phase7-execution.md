# Phase 7 execution contract — selected banking integrations

Status: **B42-B44 IN_PROGRESS, none verified**, 2026-10-11. The user selected
Razorpay, mapped CSV bank statements, and both cheque-book and cash-denomination
controls. These three optional batches remain independently releasable. Phase 6
is incomplete; selecting Phase 7 does not assert C4 or any job-work readiness.

## Authority and release boundary

Vouchers owns provider attempts, verified callbacks and the review workflow.
Accounting remains the only authority for money posting, bank instruments,
statement reconciliation and the financial result. Reports projects committed
Accounting facts. Reuse the shared Payment/Receipt vouchers and common detail
tables; no second payment ledger or voucher header per integration. Provider
confirmation, bank clearance and statement matching are distinct dated states.
No provider call runs inside a money transaction. A provider result can request
one authorized Accounting effect only after amount, currency, account, source,
company and capture status are verified; unknown outcomes remain pending.
Refunds, fees and chargebacks use explicit linked operations, never a mutation
of the original payment. Backdated financial corrections remain subject to the
company's fiscal guards. All new history is immutable, company-scoped, audited
through an outbox and idempotent under retries/concurrency.

## B42 — Razorpay payment provider

1. Define a company-scoped, disabled-by-default Razorpay connection with
   credential references outside the database payload, mode (test/live),
   webhook-secret version, allowed currency, settlement/control accounts and
   permissions. Never store raw card data, full bank account numbers or secrets.
2. Persist intent, attempt and callback receipt identities with source voucher
   revision, exact requested amount/currency, provider order/payment IDs,
   status, request hash, retry generation and correlation. The source hash and
   provider payment ID must each prevent a second effect, even under a fresh
   client idempotency key. Creating an order is an external attempt; timeouts
   resolve as UNKNOWN and require fetch/reconciliation before retry.
3. Razorpay Orders API runs from a bounded worker with allowlisted destination,
   separate test/live credentials and redacted logs. Checkout callback
   verification uses the server-retained order ID. Webhooks verify the HMAC
   against the raw request body before parsing, use a bounded body, and dedupe
   the provider delivery ID durably before acknowledgment. Out-of-order or
   duplicate events cannot regress a captured payment or repost a Receipt.
   An `authorized` event alone is insufficient for capture posting; verify a
   `captured` status and exact amount/currency/order/account. The webhook
   snapshot may lag the current payment status, so query the API for ambiguity.
4. Map confirmed capture to the existing Vouchers execution command, with the
   Accounting source guard as final dedupe authority. Fees, partial/full
   refunds and chargebacks each require source-capped linked commands and
   separate Accounting outcomes. A credit note alone is not a cash refund.
5. Expose protected intent/attempt/receipt histories and operator recovery;
   add generated client and console flows. Acceptance includes signature
   tampering, raw-body whitespace, secret rotation, wrong tenant/order/amount,
   timeout then fetch, callback reorder/replay, double submission, partial
   refund cap, fee/chargeback mapping, failed outbox, fiscal lock, recovery and
   provider test-mode certification. Native DB/broker and controlled Razorpay
   sandbox evidence precede VERIFIED; live rollout is a later activation.

Razorpay's official [integration guide](https://razorpay.com/docs/server-integration/python/test-app/)
requires checkout-signature verification and a captured payment status;
its [payment status guidance](https://razorpay.com/docs/payments/payments/dashboard/)
notes webhook payloads are event-time snapshots. Recheck the exact API/webhook
contract and credentials against the selected Razorpay account before rollout.

## B43 — mapped CSV statement reconciliation

The [detailed B43 phase plan](bank-reconciliation-phase-plan.md) breaks this selected scope
into R0-R6, with persisted grains, owner/API contracts, session controls and exit evidence.
It does not change B43's `IN_PROGRESS` status or enable release.

1. Accounting owns versioned per-bank/account CSV mappings: encoding,
   delimiter, header names, date/amount/side/reference/description/balance
   fields, decimal/date formats and timezone. Require an explicit debit/credit
   convention and bank account/currency; reject ambiguous signs, formulas,
   malformed dates, duplicate columns, oversized files and mixed account files.
   Import is preview → reviewed commit, with file hash, mapping version,
   uploader/approver, source line number, normalized row hash and storage
   evidence. Do not persist raw unmasked bank narrative in audit/logs.
2. Create statement batch/row and append-only match/unmatch evidence. Bank
   account + external transaction ID is the preferred dedupe key; a bounded
   canonical fallback hash with explicit duplicate review applies when the
   export lacks IDs. File reimport and overlapping exports must not create
   duplicate statement facts. Each row's amount is an observation, never a
   voucher or journal.
3. Match one-to-one, many-to-one, one-to-many and partial settlements through
   a guarded allocation table keyed by exact bank row and bank instrument /
   journal-line IDs. Lock the relevant rows in a stable order; cap both sides,
   preserve unapplied residuals and distinguish bank date from booking date.
   Opening uncleared items are imported as reconciliation evidence only, not
   new cash postings. Unmatch appends a reasoned reversal and rechecks residuals.
4. Differences, bank fees and interest become reviewable proposed common
   vouchers; only an authorized posting uses Accounting's existing financial
   command. Reports presents bank ledger vs statement, uncleared/unknown,
   cross-year continuity and an as-of reconciliation using one owner snapshot.
   Console supports upload/mapping/preview, match suggestions, reviewed
   commit/unmatch and protected exports.
5. Acceptance covers duplicate/overlapping files, CSV injection, locale and
   sign ambiguity, wrong company/bank/currency, partial/grouped concurrency,
   opening items, backdated clearance, correction, fiscal crossing, denied
   fields, import crash/restart and owner/report rebuild equality. No automatic
   financial adjustment is allowed from a statement line.

## B44 — cheque-book and cash-denomination controls

1. Accounting owns cheque book and leaf master identities because it owns
   bank instrument history. A book is scoped to company, bank account,
   currency and an inclusive leaf-number interval. Reject overlapping books
   for the same account and duplicate assignment under concurrency. A leaf
   follows append-only events (available/reserved/issued/presented/cleared/
   dishonoured/void) linked to a bank instrument where applicable. Printing
   creates a versioned, protected artifact and cannot issue, clear or post a
   cheque by itself. A voided leaf cannot be reused.
2. Vouchers captures denominations only on configured cash tender lines.
   Native rows record currency, denomination, count, exact subtotal and
   source revision/line; the sum must equal the selected cash tender amount.
   Denominations are evidence, not an extra payment. Reject negative counts,
   invalid denomination/currency, cross-company use, mismatched total and
   post-issue edits. Store only the needed count, not banknote serials.
3. Expose protected book/leaf history and denomination views through generated
   clients and console. Acceptance includes account interval races, duplicate
   leaf assignment, void/reprint, PDC recognition distinction, cancellation,
   two-company isolation, fiscal crossing, exact cash tally and replay. No
   claim of full Tally banking parity follows from these selected controls.

## Execution order and exit

Start with migration/model/schema and exact-domain tests for each selected
owner. Add APIs, permission/field registry, outbox, worker/consumer, generated
clients and console in the same capability slice. Then run native MySQL/broker,
security/correctness, recovery and AC27 reconciliation tests. B42 depends on
B13/B19; B43 on B14/B19; B44 on B12. These batches do not depend on Phase 6
and do not substitute for B45 production readiness. Keep each disabled until
its own complete evidence exists. Update tracker/todo with actual verification;
none is VERIFIED from this plan alone.

## Progress and remaining gates

- 2026-10-11: B42 has pure Razorpay checkout-signature and raw-body webhook
  validation with retained-order/amount/currency checks. Three focused tests
  pass. There is no connection, credential reference, durable intent/attempt,
  callback receipt, worker, owner effect, route or client; B42 is not verified.
- 2026-10-11: B43 has a bounded mapped-CSV normalizer and an exact partial/
  grouped-match preflight. Files without bank transaction IDs require duplicate
  review; duplicate IDs in one file and unsafe rows are rejected. Eleven
  focused Accounting tests for CSV and matching pass. There
  is no mapping version, statement row, allocation lock, import API, report or
  review UI; B43 is not verified.
- 2026-10-11: B44 has cheque-range/leaf-transition and cash-denomination
  validation. Two focused Accounting cheque tests and two Vouchers cash tests
  pass; the full Vouchers suite passes 151 with two skips. There are
  no native book/leaf/denomination rows, artifacts, endpoints or concurrent
  uniqueness evidence. The company-authoritative denomination face policy and
  bank-master lock/ownership contract must precede usable storage/commands;
  B44 is not verified. B19 remains an upstream gate for
  B42/B43. No release activation, commit, publication or provider test-mode
  certification has occurred.

### 2026-10-11 focused correctness review

The pure preflight boundaries were reviewed against the selected provider/bank
contracts. Razorpay webhook evidence now requires the signed payload's merchant
`account_id`, and capture matching requires the configured merchant account in
addition to the retained order, amount and currency. The verifier rejects
ambiguous duplicate JSON keys, non-ASCII currency codes and malformed delivery
IDs. This remains evidence validation only: a future durable callback receipt
must own replay prevention,
provider payment-ID uniqueness, secret rotation and the Accounting effect.

Mapped CSV preview now rejects formula-like values in **every** column (including
unmapped columns), unsafe headers, non-ASCII currency/amount digits and reports
the physical source line after skipped blank lines. Statement-match currency
validation uses the same ASCII boundary. These checks do not replace bank-account
identity validation, mapping versions, reviewed import, overlap dedupe or locked
allocations. Cheque-book preflight now enforces the inclusive 100,000-leaf cap;
native uniqueness and leaf history remain outstanding. Cash denominations were
reviewed and their existing exact-tender tests passed; no cash storage or
company-authoritative face policy has been added. B42-B44 remain IN_PROGRESS,
and none may be activated on this evidence alone.
