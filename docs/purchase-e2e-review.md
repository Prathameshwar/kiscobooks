# Purchase voucher: end-to-end review (UI, API, posting, print)

Date: 2026-10-31. Scope: the untaxed **account (expense) Purchase** — from the Console page
`/vouchers/new/purchase`, through the Vouchers service and Accounting's posting, to a printed PDF.
Goods, stock and taxed purchases, and Purchase reversal, are documented as not implemented; this review
checked that they are refused rather than half done. Companion records:
[purchase-api-progress](purchase-api-progress.md), [purchase-print-todo](purchase-print-todo.md),
[purchase-page-redesign](purchase-page-redesign.md).

## 1. Method

Four independent read-only reviewers (API lifecycle, print pipeline, Console-to-API contract, a live
isolated multi-service run) reported findings; each finding was then checked against the code before it
was fixed. A fix starts with a failing test. Nothing here was applied to the user's running databases or
services.

## 2. Chain status

| Step | Status |
|---|---|
| Create, edit (new DRAFT revision), history, revisions, list | Implemented, tested |
| Invoice preview, acceptance | Implemented; acceptance is verified by Accounting at post (see 3.2) |
| Submit, approve, reject, cancel | Implemented, tested; a single-user company cannot approve its own bill (decision D1) |
| Post (asynchronous owner operation, recovery, reconciliation to POSTED) | Implemented; journals Dr expense / Cr supplier payable verified by probe |
| Voucher number | Accounting's journal number (`PURCHASE/<FY>/<seq>`) prints as "Voucher no." on a posted bill (decision D3, 2026-11-01); Vouchers still stores none and a draft says "Not allocated" |
| Duplicate supplier bill | **No interactive guard** (decision D2) |
| Reversal | Refused with 409 (owner not implemented) |
| Goods, mixed, stock | Refused at post; now also refused at acceptance (3.2) |
| Print (standard A4) | Implemented and unit/native tested; **not deployed** to the dev stack (section 5) |

## 3. Findings and disposition

Filled in below as each is closed.

### 3.1 Console to API contract (page could not work against the real services)

