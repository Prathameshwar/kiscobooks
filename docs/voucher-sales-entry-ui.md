# Sales bill entry UI — live phase checklist

The working checklist for the Sales **creation** page. The platform contracts govern; this
tracks the front-end build only. Read with [invoice calculation](voucher-invoice-calculation.md),
[commercial configuration](voucher-commercial-configuration.md),
[Sales configuration](voucher-sales-configuration-plan.md) and
[the shared data model](voucher-data-model.md).

**Agreed scope (2026-10-28).** UI first, **static fixtures only** — no API calls, no
persistence, no posting. Creation only: no list, no edit, no cancel, no print. The form renders
from a **mocked effective-policy contract** shaped like the one
[Sales configuration §3](voucher-sales-configuration-plan.md) says the service should expose, so
wiring it later is a change of data source rather than a rewrite. This is the ordering that paid
off for the invoice designer, and for the same reason: the interface is reviewable before a
contract is committed to a migration.

**What the platform decides, and this UI may not re-decide.**

| Contract | Consequence here |
|---|---|
| The mode changes presentation and validation, not storage ([data model §4](voucher-data-model.md)) | One line grid whose **column set** changes by mode. Not three screens |
| Calculation authority is server-side and versioned ([calculation §5](voucher-invoice-calculation.md)) | Totals are a **provisional preview**, labelled, shaped like the server's accepted result. Never the authority |
| Line and document discounts normalise to shared CHARGE/ADJUSTMENT components ([§4](voucher-invoice-calculation.md)) | The discount cell is an input onto a component; the discount total is read-only |
| Tax is resolved, not entered; a display preference cannot disable tax ([commercial §3](voucher-commercial-configuration.md)) | Tax columns and the tax summary are read-only and derived. No `allow_tax_edit` anywhere |
| Actual ≠ billed quantity; 10+1 is actual 11 / billed 10 ([commercial §4.1](voucher-commercial-configuration.md)) | Two quantity columns, always. A reward row is first class, not a zero-rate hack |
| Zero consideration is not zero taxable value or zero cost ([§4.2](voucher-commercial-configuration.md)) | A free line needs a typed purpose; a blank rate is refused as a way to make something free |
| Availability, requiredness, default, editability, override permission and approval threshold are six separate properties ([Sales §3](voucher-sales-configuration-plan.md)) | The form renders from policy, never from a hardcoded field list |
| Money is `DECIMAL(19,4)` (CLAUDE.md §4) | Every amount and quantity input is **string-backed**. No `number` anywhere near money |

| Phase | Scope | State |
|---|---|---|
| S1 | Route, three-region layout, sticky document bar and totals rail, action bar; the mocked effective-policy contract the whole form reads from | **done** |
| S2 | `AmountField` and `QuantityField` — string-backed, display-config driven | **done** |
| S3 | `EntryGrid` — the keyboard model, cell types, add/remove/reorder/duplicate | **done** |
| S4 | The sales line grid: three modes, in-cell lookup, price provenance, actual/billed and reward rows, row drawer | **done** |
| S5 | Components: line / selected-line / document discount scopes, charges, rounding; the provisional totals preview | **done** |
| S6 | Settlement: credit terms, split tenders, advance application, outstanding; warnings panel; action-bar states | **done** |
| S7 | Polish: keyboard-only pass, roles and focus order, contrast in three palettes, empty and invalid states, 200-line performance, docs | **done** |
| S8 | Third review fixes: money rules, Mixed mode, screen and keyboard defects, the gaps (checklist below) | **done** |

## Open questions this UI must not answer silently

1. **There is no Issue action, deliberately.**
   [Sales configuration §3.1](voucher-sales-configuration-plan.md) is explicit: Sales invoice
   issuance is *rejected* in Vouchers pending the statutory profile, and the legal number
   allocator belongs to Accounting under **D05**. The page offers **Save draft** and
   **Preview** only. An Issue button that 400s, or that quietly allocates a second
   non-statutory number, is worse than no button — so the control is absent and the action bar
   says why rather than leaving a reader to guess.
2. **The effective-policy response shape is a proposal.** The service "should expose" source
   revision IDs, allowed/required/default/editable controls and reasons for disabled mechanics.
   Nothing implements it. `sales-entry-policy.ts` is that contract written down by building
   against it, and is **not** a service decision.
3. **Invoice acceptance is `STANDARD` only.** B24 goods posting, B25 returns and B19 statutory
   artifacts are unverified, so there is no e-invoice or e-way-bill surface here and the goods
   path is a draft-only interface.
4. **Money admission defaults to disabled** and release activation is separate (CLAUDE.md §1).
   This page can be built and reviewed; it cannot be switched on by building it.
5. **Decided (S8-1, 2026-10-29): a discount on a tax-inclusive price is inclusive too.** On a
   tax-inclusive bill every discount stage works on the inclusive figures, and each line is taken
   back to pre-tax only after them; the tax is what is left, so ₹18 off a ₹118 line at 18% leaves
   ₹100 to pay (taxable 84.75, CGST 7.63, SGST 7.62). A percentage gives the same answer either
   way. Chosen because it is what a counter clerk means by "₹118, ₹18 off" and what Tally and
   Zoho do on inclusive entry. The page states the rule beside the totals. **The service must
   confirm it** — record it in [invoice calculation](voucher-invoice-calculation.md) and its
   decision log when the calculation endpoint is built.
6. **Decided (S8-2, 2026-10-29): the policy names the rate-override grant; this page checks it.**
   The fixture names `vouchers.edit`, the nearest catalogue key. No new key is added from a UI
   change — a dedicated `vouchers.price.override`, if wanted, belongs to the permission catalogue
   and system roles ([roles-permissions](roles-permissions.md) §2, §6) together with the policy
   service, and the page needs no change for it.

## Phase S1 — delivered

The shell the rest of the phases fill in, and the contract they read from.

| Piece | What it owns |
|---|---|
| `app/vouchers/new/[kind]/page.tsx` | The route. Resolves session, company and `vouchers.create`; refuses an unsupported kind with a 404 rather than a blank screen |
| `app/components/SalesEntryPage.tsx` | The three regions, and which of them a phase fills |
| `app/components/SalesEntryHeader.tsx` | Party roles, dates, series and mode — every field rendered from policy |
| `app/components/SalesEntryTotals.tsx` | The rail: a read-only ledger of truth-so-far, with the provisional label |
| `app/lib/sales-entry-policy.ts` | The mocked effective-policy contract, and the six separate control properties |
| `app/lib/sales-entry-draft.ts` | The draft a creation page accumulates, as a pure reducer |
| `packages/ui/src/styles/entry.css` | The dense entry surface: grid, cells, rail, row states |

