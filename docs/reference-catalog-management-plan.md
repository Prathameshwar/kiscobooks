# Country, state, language and currency management

Requested 2026-10-21: dedicated list, create, view and edit pages plus delete actions
for all four catalogs, linked from Settings and reusing shared CSS/navigation.
This supersedes the earlier country/state availability-only recommendation in
`manage-countries-plan.md`. All three phases agreed by the user on 2026-10-21.

## Agreed behavior

### India GST state-code amendment (2026-10-23)

India's administration state code is its official two-digit GST code, retaining leading
zeros: Maharashtra 27, Andhra Pradesh 37, Ladakh 38 and the merged Dadra/Nagar Haveli/
Daman/Diu territory 26. The API exposes this as `display_code`; ISO `code` remains the
immutable reference used by existing foreign keys and URLs. Other countries continue
to display their existing ISO subdivision code. State directories search GST numbers
as well as name/ISO code; state-code sorting is not offered for this mixed display column.

The API assigns India's GST code from the committed seed mapping and rejects unknown
Indian subdivisions and altered GST assignments. Administration labels the two identifiers
explicitly and keeps GST read-only. The original 36-state seed/generator mapping remains
the sole source of truth, so installation/regeneration preserves this policy. Special GST
jurisdictions such as Other Territory are not invented as geographical states.

Delivery phases: API enforcement/display/search, matching UI/client, then regression and
live reference-data verification. User requested this permanent change and resumed work.
No model or storage-column change is needed. The current Identity, Catalog and Accounting
catalogs were checked: each has all 36 correct mappings, and Identity's managed revision
payloads also match. Existing identifiers and records require no data rewrite.

Source checked: [GST portal state-wise data](https://tutorial.gst.gov.in/downloads/news/monthly_gst_data_for_publishing_dec_2025_final_01jan2026.pdf).

Verification: 60 Identity reference/GST/cache/registration tests, 28 Console reference/
proxy tests and 8 API-client tests passed. Auth, Console and API-client typechecks,
strict mypy on the four affected runtime modules, Ruff and generated contract checks
passed. The running Identity API was refreshed and its read-only display-code contract
verified. API-client patch version is 0.2.8; consumer lockfiles were checked offline.
Manual simplification/security review found no remaining issues; `/simplify` and
`/security-review` are unavailable in this environment. No permissions, tax calculation
or historical identifier were changed. No commit/publication was requested.

### Existing catalog behavior

- Platform operators with live `platform.config.manage` authority manage global
  catalogs. Ordinary tenant administrators cannot change shared reference data.
- Each Settings card opens a dedicated directory with bounded signed paging,
  indexed name/code search, status filters, sorting, refresh and row kebab actions.
  States additionally filter by country; each country kebab offers Manage states.
- Create, view and edit use dedicated pages with the shared `PageNavigation`
  back link/breadcrumbs, page headers, cards, forms and notices. Preserve safe list
  filters when returning. Parent/currency selections use database-backed options.
- Create validates actual reference fields and ISO-shaped unique permanent codes:
  country code/ISO3/numeric code/name/legal name/default currency/phone prefix/
  subdivision label; state code/country/name/subdivision type/tax jurisdiction;
  language code/ISO3/name/native name; currency code/numeric code/name/symbol/
  minor unit/amount-in-words labels. No assertion that a new language provides UI
  translations or that a new country provides implemented tax jurisdiction rules.
- Codes are immutable after creation. State parent-country links and existing tax
  mappings cannot be changed to reinterpret financial records. Currency minor
  units remain display metadata and never change DECIMAL(19,4) storage; protect
  financially sensitive metadata once in use. Validate dependencies server-side.
- Delete is a confirmed, audited archive/deactivation. Preserve reference rows
  and foreign keys; retired codes cannot be reused. Existing records stay readable.
  Restore is separate and explicit, subject to active parent/dependency checks.
- Add explicit management provenance/version state so administrator-created,
  edited and archived rows survive seed reruns. Keep unchanged shipped defaults
  seeded from committed ISO data. Management changes must be durably delivered to
  service-local copies before dependent configuration is usable there; do not add
  synchronous remote reads to financial writes or claim Identity-only custom
  references work across the platform. Define bootstrap/replay/version ordering.
- Require fresh verified platform authentication for writes, exact BFF allowlists,
  strict bounded typed schemas, duplicate-field/query rejection, optimistic version
  conflicts and transactional outbox/audit. No secrets or PII in catalog audit.
- Forms show field errors, pending state, success, dependency conflicts, retry and
  deliberate session recovery. Confirm archive and protect unsaved changes.

## Phases

1. **Database, policy and APIs.** Update the ownership/seed decision and schemas;
   implement management provenance, one-DDL migrations and inverse downgrades,
   domain validation, protected list/create/detail/update/archive/restore APIs,
   stable natural-code paging, dependency/historical protection and durable local
   reference synchronization. Keep models, factories, contracts, event consumers
   and consuming library locks consistent. Test permissions, seed reruns,
   concurrency, cursor binding and rollback before proceeding.
2. **Shared UI and navigation.** Link Countries, States, Languages and Currencies
   cards for authorized platform administrators. Implement dedicated directories
   and create/view/edit pages with shared reusable layouts and existing controls;
   country-to-states navigation; archive/restore confirmation; validation, notices,
   loading/empty/error and reauthentication states. Add page/component tests.
   Payment gateway and Notifications remain disabled.
3. **Integration and final review.** Regenerate OpenAPI/client types, run relevant
   checks, verify native MySQL migrations and managed-seed preservation, exercise
   service propagation and UI CRUD/validation/history against disposable records,
   check responsive layouts/themes/keyboard navigation, review simplicity,
   authorization, audit and financial invariants, and update execution evidence.
   Restore the normal runtime and remove disposable data/processes. No publishing.

This spans services, migrations and more than about 100 lines, so CLAUDE.md section
2 requires agreement to these phases before application implementation (received). The user's
latest request explicitly expands the CRUD scope; archive is the proposed delete
contract needed to retain historical reference integrity.

## Review evidence before implementation

Country/state/currency tables are shared natural-code models and Language is an
opt-in shared ISO table. All current records come from installation seeds. The
shared seeder overwrites canonical fields and deactivates unshipped codes, so
writing directly to those rows alone would undo new CRUD changes. No global
reference-management source event/consumer currently exists. Settings has four
disabled placeholders and no Language/Currency cards. The platform proxy accepts
tenant/details routes only. Earlier preparation verified 28 Console and 10
Identity regional tests, plus failing regressions for missing country/state routes
and Settings links. Shared back navigation is now implemented and independently
verified; reuse it here.


## Completion

All three phases implemented and reviewed on 2026-10-21. See
[verification](reference-catalog-management-verification.md) for evidence,
live migration heads, runtime status and the exact archive contract.
