# Accounting finance contract

Implementation contract for the nine-phase plan approved on 2026-09-15.

**Planning amendment, 2026-10-10:** [Vouchers](vouchers-plan.md) replaces the planned
Billing/Payments applications. Accounting retains all implemented financial authority.
The proposed stock/custody/value posting extension keeps related effects in the same
Accounting transaction; it is future work subject to V0, not an implemented capability.
Payroll and related HR work are excluded. Historical source-service names remain wire
compatibility concerns and are not renamed by this document.
The [India voucher tax plan](voucher-tax-recording.md) proposes statutory-date evidence and
separate ITC/RCM/return lifecycles. Its compatibility gate precedes changes to current
posting-date tax resolution. Fiscal posting still uses `posting_date`; filed-tax periods
and legal time of supply cannot be inferred from an open accounting period.
The [financial-reporting design](voucher-posting-reporting-design.md) adds planned D11
contracts for complete source exports, committed snapshots, classification and opening/YTD
coverage. The current financial event v1 is not a complete Reports feed. Required ledgers,
TB, P&L/Income & Expense and Balance Sheet use posted facts with explicit earnings bridges;
derived carry caches never add a second opening. Annual-close automation stays deferred.

The [company financial-year design](voucher-financial-year-design.md) requires normal
next-year generation/opening/readiness and balance continuity in the voucher phases.
Reuse implemented monthly controls, including authorized SOFT_CLOSED/CLOSED reopening;
LOCKED stays terminal. D12 extends current local checks with producer close evidence and
report/carry invalidation. Existing `FiscalYear` has no status/current flag. Deferred annual
profit-transfer automation must not block ordinary new-year operations.

The [account recording design](voucher-account-recording-design.md) extends planned owner
exports/lineage and authoritative balance reads. Existing `/ledger/balance` returns cumulative
posted debit/credit through its as-of date, not period turnover or a frozen snapshot. Reports
owns derived ledgers/registers/summaries; it never authorizes credit/allocation/posting from
a stale cache. Any optional owner accelerator must be maintained by every writer atomically.

