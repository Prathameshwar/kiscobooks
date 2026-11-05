# Opening balances in the customer and supplier import

Delivered 2026-10-31. A ready customer or supplier row can carry an optional opening balance:
debit or credit (`DR`/`CR`) or to-receive or to-pay (`TO_RECEIVE`/`TO_PAY`), with an amount,
currency and, optionally, one dated bill. The import checks it, creates the party's ledger
account and **holds** the balance for the company opening. It never posts money.

Related: [party import delivery](party-import-ui-delivery.md), [account and party opening
APIs](account-party-opening-api.md), [shared import framework](shared-import-framework.md).

## 1. Why the balance is held, not posted

The company opening is one declaration at the books-begin date. It must balance as a whole
([account-party-opening-api](account-party-opening-api.md)). A file of suppliers can only
supply one side, so it cannot be saved as a declaration by itself. Imports do not invent
offsetting entries. The import therefore keeps each
balance as its own row. The opening worksheet lists the held rows and copies the ones the person
chooses into the declaration they are building, where the existing preview, balancing, posting
and finalization still apply. Since 2026-11-04, the worksheet can include a disclosed,
explicitly reviewed equity offset against its configured opening-balance offset account.
This does not change the import's held-balance lifecycle.

## 2. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | The import posts nothing and saves no declaration. It stores a held line. | Bulk imports require a separately reviewed balanced declaration. Interactive creation now completes posting under the 2026-11-04 [creation decision](master-opening-immediate-posting.md). |
| D2 | Only the ready `supplier` and `customer` resources carry opening columns. Plain `party` rows (update only since 2026-11-02) and related-record rows do not. | A balance needs an active role and a ledger account; only the ready resources create both. |
| D3 | `DR`/`TO_RECEIVE` is a debit balance, `CR`/`TO_PAY` a credit balance, whatever the role. A type is required with the amount. | A supplier we overpaid is TO_RECEIVE and a customer who paid in advance is TO_PAY. A default could silently flip a balance. |
| D4 | Every ready row creates and activates the party's ledger account in the standard Sundry Debtors or Sundry Creditors group; its code is the party code unless `opening_account_code` is set, and a foreign balance gives it a fixed currency. A row with an opening amount also holds the balance against that account; a row without one creates the account and holds nothing (decision 2026-11-02, PL-D04: a party is never without its account). | A party always has its account, so a balance never needs one created for it, and no party exists without one. |
| D5 | One document per held line: a dated bill (reference, date, due date) or `ON_ACCOUNT` with dates unknown. | A party line must reconcile to its documents. More bills per party belong in the worksheet or the account-ID opening import. |
| D6 | A foreign balance needs its rate and historical carrying value. Company currency uses rate 1 and an equal base amount. The carrying value is never recomputed from the rate. | Matches the opening rules for foreign bills. |
| D7 | Allowed only while a declaration can still take it: no finalized opening, no earlier activity, no closed or locked books, accounting and financial setup done. An unfinished worksheet declaration with nothing posted is fine, and a books-begin period that is not yet open (or soft-closed) is tolerated. A legacy-format or already-posted batch is not resumable, so it refuses. | Anything else means no declaration could take the balance, and the held line could only be withdrawn. |
| D8 | The actor needs `accounting.finance.manage` and capture write authority on the journal-line and open-item fields, as well as import rights. | Capturing a financial value is not an import right. The worksheet rechecks at save. |
| D9 | A held line can be withdrawn, with a recorded reason, until it is in the declaration. Rows are immutable and never deleted. The opening preview and save also refuse any declaration that still carries a withdrawn line. | Lets a wrong balance be dropped without touching posted evidence, and stops a stale worksheet from reviving it. |

## 3. Columns

All optional. Leave every `opening_*` column empty for no balance. Money is exact text.

| Column | Meaning |
|---|---|
| `opening_balance_type` | `DR`, `CR`, `TO_RECEIVE` or `TO_PAY`. Required with the amount. |
| `opening_amount` | Outstanding amount, positive, up to four decimals. Giving any other opening column requires it. |
| `opening_currency` | Three-letter code. Empty means the company currency. |
| `opening_exchange_rate` | Foreign balance only, up to eight decimals. |
| `opening_base_amount` | Foreign balance only: historical carrying value in company currency. |
| `opening_account_code` | Code of the new ledger account. Defaults to the party code. |
| `opening_bill_reference`, `opening_bill_date`, `opening_bill_due_date` | Together, one dated bill. Empty means on account. |

The template is the existing `ReadyPartyCreate` schema, so CSV, TSV and XLSX templates list the
columns with their instructions. A customer bill is named `INVOICE` for a debit and a supplier
bill `BILL` for a credit; the opposite direction stays an unnamed dated document because the
file cannot say whether it is a credit note or an advance.

## 4. Validation

Errors are reported against the column in the import result file, and the whole row (party,
role, account, held line) is rolled back with it.

| Rule | Column in the error |
|---|---|
| Any opening column (including only the ledger account code) without an amount; an amount without a type | `opening_amount`, `opening_balance_type` |
| Not exactly `DR`, `CR`, `TO_RECEIVE`, `TO_PAY`; amount not positive or over four decimals; bad currency code | the column (type check) |
| Company-currency balance with a rate other than 1 or a different base amount | `opening_exchange_rate`, `opening_base_amount` |
| Foreign balance without rate or carrying value | `opening_exchange_rate`, `opening_base_amount` |
| Foreign currency without the multicurrency feature or not enabled for the company | `opening_currency` |
| Bill reference, date and due date not given together; reference not printable | `opening_bill_reference` |
| Bill date on or after the opening date; due date before the bill date | `opening_bill_date`, `opening_bill_due_date` |
| Ledger account code already in use | `opening_account_code` |
| Standard debtors/creditors group missing or inactive | `opening_amount` |
| Opening finalized or earlier activity present or setup missing | `opening_amount` |
| No `accounting.finance.manage`, or capture write denied on a field | permission denied |

