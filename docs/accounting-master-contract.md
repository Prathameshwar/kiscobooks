# Accounting master contract — implementation baseline

Approved six-phase scope, 2026-09-14. The generated resource/field matrix will accompany this
contract and describe every public field, lifecycle, reference and action permission.

## Ready-to-use party imports

Decision 2026-10-27: the `parties` import definition supports `supplier:CREATE` and
`customer:CREATE` convenience commands using the existing PartyCreate fields.
Only CREATE_ONLY with a new identity is allowed: no explicit target or clear-fields
operation is accepted. Existing-party changes use the existing party/role resources.
Each convenience command creates and activates a party, its matching role and (since 2026-11-02, PL-D04) its ledger account through
ordinary native commands within the import aggregate's transaction/savepoint. It
requires full current party/role/account read/manage and field authority; status writes are
not elevated. Validation rolls back business writes/audit, and commit/replay uses
the normal import receipts/effects. There is no second party or supplier table.
Explicit template role parameters also constrain role-bearing policy schemas.
See [party-import-ui-delivery.md](party-import-ui-delivery.md).

## Party creation defaults and optional registration start

Decision 2026-10-31: creation suggests legal name from name until explicitly edited;
country from the readable company detail, falling back to `IN`; default address
label `Billing address`; and tax country/state from the identity/address steps.
Suggestions honor field permissions and remain editable across wizard navigation.

Party tax-registration `valid_from` may be omitted or null (revision 0227). Null
means no lower date bound. Date filtering, overlap rejection, registration/address
containment and voucher tax checks use this meaning; expiry still applies. A null
start is already effective and receives the existing immutable-history protections.
Other dated masters retain required starts. Public schemas/generated clients and
the signed voucher master lookup accept null; dates are never invented during
creation or downgrade. See [delivery and verification](party-creation-defaults.md).

## Opening capture during master creation

Decision 2026-11-02: PartyCreation and AccountCreation accept optional `opening`
with exact amount, explicit DEBIT/CREDIT and company books-begin date. A positive
opening is saved atomically in immutable, scoped `master_opening_balance` evidence
(migration 0230); creation never posts a journal or inserts a balancing amount.
Customer/supplier allocations retain original and pending amounts and real bill/due
dates, with at most 200 bills; only pending contributes to the opening. Simple party
balances use ON_ACCOUNT. The company opening worksheet selects held entries and
still requires full balanced validation, review and native posting. Reads, retries,
withdrawals and inclusion recheck company/tenant and native financial authority.
General accounts keep their existing DRAFT/ACTIVE creation lifecycles. See
[delivery plan](master-creation-opening-plan.md).

## Company initialization

Decision 2026-10-26: company initialization reuses the unchanged chart v3 seed to create
five fixed heads, 28 groups and 12 active business accounts atomically, including hierarchy,
template bindings and audit evidence. Empty pre-existing setups may catch up; any authored
or installed chart is preserved. Retries preserve identities and later presentation edits.
The bounded finance initialization grant permits only these fixed defaults; arbitrary
template/tax installation and master CRUD retain their existing permissions and field guards.
There are no balances, postings, fabricated parties or bank/registration details.

## Group metadata

Primary means `parent_id` is null; reserved means a server-owned `system_key` is present.
These flags are read-only. Revenue and debit-positive classification derive from the head
(revenue: INCOME/EXPENSE; debit-positive: ASSET/EXPENSE) and cannot diverge in descendants.
Gross-profit classification inherits from the parent; a root may select it only for INCOME
or EXPENSE. The STOCK system subtree is the explicit ASSET exception. Legacy backfill derives
the canonical direct-income/direct-expense/purchase/sales/stock flags from system identity,
without changing hierarchy or names. Unknown custom roots default to no gross-profit effect.

