# Notification review fixes — execution TODO

Started 2026-10-15. Scope authorized: fix the notification review findings one by one,
maintain this list, and review again after implementation. This is a new review cycle;
NR0–NR5 in the earlier remediation plan are historical, not evidence that these findings
are fixed. Baseline: 77 tests pass; domain coverage 93%; Ruff/mypy pass; no MySQL tests.

Status: `[ ]` pending, `[~]` working, `[x]` verified, `[!]` external prerequisite.
Every fix needs a failing regression first, implementation, affected tests, and evidence.
Do not mark an implementation verified based only on lint or a manually changed DB row.
Live provider/channel activation is separate from local implementation verification.

## Ordered phases

The user's one-at-a-time instruction governs this sequence. Finish and verify each item
before starting the next; update this file with failures, commands, outcomes and review
findings. No architecture/datastore changes or publishing are part of this task.

### A — callback trust and tenant integrity

- [x] B01: ignore unsigned callback metadata overrides; replay retains one effect.
- [x] B02: activation version must belong to the tenant and exact target variant.
- [x] B03: event dedupe must preserve successive statuses for a single message.
- [x] B12: normalize every constituent status in a WhatsApp batch.
- [x] B13: serialize inbox/delivery normalization and recover scheduler failures.

### B — retry and transport correctness

- [x] B04: monotonic historical attempts, repeatable manual retries, locked transition.
- [x] B05: retention preserves provider-accepted/delivered outcomes.
- [x] B06: reevaluate applicable policy before scheduled sends and retries.
- [x] B10: persistent invalid preflight rows leave the due batch.
- [x] B11: validate provider PATCH nulls, lifecycle and complete verifier configuration.
- [x] G10: validate backoff bounds and honor route timeouts.

### C — audit and deployable ingress

- [~] B07: transactional actor-attributed audit and consistent status events.
- [ ] B08: Identity gateway authentication for management/company evidence.
- [ ] B09: native provider signatures, public Twilio URL and SNS verification/confirmation.
- [ ] G06: bounded callback streaming/rate limits and provider-supported replay checks.
- [ ] G03: authenticated notification outbox publisher and runtime wiring.
- [ ] G01: supported sender verification/update/deactivation.

### D — retention, diagnostics and delivery gaps

- [ ] G02: scrub original request variables and attachment metadata; apply retention settings.
- [ ] G04: scoped request/delivery detail, attempt/timeline evidence and reconciliation.
- [ ] G05: private attachment transport or explicit rejection until supported; scanner authority.
- [ ] G07: project endpoint health and suppression from permanent provider evidence.
- [ ] G08: lean list queries, bounded endpoint history, context-bound cursor validation.
- [ ] G09: channel payload in version identity; template/variable schema validation.
- [ ] G11: assess Identity alerts/licence scanner and Accounting communications contracts;
  implement within existing owners when contracts are defined; record any required decisions.

### E — verification and second review

- [ ] Add collected MySQL migration/isolation/concurrency tests; execute on available MySQL.
- [ ] Regenerate notification OpenAPI/types and verify consumers after route/schema changes.
- [ ] Run affected suites, Ruff, strict mypy and coverage (domain floor >=90%).
- [ ] Review every finding against final code, including auth, tenant scope, outbox/audit,
  replay, races, retention and ambiguous provider results; fix discoveries and rerun checks.
- [ ] Simplification and security review required by CLAUDE.md; record availability of
  slash-command tooling and perform equivalent explicit code passes if unavailable.
- [ ] Update notification design/decision log, operations and implementation checklist;
  preserve honest external activation prerequisites.

## Verification ledger

- User requested approval-prompt repair before further notification fixes. Saved project
  `.codex/config.toml`: approval_policy=never, approvals_reviewer=auto_review,
  sandbox_mode=danger-full-access. Read-only child diagnostic mirrored the real user's
  existing trusted-project entry and verified loaded approval Never, unrestricted
  filesystem and enabled network. Active session permissions do not hot-reload.
  `.test_artifacts/codex-approval-fix/resume-no-prompts.cmd` resumes the same thread
  with explicit no-prompt/full-access startup flags. Notification work resumed on request.

- Baseline review: local SQLite reproductions confirmed B01–B06, B07 and B09.
- B01: two regressions failed (OTHER-ID override; replay inserted two rows); after fix,
  `pytest -q tests/test_callbacks.py`: 9 passed. Only verified-body metadata is accepted.
- B02: both wrong-variant and cross-tenant regressions failed with 201; after scoped
  version/membership validation, `pytest -q tests/test_review_fixes.py tests/test_management.py`:
  8 passed. Activation overlap behavior is preserved.
- B03: successive SMS status regression failed with one row; body hashes now identify
  receipts. `pytest -q tests/test_callbacks.py tests/test_remediation_regressions.py`: 18 passed.
- B12: two-message callback failed with the second delivery still accepted. After full
  batch extraction, callback/normalizer/remediation suites: 23 passed. Constituent keys
  include provider identity; unmatched constituents remain reconcilable.
- B13: malformed ciphertext and failed scheduler pass regressions failed first. Inbox
  claims use SKIP LOCKED, delivery transitions lock/refetch, per-event savepoints quarantine
  malformed input, scheduler rolls back and retries. Normalizer/maintenance: 14 passed.
  Actual MySQL concurrency remains in phase E; SQLite does not exercise row locks.
- B04: retry regression failed with attempt count 0 after attempt 1. Repeat retry and
  historical attempts pass (three cycles); lifetime numbers persist, bounded retry-cycle
  budgets derive from immutable manual-retry evidence. Review/remediation: 11 passed.
- B05: sending/accepted/delivered were incorrectly expired; only unsent queue statuses
  now expire. All maintenance tests: 12 passed.
- B06: transactional preference withdrawal incorrectly sent; final preparation now
  reevaluates shared category gates. Security bypass remains per policy. Affected: 18 passed.
- B10: missing destination/body, unverified sender and missing encryption key all raised
  repeated conflicts. They now fail before transport with evidence/outbox: 17 affected pass.
- B11: five bad PATCH cases returned 409/200; now validated as 422. Provider suites: 16 pass.
- G10: inverted backoff accepted and slow provider accepted beyond route timeout; both
  regressions pass after validation/bounded call, timeout retained for reconciliation.
  Review/remediation/management: 30 passed. Full suite checkpoint: 103 passed; mypy clean.
