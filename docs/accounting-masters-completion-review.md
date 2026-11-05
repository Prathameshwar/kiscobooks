# Accounting master completion reviews

Scope: the approved six-phase [plan](accounting-masters-completion-plan.md). This supplements
the earlier [17-finding repair report](accounting-review-20260914.md); that report's future
master additions are implemented here. This report covers local changes, not publication or
deployment. The [todo](accounting-masters-todo.md) tracks the final verification result.

## Review 1 — completeness, invariants and simplification

Reviewed the 29-resource matrix, schema/default/lifecycle paths, templates, aliases, party
associations, typed exports, migrations, backfill and error behavior. Five regressions failed
before repairs, for these findings:

| Finding | Fix and verification |
|---|---|
| Preview reported six new tax accounts even when install reused compatible v1 identities. | One shared resolver now drives preview and install. The used-v1 collision/reuse regression preserves original IDs, profiles and bindings. |
| Existing system-key accounts were bound without checking their kind, group, active status or tax profile. | Compatibility is checked before reuse; mismatches conflict atomically. Cases cover missing/wrong registration, scheme, component, duty and purpose. |
| Preview missed account-code collisions owned by another master. | Preview reports the conflict and does not promise creation; install returns conflict with no new installation. |

Simplification removed a duplicate group-subtree guard and replaced repeated backfill path
scans with one depth-map pass. Existing hierarchy/integrity tests remain green. The extended
review suite passed 20 tests. An additional affected suite passed 29 cases; its one new test
initially expected validation failure instead of the documented cycle conflict. That assertion
was corrected and the backfill rollback/retry test passed in the extended suite.

## Review 2 — authorization, upgrades, audit and concurrency

Walked CLAUDE.md sections 5 and 6: session tenant isolation, company object scope, field policy,
idempotent authorization on replay, optimistic versions, Decimal/currency protection, sensitive
data omission, effective dates, company mutation locks, transactional audit/outbox and upgrade
rollback. Four regression scenarios failed before these fixes:

| Finding | Fix and verification |
|---|---|
| Aggregate template responses could infer read-denied classification, including from saved replays. | Preview/install/replay require readable classification fields; conditional denies are conservative. Tests cover group ancestry, account kind/use, head nature and installation version. |
| History silently accepted filters it did not apply. | Dedicated history query accepts only limit, cursor and ID sort. Master filters and search return 422; OpenAPI/client updated. |
| Implicit template installation and binding writes bypassed their field policies. | Field checks run before evidence creation, and denied writes roll back installation, groups and audit effects. |
| Setup currency synchronization and template-version changes lacked field checks and business audit revisions. | A shared setup updater checks before/after state, advances row version and emits the registered setup update event in the same transaction. Used-account currency changes remain blocked. |

The security/audit and affected authorization suite passed 26 tests. The 0037 native fixture
passed after these changes, including failed backfill rollback/retry and used-hierarchy atomic
conflicts. Native concurrency verification serializes duplicate commands through existing
company locks and idempotency receipts; no alternate mutation path was added.

The named `/simplify` and `/security-review` tools were unavailable in this session. Both
reviews were performed manually with source inspection and failing-then-passing regressions;
this report does not claim those tools ran. No remaining blocker was found in the reviewed
master functionality. Final native full-suite/coverage verification passed the release gate.

## Verification and practical limits

The historical completion evidence below is supplemented by the additional final review
requested after completion. Its current verification status appears at the end of this report.

- Fresh migration parity, query-plan checks and full downgrade/upgrade on MySQL 9.6.0 use a
  disposable loopback schema. Legacy verification starts at 0037 and preserves existing IDs,
  custom names, policy/history and v1/v2 installation evidence through 0072 and metadata v1.
- Strict mypy covers Accounting source, tests and tools (71 files); Ruff lint/format are clean.
- Identity field-policy administration: 10 passed, including new group aliases, group
  metadata, rounding and tax duty. The real Identity/Accounting signed-context bridge passed.
