# Accounting and Audit integration plan

Status: accepted and implemented, 2026-09-17. All seven phases and both review/fix passes
are complete. See [execution and reviews](accounting-audit-integration-review.md) for measured
results and deployment boundaries.

## Outcome

An authorized Accounting change commits its audit evidence atomically, reaches Audit's
immutable store through authenticated asynchronous delivery, and can be found through the
authenticated Audit API and existing console. Failures are visible and recoverable without
duplicating accounting effects or audit rows.

The existing architecture remains: Accounting database transaction -> Accounting outbox ->
RabbitMQ -> Audit consumer -> Audit database. UI/server adapters use the Audit read API.
Accounting posting, balances and business authorization use authoritative Accounting data.
Local `MasterRevision` history continues to support existing Accounting history consumers.

This plan covers Accounting, the shared delivery mechanisms where necessary, Audit, the
Identity/gateway read boundary, the generated client, the existing audit console and runtime
scripts. It adds no service or datastore and does not build new Accounting administration
screens. Existing local paths and the configured folder-mapped publishing workflow remain.

## Starting point and findings

These are repository inspection findings, not proof of the running deployment's state.

| Finding | Evidence | Consequence |
|---|---|---|
| Accounting stages revisions and audit outbox rows in its database transaction. | `apis/accounting/src/accounting/tasks/commands.py`, `audit()` | Preserve this mechanism and extend its coverage. |
| Accounting puts a short verb such as `update` in `payload.action`; Audit requires `payload.action == envelope.event_type`, e.g. `accounting.party.update`. The transport signs and forwards the original body without normalization. | Accounting `commands.py`; Audit `tasks/consume.py`, `receive_audit()`; shared `broker.py` | Current Accounting-produced events fail the consumer contract even if the broker confirms publication. This is the first implementation priority. |
| The live-broker test includes an Accounting case but constructs its payload with the full event name directly. | `apis/audit/tests/test_live_rabbitmq.py` | It does not exercise the mismatched production Accounting emitter. Add an actual command-to-consumer test. |
| Accounting records changed-field markers rather than old/new values, and its generic helper does not forward a reason or trace ID. | Accounting `commands.py`, `audit()` | The trail identifies changed fields but does not fully explain a change or correlate it with a request. |
| Accounting export routes return protected data without emitting an access event. | `apis/accounting/src/accounting/api/workflows.py`, `export_records()` | Export activity is missing from the audit trail. Sensitive read coverage also needs a route inventory. |
| The Accounting publisher defaults to 12 attempts; the shared selector stops selecting exhausted rows. | Accounting `tasks/audit_publisher.py`; shared `delivery.py` | Recovery and alerts must explicitly cover exhausted rows as well as broker dead letters. |
| The local service launcher starts HTTP services; Accounting documents its publisher as a separate process. | `start/win/start-services.ps1`; Accounting README | HTTP readiness alone does not prove audit delivery is operating. |
| Audit verifies signed actor headers, while the configured `/audit/` gateway route has no Identity authorization subrequest. | `apis/audit/src/audit/api/auth.py`; `start/win/conf/bill.conf` | Complete the trusted user authentication bridge before connecting the console to live Audit reads. |
| The console audit page still uses sample audit data. Its change type assumes every field has before/after strings. The generated API client currently covers Identity, Catalog and Accounting. | Console `app/audit/page.tsx`, `app/lib/audit-trail.ts`, `app/lib/audit-events.ts`; client `scripts/generate.mjs` | Add an Audit client and live, paginated reads with legacy marker support. |
| Audit exports stage `audit.exported` with short action `exported`; an Audit-owned publisher is not present in the inspected source. Company scope is placed in context rather than the top-level audit scope. | Audit `api/routes.py`, `export_audit_events()` | Complete the export's own delivery and scope as part of the read/export integration. |

