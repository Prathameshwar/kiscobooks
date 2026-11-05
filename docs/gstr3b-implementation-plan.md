# GSTR-3B: phase-wise implementation plan

Status: implementation authorized 2026-11-02. The user requested completion of
all eight phases and final review/fixes. Direct GST Portal filing and automatic
tax payment remain outside this preparation/reporting scope.

## Intended result

Add a GST-specific GSTR-3B workspace under Reports > Tax reports for applicable
Indian GST registrations. Prepare a GSTIN-specific monthly or QRMP quarterly
return in the prescribed table structure, supported by reconciled transaction
details, exceptions, review history and statutory print/export.

The existing Invoice Tax Register, Input Tax Credit Register and Tax to Ledger
Reconciliation remain working and reconciliation reports. Their totals cannot
simply be relabelled as a GSTR-3B return: closing credit balances are different
from period claims, and ledger movements alone do not establish statutory facts.

Deliver return preparation, review and exports. GST Portal submission, DSC/EVC,
automatic tax payment and direct government connectors are separate integration
work. An imported filing acknowledgement may establish externally filed status;
generating a PDF or recording a bank payment cannot establish it.

## Applicability and navigation

- Company jurisdiction is India (`IN`), with a relevant dated `gst_in`
  registration and a regime required to file GSTR-3B.
- Resolve registration class and regime, not just `default_tax_system` or a
  GST ledger name. Existing regular, SEZ and casual-taxable-person profiles need
  their applicable rules checked. Composition, unregistered, ISD, GST TDS and
  GST TCS registrations have other obligations; a separate supplier GSTIN may
  coexist with these registrations.
- Each return belongs to one GSTIN and one statutory period. Multiple GSTINs
  never merge into a company-wide filing. Default to the eligible primary
  registration only when selection is unambiguous.
- Record monthly/QRMP filing preference by effective period. Use financial year
  and month/quarter selectors; do not expose arbitrary date ranges or Posting /
  Document date switches as the statutory filing-period basis.
  Use the GST April-March financial-year calendar independently of any different
  company accounting-year configuration.
- Keep lawful historical periods accessible after registration closure or regime
  change. Cancellation/suspension and QRMP partial-quarter obligations require
  their own dated rules.
- Gate card, page, preparation, review, drill-downs and downloads by company,
  registration and actor authority. An applicable but unconfigured report shows
  actionable setup/readiness guidance. An inapplicable regime does not get an
  enabled GSTR-3B preparation action.

## Prescribed form coverage

Phase 1 verifies exact headings, cell availability, precision, schema and rules
for the supported periods. The required coverage is:

| Form section | Required content |
|---|---|
| Header / Tables 1 and 2 | GSTIN, legal/trade name and statutory year/period as prescribed; filing-frequency context and dated registration evidence |
| 3.1(a) | Outward taxable supplies other than zero-rated, nil-rated and exempt supplies |
| 3.1(b) | Outward zero-rated supplies, including applicable exports and SEZ supplies |
| 3.1(c) | Other outward supplies: nil-rated and exempt |
| 3.1(d) | Inward supplies liable to reverse charge |
| 3.1(e) | Non-GST outward supplies |
| 3.1.1(i), (ii) | Section 9(5) supplies: ECO liability and supplier disclosures, with distinct roles and cash-payment treatment |
| 3.2 | Place-of-supply-wise inter-state supplies to unregistered persons, composition taxable persons and UIN holders; apply the period's portal mapping |
| 4(A)(1)-(5) | ITC available: imports of goods; imports of services; other inward RCM supplies; inward supplies from ISD; all other ITC |
| 4(B)(1), (2) | Reversals under Rules 38, 42, 43 and section 17(5), and other reversals, using the applicable form version |
| 4(C) | Net ITC available: 4(A) less 4(B), by tax head |
| 4(D)(1), (2) | Reclaimed ITC previously reversed in 4(B)(2); ineligible ITC under section 16(4) and restricted place-of-supply rules |
| 5 | Exempt/nil-rated inward supplies, including the prescribed composition-supplier grouping, and non-GST inward supplies; inter-state/intra-state columns |
| 5.1 | Interest and late fee in the prescribed tax-head cells, with relevant period and liability evidence |
| 6.1 and liability breakup | Tax payment/offset details: normal and reverse-charge liabilities, ITC/cash utilization, interest/late fee and applicable prior-period liability breakup |
| Declaration | Prescribed declaration/signatory fields; distinguish an internal reviewed draft from an externally filed return |

