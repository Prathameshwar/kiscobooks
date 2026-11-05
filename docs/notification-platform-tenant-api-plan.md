# Platform and tenant notification APIs: investigation and phased plan

Date: 2026-10-22. Status: proposal for review; implementation has not started.

Scope: providers, channels, templates, purpose/trigger configuration and delivery
operations for email, SMS and WhatsApp. APIs and workers first; administration UI
after the API contracts and authorization are verified. Keep the existing seven
services, MySQL, RabbitMQ/outbox and local project layout.

Confirmed requirement: platform administrators manage platform deliveries, including
platform staff and recipients who do not yet belong to a tenant. Tenant administrators
manage their own notification configuration, purposes and templates within their tenant.
Platform administration does not grant access to tenants' business delivery history.

This proposal does not supersede [notification.md](notification.md),
[roles-permissions.md](roles-permissions.md) or the existing remediation record.
Phase P0 must record accepted amendments before implementation depends on them.

## 1. What exists and what is missing

Inspected the notification models and all 26 migrations; management schemas/routes;
planning, dispatch, callbacks and provider adapters; Identity platform authentication,
gateway and notification publisher; voucher/contact ingress; shared tenant filtering,
broker envelope, permissions and system roles; nginx and Windows worker wiring.

| Area | Existing implementation | Gap relevant to this request |
|---|---|---|
| Providers | Tenant-owned `provider_account`, secret references, lifecycle, CRUD/list | No platform management boundary; provider/channel pairs and credential references need registered, scoped validation. Tenant input can currently name an environment reference resolved by the worker. |
| Channels | Code catalogue: email, SMS, WhatsApp, push | No channel discovery/readiness API or explicit per-owner channel policy. A channel is not a provider account. Push exists but is not an expansion target here. |
| Senders | Create/list; initially `unverified` | No supported verify/sync, update or deactivate workflow; dispatch requires a verified sender. Configuration cannot currently complete through APIs alone. |
| Templates | Template, channel/locale variant, immutable version, dated activation, provider binding | Incomplete read/edit/deactivate/history/preview lifecycle; variable schema is stored but not enforced; content identity omits channel payload. |
| Template selection | Event plus company/tenant specificity, then locale and activation | Multiple keys can share an event. Resolver selects one without an explicit use-case assignment or stable tie-breaker. No distinct platform namespace or placement/purpose contract. |
| Routing | Company/tenant event/category specificity and deterministic weighted selection | `conditions` is accepted but not evaluated. Need typed supported predicates or rejection, update/deactivation and an effective-policy explanation. |
| Delivery | Request/delivery lists, retry, voucher evidence routes, attempts/events in DB | No general detail, attempt/timeline, per-channel planning reason or reconciliation API. `request.completed` means planning completed, not delivery success. |
| Integrations | Signed Identity invitation/preference, Vouchers and Accounting contact consumers | Identity invitations still use tenant-owned configuration. No platform/pre-tenant execution contract. Several platform events are candidates, not existing integrations. |
| Runtime | SES email, Twilio SMS, Meta Cloud WhatsApp and FCM adapters; opt-in dispatch | Native callback onboarding and production trust are incomplete; notification audit publisher and Identity notification processes need launcher coverage. |
| Isolation | `TenantMixin` and session tenant scope; company-scoped voucher evidence | Management context requires a real tenant. `SCOPE_ALL` is only a company wildcard, not platform ownership. Tenant-wide management checks do not offer delegated company configuration. |

Evidence anchors:

- [API authentication](../apis/notification/src/notification/api/auth.py),
  [session scope](../apis/notification/src/notification/api/dependencies.py),
  [provider/query APIs](../apis/notification/src/notification/api/routes.py),
  [management APIs](../apis/notification/src/notification/api/management.py).
- [Template resolution and planning](../apis/notification/src/notification/tasks/consume.py),
  [routing](../apis/notification/src/notification/domain/routing.py),
  [restricted renderer](../apis/notification/src/notification/domain/template.py).
- [Dispatch](../apis/notification/src/notification/tasks/dispatch.py),
  [adapter resolution](../apis/notification/src/notification/tasks/delivery_worker.py),
  [callbacks](../apis/notification/src/notification/callbacks.py),
  [provider verification](../apis/notification/src/notification/providers/verify.py).
