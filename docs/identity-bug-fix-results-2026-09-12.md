# Identity API bug-fix implementation and final review

**Date:** 2026-09-12. **Status:** Completed and reviewed. B01?B15 and confirmed C01/C02 are closed.

The authorized work covers B01?B15 from the original review. The separate
[gap-completion plan](identity-gap-completion-plan.md) remains a separate workstream.
No production database or deployment was changed.

## Finding ledger

| Finding | Corrected behavior | Main regression evidence |
| --- | --- | --- |
| B01 | Privileged group joins require assignment authority; self-joins cannot grant access. Groups carrying field-policy allow rules additionally require tenant `field_policy.manage`. Scheduled grants and current database membership are checked. | `test_b01_privileged_group_requires_assignment_authority`, `test_group_field_allow_requires_policy_authority`, `test_group_regrant_uses_current_database_membership` |
| B02 | User defaults, department heads, statutory addresses and assignment targets are validated against tenant/company ownership and applicable lifecycle rules. Composite ownership constraints back the fixed relationships. | `test_b02_*`, `test_default_affiliations_merge_and_clear_consistently`, `test_tax_registration_amendment_rechecks_address_ownership`, MySQL ownership tests |
| B03 | Tenant role edits need tenant authority; expired/future grants grant nothing. Assignment lists are scope-filtered and every revoke/replay branch is authorized. | `test_b03_*`, `test_assignment_lists_respect_department_and_company_scope`, `test_revoked_assignment_does_not_bypass_scope_on_repeat` |
| B04 | Registered company field policies enforce write diffs, sparse reads, query restrictions, subject/scope precedence, active group membership and bounded conditions. | `test_b04_*`, policy subject/condition/scope regressions |
| B05 | Department updates, group creation, affiliations, identity links and tax-registration access stage transactional audits. | `test_b05_required_actions_emit_audit` |
| B06 | Audit changes use an explicit safe-field allowlist; other values are redacted while retaining field names. User and tenant personal values are excluded. | `test_b06_audit_does_not_capture_personal_values`, `test_tenant_contacts_are_redacted_and_request_errors_hide_input` |
| B07 | Company-owned events contain authoritative company scope; department events also carry department scope. Audit ingestion and company-filtered retrieval preserve scope. | `test_b07_company_audit_has_company_scope`, Audit `test_identity_event_is_visible_to_its_company_reader` |
| B08 | Inactive assignments can be explicitly restored with full authorization and idempotent replay, preserving row identity and audit history. | `test_b08_regrant_and_replay_preserve_identity`, replay/self/group regressions |
| B09 | Effective dates are ordered after defaults and use inclusive endpoints. Replays across midnight preserve the original command semantics. | `test_b09_assignment_rejects_reversed_dates`, `test_default_assignment_dates_and_cross_midnight_replay` |
| B10 | Duplicate company affiliations and competing active primary affiliations conflict, including concurrent requests and direct database writes. | `test_b10_*`, MySQL concurrency/constraint tests |
| B11 | Cursors bind normalized filters/sort, tenant, actor, scope and authority; company cursors also bind applicable field-policy state. Invalid shapes or context changes return 422. | `test_b11_*`, normalization/authority/policy changes and identity cursor tests |
| B12 | Department authority includes self and ancestors, excludes siblings, and checks both source and destination for reparenting. | `test_b12_*`, ancestor/sibling/list regressions |
| B13 | Growing child/group/member/identity lists use bounded keyset pages and explicit ORM projections. | `test_b13_*`, child envelope and identity pagination tests |
| B14 | Unknown/duplicate query keys, invalid enum filters and explicit nulls for required PATCH fields return the shared 422 envelope. OpenAPI reflects omittable but non-null fields and the actual shared error envelope. | `test_b14_*`, required-null and query validation matrices |
| B15 | User details return saved display/navigation preferences. Resolved display configuration merges presentation preferences while preserving company financial settings. | `test_b15_*`, resolved display regression |

Regression source: [Identity review regressions](../apis/identity/tests/test_review_regressions.py).
Database source: [MySQL review tests](../apis/identity/tests/test_review_mysql.py).
The original 28-observation reproduction and original review evidence are preserved.

## Additional concurrency evidence

The original two concerns are now separately confirmed as **C01** (feature dependency
race) and **C02** (reciprocal department reparent race). A deterministic replay of the
pre-fix read-before-lock transaction ordering on disposable MySQL 9.6 produced both
invalid states. This is a transaction-order replay, not a claim that an old deployed
endpoint was exercised. [Evidence](../.test_artifacts/identity-fixes-20260912/pre-fix-concurrency-results.json).

Mutating Identity requests now lock the tenant before authorization/domain reads.
Lock order is tenant, then any company/user rows, then the Catalog source generation
and native writes. This deliberately serializes administrative writes within a tenant;
throughput should be measured before narrowing the lock. Snapshot readers use the
Catalog generation lock and do not acquire the tenant lock in reverse order.

The fixed public routes reject one reciprocal reparent, keep feature prerequisites
consistent under competing requests, and allow only one duplicate/primary membership.
The final review also reproduced and fixed the field-policy group-join variant of B01,
and excluded inactive groups from policy resolution so their allow rules cannot
override a direct user denial.

## Contract and caller changes