Use Taxable value, Integrated tax, Central tax, State/UT tax and Cess columns where
prescribed. Do not force every table to have the same columns. Table 3.2 is a
breakdown of the relevant outward supplies, not an extra liability added to 3.1.
Preserve disabled/not-applicable cells as specified by the form; missing evidence
must not silently become a zero amount.

## Delivery phases

### Phase 1 — Official format and rule baseline

1. Verify the current prescribed form, GST Portal guidance/advisories, offline
   utility/import contract and relevant CBIC provisions for the target periods.
2. Create a versioned mapping matrix: statutory table/row, legal classification,
   source facts, tax heads, permitted signs, rounding, validations and applicability.
3. Separate statutory computation from portal auto-population and any current
   edit restrictions. The public FAQ contains historical descriptions; confirm
   effective-date advisories before treating them as current portal behaviour.
4. Define all readiness blockers, review authority and acceptance examples.

Exit: reviewed table/field matrix and sample expected returns; supported periods
and profiles are explicit. No hardcoded guessed rates, limits or due-date extensions.

### Phase 2 — Company GST setup and source readiness

1. Reuse Identity's GST registration APIs and validation. Assess the documented
   missing company-registration settings form and add the required setup flow
   during implementation, rather than requiring users to enter GSTINs through APIs.
2. Add or complete dated filing-frequency configuration and registration/location
   mapping. Show which GSTIN a voucher and a return belong to.
3. Audit committed sources: sales/purchases, taxable and commercial notes,
   advances and adjustments, imports/customs, ISD, exempt/non-GST transactions,
   section 9(5), RCM, ITC reversals/reclaims and tax-payment evidence.
4. Check the operational source publication and calculation pipeline. The Purchase
   tax plan documents local outbox/replica and calculation-owner gaps; reassess and
   resolve prerequisites needed for genuine end-to-end GST recording.

Exit: explicit capability matrix. Missing categories are visible blockers for an
affected return; a supported complete nil case is distinguishable from absent data.

### Phase 3 — Statutory tax facts and return-period allocations

1. Extend existing owner contracts where necessary: Identity owns registration;
   Vouchers owns source documents/external evidence; Accounting owns committed
   tax effects and guarded adjustments; Reports consumes verified snapshots.
2. Preserve source document/revision, issuing GSTIN, recipient class/state,
   treatment, HSN/SAC, component, tax point, statutory reporting/claim period,
   original-note/advance links and the legal classification reason.
3. Capture import/customs and ISD evidence, RCM liability/payment/credit events,
   permanent/temporary reversal reasons, eligible reclaims and opening carryovers.
4. Keep posting-date fiscal controls separate from statutory period allocation;
   handle late-recorded documents and prior-period corrections explicitly.
5. Synchronize any models, one-DDL migrations, events, replicas, public schemas,
   OpenAPI and clients together; preserve old frozen-source readers.

Exit: native source contracts and reconciliation tests pass. No fabricated filing
classification from account names or unrestricted manual aggregate editing.

### Phase 4 — GSTR-3B calculations, table by table

Implement and finish each section in order: 3.1, 3.1.1, 3.2, 4, 5, 5.1, 6.1.
Each section ends with mapping review, populated examples and passing tests.

- Count taxable supply bases once across CGST/SGST components; allocate notes
  and advance adjustments by their statutory purpose and period.
- Keep zero-rated, nil-rated, exempt and non-GST classifications distinct.
- Separate import-service ITC from other RCM ITC; do not count it twice.
- Calculate Table 4 from period-specific claims, reversals and reclaims, including
  eligible earlier-period invoices. An as-of purchase-credit position is not 4(A).
