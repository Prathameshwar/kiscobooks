# Vouchers authentication and authorization review — 2026-10-13

## Scope and verified controls

Reviewed all 51 public `/v1/` operations in the generated Vouchers contract, the nginx
`/vouchers/` boundary, signed actor/company context verification, company/object lookup,
permission checks, field-policy masking, idempotent writes, artifact access and internal
source/result ingress. Every public operation declares the four signed-context headers.
The gateway clears client-supplied context headers during authorization, replaces them with
Identity-issued values, and returns 404 for browser access to `/vouchers/internal/`.
Internal source/result calls use method/path/query/body-bound service signatures and explicit
tenant/company grants. Object reads use tenant-scoped sessions and company-scoped lookups.

## Fixed finding: incomplete field-policy context was accepted

Vouchers checked signatures and company identity but did not verify that Identity supplied
complete `vouchers` and `accounting` field-policy namespaces. Draft, read and administration
routes could therefore continue with a signed but incomplete context, unlike the posting
boundary. The shared Vouchers access dependency now rejects such a context with 401 before
any business route runs. A regression test first demonstrated 200 for missing/partial
namespaces, then passed for all three denied cases after the fix. The Vouchers test fixture
now models Identity's normal complete context.

## Findings at review time

1. **Counter operations (medium):** counter session opening, cash movement and balanced
   closing use `vouchers.create`; session cash details use `vouchers.read`. Cash movements
   check the opening cashier, and variance closing separately requires `vouchers.approve`,
   but there is no dedicated counter operator/read grant or outlet/counter scope. The
   salesperson/broker/counter plan already lists dedicated operator permissions as pending.
   Add those permissions, role bindings and outlet/counter object checks before wider POS rollout.
2. **Gateway rate limiting (medium):** Vouchers has a per-process 240-write/minute actor
   limiter, while the checked Windows nginx configuration has no `limit_req` or `limit_conn`
   rule. Add a shared gateway limit for write and internal ingress paths and test 429 behavior
   before scaling the service to multiple processes or exposing money mutation.

No cross-tenant, cross-company or unsigned-call bypass was found in the reviewed HTTP paths.

## Remediation completed 2026-10-13

- Counter drawer commands now use dedicated operate/close permissions. An active
  company-and-counter-scoped roster assignment is required to open, move cash, or
  close a balanced shift. Cashier session reads require ownership and an active
  assignment; separate read permission permits audit/supervisor inspection. Independent
  supervise permission, a reason and a different actor are required for variance or
  supervisor closure. Roster mutations use configuration authority and security audit
  events. The status route binds both counter and operator IDs into its idempotency
  identity, so a reused key cannot replay a different user's change. Existing counter
  events were added to the publisher's exact audit allowlist.
- The Windows nginx gateway now has a worker-shared, IP-keyed write limit for
  `/vouchers/`; GET, HEAD and OPTIONS are exempt. Rejections return a JSON 429 and
  `Retry-After`. Signed internal source and execution-result ingress, which bypasses
  the public gateway, has a per-process service/company limiter after HMAC and scope
  verification. The existing actor/company write limiter remains in the service.
- Migration `0076` adds the counter roster. The Vouchers readiness migration head was
  advanced with it, so a successfully migrated service reports ready.
- The final Identity auth-path review found silently swallowed cache-invalidation
  failures. Expected Redis outages now emit a generic warning, and unexpected
  post-commit hook failures log only the exception class. Neither path exposes cache
  keys or connection details, and the committed write still succeeds; cache TTL remains
  the revocation backstop.

The checked workspace does not contain an nginx executable, so live gateway 429
behavior and `nginx -t` must be verified in the deployed Windows environment. The
rate zone is shared across workers in one nginx instance; a multi-gateway deployment
would need a shared edge policy. These deployment checks do not weaken the service's
signed-context, company-scope or in-process write controls.

## Verification

- Vouchers native MySQL verification: 255 passed, 1 skipped; model/index/foreign-key
  parity and full downgrade/upgrade passed. This run also caught and repaired three
  older list-index downgrades that MySQL refused because the indexes supported FKs.
- Vouchers SQLite suite: 254 passed, 2 skipped; later security/audit/ingress assertions
  passed in focused reruns.
- Identity suite: 1,387 passed, 10 skipped; new role-separation test passed separately.
- Identity post-commit regression: 9 passed; full Identity source Ruff and strict mypy
  passed after the logging fix.
- Full Identity source-and-test Ruff passed after correcting three existing
  role-test line wraps; the affected role/cache tests passed (14).
- Shared platform suite: 1,056 passed.
- Ruff on changed Vouchers, Identity and platform files; strict Vouchers mypy over
  66 source files; generated OpenAPI, TypeScript typecheck and client tests passed.
