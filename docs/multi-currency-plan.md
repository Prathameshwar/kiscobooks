# Optional multi-currency: review and implementation plan

Status: implementation authorized, 2026-10-12. Release activation remains a separate
verified gate. India GST is the first statutory profile. Payroll is excluded.

Implementation checkpoint, 2026-10-12: **P1-P3 are in progress; P4-P7 are not
complete.** No foreign invoice, statutory tax, settlement or revaluation profile is
approved for release by this checkpoint. The original phase acceptance gates below
remain binding.

## Review of the current platform

| Owner | Present | Gap to close |
| --- | --- | --- |
| Identity | Company base/reporting currency, ISO reference choices and `multi_currency` feature; base currency locks after first posting and the feature ratchets after a foreign posting reservation is confirmed. | No company allowed-currency/rate/override policy. Foreign bank master can be entered without an explicit company currency policy. Reporting currency is presentation metadata, not translated statements. |
| Catalog | Currency-specific price books and a feature check for foreign prices. | No company currency allowlist, foreign price effective-date/retirement gate, or controlled choice between explicit foreign price and conversion of a base price. |
| Vouchers | Currency on all revisions, rates on financial/invoice details, per-kind `foreign_currency_allowed` money policy. | Header currency is not consistently gated at draft/issue/accept; non-posting orders need the same policy. Rates lack immutable source/date/purpose evidence. Invoice tenders are limited to invoice currency. |
| Accounting | Original/base journal amounts, BASE/FIXED/MULTI accounts, feature-gated foreign journal posting, same-currency open-item allocation and realized FX journal. | No reviewed FX rate book; direct journal rates are caller-entered. Invoice preview explicitly rejects non-base currency and rates other than 1. No cross-currency settlement contract or unrealized FX revaluation. |
| Tax | Dated GST rules and invoice tax calculation. | Foreign invoice admission is blocked; accounting conversion cannot be reused as the statutory GST conversion without a separate rule-specific rate/date. |
| Reports | Original/base GL and open-item facts, base-currency statements, single-currency transaction views, reconciliation. | No rate-usage register, currency exposure/aging, realized versus unrealized FX bridge, revaluation report or genuine translated reporting-currency statements. |
| Inventory | Proposed valued stock owner and warehouse/report work remain under B20-B27. | Foreign purchase capitalization and stock/GL value bridge depend on that owner; no foreign-priced stock posting can bypass the stock release gate. |

The existing fixed `DECIMAL(19,4)` money storage and ISO minor-unit metadata remain.
Rate precision is a separate decision: current `NUMERIC(19,8)` may be insufficient for
some quote directions, and reciprocal rates must never be calculated with binary float.

## Contract to preserve

1. One immutable company **base/functional ledger currency**. The optional
   `reporting_currency` is only display metadata until a separately verified
   translation feature exists. Every posted journal balances in base currency; original
   amounts stay separated by currency and account.
2. `multi_currency` is off by default. It, the company currency policy, the voucher-kind
   setting, account currency mode and posting authority must all admit a foreign document.
   Drafts/quotes/orders may be edited without ratcheting the feature; the first committed
   foreign financial posting locks it. Removing an allowed currency stops **new** documents
   but never strands existing bills, returns or reversals.
3. Store rates as **foreign unit to one base unit amount** with explicit direction, exact
   Decimal arithmetic, source, rate date/time zone, purpose, revision, maker/checker,
   approval and override reason. The posting snapshot carries the chosen rate ID and
   exact rate; a later corrected quote cannot change posted money. Missing, stale,
   contradictory or unpublished rates fail closed. No implicit reciprocal or cross rate.
4. Separate accounting/posting rate from statutory rate. Initial recognition, monetary
   balance remeasurement and settlement FX each have different events. Tax point/date
   and rule-selected statutory rate may differ from journal posting date/rate. Capture
   foreign taxable basis, INR taxable basis and INR component amounts with both rate
   lineages. Base-only rounding/FX lines have explicit components and reconcile to the
   original-currency lines without inventing foreign consideration.
5. One commercial currency per quote/order/invoice; general journals may have multiple
   currencies with line-level rates. No implicit mixed-currency tender or bill allocation.
   Cross-currency settlement must be a separately typed conversion/clearing operation
   with two cash legs, its own rate/spread/fees and realized FX; an ordinary allocation
   remains same-currency. Refund/credit note links preserve original invoice currency
   and legally appropriate rate dates.
6. Historical-cost inventory is capitalized in base currency at its receipt/recognition
   contract and is not revalued by a later currency closing rate. Open foreign cash,
   receivables and payables are monetary balances eligible for period-end remeasurement.
   Advances/prepayments require explicit classification and cannot silently become FX P&L.

## Delivery phases