| # | Defect | Disposition |
|---|---|---|
| C1 | Choosing a supplier asked for `party_role` on accounts: refused by the proxy and by the service | Fixed; proxy-policy test and a flow test |
| C2 | A saved bill's field-set has a different shape from the one the page read, so every reopen and every post-save readback failed | Fixed in the Vouchers service (edit view added to the saved voucher's field-set) and in the Console |
| C3 | Supplier advances: `direction=DEBIT` (service enum is DEBT or CREDIT; an advance is a CREDIT item), and the balance read was not in the proxy allowlist | Fixed |
| C4 | A finished execution reference stayed in the tab and pinned later visits to that bill | Fixed |
| C5 | Clearing the supplier-declared total was not saved | Fixed |
| C6 | The proxy refused bodies over 16 KiB; a bill of about 60 lines did not fit | Fixed (320 KiB, below the service's 256 KiB + envelope) |
| C7 | Every 409 was shown as "changed elsewhere", hiding the service's reason | Fixed |
| C8 | Cancel offered while a posting runs; a rejected bill could not be re-submitted; no warning that editing a submitted or approved bill voids its approval | Fixed |
| C9 | No shipped role can use the page (lookups need Accounting read rights no role with `vouchers.create` has) | **Decision D4** |

A new test (`purchase-wire-flow.test.tsx`) drives the real page from an empty form to POSTED through the
Console's real proxy allowlist against stand-ins that mirror the services' response shapes and query
rules. The stand-ins (`purchase-fake-service.ts`) are held to those rules by their own tests
(`purchase-fake-service.test.ts`): a calculation hash that varies with the bill and is accepted only
when it equals the owner's, writes refused under a superseded type revision, and an idempotency key
refused when reused for a different request. Reintroducing the C1 and C3 defects makes all five flow
tests fail.

Also fixed in the Console after the second review: an execution reference is dropped when the
execution is REJECTED, CANCELLED, or COMMITTED with the voucher POSTED, and is kept while it is
PENDING or committed-but-not-yet-POSTED (tested for all five cases on reload); the proxy
authenticates the caller **before** reading the request body, so an anonymous caller cannot make it
read 320 KiB; the print button gate and the print page share one permission list.

### 3.2 Vouchers service (lifecycle, integrity)

| # | Finding | Disposition |
|---|---|---|
| V1 | Acceptance stored whatever hash the client sent, and survived later edits of the bill | Fixed. Acceptance is verified against the owner's preview (409 stale, 409 owner not configured, 503 owner unreachable); every revision write clears the stored hash |
| V2 | The header supplier was not reconciled with the invoice's party ledger (a bill could name supplier A and credit supplier B's payable) | Fixed. A supplier/customer party's id must equal the ledger's `party_id` |
| V3 | Goods, mixed and stock Purchases were refused only at post | Fixed. Refused at acceptance with a clear message (`UNPOSTABLE_PURCHASE`) |
| V4 | The saved voucher's field-set could not be used to edit | Fixed (C2). A voucher whose type was retired, or whose class belongs to a superseded type revision, still reads; the edit view is withheld with the reason in `configuration_unavailable` |
| V5 | Four Vouchers tests were red at HEAD (isolation contract, owner worker) | Fixed; the isolation test now covers six more tables |
| V6 | No Vouchers voucher number for Purchase; Accounting allocates a journal number `PURCHASE/<FY>/<seq>` that Vouchers does not store | **Decision D3**, implemented for the print (section 6.1); Vouchers still stores no number |
| V7 | A creates, B accepts, A approves succeeds (the separation check is on the revision, not the bill) | **Decision D1**, with the approval flow |
| V8 | First use of an account bumps its version and stales other in-flight bills | Known; each bill is refused with the version message and re-saved. Not changed |
| V9 | No interactive duplicate supplier-bill guard | **Decision D2** |
| V10 | `execution_ready` ignores company readiness (fiscal year, periods) | Reported; posting still fails safely with the owner's reason. Not changed |
| V11 | Account evidence replicated before Accounting published `party_id` (before 2026-10-11) would refuse a legitimate bill | Now refused with its own message ("the account master must be re-synchronised from Accounting"), distinct from a supplier mismatch. **A re-sync alone does not repair such a row**: same-version account evidence with different facts is a conflict, so it is repaired when Accounting's account `row_version` next increases (any edit to that ledger). Whether to allow an additive upgrade of `party_id` is **Decision D9** |

### 3.3 Accounting (posting)

| # | Finding | Disposition |
|---|---|---|
| A1 | **High.** Posting a plain Purchase was rejected (`CONTENT_REJECTED`) for the only role that can post. Credit assessment runs for every entry that creates a debt item, supplier payables included, and demanded `accounting.credit.read` before it looked for a policy. A supplier with no credit policy can only be allowed | Fixed with the failing test first: assessment is skipped when nothing can constrain the entry (a supplier with no credit policy on the posting date). Customer debits, and suppliers with a policy, are still assessed and still need `credit.read`; supplier credit limits remain enforced (a limit is rejected, with or without the read right). My first proposal, to assess only customers, was wrong: it would have switched supplier limits off, and the new tests pin that |
| A2 | A bad or foreign advance allocation left the operation stuck instead of rejected | Fixed. A missing or foreign allocation target is `CONTENT_REJECTED`, with a sanitized log line; the preview also validates targets |
| A3 | The printed PDF named the payable ledger ("Shree Office Supplies - Payable") as the supplier | Fixed. The supplier is the Party's name through `account.party_id`, read under the party's own permission and field policy; an unreadable name prints "Supplier details restricted" and the amounts stay readable. **Consequence:** `stock_operator` held `accounting.account.read` but not `accounting.party.read`, so its prints showed the restricted label (D4; `party.read` added to it and to `purchase_clerk` on 2026-11-01) |

### 3.4 Print

