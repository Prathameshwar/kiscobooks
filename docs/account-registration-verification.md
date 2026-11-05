# Account registration verification — 2026-10-20

The local registration feature is enabled and its manual-review Authentik
blueprint is applied. The existing Auth launcher remains the entry point.

Validation results:

- Auth: 109 UI/unit tests and 40 server tests passed. Native Redis refresh
  coordination was enabled for the final full run; no tests skipped.
- Shared UI: 1,722 tests passed, including field/password primitives and themes.
- Registration PowerShell configuration: 4 Pester tests passed.
- Auth production build passed. Auth, UI and Console TypeScript checks passed.
- nginx template deployed and `nginx -t` passed; the managed instance reloaded.
- Real Edge registration: Login → Create account → branded form → pending-review
  success passed. Duplicate username returned 422, cross-origin creation returned
  403, and the form retained no password inputs after success. Mobile layout had
  no horizontal overflow. Light, Dark and Ledger rendering inspected.
- Live Authentik records had inactive status, explicit false email verification,
  external type, usable hashed passwords, the pending path and no groups.
- Manual activation plus verified=true produced a successful OIDC login and a
  verified-email access-token claim. Registration itself granted no billing roles.
  The five disposable provider test accounts were removed afterward.

Review of CLAUDE.md security and correctness rules: strict field allowlist, body
limits, trusted provider HTTPS, independent anonymous cookies, same-origin POST,
distributed rate limit, fixed sanitized errors, no credential logging/storage in
the application, and no membership/role assignment. Provider writes retain
Authentik's audit mechanism; Identity state was not changed by registration.
Money, tenant data, migrations and financial outbox behavior are outside this
provider-only change and remain governed by existing APIs.

Simplification/security review found the native executor's intermediate 302,
focus after unlocking invalid forms, and explicit body timeout handling. These
were corrected and regression checks passed. No remaining blocking finding in
the local registration path. `/simplify` and `/security-review` commands are not
available in this Codex session; their review intent was performed manually.

Early checks exposed the Windows PowerShell execution-policy restriction and a
TypeScript check racing with build-generated `.next/types`. Pester was rerun with
process-only policy bypass; final TypeScript validation ran after the build.
The final build ran with the development server stopped, then Auth was restored.

Limits: SMTP and automatic verification are deferred by request. Manual approval
is in Authentik administration, separate from the billing platform role. Existing
workspace invitation/permission flows retain their passing Auth regression tests;
this run verified provider signup and approved provider login, and did not create
a new billing workspace or exercise a new real invitation end to end. Production
exposure needs rate limits on the provider's own public enrollment endpoint too.

## Regional registration review, 2026-10-21

Completed initial registration Country/State bindings using active Identity
reference tables, with India as default and both selectors in the shared row.
The fixed Authentik enrollment saves the selected pair as account metadata; the
checked OIDC profile carries it privately into editable workspace setup defaults.
The Auth server validates references before enrollment, and Identity validates
and persists the final tenant pair. No new database schema was needed.

Evidence for this extension:

- Auth: all 132 UI/unit tests and 68 server tests passed. One opt-in native Redis
  handler test was skipped in this initial run; the final native Redis handler run
  passed all eight handler tests, including that opt-in test (69 server cases verified).
- Identity: 620 regional/onboarding, public choices and non-container migration
  checks passed; three container-only migration checks deselected. Public choices
  tests cover active filtering, inactive-country state exclusion, unknown queries,
  admission limits, bounded reference projections and no billing account writes.
- Six additional generated-workspace ID and regional default regressions passed.
- Console: 29 tenant form/directory/recovery tests passed, with TypeScript clean.
- Registration scripts: five Pester tests passed. Ruff and strict mypy clean for
  changed Identity implementation; Auth/client types, generated Identity contract
  checks, eight API-client transport tests and Auth production build passed.
- Native Edge against the production Auth build, real Redis and real Authentik:
  login link, database-backed India/state options, side-by-side desktop controls,
  all Light/Dark/Ledger themes, mobile without overflow and no hydration errors.
- Native registration persisted a usable password, exact region metadata,
  inactive external account, false verification and zero groups. A narrowly scoped
  disposable-account approval then exercised real checked OIDC sign-in; workspace
  setup retained India/Maharashtra and permitted edits.
- Workspace creation used a fully migrated and seeded disposable MySQL database.
  Independent SQL assertions confirmed country/state, INR/Asia-Kolkata/en defaults,
  generated ID, active verified non-platform billing user, one scoped bootstrap
  role assignment and audit outbox. Temporary account and database were removed.
- Authentik may ask for a second login for `prompt=login`: source inspection shows
  the first authenticated request records its login event and starts reauthentication.
  The browser check completes that fresh-login request; a wider `max_age` alone did
  not change this behavior. No speculative authentication timing change was shipped.

Manual simplification and security review covered strict seven-field input,
fresh reference validation, bounded public responses, no tenant/account lookup,
verified SSH/TLS, no caller credential forwarding, anonymous enrollment cookies,
unchanged inactive/manual-verification policy, private metadata and independent
billing grants. Found and corrected blueprint-upload pipeline error propagation
and Windows base64 newline handling. No remaining blocking finding in this tested
local registration/workspace flow. `/simplify` and `/security-review` are unavailable;
their intended review was performed manually. SMTP remains deferred by request.

Normal Auth/Console and API processes were restored after the production-build
and disposable-database check. Existing live tenants were not modified.
Final normal-runtime probes returned HTTP 200 for login, signup, registration
options, Identity public choices and nginx health. Registration was enabled with
239 active countries and 5,027 active subdivisions; both web apps reported UP.
