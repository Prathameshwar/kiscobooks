# Purchase readiness: VM scenarios

The user authorized fixes and thirty varied purchase voucher entries, including positive
and negative cases. Test data belongs to the existing E2E Batch Goods company
`01a1b12c-b4fb-71fc-9006-3891ad1cb076`. The original Banjara draft is checked without posting it.

## Phases

1. Reproduce the no-tax account defect with preview and posting regression tests. Repair
   the narrow ACCOUNT/PURCHASE path, retain statutory guards, deploy checked code and
   preview Banjara's unchanged INR 500 draft.
2. Post thirty real test purchases through create, calculate, accept, submit and post.
   Cover no-tax expenses, goods and services, different expense accounts, batches,
   nil/exempt tax, GST 5%/18%, interstate GST, RCM where supported, discounts, freight,
   inclusive pricing and multiple lines. Record source/setup failures separately from
   invalid bill inputs; repair confirmed valid-entry failures before accepting a scenario.
3. Test deliberate invalid entries: tax/default disagreement, missing statutory facts,
   stale masters, physical quantity/batch errors, incorrect accounts, unavailable fiscal
   dates, inexact money and workflow/acceptance guards. Follow the actual rejection stage;
   an invoice calculation alone is not proof that stock posting is admissible.
4. Verify balanced journals, supplier liabilities, stock quantity/cost and no duplicate
   effects on replay. Check Purchase Register, Stock Summary, Item Ledger, Invoice Tax
   Register and Input Tax Credit Register against a fresh verified report generation.
5. Review security, money precision, replay, owner-source integrity and deployment state.
   Record the completed matrix, limitations and exact verification results here.

## Verified correction

- Accounting's old no-tax guard refused an expense with no tax default whenever the
  company had a registration, despite an explicit no-tax ACCOUNT bill selection.
- A PURCHASE/ACCOUNT/UNTAXED_ACCOUNT line can now omit that default. An existing taxable
  default still refuses the untaxed profile; Service, Goods and Sales guards are retained.
- Baseline: two no-tax preview/posting regressions failed, three guard tests passed.
- Fixed affected suites: 30 passed in 187.66 seconds; Ruff and mypy passed.
- VM Accounting API restarted successfully. Banjara's original draft now previews with
  HTTP 200, payable INR 500.0000, tax INR 0.0000; it remains DRAFT.

## Final verification

Thirty valid purchases are POSTED in the existing test company. Eighteen deliberate invalid
cases were rejected without committed financial effects. Banjara's original Tea Expenses
bill remains DRAFT; its no-tax preview succeeds.

- Supplier payable for the thirty bills: INR 113848.0800; recorded tax: INR 15820.0800.
- Thirty unique committed intents and balanced journals; each supplier credit equals its bill.
- Thirteen goods receipts reconcile their quantity and landed cost, including INR 4,590
  non-claimable GST capitalised in the computer receipt. The first POST replay returns
  the original operation with `Idempotency-Replayed: true` and one financial effect.
- Fresh verified generation `01a1b1f7-9bd5-7226-8dd2-1200da5d394d`: Purchase Register, Stock Summary, Invoice Tax
  Register, Input Tax Credit Register, and five Item Ledger instances all COMPLETE.
  All thirty purchase/tax/credit rows reconcile; five affected item quantities reconcile
  between Stock Summary, Item Ledger and native balances.
- Native costs reconcile independently. Stock Summary and Item Ledger valuation remain
  unavailable when batch positions share a warehouse cost pool: current owner coverage
  cannot assign a verified value to every batch position. No missing value was replaced
  with zero. This prevents a claim that every stock-report capability is ready.

## Repairs delivered

1. Explicit no-tax ACCOUNT purchases accept an expense without a tax default, retaining
   taxable-default and Goods/Service/Sales guards.
2. Missing/newer master replicas report synchronization lag separately from stale or retired
   evidence; Purchase retains the original key and waits within a bounded interval.
