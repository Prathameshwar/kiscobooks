# Automatic company setup and reporting readiness

Status: implementation authorized by the user, 2026-11-03, for all phases in order
and two final review passes. Progress and evidence are recorded below. The user
approved the proposed readiness, enrollment and explicit opening-choice policy.

## 1. Outcome

Creating a company through any supported client must durably start its applicable
setup. The user can close the browser after submission; setup continues, resumes
after outages, and becomes visible from the company directory and overview. A new
company must not require deployment configuration edits, service restarts, a report
workspace visit, or a manual source-build request.

Automatic readiness means the shipped, applicable foundations are prepared and their
actual readiness is reported. It does not assert that every voucher kind, report,
external integration, statutory workflow or posting capability is activated.

For a healthy installation the expected flow is:

1. Submit company facts, selected features and an explicit opening-balance choice.
2. Receive the company and durable setup identity, including after a lost-response retry.
3. See progress while service owners prepare their existing defaults and source data.
4. Open a verified empty overview or verified recorded figures. Display outstanding
   business setup separately from technical initialization.
5. See figures update automatically as committed source data changes, with an honest
   verification time and freshness status.

No unavailable or unverified source is represented as zero. No opening balance is
assumed to be zero because a company has no transactions.

## 2. Findings from the current implementation

| Finding | Evidence | Consequence |
| --- | --- | --- |
| Creation already atomically creates the company, creator roles, Catalog enrollment and audit outbox record. | `apis/identity/src/identity/api/companies.py`, `services/catalog_enrollment.py` | Preserve this boundary and extend it with durable setup intent. The existing audit event is not a complete provisioning command. |
| Company creation has no idempotency key; the wizard remembers the created ID in a React ref. | `mfes/apps/console/app/components/CompanyWizard.tsx`, `create()` and `run()` | An ambiguous create response or remounted wizard needs a durable receipt, not another generated company code. |
| Features, chart, financial setup, year and period creation, and several bootstrap calls are sequenced by the browser. | `CompanyWizard.tsx`, `company-bootstrap.ts` | Completed company metadata does not prove completed setup. Much of the visible recovery state disappears on reload. |
| Catalog already discovers enrollment and prepares units, taxes, warehouses, products and pricing. Vouchers already discovers companies and prepares applicable definitions. | `apis/catalog/src/catalog/tasks/source_worker.py`; `apis/vouchers/src/vouchers/tasks/source_worker.py`; `docs/company-voucher-defaults.md` | Reuse owner provisioners. Do not introduce a second set of defaults or overwrite user-edited starter records. |
| Source admission and source workers use static Reports owner scopes. `source_worker.run()` constructs its work list at startup. | `apis/reports/src/reports/api/source_generations.py`; `tasks/source_worker.py` | Adding a company requires more than requesting a generation; discovery and scheduling must become dynamic. |
| Accounting report export checks signed credentials against explicit company scope. Identity report-authority does the same. | `apis/accounting/src/accounting/api/reporting.py`; `apis/identity/src/identity/api/report_authorizations.py` | Both ends of the service boundary must support verified enrollment. A Reports-only change is insufficient. |
| Calculation/export authority selection, recovery and temporary-artifact cleanup also use static scopes. | `clients/reporting/src/reporting_contract/authority.py`; Reports `framework_worker.py`, `job_dispatcher.py`, `artifact_cleanup.py` | A dashboard-only fix would leave new-company report runs, exports or recovery broken. |
| Inventory reporting has another scoped connection: Accounting obtains Catalog stock masters and coverage. | Accounting `tasks/stock_summary_source.py`; `clients/reporting/src/reporting_contract/catalog_stock.py` | Financial-source readiness alone cannot certify stock-report readiness. |
| Stock preparation is invoked by the Accounting snapshot worker; incremental report refresh follows the Accounting change feed. | Accounting `tasks/reporting_snapshot.py`; Reports `tasks/source_worker.py` | An incremental financial refresh must not be assumed to renew Catalog inventory evidence or its as-of date. |
| Overview selects the latest READY generation and requires a verified cut, compatible projection, history coverage and financial year. | Reports `api/overview.py`, `tasks/overview.py`, `queries/native_context.py` | A row marked READY is not by itself sufficient. Initial-build acceptance must execute the overview. Latest READY does not itself prove caught up to the latest owner sequence. |
| Source failures have coarse classification: several platform/value errors become SOURCE_VERIFICATION_FAILED and quarantine the generation. | Reports `tasks/source_worker.py`, `cycle()` | Define temporary dependency failure, authorization refusal and integrity failure separately before enabling automatic retries. |
| Managed report workers already start through `start-services.ps1` and `report-workers.ps1`. API health alone does not certify pipeline progress. | `start/win/start-services.ps1`; `lib/report-workers.ps1`; `docs/reports-framework/usage.md` | Extend existing lifecycle management and operational health; do not create a duplicate worker launcher. |
| Zero opening is an explicit, guarded financial operation with a setup version and eligibility review. | Accounting `tasks/zero_opening.py`; Console `CompanyZeroOpening.tsx` | Integrate the explicit choice without bypassing permission, concurrent-activity, period or audit checks. |

