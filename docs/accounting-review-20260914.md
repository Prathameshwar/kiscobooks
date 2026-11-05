# Accounting API review and repairs — 2026-09-14

The review found 17 defects/integration gaps in the current master-data API, plus missing
gateway, audit-publisher and generated-client wiring. They are repaired locally. The main
pattern was inconsistent validation across creation, ordinary updates, lifecycle transitions,
templates and replay. A valid initial record could later be changed into an invalid dependency,
or a field restriction could disappear when evaluated against a different record shape.

The review covered Accounting routes, resource/schema definitions, commands, reads, imports,
templates, mapping drafts, hierarchy, effective dates, models/migrations, idempotency and audit;
Identity's policy authoring/context; nginx; runtime settings; and TypeScript contracts. No
business table, migration, dependency or shared-library version changed. Existing Catalog and
UI edits were preserved. This report concerns local source and isolated verification, not a
production deployment.

## Findings and fixes

| # | Severity | Reproduced behavior | Repair |
|---|---|---|---|
| 1 | High | Conditional write denies missed status or other fields on PATCH/transition | Evaluate complete native snapshots before and after changes, retaining a narrow changed-field set |
| 2 | High | A UUID-conditioned deny leaked a field in detail/replay while export hid it | Normalize operands and record values consistently; preserve Decimal membership equality across storage scale |
| 3 | High | Templates created ACTIVE groups/accounts despite status write denies | Include implicit lifecycle changes and system keys in field authorization |
| 4 | High | Different UUIDv7 GST registrations sharing a millisecond reused the same tax accounts | Version 2 uses all UUID bits; reuse legacy accounts only after exact profile/registration/classification checks |
| 5 | High | Moving a payment line left an ACTIVE term with no schedule | Make line ownership immutable |
| 6 | High | Editing a party role orphaned accounts; retiring it ignored commercial memberships | Preserve role identity and block retirement with current/future memberships; preserve commercial-type role identity too |
| 7 | High | Changing a group's head invalidated CASH accounts before their first financial use | Reject head changes in any subtree containing accounts; retain existing financial-use movement checks |
| 8 | High | Changing an active tax profile invalidated existing posting mappings | Permit bank/tax profile changes only on unused DRAFT accounts |
| 9 | High | Clearing an expired policy's end date rewrote elapsed history | Freeze expired intervals; current rows can only change their end date without backdating it |
| 10 | Medium | Dependent validity extended outside party/company registration dates | Require contained intervals; reject parent date changes that exclude existing children |
| 11 | Medium | ACTIVE contact-use updates could point at an INACTIVE contact | Validate reference eligibility against resulting lifecycle state on every write |
| 12 | Medium | Mandatory profiles/schedule lines prevented unused parents from retiring | Distinguish owned components from independent live consumers; retain owned rows as history |
| 13 | Medium | A valid 200-row import preview succeeded but apply exceeded the receipt ceiling and returned 500 | Store ordered UUID references within the existing ceiling; reconstruct request keys on replay; accept old receipts |
| 14 | Medium | History exposed revision existence/field names despite resource field denies | Enforce structural read restrictions and filter denied changed-field names |
| 15 | Medium | A required field already populated in a draft falsely blocked activation | Check layout requiredness against complete resulting state |
| 16 | Integration | Identity rejected Accounting policy/layout authoring despite forwarding Accounting policies | Add a generated native field contract, guarded policy/layout APIs, and shared current subject/scope resolution |
| 17 | Tool safety | An inherited application database URL overrode the verifier's disposable migration URL | Bind process-local migration configuration to the validated random schema, verify connection identity and restore the environment |

The initial native diagnostic produced 19 failure observations and eight passing controls on
MySQL 9.6.0. Several findings have multiple observations. Regression tests were added and run
failing before the corresponding fixes. Evidence is retained under the ignored local directory
`.test_artifacts/accounting-review-20260914/`; the original diagnostic report describes the
pre-fix state and must not be read as the current behavior.

Regression suites:

- [Authorization](../apis/accounting/tests/test_authorization_regressions.py): conditional
  status/UUID/Decimal/pattern policies, transition snapshots, protected history, initialization,
  templates, creation semantics, malformed conditions and form writability.
- [Integrity](../apis/accounting/tests/test_integrity_regressions.py): ownership, role identity,
  memberships, group classification, active reference changes, interval containment, historical
  edits, profile semantics and retirement.
- [Workflows](../apis/accounting/tests/test_workflow_regressions.py): UUIDv7 collisions, legacy
  installation repair including financially used accounts, maximum imports/replay and verifier
  environment isolation.
