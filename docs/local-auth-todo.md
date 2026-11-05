# Local authentication — delivery checklist

Live checklist for [local-auth](local-auth.md). Phases end with tests green and the repo working.
`AUTH_PROVIDER` defaults to `local` from the first commit of this work; existing Authentik
deployments set `AUTH_PROVIDER=authentik` explicitly.

| # | Item | State |
|---|---|---|
| 0 | Design + contract (`local-auth.md`), this list, decision log entry | done |
| 1 | Settings: `auth_provider`, `LocalAuthSettings`; verifier loopback-HTTP rule (+ tests) | done |
| 2 | Domain (no DB): password policy/hash, tokens, PKCE, lockout, claims (+ unit tests) | done |
| 3 | DB: models + MySQL migrations 0090–0095 (one DDL each), factories, MySQL migration tests | done |
| 4 | Signing keys: generate, encrypt, rotate, JWKS, operator CLI (+ tests) | done |
| 5 | OIDC server: discovery, jwks, authorize, token, revoke, refresh rotation + reuse (+ tests) | done |
| 6 | Auth-app endpoints: login, registrations, recovery inspect/redeem, setup administrator, status | done |
| 7 | `/v1/session/password`, operator recovery link (`/v1/users/{id}/password-recovery`) | done |
| 8 | Provider adapters (account review, administrator provision, recovery) + factory + call sites | done |
| 9 | Audit events, rate limits (in-app + nginx), redaction | done (nginx: existing `/identity/` limit applies; confirmed in review) |
| 10 | Auth app UI/BFF: sign-in, reset, recover, change-password, setup step, signup, provider-aware NextAuth (+ tests) | done |
| 11 | Console: operator "Create recovery link" for users | done |
| 12 | Env/start scripts, nginx, OpenAPI + `clients/api-client` regeneration | done |
| 13 | Docs sync (tech-stack, identity-schema, account-registration, platform-setup README) | done |
| 14 | End-to-end run on MySQL: sign-up → review → sign-in → refresh → change → recover → revoke; first run → setup → platform tenant → new administrator | done (7 MySQL 9.6 tests, each file on a fresh database) |
| 15 | Review: security review, mutation checks, §5/§6 walk, fixes | done — see 15a–15k |
| 15a | Operator recovery link: scope-aware escalation guard, fresh sign-in (≤ 5 min), tests with real tokens | done |
| 15b | Password hashing off the event loop in a bounded thread pool (rule 4.10 deviation recorded) | done |
| 15c | Lockout race: credential row locked while counting; throttle keys fold accents/case | done (MySQL concurrency test passes on real connections) |
| 15d | Throttles: own limiter table; recovery/setup keyed on the end user's address; token/revoke no shared bucket | done |
| 15e | Code issued before a password change is refused; password change voids open recovery links | done |
| 15f | Derived provisioning usernames reserved against public sign-up | done |
| 15g | `X-Client-Address` only from trusted proxies (`AUTH_TRUSTED_PROXY_HOPS`, default 0) | done |
| 15h | API tokens cannot change/guess a password; uncommitted first signing key never cached; absolute session cap | done |
| 15i | Concurrency tests: code, refresh, lockout (MySQL, real connections) | done |
| 15j | Docs: honest enumeration statement, trust model, accepted risks, decision-log deviations | done |
| 15k | Re-run every suite; final mutation pass on the survivors | done (rounds 1–3: every survivor now killed except one equivalent mutant) |
| 16 | Final report for the local provider | done |
| 17 | **Queued by the user:** find every other place the platform uses Authentik or its API and make each work under `AUTH_PROVIDER=local`; then a second authentication review with fixes | done |
| 17a | Identity: setup readiness check names/messages provider-aware; social linking refused under local; neutral provisioning messages; first-run → platform tenant creation → new administrator sign-in proven end to end on MySQL | done |
| 17b | Start scripts: `start-all` skips the Authentik tunnel and the review worker runs for `local` (`Get-BillAuthProvider`, Pester tests); README | done |
| 17c | Docs: provider notes on setup, forgot/change password, tenant management, administrator recovery; org-model/company wording | done |
| 17d | Independent second authentication review of the whole platform (gateway, other services, Identity auth, Auth app/Console sessions) | done — 8 findings, none critical |
| 17e | Fix what 17d found, with tests: hashing capped to half the DB pool; throttle table bounded by slots; link guard counts future-dated grants and refuses platform operators, issuer named on completion; production nginx template routes `/oidc/` and overwrites `X-Forwarded-For`; legacy `IDENTITY_OIDC` with no provider refused; API audience must differ from client ids; first-run administrator creation locked + `reset-setup-administrator`; form body streamed with a limit; Authentik CA only for Authentik; stale doc statements | done |
| 17f | Final full regression, mutation round 3, final report | done (Identity 2455 passed, 2 pre-existing failures) |
| 18 | **Raised by the user:** an installation that ran on Authentik and now points at local — what about the platform administrator and other existing accounts? `adopt-users` (re-points `user.authentik_sub`, updates the recorded setup administrator, ends old sessions, issues a one-time link, audited) + `local-auth-cli.bat` + §9 of the contract | done |
| 19 | **Raised by the user:** home page → "Continue to sign in" answers `{"error":"Authentication unavailable"}`: the Auth app defaulted to `local` with only `AUTHENTIK_*` set. Fixed on this machine by running `local-auth.bat`; needs migrations 0090–0095, a restart and `adopt-users` | deployed 2026-10-31: backup/restore rehearsal, live migrations and restart complete; native operator adoption complete; password form verified |
| 20 | Local `/oidc/authorize` returns 500 because `local_authorization` is absent; Identity readiness previously checks only SELECT 1 | fixed: schema/model constraint names aligned; readiness now requires all owned tables and head 0095; fail-first tests pass; operator chooses its local password through the one-time recovery link |
| 20 | **Raised by the user:** a professional, beautiful sign-in screen that matches the existing styles, colours and layout. Ledger-sheet brand panel, larger card with footer band, taller controls, phone header; tagline kept at the design system's 32px after feedback; decision-log entry; tests pin the decisions | done |
| 21 | **Queued by the user:** check landing → login screen → sign in end to end, in a real browser | done — Chrome against an isolated stack (own database, Identity 8101, Auth 4411, Console 4421): landing → login → sign-in form → validation → wrong password → Console as platform administrator → reload → sign out; recovery link → new password; lockout. 24 of 24 checks, one transient connection reset seen once in ~25 sign-ins |
| 22 | **Requested by the user:** local sign-in by username or email, shared throttle/lockout, matching form/signup guidance | done ? 395 backend tests (93.61% scoped coverage), 327 UI/input tests, 392 Auth server tests, 2 MySQL tests; both supplied identifiers reached Console and survived reload in a real browser. [Evidence](local-auth-username-login.md) |
