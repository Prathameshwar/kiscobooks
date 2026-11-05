# Login/API remediation — 2026-10-20

The user approved all three phases on 2026-10-20:

1. Fix Identity's original-authentication revocation boundary and Auth logout/refresh,
   with security regression tests.
2. Fix Console session recovery, selected-company proof handling and recoverable
   authentication errors, with regression tests.
3. Run integration/regression checks, review the final changes against CLAUDE.md
   sections 5–6, and update operating instructions and the review findings.

Keep Authentik, NextAuth, Identity and existing Redis infrastructure. Redis 6.3.0
is pinned as an Auth dependency to coordinate rotating refresh credentials across
instances; cached token results must be encrypted and short-lived. No schema or
datastore change is planned. Preserve unrelated local edits and project paths.

All three phases are complete locally. No production deployment or publishing was requested.

## Changes and regression evidence

| Original finding | Completed behavior |
|---|---|
| 1. Console logout only navigated | Auth confirmation invokes NextAuth CSRF-protected POST; the actual handler clears the shared session and selected-company/proof cookies and invokes Identity/provider revocation. GET does not revoke anything. |
| 2. Refresh bypassed revocation | Identity rejects missing/old original `auth_time` and old `iat` after the cutoff. Signed-token ASGI tests cover self/admin revocation, refreshed credentials and fresh authentication. |
| 3. Open pages could not refresh | Shared Console fetch recovers local preflight expiry once. Validated idempotency keys and unchanged request bodies survive financial retry; unkeyed mutations require manual retry. Read downloads also recover; page/download return paths survive navigation. |
| 4. Rotating refresh raced | Redis ownership locks coordinate independent callers. HMAC keys and AES-256-GCM result encryption prevent plaintext credentials in the store. Native Redis plus eight actual NextAuth requests performs one provider grant and produces equivalent successful cookies. |
| 5. Step-up lost selected company | Completion sets HttpOnly selection/proof cookies. Console validates the UUID hint and forwards only the selected company's proof. Identity authorizes it again. Signed challenge/completion/session tests and actual encrypted-cookie Console tests cover the boundaries. |
| 6. Callback errors disappeared | Login maps query errors to generic messages and permits retry, with strict Console return destinations. Real NextAuth error redirects are tested. Revocation/logout requests fresh provider login rather than reusing old SSO authentication. |
| 7. Dependency errors escaped | Invitation outages return sanitized, bounded 503 responses. Auth handles invalid configuration, including `/refresh`. Console has a tested retry/sign-in error boundary; server-render failures still return HTTP 500 before client hydration. |
| 8. Invalid token responses looked successful | Initial and refreshed credentials must be nonempty, whitespace-free and bounded; expiry must be finite and within 30–900 seconds. Invalid refreshed credentials fail closed. |

Also fixed local nginx's missing Identity rate limit and stripping of caller-supplied
actor/signature/original-URI headers. The deployed local template passes `nginx -t`.

## Verification

| Check | Result |
|---|---|
| Auth UI/API tests | 84 passed |
| Node coordinator/real NextAuth/Console-cookie tests | 12 passed with native Redis enabled; normal runs skip the one native Redis test |
| Console suite | 417 passed |
| Identity login/session/invitation/step-up/security suites | 50 passed |
| Shared OIDC suite | 16 passed |
| Full non-MySQL Identity suite | 1,398 passed, 1 skipped, one pre-existing OpenAPI test failed because it accidentally included Reports authority in Catalog source endpoints. Narrowed that test to its actual two Catalog namespaces; its focused rerun passed. The full suite was not rerun after this test-only correction. |
| TypeScript checks / production builds | Both apps and shared UI typechecked; Auth and Console production builds passed |
| Python checks | Ruff passed on changed Python files; strict mypy passed on Identity authentication |
| Windows launcher regression suite / nginx syntax | 19 passed / successful |
| Local HTTP smoke | Auth login/logout 200; missing auth configuration yields sanitized Auth 503; Console 500 includes the recovery error boundary and omits the former raw configuration error |

Initial production builds overlapped a launcher smoke run and failed while collecting
page data. Stopped the managed development servers, reran builds successfully, then
performed the separate launcher smoke. Test-started UI and Redis processes were stopped;
Redis needed the launcher's bounded managed-process fallback. No unrelated processes
or database services were stopped.

## Final manual review and limits

Walked CLAUDE.md sections 5–6 and manually reviewed simplification, auth/CSRF, cookies,
tenant/company scope, sensitive output, retry identity, revocation and audit boundaries.
No remaining defect from the eight original findings was found in the final changes.
The additional review findings (fresh SSO login after revocation, invalid retry keys,
missing `/refresh` configuration handling and local nginx headers/limits) were fixed
and regression-tested. No API schema/model, migration, shared library or money/audit
transaction mechanism changed. The old broad Catalog OpenAPI assertion was narrowed
without changing any endpoint or its authentication contract.

`/simplify` and `/security-review` are unavailable in this environment; the manual
review is the fallback and does not claim those commands ran.

Live Authentik browser login remains unverified: local provider settings and app
environment files are absent, and the previously observed local MySQL credential
failure prevents a fully configured API login. Verify exact callback registration,
RS256 audience/scope/lifetime, original `auth_time` semantics, controlled cross-app
cookie domains, provider errors, refresh rotation/parallel tabs, protected-company
access, logout and fresh reauthentication against the real provider. The new browser
refresh endpoint accepts only configured Auth/Console origins and returns no tokens.
Remote logout revocation remains best effort during API/provider outages; local cookie
deletion is verified. Previously issued gateway contexts retain their existing TTL.

Decision record: 2026-10-20 — preserve local project layout and the authentication
architecture; enforce the original-authentication cutoff, coordinate refresh through
existing Redis, preserve financial retry identities and expose recoverable UI errors.
Operating configuration is updated in `mfes/README.md` and Identity gap operations.

Decision record: 2026-10-23 — explain provider startup failures (`OAuthSignin`) as an
unavailable sign-in service, with retry and administrator guidance. Describe known
`Configuration` failures explicitly. Preserve sanitized fallbacks for unknown codes,
existing redirect restrictions and fresh-authentication requirements. Login regressions
verify the outage message, retry behavior and configuration guidance. Manual security
and simplification review found no additional issue; authentication enforcement is unchanged.
