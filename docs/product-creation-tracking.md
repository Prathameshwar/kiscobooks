# Batch and serial entry during product creation

User request, 2026-10-28: enter batch/serial details in the appropriate product
creation step. Reuse the existing Catalog and Accounting owners and shared UI.

- [x] 1. Add optional initial batch and serial/IMEI entry to Tracking and review
  (step four), and the equivalent simple-product section. Verify company features,
  published requirements and field permissions. Validate entered facts from any
  Create button; preserve them on configuration changes or save failure.
- [x] 2. After product creation, retain the product receipt and pending tracking
  entries. Review/confirm native product activation, then use existing Accounting
  preparation commands with stable per-record retries and partial progress.
  Never recreate the product or infer stock quantity/value from prepared records.
- [x] 3. Test both product experiences, scope/configuration/permission gates,
  validation, activation blockers, partial completion and uncertain retries.
  Review correctness/security and UI/flow, fixing findings.

Decision: Accounting currently requires an activated product and its published
tracking profile. Preserve that guard. Batch/serial entry is captured during
creation and prepared after explicit reviewed activation. Catalog creation and
Accounting preparation are distinct transactions; the UI must report partial
progress honestly and retry only outstanding commands. No schema or new API is
needed, and this flow never posts opening stock or changes admission flags.

## Verification and reviews (2026-10-28)

- 101 affected Vitest tests passed across seven suites: creation wizard,
  creation attributes, simple product UI, inventory actions, tracking inputs,
  tracking draft validation and integration with both editors. After adding the
  missing-configuration-access regression, all 28 tracking tests passed again
  (102 distinct affected tests passed in total).
- Correctness/security review: preserved native Catalog activation review and
  Accounting ownership, checked company/item/profile receipts, field permissions,
  bounded inputs and exact retry identities. Fixed continuation after an uncertain
  activation succeeds; regression test first demonstrated the failure. No new
  routes, permissions, models, migrations or seeds are needed.
- UI/flow review: shared sections, grids, inputs, notices and confirmation dialog;
  optional expiry respects company configuration. Required response fields must
  be readable, and retained dates cannot bypass revoked write access. Fixed the
  simple-product saved summary to offer active-product actions after preparation.
  Missing configuration access now explains the prerequisite instead of showing
  a loading state indefinitely.
- The requested `/simplify` and `/security-review` commands are unavailable in
  this agent environment; the equivalent reviews were performed manually above.
- Live browser attempt: authenticated Console route reached, but Create product
  did not render within the 60-second wait. Live creation/activation/preparation
  and theme/viewport screenshots are therefore not claimed for this change.
- Full Console type check passed on the final rerun. The earlier concurrent
  `SalesEntryPage.tsx:211` error had been resolved by its owner; this task
  preserved that session's source.

Decision log: capture one optional initial batch and up to 50 physical serial
records, including configured serial/IMEI slots. Preparation after activation is
explicitly confirmed. On failure retain the product and completed identities;
uncertain responses permit only the identical command retry, while definite
rejections permit editing outstanding entries. Pending entries remain in this
page's guarded draft; leaving/reloading is not a server-side saved tracking job.
