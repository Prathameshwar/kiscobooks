# Catalog integration with transfers, damage, adjustments and product ledger

**Status:** Design contract; ownership revised 2026-10-10; no stock implementation claimed.
**Scope:** Catalog definitions and integration contracts only. The [Vouchers plan](vouchers-plan.md)
replaces future Billing/Payments services. Vouchers owns stock transaction/count/transfer
documents and workflows; Accounting owns parties and financial effects, with authoritative
stock/custody/value posting proposed in the same transaction. Their source APIs, migrations
and workers belong to V0-V9, not Catalog implementation.
**Read with:** [Catalog tables](catalog-table-inventory.md),
[warehouse definitions](catalog-warehouses.md) and [product rules](catalog-product-design.md).
**Price/cost boundary:** [Purchase/unit/batch price and declaration contract](catalog-pricing-design.md).

**Reading the retained scenarios:** Older references to "Billing" below are historical
requirements, not a planned service. Document/approval/fulfillment actions map to Vouchers;
stock/credit locks, physical-unit claims, movements, balances, costs, journals and period
guards map to the proposed Accounting posting extension. Party sources map to Accounting.
Use this mapping and the Vouchers plan wherever older ownership language differs. Catalog
release acknowledgement must come from the owner actually enforcing the posting rules.
The [stock recording/reporting design](voucher-stock-recording-reporting-design.md) now
specifies canonical positions, current availability, item/group/location/expiry/age/value
registers, native source histories, B27a-e and INV01-INV24. Read it with these movement/count
contracts; it refines the Accounting/Vouchers boundary rather than introducing another owner.

