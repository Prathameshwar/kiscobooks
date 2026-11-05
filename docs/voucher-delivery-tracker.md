# Voucher delivery tracker and plan review

## Unit/stock scoped checkpoint, 2026-10-31

The authorized High-finding fixes add signed dated SKU-unit admission, exact ratio
wire strings, fixed/measured entered-stock evidence and non-serial USABLE native
physical counts. Observations retain cutoff generation and version; variance
reconciles later movements and uses verified native cost or authorized review.
The Stock adjustment route prepares this native contract. Regression and API
evidence is linked in [findings](testing/unit-stock-review/findings.csv) and
[cases](testing/unit-stock-review/cases.csv). This does not activate money/C3 or
close broader B25/B27 work, serial counts or damage/disposal. See the
[count decision and implementation](tenant-admin-stock-entry-plan.md).

**Review date:** 2026-10-10. **Scope:** Plan and implementation through Phase 2.
**Result:** B01-B14 VERIFIED for their recorded foundation, ordinary-money and financial
report scope: 14 of 45 parent batches. Phase 3 B15-B18 are in progress. C0-C4 activations remain pending.
[The 2026-10-11 two-pass review](voucher-two-pass-review-2026-10-11.md)
checks all 45 statuses against the todo and current code evidence: 14 VERIFIED,
9 IN_PROGRESS and 22 PLANNED. It records the review findings, fixes and limits.
[Phase 2 evidence](voucher-phase2-execution.md) records final tests, corrections and limits.
[The Phase 1 execution note](voucher-phase1-execution.md) records completed code, evidence and later activation obligations.
Open business/contract decisions are tracked below and gate the batches that depend on them.
This is not a claim that every later batch is ready to code or that tax compliance is implemented.

Read [architecture/scope](vouchers-plan.md), [implementation work packages](voucher-implementation-plan.md),
[shared model](voucher-data-model.md) and [table inventory](voucher-table-inventory.md) together.
Architecture governs scope/ownership; the detailed contracts govern behavior; this tracker
governs execution order, status and evidence. Amend conflicting documents together, not by
silently treating a newer checklist as a different architecture.

The [saved batch note](voucher-batch-note.md) summarizes the 45 batches in eight delivery
groups. The [live implementation todo](voucher-implementation-todo.md) mirrors this tracker's
verification status as checkboxes; update both together as work progresses. This tracker
remains the authoritative prerequisite, status and evidence record.
The [Phase 8 execution contract](voucher-phase8-execution.md) details B45's
combined native rehearsal and independent C4 activation evidence. Selected
B42-B44 are prerequisites of B45 under the existing conditional dependency.
The preparatory B45 evidence gate can enumerate missing producer, case and
workstream proof, but does not advance B45 from PLANNED or activate C4.
The [posting and reporting design](voucher-posting-reporting-design.md) records required
financial statements, source contracts and RPT01-RPT20 acceptance checks under AC26.
The [stock recording/reporting design](voucher-stock-recording-reporting-design.md) adds
current/item/group/location/expiry/age registers, B27a-e and INV01-INV24 under existing gates.

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

## 1. Review findings and disposition