- [Identity gateway](../apis/identity/src/identity/api/login.py),
  [configured platform operator checks](../apis/identity/src/identity/api/platform.py),
  [local nginx](../start/win/conf/bill.conf),
  [worker launcher](../start/win/audit-workers.ps1).

Current verification: `uv run --locked pytest -q` in `apis/notification`:
**104 passed in 16.51s**. The suite contains a MySQL fixture but no collected
MySQL-marked tests; this result establishes neither MySQL concurrency nor migration
round-trip safety. No live provider credentials were used.

[notification-review-fixes-todo.md](notification-review-fixes-todo.md) is the more
honest outstanding-work record than the older broad completion checklist. In
particular B07 is still marked active; B08/B09 and several G-items are open. Some
implementation has advanced beyond the ledger, so revalidate each item rather than
assuming either the checkbox or the existence of code proves completion.

## 2. Recommended ownership and storage boundary

Use one notification engine with explicit configuration spaces. Reuse its domain
logic and adapters rather than build a second delivery pipeline.

Proposed `notification_space`:

- `id`, real owning `tenant_id`, immutable `kind=platform|tenant`, lifecycle and audit.
- One tenant space per tenant; one platform space owned by the installation's real
  operating tenant. Identity already records platform administrative audit in the
  operator's operating tenant. Provision/configure that owner explicitly; fail closed
  if installation ownership is absent or inconsistent.
- Platform ownership is a service policy, not a new cross-tenant role scope. Do not
  invent a zero-UUID tenant, make all existing `tenant_id` fields nullable, or use an
  arbitrary customer tenant as the platform owner.

Carry `space_id` on notification configuration and execution rows. Keep their real,
non-null `tenant_id` and existing tenant filter. Add a fail-closed session space
constraint as well: a tenant route can only use its tenant space; a verified platform
route can only use the platform space. Apply it to reads, ORM identity lookups,
writes, child histories and worker paths. Cross-space links are rejected, including
within the same operating tenant. Unique keys and same-service composite FKs must
include the ownership dimensions where needed.

This extra dimension is necessary even when the operating tenant also has ordinary
users or companies: tenant permissions in that tenant must not reveal platform
credentials, endpoints, templates or delivery history. Space policy belongs to
Notification; any reusable session-filter mechanism belongs to `libs/platform`.
Do not solve this with repeated route-level WHERE clauses.

Platform deliveries execute and retain evidence in the platform space, including
when the recipient belongs to a customer tenant. `subject_tenant_id` and target
company references are optional external references, not storage ownership or FKs.
Platform staff and pre-tenant recipients therefore need no customer tenant, company
or fabricated Identity user. Use a typed source-issued subject reference and an
encrypted endpoint snapshot. Only trusted, purpose-authorized producers may supply
these destinations; no arbitrary-recipient public send route.

Tenant deliveries execute in their tenant space. Company-specific resources keep
their existing company fence. Add explicit company authorization for delegated
configuration and details; all-company settings require tenant-wide authority.

Platform-supplied transport for tenant business delivery is an optional, explicit
grant, separate from platform-owned messages. Preserve the existing documented
logical-provider-per-tenant model for such grants: publish a tenant-owned managed
projection with provenance, allowed purposes and opaque credential binding. A tenant
cannot edit its protected fields, resolve the source secret or use the platform
account directly. Do not enable shared fallback by default.

## 3. Define purpose, trigger and template assignment

Keep these concepts separate:

| Concept | Meaning | Example |
|---|---|---|
| Channel | Transport class | `email`, `sms`, `whatsapp` |
| Provider adapter/account | Code implementation and configured account | SES and a platform SES account |
| Sender | Verified identity under an account | Email identity, SMS number, WhatsApp phone-number ID |
| Use case | Code-registered semantic purpose and allowed producer | Platform invitation or tenant voucher sharing |
| Trigger/placement | Named business action where that use case can run | Tenant provisioned, voucher posted, manual voucher share |
| Template | Versioned content for an owner/channel/locale | A tenant's invoice share message |
| Assignment | Explicit use-case/trigger/channel to template choice | Sales manual-share email uses template A |
| Route | Account/sender and bounded retry policy | Primary verified email sender |
| Delivery | One resolved recipient/channel execution | Accepted, then delivered or failed |

