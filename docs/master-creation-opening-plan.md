# Opening balance during Party and Account creation

Updated decision, 2026-11-04: [immediate creation posting](master-opening-immediate-posting.md)
supersedes the held-only workflow and the post-finalization refusal below. New
creation openings post automatically, including their balancing entry and bills.
The original phases remain as the historical record for older held balances.

Authorized 2026-11-02: add an optional final opening step to Party/Account creation,
with amount, Dr/Cr and date; offer clean bill-wise capture inspired by ledger
opening allocation. Reuse existing company opening review and posting rules.

## Delivery phases

1. Define bounded exact-money capture and durable held evidence for both account
   kinds, with an atomic migration/model pair and domain regressions.
2. Add atomic aggregate capture during creation, protected reads/withdrawal and
   inclusion in the existing company opening worksheet. Verify rollback, replay,
   authority, tenant/company scope and immutable evidence.
3. Add the final creation step and a shared simple/bill-wise editor. Keep one bill
   editor visible, a compact summary list, exact pending totals and optional details.
   Preserve draft state, safe retry, field authority and existing account lifecycle.
4. Synchronize API/schema/client/runtime where needed; verify UI, native storage,
   migration/model parity and responsive themes. Review and fix findings.

## Product and accounting decisions

- Opening amount is optional. Blank/zero means no opening; positive amounts need
  an explicit Dr/Cr choice. No inferred direction is silently submitted.
- Opening date starts at the company's books-begin date and must equal it. The
  creation screen does not change the company's cutover date. Capturing an opening
  is refused after finalization, earlier activity or a blocked opening window.
- Bill-wise entry applies to customer/supplier ledgers. Sales means INVOICE for a
  customer debit; Purchase means BILL for a supplier credit. Opposite balances
  explicitly use ADVANCE or CREDIT_NOTE. Different directions are never netted.
- Each bill captures reference, type, original amount, pending amount, bill date
  and due date. Pending must be positive and no larger than original. Both dates
  are real entered dates; bill date precedes opening and due date does not precede
  bill date. No fake due date or settled-history posting is created.
- The bill-wise opening amount is the exact sum of pending amounts. At most 200
  bills per new account. Bill-only fields disappear in the simple view.
- Simple party openings use the existing ON_ACCOUNT document convention, without
  invented invoice dates. General accounts have no party documents. Foreign fixed
  currency accounts require entered rate and historical carrying values through
  conditional extra controls; base-currency entry stays at the three main controls.
- Creation stores immutable held evidence for later inclusion in the balanced
  company opening worksheet. It posts no journal and inserts no balancing plug.
  Original bill amount is retained evidence; only pending amount becomes opening.
- Existing party imports and their held balances remain supported. A dedicated
  account-scoped held entry stores multiple documents for new manual creations,
  rather than changing the one-document party-import contract.
- Party, ledger and opening capture share one transaction and idempotency receipt.
  General account creation retains its native lifecycle. Capture requires current
  finance and native field write authority; replay and reads recheck authority.
- No financial creation draft is stored in browser persistence. Editing a posted
  opening remains in the existing journal/revision workflow.

## Delivery and review record

All four phases are implemented. The Party wizard has an optional fourth step;
Account creation has an optional final opening step. Purchase quick supplier and
expense-account drawers reveal the same editor through an optional checkbox.
Balance-only starts with three controls. Bill-wise entry keeps one editor visible,
shows native Sales/Purchase or advance/credit-note types, and totals pending values
with exact integer decimal arithmetic. Committed bills become compact cards on
phones. Account details show saved opening status and a worksheet link. The company
worksheet offers individually selected, bounded, paginated creation openings beside
the existing import openings, and retains every original bill amount/date.

Capture uses company books-begin date, allows pre-opening preparation while the
period is still FUTURE, and is held for review. Finalized/closed books, inventory
control openings, unavailable native fields and incorrect dates are refused.
Inventory remains in the stock opening workflow. Activation, balancing, native
preview, preparation, posting and finalization retain their existing checks.

Database/model/script/readiness head is Accounting 0230 with 147 model tables.
The restored-data native rehearsal passed 38 API/domain tests, exact scoped capture,
rollback, two populated tenants, cursor isolation, native worksheet inclusion,
immutable evidence, safe replay and withdrawal. Empty-table downgrade/upgrade and
populated-table downgrade refusal passed. Live upgrade preserved existing table
counts and runtime grants; the new table is empty. Owned API/posting-delivery
processes were restored and live/ready health are 200. See
[schema synchronization](local-schema-sync.md) for private evidence location.

Validation: 27 balance-domain tests with 100% line/branch coverage; 64 backend
regressions passed with one pre-existing skip, plus three capture-guard checks; 262 Console
regressions across creation, quick creation, worksheet, account actions and proxy;
2306 shared UI tests; Console/shared TypeScript; affected Python Ruff and strict
mypy (273 source files); OpenAPI/Accounting SDK regeneration and offline frozen
lockfile install. Client is 0.2.58 and shared UI 0.1.52. Native browser verification
covers both opening modes at 1440/768/390/320 widths in light/dark/ledger themes,
with keyboard focus, visible pending values/totals and 200% zoom.

Manual security and simplification reviews covered transaction scope, money types,
changed-field authority, receipt retries, account/tenant ownership, immutable audit
evidence, native posting boundaries and bounded lists. Review fixes included native
bill-output typing, exact carrying-value normalization, current withdrawal versions,
party bill permissions, unsaved bill protection, mobile bill cards and step-label
wrapping. The slash-command review tools are not installed in this environment;
the equivalent checks were performed manually. No critical finding remains in the
delivered opening flow. Existing unrelated Reports release-gate failures remain
separate and no release activation was changed.