The prior read-only inspection of Sharma Traders found no report company,
generation, generation request, source cut or source epoch for that company; the
saved Reports owner configuration did not include it. These are point-in-time
observations, not a guarantee that current runtime state has remained unchanged.

## 3. Proposed ownership and contracts

### 3.1 Durable coordination inside existing services

Use Identity for the company setup request and overall progress because it owns
company creation and the creator's authorized selections. Service owners retain
their native commands, transactions, domain checks, evidence and source data.
Use the existing MySQL, outbox, signed transport and managed workers. No new service
or cross-service database access is needed.

Identity records the company, chosen configuration and workflow intent in one local
transaction. Owners execute bounded steps in their own transactions. Commands and
completion evidence cross service boundaries through authenticated, versioned
contracts. Network acquisition happens outside write transactions. Notifications
accelerate delivery; persisted state and reconciliation recover lost wakeups.

Candidate persistence, finalized before each migration:

- Identity: `company_setup_run` and `company_setup_step`, with tenant/company scope,
  initiator, request fingerprint, plan version, expected configuration version,
  command identity, dependency, status, attempt, lease, next attempt, safe error
  code and owner receipt/reference. Reuse existing idempotency storage where it fits.
- Identity: report-specific enrollment with a unique tenant/company key, revision
  and lifecycle. Reuse signed enrollment mechanisms without making a Catalog grant
  automatically grant report export access. Keep existing Catalog/Vouchers enrollment
  semantics intact.
- Reports: a durable source subscription/scheduling record carrying verified
  enrollment revision/lease, observed owner sequence, applied cut, pending generation,
  scheduling state and last successful verification. Reuse `ReportGeneration`,
  `ReportGenerationRequest`, epochs and cuts for actual source work.
- Accounting and other consumers: persist only the minimum signed enrollment and
  owner-step evidence needed locally. Do not copy another service's models or add
  cross-service foreign keys. Avoid extra receipt tables where native idempotency
  and default-manifest records already provide reliable evidence.

Workflow states: PENDING, RUNNING, RETRY_WAIT, NEEDS_ACTION, COMPLETE and CANCELLED.
For optional steps, NOT_APPLICABLE carries a reason; a missing required step cannot
be called skipped or complete. Owner source states retain their existing meanings.

Expose separate readiness dimensions: company foundation, books/calendar, catalog,
voucher definitions, financial reports, inventory reports, opening balances and
posting. The last two are not inferred from successful technical initialization.
Deployment-disabled features are shown as unavailable, never enabled by creating a
company. Report runs/exports retain per-definition permission and capability checks.

### 3.2 Authority and lifecycle

- Signed installation credentials identify a service. Current enrollment authorizes
  the exact tenant/company. User permission authorizes viewing or taking an action.
  None substitutes for the others.
