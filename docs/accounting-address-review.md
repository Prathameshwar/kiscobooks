# Debtor and creditor address review

User requested an in-depth review and fixes on 2026-09-14. Scope remains Accounting
address masters and their existing workflows; UI, opening balances and Billing
consumers are separate work.

## Execution todo

- [x] Review schemas, ownership, lifecycle, registration links, defaults and access paths.
- [x] Reproduce defects and exercise adversarial address scenarios.
- [x] Fix confirmed defects and synchronize API/client contracts.
- [x] Verify native MySQL, coverage, typing and generated artifacts.
- [x] Review the final changes for security and simplicity; record results.

## Finding and fix

- Registration-address list rows omitted `registration_id`, requiring an extra detail
  request per row to identify a party's registration associations. A paginated,
  two-registration API regression failed before the change. The lean list now includes
  this existing field, with the same sparse field-policy behavior as detail/export.
- Accounting OpenAPI, the resource matrix and the generated TypeScript client are updated.
  A typed consumer example reads both address and registration IDs. No database migration,
  new permission or event payload was needed.

## Review coverage and verification

The final source review covered CLAUDE.md security and correctness invariants applicable
to master data: tenant/company scope, parent ownership and eligibility, current field
policy on writes and replay, default uniqueness, dated registration associations, bounded
reads, idempotency and transaction-local audit. `/simplify` and `/security-review` are not
available tools in this session; their checks were performed manually.

- The affected address/integrity run passed 19 tests; the new concurrency case was skipped
  on SQLite and subsequently passed in the native MySQL run.
- All five API scenarios in the expanded address review file passed on SQLite. They
  cover paginated association identity and protected filtering,
  atomic import default switching and replay without duplicate revisions or private audit
  content, default-scope conflicts, inactive/cross-party references, conditional field-policy
  escape attempts, protected exports/replay and actual foreign-company/tenant objects.
- Ruff lint/format and strict mypy passed for 73 source/test/tool files. Accounting generated
  contracts are fresh. TypeScript compilation and the Accounting transport test passed.
- The full native MySQL 9.6.0 suite passed **135 tests in 688.06 seconds**, including all
  six new address-review cases with no skips. Concurrent default activation produced one
  successful activation and one conflict, leaving exactly one active default.
- Overall coverage increased from **95.54% to 95.68%**; domain modules remain **99–100%**.
  All 72 migrations, model parity, representative query plans, concurrent idempotency and
  downgrade-to-base/upgrade round trip passed. Only the harness's own disposable loopback
  schema was used and removed; no application database was changed.

Local evidence: `.test_artifacts/accounting-completion/address-review-native.txt` and
`.test_artifacts/accounting-completion/address-review-coverage.json`.

No additional defect was identified in the existing default and lifecycle rules exercised
by this review. Default scope is enforced for active edits as well as activation; imports use the
same command path, and failed preview/default changes leave versions and revision history
unchanged.

Address requirements remain unchanged: an address is optional for account activation;
default scope is party + purpose + optional registration, shared by customer and supplier
roles. Consumer selection and immutable invoice snapshots remain deferred.

The address review and its fixes are complete. Publication and deployment were not part
of this review.
