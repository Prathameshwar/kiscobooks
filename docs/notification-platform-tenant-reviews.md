# Notification implementation: two final reviews

Both reviews walked CLAUDE.md sections 5 and 6 and the accepted phased plan. These
were separate manual passes by the same agent; no external or delegated review is
claimed. `/simplify` and `/security-review` are not available in this environment.
Their security and simplification checks were performed explicitly.

## Review 1: ownership, authorization and deterministic configuration

All findings below were fixed and regression-tested:

- Tenant and platform identity-map reads needed both owner checks. Pending changes
  must survive a lookup; clean lock-taking reads must refresh current evidence. The
  new partition session opts into pending-change preservation, while other services'
  default guarded-session refresh behavior remains unchanged.
- Ended purpose assignments could accidentally restore a legacy template. Assignment
  history now disables that fallback; a missing executable requested language can use
  an active default-language version. Overlapping/ambiguous candidates fail closed.
- Provider identity rotation needed to invalidate account and sender verification.
  Reactivating a sender also resets verification; remote results cannot overwrite a
  configuration changed during the check.
- Complaints and hard bounces must create suppression even after a read/terminal
  delivery. Historical receipts cannot mutate a newer retry cycle.
- Provider receipts could not be attached solely because they belonged to the same
  provider. Reconciliation now requires proven message/attempt identity and a stable
  idempotency receipt.
- Platform channels require explicit enablement. Source recipient references bind
  one destination per channel, under a space lock; platform ownership excludes
  missing, equal and sentinel IDs.
- Notification audit evidence needed the same platform boundary as its source rows.
  Safe realm/space context now drives separate tenant and exact platform read surfaces.

## Review 2: native providers, recovery, privacy and operability

All findings below were fixed and regression-tested:

- WhatsApp approval status alone was insufficient content evidence. Sync now compares
  provider body text and positional text header/body/URL-button parameter structure
  with the local immutable version. Named/media payloads are explicitly unsupported.
- Native callback parsing needed bounded identities, typed SNS envelope fields,
  safe malformed-response handling and no match on a missing provider message ID.
- Callback query values could leak through upstream access logs even when nginx
  access logging was disabled. The ASGI boundary retains original signing inputs
  during verification and redacts queries before response logging and error handling.
- Unknown sends needed native proof for recovery. Outgoing SES tags, signed Twilio
  callback URLs and Meta opaque callback data now carry the attempt reference. A
  verified receipt can resolve an ambiguous attempt without resending, including a
  receipt arriving before HTTP finalization. Finalization preserves that receipt's
  provider identity and terminal state. Native MySQL tests exercise this race.
- SES tag values cannot contain colons. The provider adapter uses underscore encoding
  and the signed receipt decoder restores the local UUID/attempt reference.
- Recovery required discoverable evidence. Owner-scoped cursor-paged receipt inbox
  and detail APIs expose safe identifiers/states, with a console inbox view.
- Meta batch receipts cannot be reconstructed from a first-message projection after
  raw-payload purge. Such rows are quarantined. Unverified rows cannot normalize.
- Lock order is consistent for delivery/attempt finalization and receipt matching;
  management reconciliation takes the inbox lock before the delivery lock.
- Expired requests and invalid template values now retain per-channel planning reasons.
  Corrupt retained payloads leave the due queue safely; unknown sends remain held.
- Descending keyset tie-breakers now match index direction and use a versioned cursor
  binding. Screen lists retain opaque cursors and clear stale realm/provider results.
- SES validation requires the explicit dispatch region, so it cannot report a
  transport ready by using an implicit SDK region that dispatch would reject.
- Generic server failures use a redacted envelope; SQL parameter logging is disabled
  on the API engine. Provider errors and destination/content data stay out of logs.

The final inspection found no further local blocking issue in the implemented scope.
Live account/callback certification and deliberate production activation remain gates.

## Verification

- Notification: **196 passed**, including all three native MySQL tests; domain coverage
  **98.80%**. The tests cover migrations through **0116**, restartable backfill replay,
  downgrade, actual column/nullability parity, every owned table's tenant/space isolation,
  composite foreign keys, concurrent versions/activations, admission/claiming and the
  receipt-before-finalization race. EXPLAIN checks the delivery keyset index's availability;
  this is not a production-distribution benchmark for every query shape.