Sub-ledger, net-balance and calculation flags default false. Allocation is NOT_APPLICABLE,
BY_QTY or BY_VALUE; allocation requires an income/expense classification. Display order is a
nonnegative bounded integer, default 0. System templates set canonical values. Primary groups
cannot be reparented through ordinary CRUD. System and used classifications retain existing
guards. Name and display order are presentation changes; financially meaningful attributes
are protected against changes that would reinterpret existing account classifications.

Group aliases follow account aliases: immutable group ownership, company-unique trimmed
nonempty alias, DRAFT/ACTIVE/INACTIVE lifecycle, scoped FK, no hard delete. Database collation
governs case/accent uniqueness; the API returns conflict rather than silently choosing a match.

## Ledger/profile metadata

Inventory affected defaults false; ordering defaults 0. Rounding is NONE, NORMAL, UP or DOWN.
NONE requires no limit. Other methods require a positive DECIMAL(19,4) limit and BASE/FIXED
currency mode. MULTI cannot carry an ambiguous rounding amount. These settings configure
masters only. Active/used classification changes remain forbidden.

Duty types are GST, VAT, TDS, TCS, CESS, EXCISE and OTHER. GST requires GST_IN with a GST
component; VAT requires VAT/VAT; CESS may use GST_IN/CESS or OTHER/OTHER; TDS/TCS/EXCISE use
OTHER/OTHER. OTHER preserves existing records without inferring a new statutory meaning.
GST/VAT require a matching company registration. Other duties may omit that registration;
an explicitly supplied registration must still be in the signed company context. Tax purpose
continues to determine compatible account head.

Regime is judged per company registration row. Identity never edits a row's regime (a change
closes the row and opens another), and every dated dependant must fit inside its row's window,
so a check on the row covers every effective date. GST input recovery (`INPUT_RECOVERABLE`
profiles and `INPUT_*` mappings) needs a regular row; GST output (`OUTPUT_PAYABLE` profiles and
`OUTPUT_*` mappings) needs a row whose regime `may_charge_tax` (composition, unregistered, ISD
and TDS-deductor rows may not). Reverse-charge purposes need no regime test. The GST template
needs a row that permits both and has not ended. Missing or malformed validity in the signed
context fails closed.

Posting-mapping purposes resolve through an explicit table (`domain/rules.py`
`TAX_MAPPINGS`), never a name suffix:

| Purpose | Head | Profile scheme / component | Profile purpose | Duty | Regime |
|---|---|---|---|---|---|
| `OUTPUT_{CGST,SGST,UTGST,IGST,CESS}` | LIABILITY | GST_IN / same | OUTPUT_PAYABLE | GST or OTHER (CESS also CESS) | may charge |
| `INPUT_{CGST,SGST,UTGST,IGST,CESS}` | ASSET | GST_IN / same | INPUT_RECOVERABLE | as above | regular |
| `RCM_{CGST,SGST,UTGST,IGST,CESS}` | LIABILITY | GST_IN / same | RCM_PAYABLE | as above | none |
| `TDS_PAYABLE`, `TCS_PAYABLE` | LIABILITY | OTHER / OTHER | OUTPUT_PAYABLE | TDS / TCS | none |
| `TDS_RECEIVABLE`, `TCS_RECEIVABLE` | ASSET | OTHER / OTHER | INPUT_RECOVERABLE | TDS / TCS | none |

Tax-purpose mappings target TAX accounts and carry the profile's registration (GST purposes
require one). `CASH_RECEIPT` maps to a CASH account under ASSET; `BANK_RECEIPT` maps to a BANK
account under ASSET or, for an overdraft, LIABILITY. Revenue/return/gain purposes need INCOME,
expense/loss purposes EXPENSE, `INVENTORY_VALUE` ASSET. The GST template does not create cess
accounts: cess applies only to notified goods and adding accounts would change the v3 template
hash for existing installs; cess accounts and mappings are created as ordinary masters.

