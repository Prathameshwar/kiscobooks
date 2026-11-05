# Identity to Catalog source operations

**Contract:** identity.catalog_context.v2, event identity.catalog_context.changed, schema 1.
Identity owns its native records and three source artifact tables (0035-0037). Catalog owns eleven
minimal projection tables, a checkpoint and event buffer (0016-0027, 0176). No cross-service FK or ORM import.
Contract v2 adds the company currency allowance fact for foreign price authoring; both source
publisher and Catalog consumer must be upgraded together and a complete v2 snapshot activated
before foreign pricing is enabled.

## Processes and configuration

Run each command from its service directory after applying that service's reviewed migrations.
HTTP startup does not migrate databases, seed a company or launch workers.

| Process | Command | Required environment values |
|---|---|---|
| Identity HTTP | uv run --frozen uvicorn identity.main:create_app --factory | Existing IDENTITY_DATABASE_URL, ACTOR_SIGNING_SECRET, CURSOR_SIGNING_SECRET; source settings below |
| Identity source publisher | uv run --frozen python -m identity.tasks.catalog_publisher | IDENTITY_DATABASE_URL, SOURCE_BROKER_URL, SOURCE_BROKER_USER, SOURCE_EVENT_SECRET |
| Catalog HTTP | uv run --frozen uvicorn catalog.main:create_app --factory | CATALOG_DATABASE_URL, ACTOR_SIGNING_SECRET |
| Catalog source worker | uv run --frozen python -m catalog.tasks.source_worker | CATALOG_DATABASE_URL, IDENTITY_SOURCE, SOURCE_SUBSCRIPTIONS, SOURCE_BROKER_URL, SOURCE_BROKER_USER, SOURCE_EVENT_SECRET |

Every short setting in a row uses that row's IDENTITY_ or CATALOG_ prefix. Secrets come from
deployment secret storage, never committed sample keys. Publisher SOURCE_BROKER_USER is its
broker login identity; the Catalog setting identifies the expected authenticated Identity publisher.
The consumer connects with its own credentials in SOURCE_BROKER_URL. Restrict broker permissions
and source exchange/vhost so another producer cannot impersonate this source.

Identity HTTP CATALOG_SOURCE_CREDENTIALS is a JSON object keyed by request key ID. Each entry has
secret and a scopes array of {tenant_id, company_id}. CATALOG_SOURCE_RESPONSE_SECRET independently
signs responses; CATALOG_SOURCE_RESPONSE_KEY_ID defaults to current. Keys require at least 32
characters. CATALOG_SOURCE_TTL_SECONDS defaults to 60, allowed 15-300.

Catalog IDENTITY_SOURCE is a JSON object containing base_url, request_key_id (default current),
request_secret and response_secrets (key-ID to secret map). HTTPS is required except explicit
loopback HTTP in local integration tests. Request paths/query/body hashes and exact response bytes
are signed with independent issuer/audience/operation authority. Redirects, credentials in URLs,
compressed bodies, bad signatures, missing pages and mismatched scopes reject.

Catalog SOURCE_SUBSCRIPTIONS is an optional bounded JSON array of {tenant_id, company_id}, matching the
Identity request allowlist. Alternatively, set CATALOG_SOURCE_DISCOVERY=true and explicitly grant
allow_enrolled_companies=true on the Identity source credential. The latter may have an empty
scopes array, but never a wildcard scope. Manual subscriptions remain supported and require
their explicit Identity allowlist. SOURCE_EVENT_KEY_ID defaults to current on both workers and must
match the event HMAC key. Default exchange platform.sources, queue catalog.identity_context,
dead exchange platform.source_errors. Catalog SOURCE_REFRESH_SECONDS defaults to 10 (1-20).
Do not tune refresh so the lease normally expires between successful renewals.

### Automatic company enrollment (approved 2026-10-27)

Authorised company creation atomically inserts catalog_source_enrollment alongside its creator's
company-admin assignment and security evidence (Identity migration 0088). Catalog cannot enroll
itself. Signed POST /internal/v1/catalog-enrollments pages expose only active enrolled company/tenant
IDs, with a signed cursor, at most 200 scopes per page. Discovery is an explicitly audited
installation-wide service read, independent of all user grants. Snapshot and actor-proof requests
recheck enrollment and current company/tenant status in tenant-scoped sessions. Existing static
credentials keep their original explicit authority.

The worker replaces its discovered subscriptions only after a complete authenticated list.
Discovery failures renew no leases. Duplicate scopes, cursor cycles, more than 100 pages / 10,000
scopes, malformed/signature failures and the total deadline reject the entire discovery run.
Revocation removes the company from future renewals and immediately denies further enrolled-scope
snapshot/proof requests; an existing completeness lease retains its documented expiry bound.
Valid signed events for a not-yet-enrolled tenant grant nothing and may be ignored: a later complete
enrolled snapshot establishes the authoritative baseline. Static mode retains strict rejection.

For existing installations, run identity.tasks.catalog_enrollment --env-file PATH first as a
dry run, then with --apply. The bounded, audited backfill enrolls only active companies in active
tenants and never restores an existing disabled enrollment. Local automatic configuration uses
start/win/catalog-enrollment-prepare.ps1, which preserves unrelated settings and refuses to
overwrite existing source credentials. Restart Identity/Catalog after configuration. The existing
audit-workers.ps1 lifecycle manages identity-catalog-publisher and catalog-identity-source; backend
startup starts both when configured, and backend stop stops both. New companies need no list edit
or service restart; availability follows the next successful discovery/snapshot refresh.

## Recovery and bounds

Declare the durable consumer queue before requesting bootstrap snapshots. Verify a complete
known-stream manifest and all page hashes/counts, activate atomically, then merge contiguous
buffered generations. Snapshot baseline and latest applied watermark are separate: events arriving
before a snapshot cannot make it regress or discard newer state. An incomplete catch-up rolls back.
Events never extend completeness leases. A gap or expiry stops dependent metadata/business APIs.
A source outage preserves prior evidence but cannot renew its authority.

The producer serializes participating ORM writes and snapshots with a tenant generation lock,
emits complete minimal facts/tombstones transactionally, and emits barriers for snapshot generations.
It rejects captured bulk/raw source writes. All alternate authoritative writer entry points must opt
into this capture contract; arbitrary external SQL is not claimed to produce events.

Initial engineering bounds: 10,000 records/8 MiB per snapshot, 512 KiB/128 records per page,
1,000 records/512 KiB per change, 32 live snapshots/company. Expired snapshot artifacts and caught-up
event buffers are pruned in bounded batches after five minutes' grace. Overflow fails closed and
requires the planned larger durable-job workflow; these bounds are not production capacity claims.

A dedicated confirmed outbox publisher selects only this event type; it cannot starve unrelated
Identity audit outbox records. The consumer verifies broker identity plus HMAC, deduplicates inbox
messages transactionally, and acknowledges after commit. Poisoned generations go through the
validation/DLQ path; recovery does not silently skip a generation to claim completeness.

## Evidence and remaining gates

Actual signed HTTP producer/client, company isolation, corruption, rollback, policy/subject
revocation, bootstrap races and worker renewal are covered. Broker supervisor tests are unit tests;
no live RabbitMQ recovery result is claimed. Offline migrations and SQLite constraints pass;
actual MySQL upgrade/downgrade, concurrent first claims/graph locks and query plans remain C15 gates.

## Current actor authorization

For Catalog job chunks, opt the scoped credential into allow_actor_authorization=true.
The default is false. See [permission proof contract and revocation behavior](catalog-actor-authorization.md).
Role-permission mutations publish source barriers even when no projected fact changes.