- System maintenance can prepare fixed, versioned starter defaults and report copies
  for enrolled companies. It cannot impersonate a platform administrator or acquire
  unrestricted master CRUD, posting or approval authority.
- User-selected features, calendar operations and zero-opening confirmation retain
  initiator attribution, declared scope and current applicable permission/field-policy
  checks at execution. Store no user password or long-lived browser token. Reuse
  fresh signed Identity authority; if the required authority is revoked or step-up
  expires, expose NEEDS_ACTION with an authorized continuation path.
- Revocation, suspension and enrollment revision changes stop new provisioning/source
  collection within a documented lease bound. A failed or partial discovery must not
  renew a lease or infer deletion of unseen companies. Late events cannot restore
  revoked enrollment. Explicit legacy scopes must not bypass a native revocation.
- Historical reads of closed companies remain governed by existing user permissions
  and retention rules. Active-company discovery must not become the only way to
  authorize a report over retained history. Source collection, historical report
  calculation and cleanup have distinct eligibility rules.

### 3.3 User selections and financial correctness

The recommended creation contract explicitly records ZERO_CONFIRMED, IMPORT_EXISTING
or DECIDE_LATER for opening balances. ZERO_CONFIRMED requires a visible confirmation
and reason; it is never a preselected financial assertion. Legacy clients default
to DECIDE_LATER, not zero. Confirmation applies only to the reviewed configuration
and books-begin date; changing either invalidates the pending declaration.

Keep the existing rule of opening the books-begin period and later periods in the
first year. Earlier periods remain FUTURE. Do not reopen CLOSED/LOCKED periods or
create subsequent years implicitly. Current fiscal-start/precision immutability and
first-use checks remain enforced by Accounting/Identity.

For imported or undecided balances, finish technical setup and produce a source
when valid, but label the books as incomplete. Only show zero-valued financial
tiles when the corresponding complete-source and opening semantics justify them.
GST registrations, bank data, actual products, stock quantities, prices, balances
and external provider credentials remain real business inputs.

## 4. Delivery phases

Each phase ends with its affected tests and required static/generated-contract
checks passing. A schema change ships with its model and consumers. Allocate actual
migration revisions from current heads at implementation time; one DDL statement
per revision, with reviewed downgrade or an explicit evidence-retention restriction.

### Phase 0 — Freeze the readiness contract and baseline regressions

Deliverables:

- Agree the ownership, states, setup DAG, explicit opening choice and authorization
  policy above. Enumerate required, conditional and unavailable capabilities for
  service-only, inventory, GST and feature-dependent companies.
- Inventory all company-create callers, gateway/proxy routes, generated clients,
  owner defaults and report scope checks. Record supported old-client behavior.
- Add failing regressions for ambiguous creation retry, lost browser state,
  unenrolled report admission and a new company absent from a running worker's list.
- Define source freshness as a verified owner sequence plus last contact time,
  rather than snapshot age alone. Agree a measurable healthy-local target before
  performance acceptance: proposed empty-company readiness within 60 seconds and
  small committed changes visible within 15 seconds; measure before promising an SLO.
- Update governing documentation and decision logs with the agreed contract. Keep
  data-entry readiness, report readiness and financial posting readiness explicit.

Exit: executable failure cases reproduce the observed gaps; exact contracts and
acceptance targets are reviewable. No business records are changed for investigation.

### Phase 1 — Idempotent creation and persistent setup state

Owners: Identity, shared idempotency mechanism, generated clients.

- Add a stable creation command key and request fingerprint scoped to tenant and
  actor; the receipt binds the resulting company and setup run. A replay returns
  that result; a changed payload using the same key is rejected. Retain code
  uniqueness, custom-field validation, field policies, creator grants and audit.
  The existing command identity supports a null company before creation. Preserve
  Identity's source-capture session hooks and current-authority receipt rendering
  when moving creation into its idempotent transaction. Persist the submitted code
  with the command; an uncertain outcome must not trigger a new random code.
