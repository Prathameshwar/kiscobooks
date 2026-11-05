# Local sign-in by username or email

User-authorized change, 2026-10-31. Local files remain at their existing paths.

## Delivery phases

1. Completed: add fail-first regression tests, resolve either identifier to the existing local identity,
   and preserve credential verification, status checks, account lockout and throttling.
2. Completed: update form validation and signup guidance; verify the affected suites, type checking,
   security invariants and the supplied account through the running local installation.

## Contract

The local form accepts username or email in one text field. Both are trimmed and lowercased;
the password is passed through unchanged. `@` selects the email lookup; otherwise the lookup
uses the unique username. Generated administrator usernames work at sign-in but remain reserved
at signup. Unknown identifiers and incorrect passwords give the same generic response.

Internal browser/backend requests use `identifier`. The previous `email` field is still accepted;
simultaneous fields are refused. Internal endpoints are excluded from OpenAPI, so no generated
public client change is required. Existing unique indexes are reused; no migration is required.

Input, client-address and request throttles remain. An additional throttle on the resolved
identity gives both identifiers one account budget. The credential row lock, committed failure
counter, password hashing, pending/disabled checks, PKCE, redirect validation and token issuance
use the existing paths.

## Verification

Fail-first: six backend regression cases and three BFF cases failed against the previous
email-only implementation.

Completed checks:

- Local-provider backend suite: **395 passed**, seven MySQL cases deselected from that run;
  scoped coverage **93.61%** (90% required), domain **100%**, login service **96%**, local-auth
  routes **92%**. The two affected MySQL cases were run separately as described below.
- Auth server suite: **392 passed**, one existing opt-in test skipped. After the control-character
  validation fix, the login BFF's **94 tests** passed again.
- Auth browser-component suite: **309 passed**, three existing opt-in branding cases skipped.
  This includes all **38 sign-in form tests** and the local-provider signup guidance tests.
- Shared browser/BFF identifier normalization: **18 passed**, including generated usernames,
  case/space normalization, oversized input and control characters. The control-character test
  failed first, then passed after the fix.
- Real MySQL 9.6: **2 passed** — complete provider lifecycle with email/username tokens for the
  same subject; concurrent failed guesses alternating between identifiers produce one lockout.
  These ran in a fresh task-specific database on the disposable server at port 13396; the test
  database was removed afterward. Five unrelated MySQL cases were not selected.
- Running local installation: OIDC authorization plus the real Auth BFF returned **200** for
  both `tenant1` and `tenant1@gmail.com` with the privately supplied password.
- Real browser, separate fresh contexts: both identifiers completed sign-in through NextAuth,
  reached Console, returned `tenant1@gmail.com` in the safe session response and retained the
  session after a page reload. Access/refresh tokens were absent from the session JSON.
- Ruff and strict mypy on changed backend files, Auth TypeScript checks and `git diff --check`
  passed. No credentials, tokens or cookie values are recorded in this report or test files.

The passing browser E2E check waits for provider discovery and the authorization-request check
before filling the form. Earlier harness attempts interacted before React hydration and timed
out; adding these readiness checks resolved the harness failures. Initial UI assertions for the
email-only field were updated for a text identifier field, which preserves the entered casing
on screen and normalizes it only on submission. Final UI runs used one worker and a 20-second
test timeout to accommodate the shared machine's load; repository timeout settings were unchanged.

The backend runs emit one non-failing FastAPI/Pydantic `validation_alias` metadata warning.
Canonical `identifier`, legacy `email` and simultaneous-field rejection all pass against the
real routes. Existing opt-in branding/server tests remain skipped as noted above. No full
unrelated-service regression run was needed for this change.

## Simplification and security review

The repository's `/simplify` and `/security-review` commands are not installed in this Codex
session; the corresponding manual review covered CLAUDE.md sections 5 and 6.

- One shared browser/BFF identifier normalizer and one backend domain rule; no duplicated
  credential-verification path or new dependency.
- Parameterized lookup uses one indexed column chosen by identifier shape; both identifiers
  return the same subject and preserve tenant membership.
- Strict request fields, compatibility alias exclusivity, BFF secret, browser origin and size
  checks, account status, constant-cost unknown-account verification, shared throttles/lockout,
  credential row locking, committed failure counts and redirect/PKCE controls reviewed.
- Review found browser email-shaped input could include control characters; sign-in now rejects
  these consistently with the backend, with a regression test. No unresolved findings in scope.
- No schema, permission, audit payload, public API or generated-client changes are required.
