# Tax in Accounting — Phase Plan

**2026-11-02 GSTR-1 delivery:** [GSTR-1 implementation/review](gstr1-delivery.md)
adds Accounting revision 0229, an immutable detailed `gst_outward_record` owner
resource, without changing the tax posting engine. Scoped, idempotent capture
retains exact INR amounts, invoice-rate/source-line details, notes, advances,
document series, amendments, IFF/ECO and completeness proof. Native capture
checks committed sales, posted journals, recipient registration, place of supply,
HSN, GST rates/components and retained conversion evidence. External statutory
evidence requires explicit provenance. Audit and reporting changes share the
capture transaction. Reports revisions 0040/0041 add separate GSTR-1 review/
filing evidence and indexed registration-period extraction. Missing or
contradictory evidence blocks review; this increment does not claim government
filing, portal JSON compatibility, or automatic completion of other planned tax
profiles below.

**2026-10-10 ownership amendment:** [Vouchers](vouchers-plan.md) replaces future Billing
and Payments APIs. Accounting remains the authoritative tax/ledger posting owner; Vouchers
supplies typed transaction inputs and previews. Older Billing references below describe the
historical consumer plan, not a future service to create. Payroll and related HR work are excluded.

**2026-10-10 statutory-recording extension:** The user confirmed India. The new
[voucher tax plan](voucher-tax-recording.md) specifies GST across document kinds, job work,
advances, commercial/statutory notes, ITC/RCM states, reporting and state-specific VAT gates.
It is future work beyond the completed phases below. Existing `posting_date` rate/registration
resolution needs a versioned extension for statutory tax dates while fiscal posting guards
remain unchanged. Existing RCM accounting entries do not establish payment or lawful credit
claim by themselves. A listed foreign VAT regime is not an implemented India VAT engine.
T0-T5 attach to the Vouchers delivery phases and do not reopen completed migrations in place.

Original phase status: **agreed 2026-10-05**; the user delegated remaining choices
("best fit, borrowing TallyPrime concepts").

Goal: tax stops being an invoice-only concern. Accounting owns tax accounts (already true), tax on
non-product vouchers (expenses, journals, payments), reverse charge and TDS/TCS. Catalog keeps
product GST definitions. One shared calculation mechanism serves Vouchers and Accounting. The
defects found in the 2026-10-05 tax review are fixed first.

Each phase ends with its suites green, Ruff + mypy strict clean, and the repo working. Migrations
are one DDL statement per revision, with a model, schema, factory and downgrade in the same phase.

---

## Phase 0 — Decisions and docs (no code) — done 2026-10-05

Record the boundary before building on it.

- `docs/tech-stack.md` §104/§145 and decision log: "Catalog owns *product* tax definitions;
  Accounting owns tax accounts, account-level tax defaults, withholding (TDS/TCS) and tax on
  accounting vouchers; the calculation mechanism lives in `libs/platform`; Billing and Accounting
  both apply it against local replicas."
- `docs/accounting-design.md`: new §"Tax" covering the tables in Phases 6–8.
- Resolve the reverse-charge conflict: `catalog-product-design.md` §9 says Catalog stores RCM
  applicability; `catalog-v14-api.md:57` and `catalog-v1-scope.md:66` assign it to Billing.
  Proposed: RCM applicability is a dated fact on the **Catalog rule** (goods/services notified
  under RCM) and on the **Accounting account default** (expense services); *determining* RCM per
  document stays with the posting service.
- Answer the open questions at the end of this file.

Exit: docs merged and decision logs updated.

## Phase 1 — Identity and shared-library fixes — done 2026-10-05

| # | Fix | Where |
|---|---|---|
| 1.1 | GSTIN checksum (mod-36) and state-prefix ↔ `jurisdiction_code` check; one implementation | `libs/platform/jurisdiction.py` (+ version bump) |
| 1.2 | `regime`, `number`, `jurisdiction_code`, `valid_from` immutable after create (422 for every actor). A regime change is "close the old row, open a new one". Only `valid_to` (close), legal name, address and `is_primary` stay editable. Remove the self-comparing `assert_tax_system_unchanged` call | `identity/api/company_statutory.py`, schemas |
| 1.3 | Overlap rule groups by `(tax_system, registration class, jurisdiction)`, so a regular GSTIN and a TDS-deductor / ISD registration may coexist. TAN-based GSTIN shape accepted for `tds_deductor` only | `libs/platform/statutory.py`, `jurisdiction.py` |
| 1.4 | Enforce one `is_primary` per `(tax_system, jurisdiction)` on any date | identity `domain/` |
| 1.5 | Registration-amended audit payload carries the changed-field set | identity audit |

