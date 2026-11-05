# Activities logging completeness — 2026-10-30

Authorized: inspect activity recording and coverage, fix demonstrated bugs/gaps,
and retain reusable evidence. Activities remains a safe projection of native audit
events; infrastructure/integration logs are separate documented surfaces.

1. Inventory implemented write workflows and declared event contracts across the
   services. Trace transaction/outbox, publisher, broker consumer, native reads,
   company scope and Console projection. Record coverage and demonstrated gaps.
2. Add fail-first regressions and fix missing or misprojected activity evidence,
   pagination/read failures and confirmed emission/delivery defects. Regenerate
   API clients if the response contract changes. Preserve concurrent local-auth
   implementation; do not alter its unfinished workflows without coordination.
3. Run affected producer/consumer/API/UI tests, type/lint checks and an integrated
   deterministic emission-to-feed rehearsal. Review security/correctness and
   simplification, fix remaining findings, update docs/TODO and results CSV.

- [x] Coverage inventory and findings.
- [x] Recording/delivery/read/display corrections and regression tests.
- [x] Verification, final review and reusable results.
- [!] Live VM/broker/MySQL delivery verification was not available in this run.

Completed implementation and isolated checks: see
[review](activity-logging-completeness-review.md),
[findings/cases](testing/tenant-admin/activity-logging-completeness-results.csv)
and [service coverage](testing/tenant-admin/activity-logging-service-coverage.csv).

Live VM/broker/MySQL checks require running services; they will be distinguished
from deterministic isolated tests. No direct application-database manipulation.