**Why the console shell and not the designer's full-bleed group.** The invoice designer renders
outside `ConsoleShell` because a canvas needs the viewport. A money document is the opposite
case: the company chip and the financial-year chip are exactly what a reader must not lose
sight of while entering one, and the rail is how they switch away deliberately rather than by
accident. The rail can be collapsed for density; it is not taken away.

**Why not `Stepper` / `WizardLayout`.** Both exist and both are right for company onboarding,
where a reader passes through once. A billing clerk raises dozens of these a day, and a wizard
turns a single dense screen into four pages of waiting. Tally's speed comes from exactly this
and it is cheap to match.

**The document bar is sticky and the totals rail is sticky.** Scrolling a long line list must
not take away who you are billing or what the total has become — in Zoho Books and QuickBooks
both scroll away, and it is the most common complaint about entering a fifty-line invoice.

## Phase S2 — delivered

| Piece | What it owns |
|---|---|
| `packages/ui/src/lib/numeric-input.ts` | `useNumericInput`, and the pure `canonicalise` / `storable` / `settle` |
| `packages/ui/src/components/NumericField.tsx` | `AmountField` and `QuantityField` — the form chrome over that hook |
| `.janso-numeric__unit` in `janso-ui.css` | The currency or unit beside the box |
| `tests/numeric-field.test.tsx` | 27 tests |

**A hook plus two thin components, not two components.** The entry grid needs the same parsing,
separators, storage scale and display rule in a bare cell as a form needs in a labelled field.
That mechanism is the expensive part, so it lives once — if a figure typed in the grid and read
on a form could disagree, the whole thing is worthless.

**The value is a `string` and the tests assert what is *emitted*, not only what is painted.**
A `number` prop would have been a float round-trip waiting to happen on a `DECIMAL(19,4)`
column, and the fifth decimal place is reported as an error rather than silently truncated,
because a truncated figure is a wrong figure.

**The display rule.** Focused shows canonical text (`1234.5`); blurred shows the company's
formatting (`12,34,567.50` under Indian grouping, `1,234,567.50` under western). Editing a field
that inserts separators under the caret is miserable; reading a column of ungrouped digits is
worse. The canonical value never contains a separator, so what goes on the wire is never what
was painted. An absent value stays empty rather than showing `0.00` — a blank rate and a zero
rate are different facts, and a zero in an empty box invites someone to leave it there.

**Pasting is a first-class case**, because people paste from spreadsheets, bank statements and
other systems. Grouped figures, a currency symbol, the currency code, non-breaking spaces and
the accounting `(1,234.00)` negative are all read. A company whose separators are swapped
(`1.234,56`) is read correctly, which is why the decimal separator is split off *before* group
separators are cleared.

**The currency sits beside the box, never in it.** A symbol inside the input is a character the
caret has to be driven past on every edit.

Three things the tests found, all real:

1. `12..5` was being read as `12.5` and `1.2.3` as `1.23` — a silent reinterpretation of
   genuinely ambiguous input, which is the one thing the parser must not do. Extra separators
   are now preserved so the text is unstorable and fails where a reader can see it.
2. Blur checked the raw canonical text before tidying it, so `.5` and `1.` — the exact inputs
   tidying exists for — were rejected instead of settled. Settling now happens first.
3. Unstorable text is **kept** on blur rather than reverted. `MeasureField` reverts because its
   value is a number with a usable previous state; here the text *is* the value, and silently
   discarding what someone typed into a money field is how a wrong figure gets committed.

## Phase S3 — delivered

`packages/ui/src/components/EntryGrid.tsx`, its styles in `entry.css`, 27 tests in
`tests/entry-grid.test.tsx`.

**A separate control from `DataTable`, deliberately.** That is the *read* surface — a cursor
page, a sort the server honours, a verb set per row. This is its opposite. Making one component
do both would give a read list edit machinery it never uses and give an entry grid paging it
must not have: a fifty-line invoice is one document, not a page of them.

### The keyboard model is the product

| Key | Does |
|---|---|
| `Tab` / `Shift+Tab` | Next / previous cell, native tab order |
| `Tab` on the last cell | **Adds a line and lands in its first cell** |
| `Enter` / `Shift+Enter` | Next / previous row, *same column* |
| `Ctrl+Enter` | Add a line |
| `Ctrl+D` | Duplicate this line |
| `Alt+↑` / `Alt+↓` | Move this line |
| `Ctrl+Backspace` | Remove this line — from the start of a cell (S7 review) |
| `Alt+Enter` | Open this line's detail (S7) |

Tab-out-adding-a-line is the behaviour that makes entry continuous, and most of why Tally feels
fast — without it every line costs a reach for "Add line". `Enter` moving down a column is the
commonest entry shape there is. Removing a line **moves focus first and then removes**, because
dropping focus to the body in a fifty-line document means finding your place again by eye.

**The arrow keys are left alone.** Every cell is a live input, so `←`/`→` belong to the caret
and `↑`/`↓` to the reader. Stealing them for cell movement is the single most common way a web
grid becomes unusable for anyone who types, and a test asserts the caret still moves.

### Why not `role="grid"`

The WAI-ARIA grid pattern is one tab stop with arrow-key navigation over a roving index, and
that contract cannot hold when every cell is a text input needing the arrows for the caret.
Claiming the role anyway would be a promise to a screen-reader user that is not kept — the same
reasoning as `Menu` dropping `aria-haspopup` when it has nothing to open. So it is a plain
`<table>` with native tab order, a caption naming the movement keys, `<th scope="col">` headers,
and every cell input named `"<column>, line <n>"` because a visible label per cell is impossible
in a twelve-column row.

### Cells

`text`, `amount`, `quantity`, `select`, `derived` and `custom`. The numeric cells use the **same
`useNumericInput` hook as the form fields** — if a figure typed in the grid and read on a form
could disagree, both are worthless. A `derived` cell is read-only *text*, not a disabled input:
a disabled box invites "why can I not type here", and the answer ("the service resolves this")
is not a permission problem. An unresolved one is an em dash, never `0.00`. A `custom` cell
renders its own control and is given the cell props and ref registration it needs, which is the
slot the S4 item lookup fills.

Two things the tests found: the focus registry needed to be a **registry** rather than a DOM
sweep, because a lookup cell renders a control the grid did not build and "the next input" would
find a popover's filter box as readily as the next cell; and select-on-move had to be applied in
a **layout effect**, because a numeric cell swaps grouped text for canonical on focus and
selecting before that swap leaves the caret at the end — so moving down a column *appended*
instead of replacing, the opposite of a spreadsheet.

## Phase S4 — delivered

