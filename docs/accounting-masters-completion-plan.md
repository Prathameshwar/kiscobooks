# Accounting masters completion plan

Status: implemented and verified with two review/fix passes, 2026-09-14. This plan supersedes the
remaining AM3r-AM7r execution sequence in [the earlier checklist](accounting-implementation-todo.md).
Execution and two final review/fix passes are tracked in [the live todo](accounting-masters-todo.md).

## Outcome and boundary

Deliver a complete, consistent Accounting master-data API within the agreed scope: chart of
accounts, groups and aliases; account identities and profiles; parties and their supporting
masters; dated policies; templates; master imports, exports, metadata and history. A master
must work through all supported entry points, including upgrades of existing company data.

The target is 29 business tables, adding `account_group_alias` to the existing 28. Infrastructure
tables are counted separately. Five internal accounting heads remain. The approved Tally
alignment covers master classification and configuration; it does not promise all Tally
features or data-file interoperability.

Journals, vouchers, balances, opening postings, settlement, financial closing, transaction tax
calculation, live credit enforcement, and Billing/Catalog consumers remain deferred. Cost
centres/categories and administration screens remain outside this increment. Fax, website and
email-CC fields are optional future scope. Bill-wise and credit configuration continue to use
existing dated party policies rather than duplicate account fields. Tax rates remain Catalog-owned.

## Verified starting point

- Current code has 28 business tables, migration head 0037, 25 base template groups and template
  version 2. The registration-specific tax extension adds its own supporting group.
- The September 14 repairs are complete: field authorization, lifecycle/dependency integrity,
  effective dates, template collision repair, bounded import receipts, Identity field-policy
  authoring, gateway authentication, audit publisher and generated Accounting client.
- Last complete Accounting run: 81 tests on MySQL 9.6.0, 94.92% coverage, migration parity and
  upgrade/downgrade/upgrade passed. Source Ruff and strict mypy passed. See
  [the review](accounting-review-20260914.md) for integration evidence and limitations.
- Two broader Identity Salesperson-role test expectations fail independently of Accounting.
  Recheck their ownership/status during final integration; do not silently change unrelated roles
  or claim the entire repository is green.

## Phase 1 — Freeze the master contract and compatibility rules

Produce a resource/field matrix naming ownership, types, defaults, permitted edits, lifecycle,
dependencies, permissions, query support and import/export behavior. Reconcile the old checklist
with the verified baseline. Include every existing resource, not only the new columns.

Record these proposed implementation decisions before DDL:

- Primary/reserved classification is server-controlled. Distinguish five internal heads from
  primary groups. Derive inherited classification from the primary ancestor; reject conflicting
  child values. Document the stock-in-hand gross-profit exception and canonical seed defaults.
- Preserve existing object IDs, codes, user names, references and installation history during
  upgrades. A normal template install cannot bypass field policy or used/system-master guards.
- The Reserves-to-Capital hierarchy correction must be explicitly previewed. An incompatible or
  financially used hierarchy that cannot be changed under the established history rules returns
  a conflict with no partial upgrade; legacy installations remain usable until reconciled.
- Rounding is disabled by default. Proposed enabled methods are normal/up/down with a positive
  Decimal limit; validate bounds and resolve currency through BASE/FIXED mode. Reject enabled
  rounding for an ambiguous MULTI account. Keep classification immutable under the existing
  active/financial-use rules; no runtime financial calculation is introduced.
- Define `duty_type` compatibility with the existing scheme, component, purpose and company
  registration fields. Cover GST, VAT, TDS, TCS, CESS, EXCISE and a backward-compatible OTHER
  classification. Do not label a duty supported merely because its enum can be stored: each
  supported kind must have a valid create-to-activate profile path. Document how legacy OTHER
  records retain their meaning rather than guessing their classification.
- Address defaults are scoped by party, purpose and optional registration, matching the current
  model. General and registration-specific defaults may coexist; duplicate active defaults in
  the same scope may not. Selection must use explicit registration/date context and never choose
  an arbitrary GST registration when more than one is eligible.

