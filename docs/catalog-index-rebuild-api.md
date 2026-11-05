# Catalog custom-index rebuild APIs and worker

The first C5.03 increment implements resumable non-unique scalar/member indexing for the
already migrated custom-enabled group/category masters. Unique-field adoption remains unavailable
until staged claims and complete company/tenant coverage ship. Existing uniqueness claims
have no generation and cannot be reused as a speculative adoption workspace; partial scans
cannot establish tenant-wide uniqueness.

## API and authorization

Base: /v1/companies/{company}/entities/{entity}/field-indexes/{field_key}.
Supported entities are catalog.item_group and catalog.item_category.

| Path | Method | Purpose |
|---|---|---|
| Base | GET | Current generation state and whether it matches the effective definition |
| /rebuilds | POST | Start from expected_version (0 means no index state yet) |
| /rebuilds | GET | Lean job history, status filter, id/-id sort and signed paging |
| /rebuilds/{job_id} | GET | Authorized counters, phases and safe reason code |
| /rebuilds/{job_id}/cancel | POST | Cancel an unactivated build using its expected job version |

Commands require Idempotency-Key, current custom_field.manage and the owner's read/manage
permissions on this company. Reads require the owner read permission. The field itself must be
readable; conservative conditional read-denies prevent a rebuild rather than producing a partial
index. Replays check current authority and return references under current field protection.
No response includes the private definition snapshot, custom values or transport credentials.

Normal group/category list APIs accept custom_filters as a JSON array string (at most 4 KiB,
1-16 typed predicates). Operators come from the shared custom-query contract: eq, in, gte, lte,
has_any, has_all and is_set, according to type. Decimal values remain strings. Scalar/member
predicates use EXISTS, so multiple matching members never duplicate owner rows. Native paging,
search and sorting remain unchanged; arbitrary/custom-field sorting is not introduced here.
Queries reject an unprepared/stale generation and unreadable fields. Their signed cursors include
index generations/digests, and shared state locks prevent retirement during the query transaction.

## Processing and recovery

Each generation pins the exact effective definition digest. The worker checks the initiating
user's fresh Identity permission proof outside the DB transaction, then checks source-version
agreement and current field rights inside it. Company policy, index state, job and owner rows
are locked in that order. No external network call occurs inside a chunk transaction.

Chunks default to 25 owners (maximum 100). Index rows, traversal checkpoint, counters and audit
outbox commit together. Failure or expiry before commit rolls the chunk back. A restart resumes
its durable checkpoint; UUID traversal order is not treated as a commit watermark. Normal writes
also maintain the matching building generation, including a later commit behind the cursor.
A final locked definition check switches the active generation only after the complete scan.

A source outage/version mismatch defers work without extending permission freshness. Revoked
permission, source-definition drift or invalid historical values fail the build without publishing
partial data. Round-robin polling prevents one deferred job from starving other jobs. Failed or
cancelled builds and replaced generations are pruned in bounded cleanup chunks. Cleanup acts as
the scoped service and emits system audit; it cannot select the active generation for deletion.
A previous valid active generation remains available while a same-definition rebuild runs.

## Database and operation

Migration 0033 creates field_index_state; 0034 creates field_rebuild_job. The first stores monotonic
allocation, active/building definition digests, retiring generation and optimistic version. The
second stores original actor, private definition snapshot, source/generation binding, phase/status,
checkpoint, safe counters/reason and version. Both are tenant/company scoped; job-to-state uses a
composite company/tenant FK. Pair checks and generation constraints prevent mismatched state.
There are now 34 materialized Catalog tables; no production migration has been run here.

Run python -m catalog.tasks.index_worker from apis/catalog after applying the service's migrations.
Required CATALOG_ settings: DATABASE_URL, IDENTITY_SOURCE and SOURCE_SUBSCRIPTIONS, using the
existing source transport configuration. The Identity credential must opt into actor authorization.
INDEX_CHUNK_SIZE defaults to 25 (1-100); INDEX_POLL_SECONDS defaults to 3 (1-60). Keep the separate
source worker running to refresh Catalog's security context. HTTP startup launches neither worker,
never migrates and never seeds. Worker cancellation closes its database engine.

Review evidence includes real Identity HTTP authorization/revocation, dual-write insertion behind
the cursor, multi-select de-duplication, cancellation/cleanup, rollback and expiry before commit,
source drift, tenant/company FK isolation and database generation-state regression tests.
Live MySQL concurrency/query plans and RabbitMQ propagation remain release verification gates.

Verification 2026-09-12: full Catalog 233 passed/one MySQL skip, 99.57% overall and
100% domain coverage.
