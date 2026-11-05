# Company display projection cache

Identity caches the resolved response of
`GET /v1/companies/{company_id}/display-config`. The projection contains only the
existing money/date presentation fields. Company details, features, readiness,
product configuration and every financial or write-time decision remain live.

## Safety boundary

The endpoint performs authentication, tenant scoping, company-object authorization,
current-user validation and live company field-policy resolution before reading Redis.
The cache key binds the tenant, company, user, company `updated_at`, user `updated_at`
and the resolved field-access fingerprint. It is hashed to a fixed-size opaque key.
Consequently:

- one tenant, company or user's value cannot be returned to another;
- a committed company or user preference change selects a new key immediately;
- a changed role assignment, group membership or field policy selects a new access
  fingerprint before the cache is read;
- a rollback retains the preceding source versions and projection;
- field-denied values remain absent from responses, including when an otherwise
  schema-valid Redis entry has been corrupted to include a denied field.

A hit still performs live authorization, field-policy resolution and one narrow query
for the company/user source versions and any company columns required by conditional
field policies. Denies are evaluated before Redis is read and applied again to the
returned projection. Step-up admission reads the live flag without hydrating the full
company. A miss reads company/user sources in one statement with `populate_existing`
so previously loaded ORM identities cannot publish stale values under a fresh key.
OIDC authentication independently retains its live user/tenant reads. This is a read
optimization, never an authorization cache.

## Configuration and lifecycle

The existing `IDENTITY_REDIS_URL` enables the shared Redis client.
`IDENTITY_COMPANY_DISPLAY_CACHE_TTL_SECONDS` defaults to `300`, accepts `0` through
`3600`, and disables only this projection when set to `0`. Restart Identity after a
setting change. No new Redis installation, worker, migration or dependency is needed.

The database-specific namespace is `identity:company-display:<fingerprint>`. Entries
are limited to 16 KiB and validated field-by-field against `DisplayConfig`. Old
versioned keys expire normally; operators must not flush shared Redis because it also
contains authorization, step-up, refresh coordination and reference-choice state.

Redis unavailability, timeouts, invalid UTF-8, malformed/deeply nested JSON, unpaired
Unicode surrogates, unknown fields, invalid types and oversized entries fall back to
the authoritative database resolution. Cache failures
do not change an endpoint response or block work. A failed read skips cache population
for that request, avoiding a second backend timeout. The adapter maintains process-local
bounded counters named `hit`, `miss`, `fill` and `fallback`, and emits the same outcome
at debug level without tenant, company, user, key or connection values.

## Explicit exclusions

The cache is not read by posting, tax, pricing, stock, permission, feature admission,
configuration writes, exports or reports. It stores no password, token, contact data,
bank information, tax identifier or arbitrary company/custom field. The HTTP response
and generated client contract are unchanged.

## Rollout and rollback

Deploy with Redis configured and inspect hit/fallback counters and endpoint/database
latency. If the projection does not reduce source-row reads or Redis becomes unhealthy,
set its TTL to `0` and restart Identity; the original database path is then used. Redis
contents need no cleanup. Expansion to other company or product configuration requires
separate measurements, contracts and approval.

Before restoring an older Identity database, disable this projection and restart the
service. Re-enable it only after the former maximum TTL has elapsed; restored rows can
legitimately reuse an older `updated_at`, so their pre-restore versioned keys must expire.

Verification and the two review passes are recorded in
[the delivery checklist](company-display-cache-todo.md).

## Local integration tests

`TEST_IDENTITY_REDIS_URL` is saved in the Windows user environment using this
workspace's existing `IDENTITY_REDIS_URL`. It is a test-process setting, not an
Identity runtime setting. New terminals inherit it; an already-open terminal can
load it explicitly. From `apis/identity`:

```powershell
$env:TEST_IDENTITY_REDIS_URL = [Environment]::GetEnvironmentVariable('TEST_IDENTITY_REDIS_URL', 'User')
.venv/Scripts/python.exe -m pytest tests/test_company_display_cache.py -q -ra
```

The tests use random `test:company-display:<uuid>` namespaces and delete only their
own keys in `finally` blocks. They verify real Redis hits, TTL expiry and corrupt-byte,
JSON, surrogate and oversized-value fallback without stopping or flushing Redis.
Other machines must configure their own reachable test Redis URL; no credentials
belong in this document or tracked files.
