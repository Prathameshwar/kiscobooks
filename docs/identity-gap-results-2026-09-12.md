# Identity gap implementation and review results

Date: 2026-09-12. Scope: the approved [GP0-GP8 plan](identity-gap-completion-plan.md).
Status: local implementation, verification and review complete.
External release gates remain open. Nothing was deployed or published.

## Findings and disposition

All confirmed findings below have regression tests that failed before correction and
passed afterward. The review covered authorization/object scope, tenant filtering,
input validation, sensitive data, transactional audit, durable messaging, lifecycle,
first-use immutability, client credentials and bounded recovery. Manual simplification
and security review were performed; the slash commands named in CLAUDE.md are not
available as installed skills/tools in this session.

| Finding | Effect before correction | Resolution and regression evidence |
| --- | --- | --- |
| Company session selection bypassed step-up | Explicit protected-company selection returned company data without proof | Enforce query/body/reference scopes; omit protected default selection without proof. `test_gap_step_up.py`, `test_gap_step_up_boundaries.py`, `test_gap_session_contracts.py`. |
| Field metadata overstated write authority | Read-only users and frozen/inactive fields could be presented as writable | Merge live permissions, supported mutation fields and lifecycle/posting rules into descriptors. `test_gap_customization.py`. |
| Valid empty AES-GCM plaintext failed decryption | The minimum envelope length rejected an empty authenticated payload | Accept the valid nonce+tag envelope; preserve AAD/tamper checks. Shared `test_crypto_audit_context.py`. |
| Invalid timezone paths raised 500 | Absolute, relative and empty timezone strings escaped validation | Map both unknown zones and invalid keys to 422. `test_gap_session_contracts.py`. |
| Malformed gateway company UUID raised 500 | A 36-character malformed UUID escaped the internal auth route | Validate the extracted UUID and return 422. `test_gap_session_contracts.py`. |
| Audit retry status was stale | The recovery command reset attempts but reported the pre-reset exhausted count | Flush the reset before querying diagnostics; verify persistence, repeated retry rejection and engine disposal. `test_gap_operator_commands.py`. |

The historical-revision MySQL test fixture was also corrected to insert only columns
present at that revision. New test fixture mistakes were corrected and rerun; they are
not represented as product defects. No unresolved confirmed code defect remains from
this review. That statement does not certify the unexecuted external workflows below.

## Gap-to-evidence ledger

| Gap | Implemented and verified locally | Remaining acceptance dependency |
| --- | --- | --- |
| G01 authentication | RS256/JWKS/issuer/audience checks, live grants, current session, invitations/verified linking, activation/revocation/bootstrap, Auth/Console integration, Notification adapter/template | Real Authentik and TLS gateway, configured sender/provider, invitation acceptance and sign-out in the deployed browser flow |
| G02 lifecycle | Group assignments/removal, primary membership changes, company/department/role lifecycle, history, self-escalation/replay guards, real MySQL races | No separate code dependency; include in release smoke tests |
| G03 child resources | Contacts/preferences, AES-GCM banks/reveal/rotation, one-time hash-only tokens and live revocation, private Azure workflow, actual Azurite HTTP checks | Azure cloud identity/delegation permissions, private container/CORS and cloud recovery |
| G04 customization | Company definitions/layout/policies, typed values/indexes/sequences, merged metadata, bounded rebuild, source facts and policy/query enforcement | Launch scope remains `identity.company`; dynamic options/fiscal-reset numbering await their owner adapters as documented |
| G05 step-up/support | Fresh challenges, committed proof receipts, scope/reference enforcement, read-only support start/end/expiry, attribution and client/consumer checks | Real Authentik + Redis + gateway browser flow, Redis outage and recovery |
| G06 first-use locks | Signed Billing client, reserve/confirm/abort commands, durable pending freezes, prerequisite feature locks, terminal publisher, replay/races | Actual Billing ledger/outbox/inbox integration; Billing service is absent and building it is outside this Identity plan |
| G07 audit | Authenticated allowlisted publication, confirms/retries/diagnostics/recovery, deduplicated ingestion and DLQ, real RabbitMQ restart | Combined broker + production-like Audit MySQL rollout/recovery; local live broker test used Audit SQLite persistence |
| G08 verification | Local suites, migrations, generated contracts, strict typing/lint, review and runbooks | Target-environment deployment, combined recovery exercise and load/performance measurements |