The [stock storage contract](voucher-stock-recording-reporting-design.md#32-storage-grain-relationships-and-constraints)
refines the proposed D01 boundary: immutable quantity/value effects plus synchronously guarded
positions/units/cost/source claims, linked GL facts and outbox in one owner transaction.
Operational repair is fenced separately from Reports rebuilds. These remain planned stock
extensions; existing financial journals do not prove their implementation.

## Ownership and authority

Accounting owns fiscal posting controls, journals, entered openings, open items,
settlements, reservations and overdue-charge postings. This supersedes the earlier
Billing ownership of ledger/fiscal tables. Identity owns company calendar/configuration,
roles and feature flags. Identity facts arrive in a signed, versioned company context;
financial writes reject missing financial context. Existing master-only callers remain
compatible. The future Vouchers adapter submits versioned transaction documents to this
authority; it does not create a second financial ledger.

**Phase 2 implementation amendment, 2026-10-10:** Vouchers now submits ordinary
Journal/Contra/Payment/Receipt, advances, refunds and bill adjustment through signed
protocol v2. Durable preparation, Identity reservation outside SQL, and atomic owner commit
extend this contract. Shared intent/instrument/event/allocation-link tables add provenance;
native journal/open-item/allocation rows remain the financial records. Stock and tax-bearing
voucher profiles are still unavailable. The standalone sequence-allocation endpoint was
removed: authoritative posting allocates company/series/year numbers atomically.

The 19-grain owner feed and Reports financial definitions implement the ordinary-money
slice of D11. Readiness composes native year/calendar/opening/close checks and prepared work
for D12. Source generations freeze classifications/history; old runs remain unchanged.
Retained-history limits, earnings/currency semantics, exact endpoints, migrations, test
evidence and release flags are recorded in [Phase 2 execution](voucher-phase2-execution.md).
This amendment supersedes the earlier planning-only references for that delivered slice;
it does not enable stock, statutory tax, imported YTD or automatic annual profit transfer.

Company/tenant authority is checked before object access and on replay. Amounts are
Decimal(19,4), currencies explicit, intermediate arithmetic exact and rounding applied
once at the documented result boundary. New financial permissions are separate from
master-management grants. Financial history is append-only after posting.

## Financial behavior

- Monthly fiscal periods are confirmed by the user; special calendars are deferred. Period
  checks use posting dates, not creation timestamps. OPEN allows ordinary posting;
  SOFT_CLOSED requires adjustment authority; CLOSED/LOCKED reject posting. LOCKED is
  terminal. Drafts may exist for future dates; preparing/posting requires an eligible period.
- Identity calendar, books date, base currency and rounding are captured in Accounting
  financial setup. Once a journal is posted, incompatible changes fail closed.
- Journals balance in base currency and preserve original currency plus explicit FX
  rates stored at eight decimal places. Base-currency lines use rate one and preserve
  the entered four-place amount; only foreign conversion is rounded to company precision. Party movement and allocation currency must
  agree; no implicit conversion or customer/supplier netting is permitted.
- Entered openings are finalized once at books begin. Open-item detail must reconcile
  with each party/account/currency opening. Openings contribute through journals only.
  Corrections use reversal/replacement with dependency guards, never an overwritten amount.
- Bills carry original document date, due dates, party/role/account, policy snapshots and
  source identity. Receipts/payments create credits available for allocation. Allocation
  and unallocation preserve immutable evidence and reject over-allocation. Positive
  debt and unapplied credit are visible separately. As-of reads use posted movements.
- Credit exposure includes outstanding debt and live reservations; unexplained credits
  do not silently offset exposure. Policies resolve by party/role and business date.
  INHERIT uses the authoritative company customer limit; supplier inheritance requires
  an explicit applicable default rather than borrowing the customer ceiling. Disabled
  credit limits do not bypass explicit transaction/payment holds.
- Reservations are company/party/role/currency/source bound. Confirmation converts a
  reservation into posted exposure in one Accounting transaction. Release/expiry cannot
  free a confirmed reservation. Source identities are unique across idempotency keys.
  Overrides require a separate approving actor and retain reason, amount and policy.
- Charge policies are explicit, dated and disabled unless configured. They select fixed
  fee or percentage interest, grace days, annual/monthly/daily rate basis, simple or
  daily compounding, a day-count basis, minimum/cap and income/expense account. No statutory
  rate or tax treatment is inferred. Supplier charges require an external reference and
  a separate approver before posting. Customer charges also require separate approval.
- Charges accrue from the day after due date plus grace, bounded by the explicit accrual
  start, policy valid-from, item posting date and books begin. Intervals are start-inclusive/end-exclusive. Partial settlements split
  the principal timeline. Fixed fees apply once per bill across policy versions; waived coverage counts. Calculations retain
  input versions and an explanation; approval/posting revalidates current inputs.
- Overlapping charge coverage is rejected, including concurrent runs. Waiver records
  approved coverage without debt; posted corrections reverse accounting effects. Rate
  changes create new dated policies. Charge posting carries no implicit tax calculation;
  taxable amounts require the versioned Catalog assessment contract and reconciliation.

## Delivery controls

Each phase includes typed schemas, native constraints, one DDL statement per migration,
supported metadata/import/export/history, permission and audit contracts, and regression
coverage. Lists use bounded signed cursors; aggregates require authority over every input.
No synchronous cross-service call occurs inside a financial database transaction.

The final scenario starts with reconciled openings, applies a partial settlement, checks
and reserves credit, confirms a source posting, previews/approves/posts charges, then
reverses supported effects and reconciles all ledgers/open items. Native concurrency,
tenant isolation, current policy on replay, closed periods and audit rollback are required.

Derived realized-FX journals are created only inside an allocation or unallocation transaction. They carry an explicit `authorization_journal_id` to the posted settlement whose Identity reservation already froze the company configuration and currency feature. They require the current posting guard and permissions, add no new feature, and share that existing ratchet proof without a second remote call. A zero-original-currency FX component adjusts only the base carrying balance. Generic journal entry and reversal endpoints cannot author these components.


## Calculation and correction details

Annual interest divides the percentage by 100 and the configured 360/365 day basis;
monthly interest divides by 100 and 30; daily interest divides by 100. SIMPLE accrues
against each day's eligible principal. DAILY applies the factor from the immutable
accrual origin, making split assessment intervals reproduce a single combined interval.
OUTSTANDING reduces principal on an allocation's business date. ORIGINAL uses the original
principal while an unpaid balance remains. Unallocations restore principal from their
reversal date. Both stop on full settlement. Minimum and cap apply to cumulative charge;
the incremental assessment subtracts earlier covered amounts, including waivers.

Opening corrections are allowed before trading starts. Nonzero openings reverse through
a new journal and then identify that reversed batch in the replacement import. A zero
opening uses `reopen-zero` with a version and reason before importing its replacement.
Voiding an unposted reversal allows a replacement reversal draft; a live reversal remains
unique. Reversing a document requires resolving allocations and charge dependencies first.

Charges record existing obligations and increase subsequent credit exposure. Their posting
requires charge approval, current holds and fiscal authorization; it does not reapply the
new-trade credit block to an already approved overdue obligation. Reversing a charge through
the journal endpoint requires `accounting.charges.approve`; posting/replaying its original
journal requires `accounting.charges.manage`. Opening journal actions also require
`accounting.finance.manage`.

## Catalog tax evidence

`POST /v1/companies/{company_id}/charge-tax-snapshots` accepts Catalog tax evidence
signed for operation `catalog.accounting_tax.assessed`, audience `accounting`. The
statement binds tenant/company, assessment ID/input hash, posting date, currency,
net/gross amounts and components. The signature covers the canonical JSON of the
statement exactly as sent, so each version's shape is frozen:

- **Version 1** (`contracts/catalog-tax-computation-v1.schema.json`, unchanged) has
  free-text component codes and names no company registration. It is still accepted,
  but only with zero components; taxed version-one evidence is refused (422), because
  nothing on the charge or assessment identifies the registration it was charged under.
- **Version 2** (`contracts/catalog-tax-computation-v2.schema.json`) adds a required
  `company_registration_id` (nullable only with zero components) and types component
  codes as `CGST`, `SGST`, `UTGST`, `IGST`, `CESS`. Allowed sets are CGST+SGST,
  CGST+UTGST or IGST, each optionally with CESS, without duplicates (or none).

The named registration must be a `gst_in` row of the signed Identity context whose
validity covers `posting_date` and whose `registration_class` is `supplier` (the class
Identity sends must agree with the class the regime implies, so an ISD or TDS-deductor
GSTIN in the same state is never the charging registration); with components its regime
must pass `may_charge_tax`
(composition, unregistered, ISD and TDS-deductor rows are refused). Each component's
assigned account must be an active base-currency TAX account whose tax profile is
GST_IN, the same component, purpose OUTPUT_PAYABLE and that registration. Stored
snapshots are read back with the version discriminator, so version-one rows remain
readable. Signature age is at most 300 seconds on first
acceptance. A successful idempotency replay reads its stored receipt with current user
permissions. Local component-to-TAX-account assignments are company scoped. There is no
network call during approval or posting. Foreign conversion residuals require one dated
ROUNDING_GAIN/ROUNDING_LOSS mapping. No tax rate or exemption is inferred by Accounting.

## Worker configuration and rollout

Apply Identity migration 0059 and Accounting migrations through 0108 before deploying the
corresponding services. Run each service's normal metadata/role seed process. Platform is
0.24.0 in the current workspace (including concurrent shared-library work); the
issuer-aware Identity posting client is 0.3.1. Configure separate Accounting
reservation keys and response keys in Identity; Accounting receives
`ACCOUNTING_IDENTITY_POSTING_URL` (HTTPS origin, or literal loopback HTTP when both services run on the same host), `ACCOUNTING_IDENTITY_POSTING_KEY_ID`,
`ACCOUNTING_IDENTITY_POSTING_SECRET` and `ACCOUNTING_IDENTITY_POSTING_RESPONSE_KEYS`.
Credentials come from deployment secrets, never checked-in values.
An Accounting reservation credential may use `allow_enrolled_companies=true` with no
static scopes. Identity then checks the signed request against its active native
company record before granting each request. Billing reservation credentials still
require explicit scopes. Accounting independently checks native `AccountingSetup`
before accepting an enrolled Vouchers execution credential. This lets new companies
enter Purchase posting after normal company setup without editing deployment secrets.

Run `python -m accounting.tasks.posting_delivery` continuously (or `--once` for a batch).
A PREPARED journal can be retried using the same actor and idempotency key. A void emits an
abort intent; Identity retains it even if no reserve arrived and configuration changed.
The owner-service check applies to reserve and all terminal outcomes. Failed deliveries
remain retryable; permanent failures require operator reconciliation. Period close blocks
pending journals/openings/charges, failed company deliveries, outstanding confirmations
through period end and base/original-currency subledger discrepancies.

Run `python -m accounting.tasks.financial_publisher` with `ACCOUNTING_DATABASE_URL`,
`ACCOUNTING_FINANCIAL_BROKER_URL`, `ACCOUNTING_FINANCIAL_BROKER_USER`,
`ACCOUNTING_FINANCIAL_EVENT_SECRET`, optional `ACCOUNTING_FINANCIAL_EVENT_KEY_ID` and
`ACCOUNTING_FINANCIAL_EXCHANGE` (default `accounting.financial`). Messages carry the shared
versioned envelope and signed immutable `accounting.journal.posted` or
`accounting.fiscal_period.changed` payload. Consumers must deduplicate `message_id`; period
replicas apply only increasing row versions. Fiscal generation emits every FUTURE period.

The Vouchers producer/result consumer and end-to-end Catalog source integrations remain
delivery gates. Accounting's existing API and signed contracts remain implemented and
testable independently; the new Vouchers command adapter is not implemented here.
UI, special calendars, annual carry-forward and unrealized FX revaluation remain deferred.

## Field protection

Native input-only financial fields are part of the same write-policy contract as stored
columns. Read denial of a contributing field also hides its immutable JSON request or
calculation snapshot in details, replays and exports. Calculations require permission to
read their inputs. Exports use `/v1/companies/{company_id}/exports/{resource}` with bounded
cursor pagination and current field/role authority.


The initial financial setup retains its initial timezone as evidence. Runtime backdating,
credit exposure and accrual boundaries use the current signed Identity timezone; timezone
is not part of Identity's immutable-after-posting settings. Fiscal transition reasons are
available through protected `/fiscal-transitions` details and exports. All three fiscal
resources also have typed exports. Standalone source schemas are maintained in
`apis/accounting/contracts/` and checked by `tools.export_financial_contracts --check`.

## Persistence and migration map

All financial records use tenant/company scope, UUIDv7 identifiers, row versions and
actor audit references. Local cross-record foreign keys include tenant/company scope.
Money is DECIMAL(19,4); exchange rates use eight decimal places. Generated TypeScript
contracts keep money as strings at HTTP boundaries. Posted balances derive from journal
lines and dated allocations; there is no mutable balance cache to reconcile separately.

| Revision | Table | Purpose |
|---|---|---|
| 0073 | financial_setup | Initial signed posting settings and first-posted ratchet |
| 0074 | fiscal_year | Company calendar range and unique year identity |
| 0075 | fiscal_period | Twelve monthly ranges and posting state |
| 0076 | fiscal_status_transition | Immutable transition reason and actor evidence |
| 0077 | document_sequence | Serialized numbering by company, year and journal series |
| 0078 | journal | Draft/prepared/posted lifecycle, source identity and reversal links |
| 0079 | journal_line | Exact original/base currency entries and party roles |
| 0080 | opening_batch | Import evidence, finalization and replacement chain |
| 0081 | source_document | Source request, dated terms and instalment snapshot |
| 0082 | open_item | Original debt/credit and bill dates; dated reversal evidence |
| 0083 | allocation | Partial settlement carrying amounts and realized FX links |
| 0084 | credit_override | Source-bound request, separate approval and consumption |
| 0085 | credit_reservation | Expiring source-bound exposure and posting consumption |
| 0086 | charge_policy | Effective calculation terms, caps and tax/offset selection |
| 0087 | charge_assessment | Coverage, immutable calculation evidence and disposition |
| 0088 | charge_tax_snapshot | Verified Catalog statement and local tax-account bindings |

Revisions 0089–0094 alter master constraints (tax-accounting plan Phase 3), one DDL
statement each:

| Revision | Table | Change |
|---|---|---|
| 0089 | party_tax_registration | Drop the four-value `registration_type` CHECK |
| 0090 | party_tax_registration | Add the ten-value `registration_type` CHECK |
| 0091 | party_tax_registration | `registration_number` becomes NULL-able |
| 0092 | party_tax_registration | CHECK: UNREGISTERED has no number, OVERSEAS may omit it, others need one |
| 0093 | account_posting_mapping | Drop the `purpose` CHECK |
| 0094 | account_posting_mapping | Add the `purpose` CHECK with CESS, RCM, TDS and TCS purposes |

Revisions 0104–0108 serve tax on vouchers (tax-accounting plan Phase 8). Each is one DDL
statement:

| Revision | Table | Change |
|---|---|---|
| 0104 | tax_classification_replica | Add `source_action VARCHAR(8) NOT NULL DEFAULT 'PUBLISH'` |
| 0105 | tax_classification_replica | CHECK: `source_action` is PUBLISH, UPDATE or WITHDRAW |
| 0106 | tax_rate_replica | Add `source_action VARCHAR(8) NOT NULL DEFAULT 'PUBLISH'` |
| 0107 | tax_rate_replica | CHECK: `source_action` is PUBLISH, UPDATE or WITHDRAW |
| 0108 | journal_tax | Create the voucher Tax Analysis evidence table, one row per journal |

The downgrades for 0104–0107 drop the column or the CHECK. Replica rows that were withdrawn before
0104 read as PUBLISH, so a Catalog republication is needed to record those withdrawals. The 0108
downgrade drops `journal_tax`. No other table references it, but the evidence is lost, so take a
backup first.

Downgrades restore the previous constraint or nullability; they fail (leaving the schema
at the prior revision) while rows use a newer type, purpose or a missing number, which must
be retired first.

Identity 0059 adds service ownership to posting reservations after Identity 0058.
Its downgrade refuses to remove ownership while non-Billing reservations remain.

## Planning decision log - 2026-10-10

The deeper reporting review specifies additive versioned export/catch-up contracts for
journals, allocations, openings, native classifications and later stock/tax facts. Reports
must reconcile against owner snapshots, preserve issued runs and enforce input authority.
This is a future extension, not a claim that current v1 events or balance APIs provide it.

The India tax-recording extension requires versioned statutory dates, eligibility and return
evidence while retaining this contract's fiscal guards and historical financial snapshots.
No India VAT or broader statutory workflow is claimed as implemented.

Replace future Billing/Payments application integrations with Vouchers. Preserve Accounting
as the party/ledger/fiscal/settlement authority. The Vouchers plan proposes co-located stock
and value posting to retain atomic effects; V0 must settle that extension and its migrations.
This amendment does not change existing source identifiers, posting routes or deployed behavior.
Each Accounting revision creates one table with constraints and indexes in the same
atomic statement; downgrade drops that table in dependency order. Journal reversal
uniqueness uses a generated live key so voided reversal drafts can be replaced.

## Local verification commands

From `apis/accounting`, run `.venv/Scripts/python.exe -m tools.verify_mysql --full-suite`
against the disposable loopback MySQL server on port 13396. The harness validates its
server/name and owns creation and cleanup of a unique `accounting_test_*` database;
it also checks model parity and downgrade/upgrade. Never point tests at business data.

For the real two-service bridge, use `apis/identity` as the working directory, set
`PYTHONPATH=../accounting/src;.` on Windows and run
`.venv/Scripts/python.exe -m tools.verify_accounting_finance_mysql`. This exercises
signed gateway context, reservations, postings, confirmation delivery, reconciliation
and Identity ownership migration safety using two disposable databases.

### Financial-year planning decision - 2026-10-10

Clarified existing fiscal models/transitions versus planned D12 integration. Normal
year continuation is required, distinct from the previously deferred annual close automation.
No financial command, fiscal transition, numbering policy or ledger has been changed here.

### Account-recording review - 2026-10-10

Documented existing balance semantics and planned account source/summary/read contracts.
No current endpoint, financial writer, allocation or balance was changed.

### Stock capture/storage review - 2026-10-10

Recorded the proposed stock storage/transaction and value-to-GL conservation obligations.
No stock writes, financial commands, costing policy or repair operation was performed.
