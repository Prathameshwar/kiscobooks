# Purchase account bill: create a supplier or an expense account without leaving the bill

Requested 2026-11-01. On the Purchase account bill (`/vouchers/new/purchase`):

- **Supplier** gets a small "create" icon; it opens a right-hand drawer to create the supplier (party), and on
  success the new supplier is selected and the bill is filled in (its payable account resolved).
- **Expense / service account** in each bill row gets the same small icon; the drawer creates the expense
  account and selects it in that row.

## Findings that shape the design

1. A supplier is only usable on a bill when it has a **payable account** (a `PARTY` ledger with the supplier
   role). `parties/create-with-details` used to create the party and its role but no ledger (since 2026-11-02 it always creates the ledger too, PL-D02); in the QA company
   `Supplier 1` has none and the screen says "Supplier setup needed". So the drawer must create both, and
   atomically: one command, one idempotency key, one audit trail, no half-created supplier. Backend work:
   an optional `ledger` on `create-with-details` (Accounting owns the rules and the default Sundry Creditors
   group).
2. The bill only accepts an **expense** account: `GENERAL`, posting allowed, not inventory-affected, under an
   account group whose head has `nature = EXPENSE` (`purchaseSource` re-verifies after selection). The drawer
   therefore offers only expense groups.
3. Selection reuses the bill's own paths — `dispatch({type:'supplier'})` and `dispatch({type:'subject'})` —
   which re-read and verify the record before it is accepted, exactly as picking it from the list does.
4. Gating is presentation only (the services authorize): supplier needs `accounting.party.manage` and
   `accounting.account.manage`; the expense account needs `accounting.account.manage`.

## UX (as built, after the 2026-11-01 review)

- Icon: a small outline "+" button **in the control's own row**, after the box (supplier field, each account
  row, and the mobile line editor), named "Create a new supplier" / "Create a new expense account for line N".
  Hidden without the permission or on a read-only bill; disabled while the bill is busy.
- Drawer (right, `md`), compact two-column form: supplier = name (also the legal name), code, country and,
  for India, GST status (Regular / Composition / Unregistered / Add later), state, GSTIN; expense account =
  name, code, group, description. A "Full supplier form" / "Full account form" link opens the real master
  page in a new tab. Dirty close asks first; server field errors sit beside their fields.
- Success: the record is selected through the bill's own verified path, announced in the status line, focus
  moves on (invoice number / the row's amount). Retry after a failure with no answer reuses the same key.

## Phases

- [x] P1 Backend (fork): atomic `ledger` on `create-with-details`, `POST /accounts/create-active`; 35 new tests,
      ruff/mypy clean, OpenAPI + client regenerated (see the backend notes below)
- [x] P2 `@janso/ui`: a `SearchSelect` `action` slot was built, then **removed**: the icon belongs beside the box,
      not in the label row, and the product masters already have the layout for it (`console-reference-create`)
- [x] P3 Console: `lib/purchase-quick-create.ts`, `SupplierQuickCreate`, `ExpenseAccountQuickCreate`, console proxy
      allow-list entry for `POST accounts/create-active`
- [x] P4 Wire into the bill: header icon, grid row icon, mobile line editor, permission gating (`accounting.party.manage`
      + `accounting.account.manage`; expense also `group.read` + `head.read`; GST fields `accounting.tax.manage` + `read`)
- [x] P5 Tests: 147 across five files (lib, drawers, icon placement, connected wiring, proxy allow-list) and two
      rounds of mutation checks on the new logic
- [x] P6 Live check as tenant1 (see Notes)
- [x] P7 Review, docs (design-system, party-creation-wizard), close

## Notes

- **Live findings that tests had hidden.** (1) Accounting refuses a `status` filter on account **heads** (422): heads
  have no lifecycle. (2) A head's *list row* does not carry its `nature`, so my first fixtures were wrong in the
  same way as my code; each head is now read once for its nature. Both only showed against the real service.
  (3) State options are labelled with diacritics ("Mahārāshtra") and valued `IN-MH`; the lookup is the existing one.
- **Live QA data created (tenant1 company):** one supplier `QA Quick Supplier 220153` (Regular, Maharashtra, GSTIN
  `27AAPFU0939F1ZV`) with its payable account, and one expense account `QA Quick Expense 221146` under Indirect
  Expenses. Delete or deactivate them from Suppliers / Accounts if unwanted.
- **Known follow-up, not part of this request:** existing suppliers created before this (e.g. `Supplier 1`) have no
  payable account and still show "Supplier setup needed" on the bill; a "Create payable account" action beside
  that message would fix them. Taxed purchase bills are planned in [purchase-tax-entry-plan.md](purchase-tax-entry-plan.md).
- The full wizard (`/accounting/suppliers/new`) does not send `ledger` yet, so a supplier made there still needs its
  payable account set up separately.

## Quick-create backend notes

Accounting only (`apis/accounting`); no model, migration, seed or permission key changed. Both commands run
the ordinary `mutate_master` create and activate in one transaction and one idempotency key, so validation,
refusals and audit events (one `create`, one `activate` per record) are exactly those of the two-step calls.

**`POST /v1/companies/{company_id}/parties/create-with-details`** — optional `ledger: PartyLedgerInput`
(`code`, `name`, `group_id`, `currency_mode` = `BASE|FIXED|MULTI` default `BASE`, `currency`; all optional,
`extra="forbid"`). The response is still `PartyDetail`; re-read the payable by `party_id`.

- Needs `role` of `CUSTOMER` or `SUPPLIER`; `OTHER`, `BROKER` or no role is 422 `ledger.role`.
- Adds `account` to the resources the command demands (`manage` and `read`): without
  `accounting.account.manage` the whole command is 403 and nothing is created. A request with no `ledger` asks
  nothing new of the caller.
- Created after the role: an ACTIVE `PARTY` account of this party and role, `MANUAL_ALLOWED`. Kind, party,
  role, posting policy and status are server-decided (sending them is 422).
- Defaults: code = party code, name = party name. Group = the company's active system group `group.DEBTORS`
  (customer) or `group.CREDITORS` (supplier) — `system_key` is unique per company, so there is never more than
  one; missing or inactive is 422 `ledger.group_id` and nothing is guessed. An explicit `group_id` must be this
  company's, active and under a compatible head (customer asset, supplier liability), else 422
  `ledger.group_id` (a foreign company's id is "not found", not 404).
- Other field errors are keyed `ledger.<field>`: `ledger.code` (code already used by an account),
  `ledger.currency` (FIXED needs one; only FIXED takes one). A foreign or MULTI currency still follows the
  account rules (409 without the `multi_currency` feature or an allowed currency).
- Any failure — including a ledger code clash — rolls back the party, role, ledger, audit rows and the
  idempotency claim. Replay with the same key returns the same party and creates no second account; a changed
  body under the same key is 422.

**`POST /v1/companies/{company_id}/accounts/create-active`** — body `AccountCreate` (unchanged), 201
`AccountDetail` of the now-ACTIVE account (`row_version` 2), `Location: ../accounts/{id}`. Demands `manage` and
`read` on the account resource together. Refusals are those of create-then-activate: foreign group 404, group
not active 409 (the creation is rolled back), incompatible kind/head 422, code clash, multicurrency gating.
Replay returns the same account (`Idempotency-Replayed: true`); operation `accounting.account.create_active`
has its own idempotency namespace.