The earlier review ran five targeted Accounting tests successfully. Those tests did not verify
production Accounting payload ingestion, live MySQL/RabbitMQ delivery or the console path.

## Phase 1 - Agree the event, privacy and compatibility contracts

Deliver an Accounting event matrix mapping every implemented command and sensitive read/export
to its event name, category, entity, authoritative tenant/company, actor, transaction boundary,
permitted evidence and expected event cardinality. Cover masters, templates, metadata upgrades,
imports, mapping drafts, fiscal transitions, journals, openings, source documents, allocations,
credit reservations/overrides and charges. Derived rows can be represented by their parent
event when the matrix makes that coverage explicit.

Accepted decisions for this plan:

- New audit payloads use the registered full event name as `action`, matching the current
  authenticated consumer. Local Accounting revisions retain their existing short actions.
- Legacy Accounting events may be accepted only through an explicit, issuer- and version-bound
  mapping of known event names to their original short actions. Preserve original evidence;
  do not weaken source/route authentication or accept arbitrary suffix matches. Define the
  ingestion representation and fixtures before implementing the adapter.
- Define a per-resource allowlist for before/after values. Unknown or sensitive values remain
  markers/redactions. Money is serialized exactly with currency context; no float conversion.
  Personal names, contact data, raw bank details, tax identifiers, secrets and arbitrary custom
  values never enter durable audit evidence. Free-text reasons need an explicit privacy policy;
  use a safe reason code or reference when unrestricted text cannot be retained safely.
- Current field read-denies must hold in Audit detail, activity and export views as well as
  Accounting history. Specify how trusted policy context is resolved outside money transactions.
  Preserve stored chain evidence while redacting the response; document that a redacted response
  is not a complete independently verifiable copy of the original hash input.
- Paginated Accounting exports emit one access event per successfully served page, with a
  bounded returned-row count and safe resource/scope metadata. Separate HTTP requests remain
  separate access events. Ordinary reads remain unaudited; inventory bank/tax/payment detail
  access against `docs/audit.md` section 5.3. An event describes data served, not proof a user
  saved a file. A file export receives a run identity and signed expiring download if introduced.
- Keep existing Audit permissions and Accounting history permissions distinct. Tenant-wide
  Audit reads require tenant authority; selecting a company never grants access to that company.
- Keep historical rows immutable. Missing past values, actors or company attribution cannot
  be reconstructed by guessing from today's business records.

Reconcile the governing docs and decision logs, including dated statements already superseded
by implemented authenticated delivery. No new schema is assumed: first check existing JSON and
correlation columns. Any necessary DDL gets a model/schema/test plan with one statement per revision.

Exit: reviewed event/evidence matrix and explicit compatibility, field-policy and export
semantics. Every unresolved design choice is recorded before dependent application work.

## Phase 2 - Repair and prove the Accounting-to-Audit contract

First write a regression using an event produced by the actual Accounting command path, capture
the outbox body and pass it through the actual signed transport and authenticated Audit consumer.
Confirm the current failure is the action mismatch. Align new emissions with the agreed contract
and implement only the bounded legacy compatibility from phase 1.

Exercise every registered implemented action through contract tests and representative commands
through ingestion. Validate event type, payload action, entity, company, actor, schema version,
broker identity and issuer/audience. Keep financial business events separate from audit routes.
Audit authenticates and validates before database access, commits its row and inbox before ACK,
and retains the single chain writer and message-ID deduplication.

Prepare a read-only inventory for old pending, exhausted and dead-lettered Accounting events,
including broker-confirmed events not known to be ingested. Preserve original event IDs,
message IDs, timestamps and evidence during recovery. Never reset all outbox publication state.

Exit: production-shaped new and supported legacy events persist once; transaction rollback
leaves no audit outbox row; command replay adds no duplicate mutation events; forged or mismatched
messages are rejected. No prebuilt test payload can substitute for the command-path regression.

## Phase 3 - Complete evidence and access-event coverage

