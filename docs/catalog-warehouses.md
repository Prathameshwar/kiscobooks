# Stores, godowns and stock-location configuration

**Ownership amendment, 2026-10-10:** The [Vouchers plan](vouchers-plan.md) replaces future
Billing/Payments services. Retained Billing workflow references mean Vouchers documents;
stock locks, movement/value effects and trusted policy enforcement mean the proposed
Accounting posting extension. Catalog definitions remain implemented; the operational
extension remains unavailable until delivered and acknowledged. No wire identity is renamed.

**Status:** API/DB design, 2026-09-11; Catalog definitions implemented 2026-09-18 through
revision 0143. Operational enforcement — stock, transfers, counts and the stock half of a
deactivation — remains Billing's, so `warehouse_stock_and_location_guards` reads `unavailable`
and a published policy reads `PENDING` until a trusted acknowledgement arrives.
**Execution plan:** [stock-location definitions plan](catalog-warehouse-plan.md).
**Routes:** [stock-location route registry](catalog-warehouse-api.md).
**Read with:** [Product Configuration](catalog-product-configuration.md),
[product/stock rules](catalog-product-design.md) and [schema](catalog-schema.md).

**Scope correction:** Catalog implements location/group/bin definitions and configuration only.
Billing owns physical stock, transfers, damage, counts/adjustments and the product ledger.
Detailed runtime requirements: [inventory integration contract](catalog-inventory-integration.md).
The [final table inventory](catalog-table-inventory.md) lists only Catalog tables.
The [stock reporting contract](voucher-stock-recording-reporting-design.md) defines
Accounting-owned location positions, operation-specific availability and dated warehouse-group
summaries. Store/group definitions never grant stock access or become mutable balance records.

## 1. One location model and an always-present Main

Use the existing Catalog warehouse aggregate for a store/godown/warehouse. STORE/GODOWN are
classification labels on one company-owned stock location, not separate inventories or services.
Bins are optional subdivisions. A department or sales channel remains a separate concept;
neither replaces the physical stock source/destination.

Every company has exactly one system-created MAIN location with a stable ID/code.
Provision it idempotently in Catalog's company bootstrap, including catch-up for companies
created before Catalog is deployed. MAIN is reserved from ordinary create/import APIs.
Main cannot be deleted, deactivated, reassigned to another company or replaced as the system
fallback. A friendly display label may change while the API retains its built-in Main identity.

A company warehouse configuration holds main_warehouse_id and activity defaults.
Provision Main plus that configuration in one Catalog transaction under a company lock.
Readiness stays false until this completes. Main exists as metadata even when inventory
is disabled; it creates no balance, movement or feature-use event by itself.

| Company mode | Behavior |
|---|---|
| inventory off | Main metadata exists; physical stock operations and extra stock-location activation are unavailable |
| inventory on, multi_godown off | Physical transactions resolve explicitly to Main; another location ID is rejected, never silently mapped to Main |
| inventory on, multi_godown on | Additional stores/godowns and explicit multi-location stock operations are available |

Reuse the **existing** multi_godown key, requires inventory and locks_on=godown_movement.
A movement using an additional selectable location, including opening/transfer/return, records
that use. A dispatch to transit for a non-Main source/destination also records use at dispatch;
an ordinary Main-only movement locks inventory but does not lock multi_godown.
Empty master creation alone is not financial use. Before first non-Main use, disabling requires
no additional-location stock/value, holds, pending documents or active defaults, and a reviewed
deactivation/reassignment of extra locations. After use, the existing feature ratchet applies.

### Warehouse groups and bin relocation

Use warehouse_group, warehouse_group_parent and warehouse_group_assignment for non-stockholding
region/zone hierarchies and one dated primary group per warehouse. Groups never accept stock
allocations or confer access to member stores. Reviewed reparent/membership changes preserve
historical rollups, reject cycles and deduplicate authorized member warehouses. Main remains
a physical warehouse regardless of group assignment. warehouse_bin represents physical storage
inside a warehouse; groups are not a substitute for bins.

## 2. Native per-location operational controls

Keep master identity/lifecycle separate from effective operation-policy revisions.
New ordinary locations inherit a reviewed template; do not infer their permissions from their name.