- Reclaimed credit is included under the applicable claim row and disclosed in
  4(D)(1); the disclosure does not create credit a second time. Treat 4(D)(2)
  exclusions according to their official mapping rather than deducting twice.
- Respect cash-only RCM and section 9(5) ECO liability. Validate IGST utilization
  order, prohibited CGST/SGST cross-utilization and cess-only utilization against
  dated rules; interest and late fee cannot be discharged using ordinary ITC.
- Separate cash deposits, available statutory ledger balances and actual offsets.
  Show a proposed payment working when actual offset evidence is unavailable.
- Retain exact Decimal source amounts. Return output uses official precision and
  rounding, independent of the company's configurable display precision. Report
  in statutory INR using retained lawful currency-conversion evidence where needed.
- Nil-return eligibility considers inward disclosures, ITC activity, RCM, fees,
  interest and outstanding carryover liabilities; zero sales or zero tax alone is
  insufficient. Historical cash/credit balances alone are not current activity.

Exit: every prescribed cell has an explainable source calculation, permitted
sign/rounding behaviour and independent expected-result tests.

### Phase 5 — Reconciliation, exceptions and review lifecycle

1. Bridge books -> statutory tax events -> GSTR-3B sections -> tax heads and
   payments. Show timing and eligibility differences explicitly.
2. Support validated import of relevant GSTR-1/1A summaries, GSTR-2B/IMS evidence,
   previous filed returns, reversal/reclaim balances and statutory ledger/offset
   evidence. A 2B match alone does not establish every legal ITC condition.
3. Provide exceptions for missing GSTIN/state/treatment, unsupported profile,
   duplicate document/claim, missing import/RCM evidence, period mismatch and
   reconciliation differences. Link each exception to its vouchers and corrective
   owner workflow.
4. Freeze reviewed versions with source IDs, rule/schema versions, totals,
   exclusions and reviewer evidence. Keep Draft, Needs attention, Reviewed and
   externally Filed states distinct. Changes after review create a new revision.
5. Preserve filed history; GSTR-3B once filed is not a revisable return. Later
   corrections follow supported subsequent-period adjustment rules.

Exit: reconciliation gaps cannot be exported as an apparently complete filing;
actor/company/GSTIN scope and download-time revocation pass API tests.

### Phase 6 — Dedicated GSTR-3B page and user experience

1. Add a GSTR-3B card under Tax reports with applicability/readiness checks.
2. Use a compact header: GSTIN, financial year, month/quarter, filing frequency,
   source/review status, Prepare/Refresh, Export and Print/PDF.
3. Offer prescribed-form sections in their official order, with clear tax-head
   summaries and an Exceptions/Reconciliation view.
4. Clicking an amount opens its contributing vouchers, with search, appropriate
   filters, signed journal navigation and kebab row actions. Detail drawers stay
   outside table rows; returning retains period, GSTIN, page and selected columns.
5. Reuse Day Book/Tax workspace design tokens, calendars where appropriate,
   accessibility, empty/loading/error states and Light/Dark/Ledger themes.
6. The statutory form has fixed prescribed columns. Columns preferences apply to
   supporting transaction lists, never to the official form or its print layout.
7. Label source freshness and preparation/review actions accurately. Read access
   does not imply preparation, adjustment, review, export or filing authority.

Exit: desktop/mobile review and UI tests pass for every section and permission
branch. GSTIN/period changes cannot show another selection's apparently ready form.

### Phase 7 — Prescribed print and export formats

1. Produce a statutory-layout PDF: fixed table/row numbering, official headings,
   tax-head order, GSTIN/period, required declarations and complete totals. Mark
   draft/review status and retain provenance without crowding statutory cells.
2. Design section-aware pagination and repeated headings; do not use the generic
   register's column-band layout for a prescribed GSTR-3B form.
3. Export Excel with a form-aligned summary, voucher workings, reconciliation and
   exceptions sheets. Export CSV for supporting details with exact amounts.
4. Enable GST Portal JSON only against a verified official utility/schema and an
   actual supported import workflow. Validate schema, precision, signs, state
   codes, GSTIN, period and all cross-table totals; a generic JSON file is not an
   accepted filing artifact. If unavailable, deliver the reviewed preparation
   package and keep the upload-format readiness issue explicit.
