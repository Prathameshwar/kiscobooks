# India retail chemist, wholesale and stockist backend completion plan

**Prepared:** 2026-10-12. **Status:** Implementation plan; no pharmacy stock or
dispensing capability is activated by this document. Read with the [gap review](pharmacy-chemist-gap-review.md),
[voucher delivery tracker](voucher-delivery-tracker.md), [stock design](voucher-stock-recording-reporting-design.md)
and [company/item execution record](company-item-configuration-execution.md).

## Outcome and current boundary

The intended release serves a retail chemist, a wholesale distributor and a
stockist that buys and owns its goods. A stockist/agency that merely holds a
principal's goods is a separate controlled profile described below. Each can
buy or receive, hold, transfer, sell or supply and return medicines against
identifiable physical packs/lots. The platform can show current saleable
stock and immutable item/batch/expiry registers, enforce the applicable India
licence and prescription controls, retain protected dispensing evidence, and
reconcile stock quantity/value to the GL. It must reject a transaction whose
classification, licence, lot, price declaration, prescription evidence or cost
cannot be established. No per-voucher or per-year table family is added.

PH09 and PH10 are closed, and the shared PH04 licence-check primitive is partly
closed. PH01-PH03 and PH05-PH08 remain open. CI-P1/P2 and B15-B18 are in progress;
B19-B27, CI-P3-P5 and C3 stock activation are unverified. Catalog's
`stock_execution=UNAVAILABLE` and Vouchers' disabled `post`/`reverse` remain
truthful until the owner transaction and recovery tests pass. Do not describe a
printed challan or a saved voucher as a completed stock movement.

**Implementation progress, 2026-10-12:** The first PH-A source slice now stores
reviewed, effective-dated Catalog item classification with separate licence-form
and prescription-schedule axes, source hash and reviewer. The effective item
response and signed owner snapshot expose that revision. Vouchers validates and
stores the signed history in an indexed, date-resolved projection; its pure
medicine gate rejects absent/expired evidence and Schedule X. Accounting now
stores reviewed Form 20/20B/21/21B dealer licences per party premises, exposes
dated authoring/closure and resolves the required form by operation and item
licence class. The signed owner snapshot and Vouchers indexed projection carry
the dealer evidence. This is source infrastructure only. Manufacturer licence
forms, reviewed recipient exceptions, voucher issue-time source pins and legal
gates, Accounting lot/stock/valuation,
MRP declarations, prescription records, registers and the activation/recovery
rehearsal are still outstanding. PH-A through PH-I are **not complete** and the
existing execution gates must remain closed.

## Business profiles and transaction boundaries

"Retail", "wholesale" and "stockist" are not interchangeable flags. The
transaction records four independent decisions: the company's configured
business capability, the legal operation for this supply, who owns each stock
position, and who the buyer/recipient is. A stockist selling goods it bought
normally uses a wholesale supply path; a stockist holding principal-owned goods
needs a custody/agency path whose tax and invoicing responsibility follows the
actual contract. Catalog's existing `SalesChannel` can select a price series but
does not establish a drug licence or legal operation.

| Business profile | Typical document path | Required additional controls |
|---|---|---|
| Retail chemist, including multi-branch | Purchase/receipt -> shelf/bin -> counter sale or delivery -> customer return | Premises-specific retail licence; H/H1 prescription and pharmacist evidence when applicable; small/partial-pack conversions; actual lot/expiry/printed MRP; mixed cash/card/credit tender; patient data confined to protected dispensing records. Branch transfer is a physical movement with its own tax/document decision. |
| Wholesaler/distributor | Supplier purchase -> bulk receipt -> quotation/order -> pick/dispatch challan -> tax invoice -> collection/credit note/return | Premises-specific wholesale licence; dated buyer licence or reviewed institutional exception; buyer delivery address and GST facts; written/signed order where required; competent-person evidence on the wholesale memo; pack/case/UOM conversion; credit terms/limits; batch/expiry allocation, partial dispatch and backorder; transport and e-way/e-invoice applicability; purchaser trace for recall. |
| Stockist owning purchased inventory | Manufacturer/principal purchase -> depot receipt -> allocation/scheme -> secondary wholesale sale -> settlement, expiry/breakage claim or return | Company-owned cost/value and GST input/output effects; supplier/territory/rate agreement pins; trade price levels, quantity deals/free goods and discounts from existing promotion/configuration engines; batch-wise supplier claim, replacement and short/expired/damaged stock; depot, transit and customer-level distribution reporting. Customer eligibility remains the wholesale rule. |
| Stockist/C&F or consignment custodian holding principal goods | Principal dispatch -> custody receipt -> depot transfer -> authorized fulfillment -> principal settlement/commission -> residual return | Explicit owner/principal and custody at every movement; no company inventory asset merely because goods are in its warehouse; contract-specific authority to issue invoice/challan, tax treatment and title-transfer moment; principal stock statement, fulfilled quantity and commission/claim reconciliation. This is a separate activation profile after its accounting and legal contract is verified; it is not silently treated as an owned-stock sale or job work. |

