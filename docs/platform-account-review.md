# Platform account reviews

Platform administrators open **Platform administration → Account approvals**.
Opening the directory imports the newest bounded page of Bill registrations through
Authentik's supported API. Refresh continues imports and checks again. Open an
account, check the displayed identity and email independently, record a reason and
confirm the decision. Approve enables the account and records manual verification;
for public signup it also creates the requested tenant and first administrator.
Invitation signup waits for acceptance into its existing tenant. Reject keeps the
account inactive; Reopen returns a rejection to pending review. Approval stages a
password-free account-ready email when platform Notification is configured. The
approved record always offers copyable access and login details for private sharing.

## Deployment and local operation

Apply Identity migrations through `0087`, then run the system-role seed. The
`platform_admin` seed receives `platform.account.read` and `platform.account.review`;
tenant roles and support roles do not. Existing configured-operator and fresh
five-minute authentication checks protect decisions.
Account reads and mutations resolve permissions directly from the database,
including the post-intent delivery check; cached grants cannot extend review access
after an administrator withdraws the role.

Locally run `start/win/registration/prepare-account-review.bat`. It provisions a
dedicated service account and role with object-level user view/change permissions,
checks absence of global permissions, and stores its token in ignored, private
`start/win/env/identity.env`. Existing Bill applicants are assigned this object scope.
The trusted registration post-write policy assigns it for new applicants. The
handoff stage is always skipped, so inactive applicants are never signed in.

Restart Identity after configuration. `start-services.bat` starts the worker when
configured; `stop-all.bat` stops it. Independent controls are
`start-account-review.bat`, `stop-account-review.bat`, `status-account-review.bat`.
Production runs `python -m identity.tasks.account_review_worker --env-file PRIVATE_ENV`
as a supervised worker with the same trusted HTTPS/provider configuration.

Use a restricted provider API token, never a superuser token. Rotate its token in
Authentik and replace the private environment value, then restart API and worker.
Trust the provider TLS certificate; certificate verification stays enabled.

## Failure handling and retained data

The Identity decision and audit outbox commit before provider changes. A queued
command is retried every 15 seconds in batches of 20; status becomes completed only
after matching read-back and, for public signup, atomic tenant creation. Replaying
the same idempotency key is safe. A changed
identity or revoked reviewer authority blocks delivery. External provider edits
must be reconciled deliberately; the provider has no conditional-update API, so
these managed fields must have one writer during normal review operation.

For a blocked pending/rejected registration, open its detail page, enter a
reconciliation reason and select **Reconcile current details**. This reads the
current provider snapshot, clears drift only for an inactive/unverified eligible
account and requires a fresh decision and attestation. It does not update Authentik
or revive the blocked command. Active/verified drift needs correction by an
Authentik administrator first. An unresolved queued command must finish recovery
before reconciliation is offered. Imports are bounded; Refresh continues the next
batch when more registrations remain.

Identity stores name, username, email, region and requested workspace in the operating platform tenant
for indexed review search and audit investigation. Access is restricted to platform
account readers. Audit events contain references and states, without applicant PII.
Review commands retain reasons and attestations for administrative accountability.
No passwords, raw access tokens or arbitrary provider profiles are stored.

Decision 2026-10-27: store a bounded requested workspace in the review and
decision; complete public approval only when the verified provider subject has
one active tenant administrator. Invitation reviews have an empty workspace intent;
earlier registrations require an operator supplied name. The platform tenant form
checks exact pending-registration email before provisioning a tenant administrator.
The installed Authentik provider uses `hashed_user_id`: Identity binds the validated
provider `uid` as `authentik_sub`, while the separate provider UUID remains the
review identity. Changing the OAuth subject mode requires a coordinated migration.
Retention follows the installation's administrative/security record retention policy;
there is no automatic deletion of pending or historical decisions in this release.

Decision 2026-10-27: signup derives the initial workspace name from email on the
Auth server. Both platform creation and completed signup approval stage the same
password-free account-ready notification. Approved invitation registrations retain
their pending invitation link; approved public registrations sign in directly.
The approval directory imports on entry so a newly created account is visible
without a separate manual import. API and review worker share provider TLS trust.

Queued audit is distinct from delivered audit: the Identity audit publisher and
Audit consumer must be configured and monitored separately.

For this laptop, `registration/prepare-review-audit.bat` connects the existing
private RabbitMQ runtime, preserves other audit sources and the historical cutoff,
and supplies the exact Identity event allowlist. With this configuration,
`start-services.bat` also starts the Identity publisher and Audit consumer;
`stop-all.bat` stops those owned processes. Independent controls remain
`audit-workers.ps1 -Action start -Worker identity-publisher` and
`-Worker audit-consumer`. Production uses
separate least-privilege broker credentials with the same signed event contract.
The local cutoff deliberately holds events created before delivery was configured.
