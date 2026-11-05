# Voucher API implementation batch note

**Recorded:** 2026-10-10, following the user's request to save the proposed batches and
maintain a todo list. This is the saved delivery breakdown. Implementation evidence lives in the tracker and
[Phase 1 execution note](voucher-phase1-execution.md): B01-B08 common foundation is verified;
[B09 financial export/Reports foundation](voucher-b09-execution.md) is also verified.
[Phase 2 B10-B14](voucher-phase2-execution.md) is verified for ordinary money, banking,
settlements and financial reports. B15 is next; all release activations remain pending.

**Recommendation:** 45 planned batches in eight delivery groups: **41 baseline batches**,
**one conditional reservation batch (B31)** and **three optional integration batches
(B42-B44)**. These groups summarize the existing B01-B45 register; they do not rename the
V0-V9 work packages or change their dependencies.

Use the [live implementation todo](voucher-implementation-todo.md) to follow progress,
the [delivery tracker](voucher-delivery-tracker.md) for authoritative status, prerequisites
and evidence, and the [implementation plan](voucher-implementation-plan.md) for detailed
contracts and acceptance scenarios. The [architecture plan](vouchers-plan.md) governs scope
and ownership if a summary needs correction.
The [posting/reporting design](voucher-posting-reporting-design.md) records the required
financial statements, tax/stock/party registers, source contracts and RPT01-RPT20 checks.
B14a-B14d are smaller tasks inside B14, so the recommendation stays at 45 parent batches.
The [stock design](voucher-stock-recording-reporting-design.md) similarly makes B27a-B27e
required parts of B27, with INV01-INV24 checks and explicit reservation/order/job-work extensions.

The [company financial-year design](voucher-financial-year-design.md) adds required next-year
readiness, date/numbering/close contracts under D12 and FY01-FY24 checks. Annual profit-transfer
automation remains deferred; ordinary balance continuity is required before activation.

The [account recording/maintenance design](voucher-account-recording-design.md) specifies
native entry lineage, ledger/register row grains, daily/period balance summaries, atomic
projection updates and verified rebuilds. BAL01-BAL20 extend existing D11/AC26 and batches;
account balances remain derived from Accounting facts, never independently editable masters.

