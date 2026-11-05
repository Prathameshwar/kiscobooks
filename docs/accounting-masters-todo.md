# Accounting masters execution todo

User authorization: implement all six phases uninterrupted, then review twice and fix the
findings from each review. Approved 2026-09-14. Scope and criteria:
[completion plan](accounting-masters-completion-plan.md).

## Phase 1 — Contract

- [x] Record the resource matrix, field defaults, compatibility and upgrade rules.
- [x] Fix the migration/backfill/readiness strategy before changing models.

## Phase 2 — Groups, aliases and existing installations

- [x] Group metadata, protected inheritance, 28-group base template.
- [x] Company-scoped group aliases across API, workflows, policies and audit.
- [x] Schema migrations and safe, repeatable metadata backfill.
- [x] Template preview and atomic versioned upgrades preserving old IDs/receipts/history.
- [x] Fresh/legacy/used/conflicting template and hierarchy tests; native migration parity.

## Phase 3 — Accounts and profiles

- [x] Inventory, rounding and ordering metadata with Decimal/currency validation.
- [x] Duty classification with valid profile creation/activation and legacy compatibility.
- [x] Account kind/head matrix, protected active/used semantics and template defaults.
- [x] Schema, contracts and domain/API regression tests.

## Phase 4 — Party completeness

- [x] Explicit address/registration/state/date consistency and indexed retrieval.
- [x] General/registration-scoped defaults and safe replacement lifecycle.
- [x] Comprehensive roles, contacts, registrations, beneficiaries, memberships and policy scenarios.

## Phase 5 — Contracts and workflows

- [x] Typed per-resource exports at compatible URLs; protected omission and pagination.
- [x] Metadata/filter/sort/index and import/history support for all additions.
- [x] Create Location headers and consistent errors.
- [x] Fresh Identity field contract, OpenAPI and TypeScript client plus consumer checks.

## Phase 6 — Verification and delivery preparation

- [x] Full MySQL suite and existing 0037 database upgrade/retry fixture.
- [x] Strict typing for Accounting source, tests and tools; lint/format.
- [x] Coverage >= 94.92%, domain >= 90%, affected Identity/client/Audit integration checks.
- [x] Reusable gateway/Identity/publisher verification and runtime instructions.
- [x] Documentation, actual migration/table counts and release/rollback notes.

## Final reviews

- [x] Review 1: simplification, API completeness and master invariants; record findings.
- [x] Fix review 1 findings and run affected checks.
- [x] Review 2: tenant/company authorization, field policies, upgrades, audit and concurrency.
- [x] Fix review 2 findings and run final verification.

Publication is not part of this local implementation until explicitly requested. Preserve
concurrent Catalog/UI work and the configured folder-mapped publishing workflow.

## Additional final review requested after completion

- [x] Review account/profile dependencies, workflow authorization and retained master invariants.
- [x] Reproduce findings, repair them and run affected regressions.
- [x] Complete native verification, coverage and documentation for the final fixes.

## Evidence and findings

Further debtor/creditor address review is tracked in
[the completed address review checklist](accounting-address-review.md). Its association-list
fix and six new regression cases passed the full native suite: **135 tests**, **95.68%
coverage**, all 72 migrations and the downgrade/upgrade round trip. Client contracts,
strict typing and lint/format checks are clean. No address-review item remains pending.

Starting baseline: 81 native Accounting tests, 94.92% coverage, migration head 0037, 28 business
tables, 25 base groups, template v2. Prior repairs remain in the working tree. Existing unrelated
Identity Salesperson-role expectation failures are recorded in the September 14 review.

Progress: migrations 0038–0072 reviewed and tested through native parity and down/up checks.
The 0037 fixture passed with v1/v2 installations, renamed/custom groups, existing credit policy
and history, rollback/retry of failed backfill, safe upgrade/replay and atomic used-account
conflicts. Affected party/integrity suite: 20 passed. New account/backfill suite: 6 passed.
Export/Location/Decimal/alias workflow contracts and all 29 typed export routes pass. Both
manual reviews and their fixes are recorded in [the completion review](accounting-masters-completion-review.md).
Review 1 extended suite: 20 passed. Review 2 security/audit suite: 26 passed. Strict mypy covers
71 source/test/tool files. Identity policy/layout cases: 10 passed; generated client compiles,
with 3 transport tests; gateway and Identity bridge passed; live RabbitMQ: 3 passed.
Final frozen-source MySQL 9.6.0 run: **122 passed in 493.11 seconds**, **95.38% coverage**;
domain modules **99–100%**. All 72 migrations, model parity, query-plan review, concurrent
idempotency and downgrade-to-base/upgrade passed. Both Accounting and Identity OpenAPI/client
snapshots are fresh, including the group-alias policy enum. All agreed master work is complete.
The separate Identity Salesperson rerun confirmed the same 2 unrelated expectation failures
(18 passed); details are in the completion review. Publication and live deployment remain separate.

Additional final review: three issues were reproduced and fixed, with seven new regression,
domain and import cases. The full native MySQL run passed **129 tests in 700.30 seconds** with
**95.54% overall coverage**, up from 95.38%; domain coverage remains **99–100%**. All 72
migrations, model parity, query plans, concurrent idempotency and the downgrade/upgrade round
trip passed again. Strict mypy now covers 72 files; lint, formatting and generated contracts
are clean. The final review and its fixes are complete.
