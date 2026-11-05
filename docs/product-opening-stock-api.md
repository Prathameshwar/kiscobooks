# Product opening stock API

Opening stock is an Accounting cutover at company books begin. Products, units,
warehouses and tracking definitions remain owned by Catalog; Vouchers retains
drafts, approvals and execution requests. Creating a product or preparing a batch
or serial creates no stock. Opening quantities and values are exact decimal text.

## Workflow

1. Initialize company accounting, its open books-begin period and stock account
   mappings. Publish and activate product/unit definitions effective at cutover;
   use fixed conversions. A revision effective only after cutover is rejected.
2. Read Accounting `GET /v1/companies/{company_id}/stock/openings/capabilities`
   and `/readiness`. Missing setup, closed books, pending owner confirmations,
   legacy activity and disabled admission are separate blockers. Draft preparation
   does not enable posting.
3. Use `POST .../stock/openings/calculate` with product, warehouse, cutover date,
   entered quantity/unit/revision and explicit RATE or VALUE evidence. RATE accepts
   cost per `priced_quantity` (default one); an optional supplied total must agree
   after company rounding. VALUE requires the explicit carrying total. The
   response shows base quantity, value and derived rates and is informational.
   Calculation neither reserves stock nor authorizes a voucher.
4. Register the complete reviewed manifest with `POST .../stock/openings`.
   Every cohort has a stable, case-normalized source key and exact base quantity,
   value, warehouse, optional bin/batch/serial allocation and conversion evidence.
   Retain the returned control ID, expected version and manifest hash.
5. Read `GET .../{control_id}/accounting-preview`. COMBINED shows the remaining
   Inventory Asset debit and Opening Offset credit. LINKED_GL shows planned claims
   against existing GL opening lines and zero additional GL value. This is a
   declaration preview; native posting revalidates products, policies, units,
   financial coverage, period authority and identity availability.
6. Create ordinary Vouchers `STOCK_JOURNAL / OPENING` drafts carrying that control
   ID and precisely the manifest allocations. Existing create/revise/list/detail,
   submit, approval, post, status and reversal routes remain the lifecycle. Import
   can prepare these drafts in chunks; it cannot approve or post them. Native
   prepare quotes the actual ledger under rollback and native commit rechecks
   the quote, configuration, source proofs and opening generation.
7. Deliver retained Identity confirmations through the normal delivery worker.
   Read `GET .../{control_id}/reconciliation`; finalize with
   `POST .../{control_id}/finalize`, current version/hash and a reason. Missing
   cohorts, pending execution, physical/GL mismatch or closed periods block it.
   Ordinary stock posting requires the finalized cutover.

All command routes require an `Idempotency-Key`. Retry an uncertain request with
the same key and body. Recover a native posting through its owner execution
status; do not create a replacement merely because a response was lost.

The company-scoped Stock Operator role includes draft import rights. Financial
Controller authority plus stock configuration is still required to manage a
nonzero cutover; Company Administrator's zero declaration remains narrow.

## Empty books and legacy history

`POST .../stock/openings/confirm-zero` accepts `expected_generation` from readiness
and an explicit reason. Its narrow authority is `opening_balance.initialize_zero`
plus stock read; finance managers may also use it. It requires empty physical
history, reconciled inventory GL and open books. It grants no balance-entry,
period-post, approval, correction or reopening permission. Financial zero opening
and physical zero opening are separate declarations.

Existing native history without a control is never silently initialized.
`POST .../stock/openings/adopt` requires finance management, stock configuration,
`period.post`, an open books-begin period and no later closed or locked books,
`adopt_existing: true`, no new allocations and reconciliation of existing stock
and GL, including completed terminal delivery. It retains existing native facts
and creates no quantities or journal. Its zero declared/applied manifest totals
describe the empty adoption declaration, not the existing company's stock total;
use stock positions/cost pools for that value. Adoption cannot be reopened as a
new opening.

## Accounting and correction

COMBINED creates asset/offset entries once. Existing unclaimed inventory GL
opening debits block COMBINED; use LINKED_GL and explicit eligible journal lines.
LINKED_GL consumes remaining posted opening debit coverage without another asset
journal. Native company locks prevent overclaims. Financial inventory opening
changes also respect the physical cutover fence, including after finalization.
No tax, supplier liability, purchase, sales or balancing plug is invented.

Before dependent trading, reopen a finalized control with its current version and
hash, reverse applied native openings, then replace the unused manifest and post
the replacement through the ordinary approval/execution workflow. Replacement
retains an immutable manifest revision. Reverse later dependent warehouse effects
first; closed books and unresolved reservations/confirmations remain blockers.
After trading, direct edits and retroactive recosting are unsupported. Reversals,
claims and previous manifests remain available as evidence.

