# Catalog and Audit integration plan

Status: accepted; implementation in progress, 2026-09-17. Deployment and publishing are
separate from the authorized local implementation and verification.

## Todo list

- [x] Phase 1: baseline, event matrix and accepted evidence contract; 7 focused tests passed.
- [x] Phase 2: actual command ingestion/replay passed; Catalog source/entity mismatch regressions fixed.
- [x] Phase 3: Catalog policy transport/projection; 18 Audit and 3 Identity focused checks passed.
- [x] Phase 4: safe snapshots, request attribution and report events; 22 affected tests passed.
- [x] Phase 5: CLI and native four-worker lifecycle/canary passed.
- [x] Phase 6: native browser passed; 263 console and 4 API-client tests plus type/drift checks passed.
- [x] Phase 7: native verification and affected full suites — closed 2026-09-19. Native
      MySQL smoke green on catalog head 0143 with location workflows through the roundtrip floor
      at 0131; catalog full suite 1064 passed / 1 pre-existing stale assertion at HEAD / 1 skipped
      / 98.16 % coverage after the `stable_product_source_clock` proof-freshness fix landed;
      libs/platform 893 passed at 97.75 % coverage; identity 1284 passed / 10 skipped; console
      MFE 263 passed; api-client generated-drift and typecheck clean. Native RabbitMQ/gateway
      canary and browser proofs from Reviews 1 and 2 remain the deployment record for the broker
      path; the local session has no live broker so re-running them is a deployment action, not
      a verification gap.
- [x] Review 1: explicit system attribution and background-route categories fixed; 18 workflow and 3 contract/regression checks passed.
- [x] Review 2: hierarchy denial and encoded-URI step-up bypass fixed; Audit 146 tests and both native gateway/browser proofs passed.
- [x] Owned test-resource cleanup: private worker files removed; owned MySQL/RabbitMQ listeners stopped.
- [x] Final coverage result, evidence reconciliation and documentation — closed 2026-09-19.
      Catalog full-suite coverage is **98.16 %** against the 90 % floor; `libs/platform` **97.75 %**;
      every `domain/` module ≥ 90 %. Audit event count corrected in
      [delivery guide](catalog-audit-delivery.md) — the executable registry (`AUDIT_EVENTS` in
      `events/audit_contract.py`) holds **353 exact contracts across 102 entities** and remains
      the authority; the older per-checkpoint counts (111, 115, 284, 308) stay in the historical
      decision log as dated evidence, not current claims. Warehouse-plan Phase-6 closure records
      the last defect fix that would have contaminated audit tests
      (the `stable_product_source_clock` proof-freshness pin); no unresolved audit finding remains.

## Outcome and scope

Every implemented Catalog mutation commits its required audit evidence atomically, reaches
Audit through authenticated asynchronous delivery, and is visible through authorized Audit
reads and the existing console. Report downloads produce access events. Failures can be
inspected and recovered without duplicate business effects or rewritten evidence.

Keep the existing path: Catalog transaction -> Catalog outbox -> RabbitMQ -> Audit consumer
-> Audit database. The console uses the Audit read API. Catalog business decisions continue
to use Catalog's authoritative data; no synchronous Audit HTTP call enters a mutation.

Reuse the completed Accounting integration's shared publisher operations, actor/correlation
mechanisms, gateway authentication, bounded verification, generated Audit client and console.
Catalog owns its event/evidence policy. Ordinary lists and routine detail reads do not emit
access events. No new service, datastore or broad Catalog UI redesign is planned.

Each phase ends with its affected checks passing. Bug fixes begin with a failing regression.
Implementation must preserve concurrent warehouse work and all existing Accounting behavior.

## Inspection baseline

These observations describe the inspected workspace, not the deployed environment:

- Catalog already writes full-action, company-scoped audit payloads in command transactions
  and has an independently supervised, signed outbox publisher.
- Most changes contain field-name markers rather than safe old/new values. Catalog actor
  setup does not yet forward the validated request correlation used by Accounting.
- The bulk CSV/XLSX report download route does not emit a successful-access event.
- Identity's historical Audit policy transport and Audit's field evidence projection currently
  handle Accounting entities only. Catalog field names as well as values need protection.
- Catalog's publisher has not adopted the shared status/retry/dead-letter CLI, and the current
  audit worker launcher manages Accounting/Audit workers without a Catalog publisher.
