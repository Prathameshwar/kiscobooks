# Forgot password

> **Provider note (2026-10-31).** This page describes self-service recovery through Authentik. With `local` (the default) there is no self-service reset yet, because no email is sent: `/recover` explains that an administrator issues a one-time link, and the person opens it at `/reset?token=…` to choose a new password. Administrators create links from the user's page (tenant users) or the platform access page. See [local authentication](local-auth.md).

The login page links **Forgot password?** to `/recover`. The page uses the existing
Auth shell, theme switcher, buttons, notices and back navigation. Reviewed Console
destinations and platform setup callbacks are preserved when returning to sign-in;
external or malformed return URLs are rejected.

## Current local behavior

SMTP is absent. The page explains how to contact an administrator for an expiring
recovery link. It does not collect an email address or password, send a message,
display a recovery token, or claim that mail has been delivered. Existing platform
administrator recovery links remain available through tenant administrator management.

## Email recovery after SMTP configuration

Configure Authentik's global email host, port, sender, authentication and TLS settings,
then run `start\win\registration\prepare-password-recovery.bat`. Restart the managed
Auth UI and Identity API to load their private environment settings. This prepares
both self-service email recovery and the existing administrator email option.
No SMTP credentials are added to browser configuration or billing models.

The preparation command installs `bill-self-service-recovery`, sets a validated
JANSO login destination and links the JANSO provider's identification stages to it
only when SMTP host/sender settings are present. It preserves unrelated recovery
flows and `Brand.flow_recovery`, which remains the token-bound administrator flow.
An unexpected existing flow causes preparation to stop rather than replace it.
The Auth feature flag is disabled before preparation and enabled only after success.
The native flow also checks SMTP at both planning and initial email dispatch.

The user continues to Authentik, enters their registered email address and receives
a single-use link valid for ten minutes. The native email stage verifies ownership
before password entry and retains existing MFA checks. Authentik validates matching
passwords of 6–128 characters, rejects the current password and extra writable fields,
changes the password without creating or activating an account, and confirms completion.
Continue returns to JANSO sign-in. JANSO's return parameter supplies guidance only;
it does not prove that a password changed or automatically authenticate the user.

Eligible accounts are active, verified Bill external registrations with usable native
passwords and one unambiguous email match. Unknown, inactive, unverified, passwordless,
service and provider-privileged accounts receive the same native email-stage presentation
without a token or email. Other sign-in providers and privileged Authentik operators
continue to use their provider/administrator recovery procedures. Recovery changes
credentials, not billing tenant status, account approval or role assignments.

Initial requests are limited to five per five minutes by client IP and hashed email,
across sessions. Native email resend limits also apply. Email proof is tied to the
same user and flow and is checked again before writing; provider deactivation or an
email change invalidates the write. Explicit deny stages prevent failed stage policies
from skipping security checks or showing false success. A final native password check
requires a completed write before the confirmation screen is shown.

Email token expiry is configured as nine minutes because Authentik 2026.8 adds one
minute when creating an email-stage token. The resulting link expires in ten minutes.
Native consent consumes the link once and protects against automatic email scanners.

Password changes use Authentik's native session behavior. Recovery does not promise
immediate revocation of already-issued OIDC or billing access tokens. No billing
API, database, model, schema, SDK or dependency changes were necessary.

## Review and validation

- The regression test first reproduced the missing login link. UI/server checks cover
  unavailable/configured recovery, pending and explicit retry behavior, back links,
  safe redirects, completion guidance and privacy metadata.
- Manual UX and security reviews fixed skipped-policy fallthrough, false completion
  messaging, the pending-user password comparison, stage initialization validation,
  and use of deprecated provider group access in the new flow.
  The trusted return URL is rendered into the persistent provider blueprint so
  automatic reapplication preserves JANSO navigation.
- Auth UI: 150 tests passed. Auth server: 100 passed, one existing test skipped.
  Final affected-page checks, TypeScript and production build passed.
- Windows registration/recovery deployment: 12 checks passed. Native provider: 15
  read-only checks passed, including actual deny-marker processing and prevention of
  token/email creation for hidden accounts. Test users remained unsaved.
- Browser: 173 checks at desktop, mobile and narrow mobile widths across light,
  dark and ledger themes; no browser errors or live account writes. Screens inspected.
- Native blueprints prepared locally, SMTP disabled, and managed Auth restored on
  port 4310. The final production rebuild passed. Live page navigation and privacy
  metadata passed; unsafe return URLs were rejected. Trusted HTTPS provider checks
  confirmed that native self-service recovery is denied without SMTP. The temporary
  review preview was stopped; the managed Authentik tunnel remains available.

Actual email delivery and a real emailed-password-reset run require configured SMTP.
They have not been claimed as verified. Repository slash review commands were not
available; equivalent manual reviews were performed.