Each phase ends with migrations, models, schemas, OpenAPI/clients, native permission and
audit contracts, integration tests and a working repository. Where a service publishes
currency facts, update every consumer and replay/rebuild path in the same phase.

### P1 — Company and voucher currency controls

- Identity owns effective company policy: allowed transaction currencies, new-document
  enable/disable dates, manual-rate permission, maximum override deviation, rate staleness,
  rounding policy, and role-separated approval. Base currency is mandatory. Foreign bank
  account activation and Catalog foreign price authoring must consult that policy.
- Add typed voucher-kind/class controls for foreign header currency, allowed currency set,
  whether rates may be overridden, and whether a foreign quote/order may issue. Enforce
  at draft save, issue, acceptance, posting and replay; do not rely on UI hiding fields.
- Publish versioned policy evidence to Vouchers, Catalog and Accounting. Keep feature
  ratchet and first-posting base-currency immutability; test enable/disable races,
  stale snapshots, historic settlement and tenant/object scope.

### P2 — Governed rate book and conversion preview

- Accounting owns append-only `exchange_rate_quote` revisions, with company, from/to,
  purpose (`ACCOUNTING`, `GST_GOODS`, `GST_SERVICES`, `REVALUATION`, `SETTLEMENT`),
  effective date, source kind/reference/hash, exact rate, status and approval evidence.
  Use indexed as-of lookup, unique approved resolution and explicit supersession.
- APIs: create/import candidate, review/publish/withdraw, list with filters, effective
  rate preview and conversion preview. Start with controlled manual/CSV imports; a future
  rate provider is an adapter, not an authority bypass. Validate ISO code and precision,
  reject zero/negative/overflow rates, ambiguous same-date approvals and stale quotes.
- Define conversion calculation and residual allocation once in a shared execution
  contract; retain original and base amounts at every posting grain. Choose rate storage
  precision after boundary tests for small/large currencies; migrate existing rate columns
  only if the contract needs wider precision.

### P3 — Foreign journals, banking and open items

- Make direct Accounting journal and voucher money entry select published rate evidence
  or an audited approved override. Validate line rate against company policy, account
  BASE/FIXED/MULTI mode, bank currency, tender currency and voucher-kind configuration.
- Preserve same-currency bill adjustment and existing realized-FX path. Add explicit
  foreign receipt/payment/advance/refund scenarios, partial payments and reversal parity.
  Provide a distinct cross-currency conversion/settlement command; never net USD against
  EUR by pretending the currencies match. Reconcile bank statement currency and posted
  cash/bank account currency, including bank fees and spread.
- Add idempotent rate-usage facts and FX lineage to journals/open items/allocations.
  Test multi-rate journals, base balancing/residuals, duplicate/retry, backdating,
  fiscal locks, rate corrections after posting and concurrent settlement.

### P4 — Foreign sales/purchases/returns and pricing

- Lift Accounting's current base-only invoice rejection after accepted preview includes
  rate ID/revision, rate date and exact accounting conversion. Vouchers binds the preview
  hash and the owner revalidates it at posting. Calculate each commercial component in
  invoice currency, then allocate base values deterministically; GL, party bill, credit
  control, tender and source invoice reconcile at both grains.
- Explicit currency-specific Catalog price wins; do not silently convert an INR price to
  USD. If converted pricing is enabled later, require a named policy, reviewed quote,
  quote-date/rate source and accepted price snapshot. Orders/quotes carry currency and
  price evidence without posting. Fulfillment inherits or explicitly re-quotes it.
- Returns and credit/debit notes retain source currency and quantity/amount lineage;
  any different settlement rate produces separately identified FX rather than changing
  the original sale/purchase. Stock-linked purchases wait for B20-B27 valued movements.

### P5 — India GST and statutory foreign-currency invoices

- Implement a statutory conversion resolver distinct from P2 accounting conversion:
  under current CGST Rule 34, taxable **goods** use the Customs-notified exchange rate
  for their time of supply; taxable **services** use the applicable GAAP rate for their
  time of supply. Version the rule and source/date evidence; do not infer tax rate from
  payment date or the accounting exchange rate.
- Compute tax in INR on resolved INR taxable values, with charge/discount allocation,
  tax-inclusive prices, multiple taxes/cess, RCM, ITC and source-linked return treatment.
  Preserve invoice-currency commercial totals and INR statutory registers separately.
  Block any foreign taxable profile without complete supported statutory evidence.
- Test goods versus services, GST changes across dates, mixed taxes, tax credit notes,
  exports/zero-rated profiles where configured, supplier invoice differences and
  statutory-rounding bridges. Jurisdiction packs outside India remain disabled until
  independently specified.

### P6 — Revaluation, year close and reports

