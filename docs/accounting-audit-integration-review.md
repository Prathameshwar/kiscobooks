# Accounting Audit integration execution and reviews

Implemented 2026-09-17 under the accepted seven-phase plan. Both planned review/fix passes
and the additional requested final review are complete. Native verification and cleanup passed. No deployment backlog was
replayed, no production credentials were changed, and no commit/publish was performed.

| Phase | Status | Evidence |
|---|---|---|
| 1 Contract | Complete | Accepted privacy/compatibility contract; generated Accounting event matrix; frozen 204-entry legacy manifest |
| 2 Delivery contract | Complete | Actual setup command, signed publisher, real consumer; new and legacy actions ingest once; idempotent replay retains six setup effects |
| 3 Evidence/access | Complete | Safe pre-flush snapshots, exact monetary strings/currency, request correlation, original/effective actors, export-page and sensitive-detail access events |
| 4 Operations | Complete | Three separate workers; both publishers' inventory/retry/DLQ CLI; bounded verification; native immutable grants and worker canary |
| 5 Auth/API/client | Complete | Identity policies and company step-up bound into signed gateway actor; redacted detail/export; lean list SQL; generated Audit client |
| 6 Console | Complete | Real session and BFF, company/entity scope, paging, on-demand detail/Identity actor lookup, JSON export, pending/error states |
| 7 Verification and rollout evidence | Complete | Native financial workflows, real gateway/browser, fault recovery and two review/fix passes; runbook includes consumer-first rollout and evidence-preserving rollback |

## Review 1 - correctness and simplification

Manual walk of CLAUDE.md sections 5 and 6, contract matrix, transaction ownership, compatibility,
publisher confirmation, inbox deduplication, query bounds and worker ownership. `/simplify` is
not available in this session; this was an equivalent manual pass, not a claim that the command
or an independent reviewer ran.

| Severity | Finding | Fix and verification |
|---|---|---|
| Medium | An invalid original in the dead-letter window stopped unfiltered inventory before operators could inspect other events. | Inventory now reports a sanitized ID and `verified: false`; explicit invalid selections still block replay before publication. Failing regression reproduced, then all six DLQ tests passed, including confirmation-before-ACK and preservation of original bytes. |
| Medium | PowerShell evaluated the default env-directory expression before the script root was reliably available. | Resolve it in the script body. The native worker probe starts all three workers, repeats start with stable tracked PIDs, checks status, delivers a canary, and stops twice. |
| Medium | Stopping a Windows venv launcher could leave its child interpreter running. | Stop only the verified PID tree after checking executable, module and start time. Native worker cleanup verifies repeated start/status/stop. |
| Low | The test harness captured worker-launcher pipes inherited by long-lived children, preventing EOF and cleanup. | Use private log files for launcher output and always stop workers/remove env files in cleanup. Native worker verification completed. |

Reviewed fixes preserve original messages and timestamps, avoid synchronous Audit calls in
Accounting transactions, and leave existing local revision consumers compatible.

## Review 2 - security and integration

Manual security review of actor/source trust, tenant/company and step-up scope, policy subject
resolution, legacy evidence, cursor binding, response privacy, BFF origin enforcement,
credentials, grants and recovery. `/security-review` is not available; these checks and their
regressions are the equivalent manual pass.

| Severity | Finding | Fix and verification |
|---|---|---|
| High | Legacy Accounting free-text context/reasons could expose values omitted by field-level changes redaction. | Accounting context is restricted to a bounded integer export count and free-text reasons are omitted from detail/export responses. The stored row and hashes are untouched. Regression first reproduced the leak, then verifies both surfaces and hash preservation. |
| Medium | Native browser export was rejected when Next normalized a loopback URL origin. | Compare Origin to the actual Host and request protocol, without trusting forwarded-host input. Regression accepts the real local browser while rejecting cross-origin export. Audit and existing product BFF use the same helper. |
| Low | Production build exposed missing client/transpilation boundaries and an exported helper in a Next route module. | Mark the shared list-query hook as client code, transpile the generated client, and move the unchanged product-path helper outside its route module. Authenticated console pages are explicitly dynamic so builds require no user session or runtime secrets. Full production build passes. |

The final actor-name lookup was reviewed within this pass: Identity enforces `user.read` and
tenant scope; the BFF returns only an active, non-anonymized user's name, never the profile;
reads use `no-store`, run only after successful detail authorization and fall back to IDs on
permission/session/network failures. Names never enter Audit storage or export evidence.

