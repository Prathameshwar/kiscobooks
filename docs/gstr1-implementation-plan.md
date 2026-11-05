# GSTR-1: phase-wise implementation plan

Status: implementation authorized 2026-11-02. The user requested all nine phases,
uninterrupted completion and final review/fixes. See the delivery record for
implementation progress and verification.

## Intended result and applicability

Add **Reports > Tax reports > GSTR-1** with its dedicated workspace at
`/reports/workspace?report=GSTR1`. Prepare one GSTIN's monthly or quarterly
statement of outward supplies, with statutory tables, invoice details, source
exceptions, reconciliation, review history and print/export.

Show the card when the company jurisdiction is explicitly India (`IN`) and it
has a relevant dated Indian GST (`gst_in`) registration required to furnish
GSTR-1. Evaluate the registration's legal class, validity and filing obligation;
a GST feature flag or ledger name alone does not establish applicability.
Regular, eligible SEZ and casual-taxable-person registrations need their dated
obligations resolved. Composition, ISD, non-resident, OIDAR, TDS-only and TCS-only
registrations must not receive an enabled GSTR-1 preparation action. A company
can also have another eligible supplier GSTIN, which is evaluated separately.

An eligible GSTIN without filing setup gets an actionable readiness message.
An inapplicable company does not get the card; direct navigation explains the
requirement. A report reader can see authorized history; capture, preparation,
review and download each need their own current company/field authority.

Each preparation selects one GSTIN, statutory period, dated Monthly/QRMP filing
preference and verified source cut. Multiple GSTINs never merge into one filing.
Use a month picker or calendar-quarter/year selectors, with the April-March GST
financial year independent of company accounting-year configuration. Preserve
lawful historical obligations after closure or regime changes.

The core delivery is GSTR-1 preparation and externally filed evidence. Retain
IFF/GSTR-1A evidence needed for correct quarterly/amendment reconciliation.
Standalone IFF/GSTR-1A filing workspaces, direct GST Portal submission, DSC/EVC,
GSP connectivity and e-invoice generation are separate integration scope.
Portal-upload JSON is a conditional artifact: enable it only after verifying
the current official utility/schema and validating generated files through it.

## Existing capabilities and gaps

Reuse the delivered company GST registration and dated filing-preference setup,
verified Accounting source cuts, Reports job/history/download pipeline, shared
UI primitives, GSTR-3B presentation patterns and source navigation.

The existing `GSTR1` category in `gst_return_record` is aggregate comparison
evidence for GSTR-3B. It is not an invoice-level GSTR-1 dataset. Existing invoice
facts retain supply classifications, registration IDs, dates and tax components,
but do not by themselves establish the complete recipient GSTIN snapshot,
statutory document identity, HSN/UQC quantity summary, ECO role, export evidence
or previously filed amendment baseline needed here. Do not relabel the Invoice
Tax Register or aggregate GSTR-3B allocations as a completed GSTR-1 return.

Identity owns company registration/profile history; Catalog owns applicable
item/classification/UQC references; Vouchers owns issued documents, numbering,
revisions and document evidence; Accounting owns committed tax effects and their
publication; Reports owns derived return workings, frozen review and artifacts.
Use owner APIs/events and verified replicas, without cross-service SQL or remote
Identity calls inside financial transactions.

## Required statutory coverage

Phase 1 confirms exact headings, fields, supported periods and portal mappings.

| Section | Required behavior |
|---|---|
| Header | GSTIN, legal/trade name, statutory financial year and return period; turnover/profile fields where prescribed |
| 4, 6B, 6C | Registered-recipient invoices, including outward RCM, eligible SEZ with/without payment and deemed exports, with correct flags and rate-wise details |
| 5A/5B | B2C-large interstate invoices using the period's full invoice-value threshold |
| 6A | Export invoices with/without payment; distinguish goods/services and retain shipping/customs details where applicable |
| 7 | B2C-others summarized by prescribed place-of-supply/rate keys, with eligible notes netted correctly |
| 8A-8D | Nil-rated, exempt and non-GST outward supplies, separated by registered/unregistered and interstate/intrastate categories |
| 9B | Registered and applicable unregistered/export credit/debit notes; exclude commercial-only notes from tax reduction |
| 9A, 9C, 10 | Amendments to previously reported invoices, notes and B2C summaries, retaining original filed identifiers and differential effects |
| 11A/11B and their amendments | Taxable advances and subsequent adjustments under the correct goods/service and time-of-supply rules |
| 12 | HSN/SAC summary, including dated B2B/B2C separation, rate, lawful UQC/quantity and tax values |
| 13 | Prescribed issued-document categories and serial series, total/cancelled/net-issued counts, with owner numbering evidence |
| 14/14A | Supplier disclosures for supplies through ECOs under section 52 or 9(5), and their amendments |
| 15/15A | ECO section 9(5) supplies and amendments, preserving registered/unregistered supplier and recipient roles |
| Summary/declaration | Statutory summary, recipient summary where relevant, provenance and signatory placeholders; clear internal preparation versus actual external filing status |