- Commit setup intent and versioned selected features with company creation. Do not
  start owner network calls before commit. Preserve compatibility through a staged
  contract rollout; old callers receive durable default setup with undecided openings.
- Add permission-checked setup status, resume/retry and pending-company discovery.
  Keep status payloads lean and bounded; sanitize internal errors. Persist recovery
  identifiers across navigation without placing secrets or financial payloads in URLs.
- Add the worker claim/lease and outbox-dispatch foundation, with deterministic
  per-step keys. Separate the company-created acknowledgement from setup completion.

Exit: dropped responses, double clicks, concurrent replay, page reload and process
restart produce one company and one setup run; rollback creates neither orphans nor
publication. A changed request cannot reuse the first company's receipt.

### Phase 2 — Complete owner setup without the browser

Owners: Identity coordinator, Accounting, Catalog, Vouchers.

- Reuse the existing Catalog and Vouchers provisioners and expose durable evidence
  for their status instead of relying on logs. Share their validators/writers with
  manual bootstrap APIs so there is one definition of every default.
- Prepare fixed accounting heads/groups/accounts, financial setup, first fiscal
  year and eligible periods through owner-local commands. Establish bounded signed
  delegated setup commands where public actor endpoints cannot serve a background
  workflow; keep authorization and audit equivalent to the approved user action.
- Run feature-dependent work only after the selected feature/configuration version
  is visible to its owner. Wait for signed source synchronization rather than fixed
  sleeps. A stale source must not certify a newer setup version as complete.
  Persist plan/catalogue versions so a deployment cannot silently change an in-flight
  request's intended defaults. Reconcile later feature changes as a new versioned
  operation, preserving the existing feature dependency and first-use locks.
- Model dependencies explicitly: company/roles and accepted features; owner context;
  chart/books/year/periods; opening choice; report prerequisites. Independent Catalog
  defaults continue when a separate optional default needs review.
- Execute explicit zero opening through existing Accounting eligibility/version
  checks. Do not grant new approval rights or confirm zero for a backfilled company.
- Preserve edited, retired and incompatible existing defaults; surface NEEDS_ACTION
  for collisions. Owner commits followed by lost acknowledgements resolve by receipt
  lookup/replay. A partial failure does not delete the company or undo completed work.

Exit: browser closure after the create response still completes all applicable
foundation steps. Native owner data verifies completion. Stale feature snapshots,
concurrent zero-opening activity and unavailable authority are handled explicitly.

### Phase 3 — Automatic reporting enrollment and complete authority plumbing

Owners: Identity, Accounting, Catalog where stock data applies, Reports, reporting client.

- Commit reporting eligibility/enrollment with accepted setup intent. Provide signed,
  paginated discovery and exact-company verification with revision/lease semantics.
  Service credentials and endpoint URLs remain installation configuration.
- Extend Accounting reporting and Identity report-authority admission to authenticate
  the service first, then validate enrollment and exact tenant/company scope. Preserve
  fresh user-grant and field-deny checks for calculations and exports.
- Replace static scope selection in source admission, running worker discovery,
  framework worker authority, job repair and temporary-artifact cleanup. New companies
  must enter the running processes' work lists without restart.
- Include Accounting-to-Catalog stock-report acquisition and its owner authorization.
  Keep inventory data completeness and snapshot-date requirements separate.
- Retain intentional explicit-scope compatibility during rollout and preserve revoked
  entries. Ensure authorization of retained historical jobs works for closed companies.
- Version shared contracts and update all consuming service dependencies/lockfiles,
  generated schemas and signed-message tests together.

Exit: two newly created companies in different tenants can each build sources and
run permitted reports through existing running workers. Wrong-company, tampered,
expired, revoked and unauthorized requests fail. Exports and recovery use the same
dynamic eligibility, not a second hidden allowlist.

### Phase 4 — Build and verify the initial report sources automatically

Owners: Reports, Accounting snapshot worker, Catalog stock source, setup coordinator.

- Wait for owner-confirmed chart, financial setup, fiscal year and relevant source
  projections. Request one FRESH generation using existing source-build machinery.
  Commit request/audit/scheduling state before acknowledging the step.
