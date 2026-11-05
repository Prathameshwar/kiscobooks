# Account and party opening APIs

The Accounting service owns the company opening worksheet at `company.books_begin_date`.
Account and party creation with an opening also completes its native posting and
Identity confirmation before returning success. Each such opening has an additive
native opening batch balanced by `OPENING_BALANCE_OFFSET`; it does not replace the
company worksheet. Creation retries continue the original journal. See
[immediate master posting](master-opening-immediate-posting.md). The company workspace is
available at `/accounting/opening`. Read
`/v1/companies/{company_id}/opening-batches/capabilities` before offering an action.

## Capture and completion

1. Read `/opening-batches/readiness` and `/opening-batches/workspaces/field-set`.
2. Preview a version 1 `OpeningDeclaration` at `POST /opening-batches/workspaces/preview`.
3. Save it at `POST /opening-batches/workspaces`. Saving has no ledger effect.
4. Send its current `expected_version`, `manifest_hash` and printable review
   `reason` to `POST /opening-batches/workspaces/{id}/prepare-drafts`.
5. Read the returned journals and post them through the existing native journal
   commands. Identity reservation happens outside the money transaction; the
   existing durable confirmation worker completes delivery.
6. Read `/opening-batches/workspaces/{id}/reconciliation`. All declared GL and
   bill values must match, every journal must be posted, and confirmations must
   have completed.
7. Refresh the workspace version, review it, and explicitly `POST .../{id}/finalize`.
   Ordinary trading remains blocked until this completes.

The Console automatic action explicitly confirms this entire sequence. It waits on
reconciliation while native confirmation is pending and finalizes with the refreshed
workspace version. Only a verified `FINALIZED` receipt completes that action. Manual
mode can still perform the commands individually. Missing fixed opening accounts can
be provisioned during the explicit Validate and preview action through the existing
idempotent company initialization command, before reviewing the balanced declaration.

Every mutation requires `Idempotency-Key` and current company authority. Reuse
the same key and unchanged body after a lost response. A new version or edited
body is a new command. Current field permissions are rechecked on replay. Entry `posting-link` reads expose
its stable source key, chunk, native journal and line sequence.

`accounting.finance.manage` manages declarations; `ledger.post_journal` remains
the native posting authority. Native period, field, company and financial setup
checks continue to apply. Export tickets also require `accounting.export.read`.
No additional system role or seed grant is introduced.

Opening form metadata includes `capture_permissions.journal_lines` and
`capture_permissions.open_items`, derived from finance-management authority and
the same native changed-field rules used by declaration capture. Generic open-item
CRUD metadata has no input fields and is not a declaration-capture permission
source. A controller may capture and prepare without `ledger.post_journal`;
native posting still requires it. Current read/field authority is checked before
the metadata is returned.

Opening journals, including legacy opening batches, recheck the opening revision
window at both native preparation and commit. Closing or locking later books
after draft preparation or during external authorization prevents posting. A
blocked prepared intent remains recoverable through native cancellation and
durable Identity abort delivery. Completed idempotent receipts retain replay.

## Money and historical bills

An entry names an exact company account ID, stable `source_key`, positive exact
decimal-string `amount`, explicit `DEBIT`/`CREDIT`, ISO currency and entered
`exchange_rate`. An optional explicit `base_amount` is the historical remaining
carrying value. Converted values are frozen into the execution plan, including
when the caller did not specify an explicit base amount. Display precision
changes cannot recalculate an already captured plan.

All entries balance in company base currency. Base-currency rate must be one;
its carrying value must equal its amount. The API never invents a balancing entry.
The three-step Console worksheet can disclose and include a configured equity offset
as an ordinary entry before preview, as authorized on 2026-11-04. Its stable source key
is `automatic-opening-offset`; the amount is the exact opposite of the other entries'
net base balance. It is distinct from zero-net migration clearing.
Credit cash requires `credit_cash_reviewed=true` and `credit_cash_reason`.
Bank overdrafts and supported contra-account sides remain explicit signed-side
balances in their existing account classifications.

Party entries additionally contain `documents`. The supported typed kinds are
`INVOICE`, `BILL`, `CREDIT_NOTE` and `ADVANCE`, validated against account role and
debt/credit direction. Customer and supplier roles and currencies never net
against each other. Each document keeps its reference, source key, original
document date, due date and remaining amount. Optional `original_amount` must
be at least the outstanding amount; it is evidence, never another posting.