Tests: checksum valid/invalid, prefix mismatch, immutable fields → 422, concurrent regular +
tds_deductor accepted, two regulars rejected, primary uniqueness, audit payload fields.

Landed in `billing-platform` 0.27.0 (`validate_gstin`, `gstin_check_character`,
`Regime.registration_class`, class-aware `assert_no_overlap` / `resolve_tax_registration`).
Follow-up done 2026-10-05: `registration_class` stored on `company_tax_registration` and in its
unique key (identity revisions 0060–0063), so same-day registrations of different classes coexist;
`ecommerce_operator` is class `tcs_collector` and accepts the `C`-shaped TCS GSTIN (0.27.0).

## Phase 2 — Catalog tax fixes — implemented 2026-10-05

| # | Fix | Where |
|---|---|---|
| 2.1 | Supersession cannot shorten a predecessor that is already in force today (`valid_from > today`, matching withdrawal) | `tasks/tax_commands.py:67` |
| 2.2 | CGST and SGST/UTGST must share `rounding_mode`; rounding is part of the cross-context signature | `domain/tax.py` |
| 2.3 | HSN codes in chapter 99 are rejected for goods; SAC must start with 99 | `schemas/tax.py` |
| 2.4 | Company-scope and `BOTH`-group defaults are keyed by item kind, so goods and services each get their own default (adds `item_kind` to `catalog_tax_binding`: one column + one index revision) | model, migration, resolution |
| 2.5 | Impact review no longer caps at 256 products for company or large-group scopes (decision 3) | `tasks/tax_integrity.py` |
| 2.6 | Previews: permission checked before validation; previews rate-limited | `api/tax.py`, `tax_commands.py` |
| 2.7 | Publish commands audit as `.publish`, withdrawals audit the target row | `pricing_commands.py`, `tax_governance.py` |

Tests: same-day supersede → 409, mismatched rounding → 422, HSN 99xx goods → 422, a mixed
goods/services company resolves both kinds, 300-SKU company can publish a rate, 403 before 422 on
previews, audit action names. Fill the wrong-company-ID-in-body gaps the review listed.

Landed: 2.1 409 for a supersession starting on or before the business date (new histories may
start today); 2.2 split-rounding 422 plus rounding in the three-context signature; 2.3 HSN regex
excludes 99; 2.4 `catalog_tax_binding.item_kind` (revision 0155, column only: the existing
`ix_catalog_tax_binding_date` already serves the lookup), kind-first then all-kinds resolution;
2.5 `tax-impact-reviews` (revisions 0156 `tax_impact_review`, 0157 `tax_impact_finding`) run by
`python -m catalog.tasks.tax_review_worker` in 16-product chunks; `tax-releases` takes
`impact_review_id` instead of `preview_token`, accepted only when COMPLETE, unblocked and matching
the generation/source/date/input digest; the 256-product synchronous preview bound is unchanged;
2.6 permission before validation, 120/min shared tax budget on previews; 2.7 `.publish` and target
`.withdraw` audits. Wrong-company body references already returned 403/404; covered by tests.
Known limit: a busy company whose catalog keeps changing sees long reviews go STALE.

## Phase 3 — Accounting tax fixes — implemented 2026-10-05

Migrations 0089–0094 (CHECK swaps for party `registration_type` and mapping `purpose`,
nullable party `registration_number` plus its CHECK). Charge-tax evidence version 2 carries
`company_registration_id` and typed components; version 1 is accepted only without
components. GST template cess accounts were not added (see the accounting-design decision
log). Open: UIN/NRTP numbers get only a state-prefixed shape check until the shared helper
defines their pattern. Catalog's version-two producer exists since 2026-10-06 (Phase 5) as a
task function; its caller is still undecided, so taxed charges are not yet posted end to end.

