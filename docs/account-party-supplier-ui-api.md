# Account, party and supplier configuration delivery

Party and supplier imports are available from their list actions. See
[party-import-ui-delivery.md](party-import-ui-delivery.md) for the reused workflow,
native ready-supplier/customer commands, authorization rules and verification.

## Party directory type visibility (2026-10-31)

The party directory must display the stored Organisation/Person identity type and
separate active Customer/Supplier/Other/Broker roles. Show `No active role` for a
readable empty role set; do not infer supplier status from the directory being viewed.
Unreadable types/roles remain protected. No stored classification is changed.

Delivery: first reproduce the missing list projection and column with regressions;
then extend the lean party response with the existing type and field-protected active
roles, using scoped EXISTS predicates in the same paged query. Regenerate contracts,
render clear labels on both party/supplier lists, and verify permissions, inactive
roles, paging and empty values before reviewing CLAUDE.md sections 5/6.
The role-list schema also now accepts the already-supported BROKER value; its
previous omission caused a response-validation failure when listing a Broker role.

Verification: fail-first API regression reproduced the missing party_type projection;
six UI regressions reproduced missing columns/values. All 54 affected directory,
actions and navigation UI tests passed. The new API regression passed on disposable
native MySQL, including paging, empty roles, draft/retired role exclusion and independent
type/role field denies. Full Console TypeScript, Accounting Ruff/strict mypy and
OpenAPI/client freshness checks passed. Live browser review confirmed the existing
Supplier and Customer labels alongside the stored Person type. No business rows were
changed by this review.
Eleven existing configuration API regressions passed, and the final focused SQLite
regression passed after fixing the Broker response mismatch discovered by that run.

Manual CLAUDE.md sections 5/6 and simplification review found no additional issues:
the existing scoped predicate supplies role visibility, conditional denies remain
conservative, cursor authority stays bound to field policies, no per-row API reads
or financial writes were added. The named /simplify and /security-review commands
are unavailable in this session; this is the equivalent manual review.

For the 2026-10-27 non-party account follow-up, see
[account-kind-experience-review.md](account-kind-experience-review.md). All seven
native ledger kinds share Accounts; bank/tax profiles are supporting forms, with
scoped company-bank creation now available from bank-profile setup.

Requested 2026-10-25. Implement the existing Accounting masters and their configuration
with the shared console styles, controls and layout. This is the selected execution
plan for the user's requested phased implementation.

## Phase 1: native contracts and safe editor support

Inspect existing schemas, resource permissions, field policies, lifecycle rules and
database alignment. Reuse native Accounting commands, audit/outbox, optimistic versions,
idempotency and dated policies. Add bounded supplier-role filtering, scoped searchable
references and operation-aware form metadata where the existing contracts lack them.
Regenerate OpenAPI/client contracts; add matching migrations only if storage changes.

Suppliers are parties with a SUPPLIER role. A party may also be a customer; creating a
supplier must not duplicate the party identity, addresses or accounts. Account definitions
never hold editable balances. Used/system classifications and dated history remain protected.

## Phase 2: pages and configuration workflows

Deliver account, party and supplier directories and details, create/edit forms, supported
lifecycle actions and history. Include account groups needed for account setup; account
aliases, bank/tax profiles and posting defaults; party roles, addresses/contacts and their
uses, identifiers/registrations, beneficiaries, classifications, terms and dated accounting,
credit and withholding configuration. Reference/master creation pages are linked where
needed, rather than requiring UUID entry. Provide company setup initialization and reviewed
base-chart installation so a new company can use the account pages.

Reuse shared SearchSelect, field controls, tables, kebab actions, confirmations, navigation,
formatters and unsaved-change protection. Render native metadata and scoped grants; preserve
masked values, exact decimal strings, validation drafts and uncertain command identities.
Supplier setup makes its party and role stages explicit and recoverable.

## Phase 3: review, fixes and evidence

Run appropriate API/native database tests, generated-contract/static checks, UI tests and
production build. Review desktop/mobile themes, accessible controls, navigation, 401/403/
409/422/500 handling, permission boundaries, sensitive beneficiary handling and replay.
Walk CLAUDE.md security/correctness invariants, record findings and fix them. Keep local
paths and all existing unrelated edits; no live financial/configuration data is changed by
verification, and no publication to GitHub is part of this task.

## Initial findings

- Native typed Accounting CRUD, resource/field permissions, signed keyset lists, retained
  history, scoped encrypted beneficiaries and dated configuration already exist.
- Suppliers use party roles; no separate supplier table is needed.
- Existing console Accounting access is mainly read-only lookup and transaction support.
- Current field-set metadata describes create fields but lacks object/operation-specific
  edit guidance and typed controls for exact decimals and scoped references.
- New storage has not been identified as necessary.

## Delivered workflows

All three phases are implemented. Open **Books → Accounting configuration**, or the
Accounting link in company settings/current-company configuration. The overview links
the primary masters and every permitted supporting configuration area.

- Accounts: directory, create/edit, detail, retained history and supported activation/
  retirement; groups, aliases, external references, bank/tax profiles, tax defaults and
  posting mappings are linked from the owning record. Financial balances are not form fields.
- Parties: shared identity, customer/supplier/other/broker roles, addresses, contacts,
  dated address/contact uses, business identifiers, tax registrations and registration
  addresses, encrypted beneficiaries, classifications, accounting/credit/withholding
  policies and certificates. Related directories carry the owner into creation forms.
