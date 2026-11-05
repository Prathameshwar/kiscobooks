# Identity gap contracts and operations

Implementation tracker: [todo](identity-gap-todo.md). This records contracts being
implemented; a row is not a claim that its complete workflow already exists.

| Capability | HTTP/worker surface | Authority and completion checks |
| --- | --- | --- |
| Authentication | Bearer validation; current session; internal gateway authorization | Configured Authentik issuer/audience; verified local subject; live grants; no client permission lists |
| Invitations | Existing user invitation plus resend/cancel/accept | Tenant `user.invite`; acceptance proves invited email and IdP subject; one activation |
| Platform | Tenant create/list/suspend; initial administrator | Explicit platform permission before narrowly scoped unfiltered DB access; audited bootstrap |
| Organization | Group update/lifecycle/member removal; group assignment; membership end/primary; company/department/role lifecycle | Existing resource management permission at both source and destination scopes; self-escalation denied |
| Company children | Contacts, banks, documents | Company object scope; bounded lists; sensitive reveal/download separate and audited |
| User children | Notification preferences; API-token issue/list/revoke | Self or explicit tenant administration; tokens never exceed current issuer authority |
| Customization | Definitions, layout, policy management/resolution, values and rebuilds | Tenant-only layout; registered company field support first; `custom_field.manage` / `field_policy.manage`; enforcement and source freshness together |
| Step-up | Challenge/complete, enforced at company request boundary | Authentik fresh authentication; Redis TTL proof bound to real actor and company |
| Support | Impersonation start/end and expiry sweeper | Explicit `user.impersonate`; reason; bounded read-only support access; both identities in audit |
| Posting | Internal reserve/confirm/abort and reconciliation | Authenticated Billing service; idempotent reservation outside posting transaction; no unsafe automatic timeout release |
| Audit | Identity outbox publisher → authenticated Audit consumer | Exact route allowlist, signed body, broker source identity, confirm before publish marker, commit before ACK |

All growing HTTP lists use the existing signed cursor/page contract. Actions validate
current authority on retries. New schema changes use one DDL per migration; generated
clients, permission seeds and every affected event consumer change with their producer.

## Audit delivery rollout

Run the existing Identity and Audit migrations first. Create separate RabbitMQ
accounts and a dedicated vhost with TLS in deployments. The publisher account may
write `platform.audit` and must not have RabbitMQ's `impersonator` tag. Restrict
consumer access to the exchange, queue and dead-letter topology it needs.

Publisher environment (values supplied by environment/secret manager):

- `IDENTITY_DATABASE_URL`
- `IDENTITY_AUDIT_BROKER_URL`, `IDENTITY_AUDIT_BROKER_USER`
- `IDENTITY_AUDIT_EVENT_SECRET` (at least 32 bytes), `IDENTITY_AUDIT_EVENT_KEY_ID`
- `IDENTITY_AUDIT_PUBLISH_AFTER` (explicit UTC cutoff after the corrected payload rollout)
- Optional `IDENTITY_AUDIT_MAXIMUM_ATTEMPTS` (default 12)

Audit environment retains its API/DB settings and adds `AUDIT_BROKER_URL` and
`AUDIT_SOURCE_CREDENTIALS`: a JSON object keyed by publisher key ID, each value
containing `issuer`, `broker_user`, `secret` and the exact `event_types`.
Use Identity's `identity.events.audit_contract.AUDIT_EVENT_TYPES` for those routes;
do not subscribe with wildcards or import Identity ORM models into Audit.

Start the consumer before the publisher so durable bindings exist:

```powershell
# In apis/audit, with its configured environment:
uv run python -m audit.tasks.consume
# In apis/identity, with its configured environment:
uv run python -m identity.tasks.audit_publisher
uv run python -m identity.tasks.audit_outbox
# After resolving the cause, release one reviewed exhausted event:
uv run python -m identity.tasks.audit_outbox --retry <message-uuid>
```

The new `audit.events.authenticated.v1` queue uses RabbitMQ single-active-consumer
and prefetch one. Stop the legacy unsigned consumer before using this writer; never
run both against the same hash chains. Move any legacy queue backlog only through
a reviewed remediation/republication procedure. Invalid signatures/schema go to
`audit.events.authenticated.v1.dead`; transient DB faults leave delivery unacknowledged.

Publication attempts back off exponentially to one hour and stop at the configured
limit without deleting the event. Diagnostics report pending/exhausted/held counts,
oldest eligible event and a bounded sample of identifiers/error classes, never payloads.
Monitor process liveness, repeated reconnects, pending age, exhausted count and DLQ
depth. Recovery preserves the original message ID and payload. Published and historical
held events cannot be released by the retry command. Do not rewrite immutable Audit
history or silently lower the historical cutoff.

## Environment evidence

Local MySQL 9.6 is available. No configured broker/Authentik runtime or Docker was
found at implementation start. There is no Billing service directory. Tests against
transport doubles establish handler behavior only; live integration remains tracked
separately. No production deployment or historical data has been changed.

## Decision log

- 2026-09-12: Follow the existing Authentik/NextAuth/nginx architecture. Identity stores
  local identity, invitation and authorization state; it does not become a password,
  MFA or IdP-session store. Tenant layout and registered company field support remain
  the launch scope. Support impersonation preserves the documented read-only model.
- 2026-09-12: Use the shared signed broker mechanism for Audit; replace unsigned ingress
  with an explicitly authenticated queue and hold historical events at rollout.

## Complete operation/configuration reference

See [Identity gap operations](identity-gap-operations.md) for Azure, OIDC/browser, Redis, Notification, encryption, customization recovery, Billing and rollback procedures. See the generated [OpenAPI](../apis/identity/openapi.json) and [TypeScript client](../clients/api-client/src/identity.d.ts) for current request/response contracts.