| # | Fix | Where |
|---|---|---|
| 3.1 | Charge tax resolves the company registration valid on `posting_date` and refuses components when `may_charge_tax` is false (composition, ISD, TDS deductor) | `tasks/charge_tax.py` |
| 3.2 | Component codes typed (`CGST/SGST/UTGST/IGST/CESS`). Each assigned account must hold an `account_tax_profile` with that component, purpose `OUTPUT_PAYABLE`, and the resolved registration | `schemas/charge_tax.py`, `charge_tax.py` |
| 3.3 | Regime checks in profile validation use the registration's validity window, not one current value | `tasks/validation.py:43`, `templates.py:96` |
| 3.4 | GST_IN party registrations require `state_code`; state prefix and checksum use the Phase 1 helper; entity code `0` rejected | `domain/rules.py` |
| 3.5 | Party `registration_type` adds `SEZ_UNIT`, `SEZ_DEVELOPER`, `UIN`, `OVERSEAS`, `CASUAL`, `NRTP`; `UNREGISTERED` becomes usable (no number) or is removed — see Q4 | model, migration (CHECK swap), schemas |
| 3.6 | Posting-mapping purposes add `OUTPUT_CESS`, `INPUT_CESS`, `RCM_*`, `TDS_PAYABLE`, `TCS_PAYABLE`, `TDS_RECEIVABLE`, `TCS_RECEIVABLE`; the suffix rule maps purpose → (component, purpose) explicitly instead of string suffix | model, migration, `validation.py`, GST template |
| 3.7 | `BANK_RECEIPT` accepts an overdraft bank account under LIABILITY | `validation.py:276` |

Tests: composition company → 422 with components and OK with none, wrong-profile account → 422,
regime window cases, new registration types, CESS/RCM/TDS mappings, overdraft mapping.

## Phase 4 — Shared tax calculation (`libs/platform`) — implemented 2026-10-05

Pure, framework-free mechanism in `billing_platform/tax_calc.py`; 90% coverage floor
(`tests/test_tax_calc.py`, 99%). Vocabularies mirror Catalog's `tax_rate_component`,
`tax_rate_series.applicability` and `tax_rule.treatment`, and Accounting's party
`registration_type`, so replica rows map on without translation.

- `place_of_supply(supplier_state, place_of_supply_state, buyer_type, *, utgst_states)` →
  `SupplyDetermination(context INTRA_STATE|INTRA_UT|INTER_STATE, zero_rated, reason
  EXPORT|SEZ|SAME_STATE|SAME_UT|DIFFERENT_STATE)`. Export and SEZ are *reasons* on an
  `INTER_STATE` context (IGST series), not contexts of their own. The UTGST state set is
  reference data supplied by the caller, never hardcoded.
- `compute(TaxRequest)` → `TaxComputation`: per-line, per-component `Decimal` amounts. Each
  component rounds once by its own `rounding_mode` (HALF_UP|UP|DOWN) to company
  `amount_precision`; fixed per-unit cess = amount × quantity / basis (line unit must equal the
  rate's unit); tax-exclusive and tax-inclusive basis (inclusive back-calculates, rounds by the
  document rounding mode, and the taxable value absorbs the residual so `taxable + Σtax == gross`
  exactly); zero-rated under LUT records rates at zero amount, with IGST payment charges them;
  EXEMPT/NON_GST lines carry no components; NIL_RATED lines carry none or only 0% PERCENT
  components (checked against the context's component set and CGST = SGST/UTGST; any non-zero
  or fixed per-unit component → 422), tax always 0, the 0% rates shown in the Tax Analysis;
  `may_charge_tax = False` with any non-zero rate is a hard 422.
- TallyPrime *Include in assessable value*: `AssessableCharge(applies_to GOODS|SERVICES|BOTH,
  apportion_by VALUE|QUANTITY)` apportioned before tax by cumulative rounding (shares never
  negative; the last eligible line absorbs the residual). Charges onto tax-inclusive lines are
  rejected.
- Line values and charges must be exact at company precision (an off-grid value is a 422, not a
  silent rounding); quantities and rates exact at storage scale; nothing negative.
- `TaxComputation.snapshot()` — the *Tax Analysis*, JSON-safe, `schema_version = 1`, persisted by
  posting services with the document.
- Remaining: version bump and every consuming service's lockfile (coordinator).