Extend the code catalogue with a typed notification definition: stable key, allowed
owner kinds, source service/event, category/purpose, allowed triggers, recipient
contract, allowed channels, variable schema/version, TTL and override policy. Tenant
admins configure assignments and activation for registered tenant use cases. They
cannot register arbitrary producer events, relabel marketing as security or introduce
runtime expressions that route business policy.

Candidate platform definitions: tenant onboarding/invitation, account review outcome,
tenant access change and platform operational alerts. Candidate tenant definitions:
voucher share/issued/posted, payment/receipt communication and licence reminders.
Only invitations and existing voucher sends have relevant implemented producer paths;
the others require owner-specific contracts, approvals and tests before activation.
Authentication/OTP/password delivery remains owned by the configured identity provider
unless an explicit integration assigns it here. No independent authentication engine.

Proposed `notification_use_case_binding` stores space, company applicability,
definition key, trigger key, channel, template/variant reference and dated validity.
Enforce one effective assignment for a resolution key. Templates can be reused across
triggers but every send resolves an explicit assignment. This removes the current
ambiguous event-only selection. Template category/schema must agree with the definition.

Resolution contract:

1. Authenticate producer and validate its permitted use case, owner and target.
2. Resolve space from trusted configuration and verified source context, never just
   caller-provided IDs; check TTL, idempotency and supported schema version.
3. Enforce channel enablement and current endpoint/preference/consent/suppression.
4. Within a tenant space, resolve exact company assignment then tenant default;
   within platform space, resolve only platform assignments. Resolve requested locale
   then the assigned template's declared default. Define validity as `[from, to)`.
5. Resolve an eligible route/account/verified sender and channel-compatible binding.
   A disabled or unusable candidate must not accidentally win weighted selection.
6. Persist definition, assignment, template version, route and rendered payload
   snapshot, with one durable reason for every channel sent, skipped or suppressed.
7. Dispatch after commit; recheck revocations and required provider approvals before
   sending without silently switching to a newly edited template.

No automatic platform-template fallback for tenant sends, no tenant override of
platform security messages, and no implicit fallback between SMS/email/WhatsApp.
Multiple requested channels currently mean independent sends. Any future sequential
fallback policy needs its own explicit state and duplicate-prevention contract.

The existing security category bypasses preferences, consent and suppression. Preserve
documented behavior until a separate decision distinguishes user preference bypass
from hard-bounce, provider opt-out and invalid-destination blocking. Do not silently
change it or allow tenant-authored categories to expand that bypass.

## 4. API contract to deliver

Retain tenant `/v1/...` resource routes for compatibility. Add a distinct
`/v1/platform/...` surface in the Notification service; externally the configured
gateway service prefix remains `/notification`. The server resolves the space.
No body/query field lets a tenant select platform ownership.

Provide equivalent resource operations in each authorized surface:

| Resource | API capabilities |
|---|---|
| `/channels`, `/provider-types`, `/use-cases` | Code catalogue, supported combinations, schemas, allowed purposes/triggers and capability discovery |
| `/channel-settings/{channel}` | Effective readiness and enable/disable policy; enabling validates account/sender/binding readiness |
| `/provider-accounts` | List/create/detail/update/disable; asynchronous validate/sync job; safe health result and callback onboarding metadata |
| `/sender-identities` | Bounded list/create/detail/update/deactivate; verification initiation and provider-authoritative status sync |
| `/templates` | List/create/detail/metadata update/deactivate; clone only where the source is explicitly shareable |
| `/templates/{id}/variants` | Bounded list/create/detail/deactivate by channel/locale |
| `/variants/{id}/versions` | Immutable create/list/detail; schema/content validation and preview |
| `/variants/{id}/activations` | History, scheduled activation, end/replace current window and rollback by new activation referencing an old version |
| `/template-versions/{id}/bindings` | Create/list/detail and provider status sync; approval cannot be tenant self-certification |
| `/use-case-bindings` | Configure purpose/trigger/channel assignment, list/detail and dated replacement/deactivation |
| `/routing-rules` | List/create/detail/update/deactivate; typed validation and concurrency protection |
| `/effective-policy` | Explain selected assignment, template, route and blocked prerequisites; authorized object context only, no actual send |
| `/requests`, `/deliveries` | Lean filtered lists plus scoped details, planning results, attempts and event timeline |
| `/deliveries/{id}/retry` | Idempotent authorized retry, bounded cycle, current policy/expiry check and preserved lifetime attempt history |
| `/reconciliation-cases` | List/detail and audited provider-evidence resolution; no blind retry of an ambiguous accepted send |