Profiles remain editable only on unused
DRAFT accounts; every supported duty must have a tested activation path.
Once a tax or bank profile exists, the account must retain its matching kind. Account edits
and activation recheck tax purpose against the account's resulting head, including imports.
A draft tax account may move between compatible groups; incompatible moves fail atomically.

## Party linkage

Default scope is party + purpose + optional registration. General and registration-specific
defaults coexist; duplicate ACTIVE defaults in the same scope conflict. Draft replacement is
allowed and activation rechecks uniqueness. Explicit GST address associations must match
party, country and state and fit registration validity.

Party registration types are REGULAR, COMPOSITION, UNREGISTERED, SEZ_UNIT, SEZ_DEVELOPER, UIN,
OVERSEAS, CASUAL, NRTP and OTHER (SEZ_UNIT, SEZ_DEVELOPER, UIN, CASUAL and NRTP exist only under
GST_IN). UNREGISTERED carries no number and records the buyer's Indian state for place of supply;
OVERSEAS needs a non-Indian country and, under GST_IN, carries neither GSTIN nor state; every
other type is numbered (a database CHECK enforces the same rule). GST_IN rows other than
OVERSEAS require country IN and a `state_code` that maps to a GST state code. GSTIN-bearing
types (REGULAR, COMPOSITION, SEZ_*, CASUAL, OTHER) are validated by the shared
`billing_platform.jurisdiction.validate_gstin`: shape, entity code not `0`, mod-36 check
character and state prefix equal to the state; numbers are stored without separators. UIN and
NRTP identifiers get only the fifteen-character state-prefixed shape check, because the shared
helper defines no pattern for them yet. Per party and state, REGULAR, COMPOSITION and
UNREGISTERED rows describe one GST status and never overlap in time (so at most one
UNREGISTERED row and never two overlapping REGULAR rows); numbered rows also never overlap for
the same number.
Multiple registrations are never
resolved by arbitrary first-row selection. Address/registration/date reads are bounded and
indexed. National personal identifiers and raw beneficiary reads remain prohibited.
Registration-address list rows include both `address_id` and `registration_id`, subject to
field permissions, so callers can identify each association without fetching every detail.

## Account tax defaults

`account_tax_default` (`/account-tax-defaults`, revision 0099) is a dated master: Tally's GST
details on an income, expense or asset ledger. Fields: `account_id`, `direction` SALE|PURCHASE,
`supply_kind` GOODS|SERVICE, `code_system` SAC|HSN, `code`, `rule_id`, `treatment`
TAXABLE|NIL_RATED|EXEMPT|NON_GST, `itc_eligibility` ELIGIBLE|INELIGIBLE|BLOCKED, `rcm_applicable`,
`assessable_inclusion` NONE|GOODS|SERVICES|BOTH, `apportion_by` VALUE|QUANTITY, `valid_from`,
`valid_to`. SAC codes are `99` plus four digits and classify services; HSN codes are 4, 6 or 8
digits outside chapter 99 and classify goods. Taxable and nil-rated defaults name a Catalog rule
by its Catalog id; it must exist in the company's `tax_rule_replica`, be active and match the
default's supply kind and treatment. Purchases state ITC eligibility and may be reverse-charge;
sales do neither. `apportion_by` is present exactly when an assessable inclusion is. Only ACTIVE
GENERAL accounts under INCOME, EXPENSE or ASSET heads qualify. Intervals may not overlap per
(account, direction), checked under the company lock; `account_id` and `direction` are immutable.
Permissions are `accounting.tax.read` / `accounting.tax.manage`. The list projection is account,
direction, supply kind, code system, code, treatment and dates; filters `account_id`, `direction`,
`code`, `as_of`; `q` prefix-searches the code; sorts by ID only.

## Compatibility and backfill

Every schema change is a new single-DDL revision. A setup metadata-version marker separates
DDL completion from semantic backfill. Fresh setup initializes the current marker; existing
companies retain a pending marker until the explicit, idempotent company backfill finishes.
Readiness and company data paths, including saved-command replays, refuse pending metadata.
Backfill preserves IDs, names,
references, hierarchy and template receipts, derives new classification fields, audits its
changes and advances the marker in the same transaction. No seed data is hidden in migrations.

