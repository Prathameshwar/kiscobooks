# Purchase account bill: end-to-end readiness

Reviewed 2026-11-02 at the user's request: walk the whole life of a Purchase account bill (`/vouchers/new/purchase`), say
for every step what has been seen working, and fix what was not. Two passes: an independent read-only review of the
screen's code (no knowledge of the author's reasoning), and a live pass as `tenant1` against the real services with
nothing stubbed (the GST pass stubs one read, as noted there). This page is the record; the GST part is in [purchase-tax-entry-plan](purchase-tax-entry-plan.md).

## The life of a bill, step by step

"Live" means seen working in the browser against the running services; "tests" means the console/Vouchers suites.

| Step | Live | Tests | Notes |
|---|---|---|---|
| Open the page: types, capabilities, field access | yes | yes | |
| Choose or create a supplier and an expense account | yes | yes | [quick create](purchase-quick-create-todo.md) |
| Enter lines; footer shows the lines total | yes | yes | "Lines before GST" for a bill that carries GST |
| Say whether GST applies; GST facts | no tax: yes; GST: up to save | yes | the company's registration read was stubbed live (none exists) |
| Bill details: credit terms, notes | yes | yes | declared total, difference reason, rounding account, advances, proposed payment, files: tests only |
| Save a draft, edit and save again | yes (POST, PUT) | yes | retries reuse one key and body |
| Reopen from the address, from Saved drafts, by ID | yes | yes | the address now keeps the saved bill (fixed, below) |
| Revision history and a saved revision | yes | yes | history lists *steps* (submit, approve, cancel), not each save; says so when empty |
| Calculate, accept the calculation | seen once | yes | needs the Accounting connection, which this environment does not have (item 1 below); seen during a temporary one on 2026-11-02, since removed |
| Submit and approve (this type needs no separate approval) | seen once | yes | submit needs an accepted calculation, so the same condition; reject: tests only |
| Calculate again on a submitted or approved bill | seen once | yes | shows "Accepted" and the bill total; same condition |
| Duplicate supplier bill check at submit | notice: yes; dialog: seen once | yes | the notice appears after saving; the dialog is at submit, so it needs a calculation; "Do not submit" leaves the draft |
| Post | **no** | yes | posting is switched off here by design |
| Cancel a draft | yes | yes | |
| Print | no | yes | needs the print runtime and `vouchers.artifact.*` access |
| A bill in the voucher list: edit | n/a | yes | now opens this screen (fixed, below) |

## What was fixed

From the live pass:

1. **A saved bill was lost on reload.** After the first save the screen writes the bill's id into the address with
   `history.replaceState`, so a reload or a shared link reopens it. The unsaved-changes guard
   (`use-draft-navigation`) took that for leaving the page and cancelled it whenever a command was pending, which it is
   during a save: the address never got the id, and a reload showed a blank bill. A page rewriting its own address (same
   path, `replace`) is no longer treated as leaving. The same cancelled write put "Finish the open detail editor…" over
   the "Loaded saved revision" message when a bill was opened from its address.
2. **The revision history showed nothing for a draft** with three saved revisions, because history is the step log. It now
   says "No steps recorded yet" once it has been read and is empty.

From the independent review (each confirmed in the code before it was changed, each with a test that failed first):

3. **A finished posting locked the next bill opened.** The "execution" state belonged to the page, not to a bill, so after
   posting bill A, opening draft B from Saved drafts showed B as "being posted" and read-only until a reload.
4. **Reopen-and-save rewrote lines this screen does not show.** A saved line priced *including* tax, or carrying
   quantities, a promotion, a free reason or a price denominator, was sent back as a plain amount before tax. Such a bill
   now goes to voucher review instead of being edited. The service's own defaults on a plain line are not "more".
5. **The calculation card said "Accepted" for any calculation** once the bill had accepted one. It now compares hashes: a
   fresh calculation that differs is labelled so, Submit is held back until it is accepted, and the footer no longer
   implies otherwise.
6. **Nobody could see Accounting's payable after submission.** "Calculate saved bill" is offered for draft, rejected,
   submitted and approved bills (read-only; acceptance stays for drafts), so an approver can see the real amount and
   whether it is the accepted one.
7. **Two GST controls were dead ends**: the supplier's registration choice vanished once one was picked; a company
   registration no longer in force on a new invoice date left a static "None in force" with nothing to press. Both stay
   choices.
8. **The wrong reason for a read-only bill.** A bill that is being posted, or that the person may not edit, said "you do
   not have permission to create vouchers". It now says what is true.
9. **A retained execution reference could leave a blank screen** (a failed read of it, with another bill in the address):
   the retry button is on screen, and the bill in the address is opened once the reference has been followed.
