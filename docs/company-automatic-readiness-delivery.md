# Automatic company readiness delivery

Implementation and local verification: 2026-11-03. Scope was authorized by the user
through all phases of [the plan](company-automatic-readiness-plan.md), followed by
two final reviews. No commit or publication was requested or performed. Concurrent
invoice, tax, stock and analytics changes in this workspace were preserved.
The final console check also required one display-label compatibility addition for
the concurrently added purchase-invoice stock action; its business logic was unchanged.

## Delivered phases

| Phase | Delivered behavior |
| --- | --- |
| P0 | Defined separate technical preparation, opening-balance readiness and source freshness. No automatic financial assertions. |
| P1 | Identity saves the company, creator grant, setup intent, eight steps and source enrollments atomically. Actor-bound idempotency recovers a lost creation response. |
| P2 | A leased worker rechecks native actor/company authority before owner commands. It prepares capabilities, starter masters, voucher defaults, chart, books and the first fiscal year. Closed periods stay closed. |
| P3 | Signed, bounded Identity discovery replaces per-company report credential editing. Accounting, Catalog, Reports, report execution, recovery and artifact cleanup use the appropriate collection/retained scope. |
| P4 | Reports automatically requests, copies, verifies and publishes the initial source. No ordinary-user refresh operation is needed. |
| P5 | Owner-sequence reconciliation coalesces updates and retains the last verified figures. Stock coverage is refreshed separately from financial completeness. Dependency failures retry; integrity failures remain visible. Company scheduling has bounded concurrency and independent progress. |
| P6 | The wizard submits one durable request. Progress and report freshness poll automatically. Opening choices, future books, missing financial years and delayed preparation are disclosed. |
| P7 | Managed setup/report workers participate in startup, status and shutdown. An idempotent private configuration helper and audited existing-company adoption are provided. |
| P8 | Native MySQL migrations, real gateway/owner/broker/report/export acceptance and focused regression/static checks were executed. Two review passes and their corrections are recorded below. |

## Local native evidence

- Identity migrated from 0097 to 0100; Reports from 0042 to 0043. Each new migration
  contains one DDL statement. Separate disposable databases passed upgrade, downgrade
  to the previous head, re-upgrade and Alembic model-parity checks.
- Sharma Traders (`01a1a038-d051-72ae-9560-fc8a2e960829`) was previewed, enrolled and
  enrolled again under tenant1's live native grants. Replay did not duplicate the
  enrollment. Its gateway readiness returned CURRENT with verified owner sequence 9,
  inventory READY and business state OPENING_REQUIRED. Its overview returned HTTP 200.
  Its opening balances and business masters were not changed by adoption.
- `AUTOREADY26` (`01a1a0d4-d926-743d-a3e0-14a7c9bb2c13`) was created through real local
  OIDC authentication and Identity's API. Replaying the exact command returned the
  same company. Setup finished without a browser. DECIDE_LATER produced no opening
  batch or journal. The verified overview returned HTTP 200.
- A report for that company ran through the real broker/worker boundary, completed,
  exported to CSV, and downloaded through a signed token (HTTP 200, 180 bytes).
- `AUTOZERO26` (`01a1a0da-481e-74f9-a365-c5d3016c9353`) was created with inventory and an
  explicit zero-opening declaration after report workers were running. All eight
  steps completed; exactly one finalized opening batch and no journal were found.
  Readiness returned CURRENT / READY / READY, owner sequence 10; overview returned 200.
- A description change on an account belonging only to AUTOREADY26 generated a new
  verified source automatically. No manual source request was made.
- Repeated unchanged reconciliation left owner sequences unchanged; checking stock
  freshness does not append a new source change merely because capture time advanced.

The initial three acceptance fixtures were clearly named and suspended through the audited
company lifecycle after verification. Their records and audits are preserved and
they can be reactivated. They are not Sharma Traders' books.

## Measured timing and validation limits

The proposed 60-second initial / 15-second incremental targets are not claimed as
a production SLO. Initial source publication measured 75 seconds for the inventory
fixture, and 103 seconds for a later timing fixture (`AUTOTIMING26`,
`01a1a0e0-64e4-71d2-a4d1-78ffe7d2d56e`) on this busy local installation. A small
master change became CURRENT automatically in 35.5 seconds. These exceed the proposed
targets; further performance tuning and controlled load acceptance remain necessary
before promising those timings. The setup is asynchronous and correctly reports
preparation/lag throughout. Its completion does not depend on an open browser.