Tables 12-14 contain summary/disclosure information that must not duplicate
underlying supply liability. Table 15 has its own ECO liability mapping. Apply
the prescribed invoice, note and amendment representation rather than forcing
every section into an identical five-column totals table.

## Delivery phases

### Phase 1 — Official format and dated rules

Verify current GSTN manual/advisories, prescribed form, relevant CBIC rules and
offline utility/schema. Build a versioned table/field/source matrix covering
signs, rounding, aggregation keys, required evidence and applicability.

Include at least the current GSTR-3B supported periods, October 2025 onward.
Earlier periods need verified historical mappings before being enabled. Verify:

- B2C-large: interstate unregistered supplies with full invoice value **above
  Rs. 1 lakh from August 2024**; historical threshold Rs. 2.5 lakh through July
  2024. Equality belongs to B2C-others; all intrastate unregistered supplies use
  the applicable B2C-others treatment. Do not classify using taxable value alone.
- HSN B2B/B2C separation from May 2025, turnover-based HSN/SAC digit requirements,
  authoritative code lists, mandatory fields and dated warning/blocking rules.
- Mandatory Table 13 checks, lawful amendment/credit-note time limits, annual
  return interactions, return-age restrictions and notified due-date extensions.
- Current special registration conditions, including Rule 14A where applicable;
  the portal manual describes a monthly B2B-tax restriction for that profile.
  Do not assume every ordinary-looking GST registration has identical rules.
- GSTR-1A availability and IFF quarterly handling using current guidance.

The public FAQ contains historical Rs. 2.5 lakh and September credit-note
passages alongside newer guidance. Resolve those against dated official rules;
do not blindly implement every statement in the FAQ. Portal tolerances or
warnings do not authorize unexplained differences in the application's books.

**Exit:** verified rules and sample expected returns, with an explicit supported
period/profile matrix and export-contract decision.

### Phase 2 — Company setup and source readiness

Reuse Identity GST setup. Complete any required dated turnover/profile,
registration-to-location and filing-frequency inputs with native validation.
Do not infer QRMP from turnover without confirmed filing preference.

Audit account, product and mixed sales; GST notes; exempt/non-GST supplies;
advances; exports/SEZ/deemed exports; ECO supplies; document issue/cancellation;
and legacy or externally issued invoices. Check actual publication and verified
source availability for each category. Identify missing field capture before
starting calculations; include the required owner-side work in Phase 3.

**Exit:** each supported category has a real source path. Missing evidence is
visible and blocks an affected return; absence of data never proves Nil.

### Phase 3 — Complete native outward-supply evidence

Extend typed owner contracts where needed, retaining:

- Issuer/recipient GSTIN and legal-class snapshots at the statutory date;
  explicit unregistered/UIN/SEZ/ECO roles and place-of-supply reasoning.
- Statutory document number/date/type, source voucher/revision/line, immutable
  invoice value, rate-wise taxable amounts, IGST/CGST/SGST/UTGST/cess, and lawful
  retained INR conversion evidence.
- Goods/service HSN/SAC, item quantities and UQC, including legitimate service
  quantity treatment; no fabricated unit or quantity just to fill a cell.
- Tax note versus commercial note, original supply links, lawful reduction
  grounds, advances/adjustments and export/SEZ/customs references. Missing
  shipping-bill information is not a universal blocker when the rules permit
  later amendment.
- Issued/cancelled document-series events, including prescribed non-invoice
  documents with no journal. Saved drafts do not count as issued documents.
- Original filed period/document values and identifiers for amendments;
  actual IFF/GSTR-1A evidence and IRN/import identity where supplied.

Financial supply workings consume committed sources; Table 13 also consumes
authenticated document-owner issuance/cancellation evidence. Historical imports
require validated structured detail and retained proof, not unrestricted manual
aggregate totals. Preserve old readers and frozen GSTR-3B cuts.

