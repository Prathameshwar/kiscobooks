# Product creation conflict recovery

User report, 2026-10-31: creating a product repeatedly reports a changed
configuration or a busy idempotent request while retaining an unfinished draft.

## Delivery phases

1. Reproduce with fail-first tests and inspect the running product form without
   writing diagnostic products. Keep current authorization and configuration guards.
2. Match configuration resolution to the setup effective date even when no group
   is selected. Keep the existing explicit review action and preserve draft values.
3. Give aggregate product creation 30 seconds to finish its atomic transaction;
   allow 45 seconds at the console boundary. Other requests retain their budgets.
   Retry only the exact busy conflict, at most twice, with the identical body and
   idempotency key. Respect cancellation. Other conflicts still require review.
4. Verify bounded retries, cancellation, field/context refresh, replay, rollback,
   authorization and actual creation. Review CLAUDE.md sections 5 and 6 manually
   because the named review skills are unavailable in this session.

Native Accounting regressions independently reproduced the same ten-second
timeout during initial chart provisioning, before any party or tax work. Give
that bounded, idempotent setup command 30 seconds as well, and its company-setup
proxy 45 seconds. All other Accounting command budgets stay unchanged.

The shared idempotency implementation rolls back timed-out transactions. It does
not leave a committed in-progress reservation after a timeout. Completed requests
still replay through current authorization, and a lost response retains its key.

## Verification

Fail-first tests reproduced the date/context mismatch and missing busy recovery.
The focused client/proxy/configuration suite passed 69 tests, including bounded
same-key retries and cancellation. Fourteen backend initial-product tests passed,
covering atomic rollback, signed configuration, authorization and idempotency.
Catalog Ruff and strict mypy checks passed; Console TypeScript passed. Live
creation returned 201; replaying the exact key/body returned the same product ID,
and querying its code found exactly one product. Product defaults were not replaced
by a new key or duplicate creation during recovery.

Manual CLAUDE.md sections 5/6 review found no additional issues: configuration
review remains explicit; the submitted body/key are retained; retries apply only
to the exact busy response; current authorization governs replay. Neither shared
idempotency semantics nor tenant/company, audit or transaction boundaries changed.

The matching company/product proxy and company policy suites passed 148 tests;
the longer timeout applies only to initial chart provisioning. Full Console
TypeScript and Accounting command Ruff/strict mypy checks passed. All four local
Identity/Catalog/Accounting/Vouchers services returned ready after their updates.
The native MySQL Accounting tax/domain/optional-start suite passed all 46 tests,
with 94.94% domain coverage. Initial chart provisioning no longer hit the reproduced
ten-second timeout. Upgrade, empty downgrade and the refusal to downgrade existing
NULL tax starts also passed; the disposable test database was cleaned up.
