# Purchase API implementation evidence

Updated: 2026-10-31. Implementation is in progress under the user's authorization
for all A0–A9 phases. This report does not certify completion or activate execution.
Print remains excluded. [Checklist](purchase-api-todo.md) · [Plan](purchase-api-plan.md).

## Contract audit

| Surface | Verified source contract | Implementation / remaining dependency |
|---|---|---|
| Context/configuration | Console authenticated service proxy; company-scoped Purchase types, field-set and capability reads | Connected controller loads real field access; source versions remain pinned. Local QA authentication and scoped runtime reads passed. The accessible company has no active Purchase type and invoice execution is disabled. |
| Supplier/payable/expense | Accounting native lists and detail/version/role checks | Live lookups; supplier payable ownership and expense-head validation reused. |
| Durable account draft | Vouchers POST/PUT/GET, immutable revisions | Typed workspace mapping; distinct row version, revision ID and revision number; native UUID line identities; create/edit/reopen. |
| Uncertain commands | Idempotent native mutations | Exact request/key retained in actor/company/year-scoped session storage; explicit retry after reload; no automatic replay. |
| Calculation | Persisted version preview; acceptance creates another revision | Saved-version preview and exact hash acceptance; subsequent transitions use the returned new version. Provisional UI calculations never become owner evidence. |
| Adjustments | Invoice components + effective discount/charge policy | Explicit component mapping, stable keys and field access; unsupported third-party adjustments refused. |
| Tax | UNTAXED_ACCOUNT and dated service-tax owner contracts exist | Connected account slice records either an explicit "no tax" or India GST on service lines (supplier-charged or reverse charge, 2026-11-02; see [purchase-tax-entry-plan](purchase-tax-entry-plan.md)); goods UI mapping remains pending. No automatic untaxed fallback. |
| Duplicate supplier bill | Vouchers `GET /vouchers/duplicate-bills`; `submit` refuses `409 duplicate_supplier_bill` unless it carries `acknowledge_duplicate_bill: true` | Same supplier, bill number (case/whitespace-insensitive) and fiscal year among live bills; other kinds, cancelled/rejected bills and the voucher itself never match. Backend implemented 2026-11-01 ([review](purchase-e2e-review.md) D2); the Console warning and confirm step are pending. |
| Goods/Mixed/receipts | Common item and stock contracts exist | Accounting `tasks/invoice_execution.py::request_for` explicitly rejects stock/common item lines and GOODS. Joint invoice/stock execution cannot be certified by merely mapping draft fields. Free/scheme preview also requires published evidence. A4 remains pending. |
| Lifecycle | Native submit/approve/reject/cancel and edit to a DRAFT revision | Connected commands use the same voucher ID, expected_version and native authority. History paging and read-only historical capture preserve unsaved current entries. Role/self-approval checks remain server enforced. Where the policy needs no approval, `submit` returns `APPROVED`; where it does, the creator of any revision cannot approve. |
| Settlement | Native open items/balances and InvoiceInput allocations/tenders | Dated same-supplier/payable advances and verified base-currency cash/bank instructions mapped without reducing invoice amounts. Ordinary invoice preview rejects combined over-settlement. Recognition/report reconciliation remain pending. |
| Files | Registered Purchase uploads and live-authority downloads | User selected private VM-local disk. Immutable registrations, revision binding, hash/type/size checks and expiring downloads implemented and covered by native tests. Migration/configuration/restart and authenticated verification remain pending. [Contract and retention](purchase-supporting-files.md). |
| Posting | Native asynchronous post/operation/recovery contracts | Connected controller presents pending/committed/rejected operations, explicit recovery and reconciled voucher reads. Unverified retained operations and failed confirmed-command readbacks lock further writes. Real execution/report reconciliation remains pending. No service flags changed. |
| Reversal | Vouchers `tasks/posting.py::reverse` admits ordinary money or supported stock kinds | Purchase is explicitly rejected by the owner. Purchase reversal/replacement needs owner implementation; no unsupported reversal action is exposed. |

## Verification recorded so far

