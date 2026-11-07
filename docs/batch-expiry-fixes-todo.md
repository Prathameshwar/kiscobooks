# Batch and expiry repairs

Authorized 2026-11-07: fix the consolidated findings one at a time, maintain this
checklist, and leave VM updates for later. Sources are
[configuration/master review](batch-config-master-review-2026-11-07.md) and
[create/edit UI review](batch-expiry-ui-review-2026-11-07.md).

## Delivery sequence

Each numbered item is a separate repair phase: reproduce the defect with a
fixed-behavior regression test, confirm failure, implement the smallest complete
repair, run affected checks, review correctness/security, then record evidence
here before moving on. Cross-service/schema repairs include matching contracts,
migrations where needed, generated clients, consumers and documentation. Existing
concurrent work must be preserved. VM deployment is deferred.

| # | Source | Repair | Status |
| --- | --- | --- | --- |
| 1 | B01 | Prevent batch-off from weakening mandatory tracking/date/FEFO rules | Complete |
| 2 | B02 | Enforce expiry feature on date correction and replay | Complete |
| 3 | B03 | Lock company features on actual batch/expiry use | Complete |
| 4 | B04 | Separate opening valuation cost from purchase-reference pricing | In progress |
| 5 | B05 | Supply initial/subsequent batch-price master workflow | Pending |
| 6 | U01 | Display/initialize readable expiry independently of manufacture access | Pending |
| 7 | U09 | Preserve uncertain Purchase batch creation across retry/edit/dismiss | Pending |
| 8 | B06 | Enforce MRP declaration policy and repair unused bad declarations | Pending |
| 9 | B07 | Align zero-cost opening validation across client/native contracts | Pending |
| 10 | B08 | Remove redundant SKU pricing requirements for batch products | Pending |
| 11 | U02 | Render/enforce applicable required dates in create/edit forms | Pending |
| 12 | U03 | Reject/disable date correction when no date changed | Pending |
| 13 | U04 | Include batch dates and physical MRP in final review | Pending |
| 14 | U05 | Identify incompatible hidden dates before submission | Pending |
| 15 | U06 | Align normalized code/date validation with native constraints | Pending |
| 16 | U07 | Validate opening-date relationships before creation | Pending |
| 17 | U08 | Preserve specific field errors through Advanced recovery | Pending |
| 18 | Gap | Define/enforce shelf life and expose optional manufacture entry | Pending |
| 19 | Gap | Provide controlled batch-choice transition for eligible unused products | Pending |
| 20 | Gap | Support explicit quarantine disposition for expired opening stock | Pending |
| 21 | Gap | Support Advanced zero-stock batch identities and prices | Pending |

## Evidence ledger

No repair is complete merely because an observation probe passes. Review probes
assert bad behavior; convert them to fixed expectations as their defects are
repaired. Record tests that failed before the repair, final passed checks and any
remaining limitation per phase.

### 1 — Mandatory batch rules

- New policy regressions: 11 failed before repair; all 13 pass after repair.
- Affected Catalog policy/creation/security suites: 21 passed. Accounting stock
  tracking source suite: 17 passed. Scoped Ruff and Mypy passed.
- Batch-off is rejected for mandatory dates, shelf/minimum life, FEFO or serial
  rules. Existing incompatible retained choices fail closed during resolution;
  they no longer silently erase physical rules. Optional batch-off remains valid.
- Updated the governing opening plan and converted the B01 observation probe.

### 2 — Expiry feature admission

- New API regressions reproduced 3 failures before repair; all 4 pass after repair.
- Affected Accounting tracking suite plus new regressions: 13 passed. Scoped Ruff
  and Mypy passed. The B02 observation probe now expects rejection.
- Prepare/correction and their idempotent replays check the resulting expiry state
  against current company features. Optional expiry removal remains allowed;
  rejected additions leave the row and its version unchanged.

### 3 — Actual first-use locks

- Regressions reproduced missing optional-expiry reservation/admission, unsupported
  registration ownership, and a late-create-after-abort race before their repairs.
- Identity reservation/transport suites: 15 passed. Accounting stock effects and
  feature reservation suites: 20 passed; tracking/expiry suites: 13 passed;
  registration/recovery regressions: all 7 passed (6 together plus the final
  committed-receipt/late-abort check separately).
- Scoped Ruff/Mypy passed, Identity OpenAPI/client generation checks passed, and
  the typed transport's 2 Node tests passed. Generated Identity types compile.
  The broader API-client typecheck remains affected by an existing/concurrent
  Accounting `AccountCreate` type mismatch; its Accounting artifacts were not edited.
- Empty registration reserves identity capabilities with disable protection, then
  commits confirmation alongside the native record. Rejected local writes release
  reservations; transient/uncertain requests retain the exact retry identity.
  Company locking and a terminal marker prevent late creation after abort, while
  committed receipts prevent late abort. Registration does not claim financial
  posting or inventory movement. Actual optional expiry participates in stock
  posting/reversal first use. No new database schema was needed.
- Updated feature semantics, private contracts, existing delivery consumer/backlog
  routes, dependency metadata and generated client. VM deployment remains deferred.

## Deployment

- [ ] Local repair/verification completed for all numbered items.
- [ ] Task changes reviewed without including unfinished concurrent work.
- [x] VM update performed when requested: [deployment record, 2026-11-07](vm-latest-build-2026-11-07.md).
