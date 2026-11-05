# Company and item configuration completion plan

**Prepared:** 2026-10-12. **Status:** implementation in progress; see the
[execution record](company-item-configuration-execution.md) for measured progress.
No voucher or stock execution capability has been activated by this work.
**Scope:** backend company and product/item configuration and its voucher, tax, stock and
reporting consumers. UI and payroll are excluded. This plan supplements the existing
[company](company.md), [capability](company-features.md), [product configuration](catalog-product-configuration.md),
[stock](voucher-stock-recording-reporting-design.md) and [voucher configuration](voucher-configuration-design.md)
contracts. It does not replace their service ownership or release gates.

## 1. TallyPrime concepts and platform translation

TallyPrime separates company creation (financial-year start and books-begin date), company
features (accounts, inventory, bill-wise, batches, price levels, job work, GST/VAT), and
stock-item configuration (group, unit, tax/HSN, batch/expiry, valuation method, standard
rates, opening stock and reorder levels). Its inventory-to-accounts integration is an
explicit company choice. These are useful *configuration concepts*, not a promise to copy
all Tally behavior or its permissive feature changes. Primary references:

- [Create Company](https://help.tallysolutions.com/create-company/)
- [Company Features (F11)](https://help.tallysolutions.com/company-features-f11-tally/)
- [Manage Stock Items](https://help.tallysolutions.com/knowledgebase/manage-stock-item-tally/)
- [Stock Items for GST](https://help.tallysolutions.com/set-up-stock-items-for-gst/)
- [Stock Valuation Methods](https://help.tallysolutions.com/inventory/stock-valuation-methods-tallyprime/)
- [Reorder Stock Items](https://help.tallysolutions.com/tally-prime/inventory/reorder-stock-items-reorder-status-and-reorder-quantity/)

| Concept | Existing authority | Completion rule |
|---|---|---|
| Company identity, books, fiscal start, currency, precision, addresses, GST registrations and licences | Identity company and dated statutory records | Keep native fields and first-posting locks. Resolve a registration by statutory context/date; do not turn a display default into posting authority. |
| Broad capabilities, such as inventory, multiple godowns, batches, expiry, serials and price levels | Identity fixed company-feature catalogue | Offer only implemented capabilities. Existing first-use ratchets and source replicas apply. No tenant-created money-driving feature keys. |
| Accounting bill-wise, credit, fiscal and stock-account behavior | Accounting masters, fiscal facts and posting owner | Map company choices to explicit supported owner rules. A company setting cannot replace ledger-level bill-wise or invent a second stock ledger. |
| Company, type, group, family and SKU product defaults | Catalog published product-configuration scopes/revisions | Reuse inheritance, dated publication and pinned adoption. A narrower scope cannot weaken legal, capability or hard product requirements. |
| Item identity, groups/categories, units, tax, rates, batches, warehouses, BOM | Catalog native masters and histories | Keep separate typed authorities; effective item read aggregates provenance/readiness without copying values to a generic item JSON blob. |
| Opening stock, physical quantity, valuation and sale/purchase effects | Vouchers capture and Accounting posting/stock owner | Item edits never create stock. Every effect needs source, fiscal date, cost/tax evidence, immutable movement and reconciliation. |

The platform already contains a substantial native Catalog configuration API: scoped
drafts, published dated revisions, effective reads, source explanations, authoring defaults
and adoption. It also has item inventory profiles with FIFO/moving-average/specific method
choices and a `BLOCK/WARN/ALLOW` negative-stock setting. These are **definitions**, not proof
that all three valuation/negative-stock modes execute safely. Code inspection found no
Accounting stock-movement/valuation implementation in the current source tree. Its release
gate still names `valuation_methods`; stock and inventory activation must remain closed.

The older [company/item TODO](company-item-configuration-todo.md) marks warehouse GSTIN,
negative-stock policy, HSN lookup and a cash-receipt gate complete and leaves later phases
open. Reconcile those marks against current migrations, tests and consumers at phase 0.
In particular, a stored `WARN` or `ALLOW` choice must not be exposed as an executable
negative-stock policy while valued posting can only safely block. The old TODO's
"Billing" wording and proposed sequence/stock work must be remapped to the actual
Vouchers/Accounting owners and current batch tracker, without restarting completed work.

## 2. Target configuration contract

**Company setup/readiness.** Return an authorized, versioned company-setup view with
source versions, effective dates, dependencies, missing prerequisites and locked reasons.
Group settings by legal identity/statutory registrations, books/fiscal/numbering,
accounting/bill-wise, inventory/tracking/valuation, warehouses, commercial/pricing and
presentation. This is a read model over the existing owners, not a second writable
configuration store. Identity remains the writer for company and capabilities; Catalog
for product/warehouse rules; Vouchers for voucher types/classes/numbering; Accounting
for ledger, posting and fiscal rules. Never make synchronous cross-service calls inside
a money transaction. An administrative read may compose protected owner snapshots;
posting uses acknowledged local versions and immutable source evidence.

**Company policy decisions.** Define the supported behavior before adding controls:

1. Maintain accounts is baseline. Inventory may be disabled, and account-only invoice
   entry remains possible under the appropriate voucher type. Tally's separate
   "integrate accounts with inventory" control cannot be a free toggle here: initial
   stocked invoice execution must reconcile stock value and GL by one Accounting posting
   owner. A separate stock-only accounting mode requires a distinct reviewed contract.
2. Bill-wise entry is an Accounting account/party policy. A company default may suggest
   it for new parties, but must not retroactively alter open bill references.
3. Default valuation is a Catalog authoring suggestion. The activated item profile pins
   its selected method; Accounting validates supported methods and first-use history.
   FIFO and moving average are the requested initial methods. `SPECIFIC` is selectable
   for execution only after its serialized cost path has passed acceptance. Method changes
   with stock/history need a separately designed cutover or revaluation, never a simple edit.
4. Negative stock is `BLOCK` for executable valued movements until `WARN`/`ALLOW` have
   coherent cost layers, reversal, backdated and reconciliation rules. Existing stored
   choices remain visible as inactive configuration with a readiness reason.
5. Company, registration, item/group and transaction tax choices resolve at the legal
   tax date and named precedence. GSTIN, HSN/SAC and applicable rate must be source-pinned
   on issued documents. A catalogue lookup is a candidate, not self-authorizing tax law.
6. Company physical-location defaults select from Catalog warehouses; they never grant
   location permission or change where existing stock sits. Company address, warehouse
   address and GST registration linkage must be checked together at issue time.

**Item configuration.** The effective read for a candidate or existing SKU should show
item identity/status, kind, group/type ancestry, base/alternate units and exact quantity
grid, sell/purchase eligibility, current dated tax classification/rate source, pricing
purpose/level/unit/lot scope, inventory/tracking/expiry/issue/valuation policy, warehouse
restrictions, handling/warranty/return profile, BOM participation and replenishment rules.
Each field needs its owner revision, effective interval, inherited/explicit source,
applicability, editability and `ready_for` reasons for authoring, sale, purchase, opening,
production and reporting. Goods and services get different applicability. Custom fields
remain descriptive; no tax, price, stock or posting rule reads them.

Reorder point, target/safety stock, MOQ, order multiple, supplier lead time and minimum
sale quantity are distinct. Replenishment may suggest a quantity using saleable on-hand,
reservations and *verified* incoming/outgoing orders; missing producers produce an
"unavailable" basis rather than an invented zero. Suggestions do not post or automatically
create a purchase order. Opening quantity/value stays on an opening voucher, never on Item.

## 3. Phased delivery

The identifiers **CI-P0** through **CI-P5** belong only to this company/item plan.
They are not the voucher tracker's C0–C4 activation checkpoints or new voucher batches.

| Phase | Scope and implementation | Completion evidence |
|---|---|---|
| CI-P0 — audit and reconcile | Inventory current Identity/Catalog/Accounting/Vouchers schemas, APIs, flags, revisions, tests and owner projections. Compare the old TODO and product-config claim to executable behavior; classify each control as supported, definition-only, blocked or absent. Record data migrations needed without rewriting published revisions. | Traceability matrix for every proposed setting; corrected checklist and failing regression cases for reproduced defects. No feature flag or activation changed. |
| CI-P1 — company authority and readiness | Complete protected setup/effective/readiness contracts, company fiscal/statutory/feature validations, first-use locks, feature/source version propagation and non-disclosing scope checks. Keep configuration writes in existing owners. Explicitly gate inventory/account integration and negative-stock methods to implemented owner capabilities. | Two-tenant API tests, stale-version/idempotency/audit tests, first-posting and statutory-date/registration cases, source-lag and disabled-feature cases. |
| CI-P2 — product configuration repair | Recheck scoped inheritance, PATCH/null/clear semantics, published revision immutability, SKU adoption, goods/service rules and exact units. Complete item effective response and source pins, including tax/group, price, inventory and manufacturing readiness. Repair any native option whose advertised behavior has no consumer. | Company/type/group/family/SKU precedence matrix, future-dated changes, historical SKU pins, permissions, bulk parity and native MySQL FK/roundtrip tests. |
| CI-P3 — item commercial, tax and location controls | Wire dated HSN/SAC/rate classifications and GSTIN/location selection to owner evidence; reconcile price levels, MRP/standard buying/selling rates and allowed voucher discounts; complete warehouse default/allowlist constraints. Implement typed replenishment settings and a read-only suggestion/report basis once order and stock facts are dependable. | Multi-registration, multi-location, rate/date-change, excluded/expired lot, unit conversion, MOQ/order-multiple and source-freshness tests. No unsupported tax or price fallback. |
| CI-P4 — transaction consumers | Extend Vouchers capture/preview and Accounting posting to pin/check company and item configuration revisions for sale, purchase, returns, opening stock, transfer, manufacturing and job work as their respective batches become ready. Build/reconcile the single stock quantity/value ledger, cost layers and GL effects before enabling inventory execution. Preserve original evidence on reversal/return. | Invoice-stock-GL balance, FIFO/moving average, lot/serial/expiry, negative-stock block, period close, backdated refusal, duplicate/outbox replay, returns and concurrent issue tests. Release gates remain off until owner acknowledgements. |
| CI-P5 — rollout and review | Generate OpenAPI/clients; add operator-facing setup-readiness errors and migration/rebuild/backfill procedure. Run affected full suites, Ruff/mypy, native DB tests, two-pass security/correctness review and a staged two-company rehearsal. UI may consume the metadata later. | Signed-off setting-to-owner matrix, discrepancy-free stock/GL reconciliation and explicit activation evidence. Update the voucher tracker and TODO only with measured results. |

Order CI-P0–CI-P3 so that no company/item setting claims execution from storage alone. CI-P4 may
proceed in the existing voucher batch order, but each stock/tax/valuation mechanic must
have its own owner-projection acknowledgement and release gate. Changes to schemas,
shared contracts, permissions or events require the repository's migration, generated
client, replica and audit/outbox sync checks.

## 4. Detailed work packages and exits

### CI-P0 — current-state audit and contract freeze

**Prerequisite:** none. This phase is read-only except for plan/checklist corrections and
regression tests that reproduce a confirmed defect.

1. Build a setting register with Tally concept, exact existing API/model/migration,
   authoritative service, current runtime consumer, first-use lock, tax/date dependency,
   status (`EXECUTABLE`, `DEFINITION_ONLY`, `BLOCKED`, `ABSENT`) and target phase.
   Include company financial/statutory fields, Identity feature keys, Catalog product
   configuration, item inventory profile, warehouse policy, Accounting party policy,
   Vouchers type/class policy and fiscal/numbering settings.
2. Verify the four completed marks in the old company/item TODO against native tests and
   code: warehouse-to-GSTIN linkage, negative-stock setting, HSN/SAC lookup and cash-receipt
   gate. Mark master-only and jurisdiction-sensitive behavior precisely. Replace its stale
   Billing ownership and duplicate voucher work references with links to the live tracker.
3. Map every advertised Catalog `valuation_method` and `negative_stock_policy` choice to
   an Accounting stock producer and report. Where none exists, specify the exact fail-closed
   API/readiness behavior before any further publication or use.
4. Freeze initial behavior decisions: accounts baseline; integrated stock/GL posting for
   stocked invoices; FIFO and moving average only; negative stock blocked; historical
   item/configuration revisions preserved; India GST baseline with state-VAT profile
   requiring explicit legal/date scope. Record any unimplemented choice as unavailable.
5. Write end-to-end scenarios spanning company, SKU, voucher, posting and report, with
   existing test locations and missing integration fixtures identified.

**Deliverables:** reviewed setting register, corrected old TODO and tracker links,
versioned field/owner matrix, migration inventory and test gap list. **Exit:** every
proposed control has one writer and a known consumer or an explicit non-executable state;
no old checklist checkmark is treated as runtime proof.

### CI-P1 — company authority, capability and readiness

**Prerequisite:** CI-P0 setting register and supported-mode decisions.

1. Keep `company` creation/PATCH, dated tax registrations, addresses, licences, fiscal
   context and feature changes under Identity. Validate books-begin versus financial-year
   start, jurisdiction/state/base currency, tax-registration overlap, feature dependencies
   and first-posting immutability at the writer. Accounting fiscal/period state remains
   its own authority. Add native fields only for a demonstrated missing business rule;
   do not store a second company settings JSON object.
2. Expose an Identity **company setup/readiness read** (proposed
   `GET /v1/companies/{company_id}/setup-readiness`) with field group, current source
   version, current capability, lock reason and missing prerequisites. It reports only
   Identity-owned facts; Catalog/Accounting/Vouchers expose their own protected readiness
   fragments. The later UI may compose these reads. No service silently invents another
   owner's current state.
3. Ensure feature/source changes have outbox generation, ordered local projection,
   replay dedupe and fail-closed stale/missing handling. Keep the existing first-use
   reservation fence on posting. A disabled inventory feature, unsupported valuation
   method or unacknowledged warehouse policy must not become postable through an old
   cached read.
4. Review company defaults separately from per-master rules: payment terms and credit
   ceiling are suggestions/limits; bill-wise remains on an Accounting party/account;
   legal GST registration is selected by date/state/document context; locale/printing
   never drives ledger calculation. Define an effective-facts hash for the supported
   posting inputs without including display-only changes.

**Storage/API work:** prefer existing Identity tables and company/feature endpoints;
introduce migration(s) only for verified missing native fields or projection metadata.
Any changed field registry, permission, event and generated client is updated together.
**Tests:** create/PATCH versioning and idempotency, two-company access and field denies,
feature dependency/ratchet races, pre/post-first-posting edits, overlapping/gapped
registrations, source replay and lag, and a read that does not disclose inaccessible
registration data. **Exit:** owner-scoped readiness agrees with actual write gates and
the signed company context consumed by Accounting/Vouchers.

### CI-P2 — Catalog product/item configuration completion

**Prerequisite:** CI-P1 source contract for capabilities and company dates; CI-P0 gap list.

1. Repair any reproduced defect in the existing `product_configuration_scope`, draft,
   revision, effective resolution and SKU adoption paths. Recheck omitted-versus-clear
   PATCH semantics, COMPANY→TYPE/GROUP→FAMILY→SKU precedence, conflicts between type
   and group rules, future-dated publication, protected source explanations, same-company
   references and immutable published/activated pins. Existing `catalog-defaults` and
   group-default adapters must resolve those same revisions.
2. Complete the Catalog **effective item facts** read for candidate and existing SKU:
   product kind/status/group/type, exact base/alternate unit grids, sell/purchase flags,
   tax classification source, active price policies, inventory template/profile,
   tracking/expiry/issue/valuation, allowed location policy, handling/return/warranty,
   BOM participation and authoring readiness. Return each native source ID/version,
   effective date, inheritance path and reason when unavailable. This is an aggregation
   of Catalog-owned native records, not a new writable item blob.
3. Explicitly separate **authoring allowed** from **transaction executable**. A draft
   product can select a valid inventory template while stock execution is unavailable;
   an active product cannot gain a new structural mode by changing a company default.
   Historic adoption and source-linked returns continue to resolve old pins.
4. Validate quantity precision/increments, conversion and service-versus-goods options
   exactly. Unit and price precision are independent of company display precision;
   serial quantities remain whole at the base unit. Direct create, bulk import,
   activation and configuration adoption must invoke equivalent domain rules.

**Storage/API work:** extend existing `product-configuration/effective`, authoring,
activation and item reads first; a new read model is justified only if protected
existing responses cannot convey provenance without breaking compatibility. Preserve
dated revision FKs and one-DDL-per-migration rules. **Tests:** precedence matrix,
future/historical date, ownership/field-deny, inactive group/type, active-SKU structural
lock, decimal grid, bulk parity, concurrent publish/adopt, native MySQL FK roundtrip.
**Exit:** effective facts reproduce the actual approved SKU inputs and never imply
stock, tax or price execution simply because a master revision exists.

### CI-P3 — tax, pricing, warehouses and replenishment

**Prerequisite:** CI-P2 effective item facts and CI-P1 Identity source versions. The
four workstreams can be delivered in small owner-specific batches, but each must finish
its own publication/consumer checks before its setting is described as executable.

1. **Tax:** bind item/group HSN/SAC and classification to dated Catalog tax rules,
   country/state/registration and the legal tax date. Produce a protected resolution
   result with source revision and reason; validate India GST and explicitly scoped
   state-VAT separately. Refuse missing/ambiguous sources. A reference directory is
   lookup assistance, never a replacement for an approved statutory rule.
2. **Commercial:** reconcile Catalog purchase references, standard/level prices,
   MRP, unit/lot/declaration price scope and guards with Vouchers' discount configuration.
   Preview must expose regular price, discount basis/allocations and all source IDs;
   Accounting enforces final price/MRP/benefit ceilings when the necessary Catalog
   projection exists. Keep current manual discount support distinct from automatic
   promotions, which remain behind their own publication and redemption gates.
3. **Location:** validate activity default, warehouse status, actor location scope,
   sale/purchase/return/transfer flags, item allowlist, lot condition and linked GSTIN.
   Main fallback applies only where the company and activity policy allow it. A
   changed default never moves stock or alters a posted document's source location.
4. **Replenishment:** add typed, dated SKU/location overrides for safety stock,
   reorder point, target/maximum, MOQ, order multiple, lead time and supplier
   reference where absent. Return read-only suggested order quantity with `as_of`,
   exact input buckets and completeness/freshness. Start with verified on-hand and
   reservations; include open PO/SO demand only after their producers are acknowledged.
   Reject contradictory thresholds and units. Do not auto-create orders.

**Storage/API work:** reuse tax/price/warehouse histories; add replenishment tables only
after checking existing native profiles. Required new tables carry tenant/company keys,
dated uniqueness, FK ownership, audit/outbox and reversible migrations. **Tests:**
multi-GSTIN and location, historic/future rates, ambiguous tax, MRP and stacked discount,
price-level access, expired/held stock, group precedence, MOQ rounding, zero versus
missing incoming supply, source-lag and cross-tenant access. **Exit:** every effective
tax/price/location/reorder answer has a reproducible source and clear completeness state.

### CI-P4 — voucher and Accounting execution

**Prerequisite:** relevant CI-P1–CI-P3 source publications plus the existing voucher
batch gates. This phase does not skip B15–B27 or the D02 valuation decision work.

1. **Capture and preview:** Vouchers records the selected company registration,
   item/unit/tax/price/location/profile versions and configuration digest on shared
   voucher revision/lines. Its type/class policy can narrow, never widen, company/item
   eligibility. Draft edits recalculate; submission rejects unavailable mechanics;
   approval binds an owner-derived preview rather than trusting hash presence alone.
2. **Owner projection and posting:** Accounting receives acknowledged Catalog/Identity
   generations before accepting a money command. Under one posting transaction it
   re-resolves fiscal/date/legal context, calculates money/tax/stock, creates immutable
   account and stock movements, cost layers and bill/tax references, and emits outbox
   evidence. Stocked sale/purchase/return value and GL inventory/COGS/variance accounts
   reconcile by document and period. Account-only vouchers remain independent of stock.
3. **Physical flows:** implement opening-stock reconciliation once, purchase receipt,
   sale issue, partial order/challan fulfillment, returns, location transfer, counts,
   damage and production/job-work consumption/output in the existing voucher order.
   Lot/serial/expiry and ownership evidence follows each movement; FIFO and moving
   average use exact Decimal and explicit residual allocation. Block negative stock,
   stale sources and backdated movements that would require unavailable revaluation.
4. **History and reports:** source-linked return/reversal uses original policy and
   calculation facts, with a new open-period posting. Stock ledger/balance/expiry and
   account ledger/trial balance/tax registers derive from the immutable owner facts;
   group reclassification is dated rather than rewriting historical stock.

**Storage/API work:** use common voucher tables and Accounting owner movement/cost
tables, not one table per voucher kind or a second Catalog balance. Add required owner
projection schemas/events and migrations in the service that owns each fact.
**Tests:** two-tenant stock/GL paths, approval hash provenance, idempotency/replay,
closed period, concurrent last-unit issue, FIFO/average cost, partial fulfillment,
free/deal and return source linkage when enabled, expired/held lot, transfer conservation,
valuation-to-GL reconciliation and rebuild parity. **Exit:** each enabled mechanic
passes native DB end-to-end acceptance; unfinished mechanics remain disabled.

### CI-P5 — release preparation and two-pass review

**Prerequisite:** all CI-P4 mechanics selected for a release have passed their own
owner acceptance. This phase does not automatically turn on any voucher C0–C4 gate.

1. Regenerate affected OpenAPI and typed clients; reconcile permissions, field sets,
   outbox/event contracts, local replicas, migrations, indexes and downgrade/rebuild
   scripts. Document a safe migration for already-authored company/item settings and
   a discrepancy report for records whose selected mode is unsupported.
2. Run the affected full service suites and representative native MySQL/RabbitMQ
   integration paths; hold the repository's domain coverage floor, Ruff, strict mypy,
   client typecheck and API-contract consistency. Test two companies with different
   GSTIN, inventory and item policies through a fiscal-year boundary and a return.
3. Review twice: first for money/stock/tax invariants and reconciliation, then for
   tenancy, authorization, audit/outbox, idempotency, concurrency and backwards
   compatibility. Reproduce and fix each finding, rerun its affected tests and record
   the final evidence rather than treating prior test counts as current.
4. Publish an operator setup/readiness guide and rollback/repair runbook. Update the
   company/item TODO and voucher tracker with exact supported modes and activation
   evidence; keep UI implementation on a later, separately planned track.

**Exit:** no unresolved discrepancy in the selected release scenarios, protected
readiness equals posting behavior, history/rebuilds agree, and the appropriate existing
voucher activation checkpoint is separately approved and evidenced.

## 5. Decisions to resolve during CI-P0, before dependent implementation

- Which **company-level stock/account presentation modes** are actually required beyond
  the initial integrated posting owner? Do not add Tally's independent-stock option
  unless its GL/report reconciliation semantics are specified and tested.
- `WARN`/`ALLOW` negative stock are committed target modes under the
  [stock execution plan](stock-configuration-execution-plan.md), with Accounting
  shortage costing and posting guards as prerequisites. They remain non-executable
  until those phases pass. `SPECIFIC` valuation is still an open, separately gated choice.
- Which India state-VAT scope, goods and effective periods are needed beyond the agreed
  India GST baseline; state-specific rates, dates and reports require that profile.
- Which reorder inputs are complete enough for a projected-available suggestion. Begin
  with transparent manual thresholds and current verified balances; add order/lead-time
  projection only after those sources are acknowledged.

No decision here activates an incomplete feature, changes an existing company's
posted-history locks, or alters the prior voucher batch statuses.

## Decision log

- 2026-11-04: Removed warehouse/location-specific regular pricing from CI-P3.
  Location permissions, stock allocation, tax context and replenishment remain in scope.