10. **The voucher list sent a Purchase to a second, limited editor** that cannot open a bill with GST. "Edit draft" (and
    "Edit rejected bill", new) now open `/vouchers/new/purchase`. Other kinds are unchanged.
11. Stale words ("cannot be recorded") in the tax card and in three docs.

## Not changed, and why

- **Cancel and reject act on one click** once a reason of three characters is typed. A confirmation would be better; it
  is a design choice that touches many tests, so it is listed rather than slipped in.
- **A retained command has no "discard".** After an uncertain outcome the screen insists on retrying the same request and
  key, so a command that did commit cannot be applied twice. A persistent 5xx therefore waits for the service. Discarding
  is a decision about idempotency, not a button.
- **GST pre-checks use the invoice date**, where Accounting uses the statutory tax point (reverse charge: invoice date plus
  61 days; supplier-charged: the invoice date unless the service was more than 30 days earlier). They are advice and
  block only a missing or out-of-force registration; Accounting decides at calculation. Mirroring the tax-point rules on
  the client belongs with the planned statutory-date amendment in [voucher-tax-recording](voucher-tax-recording.md).
- **Saved drafts shows a date and the end of an ID.** The voucher list row carries no supplier, invoice number or total,
  so the drawer cannot say which draft is which. That needs a lean list projection from Vouchers
  ([api-conventions](api-conventions.md)); reading every draft to fill it in would be 25 requests per opening.
- A **rejected** bill is not in the Saved drafts drawer (it lists drafts); it is in the voucher list, with "Edit rejected
  bill".

## What this environment needs before the rest can be seen live

Nothing below is a defect of the screen. Each is an activation decision.

1. **Accounting calculation connection: not configured here.** A temporary one was made on 2026-11-02 so that calculate,
   accept and submit could be seen live; it was removed the same day at the user's request (both variables deleted,
   Accounting and Vouchers restarted, the four posting flags never touched). Why it exists: Vouchers does not work out tax
   or the payable amount itself, Accounting owns that, and Vouchers asks it over a private credential scoped to one company
   (`VOUCHERS_EXECUTION_OWNER` in Vouchers, the matching entry in `ACCOUNTING_VOUCHER_EXECUTION_CREDENTIALS` in
   Accounting). Without it *Calculate saved bill* answers "invoice calculation owner is not configured for this company":
   a company can save drafts but cannot calculate, accept or submit a bill, and cannot print one (item 4). Calculation is
   read-only; it posts nothing. Setting the connection up is a deliberate per-company step for the user to decide, not
   something to switch on to make a check pass. Taxed bills also cannot be calculated here (item 3); Accounting then
   answers "invoice calculation was refused; verify accounts, configuration and tax evidence", which does not say which,
   so the GST section's own checks (no tax default, wrong reverse-charge setting, supplier not regular) are where the
   cause is named.
2. **Posting.** `VOUCHERS_MONEY_EXECUTION_ENABLED`, `VOUCHERS_INVOICE_EXECUTION_ENABLED`, `ACCOUNTING_VOUCHER_MONEY_ENABLED`
   and `ACCOUNTING_VOUCHER_INVOICE_ENABLED` are all `false`. Turning them on lets a bill post to the books.