| Finding | Execution risk | Planning correction | Status |
|---|---|---|---|
| RF01: Packages lacked a concrete batch/evidence ledger | Broad phases could be reported complete with missing dependent work or no reproducible evidence | Added 45 batches, prerequisites, decision records, capability coverage, release checkpoints and a handoff template | Corrected in plan |
| RF02: V1 documents referenced types before type administration; ITEM custom fields preceded item-detail storage | Foundation migrations/customization could depend on unavailable structures | V1.2 creates minimal type/section and ITEM identity/detail before V1.3 administration/customization; commercial calculation remains V3 | Corrected in plan |
| RF03: Complete Payment/Receipt appeared before atomic allocation and instrument support | A completed-looking payment could omit promised settlement behavior or rely on independent posts | Order V2.1 -> V2.3 -> V2.4 -> V2.2; distinguish native settlement adjustment legs from V3 invoice discount components | Corrected in plan |
| RF04: Stock movement/opening appeared before valuation and stock-period guards | Quantity could become executable before its value, first-use and close/backdate controls | Split V4.3/V4.5 into early prerequisites and later integration/correction slices; executable movements follow both | Corrected in plan |
| RF05: V9.2 was one late package and overlapped statutory delivery | Tax/stock/order registers could arrive after activation, or Reports and submission packages could wait for each other | Six reporting slices; Reports owns computation/frozen exports, Vouchers owns artifacts/submission evidence and issue gates | Corrected in plan |
| RF06: Stock-only result handling did not explicitly cover first-use fences without a journal | Zero-GL movements could bypass configuration/period protection or acquire a fake financial journal | Added explicit stock/custody source receipt, first-use and period requirements; extended AC05 | Corrected in plan; D01/D03 contract remains open |
| RF07: Retained inventory text called manufacturing optional and put reporting after job work | Implementers could omit required V8 work or required earlier exports | Corrected active handoff/delivery wording; retained optional advanced Catalog depth and historical decisions | Corrected in plan |
| RF08: Catalog enforcement acknowledgements and stock feedback were not explicit batch outputs | Definition publication might be mistaken for operational enforcement, or stock fact projections might use the wrong authority | V4.1 and AC17 require Accounting-owned enforcement/version feedback; incomplete capabilities cannot be acknowledged as enforced | Corrected in plan |
| RF09: Generic registers did not commit to named financial statements | Balanced journals could be mistaken for completed ledgers, TB, P&L or Balance Sheet | Explicit report catalogue and B14a-B14d; later invoice/stock/WIP financial rechecks | Corrected in plan |
| RF10: Existing financial events are not a complete report feed | Missing allocations, openings, master versions or tax/stock facts could yield incomplete but plausible reports | D11 complete owner exports, compatible feeds, atomic effect visibility and committed catch-up barrier | Financial export/barrier slice implemented in B09; later producer extensions remain open |
| RF11: Group names/display nature cannot define complete statements | Custom/contra accounts could disappear, or native EQUITY be treated as debt | Versioned native classification, explicit netting/mapping, unmapped-balance checks and frozen presentation | Corrected in plan; D11 mapping remains open |
| RF12: Older opening/carry text could duplicate books or lose prior earnings | Opening journals plus carry rows could double balances; next-year P&L filtering could remove equity | Separate entered openings from derived carry, migration/YTD provenance and unclosed-earnings bridge; annual-close automation stays deferred | Corrected in plan |
| RF13: Stock-report formulas could duplicate cost recognition | Perpetual COGS plus a report closing-stock adjustment could distort profit/assets | D02 owner recognition and owned-stock/WIP-to-GL bridges; third-party stock excluded from company assets | Corrected in plan; D02 policy remains open |
| RF14: Tax-account net balances cannot reconstruct statutory registers | Timing, credit eligibility, RCM and settlements could be lost or posted twice | Native tax event/component/credit/settlement feeds and explicit commercial-to-tax-to-GL-to-return bridges | Corrected in plan; D05/D09 profiles remain open |
| RF15: Period locks alone do not make a report reproducible | Late ingestion, formula or label changes could alter a previously issued report | Frozen run manifests pin owner snapshots, rule/mapping versions and outputs; corrected facts create a new run | Corrected in plan |
| RF16: Complete totals, field denies and projection rebuilds lacked explicit checks | Restricted totals could leak data or partial statements appear complete | Permission-safe full-input gates, scope labels, source reconciliation and rebuild/artifact equivalence checks | Corrected in plan |
| RF17: Stock/current/available balances lacked a canonical grain and complete definitions | Nullable position keys could duplicate buckets; transit/third-party/reserved goods could inflate availability | Canonical position constraints and explicit physical/owned/eligible/reserved/available scopes | Corrected in plan; D07 constraints pending |
| RF18: Lots and mutable status alone cannot reproduce earlier availability | Date corrections, holds or released reservations could rewrite historical reports | Native lot revisions, hold and selected reservation transition history with frozen inputs | Corrected in plan |
| RF19: Cost layers alone do not support receipt ageing under every costing method | Averaged costs, repeated lot receipts or transfers could erase residual age | Quantity receipt origins/allocations independent from value layers, with observed/assumed/unknown provenance | Corrected in plan; D02 allocation contract pending |
| RF20: Product/location grouping and units were not explicit report contracts | Reparenting, overlapping categories or mixed units could double or misstate stock | Pin dated hierarchy/assignment, deduplicate leaves, explain overlaps and restrict quantity aggregation | Corrected in plan |
| RF21: Event freshness cannot guarantee expiry freshness | Overnight expiry could leave cached availability positive or imply automatic disposal | Evaluation date/timezone/boundary, minimum-life policy, cache expiry and locked operation checks; no automatic value/quantity loss | Corrected in plan; D03 policy pending |
| RF22: Inventory reports needed physical/value/custody bridges | Counts could use availability; impairment/disposal or openings could count twice | Physical count cutoff, opening-once, remaining-value disposal and owned/transit/third-party reconciliation | Corrected in plan |
| RF23: Forecast and reservation inputs could be guessed from absent producers | Missing inbound/demand data could be shown as confirmed zero; forecasts could bypass guarded allocation | Explicit UNKNOWN/readiness, B31 selection and B32 source-slice horizon contracts | Corrected in plan |
| RF24: Broad stock registers lacked named outputs and verification slices | Item/group/expiry/age or cost-denied output could be omitted despite B27 completion | Required catalogue, B27a-e, INV01-INV24 and owner/rebuild/security fixtures | Corrected in plan |
| RF25: Selected year versus posting year | Display year could be confused with posting authority | Separate company calendar/books start, user selection and date-derived effect periods | Corrected in plan; applicable integration remains planned |
| RF26: Normal new-year scope and Tally behaviour | Tally split-data and deferred-rollover wording could prevent ordinary next-year use | Require same-company new-year readiness/continuity; keep only annual profit-transfer automation deferred | Corrected in plan; applicable integration remains planned |
| RF27: Stale fiscal entity and reopen sketches | Fiscal sketches implied year state/current flags and a future reopening feature | Align with actual period-only status and implemented authorized CLOSED/SOFT_CLOSED reopen; LOCKED remains terminal | Corrected in plan; applicable integration remains planned |
| RF28: Internal versus statutory number identity | Internal journal numbers could become invalid statutory invoice identities | Separate internal posting FY from legal invoice FY and supplier reference; D05/D12 native uniqueness and year-boundary replay | Corrected in plan; applicable integration remains planned |
| RF29: Cross-year source continuity | Annual copies or origin-year filters could duplicate/drop bills, stock and backlog | Keep stable bill/advance/cost/origin/job/order identities; carry from history without new openings or age resets | Corrected in plan; applicable integration remains planned |
| RF30: Date changes and close races | Late entries or stale approvals could silently post to another year or race close | Reject closed requested dates; explicit authorized date changes; owner commit guards and producer fencing | Corrected in plan; applicable integration remains planned |
| RF31: Complete fiscal readiness evidence | Existing local close checks could be mistaken for complete distributed readiness | Add D12 durable scoped review/producer evidence and resumable transitions; legitimate outstanding/transit balances carry | Corrected in plan; applicable integration remains planned |
| RF32: Carry invalidation and frozen reports | Late prior-year changes could stale new-year openings or overwrite frozen reports | Invalidate dependent derived caches for new runs, retain frozen evidence and earnings/YTD bridges; FY01-FY24 and two-year fixture | Corrected in plan; applicable integration remains planned |
| RF33: Account capture beyond generic report scope | Native source distributions and row identity could be absent despite balanced headers | Require exact line/component lineage, line-to-header totals and a shared authoritative GL | Corrected in plan; implementation remains planned |
| RF34: Current balance API semantics | Cumulative debit/credit could be treated as period turnover or a frozen ledger | Preserve legacy endpoint; specify period/current/future/currency bases and source tokens | Corrected in plan; implementation remains planned |
| RF35: Maintained summary grain | Mutable master balances, overlapping caches or net-only summaries could lose or double movements | Explicit account-day/period grains, gross sides, exact arithmetic and optional owner-only accelerators | Corrected in plan; implementation remains planned |
| RF36: Atomic projection and generation recovery | Partial bundle, checkpoint advance or rebuild cutover could omit/double entries | Atomic dedupe/facts/totals/checkpoint, shadow generation, owner reconciliation and pinned readers | Corrected in plan; implementation remains planned |
| RF37: Register join multiplication | Items, taxes, schedules and tenders could multiply a single document total | Declare row/additive-measure grain, preaggregate each child and dedupe legacy/source mappings | Corrected in plan; implementation remains planned |
| RF38: Running/filter/group semantics | Filtered pages, arbitrary sort or group netting could misstate balances | Stable prefix/cursor scope, separate filtered totals, leaf-once grouping and gross balance sides | Corrected in plan; implementation remains planned |
| RF39: Subledger and visibility history | Allocation-only, FX or changed reversal state could corrupt past outstanding or leak denied totals | Dated/versioned facts, party-role/currency bridges, complete-input authority and owner/report separation | Corrected in plan; implementation remains planned |
| RF40: Account maintenance verification | Report names alone did not ensure current/daily/monthly maintenance or safe recovery | BAL01-BAL20 plus worked register/ledger/summary fixture within existing B09/B14/later batches | Corrected in plan; implementation remains planned |
| RF41: Execution capture and row grain | Commercial quantities or generic voucher IDs could stand in for actual movement evidence | Record exact entered/measured/base quantities, source slices, native leg/unit allocations and profile/date snapshots | Corrected in plan; implementation remains planned |
| RF42: Position/unit identity constraints | Null dimensions, wrong lot/bin scope or exited units could create duplicate or ghost stock | Canonical scoped position constraints, item/lot/unit/bin relations and exited/consumed/returned identity rules | Corrected in plan; implementation remains planned |
| RF43: Complete value history | Mutable remaining costs or missing provisional cost could appear as a valid value ledger | Immutable normal/adjustment value legs, selected pool/layer history, explicit valuation status and exact residual reconciliation | Corrected in plan; implementation remains planned |
| RF44: Owner atomicity and lock coverage | Concurrent issue, count/hold or absent-position creation could corrupt stock and financial state | Common owner/scope lock order, commit-time checks and atomic quantity/value/unit/claim/GL/result/outbox writes | Corrected in plan; implementation remains planned |
| RF45: Transfer/return source conservation | Another shipment, invoice or repeated correction could consume the wrong physical source | Exact partial shipment claims, paired legs, bounded cumulative returns and dependency-aware corrections | Corrected in plan; implementation remains planned |
| RF46: Operational versus report repair | Reports rebuild or unguarded balance replacement could race live stock execution | Fenced owner-state repair, immutable historical inputs and separately verified Reports generation cutover | Corrected in plan; implementation remains planned |
| RF47: Import completeness and cost provenance | Retried chunks or missing migration data could duplicate stock/opening assets or invent history | Staged row identities, cutover/coverage, explicit unknown evidence and whole-import reconciliation | Corrected in plan; implementation remains planned |
| RF48: Configuration readiness and execution verification | New master fields/modes could be mistaken for stock enforcement or automatic custody changes | Reconcile parallel configuration under existing gates; add STK01-STK20 and a source/value conservation fixture | Corrected in plan; implementation remains planned |
| RF49: Repeated component scopes | One discount/tax field loses quantity, stacked and selected-line terms | Require native scope, input/basis/denominator and bounded dependencies; CAL01-CAL04/CAL15 | Corrected in plan; implementation remains planned |
| RF50: Header and multiple tax components | Header tax can duplicate line tax or mix incompatible statutory bases | Normalize header entry to supply components; retain value/quantity rules and legal combinations; CAL05-CAL08 | Corrected in plan; implementation remains planned |
| RF51: Purchase-return entitlements | Repricing partial returns loses original discounts and overclaims residual amounts | Freeze source component allocations and return treatment; cap cumulative claims atomically; CAL10-CAL12 | Corrected in plan; implementation remains planned |
| RF52: Return evidence and money timing | Stock return, purchaser advice, supplier tax note and refund could recognize one credit repeatedly | Separate linked effect identities, statutory adjustment evidence and settlement; CAL13 | Corrected in plan; implementation remains planned |
| RF53: Supplier credit versus stock cost | Tax-inclusive credit or nonrefundable freight could incorrectly set returned inventory value | Reconcile commercial, tax and carrying-value bridges, including late costs and issued stock; CAL09/CAL14 | Corrected in plan; implementation remains planned |
| RF54: Component implementation traceability | Broad invoice scope lacks concrete examples and regression evidence | Add stacked invoice/five-part return fixture and CAL01-CAL16 within existing batches and registers | Corrected in plan; implementation remains planned |
| RF55: Commercial configuration authority | Form toggles or class defaults could enable every mechanic regardless of company/type rules | Separate native Sales/Purchase policies, restrictive bindings and effective controls; CAL17/CAL23/CAL27 | Corrected in plan; implementation remains planned |
| RF56: Manual bonus versus automatic scheme | Actual/billed fields could be mistaken for an implemented automatic deal engine | Separate term evidence from rule eligibility and atomic reward consumption; CAL18/CAL19 | Corrected in plan; implementation remains planned |
| RF57: Free presentation versus tax and cost | Zero amount could erase stock cost or incorrectly exempt a gift or bundled supply | Preserve native purpose, legal classification and all-unit cost; CAL20-CAL22 | Corrected in plan; implementation remains planned |
| RF58: Reward duplication and return treatment | Lot splits/conversions or partial returns could award twice or create an unagreed gift debt | Disjoint paid/reward claims, original allocations and pinned award scope/trigger; CAL25/CAL26 | Corrected in plan; implementation remains planned |
| RF59: Configuration lifecycle enforcement | API/import or stale policy could bypass a hidden/disabled UI control | Enforce controls across entry paths, quote digests and publication/stop versus posting fences; CAL23/CAL24 | Corrected in plan; implementation remains planned |
| RF60: Deal delivery and reporting evidence | Definition support could imply live scheme readiness or reports could count free value twice | Gate automatic mechanics on all owners, expose readiness and reconcile benefit/stock facts; CAL27/CAL28 | Corrected in plan; implementation remains planned |
| RF61: All-kind configuration coverage | Sales controls alone leave account/stock/order/job types without explicit native settings | Add 22-kind settings/capture/effect matrix and shared registry; VCF01/VCF02 | Corrected in plan; implementation remains planned |
| RF62: Policy storage and resolved evidence | Live defaults or arbitrary key/value settings could reinterpret historical entries | Add shared profile/revision/binding candidates, typed schemas and captured effective-config evidence; VCF03-VCF05/VCF24 | Corrected in plan; implementation remains planned |
| RF63: Numbering and date semantics | Copying Tally options could renumber issued evidence or confuse credit-terms and posting dates | Preserve allocator/immutable identity and separate date-purpose contracts; VCF06/VCF07 | Corrected in plan; implementation remains planned |
| RF64: Account/bank configuration | Entry modes or ledger defaults could bypass role, bill or instrument requirements | Validate source roles, targets, tender changes and supported Journal purposes; VCF08-VCF11 | Corrected in plan; implementation remains planned |
| RF65: Inventory/fulfillment settings | Display/class/source settings could repeat movement, overwrite counts or convert quotes into commitments | Enforce native operation profiles, protected observations and source/scenario boundaries; VCF13-VCF18 | Corrected in plan; implementation remains planned |
| RF66: Job role and consumption | Material In/Out configuration could confuse ownership or consume raw materials twice | Pin principal/worker profile and validate separate/combined source consumption; VCF19-VCF21 | Corrected in plan; implementation remains planned |
| RF67: Configuration adoption and external actions | Stale clients or print/share/payment defaults could bypass controls or replay postings | Bind effective registry/digests to all entry paths; fence publication; separate retryable follow-up; VCF22/VCF23 | Corrected in plan; implementation remains planned |
| RF68: Configuration release and report evidence | A saved setting could imply readiness or reports could resolve current defaults for old documents | Verify settings by profile/batch and retain captured lineage; VCF01-VCF24 within existing release gates | Corrected in plan; implementation remains planned |

These dispositions close planning defects only. The corresponding contracts and tests still
need implementation evidence in their batches. Existing open costing, VAT and approval choices
were preserved rather than guessed. No new voucher-specific table family, service, payroll
scope or blanket Tally feature-parity promise was introduced.

## 2. How to execute and record a batch

The 38 work-package IDs remain stable. They are divided into **45 batches** because V4.3
and V4.5 each require two slices, and V9.2 requires six incremental slices. One batch may be
split into smaller suffixed batches when its reviewed implementation is still too large;
record all resulting prerequisites and evidence without marking the parent complete early.

Use these statuses:

- **PLANNED:** scope recorded; entry conditions not yet all satisfied.
- **READY:** prerequisite evidence and applicable decision records exist; no work claimed done.
- **IN_PROGRESS:** implementation and its tests/contracts are being completed.
- **BLOCKED:** record the exact unresolved condition and the independent work that can continue.
- **VERIFIED:** batch exit evidence is complete for its declared slice, including review fixes.
- **NOT_SELECTED:** only for an optional capability, with an explicit scope decision reference.

Before implementation, name the actual owner and files/services/migrations for the batch,
confirm prerequisites, resolve its applicable D-gate slice, and record acceptance subcases.
"Accounting + Vouchers" below is an ownership boundary, not an assigned person or an
instruction to create multiple agents. Cross-service contracts require both sides to agree.

Finish each batch with matching migration/model/schema/domain/API/worker changes, generated
contracts/clients and applicable permissions/roles/field metadata. Update tests and docs in
the same batch. Tests appropriate to the changed behavior must pass; baseline failures must
be reported and cannot excuse a newly failing dependency. Preserve unrelated working changes.

**VERIFIED is not ENABLED.** A profile's activation record separately establishes backend,
tax/statutory, web/mobile or explicitly API-only, reports and operations readiness. An AC
scenario may span batches; passing its primitive/calculation subcase is not passing its
end-to-end posting/recovery case. Record remaining subcases until the release checkpoint.
Use scoped feature gates so unfinished profiles cannot be invoked through import, direct API,
background jobs or a custom type while appearing disabled only in the UI.