| # | Finding | Disposition |
|---|---|---|
| P1 | **High.** A stuck renderer could hang the single worker | Fixed: bounded stop, Job Object, child deadline, `RENDER_TIMEOUT` |
| P2 | A finished PDF could be lost to the watchdog or to a hung driver exit | Fixed: delivered before teardown, watchdog disarmed under a lock |
| P3 | Continuation pages carried no identity | Fixed: per-page footer |
| P4 | The print button gate omitted `accounting.account.read` | Fixed |
| P5 | Content gaps (account per line, company address/GSTIN/PAN, terms, tenders and advances, non-base currency); names and display formats not frozen at job creation; Design can publish layouts the print refuses; downloads not audited | **Decision D6**. Fixed 2026-11-01 (section 6.1): voucher no., ledger per line, credit period, tenders and advances, formats frozen and hashed, base-currency refusal worded, downloads audited. **Still open:** company legal name/address/PAN/GSTIN, foreign-currency bills, Design publish-time validation, historical master names |
| P6 | The development stack has no print configuration, worker or broker | **Decision D7** |

## 4. Verified on an isolated stack

A live run stood up Identity, Accounting, Vouchers, Design, Auth and the Console on throwaway schemas
(`rv_e2e_*`) behind a private gateway, then stopped all of it. It drove the real UI and API from sign-in
to POSTED:

- Journal `PURCHASE/FY2026-2027/000002`: Cr supplier payable 17,350.50; Dr Rent 12,500.00 and
  Utilities 4,850.50. The open item carries the due date and bill reference; audit and outbox rows were
  written in the same transaction.
- The printed PDF shows the title, POSTED badge, "Internal purchase record · Not a supplier tax invoice"
  and the totals; its hash matches the job and the download used the right ticket.
- 26 of 26 negative checks passed: cross-company access, idempotent replay, a forged acceptance hash on
  an edit, self-approval, and tampered, expired and foreign download tickets.
- Default Purchase voucher types are created for a new company.
- The run found A1 (post rejected for the poster role) and A3; both are fixed above and covered by tests.

Limits of that run: the sandbox was off in a scratch snapshot for the print, there was no broker, and no
role seeded for the shipped system roles could complete the flow alone (D4). Nothing was applied to the
running development databases or services.

## 5. Readiness

| Area | Untaxed account Purchase |
|---|---|
| Entry page → API (all calls) | Works against the real services; tested through the real proxy allowlist |
| Draft, preview, acceptance, submit, approve | Works |
| Post and journal | Works once a role holds `vouchers.post`, approval and the Accounting read keys (D4) |
| Print (A4 standard) | Works; **not activated** (configuration, worker, broker, renderer version) |
| Goods, stock, taxed, reversal | Refused with a clear message; out of scope (D8) |