No unresolved critical/high finding remains from these two passes. Conditional historical denies
remain conservative; missing policy context withholds Accounting field evidence. Grant/policy
changes invalidate opaque cursors, and an event's persisted company remains authoritative.

## Verification from the two planned passes

| Check | Result |
|---|---|
| Native financial command-to-Audit workflows | 6 passed; 499 events across import, journal post/reversal, fiscal transitions, credit override, charge approval/reversal and waiver; zero chain breaks |
| Native Accounting full suite | 287 passed; 95.74% coverage; migration downgrade/upgrade round trip passed |
| Native Accounting evidence follow-up | Exact old/new high-precision monetary strings and currency, safe evidence, export and sensitive-read checks passed |
| Real RabbitMQ transport | 3 source cases passed; Accounting case rerun with actual local broker stop/start and redelivery passed |
| Audit full suite | 115 passed, 5 opt-in infrastructure skips; 91.66% coverage |
| Shared platform full suite | 881 passed; 97.75% coverage |
| Affected Identity auth/policy/impersonation suite | 14 passed |
| Console full suite | 262 passed |
| Shared UI list-query suite | 41 passed |
| Generated API client | Generation/drift check, TypeScript and 4 tests passed |
| Python checks | Ruff clean; strict mypy: Accounting 86, Audit 27, platform 60 and affected Identity 4 source files |
| Console production build | Passed; authenticated routes render on demand |

Native financial artifacts under `.test_artifacts/audit-financial` record 51 import events,
78 journal events, 69 fiscal events, 95 credit-override events, 104 charge approval/reversal
and 102 charge waiver events. Every test runs the real command workflows before publishing
their persisted outbox bodies through RabbitMQ into a separately migrated native Audit schema.
The probe checks exact message-ID coverage and the complete resulting chain.

The native gateway/browser proof records actual Accounting changes, exhausted-message recovery,
DLQ replay, live policy changes, forged-header and foreign-company denial, browser detail and
JSON export, Audit-export self-events, three worker processes and a worker-delivered canary.
It validates UPDATE/DELETE denial under the runtime Audit grant and uses a separate maintenance
credential for partitions. Query plans and screenshots accompany its JSON result.

## Verification boundaries and release readiness

Accounting and Audit in native proofs use separate disposable MySQL schemas and real RabbitMQ.
Identity uses an isolated SQLite fixture with real JWT verification against generated JWKS;
the console receives a real encrypted NextAuth session through the checked-in gateway.
This is application-boundary verification, not an external Authentik/deployment certification.

The native fault probe cancels execution exactly after broker confirmation and before outbox
commit, checks duplicate delivery after recovery, rejects a retired verification key, accepts
a delayed original under a rotated key, and causes a real MySQL credential failure before
redelivery. It does not kill a production database or delete production queues. Unit tests
separately verify rollback, invalid signatures, issuer/route/entity mismatches and reconnect
error sanitization. Small disposable query plans establish indexed access and partition pruning;
they are not a production-load benchmark.

Production scheduler registration, alert destinations, deployed broker ACLs, keys and historical
backlog selection remain deployment inputs. The code/runbook is ready for those inputs; this
work does not claim to have changed them. See [operations](accounting-audit-operations.md) for
reproducible probes, consumer-first deployment, reviewed recovery and rollback.

## Artifacts and cleanup from the two planned passes

The full-path result from those passes is
`.test_artifacts/audit-proof-ed6473daac2a43a18747e7bc/result.json`, with `query-plans.json`,
`console-detail.png` and `browser-export.json` beside it. It reports 9 Accounting events,
1 worker canary, 9 exhausted deliveries recovered, 1 dead letter recovered, 2 Audit export
self-events, zero duplicate rows and zero chain breaks. Cancellation after confirmation,
native database-failure redelivery, rotated/retired signing keys, current field policy and the
real browser all pass. Partition provisioning created January-March 2027 and a second call
created none. Detail EXPLAIN uses the primary key and one partition; the tiny company-list
fixture uses tenant index access plus filesort, so no unsupported index change was introduced.

The follow-up monetary test verifies `900719925474099.1234` to `900719925474099.5678` with INR
in native persisted outbox evidence. Its high-precision case is explicitly native-only because
SQLite's numeric affinity rounds the source value; the ordinary exact-value case also runs in
the local fast suite. This records the test-driver limit without relaxing native precision.