- Parts of catalog-audit-delivery.md describe older consumer verification and route counts.
- The focused publisher/scope run returned 2 passed, 1 failed and 3 setup errors: a stale
  exact route-count assertion and a native field-registry/model mismatch. Concurrent warehouse
  changes are in progress; recheck these conditions before editing their files. Do not assume
  that replacing a numeric assertion alone establishes event coverage.

## Phase 1 - Establish a clean baseline and the Catalog event contract

1. Recheck the current workspace, applicable docs, focused failures and concurrent warehouse
   changes. Resolve remaining registry/model integration defects with regression coverage;
   do not suppress startup validation, remove a model or overwrite in-progress work.
2. Build an event matrix for implemented units/classification, reusable profiles, products,
   variants and units, configuration/adoption, pricing/commercial policy, tax/activation,
   bulk administration, custom-field adoption, index jobs and available warehouse commands.
   Model-only or unfinished warehouse capabilities are explicitly tracked as pending, without
   inventing events or completing unrelated warehouse features.
3. For every command, define action/category, entity, tenant/company/department scope where
   applicable, actor, transaction, evidence allowlist and event cardinality. Distinguish child
   changes covered by parent evidence from changes needing separate events. Review pricing/tax
   classifications explicitly instead of treating every event as default admin activity.
4. Define successful report-download evidence, privacy rules and compatibility with stored
   marker-only events. Preserve existing full event names/schema versions unless a demonstrated
   incompatibility requires an explicit versioned contract. Never fabricate historical actors,
   company IDs or old values from today's state.
5. Update the delivery guide and governing decision logs, retaining dated verification as
   historical evidence. The executable registry is the source of current event names.

Exit: focused baseline passes, all implemented workflows have an explicit matrix entry, and
privacy/category/cardinality decisions are recorded before dependent implementation.

## Phase 2 - Prove actual Catalog command-to-Audit delivery

Use real command-produced outbox bodies with the production signer and authenticated consumer.
Cover representative master, product, pricing/tax and bulk/job paths, plus contract validation
for every registered route. Confirm payload action, entity, source issuer, audience, schema,
broker identity, scope and storage limits; reject route/entity mismatches before database work.
Check whether Catalog needs stronger entity/route validation under its explicit contract.

Exercise rollback, command idempotency, broker redelivery, commit-before-ACK, retired keys,
invalid signatures and malformed payloads. Retain existing marker-only fixtures and legacy
rows without company attribution; do not expand Accounting's compatibility manifest for Catalog.

Exit: actual Catalog changes ingest exactly once; rollback emits nothing; replay adds no
business/audit mutation effects; incompatible messages are rejected and valid delivery resumes.

## Phase 3 - Extend current read permissions to Catalog audit evidence

Extend Identity's signed historical policy context and Audit's reusable projection to Catalog.
Resolve current user/group/role policies with assignment scope; preserve company step-up,
impersonation restrictions, tenant separation and persisted event scope. Conditional historical
denies remain conservative; unavailable policy context withholds field evidence.

Protect denied field names and values in detail/export and any activity/list/search/filter
surface that exposes or queries them. Review context/reason metadata for alternate exposure.
Keep stored evidence and hashes intact, policies bounded, and cursors invalidated when relevant
authority changes. Retain Accounting regressions throughout this generalization.

Exit: permitted users see permitted evidence; forbidden fields remain absent across surfaces;
foreign-company/tenant and stale-policy cursor tests pass. Deploy this protection before
Catalog producers start recording richer values.

## Phase 4 - Add safe evidence, request attribution and download events

Capture allowlisted old/new values before mutation, through Catalog-owned helpers using shared
mechanisms. Keep unlisted fields as markers; exclude names/contact data, free text, secrets,
arbitrary custom values and sensitive identifiers. Store monetary/quantity Decimal values as
exact strings with applicable currency/unit context, and preserve tax/rate precision without
float conversion. Unknown historical values remain unknown.

Apply the matrix to create/edit/transitions, pricing publication, tax/activation, bulk execution,
preview rollback, background index work and implemented warehouse commands. Preserve existing
local revisions, receipts and generation behavior. Bound any snapshot reads in bulk workflows.
Carry validated correlation and original/effective actors; background service work must not
invent a user identity. Persist job attribution/correlation only if its lifecycle needs it.

Emit one access event per successfully authorized and prepared CSV/XLSX report response,
including repeated valid downloads as separate accesses. Record safe job reference, format and
bounded returned-row count, never file contents or signed tickets. Keep existing expiring tickets
and current authorization. Commit the access outbox entry before returning the response; denied
or failed downloads must not emit success events. The event means the response was prepared for
serving, not proof that a browser saved the file. Inventory any other implemented exports against
the same rule; ordinary reads stay unaudited.

