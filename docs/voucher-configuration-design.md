# Voucher configuration: profiles, capture and execution

**Reviewed:** 2026-10-11. **Status:** Required implementation design. The recorded B01-B14
baseline and bounded Sales configuration subset exist; the remaining typed configuration
controls are planned and company activation is separate. **Scope:** All 22 planned
non-payroll kinds and their supported profiles, including quotations, requisitions, challans,
manufacturing and job work.
**Read with:** [Architecture](vouchers-plan.md), [common data model](voucher-data-model.md),
[type extensibility](voucher-extensibility.md), [commercial controls](voucher-commercial-configuration.md),
[remaining-type implementation plan](voucher-remaining-configuration-plan.md),
[financial years](voucher-financial-year-design.md), [stock recording](voucher-stock-recording-reporting-design.md)
and [implementation tracker](voucher-delivery-tracker.md).

This is the common configuration contract. The commercial document remains the detailed
Sales/Purchase discount/tax/free/deal policy; it is one family of this framework, not a second
configuration engine. Descriptive custom fields, account/product masters, native settings,
entry preferences and executable posting rules have different authority.

## 1. TallyPrime findings and applicability

Reviewed official documentation, not live Tally screens or its private database. Releases,
country features and enabled masters affect the available options. The sources establish
product features, not that our proposed schema, approval controls or execution model exists
in Tally. We retain the agreed 22-kind catalogue; differing counts in product/help pages do
not add payroll or change that scope.

