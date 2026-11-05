# Company display cache delivery

Approved 1 November 2026: deliver the first Redis-backed company configuration
projection in phases, keep an evidence ledger, and complete two review/fix passes.
The first slice is limited to `GET /v1/companies/{company_id}/display-config`.
Company details, feature/readiness state, product configuration and all financial
admission remain live and outside this change.

Implementation, both reviews and local rollout verification are complete.

## Contract

- [x] Preserve the existing endpoint and response schema.
- [x] Authorize, tenant-scope and resolve current field policy before any cache read.
- [x] Isolate entries by tenant, company, user, company version, user version and
  field-access fingerprint.
- [x] Keep Redis fail-open: unavailable, malformed, oversized or incompatible entries
  use the authoritative database path.
- [x] Use bounded versioned entries with no Redis operation inside a write transaction.
- [x] Keep posting, tax, pricing, stock, permissions and write validation uncached.

## Delivery phases

### Phase 0 — baseline and regression

- [x] Inspect the existing endpoint, user overrides, field projection and mutation versions.
- [x] Record failing regressions before fixing the inherited implementation.
  The original preimplementation output was not retained; review red runs are recorded below.
- [x] Record the current affected-suite baseline.

### Phase 1 — cache mechanism and endpoint

- [x] Add the Identity-owned validated display projection cache.
- [x] Add strict TTL configuration and wire it to the existing shared Redis client.
- [x] Read the cache only after live authorization and field-policy resolution.
- [x] Populate from the existing resolver without changing API output.
- [x] Add bounded non-sensitive cache outcome instrumentation.

### Phase 2 — freshness and failure behavior

- [x] Prove company and user updates select new versioned keys after commit.
- [x] Prove rollback retains the preceding version.
- [x] Prove tenant, company, user and field-policy projections cannot collide.
- [x] Prove Redis outage/corruption/oversize falls back without changing responses.

### Phase 3 — verification and rollout documentation

- [x] Run affected Identity tests, Ruff and strict mypy.
- [x] Run OpenAPI/generated-client checks; record whether the unchanged contract needs regeneration.
- [x] Run a real Redis integration check with disposable keys and no database flush.
- [x] Document configuration, lifecycle, metrics and safe rollback/disable behavior.
- [x] Restart Identity and verify real OIDC sign-in, live display reads and the native Redis value.

## Reviews

- [x] Review 1: simplification, query value, failure behavior and test gaps; fix findings.
- [x] Review 2: security/correctness invariants, tenant/user/policy isolation and operational safety;
  fix findings.
- [x] Record final evidence, known limits and unchanged unrelated workspace files.

## Evidence

Verification date: 1 November 2026. Evidence files are ignored local artifacts.

| Check | Result | Evidence |
|---|---|---|
| Inherited cache/configuration/reference/authz baseline | 58 passed, zero skips; Redis integration enabled | `.test_artifacts/company-display-cache-baseline.xml` |
| Review regressions before fixes | Encoding, deep JSON, escaped surrogate and stale preloaded source rows failed | `.test_artifacts/company-display-cache-source-red.xml` |
| Cache-hit source query regression | Failed because step-up admission still hydrated the full company | Recorded command output; final affected run supersedes the initial failure |
| Schema-valid corruption reintroducing a denied field | Failed before live output masking | `.test_artifacts/company-display-cache-policy-red.xml` |
| Final affected Identity suite | 262 passed, zero skips; six real Redis cases included | `.test_artifacts/company-display-cache-affected-final.xml` |
| New cache statement/branch coverage | 100%, above the 90% floor | `.test_artifacts/company-display-cache-coverage.xml` |
| Ruff and strict mypy | Passed for changed sources; both changed test files lint clean | Local command output |
| Identity OpenAPI and generated Identity client | Both freshness checks passed; regeneration unnecessary | `tools/export_openapi.py --check`, `node scripts/generate.mjs --check --service=identity` |
| Native configured MySQL + Redis handler smoke | Matching source/cached responses and a real hit; Redis TTL 300; zero application-row writes | `.test_artifacts/company-display-cache-live-native.json` |
| Live OIDC browser/API/Redis verification | Real sign-in passed; two identical authenticated HTTP responses matched the native DB and Redis projection; unauthenticated HTTP 401; observed TTL 168 within 300 | `.test_artifacts/company-display-cache-live.json` |

The final suite includes cache behavior, company CRUD/configuration, field policies,
company master roles, step-up, session/clerk/default selection, reference/authz caches,
report display context and local-auth settings. It uses isolated SQLite databases for
API/ORM cases and the existing native Redis for six cache integration cases. This is
affected-suite evidence, not a full Identity-suite or native MySQL concurrency claim.

Review 1 fixed invalid-byte decoding, deeply nested JSON, escaped Unicode surrogates,
and stale company/user ORM identities populating newly versioned keys. Field adapters
are built once rather than on each hit. SQL capture proved cache hits use a narrow
source-version query; step-up checks now read only the live flag. Ten existing step-up
fixture failures were caused by their old full-row stub; their scalar-query adapters
were updated without weakening assertions, and the final suite passes all boundaries.

Review 2 walked CLAUDE.md sections 5 and 6. It fixed the reintroduction of denied fields
by schema-valid corrupted entries: conditional policy columns are read live, denies
are computed before the cache lookup, and the result is masked again. Regression
coverage includes conditional denies after company changes, distinct users/companies,
cross-tenant invisibility, missing records, 401/403/422, warmed-cache authority refusal,
rollback, source updates and Redis failure. No unresolved cache security/correctness
finding remains. `/simplify` and `/security-review` are unavailable in this environment;
both review passes used their manual equivalents.

`TEST_IDENTITY_REDIS_URL` was configured in the Windows user environment from the
existing ignored Identity environment file after a successful PING. Only disposable
test keys were removed. Identity was restarted through the existing ownership-checked
launcher; no migration, dependency or generated contract changed. Application data,
credentials, financial admission and unrelated purchase/role/UI edits were preserved.
The user-supplied database connection was verified and written only to the ignored
Identity environment file; Identity was restarted after that setting change.

Live browser verification used the supplied account with credentials only in the
test process environment. It exercised the real local provider/OIDC flow and the
running Identity API. The Redis value was checked using the actual authenticated
tenant/user/company, live field-policy fingerprint and configured MySQL source versions.
An intermediate runner submitted before the sign-in form was hydrated; it was fixed
to wait for React's submit handler. Those timeouts did not establish invalid credentials.
The earlier retained QA tenant was absent from the configured database. A Windows
stdin encoding mismatch in the Redis-check helper was corrected with Python UTF-8
mode; the final comparison includes the actual rupee symbol. Final live evidence
supersedes these harness attempts, and no passwords or tokens were saved to artifacts.
