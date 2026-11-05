# Product opening stock review corrections

User approved all four review fixes on 2026-10-29.

## Delivery phases

1. Add failing regressions for first-registration conflicts, closed-book adoption,
   cross-chunk cohort ordering and opening-versus-issue expiry behavior.
2. Preserve the original worksheet baseline, enforce the existing opening revision
   window for adoption, match native ordering and align opening batch eligibility.
3. Run affected UI/API checks and disposable MySQL workflows; review scope, period,
   arithmetic, audit and retry invariants and record evidence below.

All three phases completed. Existing paths, schemas, permissions, posting admission and stock valuation remain
in place. No commit or publication is included.

## Verification

The UI and API regressions were added before their production fixes. The initial
UI run failed eight cases, including the registration race, punctuation/case
ordering, near-expiry entry and adoption blockers. The initial API run reproduced
successful adoption with closed/locked books where rejection was required.

- Console opening regression suite: **88 passed in 11 files**. This includes the
  101-cohort chunk boundary, exact retry behavior, first-registration conflict and
  explicit discard/review recovery, expiry-date inclusivity and blocker controls.
- Console TypeScript check passed.
- Ruff passed for the changed Accounting task and new test/verification modules;
  mypy passed for the changed Accounting task.
- Accounting OpenAPI export and generated TypeScript client checks passed without
  contract changes. Scoped whitespace validation passed.
- Accounting API/calculation/preview/legacy suite: **38 passed**. Closed/locked
  and later-closed books reject adoption without new control, revision, posting,
  journal or outbox records. Missing `period.post` is rejected; native opening
  accepts unexpired batches below the outward-issue remaining-life threshold.
- Vouchers opening import/file suite: **32 passed**, including native chunk-order
  validation, source normalization and retained partial-import recovery.
- Migrated disposable MySQL suite: **21 passed**, covering these six regressions,
  positive legacy adoption, native FIFO/tracking cohorts and opening races. The
  runner upgraded a fresh random schema to Accounting head 0222, then dropped it.
  Its earlier failed-run schema was also dropped. The dedicated loopback MySQL
  instance started for verification was shut down afterward; pre-existing schemas
  were preserved.
- Initial SQLite and MySQL verification exposed a test snapshot taken before the
  fixture period-change audit committed; the snapshot now follows that commit to
  isolate adoption. Both corrected runs passed in full.

## Correctness and security review

The `/simplify` and `/security-review` slash commands are unavailable in this
session. Their required reviews were performed manually against CLAUDE.md
sections 5 and 6. No further findings remain in the changed paths:

- Adoption calls the existing revision-window guard while holding the existing
  company setup lock, before control/revision creation. It inherits native period
  authority and later-closed-book restrictions; tenant/company filtering and
  transactional audit/outbox handling remain in the owner command path.
- Completed idempotent receipts retain their replay behavior. The registration
  fix pins an absent baseline as well as an existing version/hash, preserving
  local edits until explicit discard without silently replacing another control.
- Sorting changes only canonical cohort order. Decimal amounts, conversion
  proofs, valuation and native chunk limits remain owner-validated.
- Batch entry accepts only unexpired opening receipts. Manufacture, ownership,
  allocation and native posting checks remain; outward-issue shelf-life policy
  is unchanged.

No new schema, migration, event contract, permission key, dependency or shared
library was introduced. This verification targets opening-stock workflows; no
full-repository coverage run or new live browser rehearsal is claimed. Existing
application company data and posting activation settings were not modified.
