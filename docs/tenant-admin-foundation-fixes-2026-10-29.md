# Tenant administrator fixes: steps 1-3

The user authorized steps 1-3 together after the acceptance findings, with steps
4-6 reserved for the next batch. This batch stabilizes the testing/authentication
foundation, handles session/service failures and repairs audit pagination and
company-selection refusal. The original acceptance CSVs remain historical;
[the batch CSV](tenant-admin-fixes-1-3-results-2026-10-29.csv) records these fixes
separately. [The TODO](tenant-admin-fixes-todo.md) tracks both batches.

## Implemented behavior

1. **Testing and authentication foundation.** The managed Authentik tunnel now
   supervises its pinned SSH child and reconnects with bounded backoff after a
   disconnect or launch failure. Explicit stop cleans up only owned processes;
   foreign listeners are preserved. Existing host-key, TLS, token expiry and
   provider authentication checks remain enabled. Auth refresh production code
   did not change; its existing expiry/concurrency tests and live ordinary
   concurrent refresh were verified.
   Four stale QA failures were repaired in test setup/expectations: Reports now
   checks the implemented 38 definitions and six AccountSummary parameters;
   Catalog independently discovers actual ORM mappers instead of maintaining an
   incomplete model list; Accounting rollback tests start with the initialized
   chart and exercise an actual new installation and a denied legacy-version
   transition. The Accounting regression verifies all existing rows and the
   template version survive the refused transaction. No production business
   contract was changed to accommodate these stale tests.
2. **Session/service recovery.** Console session reads reject refused responses,
   invalid JSON and malformed facts before rendering authenticated context.
   Selected-company display reads validate precision, required formatting values
   and supported rounding/grouping/currency conventions. Failure redirects to a
   public recovery page that reads no private session data, provides local retry
   and sign-in actions and returns an uncached 503 or 403. Existing login,
   expired-session and company step-up redirects remain intact. Retry paths reject
   external, encoded unsafe and recursive recovery/API destinations.
3. **Audit pagination and company refusal.** Audit/activity cursors now bind a
   SHA-256 digest of the complete canonical actor/query context instead of
   embedding the large grants/policies payload. HMAC signing, expiry, size limit
   and per-request authorization remain in the shared codec. Effective/real user,
   tenant, impersonation, restricted audit scope, grants, policies, query and
   surface remain bound. The company-context BFF recognizes Identity's explicit
   withheld-company contract and returns 403 `company_unavailable`; both selection
   cookies remain unchanged. Malformed/mismatched upstream responses still fail
   verification. The Identity resolver and API response schemas did not change.

## Regression and execution evidence

The original broad-admin cursor regression failed on cursor size, the new company
refusal case reproduced the original 502, and ten session recovery cases failed
before the implementation. Review then reproduced two encoded reserved-path
failures and six invalid-formatting failures before correcting those cases.

| Check | Final result | Scope |
|---|---|---|
| Audit full suite | 205 passed; 13 skipped | Includes 11 cursor-binding and two broad-admin surface regressions |
| Console affected suite | 89 passed across eight files | Session, recovery, display, authority, middleware, company context and server fetch |
| Auth component suite | 159 passed | Existing UI/session authentication regressions |
| Auth server suite | 103 passed; one skipped | Refresh coordination, expiry, origin and authentication handlers |
| Reports framework tests | 4 passed | Updated definition/parameter expectations |
| Catalog field registry tests | 2 passed | Actual native-model validation and startup drift failure |
| Accounting completion security tests | 4 passed | Actual changed-field refusal and rollback |
| Windows tunnel/startup tests | 9 passed | Reconnect, launch failure, explicit stop, foreign listeners and reuse |
| Ruff, Audit mypy, Console TypeScript | Passed | Changed Python files; Audit listing module; Console type check |
| Focused retained-tenant live run | 12 checks | Provider UI login, three-company audit/activity pagination, replay/refusal, recovery UI and ordinary concurrent refresh |
| Live tunnel replacement | Passed | Owned SSH child replaced; supervisor preserved; both ports ready |

