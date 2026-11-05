# Purchase page redesign (`/vouchers/new/purchase`)

**Update 2026-11-02:** the page can now record India GST on service lines, and the wording below that says tax
"cannot be recorded" is superseded: see [purchase-tax-entry-plan](purchase-tax-entry-plan.md). The "no tax" box,
the layout and the lifecycle described here are otherwise as they were.

Date: 2026-10-31. Scope: layout, style and wording of the live, connected Purchase page. The
service contract, request mapping, recovery rules and state machine in
[purchase-api-plan.md](purchase-api-plan.md) are unchanged. The earlier
[Purchase UI blueprint](purchase-ui-blueprint.md) still governs the shared grid, detail panels and
the synthetic `/vouchers/new/purchase-preview` route.

## 1. What a voucher, a voucher type and a Purchase are

- A **voucher** is one business document recorded in the books: Sales, Purchase, Receipt, Payment,
  Contra, Journal, credit and debit notes, orders and so on
  ([vouchers-plan](vouchers-plan.md)). It has a header, dated revisions and lines
  ([voucher-data-model](voucher-data-model.md)).
- A **voucher type** is the company's configured variant of a kind: which entry modes
  (Accounts, Items, Mixed), sections, party roles, invoice rules and fields it allows, with its own
  revisions ([voucher-configuration-design](voucher-configuration-design.md)). One company can have
  several Purchase types, for example "Account purchases".
- A **Purchase** is a supplier's bill. Recording it creates what the company owes that supplier (the
  supplier payable) against what was bought (expense accounts, or later stock). This screen supports
  one profile: an **untaxed account bill**, meaning an expense or service bill with no GST or other
  tax. Goods, receipts, stock and tax-bearing bills need other workflows that are not connected here.
- A saved purchase moves **Draft → (Accounting calculation accepted) → Submitted → Approved →
  Posted**. Saving a draft never posts anything. Accounting, not this page, calculates the bill's
  total and tax; the page only shows that result. Posting is a separate, authorised step.

## 2. What each old section was for, and the verdict

| Old section | What it did | Verdict |
|---|---|---|
| "Connected to company APIs" badge | Status of the page's own service calls | Removed. Nothing a person acts on; failures are shown where they happen. |
| Type name, "All saved vouchers", "New purchase" links in a loose row | Which voucher type is in use, and navigation | Became the page header: type chip, plus "Saved drafts" and "New purchase" actions. |
| "Account purchases · base currency INR. Confirm the bill's tax treatment… Goods and receipt allocation are not yet available here." | The screen's scope, in a paragraph | Replaced by one plain lede under the title, and an "Amounts in INR" chip. |
| "Tax treatment" select with one real choice | A deliberate confirmation that the bill carries no tax, because this profile cannot record tax and silently saving a taxed bill as untaxed would be wrong | Kept as a **required confirmation**, now a single checkbox "This bill carries no tax" beside the terms it concerns. The save is still refused without it. |
| "Find saved purchases", "Saved Purchase ID", "Open saved purchase" | Reopen a draft, by list or by pasting a UUID | Moved to a **Saved drafts** drawer. Opening by ID stays available there, below the list. |
| "Entry mode: Accounts / services" | A one-button toggle | Hidden while only one mode is allowed. |
| Invoice strip (invoice number, line count) | Sticky context on long bills | Kept in the synthetic preview. On the live page the sticky action bar carries the invoice number, the supplier and the bill's state beside the total, so they stay in view while scrolling. |
| "Purchase details" card | Detail panels the connected profile does not offer | Hidden when it would be empty. |
| Right-hand "Accounting totals" rail | Showed Accounting's calculation once one existed; otherwise only "Save changes, then calculate the saved bill" and the due date | Removed. The calculation is a card that appears only when there is one; the due date sits with the terms; the total sits in the action bar. |
| "Approval & execution" section | Status, approve/reject/cancel, posting, history | Rebuilt as one card: status and revision, a progress track, the next action, history as a list. |

## 3. Why it looked broken

