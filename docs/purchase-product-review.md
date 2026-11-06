# Purchase with Product: review 2026-11-02

The first sections record the 2026-11-02 findings. Later delivery and final-review sections below supersede their
then-current status statements.

Reviewed at the user's request: the Purchase bill for products (types `PUR_PRD` "Purchase - Product Bill" and
`PUR_MIX` "Purchase - Mixed Bill") end to end, Console, Vouchers and Accounting, including how purchased goods reach
stock. Scope agreed with the user: **review and fix within today's limits**; posting a bill that also brings goods
into stock (tracker batch B24, decision D02) is not built here, and its design is set out below for a separate
decision.

Method: three independent read-only reviews (Console, Vouchers, Accounting stock posting); each finding confirmed in
the code; each fix starts with a test that failed first.

## Where a product purchase stands today

| Step | State |
|---|---|
| Choose a Product or Mixed Purchase type on `/vouchers/new/purchase` | Offered; now says plainly it is not available yet (fix 1) |
| Enter products, units, quantities on that screen | **Not built.** The live screen records account and service bills only; the goods grid exists only in the synthetic `/vouchers/new/purchase-preview` |
| Save a product draft | API only (and not through import, fix 4) |
| Calculate, accept, submit, approve, issue, post a product bill | Refused with one message, at every step, with or without an invoice section (fix 2) |
| Print a product bill | Refused (fix 3): the layout has no quantity, unit or rate |
| Open a saved product draft | Purchase screen refuses to edit it and now links to voucher review (fix 5), which shows its item lines with received and billed quantities |
| Bring purchased goods into stock | **Receipt Note** (stock action RECEIPT): Dr Inventory / Cr the receipt clearing account (goods received, not invoiced, "GRNI"), valued at the entered receipt value |
| Return goods to the supplier | Rejections Out against the receipt: Dr GRNI / Cr Inventory / ± variance |
| Record the supplier's bill for received goods | No native path: a goods bill cannot post, and an account bill cannot debit GRNI (a liability). Today only a manual journal can clear GRNI |

## Fixed

1. **A product or mixed type was offered, then reported as misconfigured, with advice that would damage it.** The
   setup said "Purchase needs configuration: Accounts mode is disabled… Item lines are required…" and linked to
   *Edit Purchase entry rules*; following it turns the provisioned product type into an account type (a new immutable
   revision). Such a type now shows "Product bills are not available yet" with what to do instead (Receipt Note for
   stock, an Account Bill type for the bill), and no rules link. A genuinely misconfigured account type still gets
   the configuration notice and the link. (`purchase-entry.ts` `purchaseGoodsType`, `PurchaseEntryConnected.tsx`.)
2. **A goods Purchase without an invoice section could be submitted, approved and issued a number.** The goods
   refusal ran only when the bill had an invoice section, so a type configured without one let an itemised Purchase
   reach APPROVED/ISSUED, a bill that can never post and that skipped the duplicate-bill check. The refusal now runs
   first, whatever the sections (`domain/invoice.py`).
3. **A product bill printed without its goods.** The standard Purchase layout prints description and amounts only.
   Printing a product or mixed bill is refused, before any owner call, until product-bill posting brings a layout
   with quantity, unit and rate (`tasks/purchase_print.py`).
4. **Import into a product or mixed type made drafts that could never be submitted.** Imported Purchase lines are
   account/service supplies; a type whose default mode is not Accounts, that disallows Accounts, or that requires item
   lines is now refused for import with a plain reason (`tasks/imports.py` `import_type`).
5. **A saved product draft opened on the Purchase screen was a dead end.** It was correctly not edited ("requires a
   broader Purchase profile") but nothing led to where it can be seen. The notice now links to voucher review, and
   voucher review shows each item line's billed quantity next to the received one, with the company's quantity
   precision (`VoucherSummary.tsx`).

## Reported, not changed

These touch accounting choices that are open (D02) or belong to product-bill posting (B24):

- **FIFO supplier return takes the oldest layer's cost, not the returned receipt's** (`stock_claims.py` →
  `stock_ledger.cost_out`). Example: receipts of 3 @ 10 then 3 @ 20; returning one unit against the second books
  Dr GRNI 20 / Cr Inventory 10 / Cr variance 10 and leaves the dearer layer in stock. The design asks for "original
  quantity/cost lineage", but whether a FIFO return uses the specific receipt's layer is part of open decision D02.
- **The GRNI account is not guarded against manual journals** (only the inventory account is). Guarding it now would
  remove the only way, today, to recognise the supplier's payable for received goods; it belongs with B24.
- **A supplier return always debits GRNI**, which becomes wrong once a bill has cleared the receipt (B24).
- **A receipt's stock date and posting date may differ** with no recognition rule (the year-end design asks for an
  approved recognition profile).