- Track owner snapshot progress, manifest, counts, checksum, schema, scope, sequence,
  projection version, coverage and verification. Publish readiness only from valid
  completed evidence, never by manually changing a status to READY.
- Verify that the overview actually calculates for the selected year and company
  currency. Cover books beginning today, in the past, in a future period and leap-year
  boundaries; a future books date needs a meaningful empty/not-started state rather
  than an invalid default date range.
- For inventory-enabled companies, acquire applicable Catalog masters and current
  stock coverage through the existing owner pipeline. Financial readiness can succeed
  while inventory readiness has a specific blocker; do not claim full inventory
  coverage from a financial snapshot or from unsupported reservations/order/GL flags.
- Finish the reporting setup step from signed/versioned completion evidence. Verify
  source controls and representative report/export availability; do not eagerly run
  every possible report or generate unsolicited export files.

Exit: a new eligible company gets a verified overview and applicable reports without
any manual refresh. A verified empty source works. Missing setup, incomplete openings,
future books and failed source validation each have accurate, distinct outcomes.

### Phase 5 — Automatic freshness, bounded scheduling and failure recovery

Owners: Accounting/Catalog source feeds, Reports scheduler/workers.

- Use committed source-sequence changes to request refresh. Emit versioned wakeups
  through the owner's transaction/outbox where needed; periodically compare signed
  owner heads to repair missed delivery. Include metadata/calendar/opening changes,
  not just posted sales, and include inventory/date-bound source renewal.
  Prepare changed inventory masters/coverage through Accounting's existing owner
  acquisition path before pinning the corresponding report barrier. Verify whether
  an incremental feed is sufficient or a fresh owner snapshot is required; refreshing
  the financial feed alone must not leave today's stock report on yesterday's lease.
- Coalesce repeated notifications, allow one source build per company, record the
  highest requested watermark and schedule follow-up work when changes arrive during
  a build. Duplicate/out-of-order events must not lose a newer target sequence.
- Reuse verified REFRESH where lineage allows; use a bounded FRESH rebuild for a
  legitimate schema/projection/lineage change. Preserve immutable old cuts and report
  results. Verification failures cannot be made successful by unbounded rebuild loops.
- Classify transient dependency failures separately from integrity, permission,
  capacity and business-input failures. Use backoff, retry ceilings and diagnostic
  state, with lease recovery and per-tenant/company concurrency fairness.
- Serve the previous verified result while updating when it remains authorized and
  compatible. Label it with verification time/lag; when owner freshness cannot be
  established, say so. Never present cached figures as current after an integrity
  or currency/context incompatibility. Dashboard GET remains read-only.
- Add a lightweight freshness/status endpoint or compatible response fields so the
  open overview can observe a new cut without re-running heavy totals continuously.

Exit: a supported committed transaction and an opening/calendar change reach the
overview automatically within the agreed healthy target. Outages, bursts and restarts
recover without lost work, duplicate generations or rewriting retained evidence.

### Phase 6 — Company setup and overview user experience

Owners: Console, generated clients; supported mobile/API consumers.

- Replace browser-side orchestration with one durable submission and progress reads.
  Persist the creation key before sending; recover the company after an ambiguous
  response. Keep server validation and existing custom-field/feature controls.
- Collect explicit opening choice and explain consequences at creation. Carry the
  choice into the authorized backend workflow; legacy/undecided companies keep a
  clear next action. Do not show a blanket posting-ready badge.
- Offer recoverable progress after reload, re-login or company switch. Cancel stale
  client requests and bind status responses to company/run/version. Changing the
  working company remains a user action; background completion cannot switch it.
- Render preparing, verified empty, ready, updating, needs business input, dependency
  unavailable and access-denied states. Business overview shows plain messages such
  as "Preparing your overview" and "Updated at ..." rather than source-generation
  terminology. Keep detailed diagnostics in authorized administrative views.