The page's own sections were siblings of the workspace, outside any page container, so they had no
gutter, no maximum width and no spacing rhythm, and ran flush to the shell's right edge. Controls
were laid out with no grid, labels sat in prose, and a second always-empty column reserved 20rem.

## 4. Decisions

| # | Decision | Why |
|---|---|---|
| PPR-D1 | One `janso-page` column holds header, notices, the bill and the lifecycle. | Gives the page the same gutter, width cap and rhythm as every other page ([design-system](design-system.md) §4.2–4.3). |
| PPR-D2 | The shared `PageHeader` gains an optional `meta` strip. | Status and type chips under the lede are generic; Sales will need them. |
| PPR-D3 | No side rail on the live page. The action bar shows "Lines total" until Accounting has calculated, then "Bill total". | The user asked for the rail to go; the total stays visible, and an unconfirmed figure is labelled as one. |
| PPR-D4 | Tax confirmation is a checkbox, not a select. | A one-option select looks like a choice and is not one. |
| PPR-D5 | The live workspace takes `header`, `sections` slots from the controller instead of a `totals` rail. | The connected page owns its own sections; the shared workspace owns the grid and header fields. |
| PPR-D6 | Styles are `janso-purchase-*` rules in `entry.css`, tokens only. | CSS is centralised and theme-safe ([CLAUDE.md](../CLAUDE.md) §4). |
| PPR-D7 | The synthetic preview route keeps its current layout and tests. | It is a separate, finished review surface. |
| PPR-D8 | An account bill's grid is account, description and amount. Discount and net columns come back only when the type allows discounts. | A column of read-only zeros and a second copy of the amount say nothing, and the description was hidden behind line details although the bill needs it. |
| PPR-D9 | The action bar says "Lines total" for what has been typed (only when every line is complete) and "Bill total" once Accounting has calculated. The calculation card appears only when there are figures to show. | The typed figure is useful, but it must not look like Accounting's. A card that says "calculate again to see the figures" only held a place. |
| PPR-D10 | Shared fix: a checkbox that is ticked and disabled keeps a visible tick. | Found while reviewing a read-only saved bill: the tick used the inverse ink meant for the brand fill, on the pale disabled surface, so a saved "this bill carries no tax" read as unticked. It affected every such checkbox. |
| PPR-D11 | Saved drafts are read on every open of the drawer; a failed read shows in the drawer with "Try again", never as a page-wide failure. | A list read once goes stale as soon as a bill is saved, and a banner behind the drawer's scrim cannot be seen or cleared. |
| PPR-D12 | The action reason is cleared once a request succeeds or another bill is opened. | The field is hidden when neither reject nor cancel is on offer, so a reason typed earlier must not ride along, unseen, on a later save. |
| PPR-D13 | The progress track claims only what the status proves: cancelled ends at the cancellation, reversed ends after posted, an issued bill is next to post, an unknown status is shown as itself. | A track that says "Approved, not yet" for a bill cancelled after approval is false. |
| PPR-D14 | A bill that is posted, cancelled or reversed says it can no longer be edited, instead of "you do not have permission to create vouchers". | The permission wording is wrong for a finished bill, whoever is looking. |
| PPR-D15 | A description over 1,000 characters is refused on its own line. | The service refuses it for the whole bill; the line-details field already had the limit. |
| PPR-D16 | A voucher type that needs no separate approval says so, and Submit approves the bill. | Tally Prime and QuickBooks have no approval step unless it is switched on. The service moves a submit straight to Approved in that case ([purchase-e2e-review](purchase-e2e-review.md) D1); the status panel reads `policy.approval_required` and says what Submit does, so a one-person company is not left looking for a second person. The service still decides: the page reads the status it is returned. |
| PPR-D17 | A repeated supplier invoice number is advice while drafting and a question at Submit, never a silent block. | The page asks the duplicate-bill lookup after each save and shows the earlier bills; the service refuses Submit with `duplicate_supplier_bill` until the person confirms, and the page turns that refusal into a dialog, then resubmits with `acknowledge_duplicate_bill` under a new idempotency key (it is a different command). The lookup keeps slashes unescaped, because the proxy refuses an escaped slash and supplier numbers are full of them. A lookup that fails shows nothing: the service checks again at Submit. |

