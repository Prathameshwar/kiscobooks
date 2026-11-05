# Identity API — bug-fix plan

**Date:** 2026-09-12
**Status:** Completed and reviewed on 2026-09-12. [Results and evidence](identity-bug-fix-results-2026-09-12.md).
**Scope:** Correct the 15 confirmed bugs in the [Identity review](identity-api-review-2026-09-12.md).
**Separate workstream:** [Implementation-gap completion](identity-gap-completion-plan.md).

## 1. Outcome and scope

Make the existing Identity API enforce authorization and ownership consistently,
produce complete audit-safe events, support normal access restoration, and meet the
documented list, validation and preference contracts.

The B01–B15 identifiers remain the finding ledger. The phases below group those
findings for delivery; they do not introduce additional confirmed bug counts.
New production authentication, deferred resource APIs, event delivery and other
missing capabilities belong to the separate gap plan.

The two concurrency concerns from the review are verification items in BF6. They
become additional bug findings only if reproduced or otherwise established; their
status and evidence must be reported separately.

## 2. Delivery order

| Phase | Findings | Deliverable | Dependency |
| --- | --- | --- | --- |
| BF0 | Preparation | Regression cases, contract decisions and affected-client inventory | Review evidence |
| BF1 | B01, B02, B03, B12 | Correct privilege, tenant, company, department and validity checks | BF0 |
| BF2 | B04 | Field-policy enforcement in existing reads, writes and queries | BF1 |
| BF3 | B05, B06, B07 | Complete, redacted and correctly scoped audit emission | BF1 |
| BF4 | B08, B09, B10 | Valid re-grants and consistent memberships | BF1, BF3 |
| BF5 | B11, B13, B14, B15 | Correct pagination, validation and readable preferences | BF2 |
| BF6 | All; concurrency concerns separately | Verified fixes, migration checks and review closure | BF1–BF5 |

Recommended execution is BF0 → BF1 → BF2 → BF3 → BF4 → BF5 → BF6.
Dependencies describe what can be implemented safely; they are not agent-delegation
instructions or elapsed-time estimates. Close the P1 findings before treating the
service as suitable for production use.

## 3. BF0 — Preserve evidence and define regressions

- Preserve the historical [28-observation harness](../.test_artifacts/identity-review-20260912/reproduce.py)
  and its results. It asserts undesired behavior and is not a release regression gate.
- Write focused regression tests that assert the intended behavior; confirm each
  fails for the reported reason before its fix. Use real ASGI requests and database
  fixtures for route/transaction claims, with pure tests for domain rules.
- Inventory callers and generated types affected by sparse field responses,
  list envelopes, new re-grant behavior and preference responses.
- Record the concrete contract choices below in the relevant API/schema documents
  as their implementation lands. Keep existing seven-service boundaries and MySQL.
- Establish a disposable MySQL 9.6 test target for constraint/migration/concurrency
  checks. Reuse gap-plan G08 infrastructure when available; no existing application
  database is a migration-test target.

**Exit:** every finding has a reproducible regression case and an identified owning
phase; prerequisites for database-dependent tests are recorded.

## 4. BF1 — Authorization and relationship isolation

- [x] **B01 — Group escalation.** Resolve the group's active and scheduled grants
  before membership changes. Apply the same self-modification, permission-content
  and scope restrictions used for assignments. Prevent a caller with only
  `group.manage` from adding themselves or others to a more privileged group.
  Serialize membership decisions against relevant assignment changes. Keep this
  guard reusable by the future removal/group-assignment workflows in G02.
- [x] **B02 — Ownership checks.** Validate user default company/department,
  department head, registration address and company assignment target on every
  create/update path. Require real objects in the current tenant; require the
  selected department/address to belong to its declared company. Apply existing
  lifecycle rules when selecting related records. Add feasible composite database
  constraints after identifying pre-existing invalid relationships; preserve
  evidence and do not silently delete or reassign historical records.
