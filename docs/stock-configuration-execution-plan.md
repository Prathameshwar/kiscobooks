# Stock configuration and negative-stock execution

**Status:** implementation contract; stock posting and nonblocking modes are not active.
**Owners:** Accounting is the stock quantity, value and posting owner; Catalog owns item,
unit and inventory-template definitions; Vouchers owns document capture and confirmation;
Identity owns the company inventory capability. This extends the existing B20-B27 stock
work, not a separate balance or ledger.

## Current finding

Catalog already stores `BLOCK`, `WARN` and `ALLOW` on inventory template revisions and
copies the chosen value to an activated `item_inventory_profile`. Its effective-item read
correctly reports Accounting stock execution as unavailable, with an extra reason for a
nonblocking negative-stock request. The live Accounting and Vouchers code contains no stock
position, movement, cost layer or stock posting owner. A configured value therefore cannot
authorize a sale, transfer or consumption today. Turning off that readiness check would
advertise an unsafe feature.

TallyPrime exposes a voucher warning choice for negative balance; this platform also needs
a posting admission choice because stock and financial value are integrated. The initial
executable policy remains `BLOCK`. `WARN` and `ALLOW` are committed target modes, but each
must pass the accounting/valuation and release gates below before it can be published as
executable. Configurations remain visible as definitions while a mode is unavailable.

## Configuration contract

| Scope | Owner and rule |
|---|---|
| Company | Accounting publishes a dated stock-execution policy, default `BLOCK`, after Identity `inventory` capability and stock-owner readiness. It is a maximum permission, not an instruction to create stock. |
| Item | Catalog's activated `item_inventory_profile.negative_stock_policy` is a pinned item request. Changes after first stock movement require a dated successor and an Accounting compatibility check; never rewrite posted history. |
| Voucher type/class | Vouchers may narrow the allowed mode for an operation. A voucher setting cannot widen the company/item result or disable period, hold, expiry, owner, reservation or valuation guards. |
| Effective mode | Strictest of company, activated item, executable Accounting capability and voucher restriction, in order `BLOCK < WARN < ALLOW`. Missing/stale source or unimplemented cost method yields `UNAVAILABLE`, not `ALLOW` or a guessed zero balance. |

`BLOCK` rejects a source issue that would make eligible unreserved quantity negative.
`WARN` previews the shortage and requires a posting-time acknowledgement bound to the
accepted stock calculation hash, actor, source scope and current position version; posting
rechecks the scope under lock. `ALLOW` does not require interactive acknowledgement but
still records the shortage and provisional-cost evidence in the owner receipt. A warning
preference is not a stock policy override. Shortage permissions are limited to explicitly
eligible, non-serialized, non-lot-controlled goods until a physical identity and costing
contract for other classes exists. No mode permits issue from another location, owner,
custodian, held/expired stock, a reserved claim or a closed stock period.

## Delivery phases

1. **S1 — policy/source contract.** Reconcile existing Catalog template and activated-item
   values; add Accounting's dated company envelope and pinned Catalog item-profile source,
   with signed complete snapshots, version fencing and an effective-policy read. Vouchers
   stores only a restrictive type/class reference. An unavailable owner/mode fails closed.
   Test date boundaries, stale source, tenant/company scope, field permissions, first-use
   locks, policy narrowing and historical replay.
2. **S2 — stock owner baseline.** Add Accounting position, immutable signed movement,
   source-effect receipt, receipt-origin/lot, FIFO/moving-average value and GL bridges,
   stock-period/count/hold controls and common lock order. Every receipt, issue,
   transfer, adjustment, return and opening uses one atomic owner admission path. Absence
   of a position is verified zero only after source readiness; competing issues cannot
   oversell. Deliver `BLOCK` before any nonblocking mode. Test replay, reversal,
   backdating refusal, concurrent issues, quantity/value conservation and report rebuild.
3. **S3 — voucher execution.** Connect Sales, Purchase, challan, stock journal,
   manufacturing/job work and returns to the owner through accepted source claims and
   idempotent effect identities. Non-posting orders/quotes do not move stock. An invoice
   and its linked challan cannot issue twice. Recompute the effective stock policy at
   posting under the owner lock; a draft preview cannot authorize a later shortage.
4. **S4 — controlled negative quantity.** Add separate shortage layers and a supported
   provisional-cost source (prior verified cost or approved standard cost). Do not use
   sale price or silently invent zero cost. The issue posts provisional inventory/COGS
   effects once; a later receipt closes the matching shortage and posts a dated cost
   true-up without rewriting the original voucher. If no valid provisional cost exists,
   reject even under `WARN` or `ALLOW`. Keep FIFO/moving-average positive layers and
   deficits distinct; prohibit backdated reordering until its revaluation workflow exists.
5. **S5 — reporting and activation.** Expose on-hand, eligible, reserved, available and
   negative quantity separately by item/owner/location, plus open shortage age,
   provisional value and later true-up lineage. Reconcile movement, position, value,
   COGS, GL and item/group reports at one checkpoint. Enable `WARN`/`ALLOW` by explicit
   capability only after S1-S4 evidence and two-year fiscal/close/replay rehearsal.

Changing a policy to `BLOCK` stops new deficits but does not erase existing shortages;
receipts and authorized correction remain possible. Cancelling or reversing a source must
respect intervening claims and use a new open-period correction where needed. A transfer
cannot cure one warehouse's shortage by borrowing another warehouse's position implicitly.

## Release tests

- Zero, exact-zero and one-unit shortage; item/company/voucher policy combinations;
  warning acknowledgement stale after another issue; 100 concurrent issues of the last unit.
- FIFO and moving-average receipts and issues across negative-to-positive transitions;
  cost true-up and GL conservation; no unknown/zero provisional cost shortcut.
- Batch, serial, expiry, hold, reservation, consignment and ownership refusals even when
  a generic item policy says `ALLOW`.
- Partial dispatch/invoice linkage, returns, stock journal, manufacturing and job work;
  period close, fiscal rollover, reversal, duplicate delivery and full rebuild.

## Decision log

- 2026-10-12: The requested configurable negative-stock behavior is a committed
  `BLOCK/WARN/ALLOW` target. Since stock posting is not implemented, the executable
  release remains `BLOCK` and no nonblocking capability is activated. Accounting owns
  the company envelope and valuation/shortage true-up; Catalog's existing values remain
  item definitions, and voucher policy may only narrow them.