Any model changes ship with reviewed one-DDL migrations, owner audit/outbox,
projection/version updates, OpenAPI, generated clients and consumer lockfiles.
Return review keys include **return type, GSTIN and period**: the existing
GSTR-3B filed lock must neither block nor masquerade as a GSTR-1 filing.

**Exit:** native source/publication contracts and scope, money, replay and
historical-compatibility tests pass.

### Phase 4 — Invoice and supply tables, one group at a time

Implement and complete in order: registered invoices/SEZ/deemed exports;
B2C-large; B2C-others; exports; nil/exempt/non-GST; notes; advances/adjustments.
Each group gets independent expected examples, mapping review and fixes before
moving to the next.

Count invoice-level value once while preserving multiple rates/lines. Do not
double taxable bases because CGST and SGST have separate components. Preserve
document-date, tax-point and allocated reporting-period distinctions. Net B2C
notes only where prescribed; do not also count them as standalone note tax.
Apply goods-advance relief and service advance timing from dated rules. Foreign
currency or a foreign address alone does not prove an export.

Retain exact Decimal source money; round prescribed output cells consistently
before deriving their totals. Missing tax facts and ambiguous classification
remain exceptions rather than silently assigned zero values.

**Exit:** all primary supply cells reconcile to classified source documents;
boundaries, multi-rate invoices, notes and advances have passing examples.

### Phase 5 — HSN, document series, ECO and amendments

Implement Table 12 from classified source lines with correct B2B/B2C, HSN/SAC,
rate and UQC keys. Explain differences from invoice sections; require reviewed
evidence for exceptions. Preserve amendment differentials in the HSN bridge
where the current portal requires them.

Implement Table 13 from actual document-series evidence. Preserve cancellation
history, validate net-issued counts and explain sequence gaps. Do not fabricate
cancelled counts or derive legal serial ranges from invoice row counts or
lexicographic minimum/maximum values.

Implement 14/14A and 15/15A with separate supplier/ECO roles and explicit
cross-table duplicate checks. Add 9A/9C/10/11 amendment paths referencing frozen
filed baselines; output the prescribed amended values while separately showing
their differential impact on the current return.

**Exit:** supporting tables, ECO roles and amendments reconcile without duplicate
liability, invented numbering or silent mutation of filed records.

### Phase 6 — Reconciliation, QRMP and immutable review

Reconcile native sales/tax records to GSTR-1, HSN/document summaries and retained
portal/e-invoice data where available. Link classified outward values to the
appropriate GSTR-3B 3.1/3.1.1/3.2 rows using dated rules. Include advance/note/
amendment effects, exclude inward RCM and ITC, and respect the October 2025
Table 3.2 advance exclusion. Do not equate all GSTR-1 gross turnover with one
GSTR-3B row or replace verified portal comparisons with internal totals.

For QRMP, distinguish actual filed IFF entries in the first two months from
drafts, and apply the portal's quarterly inclusion/deduplication rules. Retain
same-period GSTR-1A changes separately and account for their effect on the 3B
bridge; do not assume all changes reach the recipient's same-period GSTR-2B.

Use frozen preparation versions, explicit coverage and source exceptions,
review proof and externally filed acknowledgements. GSTR-1 has its own Nil
criteria: inward purchases, opening credit or ITC claims alone do not make
GSTR-1 non-Nil, while nil-rated/exempt outward supplies still constitute activity.

Filed GSTR-1 evidence locks that return version. Subsequent lawful corrections
link to it instead of editing it. GSTR-1A is a distinct optional statutory
process with its own timing/once-per-period rules; do not expose it as arbitrary
editing of a filed GSTR-1. **GSTR-1 review/filing does not require the GSTR-3B
tax-payment/offset checks**: it is an outward-supply statement, not payment proof.

**Exit:** reconciliation, Nil, IFF evidence, amendment lineage, filing locks and
current-authority review checks pass.

### Phase 7 — Card, workspace, sections and lists

Add the India/GST-gated GSTR-1 card beside GSTR-3B in Tax reports, with server
catalogue and direct-page checks in agreement. Reuse shared spacing, typography,
filters, notices, menus and the existing GST/Day book interaction patterns.

The workspace has GSTIN, Monthly/QRMP period and verified-source selectors;
summary counts/taxable/tax amounts and readiness; statutory section cards/tabs;
and invoice/recipient detail lists. Sections group **Invoices, Notes and
amendments, Advances, HSN, Documents issued, ECO, Reconciliation** while retaining
their official table identifiers. Every section has its own prescribed columns.

