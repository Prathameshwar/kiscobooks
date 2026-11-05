# Immediate tenant administrator onboarding

Status: implemented in Identity and Console on 2026-10-27. The live Identity
database was backed up and migrated from 0085 to 0087. Controlled synthetic signup,
approval and new-administrator sign-in passed against the running installation;
see [the current review](onboarding-review-2026-10-27.md). No platform notification
ownership or email transport is configured, so real email delivery remains untested.

## Agreed decisions

- A platform operator may create a new Authentik account or select an active, verified Authentik account that is not linked to any tenant. One login remains bound to one tenant.
- For a new account, the operator confirms that the intended recipient controls the email address. That administrative attestation permits immediate verification and activation. A typed or browser-generated temporary password is sent to Authentik and shown once in Console for private sharing.
- Existing users retain their password. Sign-in is available immediately. The recipient is asked to change a supplied password after login.
- The manual sign-in handoff is always visible. When platform email channel, template assignment and provider routing are configured, Notification receives a password-free account-ready command.

## Phases and checks

1. **Provider boundary:** dedicated Authentik service account with add/view/change/reset user permissions, verified TLS, exact email and subject checks. A stable command marker lets a retry reconcile an account created before a local transaction failed. New provider users stay inactive through local commit. Disposable real-provider create/password/activation check passed and the proof account was removed.
2. **Identity command:** preflight pending registration, provision or resolve the provider account, reject a linked subject, create active tenant/user/fixed grant and audit in one local transaction, then activate the new provider account and stage a password-free notification. Receipt stores only references; the first response reveals a new password, replay does not.
3. **Console handoff:** account choice, exact-email existing-account lookup, generated or entered password, explicit email attestation, and an aligned one-time handoff panel with sign-in/change-password links. Draft recovery stores no password.
4. **Release verification:** provider adapter, tenant API and Console tests; export OpenAPI/client; live migration completed. Final login with a real recipient remains before claiming live end-to-end completion.

## Tenant creation wizard (2026-10-27)

1. Reuse `WizardLayout`, `Stepper`, `ReviewList` and the shared field components for
   Tenant details, Administrator, and Review & create. Keep tenant editing as its
   existing single form. Validate each step; check pending registration before review.
2. Preserve the new/existing administrator paths, explicit existing-account selection,
   generated/entered password and email attestation. Recheck before creation, retain
   idempotency on retry, and keep credentials out of recovered drafts and review text.
3. Show creation results within the third step: active tenant/administrator summary,
   notification status, access links and private one-time password handoff. Verify
   navigation, validation, pending-account confirmation, stale search responses,
   reauthentication, failure/retry and success with UI tests and TypeScript checks.

Verification: 24 tenant form/recovery tests passed, along with 30 company wizard
tests and 15 company API/unsaved-change tests. Console TypeScript checking passed.
Manual simplification and security review found no additional issue: credentials
remain in memory, pending registrations are checked twice, and retries preserve the
command key. Current live verification and email-delivery limits are recorded above.

## Security boundary

Authentik's stock API requires `reset_user_password` and `change_user` authority to set a password and activate an account; the dedicated token is stored only in the private Identity environment. It is not a superuser but these permissions are model-wide. Protect and rotate this credential as a privileged service secret. The platform administrator's email attestation is recorded in audit and should be made only after verifying the recipient outside this flow. A crash after local commit but before provider activation leaves an inactive provider account; retrying the same command activates it. No successful response is returned before activation readback.