## 6. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| D1 | A single-user company cannot post: `approval_required=false` still needs a separate approver | When approval is not required, submit approves automatically; keep separation of duties when it is |
| D2 | No interactive duplicate supplier-bill guard | Warn on the same supplier + bill reference + year, block on confirm |
| D3 | Purchase has no Vouchers number | Show Accounting's journal number on the voucher and print. **Status 2026-11-01:** done for the print (owner delegated the choice); the voucher read model is not changed (section 6.1) |
| D4 | No shipped role can create, approve and post a Purchase; `billing_clerk` lacks the Accounting read keys the page needs. `stock_operator` (the only `vouchers.post` holder) lacks `accounting.party.read` (prints say "Supplier details restricted") and `accounting.credit.read` (cannot post against a supplier that has a credit policy) | Add the read keys to `billing_clerk`; give the approver role `vouchers.approve` plus the artifact rights; add `accounting.party.read` to the poster. Whether the poster also gets `credit.read`, or credit is evaluated under service authority, is a role-design call. Security-sensitive: needs sign-off. **Decided 2026-11-01 (owner: best fit, least privilege) and implemented:** new `purchase_clerk` role (records, submits, posts, prints; never approves); `billing_approver` gains the four master reads and `vouchers.operation.read`; `stock_operator` gains `accounting.party.read` and the artifact keys, not `credit.read`; `billing_clerk` stays the Sales role. A probe against Accounting's real posting path also found that `accounting.party.read` is required to post (not only to print) and that `accounting.tax.read` is required to preview or post even an untaxed bill; `purchase_clerk` holds both. See [roles-permissions](roles-permissions.md) decision log. Added afterwards: `stock_operator` also gains `accounting.tax.read` (the company creator could not otherwise preview or post their own account Purchase). It still cannot post against a supplier that has a credit or accounting policy: that needs `credit.read` and `policy.read`, which `purchase_clerk` holds |
| D5 | Sandboxed Edge/Chrome does not return on this Windows machine | Allow an explicit, local-only, off-by-default switch; never in production. **Status 2026-11-01:** done (`VOUCHERS_PRINT_CHROMIUM_SANDBOX`, refused unless `VOUCHERS_ENVIRONMENT=development`; section 6.1) |
| D6 | Print content gaps and freezing names/formats at job creation | Freeze at job creation; add the missing content before first use. **Status 2026-11-01:** done except the items listed as open in P5; historical re-freezing of master names is not required (section 6.1) |
| D7 | Apply Vouchers 0110/0111 and Accounting 0226/0227, env settings, worker starts and restarts on the dev stack; bump `purchase-pdf` to `@2` first | Go ahead when the previous items are decided. **Status 2026-11-01:** the bump is done (`purchase-pdf@2`, and the layout moved to `purchase-a4@2`); the stack activation is not. **Checked read-only 2026-11-01:** the local databases are already at their migration heads (Vouchers 0111, Accounting 0227, Identity 0095), so no migration is pending; the D2 and D1 work added none. The role seed was dry-run only (`role` +1, `role_permission` +35, nothing revoked or changed); applying it was refused by the session's permission system, so it still has to be run by the owner (section 7). No service was restarted |
| D8 | Goods, taxed and reversal Purchases stay out of scope | Confirm |
| D9 | Old account evidence without `party_id` is repaired only when the ledger's version next changes | Allow an additive `party_id` upgrade for same-version account evidence in `sources.py`, or bump the affected ledgers once |

### Vouchers decisions implemented (2026-11-01)

The owner delegated D1, D1b, D2 and D9 to the platform's best fit; the Vouchers service now does this,
each with a test written first (Tally Prime and QuickBooks have no approval step unless it is enabled, and
both warn on a supplier's repeated bill number).

- **D1, approval is a configuration choice.** When the effective policy does not require approval,
  `submit` moves DRAFT or REJECTED straight to APPROVED (the response carries `status: APPROVED`).
  No approval row exists; the transition history and the audit event (same transaction) carry the reason
  "approval not required by the voucher configuration", and the execution command carries no approval ids,
  which the worker's identity check accepts. `approve` and `reject` then stay refused with 409. When approval is
  required nothing changes. It applies to every kind, because the rule lives in the shared transition.
  The company defaults state `approval_required` explicitly from the `approval_workflow` feature.
  **Review correction, same day:** the implementation first let a version 2 policy that did not state
  `approval_required` or `self_approval_allowed` inherit the envelope's permissive values (no approval,
  self-approval allowed), while the type form shows a missing key as required / not allowed. With submit now
  approving in one step, a control the administrator sees as set could be skipped. `effective()` now passes the
  type's own policy through `explicit_approval_controls()` (`domain/configuration.py`), which writes the schema
  defaults for these two keys when a version 2 type omits them; classes and bindings below the type still inherit
  sparsely from it, and `intersect()` is unchanged (its sparse-inheritance test still holds). Covered by
  `tests/test_approval_omitted_policy.py`, red first (two of the four failed before the change).
  Because the type's effective policy, and so its configuration digest, changes for any version 2 type that
  omitted a control, drafts under such a type would answer "configuration changed; revise and reapprove".
  Checked read-only on the local database on 2026-11-01: 42 type revisions, 38 version 2, **none** omit
  either control, so nothing there is affected. Count them again before deploying to another installation.