- Keep manual refresh/rebuild as an administrative recovery tool. Retry operates on
  the existing setup run and incomplete steps. Where reporting is disabled for the
  installation, explain that capability instead of leaving preparation spinning.
- Regenerate OpenAPI/TypeScript clients and update all affected callers. Mobile has
  no current company-creation screen; existing clients must remain compatible, while
  any supported creation API receives the same backend initialization guarantee.

Exit: browser tests cover close/reopen, uncertain submission, duplicate clicks,
permission changes, switching companies, responsive layouts, accessible progress,
business-input notices and recovery without creating a second company.

### Phase 7 — Deployment, health and existing-company adoption

Owners: existing Windows launchers and service deployment configuration; service owners.

- Extend the existing managed startup/stop/status registry for setup coordination,
  discovery/scheduling and worker heartbeats. Validate required broker, source and
  authority credentials, schema heads and renderer/storage prerequisites once per
  installation. Do not silently turn on disabled financial execution/release flags.
- Monitor progress as well as process presence: oldest pending setup, lease age,
  source lag, queue backlog, last verification and retry reason. Report degraded
  source/build health even if every API returns a healthy HTTP response.
- Roll out additive migrations and compatible readers/writers first; activate the
  workflow for a controlled company before making it the default. Old/new wizard
  and worker overlap must use the same owner idempotency/locking guarantees.
- Provide an audited, bounded adoption preview for existing companies, including
  Sharma Traders. Classify completed defaults, missing technical steps, missing
  enrollment, revoked enrollment, authored conflicts and unconfirmed openings.
- Apply only missing eligible work through owner APIs/commands. Preserve IDs, edits,
  retirement, history, closed periods and existing grants. Never infer a zero opening
  or automatically re-enable a deliberately disabled enrollment.
- Rollback stops new scheduling and returns compatible UI behavior while preserving
  companies, owner effects, source generations, audit and receipts. Do not drop
  evidence or blindly reverse completed financial operations.

Exit: install/start/restart discovers newly created companies without per-company
configuration. Sharma Traders can complete technical reporting setup through the
same workflow. Preview is read-only; replayed adoption performs no duplicate work.

### Phase 8 — Integrated acceptance and final review

Run focused unit/integration tests in every preceding phase; this phase proves the
whole installation with real MySQL, broker and signed owner boundaries. Use isolated
fixtures for postings and destructive failure injection, not the user's live books.

| Case | Required evidence |
| --- | --- |
| Ordinary new company | One creation action, one company/run, applicable default manifests and verified overview. |
| Lost create response | Same durable command returns the original company; no regenerated duplicate code/company. |
| Closed browser/session expiry | Accepted bounded setup continues; actions needing renewed authority become recoverable, not silently bypassed. |
| ZERO_CONFIRMED | Exactly one audited eligible zero-opening finalization; no journal fabricated; correct existing posting gates remain. |
| IMPORT_EXISTING / DECIDE_LATER | Technical setup completes; no financial assertion or fabricated opening balances. |
| Service-only / inventory / GST | Appropriate defaults, correct source dependencies and coverage, no inappropriate tax/stock activation. |
| Past/future books and fiscal boundaries | Valid period/overview behavior, no false current totals, no reopening closed history. |
| Source changes during setup | Owner results match the requested configuration revision or await reconciliation. |
| Owner commit before lost acknowledgement | Receipt reconciliation finishes the original step once. |
| Worker/broker/owner outage | Durable retry and restart recovery with clear progress; no partial verified result. |
| Running-worker discovery | New scopes appear without process restart across build, calculation, export, repair and cleanup. |
| Isolation and revocation | Two tenants and multiple companies; wrong scope/signature, expired lease, revoked grant/enrollment and field deny refused. |
| Retained closed-company history | Existing authorized historical report behavior preserved; new provisioning remains ineligible. |
| Freshness and bursts | Event replay/reordering, concurrent postings, periodic missed-event repair and bounded concurrency meet the agreed target. |
| Corrupt/quarantined source | Integrity failure visible; retained evidence unchanged; no false READY or endless rebuild loop. |
| Existing authored company | Defaults/periods/types/roles preserved; missing technical work adopted once; incompatible collisions reported. |
| Report runs and exports | Representative financial and inventory results, job retry, allowed export/download and abandoned-temp cleanup work for a newly discovered company. |
| Deployment disabled/unhealthy | Honest capability/dependency status; no perpetual spinner or automatic release activation. |