- [x] **B03 — Scope and time.** Require valid tenant-scope authority for edits to
  tenant role definitions, including metadata-only changes. Enforce grant dates
  in the endpoint permission union. Scope-filter assignment lists and authorize
  every revoke/replay branch before returning a record. Keep intentionally global
  reference/catalogue reads distinct from tenant-owned assignment data.
- [x] **B12 — Department authority.** Resolve the actual department and its ancestor
  path. Permit valid self/ancestor-department grants while rejecting siblings,
  unrelated companies and tenants. Apply scoped listing and explicit source/destination
  authority for reparenting; root department creation still needs company-level authority.

**Acceptance:** unrelated scope is denied without data leakage; invalid references
are rejected before persistence; expired/future grants grant nothing; a permitted
department manager can edit their department; privilege-escalation attempts leave
no membership, grant or misleading success audit record. Run affected shared-scope
and Catalog authorization tests when shared mechanisms change.

## 5. BF2 — Enforce field policies

- [x] **B04 — Write enforcement.** Load applicable user/group/role policies under
  the current tenant and object scope, resolve precedence through the existing
  shared mechanism, and check the actual changed-field set. Unchanged denied fields
  do not turn a legitimate no-op into a write failure; a real denied change fails
  atomically with the documented permission error.
- [x] **B04 — Read enforcement.** Apply resolved read policy before detail/list
  serialization. Use server-defined sparse response contracts so denied fields are
  absent, and update OpenAPI/client types accordingly. Reject search/filter/sort
  requests that would disclose read-denied values. Cover every existing Identity
  entity for which field policy is supported, with an explicit support inventory.

**Acceptance:** seeded policies are enforced without requiring new administration
APIs; deny/allow precedence, scope, groups, no-op writes and indirect query exposure
are tested. Field layout remains separate from authorization. The administrative
CRUD and merged field-set capabilities remain G04.

## 6. BF3 — Repair audit emission

- [x] **B05 — Missing events.** Add transactional audit events for department
  updates, group creation, membership creation and identity linking. Audit sensitive
  tax-registration reads as access events. Review all existing mutation routes for
  an equivalent omission and report any new findings explicitly.
- [x] **B06 — Personal data.** Replace unrestricted old/new-value capture with an
  allowlist of audit-safe fields. Record reference IDs and field names/redacted
  markers for personal fields. Cover tenant contact details as well as user data.
  Provide a read-only inventory of affected existing outbox/audit data and a
  remediation proposal; do not rewrite an immutable audit chain as a routine fix.
- [x] **B07 — Audit scope.** Populate authoritative `company_id` for company-owned
  actions, plus department scope where the event contract supports it. Verify that
  the Audit consumer and company-filtered queries preserve the scope.

**Acceptance:** successful required actions stage one meaningful audit event in
their transaction; rollback leaves none; events contain no forbidden personal
values; company readers can retrieve correctly ingested scoped events. Separate
Catalog source events remain intact. Outbox-to-broker deployment is owned by G07.

## 7. BF4 — Access restoration and membership consistency

- [x] **B08 — Re-grant.** Add an explicit
  `POST /v1/role-assignments/{assignment_id}/regrant` command for the retained inactive
  assignment. Its proposed body contains validity dates and a reason; subject,
  role and scope stay fixed. Re-run the full authorization guards, preserve the
  assignment identity and historical grant/revoke evidence, and audit restoration.
  Define replay behavior using the shared command/idempotency mechanism. Existing
  active duplicate grants remain conflicts.
- [x] **B09 — Validity.** Validate ordered validity windows after applying defaults
  on both creation and re-grant. Preserve the documented inclusive/exclusive date
  semantics consistently with the permission resolver.
- [x] **B10 — Memberships.** Enforce uniqueness for company-level affiliations with
  null department and maintain at most one active primary affiliation per user.
  For the existing create API, reject a conflicting primary request; the explicit
  primary-switch action belongs to G02. Serialize changes per user and add a
  migration-backed uniqueness mechanism where appropriate. Inventory existing
  duplicates before applying constraints; do not select a surviving primary silently.