Capture permitted before/after values before mutating ORM objects, then emit alongside the
business change and existing revision. Apply the same contract to create/update, transitions,
imports, template operations and background work. Record authoritative original/effective actors
for impersonation and explicitly identify system work. Carry validated request/trace correlation
and agreed reason evidence through shared mechanisms rather than duplicating helpers.

Add the planned Accounting export and sensitive-read access events using the existing local
transaction/outbox. Keep access events distinct from `MasterRevision` business edits. For import
preview, all tentative business and audit evidence rolls back. Verify category choices against
the event matrix instead of treating every lifecycle shape as a sufficient category policy.

Update Audit consumption, policy projection and client contracts for any richer payload shape in
the same phase. Preserve old marker-only events and nullable correlation fields. If the shared
library changes, bump its version and update every consuming service's lockfile.

Exit: matrix coverage is complete; exact safe values explain a representative financial change;
redacted fields stay redacted in storage and responses; exports/sensitive reads create access
events; denied requests and failed transactions do not create success evidence.

## Phase 4 - Make delivery operable and recoverable

Add repeatable worker start/stop/status configuration alongside existing local service scripts.
Run the Accounting audit publisher, the Audit consumer and the Audit export-event publisher as
separate supervised processes. Reuse the shared publisher. New background launches are hidden,
idempotent and tracked without putting secrets in command lines or logs. HTTP startup remains
independent of worker execution; status distinguishes HTTP readiness from delivery health.

Provision or validate durable queues/exchanges, exact event bindings, dead-letter routing,
least-privilege broker users and signing-key rotation. Consumer credentials/bindings supporting
new events must be deployed before producers emit them. Broker confirmation indicates broker
acceptance; only Audit persistence demonstrates ingestion. Verify database grants preserve
append-only audit rows while permitting required outbox/inbox infrastructure operations.

Expose bounded operational checks for pending count/age, exhausted attempts, dead letters,
consumer availability and ingestion lag. Supply an explicit, scoped recovery command/runbook
with a dry-run inventory and preserved message IDs. Exercise recovery in isolated infrastructure;
any real backlog replay uses a reviewed inventory and rollout authorization. Wire existing
partition maintenance and chain verification with appropriate separate credentials, and ensure
their scans are bounded sufficiently for the expected dataset.

Exit: repeated start/stop is safe; an Audit outage does not prevent Accounting commits; messages
recover after reconnection; exhausted/dead-lettered messages cannot become silently abandoned;
key rotation and the recovery procedure are demonstrated on disposable resources.

## Phase 5 - Complete authenticated Audit reads and typed client

Extend the trusted Identity/gateway pattern for Audit endpoints. Accept the user's real session,
resolve current grants server-side and replace client-supplied actor headers. Handle list scope
from validated filters and detail scope from the persisted event; do not infer authority from
an object ID or require Accounting company-context data merely to read Audit. Preserve existing
step-up and impersonation restrictions where applicable.

Complete list/detail/activity/export authorization and field-policy projection. Use the existing
company/entity/date filters for Accounting history links. Pass `occurred_at` with detail IDs to
preserve partition pruning. Lists use lean SQL projections as well as lean response models;
filters and cursors remain allowlisted, scope-bound and bounded. Review query plans and add
indexes only when supported by measured native queries. Audit must not query Accounting's database.

Fix Audit export self-events to use the agreed action and authoritative top-level company scope,
and prove their delivery through phase 4's publisher. Preserve bounded exports and explicit
truncation. If file downloads are exposed, use signed, expiring URLs and test expiry/scope.

Export Audit OpenAPI and extend `clients/api-client` generation, package exports and typed tests.
Update all affected consumers without introducing a handwritten duplicate transport contract.

Exit: real authenticated gateway requests can read only the permitted scope; spoofed headers,
expired credentials, missing permissions, foreign-company IDs and cross-scope cursors fail;
Audit exports themselves appear in the trail; generated contracts are current.