Template upgrade previews existing changes and conflicts and applies atomically under the
company lock with field policy. The v3 base has 28 groups. Moving legacy RESERVES under
CAPITAL is allowed only when its subtree has no financially used accounts and no incompatible
classification. Unsafe upgrades conflict; they never force-move used identities. Old v1/v2
bindings and receipts remain readable and replayable. GST collision repair remains available.
Preview and install share account compatibility checks for kind, group, status and tax profile;
preview reports code collisions and correctly recognizes reusable v1 accounts. Template reads
require head, group, account and setup read permissions, plus tax read for GST selections.
Denied classification fields, including conditional denies, prevent aggregate preview/replay
results that could reveal them. Implicit installation/binding/setup writes honor field policy.
Changes to replicated setup currency and installed template version receive revision/outbox
evidence; used account currency remains immutable.

## Common surfaces

The selected [account/party/supplier console delivery](account-party-supplier-ui-api.md)
adds native management pages and read-only operation-specific form/reference contracts.
These hints enforce the same field/scope authority and preserve masked values; mutation
authority remains in the existing commands. Suppliers are parties with active SUPPLIER
roles, and dated/current/used classifications retain the rules below.

All business operations retain tenant/company checks, current field policy, optimistic edit
versions and idempotent writes. Read-only and derived resources expose only their supported
actions. Create replies include a relative Location, preserving an external gateway prefix.
Decision 2026-10-31: lean party lists include readable Organisation/Person `party_type`
and an independently protected `roles` array of active Customer/Supplier/Other/Broker
roles. Role labels use company/tenant-scoped EXISTS predicates in the same paged query;
all contributing role fields must be readable. An empty array means no active role;
an omitted array means protected data. Party type and commercial roles stay distinct.
Exports have individual typed contracts at the same
URLs, sparse protected fields, signed paging and no secrets. All newly introduced fields and
resources join imports, metadata, history, audit and the generated Identity/client contracts.

The [resource matrix](accounting-master-matrix.json) is generated from schemas, resource rules
and indexes. `as_of` is an inclusive date filter on effective-dated resources; unsupported
filters and unreadable filter/search/sort fields fail closed. Display order supports signed
ascending/descending cursors with the ID tie-breaker. Alias lookup uses the alias resource's
own namespace. Deployment and populated-data downgrade conditions are in the
[release procedure](accounting-masters-release.md).
Account lists support code and name prefix search (minimum two characters), signed code/ID/name
ordering (code by default), and typed code, group, party, kind, status, currency and currency-mode filters. The
list includes currency mode when readable. Dedicated composite indexes support status, kind,
group, currency and currency-mode code pages; read-denied fields cannot be filtered or sorted.
History accepts only limit, cursor and ID sort; unsupported master filters are rejected.
Mapping-draft validation requires every evaluated mapping value to be readable, including
conditional field policy. Detail reads may still return the permitted subset of draft values.

## Withholding masters (2026-10-05)

Withholding sections are status masters with immutable kind and code. Rates, party profiles
and certificates are effective-dated: their identity fields are immutable, and current rows
may only shorten `valid_to`. Rate and certificate creates require `source_reference`, an https
`.gov.in`/`.nic.in` `source_url` and a 64-hex `source_sha256`. Threshold and certificate
currencies must equal the company base currency. A VERIFIED profile must reference the
party's own PAN-scheme identifier, and NOT_AVAILABLE forbids one. Each default section must
match the profile kind. A rate supersession names a same-section, same-deductee predecessor
that ended on the previous day, and that predecessor may have only one successor. Lists filter
on `section_id`, `deductee_type`, `party_id` and `kind`. Certificate detail reads are audited
as sensitive reads. Audit evidence never carries the certificate reference.