Exact paths and operation IDs are finalized in P0 against API conventions. Preview is
authenticated, bounded, non-persistent by default and uses sample data; it must not
fetch another service's business object or return secrets. A future real diagnostic
test send is an audited, rate-limited asynchronous command to an approved test
recipient, not a synchronous general send API.

Every list uses lean SQL projections, bounded keyset paging, indexed allowlisted
filters/search/sort and a signed cursor bound to actor visibility, space, company,
resource, filters and sort. Bound currently unbounded sender, consent and endpoint
lists too. Reject unsupported filters and arbitrary route `conditions`.

Use strict channel/provider enums, timezone-aware UTC validity values, `extra=forbid`,
the standard error envelope and concurrent-edit preconditions. Provider IO runs as a
job outside database transactions. Idempotency receipts cover retry, activation,
verification/sync jobs and other side-effecting commands. A lost response replay must
not repeat a provider action.

Keep callbacks separately public only for provider onboarding and signed receipts:
`/v1/callbacks/{channel}/{callback_key}`. A Meta verification challenge is an explicitly
public, narrow GET onboarding exception; it is not an authenticated management route.

## 5. Authorization, secrets and provider correctness

Platform routes require Identity's configured operator verification and live grants.
Extend the short-lived signed gateway contract with a purpose-bound platform
authorization context, following the existing platform-history approach. Its authority
must be verified server-side; a role name, `user_type`, header, tenant ID or
`notification.*` grant alone is insufficient. Reuse fresh platform authentication for
sensitive provider/credential and activation actions. Support impersonation stays
read-only and cannot configure platform delivery.

Add granular `platform.notification.*` permission keys for configuration and delivery
operations and explicit tenant keys for channel/use-case configuration and sync where
existing keys are insufficient. Keep ordinary `notification.*` permissions tenant
bound. Update the fixed catalogue, role definitions, auditor exclusions, seeds,
documentation and tests together. Existing platform grants confer no tenant business
delivery access; support follows the existing audited tenant-access boundary.

Credential APIs accept only opaque, owner-bound bindings to approved secret sources.
Do not allow a tenant to request `env:PLATFORM_...` or an arbitrary secret-manager path.
Keep resolution worker-only and validate ownership before IO. Distinguish references
from secret material; never return raw values. Credential onboarding/rotation must
work without a direct SQL edit. If tenant-supplied credentials need a brokered secret
write, use an available secret store and write-only contract rather than SQL storage.

Provider work uses the existing adapters, with live certification per channel:

- Email/SES: sender/domain verification status, workload identity, configuration-set
  event routing, signed SNS receipt verification, topic/account allowlisting and
  verified subscription confirmation. Existing generic HMAC is not native SNS trust.
- SMS/Twilio: native `X-Twilio-Signature`, exact trusted public callback URL and
  complete form parameters, explicit per-account status callback routing and sender
  readiness. Review destination-market sender/template requirements before enabling
  that market; the adapter's existence does not establish that readiness.
- WhatsApp/Meta: verification challenge, native `X-Hub-Signature-256`, business-account
  and phone-number scope, provider-synced template approval/quality, explicit external
  template name versus numeric ID, language and ordered typed component parameters.
  Dispatch currently supplies `external_template_id` as a template name and only body
  text parameters; correct the contract before expanding templates. Recheck approval
  at send time and handle revocation after scheduling.

Use provider-specific trust and replay controls. Do not demand an invented timestamp
header from providers that do not sign one. Preserve valid provider retries with
durable dedupe; check signed timestamps where available. Stream with a body bound,
rate-limit at nginx and in-app, and never acknowledge arbitrary integrity failures as
duplicates. Callback lookup may resolve only one globally unique routing key before
establishing the owning tenant and space. Shared vendor credentials require an
unambiguous callback-to-account mapping; do not guess a tenant from a destination.