The [stock capture/storage contract](voucher-stock-recording-reporting-design.md#31-what-an-execution-captures)
now specifies execution evidence, native quantity/value/position grains, synchronous owner
balances, transfer/return claims, guarded repair and staged imports. STK01-STK20 extend the
existing INV/FY/BAL checks and stock batches; Catalog definitions are not stock execution.

## 1. TallyPrime baseline and intended improvements

Official documentation reviewed on 2026-09-11. This is a review of published behavior, not
inspection of TallyPrime source code or an assertion about every edition, extension or feature.

| Area | Documented baseline | Contract required for this platform |
|---|---|---|
| Transfers | Source/destination Stock Journal entries; transfer expenses and quantity differences can be recorded. | Separate immediate and dispatch/receive lifecycles, explicit transit custody, partial receipts and reasoned discrepancy settlement. |
| Physical stock | Actual count produces an inward/outward correction; the register shows adjustments. | Frozen count scope, blind counts, recount evidence, reviewed variance and safe concurrent-posting rules. |
| Product reports | Stock Summary, monthly movement and voucher drill-down; godown summaries. | One immutable movement source, reproducible opening/running/closing balances, lot/serial trace and financial reconciliation. |

Sources: [TallyPrime inventory vouchers](https://help.tallysolutions.com/tally-prime/inventory/inventory-entry-tally/),
[physical stock register](https://help.tallysolutions.com/tally-prime/inventory-reports/physical-stock-register-tally/),
[stock summary](https://help.tallysolutions.com/track-your-inventory-stock-summary-tally/) and
[godown summary](https://help.tallysolutions.com/tally/godown-summary-tally/).

TallyPrime also documents location hierarchies and grouping locations that do not store goods.
Catalog therefore supports non-stockholding warehouse groups separately from physical stores,
godowns and bins. [TallyPrime godowns](https://help.tallysolutions.com/inventory-storage-using-godowns-locations-tally/).

The improvement target is explicit correctness, traceability and API behavior in these workflows.
Acceptance tests must demonstrate those properties before any production superiority claim.

## 2. Ownership and activation

| Owner | Owns | Must not own |
|---|---|---|
| Catalog | Products, units, tracking profiles, warehouse/group/bin definitions, location operation policies, product restrictions, replenishment policies and complete published releases. | Party/customer source records, stock balances, physical batches/devices, transfer/count/damage documents or financial journals. |
| Vouchers | Stock/count/transfer/damage documents, approvals, fulfillment and posting-command workflows. | An independently authoritative stock balance, valuation or financial ledger. |
| Accounting | Existing parties/financial posting; proposed stock/custody locks, movements, valuation and operational product ledger in its local posting transaction. | Editable Catalog definitions or an assumption that a Vouchers database commit is part of its transaction. |
| Reports | Required registers/exports for enabled profiles, delivered in the V9 incremental batches; separately selected analytical extensions. | Operational stock writes or the authoritative ledger. |
| libs/platform | Exact arithmetic, security, transactional events, idempotency and reusable query/job mechanisms. | Stock policy, physical custody or accounting domain ownership. |

Catalog consumes minimal authoritative party/type projections for pricing mappings and supplier
references. No party/customer CRUD is added to Catalog. If the source does not exist or is stale,
the dependent mapping/activation is explicitly unavailable; no invented customer or local master.

Catalog publication is not remote enforcement. `catalog_policy_consumer_ack` records each trusted
consumer's accepted/rejected release and enforced version. A warehouse stop is shown as pending
until Accounting acknowledges activation under its posting guards. Emergency stock holds
are authoritative Accounting commands exposed by the Vouchers workflow, not an eventual
Catalog metadata update. Product Configuration cannot
enable an operational feature whose consumer contract is unavailable.

## 3. Store-to-store and bin transfers

**Scope:** Same-company, same-owner, same-SKU movement. Different SKU conversion is manufacturing,
not a transfer. Different company or a tax context requiring a different document uses its
separately supported Billing workflow. Same-company identity alone does not establish tax
neutrality: the transaction adapter must validate source/destination registration and location
facts. Missing statutory/document support blocks posting; this document supplies no tax rule.

Each transfer has explicit source/destination allocation, requested quantity, selected pack
revision, actual base quantity and batch/unit evidence. No hidden shortage fulfillment from
another store. Warehouse groups cannot be selected as stock locations. Bin-to-bin relocation
within one warehouse is allowed when bins are enabled and the bins differ; it does not require
multiple godowns. Identical source/destination allocation is invalid.

Two execution modes:

- **Immediate:** A bounded, physically completed relocation posts matched outward/inward legs
  atomically. Company quantity and original carrying cost are conserved.
- **Dispatch/receive:** Draft -> approved if required -> reserved -> partially/fully dispatched
  -> partially/fully received -> reconciled/closed. Dispatch places custody in a protected,
  non-saleable internal-transit scope. Receipt identifies the dispatch allocation it consumes.
  Several dispatches and receipts are allowed; closing requires no unexplained remainder.

The source operator needs source dispatch authority; the receiving operator needs destination
receipt authority and access to the specific transfer. Neither needs unrestricted access to
the other store's balances. The transfer creator/approver must be authorized for both ends.
Counterpart identity may be disclosed through the transfer without disclosing its stock/cost.
Both endpoints' operation policies and permitted transfer lane are checked by Billing.

Per dispatch allocation, cumulative dispatched quantity equals accepted receipts + returned-to-
source quantity + approved loss/write-off + remaining transit. Rejected-but-held goods remain
in transit or explicit destination quarantine until a real movement resolves them. A damaged
receipt counts as received once, in damaged/quarantine disposition. Damage observation alone
does not also subtract its quantity as a loss. Over-receipt, wrong SKU/lot/serial and duplicate
scans are discrepancies, never permission to manufacture stock or consume a different shipment.

Discrepancies preserve expected/observed identity, quantity, evidence, reason and responsible
review. Resolution links real receipt/return/reclassification/adjustment effects and is bounded
by their source allocations. Thresholds determine approval, not silent tolerance write-offs.
Transfers can be rerouted only through a versioned authorized action with destination checks.
Cancellation releases undisbursed reservations; already dispatched goods require receipt,
return or approved loss resolution. Posted legs are reversed with links, never deleted.

Reservations, physical-unit claims and cost allocations use Billing's common posting locks.
Each source action and movement leg has a unique effect identity in addition to API idempotency.
Retries with a new request key cannot dispatch or receive the same source effect twice.

**Transfer costs:** Original stock cost carries unchanged through movement. Approved freight or
handling is a separate, evidenced charge with EXPENSE or supported CAPITALIZE treatment. One
source charge cannot be expensed and capitalized twice. Allocation uses a declared compatible
quantity, weight, value or reviewed manual basis; exact residual allocation conserves the charge.
Mixed incomparable units cannot use a raw quantity basis. Missing physical measurements block
weight allocation. Late charges require traced remaining-stock/consumed-cost adjustments under
Billing's valuation and period rules; unsupported recalculation is rejected. No arbitrary edit
of destination rate, no internal revenue, no assumed recovery from a carrier.

## 4. Damaged stock and loss recording

Treat condition, custody, quantity and carrying value separately:

| Action | Quantity effect | Value effect | Availability |
|---|---|---|---|
| Record suspected damage and quarantine | Matched reclassification; company on-hand unchanged | Original carrying value retained pending assessment | Immediately excluded from sale/reservation |
| Confirm damaged/repairable condition | Remains physically held in a supported disposition | Separate approved impairment if appropriate | Unavailable unless an explicit permitted release succeeds |
| Write down damaged goods | Zero quantity movement | Approved negative value adjustment; never negative carrying value | Remains unavailable |
| Destroy/write off physically removed goods | Outward quantity from actual damaged stock | Remove only remaining carrying value | No remaining available quantity |
| Release inspected goods | Matched reclassification of the same units | No automatic restoration of an earlier write-down | Sale eligibility rechecked, including expiry |
| Return damaged goods to supplier | Physical supplier-return movement | Billing return/accounting contract | Not an ordinary sale or generic adjustment |

A damage case records discovery time/place, source receipt/transfer/sale where known, exact
lot/serial quantities, assessor, evidence and supported disposition decisions. Partial-lot
damage moves only affected quantities; do not mutate the entire lot's quality to implement it.
A true lot-wide hold is a separate Billing control. Expiry is also evaluated at operation time;
a missing nightly expiry job cannot make expired goods saleable.

Quarantine is allowed promptly with the dedicated authority even while write-off approval is
pending. When affected units are reserved, the hold/reclassification atomically invalidates or
releases the affected stock reservation and records affected demand. It must not leave reserved
quantity greater than eligible stock, silently substitute other units, or consume coupon holds.
The affected order/quote is marked for reallocation/revalidation through its owner.

Damage-case status never independently changes stock. Every reclassification, impairment,
release, disposal or return links a posted Billing document. Approval binds to the exact action,
quantities, current versions and valuation evidence. An action cannot be executed twice or reuse
approval after material edits. No self-approval when separation of duties is required.

Example: 100 units cost 10 each. Quarantine 5: physical total 100, saleable 95, value 1,000.
Write their value down by 30: total value 970, quantity still 100. Later dispose of those 5:
remove remaining value 20; physical total 95, value 950. Total damage expense is 50, not 80.
Damaged customer returns preserve original physical identity/cost links; financial credit and
acceptance into damaged custody are distinct actions. Repair manufacturing, insurance settlement
and scrap conversion into a different SKU remain separately owned workflows.

## 5. Adjustments and physical counts

Billing exposes typed actions: quantity gain/loss, physical-count variance, disposition change
and value-only adjustment. Each has a native reason, allowed stock direction, account mapping,
evidence requirements and approval policy. Stock quantity and cost are never PATCHed on a product
or balance. Every action checks live warehouse controls, postability and physical identifiers.
Gains require supported cost evidence; they cannot use the Catalog sale price as cost. Negative
adjustments consume original cost. Value-only actions keep quantity unchanged and preserve a
link to the affected valuation scope/layers. Services and nonstock goods reject stock actions.

**Count lifecycle:** draft scope -> start/baseline -> count -> submit -> recount if required ->
review variance -> approve -> post bounded adjustment documents -> reconcile/close. Cancellation
before posting releases the freeze. Partial large-job posting remains explicit until every
variance is reconciled; there is no fictitious whole-warehouse atomic transaction.

- Freeze an explicit manifest of warehouse/bin/SKU/lot/disposition coverage, including how newly
  discovered items are handled. Omitted lines mean uncounted, not zero; zero must be confirmed.
- Blind counts hide book quantity and value from the counting actor, including API/export/error
  paths. Recounts are separate observations, not overwritten numbers or added to the first count.
- Record counter, time, unit/conversion, count round and exact serialized-unit observations.
  Reject duplicate identifiers; unexpected known units trigger custody reconciliation. Unknown
  units require reviewed onboarding evidence, not creation through an arbitrary count scan.
- Count compares physical on-hand, including reserved and damaged quantities where scoped.
  It does not compare counted goods with saleable or available-to-promise quantities. Transit
  requires an explicit custody-confirmation scope and is not counted again at either store.
- Difference = accepted physical count - book stock at the agreed cutoff. Wrong location/lot
  may require a matched relocation/reclassification, not unrelated gain and loss postings.
- Thresholds use native quantity/value rules and require recount/approval as configured. Count
  submission never silently authorizes write-off. Approval is invalidated by changed scope,
  count, allocation, cost or other material source versions.

Two supported operating contracts, enabled only when Billing implements their guarantees:

1. **FREEZE_SCOPE (default):** On start, Billing locks stable warehouse/count guards, activates
   the scope freeze and captures the book baseline. All quantity/condition/value writers honor
   the freeze, including new empty buckets, transfers and late imports. Safety holds may still
   block sale without changing the counted quantity; conflicting physical reclassification
   invalidates/restarts the affected count. No auto-unfreeze on worker crash or timeout.
2. **RECONCILED_CUTOFF:** Requires a common physical cutoff and evidence for every movement
   crossing the counting window. Counts and movement effects are reconciled to that cutoff;
   an unprovable physical timestamp or offline ordering rejects this mode. Capture a versioned
   movement barrier, carry subsequent confirmed movements forward, and lock/revalidate before
   posting the accepted variance. New late evidence invalidates the approval. After posting,
   later-arriving pre-cutoff events require a controlled linked correction, never silent
   backdated stock insertion. A snapshot alone is insufficient to make a live count correct.

Example: cutoff book stock 100; accepted physical count 97; after-cutoff confirmed sale 10.
Current book becomes 90. Post the approved -3 variance: current stock 87, not 97. If the sale's
physical relation to cutoff cannot be proved, require freeze/recount instead of guessing.

All inventory mutations use one consistent Billing lock order and the count/warehouse guards
before stock/cost/unit writes. Overlapping count starts serialize, including scopes that would
otherwise admit phantom buckets. Stock-count bulk uploads use frozen scope/version and ordinary
domain validation; Catalog bulk jobs cannot import stock quantities, counts or adjustments.

## 6. Product stock ledger API contract

The planned authoritative product ledger reads Accounting's append-only `stock_movement`, linked
to document allocations, cost provenance and unit movement history. There is no competing
Catalog `product_ledger` table or mutable running-balance source. Opening rows are derived from
prior movement evidence; annual rollover does not repost opening stock.

The Accounting contract provides bounded item/location ledger, document drill-down, batch/serial
trace, transfer register, count-variance register and damage/disposal register. Each ledger
result contains business date and recorded time, source document/action, reason, inward/outward
quantity and carrying value, running balances, location/disposition and authorized references.
Sale price/revenue is separate from inventory carrying value; cost-denied actors cannot recover
it through totals, implied rates, discrepancy exports or linked evidence.

Required semantics:

- Opening + net movements = closing for quantity and value under the same scope and cutoff.
- Paired transfer/reclassification legs remain visible but net to zero for company quantity;
  internal movement is not purchase/sale turnover. Transit counts once. Value-only rows show
  zero quantity. Group totals never add incompatible units or currencies.
- Date-range view and recording-order audit view are explicit. Stable ordering includes a
  commit-safe per-item sequence and effect/leg tie-breaker, not timestamps/UUIDs alone.
- Accounting serializes sequence allocation with the stock posting transaction so an issued
  barrier cannot later acquire an earlier uncommitted movement. A ledger cursor binds actor
  scope, filters, order and sequence barrier; refresh intentionally includes later corrections.
- Reviewed backdating may change a newly requested historical statement, but not an existing
  pinned statement. Responses identify the as-of barrier and whether derived snapshots are ready.
- Filtered movement lists do not mislabel the sum of selected operation kinds as the true stock
  closing balance. Actual opening/closing uses all movements in the stated stock scope; a
  filtered subtotal is separately named. Historical availability additionally requires hold/
  reservation history; do not derive it from today's reserved balance.
- Rebuildable daily/monthly snapshots are accelerators, never a second source. Build a separate
  generation from a consistent barrier, catch up and reconcile before switching readers.
  Failed rebuilds keep the previous valid generation; audit evidence is never rewritten.
- Physical movements, balances, cost layers, financial journals and transfer/count/damage
  source links must reconcile. Operational Billing reads have authoritative freshness;
  Reports projections disclose their checkpoint and may not be used for posting decisions.

### 6.1 Current balances, expiry and grouping

Current stock is a guarded projection over canonical SKU/owner/custody/location/lot/disposition
positions. Report physical on-hand, company-owned, eligible, reserved, available, transit and
external custody separately. Availability re-evaluates expiry/holds/location policy for the
requested operation and date; event catch-up alone cannot refresh a midnight expiry boundary.
Historical availability requires dated lot corrections, holds and selected reservation facts.

Use dated family/group/category and warehouse-group assignments for rollups, with a pinned
classification basis across opening/movement/closing. Deduplicate leaves and overlapping
categories; incompatible units have separate subtotals. Physical receipt origins remain
available independently from FIFO/moving-average value layers so remaining-stock age is
reproducible. Expiry does not itself post a loss or dispose of goods.

The stock design's catalogue/INV checks and B27a-e are required. B31 remains conditional;
only selected reservations add their history/availability deductions. Transfer dispatch can
post against locked current eligibility without a long-lived reservation when that capability
is disabled. Projected demand/supply needs later B32 facts, never guessed zero inputs.

## 7. Catalog deliverables and external acceptance scenarios

Catalog implements only warehouse groups/definitions, profiles/restrictions, source releases,
consumer acknowledgement and scoped history/readiness. Source references and rule contracts
are versioned. The route names below are Vouchers workflow/owner-read interface proposals,
not implemented Catalog endpoints; V0 must settle their exact location and contracts:

| External API family | Expected behavior |
|---|---|
| `/inventory-transfers` | Validate/approve/reserve/dispatch/receive/reroute/resolve-discrepancy/reverse. |
| `/inventory-damage-cases` | Record/quarantine/assess/approve disposition and link actual posted effects. |
| `/inventory-adjustments` | Reviewed typed quantity, condition and value corrections. |
| `/stock-counts` | Scope/start/count/recount/variance/approve/post/reconcile, including protected imports. |
| `/items/{id}/stock-ledger` | Scoped pinned opening/movements/closing with drill-down and exports. |

Contract scenarios to exercise with Vouchers and the Accounting stock extension when implemented:

- Dispatch 10; receive 7 good and 2 damaged; 1 remains transit until separately resolved.
- A retry, wrong serial or over-receipt never produces a second or invented unit.
- Same-store bin relocation conserves identity/value without enabling multiple godowns.
- Damage discovered on reserved stock cannot be sold while approval is pending.
- Partial-lot damage does not block unrelated good units; disposal after impairment avoids double loss.
- Count 97 versus book 100 plus later sale 10 ends at 87; omitted count is not zero.
- A late pre-cutoff receipt, freeze/dispatch race and overlapping counts cannot bypass reconciliation.
- Transfer cost allocation, write-off and period-close races reconcile inventory and journals.
- Ledger pagination remains pinned through later corrections and does not leak other stores/cost.

Catalog tests its own contract serialization, scope, validation, acknowledgement handling and
missing-consumer behavior now. Stubbed consumers are not evidence that stock operations work.
Accounting concurrency/tax/valuation and Vouchers workflow/recovery tests remain obligations
in the new plan. A workflow-only mock cannot prove atomic stock/financial effects.

## Manufacturing execution handoff for V8

[Catalog M0-M4](catalog-manufacturing-design.md) publishes immutable BOM/route/unit/profile
dependencies, expected quantities/yield/output specifications, location defaults and estimates.
Catalog owns no production order, physical material issue, production receipt, WIP or genealogy table.

The required V8 job-work and supported manufacturing scope must separately define and verify
the applicable items below. The minimum Catalog definitions are a V8 dependency; advanced
M0-M4 options remain separately selected rather than all 20 optional tables becoming mandatory:

- Pin exact BOM/route/configuration revisions, run sizes, selected alternatives and substitutions
  at order authorization. Replacing a Catalog default never revises an existing order silently.
- Material reservation/picking, partial issues and unused-material returns; actual input/output
  lot/serial allocation; tracked WIP custody; independent production issue/receipt location flags.
- Actual consumption, yield, co-products and scrap; explicit discrepancies from expected quantities.
  Manufacturing transformation is not a same-SKU transfer or a shortcut through adjustment APIs.
- Genealogy from consumed lots/serials to produced lots/serials, expiry/quality release evidence
  and recall tracing. Do not equate a recipe's expected composition with actual physical genealogy.
- Actual material/labour/overhead/subcontract cost, output allocation, WIP settlement, variances,
  residuals and late corrections under its accounting rules. Catalog estimates cannot post value.
- Idempotent stock/value effects, independent approvals, partial completion/cancellation and
  linked reversals. Avoid reversing consumed outputs blindly when downstream stock has moved.
- Product-ledger movement types and drill-down to production evidence; reconcile stock, WIP and
  financial value. Physical mass balance is meaningful only with compatible measured dimensions.

Definition publication may be supported before any execution is implemented. Unknown support or
missing dependency acknowledgements blocks operational activation, not truthful definition reads.
These requirements need the Vouchers/Accounting design and tests; Catalog contract mocks
do not complete them. Payroll/attendance and related HR work remain excluded.

## Decision log

- 2026-10-10: Stock report review added the canonical balance, eligibility/expiry, quantity
  origin and group/unit contract plus B27a-e/INV checks. Clarified Accounting product-ledger
  authority and conditional reservation use; Catalog remains the definition owner.

- 2026-10-10: Batch-readiness review corrected stale optional execution/reporting wording.
  Required V8 job-work/manufacturing coverage and minimum definitions follow the Vouchers
  scope; advanced Catalog depth remains selected. Registers/exports arrive with each enabled
  transaction profile rather than after job work. No Catalog stock authority is introduced.
- 2026-10-10: Superseded the old Billing owner with Vouchers document workflows and the
  proposed Accounting stock/value posting extension. Preserved physical/financial atomicity,
  count/transfer safeguards and Catalog-only implementation scope. Retained older detailed
  scenarios with an explicit owner mapping; no legacy wire identity is renamed.

- 2026-09-11: Added the optional BOM execution handoff for future Billing manufacturing work;
  preserved the Catalog-only migration/API scope and distinct actual-cost/ledger authority.

- 2026-09-11: Reviewed official TallyPrime workflows and specified explicit transfer discrepancies,
  damage custody/value separation, controlled counts/adjustments and a reproducible product ledger.
- 2026-09-11: User corrected implementation scope: all party and operational inventory/financial
  source work remains Billing-owned. Catalog publishes masters/configuration and consumes only
  required projections/acknowledgements; this contract does not authorize Billing implementation.

### Stock capture/storage review - 2026-10-10

Strengthened the required Accounting execution handoff: native capture/storage grains,
immutable value history, scope locks, bounded shipment/return claims, staged imports and
protected repair. Catalog still owns definitions; configuration publication is not execution.