**Acceptance:** grant → revoke → authorized re-grant succeeds and is auditable;
unauthorized and self re-grants fail; reversed dates return validation errors;
concurrent duplicate/primary membership requests cannot both succeed. Prove
constraint behavior and migration roundtrip on disposable MySQL.

## 8. BF5 — Lists, validation and preference responses

- [x] **B11 — Cursors.** Bind normalized sort, filters/search, tenant, object scope
  and current authority to the existing signed cursor mechanism. Validate decoded
  value types and sort shape. Return 422 for mismatched/expired/tampered cursors;
  retain deterministic pagination when sort values tie.
- [x] **B13 — Lists.** Introduce bounded keyset pagination for every growing group,
  member, affiliation and statutory-child list. Use explicit lean projections in
  all lists. Default to 50 and cap at 200 unless the owning contract sets a lower
  cap. Update current consumers and generated clients together when replacing arrays
  with page envelopes. Document genuinely bounded reference lists separately.
- [x] **B14 — Validation.** Forbid unknown query parameters, validate filter values,
  reject null for required-but-omittable PATCH fields and normalize request-validation
  errors through the shared envelope. Distinguish invalid input from uniqueness
  conflicts. Apply the fix across schemas with the same defect.
- [x] **B15 — Preferences.** Include stored display and navigation preferences in
  authorized user-detail responses. Provide the documented resolved company/user
  display configuration without permitting overrides of company money precision or
  other native business invariants. Update UI/client consumers that use those values.

**Acceptance:** changed cursor context yields 422 rather than 500 or silently wrong
pages; lists obey limits and scope; unknown query fields fail; required nulls yield
validation errors; clients can save, reload and use preferences. Denied fields remain
absent across all revised responses.

## 9. BF6 — Verify and close findings

- Reproduce the feature enable/disable and department reparent interleavings on
  MySQL. If confirmed, append separately identified findings, write failing tests
  and fix them before claiming the affected invariant is safe. The expected
  approach is to serialize policy reads and writes under a suitable company/user
  lock, with a documented lock order and revalidation; evidence decides the final fix.
- Run all Identity tests, affected shared-library and consumer tests, Ruff and strict
  mypy. Maintain the configured 90% gates and do not reduce the measured baseline
  coverage through a change in measurement.
- Verify model/migration parity, one DDL statement per revision, upgrade/downgrade
  on disposable MySQL, and fresh OpenAPI/generated TypeScript contracts.
- Run consumer/UI tests for changed contracts. Review scope enforcement, personal-data
  handling, transactions, replay and lock ordering after the last phase.
- Record per-finding regression names, results and any limitations in the review
  ledger. Replace stale progress statements with verified evidence as work lands.

**Completion:** B01–B15 have corrected-behavior regressions and passed relevant
checks. Pending production-database checks remain explicitly pending. Completing
this plan does not claim that the separate gap plan or the entire service is complete.

## 10. Links to the gap plan

| Bug deliverable | Gap work that consumes it |
| --- | --- |
| BF1 scope and membership guards | G01 authentication grants, G02 lifecycle, G05 impersonation |
| BF2 field-policy enforcement | G04 policy/config/custom-field administration |
| BF3 audit contracts | G07 audit publisher; all new G01–G06 workflows |
| BF4 grant/membership transitions | G02 end/switch/deactivation actions |
| BF5 response/query contracts | All new management/list APIs and real client integration |
| BF6 local and database evidence | G08 production-equivalent release verification |

## Decision log

- 2026-09-12: Created a separate proposed remediation plan for B01–B15 at the user's
  request. Kept capability additions under G01–G08 in the companion plan. Recorded
  concurrency concerns as verification work without inflating confirmed findings.

- 2026-09-12: User authorized uninterrupted implementation. BF0?BF6 completed;
  B01?B15 closed, with C01/C02 separately confirmed and fixed. Final verification:
  1,073 application tests + 8 MySQL tests passed; 93.97% package coverage. Consumer,
  static and generated-contract checks passed. Production rollout and the separate
  gap-completion workstream were not performed.