One company may enable several profiles, and one site may support both retail and
wholesale only with the corresponding licence facts. Configuration binds permitted
profile/operation to company and premises, voucher type/class and effective date;
the selected path is pinned on each issued voucher. It controls required fields,
approvals, legal evidence, invoice/challan behavior, stock effect mode, price
list, credit and tender choices. It never overrides a missing licence or
expired/held lot.

All profiles record the supplier/manufacturer source, supplier premises and
reviewed licence/authorization evidence at purchase or custody receipt. A
manufacturer's name or GSTIN alone does not prove a party may supply a given
drug. The buyer and supplier evidence is versioned by address and effective
date, with a verification reference and reviewer; issuance and receipt pin the
selected evidence. Party contacts and financial accounts remain in the
existing Accounting master model.

### Indian trade masters and configuration

| Existing owner to extend or reuse | India-specific fields and behavior |
|---|---|
| Catalog item/family, unit, manufacturer, inventory and price definitions | Medicine name/strength/form, marketer/manufacturer, carton/box/strip/tablet conversions with exact ratios, HSN/tax rule, dated regulatory class/schedule, batch/expiry requirement, storage condition and channel price levels. Define purchase cost, negotiated purchase price, price-to-stockist (PTS), price-to-retailer (PTR), institution rate and MRP as separately named facts where used; do not derive one from a fixed margin. The actual printed pack declaration belongs to the receipt cohort in Accounting. |
| Identity company address/licence and company configuration | At each retail counter/depot, enabled retail/wholesale operations, exact premises and applicable licence form/date; GST registration/branch assignment; authorized pharmacist or competent-person evidence references and approval policy. A company that does both selects the operation per voucher. |
| Accounting party, address, tax registration, credit and account masters | Supplier/manufacturer/marketer, retail dealer, wholesale dealer, hospital/institution, practitioner, government buyer and principal as reviewed party categories; dated licence/verification per address; buyer GSTIN/place-of-supply facts; credit limit/terms, advances and bill outstanding; manufacturer/stockist or C&F agreement with effective rates, territory and claims. A party may have several roles, but role does not replace statutory eligibility. |
| Vouchers type/class configuration and Catalog promotion policy | Retail counter, B2B wholesale, owned-stockist and principal-custody profiles; required prescription or signed order; allowed tender/credit; batch selection and channel-specific minimum shelf life; order/challan/invoice reference mode; permitted discounts, quantity deals and scheme stacking; return/expiry claim windows and approval thresholds. Historical vouchers pin the effective policy. |

PTS/PTR are commercial price levels used in Indian distribution, not substitutes
for the printed consumer MRP or an automatic statutory margin formula. The
existing promotion engine should represent a bundled 10+1 offer distinctly
from a standalone sample/gift: both move quantity, but their invoice value,
tax and input-credit treatments may differ. CBIC's sales-promotion circular is
the review source for that distinction. No program should infer treatment from
`rate = 0` alone.

### Document effects by path

| Event | Stock/custody effect | Financial/tax effect |
|---|---|---|
| Quotation and sales/purchase order | Demand or expected receipt only; no on-hand increment/decrement | No GL/tax posting merely because an order was accepted. |
| Owned-stock receipt note then purchase invoice | Receipt creates one company-owned lot/receipt-origin movement; invoice references it | Cost/ITC/payable according to accepted document and tax date; never a second physical receipt. |
| Retail sale | Actual selected pack/lot leaves the issuing premises once; partial-strip conversion is pinned | Price/MRP, discount, tax, tender and COGS from the same allocation. |
| Wholesale pick, challan, invoice | Pick/reservation does not issue stock; dispatch executes or enters transit once; invoice references its exact claim | Customer receivable, tax and COGS follow the supported time-of-supply/recognition policy, with no second quantity effect. |
| Branch/depot transfer | Same owner, different custody/location or protected transit; receipt consumes the dispatch claim | No invented sale; GST/challan/e-way treatment depends on registrations and effective policy. |
| Customer/supplier return or expiry claim | Source-linked quantity returns to inspected saleable custody or quarantine/supplier transit | Credit/debit note, tax adjustment, refund/claim and inventory value follow the original entitlement and supported policy. |
| Principal-owned agency receipt/fulfillment | Principal owner retained through custody movements until a reviewed title/fulfillment event | Stockist inventory asset and sale revenue remain untouched unless the contract truly transfers title; commission and settlement use separate effects. |

