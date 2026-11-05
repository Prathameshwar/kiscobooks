# Login and API integration review — 2026-10-19

Remediation update, 2026-10-20: all eight findings below were addressed under the user-approved three-phase plan. This document retains the original evidence; see [final changes, verification and limitations](login-api-fixes-2026-10-20.md) for current status. A real configured Authentik browser flow remains an external gate.

Scope: Auth UI, NextAuth callbacks/session refresh, Console session and API adapters, Identity bearer validation/current session/revocation, invitation acceptance and company step-up. Review only; application code was not changed. Existing launcher and unrelated Notification edits were preserved.

## Assessment

The intended authentication architecture exists, but login/logout integration is not ready for acceptance. Two high-priority defects concern logout and session revocation. Further defects affect expired-session recovery, concurrent refresh, company verification and error handling. A real Authentik deployment is still an outstanding verification gate.

Login is provider-based: `/login` calls NextAuth's Authentik sign-in, the provider callback creates an encrypted HttpOnly session cookie, and Console decodes that cookie server-side to send an access token to Identity `/v1/session`. Identity verifies the provider JWT, resolves the active local subject/tenant, and obtains current grants. The UI does not send a password to an Identity login API. Signup and recovery delegate to the provider flow; invitations activate the local user separately.

## Findings, ordered by priority

1. **P1 — Console Sign out leaves the authenticated session active.** `mfes/apps/console/app/components/ConsoleShell.tsx:156` only calls `goTo(signInUrl())`. It does not call NextAuth sign-out, clear the encrypted cookie, or invoke the revocation event in `mfes/apps/auth/app/lib/auth-options.ts:84`. Returning to Console can therefore continue the same session. The existing shell test explicitly expects this navigation, so the passing suite preserves the defect. Route logout through Auth and perform NextAuth's CSRF-protected sign-out before navigating; verify cookie deletion and API denial from the old session. Do not turn a GET link into a state-changing logout endpoint.

2. **P1 — Revoke sessions does not invalidate the old provider login after refresh.** `apis/identity/src/identity/api/auth.py:218` compares `claims.iat` with `tokens_valid_after_at`. Refresh creates a newer access-token issue time while retaining the original authentication/session. A signed-token reproduction returned 200 for the initial session, 204 for revocation, 401 for the original token, then 200 for a refreshed token carrying the old `auth_time`. Administrative revocation has no provider-refresh revocation integration. Enforce a durable login/session revocation boundary, using a required verified original authentication time or a provider session identity according to the chosen contract; a missing claim must not bypass the check. Verify both administrative and self-revocation across refresh and fresh reauthentication. This is a semantic defect demonstrated with signed test tokens; live Authentik refresh issuance was not exercised.

3. **P2 — Client API calls cannot recover an expired access token.** `mfes/apps/console/app/api/product-fields/route.ts:13` and `app/api/report-download/route.ts:23` return 401 near expiry; the Audit adapter also returns authentication-required. Console has no NextAuth session polling or shared client refresh/retry flow. Server page loads redirect through `/refresh`, but an already open business page continues retrying with the old cookie. With Identity's default five-minute access-token limit, ordinary long sessions repeatedly stop working until a reload or explicit sign-in. Add a shared recovery flow that preserves the current URL and action state; retry mutations only with their existing idempotency key.

4. **P2 — Parallel refreshes race when refresh tokens rotate.** `mfes/apps/auth/app/lib/auth-options.ts:42` independently exchanges the same refresh credential for every expired-cookie request. There is no coordination or reuse of an in-flight result. A parallel callback reproduction issued two grants: one returned the rotated token, the other cleared access and retained the old refresh credential after `invalid_grant`. A later failure response can overwrite the successful cookie. Coordinate refresh for the same session/credential across deployed Auth instances and test concurrent requests and response ordering. Runtime occurrence depends on the provider's rotation/reuse policy; no live policy was assumed.

5. **P2 — Completed step-up does not restore a protected default company in Console.** `mfes/apps/console/app/session.ts:17` always calls `/v1/session` without company selection. `app/identity-session.ts:23` only forwards a proof when a company appears in the path or query. Identity intentionally omits a protected default company without its proof. A reproduction confirmed that after successful challenge completion, `/v1/session` returns `company: null` without the proof and the selected company with it. Console bootstrap therefore discards the browser's existing verification and company-scoped permissions, even after the step-up screen returns to Console. Carry validated selected-company context through bootstrap and forward only that company's proof; test the complete challenge → callback → session → page flow.

6. **P2 — Provider/callback errors are hidden on the login page.** NextAuth is configured with `pages.error='/login'`, but `mfes/apps/auth/app/login/page.tsx:11` only renders locally caught exceptions. It never reads or maps the NextAuth `error` query parameter. Provider denial, OAuth callback/state failure or server configuration errors return to a normal-looking login screen. Show an allowlisted, generic explanation and a retry state without displaying raw provider messages or query values. Test error redirects using the real auth handler, not only a mocked `signIn` promise.

