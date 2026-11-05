# Identity API — implementation-gap completion plan

**Date:** 2026-09-12
**Status:** Local implementation and verification complete; tracked in [the implementation todo](identity-gap-todo.md); [results and external release gates](identity-gap-results-2026-09-12.md). The checklists below preserve the approved scope; the todo is the current completion record.
**Scope:** Complete G01–G08 from the [Identity review](identity-api-review-2026-09-12.md).
**Prerequisite workstream:** [Confirmed bug fixes](identity-bug-fix-plan.md), completed and reviewed.

## Current starting point

All 15 bug findings and both confirmed concurrency findings are closed in the
[final corrective review](identity-bug-fix-results-2026-09-12.md). Its recorded baseline
is 1,073 non-MySQL tests plus 8 MySQL tests, with 93.97% Identity coverage. This is
existing evidence, not a new test run for this planning update.

Reuse the repaired scope checks, transactional audit payloads, re-grant/idempotency,
membership constraints, bounded lists and generated clients. Field-policy enforcement
currently covers registered `identity.company` native fields and `business_roles`;
it does not mean policy administration or other entity support is complete.

G01–G07 remain open capability work. G08 has completed local database, regression
and consumer-check foundations; live broker/IdP/Billing workflows and reproducible
release gates remain open. Production has not been changed.

## 1. Outcome and boundaries

Deliver working Identity workflows from real authentication through authorized
management, durable audit delivery and production-equivalent verification. Existing
tables, domain helpers and tests are the starting point; their presence alone does
not complete a workflow.

Keep the existing seven-service architecture: Identity owns identity/org policy,
Authentik owns credentials and authentication, Notification owns message delivery,
Audit owns immutable audit storage, and Billing owns posting. Reuse shared mechanisms
for authentication, commands, outbox, filtering and workers rather than adding a new
service or duplicate implementations.

This plan covers Identity APIs, workers, necessary cross-service adapters and client
integration for authentication/preferences. The management APIs and generated clients
are included; a complete new administrative UI for every deferred resource is a
separate product scope. No existing application is represented as production-wired
while it still uses demo session data.

G01–G08 remain the gap ledger. The delivery phases below are not new finding IDs.
Full completion requires the real external dependencies; simulated Billing/IdP/broker
responses may prove local logic but cannot close an integration milestone.

## 2. Delivery order and prerequisites

| Phase | Gap | Working deliverable | Prerequisites |
| --- | --- | --- | --- |
| GP0 | G08 preparation; all contracts | Capability/route inventory, environment and acceptance matrix | Completed corrective review |
| GP1 | G07 | Identity audit events reach Audit durably | GP0; real RabbitMQ/Audit test target |
| GP2 | G01 | Real login, current session, invitation acceptance and activation | GP1; Authentik, gateway and Notification |
| GP3 | G02 | Complete org/group/assignment lifecycle actions | GP1; repaired authorization and membership mechanisms |
| GP4 | G03 | Contacts, banks, documents, preferences and API-token APIs | GP1; encryption/storage; GP2 for credential issuance |
| GP5 | G04 | Runtime custom fields, layout and policy administration | GP1; repaired field enforcement; Catalog source contracts |
| GP6 | G05 | Enforced company step-up and audited impersonation | GP1, GP2; support-access contract |
| GP7 | G06 | First-posting and feature-use locks work across service boundaries | GP1; real Billing integration |
| GP8 | G08 closure | Reproducible production-equivalent verification and release evidence | GP1–GP7 and their actual dependencies |

Recommended delivery is GP0 → GP1 → GP2 → GP3 → GP4 → GP5 → GP6 → GP7 → GP8.
G08 infrastructure starts at GP0 and runs throughout. GP3/GP5 can progress after GP1
without waiting for an unrelated Billing dependency. GP6 can follow GP2 immediately
if fresh company authentication is required for the first release. These are delivery
dependencies, not agent delegation or calendar estimates.

The Billing service directory is absent in the current workspace. GP7 therefore
includes an Identity contract and adapter milestone, followed by a separate real
Billing verification milestone. Building the full Billing service is outside this
Identity plan; its absence must not block the independent Identity phases or be
hidden by closing G06 against a test double.

## 3. GP0 — Contracts and integration environment

- Create a route/action inventory mapping each capability to request, detail/list
  response, permission, tenant/company/department scope, field policy, lifecycle,
  idempotency, audit and consumer behavior.
- Identify required new permissions and update catalogue/system-role seeds with
  their implementations. A convenience management API must not grant additional
  authority implicitly.