## Decisions to lock before migrations

1. **Supported legal matrix.** Keep two distinct dated product axes: licence-form
   class (`OTHER_THAN_C_C1_X`, `C_C1_EXCLUDING_X`, and `SCHEDULE_X`) and
   prescription/control schedule (such as H, H1, X, or none). H/H1 do not imply
   a Form 20 versus 21 choice. Record the source, effective interval, reviewer,
   review time and change reason for each classification. Treat unknown,
   conflicting and unreviewed values as unavailable. The first activation
   excludes Schedule X unless its Form 20F/20G and register/retention branch has
   its own reviewed implementation and tests; X lines fail closed in the meantime.
2. **Premises and operation.** Retail and wholesale are explicit voucher operations;
   the physical issuing premises must be a company address and must match the
   licence. Multiple branches cannot borrow a company's primary licence from
   another branch. Pin the licence row/version and number on issue/reprint.
   Wholesale buyer eligibility is resolved from dated party licence facts or
   an explicit, reviewed recipient exception; a GSTIN or a generic CUSTOMER role
   is not evidence of permission to buy a regulated drug. Signed orders and
   purchaser details are retained when the supported rule requires them.
3. **Expiry interpretation.** Store the printed expiry text and precision (day
   or month) as receipt evidence, plus a normalized last-saleable date under a
   reviewed India rule. Evaluate in the company's timezone at the physical
   supply date. A missing/ambiguous date on an expiry-required medicine blocks
   sale; a later master edit never silently changes an issued allocation.
4. **Pack and price basis.** Printed pack MRP is a physical declaration on a
   receipt/pack cohort, not the Catalog SKU MRP default. Capture its currency,
   quantity/unit, tax-inclusion basis, declaration source and corrections.
   A reviewer must sign off the final-payable comparison basis, including
   invoice-level discounts, free units and allocable charges/tax. Until then,
   keep the medicine sale profile disabled rather than comparing the wrong total.
5. **Costing and fiscal continuity.** Reuse the selected B22 FIFO and moving-average
   valuation scopes; FEFO chooses physical stock and does not choose cost method.
   Retain receipt origins across financial years. Source date, physical date,
   statutory date, posting period and recorded time remain separate and pinned.
6. **Distribution title and tax.** Owned stockist inventory and principal-owned
   custody have different GL, tax and settlement effects. The source agreement
   pins title/agency authority, invoicing party, place-of-supply and commission
   or margin treatment. Resolve India GST document/e-way/e-invoice rules from
   effective policy; do not hard-code today's thresholds into vouchers. For an
   applicable invoice or movement, pin the IRN/e-way result or verified external
   reference before treating the statutory artifact as complete. Movement
   without sale still needs its applicable challan and transport evidence.

## Implementation batches and acceptance gates

