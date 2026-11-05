# Accounting masters and financial posting

Status: master scope and later finance/tax increments implemented; the Vouchers integration
and Accounting stock/value extension proposed on 2026-10-10 remain future work.

The [company financial-year design](voucher-financial-year-design.md) adds required planned
new-year readiness, stable cross-year balances/references and distinct statutory/posting
number identities. Accounting owns fiscal generation and period transitions, including
existing permitted reopening; D12 adds producer evidence and report-cache invalidation.
Annual earnings-transfer automation remains deferred, without blocking continuous books.

The [account recording/maintenance design](voucher-account-recording-design.md) keeps
`journal`/`journal_line` as the GL and open items/allocations as the reconciled subledger.
Account definitions hold no editable balances. Reports derives scoped ledger/register
views and optional day/period summaries with source checkpoints and verified generations.

## Boundary

Accounting owns heads, groups, all posting account identities, party identities and
roles, party addresses/contacts/registrations/beneficiaries, payment terms, credit
policies, commercial classifications, templates and posting mappings. Accounting also owns
implemented journals, openings, fiscal controls, open items, allocations, credit and charges
under the [finance contract](accounting-finance-contract.md).
Identity retains company identity, company registrations/banks, permissions, field
policies, feature flags and calendar configuration. Existing company commercial
defaults are setup inputs; issued documents never resolve mutable defaults again.

The [Vouchers plan](vouchers-plan.md) replaces the future Billing/Payments APIs with one
document/workflow API. Accounting remains the authoritative posting owner. The proposed
stock/value extension is not implemented; existing journal/source-document tax and financial
controls are. Annual closing/carry-forward remains deferred. No distributed SQL atomicity is
claimed, and no existing Accounting data or route is moved. Payroll/HR is out of scope.
The planned [India voucher tax extension](voucher-tax-recording.md) also separates statutory
dates from GL posting, purchase tax from claimable credit, and RCM liability from payment/credit.
It adds job-work/return evidence and state-VAT gates; the implemented tax paths below do not
claim that broader coverage. Keep old snapshots readable and extend the contracts explicitly.
Vouchers' [shared document model](voucher-data-model.md) reuses this service's common journal,
source-document, tax and allocation authority. Complex invoices require explicit adapter
extensions and bound checks; their common document tables do not replace Accounting's ledger.
The [posting and financial-reporting design](voucher-posting-reporting-design.md) records
planned owner exports, native statement classification and opening/earnings/stock/tax
bridges for ledgers, trial balance, P&L/Income & Expense and Balance Sheet. These Reports
capabilities are not implemented by the current balance endpoint or financial event v1.

## Model

Head means one of Assets, Liabilities, Equity, Income, Expenses. Groups and subgroups
share a hierarchical table. Every posting identity is an `account`; kind-specific
profiles extend it. A party can have customer and supplier roles and several accounts
without duplicating addresses. Receivables/payables are not automatically netted.

The 30 business tables are: account_head, account_group, account_group_alias, account_group_closure,
account, account_alias, account_external_key, party, party_role, party_address,
party_address_use, party_contact, party_contact_use, party_identifier,
party_tax_registration, party_registration_address, party_bank_account,
party_commercial_type, party_commercial_type_membership, payment_term,
payment_term_line, party_accounting_policy, party_credit_policy, account_tax_profile,
account_bank_profile, accounting_setup, account_template_installation,
account_template_binding, account_posting_mapping, account_tax_default. Infrastructure tables
are separate. Four read-only replica tables mirror Catalog's GST definitions —
tax_classification_replica, tax_rule_replica, tax_rate_replica, tax_rate_component_replica —
written only by the `accounting.catalog_tax.v1` consumer, never through the API.

## Invariants

- Tenant filtering is session-level; company references are checked and constrained.
- One immutable account identity for each posting ledger; balances are never master fields.
- Draft/active/inactive for editable masters; effective date intervals for amount policies.
- Hierarchy updates serialize through company setup and reject cycles/depth above ten.
- Used/system identities cannot change financial classification; retirement keeps history.
- Writes require idempotency, expected versions on edits, current permissions and fields.
- Audit/outbox and business effects commit together. Audit payloads contain references
  and changed field names, never addresses, beneficiary numbers or tax identifiers.
