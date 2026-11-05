# Platform and tenant notifications: execution TODO

Authorized 2026-10-22: implement the accepted API-first plan sequentially, maintain
this record and perform two final review/fix passes. Existing unrelated edits are
preserved. No commit, publication or live channel activation was requested.

Status: `[ ]` pending, `[~]` in progress, `[x]` locally verified, `[!]` external gate.

- [x] P0: accepted contracts, ownership ADR, baseline and regression inventory.
- [x] P1: authenticated platform/tenant gateway and permissions.
- [x] P2: configuration spaces, migrations and session isolation.
- [x] P3: channel/provider/sender lifecycle and safe credentials.
- [x] P4: template lifecycle, preview, validation and purpose assignments.
- [x] P5: deterministic routing, durable planning and effective policy.
- [x] P6: native email/SMS/WhatsApp provider and callback workflows.
- [x] P7: platform/pre-tenant producer ingress and delivery operations.
- [x] P8: generated contracts, database/runtime verification and release controls.
- [x] P9: administration UI after the API contracts are verified.
- [x] Review 1: security/correctness review, regression tests and fixes.
- [x] Review 2: independent fresh code pass, regression tests and fixes.
- [!] Live provider canaries/production activation require real accounts, callback
  domains and explicit activation configuration; never infer success from fixtures.

## Accepted implementation decisions

- Platform space belongs to a configured real operating tenant. Tenant space IDs
  equal their owning tenant IDs to support deterministic existing-data backfill.
  Platform space ID is configured separately and must differ from the tenant ID.
- Tenant and space isolation are mandatory in sessions; platform grants do not
  confer access to customer business notifications.
- Platform staff/pre-tenant recipients are included. Their source-authorized
  endpoint snapshots and execution evidence live in the platform space.
- Existing adapters are the vendor baseline. Tenant secrets use operator-registered
  owner-bound references; arbitrary environment names are never tenant authority.
- First integrations: platform invitation and existing tenant voucher workflows.
  Other platform events require registered producer contracts before activation.
- Preserve current category policy, including documented security bypass, until a
  separate approved policy amendment. External attachments remain disabled.

## Evidence

- Investigation baseline: notification suite 104 passed; no collected MySQL tests.
- `/simplify` and `/security-review` slash tools are unavailable. The two final
  passes will explicitly review simplification and CLAUDE.md sections 5 and 6.

- P1/P2 checkpoint: 107 Notification tests and 30 affected Identity platform/setup/role
  tests passed. Missing actor context now returns 401 (previously framework 422).
- Added strict partition-aware request/worker sessions and composite tenant/space
  foreign keys. New regression covers identity-map lookup and same-operating-tenant
  platform isolation. Existing worker maintenance paths use explicit audited scans.
- P3-P5 checkpoint: nine new catalogue/configuration/planning tests passed, including
  owner-bound credential references, asynchronous idempotent provider checks, durable
  disabled-channel reason, explicit purpose assignments, typed variables and HTML escaping.
- Native callback checkpoint: 19 affected callback/space/management tests passed with
  real RSA-signed SNS fixtures, native Twilio headers and provider-authoritative approval.
- MySQL 9.6 disposable loopback instance started with the repository test launcher.
  Test fixture creates and drops a random `notification_test_*` schema, never the
  application schema. Migration upgrade/downgrade and a wrong-space FK test passed.
  That run found and fixed BLOB digest indexing and quoted-key downgrade defects.
- Checkpoint mypy passed 54 Notification source files; final evidence below supersedes it.
- Permission names use the existing maximum of three segments, e.g.
  `platform.notification_provider.read`, rather than introducing four-segment keys.
- API behavior intentionally tightened: provider references must be registered for
  their owner; template managers cannot self-approve provider templates or malware
  scans; external attachment association fails explicitly until transport exists;
  manual retries require an idempotency key and retained, unexpired content.

- P2-P7 implementation includes 90 additive revisions after the preserved 0026,
  all-table ownership fences, native signature verification, ordered WhatsApp
  text header/body/URL-button components, encrypted provider payload snapshots,
  assignment lineage, dispatch admission limits and an authenticated audit publisher.
- P9 initial verification: 33 affected UI/proxy/policy tests passed; console TypeScript
  passed. Template/route forms, paging, error states and realm cancellation are under
  final regression verification.
- Edge checks repaired ended-assignment fallback, inactive-locale fallback,
  malformed provider responses, post-read complaint suppression and unsafe receipt
  linking. Retry/activation command keys survive failed HTTP responses.
- The shared suite exposed a stale exemption inventory test: the four existing global
  reference tables were already documented and implemented. Its expected set now
  matches that existing policy; no new tenant exemption was introduced.


## Final review 1 - completed

Walked CLAUDE.md security/correctness requirements and simplified the shared partition
and list-query mechanisms. Review and fixes were performed explicitly because slash
review tools are unavailable. This is a code review by the same agent, not an external
or delegated review.

- Fixed ended-assignment legacy fallback and executable default-language resolution.
- Added safe owner checks on identity-map reads without silently refreshing away
  unflushed changes. Shared session/partition regressions pass.