| Batch | Owner and existing dependency | Implementation | Exit evidence |
|---|---|---|---|
| PH-A: source/readiness | Identity, Catalog, Accounting parties, Vouchers; CI-P1/P2, B15-B19 | Finish company address/licence/registration and effective item/tax/price/location projections. Add reviewed, effective-dated item regulatory classification and supplier/buyer drug-licence or recipient-category facts to the existing party/address model. Pin company profile, premises, operation, item class/schedule, party eligibility and source digests; reject stale or missing projections. Complete ordinary invoice/tax calculation and statutory artifact gates before medicine billing. | Two branches, licensed suppliers and buyers with different licences/expiry dates resolve correctly; consumer, licensed dealer and reviewed institution follow distinct rules; receipt/issue refuses wrong premises or ineligible party; B15-B19 invoice/tax gates pass. |
| PH-B: stock core | Accounting; B20/B21, CI-P4 | Add canonical stock position, lot, receipt origin, immutable posting/movement, guarded balance, hold/event and stock-period records with tenant/company scoped keys. Lot header has no mutable quantity. Normalize nullable position dimensions so concurrent first receipts cannot create duplicates. Receipt validates item/base-unit conversion, lot/manufacturer/dates, warehouse/bin/ownership and source identity; update position and movement atomically. Add an explicit readiness bit/version that remains off until replay/reconciliation passes. | Duplicate transport/HTTP keys and new keys for the same source cannot double-receive; concurrent receipt/issue/hold/count races preserve one position and nonnegative eligible quantity; movement sums reproduce guarded balances. |
| PH-C: eligibility and costing | Accounting; B21/B22 | Enforce receipt-date and supply-date rules, minimum remaining life, FEFO ordering, holds, owner/custody and location eligibility under the same locks. Expired or recalled goods remain counted in a non-saleable disposition. Add FIFO cost layers and moving-average pool/events, immutable value effects, GL/clearing lineage and zero-cost versus unknown-cost evidence. | Earliest eligible expiry is deterministic, ties stable; expired/held/minimum-life failures are atomic; FEFO issues produce the selected FIFO/average costs without confusing selection and valuation; stock value reconciles to GL. |
| PH-D: physical voucher flow | Vouchers + Accounting; B23-B26 and B28-B36 order/fulfillment dependencies | Add reusable typed physical allocations to common voucher lines: lot, receipt/declaration cohort, actual/base quantity, location/custody, condition and source allocation. Cover counter sale, bulk order/pick/partial challan/invoice/backorder, transfer, rejection, customer/supplier return, count and correction. Distinguish `EXECUTE`, `REFERENCE` and `DEFERRED`; exact source claims prevent challan plus invoice from moving stock twice. Preserve billed, actual and free/deal quantities separately. | Partial strips/cases, two lots, multiple dispatches and cross-year flows reconcile; returns claim only previously issued quantities; expiry/damage returns are quarantined; order, challan and invoice show one physical movement. |
| PH-E: declarations and trade commercial | Catalog + Accounting + Vouchers; B15/B16/B24/B25 and existing scheme/discount controls | Store pack MRP declaration per receipt cohort, including same manufacturer batch with different MRPs. Pin it to sale/return allocations. Use channel/premises/party price-level, rate agreement, credit/discount/scheme configuration without bypassing legal limits. Apportion invoice-level discount, deal/free benefit, charges and tax to each pack's legally relevant payable basis. Keep wholesale trade margin, supplier scheme entitlement, free stock, short/expiry claims and customer credit/debit notes distinct from physical stock cost. | Mixed-MRP test catches a price above the lower pack's cap; a 10+1 wholesale deal moves 11 units and retains correct cost/tax/claim evidence; partial returns reverse only original entitlement; credit exposure and supplier settlement reconcile. |
| PH-F: dispensing and legal registers | Catalog + Vouchers + Accounting/Reports; B19/B24/B27 | Add typed, protected retail prescription, prescriber, patient/animal-owner and pharmacist supervision evidence and typed wholesale buyer licence/institution/signed-order and competent-person evidence, with schedule/recipient-specific requiredness. Keep sensitive identity/document content out of generic custom fields, Audit payloads and unrestricted exports. Receipt and issue create append-only purchase, prescription and wholesale-memo/register facts with premises, supplier/buyer, licence evidence, medicine, actual batch/manufacturer/expiry, quantity and source reference; corrections append, never rewrite. Include H1-specific and, if enabled later, X-specific branch and retention/legal-hold rules. | Retail H/H1 issue without required evidence fails; wholesale restricted-drug supply without eligible buyer/order or competent-person evidence fails; purchase and sales registers reproduce issue-time facts; unauthorized roles cannot read/filter patient data; retention, correction and reprint pass. |
| PH-G: quality, recall and reports | Accounting + Reports; B21/B25/B27a-e | Record lot/location/partial quantity holds, release approvals, excursion readings and trace links from supplier receipt through each depot and retail/wholesale purchaser. Generate purchase register, retail day/cash summary, prescription/H1 and wholesale memo registers, order-to-dispatch outstanding, dealer ledger/credit ageing, stock and batch/expiry/near-expiry, quarantine/recall exposure, MRP/declaration, depot/branch, primary purchase/secondary sale, supplier scheme/expiry claims and quantity/value-to-GL reconciliation. No second editable stock balance or unrestricted patient export. | Recall reaches every affected receipt and buyer; hold blocks allocation immediately; depot, party and channel totals reconcile without double counting transfers or scheme units; stock and GL balances agree; reports and exports obey company, branch and sensitive-data scopes. |
| PH-H: principal-owned stockist/agency | Vouchers + Accounting + Reports; after PH-B through PH-G, separate legal/tax contract | Add an explicit principal-stock agreement with title, issuing party, permitted movements, settlement and commission terms. Reuse canonical positions with principal owner and company custody; principal dispatch/receipt, depot transfer, fulfillment, return and discrepancy effects never turn third-party goods into company inventory value. Post only contract-supported commission/settlement/tax effects and preserve principal-facing stock statements. | Principal-owned quantity reconciles separately from company-owned quantity/value and GL; one dispatch cannot be both a principal sale and a stockist sale; lost/expired/returned goods and commission claims reconcile; activation waits for reviewed contract-specific tax and licence rules. |
| PH-I: activation/recovery | All owners; CI-P5 and C3 for retail/wholesale/owned-stockist, separate later gate for PH-H | Run migration/backfill on disposable tenant data, snapshot/rebuild comparisons, failed/unknown-outcome recovery, replay, rollback and restore rehearsals. Activate per company/premises/profile only after its required gates pass. Keep unsupported X/cold-chain/agency variants explicitly disabled or refused. | Retail, wholesale and owned-stockist each pass the two-year rehearsal and reviewer-signed legal/price matrix; C3 dependencies including B28-B36 pass; `stock_execution` changes only for supported profiles. Principal-owned agency activates only after PH-H acceptance. |