| Flag | Governs |
|---|---|
| allow_sale_issue | May fulfill a sale or sale-linked free gift from this location |
| allow_purchase_receipt | May receive supplier-purchased stock into this location |
| allow_transfer_in | May receive internal transfer stock |
| allow_transfer_out | May dispatch internal transfer stock |
| allow_customer_return_receipt | May receive physical goods returned by a customer |
| allow_supplier_return_issue | May send a return to a supplier |
| allow_opening_stock | May be a destination in controlled opening/cutover documents |
| allow_adjustment | May participate in reasoned inventory adjustments, still requiring its separate permission |

Expose the first two with the labels **Allow sale from this store** and
**Allow purchase into this store**. A receive-only godown and a sale-only store are valid:

| Location example | Sale | Purchase receipt | Transfer in/out |
|---|---|---|---|
| Main | Initially allowed | Initially allowed | Allowed when the operation/capability is available |
| Retail Store | Allowed | Disabled if replenished only by transfer | Explicitly configured |
| Purchase Godown | Disabled | Allowed | Explicitly configured |
| Returns Area | Disabled | Disabled | Explicitly configured; customer returns enabled |

All operations still require feature availability, item/stock validity, actor/location scope
and the relevant action permission. These flags grant no permission by themselves.
Purchase disabled does not mean transfer-in or customer-return disabled; sale disabled does
not automatically prevent supplier returns or transfers. Zero-price gifts still require sale issue.
A company may explicitly block an activity even at Main; the resolver then reports no eligible
location rather than silently re-enabling its flag or choosing an unrelated warehouse.

The native domain handler determines operation kind and checks the matching flag.
A client cannot relabel a sale issue as an adjustment or a purchase as an opening to bypass
the rule. Generic movement endpoints enforce their own document/reason/permission contracts;
an unpaired transfer-out cannot masquerade as a sale.

## 3. Defaults, product/location restrictions and allocation

Company configuration includes separate default_sale_warehouse_id,
default_purchase_warehouse_id, default_customer_return_warehouse_id and
default_opening_warehouse_id. Initially all point to Main. Optional SKU/location policies
can restrict allowed locations/operations and suggest role-specific defaults.

Resolve an omitted location using: authorized explicit allocation > SKU activity default >
company activity default > built-in Main when no activity default is configured.
This is default selection, not an authorization override. A configured but inactive,
denied, stale or operation-disabled default is an error, not permission to continue down the
fallback chain. Every selected location is scoped, valid and persisted explicitly.

With multi_godown off, all activity defaults must be Main; a conflicting product/default
configuration must be corrected before feature disablement completes.
For stock-affecting APIs there is no nullable or virtual warehouse meaning "all stores."
Services/nonstock goods do not acquire inventory allocations merely because Main exists.
For a mixed stock/non-stock product type, an activated SKU may hold location or
replenishment policy only when activation created its inventory profile. Draft SKU
location settings are provisional: activation rejects effective restrictions, defaults or
replenishment bands if the selected configuration has no inventory profile. Cleared
historical settings do not block activation.

An optional item_warehouse_policy permits ALLOW_ALL_ACTIVE or ALLOW_LIST with explicit
membership and operation restrictions. Product restrictions can narrow location capabilities,
never widen them. A missing row means the documented company/product baseline, not a guessed
deny or a customer-supplied authorization claim. Per-location minimum/reorder/target/MOQ policies
remain native and have compatible unit rules.

A line may have explicit allocations across multiple allowed locations only if the document
and tax adapter support that shape; each allocation carries its actual warehouse/bin/lot/unit.
Default behavior is one selected source per line. Insufficient stock must not silently pull
from another location. A future automatic allocator requires an explicit supported policy.
Stock-affecting quantity, serial and scope checks run on every allocation, including gifts.

Physical source and selling/counter/channel context remain separate. Warehouse country/state/
address and any required company tax-registration reference must be available to the transaction
adapter. Different ship-from tax contexts may require separate lines/documents; do not flatten
them into one assumed tax outcome. This does not introduce a warehouse-specific tax engine.

## 4. Stock quantities and transfer behavior

Billing owns stock by company + item + warehouse/bin + lot + disposition + ownership,
with physical-unit claims where needed. Quantities, cost and reservations never move because
a default or a warehouse name changes.

