# Company accounting defaults delivery

## Authorized scope and phases, 2026-11-03

The user approved Discount Allowed/Received and all High-priority categories in
the defaults gap note, including missing parent groups, followed by a final
review of company creation. Medium/optional categories remain deferred.

1. Extend the versioned business chart with discounts, purchase returns, freight,
   payment clearing and merchant fees; preserve existing identities and groups.
2. Provision inventory COGS and applicable registration-specific GST/VAT accounts,
   profiles and supported dated mappings through the existing company setup
   transactions. Use fixed internal selections with company scope and field policies.
3. Verify creation, repeats, missing groups, conflicts, applicability, rollback,
   tenant/company isolation, migration parity and the Identity setup handoff.
   Review security, correctness and simplicity, then document actual evidence.

## Implementation decisions

- Discount Allowed is under Indirect Expenses; Discount Received under Indirect
  Income. These accounts are available for explicitly classified adjustments;
  invoice trade discounts keep their existing net revenue/inventory calculation.
- Purchase Returns is under Purchase Accounts; Freight Inward under Direct Expenses
  and Freight Outward under Indirect Expenses. Existing landed-cost allocation
  and source-linked return posting continue to determine transaction treatment.
- Gateway Clearing and POS Clearing are GENERAL assets under Current Assets;
  Merchant Fees is under Indirect Expenses. These are available empty ledgers,
  not fabricated bank/provider contracts or automatic settlement connections.
- Inventory companies receive COGS under Direct Expenses, with COST_OF_GOODS mapping
  only where no operator mapping already applies.
- Tax accounts follow authoritative registration facts and feature flags. No tax
  registration, tax rate, balance or posted transaction is invented. VAT ledger
  provisioning does not enable an unimplemented VAT calculation or filing engine.
- Existing charts are not bulk rewritten. Standard setup retries preserve existing
  identities, custom mappings and posted facts. Code conflicts must not silently
  adopt a custom account. Template version changes preserve prior receipts.
- Tax registration is a post-creation operation in the existing wizard. Adding a
  registration requeues only the enrolled books step, invalidates an in-flight lease
  and uses a feature/registration-specific command key. The original setup actor's
  live authority is rechecked. Older companies without an enrolled plan continue
  to use explicit initialization; this does not bulk enroll existing companies.
- Existing APIs and schema suffice; no model/DDL/API-shape changes were needed.

## Resulting fresh-company counts

| Configuration | Heads | Groups | Accounts |
|---|---:|---:|---:|
| Common business defaults | 5 | 28 | 20 |
| Inventory enabled, no taxes | 5 | 28 | 26 |
| One regular GST registration, no inventory/RCM | 5 | 29 | 33 |
| Inventory and one regular GST registration, no RCM | 5 | 29 | 39 |
| One standard VAT registration, no inventory | 5 | 29 | 23 |

Regular GST adds 12 profiles (input, pending input and output across CGST,
SGST/UTGST, IGST and Cess) plus a payment control ledger per registration.
Reverse charge adds four profiles only when enabled. Each enabled TDS/TCS feature
adds two accounts. VAT adds input/output and payment control for standard regimes;
restricted regimes omit input recovery. Expired, unregistered and specialist GST
registrations are skipped; supplier regimes follow the existing charge/recovery
rules. Future registrations receive mappings beginning no earlier than their
validity and books start dates. Existing mappings for a purpose/registration/currency
are preserved, including operator-authored date windows; setup does not silently
fill gaps in an operator's mapping schedule.

## Verification and review

Findings corrected during review:

1. Registration added after the initial books command could otherwise be missed;
   the durable refresh and facts-specific owner key now cover that lifecycle.
2. VAT profile validation expected a generic `vat` registration, whereas Identity
   supplies `vat_gb`/`vat_eu`/`vat_ae`/`vat_sa`; those supported systems now validate.
3. Native MySQL rejected the original long GST installation key. Full registration
   UUIDs are now encoded in Base32 with compact direction markers, fitting the
   existing 60-character column without truncation or a schema change. A regression
   asserts identifiers against actual model column limits.
4. Old chart-count assertions now include the approved additions while continuing
   to check tenant/company ownership, custom groups and cash conflicts.

Verified evidence (2026-11-03):

- **16 passed on native MySQL**: the new default-account API acceptance suite and
  existing standard-stock suite, against a freshly migrated disposable schema.
  Covers creation/replay, later and multiple registrations, GST/VAT profiles,
  inventory COGS, field-deny rollback, custom-code conflicts, narrow bootstrap
  authority, retained operator mappings and no journal creation. The schema was
  removed afterward. Local evidence:
  `.test_artifacts/default-accounts-b073e3c60c07441c8c8c031afe8e9cad/`.