- **D1b, separation across revisions.** When approval is required and self-approval is not allowed, nobody
  who created the voucher or any of its revisions, acceptance revisions included, may approve it (403
  "another authorized actor must approve this voucher"). Self-approval allowed, or approval not required,
  lifts it.
- **D2, duplicate supplier bill.** `GET /v1/companies/{company_id}/vouchers/duplicate-bills` and a refusal at
  `submit` of a Purchase invoice: same company, same supplier party (header), bill reference equal after trim,
  case-folding and collapsing whitespace, live statuses (DRAFT, SUBMITTED, APPROVED, ISSUED, POSTED), current
  revision only, same company fiscal year as the document date (the revision's recorded fiscal start), never the
  voucher itself, other kinds, or a blank reference. The refusal is `409 duplicate_supplier_bill`; `submit` with
  `acknowledge_duplicate_bill: true` proceeds and the acknowledgement is recorded in the transition reason and
  the audit event. No migration: the supplier index `ix_voucher_party_list` and the tenant-and-company unique
  keys already serve the lookup.
- **D9, party link repair.** Account evidence at its stored version may gain a missing `party_id` when the
  incoming facts are identical in every other key and the status is unchanged. Any other same-version
  difference is still a conflict, and an applied bundle is audited as before.

### Independent review of the decisions, 2026-11-01 (fixed the same day)

A separate reviewer read the D1-D9 changes; each finding below was fixed with a failing test first.

- **Duplicate guard without a header supplier (medium).** A Purchase whose `parties` is empty was never checked.
  The guard and the lookup now also key on the payable ledger (`invoice.party_account_id`); the lookup takes an
  optional `party_account_id` and needs one of it or `party_id`. The Console sends both.
- **Silent 2,000-row cut-off.** The lookup now walks every candidate in keyset batches up to 20,000 per supplier or
  ledger and fiscal year. Past that it fails closed: submit asks for acknowledgement ("the duplicate check was
  incomplete", no ids), the lookup answers `truncated: true`, and the acknowledgement is recorded
  (`duplicate_check_incomplete`).
- **Bill-number matching** now applies NFKC, drops format characters (zero-width, soft hyphen), folds every dash
  to `-`, and ignores edge whitespace and `.,;:`.
- **Guarded fields** of the lookup now include `kind` and `id`, like the list endpoint.
- **Idempotency.** `acknowledge_duplicate_bill` is left out of the hashed body when false, so a retry of a key stored
  before the deploy still replays.
- **Self-approval** now also excludes whoever submitted the voucher, not only its authors.
- **Print download** re-checks the frozen labels (supplier, ledgers, voucher number): a label that can no longer be
  read, or has changed, refuses the download with the same 409 as a changed calculation. A label that was never
  frozen is not compared.
- **Open: index.** `voucher_invoice_detail` has no index on `(tenant_id, company_id, party_account_id)`, so the ledger
  walk (and the import rule that already filters on it) range-scans the company's invoice-detail rows: correct, not
  index-driven. Adding it needs a migration under `dbs/vouchers` applied with a DDL connection, and the service's
  readiness check compares the schema version with the code's head, so it is not added mid-stream; decide it with
  the next schema change.
- **Open, owner decisions:** `purchase_clerk` and `stock_operator` post any voucher kind and manual journals
  (roles-permissions, "What purchase_clerk is, plainly"); `accounting.tax.read` is broader than the one lookup the flow
  needs.

### 6.1 Print follow-ups, 2026-11-01

The owner said to proceed with what is best fit for the platform and its configuration, borrowing from
Tally Prime or QuickBooks where unsure. The tests were written before the code. Only Accounting's journal
number and ledger-name tests were run red first (`AttributeError` on the missing facts); the Vouchers tests
import names that did not exist yet and were first run after the implementation.

| Item | What changed |
|---|---|
| D3 voucher no. | Accounting's print facts return the journal number of the journal that posted the bill (`InvoiceRecord.intent_id` to `VoucherMoneyIntent.journal_id` to `Journal.number`), read under the journal's field rights; `None` for a preview and when the number cannot be read. Vouchers freezes it in the snapshot and prints "Voucher no." in the header block, the footer and the custom `voucher.issue_number` binding. Allocation is still posting-only. Tally prints a voucher no.; QuickBooks bills have none, so this follows Tally. Not done: storing it on the voucher (the execution result carries effect ids, not the number text) |
| D5 sandbox | `VOUCHERS_ENVIRONMENT` (default `production`) and `VOUCHERS_PRINT_CHROMIUM_SANDBOX` (default `true`); `false` is accepted only in `development`, refused at start otherwise, re-checked at render, logged as a WARNING at start-up and on every render, never in any API |
| D6 content | Ledger name per line (restricted names print "Ledger restricted"); supplier invoice no. and date; credit period derived from invoice date and due date; tenders, advances and the balance after them; voucher no. Everything is in the frozen, hashed snapshot and escaped. The display formats were already frozen (`display`); a test now pins that and its hash coverage |
| D6 foreign currency | Not feasible: Accounting calculates and posts base-currency invoices only (`invoice_calculation.preview` refuses `currency != base_currency` and `exchange_rate != 1`), so no foreign bill has authoritative amounts. Vouchers now refuses it before asking Accounting, with both currencies named |
| D6 company identity | Not feasible without a new Identity contract: the signed company context carries the display name and formats, and registrations without their numbers. No synchronous call was added. Remaining gap |
| D7a versions | `purchase-pdf@2`; the layout also moves to `purchase-a4@2`, because the stylesheet's own rule is to change it whenever the printed presentation changes, and the layout digest is only `sha256` of the version string, so it cannot detect a body change by itself. Jobs under `@1` fail as `SOURCE_INTEGRITY`; nothing was activated, so nothing migrates |
| D6b audit | `vouchers.print_job.download` (category `access`) is committed through the outbox after the PDF's integrity check and before the first byte; a failure to write it blocks delivery. Issuing a ticket is not audited |

Historical master names are not frozen at posting: like Tally Prime and QuickBooks, a reprint shows the
current names of the supplier and ledgers, while the amounts, dates, numbers and references are the
posted ones. A copy is frozen when its job is created ([purchase-print-todo](purchase-print-todo.md)).

## 7. Running the print on a real stack

1. No migration is pending on the local databases (Vouchers 0111, Accounting 0227, Identity 0095 are heads). On another installation apply them first. Restart Identity, Accounting, Vouchers and Design together (Vouchers refuses Design's old `purchase-a4@1`), then re-sync Accounting master evidence once.
2. Seed the roles (D4) from the repository root, dry run first: `apis\identity\.venv\Scripts\python.exe -m seeds.roles --dry-run`, then without `--dry-run`, with `IDENTITY_DATABASE_URL` set to the intended database (or the operator's `/v1/platform/system-roles` preview and `/reconcile`). Apply it before Identity is restarted on the new code, and before company creation is used: until the installed `stock_operator` and `company_admin` grants match the catalogue, creating a company answers 409. The seed adds one role and 35 grants and, on the owner's dry run, revoked nothing; it is not insert-only (it removes any grant on a shipped role that the catalogue does not list), so run `--dry-run` again immediately before applying and check `revoked=0`. To undo it, delete the `purchase_clerk` role's rows and the nine added grants. Assign `purchase_clerk` to the person who records and posts bills and `billing_approver` to a different person.
3. Configure print: private root, scoped HMAC credentials, a separate worker database identity, the
   broker; start the dispatcher and the worker (see [purchase-print-deployment](purchase-print-deployment.md)).
4. On the VM install Chromium with its OS dependencies and run the worker as an unprivileged user.
5. `RENDERER_VERSION` is `purchase-pdf@2` and the standard layout `purchase-a4@2` (deploy Design and
   Vouchers together); print one POSTED bill and compare the PDF's hash with the job.

## 8. Verification record

Run on 2026-11-01 against the working tree (nothing committed, nothing published).

| Check | Result |
|---|---|
| Console Purchase, proxy, money-policy and field suites (`vitest`, 32 files) | 507 passed |
| Console `tsc --noEmit` | clean for every Purchase file; two unrelated errors in `native-books.test.tsx` and `report-exports.test.ts` (other work) |
| Vouchers: lifecycle integrity, saved field-set, print child/page/deadline, Purchase print, supporting files, type defaults, isolation contracts, owner worker, audit contract, release gate, foundation, invoice capture, money posting (SQLite) | 191 passed, 1 skipped (POSIX-only), 2 deselected (real browser) |
| Vouchers on native MySQL (lifecycle integrity, field-set, isolation contracts; migrations, parity, downgrade/upgrade) | 55 passed |
| Accounting: credit scope, print supplier, allocation targets, settlement preview, Purchase print, credit, invoice execution, voucher money (SQLite) | 67 passed |
| Accounting on native MySQL (credit scope, print supplier, allocation targets) | 15 passed |
| Ruff, mypy strict (Vouchers 117 files, Accounting 257 files) | clean for every file this work touched |
| `export_openapi.py --check` (Vouchers, Accounting), `api-client generate.mjs --check` | exit 0 |

Red or unclean items that are **not** from this work: Vouchers `test_stock_opening_files.py` (7
failures, stock decimals decoder, unchanged since HEAD); Accounting `test_money_contracts.py`
(`KeyError: accounting.stock_count.observe` in `tools/export_audit_contract.py`, from the in-progress
stock-count work); Ruff in Vouchers `models/__init__.py` and `tasks/notifications.py`, and `ruff format`
on nine other Vouchers files (imports and razorpay work). Real-browser print tests were not re-run:
sandboxed Edge does not return on this machine (D5); the print was rendered once with the sandbox off
in a scratch snapshot (84,912-byte PDF; child deadline exit in 4.1 s; parent kill in 4.4 s, no stray
browser left).

### Print follow-ups, 2026-11-01

Working tree, nothing committed or published.

| Check | Result |
|---|---|
| Vouchers (SQLite): Purchase print, print content, sandbox switch, child bounds, page identity, render deadline, audit contract, release gate, isolation contracts, custom artifacts, supporting files | 170 passed, 1 skipped (POSIX-only), 3 deselected (real browser) |
| Vouchers on native MySQL: print content, Purchase print, audit contract, sandbox switch | 71 passed, 3 deselected |
| Real browser with the local-only switch (`VOUCHERS_ENVIRONMENT=development`, `VOUCHERS_PRINT_CHROMIUM_SANDBOX=false`): actual worker, 80-line pagination, new content on 3+ pages | 3 passed |
| Accounting (SQLite): Purchase print, supplier, print content, credit scope | 15 passed |
| Accounting on native MySQL: print content, Purchase print, supplier | 11 passed |
| Design Purchase print resolution (standard layout `purchase-a4@2` and digest) | 1 passed |
| `voucher-execution-client` 0.3.9 print and count tests | 12 passed |
| mypy strict: Vouchers 121, Accounting 257, Design 33 files | clean |
| `export_openapi.py --check` (Vouchers, Accounting, Design); `audit-contracts.py --check-console` | exit 0 (no route, schema or entity change) |

A scratch render with the switch (sandbox off in the child only, nothing in repo behaviour) produced a 2-page
97 KB PDF: voucher no. in the header block and both footers, a ledger line under each particular (one
restricted, one 120-character name wrapping), credit period, the NEFT tender with its ledger, reference and
date, advances, and the balance, with amounts intact on one line.

Not done: a log line carrying the execution id for `CONTENT_REJECTED` (the current line cannot name
the voucher; the Accounting test pins its absence), the stock-dispatch `NotFoundError` tuple (no
failing case found), a jsdom test that the URL carries `voucher_id` after Save.
