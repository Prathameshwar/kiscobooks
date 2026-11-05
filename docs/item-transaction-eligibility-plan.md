# Goods, services and transaction eligibility

**Date:** 2026-10-12. **Scope:** backend; UI and payroll excluded.
**Progress:** Catalog stock-readiness and signed transaction-policy source plus
Vouchers lifecycle/posting direction guards implemented; dated active-item
changes and stock-owning goods execution remain open under the voucher batches.

## Product concepts and current state

TallyPrime distinguishes stock-item entry from accounting/service-ledger entry in
[purchase vouchers](https://help.tallysolutions.com/purchase-goods-and-services-tally/).
QuickBooks separates inventory, non-inventory and service products and has independent
"I sell" and "I purchase" choices in its
[product/service setup](https://quickbooks.intuit.com/oidam/intuit/sbseg/en_us/quickbooks-online/QBO-Level-1-Manual%20%281%29.pdf).
The platform should use these as transaction semantics, not copy either UI.

Catalog already has family `GOODS|SERVICE`, type `STOCK|NON_STOCK` allowances,
item `sellable`/`purchasable`, and an optional item inventory profile. Catalog
price and tax resolution check the direction flags. Stock profile activation
refuses services. Item warehouse configuration refuses service and types that
cannot stock. The signed `item_transaction_policy` snapshot now reaches Vouchers
and is checked at lifecycle transitions and before posting. Accounting still
has no stock movement runtime, so goods execution stays closed.

| Item | Sale | Purchase | Stock movement |
|---|---|---|---|
| Tracked goods | If sale-enabled | If purchase-enabled | Only for an implemented goods flow |
| Non-stock goods | If sale-enabled | If purchase-enabled | Never |
| Service | If sale-enabled | If purchase-enabled | Never |
| Internal-only goods/service | No sale or purchase unless enabled | No sale or purchase unless enabled | Other authorized operations must be separately defined |

The two direction flags are independent. An item may be sale-only, purchase-only,
both, or neither. Tax category and sale/purchase account defaults follow the
enabled direction and supply kind. A price book is not proof that posting is
allowed. An accounts-only invoice line need not invent an item, but must still
use the proper goods/service tax and ledger evidence.

## Short implementation sequence

1. **Catalog read and authoring:** report non-stock goods as stock
   `NOT_APPLICABLE`; keep stock-required goods `UNAVAILABLE` until Accounting
   executes stock. Validate selected inventory profiles against the actual item
   type. Keep service and non-stock goods out of warehouse allocations.
2. **Active item changes:** define dated, versioned sale/purchase eligibility
   revisions so an active item can be stopped in one direction without changing
   prior voucher facts. Preserve draft flags as initial defaults. Re-enabling
   requires current tax/price readiness in that direction. Source-linked
   returns remain allowed after a direction is stopped, subject to original
   invoice quantity/value/tax caps and their own return permissions.
3. **Voucher and Accounting guard:** replicate effective item kind, stock mode,
   direction permissions, unit and source versions through signed owner snapshots
   and the service outbox. Pin them on voucher lines at preview, recheck at
   submit/post, and reject
   stale or forbidden operations. Orders, quotes, challans, invoices, returns,
   and job-work/material flows each get an explicit operation mapping. Non-stock
   and service lines never create stock effects; stock goods require the stock
   owner and valuation gate. No synchronous Catalog call in a money transaction.
4. **Release:** test all four direction combinations across three item modes,
   effective-date changes, cross-company access, stale replicas, returns,
   fiscal locks and idempotent posting. Update OpenAPI/clients, migration and
   owner reconciliation evidence before enabling item-based goods posting.

## Decision log

2026-10-12: Keep `GOODS|SERVICE`, optional stock profile and independent
sale/purchase eligibility. Fixed the effective Catalog stock-readiness answer
for non-stock goods. The user agreed to the cross-service plan. Added a separate
signed, versioned Catalog transaction-policy source so existing generic item
source versions remain stable. Vouchers now checks direction, kind and physical
stock applicability at lifecycle transition and posting. No stock posting or
active-item eligibility editor is claimed complete by this slice.
2026-10-12: A stopped item may still be returned against a compatible original
invoice; re-enabling must recheck current directional definitions.