- After that consolidated run, the missing-SES-region regression was added; the
  focused provider/lifecycle suite passed **6 tests** and Ruff/mypy were rechecked.
- Shared platform: **1,096 passed**, **94.11%** coverage after the session fix; strict mypy
  and Ruff passed for the changed shared modules.
- Identity: **36 affected tests passed** for platform/setup/roles/gateway and the encrypted
  platform producer; the producer's final sentinel check also passed its focused test.
- Audit: **185 passed, 9 skipped**. The skips were seven opt-in broker cases and two
  Docker-only Audit migration tests. The Notification-to-Audit broker case was separately
  executed against local RabbitMQ with a full restart: **1 passed**, checking mandatory
  confirms, missing-route retry, durable redelivery, dedupe and forged-message DLQ.
- Console: **66 affected tests passed**; console TypeScript passed. Tests include both
  pages, permission gates, validation/error/pending states, previews/activation retry,
  cursor paging, receipt/planning views, stale-response cancellation and proxy CSRF.
- OpenAPI: **112 paths / 144 operations**. Export checks and generated Notification
  TypeScript checks passed; API-client typecheck and its **8 tests** passed.
- Notification Ruff and strict mypy passed all **58 source files**. Changed Identity and
  Audit modules also passed their targeted Ruff/mypy checks. All 11 main project lockfiles
  resolve the shared platform version **0.37.1**.
- The actual Windows nginx binary accepted the updated local routing configuration;
  the Windows worker launcher parsed successfully. Checks used temporary ignored config
  files and disposable test schemas. The started RabbitMQ/MySQL test processes were
  stopped; application schemas, the installed MySQL service and local paths were preserved.

No application database migration, live provider send, production activation, commit or
publication was performed. The API/UI changes are local and reviewable.

## Provider contract references checked during review

