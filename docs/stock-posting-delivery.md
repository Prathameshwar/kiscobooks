# Native stock posting: phase 6 implementation record

## Ubuntu activation, 2026-11-05

The single-VM Ubuntu deployment now aligns the four stock owner connections,
checks the three delivery worker configurations, enables Accounting stock posting
and Vouchers stock execution for new installations, and installs/enables the
Vouchers source/execution and Accounting posting-delivery workers. The same
idempotent step runs during upgrades; an explicit existing `false` admission flag
is preserved. This is the user's requested deployment activation of native stock
posting and the company opening setup gate. It does not activate ordinary money
or invoice execution, or the separate inventory report cards. The earlier
disabled-admission statements below record the state before this activation.

Scope explicitly confirmed by the user on 2026-10-28: build the native stock engine
with batch/serial management. Maintain the parent checklist in
[batch-serial-delivery](batch-serial-delivery.md). Stock capture/storage and voucher
financial-year designs remain authoritative; no stock authority moves to Catalog.

Implementation and both final review passes completed on 2026-10-28. All review
findings were corrected and verified. Final native MySQL rehearsal: 51 passed;
137 affected UI checks, TypeScript, live six-layout browser checks and all eight
schema/readiness checks passed. Normal stock admission remains disabled and the
existing report cards remain disabled; deployment activation and complete Reports
source cuts retain their separate gates. The current task is complete; wait for
the user's confirmation before starting another task.

## Selected release

- Company-owned usable goods at real warehouses, including untracked, batch,
  serial and combined tracking. Prepared identities have no stock until posting.
- Opening, uninvoiced receipt/dispatch, paired or dispatch/receive warehouse transfer, linked returns
  and guarded compensating reversal. Other ownership, external custody,
  manufacturing, reservations and financial purchase/sales invoice recognition
  require their own native voucher profiles; never silently reinterpret them.
- Separate company/SKU/warehouse FIFO or moving-average pools. Physical receipt
  origins and issue selection remain independent of cost consumption. Transfers
  conserve quantity/value and preserve receipt age. Returns reuse original units
  and carrying cost; residual allocations conserve the original value exactly.
- Negative stock, holds, expired issues, insufficient remaining shelf life and
  backdates affecting later warehouse pools fail closed. Expiry includes the
  entire expiry date in the company's timezone. Retired identities cannot post.
