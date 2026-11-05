# Company and financial-year remediation evidence

Date: 2026-10-22. The sections below preserve evidence for the initial Accounting
repair. For the subsequent 2026-10-23 company directory, view/edit, calendar management,
validation, pagination, bootstrap, lifecycle and recovery UI fixes, see
[company management](company-management-review.md) and
[company/year management](company-year-management.md). The older pending status below
describes that initial stage. Distributed pre-commit prevention is still separate work.

## Agreed sequence and current status

1. Repair C01 with explicit Accounting recovery for unused books and focused regression checks. The backend command is implemented. Prevention of unsafe Identity edits before commit and the management UI remain pending.
2. Address the wizard, fiscal validation, company lifecycle and explicit selection findings C02–C05.
3. Address directory/fiscal pagination and metadata-driven creation C06–C08, then verify the combined workflow.

An automated content filter blocked the next Identity/Console patch batch. That action was not retried. Steps 2 and 3 remain pending. The review also confirmed C07's `sort=start_date` requests return HTTP 422 against the current fiscal list API.

## Implemented Accounting command

`POST /v1/companies/{company_id}/financial-setup/reconcile` accepts:

```json
{
  "expected_version": 1,
  "configuration_hash": "<current reviewed company configuration digest: 64 lowercase hex characters>",
  "reason": "Correct unused books"
}
```

Use a stable `Idempotency-Key` for retries. The caller obtains the existing setup version from the authorized setup read and reviews the current company facts. The supplied digest must match the gateway-verified current financial context. Book settings are taken from that signed context, never arbitrary request fields. The command returns the field-protected financial setup detail.

`accounting.finance.read` and company-scoped `accounting.finance.manage` are required. The narrow `accounting.finance.initialize` grant is insufficient. Changing the fiscal anchor additionally requires `period.manage` and readable fiscal resources/dates. Native field-write restrictions apply to setup, years and periods; a denied change rolls back the entire command. Idempotent replay rechecks finance authority and the original calendar-management authority.

The command serializes through the existing Accounting company setup lock. It rejects a missing setup, stale setup version, mismatched reviewed digest, first posting, financially used accounts, document sequences, any non-calendar financial resource, and periods beyond FUTURE/OPEN. Conservatively, even unposted financial records prevent automatic reinterpretation of books.

For an anchor correction, it regenerates the twelve monthly date ranges for every existing year while retaining year/period IDs and statuses. Incomplete calendars are refused. Updated rows receive new versions and actor metadata. This does not automatically open the period containing a revised books-begin date; that separately authorized workflow is still pending.

Accounting writes row revisions, safe change audit evidence, a reason-bearing `accounting.financial_setup.reconciled` event, and versioned period-change events in the same transaction. The publisher allowlist and generated audit contract include the new events. Publication follows commit through the existing outbox. The browser does not issue a separate Audit mutation. Existing Audit/history readers remain the read path.

The ordinary initialize/generation/posting configuration checks remain enforced. The new recovery command does not supply Identity pre-commit validation or a cross-service reservation lease. A later concurrent Identity edit can cause drift again; coordinated prevention still needs implementation and native concurrency evidence. Do not treat C01's entire cross-service workflow as complete.

## Verification

- New reconciliation suite: **11 passed**, **92%** statement/branch coverage of the new task module. Cases include successful repair and subsequent generation, stable calendar IDs/statuses, once-only outbox emission, financial blockers, version/hash conflicts, permission and field restrictions, tenant/company isolation, and rollback.
- Extended success/authority cases rerun: **2 passed**, including original `period.manage` revocation on replay, retained three-version period history, and HTTP 422 for malformed/extra request fields.
- Existing fiscal API/domain and audit evidence regressions: **24 passed, 1 skipped** in the combined run. That run initially had one new-test failure caused by the unsupported fiscal sort; the test now uses the supported API and sorts its assertion data locally. Subsequent new-suite and extended-case runs are green. The skip requires native database prerequisites.
- Audit contract/read suites: **23 passed**. No Audit service code change is needed for the new fully qualified Accounting actions.
- Ruff checks and formatting: passed. Strict mypy on the changed task/API/schema: passed.
- Accounting OpenAPI consistency, generated audit-contract equality, generated TypeScript consistency and API-client TypeScript compilation: passed.

Verification used local SQLite/ASGI. It does not establish MySQL locking behavior, broker delivery, deployed browser behavior or complete Identity-to-Accounting concurrency. Overall service coverage was not measured; the reported coverage applies only to the new command.

## Review and change boundaries

Manual review of CLAUDE.md security and money/audit invariants found no additional defect in the implemented command. It retains scoped authorization, verified company facts, session tenant filtering, field policy, transactional idempotency, rollback and outbox delivery. No network call occurs inside the database mutation. Calendar identities and historical revisions are retained; posted books cannot be changed.

The `/simplify` and `/security-review` tools were unavailable in this session; equivalent code review was performed manually. No models, migrations, shared-library versions or permission keys changed. Accounting OpenAPI and its generated client were updated. Existing unrelated working-tree changes were preserved. Nothing was committed or published.