- Rotation invalidates account/sender verification; reactivation requires verification.
- Complaints/hard bounces suppress future delivery even after a terminal/read outcome.
- Reconciliation requires a signed receipt with an attempt-proven message identity.
- Platform channels start disabled; platform recipient reference lookup is serialized.
- Platform Notification audit evidence is withheld from ordinary tenant Audit views;
  exact platform families select its safe evidence.

Evidence: MySQL upgrade/backfill replay/downgrade, per-table isolation and concurrent
version/activation tests passed. The real RabbitMQ Notification-to-Audit test passed
with full local broker restart, publisher confirms, redelivery/dedupe and forged-event
DLQ handling. The shared suite passed 1,096 tests at 94.19% coverage after the session fix.

## Final review 2 - completed

Fresh pass through ingress -> planning -> dispatch -> callbacks -> retention, plus
management/proxy/UI and migration/runtime wiring.

- Checked approved WhatsApp body content and ordered component positions against the
  local version, rather than treating approval status alone as content evidence.
- Rejected malformed/oversized native callback identities before network or DB work.
- Preserved signatures' original query inputs while removing them before upstream
  access logging; nginx also disables callback access logs and bounds ingress.
- Kept late receipts from a prior attempt out of a manual retry's current state.
- Recorded expired/render-invalid planning outcomes and bounded corrupt-payload handling.
- Matched descending keyset tie-breakers to index order and versioned cursor bindings.
- Native MySQL concurrent claiming/admission passed; optimizer format verification was
  corrected to use explicit TRADITIONAL output on MySQL 9.6.
- nginx's actual Windows binary validated the changed local routing configuration.
- Console request history now exposes skipped-channel planning reasons; all growing
  screen lists have cursor controls, and realm changes discard delayed responses.

- Recovery follow-through: added native attempt references to SES/Twilio/Meta,
  owner-scoped paginated receipt inbox/detail APIs, and automatic resolution of
  ambiguous sends from signed attempt-correlated receipts. Tests cover a native
  RSA-signed SNS receipt arriving before finalization, preservation of its proof
  after an unknown HTTP outcome, and native MySQL callback/finalization locking.
- Corrected SES message-tag encoding to obey AWS's allowed character set; a colon
  is represented by an underscore on the wire and decoded from signed receipts.
- Quarantined unavailable Meta batch payloads instead of trusting a first-message
  projection, and used delivery-before-attempt locking consistently in normalization.


## Final evidence and remaining activation gate

- [x] All local phases P0-P9 and both manual review/fix passes are complete.
- [x] Notification: 196 passed, including native MySQL; domain coverage 98.80%.
- [x] Shared platform: 1,096 passed; coverage 94.11%.
- [x] Identity: 36 affected tests passed; Audit: 185 passed / 9 external opt-in skips.
- [x] Real RabbitMQ Notification audit restart/redelivery/dedupe/DLQ case: 1 passed.
- [x] Console: 66 affected tests passed; console and generated-client typechecks passed.
- [x] Generated client: 8 tests passed; OpenAPI and audit-contract checks passed.
- [x] Ruff and strict mypy passed; migration head 0116 / 112 paths / 144 operations.
- [x] nginx configuration and worker launcher checked; disposable test processes stopped.
- [!] Live provider and identity-provider/gateway canaries, environment-specific query
  benchmarks, actual application migration/deployment and deliberate production dispatch
  activation require the installation's real accounts, credentials and HTTPS domains.
  They were not represented as completed by the local fixture runs.

See [both review records](notification-platform-tenant-reviews.md) and
[operations/configuration](notification-operations.md) for fixes, commands, compatibility,
release controls and exact verification limits. Existing unrelated edits remain preserved.

Final provider consistency check: SES validation now requires the same explicit region
that dispatch requires; its focused provider/lifecycle suite passed 6 tests, including
the additional missing-region regression. The consolidated run above contained 196
cases before this additional regression. Ruff and strict mypy were rechecked afterward.


## Additional end-to-end review (requested after implementation)

- [x] Trace ownership, gateway authorization, configuration jobs and audit visibility.
- [x] Trace ingress, planning, dispatch admission/finalization, native receipts and recovery.
- [x] Review console/proxy contracts, migrations and runtime wiring.
- [x] Fix findings and add meaningful regression coverage.
- [x] Rerun affected checks and record evidence and remaining live activation gates.

Fixes cover Meta inspection integration, claim-time eligibility/correlation allocation,
late finalization across manual retry cycles, signed-receipt precedence, stale sender
verification, conflicting callback identity assignment, worker cleanup locking and the
deployment example port. New integration tests join native SMS/WhatsApp transport,
callback normalization, API history and tenant isolation. See the additional final
review in [the review record](notification-platform-tenant-reviews.md).

Additional final review verification: **215 Notification tests passed**, no skips,
including all three native MySQL cases; domain coverage **98.80%**. Identity 36, Audit
34, shared guard/query 2, console 66 and generated client 8 tests passed. TypeScript,
Ruff, strict mypy, contract export/generation and actual nginx HTTP checks passed.
The temporary nginx/mock processes and disposable MySQL process were stopped.
Provider/IdP/HTTPS canaries and deliberate application deployment/activation remain
external gates; no live send, application migration, commit or publish was performed.