Expose per-location on_hand, reserved, available_for_sale and transfer/receipt information with
as_of/source readiness and reasons for exclusion. Purchase/sale-disabled, held, expired or
otherwise restricted stock may remain on hand but is not automatically available for sale.
Subtract live reservations once. Company totals deduplicate dimensions and honor authorized
scope; a store-only user cannot infer hidden warehouse balances from a company total.

Example: Main has 10 and Store A has 5. Selling 3 from Store A leaves Main=10 and Store A=2.
A transfer of 4 from Main to Store A leaves Main=6 and Store A=6. Company quantity remains 12.
A sale from a different store cannot pass merely because the company total is positive.

Same-company transfers require source allow_transfer_out and destination allow_transfer_in,
valid source/destination and exact compatible quantities. Creation/approval requires both-end
scope; dispatch and receiving actors may hold only their respective operation/location scope
plus access to the specific transfer. Counterpart stock/cost remains protected. Distinct-bin
relocation within one warehouse is valid when bins are enabled; it does not require multi_godown.
Reserve/dispatch/receive uses the same canonical bucket/cost/unit locks as ordinary stock.
Cost/lot/serial identity carries through; internal transfer creates no sale, purchase or profit.
Reject transfers of stock already reserved for another demand unless explicitly released/reassigned.

Billing's separate implementation must support two explicit transfer modes:
- **Immediate:** matched source/destination legs and cost/ledger effects commit atomically.
- **Dispatch/receive:** dispatch moves stock to a non-saleable internal transit holding scope;
  receipt moves it from transit to the destination. Partial receipts retain the exact remainder,
  original cost and physical identities; losses/damage use authorized linked adjustments.

Represent transit with a reserved internal warehouse kind in the existing location model,
provisioned by Catalog when needed. It is not an ordinary selectable/default store and cannot
be targeted by public sale/purchase/opening APIs. Only typed transfer handlers use it.
Transit counts once in company-owned quantity/value but not in any store's sale availability.
Transfers between warehouses require multi_godown; the participating operation permissions and
both endpoint policies are rechecked at dispatch/receipt. Same-warehouse bin relocation does not. If receipt becomes blocked, goods stay in transit until an
authorized receive/reroute/return action, never disappear or silently return to available stock.

Dispatch/receive retries use both idempotency and unique transfer/leg/source identities.
Per dispatch allocation, received + returned + approved loss + remaining transit equals dispatched.
Damaged receipts count once in received stock with their real disposition; a damage report is
not also a loss. Over-receipt and wrong identities require explicit discrepancy resolution. Reversal follows physical position and fiscal constraints;
it is not an arbitrary counter edit. Intercompany transfers remain separate sale/purchase
workflows and are not accepted by this internal-transfer API.

## 5. Policy changes, holds and deactivation

Operation flags are live controls: resolve them at trusted operation/acceptance time, not a
caller-backdated posting date. Preserve their revision on postings; historical balances/reprints
do not reinterpret today's permission flags. Price/tax/fiscal dates keep their existing meaning.

Catalog publishes a versioned warehouse policy/default change. Billing prepares/activates it
under stable location guard locks and emits acknowledgement; API delivery state is
PENDING/APPLIED/REJECTED until the enforced revision is known. Definitions alone cannot claim
an immediate stop in another database. Active operations take shared guards; disabling or
deactivation takes an exclusive guard under the same overall document/quota/stock lock order.

Existing sale reservations are not grandfathered past a sale-disable control. New reservations
fail; existing holds cannot post and must expire/release or be explicitly reallocated with a
new accepted quote. A coupon hold retains its own capacity rules; changing warehouse may alter
tax/eligibility and invalidates the old quote as required. No automatic stock transfer is implied.

Non-Main deactivation requires zero quantity AND value across every disposition/lot/unit,
no active reservations, no pending incoming/outgoing transfer or stock document, and no default/
product/bin assignment requiring it. Check in Billing under the location guards and reject a
race with a new allocation; Catalog acknowledges deactivation only after the coordinated fence.
Do not infer safety from a displayed zero available quantity.

Prefer disabling selected new operations while clearing existing obligations, then deactivate.
Historical stock movements remain readable. Customer credit is distinct from stock receipt:
a return can use an explicitly permitted returns location without re-enabling sales or purchases
at the original location. A financially valid correction cannot erase physical location evidence.