Note for Phase 5/8 consumers: Catalog stores NIL_RATED rates as explicit 0% GST components;
pass them through unchanged — the calculation accepts and reports them (decided 2026-10-05).

## Phase 5 — Catalog → Accounting tax replica — implemented 2026-10-06 (both sides)

- Catalog emits versioned events through the outbox on tax classification, rule, rate (with
  components) and withdrawal publication.
- Accounting consumer (dedupe on `message_id`) maintains read-only replica tables:
  `tax_rule_replica`, `tax_rate_replica`, `tax_rate_component_replica`, `tax_classification_replica`
  (one revision each).
- Bootstrap/backfill command for existing companies.

Tests: redelivery → one effect, out-of-order versions, withdrawal, cross-tenant isolation per
replica table, `Decimal` round-trip.

Landed (Accounting side): revisions 0095 `tax_classification_replica`, 0096 `tax_rule_replica`,
0097 `tax_rate_replica` (Catalog's series flattened onto the rate as `series_id` +
`applicability`), 0098 `tax_rate_component_replica`. Rows keep Catalog's UUIDv7 ids and carry
`tenant_id`, `company_id`, `source_version` (Catalog's company `CatalogPolicyState.generation`)
and `source_message_id`; no foreign key from rate to rule, since events may arrive in any order.
`python -m accounting.tasks.catalog_tax_worker` consumes queue `accounting.catalog_tax.v1`
(exchange `platform.sources`, DLQ `platform.source_errors`), accepting only Catalog-signed
`catalog.tax_classification.changed`, `catalog.tax_rule.changed` and `catalog.tax_rate.changed`,
`schema_version` 1, dedupe by `consume_once`. Payload contracts:
`apis/accounting/contracts/catalog-tax-{classification,rule,rate}-changed-v1.schema.json`
(common `schema_version, tenant_id, company_id, source_version, action PUBLISH|UPDATE|WITHDRAW`
plus one `classification`, `rule` or `rate` object; a rate carries its 1–16 components; decimals
are strings, at most four places). A row moves only to a strictly newer generation; equal or older
ones are no-ops. Between generations only a classification's `valid_to`/`description`, a rule's
`name`/`is_active` and a rate's `valid_to` may change; components never do. Anything else, a
payload/envelope tenant mismatch or a company move dead-letters. Withdrawal mirrors Catalog:
`valid_to` for classifications and rates, `is_active = false` for rules; nothing is deleted. The
replica writes no audit event (Catalog audits the source change).
Landed (Catalog side, no migration, no route): every tax command that changes a
classification, rule or rate stages its `catalog.tax_*.changed` event through Catalog's outbox in
the command's own transaction, at the generation that command bumps (`events/tax_publication.py`,
`tasks/tax_publication.py`, hooked from `PricingWork.published`). A command's own row carries
the strongest of its actions (UPDATE < PUBLISH < WITHDRAW). Previews and impact reviews run in
rolled-back savepoints and publish nothing. Rule retirement (`is_active` true → false) is a
WITHDRAW. A withdrawn classification or rate is sent with `valid_to = valid_from`, because
contract v1 needs a non-null `valid_to` on WITHDRAW and Catalog's withdrawal leaves the row's
dates as they were. `python -m catalog.tasks.accounting_publisher` relays them to
`platform.sources`, signed `catalog` → `accounting` for those three event types only. Its
environment is `CATALOG_SOURCE_BROKER_URL`, `CATALOG_SOURCE_BROKER_USER`,
`CATALOG_ACCOUNTING_EVENT_SECRET` and `CATALOG_ACCOUNTING_EVENT_KEY_ID`.
`python -m catalog.tasks.tax_backfill` takes each `CATALOG_SOURCE_SUBSCRIPTIONS` company and
republishes current state at the current generation, without bumping it and without an audit
event. It is idempotent: rows already staged at that generation are skipped. Contract tests
validate the produced payloads against the Accounting schema files.

Charge-tax evidence v2 producer (closes the Phase 3 gap in code only):
`catalog.tasks.charge_tax.assess_charge_tax` resolves the rule's rate effective on
`posting_date` for the context `tax_calc.place_of_supply` decides, computes with
`tax_calc.compute`, and names the supplier-class registration valid on `posting_date`
(`domain/charge_tax.py`). `evidence()` signs it for `catalog.accounting_tax.assessed`. A taxed
supply with no such registration fails closed. A regime that may not charge (composition)
yields an untaxed statement.