The [stock capture/storage contract](voucher-stock-recording-reporting-design.md#31-what-an-execution-captures)
now specifies execution evidence, native quantity/value/position grains, synchronous owner
balances, transfer/return claims, guarded repair and staged imports. STK01-STK20 extend the
existing INV/FY/BAL checks and stock batches; Catalog definitions are not stock execution.

## Scope retained across every batch

- One Vouchers API replaces the planned Billing and Payments APIs. Accounting retains
  financial authority and is the proposed atomic owner of stock/value effects; Catalog,
  Identity and Reports provide their respective master, authorization and reporting contracts.
- All voucher kinds use common header/revision/line tables and reusable typed sections.
  Do not create a separate document table family for each kind or company-defined type.
- Cover 22 non-payroll base kinds: an 18-kind core and four required job-work kinds.
  Requisition, quotation and delivery challan profiles are included. Payroll/HR is excluded.
- Support configurable voucher types and typed custom attributes on voucher headers and
  item lines, reusing existing mechanisms. Catalog owns item-master attributes. Custom
  attributes cannot drive pricing, tax, posting, stock effects or approval policy.
- Support accounts-only, inventory-only and combined behaviors where the profile allows
  them, including charges, discounts, taxes, advances, bill adjustments and split tenders.
- Indents, quotations and orders do not change actual stock or account balances. Reservations
  are explicit. Printing a challan does not itself execute a physical movement.
- India GST is the first tax profile. State-VAT remains an architectural extension; a
  selected state/commodity/rule pack needs additional explicit implementation batches and
  legal-source review. No unspecified VAT pack is included in the 45-batch completion claim.
- Job work in both principal and worker roles, and the supported manufacturing scope, are
  required. Optional bank/provider integrations must not block them.
- Account ledgers, trial balance, P&L/Income & Expense and Balance Sheet are required outputs;
  invoice/tax, stock/COGS and WIP phases extend and recheck them before activation.
- Current stock, item/group/location balances, batch/serial/expiry/age and valuation registers
  require native positions, movement/value facts and origin/date/hold history from first posting.

## Phase 1 — Architecture contracts and shared foundation: B01-B08

| Batch | Scope | Implementation deliverables |
|---|---|---|
| B01 | Existing API and compatibility baseline | Inventory existing services, tests and client contracts; record integration behavior, compatibility constraints and pre-existing failures before changes. |
| B02 | Shared schema and voucher behavior definitions | Define common tables, kind/profile sections, ownership, numbering and initial migration contracts, including D11 statement classification and opening/history coverage. Resolve initial gates without guessing later policies. Include D12 date/year/numbering schema and readiness ownership.; define account/source lineage and fact/summary/register grains; stock capture/cardinality/value-history and parallel configuration compatibility contracts; Specify native component dependencies, unit denominators and original-return claims under D04/D05/D07; resolve native commercial policy/binding, paid/reward identity and policy/posting fences under D01/D04/D06/D07; finalize the 22-kind configuration/capture/effect matrix and shared native settings registry; VCF01-VCF04. |
| B03 | Posting and inter-service contracts | Specify signed commands/results, source identity, authority and master snapshots; committed report export/catch-up barriers; stale-data, concurrency, retry, cancellation and recovery behavior. Include period-version/producer close evidence, reopen invalidation and year-boundary recovery contracts.; specify balance read compatibility, atomic projection/checkpoint and rebuild-generation contracts; stock lock/write order, source claims, guarded operational repair and staged-import contracts; specify effective-config digest, typed command evidence, publication/stop fences and compatibility/adoption fixtures; VCF05/VCF22. |
| B04 | Vouchers service scaffold | Create service/database migrations, gateway routes, configuration, authentication, health checks, audit integration, workers and generated client scaffold; integrate local operational tooling. |
| B05 | Common voucher entry model | Implement minimal types/sections, headers, revisions, shared lines and item identity/detail before customization. Add party references, attachments, links, drafts, version checks and approval foundations; add shared native commercial-policy revision/bindings; separate company Sales and Purchase controls; create or reuse shared policy profile/revision/binding storage with native constraints and immutable accepted configuration evidence; VCF02/VCF05. |
| B06 | Configurable types and custom attributes | Implement type/class administration and company types derived from supported behaviors. Add typed header/item-line attributes, adoption, validation, field permissions, filtering, exports and field-set metadata; implement restrictive type/class policy inheritance, publication, effective controls and scope/override validation; CAL17/CAL23/CAL24/CAL27; deliver all-kind policy/type/class administration, registry discovery, effective settings and scoped publication; VCF01-VCF05/VCF22. |
| B07 | Reliable posting operations | Implement durable asynchronous operations, signed command/results, source uniqueness and idempotency. Recover from crashes, duplicate delivery and lost acknowledgments while preserving posted effects and revisions. Include effect-date/period commit guards and close/retry races.; retain exact committed financial source/line distributions and durable owner identity; enforce configuration digests at operation stages and retry/scheduled execution; VCF06/VCF07/VCF22. |
| B08 | Numbering, documents and common entry support | Implement issue series, templates, artifacts, entry/history contracts and protected downloads. Separate issue numbering from posting numbering; printing and reprinting cannot create accounting or stock effects. Include company/year/date selection and immutable internal/statutory/issue numbering; use effective allowed/required/editable controls and paid/reward/actual presentation; CAL23/CAL27; use the common field-set/effective settings for numbering, narration, required capture and artifact defaults; VCF03/VCF06/VCF23. |

**Outcome:** A shared voucher foundation, ready to receive posting behaviors; no financial
product completion is claimed at this checkpoint.

## Phase 2 — Accounting, settlements and banking inputs: B09-B14

| Batch | Scope | Implementation deliverables |
|---|---|---|
| B09 | Reporting foundation | Establish complete financial/classification/opening/settlement feeds, committed snapshot barriers, report definitions/runs/artifacts and permission-safe reconciliation. Extend with each posting capability. Include fiscal history coverage and dependent carry-cache invalidation.; line-grain account facts, selected day/period totals, atomic dedupe/checkpoints and verified generation cutover |
| B10 | Journal and Contra | Implement balanced entries, cash/bank transfers, ledger validation and fiscal guards. Add account/tender primitives under selected currency and accounting-dimension policies. Include company-year generation/opening, readiness and resumable close/reopen integration.; preserve cumulative balance API and add declared authoritative period/current/currency semantics; enforce configured Contra/Journal account roles, modes, cash/bank, dimensions and date purposes; VCF04/VCF07/VCF08/VCF11. |
| B11 | Bill and advance adjustments | Implement partial/multiple-bill allocation, advance application, on-account balances and dated reallocation/reversal. Prevent competing consumption; pure allocation must not create another cash movement. Include new-year receipts/advances allocating to prior-year bills with original due dates.; export dated allocation/reversal evidence without invented GL deltas; retain explicit chosen bill targets and original due-term basis under tracking/configuration changes; VCF09. |
| B12 | Payment modes and instruments | Implement required mode fields, references, instrument dates, cheque/post-dated handling and history. Keep booking, clearing and reconciliation distinct under the selected recognition policy; validate configured tender/reference/instrument defaults, mode changes and PDC recognition; VCF10. |
| B13 | Payment and Receipt | Implement payments, receipts, advances, refunds, split tenders, bill allocations and native settlement adjustments, including supported discounts/fees and overpayments. Keep tax-bearing profiles gated; verify Payment/Receipt modes, bill selection and recognition against native policy; VCF08-VCF10. |
| B14 | Financial statements and money registers | B14a: account ledgers and trial balance; B14b: P&L/Income & Expense; B14c: Balance Sheet, opening/earnings/comparatives; B14d: party/cash/bank, bill/advance/aging registers and complete reconciliation. Include cross-year opening/earnings, as-of allocations and BRS continuity fixtures.; B14a daily/monthly account/group ledgers and gross running totals; B14d role/currency/bank reconciliation; applicable BAL checks; expose captured type/profile/class/policy lineage in account and money registers; VCF24. |

**Outcome:** Ordinary Journal, Contra, Payment and Receipt, including advances and bill
adjustments. Tax-bearing profiles require B16-B19 and their applicable release evidence.

## Phase 3 — Invoicing, calculations and India GST: B15-B19

| Batch | Scope | Implementation deliverables |
|---|---|---|
| B15 | Common invoice calculation engine | Implement accounts-only, item and mixed calculations, actual/billed quantities, charges, discounts, inclusive/exclusive taxes and rounding. Separate commercial, taxable and inventory-cost allocation bases; Support repeated quantity/line/selected-line/invoice components and bounded named bases; CAL01-CAL04/CAL07/CAL15; implement configured sales/free/deal preview and stacking; CAL18-CAL22/CAL27; automatic schemes require published Catalog definitions and the single authoritative runtime. |
| B16 | Tax records and rules | Implement versioned line tax context/components and tax-event dates, India GST first. Cover applicable advance, ITC, reverse-charge and withholding behavior while preserving existing tax snapshots/readers; Normalize header tax to multiple supply components; verify value/quantity bases and supplier-return tax evidence; CAL05-CAL08/CAL13; distinguish sample/gift versus paid-supply reward tax purposes and mandatory tax despite UI flags; CAL20/CAL21/CAL23. |
| B17 | Accounts/service Sales and Purchase | Implement Sales, Purchase, Credit Note and Debit Note for accounts/service transactions, including payment/credit/advance combinations, source references and controlled supplier-tax differences; no stock-bearing posting yet; Preserve source component allocations for financial-only purchase returns; separate supplier credit-note evidence and refunds; applicable CAL09-CAL13; preserve account/service restrictions and original benefit correction authority under CAL25. |
| B18 | Invoice and tax registers | Implement sales/purchase registers, tax events/credit/settlement working papers and frozen exports. Reconcile timing and GL control accounts; recheck financial statements with invoices/notes/tax.; invoice/tax/settlement register grains and joins without multiplied document totals; Provide component-level purchase/return/tax drill-down without duplicate totals; CAL06/CAL16; expose monetary versus informational benefits, paid/reward quantities and tax bridges; CAL28; retain accepted policy lineage in invoice/tax facts and exports; VCF12/VCF24. |
| B19 | Statutory documents and release controls | Implement applicable document particulars, numbering, evidence and export/submission handoffs. Gate issuance where acknowledgment is required and recover rejected/unknown outcomes without assuming external success. Include statutory invoice-year identity independent of GL posting year. |

**Outcome:** Eight accounting kinds for supported accounts/service profiles. Goods invoices
follow in Phase 4; supported tax cases remain explicitly versioned and gated.

## Phase 4 — Inventory movements, valuation and goods invoices: B20-B27

| Batch | Scope | Implementation deliverables |
|---|---|---|
| B20 | Stock structures and Catalog integration | Implement canonical positions, locations, ownership/custody, lot/unit and receipt-origin/hold history; versioned group/unit/policy contracts and compatible owner acknowledgements.; native movement/position/unit/origin/value references, scoped uniqueness and accepted policy snapshots |
| B21 | Stock posting safeguards | Implement period/count/hold/expiry/eligibility, first-use and selected backdate guards. Stock-only effects need no fake GL journal; allocation checks current eligibility. Include stock-effective versus accounting period guards across year boundaries.; absent-position/count/hold guards, shared lock order and configuration enforcement gates |
| B22 | Valuation and cost recognition | Implement selected costing scope/layers/pools, source-cost allocation and clearing. Quantity receipt-age allocation stays distinct from financial cost.; immutable value legs, chosen layer/pool history, valuation status and residual conservation; Define purchase component capitalization and credit/carrying-value variance bridges; CAL09/CAL14. |
| B23 | Receipt, delivery, challan and transfers | Implement Receipt Note, Delivery Note/challan, Stock Journal transfers, transit and controlled openings. Record physical movement once with quantity/value controls and applicable statutory evidence.; actual/base/tracking capture, paired transfer legs, partial shipment claims and resumable reconciled openings; enforce note/challan/transfer mode and tracking controls without duplicate movement; VCF13/VCF14. |
| B24 | Goods and mixed invoicing | Implement direct, movement-reference and invoice-before-movement workflows, partial/multiple references and interim clearing. Prevent duplicate physical or cash effects when billing an existing movement.; invoice references versus physical execution, provisional cost/clearing and no duplicate movement; Reconcile multi-scope purchase components across payable, tax and landed cost; CAL03/CAL09/CAL14; record manual free goods and atomically consume supported automatic 10+1; all-unit stock/cost and required publication/stop fences; CAL18-CAL24. |
| B25 | Returns, rejections and physical stock | Implement Rejections In/Out, physical returns, protected counts, loss and quarantine. Separate financial notes from stock returns and account for movements concurrent with a count.; source-capped returns, exited-unit reuse, reviewed count observations and impairment/disposal lineage; Enforce original-component return treatments/caps, concurrent claims and final rounding residuals; CAL10-CAL14; return original paid/reward units without automatic gift-list-price debt, coupon restoration or new award; CAL25; enforce protected-count settings and independent source-linked return controls; VCF15/VCF16. |
| B26 | Stock corrections and revaluation | Implement supported backdated corrections, valuation adjustments and cost reversals. Respect closed periods and downstream consumption; reject unsupported correction methods.; value/quantity correction and fenced owner-state repair with downstream dependency checks; Verify late-cost and closed/cross-year purchase-return bridges under CAL14. |
| B27 | Inventory registers and reconciliation | B27a current/item ledger; b group/location; c batch/serial/expiry/age; d valuation/GL and movement/count/damage; e threshold/nonmoving exceptions, secure exports and snapshot/rebuild reconciliation. All five required. Include year-boundary quantity/value/origin/expiry continuity in B27e.; stock-value control balances reconcile to account facts at one snapshot; movement/value-grain projections, nonmultiplying joins, verified generations and applicable STK checks; Reconcile purchase/return component allocations to stock value and GL under CAL16; reconcile paid/reward/actual quantity, all-unit COGS and returns without double benefit; CAL28. |

**Outcome:** Inventory-only vouchers and goods invoices share consistent quantity, valuation
and accounting effects. B21/B22 must precede executable movement even if other work runs earlier.
Required current/group/expiry/age registers are available at declared coverage after B27a-e;
projected supply/demand and job-work custody require their later source batches.

## Phase 5 — Indents, quotations, orders and general vouchers: B28-B36

| Batch | Scope | Implementation deliverables |
|---|---|---|
| B28 | Requisition, quotation and order lifecycles | Implement plain indents/requisitions, quotations and Sales/Purchase Orders with approvals, validity, acceptance and terms. No actual stock/account/tax posting or implicit reservation; make quotation/indent/order profile settings and captured due/source facts explicit; VCF17. |
| B29 | Fulfillment schedules and conversion | Implement line delivery schedules, due dates and destinations; partial, split and consolidated conversion. Use exact source/revision claims and compatibility checks to prevent concurrent over-conversion; preserve source-scoped paid/reward entitlement and allocation identity through split/consolidated conversion; CAL26. |
| B30 | Order-to-movement-to-invoice tracking | Link orders, movements and bills; independently track ordered, executed, billed, returned and short-closed quantities. Support acknowledgment, cancellation, reopening and replacement without erasing effects; enforce reward award-scope/trigger through partial billing and fulfillment; no duplicate or unsupported deferred awards; CAL26; verify per-line source, tolerance, partial fulfillment and pre-close/reopen configuration; VCF17. |
| B31 — conditional | Explicit reservations | Implement selected stock/credit reservation, expiry, release and consumption with native-owner concurrency controls. Non-reserving profiles can activate without this batch.; reservation/source claims share issue/hold/count guards and preserve transition evidence |
| B32 | Procurement and fulfillment registers | Provide schedules, closure and independent unbilled/unmoved quantities. Add confirmed supply/demand/projected-stock/reorder views at an explicit horizon; reservation views only when selected. Include prior-year backlog/claims and cross-year fulfillment without origin-year exclusion; verify optional/post-dated/general profile settings, date purposes and actualization authority; VCF07/VCF18. |
| B33 | Memorandum, optional and pro-forma entries | Implement non-posting documents and conversion into supported actual voucher drafts. Revalidate current data, permissions and rules on the target before posting. |
| B34 | Scenario Reversing Journal | Implement scenario membership and applicability windows. Expiry changes scenario views only; it must not reverse an actual accounting journal. |
| B35 | Scenario reporting | Provide actual-versus-scenario registers/exports and core reconciliation. Exclude hypothetical entries from actual ledger, inventory and statutory totals. |
| B36 | Core voucher release review | Complete histories, artifacts, type retirement, permissions and client readiness. Verify all 18 core kinds, required profiles, reports and applicable acceptance scenarios before activation; reconcile provisional/scenario configuration and actualization without toggling posted history; VCF18. |

**Outcome:** The 18-kind core supports commercial documents through movement, invoicing and
settlement, together with general and scenario vouchers.

## Phase 6 — Job work and manufacturing: B37-B41

| Batch | Scope | Implementation deliverables |
|---|---|---|
| B37 | BOM, process and job preparation | Implement the required Catalog BOM/process subset, job templates and BOM-assisted requisitions. Capture versioned material requirements, expected outputs and processing rules; distinguish optional advanced Catalog depth; publish compatible principal/worker/BOM/process configuration templates and enforce readiness; VCF19. |
| B38 | Job orders and material custody | Implement both Job Work Order directions and Material In/Out for principal and worker roles, including direct/onward movements, returns and original dispatch references. Distinguish ownership from custody.; cross-year own/third-party custody, original dispatch evidence and bounded return claims; capture owner/custodian and Material In/Out role/consumption configuration; VCF19/VCF20. |
| B39 | Manufacturing and actual costing | Implement consumption, multiple outputs, WIP, scrap and material/output genealogy. Compare expected/actual usage and allocate actual costs without duplicate charges; payroll remains excluded.; actual input/output/scrap genealogy and cost conservation across distinct SKU/unit quantities; execute configured combined/separate consumption once with exact source/BOM/yield/cost evidence; VCF20/VCF21. |
| B40 | Job-work registers and tax working data | Provide material-at-worker, third-party custody, WIP/aging and applicable ITC-04 working exports. Preserve challan chains/aging and reconcile owned WIP to financial statements. Include cross-year custody/WIP/challan age without resets.; WIP/control balances reconcile to account facts at one snapshot; reconcile source movements, value/WIP and custody without multiplying genealogy joins; retain configuration/job-source lineage in custody/WIP/statutory report facts; VCF21/VCF24. |
| B41 | Processing invoices and job completion | Integrate processing-service invoices and settlements with job/material records. Complete challan/aging exceptions, statutory handoffs and reconciliation for all four job-related kinds. |

**Outcome:** All 22 planned non-payroll kinds are covered, including required job work and
supported manufacturing. Final production readiness is verified in B45.

## Phase 7 — Optional integrations: B42-B44

| Batch | Scope | Implementation deliverables |
|---|---|---|
| B42 — optional | Payment provider integration | Implement selected provider intents/attempts, workers and verified callbacks, with fees/refunds/chargebacks and unknown-outcome recovery. Preserve one accounting effect per business source. |
| B43 — optional | Bank statement reconciliation | Implement selected formats, deduplicated imports, grouped/partial matching, opening reconciliation items and audited unmatching. Produce reviewable adjustments rather than silently posting differences. |
| B44 — optional | Advanced cheque and cash controls | Implement selected cheque books/leaves, printing, voiding and cash denominations. Keep instrument administration separate from financial recognition and record master ownership. |

These batches require positive capability selection; they do not block job work or the core
release. Ordinary payment modes and instrument references belong to B12-B13 already.

## Phase 8 — Production readiness and rollout: B45

| Batch | Scope | Implementation deliverables |
|---|---|---|
| B45 | Final verification and staged activation | Complete backfill/load/recovery, reviews, client compatibility, report rebuild/frozen-run equivalence and end-to-end reconciliation. Verify applicable RPT01-RPT20; activate supported profiles with monitoring/recovery. Include two-year rollover/late-adjustment/recovery rehearsal and applicable FY01-FY24.; BAL01-BAL20, account projection crash/rebuild/cutover and measured large-account load; STK01-STK20 transaction failure, import/repair/rebuild and supported-load evidence; Verify applicable CAL01-CAL16 and the stacked purchase/five-part return fixture; rehearse applicable CAL17-CAL28 policy denial, scheme/stock/return replay and supported-profile rollout; verify applicable VCF01-VCF24 across policy changes, replay, rollout and historical reporting. |

## Release checkpoints and completion rules

| Checkpoint | Required evidence | Available capability |
|---|---|---|
| C0 | B01-B08 | Shared drafts, types, attributes and document foundation. |
| C1 | B09-B14, including B14a-B14d, and relevant C0 evidence | Four ordinary accounting kinds, advances/bill adjustments, ledgers/TB/P&L/Income & Expense/Balance Sheet and money/party reports at declared coverage. |
| C2 | B15-B19 and C1 | Eight accounting kinds for supported accounts/service and India GST profiles; invoice/tax reports and financial-statement rechecks. |
| C3 | Required B20-B36 including B27a-e and C2; B31 only for selected reservations | All 18 core kinds, goods/order/general profiles and named current/item/group/expiry/age/value reports. |
| C4 | B37-B41, B45 and C3; optional integrations only if selected | All 22 kinds, required job work/manufacturing and final operational readiness. |

This is a default execution sequence, not a ban on independent work. Use the exact
prerequisites in the tracker. Every batch needs its applicable migration/model/schema/API,
permissions, generated client, event-consumer, test and review evidence. Posting batches
also need concurrency, duplicate delivery, recovery and reconciliation checks. Verification
does not automatically enable a profile: activation has its own statutory, client, report
and operational requirements.

## Decision log

- 2026-10-10: Added D12/FY01-FY24 to the existing 45-batch scope: fiscal readiness,
  cross-year numbering/settlement/stock/job-work/reporting and the final two-year rehearsal.
  No annual copying of balances and no dependency on deferred profit-transfer automation.


- 2026-10-10: Stock reporting review added B27a-e and INV01-INV24 within the same 45 parents.
  Stock positions, eligibility, receipt-origin/hold/date history and group/unit rules now
  support required named registers; reservations and later supply/job-work feeds stay explicit.

- 2026-10-10: Deep reporting review made financial statements explicit in B14a-d and added
  D11 source/classification/opening contracts and later tax/stock/WIP reconciliation. Updated
  the linked tracker/todo while retaining 45 parents and zero verified implementations.

- 2026-10-10: Saved the user-requested 45-batch breakdown and linked a maintained todo.
  Recorded 41 baseline, one conditional and three optional batches, eight delivery groups
  and five release checkpoints. No implementation status, policy selection or dependency
  was changed by saving this note.

### Account-recording review - 2026-10-10

Saved account entry/register/ledger/balance maintenance as required existing-batch work,
including source facts, summary generation, join-safe registers and BAL acceptance. The
45-parent recommendation and conditional/optional capabilities remain unchanged.

### Stock capture/storage review - 2026-10-10

Saved explicit capture/storage, immutable value history, guarded stock repair and
STK acceptance in the existing 45 batches. Optional reservations and policy gates are unchanged.

### Purchase component review - 2026-10-10

Saved [multi-scope purchase/return components and CAL01-CAL16](voucher-invoice-calculation.md#81-required-component-acceptance-matrix)
as requirements in the existing 45 batches. No implementation or activation status changed.

### Sales commercial-configuration review - 2026-10-10

Saved the [commercial configuration contract](voucher-commercial-configuration.md) and CAL17-CAL28 within the existing
45 batches. Required same-item 10+1 automation and manual bonus recording are separate delivery
slices; optional campaign/coupon mechanics retain their own dependencies and readiness gates.

### All-voucher configuration review - 2026-10-10

Saved all-kind configuration capture and execution requirements from the [all-voucher configuration contract](voucher-configuration-design.md)
within the existing 45 batches. VCF01-VCF24 are per-profile release requirements; no
configuration/runtime implementation or company policy was activated by this review.
