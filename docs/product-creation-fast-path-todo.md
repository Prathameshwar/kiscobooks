# Product creation fast path: local delivery checklist

Scope: Simple and Advanced product creation through accurate progress display. VM
deployment and its live timing verification are separate checkpoints.

- [x] Phase 1: record the measured per-step timing and identify normal-path waits.
- [x] Phase 2: complete no-opening products promptly with retained receipts.
- [x] Phase 3: deliver new Catalog evidence to Vouchers without waiting for the
  periodic full source scan; retain the scan for repair.
- [x] Phase 4: recover uncertain and interrupted opening jobs automatically with
  stable commands, exact owner receipts and the existing trading fence.
- [x] Phase 5: make Simple and Advanced progress, pending, and recovery states
  accurate and persistent across navigation.
- [x] Phase 6: local end-to-end review, timing comparison, and remediation.

Phase 6 begins only after the user's confirmation.

## Phase 1 baseline and constraints

The two live Simple Goods openings measured before this change took 52.5 and
60.3 seconds end to end. Product/price activation took 23.5 and 13.4 seconds;
opening control about 2.3 seconds; Vouchers source evidence took 16.7 and
29.9 seconds; posting took 8.1 and 7.7 seconds; finalization took 1.8 and
7.0 seconds. The source worker waits 30 seconds between full scans. The Simple
Console also drives one `/advance` call per step and sleeps 100 ms between
most steps. These figures are observations, not an SLA or a new benchmark.

The source feed is a signed, scoped snapshot. The product creation coordinator
persists exact native commands before sending them. A new fast path must retain
that admission contract, the stable command keys and the stock trading fence.
Catalog currently receives short-lived gateway actor/company contexts for
`/advance`; background recovery therefore needs fresh Identity authority and
cannot replay an expired user context or store a user credential.

## Implemented local fast path (pending phase 6 review)

`POST /simple-product-creations/{id}/drive` runs bounded native steps in one
request, retaining the existing per-step command and lease checkpoints. Simple
Console uses this route and does not add a 100 ms pause between ordinary steps.
Both Simple and Advanced openings now insert a retained `SOURCE` step after
Accounting's opening control when `CATALOG_VOUCHER_SOURCE_DELIVERY` is configured.
Catalog builds only the active product's owner facts and sends them to Vouchers'
existing signed, deduplicated source ingress. The signing key must be configured
as an issuer `catalog` Vouchers source credential; `allow_enrolled_companies`
allows a newly enrolled company only when Vouchers already holds active signed
Identity company evidence. The full periodic source scan remains the repair path.
Configuration of the matching private keys is part of the later deployment.

The installed `catalog-creation-worker` discovers enrolled companies, checks
Identity for the creator's live company grants on each retry, and advances one
retained native command at a time. It does not store a user token or password.
Failures have a bounded retry delay and a sanitized saved error; successful
steps clear that error. Simple and Advanced progress screens observe the saved
status while the worker continues after navigation or a browser disconnect.

The Simple unit picker sends the resolved Product Type revision to Catalog.
Catalog returns only units in that published revision's allowed dimensions.
The exact reported first-save Grams error was not captured, so this eligibility
fix is verified but is not assigned as the proven cause of that intermittent
error.

## Later deployment configuration

For fresh single-VM installs, `bootstrap.py` generates the matching private
Catalog/Vouchers source key and enables the Identity authority key. The
systemd installer enables `kiscobooks-catalog-creation-worker.service`.
Existing installations must add `CATALOG_VOUCHER_SOURCE_DELIVERY` and a
matching `VOUCHERS_SOURCE_CREDENTIALS` entry whose issuer is `catalog`,
operation is `vouchers.sources.apply`, and `allow_enrolled_companies` is true.
They must retain `CATALOG_IDENTITY_SOURCE` with actor authorization enabled
in Identity and both Accounting and Vouchers in
`CATALOG_SIMPLE_CREATION_ORIGINS`. No VM setting or service has been changed
in this local phase.

## Local verification before phase 6

Catalog's affected product creation suite passed 24 tests, including a separate
opening workflow regression after wiring the new handoff flag. Its worker,
bounded drive, source step, and unit eligibility tests passed. Identity's actor
authorization suite passed 5 tests; Vouchers' source scope/enrollment suite
passed 11. The affected Console Simple and Advanced product suite passed 73
tests, and TypeScript type checking passed. Accounting's GST registration
validation suite and the full supplier registration field tests also passed.
## Phase 6 local review

The configured Simple opening regression now exercises real Catalog product and
unit source facts, delivers the scoped bundle before the opening voucher, and
continues through submission, posting confirmation, and finalization. Vouchers'
signed ingress and Identity's fresh creator authorization are checked in their
own service suites. No cross-service live environment was changed or timed.

The prior live VM baseline was 52.5 and 60.3 seconds. A single configured local
Catalog workflow test took about 17 seconds, including fixture setup, but uses
stubbed Accounting and Vouchers responses. Those figures are not a valid speedup
comparison. The structural comparison is that the new normal path delivers
source facts directly instead of waiting for the 30-second periodic source scan,
and the browser no longer sleeps between each native command. A post-deployment
VM measurement is still required to establish actual product save time.

Review found that a worker page ordered by immutable creation ID could repeatedly
select failing older jobs and starve jobs after the first 20. It now selects the
least recently updated jobs, and a 21-job regression proves every deferred job
gets a turn. The source ingress remains signed, deduplicated and company scoped;
worker retries recheck the creator's live permissions. Saved opening commands and
the stock posting fence remain in place. No other critical or high local review
finding remains open.

Advanced SKUs without opening stock can become active before Vouchers' periodic
Catalog source scan has copied their unit and transaction-policy facts. Purchase
creation now waits up to 60 seconds for those specific missing-source conflicts,
replaying its original idempotency key and retaining the entered bill. A continued
source outage is shown as a retryable save failure; live deployment remains the
place to verify the actual synchronization delay.

## VM verification — 2026-11-06

Release `product-purchase-20261106-1837` was activated on the Ubuntu VM with the
Catalog creation worker installed and active. Identity, Catalog, Accounting,
Vouchers, the Catalog source worker, Vouchers source worker, and Console were also
active after the release switch. The installer now creates its backup directory
and invokes Uvicorn through the selected release's Python. The latter prevents a
copied virtual environment's launcher shebang from starting the previous release.
All four affected database migrations were already at head; no new DDL was needed.

Using the deployed Console and the test tenant, `VMG0611A` became active with
100 g of opening stock, which the UI reported posted; Purchase showed 100 g in
the warehouse. `VMG0611B` became active without opening stock. The second save
took about 23 seconds from click to success; the first save was not timed
precisely. This is a measured sample, not a demonstrated general latency target.

The no-tax Purchase `VM-ACC-NOTAX-20261106` for a newly created unregistered
supplier reached POSTED, revision 3, with an accepted ₹500 calculation. A fresh
Vouchers database read found a COMMITTED posting operation with Accounting
JOURNAL, OPEN_ITEM, and SOURCE_RECEIPT references. Two earlier drafts remain
unposted: a Goods bill marked no tax with a GST-bearing product, and an account
bill using an account without a NON_GST tax default. Accounting refused both
configurations as designed. The Console now exposes the owner's refusal directly
from Create and Submit; its Purchase wire suite passed all 14 tests, including
the new refusal regression. The updated Console was rebuilt and restarted on VM.