3. **GST.** A company GST registration (no screen adds one; Identity's API does), tax rules in Accounting's replica (the
   Catalog outbox is not published here, so the replica is empty), and a purchase tax default on each expense account.
4. **Print.** The Vouchers print runtime ([purchase-print-deployment](purchase-print-deployment.md)), access to artifacts,
   and the Accounting connection of item 1, through which Vouchers reads Accounting's print facts.

## Default voucher types

New companies get the Purchase account bill with Account **and Service** lines
([company-voucher-defaults](company-voucher-defaults.md), catalogue v3), so GST can be recorded without editing the type.

## Second review, 2026-11-02 evening: configuration, permissions, lifecycle and posting

Four independent read-only reviews (configuration, authorization, the Vouchers lifecycle, Accounting calculation
and posting), each finding then confirmed in the code and fixed with a test that failed first. No migration, API
shape, permission key or role changed.

**Fixed**

1. *Presets in a common profile blocked every other voucher kind.* See
   [purchase-calculation-presets](purchase-calculation-presets.md#review-2026-11-02-purchase-bill-end-to-end-review);
   also: preset discounts are checked together against the total discount limit, and preset names are distinct.
2. *A calculation could be accepted that posting always refuses.* Accounting's preview (used for "Calculate" and for
   acceptance) now refuses what posting would: a zero payable, a due date before the bill date, price/invoice rounding
   without a rounding account, and a missing or ambiguous GST posting mapping (`domain/invoice_readiness.py`). The
   bill fails at Calculate, with its reason, instead of after approval.
3. *Accounting's reason was hidden.* Vouchers now passes Accounting's own refusal message through ("invoice
   calculation was refused: …") instead of one generic sentence; the generic one stays for a malformed answer.
4. *A supplier with two ledgers, or whose supplier role is inactive, could be billed.* The invoice calculation (so
   acceptance and posting) requires the party's supplier role to be ACTIVE and exactly one live ledger for it
   (party-ledger PL-D03/PL-D06); legacy duplicates say "repair it first".
5. *The duplicate supplier-bill guard could be stepped around.* At submit a Purchase's bill number must not be
   punctuation only, and a GST supplier invoice number (header or line) must equal the bill number (ignoring case and
   spacing), so the guard and the GST input-credit fact always name the same bill.
6. *Editing a submitted or approved bill left no trace that the approval was withdrawn.* The edit now records a
   `reopen` step (APPROVED/SUBMITTED/REJECTED → DRAFT) in the bill's history, and the audit event carries the reason.
7. *Supporting-file downloads were not audited* (the Purchase PDF's were). Each download now writes an access audit
   event, committed before any byte is sent; a refused download writes none.
8. A Console test still expected discounts to be re-sorted ahead of charges. Since the preset work the component
   order is the calculation order and can be moved; the test now says so (behaviour, not a defect).

**Reported, not changed**

- **nginx write limit is one bucket for all Console users** (`start/win/conf/bill.conf`): the Console proxy calls the
  gateway from one address, so the per-IP zone is shared. The in-app per-user limiter still applies. Fixing it means
  keying nginx on a value the proxy vouches for; that is deployment design, and `/accounting/` has no nginx limit.
- **In-app limiter is per process and refuses new keys after 4,096 in a window** (`libs/platform/rate_limit.py`).
- **Supporting-file bytes are written before the upload command commits**, so a refused upload can leave an orphan
  file. Deleting it inline races a concurrent upload of the same bytes; it needs a sweep, not a delete.
- **A supplier whose accounting policy disables bill-wise tracking** is refused only at posting: checking it at
  calculation needs `accounting.policy.read`, which the reading roles do not hold.
- **Changing a type's rules or presets** retires the type revision in-flight bills were captured under; they must be
  saved again and re-approved (fails safe).
- **POSTED is recorded on the operation's audit event and the history step**, not as a `vouchers.voucher.*` event.
- **One person can record, submit and post** when the company has no approval workflow (decision D1).

## 2026-11-03: no unnecessary blockers

Owner direction: a new company with its supplier/customer and accounts must be able to create and post any voucher;
approvers, owners and optional configuration apply only once configured, and nothing is listed per company in
deployment files ("we can have hundreds of tenants and thousands of companies").

**Changed**

| Blocker | Change |
|---|---|
| Only the books-begin month opened at company creation | Every month from books begin to the year end opens ([company-setup](company-setup.md) decision log). Existing companies open further months from Manage years. |
| Enabling a feature after books setup refused every voucher post (`CONFIGURATION_CHANGED`) | Defect fixed: Accounting compared the command with the digest stored at setup. The live digest is still checked against the delegated context before any effect. |
| A credit Sale, customer refund or Journal debiting a customer needed `accounting.credit.read` even with credit limits off | Skipped while `credit_limits` is off, when an assessment can only ALLOW ([roles-permissions](roles-permissions.md)). |
| Starter types: Sales account invoice ACCOUNT-only (no GST sale), no discounts/charges, narration and line descriptions required | Catalogue v4 ([company-voucher-defaults](company-voucher-defaults.md)). |
| A bank tender needed a reference; a new bill reference needed a due date | Both optional (contract, import and Console). A cheque still needs its date; a new bill is due on the document date. |
| Issuing an order, quotation, challan or stock document needed a number series nobody provisions | A type without a series issues from its own automatic financial-year series, created on first use. |

**Not changed, and why**

- **Per-company connection lists.** Calculation, acceptance, submit, print and posting go through the Vouchers→Accounting
  execution credential, and posting through Accounting→Identity's reservation credential; Reports, print layout and
  import lookups have the same shape. Each names its companies in env files, so every new company needs an edit and a
  restart. Replacing that with native company enrollment (the pattern the master snapshots already use) was attempted
  and refused by the session's security guard, then reverted untouched. It needs the owner's explicit permission.
- **Global posting switches** (`VOUCHERS_INVOICE_EXECUTION_ENABLED`, `ACCOUNTING_VOUCHER_MONEY_ENABLED`,
  `ACCOUNTING_VOUCHER_INVOICE_ENABLED`) stay off locally until the connections above exist; they are deployment
  switches, not per company.
- **Approval on administrator-created types** stays on by default; the type form shows it and it can be switched off.
- Goods/mixed invoices (B24), notes on GST or opening bills (B17/B25) and stock posting (B20-B26) are unbuilt work, not
  configuration.
