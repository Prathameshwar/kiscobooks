# Redis reference-choice caching plan

Requested 2026-10-21: review Redis usage and implement appropriate, usable caches.

## Review and scope

Identity already uses the shared Redis client for bounded permission caching and
single-use step-up proofs. Auth uses Redis refresh coordination. Those mechanisms
have separate namespaces and security policies. Global reference choices currently
query/hydrate the country/state/currency/language/timezone catalogs repeatedly in
registration, onboarding, platform tenant setup and company setup.

Cache those bounded read-only choice projections, containing global reference
codes/names and presentation metadata only. Keep authorization before every cache
read. Do not cache tenants, account information, financial records, mutable
administration lists/details, or write-time active/dependency/synchronization checks.
Existing permission cache behavior stays separate; catalog writes retain live grants.

## Proposed behavior

- Reuse the existing Redis client and RedisCache, with an Identity/database-specific
  namespace, bounded TTL, bounded payloads and schema validation. No new dependency.
- Add an Identity-owned global reference-cache revision row. Catalog writes,
  consumer acknowledgement progress and installation seeds change its generation
  within their database transaction. The cache key incorporates that committed
  generation, so rollback never invalidates valid data and an older in-flight loader
  cannot populate the key used by newer requests. No Redis call inside a write.
- Reads check the small revision row in the database before a cache lookup. On a
  cache miss, build the existing projection and recheck the revision under READ
  COMMITTED before populating only that revision's key. Expired generations
  disappear via TTL; no Redis scans or global flushes.
- Cache registration country/state choices, tenant regional choices, reference form
  options and company country/state/currency choices. Keep company state parent
  validation live. Cache only successful responses; no cached errors or denial.
- Redis unavailable, corrupt, oversized or incompatible entries fall back to the
  database. Disable caching cleanly if Redis is unconfigured or the TTL is zero.
  Read/cache failures never allow new unsupported or archived references in writes.
- Preserve API response contracts and existing CSS/UI bindings. No new controls.

## Phases

1. **Revision and cache mechanism:** add one-DDL Identity migration/model/factory,
   typed bounded read-through cache and runtime settings; regression tests first
   for hits, misses, outage/corruption and generation races.
2. **Integration and invalidation:** wire existing choice endpoints and transaction
   generation changes for CRUD/ack/seed paths; test authorization, archive/restore,
   pending references, rollback, seed preservation and immediate fresh reads.
3. **Live verification and final review:** migrate the existing local Identity DB,
   verify real Redis hits/TTL/fallback without stopping or flushing shared Redis,
   run affected tests/type/contract checks, review security and simplicity, restart
   Identity and document usage/results. Preserve unrelated work; no publishing.

This changes more than approximately 100 lines and adds a migration. CLAUDE.md
section 2 requires: "write the phases first and get them agreed."

All three phases agreed by the user on 2026-10-21.

All three phases completed. See [reference-cache.md](reference-cache.md) for
configuration, maintenance boundaries and verification. Live Identity is at
0080 with Redis reference caching enabled; the API/UI checks and native MySQL/
Redis verification passed. Full Identity suite: 1,603 passed, 11 skipped;
shared reference/cache/session suite: 34 passed. Manual security and simplicity
review completed because the named slash commands are unavailable here.