For example, a bill originally for 200 and now outstanding for 100 imports 100.
It does not recreate settled history. Foreign-currency bills require explicit
historical `base_amount` per bill. All bill currency amounts and base carrying
values reconcile to their party journal line. If any bill supplies a carrying
value, all bills on that line must supply one. Old legacy opening callers retain
their previous schema behavior.

Coverage normally ends before cutover. A document cannot follow the declared
coverage. Same-day coverage requires `same_day_reviewed=true`; this preserves
the existing legacy same-day convention without silently tightening it. Due
dates may be before or after cutover, but never before their document date.
No fake invoice or due dates are inserted.

## Reads, correction and financial bridges

Workspace entry/revision collections use signed keyset cursors, typed filters
and lean projections. Entry detail and historical revision detail are separate.
Filters referencing accounts or parties outside the company are rejected.

An unposted revision may be replaced. Existing DRAFT journals become VOID;
their evidence and prior immutable revisions remain. PREPARED effects must first
be resolved through native recovery. Posted corrections use native reversal
and a new declaration with `replacement_of_id`. Trading, closed periods,
settlements, charges, bank reconciliation and linked physical stock can block
correction. Cancellation of an import never claims that posted money was undone.

`GET /opening-batches/workspaces/{id}/journals/{journal_id}/recovery` is a private,
read-only, company-scoped view of a current revision's journal. It also requires
`ledger.read` and contributing journal-field access. It reports cancellation and
reversal eligibility, dependency/period blockers and any retained reversal ID,
status and version. It uses the same company fence as reconciliation; it reserves
and posts nothing. Native commands recheck all conditions after this preflight.

Cancellation uses existing `POST /journals/{id}/void` with current version/reason,
including for an interrupted reversal. Creating a reversal uses existing
`POST /journals/{id}/reversal`; posting that draft is a separate action. Cancellation
does not need period-post authority and remains available for blocked intents
under the existing native journal authority. Reversal and posting still require
their current financial and period permissions. Cancelled reversals remain retained
financial evidence; recovery selects the remaining non-void reversal, if any.

Bank opening reconciliation stays at `/bank-reconciliation/opening-items`.
Those outstanding cheques/deposits do not post the bank balance again. Stock
openings retain their `COMBINED`/`LINKED_GL` owner and native duplicate/claim
guards. Financial reconciliation reports bank GL totals and links to those
owners; it does not claim that GL capture completed physical stock or bank
reconciliation. Tax-control balances do not assert statutory return completeness.

The existing reporting source continues to publish native journals, journal
lines, opening batches and open items at its normal source snapshot. Coverage
starts at books begin. Opening effects and their reversals keep the existing
opening classification, rather than ordinary turnover. Existing annual carry
derives from posted facts and unsettled original bills; there is no new opening
journal or date reset every year.

## Import and private export

Use `/financial-opening-imports/template`, then stage JSON or base64-encoded
CSV/TSV/XLSX at `POST /financial-opening-imports`. JSON uses the typed declaration.
Files require marker `_financial_opening_schema_version,1`, text cells, exact
native account IDs and consistent source/cutover headers. The shared file reader
allows 2,000 rows; the decoded upload is additionally bounded to 2 MiB. Each native journal permits 200 lines and 1,000 documents. Large declarations
require an explicit `clearing_account_id`: an active, non-party, general
balance-sheet account in base currency, distinct from declared opening accounts
and inventory controls. Deterministic bounded chunks use that account; two
missing drafts are prepared per request. Finalization requires every child and
confirmation plus exact zero clearing. Monetary bounds include clearing turnover;
no truncation or silent difference write-off is allowed.

`POST /{job}/validate` creates a review hash over the declaration, account
versions, period/setup versions, company configuration and current authority.
`POST /{job}/commit` requires that hash and current job version. It creates the
declaration and bounded native drafts only. Its receipt explicitly identifies
that effect; it does not post, approve or finalize. `prepare-drafts` resumes the
job; `cancel` stops it while retaining independent declaration/draft receipts.
List/history rows omit stored documents and issue JSON.

`GET /{job}/declaration` returns the retained typed source for human review before
commit. It uses the same current company and contributing-field read guards as
the worksheet and prohibits caching; it does not validate, commit or post.

Workspace export and import reports use short-lived tickets tied to tenant,
company, actor, revision/job version and current authority. Downloads recheck
permissions, have no-store headers, escape spreadsheet formula text and emit
reference-only audit events. Tokens are not public object URLs.