A follow-up timing probe measured signed enrollment discovery at 0.068 seconds,
Accounting head requests at 1.1–1.7 seconds and stock evidence refresh at 6.7 seconds.
These are individual local observations, not a load benchmark. The owner refresh and
verified-source pipeline remain the performance investigation area; no verification,
current-authority check or tenant boundary was bypassed to improve the figures.
Consequently, P8's timing acceptance remains open even though functional delivery
and both review passes are complete.

The pre-existing Demo Tenant 1 source has quarantined history and a stock-source
dependency problem. This work preserves that integrity evidence; it does not silently
replace it. Sharma Traders and the newly created acceptance companies passed their
verified-source checks.

## Verification record

Counts are suite results, not an additive total; several suites were rerun after fixes.

| Check | Result |
| --- | --- |
| Identity company/setup/authority/offline migration regressions | 853 passed, four native tests deselected |
| Expanded setup regression suite | 12 passed (including all opening choices, inventory, closed periods, lost responses, revoked actors, scoped retry, adoption and support-session refusal) |
| Setup plus report-authority suite | 15 passed before the final setup additions; includes closed-company retained proofs and enrollment revocation |
| Reports source, overview, execution, recovery and export suites | 41 passed |
| Reports automatic scheduling/source regression suite | 11 passed |
| Accounting initialization, zero opening, stock and snapshot regressions | 16 passed, three native-marker tests skipped |
| Accounting snapshot suite after retry-queue correction | 5 passed, three skipped; live native snapshot acceptance also succeeded |
| Catalog stock-report source suite | 3 passed |
| Console wizard, overview and automatic readiness | Final combined run: 84 passed, including access-loss and temporary-failure regressions |
| Launcher worker selection | 9 passed |
| Private configuration preview/replay/gate preservation | 1 passed |
| Static and contract checks | Targeted Ruff, strict mypy, console TypeScript and Identity/Reports generated-contract drift checks passed |
| Native migration parity and new-revision round trips | Identity and Reports passed |

The broad Identity native migration invocation had two failures and two passes:
the downgrade-to-base and classification test both encounter the pre-existing 0058
migration's deliberate refusal to discard product-adoption evidence. Its refusal was
preserved. This is distinct from the successful new-revision round trips and parity.
The three Accounting marked skips require their dedicated native fixture; live local
owner snapshot/zero-opening tests supply additional native evidence, not a claim that
the skipped tests ran. A browser automation package was unavailable; UI verification
used RTL/Vitest and real gateway API acceptance. A whole-repository coverage/CI run
across concurrent unrelated work is not claimed.

## Review 1: behavior, recovery and simplification

Walked creation-to-owner-to-report flow, recovery after lost acknowledgements,
opening choice handling, period boundaries, scheduler progress and UI context changes.
The `/simplify` command was unavailable; this was an explicit manual review.

Corrections made and checked:

- Removed browser-owned cross-service initialization in favor of one saved command.
- Kept the original request/key after uncertain failures; definitive validation and
  code conflicts allow correction without trapping the user on a frozen bad payload.
- Kept verified figures visible while updates or dependencies fail.
- Made database outages recoverable in the setup loop and added setup workers to stop-all.
- Prevented temporary Catalog outages from consuming the snapshot integrity budget;
  corrected the worker selection predicate so those queued retries actually run.
- Replaced the all-company scheduling barrier with bounded independent tasks and
  rotation. A regression test proves a stuck company cannot prevent repeated progress
  for another company.
- Added disabled-automation and prolonged-setup notices; distinguished missing opening
  balances, future books and a missing current financial year from verified balances.
- Audited the final setup-complete transition.

## Review 2: authority, isolation and financial correctness

Walked CLAUDE.md sections 5 and 6 and the changed ingress, background execution,
discovery, retained-proof and publication paths. `/security-review` was unavailable;
this was an explicit manual review with focused authorization regressions.

- Discovery authenticates the installation requester and signs bounded, request-bound
  pages. Cursors bind requester, purpose, filter and limit. Identifier-only global
  discovery is followed by tenant-scoped owner work.
- Setup status, retries, receipts and adoption enforce current object scope. Enrollment
  does not confer actor report permissions or defeat field denials. Disabled enrollment
  is not silently reactivated. Collection excludes inactive companies.
- Background commands re-resolve active users/grants and compare approved financial
  configuration. They retain no browser token, restrict owner origins, bound responses
  and reuse stable command keys. Support impersonation cannot create a background plan
  that outlives its delegated session. Step-up companies require interactive handling.
- Closed-company report proofs remain subject to native grants and field denials;
  they do not authorize new company provisioning.