7. **P2 — Identity outages escape the authentication API and session rendering.** `mfes/apps/auth/app/api/invitations/accept/route.ts:15` leaves its outbound fetch uncaught, producing an unhandled server error instead of the documented retryable failure response. This was reproduced by rejecting the Identity fetch. Console `app/session.ts:18` similarly throws on non-OK bootstrap and display-config responses, and there is no app error boundary for recovery. Map unavailable dependencies to bounded, sanitized 503 responses and provide recoverable page states for 403/503. Preserve redirect semantics and do not expose exception details. This includes the already observed Console 500 when local authentication configuration is absent.

8. **P3 — Refresh success accepts an empty access token.** `mfes/apps/auth/app/lib/auth-options.ts:61` checks only the token's type and positive lifetime. A reproduction with `{access_token:'', expires_in:300}` returned `refreshError:false`, and the session response remains apparently valid even though Identity will reject the bearer. Require a nonempty bounded access token and finite bounded expiry metadata; validate the initial account fields as well. This fails at the API boundary rather than granting unauthorized access.

## What was verified working

- Access/refresh tokens are omitted from the public NextAuth session JSON and retained in encrypted HttpOnly cookies. HTTPS shared cookies use Secure and SameSite=Lax.
- Actual encrypted cookies, including numbered chunks, decode on Console. The local HTTP cookie name also decodes when explicitly selected.
- The real NextAuth session handler in `/refresh` rotates a valid cookie, forwards Set-Cookie on its redirect, restricts the return URL to the configured Console origin and redirects to login when refresh fails.
- Auth config enables PKCE, state and nonce checks. Identity independently enforces RS256/JWKS, issuer, audience/authorized party, scope and bounded token lifetime. Provider key failures fail closed with bounded retry behavior.
- OIDC mode ignores externally supplied signed actor fixtures. Active local user/tenant resolution and current grant checks are exercised, including wrong-tenant denial, suspended users and permission revocation.
- Invitation acceptance requires provider-verified matching email and correct tenant, activates once and rejects replay. Step-up requires fresh provider authentication, one-use challenges, actor/company binding and a committed audit receipt.

These checks establish the reviewed unit/ASGI contracts. They do not certify a deployed browser-to-provider flow or all financial workflows.

## Test evidence

| Check | Result |
|---|---|
| `pnpm.cmd test:auth` in `mfes` | 52 tests passed, 9 files |
| `pnpm.cmd test:console` in `mfes` | 393 tests passed, 34 files |
| `pnpm.cmd typecheck` in `mfes` | Shared UI, Auth and Console passed |
| Identity login/session/auth bounds/invitation/step-up suites | 44 tests passed |
| Shared OIDC suite through Identity's existing uv environment | 16 tests passed |
| Temporary deep-review probes | 8 passed: 2 signed-token/ASGI probes, 3 auth callback/API probes, 2 real NextAuth refresh-handler probes, 1 real cookie/Console probe |

The reproduction probes deliberately passed when they demonstrated the reported defects; they are evidence, not fixed regression tests. Initial real-handler probes needed Node environment and Next request AsyncLocalStorage setup; those harness failures were corrected before the final passing runs. Temporary probes/configuration files were removed after review. No database migration, provider setup, secret generation or deployment was performed.

## Local integration prerequisites and limits

No Auth/Console `.env.local` files and no populated local `IDENTITY_OIDC` setting were found. Identity's generated database connection was previously rejected by MySQL (1045). Consequently, a genuine Authentik → callback → Identity → Console browser login was not available to test. The outstanding live-provider gate is already recorded in `docs/identity-gap-todo.md:27`.

Configure the trusted HTTPS issuer, per-client audience, RS256 signing keys, `billing.api` scope, suitable access-token lifetime, exact callback URL and active local subject binding. Auth and Console need the same session secret and compatible cookie settings. Sibling HTTPS hosts require a controlled shared parent domain. The documented issuer/audience/lifetime values must agree with Identity, not just with NextAuth. The direct Identity base must support `/v1/...`; the local nginx Identity namespace instead uses `/identity/v1/...` and is not interchangeable with the direct base in adapters using `new URL('/v1/...', origin)`.

Local nginx's `/identity/` path forwards incoming actor headers and lacks the production example's Identity auth rate limit/stripping. With `IDENTITY_OIDC` configured, Identity ignores those headers; in the legacy fallback mode the path depends on trusted signed gateway contexts. Local launcher success is therefore not evidence that the production ingress/security configuration is installed.

After remediation, verify real provider cancellation/error, callback tampering, cross-app cookies, refresh expiry and parallel tabs, protected-company selection, network outages, sign-out, administrative revocation followed by refresh, and reauthentication. API JWTs must contain the verified session/login identity needed for the revocation contract.

## Review record

Manual simplification and CLAUDE.md §§5–6 security/correctness review completed. The findings above remain open; passing tests do not resolve them. No application authorization, tenant scoping or financial execution behavior was changed. `/simplify` and `/security-review` are not callable in this environment; the manual pass is the fallback and does not claim those commands ran.

Decision record: 2026-10-19 — retain the existing Authentik/NextAuth/Identity architecture and record integration defects for remediation; this review does not authorize a replacement authentication stack or claim live-provider readiness.