- Growing arrays now return `{items, page: {next_cursor, has_more}}`: user groups,
  group members, memberships, user identities, tax registrations, statutory IDs,
  licences and addresses. These lists order by stable ID, default to 50, and cap at 200.
  Companies, users, roles, departments and assignments retain their existing allowed
  sorts and now select only response/sort/condition columns.
- Global ISO choices, company classifications, permission keys and feature catalogues
  are bounded reference data and retain their existing response shapes.
- Field-policy support is explicitly `identity.company`: registered native company
  fields plus `business_roles`. Detail, create/update/visibility responses, lists and
  display configuration all omit read-denied fields. Unsupported stored policy keys
  fail closed. Other entity registration and policy/configuration CRUD remain G04.
- Write policies evaluate actual changes against both old and proposed condition
  values. Conditions use the bounded shared evaluator. Queries cannot rely on a
  conditional allow to reveal rows that may contain denied values.
- `POST /v1/role-assignments/{id}/regrant` requires `Idempotency-Key` and a nonempty
  `reason`; `valid_from` and `valid_to` are optional. Role, subject and scope stay fixed.
  Active assignments conflict (409); a changed request under the same key is the
  shared idempotency conflict (422). Receipts retain references for 24 hours and
  render current state only after fresh authorization. Replay never reactivates an
  assignment revoked after the original command.
- Required PATCH fields may be omitted but cannot be explicitly null. Truly nullable
  fields still clear with null. Validation errors expose field paths/types, not input values.
- User details add `date_format`, `datetime_format`, `digit_grouping`,
  `currency_display`, `theme` and `landing_page`. Display configuration resolves
  locale/timezone/date formats/grouping/currency display from the current user;
  amount/quantity precision, rounding and other native business settings stay company-owned.
- `billing-platform` is version 0.13.0; every existing service lockfile is updated.
  OpenAPI and `clients/api-client/src/identity.d.ts` are regenerated. The console has
  no live callers of the changed child-list endpoints; its tests and type check were run.

## Database rollout and historical data

Revisions **0043?0050** add generated uniqueness keys and composite ownership keys/FKs.
Each revision has one atomic DDL statement in each direction. The generated membership
keys normalize a null department and enforce at most one active primary per user;
historical inactive affiliations remain distinct from access grants.

Run [the read-only inventory](../apis/identity/tools/inventory_identity_integrity.py)
with `IDENTITY_DATABASE_URL` before upgrading a populated deployment. It reports
record IDs and audit field names, never personal values. Resolve reported ownership or
duplicate/primary issues through a reviewed data-remediation decision, preserving the
historical evidence. Migrations do not silently choose survivors or delete data.
A MySQL regression proves duplicate data blocks 0043 atomically and remains intact.

Existing personal values in older audit/outbox records need a separate retention and
incident-handling decision. Restrict access, inventory affected IDs, and apply approved
retention or archive controls. Do not rewrite signed/hash-chained Audit rows as a
routine repair. This implementation prevents new value capture; it does not claim to
have inspected or removed production historical data.

MySQL migration comparison emits existing circular-FK ordering and generated-expression
reflection warnings. An additional direct information-schema inspection verifies all
owner FKs/check names, and physical insert tests prove both generated uniqueness rules.
No model migration differences are returned.

## Verification

The final source passed all required checks. No blocking findings remain within this
bug-fix scope. The separate gap plan remains open.

| Check | Result |
| --- | --- |
| Identity application/schema suite | 1,073 passed; includes 94 focused review regressions |
| MySQL 9.6 migrations, owner constraints, invalid-data preservation, concurrency | 8 passed |
| Identity total | 1,081 passed |
| Package coverage, same source/branch measurement and unchanged gate | 93.97%; gate 90% (original review 91.76%) |
| Shared platform suite | 744 passed; 86 affected checks and 8 scope/audit checks also passed |
| Audit suite and Identity ingestion contract | 91 passed |
| Affected Catalog authorization/field/scope tests | 30 passed |
| Console | 43 tests passed; TypeScript check passed |
| API client | 2 tests passed; TypeScript and generated-file freshness passed |
| Identity static checks | Ruff passed for source/tests/tools; strict mypy passed for 83 files |
| Shared changed modules | Ruff and strict mypy passed |
| Contracts | OpenAPI export/freshness and generated Identity TypeScript passed; 57 operations |

[Machine-readable summary](../.test_artifacts/identity-fixes-20260912/verification-summary.json),
[Identity results](../.test_artifacts/identity-fixes-20260912/identity-suite-final.xml),
[MySQL results](../.test_artifacts/identity-fixes-20260912/mysql-suite-final.xml), and
[coverage](../.test_artifacts/identity-fixes-20260912/coverage-final.json) are retained.
The read-only integrity inventory was also exercised on the disposable schema.

The final manual review covers authorization, field-policy/query leakage, audit values,
ownership, lock order, idempotent restoration, schema/client parity and existing callers.
Production Authentik/gateway integration, live broker delivery and the other G01?G08
capabilities are outside this authorized bug-fix workstream.


### Repeating verification

From `apis/identity`, use `.venv\Scripts\python.exe -m pytest -m "not mysql" --cov=identity`
for the application suite. Set `IDENTITY_TEST_MYSQL_URL` to an **empty disposable MySQL
9.6 schema** and run `.venv\Scripts\python.exe -m pytest -m mysql` for database checks;
these tests upgrade and downgrade that schema. The temporary MySQL process used for
this review has been stopped and its data directory removed. Logs and result artifacts
are retained. The production database was never a migration-test target.
