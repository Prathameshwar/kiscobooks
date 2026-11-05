# India pharmacy and chemist backend gap review

The [pharmacy completion plan](pharmacy-chemist-implementation-plan.md) maps
these findings to the existing B15-B27, CI-P1-P5 and C3 delivery gates.

## Implementation status, 2026-10-12

- **PH09 closed:** Catalog effective-item facts now return the selected inventory
  revision's manufacture-date requirement, shelf life and minimum remaining life.
  Stock execution still reports `UNAVAILABLE` for goods.
- **PH10 closed for Catalog naming:** custom item field names now reject physical
  expiry, manufacture, lot and printed-pack-MRP names, including common variants.
  The generic product MRP master remains available as a SKU pricing definition.
- **PH04 partially closed:** the shared India licence resolver now filters by
  premises and the issue guard requires an explicit `RETAIL`/`WHOLESALE` operation,
  premises and supported drug class. Forms 20/20B cover the class outside C/C1/X;
  21/21B cover C/C1 excluding X. Unclassified and Schedule X lines fail closed in
  this primitive. Mixed-class documents require both applicable forms. Identity's
  stored-licence seam is tested with a premises-linked
  record. No live issuer calls this primitive yet, so PH03 and the issuance part of
  PH04 remain open.
- **PH01–PH03 and PH05–PH08 open:** physical lot ownership, FEFO, classification
  master and projection, protected dispensing evidence, declaration-aware MRP,
  return allocation, holds and recall cannot be asserted as executable. Vouchers'
  `post` and `reverse` HTTP routes remain disabled while Accounting stock batches
  and native reconciliation are unverified.

The class split above follows [CDSCO's Drugs Rules compilation, rule 61 and the
form descriptions](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/drug_rules/Drugs%20Rules%201945_2024%2009.09.2024.pdf).
The platform treats the licence's configured `valid_to` as a verified-through
window, not a claim that a statutory licence automatically expires. Form/category
applicability, exceptions, dispensing evidence and retention still need legal
review before a pharmacy profile can be activated.

**Reviewed:** 2026-10-12. **Scope:** company licences, Catalog item/price/inventory
masters, Vouchers capture, Accounting stock ownership and report inputs. This is a
source review, not a certified legal compliance assessment or a claim that stock
posting is live. The [company/item execution record](company-item-configuration-execution.md)
still marks CI-P1/CI-P2 partial and CI-P3–CI-P5 open.

## Existing foundation

- Identity stores dated, premises-linked company licences. The India profile names
  drug-licence Forms 20, 21, 20B and 21B and a narcotic-licence type.
- Catalog has typed inventory-template definitions for lot/serial tracking,
  manufacture/expiry requiredness, shelf life, minimum remaining life, FIFO/FEFO
  issue choice and valuation choice. Product types can require expiry, and Catalog
  has exact units, product MRP history, handling temperature bounds, return policy,
  tax and price resolution, warehouse restrictions and replenishment bands.
- Vouchers have common item lines, item/custom fields, quantities and shared
  invoice/order configuration. Orders are non-posting. The `post` and `reverse`
  routes explicitly refuse financial/stock execution while dependent batches are
  unverified. The current Accounting source tree has no physical stock-lot,
  movement, valuation or expiry model; its `opening_batch` is a financial opening
  batch, not a medicine lot.

## Findings, ordered by release risk

