# Phase 5 execution contract — indents, quotations, orders and general vouchers

Status: **B28 IN_PROGRESS (capture slice only)**, 2026-10-11. This is the detailed implementation contract for
B28-B36. It refines the saved [batch note](voucher-batch-note.md),
[tracker](voucher-delivery-tracker.md) and [todo](voucher-implementation-todo.md);
it does not verify a batch or activate a company profile. B28 follows B08/B15; B30
needs B26; C3 needs C2, B20-B36 and the B27a-e stock reports. Do not use unfinished
stock, tax or automatic-deal producers as if their receipts were authoritative.

## Common rules for every batch

- Keep one `voucher`/`voucher_revision`/`voucher_line` aggregate. Add typed shared
  details for fulfillment terms, schedules and source claims; no table per kind.
  Runtime-created types inherit the same family/profile restrictions. Typed header
  and item custom fields continue through the existing Identity field contract.
- A requisition, quotation, order, memorandum or scenario revision does not post GL,
  tax, stock, bill settlement or a reservation. Issuing/accepting it is a document
  event. Only a separately admitted real voucher operation can create effects.
  B31 adds reservations only for explicitly selected profiles.
- Use tenant/company composite references, immutable accepted revisions, current
  field permissions, idempotent operation receipts, audit/outbox, fiscal-year
  numbering and bounded queries. Preserve original-year claims across a year
  boundary. Revisions and source claims never rely on display numbers as identity.
- Counts of ordered, executed, billed, returned, cancelled and outstanding units
  are independent facts. A signed stock movement is not inferred from a bill;
  one physical effect may be referenced by multiple commercial documents only
  within its remaining guarded entitlement. Reports cannot authorize a claim.

## B28 — non-posting requisition, quotation and order lifecycle

1. Admit `SALES_ORDER/STANDARD`, `SALES_ORDER/QUOTATION`,
   `PURCHASE_ORDER/STANDARD` and `STOCK_JOURNAL/REQUISITION` against effective
   type/class/company settings. The requisition has native purpose `PROCURE`
   or `INTERNAL_ISSUE`; it is always non-posting. Require an explicit party
   role where the profile needs one, plus item/unit/version, exact requested or ordered quantity, currency, validity/required
   dates and typed fulfillment terms when the profile needs them.
2. Add a shared, revision-owned terms detail (validity, proposed/confirmed date,
   destination and delivery/payment terms) with native constraints and a bounded
   schema. Preserve quoted price, charges, discounts and tax *estimates* as
   versioned calculation evidence only when B15/B16 can resolve them; fail closed
   for an unsupported estimate profile. An accepted order retains the source
   quote/indent revision, terms and calculation hash.
3. Implement draft/edit, submit, approval/rejection, issue, acceptance/decline,
   expiry and cancellation as explicit state transitions with actor/date/reason
   evidence. Existing protected issue numbering remains the sole series owner.
   A revision after approval requires new acceptance. No stock, tax, GL or
   reservation event is emitted by this lifecycle.
4. Verify wrong-company references, stale type/party/item policy, custom-field
   denial, two-actor approval, concurrent acceptance, fiscal rollover, expired
   quote refusal, and zero owner effects after every non-posting transition.

## B29 — schedules and exact source conversion

1. Store `voucher_fulfillment_schedule` under the common revision/line: due date,
   destination, planned entered/base quantity, unit/conversion version and
   optional price/tax segment. Sum scheduled base units to the line's supported
   ordered quantity at accepted revision precision. A schedule has no physical
   movement and cannot claim future stock as present stock.
2. Introduce a guarded source-claim identity keyed by original immutable
   revision, source line/schedule and conversion purpose, plus target revision/
   line. Serialize changes through a source scope guard. Claim totals cannot
   exceed the supported original quantity or approved tolerance, even when two
   targets use different HTTP keys. Rollback leaves no claim or audit event.
3. Support source-to-target split and multiple-source consolidation only for
   compatible company, party, currency, unit/conversion, tax, terms and policy
   snapshots. Recompute unsupported/stale values on the target; never copy a
   quoted tax amount into a real invoice as statutory authority. Preserve
   paid/reward identity and award scope, preventing each split from earning a
   new full 10+1 reward.
4. Verify partial/concurrent claims, stale source revision, cross-year source,
   wrong-company target, cancellation/replacement and exact residual quantity.

## B30 — order, movement and bill linkage

1. Accept only committed Accounting stock/invoice result IDs as execution or
   billing evidence. Record source slice, original line/schedule, physical
   operation and invoice line links; assert one effect cannot be consumed twice
   beyond its own remaining quantity/value entitlement. A bill that references
   an earlier delivery has no second stock movement.
2. Maintain separate outstanding-to-execute, executed-not-billed,
   billed-not-executed (only when the supported deferred profile permits it),
   returns and short-closed quantities. Acknowledgment, cancellation, close,
   reopen and replacement append reasoned events and never erase committed
   movements, invoices or return claims. Reward entitlement follows its
   configured order/bill/fulfillment trigger and remains one source allocation.
3. Recheck current close/reopen settings and Accounting receipts at commit;
   recovered retries return the same link/claim result. Verify partial movement,
   partial invoice, return, two simultaneous bills, year crossing, and absence
   of duplicated paid/free stock or COGS.

## B31 — conditional reservation profile

Select stock and credit reservation capabilities independently in the tracker.
When selected, Accounting owns guarded stock/credit capacity and immutable
reserve/release/consume/expire history. Vouchers owns the request and result
reference. Every transition shares the stock issue/hold/count guard or the
credit owner guard, and rechecks eligibility at consumption. Expiry is not a
movement. Without selection, B28-B30 do not imply capacity claims and no report
may portray unreserved demand as reserved stock.

