# Tenant creation and management

Scope authorized by the user: account creation means a new tenant, created by
the user or by a platform administrator; verify first, implement, then review.

Existing: guarded/idempotent platform provisioning, lean directory and lifecycle
API; Console directory only. Registration creates provider credentials only.
Missing: self-service tenant onboarding, platform forms/details/invitation handoff,
and usable offline administrator invitations while SMTP is deferred.

1. Share atomic tenant/initial-admin provisioning; add verified-subject onboarding
   and protected platform detail/update/invitation operations. Preserve one login
   per tenant, fixed tenant-admin grants, idempotency and audit/outbox boundaries.
2. Add authenticated workspace onboarding and platform create/manage UI. Include
   pending, validation, permission and retry states. Keep registration credentials
   owned by Authentik and manual email verification until SMTP is configured.
3. Regenerate contracts, test API isolation/replay/lifecycle and UI branches,
   exercise local database/browser paths, then simplify and review security.

Immediate user steering included: remove the pre-registration approval paragraph;
name and username in separate rows; passwords side by side on wide screens;
password length guidance on a single line; fresh login on the first button click.

Completed 2026-10-20. [Implementation guide](tenant-management.md) and
[final verification](tenant-management-verification.md) record the delivered
directory, onboarding, database migrations, security review and test evidence.
