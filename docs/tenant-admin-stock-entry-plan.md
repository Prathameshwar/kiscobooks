# Tenant admin #15: stock entry and remaining owner work

Review the existing Accounting/Vouchers contracts before adding the offered
Stock adjustment screen. Opening, receipt, dispatch, transfer and linked returns
have native typed capture; physical count/adjustment has no executable capture
contract at this plan's original baseline. The scoped 2026-10-31 implementation
is recorded below. A correction must never be silently sent as a receipt or opening.

1. Inventory supported actions, field sets, owner execution and count/reason
   contracts. Keep the negative-stock, expiry, valuation, first-use and fiscal
   guards. Both FIFO and moving average are already selected for initial valuation.
2. Connect existing native stock preparation controls where their type and profile
   prove the action. Expose actual missing count authority as a recoverable setup
   state with relevant configuration/stock links until B25 is implemented. Do not
   manufacture a count effect or activate C3 through a navigation change.
3. Complete independent UI/access/reload/validation tests and native existing-stock
   checks; distinguish these from nonzero execution and inventory reconciliation.
4. Count implementation requires the governing D03/B25 freeze, physical-count
   grain, valuation/mapping and backdate conflict contract. Remaining goods invoice,
   B27a-e projection and C3 evidence stay in the owner TODO; record exact gaps.

This plan refines the authorized sequence and does not select unspecified stock
recognition/correction policies or change application databases directly.

## Selected workflow, 2026-10-30

The user selected **physical count with calculated difference**. Capture each
explicit observation separately from its book quantity; zero is a counted zero,
an omitted position is uncounted. The variance is accepted physical quantity minus
the protected book quantity at the count cutoff, never availability or a client
balance overwrite. Existing D03/B25 cutoff/locking and D02 valuation contracts
must govern the owner effect and concurrent movements. This decision selects the
entry workflow; it does not select a backdating/valuation shortcut or activate C3.

The independent existing-stock native suite passed 31 cases with zero skips on a
disposable native MySQL schema. Physical count implementation remains a separate
work package; these tests exercise existing effects, concurrency, costing, GL,
reconciliation and reporting and do not establish count execution.

## Count cutoff decision, 2026-10-30

The user selected **allow movements and reconcile them against a recorded count
cutoff**. Capture the book quantity from protected native movement history at the
cutoff, compare the physical observation with that quantity, and retain later
movements as separate evidence. Apply the approved variance to the current
position exactly once; never overwrite the current balance with the observed
count. Concurrent approval/posting must verify the cutoff comparison and current
position versions. Surplus valuation remains governed by its explicit owner
value/cost policy; no zero-cost or automatic last-cost default is selected here.

## Surplus valuation decision, 2026-10-30

The user selected **current verified native stock cost; review when no cost
exists**. Quantity and cost evidence must refer to the same native stock position,
costing scope and approved revision. Missing/unverified cost is a review state,
never an inferred zero. Existing FIFO/moving-average policy determines verified
cost; current stock value divided by quantity in the browser is not this contract.

At the 2026-10-30 baseline, native count execution remained B25 under D02/D03 and C3. The then-current typed
`StockAction` contract has no count/adjustment action. These decisions close the
two user policy questions; they do not manufacture an action supported by the
owner service or certify the remaining owner release work.

### Native count work sequence

1. Freeze the position grain, lock order, stock-date/backdating frontier and cost
   evidence contract with the existing D02/D03 owner specification.
2. Add native count session/observation/recount/approval schemas, scoped storage,
   migration, immutable cutoff and observed-zero versus uncounted semantics.
3. Compute native protected book-at-cutoff quantities and delta; retain concurrent
   later movements separately and version all observation/approval evidence.
4. Apply the approved delta once against the locked current position. Resolve
   surplus cost through the verified owner policy, requiring review if absent.
5. Complete tenant isolation, period/first-use, stale approval, concurrency,
   idempotency and quantity/value/GL reconciliation integration evidence before C3.
6. Connect the generated typed UI to those released native contracts. Until then,
   never send a count as an opening or receipt or claim a posted adjustment.

## Scoped native implementation and cost clarification, 2026-10-31

The user delegated the remaining FIFO choice. A single verified remaining-layer
cost is automatic; mixed FIFO layer costs require explicit authorized review.
Moving average uses the verified native pool value/quantity. Empty, missing or
unverified cost requires review; a verified native zero is distinct from missing.
Reviewed cost records a reason and pool identity/version, revalidated at execution.

The first executable contract is PHYSICAL_STOCK/STANDARD with COUNT at company-owned,
non-serial USABLE warehouse/bin/batch positions. Accounting freezes book quantity
against committed stock generation, stores append-only versioned observations,
and applies the cutoff difference to the current position while retaining later
movements. Overlapping later corrections invalidate an earlier cutoff. Counted
zero is explicit; uncounted cannot post. Claims remain immutable after reversal.
Surplus origins retain unknown receipt age rather than inventing it.

Fixed/measured entered quantities use signed Catalog revision proof and native
grids. Owner reads happen before write transactions. Existing period, expiry,
negative-stock, Identity and financial admission controls continue to govern
execution. The offered Stock adjustment route now prepares native observations.
It does not activate financial release flags.

Native domain/effect, public API, captured revision and component regressions
cover zero/recount, later movements, cost review, replay, reversal and tenant scope.
See [updated findings](testing/unit-stock-review/findings.csv) and
[reusable cases](testing/unit-stock-review/cases.csv). Serial counts, damage/disposal
and the broader B25/B27/C3 release evidence remain pending; this scoped result does
not close those milestones.
