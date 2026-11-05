# Account registration implementation

Authorized scope: branded account creation from Login, Auth API integration with
Authentik, and manual administrator review while SMTP is unavailable.

1. Configure an Authentik enrollment flow that validates credentials and creates
   inactive, unverified accounts without groups or billing permissions. Add a
   bounded, rate-limited public Auth API adapter and regression tests.
2. Build the responsive registration screen using the shared design system;
   cover validation, pending, success, unavailable and failure states.
3. Apply the local configuration, exercise registration against the running
   provider, review security and accessibility, and document manual approval.

Passwords remain owned by Authentik. Existing Identity users, invitations and
permission checks continue to govern billing access. No database migration is
needed for provider-only pending accounts. Email delivery is deferred explicitly.

Completed: native provider enrollment, strict Auth API, branded form, private local
configuration and approval documentation. Live browser creation, duplicate/origin
rejection and approved-account OIDC sign-in verified; provider records confirmed
inactive, unverified and without groups before approval. Verification evidence is
recorded in `account-registration-verification.md`.
