# Mandatory party ledger: plan and decisions

Decided 2026-11-02 (owner request, with answers to three design questions). Supersedes the
"Optional payable/receivable ledger" section of [party-creation-wizard](party-creation-wizard.md).

## Rule (PL-INV)

Every party role has exactly one ACTIVE party account for it, created in the same transaction
that activates the role. Nothing creates a party, or activates a role, without it.

| Party role | Account role | Default group |
|---|---|---|
| CUSTOMER | CUSTOMER | Sundry Debtors |
| SUPPLIER | SUPPLIER | Sundry Creditors |
| BROKER | OTHER | Sundry Creditors |
| OTHER | OTHER | Sundry Creditors |

The account table has no BROKER role, so brokers and "other" parties share the `OTHER` account
role; one party never has two accounts for the same account role. Any role's group may be
overridden with `ledger.group_id` (it must sit under a head the account role can use).

## Decisions

- **PL-D01** Plain identity-only `POST /parties` is removed. A party is created only by
  `POST /parties/create-with-details` or the ready customer/supplier import. Edit, activate
  and deactivate stay. The plain `party` import resource can update, activate and deactivate
  but no longer create.
- **PL-D02** `role` is required at creation, and the ledger is always created. `ledger` stays
  in the body only as *choices* (code, name, group, currency); leaving it out takes defaults.
- **PL-D03** Activating a party role creates its account when none exists (`ledger` choices
  optional on the activation body). A second DRAFT/ACTIVE account for the same party and
  account role is refused, whatever route creates it.
- **PL-D04** The ready import always creates the account; an opening balance is then staged
  against it (it no longer creates the account itself).
- **PL-D05** Existing parties with no account are repaired by an idempotent, audited command
  (`POST /parties/ledger-repair`); parties that already have more than one account for a role
  are reported, never merged automatically.
- **PL-D06** A voucher picks the party's account itself. The Purchase page shows no payable
  control; a supplier that has none, or more than one, cannot be chosen and says why.
  Sales and other party vouchers follow the same rule where they ask for an account.

## Phases

1. **Accounting rule** — schemas, ledger planning, aggregate creation, role activation, import,
   account uniqueness, route removal, repair command; OpenAPI, field/master contracts and the
   TS client regenerated. Backend tests moved off the plain create and new ones added.
2. **Console** — creation wizard, Purchase quick-create, Purchase page (no account control),
   other voucher screens that ask for a party account, proxy policies, UI tests.
3. **Docs and review** — wizard doc, master contract, Purchase blueprint, decision logs, review
   walk of CLAUDE.md §5/§6.

## Open

- A run against live data: existing parties without an account stay unusable in vouchers until
  the repair has been run for the company.

## Delivered detail (2026-11-02)

- **PL-D07** Accounting's account list accepts `role` (an account's party role: CUSTOMER, SUPPLIER
  or OTHER; BROKER means OTHER) and its list items carry `party_role`. A voucher takes the
  customer's receivable (`role=CUSTOMER`) or the supplier's payable (`role=SUPPLIER`) in one read,
  and never "the first party account", which for a party that is both would be the wrong
  ledger. The Sales bill and the Purchase bill both do this and accept only exactly one.
- **Role activation** (`POST /party-roles/{id}/activate`, body `expected_version` and optional
  `ledger`) creates the account too. A party taking a further role whose default code is taken
  gets `<party code>-CUST|-SUPP|-OTHR` and the name `<party name> (Customer|Supplier|…)`.
- **Repair** (`POST /v1/companies/{company}/parties/ledger-repair`, `Idempotency-Key` header, body
  `{"limit": 100, "after": null}`; needs account read+manage and party/role read): creates the
  default account for each ACTIVE party role that has none, in role-id order, and answers
  `{created, attention, next_after}`. `attention` lists what it would not do on its own: a role of
  an inactive party, a default code another account already uses, a missing standard group, and
  (first call only) any party holding more than one live account for a role, with the account
  ids. Run it again with `after` set to `next_after` until that is empty; re-running is harmless.
  It never merges or retires accounts: keep one, retire the rest by hand.
- Older data: until the repair has run, a supplier or customer with no account cannot be
  billed, and the bill says so.
- **Retiring a role** now always needs its account retired first (`guard_role_retirement` already
  refused to retire a role while a live account exists for it; since every role has one, that is
  now every role). Retire the account (which Accounting refuses while it has open items or a
  balance), then the role.
- 2026-11-02 (Purchase review): Accounting's invoice calculation, and so acceptance and posting, refuses a
  party account whose party role is not ACTIVE or whose party has more than one live (DRAFT/ACTIVE) ledger for
  that role ("repair it first"), so PL-D06 holds server-side, not only in the Console.
