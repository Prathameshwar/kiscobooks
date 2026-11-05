# reporting-contract

Shared version 0.7.0 Accounting-to-Reports export contract. No service ORM imports.

The v1 manifest pins tenant/company, schema hash, snapshot/change identity, committed
sequence, owner generation, scope/grant fingerprint, source counts, coverage and base
controls. Nineteen native fact grains cover the financial owner, including money intent
lineage, allocation links, bank instruments and append-only instrument events. Facts carry
identity/content hashes; absence of a required field is an incompatibility, not permission
to infer zero. Native amounts are decimal strings (19,4); FX rates retain 19,8 precision.

The transport uses billing-platform's requester/owner-bound HMAC request/response helpers,
explicit scoped credentials, HTTPS origins, no redirects and a 1 MiB response bound.
Accounting exports private immutable pages; Reports stages and reconciles them. Wire
schema changes require compatible owner/consumer deployment or a new explicitly supported
contract. The manifest schema hash changes with the Phase 2 fact catalogue. Deploy matching
owner/consumer packages and create a fresh generation; an old snapshot cannot be silently
treated as containing missing banking facts. Already frozen report outputs remain readable
subject to current authorization. Neither version was deployed by this implementation.

Tests live at the owner and consumer boundaries: Accounting tests/test_reporting_feed.py,
Reports tests/test_worker.py and tests/test_domain.py, plus platform signing tests.
Historical coverage means retained ledger from books-begin; it does not invent pre-cutover
YTD or historical classifications that the owner did not retain.

Version 0.7.0 adds optional position valuation detail: residual FIFO layer allocations or
the position's share of a moving-average pool. Quantity/value must reconcile exactly to
the owned position. Reports can display those allocations alongside retained immutable
value-adjustment movements. Missing detail is explicit; detailed valuation cannot infer it.
See [inventory report contract fixes](../../docs/reports-framework/inventory-review-fixes.md).
Deploy matching packages and start a fresh source epoch for the new schema. Existing
0.6.0 inventory and legacy financial manifest hashes remain supported for reads.

Version 0.14.0 adds signed, paginated report-purpose enrollment discovery.
Installation credentials opt in explicitly; each owner verifies current Identity
enrollment for the requested tenant/company. Collection excludes inactive companies;
retained-report authority also checks current actor grants and field denials. Static
scopes remain supported. See [automatic readiness delivery](../../docs/company-automatic-readiness-delivery.md).