- [Twilio native webhook signatures](https://www.twilio.com/docs/usage/webhooks/webhooks-security).
- [AWS SNS native signature verification](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html).
- [SES v2 message-tag constraints](https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_MessageTag.html).
- [Meta's template-component collection](https://www.postman.com/meta/whatsapp-business-platform/request/lwtlz1k/send-message-template-interactive).
- [AWS's official messaging sample documenting WhatsApp opaque callback data](https://github.com/aws-samples/Engagement-Database-And-Analytics-Sample-For-End-User-Messaging-And-SES).

Meta's direct reference pages returned HTTP 429/unavailable during this session. Its
published collection and the official AWS sample support the implemented contract;
actual Meta account/API-version certification remains part of the live canary gate.


## Additional final end-to-end review (2026-10-22)

Requested after the implementation and original two passes. This is a fresh manual
review by the same agent, not an independent reviewer. It walked CLAUDE.md sections
5 and 6 again; the unavailable `/simplify` and `/security-review` commands were
replaced by explicit simplification and security checks.

### Findings fixed

| Severity | Finding and resulting behavior | Regression evidence |
|---|---|---|
| High | Meta inspection shadowed the local TemplateVersion with the Graph version and used a different branch's local `matches` value as a callable. Approved bindings could never complete the actual content check. Distinct variable names and an explicit imported matcher now connect provider approval to the immutable local version. | Real inspection function with mocked HTTP responses accepts matching approved content and rejects mismatched content, including a configured Graph version. |
| High | Time/content eligibility was checked while preparing a message but not at the final claim. Admission now samples time after obtaining the delivery lock, checks schedule, backoff, request/content expiry and purge, and allocates the native attempt reference under that claim. | Five time/content gates assert no network call or attempt consumption; canonical claim references are asserted. Native MySQL capacity/recovery evidence now makes the deferred delivery due before recovery. |
| High | A failure receipt could allow a manual retry while the original HTTP call was still finishing. Its late finalization could resurrect a pending retry or overwrite a newer attempt's message ID. Finalization now completes only historical attempt evidence when the attempt number or manual-retry boundary has changed. | Two tests reproduced the incorrect state/identity before the fix, then passed with the retry still pending and with the next attempt already accepted. |
| High | A contradictory HTTP message ID or failure could overwrite identity/state already proven by a signed receipt. The receipt remains authoritative; contradictory transport evidence is recorded as unknown with `provider_result_conflicts_with_receipt`, without enabling a resend. | Signed SNS receipt before finalization tested against unknown, conflicting accepted ID, permanent failure and retryable failure HTTP outcomes. |
| Medium | Sender checks compared only the provider snapshot. A sender disabled and reactivated during network IO could be reverified by an old job. Finalization now locks and compares the sender revision too; successful verification updates its revision. | A job's mocked remote check performs both real sender API mutations; its stale result fails and the active sender remains unverified. |
| Medium | A conflicting native correlation could mutate the attempt before rejecting the receipt. Consistency checks now precede all identity assignment. Provider-configuration failure cleanup also takes the delivery lock before checking whether it is still queued. | Conflicting receipt leaves the current delivery and attempt identity untouched, and parks the receipt unmatched. Existing dispatch/worker tests remain green; cleanup lock order was inspected. |
| Medium | A recipient destination or provider configuration could change after preparing content/building the adapter. Final admission now checks destination identity and the worker's provider revision; obsolete transports defer without consuming an attempt, and stale configuration-error cleanup cannot fail a newly corrected provider. | Destination change fails before IO; a changed provider revision leaves the delivery pending with no attempt and requires rebuilding the transport. |
| Low | The deployment example used Notification port 8007 while the configured service default is 8010. The example now matches the runtime registry. | Configuration inspection and actual Windows nginx HTTP smoke with isolated temporary upstreams. |

### End-to-end paths inspected

- Signed Identity gateway authority, exact platform method/path binding, fresh platform
  mutation authority, support restrictions, permission families and object/company gates.
- Partition session queries, cached gets, writes and composite foreign keys; separate
  platform roots in a real operating tenant, including staff/pre-tenant ingress.
- Credential ownership, provider/sender setup, purpose assignment, immutable rendered
  payloads, locale fallback, planning outcomes and dated activation behavior.
- Claim/admission, transport outside SQL transactions, retry limits, ambiguous results,
  signed receipt capture, monotonic normalization, manual retry and reconciliation.
- Transactional audit/outbox selection, platform evidence visibility, encrypted content
  retention and recovery behavior; prior broker restart evidence remains applicable.
- Console permissions, proxy path allowlist and same-origin checks, cursor handling,
  idempotency/body retention and generated API contracts.
- Existing migrations through 0116, legacy backfill/rollback, Windows worker wiring and
  nginx management/callback/health/internal routes.

The new SMS and WhatsApp round trips join the planner, stored-content assembly, actual
provider adapter with mocked remote HTTP, native signed callback ingress, asynchronous
normalization, management detail/history and cross-tenant denial. They verify frozen
content/WhatsApp parameters survive later local changes. These are local integration
tests, not real Twilio or Meta sends.

### Verification for this additional review

- Notification final consolidated rerun: **215 passed**, no skips, including all three
  native MySQL migration/concurrency tests; **98.80% domain coverage**. This run includes
  every additional fix and regression described here (97.45 seconds).
- Identity: 36 affected tests passed. Audit: 34 platform-history tests passed.
- Shared partition/query regressions: 2 passed. The shared implementation did not change
  in this review; the prior 1,096-test full-suite evidence remains recorded above.
- Console: 66 affected tests passed and TypeScript passed. Generated client: 8 tests,
  typecheck and Notification generation check passed.
- Notification Ruff passed the source tree and changed/new test files; strict mypy
  passed all 58 source modules. OpenAPI and audit-contract export checks passed; no contract regeneration
  was needed for these internal fixes.
- Actual Windows nginx HTTP smoke passed using the current routing config and
  disposable loopback mock upstreams: GET/POST/PUT/PATCH/DELETE original method/path
  forwarding; forged actor-header replacement; native callback header/query forwarding;
  public health without authorization; internal-path denial. This adds HTTP behavior
  evidence to the earlier syntax check, without replacing real IdP/HTTPS canaries.

The disposable MySQL process and temporary nginx/mock upstream processes used for this
review were stopped. The installed MySQL service and application schemas were untouched.

No remaining blocking local finding was identified in the reviewed scope after these
fixes. Production activation still requires actual application migration, provider/IdP
accounts, registered senders/templates, HTTPS callback canaries and environment-specific
query benchmarks. No live provider send, application-schema migration, commit or
publication was performed.
