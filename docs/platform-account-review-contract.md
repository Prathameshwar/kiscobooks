# Account review implementation contract

Approved scope: first-three platform administration plan, 2026-10-21.

Authentik 2026.8.4 capability proof passed using disposable accounts and a
non-superuser role: object-scoped `view_user`/`change_user` permits only eligible
objects in list/detail/update, rejects unrelated users, and does not permit
`reset_user_password`. Enrollment will assign these object permissions to the
fixed review-service role through a trusted post-write policy. Existing pending
registrations are granted the same permissions by the deployment preparation.
No global view/change/reset permission is granted. The Identity adapter also
restricts path/type, groups/roles, provider identity and exact writable fields.

The provider lacks a conditional-update API. Identity serializes its own decisions,
rechecks a profile fingerprint before applying and verifies the response/readback.
Concurrent external administrator edits are drift and need reconciliation; the
managed review fields must have one administrative writer during normal operation.
Unrelated attributes are retained. Service credentials stay in private environment.

Review metadata belongs to the platform operating tenant and uses session-level
tenant filtering. It records a bounded profile snapshot to support indexed search,
an immutable provider UUID/numeric ID, a version, decision/reason/attestation, and
durable delivery state. Changes to the applicant email/profile invalidate pending
evidence. Audit stores entity/actor references and states, not applicant PII.
Review mutations accept an expected version and idempotency key. Pending commands
are committed with audit before provider calls; absolute state is reconciled on
retry. A processing or failed operation never reports successful approval.

Only pending/rejected Bill public registrations can be reviewed. Approved accounts
are read-only in this feature. Approve enables and manually verifies; Reject leaves
inactive/unverified; Reopen returns a rejection to pending. No billing user, tenant,
invitation or platform role is created. Existing onboarding remains authoritative.

Password change uses a separate native authenticated flow with current-password,
MFA when configured, new/confirmation and native success messaging. It needs no
management token. Native completion is not inferred from a return query parameter.
The application offers protected sign-out/fresh sign-in afterward; changing a
password alone does not claim immediate revocation of all issued OIDC/JANSO tokens.
