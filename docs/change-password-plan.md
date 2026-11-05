# Change password implementation plan

Authentik remains the credential authority. Use its authenticated self-service flow;
the billing application must not gain an administrator password-reset credential or
store passwords. External-provider accounts change credentials at their provider.

## Phase 1 — Authentik self-service flow

- Configure a dedicated, authenticated password-change flow with current-password
  verification, new password and confirmation, 6–128 character validation, rejection
  of unchanged passwords, and native password-change audit events.
- Use supported native stages and preserve existing authentication/enrollment flows.
- Check completion, cancellation, provider availability and session behavior.

## Phase 2 — Account navigation and page

- Add Change password above Sign out in the top-right account menu, with a reusable,
  accessible separator in the shared UserMenu component.
- Add a styled, authenticated Change password page using existing shared styles,
  navigation and messages. Continue into the secure Authentik form; preserve browser
  provider authentication and any required reauthentication/MFA.
- Configure the destination on the server, allowlist returns, and handle expired
  sessions and configuration errors without exposing tokens or accepting user IDs.
- Include clear completion/re-sign-in guidance. Do not infer password-change success
  from an untrusted query parameter.

## Phase 3 — Verification and final review

- Test menu order, separator accessibility and keyboard navigation; test page
  authentication, pending/error states, safe URLs and navigation.
- Apply and verify the native flow locally; use a disposable provider account for
  successful change, wrong current password, mismatch and length-boundary checks.
- Run affected unit tests/type checks and review CLAUDE.md §§5–6 manually, including
  credential ownership, CSRF, redirects, audit events and session limitations.
- Update run documentation and shared package version/lockfile as required.

No Identity database password columns or migrations are required. SMTP is not required
for an authenticated password change. Other concurrent edits remain untouched.