- [Runtime](../apis/accounting/tests/test_runtime_integration.py): gateway contract, scoped
  publisher/entrypoint, generated native field contract, and repeatable environment setup.
- [Identity integration](../apis/identity/tests/test_accounting_policy_api.py): policy/layout
  administration, delegation, tenant authority, active groups, current scoped roles and expiry.

## Integration completed

Nginx now obtains Accounting actor/company contexts through Identity authorization, strips
client-supplied context headers, and returns JSON authorization/dependency errors. Development
environment generation shares Identity's gateway signer and preserves existing encryption,
database and UTF-8 settings during alignment; duplicate stale signer entries are removed.

Accounting has a separate audit publisher entry point using shared confirmed outbox delivery.
Its key is restricted to issuer `accounting`, audience `audit`, and the explicit service event
contract. The Audit consumer must be configured with matching private source credentials.
The [README](../apis/accounting/README.md) gives runtime configuration and upgrade commands.
Tests do not drain an existing application outbox or provision production credentials.

The generated API client now exports `createAccountingClient` and Accounting types. Identity's
OpenAPI/client include Accounting policy entities. Native Accounting fields are generated into
an Identity-owned data artifact; Identity does not import Accounting's models at runtime.

## Verification

Completed checks on the final implementation:

- Full Accounting suite on **MySQL 9.6.0: 81 passed in 276.65 seconds**, **94.92% coverage**
  (above the 94.02% starting baseline). Domain rules have 99% branch-inclusive coverage and
  reference rules 100%. All 37 migrations upgraded, matched ORM metadata, downgraded to base,
  and upgraded again; the verifier exited **0**. Native setup, template installation, listing
  and concurrent idempotent requests passed. Each run used and removed only its own random
  schema. Log: `.test_artifacts/accounting-review-20260914/native-final.log`.
- The two existing assertions affected by the new behavior were updated: readiness reflects
  the migrated native fixture, and fixed-resource forms are read-only. Both also passed on
  SQLite. Regression tests independently demonstrate read-only actor/resource metadata.
- Targeted Identity policy/customization/session/impersonation suite: **22 passed**.
- Full Identity suite: **1,238 passed, 10 skipped, 2 failed**, 93.36% coverage. Both failures
  are existing Salesperson-role assertions: `product_configuration.read` is already in the
  role in `HEAD`, while the untouched tests expect 27 grants rather than 28. No Accounting
  grant or role definition changed. This broader suite is therefore not wholly green.
- Real RabbitMQ publisher/consumer regression: **3 passed**, including Accounting, Identity
  and Catalog issuers. It checks unroutable delivery remains pending, confirmed retry,
  reconnect/redelivery deduplication and invalid-message dead lettering in a test vhost.
- Isolated live nginx: syntax valid; public health checks, internal-route blocking, rejection
  of forged contexts, trusted header forwarding, original URI/query preservation, and
  401/403/503 JSON envelopes passed. No running gateway was restarted.
- Identity-to-Accounting bridge: real in-memory applications and signed context; policy/layout
  creation, detail/export/history protection, denied write rollback, policy deactivation and
  forged-signature rejection passed. This bridge and the live nginx harness test separate
  layers; they are not a claim of a deployed multi-service environment.
- API client: generated-file freshness, TypeScript checking and **3 transport tests passed**.
- Accounting and changed Identity files: Ruff lint/format clean. Strict mypy: **38 Accounting
  source files**, **127 Identity source files**, no issues. Both OpenAPI snapshots and the
  Accounting field contract are current. `git diff --check` passed.

## Final review and practical limits

Manual simplification and security/correctness reviews covered CLAUDE.md sections 5 and 6.
The named `/simplify` and `/security-review` commands were unavailable in this session;
equivalent source and regression reviews were performed, rather than claiming those tools ran.
Final review found and repaired additional initialization/template policy bypasses, incorrect
creation-before-state evaluation, missing tenant authority for policy administration, misleading
form writability, and duplicate/UTF-8 environment-rerun handling. No further blocking issue was
found in the repaired paths.

Tenant filtering, company object scope, Decimal storage, expected versions, idempotent replay,
transactional audit and preview rollback remain in place. Conditions with unavailable record
fields fail conservatively: conditional denies apply and conditional allows do not. This can
hide more data in lists/exports/history than a specific readable detail. Read-denying structural
identity rejects the resource; history does not retain per-revision value snapshots.

The 28-table service remains a master-data implementation. Planned Tally group/ledger additions,
individually typed export rows, full test-tree type annotations, journals, balances, financial
posting/closing, credit enforcement and Billing/Catalog consumers remain separate work. This
repair neither implements those features nor marks the older future-phase checklist complete.
Publication and live deployment were not performed.