## 5. What the import does

For a row with an opening amount, inside the row's aggregate transaction: create and activate the
party and role (unchanged), check the readiness blockers, create and activate the party account,
check that the worksheet could capture the line for this actor (the same field authority as a
declaration save), then insert the held line and its audit event. A dry run does all of this and
rolls back, so validation leaves no party, account or held line. A replay of a commit repeats
nothing.

## 6. Storage

Accounting migration 0226 adds `party_opening_balance` (one `CREATE TABLE`, tenant and company
scoped, foreign keys to `party` and `account`). Columns: party, role, account, source key,
`status` (`PENDING` or `WITHDRAWN`), side, currency, amount, exchange rate, base amount and the
one document (kind, reference, dates). `source_key` (`pob-` plus the party id) is also the
declaration entry's source key, so the worksheet knows a line is already included without a second
status. The row is immutable apart from its status and is never deleted; downgrade refuses while
rows exist.

## 7. API and audit

| Route | Purpose |
|---|---|
| `GET /v1/companies/{company}/opening-batches/party-balances` | Cursor-paged lean list. Filters `status`, `role`, `party_id`. Each item says whether the current declaration already includes it. No free-text search. |
| `POST .../party-balances/{id}/withdraw` | Idempotent, versioned, with a reason. Refused once the declaration includes the line or it is already withdrawn. |

Reads need the same opening read fields as the workspace. Withdrawal needs
`accounting.finance.manage`. Events `accounting.party_opening_balance.create` and `.withdraw` use
the money category. Creation records the held line's references and amounts, never names. Withdrawal
records only the status change and the printable reason the person gave. The opening preview and
save refuse a declaration that carries a withdrawn line's source key.

## 8. Console

- The supplier and customer import page shows an "Optional opening balances" guide next to the
  template. It reads opening readiness and warns before upload when balances can no longer be
  added; it stays quiet if the reader cannot see readiness.
- The opening worksheet, step "Accounts and bills", shows "Balances held from party imports" when
  any are pending: a list with debit and credit totals, "Add N held balances to this worksheet"
  and a per-line withdraw with a reason. Adding copies the lines into the worksheet exactly as
  imported; the person then adds the offsetting balances and uses the existing preview and save.
- The opening proxy allowlist permits exactly the two routes above.

## 9. Not covered

- More than one bill for a party in the file; use the worksheet or the account-ID opening import.
- Existing parties and accounts. The ready resources are create-only; use the opening worksheet.
- Identity-only party rows, other roles, and updates of an imported balance after it is in a
  declaration (change it in the worksheet).
- Posting. Posting, reconciliation and finalization stay in the existing opening workflow.

## 10. Rollout

Apply Accounting migration 0226 first (Alembic `upgrade head` with the Accounting database URL),
then restart Accounting and reload the Console. No setting or environment variable. Accounting
reports itself not ready until the database is at the new head, so the migration must precede the
restart; the worksheet's held-balance list also needs the table.

## 11. Verification and review

Verified 2026-10-31 on the working tree (other agents' unfinished stock-count work shares the
Accounting migration chain and generated files, so this change cannot yet be committed alone).

- Domain: pure rules, schema and gating, 44 tests with no database.
- Native API on SQLite: import dry run and commit, replay, audit payloads and reason, rollback of a
  later failing row, readiness gating (finalized, legacy draft, resumable draft), finance and
  field-policy and account-right gates, withdraw versioning/idempotency, cross-company and
  cross-tenant isolation, cursors bound to their query, immutability, and base and foreign held
  lines round-tripped through the real opening preview and save. 159 passed, 2 skipped across the
  party, import, opening and audit suites.
- Native MySQL 9.6 (disposable schema): 81 passed, model/migration parity, and the 0226
  up/down/up round trip.
- Strict mypy over the Accounting package and Ruff are clean; OpenAPI and the generated client are
  current; the audit contract rows match the exporter's logic.
- Console: library, proxy-allowlist, held-balance panel, worksheet integration (including the
  preview body and the balance requirement) and the import guide have their own tests.

Independent review (fresh reviewer, read-only) found and this change fixed: the withdrawal reason
was validated but never recorded; a withdrawn line could be revived by a stale worksheet; a legacy
or already-posted opening batch was wrongly treated as resumable; an opening column without an
amount was reported without its column name (and an account code alone would have been ignored);
the withdraw dialog did not say which balance it affected and its copy contradicted create-only
imports; the rollout note was wrong about an un-migrated database; the held-balance verifier
accepted a zero amount or rate. Added tests for each, for the field-policy and account-right
gates, for dry-run and rollback leaving no outbox rows, for audit content against the contract,
and for a foreign line through preview and save.

Known limits: the audit `safe_fields` list is maintained by hand in the exporter and tied to the
emitted keys by a test; `tools/export_audit_contract.py` currently cannot regenerate the whole
contract because another agent's stock-count events are not mapped yet (the two new rows were
added by hand); the import guide cannot tell a reader who lacks `accounting.finance.manage`
that opening rows would be rejected, because that permission is not visible to the page; and the
Console was not exercised in a real browser for this change.

## Decision log

- 2026-10-31: Held balances, not a posted or saved declaration, because the declaration must
  balance with no plug and a party file supplies one side only. D1–D9 above. Evidence: native
  import, API, domain and Console tests listed in the delivery record.

- 2026-11-04: The opening worksheet can disclose and add a configured equity offset
  before explicit preparation/posting. Import capture still holds balances and never
  generates an offset or posts money. This updates D1's wording without changing
  import APIs or stored held-balance evidence.
