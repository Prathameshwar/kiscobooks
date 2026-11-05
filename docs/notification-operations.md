# Notification service operations

## Ownership and deployment configuration

`/v1` manages the caller's tenant space. `/v1/platform` requires the configured
Identity platform operator, the exact `platform.notification_*` grant and fresh
authentication for mutations. A platform grant does not grant access to a customer
space. The platform operating tenant must be real; its configured space ID differs
from its tenant ID. Company sentinel IDs do not select the platform realm.

Configure `NOTIFICATION_PLATFORM_OWNER_TENANT_ID` and `NOTIFICATION_PLATFORM_SPACE_ID`
together. Configure the same owner/space in Identity's
`IDENTITY_NOTIFICATION_PLATFORM_TENANT_ID` and `IDENTITY_NOTIFICATION_PLATFORM_SPACE_ID`.
Set the browser server's `NOTIFICATION_GATEWAY_URL` to the full gateway namespace,
e.g. `https://api.example.invalid/notification`. Set
`NOTIFICATION_CALLBACK_PUBLIC_ORIGIN` to that same externally visible namespace.
Twilio signatures use this configured origin, never a request Host header.

Secret values belong in deployment environment or a secret manager, not SQL, API
bodies or tracked environment files. `NOTIFICATION_CREDENTIAL_BINDINGS` maps opaque
references (for example `env:EMAIL_PRIMARY`) to `tenant_id`, `space_id`,
`environment_variable` and `allowed_senders`. The referenced variable holds provider
JSON; webhook/challenge bindings hold their raw verification secret. Management lists
only that owner's registered references. Reusing a reference in another space fails.

Provider JSON contracts:

- SES: an explicit workload-identity binding `{}`, AWS credential keys, or an
  operator-provisioned `role_arn` and optional `external_id`; also configure the
  account region. Setup, send and SNS confirmation use the same bound AWS identity.
- Twilio: `account_sid` and `auth_token`. The first release verifies owned SMS-capable
  phone numbers; alphanumeric sender registration is a separate vendor workflow.
- Meta: `access_token`, `business_account_id`, `phone_number_id` and optional
  `api_version`. The app signing secret and challenge token use separate owner-bound
  references. Select an API version supported by the provisioned account.
- Existing FCM support remains; push enhancement and live certification are separate.

SES account capabilities name `sns_topic_arn`. Provision that exact ARN in
`NOTIFICATION_SNS_TOPIC_BINDINGS`, bound to the same tenant and space; an account
cannot claim another owner's topic. Meta capabilities name `verification_token_ref`.
No API accepts AWS keys, Twilio tokens or Meta access tokens directly.

## API onboarding order

Use `/v1/platform` for platform setup and `/v1` for tenant setup. All command endpoints
that create jobs, activate a version, retry or reconcile require `Idempotency-Key`.
Retain the same key and body after a lost response; a different command under the same
key returns 409. Growing collections use signed cursors, default 50 and maximum 200.

1. Read `provider-types`, `credential-bindings`, `use-cases` and `channels`.
2. Create `provider-accounts`; POST `provider-accounts/{id}/validate`; read `jobs/{id}`.
   Provider IO runs outside DB transactions. Successful validation activates a pending
   account. A disabled account must first be PATCHed to pending. Credential/region
   rotation resets account and sender verification before sends can resume. Rotation
   is bounded to 200 verified sender records; clear old verification first above that.
3. Create `sender-identities`, then POST `sender-identities/{id}/verify` or `/sync`.
   Only provider evidence can verify a sender. Reactivation resets verification.
4. PUT `channel-settings/{channel}` after provider/sender readiness. Platform channels
   default disabled. Existing tenant traffic retains its legacy enabled default until
   explicit channel settings exist. This compatibility behavior is limited to tenant
   space. Transport readiness does not imply a purpose/template/route exists.
5. Create a template, channel/language variant and immutable version. The constrained
   variable schema supports primitive fields, required names, lengths and enums;
   number fields currently accept exact integers, while money uses strings. Preview
   through `template-versions/{id}/preview`. HTML variables are escaped.
6. POST `variants/{id}/activate` to replace an open activation prospectively. Rollback
   selects a previous immutable version through that same command. History is retained.
   Create dated `use-case-bindings` for a registered purpose, trigger, company and
   channel. Once any assignment exists for a purpose/scope, an ended assignment cannot
   fall back to a legacy template. Requested language falls back to an executable
   default-language version. Ambiguity fails closed.
7. For WhatsApp create the version's provider binding and POST `bindings/{id}/sync`.
   The provider must confirm its ID/name/language, approved status, body content and parameter positions. Sends use the
   template name, not its numeric provider ID. `channel_payload.components` supports
   ordered text header/body parameters and indexed URL buttons; parameter definitions
   are `{type: "text", variable: "declared_name"}`. Legacy ordered
   `template_parameters` remains supported. Media/attachment components are rejected.
   Rendered components are encrypted with the message snapshot, so retries preserve
   the original parameters after request context retention.