PH-A and the schema design of PH-B may progress together; committed stock effects
depend on PH-A source pins and PH-B locks. PH-D depends on PH-C. PH-E and PH-F
depend on PH-D allocations. PH-G consumes committed PH-B–PH-F facts. PH-H
extends the owner/custody model; PH-I is the last gate for each selected profile.
The existing B20–B27 tracker remains authoritative; these PH labels are a
pharmacy-specific work breakdown, not new parallel posting batches.

At the existing C3 checkpoint, activate Indian pharmacy profiles gradually:
first one retail premises, then a wholesale premises with licensed-dealer and
institution cases, then an owned-stock stockist with depots and trade schemes.
Each profile retains its own recorded rehearsal and rollback evidence; a pass
for one does not authorize another. Principal-owned agency/C&F remains off
until PH-H's contract, custody and settlement tests pass. This rollout order
does not waive any C3 prerequisite in the voucher tracker.

Schedule X is a named follow-on under PH-A/PH-F/PH-I: add reviewed Form 20F/20G
premises rules, its distinct prescription copy/register/retention controls,
issue-time evidence and denial tests before its profile is offered. Cold-chain
medicines likewise need PH-G excursion-to-hold execution and readings evidence
before that handling profile is offered. Neither variant inherits acceptance
from ordinary H/H1 or room-temperature stock tests.

## Shared storage and API contract

- **Catalog:** `item_regulatory_classification` (dated immutable/reviewed
  revisions and source evidence), effective item/readiness response, signed
  owner snapshot. Product HSN/SAC, generic MRP and descriptive attributes stay
  separate.
- **Identity:** existing company licence and premises records plus effective
  business-capability/profile configuration; versioned, date-resolved owner
  facts. The posting consumer uses the same reviewed class, operation and
  premises matrix as the shared gate; no user-submitted licence number is
  accepted as authority.
- **Accounting party masters:** retain the existing party, role, address,
  tax-registration, account and credit controls. Add reviewed, effective-dated
  counterparty drug-licence and recipient-exception evidence keyed to the exact
  buying address, plus supplier/principal agreement facts where necessary.
  Avoid turning `CUSTOMER` or GST registration into wholesale eligibility.
- **Vouchers:** common revision/line plus reusable `voucher_inventory_allocation`
  and protected dispensing/wholesale-order evidence records. The public input
  schema exposes typed references/allocations and a selected operation, owner,
  premises and counterparty category; it never accepts an arbitrary stock
  balance or asserts that a user-entered licence number is verified. Issue pins
  source hashes, buyer/legal evidence, order/challan claims and selected
  commercial policy. Post/reverse call Accounting's authenticated owner
  contract only after readiness and policy validation.