3. The tax-profile list accepts INPUT_PENDING, matching existing create/detail contracts.
   The OpenAPI and generated Accounting client purpose enum were updated.
4. GST RCM payable accounts/profiles/mappings were configured through native APIs in the
   test company. Missing mapping was legitimate company setup, not a tax-calculation bypass.
5. Nginx preserves auth-subrequest 429 as a rate-limit response with Retry-After 60 instead
   of reporting an authentication outage. Isolated nginx integration: old handler failed;
   fixed 429 and real dependency-failure cases passed. Authorization limits remain enabled.
6. Reports validates non-claimable goods GST through the exact inventory principal, while
   retaining separate pending-tax and RCM links. Six regression tests cover valid cost,
   missing pending links, wrong supply identity, amount, side and account.
7. Reports' editable module path was still pinned to an older release. Its worker import
   now resolves to the checked active source; all-source verification passes.

## Tests, deployment and review

- Accounting no-tax and affected calculation/execution suites: 30 passed; tax-profile/setup:
  14 passed. Vouchers admission/source suites: 56 passed; final source fixture check: 4 passed.
- Console purchase wait/wire/tax suites: 39 passed; TypeScript and Next production build passed.
- Reports affected invoice/source suites: 35 passed; expanded six capitalization regressions:
  6 passed. Ruff and strict mypy passed for changed backend source.
- Active VM release: `/opt/kiscobooks/releases/purchase-readiness-20261106-172200`. Accounting, Vouchers, Console and Reports services/workers
  were checked active after deployment. Source hashes were guarded before each patch.
- Manual simplify/security/correctness review: no new tenant-scope, permission, float-money,
  duplicate-effect or audit bypass found. These changes preserve source integrity and strict
  fiscal/tax/stock rejection. The named review skills are unavailable in this session.
- Publishing is incomplete: `git fetch origin main` cannot write `.git/FETCH_HEAD` under this
  session's read-only Git metadata permissions. Local task files and checked VM fixes remain
  available; unrelated local changes were not staged or published.
- Coverage is this concrete supported India GST matrix, not a proof for every possible
  business/tax profile. VAT, composition/unregistered statutory goods profiles and unrelated
  retired-page restoration are not certified by these entries.

## Positive matrix

| Case | Scenario | Payable INR | Tax INR | Result |
|---|---|---:|---:|---|
| 01 | No-tax tea expense, no classification | 500.0000 | 0.0000 | POSTED |
| 02 | Goods 5 percent GST | 191.6200 | 9.1200 | POSTED |
| 03 | Goods 18 percent GST not claimable | 30090.0000 | 4590.0000 | POSTED |
| 04 | Batch goods 5 percent GST | 141.7600 | 6.7600 | POSTED |
| 05 | Service 18 percent GST | 1180.0000 | 180.0000 | POSTED |
| 06 | Nil-rated goods | 72.0000 | 0.0000 | POSTED |
| 07 | Exempt goods | 105.0000 | 0.0000 | POSTED |
| 08 | Service GST 5 percent | 1680.0000 | 80.0000 | POSTED |
| 09 | Nil-rated service | 200.0000 | 0.0000 | POSTED |
| 10 | Reverse-charge service | 1000.0000 | 180.0000 | POSTED |
| 11 | Goods with discount and freight | 997.5000 | 47.5000 | POSTED |
| 12 | Computer GST eligible | 23600.0000 | 3600.0000 | POSTED |
| 13 | Interstate goods IGST | 11800.0000 | 1800.0000 | POSTED |
| 14 | GST-inclusive service price | 1180.0000 | 180.0000 | POSTED |
| 15 | Two no-tax expense accounts | 750.0000 | 0.0000 | POSTED |
| 16 | No-tax expense with discount | 950.0000 | 0.0000 | POSTED |
| 17 | GST 5 service discount | 1575.0000 | 75.0000 | POSTED |
| 18 | GST service with billed charge | 1298.0000 | 198.0000 | POSTED |
| 19 | Nil-rated goods second receipt | 36.0000 | 0.0000 | POSTED |
| 20 | Exempt goods second receipt | 70.0000 | 0.0000 | POSTED |
| 21 | No-tax utilities expense | 250.0000 | 0.0000 | POSTED |
| 22 | No-tax rent bill | 2000.0000 | 0.0000 | POSTED |
| 23 | No-tax expense with paise | 350.5000 | 0.0000 | POSTED |
| 24 | No-tax larger discount | 900.0000 | 0.0000 | POSTED |
| 25 | GST service rounding in paise | 1800.3900 | 274.6400 | POSTED |
| 26 | Goods tax component rounding | 95.8100 | 4.5600 | POSTED |
| 27 | Batch goods repeat receipt | 94.5000 | 4.5000 | POSTED |
| 28 | Computer GST standard eligible | 30090.0000 | 4590.0000 | POSTED |
| 29 | Nil-rated service second bill | 350.0000 | 0.0000 | POSTED |
| 30 | No-tax bill exact supplier declared total | 500.0000 | 0.0000 | POSTED |