Run affected pytest suites with required coverage, Ruff, strict mypy, migration and
schema parity checks, generated-client drift checks, Vitest/RTL, applicable browser
tests and launcher tests. Walk CLAUDE.md security/correctness requirements and perform
simplification/security review; record unavailable review tooling and the equivalent
manual checks when applicable. Report actual passes, failures and skipped checks.

Exit: evidence demonstrates automatic creation-to-overview, freshness, safe recovery
and existing-company adoption. No remaining per-company environment configuration
or ordinary-user source-refresh requirement exists for the delivered capabilities.

## 5. Dependency order and delivery ledger

Recommended order: P0 -> P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> P7 -> P8.
P2 and P3 have independent portions after P1, but P4 requires both. Minimal status
APIs and worker startup support ship with their backend phase; the dedicated UI and
deployment phases integrate and verify them rather than leaving earlier work unusable.

| Phase | Status | Primary verification anchors |
| --- | --- | --- |
| P0 contracts/baseline | Implemented; acceptance below | Company creation, source worker and overview regressions |
| P1 durable creation | Implemented; acceptance below | Identity company CRUD/owner/access suites; wizard retry tests |
| P2 owner initialization | Implemented; acceptance below | Accounting `test_company_master_bootstrap.py`, `test_zero_opening.py`; Catalog/Vouchers source/default suites |
| P3 dynamic authorization | Implemented; acceptance below | Identity `test_report_authorizations.py`; owner snapshot/signature tests; Reports source/framework/dispatcher tests |
| P4 first verified source | Implemented; acceptance below | Accounting `test_reporting_snapshot.py`; Reports `test_source_versions.py`, `test_source_worker.py`, `test_company_overview.py` |
| P5 freshness/recovery | Implemented; acceptance below | Source concurrency, owner feed, dispatcher, retained-history and fault-injection tests |
| P6 client experience | Implemented; acceptance below | `company-wizard.test.tsx`, `company-overview.test.tsx`, context and browser tests |
| P7 deployment/adoption | Implemented; acceptance below | Launcher selection/lifecycle tests; audited adoption preview and native replay |
| P8 complete acceptance | Functional acceptance and both reviews completed; timing acceptance remains open | Native end-to-end record, static/contract checks, measured timing limits and final reviews |

## 6. Scope boundaries and planning risks

- This is a coordinated multi-service change with migrations and authority changes,
  not a notice-text patch. Implement and review one phase at a time.
- The exact new public/private route names and schema revisions are proposed in P0/P1,
  not reserved here. Avoid a second generic workflow framework or new datastore.
- One-time installation configuration remains necessary; the eliminated work is
  per-company configuration and manual initialization. Existing production release
  gates, unsupported features and real business inputs remain explicit.
- Existing-report runtime versions, source retention and historical calculations
  remain immutable. Freshness improvements must not change retained results.
- Explicitly decide the historical-read/service-enrollment policy and background
  delegated-authority contract before implementing them; the recommendations in
  section 3 are part of this proposal, not already implemented capabilities.
- Current workspace contains unrelated Accounting, Catalog, Reports, client and UI
  edits. Recheck their final contracts before implementation; preserve that work.
  Publish only if requested, through the repository's configured `git publish` mapping.

## 7. Planning validation

Inspected company creation, browser orchestration, existing Catalog/Vouchers
provisioners, zero-opening guards, report admission/build/verification, report-worker
authority and recovery, stock-source admission, and launcher startup. Implementation was authorized subsequently. Delivery evidence and final review findings
are recorded in `company-automatic-readiness-delivery.md`.