- Suppliers: native active-SUPPLIER role filter, with explicit recoverable stages:
  create the party, activate the party, create its SUPPLIER role, activate the role.
  Existing parties can receive another role without creating another identity.
- Reference configuration: fixed account heads are read-only; account groups, commercial
  types, payment terms/instalments and withholding sections/rates have their native
  management pages. Terms and dated policies retain the server's dependency/date rules.
- Company setup: native initialization, base-chart review/install, conflict explanation,
  optional Identity-owned GST registration and SGST/UTGST selection, and exact recovery.

Forms use native operation-aware field metadata, shared controls/CSS, searchable scoped
references, metadata labels/order, sparse protected values, native expected versions and
exact decimal strings. Inputs remain mounted during pending/uncertain saves. Failed
validation retains the draft and focuses the invalid field; conflicts require reviewed
reload, while unconfirmed commands retain the same body and idempotency key.

## API, permissions and database alignment

Added read-only native `/configuration/{resource}/field-set` and
`/configuration/options/{source}` endpoints. Resource names/sources are closed typed
contracts. Read hints respect field policy, current company scope, immutable identities,
active/used account semantics, draft profile parents and dated intervals. A deny on a
necessary lifecycle field blocks edit hints rather than revealing that field indirectly.
Party directory role filtering requires the role's contributing fields to be readable.
References use bounded signed keyset pages; exact hydration can show retained inactive
identities without permitting their selection for new records. Withholding rate labels
include readable deductee/date/rate terms. Beneficiary account numbers remain write-only.

The console and its request bridge use existing company-scoped Accounting permission
families. Role names, global UI permission arrays and platform-admin labels do not grant
company access. Identity bank/tax-registration and Catalog tax-rule lookups use their
owners' existing read authority; no synchronous owner call is introduced into a write.
Native commands remain the authority for validation, audit/outbox and idempotency.

No model or storage change was needed. Live Accounting schema audit: migration head
**0167**, **109 tables**, no missing/extra tables or Alembic model drift. OpenAPI, native
resource matrix and the Accounting client are regenerated; API client version **0.2.17**
and consuming workspace lockfile resolution are synchronized. The managed local
Accounting service was refreshed and both new routes were verified in its OpenAPI.

## Review and verification

- Broader API/native regression: **43 passed, 1 optional skipped**. Final configuration,
  matrix and schema-contract checks: **17 passed, 1 optional skipped**, plus the focused
  regression preventing unreadable account-kind hints from disclosing record semantics.
- Migrated disposable MySQL: **23 workflow regressions passed**, followed by **9 final
  configuration regressions passed**, plus native setup/template, concurrency,
  query-plan and migration downgrade/upgrade/metadata checks. The disposable database
  is dropped; live business data is not rewritten by these checks.
- Focused console workflow/contract/page/review tests: **164 passed** before the final
  full-console run. Existing Product tests passed unchanged after extracting the shared
  service read/list/command/navigation mechanisms.
- Browser: **48 checks**, 1440px/390px and light/dark/ledger themes, real console
  components/shared CSS/native field metadata with a fixture BFF. Native persistence
  and isolation are tested separately on migrated MySQL.
- Strict Accounting mypy, Ruff, console TypeScript, production build, regenerated client,
  OpenAPI and resource-matrix checks passed. Full console: **1,698 tests passed** across
  133 files. Coverage is **98.00% statements/lines,
  85.64% branches and 81.85% functions**, improving the prior 97.93/85.50/81.28 baseline.
  The pre-existing global **90% function-coverage gate still fails**; thresholds were not lowered.

Manual CLAUDE.md §5/§6 and simplification review found and fixed lifecycle hint leakage,
missing withholding-rate labels, bridge list-query validation, filtered child-create
navigation, unreachable supporting configuration, chart-conflict dead actions and input
remount/focus loss. Resource authority now runs before the shared readiness gate,
including companies with pending setup. Kind-choice hints only use readable, unconditional
kind values. Exact recovery, tenant/company authority, protected fields, native
audits and retained financial identities were rechecked. `/simplify` and
`/security-review` commands are unavailable in this session; these reviews were performed
manually. No new dependency, service, permission key or financial posting capability
was added.

## Decision log

- 2026-10-25: The user's explicit UI/configuration request selects the native Accounting
  master administration scope previously deferred from backend delivery. Suppliers remain
  parties plus roles; configuration uses existing commands/storage. Native financial
  execution, credit enforcement, bank verification/provider integration and statutory
  source content remain governed by their existing contracts.


## Experience refinement and role-picker correction (2026-10-27)

Accounts, parties, suppliers and their supporting native forms received another
UI/flow review with live tenant3 verification. Compact scoped directories, resource
sections, accessible multiline fields, readable facts, protected related-party context,
create-conflict correction and grouped navigation reuse the shared design system.

The party reference picker now applies the same field-protected active-role predicate
as the native party directory. This corrects the existing supported role query that
previously failed on a nonexistent Party.role column. Exact reference hydration retains
historical identities. Suppliers fail closed when role filtering is not available.
No public schema, storage, financial lifecycle or permission expansion is introduced.

See [account and party experience review](account-party-experience-review.md) for
findings, corrections, native/UI evidence and the exact live verification scope.