- Accounting period-end `fx_revaluation_run` and detail facts cover only eligible open
  monetary balances. Pin closing rate, source carrying value, revalued base value,
  unrealized gain/loss account, period and reversal/delta policy. Run once per period
  with idempotent correction and reopen handling; distinguish realized FX on settlement
  from unrealized FX at close, avoiding double recognition.
- Reports provide base GL/TB/P&L/B/S plus per-currency account/bank/party ledgers,
  outstanding/aging, currency exposure, rate usage, FX realized/unrealized registers
  and GL/subledger bridges. A translated `reporting_currency` statement is a separate
  subphase with current/historical/average-rate rules and translation reserve; keep it
  unavailable until those rules and comparative/year-close tests pass.
- Rebuild/report snapshots preserve rate lineage, posting/base/statutory dates and
  currency-aware permissions. Test two fiscal years, close/reopen, partial settlement,
  revaluation reversal and mixed-currency source-to-GL-to-report reconciliation.

### P7 — Release evidence and staged activation

- Seed no live rate or statutory fact by assumption. Rehearse base-only companies with
  `multi_currency` off, then gated foreign journals/payments, invoices, tax and reports
  by capability. Run native MariaDB migration round trips, multi-service broker replay,
  audit/permissions, rate import failure, backup/restore and two-year close scenarios.
- Activate each foreign posting profile only after its P1-P6 evidence is green. Keep
  unsupported foreign goods/stock, taxable profiles or cross-currency settlement blocked
  until their corresponding owner path is verified. Existing base-currency behavior must
  be byte-for-byte compatible unless a documented contract version changes.

## Decisions to settle before implementation

1. Rate direction is foreign-unit to base-unit. Reviewed quotes now use exact
   `NUMERIC(27,12)`; amount storage remains `DECIMAL(19,4)`. ISO minor units govern
   rendering, not accepted ledger storage. Boundary tests and a later scale change are
   needed before activating currencies whose quotes exceed this range.
2. First rate source is reviewed manual/CSV only. Automated provider requires source
   licensing, availability, historical correction and quality checks.
3. India AS 11 is selected for the first release. Define the exact advance, foreign
   bank and period-end reversal policies as a versioned accounting-policy choice;
   do not infer every company's accounting framework from country alone.
4. Which foreign invoice tax profiles go live first. An unsupported GST/export combination
   must fail closed, even with a valid accounting rate.

Selected 2026-10-12: approved manual and CSV rates first. Automated rate providers are
deferred until source licensing, historical corrections and quality checks are specified.

## Implementation ledger

| Phase | Current evidence | Remaining release work |
| --- | --- | --- |
| P1 | Identity company allowance and signed context, foreign bank activation guard, Catalog source projection/foreign price authoring guard, voucher-header and Accounting account/journal admission guards. Focused tests and migration checks pass. | Effective-date/override policy, instantaneous disable race, voucher-kind/class currency policy, replay and native multi-service evidence. |
| P2 | Accounting reviewed quote table with unique approved date/purpose resolution, maker/checker API, manual/CSV candidate import, exact-date lookup, bounded list, detail and conversion preview. Focused workflow and audit tests pass. | Posting rate selection and immutable usage facts, source correction policy, native MariaDB round trip, rate-usage report and full approval/idempotency stress evidence. |
| P3 | When a posted journal line matches an approved exact-date Accounting quote, Accounting records immutable `exchange_rate_usage` evidence; direct manual journal entry rejects a different rate while such a quote is active and rejects a withdrawn reviewed quote. | Governed-rate admission is not yet mandatory when no quote exists; foreign bank/open-item flows, overrides, cross-currency settlement, retry/period-close and full native evidence remain. |
| P4-P7 | Existing base-currency owner behavior remains available; unsupported foreign taxable invoices remain rejected. | Foreign invoices/pricing/returns, separate GST Rule 34 conversion, revaluation/reporting and staged release evidence. |

The quote book is a reviewed input with selective journal usage capture, not yet the
mandatory authority for every journal or voucher posting. The platform still accepts
some legacy caller-supplied foreign journal rates; release activation must wait for P3
to bind every posted rate to an immutable approved quote or explicit reviewed override.
Existing foreign stock posting additionally waits for the
valued-stock owner acceptance evidence recorded in the voucher delivery tracker.

## Source anchors

- [ICAI Accounting Standard AS 11](https://kb.icai.org/pdfs/69239asb55316-as11.pdf):
  foreign monetary items use a closing rate; historical-cost non-monetary items retain
  transaction-date conversion.
- [IFRS IAS 21](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2022/issued/part-a/ias-21-the-effects-of-changes-in-foreign-exchange-rates.pdf?bypass=on):
  recognition and subsequent measurement framework where applicable.
- [CBIC current CGST Rules, Rule 34](https://taxinformation.cbic.gov.in/content-page/explore-rules/1000120/1000001):
  goods and services have different statutory exchange-rate sources.