8. Create `routing-rules`. Provider, sender and channel must agree. Unsupported
   condition JSON is rejected. Company/event specificity, priority and deterministic
   weights choose the route. `effective-policy` explains configuration readiness;
   recipient consent, preferences and suppression are evaluated during planning and
   again immediately before dispatch. Existing documented security bypass remains.

Platform and tenant administration pages are `/platform/notifications` and
`/settings/notifications`. They use generated contracts through the authenticated
same-origin proxy. Management API authorization remains mandatory for every call.

## Producers and runtime processes

Identity stages the additive `identity.platform_notification.requested` event when
platform configuration exists, using an encrypted recipient/variables payload.
`IDENTITY_NOTIFICATION_PLATFORM_ENCRYPTION_KEY` and its key ID must match
`NOTIFICATION_PLATFORM_INGRESS_KEYS`. `NOTIFICATION_PLATFORM_SOURCES` grants an
Identity signing key/broker user only the configured operating tenant. Each recipient
reference binds one destination per channel; a destination change needs a new source
reference. Platform staff and pre-tenant evidence stays in platform space; optional
`target_tenant_id` is a reference only. No public arbitrary-send API exists.

The initial integrated producer is Identity invitation; platform staff alert is a
registered source contract. Other product events need their own producer adoption.
Identity's legacy invitation event remains an explicit compatibility path when the
new platform settings are absent. Provision and verify the new path before switching
producers; do not enable both publishers for the same business event.

Windows `audit-workers.ps1` includes these opt-in workers:

- `identity-notification-publisher`: Identity transactional outbox to Notification.
- `notification-platform`: authenticated encrypted platform ingress.
- `notification-identity`: legacy invitation/preference ingress during compatibility.
- `notification-vouchers`, `notification-accounting`: signed tenant/company-scoped
  voucher commands and Accounting-owned contact snapshots.
- `notification-dispatch`: due sends; requires `NOTIFICATION_DISPATCH_ENABLED=true`.
- `notification-scheduler`: normalization, configuration checks, unmatched receipts,
  retention, due retries and stuck-send detection.
- `notification-publisher`: exact signed audit events to `platform.audit`.

Configure `NOTIFICATION_AUDIT_BROKER_URL`, `...BROKER_USER`, `...EVENT_SECRET`,
`...EVENT_KEY_ID` and an explicit timezone-aware `...PUBLISH_AFTER` cutoff. Provision
Audit's matching source credential and exact event list from
`apis/notification/contracts/audit-events.json`; start the consumer binding before
publication. Historical outbox rows require a deliberate replay decision.
Domain planning/status events are distinct from this audit publisher's allowlist.
Platform notification evidence carries its realm/space in safe Audit context, is
excluded from tenant audit/activity/export/detail surfaces, and is available through
platform history only under the corresponding platform notification read family.

## Delivery evidence, limits and recovery

Planning completion is distinct from provider acceptance and delivery. Requests expose
one durable outcome per requested channel, including disabled channel, expired request,
missing assignment/route, consent and invalid template variables. Deliveries retain
assignment/version/provider/sender/route lineage. Details, attempts and receipts have
separate paginated endpoints. Neither API responses nor logs expose destinations,
rendered message content or raw provider errors. Template previews require read grants.

Default admission ceilings are 120 attempts per provider per minute and 300 per
space/channel per minute, configurable through `NOTIFICATION_DISPATCH_PER_PROVIDER_MINUTE`
and `NOTIFICATION_DISPATCH_PER_SPACE_CHANNEL_MINUTE`. A short space lock serializes
admission; provider IO starts after commit. Local capacity waits do not consume attempts.
Provider throttles use bounded retry/backoff. Unknown network/provider outcomes stay
in `sending`; there is no blind retry or cross-provider failover.

- Republish broker messages with the original message ID. Consumers commit before ACK
  and deduplicate replay. Invalid source/contract events go to durable dead-letter queues.
- Retry only failed/expired deliveries with retained unexpired request/content. Manual
  retries preserve lifetime attempt numbers, create a new bounded retry cycle and clear
  the previous provider identity from the current delivery. Attempts retain that identity.
- `reconciliation-cases` shows unresolved sends. The reconciliation command accepts only
  signed same-provider receipts whose message identity is already proven by the delivery
  or one of its attempts. It cannot attach an arbitrary receipt or assert success. New attempts carry native signed receipt correlation: SES message tags, Twilio's
  signed callback URL and Meta's opaque status reference. A matching signed receipt
  can settle an unknown send, including a receipt that arrives before HTTP finalization.
  A receipt for an older attempt cannot change the new cycle. Sends with no such proof
  remain held for provider-side investigation. `provider-events` lists safe receipt
  metadata and references for recovery, with owner-bound cursor paging and detail reads.
