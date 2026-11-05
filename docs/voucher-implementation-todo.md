# Voucher API implementation todo

**Last updated:** 2026-10-11. **Verified implementation batches:** 14 / 45 planned.
**Current state:** Phase 2 B10-B14 VERIFIED for the recorded ordinary-money/report scope.
**Last verified batch:** B14, including B14a-d. **Current work:** Phase 3 B15-B18 in progress; [execution record](voucher-phase3-execution.md). B19 remains planned; a bounded Phase 5 B28 capture slice is also in progress under the open B15/Phase 4 gates. No Phase 3-5 batch is verified yet. The [Sales configuration implementation plan](voucher-sales-configuration-plan.md) refines the remaining Sales controls without changing batch status.

2026-10-11 remaining-kind configuration review: [typed backend plan](voucher-remaining-configuration-plan.md)
maps the other 21 kinds and provisional `SALES/PRO_FORMA` to owner gates and slices A-I.
The review records [VC2-01 through VC2-06](voucher-remaining-configuration-plan.md#81-configuration-work-packages-and-exit-evidence)
as child work packages. Do VC2-01 schema/compatibility, VC2-02 binding/resolver and VC2-03
date/snapshot semantics before rolling out executable settings. VC2-04 extends the verified
ordinary-money baseline; VC2-05 and VC2-06 remain gated by each later owner/integration batch.
No batch or company activation status changes from this planning step.

2026-10-11 backend checkpoint: [configuration v2 execution evidence](voucher-configuration-v2-execution.md)
records a bounded implemented subset: sparse v2 policy, typed order/ordinary-money capture,
posting-date money binding, client sync, native tests and two scoped reviews. Continue the
remaining VC2-01 through VC2-06 work and the B15-B45 owner gates; no parent batch or release
activation is marked complete by this subset.

2026-10-11 Sales configuration checkpoint: a bounded account/service policy subset is implemented
in Vouchers capture and Accounting owner preview. Shared non-statutory series now support
suffix, start value, automatic/manual/override modes and fiscal-year/continuous counters.
Complete the remaining dated immutable rule, legal Sales number owner, price, group,
component-default, goods/POS and statutory artifact contracts in the linked plan;
B15-B19 and activation statuses are unchanged.
[Phase 2 evidence](voucher-phase2-execution.md) records native tests, corrected failures,
coverage and limits. All release activation checkpoints remain separate.

Read the [saved batch note](voucher-batch-note.md) for scope and deliverables, the
[delivery tracker](voucher-delivery-tracker.md) for status/dependencies/evidence, and the
[implementation plan](voucher-implementation-plan.md) for contracts and acceptance cases.
The 45 planned batches comprise 41 baseline, one conditional (B31) and three optional
(B42-B44) batches. Selected scope, rather than the raw count, determines release completion.
The [posting and reporting design](voucher-posting-reporting-design.md) defines required
reports and RPT01-RPT20 checks. Four B14 sub-batches below refine the existing parent count.
The [stock recording/reporting design](voucher-stock-recording-reporting-design.md) adds
INV01-INV24 and five B27 sub-batches for current/item/group/location/expiry/age/value reports.

The [company financial-year design](voucher-financial-year-design.md) requires next-year
readiness, D12 and FY01-FY24 across the existing batches. Normal continuity is required;
automated annual profit transfers remain deferred. Phase 1 verifies the common foundation;
financial/report/stock activation remains governed by the later batches.

The [account recording/maintenance design](voucher-account-recording-design.md) specifies
native entry lineage, ledger/register row grains, daily/period balance summaries, atomic
projection updates and verified rebuilds. BAL01-BAL20 extend existing D11/AC26 and batches;
account balances remain derived from Accounting facts, never independently editable masters.

The [stock capture/storage contract](voucher-stock-recording-reporting-design.md#31-what-an-execution-captures)
now specifies execution evidence, native quantity/value/position grains, synchronous owner
balances, transfer/return claims, guarded repair and staged imports. STK01-STK20 extend the
existing INV/FY/BAL checks and stock batches; Catalog definitions are not stock execution.

## Maintenance rules

1. Update this todo and the tracker in the same change whenever implementation progresses,
   becomes blocked, is verified or has a recorded scope selection. Keep the next eligible
   batch and last-updated date current; do not renumber B01-B45.
2. The tracker is the authoritative status and evidence record. A checked batch here means
   **VERIFIED** there, with completed exit evidence. READY, IN_PROGRESS and BLOCKED batches
   remain unchecked. Record partial work and handoff details using its
   [batch evidence template](voucher-delivery-tracker.md#6-batch-evidence-and-handoff-template).
3. Conditional/optional batches remain unchecked until verified. If explicitly not selected,
   label the entry NOT_SELECTED and link the decision in the tracker; do not check it as
   completed. Record B31 selection separately for stock and credit reservation capabilities.
4. Add smaller suffixed tasks under a batch only when useful; retain the parent's full exit
   criteria. Add any new scope, such as a selected state-VAT pack, as explicit extension
   batches with dependencies and evidence requirements in the governing plan/tracker first.
5. Keep activation checkpoints separate from implementation verification. Do not infer
   production, statutory, web/mobile or explicitly API-only readiness from code existence.
6. Preserve unrelated work. Planning checkboxes are not authorization to commit, publish or
   deploy; record those actions only when actually authorized and performed.

## Phase 1 — Architecture contracts and shared foundation

**VERIFIED:** B01-B08, for the C0 foundation slices detailed in the
[execution/evidence note](voucher-phase1-execution.md) and
[implemented contracts](voucher-phase1-contracts.md). Financial/stock distributions,
statutory numbering, paid/reward valuation and full fiscal close integrations remain gated
in their named later batches; the common tables/controls cannot enable them implicitly.

- [x] **B01:** Record the existing service/test/client baseline, compatibility constraints
  and actual pre-existing failures, including report-feed/history coverage gaps. **VERIFIED; baseline and compatibility evidence recorded.**
- [x] **B02:** Finalize foundation relationships, kind/profile sections, ownership, numbering
  and initial migration/decision contracts, including D11 classification/opening coverage.
  Record D12 calendar/date/numbering schema and readiness ownership.
  Define account/source lineage and fact/summary/register grains.
  Stock capture/cardinality/value-history and parallel configuration compatibility contracts.
  Specify native component dependencies, unit denominators and original-return claims under D04/D05/D07.
  Resolve native commercial policy/binding, paid/reward identity and policy/posting fences under D01/D04/D06/D07.
  Finalize the 22-kind configuration/capture/effect matrix and shared native settings registry; VCF01-VCF04.

- [x] **B03:** Define signed posting command/result, snapshot, authorization, concurrency,
  cancellation, committed export/catch-up and recovery contracts with fixtures.
  Define fiscal producer evidence/fences, reopen cache invalidation and year-boundary recovery.
  Specify balance read compatibility, atomic projection/checkpoint and rebuild-generation contracts.
  Stock lock/write order, source claims, guarded operational repair and staged-import contracts.
  Specify effective-config digest, typed command evidence, publication/stop fences and compatibility/adoption fixtures; VCF05/VCF22.

- [x] **B04:** Build the Vouchers service/database/gateway/auth/audit/worker/client scaffold
  and operational integration.
- [x] **B05:** Implement minimal types/sections and shared headers, revisions, lines and ITEM
  identity before customization, with drafts, references and version checks.
  Add shared native commercial-policy revision/bindings; separate company Sales and Purchase controls.
  Create or reuse shared policy profile/revision/binding storage with native constraints and immutable accepted configuration evidence; VCF02/VCF05.

- [x] **B06:** Implement type/class administration and typed header/item-line custom fields,
  including permissions, adoption, field-set, filtering and exports.
  Implement restrictive type/class policy inheritance, publication, effective controls and scope/override validation; CAL17/CAL23/CAL24/CAL27.
  Deliver all-kind policy/type/class administration, registry discovery, effective settings and scoped publication; VCF01-VCF05/VCF22.

- [x] **B07:** Implement durable operations, source guards, signed execution/results and
  idempotent crash, cancellation and lost-acknowledgment recovery.
  Recheck effect dates/period versions at commit, including close and year-boundary retries.
  Retain exact committed financial source/line distributions and durable owner identity.
  Enforce configuration digests at operation stages and retry/scheduled execution; VCF06/VCF07/VCF22.

- [x] **B08:** Implement issue series, templates/artifacts, entry/history and protected access;
  keep issuance/printing separate from posting effects.
  Add company/year/date selection and immutable internal/statutory/issue numbering.
  Use effective allowed/required/editable controls and paid/reward/actual presentation; CAL23/CAL27.
  Use the common field-set/effective settings for numbering, narration, required capture and artifact defaults; VCF03/VCF06/VCF23.

## Phase 2 — Accounting, settlements and banking inputs

- [x] **B09:** Build complete financial/classification/opening/settlement feeds, snapshot
  barriers, definition/run/artifact/checkpoint records and permission-safe reconciliation.
  Pin fiscal source coverage and invalidate dependent carry caches for new runs.
  Line-grain account facts, selected day/period totals, atomic dedupe/checkpoints and verified generation cutover.
- [x] **B10:** Implement Journal/Contra and account/tender primitives with balance, account,
  currency, fiscal and selected dimension validation.
  Integrate fiscal generation/opening, readiness and resumable close/reopen controls.
  Preserve cumulative balance API and add declared authoritative period/current/currency semantics.
  Enforce configured Contra/Journal account roles, modes, cash/bank, dimensions and date purposes; VCF04/VCF07/VCF08/VCF11.

- [x] **B11:** Implement atomic bill/advance allocation, on-account balances and dated
  reallocation/reversal with competing-value guards.
  Verify new-year receipts/advances against prior-year bills with unchanged IDs/due dates.
  Export dated allocation/reversal evidence without invented GL deltas.
  Retain explicit chosen bill targets and original due-term basis under tracking/configuration changes; VCF09.

- [x] **B12:** Implement mode/instrument inputs, references/dates, history, clearing and
  post-dated recognition under selected policies.
  Validate configured tender/reference/instrument defaults, mode changes and PDC recognition; VCF10.

- [x] **B13:** Complete Payment/Receipt purposes, refunds, split tenders, bill allocation
  and native settlement adjustment entries.
  Verify Payment/Receipt modes, bill selection and recognition against native policy; VCF08-VCF10.

- [x] **B14:** Deliver the financial statements and money/party registers below; verify all
  four sub-batches and the applicable RPT checks before completing this parent.
  Verify cross-year opening/earnings, dated allocation and bank continuity fixtures.
  B14a daily/monthly account/group ledgers and gross running totals; B14d role/currency/bank reconciliation; applicable BAL checks.
  Expose captured type/profile/class/policy lineage in account and money registers; VCF24.
  - [x] **B14a:** Account ledgers/day book and trial balance, opening/turnover/closing,
    deterministic pagination, group rollups and source drill-down.
    Include daily/monthly carry, gross Dr/Cr, filtered-view semantics and register-grain checks.
  - [x] **B14b:** Profit & Loss and Income & Expense, direct/indirect mapping, returns,
    surplus/deficit and period/comparative scope.
  - [x] **B14c:** Balance Sheet, TB/P&L bridge, prior/current unclosed earnings, entered
    opening versus derived carry, mid-year/YTD coverage and multi-year comparisons.
  - [x] **B14d:** Party/bill/advance/aging, cash/bank and payment/receipt registers;
    dated settlement/FX bridges and the combined frozen-report reconciliation fixture.
    Include allocation-only updates, all-kind bank/cash movements and source/summary reconciliation.

## Phase 3 — Invoicing, calculations and India GST

- [ ] **B15:** Implement canonical accounts/item/mixed calculations, quantities, charges,
  discounts, rounding and distinct commercial/tax/stock-cost allocations.
  Support repeated quantity/line/selected-line/invoice components and bounded named bases; CAL01-CAL04/CAL07/CAL15.
  Implement configured sales/free/deal preview and stacking; CAL18-CAL22/CAL27; automatic schemes require published Catalog definitions and the single authoritative runtime.
  Progress: exact calculator, separate allocation targets/bases, native capture/preview and
  migration 0050 are tested. Ordinary actual/billed quantity consistency is enforced by
  Vouchers and the Accounting owner; paid-bundle capture requires disjoint reward units.
  Catalog's migration head is reconciled through 0170, a bounded same-item static
  preflight is tested, and eight dormant scoped promotion/stack tables have model/migration
  parity. P1 authoring and protected publication, release projection and free-tax
  profiles remain; no promotion is executable yet.
  Published promotion and stack-policy children reject post-publication append through
  the Catalog ORM; scoped stack group/permission references are native. Protected
  publication remains pending. The promotion slice passes native MySQL upgrade,
  scoped-FK/isolation checks and downgrade/re-upgrade; whole-Catalog parity still
  has unrelated in-progress model/migration drift.
  The stored-fact reader reconstructs the supported same-item terms and rejects
  incomplete or inconsistent rows, but is not a published release or posting source.
  The standalone paid-quantity evaluator and capped manual-stack preflight have native
  CAL19 examples, but neither is wired into posting.

- [ ] **B16:** Implement versioned tax components/event dates and applicable advance, ITC,
  RCM and withholding behavior, preserving historical compatibility.
  Normalize header tax to multiple supply components; verify value/quantity bases and supplier-return tax evidence; CAL05-CAL08/CAL13.
  Distinguish sample/gift versus paid-supply reward tax purposes and mandatory tax despite UI flags; CAL20/CAL21/CAL23.
  Progress: ordinary service/RCM dates, pending credit, partial verification/claim and cash
  RCM offsets have native evidence through 0131. Advances/withholding/corrections remain.

- [ ] **B17:** Implement accounts/service Sales, Purchase, Credit Note and Debit Note with
  credit/payment/advance settlement combinations and source evidence.
  QuickBooks-informed Sales workflow checkpoint: schema-v2 due-date window and
  nonblank customer-order reference are implemented at Vouchers capture/issue/
  execution; verified order consumption remains open under B28-B33.
  Preserve source component allocations for financial-only purchase returns; separate supplier credit-note evidence and refunds; applicable CAL09-CAL13.
  Preserve account/service restrictions and original benefit correction authority under CAL25.
  Progress: service Sales/Purchase owner posting, settlement capture and separately gated
  public admission are tested. Untaxed accounts/service Credit and Debit Notes now have
  source-linked residual claims, bounded original-bill offset, cash settlement and signed
  report lineage; owner and Reports both reject original supply-kind changes. Component/tax corrections,
  refunds and the remaining acceptance matrix are open.

- [ ] **B18:** Deliver invoice/tax registers, event/credit/settlement/GL timing bridges and
  frozen validated exports; recheck financial statements with invoices, notes and tax.
  Invoice/tax/settlement register grains and joins without multiplied document totals.
  Provide component-level purchase/return/tax drill-down without duplicate totals; CAL06/CAL16.
  Expose monetary versus informational benefits, paid/reward quantities and tax bridges; CAL28.
  Retain accepted policy lineage in invoice/tax facts and exports; VCF12/VCF24.
  Progress: eight invoice/credit source grains, registers, as-of positions and GL bridges
  are implemented for existing service profiles. Native 0132/report verification passed;
  simple untaxed Credit/Debit Note register lineage is tested. Vouchers and Reports now meet
  their 90% coverage gates. Reports also requires invoice GL/open-item reference, amount,
  direction and due-date agreement; Accounting whole-service coverage, advances, benefit facts,
  broader notes/returns and full acceptance remain.

- [ ] **B19:** Complete statutory artifacts, required evidence, issuance gates and external
  handoffs before accounts/service profile release.
  Keep statutory invoice year/identity independent from the GL posting year.

## Phase 4 — Inventory movements, valuation and goods invoices

- [ ] **B20:** Implement canonical stock positions, ownership/custody, lot/unit/receipt-origin/
  hold histories and Catalog group/unit/policy contracts with compatible owner feedback.
  Native movement/position/unit/origin/value references, scoped uniqueness and accepted policy snapshots.
- [ ] **B21:** Implement stock-period/count/hold/expiry/eligibility, first-use/configuration
  and backdate safeguards, including stock-only effects without a fake journal.
  Coordinate stock-effective and accounting period guards across year boundaries.
  Absent-position/count/hold guards, shared lock order and configuration enforcement gates.
- [ ] **B22:** Implement selected costing/recognition scope, cost layers/pools and clearing;
  keep quantity receipt-age allocation distinct from financial cost before executable movements.
  Immutable value legs, chosen layer/pool history, valuation status and residual conservation.
  Define purchase component capitalization and credit/carrying-value variance bridges; CAL09/CAL14.
  D02 method choice: **FIFO and moving average both from initial release** (user,
  2026-10-11). Recognition/lineage, corrections and native acceptance are still open.

- [ ] **B23:** Implement receipt/delivery/challan, immediate/transit transfers and controlled
  openings with quantity/value and applicable statutory guards.
  Actual/base/tracking capture, paired transfer legs, partial shipment claims and resumable reconciled openings.
  Enforce note/challan/transfer mode and tracking controls without duplicate movement; VCF13/VCF14.

- [ ] **B24:** Implement direct, movement-reference and deferred goods/mixed invoices with
  cost clearing and no duplicate movement or cash effect.
  Invoice references versus physical execution, provisional cost/clearing and no duplicate movement.
  Reconcile multi-scope purchase components across payable, tax and landed cost; CAL03/CAL09/CAL14.
  Record manual free goods and atomically consume supported automatic 10+1; all-unit stock/cost and required publication/stop fences; CAL18-CAL24.

- [ ] **B25:** Implement rejections/returns, protected counts, loss/quarantine and concurrent
  discrepancy handling; preserve origin/unit evidence and separate impairment from disposal.
  Source-capped returns, exited-unit reuse, reviewed count observations and impairment/disposal lineage.
  Enforce original-component return treatments/caps, concurrent claims and final rounding residuals; CAL10-CAL14.
  Return original paid/reward units without automatic gift-list-price debt, coupon restoration or new award; CAL25.
  Enforce protected-count settings and independent source-linked return controls; VCF15/VCF16.

- [ ] **B26:** Implement supported valuation/backdate and lot-date corrections, reversals,
  historical evidence and reconciliation without changing already frozen reports.
  Value/quantity correction and fenced owner-state repair with downstream dependency checks.
  Verify late-cost and closed/cross-year purchase-return bridges under CAL14.

- [ ] **B27:** Verify all five stock-reporting sub-batches and applicable INV checks; reconcile
  owned inventory and COGS to financial statements without double counting.
  Stock-value control balances reconcile to account facts at one snapshot.
  Movement/value-grain projections, nonmultiplying joins, verified generations and applicable STK checks.
  Reconcile purchase/return component allocations to stock value and GL under CAL16.
  Reconcile paid/reward/actual quantity, all-unit COGS and returns without double benefit; CAL28.
  Reporting consumer checkpoint (2026-10-22): ten v2 report implementations, typed Accounting
  evidence publication and normal API/export verification are delivered; see the
  [inventory implementation record](reports-framework/inventory-implementation.md). The
  operational B20-B26 producer and full stock acceptance remain pending, so these batch
  checkboxes stay open.
  - [ ] **B27a:** Current physical/owned/eligible/available stock, product ledger and monthly
    opening/inward/outward/closing balances with committed cutoffs.
  - [ ] **B27b:** Item/family/group/category and warehouse/bin/group summaries, dated
    membership, leaf deduplication, overlapping categories and compatible-unit totals.
  - [ ] **B27c:** Batch/serial trace, expired/expiring/minimum-life exceptions and remaining
    stock age, with lot revisions, receipt origins and unknown/assumed-date disclosure.
  - [ ] **B27d:** Stock valuation/GL, transfers/transit, item movement, count variance,
    holds/damage/impairment/disposal and opening/return reconciliation registers.
  - [ ] **B27e:** Reorder/nonmoving exceptions, permission-safe rows/totals/exports,
    expiry-cache freshness, snapshot/rebuild reconciliation and complete inventory fixture.
    Verify stock/cost/origin/expiry carry without duplicate annual opening receipts.

## Phase 5 — Indents, quotations, orders and general vouchers

The [Phase 5 execution contract](voucher-phase5-execution.md) records B28-B36
owner boundaries, detailed exits and the current preparatory capture evidence.

- [ ] **B28:** Implement non-posting plain requisition, quotation and Sales/Purchase Order
  lifecycles, approval and terms without implicit reservation.
  Make quotation/indent/order profile settings and captured due/source facts explicit; VCF17.
  IN_PROGRESS capture slice: shared planned quantity and revision-owned fulfillment
  terms are migrated/round-tripped, profile and party validation is tested, and
  issued-document acceptance/decline/elapsed expiry plus quotation-term artifacts
  and console capture are present. Estimate calculation, full lifecycle/conversion
  matrix, cross-service acceptance and the B15 gate remain.

- [ ] **B29:** Implement fulfillment schedules, exact source claims and bounded split/
  consolidated conversion.
  Preserve source-scoped paid/reward entitlement and allocation identity through split/consolidated conversion; CAL26.

- [ ] **B30:** Implement order/movement/bill links, acknowledgments and return/close/reopen/
  replacement behavior with independent pending quantities.
  Enforce reward award-scope/trigger through partial billing and fulfillment; no duplicate or unsupported deferred awards; CAL26.
  Verify per-line source, tolerance, partial fulfillment and pre-close/reopen configuration; VCF17.

- [ ] **B31 — conditional:** Implement explicitly selected stock/credit reservations,
  expiry, release and consumption. **Selection pending; non-reserving profiles unaffected.**
  Reservation/source claims share issue/hold/count guards and preserve transition evidence.
- [ ] **B32:** Deliver indent/quote/order schedules, unmatched goods/bills and closure history;
  add deduplicated supply/demand/projected-stock/replenishment views at an explicit horizon.
  Missing feeds are unknown; reservation-dependent views require corresponding B31 capability.
  Include prior-year backlog/claims and cross-year fulfillment in current outstanding views.
  Verify optional/post-dated/general profile settings, date purposes and actualization authority; VCF07/VCF18.

- [ ] **B33:** Implement Memorandum, optional/pro-forma documents and validated conversion
  into implemented actual profiles.
- [ ] **B34:** Implement scenario membership/windows and scenario-only Reversing Journal.
- [ ] **B35:** Deliver actual-versus-scenario reporting and core reconciliation without
  hypothetical entries entering actual books or statutory totals.
- [ ] **B36:** Complete core histories/artifacts/retirement, permissions and client/report
  readiness; review all 18 core kinds before activation.
  Reconcile provisional/scenario configuration and actualization without toggling posted history; VCF18.

## Phase 6 — Job work and manufacturing

The [Phase 6 execution contract](voucher-phase6-execution.md) records the
selected baseline, owner boundaries and current B37 preparatory evidence.
The [focused manufacturing/job-work plan](voucher-manufacturing-job-work-plan.md)
adds typed settings, native contracts, execution invariants and B37-B41 exit tests;
it does not complete any unchecked item below.

- [ ] **B37:** Implement the required BOM/process subset, job templates and BOM-assisted
  requisition preparation with versioned material/output rules.
  Publish compatible principal/worker/BOM/process configuration templates and enforce readiness; VCF19.
  IN_PROGRESS exact non-posting requirement preview and typed policy only; Catalog persistence,
  publication, release and B30 source claims remain open. Baseline first;
  multi-level expansion and substitutions excluded from initial release.
  Vouchers now also has bounded schema-v2 manufacturing/job-process policy
  representation and applicability, with combined consumption kept closed.

- [ ] **B38:** Implement both job-order and Material In/Out directions, direct/onward
  custody, returns and original dispatch evidence for principal and worker roles.
  Cross-year own/third-party custody, original dispatch evidence and bounded return claims.
  Capture owner/custodian and Material In/Out role/consumption configuration; VCF19/VCF20.

- [ ] **B39:** Implement manufacturing consumption/outputs, WIP, scrap, genealogy and actual
  cost reconciliation without payroll.
  Actual input/output/scrap genealogy and cost conservation across distinct SKU/unit quantities.
  Execute configured combined/separate consumption once with exact source/BOM/yield/cost evidence; VCF20/VCF21.
  Accounting has a non-posting multi-output cost-allocation preview only;
  owner cost origins, WIP/value movement, journals and source claims remain open.

- [ ] **B40:** Deliver job/custody/WIP/aging registers and applicable ITC-04 working exports;
  preserve receipt/challan age and genealogy; reconcile owned WIP/costs to financial statements,
  excluding third-party assets, and recheck applicable INV scenarios.
  Verify cross-year custody/WIP/challan age without resets.
  WIP/control balances reconcile to account facts at one snapshot.
  Reconcile source movements, value/WIP and custody without multiplying genealogy joins.
  Retain configuration/job-source lineage in custody/WIP/statutory report facts; VCF21/VCF24.
  A pure review-only deadline classifier is present; owner residuals, effective
  policy resolution, native report projection and review workflow remain open.

- [ ] **B41:** Complete processing invoices/settlement, challan/aging exceptions and statutory
  handoffs covering all four job-work kinds.

## Phase 7 — Optional integrations

The user selected Razorpay, mapped CSV statements and both cheque-book/cash
denomination controls on 2026-10-11. The [Phase 7 execution contract](voucher-phase7-execution.md)
records owner, security and acceptance gates; selection alone verifies no batch.

- [ ] **B42 — optional:** Implement selected provider execution, verified callbacks, results,
  fees/refunds/chargebacks and unknown-outcome recovery. **Razorpay selected; validation only.**
- [ ] **B43 — optional:** Implement selected statement imports, grouped/partial reconciliation
  and opening bank reconciliation items. **Mapped-CSV owner/API/report/console slice implemented**
  with immutable imports, reviewed matching, opening items, frozen sessions and adjustment
  proposals. Native concurrent import/match tests pass. Retain B43 as `IN_PROGRESS` until B19
  and AC27 broker replay pass; see [R0-R6](bank-reconciliation-phase-plan.md).
- [ ] **B44 — optional:** Implement selected cheque-book/leaf/printing/void and denomination
  controls. **Both selected; validation only, independent of B42/B43.**

## Phase 8 — Production readiness and rollout

The [Phase 8 execution contract](voucher-phase8-execution.md) breaks B45 into
eight evidence workstreams and a combined two-year native fixture. Selected
B42-B44 are B45 prerequisites; C4 remains a separate activation checkpoint.
The preparatory evidence gate and pending-matrix generator are implemented;
B45 remains unchecked until the selected producers and native rehearsal pass.

- [ ] **B45:** Complete applicable backfill, load/recovery tests, reviews, reconciliation and
  report rebuild/frozen-run equivalence; verify applicable RPT01-RPT20 and INV01-INV24 before staged
  activation. Selected B42-B44 must pass before B45, while they do not block
  implementation of required job work.
  Run the two-year fiscal rollover/late-adjustment/recovery rehearsal and applicable FY01-FY24.
  BAL01-BAL20, account projection crash/rebuild/cutover and measured large-account load.
  STK01-STK20 transaction failure, import/repair/rebuild and supported-load evidence.
  Verify applicable CAL01-CAL28 and purchase/sales/deal/return fixtures.
  Rehearse applicable CAL17-CAL28 policy denial, scheme/stock/return replay and supported-profile rollout.
  Verify applicable VCF01-VCF24 across policy changes, replay, rollout and historical reporting.

## Separate activation checklist

- [ ] **C0:** Verify B01-B08 foundation evidence; no financial-product completion claim.
- [ ] **C1:** Verify foundation plus B09-B14 (including B14a-B14d), named statements and money/party
  reports at declared history coverage before activating supported ordinary-money profiles.
- [ ] **C2:** Verify C1 plus B15-B19, invoice/tax reports, financial-statement rechecks and
  applicable tax/statutory evidence for accounts/services.
- [ ] **C3:** Verify C2 plus required B20-B36 including B27a-e and client/stock-report readiness;
  record selected reservation scope before activating the 18-kind core.
- [ ] **C4:** Verify C3 plus B37-B41/B45 and applicable job-work/statutory evidence; activate
  the 22-kind scope under explicit supported policies, including optional work only if selected.

All applicable D01-D12 decision slices, AC01-AC28 subcases, RPT01-RPT20, INV01-INV24, FY01-FY24, BAL01-BAL20, STK01-STK20, CAL01-CAL28 and VCF01-VCF24 checks
remain governed by the tracker and implementation plan. No policy choice or successful test is implied by
this checklist. Maintain activation records per company/profile, including versions,
readiness, known limitations, operator/time and rollback/forward-repair procedures.

## Decision and progress log

- 2026-10-14: Implemented the optional Purchase bulk import ([plan](voucher-import-plan.md)
  I0-I6): template, staged dry-run validation, reviewed draft commit and result report. It
  creates drafts only and satisfies no batch or activation checkpoint; all parents remain
  unchanged.


- 2026-10-10: Added stock capture/storage sections, RF41-RF48 and STK01-STK20 to existing
  tasks. All 45 parents, nine sub-batches and five activations remain unchecked. Configuring
  Catalog policies is not stock-execution verification; next activity remains B01.


- 2026-10-10: Recorded account entry/register/ledger/balance maintenance, RF33-RF40 and
  BAL01-BAL20 under existing gates/tasks. All 45 parents, nine sub-batches and five
  activations remain unchecked; next activity remains B01.


- 2026-10-10: Saved the Tally/current-API financial-year review, D12 and FY01-FY24.
  Normal next-year readiness and cross-year correctness are required in existing batches.
  All 45 parents, nine sub-batches and five activations remain unchecked; B01 remains next.


- 2026-10-10: Saved the stock recording/reporting design and added B27a-e for current stock,
  item/group/location, batch/expiry/age and valuation/action reports. Added underlying
  origin/hold/date/unit contracts and INV checks to dependent batches. All 45 parents,
  four B14 and five B27 sub-batches, and five activations remain unchecked; next B01.

- 2026-10-10: Saved the deeper posting/reporting design and synchronized the live todo.
  Made account ledgers, trial balance, P&L/Income & Expense and Balance Sheet explicit in
  B14a-d, with invoice/tax, stock and WIP extensions in their existing batches. All 45
  parents, four B14 sub-batches and five activations remain unchecked; next activity B01.

- 2026-10-10: Saved the batch note and initialized this maintained todo at the user's request.
  All 45 implementation checkboxes and five activation checkboxes are unchecked. B01 is
  READY; B02-B45 remain PLANNED in the tracker. Conditional/optional selections remain open.
  Next implementation activity is B01; no application implementation was performed here.

### Purchase component review - 2026-10-10

Added [purchase/return component requirements](voucher-invoice-calculation.md#81-required-component-acceptance-matrix)
to the existing tasks, including stacked discounts, quantity charges, multiple taxes and
partial-return source claims. All 45 parents, nine sub-batches and five activations remain unchecked.

### Sales commercial-configuration review - 2026-10-10

Added native Sales/Purchase/type/class configuration and manual/free/10+1 requirements
from the [commercial configuration contract](voucher-commercial-configuration.md). CAL17-CAL28 cover controls, lifecycle,
stock/tax/cost and source-linked rewards. All 45 parents, nine sub-batches and five activations
remain unchecked; definition validation alone is not scheme-runtime verification.

### All-voucher configuration review - 2026-10-10

Added required all-kind registry/policy storage, capture, configuration enforcement and
VCF01-VCF24 to existing tasks through the [all-voucher configuration contract](voucher-configuration-design.md). All 45 parents,
nine sub-batches and five activations remain unchecked. Next activity remains B01.


2026-10-10 implementation checkpoint: B01-B08 VERIFIED for the shared C0 foundation.
The [Phase 1 note](voucher-phase1-execution.md) records code, native DB/broker/client tests,
manual correctness/security review, operational handoff and later acceptance obligations.
C0 activation is unchecked. B09 is the next ready batch. No commit/publish/deploy performed.
C0 remains unchecked. Earlier planning-only log entries below/above describe their original dates,
not the current implementation state.


2026-10-10 B09 checkpoint: financial owner export/barrier, Reports source projections,
reconciled generation cutover and frozen diagnostic runs VERIFIED. See the
[B09 implementation/evidence note](voucher-b09-execution.md) for exact limits and tests,
including the separate concurrent sequence failure. B10 is next; B14 report calculations,
later producer/report slices and all release activations remain unchecked. No commit,
publish, real-company migration or deployment performed.


Separate parallel-work follow-up (not a B09 exit):

- [x] B10 sequence review completed: remove the independent allocation endpoint and allocate
  only inside authoritative posting with scope, idempotency, audit and concurrency checks.
  Native money tests prove one number/effect; the B09 failure remains historical evidence.

2026-10-10 Phase 2 checkpoint: B10-B14 and B14a-d VERIFIED. The
[execution note](voucher-phase2-execution.md) records supported profiles, native DB/broker
and console results, corrected full-run fixtures, coverage and manual review. Fourteen
parents are complete; B15 is next. Tax, stock, orders and job work remain their later
batches. Payroll remains excluded. C0-C4 activations are unchecked; posting flags stay
disabled by default. No commit, publish, deployment or real-company migration performed.