- Console affected regression: **187 tests passed in 12 files**. Subsequent adapter
  and file review tests passed (**52 tests**); the expanded connected controller
  suite passed **13 tests**, including confirmed-save readback failure and immutable
  history review. One parallel controller run exceeded the default five-second
  timeout under concurrent workspace load; the isolated rerun passed all cases.
- Vouchers native MySQL: **61 tests passed** against a newly created disposable
  loopback schema, including file isolation, current/historical access, immutable
  registrations, hash-bound large-upload idempotency and audit contracts. Native
  migrations, model/index parity and empty-schema downgrade/upgrade passed. The
  application's databases were not used or changed.
- Accounting native MySQL: **11 tests passed**, including combined allocation/tender
  over-settlement rejection and existing execution/reporting/tax contracts. Migration
  downgrade/upgrade passed. The guard preserves financial-note preparation semantics.
- Review regressions reproduced defects before their fixes: hidden invoice capture
  interpreted as empty; broad retained-command paths; operation envelopes attached
  to ordinary commands; failed execution restoration leaving writes available;
  missing rounding-account mapping; and no escape from a failed file upload.
- Full Console TypeScript passed after the review fixes. The connected browser review
  passed all **12 checks**, with no runtime errors or recorded accessibility/overflow
  violations, across light/dark/ledger themes and desktop/tablet/mobile sizes. Browser
  fixtures are explicitly mocked. The actual Next production build passed after the
  Purchase UX fixes (build `MOeStBcYjOzIBWOguLWAl`), preserving the running dev output.
  A subsequent proxy-only namespace refinement is covered by the policy tests below.
- [Runtime audit](testing/purchase-api/runtime.json): all five `/health/ready` probes
  returned 200. Local sign-in, actual account company discovery and scoped Vouchers
  capability/type reads passed. The accessible company has **zero active Purchase
  types**, `invoice_execution=false`, `financial_execution=false` and Purchase
  `execution_ready=false`. The running service does not report the new file capability.
  Thus real Purchase execution/file E2E is not established. The harness waits for
  hydrated handlers and accepts the normal onboarding landing; no credentials are
  printed or stored in tracked evidence, and no authentication settings were changed.

## Review and deployment boundary

Manual equivalents of the unavailable `/simplify` and `/security-review` commands
walked `CLAUDE.md` sections 5 and 6. Fixes above retain exact money strings, native
versions, explicit idempotent retries, live file authority and immutable history.
Pending owner profiles are refused instead of being represented as completed.
The separate Items-page proxy issue was reproduced as 422 before correcting policy
delegation; **138 affected policy/proxy tests passed**, and an authenticated browser opened
`/masters/items?returnTo=%2Fmasters` with the Products heading and no rejected Catalog
requests. A separate shell Reports overview read returned 409; this is not a Catalog
or product-authoring request and was not changed by this fix. A review regression
also verifies that search text naming a product route cannot change which policy
owns a configuration lookup.

Deployment requires Vouchers migrations **0110 and 0111** (0111 is print jobs), a private absolute
`VOUCHERS_SUPPORTING_FILE_ROOT`, matching database/volume backups, generated client
**0.2.47 or later**, and application restart. Native disposable-schema verification does not
apply that migration to the running application. No production admission flags,
posting activation, commit or publication were performed. Automated file cleanup,
taxable service capture, concurrent interactive duplicate enforcement, goods/Mixed
and receipts, Purchase reversal and real financial/stock/report reconciliation remain
pending; A0–A9 are not certified complete.

Mocks in Console unit tests are not authenticated E2E evidence. Native owner tests
do not substitute for company-scoped connected browser and reconciliation checks.

## Decisions and external inputs

- All phase confirmations were superseded by the user's uninterrupted authorization.
- Reuse the approved workspace and owner contracts; do not send presentation state
  or fixture recipes to services.
- Preserve unsupported saved capture or refuse editing; never replace hidden or
  unrepresented sections with empty collections.
- User selected private VM-local disk for Purchase and supplied local QA credentials.
  The credentials are retained only in Windows-protected local test artifacts;
  authentication and scoped runtime reads now pass. Broader Purchase E2E remains
  pending local type/setup and owner/activation prerequisites.
- Production admission/rollout and print remain separate. Global voucher batch and
  activation status are unchanged.
