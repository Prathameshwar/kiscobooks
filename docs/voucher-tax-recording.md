# Voucher tax recording: India GST and state VAT

**Date:** 2026-10-10. **Status:** Required planning extension; not a claim of implemented compliance.
**Jurisdiction:** User confirmed India. GST is the first profile; Indian VAT needs explicit
state/commodity coverage. No foreign VAT jurisdiction or all-India VAT engine is assumed.
**Read with:** [Vouchers](vouchers-plan.md), [existing tax implementation](tax-accounting-plan.md),
[Accounting](accounting-design.md), [company registrations](company.md) and [fiscal controls](fiscal-year.md).
**Storage:** The [shared voucher model](voucher-data-model.md) holds native tax context and
per-line component inputs/analysis for all voucher kinds. Taxable invoices do not get separate
document tables. These inputs/evidence are distinct from Accounting's authoritative tax events.

The [financial-year design](voucher-financial-year-design.md) separates company GL fiscal
year from the legal invoice-year/number and statutory tax-event/return period. Preserve
original supplier/issuer references, credits, advances and return evidence across years.
D05/D12 require a native statutory identity separate from the internal journal reference
where they differ; fiscal reopening cannot automatically amend/unfile a tax return. Reverify
effective jurisdiction rules at activation; a UI-selected year is never a tax-date rule.

## 1. Separate business documents, tax events and tax returns

A voucher's name does not determine whether a transaction is taxable. Evaluate the actual
supply, parties and registrations, ownership, location/place of supply, dates and applicable
legal profile. Keep four linked records: the business voucher; physical/financial postings;
tax evidence and eligibility; and statutory document/return submissions. One event may affect
some of these without affecting all of them. Never count a quotation, challan and invoice as
three supplies of the same goods.

The plan uses "voucher" for a business/accounting record. It does not introduce a gift-card,
coupon or stored-value product, which would need a separate legal and business design.

India GST supports applicable CGST + SGST or UTGST, IGST and cess through dated rules. Keep
taxable, nil-rated, exempt, zero-rated and non-GST treatments distinct even when the tax amount
is zero. Regular, composition and other registration classes are not interchangeable. Exports,
SEZ supplies, imports, reverse charge, related/distinct persons and special place-of-supply
rules require their own validated profiles, not just a buyer-state comparison or a zero rate.
Unimplemented cases must return a clear unsupported-profile result before posting.
Tax valuation must also address supported composite/mixed supplies, discounts, freight and
other assessable charges. Product HSN/SAC or an account default proposes classification;
it is not alone sufficient to decide tax. Explicit approved overrides retain their reason,
authority and original evidence. Unknown valuation/place-of-supply rules block affected flows.

## 2. Recording matrix

This is the platform's required behavior, conditional on the applicable legal profile. A
"no tax" business-document step does not excuse an actual supply or advance from being
recorded through its separate tax event. All 22 initial kinds are covered below.

| Voucher/workflow | Recording requirement |
|---|---|
| Quotation, pro forma, Sales Order, Purchase Order | Store estimated line taxes and quote validity, but no actual liability, ITC or return entry. A subsequent advance uses Receipt/Payment with its own rules |
| Job Work In Order / Job Work Out Order | Commitments, expected materials and quoted service tax only; no tax event merely on order issue |
| Sales | Tax invoice or bill-of-supply profile as applicable; record outward supply, taxable base and components, registration and return category. Tax timing need not equal collection date |
| Purchase | Record supplier invoice/customs evidence and purchase tax separately from claimable ITC; distinguish eligible, pending, blocked and nonrecoverable amounts |
| Credit Note | Native issuer/direction and statutory-versus-commercial classification; outward supplier credit or received supplier credit has the appropriate liability/ITC effect, subject to legal conditions |
| Debit Note | A supplier's GST debit note increases the relevant supply/tax. A purchaser's commercial debit/return advice is not that statutory document; link the supplier's credit note and required recipient credit adjustments separately |
| Receipt / Payment | Ordinary settlement does not charge invoice GST twice. Taxable advances, refunds, reverse-charge timing, withholding and tax-authority payments use explicit profiles and allocation evidence |
| Contra | Own-bank/cash transfer has no supply tax. Bank service charges and their tax need separate expense evidence |
| Journal | Supported accrual, ITC reversal/reclaim, RCM liability, tax settlement or correction profiles; a generic journal into a GST account is insufficient return evidence |
| Delivery Note / Delivery Challan / Receipt Note | Record movement/receipt and source invoice links. Capture the lawful document basis and invoicing deadline; a challan alone neither charges nor exempts a supply |
| Rejections In / Rejections Out | Record the physical return once; separately link financial credit/debit and statutory tax adjustment. Stock return is not automatic cancellation of reported GST |
| Stock Journal / manufacturing mode | Transformation/location changes have no automatic outward GST; evaluate distinct-registration supply, own-use/disposal and credit-adjustment rules separately |
| Physical Stock | Count adjustment requires a reason; loss/destruction/write-off can require credit adjustments even without a customer sale |
| Material In / Material Out | Track job-work owner/custodian and challan chain. Qualifying material movement and taxable processing charges are distinct; exceptions and deemed supplies are explicitly evaluated |
| Memorandum / scenario Reversing Journal / optional mode | Excluded from actual GST/VAT books and returns. Record any real supply, receipt or movement with a real voucher; scenario status cannot defer an incurred liability |