## 3. Ordered batch register

B01-B08 are verified for their common C0 foundation slices; B09 is verified for its
export/projection/run foundation and B10-B14 for ordinary money and financial reports.
B15 is the next ordered implementation batch.
[Phase 1 evidence](voucher-phase1-execution.md) records the concrete scope, native tests,
contracts and remaining profile/activation obligations. Prerequisites below reference
completed evidence, not merely files that exist. Optional B42-B44 are skipped
unless selected; they do not block required job work. Per-phase D07 schema/API limits apply
to every batch adding or changing structures, even when not repeated in the gate column.

| Batch | Package/slice | Owner | Concrete boundary | Prerequisites | Decision/gate basis | Status |
|---|---|---|---|---|---|---|
| B01 | V0.1 | Integration | Existing service/test/client baseline and legacy compatibility inventory | None | Record actual baseline and unresolved failures | VERIFIED |
| B02 | V0.2 | Accounting + Vouchers + Identity/Reports | Foundation schema, kind/profile matrix, source/settlement and statement/opening coverage; D12 date/year/numbering schema and readiness ownership; define account/source lineage and fact/summary/register grains; stock capture/cardinality/value-history and parallel configuration compatibility contracts; native component/dependency/return-claim manifest under D04/D05/D07; resolve native commercial policy/binding, paid/reward identity and policy/posting fences under D01/D04/D06/D07; finalize the 22-kind configuration/capture/effect matrix and shared native settings registry; VCF01-VCF04. | B01 | Resolve D01 and initial D04/D05/D06/D07/D11 slices; record later gates; applicable D12/FY checks | VERIFIED |
| B03 | V0.3 | Accounting + Vouchers + Catalog/Identity/Reports | Signed command/result, source snapshots, committed export/catch-up barrier and recovery contracts; period-version/producer close evidence, reopen invalidation and year-boundary recovery contracts; specify balance read compatibility, atomic projection/checkpoint and rebuild-generation contracts; stock lock/write order, source claims, guarded operational repair and staged-import contracts; specify effective-config digest, typed command evidence, publication/stop fences and compatibility/adoption fixtures; VCF05/VCF22. | B02 | D01, initial D04/D06/D11; fixtures and version compatibility; applicable D12/FY checks | VERIFIED |
| B04 | V1.1 | Vouchers + platform integration | Service/DB/gateway/auth/audit/worker/client scaffold | B03 | D07 foundation manifest; native readiness checks | VERIFIED |
| B05 | V1.2 | Vouchers | Minimal types/sections before common document/revision/line and ITEM identity/detail; add shared native commercial-policy revision/bindings; separate company Sales and Purchase controls; create or reuse shared policy profile/revision/binding storage with native constraints and immutable accepted configuration evidence; VCF02/VCF05. | B04 | D06 document authority; scoped FKs and migration order | VERIFIED |
| B06 | V1.3 | Vouchers + Identity | Type/class administration, both custom-field entities, adoption/indexes and field-set; implement restrictive type/class policy inheritance, publication, effective controls and scope/override validation; CAL17/CAL23/CAL24/CAL27; deliver all-kind policy/type/class administration, registry discovery, effective settings and scoped publication; VCF01-VCF05/VCF22. | B05 | Existing 12 types and V1a-V1c tests; no type-specific DDL | VERIFIED |
| B07 | V1.4 | Vouchers + Accounting | Durable operation, command/result, source guard and cancel/recovery machinery; effect-date/period commit guards and close/retry races; retain exact committed financial source/line distributions and durable owner identity; enforce configuration digests at operation stages and retry/scheduled execution; VCF06/VCF07/VCF22. | B06 | D01/D04/D06 authority and source identity; AC04/AC05 slices; applicable D12/FY checks | VERIFIED |
| B08 | V1.5 | Vouchers + clients | Artifacts/templates, issue series, common entry/history and signed access; company/year/date selection and immutable internal/statutory/issue numbering; use effective allowed/required/editable controls and paid/reward/actual presentation; CAL23/CAL27; use the common field-set/effective settings for numbering, narration, required capture and artifact defaults; VCF03/VCF06/VCF23. | B07 | D05 numbering foundation and D06 issue policy; monetary posting remains gated; applicable D12/FY checks | VERIFIED |
| B09 | V9.1 | Reports + source owners | Complete financial/classification/opening/settlement feeds, snapshot barrier, report definitions/runs/artifacts and reconciliation; fiscal history coverage and dependent carry-cache invalidation; line-grain account facts, selected day/period totals, atomic dedupe/checkpoints and verified generation cutover | B08 | Initial D11 export/permission/coverage contract; no cross-service SQL; [B09 evidence](voucher-b09-execution.md) | VERIFIED |
| B10 | V2.1 | Accounting + Vouchers | Journal/Contra, account/tender primitives and immediate cash/bank validation; company-year generation/opening, readiness and resumable close/reopen integration; preserve cumulative balance API and add declared authoritative period/current/currency semantics; enforce configured Contra/Journal account roles, modes, cash/bank, dimensions and date purposes; VCF04/VCF07/VCF08/VCF11. | B08 | D04 ledger/FX scope; D06 accounts/dimensions/basic bank policy; applicable D12/FY checks | VERIFIED |
| B11 | V2.3 | Accounting + Vouchers | Atomic bill/advance allocation, dated reallocation/reversal and competing-value guards; new-year receipts/advances allocating to prior-year bills with original due dates; export dated allocation/reversal evidence without invented GL deltas; retain explicit chosen bill targets and original due-term basis under tracking/configuration changes; VCF09. | B10 | D04 batch atomicity; test against existing supported open-item fixtures | VERIFIED |
| B12 | V2.4 | Accounting + Vouchers | Instrument input/history, reference/date, clearing and post-dated recognition; validate configured tender/reference/instrument defaults, mode changes and PDC recognition; VCF10. | B11 | D06 instrument policy; no provider execution | VERIFIED |
| B13 | V2.2 | Accounting + Vouchers | Complete Payment/Receipt, purposes, refunds, splits and settlement adjustment legs; verify Payment/Receipt modes, bill selection and recognition against native policy; VCF08-VCF10. | B10, B11, B12 | D04/D06; tax-bearing profiles wait for B16-B19 | VERIFIED |
| B14 | V9.2 — money | Reports + Accounting | B14a-B14d: account ledgers, TB, P&L/Income & Expense, Balance Sheet, opening/earnings bridges and party/cash/bank registers; cross-year opening/earnings, as-of allocations and BRS continuity fixtures; B14a daily/monthly account/group ledgers and gross running totals; B14d role/currency/bank reconciliation; applicable BAL checks; expose captured type/profile/class/policy lineage in account and money registers; VCF24. | B09, B13 | D11; AC26 and applicable RPT checks; C1 checkpoint; applicable D12/FY checks | VERIFIED |
| B15 | V3.1 | Accounting + Vouchers + Catalog | Canonical accounts/item/mixed calculation, charges/discounts and preview evidence; quantity/line/selected-line/invoice stacking, named dependency bases and CAL01-CAL04/CAL07/CAL15; implement configured sales/free/deal preview and stacking; CAL18-CAL22/CAL27; automatic schemes require published Catalog definitions and the single authoritative runtime. | B13 | D04 calculation/FX bounds; advance results use B11/B13 | IN_PROGRESS |
| B16 | V3.2 | Accounting + Identity/Catalog | Line tax/event dates, tax snapshot compatibility, advance/ITC/RCM/withholding; header tax normalization, value/quantity tax components and CAL05-CAL08/CAL13; distinguish sample/gift versus paid-supply reward tax purposes and mandatory tax despite UI flags; CAL20/CAL21/CAL23. | B15 | D05 and D09 GST profile/rule versions; T0/T1 | IN_PROGRESS |
| B17 | V3.3 | Accounting + Vouchers | Account/service invoices and notes with combined credit/settlement; financial-only purchase returns and original-component credit/supplier-note/refund reconciliation; applicable CAL09-CAL13; preserve account/service restrictions and original benefit correction authority under CAL25. | B13, B16 | No stock-bearing posting; statutory activation waits for B19 | IN_PROGRESS — native Sales/Purchase owner posting, public guarded producer, accepted revision and untaxed source-linked Credit/Debit Notes with original-bill offset and cash settlement; tax/component notes and broader refunds remain |
| B18 | V9.2 — invoices/tax | Reports + Accounting | Invoice/tax registers and event/credit/settlement/GL bridges, frozen exports and financial-statement rechecks; invoice/tax/settlement register grains and joins without multiplied document totals; component-level purchase/return/tax drill-down and CAL06/CAL16; expose monetary versus informational benefits, paid/reward quantities and tax bridges; CAL28; retain accepted policy lineage in invoice/tax facts and exports; VCF12/VCF24. | B09, B17 | D11 tax extension; T4 data/export subset; source events may be unsubmitted | IN_PROGRESS — invoice/credit grains, untaxed source-linked notes, GL/open-item reconciliation and native Reports 90.44% coverage; dependent advance/benefit profiles and full verification remain |
| B19 | V3.4 | Vouchers + Reports + clients | Statutory artifacts/evidence/issue gates, export handoff and service-invoice release; statutory invoice-year identity independent of GL posting year | B08, B17, B18 | D05/D09, applicable T4 and C2; external success never assumed; applicable D12/FY checks | PLANNED |
| B20 | V4.1 | Accounting + Catalog/Vouchers | Canonical stock positions, lot/unit/origin/hold history and versioned Catalog policy/group/unit contracts; native movement/position/unit/origin/value references, scoped uniqueness and accepted policy snapshots | B19 | D01, D02/D03 and D07 stock manifest; INV01 | PLANNED |
| B21 | V4.5 — guards | Accounting + Identity | Stock-period, count/hold/expiry/eligibility, first-use/configuration and backdate guards; stock-effective versus accounting period guards across year boundaries; absent-position/count/hold guards, shared lock order and configuration enforcement gates | B20 | D01/D03; INV04/INV06; no fake GL journal; applicable D12/FY checks | PLANNED |
| B22 | V4.3 — valuation | Accounting | Cost/recognition scope, layers/pools and source-cost allocations independent from quantity receipt origins; immutable value legs, chosen layer/pool history, valuation status and residual conservation; commercial-credit versus stock-carrying-value bridge; CAL09/CAL14 | B21 | D02; INV08/INV17; native-DB evidence before executable movement | PLANNED |
| B23 | V4.2 | Accounting + Vouchers | Receipt/delivery/challan, immediate/transit transfers and controlled openings; actual/base/tracking capture, paired transfer legs, partial shipment claims and resumable reconciled openings; enforce note/challan/transfer mode and tracking controls without duplicate movement; VCF13/VCF14. | B20, B21, B22 | D02/D03, T2/relevant T4; quantity and value guards present together | PLANNED |
| B24 | V4.3 — invoice integration | Accounting + Vouchers | Direct, movement-reference and deferred goods/mixed invoicing and cost clearing; invoice references versus physical execution, provisional cost/clearing and no duplicate movement; multi-scope purchase components, payable/tax/landed-cost bridges; CAL03/CAL09/CAL14; record manual free goods and atomically consume supported automatic 10+1; all-unit stock/cost and required publication/stop fences; CAL18-CAL24. | B23, B16 | AC12/AC15 full posting slices; one physical/cash owner | IN_PROGRESS (2026-11-03: direct goods/mixed Purchase capture, calculation, posting and Purchase-screen entry, with standard stock accounts at company setup; Receipt Note linking, returns and sales goods remain) |
| B25 | V4.4 | Accounting + Vouchers | Returns/counts, holds/quarantine, loss/impairment/disposal and origin/unit evidence; source-capped returns, exited-unit reuse, reviewed count observations and impairment/disposal lineage; original component return entitlements, concurrent quantity/value/tax caps and final residuals; CAL10-CAL14; return original paid/reward units without automatic gift-list-price debt, coupon restoration or new award; CAL25; enforce protected-count settings and independent source-linked return controls; VCF15/VCF16. | B24 | D02/D03; INV09/INV15/INV16 and source/concurrent count guards | PLANNED |
| B26 | V4.5 — corrections | Accounting | Supported revaluation/backdating, lot-date revisions, cost correction and historical reconciliation; value/quantity correction and fenced owner-state repair with downstream dependency checks; late cost and cross-year purchase-return bridges under CAL14 | B24, B25 | D02/D03; INV07/INV17; unsupported corrections remain rejected | PLANNED |
| B27 | V9.2 — stock | Reports + Accounting/Catalog | B27a-e: current/item ledgers, group/location, lot/serial/expiry/age, valuation/GL, movement/count/damage and protected snapshot exports; year-boundary quantity/value/origin/expiry continuity in B27e; stock-value control balances reconcile to account facts at one snapshot; movement/value-grain projections, nonmultiplying joins, verified generations and applicable STK checks; purchase/return component-to-stock/GL reconciliation under CAL16; reconcile paid/reward/actual quantity, all-unit COGS and returns without double benefit; CAL28. | B09, B26 | D02/D03/D11; AC15-AC18/AC26 and applicable INV01-INV24; applicable D12/FY checks | IN_PROGRESS - [ten report consumers and evidence adapter implemented](reports-framework/inventory-implementation.md); B20-B26 stock producers and full stock acceptance pending |
| B28 | V5.1 | Vouchers + clients | Plain requisition, quotation and Sales/Purchase Order lifecycle; make quotation/indent/order profile settings and captured due/source facts explicit; VCF17. | B08, B15 | D06 approvals; estimates only, no implicit commitment/reservation from quotes/indents | IN_PROGRESS (capture only; upstream gate open) |
| B29 | V5.2 | Vouchers | Fulfillment schedules, source claims and split/consolidated conversion; preserve source-scoped paid/reward entitlement and allocation identity through split/consolidated conversion; CAL26. | B28 | D07 schedule/link contract; compatible source/revision/unit scope | PLANNED |
| B30 | V5.3 | Vouchers + Accounting | Link orders to movements/bills, acknowledgments, return/close/reopen/replacement; enforce reward award-scope/trigger through partial billing and fulfillment; no duplicate or unsupported deferred awards; CAL26; verify per-line source, tolerance, partial fulfillment and pre-close/reopen configuration; VCF17. | B29, B26 | AC19/AC20; claims and effect outcomes fenced together | PLANNED |
| B31 | V5.4 | Accounting + Vouchers | Explicit stock/credit reservation, expiry and consumption where selected; reservation/source claims share issue/hold/count guards and preserve transition evidence | B30 | D03/D06 reservation policy; non-reserving profiles do not depend on activation | PLANNED |
| B32 | V9.2 — orders | Reports + Vouchers/Accounting | Indent/quote/order schedules, unmatched goods/bills, closure and deduplicated supply/demand/projected-stock/reorder views; prior-year backlog/claims and cross-year fulfillment without origin-year exclusion; verify optional/post-dated/general profile settings, date purposes and actualization authority; VCF07/VCF18. | B09, B30; B31 if reservation views enabled | AC19-AC21 and INV19/INV20; absent producers are unknown, not zero | PLANNED |
| B33 | V6.1 | Vouchers | Memo/optional/pro-forma and conversion to implemented real profiles | B08, B30 | Conversion only to ready targets; no actual effect from optional content | PLANNED |
| B34 | V6.2 | Vouchers + Reports | Scenario membership/windows and scenario Reversing Journal | B33, B09 | AC22; no actual reversal by scenario expiry | PLANNED |
| B35 | V9.2 — scenarios | Reports | Actual-versus-scenario registers/exports and core report reconciliation | B34, B27, B32 | AC22/AC26 scope segregation | PLANNED |
| B36 | V6.3 | Vouchers + Reports/clients | All core histories/artifacts/retirement and 18-kind activation review; reconcile provisional/scenario configuration and actualization without toggling posted history; VCF18. | B35 | C3, all applicable T/AC cases and explicit client readiness | PLANNED |
| B37 | V8.1 | Catalog + Vouchers | Required BOM/process subset, requisition preparation and job templates; publish compatible principal/worker/BOM/process configuration templates and enforce readiness; VCF19. | B30 | D08/D07 selected depth; no blanket activation of optional Catalog tables | IN_PROGRESS (exact preview and typed policy only; B30 gate open) |
| B38 | V8.2 | Vouchers + Accounting | Both job-order/material directions, direct/onward movements, custody and returns; cross-year own/third-party custody, original dispatch evidence and bounded return claims; capture owner/custodian and Material In/Out role/consumption configuration; VCF19/VCF20. | B37, B23, B25 | D08/D09 material profiles; original dispatch evidence; release waits for B41 | PLANNED |
| B39 | V8.3 | Accounting + Vouchers | Manufacturing consumption/outputs, WIP, scrap, genealogy and actual cost; actual input/output/scrap genealogy and cost conservation across distinct SKU/unit quantities; execute configured combined/separate consumption once with exact source/BOM/yield/cost evidence; VCF20/VCF21. | B37, B38, B26 | D02/D08 transformation scope; quantity/cost reconciliation | PLANNED |
| B40 | V9.2 — job work | Reports + source owners | Job/custody/WIP, origin/age/genealogy, owned-WIP-to-statements and applicable ITC-04 exports; cross-year custody/WIP/challan age without resets; WIP/control balances reconcile to account facts at one snapshot; reconcile source movements, value/WIP and custody without multiplying genealogy joins; retain configuration/job-source lineage in custody/WIP/statutory report facts; VCF21/VCF24. | B38, B39, B18 | D11; INV09/INV18; T3/T4 export subset, no reset of custody aging | PLANNED |
| B41 | V8.4 | Vouchers + Accounting/Reports | Processing invoices/settlement, challan/aging exceptions and statutory handoff | B40, B19 | D08/D09 and T3/relevant T4; all four job kinds covered | PLANNED |
| B42 | V7.1 — optional | Vouchers + Accounting | Selected provider execution/callback/result, fee/refund/chargeback | B13, B19 | D10 selected provider scope; AC27 before activation | IN_PROGRESS (Razorpay validation only; B19 gate open) |
| B43 | V7.2 — optional | Vouchers + Accounting/Reports | Selected statement imports, grouped/partial reconciliation and opening BRS | B14, B19 | D10 selected reconciliation scope; independent of B42 | IN_PROGRESS (R0–R5 mapped-CSV owner/API/report/console slice locally verified, including native import/match races; R6 B19 release gate and AC27 broker replay remain open) |
| B44 | V7.3 — optional | Vouchers + bank-master owner | Selected cheque-book/leaf/printing/void or cash denomination controls | B12 | D10 selected scope/master ownership; independent of B42/B43 | IN_PROGRESS (cheque/cash validation only) |
| B45 | V9.3 | All affected owners | Final backfill/load/recovery, reviews, report rebuild/frozen-run equivalence, full reconciliation and staged activation; two-year rollover/late-adjustment/recovery rehearsal and applicable FY01-FY24; BAL01-BAL20, account projection crash/rebuild/cutover and measured large-account load; STK01-STK20 transaction failure, import/repair/rebuild and supported-load evidence; applicable CAL01-CAL28 and purchase/sales/deal/partial-return rehearsal; rehearse applicable CAL17-CAL28 policy denial, scheme/stock/return replay and supported-profile rollout; verify applicable VCF01-VCF24 across policy changes, replay, rollout and historical reporting. | B36, B41; B42-B44 only if selected | C4; applicable RPT01-RPT20/INV01-INV24 and all selected readiness dimensions/findings; applicable D12/FY checks | PLANNED |