- Zero opening uses Accounting's existing review/version/eligibility/idempotency
  boundary. Other choices create no balances. Closed periods are never reopened.
- Source publication still requires verified immutable evidence and control checks.
  Quarantined evidence is retained rather than silently replaced. No money admission
  or release flag was enabled by configuration.
- Cached overview figures are cleared on 401/403/404 after permission loss; only
  recoverable refresh failures retain old figures, with a visible notice.
- No credential is stored in tracked configuration, logs or this record.

## Follow-up final review and native acceptance

On 2026-11-03 the user requested a further review, a new company and working reports
for an existing company, with changes that apply generally. Rechecked the creation
transaction, live enrollment discovery, worker startup/restart, bounded scheduling,
authority checks, recovery and explicit opening-balance choice. No company-specific
branches or allowlist entries were introduced.

One additional general defect was found and corrected: successful setup steps had
increased the retry counter, so the first dependency failure in the reporting step
could wait the maximum 60 seconds. The counter now resets after successful steps.
A regression first failed with `attempt == 8` instead of `1`, then passed after the
fix. Tests use a fixed worker clock to prove first/second failure backoffs of 2/4
seconds, stable owner idempotency keys, recovery, all opening choices and the closed
period guard. Setup plus authority tests passed (18); Reports automatic/source
worker tests passed (11). After making the retry-time assertions deterministic, the
setup suite passed again (12). Targeted Ruff and strict mypy passed. The security review
of this correction found no change to leases, authority checks or financial actions.

Native acceptance used tenant1's real local authentication and the public APIs:

| Company | Evidence |
| --- | --- |
| Readiness Final Review (`READYREVIEW26`, `01a1a0e8-3399-76f3-bdfe-c7ab8999274e`) | Created while workers were already running; replay returned the same company; all technical setup completed; CURRENT with inventory READY; overview HTTP 200. |
| Sharma Traders (`01a1a038-d051-72ae-9560-fc8a2e960829`) | Repeated the existing-company enrollment API twice; both returned enrolled without duplicating work; CURRENT with inventory READY; overview HTTP 200. |

Outstanding Bills and Stock Summary runs completed for **both** companies. All four
CSV exports completed and downloaded with HTTP 200; byte counts and SHA-256 hashes
matched their signed download metadata. The initial report probe used an incorrect
`as_of` parameter for Outstanding Bills and correctly received 422; the successful
probe used the report's declared `date_to` parameter. Inventory uses `as_of`.

The setup and Reports source workers were restarted through the managed launcher.
The existing verified generations survived, and live owner checks resumed. The new
company ID was absent from every relevant service credential/enrollment configuration;
discovery required no per-company configuration edits. General eligibility remains
active tenant/company plus report enrollment, with native user permissions checked
for report access. Existing companies use the same audited adoption endpoint; disabled
enrollment and quarantined sources retain their explicit handling.

An account-description-only change in the new review company advanced its verified
source from sequence 16 to 17 automatically in 16.2 seconds. It went through UPDATING
and back to CURRENT, and both overviews still returned HTTP 200. No source-refresh
command was submitted. Sharma Traders' business data was unchanged. The new company
remains **active for user inspection**; its opening choice is DECIDE_LATER and the
visible OPENING_REQUIRED state is intentional. No opening balances were invented.

Before deployment of the retry correction, this additional creation reached CURRENT
at 109.3 seconds and completed setup at 113.6 seconds. These measurements and the
16.2-second update still do not establish the proposed 60/15-second performance targets;
timing acceptance remains open. The retry correction is a general recovery fix,
not evidence that those end-to-end targets have been met.

## Operation and rollback

1. Apply each service's additive migrations with its DDL identity. Runtime database
   users do not need DDL grants.
2. Run `start/win/configure-company-readiness.py` with the Identity interpreter for a
   secret-free preview; `--apply` writes the private local environment files.
3. Restart affected APIs, then use `start/win/report-workers.ps1 -Action start`.
   Status lists the setup worker, Accounting snapshot worker and existing Reports lanes.
4. Existing-company adoption uses `python -m identity.tasks.report_adoption` with
   `--env-file`, `--tenant`, `--company`, `--actor`; preview is default, `--apply` is
   audited and idempotent. It enrolls reporting and does not infer missing business data.
5. To roll back scheduling, stop the setup/source workers and disable automatic-source
   admission. Retain setup receipts, companies, openings, source cuts and audits. Do not
   downgrade evidence tables in a live installation or reverse completed business work.

Shared reporting contract: 0.14.0, with all four consuming service lockfiles updated.
Generated TypeScript SDK: 0.2.59. No new service or dependency was introduced.