| Piece | What it owns |
|---|---|
| `app/lib/sales-entry-columns.tsx` | Which columns a sales bill has, what each means, and the rate-provenance and reward-quantity derivations |
| `app/components/SalesLineGrid.tsx` | Joining the grid to the draft: cell changes, row state, row notes, the drawer |
| `app/components/SalesLineDrawer.tsx` | The long tail — HSN/SAC, stock intent, warehouse, batch, expiry, the reasons, the note |
| `app/lib/sales-entry-draft.ts` | Drawer fields, plus `duplicateLine` and `moveLine` |
| `tests/sales-line-grid.test.tsx` | 22 tests |

`EntryGrid` owns the keyboard and the row chrome; `sales-entry-columns` owns the sales policy.
A purchase bill or a credit note will reuse the grid with its own column list, which is the
mechanism-versus-policy line the platform draws everywhere else.

**The subject is a lookup, not a text box**, and choosing one patches several fields at once
rather than writing a cell. `SearchSelect` already portals its list and pages remotely, which is
what makes it usable inside the grid's horizontal scroller at all.

**Every figure the service owns is a `derived` column** — taxable value, tax rate, tax amount,
amount — rendered as read-only text and shown as an em dash until S5. There is no box to wonder
about, because tax is resolved and not entered.

**A reward line is marked as deliberate, not as wrong.** Actual above billed gets the success
edge rather than the danger one: free units are a recorded term, and a row that looks like an
error every time someone gives a sample away trains people to ignore the marker that matters. It
is still *invalid* until it says why the quantities differ, because a bare difference is not
evidence of an authorised bonus. The free quantity is **derived** — never a third editable
quantity and never a second stock movement.

**The reason fields live in the drawer**, not in a grid cell. A reason typed into a narrow cell
is a reason nobody reads; the grid marks the row and names the missing field, and the drawer is
where it gets answered. The drawer also explains the 10+1 arithmetic in words, because "the bonus
must not deduct from the already-normalised amount" is the part people get wrong.

**Stock intent is explicit on every goods line** — dispatch now, already dispatched or dispatch
later — and the drawer says what each one means. Goods billed against a delivery note must not
move a second time, and a deferred bill must not fabricate a movement that has not happened.
There is no "does not affect stock" choice on a goods line; a service line has no stock to move
and is told so. *(Corrected in S8: this paragraph used to list "no stock effect" among the goods
choices while saying no such switch existed, and the drawer offered it.)*

**Duplicating a line does not carry its reasons.** A quantity-difference reason and a rate
override justify *that* line; copying them would let an approved exception be multiplied by
pressing `Ctrl+D`. **Reordering does not re-price**: row order is presentation, and the
calculation contract says document order alone cannot change a result.

One change to the primitive, found by using it: `EntryGrid`'s key handler now walks up from the
event target with `closest('[data-entry-row][data-entry-col]')` rather than reading the
attributes off the target, and `focusCell` finds the first focusable element inside whatever a
`custom` cell registered. A custom cell renders a control the grid did not build and cannot be
expected to forward arbitrary attributes onto whichever element ends up focused — without this
the lookup column had no keyboard integration at all.

## Phase S5 — delivered

| Piece | What it owns |
|---|---|
| `app/lib/fixed-decimal.ts` | Exact arithmetic: `bigint` at the storage scale, half-up rounding in one place, largest-remainder allocation |
| `app/lib/sales-entry-preview.ts` | `previewInvoice` — the provisional preview, in the calculation contract's order, shaped like the service's accepted result |
| `app/lib/sales-entry-draft.ts` | Bill and selected-line discounts, charges, the customer's state, a resolved `taxRate` per line |
| `app/components/SalesComponentsDrawer.tsx` | Discounts above the line and charges |
| `app/components/SalesEntryTotals.tsx` | The rail, from the preview; `totalsLines` as a pure function |
| `tests/sales-entry-preview.test.ts`, `tests/sales-entry-components.test.tsx` | 25 and 13 tests |

**Exact, not approximate.** Every figure is a `bigint` scaled by 10⁴. A `number` cannot do this
honestly — `0.1 + 0.2` is the demonstration, and a 2.5% component on a six-figure line drifts by
exactly the paisa that would make a preview disagree with the accepted invoice for no reason. With
exact arithmetic, when the two differ it is because of a rule, which can be explained; floating
point cannot be.

**The order is the contract's order** — base, line discount, selected-line discounts, bill
discount, tax per line, charges, round off — and it matters, because each discount stage applies
to what the stage before it left. The contract's own worked example is a test: 10% then 5% is
**14.5%**, not 15%. An amount discount is apportioned by remaining value with the
**largest-remainder** method, so ₹100 over three equal lines is `33.34 / 33.33 / 33.33` and
reconciles to its source exactly; independent rounding would give 99.99, and the contract rejects
an allocation that does not reconcile.