- **Accounting:** `stock_posting`, `stock_movement`, `stock_balance`/position,
  `stock_lot`, receipt-origin/declaration, hold/event, cost layer or average-pool,
  cost allocation/value and source-claim records. A single company-scoped
  transaction owns quantity, value, GL, idempotent result and outbox. Its
  owner/custody dimensions also separate owned stockist goods from principal
  goods, so only the former joins the stockist's inventory asset. Use the names
  in the stock design where existing migrations settle them; no cross-service
  FK or duplicate quantity authority.
- **Reports:** checkpointed registers and aggregates rebuilt from immutable
  Accounting and protected dispensing facts. Include channel, branch/depot,
  customer/secondary sale, supplier claim, principal custody and credit views
  without summing overlapping ownership or transfer slices. API filters,
  cursors, exports and row/total access checks follow existing conventions.

Each new table needs its own reviewed one-DDL migration, tenant/company scoped
key/FK strategy, downgrade or explicit reason, audit/outbox event, permission
mapping, generated OpenAPI/client contract and native DB race/replay tests. Do
not infer completion from an ORM model or unit-only FEFO test.

## Required end-to-end rehearsal

Use two companies and two premises, retail/wholesale licences, both supported
drug classes, H and H1 items, two manufacturer lots with different expiries,
and one manufacturer batch split into two printed-MRP receipt cohorts. At each
step compare physical, saleable, held and valued quantities, immutable movement
sums, source claims, tax/GL, register facts and reprint output.

| Profile rehearsal | Required sequence and failure case |
|---|---|
| Retail | Receive packs, sell part of a strip on prescription under pharmacist supervision, accept cash plus digital tender, accept a customer return of part of the sold quantity, and quarantine an expired/damaged return. Reject wrong-branch licence, missing required prescription and a price above the actual pack declaration. |
| Wholesale | Validate a licensed dealer and a reviewed institution recipient separately; accept an order, dispatch two partial challans from different lots, invoice by referencing those exact movements, and apply PTR/negotiated rate, credit terms, competent-person evidence, transport/GST evidence and a later credit note. Reject expired buyer licence, missing applicable signed order or competent-person evidence, and duplicated dispatch claim. |
| Owned-stock stockist | Buy cases at a recorded PTS/negotiated cost from a licensed source, distribute across two depots, sell a 10+1 deal to two dealers at their effective trade rates, distinguish the deal from a standalone sample, reconcile supplier scheme/expiry/shortage claims and credit exposure, and cross a financial year. Reject a return that exceeds the original dealer/lot entitlement. |
| Principal-owned stockist/agency, when enabled | Receive principal goods into custody, transfer between depots, fulfill only the principal-authorized quantity, report remaining principal stock and settle commission. Reject any posting that values the goods as the stockist's asset or bills them as its own sale without contract authority. |

Recall one lot across all four paths. Repeat with concurrent issues, duplicate
requests, stale item/party/licence projections, wrong premises, expired/held
stock and an unknown Accounting outcome; each must fail or replay without
partial effects. Rebuild registers and balances from immutable facts and match
the same fiscal cutoff. Separate activation evidence is kept for retail,
wholesale, owned stockist and principal-owned agency.

## Regulatory review references

The [CDSCO Drugs Rules compilation](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/drug_rules/Drugs%20Rules%201945_2024%2009.09.2024.pdf)
sets out Rule 61 licence forms and Rule 65 retail/wholesale purchase,
dispensing, memo and register particulars, including buyer/recipient and
signed-order review points.
The [CDSCO rules text](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/drug_rules/Drugs%20Rules%2C%201945.pdf)
identifies Forms 20F/20G for Schedule X. [NPPA's DPCO material](https://nppaindia.nic.in/dpco2013)
is the starting point for the price-cap review. [CBIC's e-way rules](https://cbic-gst.gov.in/ewaybill-rules.html)
are a source for movement document policy. [CBIC Circular 92/11/2019-GST](https://cbic-gst.gov.in/pdf/circular-cgst-92.pdf)
distinguishes bundled buy-one-get-one supplies from standalone free samples;
[NPPA's pricing explanation](https://www.nppaindia.nic.in/proactivedisclosure)
uses PTR for its ceiling-price methodology. TallyPrime's
[order-to-delivery-note-to-invoice flow](https://help.tallysolutions.com/sales-order-tally/) and
[batch/expiry entries](https://help.tallysolutions.com/manage-inventory-batch-wise-tally/)
inform the operational workflow, not legal applicability. These are scope
inputs, not a substitute for a current India pharmaceutical legal review of
applicability, exceptions, printed-price basis and retention before activation.