- Inventory value and clearing accounts must be configured and validated before
  valued openings, uninvoiced receipts or dispatches. No account is guessed from
  a name, and unavailable valuation is never recorded as zero.
  A company created with inventory gets five standard stock accounts and their policy from its books
  step (2026-11-03, [purchase-product-review](purchase-product-review.md#company-setup-defaults-2026-11-03));
  they are created under fixed system keys, never adopted from an existing account.
- Every effect, including a zero-value transfer, requires fiscal/stock-date,
  current company/actor/field authority and Identity first-use fences. Quantity,
  value, unit custody, GL, receipt and outbox commit atomically in Accounting.

## Work packages

- [x] 6a. Exact cost/eligibility contracts and invariant tests; reviewed owner/schema
  manifest, including canonical non-null identities and receipt/cost separation.
- [x] 6b. Accounting positions/balances, immutable posting/movement/value evidence,
  receipt origins/allocations, FIFO layers or average pools and unit position.
- [x] 6c. Authenticated Catalog facts outside money transactions with a bounded
  source fence, warehouse/profile enforcement and compatible policy acknowledgements.
- [x] 6d. Company stock account mappings and owner prepare/reserve/commit/recovery;
  first-use and period guards also apply to zero-GL effects.
- [x] 6e. Vouchers typed stock capture, approval/execution adapter and source claims;
  receipts, issues, transfers, linked returns and compensating reversals.
- [x] 6f. UI entry/availability/history, useful failure/retry recovery and native
  end-to-end fixtures. Synchronize models, migrations, scripts, contracts and SDK.
- [x] 6g. Quantity/value/GL reconciliation, concurrency, duplicate source effects,
  closing/backdating and outage/recovery verification before activation.

## Owner/schema review

Accounting will reuse its company lock, fiscal periods, native journals/lines,
voucher execution/source guards, prepared intents, Identity posting reservations
and atomic audit/outbox. Stock-specific tables must carry scoped local FKs and
indexed source/position histories. Canonical warehouse/lot identity uses explicit
non-null normalized keys alongside actual dimensions, with checked equality.

Vouchers capture manifest (0098–0100, one CREATE per migration): reusable
`voucher_stock_context`, `voucher_stock_detail` and `voucher_stock_unit` sections.
Common item detail remains the sole captured quantity/item authority; native stock
details supply physical dimensions, reviewed inward value and original source
claims, with bounded unique serial selections. Every child is revision scoped,
immutable, and writable only while its parent revision is created. These are common
sections for the supported stock kinds, not separate document tables per kind.
No nullable composite unique key or digest alone establishes a position.

Reviewed Accounting table manifest (one CREATE/DROP per migration): `stock_position`,
`stock_balance`, `stock_posting`, `stock_movement`, `stock_receipt_origin`,
`stock_origin_balance`, `stock_origin_allocation`, `stock_cost_pool`,
`stock_cost_layer`, `stock_cost_pool_event`, `stock_cost_allocation`,
`stock_value_entry`, `stock_unit_position`, `stock_movement_unit`,
`stock_source_claim`, `stock_account_policy` and `stock_opening_bridge`. Reuse the existing prepared
voucher intent rather than creating a second source-commit authority.
Nullable actual bin/lot references have non-null UUID keys; database checks require
the actual ID when present and the all-zero binary sentinel when absent. The
sentinel is a canonical key only and never creates a fake batch, bin or warehouse.
Local batch/unit/source/pool/movement references use tenant/company composite FKs.
External Catalog/Vouchers identities stay opaque owner references with retained
authenticated snapshots. Posting and immutable histories forbid update/delete;
only guarded balance/residual/custody projections may advance.

Opening value either supplies its authorized combined GL opening or links to an
existing posted GL opening line. Immutable bridge claims prevent counting the
same inventory asset twice; non-opening stock posting requires reconciled opening
coverage. Stock value is not re-opened at year rollover. An uninvoiced supplier
return clears its original received amount and uses current carrying cost; any
difference requires the configured stock-variance account rather than an
unbalanced journal or an invented amount.

Native schema extension review, 0189-0192 (one atomic ALTER per revision): explicit
transit custody for the company's reserved transit location; separate return,
transfer, invoice and reversal claim counters on each source movement; retained
per-unit carrying value for exact serialized returns; typed dispatch/receive
transfer posting actions. An unrelated shipment cannot satisfy another shipment's
receipt. Cost allocations and receipt age follow the original transfer claim,
including partial receipts over a financial-year boundary.

0193 adds `stock_execution_plan`: immutable, one-to-one prepared source-fence and
effect evidence beneath the existing `voucher_money_intent`. It has no independent
lifecycle or commit authority. It permits recoverable prepare/reserve/commit with
fresh source authority and stable effect IDs; source facts and stock versions are
rechecked before the common owner transaction commits.

0194-0198 review: indexes for remaining FIFO layers and physical cohorts avoid
scanning exhausted history. `stock_origin_claim` guards each partial source/cohort
claim without repeatedly summing all past returns. Unit custody and immutable
movement membership retain the physical receipt origin as well as assigned cost;
returning a particular serial cannot consume another serial's receipt cohort.
The new origin fields refuse unreviewed backfill of retained legacy unit moves.

0199 adds immutable `stock_claim_allocation` evidence alongside residual counters.
Each partial return/transfer records the exact original quantity/value it claims;
compensating reversal unwinds that evidence, including original supplier clearing
value when current carrying cost differs. Projection counters are not a second
value store. Catalog 0209 adds bounded owner definition leases with exact delegated
company authority, signed request/response framing and immutable retained evidence.

FIFO inward ordering belongs to the warehouse cost pool: a new warehouse receipt
or genuine customer return creates an inward cost layer at that movement date.
Physical age remains on the original receipt cohort independently. A bin-only
transfer within one warehouse restores the same cost layers, and a compensating
reversal restores its original allocations rather than inventing a new purchase
age or changing the FIFO order.

Separate physical receipt origins, origin-position residuals and movement-origin
allocations preserve age without treating a FIFO layer as the physical batch.
Separate cost pools, FIFO layers, allocations and immutable value entries retain
carrying value without counting caches and history as separate assets. A serial
has at most one on-hand position and cannot be received again as a new identity.

Catalog facts cross an authenticated owner boundary before the local Accounting
transaction. An execution must retain the exact published definitions and source
fence. Warehouse policy acknowledgement must use an explicit Accounting adapter
for the existing `billing` consumer identity; renaming that wire identity or
asserting enforcement from configuration alone is prohibited.

This manifest is an implementation review, not a claim that the above tables,
workflows or activation gates are already delivered. Update individual packages
only when their native verification is green.


Automatic enrollment and first-use boundary review:

- Source discovery uses an explicit Vouchers installation capability, signed
  paged active-company enrollment IDs, and each owner's native admission check.
  Existing explicit snapshot, financial and report credentials remain scoped.
- The ordinary Identity reservation credentials intentionally reject automatic
  enrollment. A stock release must not broaden those credentials to make new
  companies work. The native stock adapter will use a separate signed, delegated
  stock first-use channel and the existing PostingReservation lifecycle.
- The common reservation will retain a typed STOCK authority discriminator,
  source execution/hash/action, and guarded exact replay. The stock credential
  can confirm/abort only STOCK reservations; ordinary financial reservations
  remain inaccessible. A fresh gateway actor/company proof is mandatory for a
  new reserve, with stock, voucher and ledger permissions. Retained signed proof
  is usable only to retain a cancellation tombstone, never to grant a reserve.
- Stock confirmation/abort delivery remains atomic-outbox based and covers both
  journal-valued and zero-GL effects. Connection scripts must pair credentials
  without enabling posting or guessing a financial company grant.

0200 retains the indexed original destination of every staged shipment. Accounting
0201-0209 add explicit immutable currency to every monetary stock history and
projection; native reversible migration/model parity and 21 integration checks
passed and the changes are applied locally. Source verification has thirteen
passing checks, including gateway path preservation. The current ledger suite
has fourteen passing cases, including refusal of unverified prepared serials;
valued and zero-value compensating execution reversals both pass.

## Verification history

Earlier stage-specific pending statements below are retained as history. The
completed work packages and final verification evidence supersede those notes.

- Accounting, Catalog, Vouchers and Identity are locally aligned at migrations
  0209, 0209, 0100 and 0089 respectively. All eight APIs and the source/execution/
  posting-delivery workers were restarted successfully. Connection scripts pair
  stock credentials and automatic enrollment without changing activation flags.
- The separate stock Identity channel now reuses the common PostingReservation
  lifecycle. Native MySQL first-use checks and the reversible 0089 migration passed.
  Financial reservations remain inaccessible through the stock credential.
- Stock account setup supports an explicit, audited correction of the latest
  unused mapping. Used mappings, inflight preparation and established predecessor
  date windows are protected. A future mapping cannot silently move carrying value
  to another inventory account. Existing ordinary posted GL history requires
  reconciliation before adopting an account for native stock.
- Physical issue order is now enforced independently from cost allocation.
  FIFO preserves original receipt age, including same-date transfer ties; FEFO
  orders eligible expiry dates, then receipt age and stable identities. Held,
  retired and expired stock is excluded. Source-linked returns/transit use their
  original claims. Selection is bounded to 200 physical cohorts per issue.
- The SQLite compiler/ledger/execution regression run passed 27 checks; the newer
  policy/candidate run passed seven checks, and FIFO/FEFO/held-serial selection
  passed three. The Console stock and Masters tests passed 36 checks and the full
  Console TypeScript check passed. Expanded native verification is running.
- Warehouse operation revisions are live controls, as defined in their owner
  module. Catalog release effective dates govern numbered delivery boundaries;
  they do not postpone an already published operation revision. No attempt was
  made to reconstruct a nonexistent historical manifest from current flags.

Pre-activation implementation tasks (completed in final verification):

- [x] Complete and test source-verified candidate/available-serial APIs and the
  native stock voucher entry controls, including contributor field denies.
- [x] Implement current warehouse/bin NoStock safeguards and the explicit
  Accounting adapter for the existing `billing` policy consumer identity.
- [x] Complete quantity/value/GL reconciliation, projection rebuild verification,
  stock ledger/report handoff and the native multi-owner execution fixture.
- [x] Refresh every affected contract/client; run final native/browser coverage.
- [x] Perform both complete final reviews and fix each review's findings.

Stock posting remains disabled. Preparation and read/configuration evidence is
not a claim that native physical posting is ready for activation.

### Continuation checklist, 2026-10-28

- [x] Fresh tenant3 browser login after restoring the disabled host network adapter.
- [x] Live QA-bin deactivation through Catalog, Vouchers and Accounting, retaining
  versioned history; no browser errors. Native Catalog retirement/fence checks
  previously passed ten tests, and the broader warehouse regression passed 29.
- [x] Automatic Main/transit locations and operation policies when verified
  inventory-enabled companies enroll. Preserve existing authored revisions;
  inventory enabled after creation also receives defaults. Shared public/worker
  provisioning passed 25 warehouse/default tests; source worker restarted.
- [x] Exclude receipts later than the requested selection date (four physical
  ordering regressions). Receipt serial choices exclude previously received units;
  linked choices retain original movement membership (three candidate checks).
- [x] Connect native stock capture to common voucher drafts, zero billed quantity,
  shared field-set controls, warehouse/bin/batch/serial choices, carrying value,
  destinations and source evidence. Initial UI suites passed 26 tests; reference
  hydration and availability controls are receiving further review.
- [x] Finish native stock entry browser checks, linked opening selection, final
  permission/validation review and uncertainty/retry handling.
  The native tenant3 receipt draft saved with its batch and serial. A subsequent
  preview verified readable base-unit labels without saving another draft; all
  three themes at 1440/390 pixels passed with no browser exceptions or horizontal
  document overflow. The affected Console suites passed 88 tests and typechecking.
- [x] Finish retained product-definition and root-commit lease regression checks.
  Stock shapes must not change through a newer source definition or new warehouse.
- [x] Owner quantity/origin/FIFO or moving-average value reconciliation against
  immutable history, inventory GL control reconciliation, and period-close
  barriers for prepared stock and undelivered zero-GL confirmation. Five stock
  reconciliation tests and ten existing fiscal API tests passed together.
- [x] Eligible posted GL opening lookup, sparse-field permission checks, exact
  remaining claims and shared-style linked-opening selector; initial native
  storage/API test passed and shared claim-expression refactor is being checked.
- [x] Complete owner reconciliation/rebuild verification, policy release adapter,
  multi-owner posting fixture and synchronized contracts/client validation.
- [x] Real four-owner QA receipt, duplicate delivery and compensating reversal:
  quantity/value 1/12.50 then 0/0, two immutable postings, GL and physical control
  reconciled. Normal admission stays disabled; only the owned QA rehearsal host
  enabled posting. Identity first-use confirmation was delivered and verified.
- [x] Explicit zero-opening confirmation through Company readiness, all three
  themes at desktop/mobile sizes, no page exceptions or horizontal overflow.
- [x] Policy adapter native follow-up: Catalog 17 and Accounting focused 34 checks
  passed. Shared policy/retirement contracts passed 21 after transport separation.
- [x] Complete clock-skew ordering and projection recovery regressions/native checks.
- [x] Verify permanent startup of source/execution/Identity-confirmation workers.
- [x] Final review one: security/correctness and fixes.
- [x] Final review two: UI/flow, failure/recovery and fixes.

The resumed native Accounting rehearsal passed reversible 0210–0212 migrations,
model parity and 42 stock checks before the final definition/commit-lease additions.
Accounting remains at 0212 and Vouchers at 0101. The latest source changes do not
add tables or alter the activation settings.

Further continuation evidence:

- Native Accounting upgrade/downgrade/re-upgrade and model parity passed with
  64 stock integration tests. Catalog native retirement/default provisioning
  passed 12 tests. The normal installation's stock admission remains disabled.
- The user authorised permanent roles/access needed by this workflow. A seeded,
  company-scoped Stock Operator role now supplies native voucher capture,
  posting/reversal, ledger recording and batch/serial management dependencies.
  Company creation grants that fixed role alongside Company Administrator to
  the actual company creator, under the existing audited ownership exception.
  It grants neither voucher approval nor period closing. Revoked, expired or
  scheduled grants are never silently restored. Both owned tenant3 companies
  passed the bounded native bootstrap/replay, and the seed immediately replayed
  with 13 roles/630 permission grants unchanged. Fourteen role/seed checks pass;
  the broader creator/assignment/API suite previously passed 52 checks. The native
  company-create rehearsal retained no test company and verified two grants and
  three atomic audits before rolling back.
- Fully reversing an initial serial receipt restores its prepared identity. The
  receipt selector now includes that identity and excludes issued stock retaining
  an origin, rather than requiring a new serial. Five candidate tests pass.
- Reconciliation review reproduced a count-preserving serial custody swap that
  previously escaped detection. Exact latest immutable membership, position,
  origin and last-movement checks now supplement quantity counts; regression and
  native follow-up verification are in progress.
- A bounded, loopback-only multi-owner rehearsal is being prepared for the owned
  QA company. It uses real Identity gateway authority and native Catalog/Identity
  owner transports, while normal admission stays disabled. QA stock accounts
  were created/activated through native APIs. The first posting attempt correctly
  refused absent fiscal setup; no physical stock was posted by that attempt.

The remaining adapter, reporting/rebuild, multi-owner execution and two final
review entries above remain open. This continuation is not a release-complete
or activation claim. After the current task is finished, wait for the user's
confirmation before starting another task (instruction 2026-10-28).

Policy and opening continuation:

- The explicit native policy-inspection adapter now binds the original company
  publisher, exact release manifest/digest, nonce and bounded freshness under a
  separate paired service key. It preserves the `billing` consumer identity and
  ordinary acknowledgement monotonicity. Missing owners, disabled admission and
  future releases retain pending delivery. Supported native flags are checked
  against the compiler's actual operation catalogue, including the adjustment
  flag enforced by compensating reversals. Free-form adjustment entry remains
  outside this selected release. No fake acknowledgement
  is generated merely because connection settings exist. Thirteen Catalog
  digest/delivery checks and the Accounting signed inspection check passed; 21
  shared transport/contract checks passed. Native follow-up and final review remain.
- The user explicitly selected narrow company-admin zero-opening confirmation.
  The API atomically creates/finalizes an initial empty opening, audits both
  transitions and provides a protected eligibility review. It refuses historical
  openings, journals, stock, pending execution, stale setup, closed opening periods,
  extra amount/account/date fields and field denies. Four API checks passed.
  Company readiness reuses the shared dialog, field, feedback and retry controls;
  the same request/key is retained after an uncertain response. Twenty-two
  opening/readiness UI checks and TypeScript passed. Live application is next.
- Additional reconciliation now checks source and cohort claim counters against
  immutable allocations, including partial return/transfer and reversal unwind.
  The ledger/reconciliation regression passed 24 checks. SQL comparisons preserve
  native decimal sums and normalize SQLite residue at the four-decimal storage
  scale. The prior native focused run passed 28 checks before these last additions.

### Final verification continuation, 2026-10-28

- The four-owner QA rehearsal completed a valued receipt, retained replay and
  compensating reversal. Stock/GL reconciled at 1 unit/INR 12.50 and subsequently
  zero; both immutable postings remain. Identity first-use confirmation and the
  reversed serial's receipt eligibility were subsequently verified again.
- Normal startup now starts configured source, execution and posting-confirmation
  workers even when another API's readiness fails. Admission may remain disabled
  while retained work recovers. All three configuration preflights and actual
  managed restarts passed; three startup-selection checks passed.
- The affected Console run passed 122 checks and TypeScript. The subsequent
  posting/workflow run passed 15, including the explicit issue-before-stock-post
  guidance. Native stock commands retain the real owner-issued voucher number
  without changing their immutable revision hash. Legacy commands omit the new
  optional field and preserve their request digest and recovery semantics.
- Native movement evidence now commits through the existing Accounting reporting
  feed in the same transaction as stock, GL and the common execution receipt.
  Dispatch is distinct from recognized sale; reversal retains its actual signed
  delta. A company-monotonic commit generation plus bounded leg ordinal supplies
  stable order across writers' clocks. Three Accounting handoff checks and 83
  inventory report/consumer checks passed. Reporting contract 0.7.1 and all three
  service consumers' lockfiles are synchronized.
- This incremental movement handoff does **not** assert full-company report
  coverage or invent Catalog labels, residual bin assets or voucher numbers for
  older receipts. Reports still requires its complete verified inventory source
  cut; existing disabled report cards remain disabled as requested. Complete
  inventory report activation belongs to its existing B27 release gates.
- The first final correctness/security review reproduced cross-process clock
  ordering failures and an incomplete-history repair preview. Guards now use
  committed owner generations, validate exact serial custody and individual FIFO
  residuals, and refuse incomplete native immutable history. The review also
  caught and corrected the policy adapter's reversal/adjustment-flag mismatch.
  Native follow-up passed before the review was marked complete.
- The subsequent same-day FIFO regression reproduced a later receipt's cost and
  physical origin being consumed first when its writer's UUID clock was behind.
  FIFO layers, physical cohort paging and preview tie-breaks now use the owner's
  committed generation after the business receipt date; FEFO retains expiry as
  its primary order. Eight ordering/selection checks passed. Missing production
  owner order fails closed; unreceipted storage fixtures retain their legacy tie.
- The broad native run passed 43 checks; the first review follow-up passed 11.
  The final native run repeats the affected warehouse ledger/selection paths and
  adds a real two-connection last-serial race under the company row lock.
- Domain tests passed 17 checks with 96% cost, 98% eligibility and 100% tracking
  branch-aware coverage. The full Accounting source passed Ruff and strict mypy
  (221 modules); Vouchers strict mypy passed 87 modules. A pre-existing unrelated
  long notification line still prevents a repository-wide Vouchers Ruff claim;
  all changed Vouchers source and test files pass their applicable Ruff checks.
- All eight native schemas match migrations/models after the other session's
  Catalog 0210 rollout. This stock work did not apply that live Catalog change.
  Repeated browser receipt previews pass all six theme/viewport combinations,
  with no browser exceptions, horizontal overflow or additional saved draft.
- Final native MySQL run: 51 passed, including the same-day FIFO/FEFO regressions
  and actual competing last-serial writers. Native migration round trips and
  stock/common-intent parity passed again. Both complete reviews are closed.
- Audit review reproduced invalid top-level repair evidence. The producer now
  uses Audit's supported `context` field; all five repair regressions pass and
  invoke Audit's actual strict payload parser on the emitted evidence. No source
  histories or monetary effects changed to correct this wire format.
- Final browser/native receipt confirmation and API health checks passed. The
  owned Accounting/Vouchers processes and required execution/confirmation workers
  were refreshed. A separately managed Reports process was preserved; refresh
  its consumer/runtime before any future native inventory-report activation.

### Operator projection recovery

`apis/accounting/tools/stock_repair.py` is an offline service-operator command,
not an HTTP balance-authoring API. Run it with Accounting's existing environment
and explicit `--tenant` / `--company`; preview is the default and changes no rows.
It returns a company generation, opaque digest and row counts, never balances or
credentials. Apply additionally requires `--apply`, `--expected-generation`,
`--expected-digest` and a bounded `--reason` from that review.

Both paths hold the normal Accounting company posting lock. Prepared execution
blocks recovery. Reads page at 200 rows, with a one-million-row rehearsal bound
and at most 10,000 changed projections; larger repairs require reviewed recovery.
The tool reconstructs quantities, warehouse cost/method/last-use state, origins,
FIFO residuals, serial positions and source/cohort claims from retained history.
It preserves all source identities, currencies, movements, costs, GL and owner
receipts. Apply rejects a stale preview, reconciles physical and GL control,
advances the company generation and atomically audits activation; any failure
rolls back the entire repair. Missing structural/history rows are unsupported
recovery, never invented balancing movements. FIFO/moving-average recovery,
scope, stale preview, pending-work and failure rollback checks passed; the final
native rehearsal also includes these paths.

### Retirement coordination implementation contract

The native adapter will retain the existing `billing` acknowledgement identity.
Catalog holds its company policy lock and refuses retirement while any current
stock-definition lease is live. It then obtains a bounded Vouchers lease, which
checks current pending stock revisions and prevents new references under the
existing VoucherCompanyGuard, and asks Accounting for current NoStock evidence
under the same AccountingSetup lock that serializes posting. No owner performs
outbound I/O inside an Accounting money transaction. The Catalog configuration
transaction may wait on these bounded owner checks while holding its policy lock.

This ordering closes the stale-clearance race: a new Accounting operation cannot
obtain Catalog source authority while Catalog holds the policy lock; an earlier
operation's live source lease blocks retirement, and an already running local
commit must finish before Accounting grants NoStock. The Vouchers lease separately
prevents a draft/reference race. Catalog must validate exact scope, command hash,
row versions and freshness before flushing/committing deactivation. The lease is
released after completion or failure and otherwise expires. An absent owner or
uninitialized Accounting company is SOURCE_UNAVAILABLE, never assumed empty.

NoStock includes quantities, unit custody, warehouse carrying value, prepared
native posting and both source/destination obligations of staged transfers.
Bins share a warehouse cost pool: summing their historical movement values does
not establish a residual bin asset when physical FEFO and financial FIFO/MVA
consume different origins. Empty bin custody can clear independently; retiring
the warehouse still requires its entire quantity and cost pool to be zero.

Accounting 0210-0212 add the indexed location and pending-intent probes (one CREATE
INDEX per migration). Native upgrade/downgrade/re-upgrade, model parity and forty
stock integration checks passed; these indexes are applied locally. The local
Accounting head is now 0212. The current local NoStock checker passes source and
destination transfer obligations and empty-bin checks; the coordinated transport
and Vouchers lease remain to be connected and verified before activation.

The native retirement connections and Vouchers write lease are now implemented
and configured locally. Vouchers 0101 passed native reversible migration/model
parity and 21 capture/posting/lease checks and is applied locally (69 tables).
Accounting and Vouchers private transports additionally verify the original
gateway subject and exact lifecycle permission; signed wrong-company/invalid-key
tests fail closed. Catalog checks fresh owner evidence under its company lock,
retains the `billing` retirement acknowledgement and checks freshness again at
root commit. Four existing warehouse/bin lifecycle checks pass with current owner
evidence. The complete Catalog regression and native concurrency/failure checks
remain in progress. All eight services passed readiness after the owner restart.