- Establish disposable MySQL 9.6, RabbitMQ, Audit, Notification and Authentik test
  resources, and the required secrets/configuration. Use isolated test data and
  explicit configuration rather than credentials in source.
- Inventory existing storage/encryption adapters for documents and bank data, the
  gateway deployment boundary, notification templates, and the Billing posting
  integration contract. Record missing external inputs per dependent phase so
  independent work can continue.
- Define deployment/migration order and contract compatibility for existing consumers.
- Record outstanding product decisions separately from environment setup. In
  particular, confirm launch entity coverage and policy limits for GP5, the support
  access model for GP6, and the freeze/abort contract for GP7 before their dependent
  implementation. Preserve already agreed scope such as tenant-only field layout.
  Print/report integration, multilingual custom labels, nested groups and subscription
  plans are not silently added to this Identity workstream.

**Exit:** a concrete endpoint/capability matrix and runnable integration setup;
unavailable dependencies have explicit affected milestones and verification steps.

## 4. GP1 — G07: Durable audit delivery

- [ ] Add an Identity audit publisher using the existing outbox/broker mechanism,
  an explicit audit-event allowlist and the Audit service's authenticated ingestion
  contract. Keep Catalog source publication on its own existing route/allowlist.
- [ ] Implement publish confirmation, retry/backoff, retry exhaustion handling and
  worker lifecycle configuration. Recovery must not lose committed events or mark
  unconfirmed messages delivered.
- [ ] Supply startup/run configuration and operational visibility for oldest pending
  event, delivery failures, worker health and dead-letter recovery.
- [ ] Verify scoped querying in Audit after delivery of BF3's corrected payloads.

**Acceptance:** a committed Identity mutation produces an Audit row; a rolled-back
mutation does not. Broker outage and worker restart preserve delivery; duplicate
delivery produces one logical audit effect. Company scope and redaction survive
transport. Personal-data remediation identified by BF3 is handled deliberately
before historical affected events are released to the immutable store.

## 5. GP2 — G01: Authentication, session and invitations

- [ ] Connect the gateway to Authentik's real OIDC flow and validate issuer, audience,
  signature and token lifetime through the agreed shared mechanism. Resolve local
  tenant/user identity and live server-side grants; never trust client permission lists.
  Strip client-supplied actor headers at the gateway and keep actor signing keys on
  trusted servers. Define revocation/cache lifetime and enforce inactive-user/tenant rules.
- [ ] Implement authenticated current-user/session resolution with company choices,
  scopes, effective permissions and preferences. Replace demo login/session sources
  in the existing auth and console clients using the generated contract.
- [ ] Complete invitation creation, Notification command/template integration,
  expiry, resend, cancellation and single-use acceptance. Keep raw credentials or
  invitation secrets out of audit and logs. Bind the authenticated provider subject
  to the invited user only after appropriate proof and activate atomically.
- [ ] Protect external identity linking with provider ownership proof and explicit
  link/unlink authority. Avoid account binding by a profile editor who merely knows
  a provider subject. Enforce unique mappings and prevent accidental removal of
  the final usable login method.
- [ ] Complete applicable user suspension/deactivation/session revocation and
  tenant bootstrap: a new tenant receives its initial administrator through the
  documented system-principal exception, with audit evidence. Platform create/list/
  suspend uses explicit platform authority and a dedicated tenant-isolation boundary.
  Subscription-plan management remains outside this review's G01 scope.

**Acceptance:** a real invited user can accept once, sign in, resolve only their
authorized tenant/company data and sign out. Expired/replayed invitations, forged
actor headers, wrong audiences/tenants and unverified subject linking fail. Revocation
takes effect within the documented bound; fixture sign-in cannot grant production
access. No production login or account-takeover claim is based solely on mocked tests.

## 6. GP3 — G02: Organization and access lifecycle APIs

- [ ] Enable group role assignments through the repaired assignment guards and
  date validation. Check self-membership and delegation restrictions on all changes.
- [ ] Add group-member removal and group update/deactivation, preserving historical
  references and recording authorization-affecting changes as security events.
- [ ] Add membership end and primary-switch actions. Reuse BF4's uniqueness and
  per-user serialization; switching primary is atomic and rejects invalid targets.
- [ ] Add company, department and custom-role deactivation/reactivation where the
  domain permits it. Define descendant/member/default-selection consequences,
  preserve system-role immutability and retain historical readability.
- [ ] Publish the required source changes and invalidate/re-resolve access within
  the agreed freshness bound. Use BF4's re-grant endpoint for access restoration.