The [focused manufacturing/job-work plan](voucher-manufacturing-job-work-plan.md)
details B37-B41 typed settings, data/owner contracts, role paths and acceptance.
It changes neither the batch statuses above nor C4 readiness.

The sequence is a safe default, not a ban on independent progress. Earlier non-posting V5/V6
scaffolding can be implemented once its actual prerequisite slice is verified; record such
a split explicitly. Do not bypass B21/B22 to post stock, or activate an invoice without its
statutory/report gates. B31 selection is recorded per reservation capability; it cannot become
an implicit requirement to reserve merely by issuing an order.

B14 is split into four suffixed tasks in the live todo: ledgers/TB (a), P&L/Income & Expense
(b), Balance Sheet/openings/earnings/comparatives (c), party/cash/bank and reconciliation (d).
These do not increase the 45-parent count. All require B09/B13 and the relevant D11 slice;
b/c reuse a's reconciled facts, and d completes the combined acceptance fixture. B18, B27
and B40 extend financial checks when their source profiles become available. Statement
readiness at C1 covers only the declared money/history scope, not later inventory or tax.

B27 now has five required suffixed tasks: current/item balances (a), groups/locations (b),
batch/serial/expiry/age (c), value/GL and action registers (d), secure exceptions/exports and
combined reconciliation (e). They retain B09/B26 prerequisites, with b-d using a's facts and
e completing the combined checks. This does not increase the 45-parent count or make B31
reservations mandatory. B32 and B40 extend stock reports for commitments and job work.

Financial-year acceptance follows the linked design: C1 requires ordinary financial-year
readiness and continuity; C2 adds statutory-year identity; C3 adds stock/order year-boundary
checks; C4 adds job-work continuity and the B45 two-year rehearsal. These requirements use
existing batch IDs and do not depend on automated annual earnings-transfer journals.

Account capture/maintenance acceptance uses BAL01-BAL20: C1 includes ordinary GL,
account/group/daily/monthly/register and party/bank scopes; later checkpoints extend
invoice/tax, stock and WIP bridges. All summaries reconcile to Accounting facts at one
source snapshot. Existing B14a-d task IDs and optional-integration boundaries are unchanged.

STK01-STK20 are required applicable evidence for stock activation: C3 covers capture,
quantity/value transactions, storage constraints and recovery; C4 extends job-work and
manufacturing. Configuration-only changes cannot satisfy these execution gates. B31 remains
conditional and no automatic quarantine/negative-stock relaxation is selected here.

## 4. Decision records and scope limits

Every D gate starts **OPEN** for its remaining implementation contract. Previously agreed
requirements remain settled; OPEN does not reopen payroll exclusion, common tables, India as
the jurisdiction, required job work or the voucher catalogue. A gate can close in phase-specific
slices; record which later slices are still open instead of marking the whole gate done.