Official references checked during investigation:
[Twilio webhook validation](https://www.twilio.com/docs/usage/webhooks/webhooks-security),
[Twilio outbound status callbacks](https://www.twilio.com/docs/messaging/guides/track-outbound-message-status),
[AWS SNS signature verification](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html),
[SNS subscription confirmation](https://docs.aws.amazon.com/sns/latest/dg/http-subscription-confirmation-json.html).
The Meta template documentation fetch returned HTTP 429; refresh official Meta
contracts in P0/P6 before implementation, rather than treating this review as current
provider certification.

## 6. Phased delivery and acceptance gates

Implement sequentially in reviewable batches. A phase finishes with a working repo,
affected tests green and updated evidence. No migration-only phase or UI-first work.

| Phase | Deliverables and owners | Acceptance gate |
|---|---|---|
| P0: contracts and baseline | Notification owns the ADR, API inventory, platform operating-space design, use-case matrix, producer contracts and migration inventory. Reconcile B07 onward with current code and capture missing regressions. Identity owns platform gateway authority. | Agree ownership, recipient contracts, platform event list and credential onboarding. Record amendments in governing docs/decision logs. Baseline unit/type/lint evidence, collected MySQL test inventory and draft OpenAPI contracts. |
| P1: authenticated boundaries | Identity gateway verification for tenant and platform surfaces; signed platform authority, fresh authentication where required; nginx separates management, probes and callbacks; permissions/roles/seeds. Standard missing-auth and validation errors. | Real credential-to-gateway-to-service tests; missing auth 401, denied 403; forged/stale context, non-operator with matching keys and impersonated writes rejected. Existing tenant and voucher paths remain usable. |
| P2: ownership and safe migration | Notification space model/session guard; matching models, schemas, fixtures and migrations; backfill existing rows into tenant spaces; provision platform space explicitly. Add composite ownership constraints and versioned ingress target resolution. | Two tenants plus platform space isolation on every table; operating-tenant ordinary users cannot read platform rows; cross-space associations and forged ownership rejected. MySQL upgrade/downgrade, interrupted-upgrade and concurrent-write checks. |
| P3: providers, channels and senders | Registered provider capability catalogue, typed channel settings, complete provider/sender lifecycle, scoped credential bindings, validation/sync jobs, readiness and rotation workflow. | Each channel can be configured through APIs without SQL edits; tenant cannot resolve platform credentials; unsupported pairs fail before IO; unverified/disabled senders cannot send; provider timeout does not hold DB transaction open. |
| P4: templates and purpose assignments | Complete template reads/lifecycle, strict variable/channel schema validation, payload-inclusive content identity, locked version allocation, activation replacement/rollback, previews and explicit use-case/trigger bindings. | Platform/tenant templates with identical keys cannot collide or override one another. Deterministic company/tenant and locale selection; wrong-purpose/schema binding rejected; concurrent versions and activations safe on MySQL. |
| P5: routing and durable planning | Typed routing, effective-policy explanation, durable per-channel planning outcomes, snapshot lineage, disabled-candidate rejection, configuration concurrency controls and independently enabled channels. | Every requested channel has a visible reason; replay creates one effect; no route/template ambiguity; no implicit cross-owner/channel fallback. Current revocations block scheduled sends and retry without changing historical content. |
| P6: provider send/receipt completion | SES/SNS, Twilio and Meta onboarding, native signatures, callback routing, trustworthy approval sync, structured WhatsApp payloads, endpoint health/suppression projection and bounded ingress. | For each channel: accepted, delivered, permanent failure, throttling, delayed/duplicate/out-of-order callback and unmatched reconciliation fixtures. Invalid trust rejected. Live account/callback certification remains separately evidenced. |
| P7: producer adoption and operations APIs | Platform staff/pre-tenant producer path; adapt Identity invitation and existing Vouchers/Accounting contracts without breaking tenant workflows. Add approved platform event producers in small batches. General details/timeline, idempotent retry and reconciliation, retention and publisher/runtime wiring. | Platform invitation works with no customer tenant configuration; tenant voucher uses only its own assignment. Rollback leaves no send/audit effect; no business/money transaction calls Notification. Retention scrubs request variables and attachment metadata as well as content. |
| P8: release evidence and activation | Generated OpenAPI and TypeScript consumers; MySQL migration/isolation/concurrency/EXPLAIN suite; broker replay/DLQ/restart, ambiguous send recovery, quotas and alerts. Final simplification/security review and operations update. | Domain/shared coverage >=90%, affected service tests and consumers green, Ruff/strict mypy clean. Per-channel non-production canary then deliberate production activation with disable/rollback procedure. |
| P9: administration UI | Platform and tenant screens consume the proven APIs: channel readiness, provider/sender setup, templates/assignments and delivery evidence. | Permission and accessibility tests plus form/error states; UI cannot introduce authority or provider behavior absent from the APIs. |

P1/P2 precede platform mutations. P3/P4 precede effective policy and dispatch changes.
P6 and P7 both finish before P8 activation. P9 is deferred until the API behavior is
stable; the three requested channels are required backend outcomes, not optional
follow-up work. Extra provider vendors and push enhancement are separate scope.

## 7. Migration, regression and release details

Keep existing IDs, evidence and local paths. Add columns nullable first where needed,
backfill in restartable bounded batches, validate ownership/constraints, then enforce
NOT NULL and switch readers/writers through an explicit compatibility period. Account
for callbacks and in-flight workers during backfill. Each revision performs one DDL
statement and ships its matching model; seeds stay outside migrations.

Current revision 0026 contains two ALTER statements plus a backfill in one revision,
contrary to the repository's one-DDL rule. Inventory applied deployment state in P0;
do not rewrite an applied migration casually. New work follows the rule and supplies
an explicit recovery procedure for existing partial states. Do not assume migration
numbers until concurrent repository work is checked.

Do not mutate a published event in place. Existing broker validation only accepts
schema version 1, so new platform/space contracts need an additive event type or
coordinated version-aware validator and producer/consumer rollout. Include signed
execution ownership, purpose and permitted recipient reference; do not trust a payload
that merely claims `source_service=identity`. Avoid a global source key that can name
any customer tenant. Preserve original `message_id` through retries and compatibility
translation, including processed-message receipts and encrypted context binding.

P2 tests must exercise reads, direct `get`, writes and parent-child references across
two customer tenants and platform/tenant spaces in the same operating tenant. P4/P5
tests cover effective-date boundaries, requested/default locale, multiple templates
for one event, schema errors, scheduled activation and no valid assignment. Provider
tests use native signed fixtures, not only custom generic signature headers. Collected
MySQL tests must exercise real row locks, concurrent activation/version allocation,
worker claiming, retry and callback races; SQLite cannot certify these properties.

Attachments remain explicitly unsupported for external delivery until private artifact
handoff and scanner authority exist. Current registration/scan APIs must not let an
ordinary template manager assert a file is clean or imply attachment bytes were sent.
The original invoice/voucher attachment release gate remains independent.

Separate configuration validation, planning completion, provider acceptance and final
delivery in responses and metrics. Track queue/outbox age, callback trust failures,
per-account throttling/errors, unknown outcomes, no-route/template reasons and stale
provider approvals. Per-space/channel limits, provider rate limits and bounded retries
prevent one tenant or failing provider from exhausting dispatch capacity. Never infer
monetary charges from attempt counts; commercial billing is separate work.

No implementation phase is complete until transactional audit and its actual publisher
path are verified. Audit contains IDs and safe state changes, never destinations,
invitation URLs, rendered content or secret values. Review logs, previews, failures,
exports, callback payload retention and support access, not just CRUD happy paths.

## 8. Decisions and remaining inputs

Recorded requirements: all three requested channels; platform and tenant administration
separate; different purposes/triggers/templates allowed; platform staff and pre-tenant
recipients included; API-first phased implementation.

Proposed design decisions for P0: configuration spaces with a real operating-tenant
owner; mandatory session space isolation; platform delivery evidence stays in platform
space; code-registered use cases with explicit template assignments; no implicit shared
fallback; existing adapters remain the initial provider baseline.

Before affected activation, identify the installation operating tenant, exact first
platform events and approved recipient authorities; available secret store/onboarding;
actual provider accounts, callback domains and destination markets; and whether the
platform will grant subsidized transport for tenant business messages. These inputs
do not prevent P0 investigation/contract work. Default proposed first release is
platform invitation plus existing tenant voucher communication, followed by separately
registered platform operational events. No campaign engine, two-way inbox or arbitrary
tenant-defined event execution is included.

Review of this proposal: preserve tenant/audit/outbox invariants and existing category
policy; expose the new platform/space boundary as an explicit ADR rather than an
undocumented exception. `/simplify` and `/security-review` slash tools are not exposed
in this session; an explicit design security/simplification pass was performed. Findings
are the ownership, credential-reference, gateway/callback trust, deterministic selection,
evidence visibility and verification gaps listed above. Application code was not changed.
