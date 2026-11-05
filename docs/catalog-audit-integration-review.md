# Catalog audit integration execution and review

Date: 2026-09-17. Local implementation and verification; no deployment or publishing.
Status: implementation/build and both native proofs complete; final Catalog coverage in progress. See the maintained
[phase todo](catalog-audit-integration-plan.md).

## Implemented behavior

Catalog mutations retain their transaction/outbox/RabbitMQ path into Audit. There is no
synchronous Audit HTTP dependency in business commands. The generated Catalog route/evidence
matrix also generates the console entity filter. Safe scalar before/after values retain
Decimal precision; private fields and unknown prior values remain markers. Pricing/tax
configuration events are money-category; successful prepared CSV/XLSX downloads are access
records committed before the response. Original/effective actors and validated correlation
are retained; background cleanup/failure explicitly identifies a system actor.

Identity supplies current Catalog historical field policies to Audit. Detail/export project
field names as well as values, custom-field policy keys, aggregate markers and safe metadata.
Catalog's gateway business route now obtains a signed actor from Identity and overwrites
client-supplied actor headers. Publisher operations and the owned worker launcher include
Catalog. Shared scalar normalization was extracted from Accounting; platform/client versions
and every Python consumer lockfile were updated offline.

## Reviews and fixes

The repository requests `/simplify` and `/security-review`. Those commands are not available
in this session. Two sequential manual reviews apply CLAUDE.md sections 5 and 6 and the plan's
checklists, with regressions before application fixes. No delegated review is claimed.

### Review 1: correctness and simplification

- Fixed missing `actor_type` on index cleanup/failure; user-attributable events remain user
  events. The new regression first failed with `KeyError: actor_type`; after the fix the
  index lifecycle/rebuild selection passed 18 tests.
- Fixed the generated matrix classifying background cleanup/failure as admin even though
  production emits system-category. The category regression first failed, then all three
  contract/attribution checks passed. Regenerated the matrix and console entity list.
- Reviewed command snapshots, create/update/delete markers, Decimal normalization, replay,
  preview rollback, report commit ordering, route coverage and worker PID ownership.
  Shared normalization preserves Accounting behavior; domain allowlists remain in Catalog.

### Review 2: security and integration

- Final URI review reproduced company step-up bypasses on encoded Catalog/Accounting company
  IDs and an encoded Audit prefix: the gateway authorized all three with 204 instead of 403.
  Identity now normalizes percent encoding, slashes and dot segments before resolving scope,
  and rejects malformed/nested encoding. Expanded URI regressions and native nginx checks
  verify that normalization cannot remove company step-up or historical Audit policy context.
  Both Catalog and Accounting native gateway/browser/worker proofs passed, including
  encoded-scope checks.

- Reproduced a hierarchy marker bypass: a deny on `catalog.item_group_parent.parent_group_id`
  hid the child event's field but left its parent group's `hierarchy` marker visible. Added
  item groups to the conservative aggregate projection. The regression also verifies that
  a deny in another company does not suppress this company's evidence. Full Audit retest:
  146 passed, 5 opt-in infrastructure skips, 92.77% coverage; evidence projection 100%.
- Reviewed source issuer/action/entity binding, original/effective actor handling, company and
  tenant isolation, scoped roles, conditional policies, unknown policy context, custom-field
  markers, metadata/reasons, download authorization, signed cursor policy binding and recovery
  authority. Existing source mismatch, private-field and gateway forgery regressions remain.

## Native evidence

The completed Catalog gateway proof is in ignored artifacts
`.test_artifacts/audit-proof-1d02f230b5bb44cd8a8a1954/result.json`, with query plans, browser
screenshot/export and worker lifecycle records. It verified four initial Catalog events,
one independently supervised worker canary, two Audit export self-events, four exhausted
messages recovered, one dead-letter recovery, two malformed payloads rejected, zero duplicate
rows and zero chain breaks. Rotation, delayed signatures, commit-before-outbox-mark cancellation,
native database failure/redelivery, immutable runtime grants, bounded query plans, policy/scope
checks and all four workers' repeated start/status/stop passed.

Native GOODS product (6), SERVICE product (6), pricing (13), tax (4), CSV (4) and XLSX (4)
workflows passed exact message-ID coverage and chain verification against independently
migrated Catalog/Audit schemas. Results are in `.test_artifacts/catalog-audit-workflows/result.json`.

Boundaries: MySQL/RabbitMQ and Catalog/Audit HTTP/gateway/browser are real local processes.
Identity uses disposable SQLite plus real JWT/JWKS validation; Catalog source facts are explicit
fixtures. This does not certify external Authentik or a deployed environment. Individual
workflow tests use their existing fixed authorization clock; the gateway proof uses real clocks.
No schema migration was added by this audit integration. Fresh schemas upgrade to head; existing revision
0131 intentionally blocks downgrade, so this audit proof does not claim a migration round trip.

Test harness fixes are distinct from application findings: service-owned ORM maps required
separate Catalog/Identity interpreters; basic.get required bounded polling for asynchronous
dead-letter routing; the four-worker PowerShell timeout needed host-load headroom; and long
native workflows needed their existing fixed authorization clock. Initial unsuccessful probes
were rerun after these corrections. The Accounting browser initially exceeded its 30-second row wait while Next.js compiled
the first API route (the request returned 200 in 30.5 seconds). Its first-row wait now uses
the same bounded 90-second startup allowance as navigation. Private configuration is never committed.