Exit: reviewed field/default/compatibility matrix and migration sequence, with no unresolved
behavior hidden in implementation. Any departure from existing documented decisions is called
out in the design decision log.

## Phase 2 — Complete groups, aliases and template upgrades

Implement the 28-group base chart: add Branch/Divisions, Suspense and Miscellaneous Expenses;
place Reserves under Capital where the safe-upgrade rules permit. Retain the internal Equity
head and define its explicit mapping to Tally's Liabilities nature. Separate the 28-group base
count from optional registration-specific groups.

Add the ten planned group attributes: `is_primary`, `is_reserved`, `affects_gross_profit`,
`is_revenue`, `is_deemed_positive`, `sub_ledger_behaviour`, `nett_balances`,
`used_for_calculation`, `allocation_method`, and `sort_order`. Implement validated inheritance,
cycle/depth limits, reserved/primary restrictions and account-subtree compatibility.

Add `account_group_alias` with company-scoped references and uniqueness, lifecycle, protected
CRUD/list/field-set, import/export and history/audit support. Reuse group read/manage permissions.
Alias lookup must be unambiguous within its documented namespace and collation rules.

Deliver a new versioned template with preview, fresh install and existing-install upgrade.
Preview identifies adds, safe metadata changes, hierarchy changes and conflicts; apply rechecks
under the company lock. Preserve version 1/2 receipts and bindings, registration-safe tax account
reuse, existing names and IDs. A repeated command has one effect; failure leaves no partial data
or audit state. Do not treat a version increment or a new installation row as proof that existing
groups received the new attributes.

Exit: fresh base chart has 28 groups with the planned 15-primary/13-subgroup layout; valid legacy
upgrades converge without duplicates; protected legacy conflicts are explicit and atomic.
Aliases pass cross-tenant/company tests, and hierarchy/metadata behavior matches the phase 1 matrix.

## Phase 3 — Complete account and profile metadata

Add account `inventory_affected`, `rounding_method`, `rounding_limit` and `sort_order`, plus
tax-profile `duty_type`. Apply the phase 1 currency, default and compatibility rules to create,
update, activation, imports, templates and mapping validation. Keep Decimal(19,4) storage and
reject float input. Existing bank/party account separation and active-profile immutability remain.

Complete the account-kind versus group-nature matrix for GENERAL, CASH, BANK, PARTY, TAX,
INVENTORY_CONTROL and ASSET_CONTROL, including customer/supplier roles. Exercise referenced
group changes as well as direct account edits. Account/profile templates must populate valid
metadata and preserve existing dated policies and mapping references.

Exit: every supported kind/profile has happy and invalid lifecycle cases; rounding bounds/currency
and duty combinations are enforced; existing active/used accounts retain their semantics after
schema/template upgrade. These are master settings only, with no tax or inventory execution.

## Phase 4 — Close party, address and registration completeness

Verify the whole existing party model: multiple roles and accounts; addresses and contacts by
purpose; business identifiers; registrations and address associations; bank beneficiaries;
commercial types/memberships; payment terms/schedules; and dated accounting/credit policies.
Reuse the working structures and tests, adding missing rules only where the matrix shows a gap.

Exercise a party with billing and shipping addresses in different states and multiple valid
registrations. Verify explicit address-registration associations, state/scheme consistency and
effective-date containment, including expired/future and ambiguous associations. An interstate
delivery alone must not create or assume a registration. Add bounded, indexed resource-specific
filters such as address/registration IDs where existing reads cannot retrieve the required link.

Test default replacement, duplicate active defaults, retired references, overlapping policies,
role retirement, owned component retention and raw bank-value protection. The acceptance result
is correct master linkage and retrieval; transaction place-of-supply/tax selection stays deferred.

Exit: the complete party scenario succeeds through public APIs with scoped credentials, and
wrong-party/company/state/date or ambiguous associations fail consistently with error envelopes.

## Phase 5 — Finish API contracts and all master workflows