| Gate | First recorded output | First dependent implementation | Current record |
|---|---|---|---|
| D01 | B02/B03 source/effect ownership, signing, first-use and cancel/recovery contract; stock extension detail before B20; commercial policy/posting fences and authoritative reward consumption; all-kind effective-config digest/readiness enforcement | B07; stock guards B20/B21 | OPEN |
| D02 | Cost/recognition scope and mapping; quantity receipt origins versus cost layers/pools; worked opening/receipt/dispatch/correction examples; immutable value/cost-state history and valuation readiness; purchase capitalization and source-return credit/carrying-value mappings | B20-B24; WIP extension B39 | Purchase recognition DECIDED 2026-11-03 (bill adds stock at landed cost; [review](purchase-product-review.md#owner-decisions-2026-11-03)); OPEN otherwise; FIFO and moving average both selected 2026-10-11. Count surplus uses current verified native stock cost, mandatory review when absent (2026-10-30); [count plan](tenant-admin-stock-entry-plan.md) records the selected slice, not owner delivery. |
| D03 | Negative-stock rejection baseline, hold/expiry-day/minimum-life, backdate/close/count/transit and reservation fences, including zero-GL effects; native stock scope lock order and fenced repair | B20/B21; count B25 and reservation B31 | OPEN overall; count permits movements reconciled against a recorded cutoff (2026-10-30). Native grain, lock/fence and owner acceptance remain under B25; [count plan](tenant-admin-stock-entry-plan.md). |
| D04 | Source/party/distribution/FX support matrix, aggregate limits and atomic allocation result; atomic original-component monetary/tax return entitlement claims; disjoint paid/reward identity and award-scope/trigger contract | B07/B10/B11; invoice extension B15-B17 | OPEN |
| D05 | Issue-versus-posting numbering owner/schema in B02; tax dates/registrations and old-reader migration; legal profile artifact sequence; multi-component tax bases and supplier-return adjustment evidence; configured number-method/override compatibility with immutable issued identities | Numbering schema B04-B08; tax B16/B19 | OPEN |
| D06 | Action/approval/location/field authority and limits; dimension and instrument scope; Sales/Purchase/type/class commercial policies and override/stack authority; all-kind setting applicability/merge/requiredness/adoption and VCF coverage | B05/B06; money B10-B13; each later profile before activation | OPEN |
| D07 | Table/column/index/constraint, API and migration manifest for each batch, including early ITEM identity; stock leg/position/unit/source constraints and import chunk identity; bounded native component dependency/basis and return-source relations; shared commercial-policy revision/binding and paid/reward membership manifest; shared native policy profile/revision/binding and effective-settings snapshot manifest | B04 onward, reviewed before its migrations | OPEN |
| D08 | Minimum required BOM/process/job material/cost/variance contract; advanced optional depth separated; principal/worker and separate/combined consumption profile/claim evidence | B37-B41 | OPEN; baseline first selected 2026-10-11, multi-level/substitutions excluded initially |
| D09 | India GST profile/effective-rule/evidence matrix; jurisdiction is settled, actual supported cases must be explicit | B16/B19; movement B23; job work B38-B41 | OPEN; job-work time-limit cases flag for review, no automatic invoice/posting (2026-10-11) |
| D10 | Positive selection and ownership for each optional provider/bank/recurrence feature | B42-B44 or separately planned extension | OPEN for implementation/certification; user selected Razorpay, mapped CSV statements and both cheque-book/cash-denomination controls on 2026-10-11; recurrence remains unselected |
| D11 | B02/B03 statement classification, opening/YTD coverage, earnings, snapshot/catch-up and permission contracts; tax/stock/WIP extensions with their phases; native account/source lineage, fact/day/period/register grains and projection generation/read contracts; stock movement/value projection grains and safe generation cutover; configuration lineage in captured register/report facts | B09/B14, then B18/B27/B40 | OPEN |
| D12 | B02/B03 company calendar/date/numbering-year and close-evidence contracts; existing monthly APIs versus planned readiness/reopen cache integration; credit-terms effective date distinct from posting/stock/statutory dates | B07/B08/B10; fiscal slices in B14/B19/B21/B27/B32/B40/B45 | OPEN |

Each record contains the question, settled requirements, chosen supported behavior and rejected
or deferred cases, effective version, accountable reviewer, rationale, contract/schema/API
impact and test fixtures. Record an actual decision, never infer one from elapsed time or a
generic phase approval. Work unaffected by an open decision can continue.

Phase 2's [implementation record](voucher-phase2-execution.md#implemented-scope-and-decision-slices)
records the concrete ordinary-money selections for D01/D04/D06/D11/D12 and their D07
migrations. Accounting remains the single GL/allocation authority; STANDARD Journal/Contra/
Payment/Receipt and Payment/Receipt ADVANCE use current owner policies, manual banking
evidence and retained-history reports. Dimensions, imported pre-cutover YTD, automatic PDC
execution and annual profit-transfer automation are excluded from this slice. Tax, inventory,
orders and job-work extensions keep these gates OPEN for their own contracts and evidence.

India state-VAT remains required architectural extensibility with a separately selected
state/commodity pack under T5; no state is silently assumed. When selected, add explicit
extension batches, legal-source review, schemas/registers and tests before activation.
Supplier RFQs/bid comparison, advanced banking and recurring execution likewise need their
own selected extension scope. Manual Payment/Receipt and bank-reference support remain core.

## 5. Coverage and activation checkpoints

Each base kind maps to common structures and a delivery batch. Company-defined types and
profiles reuse these behaviors; they are not new independent posting tables.

| Base kind | Implementation batch | Required activation checkpoint |
|---|---|---|
| `CONTRA` | B10; supported instrument extensions B12 | C1 |
| `PAYMENT` | B13; tax-bearing profiles B16-B19 | C1 ordinary; C2 tax-bearing |
| `RECEIPT` | B13; tax-bearing profiles B16-B19 | C1 ordinary; C2 tax-bearing |
| `JOURNAL` | B10; supported bank/tax profiles B12/B16 | C1 ordinary; C2 tax-bearing |
| `SALES` | B17 accounts/service; B24 goods/mixed execution | C2 accounts/service; C3 goods |
| `PURCHASE` | B17 accounts/service; B24 goods/mixed execution | C2 accounts/service; C3 goods |
| `CREDIT_NOTE` | B17 financial; B24/B25 inventory-linked | C2 financial; C3 inventory-linked |
| `DEBIT_NOTE` | B17 financial; B24/B25 inventory-linked | C2 financial; C3 inventory-linked |
| `RECEIPT_NOTE` | B23 | C3 |
| `DELIVERY_NOTE` | B23 | C3 |
| `REJECTIONS_IN` | B25 | C3 |
| `REJECTIONS_OUT` | B25 | C3 |
| `STOCK_JOURNAL` | B23 transfer; B39 manufacturing | C3 transfer; C4 manufacturing |
| `PHYSICAL_STOCK` | B25 | C3 |
| `MATERIAL_IN` | B38/B41 | C4 |
| `MATERIAL_OUT` | B38/B41 | C4 |
| `SALES_ORDER` | B28-B30 | C3 |
| `PURCHASE_ORDER` | B28-B30 | C3 |
| `JOB_WORK_IN_ORDER` | B38/B41 | C4 |
| `JOB_WORK_OUT_ORDER` | B38/B41 | C4 |
| `MEMORANDUM` | B33 | C3 |
| `REVERSING_JOURNAL` | B34 scenario behavior | C3 |

| Required cross-kind capability/profile | Covered by |
|---|---|
| Plain purchase/material indent; BOM-assisted requisition | B28/B29, later B37; non-posting REQUISITION profile |
| Quotation acceptance/expiry, bounded conversion | B28/B29; QUOTATION profile; no committed order until conversion |
| Delivery Challan and supplier challan evidence | B23/B30; common movement/reference/artifact sections; T2/T4 gates |
| Advances, bill adjustments, refunds and split payment modes/references | B11-B13, B16/B17; no extra Advance or Bill Adjustment base kind |
| Accounts-only, item/mixed invoice, charges/taxes/discounts and landed cost | B15-B19, B22-B26; common sections and one effect owner |
| Runtime company voucher types and typed header/item custom fields | B05/B06; exercised again in every conversion/import/export phase |
| Journal dimensions and bank instruments | B10/B12 under declared D06 scope; enhanced banking only if selected |
| India GST, credit/RCM, tax events and required returns/artifacts | B16/B18/B19, movement B23/B24, job work B40/B41 |
| Stock locks, serial/lot/owner/custody, opening/count/period integrity | B20-B27; reservations B31 where enabled |
| Principal/worker job work, supported manufacturing, WIP/scrap/genealogy | B37-B41; payroll/HR excluded |
| General/scenario documents, day book/history and protected printing | B08, B33-B36; scenario views excluded from actual books |
| Account ledgers, TB, P&L/Income & Expense, Balance Sheet, opening/earnings and GL/subledger bridges | B09/B14a-B14d; tax B18, stock/COGS B27, WIP B40; RPT01-RPT20 evidence |
| Current/item/group/location stock, batches/serials/expiry/age and inventory value/action registers | B20-B27a-e; projected supply/demand B32, reservations if B31 selected, custody/WIP B40; INV01-INV24 |

| Checkpoint | Minimum completed evidence | Activation result |
|---|---|---|
| C0 — foundation | B01-B08 | Common drafts/configuration/customization; no claimed financial product completion |
| C1 — ordinary money | B09-B14 including a-d plus relevant C0 evidence and AC01-AC09/AC25/AC26/RPT subcases | Four ordinary accounting kinds, ledgers/TB/P&L/Income & Expense/Balance Sheet and party/cash/bank reports at declared coverage; tax/incomplete instruments disabled |
| C2 — account/service | B15-B19 plus C1, applicable T0/T1/T4 and financial-statement rechecks | Eight accounting kinds for supported account/service profiles plus invoice/tax registers; no goods posting |
| C3 — 18-kind core | Required B20-B36 including B27a-e, plus C2; selected reservation scope; T2/T4 and applicable AC/INV evidence | Goods/order/general core, named stock/expiry/age registers and corresponding client/report readiness |
| C4 — 22-kind scope | B37-B41, B45 and C3; relevant T3/T4; optional batches only if selected | Required job work/manufacturing and final reconciliation; selected policies clearly declared |

For each activated company/profile record: type/profile/rule versions; applicable decisions;
verified batches and AC subcases; statutory artifact/export route; backend and worker readiness;
web/mobile readiness or explicit API-only scope; register/checkpoint freshness; unresolved
non-blocking limitations; activation operator/time and rollback/forward-repair procedure.
No field is inferred from a generic VERIFIED batch flag.

## 6. Batch evidence and handoff template

Append an entry here, or link a dedicated review artifact from the batch row, when work begins.
Keep the entry updated so another implementation session can resume without reconstructing intent.
Do not pre-fill successful commands, commit IDs, migration revisions or human approvals.

```text
Batch / package slice:
Status / actual owner / last updated:
Scope and capability flags:
Prerequisites and evidence links:
Applicable D decisions (closed slice; still-open slices):
Affected service paths and exact task files:
Schema manifest (owner/table/columns/keys/constraints/indexes/backfill/actual migration IDs):
API/event/field-contract versions; producer/consumer rollout order:
Implementation outcome and source/effect ownership:
AC scenarios and exact subcases covered; remaining subcases:
Verification commands, environment and pass/fail/skipped results:
Native DB/broker/gateway/concurrency/recovery evidence where applicable:
Generated clients and web/mobile/report/artifact checks:
Correctness/security/simplification review findings and fixes:
Existing failures or unresolved issues; exact impact and dependent batches:
Activation status (separate from batch verification):
Rollback/forward-repair and recovery notes:
Task commit reference if committed; publish reference only if actually published:
Next eligible batch and precise handoff:
```

Before VERIFIED, check the repository's synchronization rules: migrations match models,
routes match generated clients, events match consumers, permissions match roles/registries,
and changed decisions match their documentation/log. Apply company/field-denial and race
tests to all new surfaces, including imports and recovery tools. A report difference is not
fixed by editing a projection or deleting source effects.

## 7. Review validation and remaining work

The planning review checks local links/anchors, work-package and batch coverage, dependency
order/cycles, all 22 kinds, D01-D12, AC01-AC28, RF01-RF68, RPT01-RPT20, INV01-INV24,
FY01-FY24, BAL01-BAL20, STK01-STK20, CAL01-CAL28 and VCF01-VCF24 references, baseline table numbering and the
worked Decimal invoice/cost/fulfillment examples. These checks establish documentation
consistency only. Native DB, broker, API, application and statutory tests remain future batch work.

Initial batch-planning validation executed on 2026-10-10 (before the later financial-reporting expansion):

| Check | Recorded result |
|---|---|
| Inline Python document validation using `apis/identity/.venv/Scripts/python.exe` | PASS: 28 task documentation files, 383 local links/anchors, balanced fences and no trailing whitespace |
| Batch/package graph and initial status validation | PASS: 45 unique batches cover all 38 packages; prerequisite order is acyclic; optional B42-B44 are not required ancestors of job-work completion B41; only B01 is READY |
| Catalogue/gate/scenario/review coverage | PASS: tracker kinds exactly match all 22 architecture kinds; D01-D10, AC01-AC28 and RF01-RF08 are present |
| Candidate inventory and worked Decimal fixtures | PASS: 51 unique numbered baseline candidates preserved; invoice remainder 591, unit cost 70 and delivery/billing example reconcile |
| `git -c core.safecrlf=false diff --check` | PASS |
| Application/native DB/broker/statutory implementation verification | Not run; no implementation batch performed in this review |

Financial-reporting expansion validation executed later on 2026-10-10:

| Check | Recorded result |
|---|---|
| Inline Python document validation using `apis/identity/.venv/Scripts/python.exe` | PASS: 31 task Markdown files, 433 local links/anchors, balanced fences and no trailing whitespace |
| Batch/package/status and dependency checks | PASS: all 45 parent IDs agree across tracker/note/todo; 38 packages covered; prerequisites precede dependents; optional banking is not an ancestor of B41; B01 READY and others PLANNED |
| Coverage and checklist checks | PASS: 22 kinds, D01-D11, AC01-AC28, RF01-RF16, RPT01-RPT20 and 51 numbered baseline candidates; all 45 parents, four B14 sub-batches and five activations unchecked |
| Independent Decimal financial fixture | PASS: balanced entries; TB sides 31,800; assets 29,800 = liabilities 1,800 + equity 20,000 + earnings 8,000; receivable 7,800; tagged closing fixture clears nominal balances with unchanged net equity |
| `git -c core.safecrlf=false diff --check` | PASS |
| Implementation evidence | No application/native DB/broker/report API/statutory tests run; RPT checks remain future batch work |

Stock-recording/reporting expansion validation executed later on 2026-10-10:

| Check | Recorded result |
|---|---|
| Inline Python document validation using `apis/identity/.venv/Scripts/python.exe` | PASS: 32 task Markdown files, 465 local links/anchors, balanced fences and no trailing whitespace |
| Batch/package/dependency/status checks | PASS: 45 parent IDs match tracker/note/todo; 38 packages and 22 kinds covered; dependencies including expanded ranges precede dependents; optional banking does not gate B41; only B01 READY |
| Inventory coverage/checklists | PASS: D01-D11, AC01-AC28, RF01-RF24, RPT01-RPT20, INV01-INV24 and 51 numbered baseline candidates; all 45 parents, four B14/five B27 sub-batches and five activations unchecked |
| Independent Decimal inventory fixture | PASS: owned 85, local 81, eligible 36, reserved 8, available 28, transit 4 and value 850; impairment keeps quantity/value becomes 830; disposal leaves quantity 80/value 800; later expiry changes eligibility without quantity/value loss |
| `git -c core.safecrlf=false diff --check` | PASS |
| Implementation evidence | No stock/API/native DB/broker/report execution tests run; INV checks are future implementation requirements |

Financial-year expansion validation executed later on 2026-10-10:

| Check | Recorded result |
|---|---|
| Inline Python document validation | PASS: 34 task Markdown files, 501 local links/anchors, balanced fences and no trailing whitespace |
| Batch/package/coverage/status checks | PASS: 45 parents, 38 packages, 22 kinds, D01-D12, AC01-AC28, RF01-RF32, RPT01-RPT20, INV01-INV24, FY01-FY24 and 51 numbered candidates; acyclic prerequisites; only B01 READY |
| Todo and activation agreement | PASS: all 45 parents, nine B14/B27 sub-batches and five activations unchecked; optional banking does not gate B41 |
| Existing pure fiscal helper checks | PASS: twelve April/January/leap/short-month calendar cases; allowed manage/reopen permissions, terminal LOCKED and preceding-period guards |
| Independent Decimal two-year fixture | PASS: original assets/TB 31,800; old bill 8,800 then 4,800 after April receipt; late March adjustment yields assets 31,300 and earnings 9,500; frozen original unchanged; separate stock-origin carry preserves 30 units/value 300 |
| `git -c core.safecrlf=false diff --check` | PASS |
| Implementation evidence | No application/native DB/broker/statutory tests run and no fiscal transitions performed; FY01-FY24 remain future implementation acceptance requirements |

Account capture/maintenance review validation executed later on 2026-10-10:

| Check | Recorded result |
|---|---|
| Inline Python Markdown/link validation | PASS: 35 changed/untracked Markdown files checked, 529 local links/anchors, balanced fences and no trailing whitespace |
| Batch/package/coverage and status checks | PASS: 45 parents, 38 packages, 22 kinds, twelve gates, 28 AC, RF01-RF40, 20 RPT, 24 INV, 24 FY, BAL01-BAL20 and 51 numbered candidates; acyclic prerequisites; only B01 READY |
| Todo consistency | PASS: all 45 parents, nine sub-batches and five activations remain unchecked; optional banking is not an ancestor of B41 |
| Independent Decimal recording fixture | PASS: balanced entries, TB sides 11,562, assets 10,862/profit 200; bank gross Dr 550/Cr 1,250 and closing 9,300; customer 562; daily totals and running pages agree; register fanout detected; later reversal/adjustment preserves frozen May |
| Scoped documentation diff check | PASS: `git -c core.safecrlf=false diff --check -- CLAUDE.md docs` |
| Whole-workspace diff check | Reports trailing whitespace in separate Catalog `models/warehouses.py` and `schemas/warehouses.py` edits; those application files were not changed by this planning review |
| Implementation evidence | No application/native DB/broker/API or projection-recovery tests run; BAL01-BAL20 remain planned implementation requirements |

Stock capture/storage review validation executed later on 2026-10-10:

| Check | Recorded result |
|---|---|
| Inline Python Markdown/link validation | PASS: 35 changed/untracked Markdown files, 544 local links/anchors, balanced fences and no trailing whitespace |
| Coverage/dependency/status agreement | PASS: 45 parents, 38 packages, 22 kinds, twelve gates, 28 AC, RF01-RF48, 20 RPT, 24 INV, 24 FY, 20 BAL, STK01-STK20 and 51 numbered candidates; acyclic prerequisites; only B01 READY |
| Todo/activation agreement | PASS: all 45 parents, nine sub-batches and five activations unchecked; optional bank integrations do not gate B41 |
| Independent Decimal storage fixture | PASS: actual 24 versus billed 20; two receipt origins total 36/value 420; partial transit 3/value 30; impairment/disposal/return ends at 27/value 330; net sale cost 70 and damage 20 reconcile; movement/value rebuild and exact residual allocation agree |
| Scoped documentation diff check | PASS: `git -c core.safecrlf=false diff --check -- CLAUDE.md docs` |
| Integration review | Parallel Catalog/configuration edits remain untouched; their operational enforcement and broader policy activation require the recorded D02/D03/D05/D07 gates |
| Implementation evidence | No stock/API/native DB/broker/concurrency/repair tests or migrations run; STK01-STK20 are future acceptance requirements, not implemented capability |

Purchase component and return review validation executed later on 2026-10-10:

| Check | Recorded result |
|---|---|
| Inline Python Markdown/link validation | PASS: 35 changed/untracked Markdown files, 555 local links/anchors, balanced fences and no trailing whitespace |
| Coverage/dependency/status agreement | PASS: 45 parents, 38 packages, 22 kinds, twelve gates, 28 AC, RF01-RF54, CAL01-CAL16 and 51 numbered candidates; existing RPT/INV/FY/BAL/STK checks retained; prerequisites ordered/acyclic; only B01 READY |
| Todo/activation agreement | PASS: all 45 parents, nine sub-batches and five activations remain unchecked |
| Independent Decimal component fixture | PASS: purchase total 1387.88; A credits 4 x 192.10 + 192.12 = 960.52; B remains 427.36; original component/tax residuals conserved; sequential versus common-base discounts checked |
| Scoped documentation diff check | PASS: `git -c core.safecrlf=false diff --check -- CLAUDE.md docs` |
| Review limits | Tally documentation confirms relevant entry capabilities, not this proposed schema or statutory validity of every recipe; actual tax/cost profiles retain existing decision gates |
| Implementation evidence | Documentation and arithmetic checks only; no application, native DB, concurrency or statutory integration tests run; CAL01-CAL16 are future requirements |

Sales commercial-configuration review validation executed later on 2026-10-10:

| Check | Recorded result |
|---|---|
| Inline Python Markdown/link validation | PASS: 38 changed/untracked Markdown files, 620 local links/anchors, balanced fences and no trailing whitespace |
| Coverage/dependency/status agreement | PASS: 45 parents, 38 packages, 22 kinds, twelve gates, 28 AC, RF01-RF60, CAL01-CAL28 and 51 numbered candidates; RPT/INV/FY/BAL/STK coverage retained; prerequisites ordered/acyclic; only B01 READY |
| Todo/activation agreement | PASS: all 45 parents, nine sub-batches and five activations unchecked; optional bank integrations do not gate B41 |
| Independent Decimal examples | PASS: paid quantities 9/10/19/20 yield 0/1/1/2 uncapped 10+1 rewards; configured sale totals 1032.50 with actual quantity 11 and cost 660; purchase total 1387.88 and five-return residual fixture retained |
| Scoped documentation diff check | PASS: `git -c core.safecrlf=false diff --check -- CLAUDE.md docs` |
| Research and design review | Official TallyHelp settings distinguished from proposed automatic scheme behavior; restrictive policy inheritance, manual/automatic sources, free-stock cost, gift tax purpose, return and partial-fulfillment duplication addressed in RF55-RF60 |
| Implementation evidence | Documentation/arithmetic checks only; no live Tally, voucher API, policy-race, scheme-redemption, native DB or statutory tests run; CAL17-CAL28 remain future implementation requirements |

All-voucher configuration review validation executed later on 2026-10-10:

| Check | Recorded result |
|---|---|
| Inline Python Markdown/link validation | PASS: 39 changed/untracked Markdown files, 640 local links/anchors, balanced fences and no trailing whitespace |
| Configuration/capture coverage | PASS: the configuration matrix exactly matches all 22 kinds; VCF01-VCF24 are sequential and reference existing batches; three shared policy candidates appear in the configuration contract and table manifest |
| Roadmap/dependency/status agreement | PASS: 45 parents, 38 packages, twelve gates, 28 AC, RF01-RF68, 28 CAL, 24 VCF and 51 baseline numbered candidates plus three shared configuration candidates; existing RPT/INV/FY/BAL/STK coverage retained; prerequisites ordered/acyclic; only B01 READY |
| Todo/activation agreement | PASS: 45 parents, nine sub-batches and five activations unchecked; optional bank integrations remain outside B41 prerequisites |
| Existing Decimal fixtures | PASS: sales 1032.50 with actual 11/cost 660, 10+1 threshold examples and purchase 1387.88/five-return residual checks remain consistent |
| Scoped documentation diff check | PASS: `git -c core.safecrlf=false diff --check -- CLAUDE.md docs` |
| Design review | Numbering/credit-date divergence from Tally, native role/account selection, typed configuration storage, count/movement and job-consumption rules, historical evidence and independent external actions are recorded in RF61-RF68; D06 covers each later profile before activation |
| Implementation evidence | Planning/source/arithmetic checks only; no live Tally, application/native DB, resolver/publication race, bank/job execution or integration tests run; VCF01-VCF24 remain future requirements |

The preceding validation table is an archived 2026-10-10 planning snapshot from before Phase 1.
Current implementation status is at the top of this tracker and in the live todo; B01-B14 are
verified only for their recorded scope. Remaining implementation prerequisites are recorded in
section 4. Later costing, stock, BOM or VAT choices block only their dependent work.

## Decision log

- 2026-11-03: Owner direction: a company created with inventory on is ready to bill goods.
  The books step creates the five standard stock accounts and maps them from books begin;
  chart initialization gives a chart with no cash account its Cash account in Cash-in-hand.
  Created under fixed system keys only, never adopted by name, skipped rather than failing
  setup when a code is taken ([purchase-product-review](purchase-product-review.md#company-setup-defaults-2026-11-03)).
- 2026-11-03: D02 answered for B24 ([purchase-product-review](purchase-product-review.md#owner-decisions-2026-11-03)):
  a Product/Mixed Purchase bill adds stock in one posting at landed cost (charges and non-claimable GST capitalised by
  value), Receipt Notes optional and clearable by reference, returns at the originating purchase cost with variance.
  B24 moves from PLANNED to IN_PROGRESS once its phase plan is agreed.
- 2026-11-03: Owner direction: a new company with its party and accounts must be able to
  create and post a voucher with no unnecessary blocker; approvers, owners and optional
  configuration apply only once configured. Done in this change: (1) company creation opens
  every period from books begin to the year end ([company-setup](company-setup.md) decision
  log); (2) defect fixed: Accounting's execution adapter compared the command's company
  configuration digest with the digest stored at financial setup, so enabling any feature
  after books setup refused every voucher post as `CONFIGURATION_CHANGED`. The live digest is
  still compared with the delegated context in `authority()` before any effect, matching the
  frozen-settings rule in [fiscal-year](fiscal-year.md) readiness; (3) credit assessment is
  skipped while `credit_limits` is off; (4) company voucher catalogue v4; (5) non-cash tender
  references and new-bill due dates are optional; (6) a type without a series issues from an
  automatic per-type series. No batch status changes. Not done, pending the
  owner's permission for the security-sensitive change: replacing the per-company env lists
  on the Vouchers↔Accounting execution, Accounting→Identity posting-reservation and Reports
  credentials with native company enrollment
  ([purchase-bill-readiness](purchase-bill-readiness.md#2026-11-03-no-unnecessary-blockers)).
- 2026-11-02: [Purchase with Product review](purchase-product-review.md). No status changes:
  B24 stays PLANNED and D02 OPEN. The goods/mixed Purchase refusal now holds with or without
  an invoice section, product bills are not printed or imported, and the Console says plainly
  that product bills are not available. The review records the B24 design options (bill
  against Receipt Notes clearing GRNI first; bill-as-receipt second) and eight owner decisions.
- 2026-11-01: The owner delegated the Purchase review's Vouchers decisions to the
  platform's own best fit ([purchase review](purchase-e2e-review.md) section 6). Taken
  for every kind: (D1) when the effective policy does not require approval `submit` moves
  DRAFT/REJECTED straight to APPROVED, with no approval row, the reason "approval not
  required by the voucher configuration" in the transition and the audit event, and an
  execution command that carries no approval ids; approve/reject then stay refused (409).
  (D1b) when approval is required and self-approval is not allowed, nobody who created the
  voucher or any revision (acceptance included) may approve it (403). (D2) `PURCHASE`
  submit refuses a recorded bill number (same supplier, fiscal year, normalised case and
  whitespace, live statuses) with `409 duplicate_supplier_bill` unless the submit
  acknowledges it, and `GET /vouchers/duplicate-bills` serves the same lookup. (D9) account
  evidence at its stored version may gain a missing `party_id` link; any other same-version
  difference stays a conflict. No configuration shape, migration or activation changed.
  Review correction the same day: a version 2 voucher type that omits `approval_required`
  or `self_approval_allowed` keeps the schema default (required; self-approval not allowed)
  instead of inheriting the permissive company envelope, so an omitted control never fails
  open now that submit can approve (`explicit_approval_controls` in
  `domain/configuration.py`, applied to the type's policy in `effective()`; classes and
  bindings still inherit sparsely from the type).

- 2026-10-30: Tenant-admin owner selected continuing movements reconciled against
  a recorded physical-count cutoff, and current verified native stock cost for
  surplus with mandatory review when no cost exists. These resolve the two count
  policy questions; they do not complete the broader D02/D03 owner contracts,
  B25 implementation or C3 activation. See the tenant-admin stock entry plan.

- 2026-10-11: Final Vouchers/configuration review repaired restrictive order
  inheritance, nonblank supplier-reference enforcement and kind/profile
  policy viability checks. Impossible required/forbidden evidence is refused
  before publication. B15-B45 and company activation status remain unchanged.

- 2026-10-11: The [QuickBooks-informed voucher review](voucher-quickbooks-coverage-plan.md)
  selected a small schema-v2 Sales terms/reference slice and identified durable
  source allocation, recurrence and reporting dimensions as separately gated
  extensions. The new setting does not change B15-B45 status or release gates.

- 2026-10-11: Phase 7 preflight review strengthened Razorpay merchant-account
  binding and CSV/cheque input boundaries. The selected B42-B44 optional scope,
  owner responsibilities and IN_PROGRESS statuses are unchanged; durable
  provider/import/book execution and native evidence remain release gates.

- 2026-10-11: Added [the remaining-kind configuration implementation plan](voucher-remaining-configuration-plan.md)
  for all 21 non-Sales kinds, including quotation, indent, challan, job-work and bank
  profiles. It assigns typed controls, validation/owner stages and slices to existing
  B05-B45 gates. This documentation-only refinement does not change verified statuses,
  selected optional scope or company activation readiness.
- 2026-10-11: Reviewed that plan against the v1 policy schema/resolver and recorded
  [VC2-01 through VC2-06](voucher-remaining-configuration-plan.md#81-configuration-work-packages-and-exit-evidence)
  as child work packages. Corrected bindable-family and date-basis assumptions, inheritance
  compatibility, legal challan numbering, Pro Forma coverage and bank-match boundaries.
  These packages extend verified baselines only within their future evidence; no parent batch
  status, activation or optional-bank selection changes.
- 2026-10-11: Implemented and twice reviewed the [scoped configuration v2 backend slice](voucher-configuration-v2-execution.md):
  sparse presence-aware policy inheritance, typed existing order/money capture restrictions,
  v2 posting-date money binding, v1 digest compatibility and generated client sync. Native
  verification passed. VC2-01 through VC2-06 are not complete; B15-B45 statuses and separate
  company activation gates remain unchanged.

- 2026-10-10: Financial-year review added RF25-RF32, D12 and FY01-FY24. Required normal
  year readiness, stable cross-year bill/stock/order/job histories, distinct statutory and
  posting identities, close evidence and controlled reopening/cache invalidation. All
  45 parents remain unverified; 38 packages, B14a-d/B27a-e and next activity B01 are unchanged.


- 2026-10-10: Stock reporting review added RF17-RF24, B27a-e and INV01-INV24 under existing
  gates/AC IDs. Named inventory output and underlying origin/date/hold/group/unit contracts
  are required before activation. All 45 parents remain unverified; B01 stays next.

- 2026-10-10: Recorded RF09-RF16 from the deeper financial-reporting review, D11, B14a-B14d
  and RPT01-RPT20 under AC26. Extended B09/B18/B27/B40/B45 and activation evidence; retained
  45 parent batches, 38 packages and zero verified implementations. Reporting contracts are
  now explicit; outstanding schema/business decisions still need their phase evidence.

- 2026-10-10: User requested saving the proposed batch breakdown and maintaining a todo.
  Added the linked note and live checklist, with 41 baseline batches, conditional B31 and
  optional B42-B44. Kept all implementation and activation tasks uncompleted and preserved
  this tracker as the status/evidence authority; no policy selection or implementation began.
- 2026-10-10: User requested review and recording for implementation in batches/phases.
  Recorded eight planning findings and corrections, preserved the 38 work packages, introduced
  45 dependency-ordered batches and five activation checkpoints, mapped all 22 kinds/required
  profiles, and added decision/evidence handoff records. No batch implementation, deployment,
  commit or publishing is claimed by this review.

### Account-recording review - 2026-10-10

Recorded RF33-RF40 and BAL01-BAL20 under existing D11/AC26. Strengthened B02/B03,
B07/B09/B10/B11/B14 and later reporting/recovery scope. No batch was implemented or verified;
45 parents, 38 packages, twelve gates and next activity B01 remain unchanged.

### Stock capture/storage review - 2026-10-10

Recorded RF41-RF48 and STK01-STK20 for stock capture/storage and recovery. Extended
existing stock/value/source/import batches without changing dependencies or completion status.
Separate configuration work must reconcile its activation contracts; its files are untouched.

### Purchase component review - 2026-10-10

Recorded RF49-RF54 and [CAL01-CAL16](voucher-invoice-calculation.md#81-required-component-acceptance-matrix).
Existing calculation/tax/invoice/return/reporting batches now include stacked quantity, line
and invoice components, original-allocation claims and supplier-credit/tax/cost reconciliation.
All 45 parent statuses and activation prerequisites are unchanged.

### Sales commercial-configuration review - 2026-10-10

Recorded RF55-RF60 and CAL17-CAL28 from the [commercial configuration contract](voucher-commercial-configuration.md).
Bound independent Sales/Purchase policies, manual/automatic deals, tax/cost distinction and
source-linked rewards to existing batches. Automatic schemes require Catalog publication/
projection and atomic Accounting execution; all 45 statuses and activation records remain unchanged.

### All-voucher configuration review - 2026-10-10

Recorded RF61-RF68 and VCF01-VCF24 from the [all-voucher configuration contract](voucher-configuration-design.md).
All 22 kinds have specified settings/capture/effect requirements in the design matrix;
runtime and shared configuration evidence remain limited to the verified batch scope.
Added three policy storage candidates outside the 51 numbered baseline; existing 45 statuses,
38 packages and separate activation checkpoints remain unchanged.

## Phase 1 execution - 2026-10-10

B01-B08 **VERIFIED** for the common C0 foundation. The user authorized implementation
of Phase 1. [The execution record](voucher-phase1-execution.md) contains per-batch scope,
actual paths, exact migration heads, verification counts/commands, compatibility limits,
security/correctness fixes and the operational handoff. The
[contracts note](voucher-phase1-contracts.md) records resolved initial decision slices and
required later owner contracts. These two records together supply the batch evidence template.

Accounting's signed command/status/result adapter, durable source guard, transactional
callback boundary, committed-generation receipts, cancel/recovery/close/expiry races and
Vouchers durable delivery are verified. Every actual financial/stock profile remains
disabled; their native effects and full end-to-end acceptance belong to subsequent batches.
The final Vouchers native DB/broker run passed 87 tests; Accounting native slice passed 18.
The ordinary Vouchers suite passed 85 with 2 native-only skips and 99.07% domain coverage.
Generated clients, strict typing, targeted console checks and Windows script parsing passed.

C0-C4 release activation remains pending. Live gateway deployment/mobile delivery, real
financial executors, statutory providers, report projections and stock profiles are not
claimed complete. B09 is the next ready batch; B10 is dependency-eligible after B08 and
follows B09 in the saved delivery order. Existing/concurrent Catalog work was preserved.
No real-company database migration, commit, publication or deployment was performed.

## B09 execution - 2026-10-10

B09 VERIFIED for committed Accounting exports and Reports generations/projections/runs.
[The B09 record](voucher-b09-execution.md) documents the 15-grain contract, 4 Accounting and
16 Reports migrations, 35 native/broker tests, 32-test Accounting native baseline, 1,034-test
platform run, typing/client checks, supported limits and manual review. Current-workspace
Accounting verification additionally found one failing test in separate parallel sequence
work (9 other tests passed); that feature is preserved, unverified and outside B09.

Only SOURCE_RECONCILIATION is available. COMPLETE does not mean a financial statement;
B14 owns ledger/TB/P&L/Balance Sheet and settlement calculations. Initial source coverage is
retained ledger from books-begin, never fabricated YTD. B09 resolves the export/barrier,
permission, source/projection and frozen-run slices of D11; statement netting/earnings and
later producer extensions stay open. Native stock, tax and voucher posting remain disabled.
Nine of 45 parent batches are verified; B10 is next. Activation, publication and deployment
remain separate. The preceding Phase 1 entry is historical and retains its original scope.

## Phase 2 execution - 2026-10-10

B10-B14, including B14a-d, VERIFIED for the ordinary-money selections in
[the execution record](voucher-phase2-execution.md). Journal/Contra, Payment/Receipt,
advances/refunds, atomic bill settlement, manual bank history, fiscal readiness and 16
financial reports use the existing Accounting authority and common voucher detail tables.
The unfinished independent sequence allocator was removed; authoritative posting allocates
the number atomically. No per-kind document tables or separate payment ledger were added.

Vouchers passed 126 native/broker tests, Reports 64 and the console 328. Accounting's
original full native run passed 510 with four fixture/assertion failures and six broker-only
skips. All four failures were corrected and passed in current native reruns; the current
21-test broker/acceptance, 33-test regression and 2-test bank/snapshot groups passed.
Combined Accounting coverage is 95.14% overall and 99.60% domain. The execution record
retains original results, exact coverage limitations, migration and static-check evidence.

Fourteen of 45 parent batches are verified; Phase 3 B15 is next. D gates retain later
tax/stock/order/job-work extensions and C0-C4 release activations remain separate. Both
money-execution flags default false. No real-company migration, commit, publication or
deployment was performed. Earlier checkpoints above are historical, not current status.

## Phase 3 working checkpoint - 2026-10-11

B15-B18 remain IN_PROGRESS and B19 PLANNED; no Phase 3 acceptance or C2 activation is
claimed. Catalog now has dormant, same-company promotion storage and one-DDL migrations
0161-0165, plus a bounded same-item preflight. Accounting's isolated paid-quantity
evaluator covers the 9/10/19/20 paid-unit cases. Catalog's targeted migration/promotion
suite passed 35 tests with the live Docker test skipped. Three storage tests pass for
all five tables' tenant isolation, a cross-tenant SKU FK refusal and published-row ORM
immutability. Accounting's focused
calculator/preview/deal regression group passed 73 tests.
An attempted whole-Catalog suite was stopped at 6%; it is not counted as verification.
Protected Catalog publication, complete release acknowledgement,
Accounting projection, tax/free-supply authority, statutory issuance and full native
acceptance remain open. [The Phase 3 record](voucher-phase3-execution.md) carries the
detailed evidence and unchanged gates. Phase 4 has not started.

The subsequent B15 storage guard review closed a post-publication append path for
promotion benefit and target rows at the ORM boundary. A failing regression preceded
the fix; four focused storage tests, targeted Ruff and mypy pass. Direct SQL remains
covered by scoped FKs but not an immutability trigger. B15-B19 status, D02 and the
Phase 4 prerequisite order are unchanged.

The next B15 slice adds Catalog stack-policy/group/permission tables and native
promotion-to-stack FKs through revision 0170. Focused promotion/migration tests pass
42 with one Docker-only skip; a disposable loopback MySQL run verifies the scoped
tables/FKs, four native isolation/immutability cases and downgrade/re-upgrade.
Whole-Catalog metadata still has unrelated in-progress drift. Catalog publication,
complete release acknowledgement and Accounting projection remain open; B15 stays
IN_PROGRESS and later batch statuses are unchanged.
The scoped stored-fact reader now reconstructs a bounded same-item deal and rejects
missing benefit/target facts or an inconsistent stack before release work. It grants
no execution authority; publication hashes, dependencies and Accounting acknowledgement
are still required.

## Phase 5 preparatory checkpoint - 2026-10-11

The user authorized implementation after the detailed Phase 5 plan. B28 is now
IN_PROGRESS for a non-posting capture slice only: migrations 0052/0053, shared
planned item quantity and fulfillment terms, quotation/requisition/order validation,
revision-bound storage/read and a generated API contract. A dedicated API test
proves quotation submission creates no owner posting and post is refused. The
generic two-tenant schema fixture includes the new table. B28 cannot be VERIFIED
before B15, its remaining lifecycle/estimate/client scope and full acceptance.
B29-B36, C3 and B31 selection remain pending; Phase 4 has not been verified.
The full Vouchers suite passed 143 tests with two broker-only skips; the focused
B28/domain/isolation group passed 49. Full Vouchers source mypy, Ruff, OpenAPI
and generated-client checks and eight API-client tests pass. The new table's
constraint names were checked against SQLAlchemy metadata. No live MySQL
roundtrip or C3 evidence is claimed.
Identity's native voucher field registry was extended for the two new fields;
its focused source/field test group passed two tests with Ruff and mypy clean.
The follow-on B28 capture slice now permits protected quotation-term artifacts,
declares terms in the response schema, and has profile-gated issue acceptance,
decline and elapsed-validity expiry with dedicated permission keys. Submitted
Sales Orders/quotations require CUSTOMER and Purchase Orders require SUPPLIER.
The focused domain/order group passed 25 after this change; full B28 conversion,
estimates and acceptance gates remain open. The user authorized commit and
`git publish` after complete Phase 5 review, not at this partial checkpoint.
The user selected both FIFO and moving average for the initial D02 valuation
release. D02 remains OPEN until the detailed recognition, allocation and
native-database acceptance contracts are implemented. The console now captures
planned order units and typed fulfillment terms and exposes permitted issued
order decisions; a real field-set exposes both native fields. Focused UI tests,
console typecheck and the final Vouchers regression run (146 passed, two broker
skips) pass.

## B15 manual-discount control checkpoint - 2026-10-11

The shared invoice policy now has restrictive discount input/basis choices,
component-count and compounding controls, and final allocated amount/percentage
limits. Vouchers rejects unsupported recipes at capture, and Accounting repeats
that validation and caps actual allocated commercial deductions per line and
invoice. The versioned policy and generated voucher contract carry the settings;
legacy default serialization remains stable. This is a partial B15 control slice.
Catalog price/discount ceilings are not yet projected into the Accounting quote,
and Catalog publication, automatic scheme execution, free-goods tax/stock posting,
source-linked adjusted returns and UI invoice entry remain open. B15 stays
IN_PROGRESS; no activation checkpoint changes.
Verification: Vouchers 219 passed/2 skipped; focused Accounting invoice and
discount suites 55 passed; Ruff, strict source typing, generated voucher client
and TypeScript checks passed. The full Accounting run had 684 passed/15 skipped
and two pre-existing contract/test mismatches outside invoice code: stale
Identity Accounting field export and a native verifier test expecting three
migration calls when the verifier makes four. Neither is counted as B15 evidence.

Two subsequent review passes closed draft-transition gaps. First, unsupported
free/scheme-purpose invoice lines are now refused beyond draft, matching Accounting's
preview boundary. Second, ordinary invoices require a calculation hash before
submission. Domain and API regression tests cover the transitions; the final full
Vouchers suite passed 221 tests with two skips, and the affected Accounting tests
passed 10. Vouchers Ruff and strict mypy passed.
Accounting remains the posting authority and recomputes the hash. Caller-supplied hash
provenance at the approval stage remains an open execution gate, as do Catalog ceilings
and scheme publication/projection. These reviews do not advance B15 or activation.

## Item transaction eligibility checkpoint - 2026-10-12

Catalog now publishes a separate signed `item_transaction_policy` source with item kind,
stock mode, sale/purchase flags and a composite item/family version. Vouchers validates
that source at item-bearing lifecycle transitions and before posting: disabled sale or
purchase directions, stale item versions, mismatched invoice supply kinds and physical
use of service/non-stock goods fail closed. Non-stock goods report stock execution as
not applicable in Catalog effective facts. Catalog source and Vouchers order/adjacent
invoice/money/source tests passed. This does not close B15-B27: Accounting has no stock
position, cost-layer or goods invoice execution path, and their release gates remain open.