## Phase 6 - Connect and review the existing audit console

Replace sample data in the runtime audit route with the generated client through the trusted
server/gateway path. Resolve active company IDs as well as display names from the authenticated
session. Load one list page, fetch detail on demand and keep data uncached across users/tenants.
Do not ship the entire history or hidden event details to the browser.

Support Accounting company/entity/object filters and deep links from existing record views
where such views exist. Render full event names with friendly labels, old change markers,
redactions, safe before/after values, actor references and optional reasons/correlation. Resolve
actor names through authorized Identity reads with deleted/anonymized-user fallbacks.

Handle loading, empty, permission-denied, expired-session, invalid-cursor and unavailable-service
states. Explain eventual delivery without suggesting that an empty result proves no change
occurred. Keep the existing UI/design-system conventions; add no new Accounting screens.

Exit: a real Accounting change can be located and inspected in the console; sample events are
confined to tests; paging/detail/export, company switching, formatting and accessibility pass
component/page tests and a focused authenticated browser scenario.

## Phase 7 - Native verification, review, fixes and rollout evidence

Run the complete path using disposable Accounting and Audit MySQL schemas, an isolated RabbitMQ
vhost/queues and the real gateway/session boundary. At minimum exercise master update, import
preview/apply, journal posting/reversal, fiscal close, credit override, charge approval/waiver,
Accounting export and Audit export. Compare the committed business state, outbox message,
ingested Audit row and API/UI result.

Fault tests cover rollback, idempotency replay, missing bindings, broker/consumer restart, Audit
database failure, crash after broker confirmation, consumer redelivery, expired signing-key
rotation policy, invalid signatures, exhausted attempts and dead-letter recovery. Verify tenant
and company isolation, impersonation attribution, field denies, no stored PII, native Decimal
round trips, immutable-row grants, chain integrity and partition maintenance.

Run affected suites at every phase; finish with Accounting, Audit, shared platform and affected
Identity/client/console suites, Ruff, strict mypy, client drift checks, frontend type/build checks
and required coverage floors. MySQL/RabbitMQ tests cannot be replaced by SQLite/fake transport
results. Record unrelated baseline failures, skips and infrastructure limitations explicitly.

Perform two review passes:

1. Correctness and simplification: event coverage, transaction boundaries, original timestamps,
   legacy handling, retries/deduplication, category/retention policy, paging and compatibility.
2. Security and integration: actor/source trust, scope and field-policy bypasses, PII, key/grant
   boundaries, export evidence, UI behavior, recovery and rollout order.

Run `/simplify` and `/security-review` when available. Otherwise document the equivalent manual
review and its limitations. Fix findings with failing regression tests first, rerun affected
checks, and review the fixes. Record severity, evidence and disposition in
`docs/accounting-audit-integration-review.md`; release stops for unresolved critical/high findings.

Prepare a release checklist covering compatible consumer deployment, credential/binding
validation, producers/workers, authenticated reads/UI, controlled backlog recovery and a
canary event. Rollback preserves committed business data, audit evidence and pending events;
never drop a queue or rewrite the chain as rollback. Publishing, when separately authorized,
stages only task files and uses `git publish --dry-run` followed by `git publish`.

Exit: review findings are resolved or explicitly accepted within policy, evidence demonstrates
the real command-to-console path and failure recovery, and delivery status includes measured
results rather than an HTTP-health claim.

## Phase discipline and completion rule

Execute phases in order after plan agreement. Each phase ends with affected tests green, a
working repository, documented findings and a short progress report before the next phase.
Safe-value exposure from phase 3 must not reach a deployment before phase 5's read-policy
enforcement is ready. No partial deployment may relax existing data visibility.

Plan preparation is complete when this document is reviewed. Integration is complete only when
all seven phase exits are met. A publisher test, a broker ACK, an outbox row, an HTTP health
response or a sample UI event is insufficient evidence on its own.