## 6. Catalog schema and external runtime references

| Owner / structure | Essential contract |
|---|---|
| Catalog warehouse | Existing company/code/name, kind STORE/GODOWN/INTERNAL_TRANSIT, optional department, timezone and native address/tax-location facts; Main has reserved immutable identity |
| Catalog warehouse_group / warehouse_group_parent / warehouse_group_assignment | Non-stockholding dated hierarchy; same-company/cycle/cardinality constraints, scoped deduplicated rollups and no effect on stock balances |
| Catalog catalog_policy_release / catalog_policy_consumer_ack | Validated complete release manifest, then trusted consumer activation evidence; idempotent source-only events and no current-state regression |
| Catalog company_warehouse_configuration | Company PK, immutable main_warehouse_id, current activity-default pointers with audited change history, and source version; unique Main and atomic bootstrap |
| Catalog warehouse_operation_policy_revision | warehouse_id, revision, UTC validity window, typed operation booleans; stable policy scope/version; no arbitrary JSON operation keys |
| Catalog item_warehouse_policy / item_warehouse_permission | SKU allocation mode, activity defaults and explicit warehouse/operation restrictions; local same-company FKs; restrictive composition |
| Existing warehouse_bin | Parent-scoped identity; subordinate to warehouse permissions and stock/deactivation checks |
| External Billing warehouse projection / warehouse_operation_guard | Complete location/policy/default versions, pending transitions and acknowledgement; serializes use/disable/deactivate |
| Existing stock bucket/balance/reservation/movement | Explicit location dimensions and pinned policy evidence; no competing Catalog quantity |
| External Billing inventory_transfer / transfer_line / transfer_leg | Source/destination/mode, source identity, typed lifecycle, dispatch/receipt quantities and allocation/cost references; unique per-leg effects |
| Internal transit location/buckets | Non-selectable custody scope; only typed transfer handlers may access stock; no sale/default fallback |

| API family | Contract |
|---|---|
| Catalog GET /warehouse-configuration; preview/publish defaults | Main plus role defaults, multi_godown state and readiness; capability changes still use Identity |
| Catalog warehouse CRUD/usage; operation-policy history/preview/publish | Typed flags, native location facts, scoped default/dependency checks and coordinated deactivation |
| Catalog GET/PUT /items/{id}/warehouse-policy | Explicit allowed locations/defaults/restrictions; no permission expansion |
| Billing stock availability/balances | Warehouse-specific and authorized aggregate views, with eligible sale availability |
| Billing /inventory-transfers with validate/reserve/post or dispatch/receive/reverse actions | Whole-transaction immediate mode or explicitly tracked transit mode; no generic unpaired movement |
| Existing opening/purchase-receipt/sale/return/adjustment/quote/import APIs | Resolve and persist location, operation policy/version and actual allocation |

All Billing source/stock routes and tables above are external contract references, not Catalog
deliverables. Its supplier-origin receipt kernel must enforce the purchase flag; full procurement
and supplier-invoice automation remain in that API's own plan. Catalog cannot report a live
policy as applied until a trusted acknowledgement is received.
All new actions have fixed permissions, field policies, idempotency and atomic audit/outbox.
Bulk uploads use exact scoped warehouse codes/IDs; omitted locations use the same resolver.

## 7. Phase integration and acceptance

C0 fixes ownership/Main/default/operation contracts; C5 implements Catalog release/acknowledgement
and producer readiness; C7 implements actual location/group/bin masters and product policies;
C10 imports only those definitions. C15 verifies Catalog behavior and missing-consumer states.
The agreed phase breakdown, revision numbers and per-phase exit tests are in the
[stock-location definitions plan](catalog-warehouse-plan.md); the Catalog halves of C0, C5, C7 and
C10 landed in revisions 0132–0143 and every delivered route is listed in the
[route registry](catalog-warehouse-api.md).
Legacy C11-C14 stock phases and P2-P4 runtime phases are external owner work, not this checklist.
Billing implementation must pass the stock-operation scenarios below when it is delivered.

