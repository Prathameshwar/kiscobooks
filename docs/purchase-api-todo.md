# Purchase API integration todo

Updated: 2026-11-01. End-to-end review and fixes: [purchase-e2e-review](purchase-e2e-review.md). Current task: implement and review API phases A0–A9.
Implementation authorization: all phases authorized together; no intermediate
phase confirmation is required. Print/PDF and production activation remain separate.
Plan: [Purchase API integration](purchase-api-plan.md).
Completed UI baseline: [readiness](purchase-ui-readiness.md), [UI ledger](purchase-ui-todo.md).
Implementation evidence: [progress and contract matrix](purchase-api-progress.md).

## Phase ledger

| Phase | Deliverable | Status |
|---|---|---|
| A0 | Contract audit, runtime capability/profile matrix and dependency decisions | Source/runtime matrix recorded; VM-local storage selected; accessible company has no active Purchase type and execution is disabled |
| A1 | Live context, effective configuration, permissions and master lookups | Account slice implemented; broader profiles and live verification pending |
| A2 | Typed mapping, durable draft create/edit/reopen and safe command recovery | Account slice implemented and regression reviewed; broader profiles pending |
| A3 | Authoritative calculation/acceptance, tax, duplicates and mismatch resolution | Account calculation/acceptance implemented; broader tax/duplicates pending |
| A4 | Items/Mixed, receipt allocation, quantities, units and tracking | Pending |
| A5 | Submit/approve/reject/correct/cancel, history and concurrency | Native transitions, history paging and immutable revision review implemented; authenticated authority/conflict checks pending |
| A6 | Real terms, advance allocations and supported payment instructions | Terms, advance sources and cash/bank instruction mapping implemented; verification in progress |
| A7 | Secure supporting-file upload/download and validation | Private VM disk transport/revision binding implemented and native tests passed; live migration/configuration/E2E and automated cleanup pending |
| A8 | Real posting/reversal/recovery and financial/stock/report reconciliation | Pending owner/activation prerequisites |
| A9 | Connected UI regression, authenticated E2E and production handoff | Unit/native verification and review in progress; authenticated E2E pending local QA access |

## Planning completed

- [x] Inspect completed UI scope and the existing live account-Purchase builder.
- [x] Inspect configuration, draft/revision, invoice preview/acceptance, lifecycle,
  execution, attachment metadata and proxy contracts.
- [x] Record the persisted-draft calculation dependency and acceptance revision change.
- [x] Record demo correction versus real unposted revision semantics.
- [x] Separate source existence from runtime readiness and activation authority.
- [x] Write phases, owners/dependencies, review gates and PU01–PU09 acceptance mapping.

## Pending implementation

- [x] A0: obtain authorization for all API implementation phases.
- [x] A0: record the field/profile/endpoint/owner source matrix.
- [ ] A0: verify running contracts and classify missing owner work against global batches.
- [ ] A0: settle genuinely unresolved duplicate, mismatch, terms and file-transport rules.
- [ ] A1: integrate scoped configuration, field access, live lookups and stale-response protection.
- [ ] A2: implement typed wire adapters and durable save/edit/list/reopen with exact retries.
- [ ] A3: implement save → authoritative preview → acceptance → returned revision flow.
- [ ] A3: enforce supported tax profiles, duplicate identity and supplier-difference policy.
- [ ] A4: integrate goods/Mixed, receipt modes, exact quantities/units and required tracking.
- [ ] A5: implement real lifecycle, revision lineage, role checks and concurrency recovery.
- [ ] A6: integrate eligible sources, terms, advances and payment intent/recognition states.
- [ ] A7: integrate authorized file bytes, verification, private access and retention lifecycle.
- [ ] A8: verify execution/reversal, asynchronous recovery, exactly-once effects and reconciliation.
- [ ] A9: run connected UI/accessibility/performance, contract/API/browser E2E and full build checks.
- [ ] A9: complete manual simplify/security review, recovery/rollback and cutover handoff.
- [ ] Obtain separate production activation/rollout authorization after concrete evidence.

For every phase: record tests and evidence, review findings, completed fixes and
remaining dependencies; proceed between phases under the user's blanket authorization.
Missing prerequisites remain pending rather than becoming simulated success.
Global voucher batch/activation statuses are not changed by this planning ledger.

## Reviewed implementation slices

- [ ] Purchase printing is now authorized (2026-10-31); phases, fixes and evidence are tracked in [purchase-print-todo.md](purchase-print-todo.md).
- [x] Company settings includes a scoped Voucher types card; 23 settings-page cases and TypeScript passed (2026-10-31).
- [x] Account-only live mapping, saved UUID/revision/version handling and exact retry journal.
- [x] Saved-revision calculation and acceptance; supplier-difference reason and rounding account.
- [x] Dated supplier advance balances and verified cash/bank instruction mapping.
- [x] Combined ordinary-invoice allocation/payment over-settlement guard and native regression.
- [x] Native transitions and read-only history review that preserves unsaved entries.
- [x] Retained execution verification and confirmed-save readback locks; explicit recovery.
- [x] Private VM-disk file registration, live authorized downloads and immutable revision binding.
- [x] Native owner verification: 61 Vouchers and 11 Accounting cases; migration parity/roundtrip.
- [x] Review fixes: 52 adapter/file tests and 13 connected-controller tests passed.
- [x] Refresh production build and connected-browser review after the last Purchase UX fixes.
- [x] Resolve authenticated browser handshake and read actual company Purchase capabilities/types.
- [ ] Prepare a reviewed test-company Purchase type/setup and verify live commands; execution admission remains separately controlled.
- [x] Company onboarding (verified live 2026-11-01): a new company receives default voucher types (`PUR_ACC`, `PUR_PRD`, `PUR_MIX` among them) when Identity's company fact is applied, and `POST /voucher-type-defaults/bootstrap` backfills existing companies. Execution admission stays separate. The goods and mixed types can be drafted but are refused at acceptance until their execution exists.
- [ ] Deliver dated taxable-service capture and concurrent interactive supplier-bill duplicate guard.
- [ ] Complete goods/Mixed/receipt execution with the stock and tax owners.
- [ ] Complete Purchase reversal and real financial/stock/report reconciliation.
- [ ] Apply/rehearse Vouchers migrations 0110 and 0111 (supporting files, print jobs) and Accounting 0226-0227 on the dev stack with the selected private volumes, backup/restore and service restarts. Rehearsed on a throwaway schema (2026-11-01); not applied to the running database. See [purchase-e2e-review](purchase-e2e-review.md) section 5.
- [ ] Deliver audited orphan maintenance; preserve registered/historical files meanwhile.