- Currency is explicit and amounts use Decimal(19,4). Float amounts are rejected.
- Address defaults are per party, purpose and optional registration; general and scoped defaults
  coexist. Explicit registration associations preserve country, state and date consistency.
- Terms/credit/mapping overlap is rejected under the company lock. Credit configuration
  is not live enforcement. Future credit reservations require a separate financial phase.
- Posting consumers must snapshot party details, registration, terms and mapping versions.
- Company bank profiles reference Identity; party bank beneficiaries belong to Accounting.
- National personal identifiers are prohibited; business identifiers have typed schemes.
- Lists use bounded signed keyset cursors and allowlisted filters; exports enforce fields.

## Delivery

See [the phase checklist](accounting-implementation-todo.md). Backend reuses the shared
platform. Migrations have one DDL statement per revision; seed contents are versioned
separately. The administration form reads field metadata. Import preview performs the
same validation as application and application rechecks permissions and versions.

## Withholding (TDS/TCS) masters

Four company masters follow Tally's TDS/TCS nature-of-payment model:

- `withholding_section` holds the status-managed nature of payment/collection, keyed by kind and code.
- `withholding_rate` holds dated rates per section and deductee type, with the normal rate, the no-PAN rate, optional single-transaction and aggregate-annual thresholds, and a threshold basis of TRANSACTION, AGGREGATE or EXCESS.
- `party_withholding_profile` holds the dated deductible flag, deductee type, PAN status, the verified PAN identifier and the default section, per party and kind.
- `withholding_certificate` holds dated lower/nil deduction certificates, with an optional amount limit.

Accounting ships no statutory sections, rates or thresholds in code, seeds or migrations. Each rate and certificate records `source_reference`, an official https `source_url` (`.gov.in`/`.nic.in`) and the `source_sha256` of the cited document.

Writes need the company's `tds` or `tcs` feature, otherwise they return 409 `FeatureNotEnabledError`. Overlapping intervals per (section, deductee type), (party, kind) or (party, section) conflict. A rate revision names its predecessor through `supersedes_id`, and must start the day after the predecessor ends.

`POST /withholding-previews` is read-only and needs `accounting.withholding.read`. It resolves the profile, rate and certificate effective on `posting_date`. Precedence is: certificate (up to its remaining limit), then the no-PAN rate if the PAN is not verified, then the normal rate. The preview takes year-to-date amounts from the caller. It does not post, accumulate or reserve anything.

Posting purposes TDS_PAYABLE, TCS_PAYABLE, TDS_RECEIVABLE and TCS_RECEIVABLE are in the mapping catalogue (tax-accounting Phase 3, revision 0094; see the [master contract](accounting-master-contract.md)). Party documents post withheld amounts through them (see § Tax).

## Tax

Tax on accounting vouchers (tax-accounting plan Phase 8) is added to existing flows, without new voucher
types. It applies to manual journals (`JournalCreate.tax`) and to INVOICE, BILL and PAYMENT source
documents (`SourceCreate.tax`). Everything resolves by `posting_date` from local rows: account tax
defaults, the Catalog GST replica, posting mappings, party GST registrations, the withholding masters
and the signed Identity company context. No synchronous cross-service call is made.

- **GST.** A taxable line is one on the direction's side (credit for SALE, debit for PURCHASE) whose
  account has an `account_tax_default` for that direction on the date. Resolution order:
  1. the default;
  2. its replica rule;
  3. the one rate effective on the date for the supply context;
  4. the place of supply;
  5. `tax_calc.compute`;
  6. tax lines through the posting mappings, scoped to the charging registration: `OUTPUT_<c>`
     for SALE, `INPUT_<c>` for recoverable purchase credit.
  For party documents, the GST default sits on the counterpart account. The company registration
  is the named one, or else the single supplier-class `gst_in` registration covering the date. The
  UTGST state list is service configuration (`utgst_states`).
- **Purchases.** The supplier's state is the origin. Imports and SEZ supplies to the company are
  inter-state and taxable. A composition, unregistered, UIN or overseas supplier charges nothing
  unless reverse charge applies. Input credit is recovered only when the default is ELIGIBLE and
  the company regime recovers input (`regular`). Otherwise the tax is debited to the line's own
  account as cost.