- **17 passed**: pure applicability/identifier tests, including UTGST, RCM,
  withholding, restricted regimes and registration date windows.
- **17 passed**: existing tax-mapping and financial-setup API regressions.
- **24 passed**: Identity company setup, statutory API and the new refresh test.
  The refresh test creates a company and registration through the real Identity
  API, then checks worker state, signed owner context, changed/stable command keys
  and tenant isolation using a mocked Accounting HTTP transport. Accounting's
  owner behavior is independently exercised by the native API tests above.
- **9 passed** on the final chart/cash/bootstrap rerun and **5 passed** on the
  final master API/template suite. The broader 43-case sweep
  passed 40 and identified three outdated count/receipt assertions; these were
  corrected, and both affected suite reruns above passed completely.
- Accounting and Identity changed-source Ruff/format, strict mypy and OpenAPI
  freshness checks passed. No client regeneration or migration is required.
- Read-only local schema verification found Accounting **147 tables / head 0231**
  and Identity **67 tables / head 0100** aligned with models, migrations and
  readiness. No missing/extra tables, native differences or Alembic drift.
- Reloaded the managed Identity and Accounting APIs and company-setup worker.
  Identity (8001) and Accounting (8011) returned **HTTP 200** from `/health/ready`;
  the company-setup worker is running. No business company was created for live
  testing; native acceptance used only the disposable schema above.

Manual simplification and security review followed CLAUDE.md sections 5 and 6:
fixed selections cannot be supplied by an API caller; initialization remains
company-scoped under current authority; field policies and transactional audit
still apply; company locks and fenced setup leases preserve retry safety; no
balances, journals, rates, registrations or settlement contracts are fabricated.
The `/simplify` and `/security-review` slash commands are unavailable in this
session, so their equivalent review was performed manually. This is targeted
creation/defaults evidence, not a full application-suite or browser end-to-end
certification. No unresolved findings remain within the reviewed creation/defaults
scope. VAT account provisioning does not add VAT posting or filing.

## Follow-up final review, 2026-11-03

The expanded combined-feature test exposed a Windows configuration gap: missing
`ACCOUNTING_UTGST_STATES` defaults to an empty set, causing a Chandigarh registration
to receive SGST rather than UTGST accounts. Windows environment generation now
adds the reference-backed territory list for fresh files and backfills it when
missing. Explicit values, including an empty list, survive retries and forced
regeneration. Account selection and tax calculation continue to share the same
configured list; no statutory list was hardcoded into their domain logic.

The versioned configuration is `start/win/conf/utgst-states.json`. Its source is
the [UTGST Act, sections 1(2) and 2(8)](https://www.indiacode.nic.in/bitstream/123456789/2252/1/A2017-14.pdf),
mapped to existing platform ISO subdivision codes. Other territory has no selectable
subdivision in the current reference catalogue. Deployments outside the Windows
launcher must supply their own reviewed `ACCOUNTING_UTGST_STATES` configuration.

Added regressions exercise registration arrival while the owner request is still
running, including both stale success and stale failure. Both must leave the new
books refresh pending; a subsequent request carries the new registration and a
different command key. The field-deny test now asserts unchanged audit outbox IDs
as well as rollback of account/setup records. The combined inventory, UTGST, RCM,
TDS and TCS test verifies 47 accounts, 20 tax profiles and 21 posting mappings,
with stable account IDs on replay.

The local missing setting was backfilled without replacing existing values.
Read-only assessment found **zero local UTGST registrations and zero affected
SGST profiles**; no existing accounting records required correction.

Follow-up verification: **3 Identity lifecycle cases passed**, **5 Windows
configuration/encryption regressions passed**, and **2 native MySQL cases passed**
(combined defaults and audit rollback). The disposable schema was removed;
evidence is in `.test_artifacts/default-accounts-92ca5c599d814fbd9d6c7f71cb383605/`.
Changed Python tests pass Ruff and formatting checks. Loading the local Accounting
settings confirms all five configured subdivisions. Models, migrations, API
contracts and account counts for other configurations are unchanged.
Accounting was restarted with the corrected environment. Both Accounting and
Identity returned HTTP 200 readiness; the company-setup worker remains running.
The follow-up security/simplicity review found no additional unresolved issues in
this scope: configuration is local reference data, explicit values are preserved,
no runtime network lookup was added, and no business records were rewritten.