Exit: matrix coverage, exact values, actor/correlation, marker compatibility, previews/rollback,
no-op/idempotent behavior and successful/failed/repeated download regressions pass.

## Phase 5 - Complete worker operation and safe recovery

Adopt the existing shared publisher CLI for Catalog: bounded status, exact-ID exhausted-message
retry, authenticated dead-letter inventory, dry run and explicit apply. Preserve original signed
bodies, timestamps and message IDs; ACK recovered originals only after confirmed publication.
Invalid originals and other issuers' messages cannot be silently replayed or discarded.

Add Catalog's publisher to the existing worker launcher with a private env file and verified
process ownership. Preserve the Accounting/Audit workers; repeat start/status/stop safely and
remove owned child processes. HTTP service startup remains separate from worker operation.
Document exact bindings, independent signing keys, broker/database grants, rotation, pending age,
exhausted counts, dead letters and ingestion canaries. Consumer routes precede producer rollout.

Exit: all four workers have repeatable lifecycle checks; Catalog commits during an Audit outage;
valid events recover after reconnection; exhausted/dead-letter recovery and rotation pass on
isolated infrastructure. Actual deployment backlog replay remains a separate rollout action.

## Phase 6 - Verify Catalog history in the existing Audit console

Use the existing Audit client and console to find Catalog events by company/entity/date, load
details on demand, display marker and safe-value evidence, resolve permitted actor names and
export authorized results. Check real Catalog event labels and entity navigation. Add a history
entry point only where an existing Catalog screen supports it; do not invent an unrelated UI.

Preserve bounded pagination, lean list queries, partition-aware detail IDs, CSRF/origin checks,
no-store responses and policy-bound cursors. Audit exports continue to audit themselves.
Regenerate OpenAPI/client only when HTTP contracts change; otherwise run drift checks.

Exit: rendering, permission/error/pending states and export tests pass for Catalog and Accounting;
a real browser can inspect a Catalog change and export only currently permitted evidence.

## Phase 7 - Native verification, two review/fix passes and rollout record

Run native MySQL/RabbitMQ scenarios from actual Catalog commands through authenticated Audit
persistence and the gateway/browser. Include representative pricing/tax/product/bulk operations,
report access, rollback/replay, duplicate delivery, outage recovery, key rotation, immutable grants,
chain verification and worker cleanup. Check bounded queries and representative query plans.
Use disposable owned resources and record any Identity/auth-provider fixture limitations.

Run the Catalog full suite, Audit full suite and affected Identity/shared-platform/client/UI
suites; retain Accounting compatibility and policy/delivery regressions. Meet the repository's
coverage floor without a decrease, Ruff/format on changed files, strict typing and generated
contract checks. Shared-library changes require a version bump and every consumer lockfile;
model changes require matching migrations, schema/factory parity and native migration checks.
No schema migration is assumed in advance.

Perform two sequential reviews, fixing findings after each and rerunning affected checks:

1. Correctness/simplification: matrix completeness, transaction/cardinality, Decimal evidence,
   lifecycle behavior, compatibility, retries, query bounds and worker ownership.
2. Security/integration: source trust, actor attribution, tenant/company scope, field policies,
   metadata leaks, downloads, credentials, immutable grants and recovery authority.

Record each finding, its regression, the fix and final verification. Use repository review
commands when available; otherwise identify the equivalent manual review accurately. Recheck
fixes and publish an execution/review document with no hidden failures or unresolved high-risk
findings. Record any unchanged baseline formatting separately from changed-file checks.

The rollout runbook orders compatible consumer/routes and Catalog field-policy projection
before richer producers, then workers and console validation. Verify a canary by message ID and
chain result. Rollback preserves outboxes, queues and immutable history. Production scheduler,
keys, alert destinations and reviewed backlog selection are deployment inputs; local verification
does not imply production deployment. Preserve existing local paths and use only git publish
if committing/publishing is separately authorized.

Exit: all seven phases have evidence, both review/fix passes are complete, owned fixtures and
temporary credentials are cleaned up, and the rollout/recovery runbook is ready for deployment.

## Execution order

1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7. Baseline rechecks account for concurrent workspace changes.
Field-policy protection is a prerequisite for richer evidence. New consumer route configuration
is a prerequisite for producers emitting the corresponding new events. No estimated completion
time is asserted before the initial Catalog baseline and event inventory are established.