- **Reverse charge.** A default with `rcm_applicable` credits `RCM_<c>` with the tax. The debit
  side follows the same ITC rule. The supplier's party amount excludes reverse-charge tax. Forward
  and reverse charge cannot be mixed on one voucher.
- **TDS/TCS.** TDS applies to BILL and PAYMENT, and TCS to INVOICE, through `resolve_withholding`.
  - It needs the `tds` or `tcs` company feature (409 otherwise).
  - The base is the taxable value for BILL, the amount paid for PAYMENT, and the gross for INVOICE.
  - Year-to-date counted and withheld bases, and certificate consumption, are summed from posted,
    unreversed `journal_tax` rows of the fiscal year.
  - TDS reduces the party amount (BILL) or the cash leg (PAYMENT) and credits `TDS_PAYABLE`.
  - TCS raises the invoice amount and credits `TCS_PAYABLE`.
  - Withholding is not available on manual journals.
- **Party amount.** Each document states its party amount. If it differs from the amount after
  tax, the result is a `PARTY_AMOUNT_MISMATCH` exception.
- **Tax Analysis.** `POST /voucher-tax-previews` is read-only and needs `ledger.read`. It returns
  a status of `READY` or `EXCEPTION`, coded exception reasons, the generated lines and, when ready,
  the snapshot. Drafting or editing a voucher with exceptions returns 422 with the codes in
  `fields`.
- **Evidence.** A taxed draft writes the entered lines plus the generated lines, which may reach
  TAX accounts that refuse manual posting. Its `journal_tax` row (one per journal) stores:
  - the request;
  - the snapshot and its SHA-256;
  - the entered line count;
  - the summary columns.
  The row is created and audited through the outbox in the same transaction. Tax presence cannot
  change on a draft edit. An edit re-resolves the analysis and updates the row.
- **Posting.** Posting re-derives the analysis from the stored request after `assert_postable`.
  - A new exception refuses the post (422).
  - Any other difference in the hash or the lines refuses it with 409 ("recalculate the
    draft"). For example, another posting can move the TDS year-to-date.
  Posted vouchers are never recomputed. Corrections are reversals.
- **Limits.** Only the base currency is supported (`FOREIGN_CURRENCY` otherwise). Assessable
  charges are not applied on vouchers. A fixed per-unit cess has no quantity on a voucher, so it
  returns `COMPUTATION_REFUSED`.

## Decision log

- 2026-10-10: Financial-reporting review added explicit source-export, classification and
  reconciliation requirements. Accounting remains fact authority; Reports owns rebuildable
  outputs. Entered openings count once; annual-close automation remains deferred.

- 2026-10-10: Linked the user-selected shared Vouchers model. Reuse existing generic journal,
  tax and settlement structures; validate adapters for multiline invoices, advances and split
  tenders before enabling them. No per-voucher-kind Accounting table family is proposed.
- 2026-10-10: Linked the required India voucher tax extension. Accounting remains tax/ledger
  authority; statutory dates, ITC/RCM lifecycles, job work and state-VAT support need the future
  T0-T5 contracts/tests rather than being inferred from existing GST journals.
- 2026-10-10: Updated the boundary to reflect implemented financial/tax increments and the
  user-selected Vouchers replacement for Billing/Payments. Retained Accounting financial
  authority; stock/value posting is proposed under V0 rather than claimed as implemented.

- 2026-10-06: Tax-accounting Phase 8, tax on vouchers (see § Tax). Tax is a block on journals and
  on INVOICE, BILL and PAYMENT source documents, not a new voucher type.
  - The Tax Analysis is stored in a new `journal_tax` table (revision 0108). It is re-derived and
    compared at posting, never recomputed after posting.
  - The UTGST state list is service configuration, because no shared reference data exists for it.
  - Tax presence is fixed once a draft exists.
  - Withholding year-to-date comes only from posted `journal_tax` evidence.
  - Replica rows now record `source_action` (revisions 0104–0107). A withdrawal is therefore never
    treated as effective, and rows replicated before the revision default to PUBLISH.
  - Permissions are reused: `ledger.read` and `ledger.post_journal`.

- 2026-10-06: Tax-accounting Phases 5 and 6 (Accounting side). A Catalog GST replica (revisions
  0095–0098) is maintained by `accounting.tasks.catalog_tax_worker` from Catalog-signed,
  outbox-published `catalog.tax_{classification,rule,rate}.changed` version 1 events, deduped by
  message id and ordered by Catalog's company policy generation (`source_version`): equal or older
  generations are ignored, and a newer one may change only end dates, a rule's name/active flag or
  a classification's description — anything else is refused to the DLQ rather than rewriting
  history. Withdrawal mirrors Catalog (end date, or inactive rule); replica rows are never
  deleted or audited by Accounting. `account_tax_default` (revision 0099) is a dated master —
  Tally's GST details on an income/expense/asset ledger — keyed for overlap by (account,
  direction) under the company lock, referencing a same-company active replica rule whose item
  kind and treatment match. It reuses `accounting.tax.read/manage` instead of new permission keys:
  it is the same administrative trust as `account_tax_profile`. See
  [tax-accounting-plan](tax-accounting-plan.md) Phases 5–6.