Use important defaults: document number/date, recipient GSTIN/name where
relevant, place of supply, invoice/taxable value, tax and readiness. Optional
source IDs, IRN and detailed classification fields live in Columns or the drawer.
Support full-result search, table/recipient/status filters, stable server paging,
amount-to-contributor links and authorized voucher navigation. Kebab actions and
drawers preserve row height. Refresh, source refresh, exports and Print/PDF share
a compact action row. Changing dimensions clears the displayed preparation and
proof; saved history restores its own GSTIN/period/source. Filed views disable
inappropriate preparation/review actions while preserving authorized downloads.

**Exit:** usable section/list/drill-down flows, all permission branches and Light,
Dark and Ledger themes at desktop/mobile widths pass UI review.

### Phase 8 — Statutory print and exports

Provide protected preview/download using the existing Reports artifact pipeline:
prescribed summary PDF plus paginated detail, a section-wise Excel workbook,
complete supporting CSV and an exceptions/reconciliation working pack. Preserve
invoice numbers as text, exact money and amendment provenance. Export section
filters explicitly; label complete-return exports so users understand their scope.

If Phase 1 verifies a current official portal utility/schema, deliver validated
upload JSON and/or the exact official import template with round-trip examples
and retained schema version. Otherwise expose working-paper exports and an
explicit unavailable status; do not label generic JSON/Excel as portal-ready.
Print/export never establishes external filing or government acceptance.

**Exit:** all supported artifacts match the same frozen preparation; formatting,
precision, pagination, file safety and revoked-access checks pass.

### Phase 9 — Final review, fixes and end-to-end acceptance

Run native MySQL owner/report integration tests, migration/model/index parity,
replay/audit checks, typed contract/OpenAPI/generated-client checks, scoped UI
tests, and equivalent simplify/security review. Fix findings and rerun the
affected checks before declaring the work complete.

Exercise single/multiple GSTINs; permitted/denied roles and field restrictions;
monthly/QRMP; B2C threshold boundaries; multi-rate product/account/mixed invoices;
RCM outward supplies; SEZ versus deemed export; goods/service exports; tax and
commercial notes; advances; HSN/UQC; document cancellations; ECO roles; IFF and
amendment continuity; true Nil versus exempt-only; late/cross-year recording;
missing source evidence; exact rounding; filed locks; search/paging/drill-down;
and protected PDF/Excel/CSV/conditional portal artifacts.

Finish with actual-company readiness and authorized source-to-report review.
If a real eligible GSTIN/profile or actual filing evidence is unavailable, report
that limitation and identify fixture-assisted browser evidence clearly. Do not
create synthetic live GST registrations, financial postings or acknowledgements.

**Exit:** all enabled categories are verified end to end, findings are fixed,
unsupported evidence is visibly blocked, and remaining integration limits are
documented in a delivery/review record.

## Sources and decisions

- 2026-11-02 implementation authorization supersedes the earlier documentation-only
  request. All nine phases and final review are recorded in
  [GSTR-1 delivery](gstr1-delivery.md). Portal-upload JSON remains unavailable
  under the conditional schema-verification gate; PDF/Excel/CSV are working papers.

- [GST Portal GSTR-1 FAQ](https://tutorial.gst.gov.in/userguide/returns/GSTR_1.htm),
  retrieved 2026-11-02: applicability, HSN B2B/B2C guidance, document checks and
  updated GSTR-1A questions. Some other passages remain historical.
- [GST Portal GSTR-1 online manual](https://tutorial.gst.gov.in/userguide/returns/Creation_of_Outward_Supplies_Return_in_GSTR-1.htm),
  retrieved 2026-11-02: current table structure, August 2024 B2C threshold,
  May 2025 HSN separation, amendments, ECO and Rule 14A portal conditions.
- [GST Portal GSTR-3B guide](https://tutorial.gst.gov.in/userguide/returns/GSTR3B.htm),
  retrieved 2026-11-02: dated GSTR-1/1A-to-3B table mappings.
- [Existing GST delivery](gstr3b-delivery.md), [final review](gstr3b-final-review.md)
  and [native tax-recording design](voucher-tax-recording.md).
- Research evidence is retained in the ignored
  `.test_artifacts/tax-reports-review/gstr1-plan-research/` directory. The standalone
  older `GSTR-1A.htm` page says suspended, contradicting updated questions in the
  current GSTR-1 FAQ; it is not a current activation authority.
- 2026-11-02: user requested a GSTR-1 phase-wise plan with India/GST visibility.
  Documentation only is authorized. The plan reuses the existing architecture,
  requires detailed statutory sources, preserves GSTR-3B behavior, and separates
  preparation/export evidence from government filing.