- Generated TypeScript client compiles all 29 export examples and rejected-input examples;
  all 3 transport tests passed. Generated contracts are checked for freshness.
- Isolated nginx authentication/forwarding/internal-route checks passed. Real RabbitMQ
  publisher/consumer cases: 3 passed, including Accounting's expanded event contract.
- Initial complete SQLite run before review fixes: 105 passed, 94.05% overall coverage with branches enabled.
  Missing export-route/upgrade/currency coverage was added.
- Final full native MySQL 9.6.0 run: **122 passed in 493.11 seconds**, **95.38% overall
  coverage** with branches enabled, and domain modules **99–100%**. All 72 migrations passed parity and the
  downgrade-to-base/upgrade round trip; representative query plans and concurrent idempotency passed.
- Final generated-file checks found and corrected a stale Identity group-alias policy enum.
  Identity OpenAPI and its client were regenerated; explicit policy request/result compile
  examples now cover the alias entity. Both service contracts and client snapshots are fresh.

The broader Identity suite's two existing Salesperson-role expectation failures were recorded
in the earlier repair report (1,238 passed, 10 skipped, 2 failed). This completion rechecked
affected Identity tests and did not alter those unrelated roles or claim the entire repository
is green. A fresh rerun of `tests/test_salesperson_role.py` confirmed 18 passed and the same
2 failures: the unchanged role contains `product_configuration.read`, while the unchanged
tests expect the older 27-permission set. Existing unrelated Catalog/UI edits remain preserved.

Transaction posting, balances, closing, tax execution, live credit enforcement, cost centres,
Billing/Catalog consumers and administration screens remain outside the approved master scope.
See [release/rollback instructions](accounting-masters-release.md) before an authorized deployment;
populated-data downgrades require reconciliation of new registration-free duty profiles and
general/registration-specific address uses. No live database, application outbox or deployed
gateway was changed by this work.

## Additional final review and fixes

The user requested a further final review after the six-phase completion. Manual review
again covered account/profile dependencies, party/date invariants, group protection, import
and mapping workflows, field authorization, audit rollback and tenant/company scoping. The
named review slash tools remain unavailable; this was a source and regression review.

Five regression cases reproduced three issues before application changes:

| Finding | Repair |
|---|---|
| A draft account could change from TAX or BANK to GENERAL while retaining its old profile. | Every existing-account mutation checks both owned profile types and rejects incompatible account kind with 409. |
| A draft tax account could move to an incompatible head after profile creation, and activation also missed that conflict. | Shared domain validation checks purpose/head compatibility on profile writes, account edits and activation. Legacy inconsistent drafts cannot activate; compatible draft group changes remain supported. |
| Mapping-draft validation could reveal facts about read-denied values through success or validation errors. | Validation checks readability before evaluating the stored values, including conditional denies. Sparse detail reads remain available. |

All seven new regression/domain/import cases passed. The affected account, integrity and
workflow run passed 25 tests. Tests verify rejection leaves account version/status and audit
history unchanged, and import preview leaves no mutation. Strict mypy covers 72 files;
Ruff lint/format and generated-contract checks pass. No migration or public schema changed.
The full native MySQL 9.6.0 run passed **129 tests in 700.30 seconds**, with **95.54% overall
coverage**, up from 95.38%. Domain modules remain **99–100%** covered. All 72 migrations,
model parity, representative query plans, concurrent idempotency and the complete
downgrade-to-base/upgrade round trip passed. The final review fixes and verification are
complete; no further blocking finding remains in the reviewed master scope.

Evidence: `.test_artifacts/accounting-completion/final-review-native.txt` and
`.test_artifacts/accounting-completion/final-review-coverage.json`. These are local test
artifacts, not deployment records. The unrelated Identity role failures recorded above
remain outside these fixes.