Replace generic `Page[dict]` export contracts with resource-specific typed export responses.
Prefer explicit typed routes at the existing `/exports/<resource>` URLs, retaining wire format,
paging and current field policy. Denied values must remain omitted rather than fabricated as
nulls; raw beneficiary numbers and ciphertext never become export fields.

For every new field/resource update schemas, lean list projections, field-set metadata, supported
filters/sorts and indexes, import preview/apply, exports, history and audit event registration.
Use bounded signed cursors with stable tie-breakers. New filter/sort fields require native query
plan review. Extend the generated Identity field contract, policy-authoring tests, Accounting
OpenAPI and TypeScript client together; introduce no permission grants unless explicitly needed.

Retain 200-row import support, preview rollback, optimistic versions, stable idempotency keys,
legacy receipt compatibility and current authorization on replay. Fix per-route gaps against
the established API conventions, including response/error shapes and create Location headers.

Exit: compile-time client examples cover each typed export and the new master writes. A new
field works consistently through create, edit, transition, list, import, export and history,
including conditional read/write denies and policy revocation.

## Phase 6 — Verify, review and prepare delivery

Run the complete Accounting native suite on a disposable schema, plus affected Identity/client/
Audit checks. Add an upgrade fixture starting from the current 0037 schema with realistic version
1/2 installations, renamed/custom groups, used accounts, policies and audit history. Test failure,
retry and rerun of the schema/data upgrade; verify all old IDs and relationships survive.

Finish strict typing for Accounting tests and tools as well as source. Complete the full master
endpoint matrix, concurrency, tenant/company isolation, field-policy, encryption, optimistic
version and audit rollback/replay checks. Refresh gateway/Identity/publisher integration evidence
where changed contracts affect it. Make reusable new verification harnesses part of the repository.

Review simplification, authorization, sensitive data, financial-master invariants and audit
against CLAUDE.md. Run the named review tools when available; otherwise document the manual
equivalent and its findings. Update the design, actual table/migration counts, decisions, README,
permission/seed documentation and the completion checklist. Verify the documented publisher
startup and Audit source configuration using isolated test credentials.

Exit: all Accounting and affected integration checks pass; Accounting coverage is at least the established
94.92% baseline with every domain at least 90%; lint/format, strict typing, generated artifacts and
native migration parity pass. No unresolved blocker in the master scope. Report unrelated suite
failures separately. Prepare a task-only change set and release/rollback notes. Publishing, when
authorized, uses `git publish --dry-run` then `git publish`; live deployment remains a separate action.

## Rules applied to every implementation phase

- Deliver model, migration, schemas, runtime behavior, tests and generated contracts together.
  No schema-only intermediate phase. Use one DDL statement per revision and inspect native DDL,
  constraints, collation and indexes; do not assume the old estimated revision count is complete.
- Preserve historical migration files. New columns need explicit safe defaults/backfill and
  downgrade behavior. Versioned seed/data upgrades remain outside DDL migrations, with a defined
  startup/readiness contract so incomplete backfills cannot serve incorrect metadata.
- Use tenant-scoped sessions and company locks; enforce reference scope and current field policy
  on every entry point. Add no cross-service ORM import or database foreign key.
- Write and observe failing regression tests before fixing a defect. Run affected tests at each
  phase exit. The current 81 tests are the starting suite, not a fixed target count.
- Preserve concurrent Catalog/UI work, local paths, old receipts and master identities.

## Reference alignment

Tally's published chart has 28 predefined groups, divided into 15 primary and 13 secondary
groups. That validates the existing plan's target count. [Tally accounting overview](https://help.tallysolutions.com/accounting-in-tally-prime/).

Group aliases, nature, gross-profit placement, sub-ledger presentation, net balances and
purchase expense allocation are documented configuration concepts. The exact persistence,
inheritance and stricter history protections above are this project's proposed implementation
rules. [Tally group configuration](https://help.tallysolutions.com/groups-in-tallyprime/).

GST ledger setup documents duty classification, tax component, rounding method and limit;
this plan adds only validated master configuration. [Tally GST ledger setup](https://help.tallysolutions.com/set-up-tax-ledgers-for-gst/).