Open:
- (a) Contract v1 has no "never effective" form. Accounting needs a withdrawn flag or relaxed
  date ordering so the one-day `valid_to = valid_from` window disappears.
- (b) The caller/trigger of charge-tax evidence (which service asks, and when) is undecided, so
  there is no route.
- (c) Registrations and the UTGST state set are explicit inputs. Catalog's Identity context
  carries neither, and the UTGST set should come from reference data.
- (d) Foreign-currency charge tax is refused.
- (e) Accounting's catalog-tax credential must match Catalog's publisher key.

## Phase 6 — Account-level tax defaults (Accounting) — implemented 2026-10-06

New master `account_tax_default` — Tally's GST details on an expense/income ledger:

`account_id, direction SALE|PURCHASE, supply_kind GOODS|SERVICE, code_system SAC|HSN, code,
rule_id (replica), treatment, itc_eligibility ELIGIBLE|INELIGIBLE|BLOCKED, rcm_applicable,
assessable_inclusion NONE|GOODS|SERVICES|BOTH, apportion_by VALUE|QUANTITY (required when
inclusion is not NONE), valid_from, valid_to`

- Full CRUD per `api-conventions.md`: cursor list, lean `ListItem`, allowlisted filters,
  field-set, exports, field policy.
- Permissions `accounting.account_tax_default.read/manage` in the catalogue, system roles, seeds.
- Non-overlap per `(account, direction)` under the company lock; audit via outbox; idempotent.
- Only accounts of kind GENERAL under INCOME/EXPENSE/ASSET heads may carry a default.

Tests: the full §7 per-endpoint set plus overlap, wrong-company rule id, field deny.

Landed: revision 0099 `account_tax_default`, `/v1/companies/{company_id}/account-tax-defaults`
(list, field-set, get, create, patch) and `/exports/account-tax-defaults`. Permissions reuse the
existing `accounting.tax.read` / `accounting.tax.manage` (the tax family that already guards
`account_tax_profile`), so no new key, role or seed. Rules: SAC = `99` + four digits, HSN = 4/6/8
digits outside chapter 99; HSN ↔ GOODS and SAC ↔ SERVICE; `rule_id` is required for TAXABLE and
NIL_RATED (optional for EXEMPT/NON_GST) and must be an active same-company replica rule with the
same item kind and treatment (wrong company → 403, unknown → 404); `itc_eligibility` is required
for PURCHASE and absent for SALE; `rcm_applicable` only on PURCHASE; `apportion_by` iff inclusion
is not NONE; the account must be ACTIVE, kind GENERAL, under an INCOME, EXPENSE or ASSET head;
`account_id` and `direction` are immutable. Lean list: account_id, direction, supply_kind,
code_system, code, treatment, valid_from, valid_to; new `direction` filter; `q` searches `code`.

## Phase 7 — TDS / TCS masters (Accounting)

Gated by the existing `tds` / `tcs` company features.

- `withholding_section`: `code` (e.g. 194C), `kind TDS|TCS`, nature, dated `withholding_rate`
  rows per deductee type, single and aggregate thresholds, no-PAN rate, source evidence.
- `party_withholding_profile`: deductee type, PAN status reference, lower/nil-deduction
  certificate (number reference, rate, limit, validity).
- Statutory rates load from `seeds/` with official source references — never invented (Q5).

Tests: §7 set, threshold boundaries, certificate validity by date, feature gate off → 422.

## Phase 8 — Tax on accounting vouchers

- Journal/expense/purchase-bill lines may carry tax: account default → replica rule → Phase 4
  calculation → tax lines posted to accounts resolved through posting mappings.
- Reverse charge: liability to `RCM_PAYABLE`, credit to input if ITC-eligible.
- TDS deduction on payment/bill: section + profile + threshold → `TDS_PAYABLE` line.
- `assert_postable`, idempotency key, posting-date resolution of registration and rates, tax
  snapshot persisted on the posted line; posted vouchers never recomputed.

Tests: GST expense intra/inter, RCM, ITC-ineligible, TDS below/above threshold, composition
company, closed period rejected, replay → one effect, rollback → no audit row.

