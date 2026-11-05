# Public registration workspace provisioning

Status: implementation and isolated verification complete. The live Identity database
has been migrated through 0087 and public signup is enabled. Current verification
is recorded in [the onboarding review](onboarding-review-2026-10-27.md).

## Journey

Public signup derives a workspace name from the email address and collects the
account and regional details without a workspace-name input.
It creates an inactive Authentik account only. The platform administrator sees the
requested workspace in Account approvals, independently checks the applicant and
email, and confirms approval. Identity completes the decision only after Authentik
reports the account active with its email verified and Identity has transactionally
created one tenant, its active first administrator, fixed `tenant_admin` assignment
and audit/outbox records. The next sign-in opens that workspace automatically.

Signup reached from an existing invitation records an invitation intent and does
not request or create another workspace. After approval the recipient signs in and
accepts the invitation. Legacy pending registrations without a workspace request
need an explicit workspace name from the reviewing operator before approval can
create a tenant.
The Auth server verifies invitation tenant, ID and matching invited email with the
public, rate-limited Identity availability endpoint before accepting an empty
workspace request. It never forwards these invitation identifiers to Authentik.

When the platform tenant form encounters an exact pending-registration email, it
pauses before writing. **Yes** opens that registration's review with the requested
workspace details and lets the administrator approve it; successful approval makes
the tenant. **No** cancels the attempted creation and keeps the form draft. An
unreviewed matching registration is never silently duplicated as a new tenant.
If no pending registration matches, platform tenant creation provisions an immediately
active administrator with an entered/generated password or selects an existing active,
verified account not linked to a tenant. It always offers manual access details.

## Phases and gates

1. **Registration contract.** Add a workspace request to the branded signup and
   strict Auth/Authentik input contract. Store only fixed workspace intent metadata
   in Authentik, with an invitation marker for invited signups. Extend Identity's
   platform review projection using one DDL statement per migration. Tests cover
   normal, invitation, duplicate and malformed submissions. No workspace is
   created at this stage.
2. **Durable approval provisioning.** After provider read-back, provision through
   Identity's existing `create_tenant` mechanism before completing the account
   decision in the same Identity transaction. The installed Authentik OAuth provider
   uses `hashed_user_id`, so the OIDC subject is Authentik `User.uid`; its UUID is
   only the review object's stable provider key. Replays and worker retries use the unique
   provider subject and command status to avoid duplicate tenants. An approved
   provider account cannot self-create a conflicting tenant while its decision is
   queued. Failed provisioning leaves the command queued or blocked with a safe
   recovery action; it never reports success or silently creates a second tenant.
3. **Platform handoff.** Add an authorized exact-email pending-registration lookup
   and a reviewed Yes/No confirmation before platform tenant creation. The server
   rechecks the match under the tenant-creation lock so stale UI checks cannot
   bypass it. Yes leads to Account approvals and an explicit attestation; No leaves
   the draft intact. Tests cover ambiguity, races, denied permission and replay.
4. **Release verification.** Run Auth, Identity and Console tests plus migration and
   real provider checks. Exercise a controlled new account from signup through
   completed approval and first sign-in, an invitation signup, concurrent/replayed
   approvals, provider outage and duplicate-email rejection. Do not attest to a
   real email address without independent evidence of ownership.

## Decision log

- 2026-10-27: derive the public workspace name from email; apply migrations 0086–0087
  and enable signup locally. Platform tenant creation uses immediate administrator
  provisioning and a three-step wizard. Approval queues optional account-ready email;
  manual sharing remains available whether or not email delivery is configured.
- 2026-10-27: public signup requests a workspace name; manual approval creates its
  tenant immediately after provider verification succeeds. Platform tenant creation
  redirects a matching pending signup to review instead of duplicating it.
- 2026-10-27: an invitation signup joins the existing tenant and does not create a
  new one. No platform administrator password or email-verification bypass is added.
