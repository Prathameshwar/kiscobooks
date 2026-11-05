# Openings entered during master creation

Decision, 2026-11-04: the user requires an opening entered while creating an account,
buyer or supplier to be posted by that creation action, without another worksheet,
approval or posting action. This supersedes the earlier held-only creation decision.

1. Add regression evidence for immediate posting, exact balancing and outstanding
   bills, repeated account creation, permissions, period restrictions and interrupted
   posting retries.
2. Create an immutable master opening and its native opening batch/journal together.
   Balance against the configured opening-balance offset account, at books begin.
   Post through the existing journal authorization/commit protocol after that local
   transaction. Return creation success only after posting and Identity confirmation.
   A retry of the same creation continues its existing journal.
3. Update the creation and detail experience to describe automatic posting and show
   completed openings without a worksheet handoff. Regenerate contracts and validate.

Each new master has its own additive opening batch. These batches do not replace or
hide the company worksheet. A previously finalized company opening does not prevent
an opening for a newly created account; closed-period and later-closed-books guards
still apply. The worksheet cannot include an already posting/posted master opening.
Existing held imports and older held master openings retain their review workflow.
An account created with an opening is activated as part of the creation transaction.
No opening supplied means the existing creation lifecycle remains unchanged.

Money execution continues to use native ledger/subledger writers, current scoped
permissions, exact decimals, company locking, audit and durable terminal delivery.
No real-company postings are used for verification.

Account creation accepts optional `bank_profile` and `tax_profile` objects. When an
opening is supplied, the matching profile is captured in the same transaction before
activation, avoiding a later profile-completion step. Native profile validation and
permissions remain in force. The UI reveals these fields alongside the opening.

Migration 0234 expands only the master opening status check. New records progress
from POSTING to POSTED with the native GL/subledger commit; native reversal records
REVERSED. Existing PENDING/WITHDRAWN evidence remains compatible. Downgrade refuses
to discard posting evidence.

Verification (2026-11-04):

- 15 native MySQL posting/period cases passed, including customer/supplier Dr/Cr,
  exact four-place GL and open-item amounts, posted/native reversal lineage,
  repeated creation, permissions, unsafe offset rollback, bank profiles,
  reserve/terminal outages and same-command recovery. Migration upgrade, empty
  downgrade/re-upgrade and refusal to downgrade posted evidence passed.
- 12 capture/legacy-held API cases passed; 27 domain cases and the reversal case
  passed. Company opening API regression: 12 passed, one MySQL-specific case skipped
  by that SQLite run. The closed-books case passes after the terminal delivery fix.
- Creation/editor/quick-create checks passed (122 initial checks, followed by the
  new posted/pending summary and profile cases). All 52 party wizard cases passed;
  two timed out under parallel browser load and passed with a 20-second test limit.
- Browser checks cover supplier balance/bills and GENERAL/BANK/TAX creation at
  1440, 768, 390 and 320 pixels in light, dark and ledger themes. No horizontal
  clipping; keyboard focus and actions remain visible.
- OpenAPI/client freshness, client and Console TypeScript, strict backend typing,
  lint and whitespace checks passed. API client version is 0.2.69.

Focused simplicity/security review found and fixed incomplete local confirmation
delivery, duplicate inclusion through the legacy opening endpoint, and missing
inline bank/tax profiles. Current permissions and account/offset identities are
checked before posting; confirmed terminal delivery is acknowledged with explicit
tenant/company/operation predicates. No unresolved implementation findings remain.

Local activation completed (2026-11-04): Accounting advanced from 0233 to 0234.
All 147 tables match the models, migration scripts and readiness inventory; native
schema comparison has zero differences and the Alembic check passes. The existing
opening record retains every original value, verified by before/after hashes.
Accounting and its previously running publisher and posting-delivery workers were
restarted. Live and readiness probes return 200, and the served creation contract
includes the posting statuses and inline bank/tax profiles. Administrator input
was used only in memory; runtime credentials and grants are unchanged. Existing
live balances were not posted for verification.