| Area | Documented configuration/capability | Primary source |
|---|---|---|
| Type identity and behavior | Derived types, activation, dates, optional entry, narration/default allocations, purchase-cost tracking and type-dependent options | [Voucher types](https://help.tallysolutions.com/voucher-types-tally/) |
| Numbering | Automatic/manual/override/concurrent entry, multiple series, prefix/suffix/restarts and selectable insertion/deletion behavior | [Numbering methods](https://help.tallysolutions.com/use-voucher-numbering-methods/) |
| Effective date | A separate date can drive due-date/interest and aging calculations | [Accounting FAQ](https://help.tallysolutions.com/accounting-faq/) |
| Classes | Party-group restrictions, default ledger distributions, invoice charges/taxes, POS tenders and transfer classes | [Accounting entry/classes](https://help.tallysolutions.com/accounting-entry-tally/), [type classes](https://help.tallysolutions.com/voucher-types-tally/) |
| Payment/Receipt | Single/debit-credit entry, ledger-wise bank allocations, mode/instrument data, bank status/reconciliation details and bill selection before amounts | [Payments and receipts](https://help.tallysolutions.com/knowledgebase/payments-and-receipts-tally/) |
| Outstanding tracking | Company/party tracking choices and reference-purpose selection distinguish new dues, settlement and on-account amounts | [Outstanding methods](https://help.tallysolutions.com/receivables-payables-tracking-methods/) |
| Journal dimensions | Compound adjustments, cash/bank usage and supported currency/cost-centre allocation; these need applicable entry/master setup | [Accounting entry](https://help.tallysolutions.com/accounting-entry-tally/), [cost centres](https://help.tallysolutions.com/cost-centre-or-profit-centre-tally/), [currencies](https://help.tallysolutions.com/multi-currency-accounting-made-simple-with-tallyprime/) |
| Sales/Purchase | Invoice modes, price levels, discounts/charges/free quantities, tax and classes; reviewed separately | [Commercial research](voucher-commercial-configuration.md#1-tallyprime-configuration-findings) |
| Orders and quotations | Per-item order references, due schedules, receipt/delivery tracking and pre-closure; optional Sales Order can print as quotation | [Sales orders](https://help.tallysolutions.com/sales-order-tally/), [purchase orders](https://help.tallysolutions.com/purchase-order-tally/) |
| Inventory notes/counts | Location/batch-dependent entry, tracking of deliveries/receipts/rejections, physical-count dates/quantities and entry-display preferences | [Inventory entries](https://help.tallysolutions.com/inventory-entry-tally/) |
| Transfers and job costing | Stock Journal classes distinguish location transfer from consumption, with source/destination and project allocation | [Job costing](https://help.tallysolutions.com/job-costing-tally/) |
| Manufacturing/requisition | BOM/output/cost entry and an optional manufacturing Stock Journal used as a purchase requisition | [Manufacturing](https://help.tallysolutions.com/manage-inventory-in-manufacturing-tally/) |
| Job work | Company job-order feature, Material In/Out role setup and optional consumption on finished-goods receipt | [Job-work setup](https://help.tallysolutions.com/job-work-setup/), [consumption prerequisites](https://help.tallysolutions.com/inventory-and-manufacturing-faq/) |
| Scenarios | Memo, optional and reversing-journal entries participate in selected scenario reports | [Scenarios](https://help.tallysolutions.com/scenarios-tally/) |
| Security | Role/activity controls, report access, permitted backdating window and cutoff | [User security](https://help.tallysolutions.com/tally-prime/tally-company/manage-users-in-tallyprime/) |
| Output and follow-up | Type-dependent print templates/titles/bank details/terms, print-after-save and sharing/payment-request options | [Voucher output options](https://help.tallysolutions.com/voucher-types-tally/) |

We deliberately preserve our stronger existing invariants: issued identifiers are not
renumbered/recycled, posted facts are corrected with linked operations, and bank reconciliation
cannot be silently deleted by changing an entry preference. Tally's optional/scheduled modes
inspire supported workflows; a checkbox cannot erase an actual posting or bypass a period lock.
An effective date for credit terms is not automatically a GL, stock or statutory effect date.
Interest accrual automation, external payment execution, messaging channels and unsupported
localizations do not become implemented merely because a setting can be described.

## 2. Native settings registry and resolution

Keep a code-defined, versioned registry of supported kind/profile/mode and setting families.
Each setting descriptor declares its key, owner, typed schema/version, permitted values/ranges,
kind/profile applicability, required capabilities, dependencies/incompatibilities, stage of
validation, default/requiredness/editability, override/approval rule, merge semantics,
sensitivity, mutability-after-use and implementation/readiness requirement. No administrator
can add executable setting keys, formulas, SQL or arbitrary condition expressions at runtime.
Company-created types select implemented behavior and registered custom attributes without DDL.

Resolve implemented profile -> enabled company capabilities -> applicable company policy
families -> type revision -> permitted class defaults, then validate master/context restrictions
and live actor authority. Restrictions intersect; a deny wins. Defaults can specialize only
within the resulting permitted set. Independent settings do not use a universal last-write-wins
merge: the descriptor chooses intersection, minimum/maximum bound, requiredness tightening or
an explicit permitted default. Reject contradictory requirements, cycles, ambiguous bindings,
cross-company references and overlapping effective bindings for the same scope/priority.

Resolve business policies using their declared business-date basis and retain the selected
revisions. Live security, stop controls and statutory/period readiness are rechecked at action
time; backdating must not select a permissive obsolete access policy. Later changes cannot
rewrite historical documents. Location-specific restrictions, where supported, require explicit
scoped bindings; absent location cannot fall back to a broader permission. Product/account
defaults remain with Catalog/Accounting and are captured from versioned owner evidence.

### 2.1 Configuration families and required fields

These are shared native responsibilities, not one table per row. The registry must expose
which fields are absent, optional, required, defaulted or read-only in each profile/stage.

| Family | Required controls and evidence |
|---|---|
| Identity/lifecycle | Base kind/profile, company code/name/abbreviation, activation/retirement, template origin, allowed modes; used-kind/ownership changes require a new type |
| Numbering | Allocator/series references, issuance trigger, permitted method/override, scope/year, format/restart revision and supplier-reference rules; stable internal ID always exists |
| Dates and periods | Entry/business/posting/stock/statutory dates, credit-terms basis, future scheduling and authorized backdate window/cutoff; profile-specific fiscal checks |
| Entry/sections | Account/item/mixed or simplified/debit-credit mode, stage-specific section/cardinality rules, header/line narration and extra descriptions |
| Parties/accounts | Allowed native roles/group ancestry, excluded groups/accounts, active/postable/currency constraints, default distributions, common/per-item mappings and override authority |
| Bills/advances | Required bill tracking, allowed reference purposes, due-term defaults, preselection/auto-match policy, partial allocation/on-account limits and advance purpose; exact chosen targets persist |
| Money/banking | Allowed tenders, default cash/bank/clearing accounts, split limits, mode-specific reference/date requirements, cheque/PDC recognition, fees/refunds and approval; bank processing status is separate evidence |
| Dimensions/FX | Required cost-centre/project distributions, permissible categories/currencies, rate source/date and override limits; dimension totals and source/base amounts reconcile |
| Commercial/tax | References to Sales/Purchase commercial policy, charge/discount/deal and tax profiles; mandatory tax or product guards cannot be disabled here |
| Inventory | Allowed movement operations, execute/reference/defer modes, source/destination locations, owner/custodian roles, units/tracking, negative-stock/expiry/hold/count policy references and value readiness |
| Fulfillment/returns | Required/optional source orders/notes/invoices, line/schedule links, tolerances, partial/split/consolidated execution, short-close/reopen authority, original return caps and reward entitlements; separately enabled reservation actions |
| Counts/corrections | Count scope/cutoff, observation completeness, blind/recount/approval mode if supported, variance tolerance/account mapping and allowed correction methods |
| Job/process | Principal/worker direction, permitted materials/outputs, BOM/process revision, automatic/manual consumption, consumption location, yield/scrap/cost mapping and statutory evidence |
| Scenario/scheduling | Permitted optional/memo/scenario use, scenario validity and inclusion; separately authorized scheduling and actualization with fresh validation |
| Approval/evidence | Actor actions, maker/checker rules, thresholds/reasons/attachments, override authority, submit/approve/issue/post validation stages and source compatibility |
| Artifacts/follow-up | Pinned templates, titles/declarations/terms, copies/locale/print bank, delivery preference and explicit trigger; provider/payment-request capabilities stay separately gated |

Do not duplicate master choices as unconstrained voucher flags. For example, a voucher can
restrict a supported stock profile, but cannot override a product's serial requirement or
enable negative-stock execution beyond the accepted D03 policy. Company capability first-use
locks remain authoritative. Disabling new entry leaves authorized historical correction and
report access available under their separate permissions.

## 3. Configuration and capture matrix for every base kind

Each row is our required contract informed by the sources, not a claim that Tally has these
exact fields. All use common revisions/lines/details; each runtime type binds one compatible
profile, settings revision set and permitted sections. Account selection uses semantic role
and native hierarchy IDs, never comparisons with display names such as Sundry Debtors.

| Kind | Configurable choices | Native capture and execution requirements |
|---|---|---|
| `CONTRA` | Simplified/debit-credit mode, permitted own cash/bank accounts, transfer modes and reference/approval rules | Paired source/destination money legs, amount/currency/rate and instrument facts; ordinary same-currency transfer does not create party bills, income or stock; fees/FX require supported purposes |
| `PAYMENT` | Money-account default, expense/supplier/advance/refund purpose, bill preselection/matching, tenders and settlement adjustments | Party/role, source/target bills, dated allocations, bank/instrument and fee/withholding/FX details; one recognized payment effect |
| `RECEIPT` | Cash/bank/clearing defaults, customer/income/advance/refund purpose, split modes and allowed discounts/write-offs | Payer/role, tenders, bill/advance allocations and recognized versus pending status; bank receipt need not equal invoice debt reduction |
| `JOURNAL` | Compound accounts, dimensions/currencies, cash/bank eligibility, bill tracking and supported tax/valuation adjustment purposes | Balanced native allocations and source links; cash/bank requires the same instrument evidence; ordinary Journal cannot create stock from an enabled checkbox |
| `SALES` | Account/item/mixed, cash/credit/POS/export profiles, commercial rules, settlement, tax and movement mode | Resolved accounts/party, component and paid/reward allocations, tax/stock/tender evidence; referenced dispatch and payments are not repeated |
| `PURCHASE` | Account/item/mixed, supplier-reference rules, commercial terms, recoverability/landed cost and receipt linkage | Declared versus calculated invoice facts, component allocations, supplier open item and receipt/cost sources; external freight retains its own liability |
| `CREDIT_NOTE` | Supported adjustment/return purpose, source requirements, amount-only versus stock-linked mode and reason/approval | Original revision/line/component claims, statutory identity and independent refund/movement references; caps and tax purpose govern actual effects |
| `DEBIT_NOTE` | Supported purchase-return/value-adjustment purpose, source/party rules, financial versus physical scope | Commercial advice versus supplier statutory note evidence, original allocations and settlement/cost bridges; naming a type does not decide tax direction |
| `DELIVERY_NOTE` | Delivery Challan profile, linked/direct dispatch, location/transport/party details and invoice/deferred fulfillment policy | Actual dispatch/tracking, owner/custody, source line/schedule and statutory transport evidence; printing does not issue stock; dispatch need not recognize a sale |
| `RECEIPT_NOTE` | Linked/direct receipt, receiving location, accepted/rejected quantities, supplier/order/transport evidence | Exact receipt/origin/tracking and source claims, applicable unbilled-stock clearing; a later purchase invoice references this movement |
| `REJECTIONS_IN` | Required original dispatch, eligible return reasons/destinations and inspection/hold policy | Source-capped incoming quantities, unit/origin and condition; financial credit is a linked independent action |
| `REJECTIONS_OUT` | Required receipt origin, supplier return reason, source location and dispatch evidence | Source-capped outgoing quantities and cost lineage; purchase debit advice/tax adjustment does not follow automatically from physical return |
| `STOCK_JOURNAL` | Explicit transfer, consumption, transformation, loss or value-adjustment profiles; compatible classes and cost rules | Typed source/destination/consumption/output legs and required source/cost/BOM facts; immediate transfer conserves quantity/value, other profiles use their own invariants |
| `PHYSICAL_STOCK` | Count scope/cutoff, observation/recount/approval controls and variance policy | Item/location/owner/lot/unit observations, observed quantity, protected comparison and approved delta; omitted observation is not zero and balances are never overwritten |
| `MATERIAL_IN` | Principal versus worker role; raw/finished/scrap receipt; order-required/direct mode; explicit separate or combined consumption | Owner/custodian/job/source-challan, quantities, locations and process references; combined consumption claims exact component stock once and records genealogy/cost |
| `MATERIAL_OUT` | Principal versus worker role; component dispatch or output return; order/source/transport rules and zero commercial-value display | Owned-at-worker versus third-party-held stock, exact lots/units and original dispatch history; zero displayed amount does not erase cost/ownership |
| `SALES_ORDER` | Order versus quotation profile, schedules, pricing estimates, source requirements and short-close rules | Customer, line/schedule quantities, due dates, prices/terms and native commitments for actual orders; quotation has no commitment, stock or ledger effects |
| `PURCHASE_ORDER` | Supplier/order terms, requisition/source policy, per-line references, due schedules and pre-closure | Exact ordered/fulfilled/closed quantities with reasons; no payable or on-hand stock until separately authorized execution |
| `JOB_WORK_IN_ORDER` | Worker's accepted-work profile, principal/material owner, expected receipts/outputs and process defaults | Job commitments, source material/output specifications and dates; receipt/consumption/service billing remain separately executed |
| `JOB_WORK_OUT_ORDER` | Principal's subcontract profile, job worker, BOM/material issue/output expectations and due terms | Owned material commitments, custody destinations, expected yield/scrap and processing terms; issuing the order is not a material issue or payment |
| `MEMORANDUM` | Allowed provisional purpose, parties/accounts/items as evidence, follow-up and conversion requirements | Scenario/provisional data and linked actualization provenance only; no ledger, stock, tax, settlement or reservation effects |
| `REVERSING_JOURNAL` | Scenario membership, validity window, permitted provisional account distributions | Scenario-only time-bounded facts; neither the end date nor a setting executes an actual financial reversal |

### 3.1 Required profiles and cross-kind controls

Quotation remains a SALES_ORDER profile; pro forma is a non-posting SALES profile; plain
procurement/internal-issue requisition is a non-posting STOCK_JOURNAL profile. Their lifecycle,
sections and artifacts must be explicitly discoverable. A quotation title on a real order
does not remove its commitment. A manufacturing requisition cannot consume stock.
Manufacturing is an implemented STOCK_JOURNAL transformation profile; its BOM assistance is
not the definition of every requisition. These distinctions survive type cloning/conversion.
Conditional B31 reservation configuration authorizes only separately executed reservation
commands; accepting a quote/order never silently changes on-hand, held quantity or credit use.

Optional mode, where supported, creates provisional data with no actual effects. Post-dated
mode retains eligible-action dates and scheduling evidence; actualization must use current
authority, period, source and availability checks. Drafts may be changed with optimistic
versioning; issued evidence is immutable. Source-linked conversion creates an explicit actual
document/operation and never silently flips an already-posted record to optional.

Journal cash/bank, interest/FX adjustments and extra-cost attribution require their implemented
native purpose/mappings. Do not copy Tally's broad additional-cost checkbox as authority for any
kind to change valuation. Bill tracking presentation may be switched, but historical open
items and allocations persist; changing party tracking mode needs an owner-reviewed adoption
plan. A new-reference/on-account UI choice does not erase an advance's business/tax purpose.

Job-work role and combined consumption are particularly important: the same Material In
label may receive customer-owned raw material or company-owned finished goods. Freeze that
role on the profile and entry. Automatic consumption must resolve the consumption location,
source lots/units, actual quantities, BOM deviations and selected costing before execution.
If the source was already consumed, reference that execution; if it is not ready, block
combined execution. Separate consumption and receipt cannot both decrement the same stock.
No payroll work is included in process costs or configuration.

## 4. Central storage and captured configuration evidence

### 4.1 Shared native policy storage

Refine the existing candidate inventory under D07; do not create one settings/entry table per
kind or one arbitrary name/value table for executable business rules. The following reusable
responsibilities make company-wide policies concrete without duplicating type settings.

| Shared structure | Required fields/constraints and ownership |
|---|---|
| Candidate `voucher_configuration_profile` | Vouchers company-scoped stable ID/code/family, origin and retirement; reusable native bundle for the supported families, not a new voucher kind |
| Candidate `voucher_configuration_revision` | Profile ID, monotonic revision, schema/registry version, typed payload/children, valid-from/to business-date basis, lifecycle, author/publisher, expected version and content digest; published content immutable |
| Candidate `voucher_configuration_binding` | Scoped company default or permitted type/class/location binding, family, exact target revision, applicability window, bounded priority and provenance; unique compatible active binding, no cross-company or circular resolution |
| Existing `voucher_type_revision`, `voucher_type_section`, `voucher_class` | Type identity/mode/direct restrictions and compatible class defaults; reference reusable policy revisions, with one declared owner for each setting rather than duplicated writable values |
| Common `voucher_revision` evidence | Type/class and policy revision references, registry/resolver versions, normalized effective-config digest, source-master generations, input digest and approved override/approval references |
| Reusable native transaction details | Persist entered and resolved party/account/quantity/dimension/component/bill/instrument/source/process facts separately from defaults; local scoped FKs and cross-owner evidence IDs |
| Existing operations/approval/artifacts/outbox | Validation stage and resolved digest, operation attempts/outcomes, effect IDs, pinned artifact/template identity and independently retryable follow-up intent/status |

The three configuration candidates elaborate the earlier commercial-policy storage requirement;
they are additional shared candidates outside the historical 51 numbered Vouchers entries.
D07 may reuse/merge a responsibility after proving the same constraints. Native reference sets,
allocations and searchable bindings use normalized typed relations as needed. A bounded payload
may hold code-schema-validated scalar settings; it is not free-form EAV/custom-attribute logic.
No cross-service SQL/FKs, credentials in policy payloads or configuration-derived shadow balances.

Policy configuration belongs to Vouchers; master, tax, numbering/effect, capability and access
authorities keep their existing owners. Accounting receives versioned verified configuration
evidence, validates executable effects and returns its result. Vouchers cannot authorize an
unsupported journal/stock/tax outcome by placing it in a signed command.

### 4.2 Capture at entry and execution

At preparation, resolve context and retain which values were entered, defaulted or overridden.
Snapshot default master facts actually used (party addresses/terms, account mappings, bank
details for print, unit conversions, process/class and tax rules) with provenance. Do not rely
on today's live master for a historical invoice or register. Sensitive source values remain
subject to read policy even when retained as immutable evidence.

At each required stage, validate typed fields and section cardinalities against the same
registry/effective configuration. A bank mode change invalidates incompatible instrument
details rather than quietly reusing a cheque number; a type/profile/class change revalidates
or explicitly maps affected fields and invalidates approval. Do not silently drop forbidden
amounts or transform an unresolved source into an on-account posting. Draft-incomplete state
does not excuse cross-company references or incorrectly typed facts.

At approval/issue/post, pin the accepted revision/digests and recheck live access, first-use,
stop/period and owner-readiness fences. Retried operations bind the same input/config digest
or fail with a conflict; posting with stale/unknown policy versions fails closed. Configuration
publication acknowledgment is not proof of the transactional outcome. A report uses captured
facts and committed effect IDs, never recalculates old vouchers with a new default.

## 5. API, administration and lifecycle

Extend the already planned type/field-set/common-voucher surfaces, with these proposed native
configuration operations. These are design paths, not endpoints claimed to exist today.

| Proposed surface | Contract |
|---|---|
| `GET /voucher-capabilities` | Scoped supported kind/profile/mode/setting registry, schema versions, implementation/readiness and dependency reasons; payroll absent |
| `/voucher-configurations`, `/{id}/revisions` | Company policy bundles and immutable revision history; expected-version draft writes and bounded typed payloads |
| `POST /voucher-configurations/{id}/validate`, `/publish`, `/retire` | Validation/impact review, explicit revision/effective window, idempotency and publication/readiness status; no arbitrary live mutation |
| `/voucher-types/{id}/configuration-bindings` | Bind exact supported policy revisions within the type's scope and permitted company envelope |
| `GET /voucher-types/{id}/effective-configuration` | Contextual settings, origin/constraints, stage requirements, allowed overrides and readiness digest; does not claim a stock reservation or posting approval |
| Existing type/voucher/item `field-set` and common preview | Same effective context/digest controls forms, native input validation, masked explanations and calculated effects |
| Existing operation/history routes | Capture selected revisions, approved exceptions, latest readiness and immutable result/follow-up references |

Scope policy CRUD/validate/publish/retire separately from using a voucher and applying an
override. Reuse Identity roles/actions/field denies; a type creator does not gain posting
authority. Generated clients, bulk import and server jobs use these same contracts. Reject
unknown settings, unsupported enum variants and structurally valid but incompatible combinations.
Use bounded resolver depth/payload/reference counts and indexed scope/family/effective lookups.

Publication requires a complete validated dependency digest and consumer acknowledgment for
new executable settings. Impact preview lists affected types, unposted drafts, approvals,
scheduled actions and source obligations; adoption must not silently clear their data. Apply
future revisions explicitly, block illegal after-use changes and retain old snapshots.
Stop/retirement prevents new use under the defined policy while permitting separately
authorized historical returns/reversals. Publish-versus-post/import/schedule races require
owner fencing. Prevent an old offline client from using an obsolete policy to post later.

Numbering retains the existing split: Vouchers issues its authorized document numbers;
Accounting allocates internal/statutory identifiers under D05/D12. Manual/override input is
accepted only where the profile/allocator supports it and uniqueness is enforced atomically.
Unnumbered display is allowed only for profiles without a number requirement; stable IDs remain.
Fiscal restart, scope and prefix changes never renumber history or reuse voided issued numbers.

Output defaults pin the artifact/template and required legal content. Printing is not dispatch,
posting or payment. Sharing/notification and payment-link generation are explicit authorized
follow-up operations with delivery/idempotency evidence; a successful posting is not repeated
when printing, notification or a provider call fails. Bank credentials remain in the provider
configuration owner. D10 and existing Notification readiness gate actual integrations; this
planning review sends no messages or payment requests.

## 6. Delivery slices and acceptance

Retain the 45 parent batches and separate activation checkpoints. B02/B03 finalize registry,
scope/merge and snapshot contracts; B05/B06 implement shared profiles/bindings and type/class
administration; B07/B08 implement stage enforcement, artifact and numbering controls. Account/
bank settings are exercised by B10-B13, commercial settings by B15-B19, stock by B20-B27,
orders/general/scenarios by B28-B36, and jobs/processes by B37-B41. B42-B44 remain optional
provider/reconciliation/cheque slices. Each release verifies its relevant settings before
activation; B45 is the combined rehearsal, not the first configuration test.

| Check | Required implementation evidence | Batches |
|---|---|---|
| VCF01 | All 22 base kinds and required quotation/pro-forma/requisition/challan/manufacturing profiles have explicit settings, capture and effects; payroll absent | B02/B06 |
| VCF02 | Registry rejects unknown keys, unsupported profiles, schema versions, malformed values and illegal capability combinations | B05/B06 |
| VCF03 | Company/type/class/location restrictions and default precedence resolve deterministically; contradictory required/denied fields fail; no permission widening | B06/B08 |
| VCF04 | Company isolation, native role/group selection, protected lookups and cross-company policy/master/reference substitution checks | B06/B10 |
| VCF05 | Expected-version publishing, immutable policy/class history, effective windows, duplicate/ambiguous bindings and resolver-cycle bounds | B05/B06 |
| VCF06 | Concurrent/manual numbering, restart and issue-versus-post identity preserve uniqueness and no reuse/renumber; statutory profiles reject missing required numbers | B07/B08/B19 |
| VCF07 | Credit-terms effective date differs safely from GL/stock/statutory dates; backdate/cutoff/future rules recheck live authority and periods | B07/B10/B21/B32 |
| VCF08 | Simplified versus debit/credit entry produces identical promised account effects; forbidden party/stock/tax sections fail for the selected profile | B10/B13 |
| VCF09 | Bill preselection/auto-match resolves explicit targets once, requires current entitlement and never changes historical tracking or due terms silently | B11/B13 |
| VCF10 | Tender/instrument defaults and changes, split amounts, PDC recognition and source-reference requirements cannot imply bank confirmation | B12/B13 |
| VCF11 | Journal cash/bank/dimension/FX/tax-purpose restrictions preserve balanced postings and prevent stock or subledger bypass | B10/B16 |
| VCF12 | Sales/Purchase controls and original-note corrections exercise applicable CAL01-CAL28, including free/deal restrictions | B15-B19/B24/B25 |
| VCF13 | Direct/reference/deferred notes/invoices and challan printing execute physical stock exactly once; serial/lot/location/owner requirements cannot be hidden away | B21/B23/B24 |
| VCF14 | Stock Journal transfer/consumption/value profiles have distinct conservation rules; a class/default cannot switch executed history into another operation | B22/B23/B26 |
| VCF15 | Protected count cutoff, omitted versus zero observation, recount/approval and concurrent movement produce reviewed delta, not a balance overwrite | B25 |
| VCF16 | Source-required/direct return and source-cap rules survive mode changes; financial, physical and tax return effects stay distinct | B17/B25 |
| VCF17 | Quotes/indents/order schedules, per-line sources, partial fulfillment, tolerance and pre-close/reopen controls preserve commitment/effect boundaries; reservations are separate enabled commands | B28-B30; B31 if selected |
| VCF18 | Optional/memo/reversing scenarios remain separate from books; actualization and due scheduling revalidate and cannot silently flip posted state | B32-B36 |
| VCF19 | Material In/Out principal/worker profiles preserve ownership and zero-commercial versus stock-value distinctions in both directions | B37/B38 |
| VCF20 | Job receipt with separate/combined consumption resolves source location/BOM/units and cannot consume previously used components twice | B38/B39 |
| VCF21 | Process yield/scrap/additional-cost and statutory job-source controls retain original dispatch/aging and no payroll dependency | B39-B41 |
| VCF22 | UI/API/import/client/jobs use one registry/digest; stale consumer, publication/stop and scheduling races cannot bypass current authority | B06/B07 and each posting slice |
| VCF23 | Artifact defaults/live field denies and follow-up failures preserve issued snapshots; print/share/payment request cannot duplicate posting or reconciliation | B08/B19; B42-B44 only if selected |
| VCF24 | Registers expose type/profile/class/policy lineage, comparable source/effect facts and settings-change audit; replay/rollover/rebuild uses historical snapshots | B14/B18/B27/B40/B45 |

VCF checks supplement existing AC/CAL/BAL/STK/FY/INV/RPT requirements. D01/D04/D05/D06/D07/
D08/D10/D11/D12 retain their existing decision scope; no business threshold, legal profile,
costing method, optional integration or policy was activated here.

## Decision log

- 2026-10-10: Deep TallyPrime configuration review extended commercial controls into a
  common native registry and settings/capture/effect matrix for all 22 kinds and required
  profiles. Added reusable policy candidates, immutable resolved evidence, API/publication
  contracts and VCF01-VCF24 within existing batches. Preserved shared tables, effect-owner
  authority, payroll exclusion and the distinction between researched Tally capabilities
  and our proposed configuration/execution design.
- 2026-10-11: Added a detailed backend implementation plan for the 21 non-Sales kinds and
  their quotation, requisition, challan, bank and job-work profiles. It elaborates typed
  controls, owner boundaries, stage gates and batch acceptance without changing the
  22-kind registry, activating any profile or marking a batch verified.
- 2026-10-11: Reviewed the linked remaining-kind plan against the current v1 policy schema and
  resolver. New typed subpolicies first bind through `COMMON`; further binding families need
  coordinated migration. Presence-aware inheritance, per-setting date basis and accepted
  snapshot compatibility precede rollout. Pro-forma, legal challan identity and separate
  VC2 work-package gates are explicit. The 22-kind coverage matrix describes required design,
  not completed runtime for every kind.
- 2026-10-11: A [scoped v2 backend execution slice](voucher-configuration-v2-execution.md)
  now preserves v1 digests, supports sparse inheritance and typed order/ordinary-money capture,
  and selects v2 money bindings by posting date. Remaining descriptors, owner effects and
  activation still follow the linked plan and existing batch gates.
- 2026-10-31: Added [company voucher defaults](company-voucher-defaults.md): a versioned
  company-scoped catalogue, Account/Product/Mixed Sales and Purchase types, common native
  policies and feature-gated stock/BOM profiles. Signed company discovery and explicit
  setup provision definitions without enabling effects or changing authored revisions.
- 2026-10-31: Follow-up default usability review removed conflicting Journal/note
  requirements, versioned the corrected starter rules as v2 and added safe preparation
  for existing companies. Entry controls now respect requisition purposes and standard
  Sales profiles; the defaults document records the remaining specialised workflow gaps.
- 2026-11-02: The `purchase_calculation` policy section ([purchase calculation
  presets](purchase-calculation-presets.md)) holds suggested Purchase discount/charge recipes,
  never money rules. It is valid only on standard Purchase types and PURCHASE-family
  configuration profiles; effective resolution drops it for every other kind, and its discount
  steps are checked against the invoice policy's total discount limits.
