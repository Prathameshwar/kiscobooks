# Bank reconciliation implementation review — 2026-10-13

The selected mapped-CSV bank reconciliation path is implemented through Accounting, Reports,
Identity permissions and the console. Accounting owns immutable mapping/import/row, bank-match,
opening, policy, session and adjustment-proposal evidence. Import, matching, clearing and
proposal commands are non-posting. Only the existing voucher/journal posting path can change
GL or party balances. A bank statement row can resolve a correction proposal only after a
committed voucher intent has produced a matching bank instrument and the instrument is matched
to that row.

## Review pass 1 — contracts and owner safety

- Confirmed tenant/company fences, fixed bank-account currency, reviewed duplicate decisions,
  exact debit/credit direction and allocation caps. A correction proposal records only the
  unmatched bank-row remainder and resolves only when its posted voucher covers that amount.
  Added an explicit match preview and
  history, import listing/detail/rejection, a bank-only adjustment proposal flow and the
  missing bank-specific field-policy permission mapping for proposals.
- Confirmed sessions cannot finalize from a zero net difference alone: every accepted bank row
  must be covered, unreviewed duplicates and uncovered posted bank lines block finalization,
  and book-versus-bank balances must agree at the same account currency.
- Added a Reports read-denial guard so bank evidence/worklist artifacts cannot disclose source
  fields hidden by an Accounting field policy. The original balance-only report is explicitly
  labelled manual; the final-session report rechecks source facts.

## Review pass 2 — history, fiscal boundaries and operator workflow

- Repaired pre-cutover manual clearance treatment: it is not an opening uncleared item, stays
  cleared across later periods, appears separately in frozen report evidence, and cannot also
  consume a new statement match. Late historical bank evidence requires amendment of a frozen
  session.
- Blocked overlapping/future finalized bank-session chains and backdated bank journal posting
  into a finalized bank period. A new CSV export overlapping a committed period remains
  previewable for duplicate review but cannot join the committed balance chain.
- Added grouped-allocation preview/commit, opening-item and proposal controls, session history
  and amendment, and an operational Reports worklist for bank-only, book-only, partial, manual
  evidence and reconciled-later rows with dated aging. Read-only roles cannot see mutation
  controls. Evidence and worklist residuals aggregate match events once per generation, rather
  than rescanning every allocation for every source row.

## Verification and release state

The native MySQL 9.6 verifier applied revisions `0138`–`0145` and passed a complete
downgrade/upgrade round trip. Focused Accounting bank/CSV/match and money tests, the Reports
suite, strict Accounting and Reports typing, Ruff on changed sources, generated OpenAPI/client
checks, console typecheck and console tests passed. Native MySQL concurrent same-file import
and competing bank-match tests passed. The full Accounting suite passed with 708 passed,
15 skipped and one non-failing runtime warning. This result covers the reconciliation changes;
the subsequent account-list additions received focused regression tests separately.

B43 stays `IN_PROGRESS`. The upstream B19 issue gate is still `PLANNED`, and AC27 still needs a
broker replay rehearsal. The implemented path does not
claim live bank connectivity, every CSV layout, auto-matching commit, automatic voucher posting
or an enabled production release flag.