The original Accounting native proof also passed after the shared harness changes:
`.test_artifacts/audit-proof-1bb23b43f11547218028cc6f/result.json`. It retained nine Accounting
events, one worker canary, two export self-events, zero duplicates and a clean chain, including
its original three-worker configuration. Catalog's separate proof verifies all four workers.

## Validation record

- Console: 263 tests; TypeScript and production build passed.
- API client: 4 tests; TypeScript and generated-contract checks passed.
- Identity affected URI/policy/session/impersonation selection: 18 tests; gateway and policy
  services strict typing passed.
- Real RabbitMQ transport: 3 source cases passed (Identity, Catalog, Accounting).
- Platform: full 881 tests plus 12 new scalar cases; combined coverage 97.75%.
- Accounting affected evidence/delivery: 6 passed, 1 existing native-only case skipped in SQLite.
- Audit: final full 146 passed, 5 opt-in infrastructure skips, 92.77%.
- Catalog: focused phase and review checks passed, including failed report-access commit
  rollback with no successful file response or extra outbox event; full coverage run pending.
- Changed-file Ruff and formatting pass. Strict typing passed for Catalog (225 selected source/test/tool files),
  Audit (27), Identity policy services and platform. OpenAPI and generated client/matrix checks
  passed. Owned infrastructure cleanup passed. Final Catalog coverage pending.


## Cleanup record

Removed the disposable schemas/users from completed proofs and the interrupted Catalog
proof (077dcd4f66624990a60784c0). Its partial catalog_test schema was identified by its sole
alembic_version table and creation time matching the interrupted command. Empty interrupted
Catalog proof queues/exchanges were identified by their Catalog bindings and removed with
empty/unused checks. Pre-existing Accounting test schemas and inherited broker fixtures were
preserved. Worker env files are empty, no worker Python processes remain, and the owned
MySQL/RabbitMQ listeners have stopped. The interrupted proof's two remaining nginx processes were matched to its exact runtime
configuration and stopped; final inspection found no owned worker/gateway/console children.


The full Catalog coverage run is split by test file into four isolated Python processes,
with all 957 collected tests assigned exactly once and separate coverage/cache files. This
uses no skipped test selection; the combined report retains the 90% floor. The single
sequential run was replaced after 28 minutes at roughly 100 tests, and is not counted as a
completed suite. Manifests/logs/results are under `.test_artifacts/catalog-audit-validation`.


## Full-suite finding and fix

The parallel run reproduced `test_custom_expansion_and_owner_bounds_fail_before_writing`:
its 4096-character fixture is now rejected by the existing scalar contract guard, before the
normalized claim byte limit, so the older expected ValidationFailedError was stale. The test
now asserts that contract conflict separately and uses valid raw text with Unicode expansion
to exercise the intended byte limit. Production validation and storage bounds were preserved.
The complete persistence module passed all 16 tests after correction, both normally and
with coverage. The formatted index/audit-evidence selection passed 22 coverage tests. A pytest cache-directory
rename warning did not affect assertions; isolated cache directories have been prepared.

The instrumented bulk activation workflow reproduced a 30-second actor-proof expiry at
`bulk_execution.current_actor`. The normal run passed. The existing workflow clock fixture
now freezes proof generation and validation together; production proof lifetime is unchanged.
The followup includes the explicit expired-preview rollback and actor-authorization checks.

Concurrent warehouse model edits briefly prevented isolated collection with an undefined
OPERATION_FLAGS import. The concurrent edit resolved it; this task did not modify those files.
The full-suite manifest records the test inventory at collection time.

The Accounting browser retry reached real list/detail responses, but first-time actor-route
compilation exhausted its detail wait. Detail startup waits and the enclosing process budget
now cover bounded dev compilation. The complete proof is being rerun with those bounded startup budgets.

The fixed-clock bulk activation selection passed all 4 coverage cases, including expired
preview rollback and actor authorization. Both original product roundtrip cases passed
normally and under coverage (2 each); their initial shard failure reports are still pending.
Changed fixture typing and final native-harness Ruff/format checks passed.

A fresh collection found 993 tests: the original 957 plus 36 concurrently added warehouse
resolution cases. Those additions have a separate coverage selection; no original node
was removed. The collection delta is retained beside the initial manifest.

The concurrent warehouse field registry added WarehouseOperationPolicyRevision. The current
registry regression reproduced its missing model mapping. Catalog startup and the parity
test now include that model; unrelated warehouse implementation was preserved.

The current warehouse selection passed all 72 cases with coverage; the new startup mapping
also passed 7 registry/audit checks and strict typing. Native proof schemas/users and private
worker files were removed. MySQL stopped normally. RabbitMQ control commands stalled after
proof completion; cleanup verified the owned Erlang executable, start time and listener PID
before terminating that test process and its owned control clients. Existing broker data
and unrelated schemas were preserved; this cleanup does not claim graceful broker shutdown.

Representative scheme-governance and commercial-history failures both passed isolated
coverage retesting (2 cases). The full shard reports remain the source of truth for diagnosing
the initial failures; successful retries are recorded separately rather than called a clean run.

The first completed shard reported a shared Windows pytest-temp PermissionError in all
three warehouse-concurrency setups; the separate current warehouse run passed those cases.
The final followup uses a unique, verified workspace basetemp. Four long lifecycle-test
modules now use the existing fixed workflow clock. The followup also includes explicit
source-freshness and actor-expiry checks so production rejection behavior remains tested.