Status (2026-10-06): **implemented**. Design is in [accounting-design](accounting-design.md)
§ Tax, migrations are 0104–0108, and tests are in `apis/accounting/tests/test_voucher_tax.py`.
- Evidence is stored in the `journal_tax` table, not on the posted line.
- Withholding is limited to party documents.
- Assessable charges and foreign currency are not supported on vouchers.

## Phase 9 — Clients

OpenAPI → regenerated `clients/api-client`. The console has no accounting screens today; UI for
these masters is out of scope unless requested (Q6).

## Phase 10 — Review

Walk CLAUDE.md §5 and §6, run `/simplify` and `/security-review`, report coverage and findings.

---

## Decisions

- 2026-10-10: Added [India voucher tax recording](voucher-tax-recording.md) at the user's
  request. Separated statutory timing/return status from GL posting and RCM liability from
  paid/claimable credit, with explicit future compatibility gates. State VAT, job-work compliance
  and end-to-end statutory workflows are not implied by the historical implemented phases.
- 2026-10-10: Vouchers replaces future Billing/Payments applications; Accounting retains
  authoritative tax/ledger posting. Payroll/HR is excluded. Earlier implementation evidence
  and existing contract identifiers remain unchanged.

### Original decisions (2026-10-05)

1. **Boundary** — product GST definitions stay in Catalog; accounting-side tax as above.
2. **RCM ownership** — Phase 0 proposal accepted.
3. **Large impact reviews** — chunked background job; publish references the reviewed report.
4. **`UNREGISTERED` party registrations** — allowed without a number; the row records the
   buyer's state for place of supply.

5. **TDS/TCS statutory data** — no statutory section, rate or threshold ships in code or seeds
   (catalog-product-design §9: never invent statutory values). Sections are company masters
   entered with mandatory source evidence, the way catalog tax rates are. A verified seed pack can
   be added later from an official source without schema change.
6. **UI** — console screens are out of this increment (the console has no accounting screens yet);
   the regenerated API client is delivered so screens can follow.

## TallyPrime concepts borrowed

GSTR-3B preparation increment (2026-11-02): Accounting revision 0228 adds
gst_return_record with its native model, exact wire schema, audited/idempotent
financial capture and immutable owner evidence. Registration_id identifies the
Identity-owned GSTIN without a cross-service foreign key. Return_date is the
allocated statutory period; event_date retains the original evidence date.
Category maps statutory rows, comparison/coverage, opening ledgers or actual
offsets. Source_entity/source_id identify native evidence or EXTERNAL;
reference, evidence_hash and explanation retain the reviewed source proof.
Original_record_id has a tenant/company-scoped self-reference for later-period
reversal/reclaim evidence. Taxable, IGST, CGST, SGST/UTGST and cess are
DECIMAL(19,4) with INR currency. Optional conversion_rate is DECIMAL(19,8) and
must match retained native foreign-currency execution; an INR native source
cannot carry a fabricated conversion rate. Place_of_supply, recipient,
is_advance, credit_head and explicit coverage area/status/sequence support the
prescribed mappings and readiness checks. Native source publication now also
includes retained journal_tax evidence. See
[GSTR-3B delivery and capability limits](gstr3b-delivery.md).

| TallyPrime | Here |
|---|---|
| GST details on an expense/income ledger (*Specify Details Here*) | `account_tax_default` (Phase 6) |
| *Eligible for input tax credit* on a ledger/classification | `itc_eligibility` on `account_tax_default` |
| *Include in assessable value calculation* → Goods/Services, by value/quantity | `assessable_inclusion` + `apportion_by` on `account_tax_default`, honoured by the Phase 4 calculation |
| Ledger *Type of supply* and RCM applicability | `supply_kind`, `rcm_applicable` on `account_tax_default` |
| *Nature of Payment* (TDS) / *Nature of Goods* (TCS) | `withholding_section` + dated `withholding_rate` (Phase 7) |
| Party *Is TDS deductible*, *Deductee type*, lower-deduction certificate | `party_withholding_profile` (Phase 7) |
| *Tax Analysis* (Alt+A) | the versioned tax snapshot returned with every computed voucher (Phases 4, 8) |
| *Uncertain transactions* exception list | tax-exception status on voucher preview: unresolved defaults, missing registration, regime refusal (Phase 8) |