**CGST and SGST are separate components**, each computed at half the rate and rounded on its own —
not one tax figure halved. On ₹333.33 at 5% each half is 8.33 and the tax is 16.66; halving a
rounded 16.67 would give two components of 8.34 that do not exist. Intra- versus inter-state
follows the chosen customer's state against the company's, and **until a customer is chosen the
rail shows one tax figure**, computed as CGST + SGST, and says so. (S7 review: this said the total
was the same either way. It is not — IGST rounds once and CGST + SGST twice, so the two can
differ by a paisa per line — and the rail's sentence now says that.)

**Unknown is `null`, never zero.** A line whose tax rate is unresolved makes the tax and the total
unknown: a partial tax total is a wrong one, and zero reads as "untaxed". A tax-inclusive rate
whose tax is unknown cannot be taken back to its base, and that line is left out with a sentence
saying why — and, since the S7 review, the total is then unknown too, for the same reason. An empty bill, by contrast, genuinely totals zero, and the rail says so — the S1 test
that every figure was an em dash was restated, because it was right then and would be the
opposite error now.

**Round off is its own line**, half-up to the configured increment, never a nudge to a tax
figure. **Charges are added untaxed and the rail says so**: whether freight is part of a supply's
assessable value is a tax-profile result, and the drawer has no "taxable" checkbox because that is
not the reader's switch.

**The drawer offers one bill discount, not two** — two would be two authorities for one benefit —
and a discount above the policy's approval threshold is a **warning**, not an error: it is a step
someone else takes, and the reader should know before saving rather than after. A selected-line
discount that still names a removed line drops the reference, because an allocation to a target
that no longer exists is one the contract rejects.

**Master data resolves, it is not typed.** Choosing an item brings its list price (marked as the
list price, so typing over it is visibly an override), unit, HSN/SAC and tax rate; choosing a
customer brings their state. The fixture tax rates in `SalesEntryRoute` stand in for the
jurisdiction adapter's answer and are explicitly **not** statutory claims.

## Phase S6 — delivered

| Piece | What it owns |
|---|---|
| `app/lib/sales-entry-policy.ts` | Accepted tender modes and which of them require a reference |
| `app/lib/sales-entry-draft.ts` | Tenders and applied advances on the draft; their validation, including the card-number refusal |
| `app/lib/sales-entry-preview.ts` | `settlement` on the preview and `settlementProblems`; `addDays` for due dates |
| `app/components/SalesSettlementDrawer.tsx` | Payment: tenders, one-press "Receive ₹X by <mode>", the customer's open advances, credit terms |
| `app/components/SalesReviewDialog.tsx` | "Check this bill before saving" — a summary, not a printout |
| `app/components/SalesEntryTotals.tsx` | The payment card in the rail; problem items link to their line |
| `app/components/SalesEntryPage.tsx` | Panels, Ctrl+S, the leave guard, go-to-line, the "Before saving" sentence |
| `tests/sales-entry-settlement.test.ts`, `tests/sales-entry-payment.test.tsx` | 24 and 13 tests |

**One equation.** Total, less advances applied, less money received, is what is left owing.
Payment method never changes revenue or tax, so the payment card sits *below* the invoice
figures rather than among them, and a test proves a UPI and a cash payment produce the same
invoice. When the total is unknown, so is what is owed — an em dash, not a guess.

**Change comes only out of cash.** Cash tendered, cash applied and change returned are separate
facts; the rail shows "Return ₹400.00 in change", the number the counter actually needs. Paying
more than the bill by UPI, card or transfer is an **error**, because nobody hands back change on
those, and the sentence says to reduce a payment. **A cheque is recorded, not cleared**: it
settles what is owed on this draft but shows as "Cheque, to clear", never as received.

**An advance points at an existing credit.** The drawer lists the chosen customer's open
advances (stale responses ignored when the customer changes), applies each source at most once,
refuses more than it has unallocated, and caps what it takes at the bill — the rest stays on the
advance for another document. Changing the customer drops applied advances, because they were
the other party's money.

**No card number is ever stored** (CLAUDE.md §5.10). A card tender asks for the approval code,
says card numbers are never stored, and refuses a 12–19 digit run (spaces and dashes ignored)
with a sentence naming why.

**Due dates are business dates**: credit days are a whole number up to 999, added to the
invoice date in UTC so a browser east of Greenwich never shifts the day, and shown only while
something is owed.

**The action bar always says why.** A disabled Save carries "Before saving: <first error>";
Preview opens the review dialog, which saves from its footer; **Ctrl+S** saves from anywhere on
the page; leaving with unsaved work raises the browser's prompt, which stops once the revision is
saved. Saving is still a stub that says nothing was stored — the vouchers write path plugs in at
`onSave`. **No Issue action**: statutory numbering is unreleased (D05).

**Problems link to their line.** Each line problem in the rail has a "Line N" button that
scrolls to and focuses that line's first control. The page test caught a real bug here: one
selector list returned the lookup's wrapping span (document order) instead of its input, so
focus went nowhere; the cell's host is now found first, then the control at or inside it.

## Phase S7 — delivered

| Piece | What it owns |
|---|---|
| `packages/ui/src/components/EntryGrid.tsx` | Memoised rows (`rowSignature`), forward Tab past row buttons, blank-last-row exit, `Alt+Enter`, `showUnit`, `adornment`, `renderKey`, `isRowBlank` |
| `packages/ui/src/styles/entry.css` | Visible cell unit, provenance chip placement, party field width (was an inline style), shortcut list, empty-grid hint |
| `packages/ui/src/styles/theme-ledger.css` | `--janso-ink-faint` lifted `#736b5d` → `#70685a` |
| `packages/ui/tests/contrast.test.ts` | Fourteen entry-surface pairings, in all three palettes |
| `app/lib/sales-entry-draft.ts` | `problemTarget` — where each problem is fixed; `inSentence` for labels mid-sentence |
| `app/lib/sales-entry-columns.tsx` | Indexed problem and preview lookups; rate provenance chip; visible `%` on the discount cell |
| `app/components/SalesShortcutsDialog.tsx` | Every key, on `Ctrl+/` and a Keys button |
| `app/components/SalesEntryPage.tsx`, `SalesEntryTotals.tsx`, `SalesEntryHeader.tsx` | Arrival focus, quiet first paint, links from every problem to its fix, save announcement |
| `tests/sales-entry-polish.test.tsx`, `tests/sales-entry-scale.test.ts`, `packages/ui/tests/entry-grid.test.tsx` | 11, 7 and 12 new tests |

### Keyboard-only

The bill can be raised without the mouse from arrival to save. **Focus starts at the customer**,
once, as Tally's voucher screen starts at the party. **Tab going forward skips a line's three
buttons** and lands on the next line's first cell — three extra presses per line is a hundred and
fifty on a fifty-line bill, spent on controls that have their own keys. Going back, `Shift+Tab`
reaches them, so nothing is unreachable. **A blank last line ends the grid**: tabbing or pressing
Enter out of a line nobody typed into no longer adds another blank one, and focus moves on to
what follows the grid. `Alt+Enter` opens a line's detail, the last row action that had no key.
`Ctrl+/` (and a Keys button, for a reader who does not know that key) lists every key.

### Empty and invalid states

**The first paint says nothing is wrong.** A form that opens with "Choose the customer" in red
and two items "to fix" in the rail is scolding someone for not having started; problems are
shown from the first change onwards, and Save is disabled throughout. The empty grid carries a
one-line hint on how entry works, which goes as soon as a line exists.

**Every problem names where it is fixed** — "Line 3", "Customer", "Payment", "Discounts and
charges" — and the name is a button that goes there: it focuses the line or the field, or opens
the drawer. The "Before saving" sentence beside the disabled Save carries the same button.
Routing looks a component's key up on the draft rather than parsing its spelling.

Found and fixed on the way:

- **Credit days never showed its own error** — the draft reported it and the field did not.
- **The discount cell's `%` was only in its accessible name.** `10` percent and `10` rupees
  looked identical; a column can now show its unit, and the discount column does.
- **The rate's provenance chip from S4 was derived and tested but never rendered.** The rate cell
  now shows List / Tier / Last quietly and Override as a warning badge.
- **Labels were lower-cased whole into sentences**, giving "Enter the utr." and "Receive ₹X by
  upi". `inSentence` keeps acronyms; one S6 test changed with it, deliberately.
- A reward line's note now states the arithmetic — "10 charged + 1 free — reason".
- The review dialog formatted half-typed tender text as an amount; it now shows an em dash, and
  marks a cheque as to clear.
- The party field's width was an inline style; it is a class, per the centralised-CSS rule.

### Roles and announcements

A save is announced through a `role="status"` region that is empty until the current revision
is saved, so each save is a fresh announcement. The shortcut list is a description list, so a
screen reader reads each key with what it does. The grid stays a plain table with named cells
(S3), and no new role was claimed that the page does not implement.

### Contrast

Fourteen pairings the entry surface puts on screen were not measured: the required mark on the
grid's header tile, row notes at rest and under the pointer, the row-state edges, the change
edge, text on a hovered row, and the focused cell's placeholder and inset ring. All are now in
`contrast.test.ts` across light, dark and ledger. **One failed**: ledger `ink-faint` on a hovered
row measured 4.43:1. The token was lifted to `#70685a` (4.63:1), which only ever increases its
contrast elsewhere and stays lighter than `ink-soft`.

### 200 lines

Measured before changing anything: the reduce–validate–preview pass costs about 2 ms per key on
200 lines, but re-rendering the grid cost 400–1,200 ms in jsdom, because every key repainted
some 2,400 controls. Rows are now memoised on a **signature** — what each column returns for the
row — rather than on the column objects, which a caller whose derived cells read a live preview
must rebuild every render. Callbacks are held in refs so a row is never handed a stale one. A
custom cell that renders from anything beyond its row, value, problem, read-only state and unit
declares it in `renderKey`; that is the contract the memo needs. The per-cell problem and
preview lookups became maps. Tests count repaints rather than time them — one row repaints when
one row changes — and the pure pass has a 16 ms budget on 200 lines that it clears by a wide
margin.

## What is left for wiring

The page is complete as an interface and still saves nothing. Wiring needs the effective-policy
endpoint (open question 2), the vouchers draft write path at `onSave`, the item and customer
lookups behind the two loaders, the advance projection behind `loadAdvances`, and the jurisdiction
adapter's resolved tax rate in place of the fixtures. Issue stays absent until the statutory
numbering profile is released (open question 1).

## Review after S7, and the fixes

An independent review of the whole page (every file above, read rather than diffed) reported
fourteen findings. Each was checked against the code; all fourteen were real and are fixed, each
with a regression test in `tests/sales-entry-review-fixes.test.ts`,
`tests/sales-entry-polish.test.tsx`, `tests/sales-entry-payment.test.tsx` or
`packages/ui/tests/entry-grid.test.tsx`.

| # | Finding | Fix |
|---|---|---|
| 1 | Switching to Accounts repriced item lines as one unit each, silently | Lines carry `subjectKind`; a subject that does not fit the mode is an error and is left out of the totals |
| 2 | A cell could show `2450.12345` while the draft held 2,450 — and Save handed over 2,450 | `useNumericInput` reports text that settling cannot rescue (`onUnstorable`); the grid and the drawers pass it up; the page treats it as a problem that blocks Save |
| 3 | A short supply (actual 9, billed 10) demanded a reason the drawer never offered; `10` vs `10.0` demanded one too | The reason picker follows any difference, compared as decimals, with a short-supply notice |
| 4 | Choosing an item with Enter also moved down a row | The grid ignores a key the cell's own control already handled |
| 5 | Tax-inclusive 100 at 18% billed 100.01 | An undiscounted inclusive line's tax is what is left of the inclusive figure; the halves add back exactly |
| 6 | Amount discounts and advances above their limits were capped without a word, while the draft carried the larger figure | Each cap is a stated problem (`previewProblems`) |
| 7 | Re-choosing an item kept the previous one's list price, badge, HSN, tax rate and unit | A subject change clears what the previous subject supplied; a rate the reader typed stays |
| 8 | Save released the leave guard though nothing was stored; in-app links were never guarded | The guard holds until an `onSaveDraft` write path exists and has taken the revision; the page says "checked, not stored"; in-app links ask first |
| 9 | Enter and Ctrl+Enter added a line and left the caret in the old one | Focus follows the new line |
| 10 | Tab died on a read-only grid | A skip happens only if the target took focus |
| 11 | A card number survived by switching the tender's mode, or with dots between the digits | Changing mode clears the reference; every non-digit is ignored in the check |
| 12 | Float free quantity (`0.10000000000000009`); "the total is the same either way" before a customer; an inclusive line left out of a total still shown as known | Exact arithmetic; the sentence corrected; the total unknown |
| 13 | Reason problems linked to the row, not the drawer; Escape kept unstorable text; a selected-line discount on an emptied line passed | A `detail` target opens the line's drawer; Escape reverts a figure; an emptied line is not a target |
| 14 | Every item lookup was announced as "Item"; cell errors were not linked; the rail's payment card label was ignored; every Remove button had the same name | The lookup takes the cell's name; cells point `aria-describedby` at their row note; the card is a labelled group; Remove buttons name what they remove |

Also from the review: `Ctrl+Backspace` is "delete the previous word" in every text box, so it now
removes a line only from the start of a cell, where the native action has nothing to do; and
the document bar is read-only for a reader who may not raise a bill, like the grid already was.

**Not changed, with the reason.** The lookup's `scopeKey` stays the mode, which is harmless while
Mixed mode uses the item source; it needs revisiting when Mixed has its own lookup. Removing a
line has no undo yet; the narrower `Ctrl+Backspace` makes an accidental removal much less likely,
and an undo belongs with the draft write path, which will hold revisions.


## Second review: the page in a browser, and the fixes

The first review read code. This one also rendered the real components in headless Chrome, with
the real stylesheets, at 900, 1440 and 1920 pixels wide and in all three themes, and drove a bill
by keyboard. A second independent code review ran alongside. jsdom applies no layout, so most of
what the browser showed could never have failed a unit test; each fix still has one where the
behaviour is testable (`tests/sales-entry-ui-review.test.tsx`, `packages/ui/tests/numeric-field.test.tsx`,
`entry-grid.test.tsx`, `editor-controls.test.tsx`), and the layout rules are asserted against
`entry.css` where they are load-bearing.

| # | Found | Fix |
|---|---|---|
| 1 | The mode choice and the "rates include tax" switch rendered as bare browser buttons and an empty pill: their styles lived in `designer.css`, which only the editor routes load | The segmented choice's rules moved to a new shared `controls.css` (root layout); `SegmentedControl` gained `showLabel` for forms; the switch became a labelled `Checkbox` |
| 2 | Once the grid overflowed, every column shrank below its stated width: a 2,450 rate showed as `2`, `bag` as `ba` | The table is `max-content` wide, never narrower than its scroller |
| 3 | Beside the rail, a laptop saw two scrolling columns at a time, and scrolling across lost the item and the amount | Item and Amount are pinned (`EntryColumn.pin`); the rail goes under the lines below 90rem of *content* width (a container query) and the action bar carries the running total |
| 4 | Header fields did not line up (a hint lifted its label); Credit days took a row to itself | Fields align to the top; narrow fields are narrower; the statutory note left the sticky band |
| 5 | The sticky bar covered Subtotal, Discounts and Taxable value; the rail could run off the bottom | The rail sticks below the measured bar and scrolls within itself; on a short window the bar scrolls away |
| 6 | Paragraph and list margins made the rail loose and indented the problem list; a zero discount read "− 0.00"; the row number sat on the state edge | Margins reset, a problem list class, unsigned zero, frame-column padding that wins |
| 7 | Drawer content had no spacing between a choice, a heading and a button; four stock options overlapped | Drawer and dialog bodies are one stack; segments wrap their text |
| 8 | **A comma-decimal company corrupted figures:** the focused box showed `12.5`, and the next key re-read the point as a group separator — `12,56` stored 1256; blur did the same to stored values | The focused box shows the company's decimal separator, and only typed text is re-read |
| 9 | A reader without create access could edit a line through its detail drawer | The drawer opens read-only; the editing panels refuse to open for them |
| 10 | Closing a drawer holding `12..5` dropped the problem and kept 12 | The drawer stays open, says why, and focuses the field |
| 11 | The first line's key came from a module counter, so the server and client rendered different row keys | The first line's key is fixed |
| 12 | Default dates were the UTC day — yesterday before 05:30 in India | `businessToday(config.timezone)` |
| 13 | A pasted `-50` became a 50 discount | The sign is kept and refused with its own message |
| 14 | Smaller: a clear button as an extra tab stop in each item cell; Ctrl+/ stacked a dialog on a drawer; "Try again" with nothing to press; `5.00%`; raw figures in sentences; the keycap read aloud in "Add line"; going to a line landed on the item rather than the problem's cell | Each fixed |

**Changed behaviour.** `canonicalise` no longer drops a minus sign where negatives are not
allowed (its test changed to say so). The rail sits under the lines on most laptops now; above
90rem of content it stays beside them. The tax-inclusive control is a checkbox.

**Not changed.** Price levels are still a fixed list in the header; they come from the policy
once the effective-policy endpoint exists (open question 2). Figures inside draft and preview
*problem messages* are still unformatted strings; formatting them means carrying the raw figures
on the problem and formatting at render, which belongs with the wiring pass.

## Phase S8 — third review: checklist

From the third review (browser pass plus an independent code review, 2026-10-29). Ticked as each
lands with its test.

**A. Money and rules**
- [x] A1 Zero consideration by rounding or a 100% / full-value discount is refused like a zero rate
- [x] A2 Rate override: refused when the policy forbids it; approval warning above `approvalAbove`
- [x] A3 Discount approval measured on the effective discount, every kind and scope
- [x] A4 Rate equal to the list price compared as a decimal (`2450.00` is not an override)
- [x] A5 Preview dialog shows every totals row the rail shows (one source)
- [x] A6 Computed line amounts and totals beyond `DECIMAL(19,4)` are refused
- [x] A7 Settlement compares with exact decimals; an amount that rounds to zero is refused
- [x] A8 The quantity reason must match the direction of the difference

**B. Mixed mode, screen and keyboard**
- [x] B1 Mixed mode: one lookup over items and accounts; an account line prices as one, hides its quantities; switching keeps account lines valid
- [x] B2 Pinned columns off on a narrow grid (phone)
- [x] B3 Action-bar sentence never pushes the buttons onto two rows
- [x] B4 The advances problem shows in the Payment drawer
- [x] B5 Segmented choice: arrow keys move focus with the selection
- [x] B6 Goods lines cannot pick "No stock effect"
- [x] B7 Amount discounts show ₹; switching kind clears the figure
- [x] B8 Alt+↑/↓ keeps focus on the moved line

**C. Gaps**
- [x] C1 Bill-to, ship-to and supply date rendered from policy; place of supply decides the tax split
- [x] C2 Changing price level re-prices list-priced lines; inclusive and mode switches with lines ask first
- [x] C3 Free item: a purpose field, so a declared free line can be saved
- [x] C4 Apply advance prefills the smaller of available and outstanding
- [x] C5 Cheque date required, post-dated and stale cheques warned, bank name captured
- [x] C6 Preview dialog lists the lines and flags overrides, free and short lines
- [x] C7 Keyboard: Ctrl+D focuses the copy; Ctrl+Shift+Enter inserts below; `%`/`₹` typed in a discount cell switch its kind; the lookup opens on typing, not on focus
- [x] C8 Credit limit and overdue warning from the customer master
- [x] C9 Tax-inclusive with an amount discount: decided — discounts come off the inclusive price (S8-1), and the UI states it

## Phase S8 — delivered

All twenty-five items above landed, each with a test: `tests/sales-entry-third-review.test.ts`
(the rules, no DOM), `tests/sales-entry-third-review-page.test.tsx` (the page on the route's own
fixtures), and in `@janso/ui` `entry-grid.test.tsx`, `editor-controls.test.tsx` and
`search-select-focus.test.tsx`. The browser pass was repeated at 375 and 1440 pixels.

| Change | Where |
|---|---|
| Zero consideration by rounding or full discount; storage overflow; amounts that round to nothing; discount approval on the effective share; credit and overdue warnings; the inclusive-discount rule stated | `sales-entry-preview.ts` |
| Override refused when forbidden, gated by the policy's grant, approval warning past the threshold; `2450.00` equals `2450`; reasons typed by direction; goods cannot be "no stock effect"; cheque date required, post-dated and stale warned; exact advance comparison; free purpose | `sales-entry-draft.ts`, `sales-entry-policy.ts` (`DifferenceReason`, `freePurposes`) |
| Mixed mode: one lookup over both masters; the resolver names the kind; account lines price as one and their quantity cells are read-only | `SalesEntryRoute.tsx`, `sales-entry-columns.tsx`, `isAccountLine` |
| Bill-to, ship-to and supply date under the bar; the ship-to state is the place of supply | `SalesEntryHeader.tsx`, draft `shipToState` |
| Price level re-prices list-priced lines; mode and tax-inclusive switches with lines ask first | `SalesEntryPage.tsx` (`ConfirmDialog`) |
| Preview lists the lines with override / free / short flags and every rail row (`totalsLines`) | `SalesReviewDialog.tsx` |
| Advances error in the Payment drawer; Apply prefills; cheque bank | `SalesSettlementDrawer.tsx` |
| Ctrl+D lands in the copy; Ctrl+Shift+Enter inserts below; Alt+↑/↓ keeps focus; `%`/`₹` in a discount cell switch its kind; pinning off below 40rem of grid | `EntryGrid.tsx` (`onInsertRow`, `unitKeys`), `entry.css` |
| Segmented choice moves focus with the selection; a lookup can stay closed on focus | `EditorControls.tsx`, `SearchSelect.tsx` (`openOnFocus`) |
| Action-bar buttons as one group that wraps inside itself on a phone | `entry.css` |

**Changed behaviour.** A percentage bill discount still warns as typed; an amount is measured on
what it comes to. Overriding a list price now needs the grant the policy names. Switching a
discount's kind in a drawer clears its figure; typing `%` or `₹` in the cell keeps it.

**Decisions taken in S8** are recorded as open questions 5 and 6 above (now decided).

**Still open.** Figures in the draft's own messages ("Only 5000 of …", "The list price is …")
are not yet run through the company formatter; the preview's are. The price-level list in the
header is fixed until the effective-policy endpoint exists.

## Fourth review, after S8, and the fixes

An independent review of the S8 batch confirmed most of it and found nine defects plus five
smaller ones. All are fixed, each with a regression test ("the fourth review" suites in
`tests/sales-entry-third-review*.ts(x)`, `entry-grid.test.tsx`, `editor-controls.test.tsx`).

| # | Found | Fix |
|---|---|---|
| 1 | A grid move or duplicate that changed nothing (Alt+↑ on line 1, a refused copy) left a focus jump armed, which fired on the next edit anywhere | A chase remembers the row keys it was armed with and is dropped if they did not change; a move off either end is not attempted |
| 2 | A bill too large to store passed when a tax rate was unresolved — only the amount, then unknown, was checked | The base, the taxable value and the subtotal are checked too |
| 3 | The credit-limit warning fired on a bill paid in full; the overdue warning waited for every line to be complete | Only a bill that leaves something owing can cross a limit; overdue is said as soon as the customer is chosen |
| 4 | On a mixed bill, re-choosing an account over an item kept its quantities, still flagged as free units | Choosing an account clears quantity, unit and reason; the reward state and preview flags ignore account lines |
| 5 | One full bill discount produced three problems, one on a line's empty discount cell, asking for a purpose the policy did not allow | Said once, on the discount that did it, worded by the policy; no approval warning on a discount already over its pool; no override or approval stacked on a zero rate |
| 6 | With no ship-to, the place of supply ignored the bill-to address | Goods: ship-to, then bill-to, then the customer. A services-only bill: bill-to, then the customer |
| 7 | A price-level change re-priced tier and last-sold rates, kept "Override" on a rate that now equals the list, and left a missing price marked "List" | Only list-priced lines re-price; an override equal to the new list stops being one; a missing price drops the "List" mark |
| 8 | The mode choice's arrow key moved focus before the confirm dialog accepted the change | Focus moves once the value actually changes |
| 9 | The selected segment's shadow was invalid CSS (a shadow inside a shadow), so it had no lift in any theme | `box-shadow: var(--janso-shadow-card)` |

Smaller: a mixed bill's empty line asks for "an item or an account"; a company that does not
record quantity differences is told once, not asked for a reason as well; a refused override
raises no approval warning; a free-item purpose is dropped once the line has a price; dates and
figures in the draft's own messages use the company's formatters (`ProblemOptions.formatMoney`,
`formatDate`), which closes the S8 "still open" item.

## Wiring plan — W1 to W7 (agreed 2026-10-29; W1–W6 done, W7 partly — see below)

The page is complete against fixtures. This plan connects it to the services that exist today,
end to end as far as the platform allows. **What the platform allows decides the end:** a Sales
draft can be created, edited, calculated by the service, accepted, submitted and approved; it
cannot be issued (statutory profile, D05 — open question 1) and, today, **cannot be calculated
for goods** (see blocker B1).

### What exists and what each piece of the page binds to

| Page piece | Service call (all under `/v1/companies/{company_id}`) | Notes |
|---|---|---|
| Policy | Vouchers `GET /voucher-types?kind=SALES`, `/voucher-classes`, `/voucher-types/{id}/effective-configuration`, `/voucher-types/{id}/field-set` | `policy.invoice` carries tender modes, discount scopes, credit, split, advance, rounding, account allowlists, tax profiles. Per-control allowed/required/default/editable is *planned only* (Sales configuration §3) — an adapter fills the rest from field-set read-only flags |
| Customer | Accounting `GET /parties?role=CUSTOMER&q`, `/parties/{id}`, `/accounts?party_id&kind=PARTY` | The invoice needs the party **account** and its version, not only the party |
| Bill-to / ship-to | Accounting `/party-addresses?party_id` (state code) | **Not on the voucher payload** — blocker B2 |
| Credit | Accounting `POST /credit/check`, `GET /subledger/ageing` | Replaces the fixture's limit/outstanding/overdue |
| Items | Catalog `GET /items?q&sellable`, `/units`, `POST /prices/resolve` (party, price level), `POST /tax-configurations/resolve`, `/tax-reference/hsn-sac` | A price is a resolution with a status (`RESOLVED`, `MISSING`, `NEEDS_TAX_CONTEXT`) |
| Price levels | Catalog `/price-levels`, `/customer-pricing/effective` | Replaces the hardcoded Retail/Wholesale list |
| Accounts mode | Accounting `/accounts?kind=GENERAL`, narrowed by the policy's supply-account allowlist | |
| Advances | Accounting `/open-items?party_id&direction=CREDIT` + `/open-items/{id}/balance` | Sent as `allocations[]` |
| Save | Vouchers `POST /vouchers` (create, `Idempotency-Key`), `PUT /vouchers/{id}` (`expected_version`, `reason`) | Each edit is a new revision |
| Calculate | Vouchers `POST /vouchers/{id}/invoice-preview` → `InvoiceCalculationDetail` | Server-side tax; replaces the provisional figures once available |
| Accept / submit | `POST /vouchers/{id}/invoice-acceptance` (`calculation_hash`), `/submit`, `/approve` | Issue stays absent |

### Blockers and decisions — answers needed before W5

- **B1 Goods GST is not calculated by the service.** Accounting's invoice tax profiles are
  `INDIA_DOMESTIC_SERVICE`, `…_RCM` and `UNTAXED_ACCOUNT`; there is no goods profile. An
  items-mode bill of goods can be **saved as a draft** but not previewed, accepted or submitted.
  *Recommended:* wire everything now; goods drafts save with the page's provisional preview and
  say why the service cannot calculate them yet; services and accounts lines go all the way to
  acceptance. A goods tax profile is a separate Accounting backend plan (migration, recipes,
  tests) and is not started by this one.
- **B2 Bill-to / ship-to have no field on `VoucherInput`.** Only a `CONSIGNEE` party role
  exists, and the place of supply travels as `invoice.tax.place_of_supply`. *Recommended:* send
  the place of supply (derived as the page does now) and the consignee role; keep the address
  pickers as a UI choice that feeds them. Storing the chosen address on the voucher is a vouchers
  schema change (model, migration, schema, client) proposed separately.
- **B3 Line fields with no home on the payload** — warehouse, batch, expiry, stock intent,
  income-ledger override, note. `ItemInput` carries item, unit and the two quantities only.
  *Recommended:* render each only when the field-set marks it writable (it will not, today), so
  nothing is typed that the save would drop.
- **B4 A typed discount needs `source_evidence`.** The contract requires it on every component.
  *Recommended:* `manual:{actor}:{reason or "entered on the bill"}`, and the reason field the
  page already has for overrides; confirm with the calculation owner.

### Phases (each ends green, suites run and reported)

- [x] **W1 Proxy allowlist and data layer.** A Sales entry request policy behind the existing BFF
  proxy (`service-proxy.ts`), deny by default, allowing exactly the calls above; fixes the
  existing gap that makes `VoucherWorkflow`'s Preview and Accept fail (`invoice-preview`,
  `invoice-acceptance`, `field-set` are not allowlisted today). Tests: every allowed path, and
  near-misses refused.