- 2026-09-14: Address review: registration-address list projections expose both endpoint
  IDs under existing field permissions. This closes an ambiguous association-list response
  without adding personal address content or changing the database schema.
- 2026-09-13: User approved dedicated Accounting and unified accounts with supporting
  party tables. User explicitly deferred all Billing/Catalog use and impact work.
- 2026-09-13: Heads are fixed classification roots, not a second posting ledger master.
- 2026-09-13: Administration screens are out of scope. Delivery is API and database
  only; generated OpenAPI and the typed client remain in scope as contract artifacts.
- 2026-09-13: The chart of accounts follows Tally Prime. Groups gain Tally's behaviour
  attributes and group aliases, taking business tables from 28 to 29; the seed grows
  from 25 to Tally's 28 predefined groups.
- 2026-09-13: Five heads are kept, including Equity, for Schedule III presentation.
  Tally's four natures map in and out by folding Equity into Liabilities.
- 2026-09-13: Cost categories and cost centres are deferred. They only earn their place
  once vouchers post allocations, which is itself deferred.
- 2026-09-13: Opening balance is not a master field. A balance is a posted fact, and an
  amount on `account` that no journal backs would be a second source of truth.
- 2026-09-13: `account_tax_profile` holds duty classification only. Tax rates stay in
  the Catalog tax master, so an invoice has one rate authority.
- 2026-09-14: Integrity/security repair of the existing 28-table implementation is
  separate from the planned Tally extension above. No schema or migration changes.
  See [the review](accounting-review-20260914.md) for evidence and operational wiring.
- 2026-09-14: Role identity, commercial-type role and payment-line ownership are
  immutable. Bank/tax profiles may change only while their account is unused and
  DRAFT. Group head changes require an account-free subtree, including inactive
  accounts; moving a group remains subject to the financial-use guard.
- 2026-09-14: Effective history cannot be reopened after its end date. Current
  effective rows may change only their end date, which cannot move into the past.
  Dependent date intervals must fit their parents, including company registrations
  supplied by Identity. Parent edits must preserve existing child coverage. Active
  resources revalidate reference eligibility on every update. Owned profiles and
  schedule lines remain attached when an otherwise unused parent retires.
- 2026-09-14: Field policy evaluates native typed full snapshots before and after
  edits, and resulting state on creation. Initialization and templates enforce
  implicit field changes. Reads without full snapshots apply conditional denies
  conservatively; history filters changed-field names. Identity administers native
  Accounting policy/layout from a generated service-owned contract, without cross-service
  model imports or granting Accounting custom-field definitions.
- 2026-09-14: Template version 2 uses all registration UUID bits. Reinstall preserves
  compatible version 1 account identities and historical bindings while creating
  distinct accounts for previously collided registrations. Import receipts store
  ordered references so every valid 200-row request fits the receipt size limit.
- 2026-09-14: Accounting has a generated typed client, authenticated nginx context
  forwarding and a separate confirmed outbox publisher using the existing shared
  mechanism. Deployment must configure matching Audit source credentials and supervise
  the publisher. Neither tests nor installation silently drain an existing outbox.