CGST section 31 distinguishes tax invoices, bills of supply and advance/RCM documents;
section 34 governs supplier credit/debit notes. Keep commercial adjustment evidence separate
from a legally eligible reduction of tax. Current text includes amendment commencement
notes: a published amendment must not become an active rule before its effective date.
[CBIC section 31](https://taxinformation.cbic.gov.in/content-page/explore-act/1000300/1000001/invoice/ACTS),
[section 34](https://taxinformation.cbic.gov.in/content-page/explore-act/1000304/1000001).

## 3. Native tax facts and dates

These fields are native, typed and versioned, never user-created custom attributes:

| Level | Required facts |
|---|---|
| Company/registration | Tax system, jurisdiction/state, statutory registration, registration class/regime and validity; local location-to-registration mapping; supplier/customer roles |
| Voucher | Document profile, issuer, inward/outward direction, supplier/recipient registration snapshots, bill-to/ship-to/dispatch/service facts, place-of-supply decision and reason, supply category, invoice references, currency and statutory declarations |
| Item or account line | Goods/service, HSN/SAC or applicable VAT commodity classification, quantity/unit, gross/discount/assessable charges, taxable value, inclusive/exclusive basis, treatment, rule/rate revision, component amounts and rounding |
| Tax event/allocation | Liability/credit/adjustment purpose, event identity, source revision/line, original invoice or advance allocation, legal basis, effective rule version, tax date, reporting period, recoverability and correction links |
| Statutory evidence | Internal/external document number, issuer registration, original date, immutable payload/hash, IRN/acknowledgement/QR or e-way-bill references where applicable, government submission and cancellation status |

Separate `document_date`, `posting_date`, actual supply/dispatch/receipt dates, invoice issue
date and payment/book/bank dates needed by the applicable rule. Derive `tax_point_date` and
the relevant rate/registration dates from those facts; do not accept an unrestricted client
choice. Preserve all inputs and the reason for the decision. Support more than one tax event
and return allocation for one voucher, including partial advances and later adjustments.

`posting_date` continues to select and guard the accounting fiscal period. A late entry or
correction in an open period retains original statutory dates and the required tax-period
adjustment; it must not move the legal tax event just to match open books. Financial close
and filed tax-period locks are separate controls. Historical tax snapshots are not recomputed
using current rates. Rate-change rules can depend on supply, invoice and payment dates.
[CBIC time of supply of goods](https://taxinformation.cbic.gov.in/content-page/explore-act/1000281/1000001),
[change in tax rate](https://taxinformation.cbic.gov.in/content-page/explore-act/1000283/1000001).

**Compatibility gate:** Existing shared GST calculation and Accounting callers resolve
registration/rates using `posting_date`; the pure calculator itself consumes resolved facts.
This plan proposes a versioned tax-context resolver and evidence contract, not a silent
change to those callers. V0/T0 must define distinct legal dates, update affected invariants,
replicas, source contracts and clients, retain readers for old snapshots and regression-test
existing journals. The posting-period guard never uses the statutory tax date instead.

For multiple GST registrations, partition tax accounts, document series and returns by
registration/jurisdiction. V0 must settle the current one-supplier-registration-per-state
restriction and the location mapping before enabling cases it cannot represent. Identical
company ownership does not make a transfer between distinct GST persons a non-supply.
Use a linked outward/inward tax-document pair with inter-branch clearing and one physical
movement identity; consolidation eliminates internal balances without deleting tax evidence.
[CBIC Schedule I](https://taxinformation.cbic.gov.in/content-page/explore-act/1000734/1000001).
Enforce statutory number format and uniqueness within the applicable registration, financial
year and document-category rules across all derived voucher types. Company type labels do
not create independent legal numbering namespaces. One statutory document identifies one
issuing registration; a multi-registration transaction requires linked documents.

### Commercial configuration and free-item purposes

The [commercial configuration contract](voucher-commercial-configuration.md) distinguishes manually supplied bonus quantities,
automatic paid-supply rewards, and independent samples/gifts. Retain native purpose and any
consideration allocation; zero commercial presentation cannot decide taxable value, ITC or
stock cost. CBIC Circular 92/11/2019 distinguishes samples/gifts from offers supplying several
items for one consideration; validate current applicable rules at legal-profile activation.
[Official circular](https://cbic-gst.gov.in/pdf/circular-cgst-92.pdf). Tax-display, voucher-class
or discount toggles cannot waive mandatory tax. CAL20/CAL21/CAL23 verify this boundary.

## 4. Accounting, advances and input credit

Sales/Purchase calculation follows the [invoice contract](voucher-invoice-calculation.md).
Commercial net, statutory taxable value and landed inventory cost remain distinct. Qualifying
discounts, assessable charges, independent charged services and composite/mixed supplies need
explicit dated tax treatment; a generic before/after-tax flag or ledger display order is not
sufficient. Inclusive prices and discounts require supported component extraction/allocation.
Supplier-declared tax and computed tax both remain in evidence, with authorized difference
handling. Invoice rounding must not silently change statutory tax components; advance/tender
application must not subtract from the taxable supply a second time.

The [purchase component/return contract](voucher-invoice-calculation.md#51-purchase-return-component-and-adjustment-contract)
requires repeated taxes with native value/quantity bases and effective rule versions, alongside
stacked quantity/line/invoice discounts and charges. Header tax inputs allocate to eligible
supplies; derived summaries cannot add tax again. Validate component combinations, independent
service-charge versus assessable-charge treatment, mixed rates and recovery status. Do not
infer legal applicability from a ledger label or simply stack GST and VAT.

For a purchase return, retain original per-source taxable-base/component allocations and
remaining adjustment entitlements, while applying the supported statutory adjustment rules
and evidence at the event date. A physical return, purchaser commercial advice, supplier tax
note and actual refund have separate identities and timing. Supplier-note matching must not
recognize an already-booked commercial credit twice; ITC adjustment requires its own supported
evidence/recognition, not just negative returned quantity. New restocking/return freight uses
separate components. CAL05-CAL14 cover these requirements; tax registers retain all bridges.

Accounting owns immutable tax-event evidence and its links to journals, open items and stock
value. Use separate accounts/subledger dimensions for output liability, purchase tax pending
eligibility, eligible input credit, RCM liability, credit reversal, nonrecoverable tax, statutory
cash deposits and tax settlements, by registration and component. Exact accounts remain the
company's approved posting mappings. Vouchers owns the source evidence/workflow, not a second
authoritative tax ledger. Reports consumes committed snapshots with reconciliation checkpoints.

Illustrative journal patterns, assuming the selected tax treatment is valid:

| Event | Debit | Credit |
|---|---|---|
| Taxable credit sale | Customer: gross | Revenue: net; output GST: tax |
| Purchase awaiting credit eligibility | Stock/expense: net; purchase tax pending: tax | Supplier: gross |
| Approved ITC recognition | Eligible input GST | Purchase tax pending; blocked amounts instead follow reviewed expense/capitalization policy |
| Collection against a taxed invoice | Bank | Customer; no repeated GST |
| Taxable service advance | Bank: gross received | Customer advance: base; output tax on advance |
| Tax deposit with government | Statutory cash-deposit control | Bank |
| Confirmed liability offset | Applicable tax payable | Permitted eligible input-credit and/or statutory cash-deposit controls |

These patterns do not prescribe revenue recognition or immediate ITC entitlement. Linked
advance adjustment removes the already-recognized advance tax when the final invoice tax
is recognized; a partial invoice consumes only its allocated advance base/tax. Refunds and
unapplied balances retain their source links. Document issuance and accounting effects are
idempotent independently, then reconciled by common source/event identity.

GST treatment differs between advances for ordinary goods covered by the applicable
notification and taxable services. Apply Notification 66/2017 as amended and its actual
scope/exceptions; never assume every money receipt is taxable or that all goods advances
are exempt. Track receipt-voucher/refund-voucher evidence where required. Deposits not yet
consideration need a separate classification and later application history.
[Notification 66/2017](https://upload.indiacode.nic.in/showfile?actid=AC_CEN_2_2_00042_201712_1517807328102&filename=notfctn-66-central-tax-english.pdf&type=notification),
[GST Portal advance reporting](https://tutorial.gst.gov.in/userguide/returns/GSTR_1.htm).

The [Tally settlement review](tally-settlement-functional-review.md) distinguishes financial
bill application from tax-advance adjustment. Store both allocations with source event/line,
registration, taxable base, tax components and remaining eligible amounts; a receipt's financial
balance is not sufficient to decide its remaining statutory adjustment. Automatic matching
first filters compatible tax/party/currency scope and only then applies a selected ordering rule.
Refunds and return-credit reinstatements are linked events, not edits to the original advance.
Opening financial credit and opening tax-advance evidence must reconcile without creating a
second receipt/payment. Product settings or a New Ref/Advance/On Account label cannot choose
the legal tax point or turn every supplier advance into RCM. Apply the dated rules above.

ITC lifecycle: recorded -> pending verification -> eligible -> claimed, with blocked,
reversed and reclaimed states and amount-level allocations. Invoice evidence, receipt,
business use, statutory restrictions, supplier reporting, time limits and payment-related
reversals are separate checks. A GSTR-2B/IMS match supports review; it cannot prove all legal
conditions by itself. Import/customs and other special credit evidence must be supported
explicitly. Reconciliation differences do not silently rewrite a posted Purchase voucher.
[CBIC section 16](https://taxinformation.cbic.gov.in/content-page/explore-act/1000285/1000001).

For RCM, separately record applicability, legal timing, recipient liability, payment evidence
and later eligible credit. An unregistered supplier alone is not a blanket RCM rule. Do not
net RCM payable against input credit at invoice creation; discharge follows the applicable
cash-payment requirement, and credit is enabled only after required conditions are met.
[CBIC RCM payment scrutiny guidance](https://cbic-gst.gov.in/pdf/02-2022-GST-DATED-22032022.pdf).

A GST payment challan is different from a delivery/job-work challan. Store CPIN/CIN or other
accepted payment references and reconcile deposits versus actual offset. A bank payment into
the electronic cash ledger does not by itself prove the tax liability has been discharged.
[CBIC payment rules](https://cbic-gst.gov.in/gst-payment-rules.html).

## 5. Job work, challans and inventory exceptions

Record principal and worker GST registrations, ownership, original dispatch/direct-receipt
date, inputs versus capital goods, each challan/endorsement and source line, onward worker
transfers, quantities received/consumed/returned, outputs, scrap, loss and outstanding custody.
Never reset statutory aging when goods move between workers or when an order is short-closed.

Under section 143, qualifying inputs/capital goods can be sent for job work without tax on
that movement, subject to conditions. The baseline return/supply periods are one year for
inputs and three years for capital goods, with specified exclusions/extensions. Model those
as dated rules and evidence, not unconditional timers. Overdue cases need review of deemed
supply from the original relevant date and consequent tax/interest, without backdating closed
GL entries. Direct supplies from the worker's premises and waste/scrap disposal require the
correct responsible supplier and statutory conditions.
[CBIC section 143](https://taxinformation.cbic.gov.in/content-page/explore-act/1000420/1000001/Job%20work/ACTS).

The worker's processing/service invoice is a separate taxable supply assessment, linked to
the material job. Its classification and rate require dated rules; do not use one universal
job-work rate or copy the tax treatment of the principal's material. Principal-owned stock
is never included in the worker's sales just because it passes through their premises.
Purchased material delivered directly to the worker retains the principal's purchase and
receipt evidence; no fictitious receipt at the principal's warehouse is required.

Delivery/job-work challans capture prescribed party, item, quantity, value, movement and tax
information where applicable. Rule 55 permits specified uses; "invoice later" is not a general
permission to defer invoicing every sale. Track legal purpose and invoice deadline. A challan
can display a valuation or tax particulars without creating a second liability event.
[CBIC Rule 55](https://taxinformation.cbic.gov.in/content-page/explore-rules/1000146/1000001).

Maintain a principal-side ITC-04 working register and validated export for applicable
reporting periods, including outward material, returns, onward transfers and exceptions.
Preserve original and subsequent challan links; allow documented many-to-many input/output
reconciliation when one-to-one matching is not possible. Filing periodicity, applicability,
schema and extensions come from the effective rule pack, not a hardcoded quarterly job.
[GST Portal ITC-04 utility guide](https://tutorial.gst.gov.in/downloads/formgstitc04.pdf).

Evaluate e-way-bill requirements by movement purpose, route, goods, persons, value and dated
exceptions. Specified job-work movements have requirements even below the general value
threshold. Keep e-way-bill generation/cancellation/expiry and transport changes separate
from invoice tax and physical posting; none is proof of the others.
[Official e-way-bill guidance](https://docs.ewaybillgst.gov.in/html/ewb_qna.html).

Loss/destruction, gifts/free samples, own use and disposal need native reason profiles and
reviewed supply/ITC rules. A zero sale price or zero stock value cannot be used as proof of
zero tax consequences. This is a required exception matrix before those profiles are enabled.
[CBIC section 17](https://taxinformation.cbic.gov.in/content-page/explore-act/1000286/1000001).

## 6. Indian VAT and other taxes

GST and applicable state VAT must be representable in the same company using separate
registrations, commodity treatments, ledgers and returns. A company-wide default tax system
only defaults forms; it cannot classify every line. GST law excludes certain supplies and
has separate commencement provisions for specified petroleum products. Do not classify all
petroleum-derived goods as outside GST or interpret non-GST as exempt from every other levy.
[CBIC section 9](https://taxinformation.cbic.gov.in/content-page/explore-act/1000278/1000001).

State VAT/CST profiles require the selected state's effective commodity schedules, registration
and invoice rules, assessable basis, rate/form/concession evidence, input-credit restrictions,
returns and payment process. The design must allow a supported mix of GST and VAT business,
but split documents where the relevant rules require it. Never offset VAT credit against GST
liability. Applicable excise/customs or other levies require explicit native components and
accounting treatment; no generic percentage field can claim that coverage.
For example, Maharashtra publishes its own VAT/CST schedules; this is evidence for a
state-specific design, not a selection of Maharashtra as the first supported state or a
current rate pack. [Maharashtra tax schedules](https://www.mahagst.gov.in/en/vat-and-cst-rate-schedule).

**Current gap:** The company tax catalogue lists `gst_in` and foreign VAT systems, but no
implemented India state-VAT profile is established by this review. Add the jurisdiction/regime
registry, registrations, validators, calculation/timing policy, mapping, return schema and
tests through a reviewed extension before enabling it. Do not reuse `vat_gb` or present
existing GST calculation as VAT support. States/commodities remain an implementation gate.

Keep Income-tax TDS/TCS and GST TDS/TCS in separate statutory namespaces, rates, threshold
accumulators, ledgers and reporting. Neither changes output GST by simply reducing the cash
paid. Job-work vendor withholding can use supported dated rules without introducing payroll.
Amounts from official rate packs or company-authored sourced rules require review, activation
dates and provenance; no statutory rate or threshold is invented in this plan.

## 7. Statutory documents, return evidence and service boundaries

Read the [posting/reporting design](voucher-posting-reporting-design.md) for common frozen-run,
source-cutoff, permission and reconciliation contracts. Tax working registers must bridge
commercial values, statutory events, GL control balances and return allocations, including
timing/eligibility differences. They cannot be reconstructed from tax-account net balances
alone or from the current financial event v1. Required B18/B40 reports extend those feeds.

Use native statutory profiles on the existing kinds: Tax Invoice, Bill of Supply, eligible
GST Credit/Debit Note, Advance Receipt Voucher, Refund Voucher, RCM self-invoice/payment
voucher where required, and Delivery/Job-work Challan. Profiles may be linked evidence on an
existing voucher; they must not duplicate revenue, cash or stock postings. These do not add
new base kinds merely to change a document heading.

Vouchers owns document generation, integration attempts and authoritative external responses.
Accounting owns committed tax effects, evidence and guarded eligibility/settlement adjustments.
Reports owns rebuildable GSTR-1/IFF, GSTR-3B, purchase-credit reconciliation, ITC-04 and enabled
VAT working reports/exports. Composition and other supported regimes require their own return
mappings rather than being sent to regular-taxpayer returns. Filing workflow/acknowledgements
remain tied to Vouchers' immutable submission record; report totals must trace to Accounting.

IRN/QR and e-way-bill applicability are different decisions. A material job-work challan is
not a processing-service tax invoice; do not extend a challan exemption to that invoice.
Evaluate notified e-invoice scope per taxpayer and transaction with current rules.
[GSTN e-invoice guidance](https://www.gstn.org.in/einvoice-faqs).

No remote call occurs inside Accounting's money transaction. V0 must design the sequence
between committed invoice number/evidence and external registration: pending registration,
accepted, rejected and unknown outcomes; retry/query recovery; lawful cancellation/correction;
and blocks on final issue/dispatch where required. Never mark a document compliant simply
because the journal posted, reuse a failed number, or delete a posted invoice after rejection.
Signed imports of externally obtained acknowledgements need the same validation and audit
when a direct connector is unavailable. Unsupported mandated flows stay disabled.

Freeze each reviewed submission's source revision IDs, control totals, schema/rule version,
period, registration, exclusions and exception approvals. Preserve acknowledgements and filed
versions; later corrections become linked amendments/adjustments, not edited historical
exports. Reconcile invoice registers -> tax events -> GL components -> return totals -> tax
payments/offsets. Keep input claims and reversals traceable to invoice/receipt evidence and
their claim periods. UI warnings cannot substitute for posting/filing rejection on missing
required facts. Read-denies and tenant/company/registration scope apply to all artifacts.

## 8. Delivery and verification

The [implementation roadmap](voucher-implementation-plan.md#7-work-packages) attaches tax
work to V2/V3, V4 and V8, with V9.1 Reports foundations and V9.2 exports delivered alongside
the relevant transaction phase. T4 statutory artifacts/evidence and required exports cannot
be deferred to final V9.3 hardening. Ordinary non-tax V2 settlements can proceed while a
tax-bearing advance/withholding profile remains gated on its completed T1 contract.

| Gate | Attached phase | Required deliverable and evidence |
|---|---|---|
| T0 | V0/V1 | India legal-profile inventory; tax-date migration contract; registration/location/numbering scope; native field/schema design; source/effective-date review; unsupported-profile rejection |
| T1 | V2/V3 | Sales/Purchase and statutory-versus-commercial notes; ordinary settlements versus advances/refunds; ITC states; RCM liability/payment/credit; native journals and immutable tax snapshots |
| T2 | V4 | Goods receipt/dispatch/invoice linkage, challan legal basis, no double tax/stock, distinct-GSTIN transfers, loss/return adjustments and opening-stock credit provenance |
| T3 | V8 | Principal/worker material chains, direct deliveries, service charges, aging/extension/deemed-supply cases, scrap/returns and ITC-04 exports |
| T4 | V3-V9, before enabling the affected profile | Validated statutory print/export, e-invoice/e-way-bill compliance workflow, return reconciliation/locks; direct connector or validated external-evidence path; recoverable unknown outcomes |
| T5 | Separate scoped extension | Selected India VAT state/commodity pack, coexistence with GST, statutory registers and native database/API/client tests before activation |

Acceptance cases must include partial taxable service advances followed by invoices/refunds;
ordinary goods advances and scoped exceptions; purchase tax pending versus blocked/claimed;
RCM payment before credit; supplier statutory debit versus purchaser commercial debit;
cross-period corrections and rate changes; bill-to/ship-to and supported service place-of-supply
cases; composition/exempt/nil/zero-rated distinctions; imports/exports only where supported;
distinct-registration stock transfers; job-work partial/multi-worker returns and overdue cases;
duplicate/out-of-order events; external rejection after local posting; and full tax-to-GL tie-out.

This document changes the plan only. Existing tax tests/calculation are useful foundations,
not evidence that these end-to-end statutory workflows or VAT packs already work. Reverify
official notifications, commencement dates, schemas and portal restrictions at implementation
and activation; research here was reviewed on 2026-10-10. TallyPrime supplies workflow ideas,
while official law and portal contracts govern India's statutory behavior.

## Decision log

- 2026-11-03 (B24): purchased goods use profile `INDIA_DOMESTIC_GOODS`: forward-charge GST from the item's
  published purchase HSN classification and rule (Catalog's signed stock facts, checked against Accounting's replicas),
  tax point the supplier invoice date (CGST s.12(2)(a)), intra/inter-state by the place of supply. A line may be
  marked not claimable with a reason; its GST is then part of the goods' cost. A company without GST registration
  bills goods untaxed at their price. Sales of goods and goods RCM remain future profiles.

- 2026-10-10: Linked the deeper report contract and explicit commercial/event/GL/return
  reconciliation, snapshot and access requirements. Common run infrastructure is shared
  with financial statements; tax profiles/rule versions retain their existing gates.

- 2026-10-10: Consolidated implementation sequencing now brings statutory artifacts,
  acknowledgment evidence and Reports exports into each dependent transaction release;
  final hardening is not the first reporting delivery. Existing legal-profile gates persist.
- 2026-10-10: Sales/Purchase review added separate commercial/tax/landed-cost allocation,
  inclusive-price and discount handling, supplier-declared differences and rounding controls.
  The shared invoice calculator must implement the dated jurisdiction rules, not ledger-order guesses.
- 2026-10-10: Follow-up Payment/Receipt/advance research clarified separate financial and
  statutory advance allocations, compatible matching, refund/return events and opening
  evidence reconciliation. Tally entry settings do not replace the dated India tax rules.
- 2026-10-10: Bound tax entry/calculation to the common voucher revision/line model and shared
  tax components, charges and source allocations. Type-specific requirements remain native
  rules; neither a generic custom field nor a separate invoice-kind table is the tax engine.
- 2026-10-10: User requested proper GST/VAT treatment and confirmed India. Added native tax
  event/evidence design, India GST-first delivery, state-specific VAT gates, job-work compliance,
  statutory date separation, ITC/RCM lifecycle and return/GL reconciliation. No application code,
  tax rates, thresholds or government submissions were changed.

- 2026-11-02: Purchase account bills can carry India GST on service lines in the console (see
  [purchase-tax-entry-plan](purchase-tax-entry-plan.md)). The person chooses supplier-charged or reverse charge and confirms the
  company registration, place of supply, completion date and the supplier's regular GST registration; rates and amounts stay
  Accounting's, from each expense account's tax default. Goods stay out, VAT and other regimes wait for their service profiles,
  and composition or unregistered suppliers are explained, not offered. No service rule or rate changed.

### Financial-year planning decision - 2026-10-10

Added cross-year statutory versus GL identity and continuity requirements, using the
financial-year design and FY21 acceptance. Current tax resolver changes remain compatibility
work; no statutory filing, legal-profile activation or accounting posting was performed.

### Purchase component review - 2026-10-10

Refined shared native component scopes, dependency/basis evidence, header-tax allocation
and source-linked purchase returns under the [invoice calculation contract](voucher-invoice-calculation.md).
The 51 numbered Vouchers candidates remain unchanged; D07 reviews necessary shared relations,
and Accounting retains authoritative financial/tax/stock effects. CAL01-CAL16 remain planned.

### Sales commercial-configuration review - 2026-10-10

Added native free/sample/deal purpose and configuration restrictions using the commercial
configuration contract and official classification evidence. D05/D09 retain dated legal-profile
validation; no universal exemption, gift-credit rule or statutory rate was selected.