- [x] **W2 Policy adapter.** Load the Sales type, class and effective configuration; map them to
  `SalesEntryPolicy` (the page does not change shape); loading, empty ("no Sales type is set
  up"), 401/403/422/500 states. The fixture stays as the test double.
- [x] **W3 Lookups.** Customers (+ party account, addresses, credit), items (+ units, price
  resolution per line and price level, tax classification), income accounts, advances. The
  resolver becomes async; a `MISSING` price leaves the rate blank and says so.
- [x] **W4 Save draft.** `toVoucherInput(draft, policy, refs)` — a pure mapper with its own
  tests against the generated types — then create, and edit with `expected_version`; 409
  "changed elsewhere" reload; 422 field paths mapped back onto cells and fields; the leave guard
  releases on the stored revision; retry reuses the idempotency key.
- [x] **W5 Service calculation.** Calculate after save; the rail shows the service's figures,
  marked as the service's, and states any difference from the provisional ones; tax evidence
  shown. Goods lines follow B1.
- [x] **W6 Accept and submit.** Accept the calculation hash, then submit; approve where the
  reader holds it; history. Issue stays absent with its reason.
- [ ] **W7 End to end.** A Playwright run against the local stack (draft → calculate → accept →
  submit for a services bill; draft only for goods), plus the `/security-review` and §5/§6 walk
  — tenant and company scope on every call, idempotency, no card data, audit on every write
  (service side).

### Wiring — delivered

| Piece | What it does |
|---|---|
| `app/api/sales-entry/route.ts`, `lib/sales-entry-request-policy.ts` | The page's own proxy route and allowlist, deny by default: identity (company, tax registrations), vouchers (types, configuration, draft create/edit/read, invoice-preview, invoice-acceptance, submit, approve), accounting (parties, accounts, addresses and their uses, credit check, ageing, open items and balances), catalog (items, unit bindings and revisions, price levels, price resolution, tax classification). Issue and post are not on it |
| `lib/voucher-request-policy.ts` | Fixed: `invoice-preview`, `invoice-acceptance` and `vouchers/{id}/field-set` were refused, so `VoucherWorkflow`'s Preview and Accept never worked |
| `lib/sales-entry-connection.ts` | `InvoicePolicy` → `SalesEntryPolicy`: modes from supply kinds, discount scopes and manual-discount switch, charges, free lines, tender modes (NEFT/RTGS/IMPS read as bank transfer), credit, split, advances, rounding, price basis. What the service does not decide (price-level list fallback, override rule and threshold, difference reasons, free purposes) comes from the page's defaults, named there |
| `lib/sales-entry-lookups.ts` | Company state and GST registration; Sales types; book accounts by system key (`SALES_REVENUE`, `SERVICE_REVENUE`, `CASH_MAIN`, the first bank, `ROUNDING_GAIN`/`LOSS`); customers with version, receivable, registered state and credit (`/credit/check` at zero); addresses; items and accounts by mode; an item's unit binding and revision, price (`prices/resolve`, customer and level) and classification (SAC = service); price levels; open advances with balances |
| `lib/sales-entry-wire.ts` | The draft as `VoucherInput` + `invoice`: item detail and supplies sharing one identity, staged discount components with `dependencies` and the inclusive amount basis, charges, tenders by receiving account, advances as allocations, rounding to gain or loss, the service tax context (registration, place of supply, completion date) or untaxed |
| `components/SalesEntryConnected.tsx` | Loads, renders the page, saves (POST then PUT with `expected_version`; one idempotency key per request, reused on a 5xx retry), calculates, accepts the calculation hash, submits; the service's figures in the rail beside the provisional ones |
| `SalesEntryPage` | Resolvers may answer later (`resolveLine` / `resolveCustomer` apply only if the subject or customer is unchanged); a save is "saved" only once stored, and a refusal is said beside Save; slots for the rail, actions and status |

**Decisions applied.** B1: goods lines refuse to save, saying why — sending goods under the
service profile would claim a tax nobody computed. B2: the place of supply goes on the tax
context; the addresses themselves stay on the page. B3: unchanged (the drawer fields have no
payload home). B4: typed discounts carry `source_evidence: "Entered on the bill"`; a charge
carries its printed label. A short supply (fewer leave than billed) refuses to save: the
contract accepts a difference only as a paid bundle (more leave than billed), saved as a draft.

**Verified.** The mapper's output for a mixed services + accounts bill with line and bill
discounts, cash and UPI tenders, an advance and rounding was validated against the vouchers
service's own `VoucherInput` and `validate_invoice` (draft stage). That check found one real
defect — an item supply must reuse its item line's identity — now fixed and pinned by a test. The read
bodies were checked the same way against Catalog's price and tax `ResolveInput`, Accounting's
`CreditCheck` and list queries; that found the credit check refuses a zero amount (it now asks
for the smallest, 0.0001, and reads exposure, limit and overdue).

**W7, not done:** a browser run against the live stack. The local services are not running in
this workspace and starting them needs credentials this session does not hold. Run it with the
stack up: services bill draft → Calculate → Accept → Submit; goods bill refused at save.