## Verification results

Counts below are separate runs and can overlap; do not add them as a unique-test total.
The Identity coverage baseline from the preceding bug workstream was 93.97%.

| Check | Result |
| --- | --- |
| Final Identity suite, four workers, excluding MySQL marker | 1,224 passed, 1 opt-in Azurite test skipped; 93.97% combined line/branch coverage, matching the baseline. The Azurite test passed separately. |
| Shared platform full suite | 771 passed, 98.56% combined line/branch coverage |
| MySQL 9.6 migration/constraint/race verification | 483 passed through revision 0057, including actual upgrade/downgrade/drift, ownership and concurrency checks; count also includes migration static checks |
| Azure SDK/document API tests | 12 SDK contract and 5 document workflow tests passed; also included in Identity suite |
| Actual Azurite HTTP protocol | 1 passed: private read denial, create-only overwrite rejection, verified finalization, snapshot stability and cleanup replay |
| Actual RabbitMQ restart | 1 passed: confirm, unroutable retry, persistent unacked redelivery, inbox dedupe and invalid-message DLQ |
| Audit affected suite | 98 passed, 1 opt-in live test skipped and 2 MySQL tests deselected; broker test executed separately |
| Notification affected suite | 55 passed, including Identity preference/invitation delivery |
| Catalog affected auth/audit checks | 5 passed; unrelated concurrent Catalog product changes excluded from this review |
| Auth UI | 39 existing/flow tests plus 11 server authentication tests passed |
| Console UI | 68 existing tests plus 4 Identity session/credential forwarding tests passed |
| Generated TypeScript transport | 2 passed; Identity generation drift check passed |
| Static checks | Identity/Billing client strict mypy: 125 source files clean; shared/Notification typing and Ruff clean; Auth/Console TypeScript clean |

The final run used unchanged application source throughout and finished in 333.66 seconds.
The explicit 93.97% overall gate and every Identity domain floor passed; the lowest
domain file was 94.87%.

Final artifacts are under `.test_artifacts/identity-gaps-20260912/`, including
`identity-final.xml`, `coverage-final.json`, `platform-final.xml`, `platform-final.json`
and `final-boundaries.xml`. Earlier failed coverage runs in that directory are historical
attempts, not the final gate. No coverage exclusion or threshold was relaxed.

## Operational handoff and release gates

Use [operations](identity-gap-operations.md), [contracts](identity-gap-contracts.md) and
[local RabbitMQ](local-rabbitmq.md). The maintained [todo](identity-gap-todo.md) distinguishes
local completion from live acceptance. Secrets belong in environment/secret-manager
configuration, never in chat, tracked files or logs.

1. Configure an actual Authentik application/flows and trusted TLS gateway, then exercise
   invitation acceptance, account linking, renewal, revocation and sign-out with a real
   Notification email route. Provider fixture signatures do not establish this evidence.
2. Configure Redis and exercise challenge completion, reuse/expiry/revocation and outage
   recovery through Auth and Console. The Redis adapter unit tests are not a live Redis run.
3. Configure the selected Azure account/private container and managed/environment identity;
   verify account-level delegation permission, scoped data permission, CORS, signed URL
   expiry and cleanup under cloud failures. Azurite cannot validate Azure RBAC.
4. Integrate the Billing client and terminal events with a durable ledger transaction,
   outbox/inbox and persisted operation ID. Never auto-abort an uncertain money outcome.
5. On the release target, combine real broker + Audit MySQL persistence and perform
   restart/deployment recovery and representative load checks. Local bounded-query and
   batch tests establish safeguards, not capacity or latency claims.

## Synchronization and scope

Identity migrations 0051-0057, ORM/schema/factories and OpenAPI/TypeScript contracts are
synchronized. Shared package 0.17.0 and consuming locks are updated. Azure SDK packages
are pinned; pytest-xdist is a dev dependency for isolated test workers. The Billing client
is a separate package and imports no Identity ORM. PostgreSQL/system MySQL were not
repurposed; local RabbitMQ, Azurite and the disposable MySQL use isolated runtime state.
Existing Catalog and UI work from other concurrent tasks was preserved.
