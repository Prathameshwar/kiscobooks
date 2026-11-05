# Voucher table inventory

**Date:** 2026-10-10. **Status:** Proposed inventory for the agreed scope; no tables created.
**Read with:** [shared model](voucher-data-model.md), [delivery plan](vouchers-plan.md),
[customization](voucher-extensibility.md), [tax](voucher-tax-recording.md) and
[inventory ownership](catalog-inventory-integration.md).

This is a comprehensive candidate list for the discussed features, not a universal maximum
or a requirement to build all tables at once. There are **42 Vouchers domain candidates**
for entry and supporting workflows, plus **9 optional operational candidates**. Many of the
42 are conditional on a feature: a plain journal needs no item, tax, transport or tender rows.
Shared infrastructure, existing masters and Accounting/Reports tables are listed separately.
Detailed normalization may merge or split a responsibility during V0; changes must preserve
one source of authority and must not introduce a document table family per voucher kind.
The [implementation roadmap](voucher-implementation-plan.md#4-shared-schema-work) groups these
candidates into phased schema work and requires a constraint/index/backfill manifest before
each dependent migration. The baseline and later candidates are not one compulsory DDL batch.

All Vouchers table names below are proposed. A company-created type adds configuration rows,
not tables. Each applicable row carries tenant/company scope; document details attach to an
exact immutable revision/line. Operational outcomes append history against that revision.
Local relationships use scoped constraints. References to another service are validated IDs
and versioned evidence, never cross-database foreign keys. The initial 22 non-payroll kinds
share these structures. Kind/profile definitions remain a code-defined registry, not arbitrary
user-authored posting behavior in a `voucher_kind` table.

## 1. Type configuration and numbering: 8 candidates

| # | Table | Purpose | Gate |
|---|---|---|---|
| 1 | `voucher_type` | Company type identity, base kind/profile, code and retirement state | V1 |
| 2 | `voucher_type_revision` | Immutable type settings, native company commercial-policy bindings, entry modes, required/default/allowed mechanics and override limits | V1 |
| 3 | `voucher_type_section` | Required/optional/forbidden sections, cardinality and supported conditional rule keys for a type revision | V1 |
| 4 | `voucher_type_field_binding` | Bind accepted Identity header/item field definitions and layout restrictions to a type revision | V1 |
| 5 | `voucher_class` | Compatible account/charge/discount/rounding defaults within type and company commercial restrictions; used versions are immutable and pinned | When classes are enabled |
| 6 | `voucher_number_series` | Issuer/type/registration/document-category series configuration and effective format | V1 |
| 7 | `voucher_number_counter` | Transactionally allocated counters for Vouchers-owned issue-time series | Issued orders, quotations, challans and similar documents |
| 8 | `voucher_number_assignment` | Durable issued-number assignment and void/cancellation evidence; used numbers are never recycled | When a number is issued |

Vouchers allocates its own non-posting document numbers only. Accounting's existing
`document_sequence` remains the internal posting allocator. Accounting's D05/D12 extension
returns a separate statutory identity when its legal date/year/series differs; Vouchers
stores each returned identity read-only with allocator provenance. The current internal
format is not automatically a valid legal invoice number. The two owners never allocate
the same series. Statutory uniqueness applies across derived types. Drafts use IDs. A series
row is configuration, not proof of posting or statutory registration.

### Shared native policy refinements outside baseline counts

The [configuration storage contract](voucher-configuration-design.md#41-shared-native-policy-storage)
elaborates required common policy storage. These three additional candidates are not included
in the historical 51 numbered Vouchers entries; D07 reviews reuse/normalization before DDL.

| Shared candidate | Required responsibility |
|---|---|
| `voucher_configuration_profile` | Company-scoped stable native policy family/code, origin and retirement; reusable across compatible types |
| `voucher_configuration_revision` | Immutable schema/registry-versioned typed settings, applicability dates, author/publisher, lifecycle/version and digest |
| `voucher_configuration_binding` | Exact company/type/class/permitted-location binding, revision and effective window; scoped uniqueness and deterministic restrictive resolution |

Type/class settings reference those policies without creating another writable authority for
master/tax/capability data. Common voucher revisions retain policy/source revision sets,
resolved-config digest and override evidence. Native entry details capture the actual fields
required by the selected profile; no table per kind or arbitrary setting-name/value engine.

## 2. Common document structure: 7 candidates

| # | Table | Purpose | Gate |
|---|---|---|---|
| 9 | `voucher` | Stable document identity, current revision, workflow state and optimistic version | V1 |
| 10 | `voucher_revision` | Immutable dates, party/terms, mode, currency, totals, type revision, calculation hash and header custom fields | V1 |
| 11 | `voucher_line` | Common ordered ACCOUNT/ITEM/CHARGE/ADJUSTMENT lines, stable line key and revision-specific row ID | V1 |
| 12 | `voucher_party` | Party roles and snapshots: customer/supplier, ship-to, principal, worker, carrier and their scoped registration/address evidence | Where roles are required |
| 13 | `voucher_reference` | Typed customer PO, supplier invoice, external job, shipping or other document references | Where applicable |
| 14 | `voucher_link` | Typed source/target revision/line/schedule relationships, quantity/amount claims and operation references for conversion, fulfillment, returns and corrections | V2-V8 |
| 15 | `voucher_attachment` | Evidence-file metadata, access scope, content hash and protected object-storage reference | Supporting evidence |

`voucher_link` stores requested allocations on immutable source/target revisions and append-only
accepted/released/reversed relationships through operations. Current fulfillment is a guarded
projection of accepted links, not a mutable total on an issued order. Only the authoritative
posting/result contract can confirm physical or financial completion. This avoids separate
`sales_order_line`, `purchase_order_line`, `invoice_line` and job-order line families.

## 3. Reusable entry details: 14 candidates

| # | Table | Purpose | Gate |
|---|---|---|---|
| 16 | `voucher_account_allocation` | Manual debit/credit input or commercial-line account distributions, with purpose, amount, currency and party role | V2/V3 |
| 17 | `voucher_item_detail` | ITEM-line identity/SKU/version first; commercial quantity/unit/price/basis, derived discount, goods/service classification and inventory role as capabilities arrive | V1.2 identity for line customization; V3-V8 full behavior |
| 18 | `voucher_inventory_allocation` | Location, owner/custodian, lot/unit, quantity and supported execute/existing-reference/deferred movement intent | V4/V8 |
| 19 | `voucher_charge_detail` | Repeated quantity/line/selected-line/document charge, discount or rounding component; input kind, unit denominator, dependency recipe, account, commercial/tax/cost and return treatments | V3 |
| 20 | `voucher_charge_allocation` | Purpose-tagged commercial, tax-base or cost distribution to eligible lines/receipts; basis, source component identity, partial-return allocation and deterministic residual evidence | V3/V4 |
| 21 | `voucher_tax_context` | Native issuer/recipient registrations, supply direction, place, dates, treatment and evidence for the revision | T0/T1 |
| 22 | `voucher_tax_component` | Repeated entered/calculated tax component value/quantity bases and amounts per supply/event input; rule/rate/unit versions, header-entry normalization, source-return evidence and difference handling | T1 onward |
| 23 | `voucher_withholding_detail` | Typed extension of a withholding component: section, certificate and threshold evidence; no duplicated tax amount | Supported TDS/TCS profiles |
| 24 | `voucher_bill_allocation` | Native reference mode and purpose; scoped requests for new bill, advance use, refund, existing-item settlement or on-account amount; source/result links | V2/V3 |
| 25 | `voucher_tender` | Split cash/bank/UPI/card/cheque amounts, mode-specific dates/references and evidence state | V2/V3 |
| 26 | `voucher_payment_schedule` | Snapshot of agreed money due-date/installment amounts; separate from physical fulfillment schedules; changing master terms never rewrites an issued voucher | Installment/deferred terms |
| 27 | `voucher_measurement` | Native observations/recounts/accepted quantities with item/location/unit, actor, time and evidence; no balance overwrite | V4 counts; later supported measurement workflows |
| 28 | `voucher_process_detail` | BOM/route/version, run/output expectations, process/step and supported variance inputs, linked to common item lines | V8 manufacturing/job work |
| 29 | `voucher_transport_detail` | Dispatch/receipt legs, carrier/vehicle, from/to locations and acknowledged transport facts with movement links | V4/V8 goods movement |

These detail tables are organized by capability, not by voucher kind. A measurement can
support count or process evidence; a process detail can support in-house manufacturing,
repacking or subcontract work. Implement only their supported native profiles, with typed
fields and validation. They are not generic EAV bags. Inventory quantity/value and actual
process genealogy remain Accounting effects. Descriptive custom values stay on header/ITEM
lines under the existing field contract, not in one new value table per type.

Account, charge, tax and tender allocations are not extra sale amounts. Reconcile commercial
totals, account distributions, tax analysis and settlement separately. An applied advance
consumes an existing credit, while a new confirmed tender requests a new money effect. Later
clearance/settlement results attach through operations without mutating issued tender inputs.
One stock movement or collection has one authoritative source identity despite multiple links.

The [component contract](voucher-invoice-calculation.md#42-component-dependencies-storage-and-explanations)
requires native scoped dependency/basis membership and return-source references for repeated
components. D07 must choose normalized shared relations and constraints before migrations;
review any required supporting relation outside these unchanged 51 numbered candidates.
The B28 shared `voucher_fulfillment_terms` relation is one such additional
normalization: it stores typed revision-owned non-posting requisition, quotation
and order terms without creating an order-specific header. `voucher_item_detail`
now has a nullable planned quantity distinct from physical actual and invoice
billed quantities. This does not change the 51 baseline candidate count.
Document allocations retain evidence; authoritative cumulative money/tax/stock claims belong
to Accounting's guarded effect transaction. No purchase/return-specific component tables.

## 4. Workflow and scenario coordination: 6 candidates

| # | Table | Purpose | Gate |
|---|---|---|---|
| 30 | `voucher_approval` | Revision-bound requested/approved/rejected decisions, actor and authority evidence | V1 |
| 31 | `voucher_operation` | Idempotent submit/post/cancel/reverse/convert/fulfill command, source hash and durable outcome | V1 onward |
| 32 | `voucher_operation_transition` | Append-only operation attempts/status transitions, including unknown outcomes and recovery references | Reliable asynchronous workflows |
| 33 | `voucher_posting_reference` | Accounting journal, stock, tax and settlement result IDs tied to the operation and immutable source revision | Actual posted effects |
| 34 | `voucher_scenario` | Named what-if scenario, effective period and non-posting configuration | V6 scenarios |
| 35 | `voucher_scenario_member` | Exact voucher revisions included/excluded in a scenario, with supported effective windows | V6 scenarios |

Approval policy stays in versioned native type/company configuration. Audit remains the
separate action-evidence service; operational transitions support recovery and do not replace
audit events. Reversal is another authorized voucher/operation plus links; it needs no duplicate
`reversal_voucher` header table. Period and current-balance checks execute at Accounting.
Scenario membership affects projections only. It cannot change actual journals, tax, cash or
stock; creating a real transaction from a scenario requires a separately validated voucher.

## 5. Artifacts and statutory submissions: 7 candidates

| # | Table | Purpose | Gate |
|---|---|---|---|
| 36 | `voucher_template` | Identity and scope of supported print/document templates | Configurable printing |
| 37 | `voucher_template_revision` | Immutable approved layout/version and allowed field bindings | Configurable printing |
| 38 | `voucher_artifact` | Generated PDF/export payload metadata, source/template version, hash and protected download reference | Document/export generation |
| 39 | `voucher_statutory_document` | Typed statutory identity and evidence for invoice/challan/IRN/e-way-bill profiles, linked to the same source voucher | Applicable statutory profiles |
| 40 | `voucher_submission` | Immutable submission batch/payload identity and current external status, including multi-voucher returns | T4 and applicable integrations |
| 41 | `voucher_submission_item` | Exact voucher revisions, Accounting tax-event references or frozen report-run lines included in a submission | Multi-document/return submissions |
| 42 | `voucher_submission_attempt` | Requests, acknowledgements, rejection/unknown outcomes and retry/query evidence | Submitted statutory documents/returns |

A statutory-document record is an extension/evidence record, not a second invoice header
or another posting. The same structures handle applicable GST and future state-VAT profiles.
No per-GST-return transactional table or separate VAT invoice family is required. Printed
documents preserve their source revision and template version; attachments are incoming
evidence, artifacts are generated output. Access policies apply to both.

## 6. Optional operations: 9 additional candidates

These are possible supporting features, not newly committed delivery scope. Reuse existing
shared job/integration machinery where appropriate rather than implementing another framework.

| # | Table | Purpose | Activation |
|---|---|---|---|
| 43 | `voucher_payment_intent` | Requested external collection/payment with intended amount, currency and source | Optional V7 gateway/banking execution |
| 44 | `voucher_payment_attempt` | Individual provider attempt, provider ID, idempotency and outcome evidence | Optional V7 |
| 45 | `voucher_reconciliation_batch` | Imported bank/provider statement identity, period, hash and control totals | Optional bank/provider reconciliation |
| 46 | `voucher_reconciliation_line` | Individual imported statement/settlement item and immutable source values | Optional reconciliation |
| 47 | `voucher_reconciliation_match` | Amount-level many-to-many matches to tenders/Accounting effects, with reversal history | Optional reconciliation |
| 48 | `voucher_import_job` | Import source, schema/mapping version, validation state and review/apply checkpoints | Optional bulk entry; implemented with `voucher_import_artifact`, `voucher_import_row` and `voucher_import_effect` ([import plan](voucher-import-plan.md) §6) |
| 49 | `voucher_import_row` | Bounded staged rows, errors, source keys and resulting voucher/operation IDs | Optional bulk entry |
| 50 | `voucher_schedule` | Authorized recurring-draft instructions with pinned type/template and next eligible run | Optional recurring-entry scope |
| 51 | `voucher_schedule_run` | Unique schedule occurrence and resulting draft/operation; retry does not duplicate a voucher | Optional recurring-entry scope |

Reconciliation matches evidence; corrections still require vouchers and Accounting postings.
Schedules normally generate drafts for fresh validation/approval and do not bypass fiscal or
tax checks. Payment attempts and provider callbacks cannot move money twice. Gateway refunds
and chargebacks use typed operation/purpose plus linked Payment/Receipt/correction vouchers;
they do not require a new voucher header family. Payroll/attendance is excluded throughout.

## 7. Reused local infrastructure and customization

These are outside the 51 domain candidates. "Existing pattern" means implemented elsewhere
in the repository, not installed in an existing Vouchers service; that service is still planned.

| Table/pattern | Status and ownership | Use |
|---|---|---|
| `outbox` | Existing shared platform model; instantiate per owning service | Publish committed events/commands without a database/broker dual write |
| `processed_message` | Existing shared platform model | Broker-message deduplication; domain source identity still independently unique |
| `idempotency_key` | Existing shared platform model | Request hash/result and replay protection |
| `custom_field_adoption` | Existing Catalog pattern; planned Vouchers adapter | Accepted definition contracts by company/entity |
| `custom_field_unique_claim` | Existing Catalog pattern | Transactional custom-field uniqueness |
| `custom_field_sequence` | Existing Catalog pattern | Auxiliary custom-field auto-numbers, separate from statutory series |
| `custom_field_value_index` | Existing Catalog pattern | Authorized scalar field filtering/sorting |
| `custom_field_value_member` | Existing Catalog pattern | Multi-select membership index |
| `field_index_state` | Existing Catalog pattern | Active index generation/readiness |
| `field_rebuild_job` | Existing Catalog pattern | Bounded resumable field-index rebuilding |
| `voucher_source_snapshot` | Proposed local projection/evidence envelope; reuse an existing context adapter where suitable | Signed/versioned Identity/Catalog/Accounting inputs used in validation; native indexed replicas can be added per approved contract |
| `voucher_sync_checkpoint` | Proposed consumer-scope checkpoint; reuse shared adapters | Source version, gap detection, freshness and resynchronization; not posting authority |
| `integration_inbox` | Proposed durable integration pattern; consolidate with any selected existing adapter | Verified callback identity, payload hash/protected evidence, processing status and replay protection before acknowledgement |

Identity retains `custom_field_definition`, `field_config` and `field_policy` as master
authority. Do not copy their administration into Vouchers. Local read projections are not
a second definition authority. Required master facts must be local before Accounting's posting
transaction; selecting a broad snapshot envelope never removes native validation or query
requirements. Integration inboxes store only permitted evidence; raw card data is prohibited.

## 8. Existing Accounting tables to reuse

Names verified against current model declarations. These remain in Accounting; they are
not 17 more Vouchers entry tables or proof that their current APIs support all planned flows.

| Table | Current responsibility |
|---|---|
| `journal` | Shared financial posting header and unique source identity |
| `journal_line` | Debit/credit entries, account/party/currency and amount |
| `source_document` | Existing financial source-document record linked to a journal |
| `journal_tax` | Existing tax request/analysis snapshot and summary evidence |
| `open_item` | Receivable/payable/credit facts arising from party postings |
| `allocation` | Settlement between debt and credit open items |
| `opening_batch` | Controlled opening financial balances |
| `document_sequence` | Authoritative posted-number allocation |
| `financial_setup` | Financial setup/freeze and posting controls |
| `fiscal_year` | Accounting years |
| `fiscal_period` | Posting periods and locks |
| `fiscal_status_transition` | Fiscal-state transition evidence |
| `credit_override` | Authorized exception to credit controls |
| `credit_reservation` | Credit exposure reservation |
| `charge_policy` | Existing overdue-charge policy, distinct from invoice freight/packing inputs |
| `charge_assessment` | Existing overdue-charge assessment/posting evidence |
| `charge_tax_snapshot` | Tax evidence for existing assessed overdue charges |

Master dependencies such as `account`, `account_posting_mapping`, `account_tax_profile`,
`account_tax_default`, `party`, `party_role`, `party_tax_registration`, `party_bank_account`,
`payment_term`, `payment_term_line`, `withholding_section`, `withholding_rate`,
`party_withholding_profile` and `withholding_certificate` also stay with Accounting.
See [the Accounting model](accounting-design.md) for the full master inventory. `allocation`
is the actual settlement; `voucher_bill_allocation` is its requested input/result reference.

## 9. Proposed Accounting stock and tax extensions

These are candidate responsibilities for the proposed Accounting effect boundary, still a
V0 decision. They do not currently exist as an implemented stock/tax-event subsystem. Costing,
registration and statutory contract decisions may change the final physical breakdown.

| Table | Purpose |
|---|---|
| `stock_posting` | Atomic stock/value effect batch, source identity and links to associated financial effects |
| `stock_movement` | Append-only signed position legs, transfer/reclassification and source-line links; entered/base units, origin and cost references |
| `stock_balance` | Guarded current quantity by canonical item/owner/custody/location/lot/disposition position; unique even without lot/bin; no editable product balance |
| `stock_reservation` | Authorized availability reservations and release/consumption |
| `stock_lot` | Company/SKU/source-scoped batch identity and date provenance; spans receipts/locations, with no lot-header warehouse balance |
| `stock_unit` | Individual tracked physical unit and current custody state |
| `stock_unit_identifier` | Validated serial/device identifiers and uniqueness claims for a physical unit |
| `stock_cost_layer` | Inventory carrying-value layers or equivalent chosen costing state |
| `stock_cost_allocation` | Allocate consumed/landed/production costs to movements and outputs |
| `stock_value_adjustment` | Value-only corrections, impairment or revaluation tied to source layers and GL |
| `stock_count_scope` | Authoritative count scope/cutoff and concurrent-movement guard |
| `stock_count_snapshot` | Protected book quantity evidence per stock key at the count cutoff |
| `stock_genealogy` | Actual consumed-lot/unit to output-lot/unit relationships |
| `stock_period` | Stock/cost close and backdating/revaluation guards under the chosen policy |
| `tax_event` | Statutory liability/credit/adjustment identity, legal dates and immutable source evidence |
| `tax_event_component` | Component-level base, amount, registration and journal linkage |
| `tax_credit_decision` | Auditable eligible/pending/blocked/reversal/reclaim decisions and amount-level evidence |
| `tax_credit_allocation` | Amounts attributed to credit claims/periods with source-component references |
| `tax_settlement` | Confirmed tax liability offset/settlement operation and source evidence |
| `tax_settlement_allocation` | Liability-component amounts discharged from permitted cash/credit sources |

WIP and goods at a job worker use the same stock owner/custody/value structures. Do not add
another authoritative `job_work_stock_balance` or manufacture customer-owned inventory value.
Document-side count observations live in `voucher_measurement`; the accepted count delta posts
through the common stock effects. Tax extensions must map historical `journal_tax` evidence
and preserve old readers, without recognizing the same liability twice.

### 9.1 Stock history and report refinements outside baseline counts

The [stock recording/reporting design](voucher-stock-recording-reporting-design.md#3-records-to-retain)
requires additional native histories. These may extend existing structures or use the
following candidates; D07 decides final normalization before dependent migrations:

| Accounting candidate | Required behavior |
|---|---|
| `stock_lot_revision` | Audited manufacture/expiry/best-before corrections with effective/recorded versions and immutable evidence |
| `stock_hold`, `stock_hold_event` | Scope, reason, operation block, actor and dated release history; preserve physical quantity and prevent duplicate exclusion |
| `stock_receipt_origin`, `stock_origin_allocation` | Residual receipt/production/opening cohorts and issue/transfer/return links, independent of financial costing |
| `stock_reservation_event`, when selected | Dated claim/release/consume/expiry/reallocation evidence, potentially reusing common operations |

Canonical stock-key uniqueness must handle absent lot/bin without SQL NULL permitting
duplicates. Lot headers do not store current quantity. Unit custody, hold eligibility and
receipt-origin quantities reconcile to movement positions. Reports can add rebuildable stock
facts/day-period summaries, never a table per SKU, group, expiry bucket or voucher type.
The 20 earlier Accounting entries and 51 Vouchers entries remain baseline counts, not the
final schema total. Reusable report-run infrastructure serves these inventory outputs too.

### Stock storage normalization and immutable value facts

The [storage contract](voucher-stock-recording-reporting-design.md#32-storage-grain-relationships-and-constraints)
requires exact quantity/value/source grains and transactional constraints. Additional candidates
are outside baseline counts and may reuse existing allocation/effect structures:

| Owner / candidate | Required capability |
|---|---|
| Accounting: `stock_position` or identity within `stock_balance` | One canonical scoped position, independent of row-existence races; never two quantity authorities |
| Accounting: native movement-unit/source/shipment allocations | Unit membership, partial dispatch/receipt/return claims, bounded consumption and immutable source-line identity |
| Accounting: `stock_value_entry` or equivalent shared value leg | Every inventory/WIP value change, including ordinary receipt/issue/transfer and zero-quantity adjustments; separate from mutable remaining cost state |
| Accounting: `stock_cost_pool`, `stock_cost_pool_event`, if MOVING_AVERAGE selected | Rebuildable pool quantity/value and versioned cost changes with exact residual treatment |
| Reports: movement/value facts and optional stock day/period totals | Source-leg grain, gross movements and date/currency/position/generation keys; no multiplicative origin/unit/cost joins |

Operational stock repair fences owner writers and reconciles positions/units/origins/costs/claims.
Reports reuses common projection generations; its rebuild cannot replace live Accounting state.
No new stock store in Catalog, table per warehouse/SKU/year, or independent editable stock total.

### 9.2 Financial-year refinements outside baseline counts

The [financial-year design](voucher-financial-year-design.md) reuses existing company
`financial_setup`, `fiscal_year`, `fiscal_period`, transition, journal/opening and sequence
tables. Candidate `fiscal_review_run` / `fiscal_review_item` (or shared operation detail)
record readiness scope, period/fence versions, actor, producer snapshots, blocker evidence
and transition outcomes. They are Accounting-owned review evidence, not annual balances.

D05/D07/D12 must specify native posted/statutory numbering policy and assignment fields
where existing `document_sequence` is insufficient: issuer registration/legal category,
rule revision, reset key/date basis, canonical full identity and source/void history. Reuse
or extend shared structures; do not duplicate the Vouchers issue-series authority. These
additional Accounting candidates are outside the 51 numbered Vouchers candidates. No
separate tables per year or annual copies of open items, cost layers or stock receipts.

## 10. Reports and existing external masters

Reports may need these four planned reusable working-report structures; they are not books:

| Table | Purpose |
|---|---|
| `tax_return_run` | Rebuildable report run plus frozen approved version, registration/period/schema and control totals |
| `tax_return_line` | Source-event allocations and return-field totals with drill-down evidence |
| `tax_reconciliation_run` | Imported statutory statement identity and matched source snapshot/checkpoint |
| `tax_reconciliation_difference` | Missing/mismatched/duplicate items and review evidence; adjustments go back through Accounting |

The exact report engine may generalize these names. Vouchers owns submission/acknowledgement
records for a frozen run, Accounting owns the tax effect, and Reports never silently edits
the journal or claims credit. Broader day-book and stock reports can read owner exports or
rebuildable projections; this list does not prescribe a permanent table per report.

The [financial-reporting design](voucher-posting-reporting-design.md#2-authority-and-records)
adds the following candidates **outside the baseline counts**, to normalize under D07/D11:

| Owner / candidate | Purpose |
|---|---|
| Accounting: `account_statement_mapping` or native metadata extension | Versioned semantic classification, contra/maturity treatment and statement coverage alongside existing heads/groups/purposes |
| Reports: `report_definition`, `report_definition_revision` | Supported calculation kinds and pinned formula/layout versions |
| Reports: `report_run`, `report_artifact` | Period/scope, source manifests, frozen output and protected artifact/hash |
| Reports: `report_checkpoint`, `report_reconciliation` | Committed owner cutoffs, ingestion barriers and source/TB/subledger/statement checks |
| Accounting: `journal_line_source_allocation` or shared effect distribution | Native source revision/line/component contributions to journal lines; reuse the shared distribution capability |
| Reports: `report_ledger_fact` or shared owner-fact projection | Required one-line-grain read capability, scoped source/hash/order and monetary facts; no editable account balances |
| Reports: optional `report_account_day_total`, `report_account_period_total` | Gross debit/credit movement and line counts at explicit account/date/basis/currency/generation grain; no overlapping totals |
| Reports: `report_projection_generation` or extended `report_checkpoint` | Snapshot/catch-up, schema/definition revision, shadow-build verification, active cutover and pinned-reader generation |

The [account recording design](voucher-account-recording-design.md) specifies native grain,
uniqueness, atomic updates, filtered-query limits, late-entry invalidation and rebuild rules.
These candidates are outside baseline counts; D07 decides shared structures versus new tables.
No table per account/year/register or editable current/opening amount on an account master.

Tax return/reconciliation runs can specialize the common run engine; this is not a direction
to create two copies. Existing opening journals remain the financial authority; any future
`account_opening_balance` is a derived carry cache, never an additional opening effect.
Exports require full line/allocation lineage and historical classifications. Final DDL and
the normalized total are phase contracts, not the sum of every candidate name in this note.

Identity supplies companies, registrations, banks, users, roles and field definitions.
Catalog supplies item/family/unit/warehouse, attributes, prices, tax rules/rates and future
BOM/route definitions. Country/currency/state and other shared reference data reuse existing
platform materialization. Audit and Notification keep their existing delivery/evidence stores.
None becomes a duplicate editable master in Vouchers. The complete existing master/service
schemas are linked from [architecture](tech-stack.md) and [Catalog inventory](catalog-table-inventory.md).

## 11. Delivery and count interpretation

Use [V0-V9](vouchers-plan.md#5-delivery-phases-and-acceptance-gates), not one migration batch:
configuration/core first; then accounts/settlements; invoice/charge/tax; stock; orders and
job work. Required statutory/reporting structures arrive with the transaction phases that
need them; explicitly selected optional operations have separate prerequisites. Follow the
[reviewed batch tracker](voucher-delivery-tracker.md#3-ordered-batch-register), including early
stock-period/valuation guards and the incremental Reports slices.
Every phase carries matching schemas, constraints, APIs, clients, authorization and tests.

Inventory counts: **51 Vouchers domain candidates = 42 entry/workflow + 9 optional**, **13
infrastructure/customization patterns**, **17 existing Accounting support tables**, **20
proposed Accounting extensions**, and **4 initial tax-report candidates**. These baseline counts are
review aids, not a database sizing estimate: existing masters/reference data, approved local
replicas, migrations and future statutory rule packs are deliberately not counted in them.
No claim is made that this is the number of new tables required for the first release.
The financial-reporting candidates above are additional refinements pending normalization.

The later [Tally functional review](tally-voucher-functional-review.md#4-gaps-and-refinements-for-our-common-model)
identifies additional normalization candidates: native dimension allocations, tender-to-account
distribution, shared instrument lifecycle, cheque-book/leaf controls and cash denominations.
They are outside the 51-table baseline pending capability selection and owner/schema review.
Opening bank reconciliation and statement-created vouchers may extend existing candidates.
The baseline is not a closed list of every future capability; preserve shared structures
and single effect ownership when incorporating the selected refinements.

The [settlement review](tally-settlement-functional-review.md) further refines bill-allocation
fields, late allocation operations, refund/return-credit links and tax-advance evidence. These
reuse the existing shared candidates and Accounting open-item/allocation authority; no separate
`advance_voucher`, `bill_adjustment_voucher` or mutable advance-balance table is proposed.

The [invoice calculation contract](voucher-invoice-calculation.md) refines the same shared
details for accounts-only/item Sales and Purchase. Discounts have one component authority;
commercial, taxable-base and cost allocations are distinct views of that source. Actual versus
billed quantities, inclusive price basis and clearing/settlement evidence are native fields,
not custom attributes or reasons to add per-kind tables. The baseline count remains unchanged.

The [order/fulfillment review](tally-order-fulfillment-review.md#6-shared-storage-and-api-refinements)
adds `voucher_fulfillment_schedule` as another shared capability candidate outside that baseline,
pending V0 normalization. It stores planned quantity/date/destination slices for indents, orders
and deferred fulfillment; `voucher_payment_schedule` stores money installments. Approval,
conversion claims, closure and movement/billing provenance refine the existing revision/link/
operation structures. No indent-, quotation-, order- or challan-specific document tables are added.

## Decision log

- 2026-10-10: Stock reporting review refined position/movement/lot fields and added lot-date,
  hold, receipt-origin and selected reservation histories outside baseline counts. They
  support current/group/expiry/age reporting; exact normalized DDL remains D07.

- 2026-10-10: Added financial-statement mapping and shared report definition/run/artifact/
  checkpoint/reconciliation candidates outside baseline counts. Required common infrastructure
  reuse with tax runs, immutable source lineage and no second opening or editable balance.

- 2026-10-10: Review moved minimal ITEM detail to V1.2 before line customization and corrected
  delivery text that incorrectly placed statutory/reporting work after job work. Exact DDL
  remains governed by the per-batch manifest; baseline candidate counts remain unchanged.
- 2026-10-10: Connected the candidate inventory to the detailed implementation roadmap's
  dependency groups and D07 migration manifest. Baseline counts remain planning references;
  later common schedule/dimension/instrument refinements require explicit normalization.
- 2026-10-10: Indent/order/challan review refined source-link claims and added the shared
  fulfillment-schedule candidate outside the 51-table baseline pending V0 normalization.
  Delivery quantities/dates are distinct from monetary installment schedules; common base
  tables still serve every kind/profile.
- 2026-10-10: Sales/Purchase research refined item quantities/price basis and canonical
  discount/charge components with purpose-tagged distributions. Reused existing candidates;
  additional fields and contracts do not imply a new table family or implemented calculator.
- 2026-10-10: Payment/Receipt/advance review refined shared allocation responsibilities without
  changing the baseline count. Money, bill application and statutory adjustments retain distinct
  evidence while authoritative balances stay in Accounting.
- 2026-10-10: Linked the subsequent Journal/Stock Journal/banking functional review and its
  additional shared capability candidates. Kept existing counts explicit as a baseline rather
  than claiming unreviewed banking and accounting-dimension structures are already included.
- 2026-10-10: User requested all possible tables supporting voucher entries. Expanded the
  shared-model sketch into an owner-scoped candidate inventory with entry/workflow, optional,
  infrastructure, existing Accounting, proposed stock/tax and Reports groups. Preserved common
  base tables across kinds; numbering/settlement/stock/tax each retain one effect authority.
  Counts describe planning candidates, not implemented tables or newly approved optional scope.

### Financial-year planning decision - 2026-10-10

Recorded fiscal readiness and statutory-numbering extension candidates separately from
the stable numbered Vouchers inventory. Final physical schemas remain D07/D12 decisions.

### Account-recording review - 2026-10-10

Account review refined required line-grain reads, native source allocations and optional
day/period summaries with generation controls. Shared engines/capabilities may absorb these
candidates; the 51 numbered Vouchers candidates remain unchanged.

### Stock capture/storage review - 2026-10-10

Refined native stock storage/cardinality and immutable value/pool history candidates
outside the unchanged 20 Accounting and 51 Vouchers baseline lists. D07 controls reuse/DDL;
owner repair and Reports rebuild have distinct authority and concurrency requirements.

### Purchase component review - 2026-10-10

Refined shared native component scopes, dependency/basis evidence, header-tax allocation
and source-linked purchase returns under the [invoice calculation contract](voucher-invoice-calculation.md).
The 51 numbered Vouchers candidates remain unchanged; D07 reviews necessary shared relations,
and Accounting retains authoritative financial/tax/stock effects. CAL01-CAL16 remain planned.

### Sales commercial-configuration review - 2026-10-10

The [commercial configuration contract](voucher-commercial-configuration.md) now requires native company Sales/Purchase
policy revisions, restrictive type/class bindings and disjoint paid/reward source evidence.
D07 finalizes shared policy/benefit relations; no per-type table or custom-field posting logic.
CAL17-CAL28 remain future implementation checks.

### All-voucher configuration review - 2026-10-10

Made common policy profile/revision/binding candidates explicit outside the unchanged
51-entry baseline. Common source/configuration snapshots and typed reference constraints
remain D07 requirements, with no per-voucher-type table family.

### Phase 5 shared terms normalization - 2026-10-11

B28 selected one shared `voucher_fulfillment_terms` relation outside the numbered
baseline for native requisition/quote/order terms. The same common item detail
gained nullable planned quantity. The 51 candidate count and one-header design
remain unchanged; B29 schedules and claims are not inferred from this capture.
