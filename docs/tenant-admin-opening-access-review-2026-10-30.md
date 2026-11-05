# Tenant Administrator opening-access review

The shipped role omitted the native opening workflow's management and posting
permissions. Source/amount controls and opening commands therefore remained read-only
even after company bootstrap. Two regressions reproduced all seven missing grants.

The user-approved policy adds existing finance management, journal/ordinary-period
posting, opening read/manage/zero and Accounting export-read keys to the canonical
Tenant Administrator. The fresh platform operator applied the fixed catalogue
through the UI; exact replay returned the same receipt and seven added grants.
Role identities, existing assignments and custom roles were retained. Fresh seeding
and new-tenant provisioning inherit this same policy.

Verification:

- 34 Identity role/seed/provisioning/platform API checks passed.
- Five opening page tests passed, including tenant/company grants and refusal to
  use another company's grants. The existing workspace/zero component suites also
  passed their 32 cases. Console TypeScript and affected Identity Ruff/mypy checks passed.
- All 17 opening and zero-opening owner cases passed on a disposable native MySQL
  schema with no skips. This is native model-schema acceptance, not migration evidence.
- Actual effective authority and writable capture fields were verified in all
  three retained companies. A separate auxiliary services company was created,
  activated and bootstrapped through the wizard. Explicit zero confirmation finalized
  once, replayed the same ID and produced no journal.
- A balanced cash/equity worksheet passed native preview through the UI, enabled
  reviewed save, and was discarded. No invented migration balances were saved or posted.

Initial harness failures are retained: an empty worksheet correctly requires the
explicit zero path; the chart seeds accumulated profit/loss rather than an account
named Capital; the success notice has both outer and inner status elements. Final
preview evidence supersedes those harness assumptions, not native owner rules.

Manual security/correctness and simplification review found no remaining defect in
this change. The named review commands are unavailable in this environment, so the
equivalent checks were performed directly. Existing permission keys were reused;
no per-user patch, token alteration, direct application-database mutation or native
guard bypass was added. These grants also authorize native finance and journal
operations, as recorded in the policy; they are not an opening-only permission set.
Close/reopen/lock/adjustment, voucher approval/post, impersonation and security-audit
self-review remain absent from the canonical role. Existing custom grants remain
independent. Ordinary voucher/stock release flags were not enabled.

Reusable cases and outcomes are in the [current CSV](tenant-admin-fixes-after-6-results-2026-10-30.csv)
and [test instructions](testing/tenant-admin/README.md). Evidence files remain in the
ignored local QA artifact directory, with protected credentials excluded from reports.
