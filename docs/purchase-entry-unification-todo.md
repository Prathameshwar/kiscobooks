# Purchase entry: one screen, styled, aligned — live todo

Reported 2026-11-01 against `/vouchers/entry?kind=PURCHASE&type_id=…` (reached from Operate → Expense →
Purchase → Purchase - Account Bill) while `/vouchers/new/purchase` looked right.

## Findings and what was done

1. **No styling on `/vouchers/entry`.** Both routes rendered the same `PurchaseEntryConnected`, but the dense
   entry stylesheet (`entry.css`) is loaded only by the `/vouchers/new` layout; the entry route had none, so
   the right markup rendered with none of its CSS (and nested a second `janso-page` inside the shell's page).
   *Fixed at the root, see 2: that route no longer renders the workspace at all.* A test
   (`voucher-entry-stylesheet.test.ts`) fails if any route that renders a Sales/Purchase entry workspace is not
   under a layout that imports `entry.css`.
2. **Two routes for one screen.** `/vouchers/new/<kind>` (top-bar New, drafts, resume links) and
   `/vouchers/entry?kind=…&type_id=…` (Operate) both opened the Sales/Purchase workspace. Now there is one:
   `/vouchers/new/sales` and `/vouchers/new/purchase`, which accept `type_id` (a company voucher type) and
   `returnTo` (a known Operate list, for Back and for the rail highlight). `/vouchers/entry` serves only the
   kinds that use the generic entry and *redirects* Sales and Purchase to the canonical address, so old links
   and bookmarks still land on the right screen. Operate's "New voucher" now links to the canonical address
   directly (`newVoucherHref`).
3. **Two Purchase types doing the same job.** `PUR "Purchase voucher"` (a catch-all with all three modes,
   default Accounts) sat beside `PUR_ACC "Purchase - Account Bill"` in this company. It is **not** provisioned:
   company creation (`company-voucher-defaults-v2`) creates only `PUR_ACC`, `PUR_PRD`, `PUR_MIX`, and
   `test_bootstrap_provisions_account_product_and_mixed_purchase` pins exactly that set (replay creates no
   duplicates). `PUR` was created by hand on 2026-10-31 13:49, earlier than the 16:00 provisioning run, and has
   no vouchers. Operate already hid it by name; the New → Purchase chooser listed it. One shared rule
   (`GENERIC_PURCHASE_TYPE` / `offeredPurchaseTypes`) now drives both: the catch-all is not offered beside
   specific types, and is still offered when it is the company's only Purchase type. A lone remaining type is
   opened without a chooser step. *No provisioning change was needed.* The leftover type itself can be
   retired in Masters → Voucher types (it is data, not code; retiring it is the user's call).
4. **Amount header right-aligned, entered value left of it.** The numeric cell wrapper is a fixed-width block
   inside a wider cell; `text-align: end` moves text, not a block, so the field sat at the start of the cell
   (measured on the live page: field 1121–1233px under a heading ending at 1302px). The wrapper is now pushed
   to the end of an end-aligned cell (field 1190–1302px), for every numeric column of the grid (amount, rate,
   quantity, discount). Guarded by `entry-grid-alignment.test.ts`.

## Todo

- [x] Stylesheet guard for every route that renders an entry workspace
- [x] One canonical route per native kind; `/vouchers/entry` redirects Sales/Purchase; Operate links canonical
- [x] One rule for the offered Purchase types, shared by Operate and the chooser; lone type opens directly
- [x] Amount column alignment + regression test; measured before/after on the live page
- [x] Provisioning checked: new companies get exactly the specific types (existing test), no change needed
- [x] Tests (see below), typecheck, live check as tenant1

## Verification

Live, signed in as the QA owner (`tenant1`): `/vouchers/entry?kind=PURCHASE&type_id=…&returnTo=…` redirects to
`/vouchers/new/purchase?type_id=…&returnTo=…`, renders fully styled with the Account Bill type opened, a Back
button to the list and the Expense rail entry highlighted; the old Sales link redirects the same way; the New →
Purchase chooser lists Account, Product and Mixed bills only; a typed amount ends under its heading's right edge.