- **Receipt cost is final, with no supplier on the GRNI line**, so GRNI cannot be aged or matched by supplier.
- **Purchase item lines do not store** the unit revision and base quantity used at entry, measured (variable)
  units have no base quantity, a paid goods line may carry zero quantity, item eligibility is checked only at submit,
  item lines have no warehouse, and a bill's links to Receipt Notes are untyped. None of this can post today; each is
  a B24 contract item below.
- **The Console has no product entry**: item search, units, warehouse, receipt matching, goods GST (HSN) and an
  item-aware wire/reload are all missing on the live screen (the preview's model would lose facts if reused).

## Product-bill posting (B24): what it takes

**Recommended first profile — bill against Receipt Notes, clearing GRNI.** The goods arrive on a Receipt Note
(already posting Dr Inventory / Cr GRNI). The supplier's bill lists the receipts it covers; Accounting claims each
receipt (the claim counters and the INVOICE claim type already exist), and posts Dr GRNI (claimed receipt value)
/ Dr recoverable input GST / Cr Supplier, with a party bill for payment. No stock moves, so the inventory guard is
untouched. Size: medium (about one to two weeks): one or two migrations, invoice execution and calculation,
Vouchers receipt references, schemas, client and the test matrix.

**Second profile — the bill is the receipt** (Dr Inventory / Dr input GST / Cr Supplier in one posting, stock
received per line). Reuses the stock execution, but calculation must allocate value to item lines, charges and free
goods hit stock value directly. Size: large (two to four weeks).

Decisions needed from the owner before either starts:

1. Recognition: bill against receipts, bill as receipt, or both by voucher type.
2. Price difference between bill and receipt value: block, variance account, or capitalise to stock still held.
3. FIFO return cost: the returned receipt's own layer, or oldest layer plus variance.
4. Freight and other charges on goods: capitalised into the receipts or expensed at first.
5. Whether ineligible GST is capitalised into stock.
6. Whether a receipt's stock date must equal its posting date.
7. Whether a receipt carries its supplier (GRNI ageing), and whether a receipt's value is provisional.
8. Returning goods already billed: a debit-note clearing account or the supplier's payable.

## Owner decisions, 2026-11-03

The owner chose to build product-bill posting after meeting the refusal on a new company's Mixed bill:

1. **Recognition: the bill adds stock** (the second profile above, like Tally's item-invoice purchase): one posting
   Dr Inventory at landed cost + Dr recoverable input GST / Cr Supplier. Receipt Notes stay optional; a bill line that
   references an earlier Receipt Note clears its GRNI instead of adding the goods again.
2. **Landed cost:** freight, packing and other charges on a goods bill, and GST that is not claimable, are capitalised
   into stock cost, apportioned over the goods lines by value.
3. **Returns:** goods returned to the supplier take back the exact cost of the purchase they came from; a difference
   to the debit note goes to a price-variance account.

Taken as best fit with them, and open to revision: a bill that adds stock has its stock date equal to its posting date;
a price difference between a bill and a referenced receipt goes to the price-variance account; a mixed bill posts goods
lines to stock and account/service lines to their accounts in the same journal. Decisions 6-8 above follow from these.

## Verification

- Live, as `tenant1` after restarting the Vouchers and Accounting APIs (`.tools/purchase-product-live-review.cjs`):
  the chooser offers Account, Product and Mixed bills; Product and Mixed show "Product bills are not available yet"
  with no configuration error and no rules link; the Account Bill opens its workspace; through the Console proxy, an
  import template for the Product Bill type answers 409 with its reason. Nothing was saved or posted.
- Tests only: the refusal at submit/approve/issue/post without an invoice section, the print refusal, and the voucher
  review quantities (Vouchers `test_purchase_review_2026_11_02.py`; Console `purchase-connected`, `voucher-summary`).
  Each new test failed before its fix.
- Vouchers full suite: 769 passed, 10 failed, all failing before this work (real-browser print tests that cannot
  start Chromium here, and `test_stock_opening_files.py`). Ruff and strict mypy clean in both services; Console
  `tsc` clean.

## Delivery: phase 1, 2026-11-03 (capture and calculation)

A Product or Mixed Purchase bill can be saved with its stock lines (stock action `PURCHASE_INVOICE`), calculated by
Accounting from each item's published facts, and its calculation accepted. Submitting and posting it is refused with
"A product bill can be saved and calculated; submitting and posting it is not released yet" until phase 2.

| Owner | What changed |
|---|---|
| Contract `voucher-execution-client` 0.4.0 | `PURCHASE_INVOICE` stock action mapped to `PURCHASE/STANDARD`, never carrying a received value or (until linking is built) a Receipt Note reference; `INDIA_DOMESTIC_GOODS` tax profile; `InvoiceSupply.input_credit`/`input_credit_reason` (goods only, reason iff not claimable); `SupplyCalculation.stock_cost`; `StockItemFact.purchase_tax` and `StockFenceRequest.include_purchase_tax`; the preview command carries a goods bill's stock lines. New fields are omitted from the wire when unset, so existing hashes are unchanged. Deploy Catalog and Accounting before Vouchers. |
| Catalog | On request, the stock facts carry each item's complete purchase GST bundle (classification, HSN code, rule, treatment) resolved through the same dated ancestry as activation, under the user's own field access; an incomplete bundle is absent, never guessed. |
| Accounting | Goods tax from the item's bundle checked against Accounting's own replicas, tax point the supplier invoice date (CGST s.12(2)(a)), CGST+SGST/UTGST or IGST by place of supply; a company without GST registration bills goods untaxed at their price. Goods must post to the stock policy's inventory account, bill exactly the received base quantity, and belong to an active purchasable product allowed in the warehouse. Charges on goods carry no separate account and are spread over goods lines by value. `stock_cost` = commercial value + GST that cannot be claimed (`domain/invoice_landed_cost.py`). |
| Vouchers | Content allows `stock` + `invoice` together only for `PURCHASE_INVOICE`, billing what it receives on its posting date; the type must allow goods supplies; a mixed bill's account/service lines carry no stock. Migrations 0112-0115 (one DDL each). |
| Console | The new stock action is labelled in voucher review. |

Tests: contract `test_purchase_goods.py`; Catalog `test_stock_purchase_tax_facts.py`; Accounting
`test_goods_invoice_calculation.py` (the worked example: 10 x 100 + 5 x 100 with 150 freight, 18% intra-state, the
second line not claimable gives stock costs 1,100 and 649 and a payable of 1,947), `test_invoice_landed_cost.py`;
Vouchers `test_purchase_goods_capture.py`.

## Delivery: phase 2, 2026-11-03 (posting)

A goods Purchase bill posts its stock and its invoice in one Accounting execution. Stock comes in at each line's
`stock_cost` from the accepted calculation (commercial value + capitalised charges + GST that cannot be claimed); the
journal debits the inventory account by the same amounts and recoverable input GST, and credits the supplier, whose
bill opens as an open item. The stock channel carries the bill (`include_purchase_tax` on the fence for a POST), the
release must also have invoice execution on, and a changed or unaccepted calculation never posts. Accounting migration
0231 admits `PURCHASE_INVOICE` in the stock posting action check (one DDL).

Tests: Accounting `test_goods_bill_posting.py` (the worked example posts 1,100 + 649 into stock, 198 input GST and a
1,947 supplier bill, once on replay; refused while the release is off; refused when the hash or a price changed).

## Delivery: phase 3, 2026-11-03 (Purchase screen)

The Purchase screen takes product lines on a type that allows goods supplies. It opens in the type's default mode and
offers Items, Accounts / services and Mixed as the type allows. An item line searches the company's active purchasable
products; a choice is verified with Catalog (active, purchasable, this company, its base unit) before the line takes
it. Typing one quantity fills the other while they agree, since the bill receives what it bills. On save the screen
reads the inventory account in force on the posting date and the purchase warehouse (default purchase, else main),
and sends common item lines, goods supplies (inventory account, base-unit ACTUAL and BILLED quantities, unit price,
amount = quantity x rate rounded once in the company's rounding) and the `PURCHASE_INVOICE` stock section. A taxed
goods bill carries the goods GST profile in its header and the service context on any service line; reverse charge on
goods is refused. A saved goods bill reopens exactly and keeps its warehouse; this phase sent bins, lots, a second
warehouse, a shortfall, and captured values to voucher review. A Product type whose rules
do not allow goods supplies says so instead of opening.

Tests: Console `purchase-goods.test.ts`, `purchase-goods-connected.test.tsx`; updated `purchase-api`,
`purchase-connected` for the new behaviour.

## Direct bill tracking extension, 2026-11-05

The direct Product and Mixed Purchase draft now captures one stock destination per item row. A row can name a
warehouse, optional bin, a prepared batch when its current profile requires one, and prepared serial identities.
Repeated product rows are used to divide a purchase across warehouses or batches. The compact line editor and
desktop line-details drawer use searchable master references and show only the controls required by the product's
tracking profile. Save reloads each distinct product's tracking profile and the dated stock-account context; the
native posting path remains authoritative for held/expired tracking, warehouse policy, changed profiles and
concurrent claims. Reopening retains each row's IDs, including different warehouses.

This extension does **not** add a Receipt Note matching path. The native `PURCHASE_INVOICE` contract still rejects
`source_movement_id`, so a bill against previously received goods cannot yet clear GRNI without adding stock again.
That requires a separate contract, Accounting claim and valuation rules, Vouchers linkage, client generation, and
an end-to-end posting test before the UI can offer it. The direct bill's posting controls remain under the existing
stock and invoice execution gates.

Verification for this extension: the contract's purchase goods tests pass (8 tests), including two warehouses,
bin/batch/serial capture and duplicate serial refusal. Console tests were updated for tracked round trips and
multiple warehouses but could not run locally because the frontend dependency installation is absent. Release
activation and a live tracked posting are not evidenced by this entry.

### Final entry and configuration review, 2026-11-05

The provisioned types remain `PUR_ACC` (Accounts, Account/Service supplies), `PUR_PRD` (Items, Goods/Service
supplies), and `PUR_MIX` (Mixed, Account/Goods/Service supplies). The Purchase type editor now offers a Goods
supply switch beside Account and Service, and enabling a missing invoice policy starts with supply kinds that fit
the type's allowed entry modes. It warns when Items or Mixed is enabled but Goods is off. The live entry follows
the effective type's allowed modes and supply kinds, keeps Mixed mode on a goods-only Mixed bill, and checks the
required stock header and line field access before offering goods entry. Optional bin/batch/serial controls respect
their separate field access. Warehouse defaults still come from Catalog; product tracking requirements and stock
eligibility still come from Accounting, rather than a new voucher-type switch.

Two review findings were fixed: the saved draft had inferred `ITEMS` for a goods-only `MIXED` bill even when its
type allowed only Mixed, and the type editor had no way to restore Goods after disabling it. The review also found
missing stock-line access checks and a connected test that did not mock the newly required tracking profile read;
both are fixed. The native stock contract tests pass (20 targeted tests). Console typecheck and UI tests remain
unverified here because `mfes/node_modules` is absent and TypeScript is not available in the offline npm cache.
Receipt Note matching and GRNI clearing remain a separate unfinished phase, as described above.

## Company setup defaults, 2026-11-03

Requested by the owner: a company created with inventory on can bill goods without first mapping stock accounts.

- The books step (`financial-setup/initialize`) creates five standard stock accounts under fixed system keys and maps
  them in a stock account policy from the books begin date: Stock-in-hand (Stock-in-hand group), Goods Received, Not
  Billed (Current Liabilities), Goods Dispatched, Not Billed (Current Assets), Opening Stock Offset (Capital Account)
  and Stock Variance (Direct Expenses). A company that already has a stock account policy is never changed; one
  whose books were set up before inventory was on catches up when the books step runs again. A template code already
  owned by another master leaves the books set up without them, for an administrator to map, instead of failing the
  company's setup. Accounts are created, never adopted by name.
- Chart initialization (`accounting-setup/initialize`) makes sure every company has a cash account: a chart with no
  cash account at all gets Cash in Cash-in-hand (and Current Assets) from the template; a chart with its own cash
  account, or whose template codes are taken, is left as it is. Fresh companies already get Cash from the business
  chart.

Tests: Accounting `test_standard_stock_accounts.py`, `test_chart_cash.py`.