## 5. New layout

```
Purchases                                [Saved drafts] [New purchase*]
New purchase
Record an expense or service bill from a supplier. Bills with tax, and stock
purchases, cannot be recorded on this screen yet.
(Draft) (Account purchases) (Amounts in INR)      * New purchase appears once a bill is saved

[ notices: failure · recovery · status ]

┌ Supplier and bill ──────────────────────────────────────────────────────┐
│ Supplier                         Supplier payable account                │
│ Supplier invoice no.   Invoice date   Posting date   Payment due (read)  │
└─────────────────────────────────────────────────────────────────────────┘
┌ Bill lines ─ n entered ─────────────────────────────────────────────────┐
│ line grid (desktop)  ·  line cards (narrow)                              │
└─────────────────────────────────────────────────────────────────────────┘
┌ Terms and tax ──────────────────────────────────────────────────────────┐
│ [x] This bill carries no tax        Credit terms · Supplier total · Notes │
│                                                  [Edit terms and details] │
└─────────────────────────────────────────────────────────────────────────┘
┌ Accounting calculation (only once calculated) ──────────────────────────┐
┌ Status and approval (only once saved) ──────────────────────────────────┐
  Draft ─ Calculated ─ Submitted ─ Approved ─ Posted     [next action]
══ Lines total ₹24,650.50 · INV-1 · Sharma Office Supplies · Not saved ══ [Review bill] [Save draft] ══
```

## 6. Phases

| Phase | Delivers | Exit |
|---|---|---|
| P1 | Page container and header, drafts drawer, supplier and bill card, terms and tax card, calculation card, rail removed, CSS | Console and UI suites green; page checked in the browser |
| P2 | Status and approval card with progress track and history; loading and setup-needed states | Same, plus lifecycle tests |
| P3 | Narrow and wide layouts, three themes, keyboard order, zoom | Browser evidence recorded below |
| P4 | Independent review, fixes, this document's record | No open blocking finding |

## 7. Verification record

Verified 2026-10-31 on the working tree.

**Browser.** The real `PurchaseEntryConnected` against a fake service backend, in Chrome through Playwright
(harness kept outside the repository). Seen at 1440, 820 and 390 px, in the light, dark and ledger themes,
and in these states: new, validation errors, tax confirmation refused, saved draft, calculated, Saved
drafts drawer, approved, submitted read-only, two voucher types. No horizontal scroll at 390 px. The
read-only saved bill showed an empty tax checkbox; that was a shared styling defect, fixed (PPR-D10).
Not run: a real authenticated Console against the live services, Firefox, Safari, a screen reader.

**Independent review** (a fresh read-only reviewer: code against HEAD, its own browser probes, axe-core
on six states). It found no change to any request path, body, idempotency key or send guard. It found
and this change fixed: the drafts list read once and never refreshed; a failed drafts read that could
not be retried; a stale tax refusal after reopening; a hidden action reason still sent on a later save;
focus lost after choosing a draft; an unrelated failure shown in the drawer; the invoice and supplier no
longer in view on a long bill; a progress track that was wrong for issued, cancelled, reversed and unknown
statuses; no length limit on the new description column; a browser-review script for the old controls;
dead code and CSS; a wrong "review only" message; and test gaps. PPR-D11 to D15 record the decisions.

**Tests.** Console type-check and the shared UI type-check pass. Console Purchase, voucher and
voucher-type suites: 538 passed and 1 failed (`purchase-entry-form`, which asserts wording another
agent has since changed in `purchase-entry.ts`). Shared UI suite: 75 files, 2,278 tests passed. A full
Console run under load had 90 failures in 30 files; 17 of those files still fail when run alone, all in
areas this change does not touch (company configuration, tax, warehouse, invoice designer and similar,
plus the `purchase-entry-form` file above).