**Acceptance:** group assignment/removal changes effective access correctly;
deactivation blocks new selection/use without hiding history; primary switching
never creates two active primaries; self-escalation and unauthorized broadening
remain impossible. All transitions are auditable and have deterministic retry behavior.

## 7. GP4 — G03: Deferred child-resource APIs

Implement each slice as a complete request → authorization → persistence → response
→ audit workflow, with bounded lists and generated client contracts.

| Slice | Work | Acceptance |
| --- | --- | --- |
| GP4a — Contacts and notification preferences | Contact management/lifecycle; self/admin preference authority and supported channels/topics; documented precedence with Notification consent/suppression | Wrong-company/user access denied; validated preferences are readable and respected without bypassing consent |
| GP4b — Bank accounts | Masked list/detail contracts, restricted reveal, audited sensitive reads, encrypted storage through the approved adapter, primary-account and lifecycle rules | Full account data absent from ordinary responses/logs/audit; authorized reveal works and is audited; key lifecycle tested |
| GP4c — Documents | Metadata and upload/finalization flow, approved object storage, scoped signed expiring download links, type/size checks and lifecycle | Foreign-object access denied; links expire; failed uploads can be reconciled; referenced history retained |
| GP4d — API tokens | Scoped token issuance with one-time secret display, hash-only storage, expiry, revocation and gateway validation | Secret cannot be retrieved again; scope cannot exceed issuer authority; expired/revoked tokens fail; no raw secret in storage/logs/audit |

**Dependencies:** GP4b/GP4c require the approved encryption/storage configuration;
GP4d requires GP2 authentication and the token-consumption path. A schema-only or
mock-adapter implementation does not close its slice.

## 8. GP5 — G04: Extensibility and policy administration

- [ ] Add custom-field definition management: supported types, validation, defaults,
  options, feature prerequisites, searchability, lifecycle and immutable-field rules.
  Reuse the existing shared mechanism and respect the definition's owning service.
- [ ] Add field layout/configuration APIs and merge the field-set endpoint with
  applicable native fields, custom definitions, features and layout configuration.
  Preserve the agreed tenant-only launch scope for layout unless a documented scope
  change is made. Layout never grants or denies authorization.
- [ ] Add field-policy administration and resolved-policy reads with distinct
  permission checks, validated subjects/fields/conditions, security audit and source
  version/freshness propagation. Reuse BF2 enforcement rather than creating a second
  policy engine.
- [ ] Declare supported entity/field coverage explicitly. Extend the runtime registry,
  sparse response contracts and query guards together for each added entity. Prevent
  policy edits or group membership changes from granting authority the administrator
  cannot delegate; retain the repaired self-escalation checks.
- [ ] Wire custom values into supported Identity entity writes and reads, typed
  searchable indexes, sequence allocation and bounded rebuild/backfill workflows.
  Validate changes against existing data before making a definition stricter.
- [ ] Verify that consumers such as Catalog receive complete source facts and respect
  policy/definition changes. Domain decisions never derive money or approval behavior
  from arbitrary custom fields.

**Acceptance:** a permitted administrator defines and configures a field; authorized
users store/read it, permitted searches use its index, denied fields cannot leak
through queries, and lifecycle/type changes do not corrupt existing values. Source
replay and rebuild recovery preserve consistent consumer behavior.

## 9. GP6 — G05: Step-up and impersonation

- [ ] Implement company-scoped fresh-authentication challenges through Authentik,
  with short-lived server-validated proof. Enforce `requires_step_up` at the actual
  request boundary, including relevant downstream service requests.
- [ ] Add explicit impersonation start/end operations with authority, reason,
  bounded lifetime, expiry enforcement and revocation. Define non-escalation and
  nested-impersonation restrictions using the documented support-access model.
- [ ] Carry real actor and effective user separately in trusted request context.
  Preserve `on_behalf_of_user_id` and the initiating actor through every audit-producing
  consumer. Invalidate access on end/expiry even if a cleanup worker has not run.

**Acceptance:** ordinary company access fails when fresh authentication is required;
proof for another company/user or an expired session cannot be reused. Impersonation
start/end and resulting mutations are attributable to both identities; expiry closes
authority automatically. Verify the actual OIDC/gateway flow and client challenge UX.

## 10. GP7 — G06: First-posting and feature-use locks

This phase depends on a real Billing posting path. Designing the contract can proceed
earlier; implementation and end-to-end completion cannot be claimed from a stub.

- [ ] Specify a protocol that prevents company money-shaping settings or used
  features changing concurrently with first use. An eventual post event by itself
  leaves a race window and is insufficient.