| ID | Severity | Finding and source evidence | Required behavior |
|---|---|---|---|
| PH01 | Release blocker | Physical medicine batch/lot, expiry, receipt origin, per-location quantity, hold and cost allocation are absent from Accounting. Catalog intentionally refuses stock facts in `domain/stock_facts.py`; Vouchers `schemas/documents.py` item lines carry no batch or expiry. | Add one Accounting stock owner with immutable receipt/issue/return/transfer/adjustment movements, lot/date provenance, guarded positions and cost layers. Keep stock posting closed until native reconciliation passes. |
| PH02 | Release blocker | Catalog's FEFO/expiry/minimum-life fields are configuration only; there is no execution-time lot eligibility, deterministic FEFO allocation, expiry-day rule or expired-stock quarantine. | On every allocation, check expiry and remaining life in company timezone, ownership, location and holds. Prevent sale of expired/held lots; retain quantity in segregated non-saleable custody for withdrawal/return/disposal. |
| PH03 | Release blocker | No native drug schedule/classification on item/family and no source path from an item to the `line_gates` argument of `billing_platform.statutory.assert_company_can_issue`. The latter is used in unit tests, but no Vouchers/Accounting issuer calls it. `scheduled_drug` therefore cannot currently gate an issued drug line. | Add dated, reviewed product regulatory classification distinct from HSN/SAC. Pin the classification and apply the relevant licence/premises/operation gate on invoice and challan issue. Never use a free-form custom field for this decision. |
| PH04 | High latent defect | The India jurisdiction profile maps both retail-labelled Forms 20/21 and wholesale-labelled 20B/21B to the same `scheduled_drug` gate. `assert_company_can_issue` accepts **any** valid kind for that gate, with no sale-channel, premises or product-class argument. Its `resolve_licence` likewise chooses a company-wide primary without premises context. | Replace the single gate with a reviewed operation/premises/product-class licence matrix, then test retail versus wholesale and multiple premises before wiring it to issuance. |
| PH05 | Release blocker | Vouchers' typed `VoucherInput` and `ItemInput` have no prescription, prescriber/patient, pharmacist supervision, Schedule H1 or Schedule X register reference. The generic `ReferenceInput` has only supplier invoice, customer order, external and challan purposes. | For the regulated profiles that apply, capture protected prescription and supervision evidence, preserve issue-time batch/manufacturer/expiry, and generate auditable register entries with the appropriate retention/access policy. Determine precise applicability with a legal reviewer. |
| PH06 | High | `ItemMrp` is a dated SKU/unit/jurisdiction default. There is no physical stock price-declaration owner or allocation field in Vouchers. Two packs of one SKU/manufacturer batch with different printed MRPs cannot be sold or returned against their own declaration. | Capture printed MRP and declaration identity per receipt/pack allocation. At sale, compare the final payable amount on the applicable legal basis with the actual selected pack declaration; preserve original declaration on return and reprint. |
| PH07 | High | Purchase receipt, sales challan, sale, purchase return and customer return lines do not identify actual lot, manufacture/expiry dates, received pack/declaration, condition or source issue allocation. A source-linked financial note alone cannot restore the right physical stock. | Implement quantity-by-lot and declaration allocations for each physical voucher kind. Return to saleable stock only after condition/expiry checks; otherwise quarantine or supplier-return it. |
| PH08 | High | Catalog handling profiles store temperature limits, but no custody readings, excursion events or hard stock hold are present. Planned recall/hold/genealogy in `docs/catalog-inventory-integration.md` and `docs/voucher-stock-recording-reporting-design.md` have no owner implementation. | Add lot/location hold and release evidence, recall trace to purchasers and supplier receipts, and optional cold-chain excursion capture before calling these capabilities executable. |
| PH09 | Medium | Catalog's new `EffectiveItemFacts.inventory` response exposes lot/serial/expiry flags and issue strategy but omits `manufacture_date_required`, `shelf_life_days` and `minimum_remaining_life_days` that exist on the template. This is an API completeness gap even for master review. | Expose those protected source fields with the template revision ID; retain `stock_execution=UNAVAILABLE` until the owner can enforce them. |
| PH10 | Medium | `domain/stock_facts.py` reserves custom field names such as `batch_number` but not `expiry_date` or physical pack MRP. A tenant could create a descriptive item custom field that appears to be a live lot fact; domain logic correctly does not read custom fields. | Reserve or clearly namespace physical-lot and declaration names in Catalog custom fields, and route such data to the Accounting receipt/declaration authority. |

## Release order and acceptance

1. Complete the existing B15–B19 invoice/tax source contract and CI-P1–CI-P3
   company/item projection work; add dated regulatory product classification and
   licence matrix with legal review.
2. Complete B20–B27's single stock owner, receipt lots, expiry/FEFO, holds,
   declaration-aware MRP, sales/returns/transfers, valuation and registers. Add
   pharmacy scenarios to those batches rather than a separate stock ledger.
3. Add protected prescription/dispensing evidence and schedule-specific registers
   before enabling applicable retail profiles. Keep patient data out of generic
   custom fields and unrestricted report/export surfaces.
4. Rehearse two premises, two licences, two batches with different expiry and
   printed MRP, partial pack sale, expired/held lot rejection, customer return,
   supplier return/recall, and a year boundary. Reconcile lot quantities and value
   to stock/GL and verify register/print history before activation.

## Regulatory references used for scope

The [CDSCO Drugs Rules compilation](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/drug_rules/Drugs%20Rules%201945_2024%2009.09.2024.pdf)
describes prescription-register particulars including manufacturer, batch and expiry
for applicable drugs. The [Schedule H1 amendment](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadGazette_NotificationsFiles/588E30thAug2013.pdf)
specifies a separate supply register and retention period. The [CDSCO rules text](https://cdsco.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/acts_rules/2016DrugsandCosmeticsAct1940Rules1945.pdf)
describes expired-drug sale/stock restrictions and segregation pending withdrawal.
The [NPPA DPCO page](https://nppaindia.nic.in/dpco2013) provides official medicine
price-control material. The [2026 Schedule H1 amendment](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadGazette_NotificationsFiles/2026.05.13%20G.S.R.%20377%28E%29_Notification%20for%20amendment%20in%20Schedule%20H1%20for%20inclusion%20of%20Pregabalin%20and%20its%20drug%20formulations.pdf)
shows why regulatory classification must be effective-dated. Exact legal coverage,
form/category applicability and retention should be checked against current
amendments with a qualified reviewer before release.