## Storage and rollout

Additive Accounting migrations 0217–0220 create four scoped tables:

| Table | Purpose |
|---|---|
| `financial_opening_revision` | Immutable declaration header, revision and manifest hash |
| `financial_opening_entry` | Immutable indexed account/party/currency amounts and document evidence |
| `financial_opening_chunk` | Immutable native draft plan and a once-only journal binding |
| `financial_opening_import` | Stable source/input hash, durable review state and draft handoff receipt |

They retain native opening batch/journal ownership. Scoped foreign keys, unique
source/revision constraints, checks and cursor/filter indexes match their models.
Deleting retained evidence or modifying captured source content is rejected.
Each table revision has one CREATE TABLE statement; downgrade requires empty
evidence. Migrations 0221-0222 separately make open-item document and due dates
nullable. Their downgrade refuses retained unknown-date evidence.
OpenAPI, generated TS client and Identity field metadata accompany the change.
UI and posting admission switches are separate from schema rollout.

## Approved migration modes

All three decisions were confirmed during implementation on 2026-10-28.

- `ON_ACCOUNT` preserves an explicitly labelled balance with both document and due
  dates null. The native item records `tracking=ON_ACCOUNT` and unknown-history
  provenance. Accounting ageing exposes `unknown_due`; Reports exposes `UNKNOWN`.
  These balances remain in credit exposure and settle normally, but cannot accrue
  automatic overdue charges without known historical dates. No dates are invented.
- `POST_CUTOVER_ONLY` reports only retained activity. `YTD_SUMMARY` additionally
  requires `originating_year_start` matching the company fiscal year, coverage
  through D-1, and an explicit `ytd_summary` array (including explicit empty for zero).
  Each summary row has account ID, side, currency, amount and base amount. Only
  income/expense accounts are allowed, and their signed transaction/base totals
  must match nominal opening GL balances. Rolled-up retained earnings cannot be
  silently imported again as nominal activity.
- Reports allows the full originating-year aggregate in P&L/Income & Expense,
  discloses `imported_ytd_amount` and source coverage, and keeps post-cutover views
  separate. A partial pre-cutover range or historical monthly detail is unavailable.
  Balance Sheet earnings classify the same GL once as current or prior earnings;
  YTD summaries create no extra ledger posting. Report publication independently
  reconciles summary provenance to native opening journals. Existing source schema
  hashes remain readable through reporting-contract 0.8.0 compatibility handling.
- Large declarations use configured clearing as described above. After partial
  reversal, `void` closes the remaining unposted plan and completes REVERSED status;
  it never deletes posted evidence. A replacement names the reversed predecessor.

New report definition versions and implementation hashes accompany these rules;
existing completed runs and exports retain their original evidence. The UI delivery
and subsequent hardening are recorded separately.

## Balances held from party imports

A ready customer or supplier import row may carry an opening balance. It creates the party's
ledger account and a held `party_opening_balance` row (migration 0226), never a declaration or a
journal. `GET .../opening-batches/party-balances` lists the held rows with an `included` flag
(the current declaration already has the entry with the same source key) and
`POST .../party-balances/{id}/withdraw` drops one that is not yet included. The worksheet copies
held rows into the declaration the person is building; the declaration still must balance,
including any explicitly reviewed equity offset. Save, preview, posting and finalization
retain their existing contracts. Full contract:
[party-opening-balance-import](party-opening-balance-import.md).

## Decision log

- 2026-11-04: User approved one company books-begin date and a configured opening-equity
  offset for the three-step worksheet. Automatic mode fills source settings, discloses the
  offset, and uses existing save/prepare/post commands only after explicit confirmation.
  Unknown outcomes replay the identical command and idempotency key. Finalization still
  follows confirmed reconciliation. Chart v5 provides separate offset and clearing defaults.

- 2026-10-31: Party imports hold opening balances beside the declaration instead of saving or
  posting one, because a party file supplies one side only. The no-plug, balanced-declaration and
  master-creation-posts-no-money rules are unchanged.

- 2026-10-29: Apply the revision window at both posting boundaries for all native
  opening journals. Reuse fiscal blockers in readiness and reconciliation. Add
  scoped read-only correction preflight and durable reversal discovery over the
  existing cancellation/reversal commands. UI capture reads the immutable revision
  named by its workspace and pins its edit baseline, including an absent batch.
  Evidence: [review implementation](account-opening-review-implementation.md).
