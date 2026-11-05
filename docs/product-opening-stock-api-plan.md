# Product opening stock and value: API delivery plan

Date: 2026-10-28. Status: implementation authorized by the user's subsequent
instruction; activation remains separate. UI is deferred. This extends the existing stock
engine rather than replacing it. Each phase ends with green affected checks.

## 1. Research and existing implementation

Official product concepts consulted:

- [TallyPrime stock items](https://help.tallysolutions.com/knowledgebase/manage-stock-item-tally/):
  opening quantity, rate and value at books begin; editable value recalculates rate.
- [TallyPrime opening-date rules](https://help.tallysolutions.com/stock-items-faq/):
  stock-master opening is at books begin; later changes use stock transactions.
- [Tally stock import allocations](https://help.tallysolutions.com/sample-xml/):
  quantity, rate, value, godown and batch facts in opening allocations.
- [Intuit inventory start-date SDK contract](https://static.developer.intuit.com/sdkdocs/qbv3doc/ippdotnetdevkitv3/html/9e3dd37d-e874-156d-fc39-6d4a05942eb7.htm):
  dated opening transaction with quantity multiplied by cost.
- [Intuit inventory onboarding manual](https://www.intuit.com/content/dam/intuit/intuitcom/partners/documents/icom-education-program-ca-qbo-ch10-inventory.pdf):
  initial on-hand quantity, as-of date and inventory asset account. The SDK/manual
  are conceptual references, not claims about every current QuickBooks edition.

Proposed adaptation: an explicit, auditable opening operation with convenient
quantity/rate/value capture, warehouse/batch/serial allocations and visible GL
effects. Catalog product creation remains independent from financial posting.
Keep the existing books-begin cutoff; adopting per-product later start dates
would need a separately agreed policy and stock-history checks.

Source inspection found these reusable foundations:

| Existing implementation | Reuse / limitation to address |
|---|---|
| `clients/voucher-execution/src/voucher_execution/stock.py` | `STOCK_JOURNAL/OPENING`, exact positive quantity, explicit received value, `COMBINED` or `LINKED_GL`; bounded 100 lines / 1,000 units per operation |
| `apis/vouchers/src/vouchers/tasks/stock_details.py` | Immutable common voucher revisions and normalized stock allocation capture; approvals/execution already have an owner |
| `apis/accounting/src/accounting/tasks/stock_effects.py` | Opening at books begin, active stock-item/location authority, duplicate-position guard, linked GL claims, no openings after physical trading |
| `apis/accounting/src/accounting/tasks/stock_ledger.py` | Atomic positions, origins, warehouse FIFO/MVA pools, serial custody and immutable quantity/value evidence |
| `apis/accounting/src/accounting/tasks/stock_openings.py` | Authorized eligible posted GL opening debits, remaining unclaimed values and bounded selection |
| `apis/accounting/src/accounting/tasks/stock_opening_claims.py` | Shared signed net claim calculation; reversal releases coverage rather than duplicating value |
| `apis/accounting/src/accounting/tasks/stock_gl.py` | Governed inventory-account posting and linked-opening reversal protection |
| `apis/accounting/src/accounting/tasks/openings.py`, `zero_opening.py` | Existing financial opening lifecycle and narrowly permitted explicit zero declaration |
| Stock reconciliation, first-use reservations, outbox and recovery | Reuse native controls; no new direct balance-write authority |

Specific gaps confirmed in code: StockLine carries received value but no explicit
rate input, entered-unit conversion or historical opening cohort date. New origins
and cost layers currently use the stock-posting date. Existing opening protection
is at physical-position scope and must be deliberately adapted for several
historical cohorts in that same position. There is no dedicated durable bulk
opening workbench in the inspected opening/stock modules. Recheck current source
before implementation because concurrent work is ongoing. No new live verification
of these foundations was performed for this planning task.

## 2. Proposed contract and invariants

One opening line identifies a company/SKU, warehouse, optional bin and batch,
entered quantity/unit, normalized base quantity, company currency, carrying value,
valuation input mode, evidence and stable external/source key. Optional child
cohorts retain historical receipt date/order, remaining quantity/value and exact
serial assignments. Physical origin and financial cost cohorts remain distinct.

- Accept decimal strings only; fixed DECIMAL(19,4) storage, existing company
  precision/rounding and overflow checks. Never use selling price, MRP, latest
  purchase rate or missing cost as an implicit opening valuation.
- Propose `RATE` input (quantity x cost per priced quantity) and `VALUE` input
  (entered total is authoritative; unit rate is derived). Require an explicit
  priced quantity/basis for rates. If both rate and value are supplied, validate
  their rounded agreement; do not silently overwrite an inconsistent total.
- Base-unit normalization uses published, permitted conversions. Preview pins
  conversion/profile versions and exposes entered/base quantities and rounding.
  Reject an unrepresentable quantity; do not truncate it. Serialized stock stays
  integral in its base unit.
- Reject negative opening stock/value, zero quantity with nonzero value and
  unsupported ownership/custody. Explicit free stock needs the existing enabled
  zero-value policy and a meaningful reason. Missing value never means zero.
- Batch/serial requirements follow activated profiles. Serial count equals base
  quantity; a physical unit occurs once across the complete opening operation.
  Preparing an identity alone never creates stock.
- Company/SKU/warehouse remains the cost-pool scope. Bins/batches are physical
  dimensions; an allocation's value is not a promise of an independent bin/batch
  valuation pool. FIFO/FEFO physical selection and financial cost consumption
  remain separate.
- Initial migration uses books begin; retain earlier receipt/manufacture dates
  as historical evidence without posting pre-cutoff on-hand balances. Unknown
  history must be marked unknown; never invent supplier invoices or receipt ages.
- No annual opening repost. Existing positions, cost layers, dates and serials
  carry across financial years. Later purchases/count adjustments use their own
  operations. No opening loophole after trading begins.
- Native Accounting commit atomically records quantity, cost, serial custody,
  journal or linked claim, source receipt and audit/outbox. Cross-service progress
  is durable and recoverable, never advertised as one distributed transaction.

## 3. Delivery phases

### Phase 1 — Contract, policy and baseline verification

Audit the current native opening tests and deployment gates; establish a baseline
for combined opening, linked GL, zero opening and later trading. Review the exact
interaction between financial opening finalization, zero declaration, stock
coverage, first-use and normal trading admission. Define a durable readiness
contract with precise blocker codes and remediation, including missing products,
locations, account mapping, dates, authority and unresolved execution.

Agree cutover, expired-stock, cohort, zero-value and correction policies below.
Document proposed schemas, resource/field permission matrix and owner/migration
manifest before implementation. Reuse common voucher drafts/revisions; add only
the workflow metadata that cannot fit their existing contracts.

Exit: reviewed contract, baseline tests green and no unresolved decision silently
converted into code. Existing stock admission stays unchanged.

### Phase 2 — Opening drafts, exact calculation and validation APIs

Extend the common Vouchers opening profile for entered unit/quantity, explicit
rate/value modes and stable allocation identities. Provide create/revise/list/
detail and validation against expected revision; use existing lifecycle routes
where sufficient. Provide machine-readable line/field issues and a capability
schema for future clients. No stock effect from saving or validating a draft.

Expose normalized quantities, valuation totals, calculated rates, currency,
rounding decisions and projected account distribution. Keep product creation
receipt independent: later clients may create a product then an opening draft,
with honest partial progress and no duplicate product on retry.

Exit: invalid units/costs rejected; exact decimals, stale edits, field denies,
other-company references, draft retry and no-stock-on-save tests green.

### Phase 3 — Historical cohorts, batches and serial allocations

Support multiple warehouse/bin/batch allocations and historical cohorts in the
same position. Extend versioned shared execution contracts and native models only
as required. Replace the simplistic one-opening-per-position check with an
equally strong opening-scope/cohort identity rule under the existing owner lock.
Multiple cost cohorts may share one position; a second independent opening must
still be rejected.

For FIFO import remaining historical layers with stable date/tie order. For MVA
import exact remaining quantity/value per warehouse, retaining known physical
origins separately. Validate cohort sums, serial placement and per-unit value
conservation; never replace known historical layers with an unexplained average.
Date provenance is explicit when unavailable. Prepared batches/serials can be
referenced; optional preparation orchestration must keep owner receipts separate.

Exit: multi-cohort same-position, multi-warehouse, serial collisions, expiry,
unknown history and exact residual allocation pass native MySQL checks.

### Phase 4 — Reviewed posting and accounting integration

Use existing Vouchers submit/approval and stock owner prepare/reserve/commit/status
workflow. Extend review evidence to bind draft content, configuration/source
versions, unit conversions, opening generation and financial coverage. Revalidate
at commit. Reuse the native first-use/period/field guards and source fences.

`COMBINED` creates Inventory Asset debit / configured Opening Offset credit once.
`LINKED_GL` consumes the authorized existing opening debit without another asset
journal. Existing GL coverage must be explicitly reviewed before choosing combined
mode; do not silently duplicate imported trial-balance inventory. No tax, payable,
supplier purchase or revenue is invented by an opening.

Exit: stock and GL commit/rollback together, exact replay causes one effect,
concurrent claims cannot overconsume GL, lost responses recover from owner receipts
and stale approval/configuration cannot post.

### Phase 5 — Company cutover reconciliation and finalization

Expose opening-session coverage and reconciliation: quantity allocations to
positions, units to quantity, cohorts to warehouse values, inventory controls to
GL and linked debits to signed claims. Include pending and unknown executions.
Add a reviewed finalization fence so all entry paths serialize opening changes
against trading; do not rely only on the first observed stock posting.

For bulk chunks, retain company-level incomplete state until every required chunk
and reconciliation succeeds. Reuse the explicit zero declaration for empty books
without granting balance-entry, journal approval or reopening rights. Clarify
financial and physical zero/readiness states rather than treating one as proof of
the other. No balancing plug is permitted.

Exit: incomplete imports, unmatched GL, pending execution, trading/finalize races
and closed periods block correctly; complete cutover permits normal stock flows.

### Phase 6 — Audited correction and recovery

Editable drafts use expected versions. Posted openings remain immutable. Before
dependent trading, use reviewed reversal/replacement and release/reclaim linked
GL coverage through existing guards. Reconcile reservations and lost responses
before allowing replacement. Closed/locked periods retain their current guards.

After dependent trading, return a precise blocker and the supported corrective
workflow. Retroactive recosting and value-only adjustments must not be implemented
as direct balance edits; a broader recosting engine requires separate agreement.

Exit: correction preserves history, double reversal is refused, linked GL cannot
reverse while claimed and downstream cost/serial lineage cannot be invalidated.

### Phase 7 — Bulk opening import and restartable execution

Provide an opening import job, bounded upload/schema validation, row mapping,
duplicate detection, dry run, immutable reviewed manifest, explicit commit and
status/error export. Reuse proven import mechanisms where suitable, keeping stock
facts out of Catalog master imports. Resolve SKU/location identifiers only through
authorized company mappings; require explicit resolution of ambiguous references.

Support header/allocation/cohort/serial input with stable source row keys and
control totals. Replays under different request keys still identify the same
source operation. Chunk within native limits; persist chunk receipts and resume
only outstanding work. Cancellation after posting requires explicit reversal;
do not present already committed chunks as rolled back. Load limits and retention
budgets are established and measured before release.

Exit: interrupted jobs resume without duplicates, review becomes stale on any
material change, malformed/hostile files are bounded and company trading remains
blocked until the complete import is reconciled.

### Phase 8 — Read APIs and reporting evidence

Expose authorized opening history/status, per-product/per-warehouse opening
quantity/value, cost cohorts, serial assignments, GL links, reconciliation and
correction lineage. Use signed keyset cursors, allowlisted filters, supporting
indexes and lean projections. Cost read-denies also apply to aggregates, derived
rates, search/sort/filter and exports; quantity access must not leak denied value.

Reuse immutable stock/GL facts and existing Reports source contracts. Distinguish
operational API reads from complete Reports source-cut activation. Annual opening
views derive from prior closing facts without writing new opening transactions.

Exit: authorized drill-down explains totals, API/export permissions hold and
cross-year reads conserve quantity, cost, origin dates and serial custody.

### Phase 9 — Native integration, synchronization and release rehearsal

Test complete API flows against MySQL and applicable delivery workers: active
untracked/batch/serial/both products, FIFO/MVA, multiple warehouses, conversions,
rounding residuals, zero value policy, stale profile/approval, wrong tenant/company,
field denies, duplicate source, concurrent post/finalize/GL claims, service outages,
unknown commit responses, correction and year continuation. Verify existing issues,
transfers and reversals consume the imported costs correctly.

For every change synchronize models, single-DDL migrations, schemas, factories,
OpenAPI, generated clients, events/consumers, permissions/roles/seeds, startup and
readiness checks. Rehearse upgrade/downgrade/re-upgrade and backfill on a copy;
no fabricated stock to backfill missing history. Benchmark bounded imports and
reads, verify indexes and retain reconciliation evidence.

Perform two final reviews: (1) arithmetic, security, concurrency and transactional
failure; (2) full API/operator recovery, migration and release claims. Fix findings
and rerun affected checks after each. Physical posting activation is a separate
explicit deployment step after evidence is accepted. UI remains deferred.

Exit: native evidence and at least 90% changed-domain coverage, no lowered overall
coverage, clean lint/type checks, synchronized deployment and no unresolved
correctness/security defects. A completed checklist is not activation authority.

## 4. Proposed API surface (names to finalize in phase 1)

All public paths are company-scoped and permission/field-policy protected.

| Owner | Purpose | Reuse or proposal |
|---|---|---|
| Vouchers | Create/revise/read opening drafts and submit/approve/execute | Reuse `/vouchers` and lifecycle actions, `STOCK_JOURNAL/OPENING`; extend typed capture |
| Vouchers | Validate/preview opening calculation and native effects | Extend existing review flow; stable issue codes and expected revision |
| Accounting | Opening requirements/readiness and reconciliation | Proposed `/stock/openings/readiness` and `/stock/openings/reconciliation` |
| Accounting | Select remaining posted inventory opening debit | Existing `/stock/opening-lines` |
| Accounting | Reviewed cutover finalization/status | Add the narrowest extension to the existing opening lifecycle; no parallel posting engine |
| Vouchers | Bulk import manifest, dry-run/commit/status/issues | Proposed `/stock-opening-imports` job resource, common opening executions |
| Accounting | Positions, movements, cost pools, postings and linked history | Reuse existing `/stock/*` reads, add bounded opening filters/projections |
| Internal owners | Signed execution, source fences, receipts, outbox delivery | Reuse existing stock execution protocol and Identity reservation authority |

Proposed failure codes include `OPENING_DATE_MISMATCH`, `PRODUCT_NOT_ACTIVE`,
`UNIT_CONVERSION_INVALID`, `SERIAL_COUNT_MISMATCH`, `COHORT_TOTAL_MISMATCH`,
`OPENING_ALREADY_RECORDED`, `GL_OPENING_UNCOVERED`, `GL_OPENING_OVERCLAIMED`,
`OPENING_FINALIZED`, `TRADING_ALREADY_STARTED`, `REVIEW_STALE`,
`EXECUTION_UNCONFIRMED` and `CORRECTION_HAS_DEPENDENCIES`. Final wire shape must
follow the existing error envelope, not expose internal exceptions.

## 5. Decisions for agreement before dependent implementation

Recommendations, not newly approved policy:

1. Keep first-time opening at company books begin, including a mid-year company
   migration configured with that books-begin date. Later discovery/new products
   use receipts/approved adjustments. A later per-product cutover requires an
   explicit additional design; do not reopen all company openings automatically.
2. Support both aggregate and detailed historical opening costs. Preserve supplied
   FIFO layers; if only an aggregate is known, use an explicitly acknowledged
   opening cohort with unknown prior history, never claim reconstructed FIFO age.
3. Existing zero-cost receipts remain disabled unless explicitly configured;
   enabled zero value requires evidence. Do not make free goods the fallback for
   missing cost or an onboarding convenience default.
4. Initial release covers company-owned usable goods in actual warehouses.
   Expired/damaged/quarantined, third-party-owned, goods-in-transit, job-worker
   custody and WIP openings need typed custody/disposition/valuation handling.
   Recommend a subsequent scoped extension; refuse unsupported import rows rather
   than dropping them or importing expired stock as saleable stock.
5. Keep financial approval separation. Product creation/tenant administration
   alone must not grant approval, stock posting, cost read or opening corrections.
6. Preserve imported GL controls through linked mode; combined mode requires
   explicit review that it creates new asset value. Do not infer a mode solely
   from account names, a zero declaration or the presence of any GL history.
7. Use immutable reversal/replacement before dependent trading. Defer automatic
   retroactive recosting after transactions to a separately approved phase.

## Decision log

- 2026-10-28: User authorized implementation of all phases followed by two reviews
  and fixes. Recommendations in section 5 define the selected initial scope.
  Track work and verification in `product-opening-stock-api-delivery.md`.

- 2026-10-28: User requested a deep API-first phased plan, with TallyPrime/
  QuickBooks concepts and UI deferred. Inspected current native implementation
  and official product documentation; recorded this proposal only. Existing
  warehouse-specific costing, conservative stock rules and service ownership are
  retained. No application code, database data, migrations, roles, posting flags,
  commits or publication were changed by this planning task.
