# Current actor authority for Catalog jobs

Catalog jobs retain the original initiating user ID, never a durable copy of gateway grants.
Identity now provides a scoped permission proof outside the Catalog business transaction.
This is a prerequisite for C5.05; the durable job runner and artifacts remain separate work.

| Contract | Behavior |
|---|---|
| POST /internal/v1/tenants/{tenant}/companies/{company}/catalog-authorizations | Request ID, user ID and 1-32 registered permission keys; bounded 4 KiB input |
| Service authority | Existing company-scoped source credential must explicitly set allow_actor_authorization=true; default false |
| Domain separation | Request operation catalog.actor.authorize; response operation catalog.actor.authorization.response |
| Permission result | Only requested Catalog keys (plus custom_field.manage) that native active roles/assignments grant in this company |
| Subjects | Active user, active company, direct user and active group assignments; tenant/company ancestor scope, inclusive UTC grant dates |
| Proof | identity.company_actor_authorization.v1, exact request/tenant/company/user binding, source version, UTC issue/expiry, granted subset |
| Lifetime | At most 30 seconds and never across the next UTC grant-date boundary |
| Catalog checks | Verify signed response before parsing; reject extra permission, request mismatch, wrong scope, expiry or future issue time; 32 KiB response limit |
| Chunk transaction | Current verified source checkpoint must equal proof version; hold source lock and recheck authority before commit; never fetch HTTP inside the transaction |

No role name or user_type grants permissions. Missing native actor/company denies; missing source
bootstrap fails unavailable. More than 1,000 groups or scoped assignments fails unavailable.
An empty granted set is an authenticated denial, not an unavailable producer or a default role.
A department grant cannot authorize a whole-company job.

Tenant role-permission mutations now advance the existing source stream with a barrier, including
mutations that do not change a projected fact. The v1 fact schema is unchanged. Captured bulk/raw
role-permission writes are rejected. System-role seed changes require the documented fresh source
bootstrap; arbitrary SQL and writes outside the source capture contract are not event producers.

Proofs are short leases, not a claim of instantaneous distributed revocation. Acquire a fresh proof
for every chunk; a detected source-version change forces retry/refetch. Transport credentials,
proofs and gateway tokens are never persisted as job authority or published to clients.

Verification includes a real loopback Identity process: bootstrap, fetch proof, activate Catalog
context, remove unit.manage through Identity's ordinary role API, fetch the new proof, refresh
context, and reject the next Catalog actor check. Native group/role/user/company deactivation,
dated assignments, tenant/company isolation, key opt-in and signature separation are tested.
Live MySQL lock behavior and broker propagation remain release verification gates.

Decision 2026-09-11: use a minimal owner-side proof endpoint instead of adding permissions to the
existing snapshot fact schema. Shared request/proof DTOs and Catalog permission ownership are in
billing-platform 0.8.0; both services reuse the existing bounded signed-source transport.