## Negative matrix

| Scenario | Rejection stage | HTTP/result |
|---|---|---|
| taxable-default-with-no-tax | calculate | 409 |
| taxed-without-default | calculate | 409 |
| missing-company-registration | calculate | 409 |
| unknown-company-registration | calculate | 409 |
| missing-supplier-registration | calculate | 409 |
| missing-service-date | calculate | 409 |
| goods-quantity-mismatch | create | 422 |
| goods-wrong-inventory-account | calculate | 409 |
| zero-goods-quantity | create | 422 |
| float-money | create | 422 |
| closed-or-unavailable-period | post | 409 |
| stale-expense-version | create | 409 |
| wrong-payable-account | create | 422 |
| stale-preview | invoice-preview | 409 |
| unaccepted-submit | submit | 422 |
| unissued-post | post | 409 |
| wrong-calculation-hash | invoice-acceptance | 409 |
| batch-goods-without-batch | post | 409 |

[Native voucher, journal and report evidence](purchase-live-evidence-2026-11-06.json) contains
QA references and verification results; no credentials or full tax identifiers. Earlier
source-lag/duplicate-bill attempts were excluded from the intended negative results.


## Actual-code follow-up

The follow-up confirms that Accounting's no-tax rule and tax-profile enum, Vouchers'
master-readiness distinction, Reports' capitalization verifier and the Console wait helper
have identical normalized source hashes locally and in the active VM release.

The VM's editable Reports path had been repaired operationally, but a future runtime install
could recur. The repository's `deploy/ubuntu/install-runtime.sh` now explicitly selects the
active API source and configures the report source worker/calculation lanes to load their
service source from the systemd working release. Source paths resolve at process launch,
so each process remains on its starting release until restarted. Existing shared-library
and installed dependency versions are retained.

A real copied-venv regression initially failed for both API and worker imports. Three
runtime tests now pass: API (including unknown-service refusal), source worker, and all
four report lanes, each exercised across release A/B. The reviewed configuration was
applied to the active VM installer, API launcher and five Reports units; the units are active.
No full installer or unrelated configuration reset was run.

Local follow-up regressions: Accounting 6 passed, Vouchers 4 passed, Reports 6 passed;
runtime 3 passed. Accounting Ruff/strict mypy and runtime-test Ruff passed. The thirty unique
committed journals, thirteen stock receipts and eighteen rejected cases still reconcile,
as do all thirty tax/credit results and five item quantities from the verified report cut.

Manual security/correctness review found no additional scope, permission, monetary precision,
or replay bypass. The active-source fix prevents stale application imports without changing
authentication or library versions. Warehouse/batch valuation limitations above remain;
bin/batch movement values cannot be substituted for residual warehouse-pool allocation.
Git publishing remains blocked by read-only `.git/FETCH_HEAD` in this session.