Audit skips need a reachable Docker/MySQL testcontainer runtime or the opt-in
live RabbitMQ integration prerequisites. Auth's skipped actual Redis-backed
concurrent-handler case requires `TEST_AUTH_REDIS_URL`; deterministic coordinator
tests did execute. These are explicit verification gaps. The live API run uses
the ordinary running services and does not replace native container tests.
The live refresh requests used valid tokens; a naturally expired-token exchange
was not repeated against the provider. VM reboot and laptop suspend/resume were
not exercised. Full unrelated Console/Catalog suites were not rerun; remaining
step-4 candidates and original acceptance gaps are not declared fixed.

## Reuse

From the repository root, run the existing credential-safe UI harness:

```powershell
node docs/testing/tenant-admin/verify-foundation.cjs
```

The harness reuses the retained active tenant and three company profiles. Provider
credentials remain DPAPI-encrypted in ignored evidence. It uses ordinary UI/API
paths and changes only test-browser company selection. Results are written to
`.test_artifacts/tenant-admin-20261029/live/foundation-fixes-results.json`.
Live tunnel evidence is in
`.test_artifacts/tenant-admin-fixes-batch1/tunnel-reconnect.json`.

Backend commands, from each named service directory:

```powershell
# apis/audit
uv run --no-sync pytest -q
uv run --no-sync ruff check src/audit/api/listing.py tests/test_cursor_binding.py tests/test_read_boundaries.py
uv run --no-sync mypy src/audit/api/listing.py
# apis/reports
uv run --no-sync pytest -q tests/test_framework_api.py
# apis/catalog
uv run --no-sync pytest -q tests/test_field_registry.py
# apis/accounting
uv run --no-sync pytest -q tests/test_completion_review_security.py
```

From `mfes/apps/console`:

```powershell
pnpm.cmd exec vitest run tests/session-selection.test.ts tests/session-display.test.ts tests/session-authority.test.ts tests/identity-session.test.ts tests/middleware.test.ts tests/company-context-route.test.ts tests/session-unavailable.test.tsx tests/session-recovery.test.ts
pnpm.cmd exec tsc --noEmit
```

From `mfes/apps/auth`:

```powershell
pnpm.cmd exec vitest run
pnpm.cmd exec vitest run --config vitest.server.config.ts
```

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Pester -Script @('start/win/tests/tunnel-supervision.Tests.ps1','start/win/tests/start-all.Tests.ps1') -EnableExit"
```

## Simplification and security review

Walked CLAUDE.md sections 5 and 6. The named `/simplify` and `/security-review`
commands are unavailable in this session; equivalent manual source and regression
review was performed, rather than claiming the commands ran. Simplification uses
the existing signed codec, central display formatter, shared UI components and
managed process lifecycle; no dependency or duplicate auth mechanism was added.
Review found the encoded retry-path and invalid formatting issues above; both
were fixed and covered with regressions. No remaining issue was identified in
the changed paths within this review's scope.

Cursor digests authorize no data: current route grants and tenant/company scope
are still checked for each page. Recovery renders no partial authenticated state
or guessed money configuration. The BFF refuses the selected company before
changing either cookie. SSH uses pinned keys and localhost bindings; cleanup
targets owned processes and sanitizes launch failures. Reports/Catalog test
maintenance does not weaken field authorization; Accounting asserts unchanged
state after an actual denied write. No model, migration, permission catalogue,
shared library or generated API schema changed. Money posting, idempotency,
outbox emission and immutable historical data were unaffected.

Deployment note: pre-change audit cursors return 422 after the new binding
revision; reload the first page. This is a deliberate bounded cursor transition,
not a relaxation of validation. Services/tunnel were restarted locally for live
verification. No direct application database manipulation, financial release
activation, unrelated staging, commit or publication was performed.
