# Redis reference choices

Identity caches bounded global dropdown projections for registration, workspace
setup, platform tenant forms, reference forms and company setup. This includes
countries, states, currencies, languages and timezones. Existing API responses
and UI bindings are unchanged. Redis contains codes, names and presentation
metadata only; the database remains authoritative.

## Configuration and lifecycle

The existing `IDENTITY_REDIS_URL` enables this cache using Identity's shared
Redis client. `IDENTITY_REFERENCE_CACHE_TTL_SECONDS` defaults to 300; allowed
values are 0 through 3600 seconds. Set 0 to disable reference caching without
disabling permission caching or step-up proofs. The local setting is in the
ignored `start/win/env/identity.env`. Restart Identity after changing it.

Use the existing API launchers (`start/win/start-all.bat` and
`start/win/stop-all.bat`) and Redis lifecycle scripts. No extra cache worker or
new Redis installation is needed. Reference-sync workers keep their existing
start/stop/status scripts. Never flush the shared Redis instance to refresh
dropdowns: it also serves authentication mechanisms.

For a fresh installation use `python -m identity.install` with the intended
`IDENTITY_DATABASE_URL`; it migrates and seeds the initial generation. Existing
installations must upgrade Identity to 0080 and seed the initial generation
before enabling the cache. The canonical `python -m seeds.reference identity`
entry point also registers transactional invalidation. Always run deployment
seeds with the intended service environment and after migrations.

## Freshness and failure behavior

One indexed database lookup reads the global generation before a cache hit.
The namespace is `identity:references:<database fingerprint>`; keys contain
schema version, projection, optional country and the committed UUID generation.
Redis values are limited to 2,000,000 UTF-8 bytes and validated against the
projection schema and catalog row limits. Old generations expire normally.

Country/state/currency/language/timezone changes, provenance changes and service
acknowledgements rotate the generation inside the source database transaction.
Rollback preserves the previous cache. A generation recheck after loading
prevents a concurrent READ COMMITTED edit from publishing mixed cached data.
No Redis operation participates in a reference write transaction.

Redis outages, invalid encoding, corrupt JSON, oversized data and incompatible
schemas fall back to the existing database loaders. Disabled/unconfigured cache
also uses the database. Cached data never bypasses current user status, tenant
scope, permissions, setup-key checks or company-country validation. Custom
references still wait for both Catalog and Accounting acknowledgements.

Administration list/detail responses, accounts, tenants, balances, transactions
and write-time reference checks remain live. Existing auth caching/proofs keep
their separate namespaces and policies.

Direct SQL edits or restoration of a database are outside ORM invalidation.
Such maintenance must replace the global generation token with a new UUIDv7
in the same transaction as reference changes. A database restore must rotate
the token before reopening traffic, preventing reuse of pre-restore keys.
Never remove the global generation row to refresh the cache.

## Verification (2026-10-21)

- Affected API regression suite: 739 passed, 3 MySQL-container checks skipped.
- Full Identity suite: 1,603 passed, 11 skipped. The additional seed change/no-op
  regression added during final review also passed separately.
- Shared cache/session/reference regression suite: 34 passed.
- New reference-cache tests cover hits, rollback, edits/archive, acknowledgements,
  disabled caching, strict environment configuration, outage/corruption/encoding,
  country key isolation, bounded TTL and live account revocation.
- Native local MySQL and real Redis: 0080 upgrade/downgrade/upgrade, cache hit
  using one revision query, TTL expiry, concurrent committed edit, rollback and
  unavailable Redis fallback passed. Only disposable test keys/schema were removed.
- Live Identity migrated to 0080 with existing reference/account counts unchanged.
  The API and Auth `/api/registration` returned the same 239 countries and 5,027
  states; the real Redis entry had the configured 300-second TTL.
- Identity restarted successfully. All seven APIs, MySQL, Redis, RabbitMQ,
  nginx, both web apps and both reference-sync workers were checked running.
- Strict mypy, Ruff, migration-shape checks, OpenAPI/generated Identity-client
  checks and all shared-library consumer lockfile checks passed.

Manual simplicity and security review covered CLAUDE.md sections 5 and 6. The
`/simplify` and `/security-review` commands are unavailable in this environment.
Review found and fixed environment-string TTL handling and legacy seed policy
registration; no unresolved cache authorization or tenant-isolation finding.
Native evidence uses this computer's MySQL installation; container-based MySQL
9.6 checks require the repository's configured container runtime.