Shared library changes are synchronized with the current workspace version (0.26.0, including
concurrent warehouse work); all seven consumer/source lockfiles pass offline lock checks.
The API client and UI packages are version 0.1.1. The Identity posting adapter dependency is
updated with its version 0.2.1. Concurrent Catalog/warehouse application edits were preserved.
The first platform run's concurrent permission-doc mismatch is resolved: the final full
platform suite is green. No unresolved baseline failure is being hidden.

Owned test schemas, worker processes and temporary worker env files were cleaned up. Two
pre-existing September 15 test schemas were left untouched. The
separate native financial and full service suites are complete. Final Ruff/format, strict
mypy, generated OpenAPI/client checks, client typechecks, production build and whitespace
checks pass. No production credentials, deployment schedulers or actual backlog were changed.

## Additional final review - 2026-09-17

Reviewed the completed integration and walked the security/correctness invariants again,
including consumer validation, immutable evidence, bounded verification and HTTP failure
responses. This was a manual review with regression tests; `/simplify` and `/security-review`
remain unavailable in this session. Each finding below was reproduced with a failing test
before its fix. The fixes were then reviewed and validated together.

| Severity | Finding | Fix and verification |
|---|---|---|
| High | Sequence-only chain pagination skipped a duplicate sequence when it crossed a page boundary, incorrectly reporting an intact chain. | Order and paginate by `(sequence, occurred_at, id)` while carrying the preceding hash and sequence. Regression covers page sizes 1 and 2. Native MySQL detects an inserted duplicate at page size 1; rollback restores the original clean chain. |
| High | Authenticated messages with oversized string fields or non-finite JSON reached database handling, where permanent storage errors could stall the single consumer. | Match the existing column lengths and validate finite JSON in changes/context before opening a database session. Signed-message regressions assert rejection without a database call. Native RabbitMQ confirms both malformed examples reach the dead-letter queue while subsequent valid delivery succeeds. Database outages still remain retryable. |
| Medium | Unexpected Audit API errors returned plain text without the required no-store error response. | Add a generic error-envelope handler with explicit `Cache-Control: no-store`. A real ASGI request with a failing session verifies status 500, the standard envelope and omission of private exception details. |

| Verification rerun for this review | Result |
|---|---|
| Audit full suite | 134 passed, 5 opt-in infrastructure skips; 91.81% coverage |
| Accounting actual-command ingestion and legacy compatibility | 2 passed |
| Real RabbitMQ transport | 3 source cases passed |
| Expanded native gateway/browser/worker proof | Passed; 2 invalid payloads dead-lettered and duplicate-sequence detection passed |
| Audit Ruff and strict mypy | Passed; 27 source files checked by mypy |
| Changed Audit file formatting | All 19 changed Python files passed |
| Native proof helper Ruff/format | Passed |
| Audit OpenAPI drift check | Passed; HTTP schema and generated client unchanged |
| Whitespace check | Passed |

The latest full-path artifacts are in
`.test_artifacts/audit-proof-62fb3441358a473a80586c95/`, including `result.json`, query plans
and browser evidence. The run also records 9 Accounting events, 1 worker canary, 9 exhausted
deliveries recovered, 1 dead letter recovered, 2 Audit export self-events, no duplicate
persisted deliveries and zero final chain breaks. Native database-failure redelivery,
confirmation-before-commit cancellation, signing-key rotation/retirement, scope, current field
policy, browser access and worker start/restart/status/stop all pass. The deliberate duplicate
used to test verification is rolled back before the final clean-chain assertion.

A broader formatter check also flagged seven unchanged baseline files: `domain/categories.py`,
`domain/partitions.py`, `domain/retention.py`, `tests/test_consume.py`,
`tests/test_live_rabbitmq.py`, `tests/test_routes.py` and `tests/test_routes_more.py` under Audit.
These unrelated formatting differences were left untouched; all changed files pass.

The earlier full Accounting financial, shared-library and UI suite results above remain the
record of those planned passes; they are not claimed as reruns in this review. The native
Identity fixture and deployment boundaries stated above still apply. No unresolved finding
remains from this final pass. Owned test fixtures and temporary worker credentials were cleaned
up, with pre-existing schemas and unrelated concurrent work preserved.