- Native SNS, Twilio and Meta callbacks are bounded and signature verified before inbox
  persistence. SNS certificates/confirmation targets are restricted to the topic's AWS
  SNS region host. Confirmation uses the SDK. No generic email HMAC fallback is accepted.
  Callback query values are redacted before application access logging; nginx callback access logging is disabled because the Meta challenge query contains a token.
- Retention nulls rendered and provider ciphertext, request variables and expired attachment
  metadata, preserving hashes/status evidence. Defaults are 90 days; configured content
  and provider retention cannot be shorter. Interrupted configuration jobs fail visibly
  after 15 minutes. Only clean scanner-authorized artifacts could become eligible, and
  external attachment association remains explicitly disabled pending private handoff.

## Alerts and deployment gate

Alert on queue/outbox age, DLQ count, callback trust failures, unmatched/stuck sends,
provider latency/throttles, retry exhaustion, invalid template outcomes, local capacity
waits, stale sender/template approvals and retention backlog. Use IDs and safe reason
codes in alerts. Do not log payloads, credentials, invitation URLs or destination data.

Stop API/consumer/dispatch/scheduler writers before migration. Preserve original revisions
0001-0026. Upgrade through 0116 using the matching release: nullable ownership columns,
restartable 0051 data backfill, then non-null constraints, composite FKs and new control
models. Backfill is data conversion, not seed configuration. Inspect legacy 0026 applied
state before proceeding: it historically contained multiple DDL statements and must not
be rewritten on an installed deployment. New revisions each issue one DDL statement.
If deployment stops, inspect the applied Alembic head and table state, then resume after
resolving the failed statement; do not stamp an unapplied revision.

Downgrade deliberately refuses when ownership collapse or purged request context would
lose evidence. Export evidence and retain ciphertext backups before destructive rollback;
reverting API code and disabling dispatch is the first operational rollback. The 0051
backfill is restartable and leaves ownership roots until their schema revisions unwind.

After legacy 0026, run Accounting's `party_contact_backfill` and drain signed snapshots
before tenant voucher sends. Old all-company party endpoints cannot satisfy company-owned
voucher requests.

Local verification and the two review results are recorded in
[the execution TODO](notification-platform-tenant-todo.md). Fixture sends and signed
callback tests do not certify real provider accounts. Production dispatch remains disabled
until non-production email/SMS/WhatsApp canaries pass with actual sender registrations,
provider approvals, owner-bound credentials and HTTPS callback domains. Activate one
space/channel deliberately, watch evidence and disable its channel/dispatch flag to stop
new sends. In-flight provider submissions cannot be recalled by a configuration change.

Decision log (2026-10-22): adopted platform/tenant ownership, exact audit realm handling,
provider-authoritative setup, frozen WhatsApp payloads, bounded admission and encrypted
platform ingress. Compatibility is explicit; live external channel activation remains a
separate operational gate.

SES attempt tags use the vendor-permitted underscore encoding of the local UUID/attempt
reference; the signed receipt decoder restores the local reference. Provider receipt
APIs expose identifiers and processing states only. They exclude callback bodies,
credentials and destination data. Keep the data encryption key/reference stable for
retained evidence; changing a provider credential is independent of ciphertext-key
rotation. Confirm retained evidence decrypts before deploying key changes.


Final review recovery notes (2026-10-22): dispatch rechecks schedule/backoff and
request/content expiry at claim time, and allocates its native attempt reference while
holding the claim lock. A delayed HTTP response can complete its original attempt's
evidence but cannot change a newer manual retry cycle. If HTTP evidence contradicts
a signed receipt, the attempt records `provider_result_conflicts_with_receipt`; retain
the proven identity and investigate rather than issuing a blind resend. Sender checks
that overlap configuration changes fail with `configuration_changed_during_check`;
queue a new verification job after the intended configuration is stable. The additional
[final review](notification-platform-tenant-reviews.md) records fixes and verification.

Admission also compares the current recipient destination identity with the frozen
delivery and compares provider configuration with the worker's transport snapshot.
A changed destination fails safely; a changed provider revision leaves the delivery
queued so the next scan can construct a transport from current credentials.

Notification administration screens and setup order are documented in
[Notification UI usage](notification-ui-usage.md). Platform administration's Notification
card opens the platform-owned workspace; Settings opens the tenant-owned workspace.
The [UI execution TODO](notification-ui-todo.md) and [two UI reviews](notification-ui-reviews.md)
record the additional local UI/API/browser verification. They do not change the live
provider/IdP/HTTPS deployment gate above.