- 2026-09-14: The approved master completion adds group aliases and ten group metadata fields,
  account inventory/rounding/order and duty classification. The base v3 chart has 28 groups,
  15 primary and 13 subgroups. Equity remains an internal head; its external Tally nature
  maps to Liability. See the [master contract](accounting-master-contract.md).
- 2026-09-14: Revisions 0038–0072 extend the original schema without rewriting history.
  Metadata version 1 is initialized for new companies; existing companies require an explicit
  audited, transactional backfill. Pending metadata blocks data access including receipt replay.
  Template v3 preserves IDs/names/bindings and permits only the reviewed unused Reserves correction.
- 2026-09-14: Duty type OTHER preserves legacy meaning. New GST/VAT profiles require matching
  registrations; other duty classifications support registration-free profiles. Rounding requires
  an explicit positive Decimal limit and unambiguous account currency. No financial execution added.
- 2026-09-14: Exports use per-resource typed routes at unchanged URLs. Decimal input contracts
  use strings; 201 Location is relative to preserve a gateway prefix. Identity field contracts,
  resource matrix and TypeScript declarations are generated alongside source changes.
- 2026-09-14: Final reviews unify template preview/install account matching and reject
  incompatible existing system identities. Aggregate template responses require readable
  classification fields; history has a dedicated query contract. Implicit template evidence
  writes honor field policy, and setup currency/template-version changes are versioned and
  audited. Generation remains internal coordination, not a separate business edit.
- 2026-09-14: The additional final review closes account/profile dependency gaps. An existing
  tax/bank profile retains account kind; account edits and activation revalidate tax purpose
  against the resulting head. Read-only mapping validation requires readable input fields,
  preventing validation outcomes from revealing denied draft values. No schema changes.
- 2026-10-05: Tax-accounting Phase 3. Catalog tax evidence version 2 names the company
  registration and types its components (CGST+SGST, CGST+UTGST or IGST, each optionally with
  CESS); version 1 remains readable and acceptable only without components, so its signed shape
  never changes. Charging resolves that supplier-class registration on `posting_date` from the
  signed Identity context and refuses regimes that may not charge tax; each component's account
  profile must match component, OUTPUT_PAYABLE and registration. Regime checks are per
  registration row (rows are regime-immutable and dependants fit their windows). Posting
  purposes gain CESS, reverse-charge and TDS/TCS entries through an explicit purpose table
  instead of a name suffix; BANK_RECEIPT may use an overdraft bank account under LIABILITY.
  Party registrations gain SEZ_UNIT, SEZ_DEVELOPER, UIN, OVERSEAS, CASUAL and NRTP;
  UNREGISTERED has no number and records the buyer's state; GSTINs use the shared
  checksum/state-prefix helper; one GST status (regular, composition or unregistered) per party
  and state at a time. The GST template gains no cess accounts (notified goods only; a template
  hash change would affect existing installs). Migrations 0089–0094. See the
  [master](accounting-master-contract.md) and [finance](accounting-finance-contract.md)
  contracts.
- 2026-10-05: TDS/TCS withholding masters (revisions 0100–0103) follow Tally's
  nature-of-payment model. Statutory content is tenant-maintained data with official-source
  evidence, never shipped. Writes are feature gated with 409. A distinct
  `accounting.withholding.*` family is used. The preview is read-only, and posting
  mappings are deferred. The deductee-type list (13 values) awaits confirmation.

### Financial-year planning decision - 2026-10-10

Linked required company-year integration and cross-year continuity to the existing
monthly controls; no new ledger or annual balance-copy authority is introduced.

### Account-recording review - 2026-10-10

Linked the refined source-lineage, balance-read, summary-maintenance and register contract.
Accounting remains the only financial authority; no additional ledger is introduced.

### Native master configuration UI - 2026-10-25

The user's explicit request selects native account, party and supplier configuration UI,
including related profiles/defaults, groups, terms, withholding masters and reviewed chart
setup. See the [delivery and review](account-party-supplier-ui-api.md). Existing typed
commands, field authority, company/tenant boundaries, dated policies, audit/outbox and
storage remain authoritative. Read-only form hints and scoped references support the
console; a supplier remains one party plus its SUPPLIER role. No new financial authority
or posting capability is introduced.