Mandatory tests: concurrent bootstrap creates one Main; inventory-off Main has no stock;
multi_godown-off rejects another source; sale-only/purchase-only flags are independent;
Main and role defaults cannot bypass scope or item allowlists; company totals never satisfy a
store-specific shortage; opening and gifts obey their own flags; partial transit receipt counts
once; duplicate dispatch/receipt cannot move twice; serial identity/cost survives transfer;
sale disable racing with reservation/post is serialized; deactivation rejects stock/value/
holds/pending transfers; default changes never move stock; restricted users cannot see other stores.

## Optional manufacturing location policies

[BOM M0-M4](catalog-manufacturing-design.md#5-operations-quality-tracking-and-stores) extends
the existing typed warehouse operation policy with independent allow_production_issue and
allow_production_receipt. Neither sale/purchase flags nor BOM publication authorizes production.
Defaults remain operationally unavailable until Billing supports and acknowledges these actions.

bom_location_default supplies scoped issue/output/WIP/recoverable-scrap hints. Main is the initial
compatible issue/output fallback; WIP/quarantine/scrap routing requires explicit suitable roles.
Apply the same actor, SKU, bin, multi_godown, restrictiveness and policy-version checks. A route
step or workstation is not a warehouse. Actual material custody, WIP movements and output stock
remain Billing records under its future production contract; no new Catalog balance table.

## Decision log

- 2026-10-28: The native Accounting stock adapter keeps the existing `billing`
  consumer identity. Retirement always requires a fresh, scoped Accounting
  NoStock check plus a bounded Vouchers NoPendingDocument write lease while
  Catalog holds its company policy lock and no live stock-definition lease exists.
  Cached acknowledgements alone cannot authorise retirement. Both scopes, command
  hash, row versions and expiry are checked before flush and final commit.
  A fresh native NoStock clearance may replace a previous volatile retirement
  refusal at the same operation revision; ordinary broker acknowledgements retain
  their monotonic policy rules. Savepoints cannot discard the final expiry check.
  Empty bins share their warehouse cost pool and do not acquire an independent
  asset balance from a sum of historical movements. Physical posting activation
  remains separately gated by the stock delivery checklist.

- 2026-10-10: Linked required location/group stock and availability reporting to the shared
  stock design. Canonical positions stay in Accounting; dated hierarchy and scoped access
  govern summaries, with no mutable warehouse/group balance in Catalog.

- 2026-10-10: Vouchers supplies future warehouse transaction workflows; the proposed
  Accounting stock extension supplies enforcement and acknowledgements. Updated the owner
  mapping without claiming operational availability or renaming deployed consumer identities.

- 2026-09-18: A reviewed file may create locations, groups, bins and their dated links and may
  publish an operation or product policy, all through the same commands the routes call. It may not
  name a stock balance, a transfer, a count or a trading party — those resources do not exist in
  the bulk registry, so a file claiming one is refused when it is staged rather than partly applied
  — and it may not deactivate a location or write the provisioning singleton, because each is one
  reviewed coordinated action and a file of them is what the fence exists to prevent.
  `stock_location_definitions` reads implemented while `warehouse_stock_and_location_guards` reads
  unavailable: the two answer different questions, and collapsing them would have made the
  definitions unreportable until another service shipped.

- 2026-09-17: Company activity defaults are current-state pointers with audited change history,
  not dated revision rows: a default is resolution convenience evaluated at operation time, not a
  term that prices or posts, and dating it would change resolution silently on a boundary crossing.
  Release and acknowledgement tables ship with the location masters so publication can report an
  enforced version and deactivation has a real fence. `item_supplier_term` stays unimplemented
  while Billing has no authoritative party projection.

- 2026-09-11: Added optional independent manufacturing issue/receipt policy definitions and
  BOM location hints; preserved acknowledged runtime enforcement and sole Billing stock custody.

- 2026-09-11: Restricted delivery to Catalog masters/configuration and added warehouse groups,
  consumer acknowledgement and the detailed transfer/damage/count/ledger integration contract.
  Operational Billing candidates and acceptance scenarios are external dependencies only.

- 2026-09-11: Recorded the user's always-present Main, multiple stores/godowns, stock per
  location and sale/purchase enablement requirements. Reused warehouse and multi_godown.
- 2026-09-11: Made activity defaults, restrictive product/location controls, transfer/transit
  accounting and acknowledged runtime policy changes explicit within existing API/DB phases.