5. Reuse private downloads, access revocation and full-result export processing.

Exit: compare populated PDF/Excel against official examples, inspect every page,
validate generated artifacts and prove PDF preview matches the downloaded file.

### Phase 8 — Final end-to-end review and fixes

Run each statutory section through correctness, security, UI/style, export and
end-to-end review. Fix findings, then rerun affected regressions.

Required scenarios: CGST/SGST, UTGST, IGST and cess; exports/SEZ with applicable
payment/LUT treatment; exempt/nil/non-GST; applicable notes and service advances;
section 9(5) roles; RCM paid/unpaid and credit timing; imports/ISD; earlier-period
claims; permanent/temporary reversal and reclaim; section 16(4)/PoS restrictions;
monthly/QRMP and regime transitions; multi-GSTIN isolation; late corrections;
nil versus non-nil zero liability; foreign currency evidence; missing-source
blockers; actual offset versus cash deposit; rounding; denied/revoked access;
retry/idempotency, frozen history and every supported artifact.

Use disposable native databases and independently calculated expected returns.
Do not create synthetic live company postings solely for testing. Verify real
positive workflow in the authorized test environment once source readiness is
complete, followed by final all-theme desktop/mobile and print review.

Exit: all section totals, reconciliations, permissions, workflows and exact
artifact formats pass. Publish the reviewed evidence and remaining explicit
capability limits before enabling preparation for a legal profile.

## Sources and decision log

- [GST Portal GSTR-3B FAQ](https://tutorial.gst.gov.in/userguide/returns/GSTR3B.htm),
  retrieved 2026-11-02. It documents GSTIN/period filing, monthly/quarterly
  frequency, 3.1.1, Table 4 mappings, nil eligibility, cash-only ECO liability,
  prior-period liability breakup and the inability to revise a filed GSTR-3B.
  It specifically states that advances no longer flow into Table 3.2 from the
  October 2025 tax period. Confirm applicable advisories/schema in Phase 1;
  historical FAQ descriptions are not a substitute for a dated portal contract.
- [India voucher tax recording](voucher-tax-recording.md), especially native
  statutory dates, ITC/RCM evidence and Reports/Accounting/Vouchers ownership.
- [Company registration model](company.md) and
  [existing tax-accounting implementation](tax-accounting-plan.md).
- [Current tax-report review](tax-reports-review.md) and
  [Purchase GST source-readiness findings](purchase-tax-entry-plan.md).
- 2026-11-02: user requested a phase-wise GSTR-3B plan without code changes.
  Scope is preparation/reconciliation and prescribed artifacts. Applicability is
  GSTIN/regime/period-specific; current working tax registers remain separate.
- 2026-11-02: user subsequently authorized implementation of all phases and final
  review/fixes. Identity retains dated registration/filing preference ownership;
  Accounting retains committed statutory evidence and snapshot publication;
  Reports prepares and reviews frozen return versions and private artifacts.
- 2026-11-02: implementation and final review delivered; see
  [delivery and review](gstr3b-delivery.md) for native/UI/artifact evidence and
  source capability limits. The current rules cover October 2025 onward.
  Preparation requires scoped posting, finance-management or report-management
  authority. Statutory row order is frozen explicitly because MySQL JSON object
  order does not preserve form order. Portal-upload JSON remains unavailable
  until an official schema and actual import workflow are verified.
- 2026-11-02: subsequent GST/GSTR-3B review clarified statutory rounding: aggregate
  source records within each leaf cell first, round that cell to two decimals,
  then derive totals and payment/net-credit workings from the displayed cells.
  Four-decimal source evidence remains immutable. The portal guide also maps
  ECO Table 15/15A into both 3.1.1(i) and 3.2; only supplier 3.1.1(ii) remains
  excluded from that disclosure ceiling. Historical opening cash/credit and
  previous-return amounts alone do not disqualify an otherwise supported Nil
  return. See [final review](gstr3b-final-review.md) for regression evidence.