- [ ] Develop the concrete owner contract around a pre-post freeze/reservation
  outside the money transaction, or an equivalently proven protocol consistent
  with the existing architecture. Distinguish a pending freeze from confirmed
  `first_posted_at`; define abort, uncertain outcomes, retries and recovery before
  coding either side. No synchronous cross-service request runs inside Billing's
  money transaction.
- [ ] Implement authenticated, idempotent Identity commands and Billing integration,
  with terminal events through the outbox. Preserve the first confirmed posting
  timestamp and irreversible feature locks under replay and out-of-order delivery.
- [ ] Publish authoritative lock state to consumers; enforce it on settings edits
  and feature toggles and reconcile interrupted workflows safely.

**Acceptance:** concurrent first-post/settings-edit and first-use/feature-disable
tests cannot both commit inconsistent states. Crash/retry scenarios preserve money
invariants; aborts do not fabricate a successful posting; duplicate events do not
move or clear the first confirmed timestamp/lock. Run this against real Identity,
Billing, MySQL and broker components.

## 11. GP8 — G08: Production-equivalent verification and release evidence

- [ ] Extend and run Identity's complete suite from the completed 1,073 non-MySQL
  and 8 MySQL test baseline, adding new route, lifecycle and concurrency regressions.
  Reproduce the MySQL gates in the release environment. Test migrations
  and seeds on fresh and upgraded disposable databases; verify drift and recovery.
- [ ] Run real Authentik → gateway → Identity → Notification/Audit workflows and
  the Billing lock integration. Verify tenant isolation, credential revocation,
  signed callbacks/requests, event replay, worker restarts and dependency outages.
- [ ] Exercise large lists and indexes with representative tenant data and MySQL
  query plans. Document bounded resource use and enforce the agreed API contracts.
  Measure contention from the current per-tenant mutation lock; preserve its ordering
  and correctness unless evidence supports a separately reviewed narrower protocol.
- [ ] Regenerate OpenAPI and API clients; run affected UI/client and cross-service
  tests. Check Ruff, strict mypy and configured coverage gates without weakening them.
- [ ] Verify deployment configuration, migration/worker start order, operational
  monitoring, retry/recovery procedures and backup/restore behavior for new state.
- [ ] Perform the final authorization/correctness/security review. Record evidence
  per G01–G08 and update stale tracker statements based on the actual results.

**Completion:** all eight gaps have working end-to-end evidence, the prerequisite
bug findings are closed and no dependent milestone relies on a placeholder.
Unavailable external dependencies remain open milestones. A deliberately scoped
release must name the unavailable capabilities; it is not full Identity completion.

## Evidence required at every phase

Each phase finishes with its affected tests passing, synchronized migrations/models,
OpenAPI/generated clients and consumers, updated permissions/seeds, and an implementation
review. Keep strict typing, lint and configured coverage floors; compare coverage with
the completed baseline rather than resetting it to a lower target.

For new endpoints cover authentication, permission and object scope, tenant isolation,
validation, lifecycle, replay/concurrency where applicable, sensitive-field handling
and transactional audit. For each integration record the actual service versions,
configuration and success/outage/recovery evidence. Test doubles remain useful for
unit tests but do not close a live integration gate.

The final report maps every G01–G08 finding to implemented behavior, test evidence,
deployment prerequisites and any unresolved dependency. Complete the final security
and correctness review after the last implementation phase.

## 12. Separation from the bug plan

| Existing behavior repaired in bug plan | New capability delivered here |
| --- | --- |
| B01/B03 authorization on existing operations | G02 additional lifecycle/group-assignment endpoints |
| B04 enforcing stored field policies | G04 APIs to administer policies and runtime configuration |
| B05–B07 complete/correct outbox payloads | G07 operational delivery into Audit |
| B08 re-grant; B10 membership consistency | G02 primary switching, ending affiliations and broader lifecycle |
| B15 reading saved preferences | G01 actual signed-in session/client wiring |
| Company guards when lock state exists | G06 distributed first-post/first-use protocol |
| BF6 fixing and validating reproduced races | G08 integrated release verification across live components |

## Decision log

- 2026-09-12: Created a separate proposed plan for G01–G08 at the user's request.
  Kept the bug ledger separate, made cross-plan prerequisites explicit, and retained
  Billing/Authentik/broker/storage dependencies as real completion requirements.
- 2026-09-12: Refreshed the plan after completion of B01–B15 and C01/C02. Credited
  the existing MySQL/regression evidence, removed stale prerequisite status, bounded
  field-policy expansion, and separated Identity's G06 work from the unavailable
  Billing implementation. Gap implementation remains proposed.
