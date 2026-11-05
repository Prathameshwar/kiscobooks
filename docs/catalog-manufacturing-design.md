# Optional BOM and manufacturing definitions

**Ownership amendment, 2026-10-10:** [Vouchers](vouchers-plan.md) replaces future Billing
and Payments APIs. Catalog still owns BOM/route definitions. Later Vouchers manufacturing
workflows use a Stock Journal mode; Accounting's proposed stock/value extension owns actual
consumption/output, custody, WIP valuation and financial effects. Retained Billing references
below map accordingly. Payroll, attendance, salary processing and related HR work are excluded;
manufacturing cost evidence does not imply a payroll subsystem.
**Scope clarification, 2026-10-10:** The user included job work in both directions in the
[Vouchers scope](vouchers-plan.md#27-job-work-and-manufacturing-included-scope). Its V8 must
support material custody, processing, returns/scrap, service charges and statutory evidence.
The minimum Catalog BOM definitions needed by that implementation must be selected explicitly;
this does not automatically activate all 20 optional tables below. Job-work tax recording is
specified in [the India tax plan](voucher-tax-recording.md#5-job-work-challans-and-inventory-exceptions).
**D08 decision, 2026-10-11:** The user selected the baseline first for Phase 6:
single-level BOM/process definitions, multiple outputs, scrap, WIP and both
principal/worker directions. Multi-level expansion and substitutions are
excluded from the initial release and must fail closed. See the
[Phase 6 execution contract](voucher-phase6-execution.md). Definition math may
be built ahead of B30; it cannot activate job-work stock or actual costing.

**Status:** Proposed Catalog extension, 2026-09-11. Operation/route authoring and the M1 BOM
identity/draft/revision/component/output/assignment slice (single-level only) were implemented
2026-10-27; substitution, phantom BOMs, location/quality/cost children, bulk authoring and
execution handoff (M2-M4) remain pending. See the decision log.
**Scope:** Optional manufacturing definitions and reproducible estimates. No production execution.
**Size:** 20 optional Catalog tables.
**Read with:** [table inventory](catalog-table-inventory.md), [pricing](catalog-pricing-design.md),
[configuration](catalog-product-configuration.md), [inventory contract](catalog-inventory-integration.md).

## 1. Research findings and design decision

TallyPrime documents named alternative BOMs, an output quantity basis, components, godown
selection, co-products/by-products/scrap, allocation percentages and additional manufacturing
costs. Its Manufacturing Journal records consumption and production. We adopt the useful
definition concepts while respecting this platform's separate inventory owner.
[TallyPrime manufacturing](https://help.tallysolutions.com/tally-prime/inventory/manage-inventory-in-manufacturing-tally/).

ERPNext documents multi-level BOMs, logical phantom assemblies, routing operations, repeated
component rows, alternatives and approximate manufacturing costs. It distinguishes workstations
from stockholding warehouses. These are useful design checks for assemblies and process recipes.
[ERPNext BOM](https://docs.frappe.io/erpnext/bill-of-materials).

Changing a subassembly does not automatically update its parents in ERPNext: revised parents
must reference the replacement BOM. We retain explicit child revisions and add reviewed
where-used impact before adoption.
[Multi-level revision behavior](https://docs.frappe.io/erpnext/managing-multi-level-bom).

The rules below are our proposed design, not claims about competitors' missing features or an
inspection of their source code. The main additions are enforceable revision history, exact
unit/quantity semantics, bounded graph expansion, protected estimates and reliable consumer handoff.

## 2. Ownership and optional enablement

| Catalog owns | External owner retains |
|---|---|
| BOMs, revisions, components, expected outputs and approved substitutions | Production/work orders, scheduling, job cards and actual substitutions |
| Reusable operation/routing definitions and estimated charges | Machines/work centres, labour, calendars, capacity, time capture and maintenance |
| Material/output requirements, quality specifications and location defaults | Reservation, picking, lot/serial allocation, inspections, consumption and production receipts |
| Expected yield/scrap and estimate allocation rules | Actual yield/scrap, WIP, subcontract custody, costing, variances and financial posting |
| Revision release manifests and protected cost estimates | Actual batch genealogy, recall tracing, stock movements and product ledger |

Execution belongs in the existing Billing/inventory ownership, subject to its own future design;
do not introduce an eighth API or a Catalog production-order table. Supplier identity, purchase
orders and subcontract settlements remain outside Catalog. Reports owns large manufacturing analytics.

Propose one fixed company capability, **bom_definitions**, requiring inventory. It is currently
absent from the runtime and must be supplied by Identity's capability contract before enablement.
The Catalog checklist consumes that contract; it does not implement Identity's source changes.
Native Product Configuration controls the options below. There is no implied operational
manufacturing capability: definition authoring and estimation may be ready while execution is unavailable.

Feature-off companies keep ordinary goods/service behavior and need no BOM. Disabling future
authoring/selection preserves published definitions, estimates and referenced history. Revoking
operational use requires the owner's acknowledgement; a flag cannot invalidate a running order.
If the capability has become subject to Identity's use ratchet, follow that existing contract.

## 3. Product and BOM structure

| Concept | Native contract |
|---|---|
| Goods/service | Produced physical outputs must be stock-enabled GOODS SKUs. Services can contribute estimated operations/charges, never physical output or consumption. |
| Manufacturing profile | Dated SKU profile: sourcing BUY/MAKE/BOTH; applicable raw-material, packaging, subassembly, finished-good or recoverable-output roles; default BOM requirement. Multiple roles are allowed. Existing purchase/sale eligibility stays authoritative. |
| Named BOM | Stable company/code identity and kind MANUFACTURE or PHANTOM. MANUFACTURE covers assembly and bounded process recipes; exactly one primary output SKU. |
| Draft and revision | ETag-protected typed draft; publishing creates a complete immutable revision with reason, approver where required, content hash and pinned dependencies. Effective selection is controlled by dated assignments; revised content never edits a published row. |
| Components | Stable line IDs, sequence, actual SKU/unit revision, quantity basis, loss policy, optional route step and native dimensional specifications. Repeated SKU rows remain distinct for different cuts/operations. |
| Physical subassembly | Explicit component mode STOCK_INPUT or EXPLODE_CHILD. The latter pins a published child revision producing that exact SKU; no availability-based mode switching. |
| Phantom | A logical group with its own positive scaling basis, no output SKU/stock/cost balance. A parent component references the phantom revision directly; no dummy service item. Always expand; the parent retains traceable paths. |
| Outputs | Primary output plus optional co-product, by-product and recoverable scrap SKUs. Output quantities and costing roles are explicit; process loss is not a stock item. |
| Assignment | Dated default BOM revision for exact primary-output SKU and optional production warehouse. Exact warehouse beats company-wide; overlap at either specificity is rejected. Explicit alternatives require authorized selection and compatible applicability. |

Default assignments point to published revisions, not a mutable 'latest BOM'. A production
warehouse is a Catalog location reference, not a machine or an inferred manufacturer plant.
Family copy/templates can generate drafts, but publication resolves every output/component to
real SKUs. No unresolved colour/size placeholder or custom-field expression reaches a consumer.
Separate standard, premium, packaging or make/buy alternatives are named BOMs, not customer masters.

Primary bom_output is the single authority for manufacture basis quantity B, yield y and unit;
the revision header only exposes derived aliases. Other outputs have their own nominal quantities
and yields. A phantom has a positive logical count basis on bom_revision instead, no physical
unit profile, output, yield, route, fixed/run input or charge. Its variable inputs expand into
the containing requirement tree; physical children still retain their own run/setup definitions.
Only a primary output drives default selection/expansion; co-product demand planning is external.

Drafts may reference new DRAFT SKUs. Publication requires finalized validated unit/tracking
revisions; operational selection requires ACTIVE products and the complete acknowledged release.
For a new MAKE SKU requiring a default BOM, publish the definition against its finalized profiles,
then atomically activate the SKU and dated assignment in Catalog. This avoids a circular active-
product/active-BOM prerequisite while preventing premature operational selection.

Sales bundles/promotional gifts do not imply assembly. Pack conversion changes units of the
same SKU; manufacturing consumes inputs to produce outputs. Rework, dismantling and repair
execution are deferred: never generate a reverse BOM by negating quantities. Consuming and
producing the same SKU in a normal BOM is rejected rather than hiding a rework loop.

## 4. Quantity, yield, batch size and substitutions

Reuse DECIMAL(19,4), item_unit_revision, exact rational conversions, quantity increments and
per-N bases. Intermediate arithmetic must be exact or use the bounded platform Decimal rules;
no float or extra storage precision. Serialized input/output base quantities remain integers.
Each component uses either a physical SKU or phantom reference, never both. A physical
component can additionally pin a child BOM only in EXPLODE_CHILD mode.

- Store a positive nominal primary output basis B and expected good yield y, where 0 < y <= 1.
  For requested good output Q, scale n = Q / (B * y). Report both nominal and expected good
  output. Other outputs state their own quantity per nominal basis; do not apply primary yield
  to them again. Multi-output formulas must identify where every yield/loss applies.
- Component quantities declare GROSS_INPUT or NET_REQUIRED. Gross is scaled directly. Net
  uses q * n / (1 - component_loss), with 0 <= loss < 1. BOM yield and component loss describe
  different losses; validation/preview must expose both and prevent importing an already gross
  quantity as net. A stock scrap output must not count the same process loss twice.
- Support variable-per-basis and fixed-per-run inputs/charges separately. Batch min/max/multiple
  applies to nominal run sizes. Requests provide a valid run breakdown when fixed costs or
  batch limits matter; deterministic splitting is an explicit preview option, not an implicit
  assumption. Each expanded subassembly has its own run breakdown and setup count.
- Default quantity handling is REJECT if not representable. Explicit ROUND_UP_TO_INCREMENT
  returns exact requirement, planned issue and overage separately; it never manufactures extra
  good output silently. Partial packs obey the existing unit profile. Aggregate summaries never
  merge distinct cut/operation requirements before rounding.
- Optional percentage recipes use one compatible physical dimension and a declared gross-input
  basis. Component percentages total exactly 100%; packaging, services and setup inputs sit
  outside that pool. Output yield is separately declared. Do not convert mass to volume using
  guessed density or apply both percentages and component-loss gross-up to the same pool.

Example: B = 100 pieces, y = 0.95, Q = 190 good pieces gives n = 2 and nominal output 200.
A 10 kg net component with 20% component loss needs 25 kg. A 0.5 kg fixed setup input over
two declared runs adds 1 kg: planned input is 26 kg. Output/scrap quantities require their own
definition; the difference between kilograms and pieces is not a mass-balance calculation.

An approved substitute is local to a BOM component/revision: alternate SKU, exact replacement
ratio, unit/profile constraints, validity and approval requirement. The supported initial mode
selects one substitute for the entire line; split substitution and partial-share limits are
deferred and rejected as unsupported settings. No chain inference, silent cheapest
choice or two-way assumption. Generic item_relationship alternatives only suggest candidates.
Chosen substitutions are explicit estimate inputs and later pinned by the execution owner.

Publishing and expansion reject cycles through child/phantom and allowed substitute-child
edges, including different revisions that recur to an ancestor output SKU. Shared subassemblies
in independent branches are valid. Start with depth 32, 1,000 direct lines/revision and 10,000
expanded paths/request; confirm bounds against workload tests in M4. Never return truncated
requirements as complete. Large valid exports use existing durable jobs.

## 5. Operations, quality, tracking and stores

Reusable manufacturing_operation revisions define the operation and optional service reference.
Manufacturing routes contain ordered steps with pinned operation revisions, setup/run time,
time basis, declared batch sizing and lead-time estimates. Initial routes are sequential;
parallel scheduling, resource capacity and calendar promises are outside this extension.
Component/quality/charge step references must belong to the pinned route. If a route changes,
publish a BOM revision with a reviewed remap; stable step codes do not authorize silent remapping.

Quality requirements are bounded native numeric-range, boolean or controlled-choice checks,
linked to input/output/step and pinned native attribute/unit definitions. They state whether
inspection/release is required; they do not store test results, certificates, sampling plans,
equipment calibration or quality-release decisions. No executable expressions or custom-field
policy. A consumer unable to enforce a required check must reject operational activation.

Reuse item tracking/identifier/handling profiles for batch, expiry, serial/IMEI and remaining
shelf life. BOMs contain no physical lot/serial numbers. Produced lot numbers, dates, identifiers,
actual shelf-life derivation and component-to-output genealogy belong to Billing. Authoring a
BOM cannot certify an output's expiry or quality. Reuse manufacturer/site references where
needed for approved sources; never create a supplier account from a BOM import.

bom_location_default records issue, output, WIP or recoverable-scrap location hints. Main is
the initial fallback for compatible issue/output roles. WIP/quarantine/scrap defaults require
explicit role suitability; do not silently route them to a saleable bin. Multi-store/bin rules,
actor scope and SKU restrictions still apply. Extend the existing warehouse policy definition
with independent allow_production_issue/allow_production_receipt; sale/purchase permission does
not imply these permissions. They remain operationally unavailable until Billing supports and
acknowledges them. Defaults neither move stock nor guarantee availability.

## 6. Cost estimates and relationship to prices

Catalog computes **manufacturing estimates**, never actual production cost. A saved estimate
pins BOM/route/unit/configuration revisions, good-output target, run sizes, substitutions,
valuation date, currency and every source reference/version. Historical estimates are immutable;
a refresh creates another estimate. Child expansion is costed once: either use the stocked
subassembly's permitted reference cost or expand its child estimate, never both.

| Input or result | Rule |
|---|---|
| Materials | Explicit source policy chooses dated Catalog purchase net reference or item_reference_cost; no silent fallback to selling price/MRP or actual-cost projections. |
| Operations/services | Declared fixed-per-run, per-output or time-based estimate from a pinned service reference cost or authorized manual estimate. These are not wages, supplier invoices or machine accounting. |
| Overheads | Typed fixed or percentage-of-direct-material / direct-operation / combined-direct-cost charges; no recursive overhead, arbitrary script or percentage on a total containing itself. |
| Tax/currency | Comparable explicit cost basis and one currency. Unknown recoverability, incompatible bases or missing FX context makes an estimate incomplete; do not calculate transaction tax or guess FX. |
| Multi-output allocation | Primary-only or explicit output percentages totaling 100%, including primary. Zero-cost scrap is explicit. Allocate the rounded residual deterministically to primary so allocated amounts reconcile exactly. |
| Unit estimate | Each output's allocated estimate / expected good output in its pinned unit, represented using the existing per-N basis when needed. Zero expected quantity cannot receive positive allocation. |
| Commercial adoption | Authorized preview can publish a complete estimate as a new STANDARD_ESTIMATE item_reference_cost, with source estimate/output/run basis and date. Price recipes may then use that reference. No automatic selling/MRP/purchase-rate rewrite. |

Example: materials 800 + operation estimates 150 + overhead 50 = 1,000. An explicit 80%/20%
allocation gives 800 to 100 primary pieces and 200 to 20 co-product pieces: estimates 8 and
10 per piece. Treating all 1,000 as primary cost would double-count the co-product allocation.
Different run sizes can give different per-piece estimates because setup is fixed.

Recoverable scrap uses the declared allocation method; estimated resale value is not negative
material cost or recognized revenue. Net-realizable-value allocation, joint-process optimization
and automatic cost revaluation are deferred. Changing a BOM never changes posted inventory,
COGS, a receipt layer, batch MRP or actual manufactured cost. Free-of-charge inputs require
explicit zero-cost evidence; absent/denied source is not zero.

Results state COMPLETE, INCOMPLETE or INVALID with scoped reasons. Missing/denied source costs
must not leak through totals, residuals, sorting, export or asynchronous artifacts. Cost reading,
estimating, approving and reference-cost publication have separate permissions. Only complete,
currently authorized, non-stale source manifests qualify for reviewed reference-cost adoption.

## 7. Configuration and lifecycle controls

product_manufacturing_policy is a typed child of Product Configuration revisions, not a generic
JSON rule bag. Reuse company/type/group/family/SKU inheritance within mandatory constraints.

| Area | Controls and safe default |
|---|---|
| Enablement | bom_definitions OFF; per-SKU manufacturing participation OPTIONAL; required default BOM only for an explicitly configured MAKE/BOTH activation. |
| Structure | Alternative BOMs, multi-level, phantoms, percentage recipes, secondary outputs and substitutions independently disabled until their supported option is enabled. |
| Precision/batches | Quantity rounding REJECT; typed batch min/max/multiple; accepted precision comes from existing unit profiles, not a separate BOM scale. |
| Quality/routing | Optional operation routes and inspection requirements; declared required checks need a compatible runtime consumer for operational activation. |
| Cost | Estimation OFF until source policy configured; explicit material sources, operation/overhead rules, allocation method and separate reference-cost publish permission. |
| Change governance | Review/publish authority, future effective dates, impact acknowledgement and exact revision adoption; no automatic parent update. |
| Operational handoff | Source/consumer support and acknowledgement exposed separately from definition availability. Native controls cannot enable unimplemented backflush, WIP or production posting. |

Published revision content is immutable. Effective applicability/default assignment changes use
dated, audited actions under aggregate locks; no overlapping defaults. Retire blocks new
selection but does not invalidate pinned history. Consumer orders must explicitly adopt a
replacement, subject to execution-owner rules. Hard recall/stop is an external operational
action, not an inferred effect of Catalog retirement.

Reuse catalog_policy_state/release/consumer_ack, domain audit/outbox, existing jobs and source
freshness contracts. A revision release manifest includes the complete dependency closure and
hashes; consumers acknowledge only after all required parts are durable. Parent events arriving
before children remain unready. Referenced products/units/routes cannot be hard-deleted.
Draft graph validation at publish is serialized per company graph generation so two concurrent
changes cannot evade cycle/assignment checks. No remote calls occur inside the publish transaction.
Draft editing does not reserve publication dates or graph validity. Review-required publication
records a distinct authorized approver; maker/checker separation follows the native policy and
cannot be bypassed by an import worker or service account.

## 8. API, bulk and persistence

All routes use the existing Catalog prefix/version, thin routers, strict native schemas, scoped
services, fixed permissions, keyset lists, expected_version and idempotent mutations. Illustrative
suffixes below become the owned endpoint registry in M0; none execute manufacturing.

Reuse libs/platform security, Decimal/conversion mechanisms, field-policy/custom-field adapters,
jobs, audit/outbox, idempotency and release transport. BOM graphs, selection, quantity rules,
estimate policies and their ORM stay in Catalog; do not put manufacturing domain logic in libs.

| API family | Purpose |
|---|---|
| /boms; /boms/{id}/drafts; /bom-drafts/{id} | Scoped identity, clone and draft editing with full-revision validation. |
| /bom-drafts/{id}/validate, /preview, /publish | Errors, normalized requirements/diff/impact and immutable publication. |
| /boms/{id}/revisions; /bom-revisions/{id}; /retire | Version history and governed stop of new selection. |
| /bom-assignments; /items/{id}/bom-resolution | Dated default/alternative assignment and context-aware revision selection. |
| /bom-revisions/{id}/explode, /where-used, /compare | Bounded material tree, reverse impact and normalized revision diff; no stock availability claim. |
| /bom-revisions/{id}/estimates; /bom-estimates/{id}; /publish-reference-cost | Saved reproducible estimate and separately authorized reviewed cost publication. |
| /manufacturing-operations; /manufacturing-routes | Reusable revisioned definitions and their validate/publish/history actions. |
| Existing configuration/import/release routes | Native options, typed import templates, dry run, commit and consumer readiness. |

DB/API representation uses [20 optional tables](catalog-table-inventory.md#14-optional-bom-and-manufacturing-definitions).
bom_draft holds the validated authoring document with ETag; publication materializes normalized
bom_revision, bom_component/substitute/output/location/quality/cost children atomically. Route
and operation revisions use DRAFT -> PUBLISHED -> RETIRED with immutable published content;
their child rows share that lifecycle. Profiles and assignments keep dated immutable history.
Estimate lines retain tree path, quantity/unit, cost basis and source versions, not a live cache.

Typed bulk resources cover operations/routes, BOM drafts/components/substitutes/outputs and
assignments. Use explicit source keys and line IDs. Missing children, cycles, profile/permission
conflicts or stale dependencies fail validation. Draft-only references can be staged together;
publication freezes a topologically sorted dependency manifest. Child revisions publish first.
Each BOM revision is atomic; a job spanning several BOMs is resumable, not one giant transaction.
Partial job completion does not activate a parent with missing children. All-or-nothing selection
activation uses the existing complete policy release after every intended revision succeeds.

Bulk changes to quantity, material, yield, route or allocation create new drafts/revisions,
show where-used/cost/default-assignment impact, and never mutate published recipes or running
orders. Recheck current authority, ETags, source versions and graph generation at commit. Reject
production quantities actually consumed, actual costs, physical serials and ledger imports here.
Cancel before commit stops pending work; after publish use governed retire/replacement, not deletion.

## 9. Delivery phases and acceptance

| Phase | Deliverable | Depends on | Exit evidence |
|---|---|---|---|
| M0 | Scope, source readiness, manufacturing configuration and native contracts | C0, C6 | Feature-off remains unchanged; ownership/options/permissions fixed. |
| M1 | BOM revisions, assignments, exact expansion and input/output specifications | M0, C7 | Deterministic selection/quantities; graph/history/concurrency constraints hold. |
| M2 | Reusable routes and complete protected manufacturing estimates | M1, C8, C9 | Reproducible estimate and reviewed reference-cost adoption; no actual-cost write. |
| M3 | Bulk authoring, impact review and dependency-complete publication | M2, C10 | Atomic revisions, resumable jobs, no partial activation or silent parent change. |
| M4 | Optional-module verification and truthful execution-owner handoff | M3, C5 | Security/recovery/limits pass; definition readiness and operational readiness separate. |

The base 147-table, 165-task plan remains deliverable without this optional branch. With this
branch selected there are 167 Catalog tables and 205 tasks over 20 owned phases. M0 may start
after C6; follow dependencies and finish M4 before C15 for a release that includes BOM definitions.
The combined schedule has 12 dependency stages; the base schedule without BOM has 11.
Promotions have no dependency on manufacturing.

Acceptance covers wrong tenant/company/scope, protected component/cost inference, goods/service
constraints, exact pack/serialized quantities, yield versus gross/net loss, setup run counts,
mixed dimensions, secondary allocation conservation, shared/cyclic graphs, stale revisions,
simultaneous publications, interrupted imports, duplicate/out-of-order events and graph limits.
Traceability, physical conservation, stock/value reconciliation and production reversal tests
belong to Billing's future execution plan; Catalog mocks cannot prove those behaviors.

## Decision log

- 2026-10-27: Sequential route authoring is implemented as an independent preparatory slice.
  Drafts contain 0?50 ordered native steps; publication requires at least one contiguous sequence
  and published nonretired revisions of active operations. Steps retain stable IDs through draft
  reordering. DECIMAL(19,4) setup/run/lead-time minutes and positive quantity basis are exact;
  PER_OUTPUT_UNIT binds to the BOM output unit at adoption, PER_BATCH declares the batch size.
  Retirement preserves content and pinned history. This does not enable BOM selection, estimation,
  scheduling or execution; full BOM configuration and consumer release gates remain separate.


- 2026-10-27: M0 starts with independent reusable operation authoring. Stable company/code/name
  headers have active/inactive availability; codes freeze once any revision exists. Required typed
  specifications and change reasons may reference a current-company active SERVICE SKU. Revisions
  progress DRAFT -> PUBLISHED -> RETIRED; published content and historical references are preserved.
  Expected versions, existing idempotency/audit mechanisms and current company/field authority apply.
  Later routes must pin a published nonretired revision. This slice does not assert `bom_definitions`
  or operational readiness; that capability/configuration contract remains a later route/BOM gate.
  Operation publication supplies no charge calculation, estimation, expansion or execution.

- 2026-10-27: M1 BOM identity, ETag-protected draft, immutable revision, component and output
  persistence implemented, matching the D08 single-level baseline: exactly one PRIMARY output per
  draft/revision (enforced by a generated column plus unique constraint), GROSS_INPUT/NET_REQUIRED
  component basis with PER_BASIS/PER_RUN timing, and an optional pinned route step. There is no
  EXPLODE_CHILD component mode, phantom kind, substitute table or multi-level reference anywhere in
  the schema, so multi-level expansion and substitution stay structurally unsupported rather than
  merely rejected by a runtime check. Dated bom_assignment adds default primary-output applicability
  per item and optional warehouse scope, with non-overlapping active intervals enforced under the
  existing company policy lock. Publish/retire/create/update use the existing idempotent command
  pipeline with field-policy, tenant/company scope and permission checks (`bom.manage`/`bom.publish`/
  `bom.assign`); none of this flips `bom_definitions` to ready or admits any execution, cost estimate,
  location/quality child, bulk authoring or operational-readiness behavior from §§4-8 above.

- 2026-10-10: User confirmed job-work coverage. Vouchers job work is included later scope;
  Catalog's optional full manufacturing definition package remains separately scoped. Added
  links to principal/worker workflows and India GST challan/service/return evidence.
- 2026-10-10: Mapped future manufacturing execution to Vouchers Stock Journal workflows
  and proposed Accounting stock/WIP/value posting. Payroll and related HR work are excluded.

- 2026-09-11: User requested optional BOM/manufacturing coverage. Reviewed official TallyPrime
  and ERPNext documentation; added definition/estimate scope, 20 optional tables and M0-M4.
  Kept manufacturing execution, actual costs, parties, WIP and ledger outside Catalog.