## Cohorts and stock rules

- Cost pools are company/product/warehouse FIFO or moving average. Bins and batches
  are physical dimensions, not separate valuation pools.
- Known original receipt dates precede or equal cutover. Unknown age is explicit:
  `history_known: false`, no original receipt date. Selection/history exposes the
  flag; no supplier invoice or historical age is invented.
- Within a warehouse pool, import/post chunks in receipt-date, cohort-order and
  source-key order, using canonical lower-case ASCII comparison rather than locale
  collation. Native posting refuses a later chunk while earlier reviewed
  cohorts remain missing. This preserves FIFO ties across separate commits.
- Prepared identities have no quantity/value until native posting. Serial count
  must equal integral base quantity, with no reuse across the manifest/import.
  Expired, held, retired, wrong-product or wrongly allocated identities are refused.
  Expiry on the cutover date is inclusive. Opening receipts accept unexpired
  batches below the minimum remaining life required for outward issues; the
  native issue policy continues to enforce that threshold on issue.
- Zero value needs explicit voucher configuration and meaningful evidence.
  Missing value is never zero. Negative openings and unsupported custody,
  quarantine, third-party, WIP or transit opening imports are refused.
- Annual continuation uses native remaining positions, origins and warehouse
  costs. There is no annual opening repost or later per-product opening date.

## Imports, reads and budgets

Vouchers prefix: `/v1/companies/{company_id}/stock-opening-imports`.
Endpoints: `GET /template`, `POST /`, `GET /`, `GET /{id}`, and
`POST /{id}/validate`, `/commit`, `/cancel`. `GET /{id}/report-ticket` issues a
five-minute authenticated result-download ticket. Tickets bind actor authority,
company and job version; downloads recheck permission and field policies.

JSON supplies typed native voucher inputs. CSV/TSV/XLSX supplies versioned text
columns from the template and exact native owner IDs; names and ambiguous codes
are rejected. Limits: two MiB decoded source, three MiB upload request, 1,000
cohorts, 10,000 distinct serials and 100 native chunks. Each chunk respects the
native 100-line/1,000-serial operation bound and 200 serials per allocation.
Validation/commit advances at most two chunks per request. Staging is limited to
10 requests/minute and steps to 120; opening controller/calculation commands are
limited to 30/minute per actor/company. Raw source execution expires after seven
days. Immutable source, native effect receipts and audit evidence remain retained;
expiry or cancellation never deletes created vouchers or reverses posted stock.

Validation dry-runs native draft creation and rolls it back. `READY` means ready
to create drafts; `DRAFTS_CREATED` explicitly has `effect_kind: DRAFT_ONLY` and
reports whether native posting remains required. Actual physical eligibility and
financial coverage are authoritatively checked by native posting. Completed chunk
receipts survive a later failure; revalidate and resume only outstanding chunks.
Duplicate content under another upload key returns its original job. An active
cohort cannot acquire a second imported draft in another job.

Accounting reads include current manifest, signed keyset cohort history with
product/warehouse filters, reconciliation, lean manifest revisions and each
revision's manifest. `GET .../{control_id}/export-ticket` creates a five-minute
ticket for the bounded current declaration CSV, including applied flags and exact
allocations. Export requires `accounting.export.read` in addition to stock read.
Cost/dimension/date/capture denies apply to derived values, history, filters and
exports. No denied cost is inferred through totals or rates. Existing movement,
cost-pool, tracking and journal reads provide native drill-down.

## Deployment and evidence

Models and single-DDL migrations: Accounting 0213-0216; Vouchers 0102-0105.
Upgrade/downgrade/re-upgrade and full model parity are rehearsed on disposable
MySQL. Downgrades refuse to remove retained evidence. The nullable historical-age
column preserves legacy inference; no missing historical dates are backfilled.
The shared execution client is 0.3.6 and requires Pydantic 2.12 or later; all three
consuming service locks and generated API client 0.2.39 are synchronized.

UI and normal posting activation remain separate. Reports source-cut activation
is also separate from these operational reads. Verification and the two reviews
are recorded in [the delivery checklist](product-opening-stock-api-delivery.md).

## Decision log

- 2026-10-29: Legacy adoption uses the existing opening revision window and period
  authority. Browser chunk ordering follows canonical native ordering, and batch
  entry distinguishes opening receipt eligibility from outward-issue shelf life.
  First-registration conflicts retain their absent-control baseline until the
  user explicitly discards and reviews the current worksheet. Evidence is in
  [the review corrections](product-opening-stock-review-fixes.md).