## B32 — procurement and fulfillment registers

Reports projects source revisions, schedules, guarded claims, committed movement/
invoice links and closure history using a complete owner barrier. Deliver
indent/quote/order registers, due and overdue schedules, open quantity,
executed-unbilled, billed-unmoved where supported, and cross-year backlog.
Projected supply/demand and reorder views require explicit horizon and
deduplicated source slices; unknown/missing stock producer coverage is `UNKNOWN`,
not zero. Reservation columns appear only after selected B31 evidence. Rebuild
and frozen-run equality, permission masking and nonmultiplying joins are exit
tests, along with VCF07/VCF18 date-purpose settings.

## B33 — memorandum, optional and pro-forma

Use the common voucher revision with a non-posting designation and expiry/validity
evidence. Conversion creates a new draft real voucher with an original-revision
link; it revalidates parties, masters, policy, tax dates, amounts, permissions and
fiscal readiness. No memo/pro-forma issue, print or expiry can post an effect.
Verify that conversion to an unavailable target profile is refused and that two
conversions do not silently share a financial or stock operation identity.

## B34-B35 — scenario Reversing Journal and reporting

B34 stores scenario membership with effective windows and an immutable selected
voucher revision. The Reversing Journal exists only in a scenario projection;
expiration changes scenario applicability, never the actual GL. B35 provides
actual-versus-scenario ledger, trial balance and statement/register exports with
explicit scenario ID and snapshot. Actual tax, stock, cash and statutory outputs
exclude hypothetical facts. Rebuild and permission tests prove that scenario
joins cannot alter actual totals.

## B36 — core review and activation handoff

Verify all 18 core kinds/profile gates, artifacts, history, type retirement,
permissions, generated clients and console/mobile behavior where applicable.
Run cross-service native DB/broker crash/replay and wrong-company tests for each
new relation and mutation; reconcile exact quantity/claim/movement/bill, GL/tax,
stock cost and report snapshots. Review unsupported/conditional profiles, B31
selection, fiscal-year carry, security and operational recovery. Record B28-B36
as VERIFIED only with evidence in the tracker. C3 remains a separate per-company
activation after C2 and all required B20-B36/B27a-e gates pass.

## Decision log

- 2026-10-11: Expanded the saved B28-B36 batches into owner records, command
  boundaries, dependencies and acceptance cases. Kept B31 conditional and
  preserved C2/Phase 4 prerequisites; no phase status or activation changed.
- 2026-10-11: Began a bounded B28 capture slice ahead of release: common item detail
  now has a nullable `planned_quantity` distinct from actual/billed units (migration
  0052), and immutable `voucher_fulfillment_terms` stores shared revision-owned
  purpose, validity, required date, destination reference and terms (0053).
  Quotation/requisition/order validation requires non-posting item content and
  exact positive planned units at submission; draft/read roundtrip, tenant
  isolation and post refusal have targeted tests. This is not B28 completion:
  acceptance/decline/expiry lifecycle, source conversion, estimates, approval
  matrix, complete client flow and prerequisite B15 verification remain open.
  Vouchers' full local suite passed 143 tests with two broker-only skips after a
  wrong-company test expectation was corrected; the targeted B28/domain/isolation
  group passed 49. Complete source mypy and Ruff pass, as do OpenAPI/client
  generation checks and all eight API-client tests. No live MySQL migration
  roundtrip or Phase 5 acceptance matrix is claimed.
  Identity's native voucher field contract now recognizes `fulfillment_terms`
  and `planned_quantity`; its two focused source/contract tests and static checks
  pass. This keeps field-level policy metadata aligned with capture.
- 2026-10-11: Extended the bounded B28 slice with template rendering of native
  fulfillment terms, an accurate `VoucherDetail` response schema, and explicit
  issued-order `accept`, `decline` and elapsed-validity `expire` transitions. New
  permissions are catalogued and seeded to approver/controller roles. The action
  guard limits these transitions to non-posting order/requisition profiles;
  cancellation of an issued document is supported, but an accepted document
  cannot be edited or cancelled through the generic route. Submitted Sales
  Orders/quotations require a CUSTOMER party; Purchase Orders require SUPPLIER.
  API coverage verifies approval, issue, permission denial, accepted/stale
  decisions, time-based expiry, protected term printing and zero posting effects.
  Vouchers passed 146 tests with two broker-only skips before the party-role
  tightening; its affected order/domain group passed 25 afterward. The platform
  permission group passed 33, Identity role tests passed nine and API-client
  tests passed eight. Generated OpenAPI/client checks, Vouchers mypy and Ruff
  passed. Full B28 lifecycle and Phase 5 remain unverified.
- 2026-10-11: The user authorized a commit and `git publish` only after Phase 5
  is complete and reviewed. Keep the workspace mapping and stage only task
  files. Do not publish this preparatory slice as a completed Phase 5 release.
- 2026-10-11: The user selected **both FIFO and moving average from initial
  release** for D02. This resolves the costing-method choice, while D02's
  recognition, source allocation, correction and native stock gates remain
  open. The console now captures typed non-posting fulfillment terms and planned
  item units, keeping actual/billed units zero; issued order decisions are
  permission-gated in the UI. The real field-set exposes both new native fields;
  the console draft test confirms exact planned units and terms with no posting
  date. Targeted console tests and typecheck pass.
